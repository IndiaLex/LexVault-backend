import hashlib
import json
from typing import List, Optional
from sqlalchemy.orm import Session
from app.models.custody_event import CustodyEvent
from app.models.document import Document
from contracts.enums import CustodyEventType


def compute_event_hash(
    case_id: str,
    document_id: Optional[str],
    event_type: str,
    actor_id: str,
    metadata: dict,
) -> str:
    canonical = json.dumps(
        {
            "case_id": str(case_id),
            "document_id": str(document_id) if document_id else None,
            "type": event_type,
            "actor_id": str(actor_id),
            "metadata": metadata,
        },
        sort_keys=True,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()


def record_event(
    db: Session,
    case_id: str,
    event_type: str,
    actor_id: str,
    document_id: Optional[str] = None,
    metadata: Optional[dict] = None,
    anchor_batch_id: Optional[str] = None,
) -> CustodyEvent:
    event_hash = compute_event_hash(
        case_id=case_id,
        document_id=document_id,
        event_type=event_type,
        actor_id=actor_id,
        metadata=metadata or {},
    )
    event = CustodyEvent(
        case_id=case_id,
        document_id=document_id,
        type=event_type,
        actor_id=actor_id,
        event_metadata=metadata or {},
        event_hash=event_hash,
        anchor_batch_id=anchor_batch_id,
    )
    db.add(event)
    db.flush()
    return event


EVENT_LABELS = {
    CustodyEventType.UPLOADED.value: "Document Uploaded",
    CustodyEventType.OCR_COMPLETE.value: "OCR Complete",
    CustodyEventType.NER_COMPLETE.value: "NER Complete",
    CustodyEventType.REDACTED.value: "Redacted",
    CustodyEventType.ANCHORED.value: "Anchored on-chain",
    CustodyEventType.VERIFIED.value: "Verified",
    CustodyEventType.TRANSFERRED.value: "Transferred",
    CustodyEventType.ACCESSED.value: "Accessed",
    CustodyEventType.ACCESS_DENIED.value: "Access Denied",
    CustodyEventType.DOWNLOADED.value: "Downloaded",
    CustodyEventType.VERSION_CREATED.value: "Version Created",
}


def compute_tags(event: CustodyEvent) -> List[str]:
    tags = []
    if event.type == CustodyEventType.ANCHORED.value:
        tags.append("Sealed")
    if event.type == CustodyEventType.REDACTED.value:
        tags.append("Redacted")
    if event.type == CustodyEventType.ACCESS_DENIED.value:
        tags.append("Denied")
    if event.type == CustodyEventType.VERIFIED.value:
        result = (event.event_metadata or {}).get("result")
        if result == "pass":
            tags.append("Verified")
        elif result == "fail":
            tags.append("Failed")
    return tags


def build_graph(events: List[CustodyEvent]) -> dict:
    nodes = []
    edges = []
    lanes: dict = {}

    for e in sorted(events, key=lambda x: x.timestamp):
        node = {
            "id": str(e.id),
            "lane": str(e.document_id) if e.document_id else "case",
            "type": e.type,
            "label": EVENT_LABELS.get(e.type, e.type),
            "actor": e.actor.name if e.actor else "Unknown",
            "timestamp": e.timestamp.isoformat(),
            "hash": e.event_hash,
            "anchored": e.anchor_batch_id is not None,
            "tags": compute_tags(e),
        }
        nodes.append(node)
        lane_key = str(e.document_id) if e.document_id else "case"
        if lane_key in lanes and lanes[lane_key]:
            prev_id = lanes[lane_key][-1]
            curr_id = str(e.id)
            edges.append({
                "id": f"edge-{prev_id}-{curr_id}",
                "from": prev_id,
                "to": curr_id,
                "source": prev_id,
                "target": curr_id,
            })
        lanes.setdefault(lane_key, []).append(str(e.id))

    return {"nodes": nodes, "edges": edges}
