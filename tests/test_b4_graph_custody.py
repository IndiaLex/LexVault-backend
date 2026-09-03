"""
tests/test_b4_graph_custody.py
-------------------------------
Phase B4 integration tests: Case history graph + Custody log endpoints.

Requirements verified:
  - GET /cases/:id/graph        -> real DB events, correct node/edge shape
  - GET /cases/:id/graph        -> 404 for unknown case
  - GET /cases/:id/graph        -> empty graph for case with no documents
  - GET /cases/:id/graph        -> nodes populated after upload (UPLOADED event)
  - GET /cases/:id/graph        -> node fields: id, lane, type, label, actor,
                                   timestamp, hash (64-char hex), anchored, tags
  - GET /cases/:id/custody-log  -> chronological flat list
  - GET /cases/:id/custody-log  -> 404 for unknown case
  - GET /cases/:id/custody-log  -> ?type= filter returns only matching events
  - GET /cases/:id/custody-log  -> actor is resolved name, not UUID
  - GET /cases/:id/custody-log  -> hash is 64-char hex string
  - Unauthenticated access returns 401

All tests run against the live local service (http://localhost:8000).
Server must be running: python -m uvicorn app.main:app --port 8000
"""

import io
import uuid
import pytest
import httpx

BASE_URL = "http://localhost:8000"


# ---------------------------------------------------------------------------
# Auth fixture
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def auth_headers():
    resp = httpx.post(
        f"{BASE_URL}/auth/login",
        json={"username": "demo_officer", "password": "password123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    token = resp.json()["access_token"]
    return {"Authorization": f"Bearer {token}", "X-Bypass-Rate-Limit": "true"}


# ---------------------------------------------------------------------------
# Helpers: create a real case + upload a real document
# ---------------------------------------------------------------------------

def create_case(auth_headers, title="B4 Test Case") -> str:
    resp = httpx.post(
        f"{BASE_URL}/cases",
        json={"title": title},
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Case creation failed: {resp.text}"
    return resp.json()["id"]


def upload_doc(auth_headers, case_id: str, filename="b4_test.pdf") -> str:
    resp = httpx.post(
        f"{BASE_URL}/cases/{case_id}/documents",
        headers=auth_headers,
        files={"file": (filename, io.BytesIO(b"%PDF-1.4 B4 test content"), "application/pdf")},
    )
    assert resp.status_code == 201, f"Upload failed: {resp.text}"
    return resp.json()["document_id"]


# ---------------------------------------------------------------------------
# Graph tests
# ---------------------------------------------------------------------------

class TestGraph:

    def test_graph_404_unknown_case(self, auth_headers):
        """GET /cases/fake/graph -> 404."""
        fake_id = str(uuid.uuid4())
        resp = httpx.get(f"{BASE_URL}/cases/{fake_id}/graph", headers=auth_headers)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_graph_empty_case(self, auth_headers):
        """GET /cases/:id/graph for a case with no documents -> empty nodes/edges."""
        case_id = create_case(auth_headers, "B4 Empty Case Graph")
        resp = httpx.get(f"{BASE_URL}/cases/{case_id}/graph", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert "nodes" in body
        assert "edges" in body
        assert isinstance(body["nodes"], list)
        assert isinstance(body["edges"], list)
        assert len(body["nodes"]) == 0
        assert len(body["edges"]) == 0

    def test_graph_has_uploaded_node_after_upload(self, auth_headers):
        """After uploading a doc, graph must contain an UPLOADED node."""
        case_id = create_case(auth_headers, "B4 Graph After Upload")
        upload_doc(auth_headers, case_id)

        resp = httpx.get(f"{BASE_URL}/cases/{case_id}/graph", headers=auth_headers)
        assert resp.status_code == 200
        nodes = resp.json()["nodes"]
        assert len(nodes) >= 1

        types = [n["type"] for n in nodes]
        assert "UPLOADED" in types, f"UPLOADED node not found. Types present: {types}"

    def test_graph_node_schema(self, auth_headers):
        """Every node must have all required fields with correct types."""
        case_id = create_case(auth_headers, "B4 Node Schema Check")
        upload_doc(auth_headers, case_id)

        resp = httpx.get(f"{BASE_URL}/cases/{case_id}/graph", headers=auth_headers)
        assert resp.status_code == 200
        nodes = resp.json()["nodes"]
        assert len(nodes) >= 1

        for node in nodes:
            # Required fields
            assert "id" in node,        f"Missing 'id' in node: {node}"
            assert "lane" in node,      f"Missing 'lane' in node: {node}"
            assert "type" in node,      f"Missing 'type' in node: {node}"
            assert "label" in node,     f"Missing 'label' in node: {node}"
            assert "actor" in node,     f"Missing 'actor' in node: {node}"
            assert "timestamp" in node, f"Missing 'timestamp' in node: {node}"
            assert "hash" in node,      f"Missing 'hash' in node: {node}"
            assert "anchored" in node,  f"Missing 'anchored' in node: {node}"
            assert "tags" in node,      f"Missing 'tags' in node: {node}"

            # hash must be a 64-character hex string (SHA-256)
            assert len(node["hash"]) == 64, f"hash is {len(node['hash'])} chars, expected 64"
            assert all(c in "0123456789abcdef" for c in node["hash"]), "hash is not lowercase hex"

            # anchored must be bool
            assert isinstance(node["anchored"], bool)

            # tags must be list
            assert isinstance(node["tags"], list)

    def test_graph_uploaded_node_lane_is_document_id(self, auth_headers):
        """UPLOADED node lane must be the document UUID, not 'case'."""
        case_id = create_case(auth_headers, "B4 Lane Check")
        doc_id = upload_doc(auth_headers, case_id)

        resp = httpx.get(f"{BASE_URL}/cases/{case_id}/graph", headers=auth_headers)
        assert resp.status_code == 200
        nodes = resp.json()["nodes"]

        uploaded = [n for n in nodes if n["type"] == "UPLOADED"]
        assert len(uploaded) >= 1
        assert uploaded[0]["lane"] == doc_id, (
            f"Expected lane={doc_id}, got lane={uploaded[0]['lane']}"
        )

    def test_graph_edges_connect_sequential_events(self, auth_headers):
        """If multiple events exist on the same lane, edges must connect them."""
        case_id = create_case(auth_headers, "B4 Edge Connectivity")
        upload_doc(auth_headers, case_id)

        resp = httpx.get(f"{BASE_URL}/cases/{case_id}/graph", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        nodes = body["nodes"]
        edges = body["edges"]

        # If >1 node on same lane, there must be edges
        if len(nodes) > 1:
            assert len(edges) >= 1, "Multiple nodes but no edges found"
            node_ids = {n["id"] for n in nodes}
            for edge in edges:
                assert edge["from"] in node_ids, f"Edge source {edge['from']} not in nodes"
                assert edge["to"] in node_ids, f"Edge target {edge['to']} not in nodes"

    def test_graph_unauthenticated(self):
        """GET /cases/:id/graph without token -> 401."""
        case_id = str(uuid.uuid4())
        resp = httpx.get(f"{BASE_URL}/cases/{case_id}/graph")
        assert resp.status_code == 401


# ---------------------------------------------------------------------------
# Custody log tests
# ---------------------------------------------------------------------------

class TestCustodyLog:

    def test_log_404_unknown_case(self, auth_headers):
        """GET /cases/fake/custody-log -> 404."""
        fake_id = str(uuid.uuid4())
        resp = httpx.get(f"{BASE_URL}/cases/{fake_id}/custody-log", headers=auth_headers)
        assert resp.status_code == 404
        assert "not found" in resp.json()["detail"].lower()

    def test_log_empty_case(self, auth_headers):
        """Custody log for a case with no events returns empty list."""
        case_id = create_case(auth_headers, "B4 Empty Custody Log")
        resp = httpx.get(f"{BASE_URL}/cases/{case_id}/custody-log", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["events"] == []
        assert body["total"] == 0

    def test_log_has_uploaded_event(self, auth_headers):
        """After upload, custody log must contain an UPLOADED event."""
        case_id = create_case(auth_headers, "B4 Log Has Upload Event")
        upload_doc(auth_headers, case_id)

        resp = httpx.get(f"{BASE_URL}/cases/{case_id}/custody-log", headers=auth_headers)
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] >= 1

        types = [e["type"] for e in body["events"]]
        assert "UPLOADED" in types, f"UPLOADED not found in log types: {types}"

    def test_log_event_schema(self, auth_headers):
        """Every event in the custody log must have all required fields."""
        case_id = create_case(auth_headers, "B4 Log Event Schema")
        upload_doc(auth_headers, case_id)

        resp = httpx.get(f"{BASE_URL}/cases/{case_id}/custody-log", headers=auth_headers)
        assert resp.status_code == 200
        events = resp.json()["events"]
        assert len(events) >= 1

        for event in events:
            assert "id" in event,          f"Missing 'id': {event}"
            assert "case_id" in event,     f"Missing 'case_id': {event}"
            assert "type" in event,        f"Missing 'type': {event}"
            assert "actor" in event,       f"Missing 'actor': {event}"
            assert "timestamp" in event,   f"Missing 'timestamp': {event}"
            assert "hash" in event,        f"Missing 'hash': {event}"
            assert "anchored" in event,    f"Missing 'anchored': {event}"
            assert "tags" in event,        f"Missing 'tags': {event}"

            # hash must be 64-char hex
            assert len(event["hash"]) == 64, f"hash is {len(event['hash'])} chars, expected 64"
            assert all(c in "0123456789abcdef" for c in event["hash"])

            # actor must be a name, not a UUID
            try:
                uuid.UUID(event["actor"])
                assert False, f"actor is a raw UUID, expected a name: {event['actor']}"
            except ValueError:
                pass  # correct — it's a name, not a UUID

            # case_id must match
            assert event["case_id"] == case_id

    def test_log_type_filter(self, auth_headers):
        """?type=UPLOADED returns only UPLOADED events."""
        case_id = create_case(auth_headers, "B4 Log Type Filter")
        upload_doc(auth_headers, case_id)

        resp = httpx.get(
            f"{BASE_URL}/cases/{case_id}/custody-log",
            params={"type": "UPLOADED"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        for event in body["events"]:
            assert event["type"] == "UPLOADED", (
                f"Filter ?type=UPLOADED returned event with type={event['type']}"
            )

    def test_log_type_filter_no_results(self, auth_headers):
        """?type=ANCHORED on a fresh case returns empty list."""
        case_id = create_case(auth_headers, "B4 Log Filter No Results")

        resp = httpx.get(
            f"{BASE_URL}/cases/{case_id}/custody-log",
            params={"type": "ANCHORED"},
            headers=auth_headers,
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["events"] == []
        assert body["total"] == 0

    def test_log_chronological_order(self, auth_headers):
        """Events must be returned in ascending timestamp order."""
        case_id = create_case(auth_headers, "B4 Log Order Check")
        upload_doc(auth_headers, case_id, "b4_order_1.pdf")
        upload_doc(auth_headers, case_id, "b4_order_2.pdf")

        resp = httpx.get(f"{BASE_URL}/cases/{case_id}/custody-log", headers=auth_headers)
        assert resp.status_code == 200
        events = resp.json()["events"]

        timestamps = [e["timestamp"] for e in events]
        assert timestamps == sorted(timestamps), (
            "Custody log is not in ascending chronological order"
        )

    def test_log_unauthenticated(self):
        """GET /cases/:id/custody-log without token -> 401."""
        case_id = str(uuid.uuid4())
        resp = httpx.get(f"{BASE_URL}/cases/{case_id}/custody-log")
        assert resp.status_code == 401
