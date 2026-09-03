# SecureDocX — Backend Core (Service 2)

FastAPI + PostgreSQL + MinIO document management system for SecureDocX (SIH 2026).

---

## Quick Start

### Option A — Docker (recommended, works out of the box)

```bash
docker compose up -d
```

- App: http://localhost:8000
- API docs (Swagger): http://localhost:8000/docs
- MinIO console: http://localhost:9001 (minioadmin / minioadmin)

### Option B — Local dev (Native Python)

> **Prerequisite:** Python 3.11 or 3.12 recommended. PostgreSQL (port 5432) and MinIO (port 9000) running locally.

```bash
# 1. Create and activate virtual environment
python -m venv .venv
.venv\Scripts\activate          # Windows
# source .venv/bin/activate     # Linux/macOS

# 2. Install dependencies
pip install -r requirements.txt

# 3. Copy and configure env
cp .env.example .env
# Edit .env if your Postgres/MinIO credentials differ

# 4. Run the app
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

> **Note for Windows native users:** if `psycopg2-binary` prompts for pg_config, install using pre-built binary:
> `pip install psycopg2-binary --only-binary :all:`

---

## Verify it is running

```bash
curl http://localhost:8000/health
# {"status":"ok","db":"ok","storage":"ok","mock_ai":true,"mock_blockchain":true}
```

---

## Seed demo data

- **Inside Docker:**
  ```bash
  docker compose exec backend-core python seed.py
  ```
- **Local Native:**
  ```bash
  python seed.py
  ```

Creates:
- 5 demo users with roles: `officer`, `supervisor`, `forensic`, `auditor`, `admin` (password: `password123`)
- 1 case: `FIR-2026-0417 — Suspected Financial Fraud at Vertex Corp`
- 4 uploaded evidence documents (PDFs and images)
- 1 deliberately tampered document for live audit demonstration
- 1 confirmed anchor batch (Polygon Amoy testnet ID `80002`)
- 24 timeline custody events across lanes
- 4 AI analysis records with OCR text and redaction bounding boxes

---

## Database Migrations (Alembic)

`alembic/env.py` dynamically sources `DATABASE_URL` from your environment/`.env`.

- **Inside Docker:**
  ```bash
  docker compose exec backend-core alembic current
  docker compose exec backend-core alembic upgrade head
  ```
- **Local Native:**
  ```bash
  alembic current
  alembic upgrade head
  ```

---

## Mock flags

Backend Core mocks downstream services by default. Flip these in `.env` as other teams come online:

```env
MOCK_AI_SERVICE=true        # flip to false when AI team is ready
MOCK_BLOCKCHAIN_SERVICE=true  # flip to false when Blockchain team is ready
```

---

## Run tests

```bash
pytest tests/ -v
```

---

## Project structure

```
app/
  main.py          FastAPI entry point, health check
  config.py        All settings from .env
  database.py      SQLAlchemy engine + session
  models/          ORM models (User, Case, Document, CustodyEvent, etc.)
  schemas/         Pydantic request/response models
  routers/         HTTP endpoint handlers (auth, cases, documents, custody, anchor)
  services/
    storage_service.py     MinIO wrapper + SHA-256 hashing
    custody_service.py     Event recording + graph construction
    ai_client.py           Calls Backend AI (mockable)
    blockchain_client.py   Calls Blockchain Service (mockable)
    rbac.py                FastAPI auth & role-based access control
    rate_limiter.py        Sliding-window rate limiter (10 uploads/min, 30 verifies/min)
contracts/
  enums.py         Shared enums (CustodyEventType, Role, etc.)
  entities.py      Shared Pydantic schemas (AI contract, anchor contract)
seed.py            Demo data generator
```

---

## API Endpoints Reference

Full interactive docs are available at **http://localhost:8000/docs** once the service is running.

| Method | Endpoint | Allowed Roles | Description |
|---|---|---|---|
| `GET` | `/health` | Public | Live health check (DB, MinIO, Mock flags) |
| `POST` | `/auth/login` | Public | Authenticate user, return JWT access token |
| `GET` | `/auth/me` | All Roles | Decode JWT, return current user profile |
| `POST` | `/cases` | `officer`, `supervisor`, `admin` | Create a new case |
| `GET` | `/cases` | All Roles | List all cases in descending chronological order |
| `GET` | `/cases/{id}` | All Roles | Get case details by UUID |
| `POST` | `/cases/{id}/documents` | `officer`, `forensic`, `supervisor`, `admin` | Upload document ($\le 50\text{ MB}$, PDF/PNG/JPG/TIFF), hash, store in MinIO, record `UPLOADED` event, trigger async AI |
| `GET` | `/documents/{id}` | All Roles | Get document metadata by UUID |
| `GET` | `/documents/{id}/download` | All Roles | Generate 15-minute presigned MinIO URL, record `DOWNLOADED` event |
| `GET` | `/cases/{id}/graph` | All Roles | Get visual DAG graph for case timeline (dagre/React Flow format) |
| `GET` | `/cases/{id}/custody-log` | All Roles | Get flat chronological custody audit log (optional `?type=` filter) |
| `POST` | `/cases/{id}/anchor` | `officer`, `supervisor`, `admin` | Batch anchor unanchored documents to Polygon Amoy |
| `GET` | `/anchors/{batch_id}` | All Roles | Get anchor batch status (`pending`, `confirmed`, `failed`) |
| `GET` | `/anchors/{batch_id}/verify` | All Roles | Two-stage tamper verification: Stage 1 local MinIO re-hash, Stage 2 on-chain Merkle proof |

---

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql://securedocx:securedocx@localhost:5432/securedocx` | Postgres connection string |
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO host:port |
| `MINIO_ACCESS_KEY` | `minioadmin` | MinIO access key |
| `MINIO_SECRET_KEY` | `minioadmin` | MinIO secret key |
| `MINIO_BUCKET` | `securedocx` | Bucket name |
| `JWT_SECRET` | `change-me-in-production` | JWT signing secret |
| `JWT_EXPIRE_MINUTES` | `60` | Token lifetime |
| `AI_SERVICE_URL` | `http://localhost:8001` | Backend AI base URL |
| `BLOCKCHAIN_SERVICE_URL` | `http://localhost:3000` | Blockchain Service base URL |
| `MOCK_AI_SERVICE` | `true` | Use mock AI responses |
| `MOCK_BLOCKCHAIN_SERVICE` | `true` | Use mock blockchain responses |
| `MAX_UPLOAD_SIZE_MB` | `50` | Max file upload size |
| `ALLOWED_MIME_TYPES` | `application/pdf,image/jpeg,image/png,image/tiff` | Accepted file types |
| `RATE_LIMIT_ENABLED` | `true` | Enable/disable in-memory sliding-window rate limiting |
