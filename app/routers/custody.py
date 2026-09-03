"""
app/routers/custody.py
----------------------
Custody log and case history graph endpoints — Phase B4: real DB queries.

Endpoints:
  GET /cases/:case_id/graph            -> GraphResponse
  GET /cases/:case_id/custody-log      -> CustodyLogResponse

Graph contract (for Frontend team):
  - nodes[].lane  = document_id (one horizontal lane per document in dagre)
                    "case" for case-level events with no document_id
  - nodes[].type  = CustodyEventType string (see contracts/enums.py)
  - nodes[].hash  = SHA-256 of the canonical event JSON (tamper-evident)
  - nodes[].anchored = true if part of a confirmed AnchorBatch
  - nodes[].metadata = raw event metadata for the inspector panel
  - edges[].from / edges[].to = sequential node ids within the same lane
  Layout is handled by the frontend (dagre, rankdir: LR).
  This endpoint supplies topology + semantics only.

Custody log contract (court-friendly flat view):
  - Ordered chronologically (oldest first).
  - ?type= query param filters by CustodyEventType value (e.g. ANCHORED).
  - actor field is the resolved user name, not the raw actor_id UUID.

Both endpoints return 404 if the case does not exist.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from typing import Optional

from app.database import get_db
from app.models.case import Case
from app.models.custody_event import CustodyEvent
from app.models.user import User
from app.schemas.custody import (
    GraphResponse, GraphNode, GraphEdge,
    CustodyLogResponse, CustodyEventResponse,
)
from app.services.custody_service import build_graph, compute_tags, EVENT_LABELS
from app.services.rbac import get_current_user

router = APIRouter()


# ---------------------------------------------------------------------------
# Graph endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/cases/{case_id}/graph",
    response_model=GraphResponse,
    summary="Get the visual case history graph",
)
def get_case_graph(
    case_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns the full DAG (directed acyclic graph) of all custody events
    for a case, built from the live database.

    Each document in the case becomes a lane (horizontal track in dagre).
    Each custody event becomes a node on that lane.
    Sequential events within the same lane are connected by directed edges.

    Poll this endpoint every 3 seconds to see new nodes appear as AI
    processing (OCR_COMPLETE, NER_COMPLETE, REDACTED) and anchoring
    (ANCHORED) complete in the background.

    Raises 404 if the case does not exist.
    """
    # Verify case exists
    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    # Load all custody events for this case, eager-loading actor relationship
    events = (
        db.query(CustodyEvent)
        .filter(CustodyEvent.case_id == case_id)
        .order_by(CustodyEvent.timestamp.asc())
        .all()
    )

    # Build graph topology using custody_service.build_graph()
    graph_dict = build_graph(events)

    # Convert raw dicts to Pydantic schema objects
    nodes = [
        GraphNode(
            id=n["id"],
            lane=n["lane"],
            type=n["type"],
            label=n["label"],
            actor=n["actor"],
            timestamp=n["timestamp"],
            hash=n["hash"],
            anchored=n["anchored"],
            tags=n["tags"],
            metadata=next(
                (e.event_metadata for e in events if str(e.id) == n["id"]),
                None,
            ),
        )
        for n in graph_dict["nodes"]
    ]

    edges = [
        GraphEdge(**{"from": edge["from"], "to": edge["to"]})
        for edge in graph_dict["edges"]
    ]

    return GraphResponse(nodes=nodes, edges=edges)


# ---------------------------------------------------------------------------
# Custody log endpoint
# ---------------------------------------------------------------------------

@router.get(
    "/cases/{case_id}/custody-log",
    response_model=CustodyLogResponse,
    summary="Get the flat chronological custody log",
)
def get_custody_log(
    case_id: str,
    type: Optional[str] = Query(
        default=None,
        description="Filter by CustodyEventType (e.g. ANCHORED, UPLOADED, REDACTED)",
    ),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """
    Returns all custody events for a case as a flat chronological list.
    This is the court-friendly audit view (as opposed to the visual graph).

    Query params:
      - type: filter by CustodyEventType value (e.g. ?type=ANCHORED)
              Multiple values not supported; use one filter per request.

    actor field is the resolved user full name (not raw UUID).
    anchored=true means the event is part of a confirmed AnchorBatch.

    Raises 404 if the case does not exist.
    """
    # Verify case exists
    case = db.query(Case).filter(Case.id == case_id).first()
    if case is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Case '{case_id}' not found",
        )

    # Build query
    query = (
        db.query(CustodyEvent)
        .filter(CustodyEvent.case_id == case_id)
        .order_by(CustodyEvent.timestamp.asc())
    )

    # Apply optional type filter
    if type is not None:
        query = query.filter(CustodyEvent.type == type)

    events = query.all()

    # Build response list — resolve actor name from relationship
    event_responses = []
    for e in events:
        actor_name = e.actor.name if e.actor else "Unknown"
        event_responses.append(
            CustodyEventResponse(
                id=str(e.id),
                case_id=str(e.case_id),
                document_id=str(e.document_id) if e.document_id else None,
                type=e.type,
                actor=actor_name,
                timestamp=e.timestamp,
                hash=e.event_hash,
                anchored=e.anchor_batch_id is not None,
                tags=compute_tags(e),
                metadata=e.event_metadata,
            )
        )

    return CustodyLogResponse(events=event_responses, total=len(event_responses))
