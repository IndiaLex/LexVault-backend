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
from app.services.rbac import get_password_hash


def seed(reset: bool = False):
    create_all()
    db = get_session_factory()()
    storage = get_storage_service()

    try:
        if reset:
            print("[seed] Resetting database: removing existing seed and test cases...")
            db.query(CustodyEvent).delete()
            db.query(AIAnalysis).delete()
            db.query(DocumentVersion).delete()
            db.query(Document).delete()
            db.query(AnchorBatch).delete()
            db.query(Case).delete()
            db.query(User).delete()
            db.commit()

        existing = db.query(User).filter(User.username == "demo_officer").first()
        if existing and not reset:
            # Clean up temporary test cases created during test runs (cases starting with 'Test Case', 'Smoke Test', 'B3-', 'B4', 'B5', 'B6', 'Upload', 'Auditor', 'Denied', 'MIME', 'Rate')
            print("[seed] Cleaning up temporary test cases to maintain clean demo docket...")
            test_cases = db.query(Case).filter(
                (Case.title.like("Test Case%")) |
                (Case.title.like("Smoke Test%")) |
                (Case.title.like("B3-%")) |
                (Case.title.like("B4 %")) |
                (Case.title.like("B5 %")) |
                (Case.title.like("Officer Case%")) |
                (Case.title.like("Supervisor Case%")) |
                (Case.title.like("Admin Case%")) |
                (Case.title.like("Upload Permissions%")) |
                (Case.title.like("Auditor Denied%")) |
                (Case.title.like("Denied Anchor%")) |
                (Case.title.like("Anchor Case%")) |
                (Case.title.like("MIME test%")) |
                (Case.title.like("Rate Limit%"))
            ).all()
            for tc in test_cases:
                db.query(CustodyEvent).filter(CustodyEvent.case_id == tc.id).delete()
                for doc in tc.documents:
                    db.query(AIAnalysis).filter(AIAnalysis.document_id == doc.id).delete()
                    db.query(DocumentVersion).filter(DocumentVersion.document_id == doc.id).delete()
                db.query(Document).filter(Document.case_id == tc.id).delete()
                db.delete(tc)
            db.commit()
            print(f"[seed] Cleaned up {len(test_cases)} temporary test cases. Database ready for demo.")
            return

        users = [
            User(
                username="demo_officer",
                password_hash=get_password_hash("password123"),
                name="Inspector Sharma",
                role=Role.OFFICER.value,
            ),
            User(
                username="demo_supervisor",
                password_hash=get_password_hash("password123"),
                name="SP Gupta",
                role=Role.SUPERVISOR.value,
            ),
            User(
                username="demo_forensic",
                password_hash=get_password_hash("password123"),
                name="Dr. Mehta",
                role=Role.FORENSIC.value,
            ),
            User(
                username="demo_auditor",
                password_hash=get_password_hash("password123"),
                name="Auditor Patel",
                role=Role.AUDITOR.value,
            ),
            User(
                username="demo_admin",
                password_hash=get_password_hash("password123"),
                name="Admin",
                role=Role.ADMIN.value,
            ),
        ]
        db.add_all(users)
        db.flush()

        now = datetime.now(timezone.utc)

        # -------------------------------------------------------------------
        # CASE 1: FIR-2026-0417 — State vs. Vertex Corp (Primary Demo Case)
        # -------------------------------------------------------------------
        case1_dossier = {
            "firNumber": "FIR-2026-0417",
            "policeStation": "Civil Lines Police Station, Central District",
            "district": "Central District, New Delhi",
            "actsSections": ["IPC 354", "IPC 452", "BNS 74"],
            "dateOfOccurrence": "2026-09-01 20:30",
            "dateReported": "2026-09-02 09:15",
            "investigatingOfficer": "Inspector Sharma",
            "status": "Under Investigation",
            "complainant": {
                "name": "Smt. Sunita Devi",
                "contact": "+91 98101 23456",
                "address": "House No. 42, Civil Lines, Central District, New Delhi",
            },
            "victim": {
                "alias": "Victim Alpha-1",
                "age": 29,
                "gender": "Female",
                "isProtected": True,
                "maskedIdentityRef": "REF-228A-DEL-2026-0417",
            },
            "suspects": [
                {
                    "name": "Rakesh Kumar",
                    "alias": "Rocky",
                    "status": "Under Interrogation",
                    "details": "Detained near Kashmere Gate terminal; forensic device seized for analysis.",
                }
            ],
            "diaryEntries": [
                {
                    "dayNumber": 1,
                    "date": "2026-09-02",
                    "time": "09:30",
                    "activity": "FIR Registered upon formal complaint by IO Inspector Sharma. Scene of crime cordoned off.",
                    "conductedBy": "Inspector Sharma",
                    "outcome": "Spot inspection completed; rough site map prepared; CCTV footage seized.",
                },
                {
                    "dayNumber": 2,
                    "date": "2026-09-03",
                    "time": "14:15",
                    "activity": "Suspect Rakesh Kumar interrogated; mobile device forwarded to FSL under sealed parcel.",
                    "conductedBy": "Inspector Sharma",
                    "outcome": "Device entered in Malkhana register under Exhibit M-01.",
                },
            ],
            "propertyRegister": [
                {
                    "propertyId": "EX-2026-01",
                    "description": "One Android Smartphone (Samsung S21) in tamper-evident sealed tamper pouch",
                    "seizedFrom": "Rakesh Kumar (Suspect)",
                    "custodyLocation": "Forensic Science Lab (FSL)",
                    "sealIntact": True,
                }
            ],
        }

        case1 = Case(
            title="FIR-2026-0417 — State vs. Vertex Corp (Corporate Financial Fraud)",
            status=CaseStatus.UNDER_INVESTIGATION.value,
            created_by=users[0].id,
            dossier=case1_dossier,
        )
        db.add(case1)
        db.flush()

        doc_configs1 = [
            ("FIR_First_Report.pdf", b"%PDF-1.4 fake-fir-content-001", "application/pdf"),
            ("Witness_Statement_Rahul.pdf", b"%PDF-1.4 fake-witness-statement-002", "application/pdf"),
            ("Medical_Report_Victim.jpg", b"\xff\xd8\xff\xe0 fake-medical-report-003", "image/jpeg"),
            ("Financial_Records_Suspect.png", b"\x89PNG fake-financial-records-004", "image/png"),
        ]

        documents1 = []
        for filename, content, mime in doc_configs1:
            sha256 = hashlib.sha256(content).hexdigest()
            storage_key = storage.upload_file(case1.id, filename, content, sha256)

            doc = Document(
                case_id=case1.id,
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
            documents1.append(doc)

        # Upload deliberately tampered file
        tampered_content = b"%PDF-1.4 TAMPERED-CONTENT-999"
        tampered_storage_key = storage.upload_file(case1.id, "FIR_First_Report.pdf", tampered_content, "tampered-hash-placeholder")
        documents1[0].storage_key = tampered_storage_key

        anchor_batch1 = AnchorBatch(
            merkle_root="0x1a2b3c4d5e6f7a8b9c0d1e2f3a4b5c6d7e8f9a0b1c2d3e4f5a6b7c8d9e0f1a2b",
            tx_hash="0xabcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890",
            chain_id="80002",
            status=AnchorBatchStatus.CONFIRMED.value,
            confirmed_at=now - timedelta(hours=1),
        )
        db.add(anchor_batch1)
        db.flush()

        events1 = [
            (CustodyEventType.UPLOADED.value, users[0].id, documents1[0].id, {"filename": "FIR_First_Report.pdf"}),
            (CustodyEventType.UPLOADED.value, users[0].id, documents1[1].id, {"filename": "Witness_Statement_Rahul.pdf"}),
            (CustodyEventType.UPLOADED.value, users[0].id, documents1[2].id, {"filename": "Medical_Report_Victim.jpg"}),
            (CustodyEventType.UPLOADED.value, users[0].id, documents1[3].id, {"filename": "Financial_Records_Suspect.png"}),
            (CustodyEventType.OCR_COMPLETE.value, users[0].id, documents1[0].id, {"pages": 3}),
            (CustodyEventType.OCR_COMPLETE.value, users[0].id, documents1[1].id, {"pages": 2}),
            (CustodyEventType.OCR_COMPLETE.value, users[0].id, documents1[2].id, {"pages": 1}),
            (CustodyEventType.OCR_COMPLETE.value, users[0].id, documents1[3].id, {"pages": 5}),
            (CustodyEventType.NER_COMPLETE.value, users[0].id, documents1[0].id, {"entities_found": 12}),
            (CustodyEventType.NER_COMPLETE.value, users[0].id, documents1[1].id, {"entities_found": 8}),
            (CustodyEventType.NER_COMPLETE.value, users[0].id, documents1[2].id, {"entities_found": 4}),
            (CustodyEventType.NER_COMPLETE.value, users[0].id, documents1[3].id, {"entities_found": 15}),
            (CustodyEventType.REDACTED.value, users[0].id, documents1[0].id, {"boxes": 3}),
            (CustodyEventType.REDACTED.value, users[0].id, documents1[2].id, {"boxes": 1}),
            (CustodyEventType.ACCESSED.value, users[1].id, documents1[0].id, {"action": "view"}),
            (CustodyEventType.ACCESSED.value, users[2].id, documents1[2].id, {"action": "view"}),
            (CustodyEventType.ACCESS_DENIED.value, users[3].id, documents1[0].id, {"reason": "insufficient_permissions"}),
            (CustodyEventType.DOWNLOADED.value, users[1].id, documents1[1].id, {"format": "pdf"}),
            (CustodyEventType.ANCHORED.value, users[0].id, documents1[0].id, {"batch_id": anchor_batch1.id}),
            (CustodyEventType.ANCHORED.value, users[0].id, documents1[1].id, {"batch_id": anchor_batch1.id}),
            (CustodyEventType.ANCHORED.value, users[0].id, documents1[2].id, {"batch_id": anchor_batch1.id}),
            (CustodyEventType.ANCHORED.value, users[0].id, documents1[3].id, {"batch_id": anchor_batch1.id}),
            (CustodyEventType.VERIFIED.value, users[0].id, documents1[0].id, {"result": "pass"}),
            (CustodyEventType.VERIFIED.value, users[0].id, documents1[1].id, {"result": "pass"}),
        ]

        for i, (event_type, actor_id, doc_id, metadata) in enumerate(events1):
            event_hash = compute_event_hash(
                case_id=case1.id,
                document_id=doc_id,
                event_type=event_type,
                actor_id=actor_id,
                metadata=metadata,
            )
            event = CustodyEvent(
                case_id=case1.id,
                document_id=doc_id,
                type=event_type,
                actor_id=actor_id,
                timestamp=now - timedelta(hours=len(events1) - i),
                event_metadata=metadata,
                event_hash=event_hash,
                anchor_batch_id=anchor_batch1.id if event_type == CustodyEventType.ANCHORED.value else None,
            )
            db.add(event)

        for doc in documents1:
            analysis = AIAnalysis(
                document_id=doc.id,
                ocr_text=f"Sample OCR text for {doc.filename}. This is an official judicial evidence transcript.",
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

        # -------------------------------------------------------------------
        # CASE 2: FIR-2026-0182 — State vs. Cyber Syndicate
        # -------------------------------------------------------------------
        case2_dossier = {
            "firNumber": "FIR-2026-0182",
            "policeStation": "Cyber Crime Police Station, North Range",
            "district": "North District, New Delhi",
            "actsSections": ["IT Act Sec. 66C", "IT Act Sec. 66D", "IPC 420"],
            "dateOfOccurrence": "2026-08-25 14:00",
            "dateReported": "2026-08-26 10:30",
            "investigatingOfficer": "Inspector Sharma",
            "status": "Under Investigation",
            "complainant": {
                "name": "Amit Saxena",
                "contact": "+91 98765 43210",
                "address": "Model Town, North District, New Delhi",
            },
            "victim": {
                "alias": "Victim Beta-2",
                "age": 34,
                "gender": "Male",
                "isProtected": True,
                "maskedIdentityRef": "REF-228A-DEL-2026-0182",
            },
            "suspects": [
                {
                    "name": "Vikram Malhotra",
                    "alias": "Vicky",
                    "status": "Absconding",
                    "details": "Alleged syndicate operator handling fraudulent banking gateways.",
                }
            ],
            "diaryEntries": [
                {
                    "dayNumber": 1,
                    "date": "2026-08-26",
                    "time": "11:00",
                    "activity": "Complaint received regarding unauthorized banking transfer via spoofed OTP.",
                    "conductedBy": "Inspector Sharma",
                    "outcome": "Server transaction logs requested from nodal officer.",
                }
            ],
            "propertyRegister": [
                {
                    "propertyId": "EX-2026-09",
                    "description": "Seized Laptop (Lenovo ThinkPad) containing phishing scripts",
                    "seizedFrom": "Cyber Cafe, Rohini",
                    "custodyLocation": "Forensic Science Lab (FSL)",
                    "sealIntact": True,
                }
            ],
        }

        case2 = Case(
            title="FIR-2026-0182 — State vs. Cyber Syndicate (Financial Impersonation)",
            status=CaseStatus.UNDER_INVESTIGATION.value,
            created_by=users[0].id,
            dossier=case2_dossier,
        )
        db.add(case2)
        db.flush()

        doc_configs2 = [
            ("Cyber_Forensics_Extraction.pdf", b"%PDF-1.4 cyber-forensic-extraction-data", "application/pdf"),
            ("IP_CDR_Traffic_Log.pdf", b"%PDF-1.4 cdr-traffic-log-analysis", "application/pdf"),
        ]
        for filename, content, mime in doc_configs2:
            sha256 = hashlib.sha256(content).hexdigest()
            storage_key = storage.upload_file(case2.id, filename, content, sha256)
            doc = Document(
                case_id=case2.id,
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

            evt_hash = compute_event_hash(case2.id, doc.id, CustodyEventType.UPLOADED.value, users[0].id, {"filename": filename})
            db.add(CustodyEvent(
                case_id=case2.id,
                document_id=doc.id,
                type=CustodyEventType.UPLOADED.value,
                actor_id=users[0].id,
                timestamp=now - timedelta(days=2),
                event_metadata={"filename": filename},
                event_hash=evt_hash,
            ))

        # -------------------------------------------------------------------
        # CASE 3: FIR-2026-0094 — Seizure & Digital Evidence Chain Verification
        # -------------------------------------------------------------------
        case3_dossier = {
            "firNumber": "FIR-2026-0094",
            "policeStation": "Special Crime Branch, Central Range",
            "district": "Central District, New Delhi",
            "actsSections": ["IPC 120B", "IPC 468", "IPC 471"],
            "dateOfOccurrence": "2026-07-15 18:00",
            "dateReported": "2026-07-16 09:00",
            "investigatingOfficer": "Inspector Sharma",
            "status": "Charge Sheeted",
            "complainant": {
                "name": "State on relation of Central Crime Bureau",
                "contact": "+91 11 2436 0000",
                "address": "CGO Complex, Lodhi Road, New Delhi",
            },
            "victim": {
                "alias": "Public Revenue Dept",
                "age": 0,
                "gender": "N/A",
                "isProtected": False,
                "maskedIdentityRef": "REF-PUB-2026-0094",
            },
            "suspects": [
                {
                    "name": "Anil Singhania",
                    "alias": "Munna",
                    "status": "Arrested",
                    "details": "Remanded to judicial custody; charge sheet submitted before ACMM Court.",
                }
            ],
            "diaryEntries": [
                {
                    "dayNumber": 1,
                    "date": "2026-07-16",
                    "time": "10:00",
                    "activity": "Charge sheet finalized and cryptographic custody log attached.",
                    "conductedBy": "Inspector Sharma",
                    "outcome": "Court bundle Section 65B certificate generated and sealed.",
                }
            ],
            "propertyRegister": [
                {
                    "propertyId": "EX-2026-15",
                    "description": "Hard Drive (Seagate 2TB) with cloned forensic image",
                    "seizedFrom": "Accounting Office",
                    "custodyLocation": "Court Safe",
                    "sealIntact": True,
                }
            ],
        }

        case3 = Case(
            title="FIR-2026-0094 — Seizure & Digital Evidence Chain Verification",
            status="closed",
            created_by=users[0].id,
            dossier=case3_dossier,
        )
        db.add(case3)
        db.flush()

        doc_configs3 = [
            ("Seizure_Malkhana_Panchnama.pdf", b"%PDF-1.4 malkhana-panchnama-record", "application/pdf"),
            ("Forensic_Lab_Ballistics.pdf", b"%PDF-1.4 forensic-lab-ballistics-report", "application/pdf"),
        ]
        for filename, content, mime in doc_configs3:
            sha256 = hashlib.sha256(content).hexdigest()
            storage_key = storage.upload_file(case3.id, filename, content, sha256)
            doc = Document(
                case_id=case3.id,
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

            evt_hash = compute_event_hash(case3.id, doc.id, CustodyEventType.UPLOADED.value, users[0].id, {"filename": filename})
            db.add(CustodyEvent(
                case_id=case3.id,
                document_id=doc.id,
                type=CustodyEventType.UPLOADED.value,
                actor_id=users[0].id,
                timestamp=now - timedelta(days=10),
                event_metadata={"filename": filename},
                event_hash=evt_hash,
            ))

        db.commit()
        print(f"Seed data created successfully with exactly 3 demo cases:")
        print(f"  - 5 official users (officer, supervisor, forensic, auditor, admin)")
        print(f"  - Case 1: FIR-2026-0417 — State vs. Vertex Corp (Corporate Financial Fraud)")
        print(f"  - Case 2: FIR-2026-0182 — State vs. Cyber Syndicate (Financial Impersonation)")
        print(f"  - Case 3: FIR-2026-0094 — Seizure & Digital Evidence Chain Verification")

    except Exception as e:
        db.rollback()
        print(f"Error seeding data: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    reset_flag = "--reset" in sys.argv or "--force" in sys.argv
    seed(reset=reset_flag)
