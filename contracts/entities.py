from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime


class RedactionBox(BaseModel):
    page: int
    x: float
    y: float
    width: float
    height: float
    reason: str
    confidence: float
    entity_id: str


class Entity(BaseModel):
    entity_id: str
    text: str
    label: str
    start_char: int
    end_char: int
    page: int
    confidence: float


class ProcessRequest(BaseModel):
    document_id: str
    storage_key: str


class AIResult(BaseModel):
    document_id: str
    ocr_text: str
    entities: List[Entity]
    redaction_boxes: List[RedactionBox]
    doc_class: str
    confidence: float
    needs_review: bool
    review_count: int


class AnchorSubmitRequest(BaseModel):
    hashes: List[str]


class AnchorBatchResponse(BaseModel):
    batch_id: str
    status: str
    chain_id: Optional[str] = None


class AnchorStatusResponse(BaseModel):
    batch_id: str
    status: str
    merkle_root: Optional[str] = None
    tx_hash: Optional[str] = None
    block_number: Optional[int] = None


class AnchorVerifyResponse(BaseModel):
    valid: bool
    merkle_root: Optional[str] = None
    tx_hash: Optional[str] = None
    proof: List[str] = []
    explorer_url: Optional[str] = None
