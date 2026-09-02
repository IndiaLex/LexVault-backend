from app.models.user import User
from app.models.case import Case
from app.models.document import Document
from app.models.document_version import DocumentVersion
from app.models.custody_event import CustodyEvent
from app.models.anchor_batch import AnchorBatch
from app.models.ai_analysis import AIAnalysis
from contracts.enums import Role, CaseStatus, AnchorBatchStatus


def test_user_model():
    user = User(
        username="test_user",
        password_hash="hashed_password",
        name="Test User",
        role=Role.OFFICER.value,
    )
    assert user.username == "test_user"
    assert user.role == Role.OFFICER.value


def test_case_model():
    case = Case(
        title="Test Case",
        status=CaseStatus.OPEN.value,
        created_by="user-123",
    )
    assert case.title == "Test Case"
    assert case.status == CaseStatus.OPEN.value


def test_document_model():
    doc = Document(
        case_id="case-123",
        filename="test.pdf",
        storage_key="case-123/abc123_test.pdf",
        sha256="abc123def456",
        mime="application/pdf",
        size=1024,
        uploaded_by="user-123",
        current_version=1,
    )
    assert doc.filename == "test.pdf"
    assert doc.current_version == 1


def test_anchor_batch_model():
    batch = AnchorBatch(
        merkle_root="0xabc123",
        tx_hash="0xdef456",
        chain_id="80001",
        status=AnchorBatchStatus.PENDING.value,
    )
    assert batch.status == AnchorBatchStatus.PENDING.value
    assert batch.chain_id == "80001"
