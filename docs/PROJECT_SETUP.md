# FINN Project Setup

## Current implementation boundary

This repository contains the mobile-first application shell, routes, shared styling/components, API health integration, FastAPI foundation, SQLAlchemy models, Alembic migrations, and reproducible demo seed infrastructure.

Data ingestion foundations include EOD market history, public filing adapters, issuer primary-document discovery, and an explicitly fictional network fixture loader. Push provides deterministic 17-label announcement categorization, explainable materiality, filtered digests, results comparisons, configurable persisted alerts, and a responsive API-connected workspace. Pull provides document discovery, secure PDF download/validation, page/table extraction with conditional OCR, chunking, optional pgvector embeddings, filtered retrieval, structured answers, citation validation, and the Company Research UI. Network provides workspace-scoped contact search, entity matching, evidence-backed relationship traversal, and ranked recommendations over explicit synthetic links. JWT verification protects private endpoints; production user provisioning, PostgreSQL RLS, the frontend sign-in flow, and user settings persistence remain incomplete. The Command Centre still displays illustrative UI values. Do not treat synthetic fixtures as company-reported data or investment research.

## Repository map

```text
frontend/
  src/app/               Next.js App Router pages and health BFF route
  src/components/        Shared shell, chart, API status, UI primitives
  src/lib/               API client and class-name helper
backend/
  finn_api/api/          FastAPI routers
  finn_api/db/           SQLAlchemy base, models, connection, seed loader
  finn_api/pull/         Primary-document processing, retrieval, and citation services
  finn_api/schemas/      Pydantic response schemas
  migrations/            Alembic environment and initial migration
  requirements.txt
data/
  fixtures/              Synthetic test data
  seed/                  Empty demo seed contract
  documents/             Local-only documents (ignored by Git)
scripts/                 Root-level DB migration and seed commands
                        Market, announcement, document, and network ingestion CLIs
tests/                   Backend health and metadata tests
docs/                    Architecture, design, requirements, and setup
```

## Requirements

- Node.js 22+; npm.
- Python 3.12+.
- PostgreSQL with the `vector` extension for migrations and DB readiness.
- Optional: Tesseract executable for OCR of scanned PDFs; OCR runs only on pages with insufficient extracted text.
- Optional: OpenAI-compatible provider key for embeddings and structured answer generation. Without a key, Pull returns keyword-ranked verbatim evidence.
- Optional: Supabase CLI + Docker for a local Supabase-compatible Auth/Postgres stack. Neither is required for frontend startup or API liveness.

## Environment

Copy the root template:

```powershell
Copy-Item .env.example .env
```

When running Next.js from `frontend/`, copy its server-side proxy template to
`frontend/.env.local` as well:

```powershell
Copy-Item frontend\.env.example frontend\.env.local
```

`FINN_WORKSPACE_ID` must identify a seeded workspace. The sample value is the
synthetic demo workspace and is not an authentication mechanism.

`FINN_DATABASE_URL` should be a SQLAlchemy Psycopg URL, for example:

```text
postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres
```

`FINN_API_BASE_URL` is consumed only by the Next.js server health proxy. No API credentials are required for startup. Never place service-role keys, database passwords, or model keys in browser-visible `NEXT_PUBLIC_*` variables.

Pull model settings include `FINN_RESEARCH_API_BASE_URL`,
`FINN_RESEARCH_API_KEY`, `FINN_RESEARCH_MODEL`, `FINN_EMBEDDING_MODEL`, and
`FINN_EMBEDDING_DIMENSIONS` (1536 for the current pgvector column).
`FINN_DOCUMENT_ALLOWED_HOSTS` is a comma-separated operator-managed allowlist
for company-authorized CDNs. Keep it restricted to verified issuer document
hosts.

Private Push, Network, saved-report, document discovery/ingestion, financial
extraction, and RAG answer operations require a valid Supabase-compatible JWT
and a provisioned `users.auth_subject` matching the token `sub`. Configure
`FINN_AUTH_JWKS_URL`, `FINN_AUTH_ISSUER`, and `FINN_AUTH_AUDIENCE` from the
Supabase project. Missing auth configuration fails closed for private API
routes; health checks and company search remain available. Membership in the
requested workspace is checked for every private operation. A seeded workspace
UUID is not an authentication credential.

## Start the backend

From the repository root in PowerShell:

```powershell
python -m venv backend\.venv
.\backend\.venv\Scripts\Activate.ps1
python -m pip install -r backend\requirements-dev.txt
python -m uvicorn finn_api.main:app --app-dir backend --reload --port 8000
```

Health URLs:

- `http://localhost:8000/health/live` — process liveness, independent of PostgreSQL.
- `http://localhost:8000/health/ready` — checks database connectivity and required core tables; returns `503` if the database is unreachable or its schema is not initialized.
- `http://localhost:8000/api/v1/health/live` — versioned liveness.
- `http://localhost:8000/docs` — generated OpenAPI docs.

## Start the frontend

In another PowerShell terminal:

```powershell
Set-Location frontend
npm install
npm run dev
```

Open `http://localhost:3000`. Next.js BFF routes forward bearer tokens to
FastAPI. Private Push, Network, Copilot, saved reports, document discovery and
ingestion, financial extraction, and RAG answer generation require a valid
token and workspace membership where applicable. The frontend has no complete
sign-in flow; a user token can currently be supplied through the Network page
for the browser session. This is not a production session design.

## Database initialization and seed data

Start a PostgreSQL service with pgvector available and set `FINN_DATABASE_URL`.
For a normal migration and mapping-seed flow, from the repository root run:

```powershell
python scripts\init_db.py
python scripts\seed_data.py
```

The migration chain through `0008_copilot_conversations` includes document
ingestion metadata, evidenced relationship last-interaction timestamps, and
workspace-scoped Copilot history. The company mapping seed contains 18
**provisional demo issuers**, not an official ENAM portfolio, and is idempotent.
To reset a disposable local PostgreSQL DB and load the complete labeled demo,
use `python scripts\reset_and_seed_demo.py --confirm-reset`; it refuses
production and non-local hosts. For a hosted evaluation DB, first create a
Supabase Auth user and then run the non-destructive seed:
`python scripts\seed_demo_data.py --auth-subject <supabase-user-uuid>`.
This loader is idempotent and binds the synthetic demo workspace user to that
existing identity. Override `FINN_MARKET_TICKERS` for a different supported
NSE portfolio.

JWT verification and API membership checks are implemented for private
operations. Production startup requires remote PostgreSQL with TLS, exact HTTPS
CORS origins, and HTTPS Auth/JWKS URLs. Production RLS, rate limiting, secure
session management, real user provisioning, and a built-in frontend sign-in
flow remain outstanding. Do not deploy with real private data until those
controls are complete.

## Tests and checks

From the repository root:

```powershell
python -m pytest
```

From `frontend/`:

```powershell
npm run typecheck
npm run lint
npm run build
```

Backend tests cover API startup/contracts, schema/seed integrity, source ingestion, all 17 announcement labels, Push scoring/results/alerts, PDF validation/extraction/OCR gating, page-preserving chunking, RAG retrieval filters/cache, citation validation, missing evidence, and document checksum/version handling. They use generated PDFs, injected HTTP data, and SQLite; they do not prove live exchange availability, hosted PostgreSQL migration execution, production privacy boundaries, or paid model-provider behavior.

See [RAG architecture](RAG_ARCHITECTURE.md) for a live primary-source
demonstration using the official Reliance investor-relations annual report.

## Common issues

- **Readiness returns 503:** the database is not reachable at `FINN_DATABASE_URL` or required core tables are missing; liveness may still return 200. Configure/start the DB and apply migrations before serving requests.
- **Migration fails on `vector`:** enable/install pgvector in the target PostgreSQL service before applying the initial migration.
- **Frontend shows API offline:** start FastAPI on port 8000 or set `FINN_API_BASE_URL` for the Next.js server.
- **Port conflicts:** change the Uvicorn/Next.js port and update the BFF origin in `.env`.
- **PowerShell activation is blocked:** use `backend\.venv\Scripts\python.exe -m pip ...` directly rather than changing execution policy.

## Deployment note

The approved target remains Vercel for Next.js, Render/Railway for FastAPI and its worker, and Supabase for PostgreSQL/Auth/pgvector. Production auth, RLS policy verification, scheduled worker orchestration, and secret configuration remain outstanding. Review [Data pipelines](./DATA_PIPELINES.md) for source limitations and permitted retrieval behavior before scheduling ingestion or handling private user data.
