"""
app/schemas/custody.py
----------------------
Pydantic schemas for the custody log and case history graph.

IMPORTANT for Frontend team:
  GET /cases/:id/graph returns GraphResponse.
  - nodes[].lane  = document_id (one lane per document in the graph).
  - nodes[].type  = CustodyEventType string (see contracts/enums.py).
  - nodes[].hash  = SHA-256 event hash (click -> verify on-chain).
  - nodes[].anchored = true means this event is part of a confirmed batch.
  - edges[].from / edges[].to = node ids, ordered chronologically.

The frontend (dagre, rankdir:LR) handles layout; this service supplies
only topology and semantics.
"""

from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Any


class GraphNode(BaseModel):
    id: str
    lane: str                          # document_id, or "case" for case-level events
    type: str                          # CustodyEventType value
    label: str                         # Human-readable, e.g. "Document Uploaded"
    actor: str                         # Name of the user or service that caused it
    timestamp: str                     # ISO 8601
    hash: str                          # event_hash (SHA-256 of canonical event)
    anchored: bool                     # True if part of a confirmed AnchorBatch
    tags: List[str] = []               # e.g. ["Sealed", "Redacted", "Failed"]
    metadata: Optional[Any] = None     # raw event metadata for inspector panel


class GraphEdge(BaseModel):
    id: Optional[str] = None
    source: Optional[str] = None
    target: Optional[str] = None
    from_node: Optional[str] = Field(default=None, alias="from")
    to_node: Optional[str] = Field(default=None, alias="to")

    def __init__(self, **data):
        s = data.get("source") or data.get("from")
        t = data.get("target") or data.get("to")
        data["source"] = s
        data["target"] = t
        data["from"] = s
        data["to"] = t
        if "id" not in data and s and t:
            data["id"] = f"edge-{s}-{t}"
        super().__init__(**data)

    class Config:
        populate_by_name = True


class GraphResponse(BaseModel):
    nodes: List[GraphNode]
    edges: List[GraphEdge]


class CustodyEventResponse(BaseModel):
    """Used by GET /cases/:id/custody-log — the flat court-friendly view."""
    id: str
    case_id: str
    document_id: Optional[str]
    type: str
    actor: str                   # resolved name, not raw actor_id
    timestamp: datetime
    hash: str
    anchored: bool
    tags: List[str] = []
    metadata: Optional[Any] = None

    class Config:
        from_attributes = True


class CustodyLogResponse(BaseModel):
    events: List[CustodyEventResponse]
    total: int
