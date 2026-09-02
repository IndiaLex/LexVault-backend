import sys
import os
import hashlib
import json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.database import get_session_factory, create_all
from app.models import User, Case, Document, DocumentVersion, CustodyEvent, AnchorBatch, AIAnalysis
from app.services.storage_service import get_storage_service
from app.services.custody_service import compute_event_hash
from contracts.enums import Role, CaseStatus, CustodyEventType, AnchorBatchStatus
from passlib.hash import bcrypt


def seed():
    create_all()
    db = get_session_factory()()
    storage = get_storage_service()

    try:
        existing = db.query(User).filter(User.username == "demo_officer").first()
        if existing:
            print("Seed data already exists. Skipping.")
            return

        users = [
            User(
                username="demo_officer",
                password_hash=bcrypt.hash("password123"),
                name="Inspector Sharma",
                role=Role.OFFICER.value,
            ),
            User(
                username="demo_supervisor",
                password_hash=bcrypt.hash("password123"),
                name="SP Gupta",
                role=Role.SUPERVISOR.value,
            ),
            User(
                username="demo_forensic",
                password_hash=bcrypt.hash("password123"),
                name="Dr. Mehta",
                role=Role.FORENSIC.value,
            ),
            User(
                username="demo_auditor",
                password_hash=bcrypt.hash("password123"),
                name="Auditor Patel",
                role=Role.AUDITOR.value,
            ),
            User(
                username="demo_admin",
                password_hash=bcrypt.hash("password123"),
                name="Admin",
                role=Role.ADMIN.value,
            ),
        ]
        db.add_all(users)
        db.flush()

        case = Case(
            title="FIR-2026-0417 — Suspected Financial Fraud at Vertex Corp",
            status=CaseStatus.UNDER_INVESTIGATION.value,
            created_by=users[0].id,
        )
        db.add(case)
        db.flush()

        doc_configs = [
            ("FIR_First_Report.pdf", b"%PDF-1.4 fake-fir-content-001", "application/pdf"),
            ("Witness_Statement_Rahul.pdf", b"%PDF-1.4 fake-witness-statement-002", "application/pdf"),
            ("Medical_Report_Victim.jpg", b"\xff\xd8\xff\xe0 fake-medical-report-003", "image/jpeg"),
            ("Financial_Records_Suspect.png", b"\x89PNG fake-financial-records-004", "image/png"),
        ]

        documents = []
        for filename, content, mime in doc_configs:
            sha256 = hashlib.sha256(content).hexdigest()
            storage_key = storage.upload_file(case.id, filename, content, sha256)

            doc = Document(
                case_id=case.id,
                filename=filename,
                storage_key=storage_key,
                sha256=sha256,
                mime=mime,
                size=len(content),
                uploaded_by=users[0].id,
                current_version=1,
            )
            db.add(doc)
            db.flush()

            version = DocumentVersion(
                document_id=doc.id,
                sha256=sha256,
                storage_key=storage_key,
                created_by=users[0].id,
            )
            db.add(version)
            documents.append(doc)

        db.flush()

        tampered_content = b"%PDF-1.4 TAMPERED-fake-fir-content-001"
        tampered_sha256 = hashlib.sha256(tampered_content).hexdigest()
        storage.upload_file(case.id, "FIR_First_Report_TAMPERED.pdf", tampered_content, tampered_sha256)

        now = datetime.now(timezone.utc)
        anchor_batch = AnchorBatch(
            merkle_root="0x" + hashlib.sha256(b"demo-merkle-root").hexdigest(),
            tx_hash="0x" + hashlib.sha256(b"demo-tx-hash").hexdigest(),
            chain_id="80002",
            status=AnchorBatchStatus.CONFIRMED.value,
            confirmed_at=now - timedelta(hours=1),
        )
        db.add(anchor_batch)
        db.flush()

        events = [
            (CustodyEventType.UPLOADED.value, users[0].id, documents[0].id, {"filename": "FIR_First_Report.pdf"}),
            (CustodyEventType.UPLOADED.value, users[0].id, documents[1].id, {"filename": "Witness_Statement_Rahul.pdf"}),
            (CustodyEventType.UPLOADED.value, users[0].id, documents[2].id, {"filename": "Medical_Report_Victim.jpg"}),
            (CustodyEventType.UPLOADED.value, users[0].id, documents[3].id, {"filename": "Financial_Records_Suspect.png"}),
            (CustodyEventType.OCR_COMPLETE.value, users[0].id, documents[0].id, {"pages": 3}),
            (CustodyEventType.OCR_COMPLETE.value, users[0].id, documents[1].id, {"pages": 2}),
            (CustodyEventType.OCR_COMPLETE.value, users[0].id, documents[2].id, {"pages": 1}),
            (CustodyEventType.OCR_COMPLETE.value, users[0].id, documents[3].id, {"pages": 5}),
            (CustodyEventType.NER_COMPLETE.value, users[0].id, documents[0].id, {"entities_found": 12}),
            (CustodyEventType.NER_COMPLETE.value, users[0].id, documents[1].id, {"entities_found": 8}),
            (CustodyEventType.NER_COMPLETE.value, users[0].id, documents[2].id, {"entities_found": 4}),
            (CustodyEventType.NER_COMPLETE.value, users[0].id, documents[3].id, {"entities_found": 15}),
            (CustodyEventType.REDACTED.value, users[0].id, documents[0].id, {"boxes": 3}),
            (CustodyEventType.REDACTED.value, users[0].id, documents[2].id, {"boxes": 1}),
            (CustodyEventType.ACCESSED.value, users[1].id, documents[0].id, {"action": "view"}),
            (CustodyEventType.ACCESSED.value, users[2].id, documents[2].id, {"action": "view"}),
            (CustodyEventType.ACCESS_DENIED.value, users[3].id, documents[0].id, {"reason": "insufficient_permissions"}),
            (CustodyEventType.DOWNLOADED.value, users[1].id, documents[1].id, {"format": "pdf"}),
            (CustodyEventType.ANCHORED.value, users[0].id, documents[0].id, {"batch_id": anchor_batch.id}),
            (CustodyEventType.ANCHORED.value, users[0].id, documents[1].id, {"batch_id": anchor_batch.id}),
            (CustodyEventType.ANCHORED.value, users[0].id, documents[2].id, {"batch_id": anchor_batch.id}),
            (CustodyEventType.ANCHORED.value, users[0].id, documents[3].id, {"batch_id": anchor_batch.id}),
            (CustodyEventType.VERIFIED.value, users[0].id, documents[0].id, {"result": "pass"}),
            (CustodyEventType.VERIFIED.value, users[0].id, documents[1].id, {"result": "pass"}),
        ]

        for i, (event_type, actor_id, doc_id, metadata) in enumerate(events):
            event_hash = compute_event_hash(
                case_id=case.id,
                document_id=doc_id,
                event_type=event_type,
                actor_id=actor_id,
                metadata=metadata,
            )
            event = CustodyEvent(
                case_id=case.id,
                document_id=doc_id,
                type=event_type,
                actor_id=actor_id,
                timestamp=now - timedelta(hours=len(events) - i),
                event_metadata=metadata,
                event_hash=event_hash,
                anchor_batch_id=anchor_batch.id if event_type == CustodyEventType.ANCHORED.value else None,
            )
            db.add(event)

        for doc in documents:
            analysis = AIAnalysis(
                document_id=doc.id,
                ocr_text=f"Sample OCR text for {doc.filename}. This is a placeholder.",
                entities=[
                    {"entity_id": "e1", "text": "Rahul Kumar", "label": "PERSON", "start_char": 0, "end_char": 11, "page": 1, "confidence": 0.95},
                    {"entity_id": "e2", "text": "123 Main Street", "label": "ADDRESS", "start_char": 20, "end_char": 35, "page": 1, "confidence": 0.88},
                ],
                redaction_boxes=[
                    {"page": 1, "x": 0.1, "y": 0.2, "width": 0.15, "height": 0.05, "reason": "AADHAAR", "confidence": 0.92, "entity_id": "e3"},
                ],
                doc_class="FIR",
                confidence="0.91",
                needs_review=False,
                review_count=0,
                processed_at=now,
            )
            db.add(analysis)

        db.commit()
        print(f"Seed data created successfully:")
        print(f"  - {len(users)} users")
        print(f"  - 1 case (FIR-2026-0417)")
        print(f"  - {len(documents)} documents")
        print(f"  - {len(events)} custody events")
        print(f"  - 1 anchor batch (confirmed)")
        print(f"  - {len(documents)} AI analyses")
        print(f"  - 1 deliberately tampered file uploaded")

    except Exception as e:
        db.rollback()
        print(f"Error seeding data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed()
