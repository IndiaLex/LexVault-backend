"""
app/routers/custody.py
----------------------
Custody log and case history graph endpoints.

Phase B1: stubs.
Phase B4: real graph construction from DB events.

Endpoints:
  GET /cases/:case_id/graph            -> GraphResponse
  GET /cases/:case_id/custody-log      -> CustodyLogResponse

Graph contract (for Frontend team):
  - nodes[].lane = document_id (one horizontal lane per document in dagre)
  - nodes[].type = CustodyEventType string (see contracts/enums.py)
  - nodes[].hash = SHA-256 event hash (clicking -> on-chain verify)
  - nodes[].anchored = true if part of a confirmed AnchorBatch
  - edges[].from / edges[].to = sequential node ids within the same lane
  - Cross-lane edges added for TRANSFERRED events
  Layout is handled by the frontend (dagre, rankdir: LR).
  This endpoint supplies topology + semantics only.
"""

from fastapi import APIRouter, Depends
from datetime import datetime, timezone

from app.schemas.custody import GraphResponse, GraphNode, GraphEdge, CustodyLogResponse, CustodyEventResponse
from app.services.rbac import get_current_user

router = APIRouter()


@router.get(
    "/cases/{case_id}/graph",
    response_model=GraphResponse,
    summary="Get the visual case history graph",
)
def get_case_graph(case_id: str, current_user=Depends(get_current_user)):
    """
    Returns the full DAG (directed acyclic graph) of custody events for a case.

    Each document in the case becomes a lane (horizontal track).
    Each custody event becomes a node on that lane.
    Sequential events within a lane are connected by edges.

    Poll this endpoint every 3 seconds (or use WebSocket in Phase 6) to
    see new nodes appear as AI processing and anchoring complete.

    [STUB - Phase B1] Returns a hardcoded 3-node graph to let the
    Frontend team build their graph renderer against a real response shape.
    """
    stub_ts = datetime.now(timezone.utc).isoformat()
    stub_hash = "a" * 64

    nodes = [
        GraphNode(
            id="node-001", lane="doc-stub-001", type="UPLOADED",
            label="Document Uploaded", actor="Inspector Sharma",
            timestamp=stub_ts, hash=stub_hash,
            anchored=False, tags=[],
        ),
        GraphNode(
            id="node-002", lane="doc-stub-001", type="OCR_COMPLETE",
            label="OCR Complete", actor="AI Service",
            timestamp=stub_ts, hash="b" * 64,
            anchored=False, tags=[],
        ),
        GraphNode(
            id="node-003", lane="doc-stub-001", type="REDACTED",
            label="Redacted", actor="AI Service",
            timestamp=stub_ts, hash="c" * 64,
            anchored=True, tags=["Redacted", "Sealed"],
        ),
    ]
    edges = [
        GraphEdge(**{"from": "node-001", "to": "node-002"}),
        GraphEdge(**{"from": "node-002", "to": "node-003"}),
    ]
    return GraphResponse(nodes=nodes, edges=edges)


@router.get(
    "/cases/{case_id}/custody-log",
    response_model=CustodyLogResponse,
    summary="Get the flat chronological custody log",
)
def get_custody_log(
    case_id: str,
    type: str = None,
    current_user=Depends(get_current_user),
):
    """
    Returns all custody events for a case as a flat chronological list.
    This is the court-friendly audit view (as opposed to the visual graph).

    Query params:
      - type: filter by CustodyEventType (e.g. ?type=ANCHORED)

    Records a ACCESSED custody event for audit purposes.

    [STUB - Phase B1]
    """
    stub_ts = datetime.now(timezone.utc)
    events = [
        CustodyEventResponse(
            id="event-stub-001", case_id=case_id,
            document_id="doc-stub-001", type="UPLOADED",
            actor="Inspector Sharma", timestamp=stub_ts,
            hash="a" * 64, anchored=False, tags=[],
        )
    ]
    return CustodyLogResponse(events=events, total=len(events))
