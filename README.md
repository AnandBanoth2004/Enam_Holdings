# FINN — Financial Investment Agent

FINN is a mobile-first investment-intelligence prototype that combines
portfolio monitoring, primary-source company research, and professional
relationship intelligence.

> **Prototype notice:** FINN is not investment advice and is not certified for
> production use. Synthetic fixtures are explicitly labeled and are not
> company-reported financial data. Market history is end-of-day, not live.

## Business problem

Investors need to monitor portfolio filings, verify company claims against
primary documents, and find relevant context in their professional network.
Those tasks are often spread across exchange websites, PDFs, spreadsheets, and
personal contact lists. FINN connects the workflows while keeping source
evidence, uncertainty, and relationship provenance visible.

## Product overview

- **Push** prioritizes exchange-style announcements with transparent,
  rule-based materiality, source links, digest filters, and persisted alerts.
- **Pull** discovers issuer documents, extracts page-preserving evidence,
  retrieves relevant passages, calculates financial metrics deterministically,
  tracks guidance, and retains citations.
- **Network** searches synthetic or authorized professional profiles and
  relationship paths, showing evidence and connection distance rather than
  inferring acquaintance from shared employers or schools.
- **Copilot** routes supported questions to Push, Pull, and Network services;
  deterministic calculations and relationship retrieval stay in backend
  services.

## Architecture

```mermaid
flowchart LR
    Browser[Mobile-first Next.js UI]
    BFF[Next.js same-origin API proxy]
    API[FastAPI and Pydantic]
    PG[(PostgreSQL and pgvector)]
    Sources[Issuer IR, NSE/BSE, yfinance]
    Models[Optional LLM and embedding provider]
    Browser --> BFF
    BFF -->|FINN_API_BASE_URL| API
    API -->|JWT and workspace checks| PG
    API -->|EOD and filing adapters| Sources
    API -->|Retrieved primary-source context only| Models
    API --> PG
```

### Push architecture

Source adapters collect market observations and public filings; validation,
deduplication, classification, materiality, and alert evaluation are
deterministic services. Market observations are labeled end-of-day and filing
availability/freshness depends on upstream sources.

### Pull architecture

Issuer-document discovery → PDF validation → page/table extraction → semantic
chunking → optional pgvector embeddings → company/period-filtered retrieval →
citation-checked answers. Revenue, margin, cash flow, leverage, and comparison
calculations are Python calculations, not LLM arithmetic.

### Network architecture

Workspace-scoped contact, organization, education, and relationship records
feed deterministic entity matching and graph traversal. Demo identities and
relationships are synthetic. Shared employment history is evidence for
relevance, not proof of a personal relationship.

## Technology stack

| Layer | Technologies |
|---|---|
| Web | Next.js, React, TypeScript, Tailwind CSS, Recharts, React Flow |
| API | Python, FastAPI, Pydantic, SQLAlchemy |
| Data | PostgreSQL, Alembic, pgvector, Pandas, NumPy |
| Documents | PyMuPDF/pdfplumber, optional OCR with Tesseract |
| Sources | yfinance, permitted exchange endpoints, issuer investor-relations sites |
| Optional AI | OpenAI-compatible structured generation and embeddings |
| Hosting target | Vercel, Render, Supabase PostgreSQL/Auth |

## Screenshots

Screenshots are intentionally not fabricated. Capture current, non-sensitive
screenshots before publishing and add them under `docs/screenshots/`.

<!-- Screenshot placeholder: docs/screenshots/push-workspace.png -->
<!-- Screenshot placeholder: docs/screenshots/company-research.png -->
<!-- Screenshot placeholder: docs/screenshots/network-intelligence.png -->

## Local installation

### Prerequisites

- Windows 10/11, PowerShell, Git, Node.js 22+ with npm, Python 3.12+, and
  Docker Desktop.
- Open PowerShell in the repository root. Check that the required tools are
  installed and Docker Desktop is running:

  ```powershell
  git --version
  node --version
  npm --version
  py --version
  docker version
  ```

### 1. Start PostgreSQL with pgvector

For a disposable local database:

```powershell
docker run --name finn-postgres `
  -e POSTGRES_PASSWORD=postgres `
  -p 54322:5432 `
  -d pgvector/pgvector:pg16
```

This password is for the local container only. Never reuse it in a hosted
environment.

If you already created this container, start it instead:

```powershell
docker start finn-postgres
```

### 2. Configure and install the backend

From the repository root:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
# Edit .env and set FINN_DATABASE_URL to:
# postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres

py -3 -m venv backend\.venv
.\backend\.venv\Scripts\python.exe -m pip install -r backend\requirements-dev.txt
```

Set `FINN_DATABASE_URL` in `.env` to
`postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres`. Save and
close Notepad. Do not overwrite an existing `.env`; it may contain local
settings you want to keep.

### 3. Initialize and seed the local demo

In the setup PowerShell window, configure the local database and development
mode, then run the guarded destructive reset:

```powershell
$env:FINN_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres"
$env:FINN_APP_ENVIRONMENT = "development"
.\backend\.venv\Scripts\python.exe scripts\reset_and_seed_demo.py --confirm-reset
```

Wait for `FINN local demo database reset and seed completed.` before moving on.
This command deletes and recreates FINN application tables before seeding. It
refuses production and non-local PostgreSQL hosts; never use it with Supabase
or a database containing data you need to keep. It seeds a synthetic
18-company demo, announcements, market observations, financial/document
fixtures, and fictional network profiles. This is not an official ENAM
portfolio. For non-destructive schema upgrades, use
`.\backend\.venv\Scripts\python.exe scripts\init_db.py`.

To use a hosted Supabase Auth project with the local demo database:

1. Configure `FINN_AUTH_JWKS_URL`, `FINN_AUTH_ISSUER`, and
   `FINN_AUTH_AUDIENCE` in `.env` using that project’s Auth settings.
2. Create an evaluation user in Supabase Auth and copy the user UUID (`sub`).
3. Run
   `.\backend\.venv\Scripts\python.exe scripts\seed_demo_data.py --auth-subject <SUPABASE_USER_UUID>`.
   This idempotently seeds demo records and maps the synthetic demo workspace
   user to that identity; it refuses to reassign an identity already owned by
   another FINN user.
4. Copy `frontend\.env.example` to `frontend\.env.local`, and set
   `FINN_WORKSPACE_ID` to the seeded demo workspace ID.
5. Sign in through an approved Supabase client to obtain a user access token.
   The current prototype has no built-in sign-in flow; paste the user token in
   the Network page for this browser session. Never use a service-role key.

Without a configured identity provider and user token, private APIs correctly
return `401`; UI pages can load but private Push/Network/Copilot data will not.
Automated tests use SQLite and do not require a live provider.

### 4. Start and check the backend

After the migration and seed command succeeds, start the API in the same
PowerShell window:

```powershell
.\backend\.venv\Scripts\python.exe -m uvicorn finn_api.main:app --app-dir backend --reload --port 8000
```

Keep that window open. In a second PowerShell window, check the API and its
database connection:

```powershell
Invoke-RestMethod http://localhost:8000/health/live
Invoke-RestMethod http://localhost:8000/health/ready
```

Both responses should have `status` set to `ok`. API documentation:
`http://localhost:8000/docs`.

### 5. Start the frontend

```powershell
if (-not (Test-Path frontend\.env.local)) {
    Copy-Item frontend\.env.example frontend\.env.local
}
Set-Location frontend
npm ci
npm run dev
```

Open `http://localhost:3000`. The frontend calls same-origin Next.js API proxy
routes, which forward server-side to `FINN_API_BASE_URL`. Keep this terminal
open while using the site. Without Supabase Auth and a user access token,
private APIs return `401`; the public UI can still load.

### 6. Run the checks before publishing

From the repository root, run the backend tests:

```powershell
.\backend\.venv\Scripts\python.exe -m pytest -q
```

Then run the frontend checks:

```powershell
Set-Location frontend
npm run lint
npm run typecheck
npm run build
Set-Location ..
```

Proceed only after all commands complete successfully. Fix and rerun any
command that fails.

## Environment variables

| Variable | Service | Required in production | Purpose |
|---|---|---:|---|
| `FINN_APP_ENVIRONMENT` | Backend | Yes | Set to `production`; startup validates other production settings. |
| `FINN_DATABASE_URL` | Backend | Yes | PostgreSQL/pgvector SQLAlchemy URL; keep server-side only. |
| `FINN_CORS_ORIGINS` | Backend | Yes | Comma-separated exact HTTPS frontend origins; no wildcard. |
| `FINN_AUTH_JWKS_URL` | Backend | Yes | Supabase-compatible public JWKS endpoint. |
| `FINN_AUTH_ISSUER` | Backend | Yes | Expected JWT issuer. |
| `FINN_AUTH_AUDIENCE` | Backend | Yes | Usually `authenticated`. |
| `FINN_API_BASE_URL` | Vercel server | Yes | HTTPS origin of the deployed FastAPI API. Never expose as `NEXT_PUBLIC_*`. |
| `FINN_WORKSPACE_ID` | Vercel server | Yes for private workspace views | Seeded/authorized workspace UUID; not a credential. |
| `FINN_RESEARCH_API_KEY` | Backend | Optional | Server-only model provider key for generated synthesis/embeddings. |
| `FINN_MARKET_TICKERS` | Backend | Optional | Comma-separated supported NSE symbols. |
| `FINN_DOCUMENT_ALLOWED_HOSTS` | Backend | Optional | Operator-approved issuer CDN hosts. |
| `FINN_LOG_LEVEL` | Backend | Optional | Usually `INFO` in production. |

`.env.example` and `frontend/.env.example` contain local placeholders only.
Production secrets belong in Render/Vercel secret stores. Do not commit `.env`,
database URLs, JWTs, provider keys, or Supabase service-role credentials.

## Database setup

The checked-in Alembic chain currently ends at
`0008_copilot_conversations`. Production deployment runs
`python scripts/init_db.py` as the Render pre-deploy migration command. The
migration enables the PostgreSQL `vector` extension; enable pgvector in the
managed database before first deploy if the provider requires an explicit
extension toggle.

Demo data is not loaded automatically during every service start. After
migrations, create the evaluation Auth user and run the one-time,
non-destructive seed:

```powershell
python scripts\seed_demo_data.py --auth-subject <SUPABASE_USER_UUID>
```

Use synthetic-only data in public evaluation environments. Never run the local
reset script against a hosted or production database.

## Testing

From the repository root:

```powershell
python -m pip install -r backend\requirements-dev.txt
python -m pytest -q
```

From `frontend/`:

```powershell
npm ci
npm run lint
npm run typecheck
npm run build
```

Tests cover deterministic financial math, ingestion validation and failure
handling, all 17 announcement categories, alert/materiality behavior, primary
PDF extraction and citations, tenant boundaries, network matching/traversal,
Copilot routing, and production configuration checks. Automated fixture tests
are not proof of live exchange coverage, PostgreSQL provider behavior, or model
accuracy.

## Deployment

Target deployment is Vercel for the Next.js app, Render for FastAPI, and
Supabase PostgreSQL/Auth with pgvector. Production configuration is separate:
`render.yaml` defines server-side service settings and `frontend/vercel.json`
defines the Vercel build. Required secret values are entered in provider
dashboards and are deliberately not committed.

### Publish the project to GitHub

Only continue after the local database, API, website, and checks above work.
From the repository root, inspect and stage the project files:

```powershell
git status --short
git add -A
git diff --cached --check
git diff --cached --name-only
```

Before committing, confirm that `.env`, `frontend\.env.local`, credentials,
and files you do not have permission to publish are not staged. Then commit
and push. Replace the placeholders with your GitHub owner and repository:

```powershell
git commit -m "Prepare FINN for deployment"
git remote add origin https://github.com/<GITHUB_OWNER>/<REPOSITORY>.git
git push -u origin main
```

If `origin` already exists, use this command instead of `git remote add`:

```powershell
git remote set-url origin https://github.com/<GITHUB_OWNER>/<REPOSITORY>.git
```

Open the GitHub repository after the push and confirm the files are present.
Never commit `.env`, `.env.local`, database URLs, JWTs, provider keys, or
Supabase service-role credentials.

### Deploy with Supabase, Render, and Vercel

After the GitHub push succeeds, follow [Deployment plan](docs/DEPLOYMENT_PLAN.md)
in order. In summary:

1. Create a Supabase project, enable `vector`, create an Auth evaluation user,
   and keep its database URL, issuer, JWKS URL, and user UUID available for
   provider configuration. Do not put credentials in the repository.
2. Create a Render Web Service from the GitHub repository root using
   `render.yaml`. Set the Supabase database URL, Auth issuer/JWKS URL, and
   exact frontend HTTPS CORS origin in Render's environment settings. Confirm
   the migration pre-deploy step succeeds and
   `https://<RENDER_SERVICE>.onrender.com/health/ready` returns `status: ok`.
3. Create a Vercel project from the same GitHub repository and set its root
   directory to `frontend`. Set `FINN_API_BASE_URL` to the Render API origin
   and `FINN_WORKSPACE_ID` to the demo workspace UUID in Vercel's server-side
   environment settings, then deploy the site.
4. Add the final Vercel HTTPS origin to Render's `FINN_CORS_ORIGINS`, then
   redeploy/restart the Render service. Seed the synthetic evaluation data
   after migrations and use the Supabase evaluation user as described in the
   deployment plan.
5. Open the Vercel website, test the deployed site and API connection, and
   save the actual Vercel URL for the assignment. Supabase provides the
   database/Auth project, not the public website URL; the Vercel URL is the
   website link to submit.

Deployment has **not** been performed: this workspace has no provider
credentials, deployment CLI login, Git repository remote, or recorded public
URLs. See [Deployment plan](docs/DEPLOYMENT_PLAN.md) for the exact provider
setup, migration, seed, health, and smoke-test steps.

## Final technical and submission documents

- [Final architecture](docs/FINAL_ARCHITECTURE.md)
- [Data security and privacy](docs/DATA_SECURITY_AND_PRIVACY.md)
- [AI and agent design](docs/AI_AGENT_DESIGN.md)
- [Data provenance](docs/DATA_PROVENANCE.md)
- [Engineering trade-offs](docs/ENGINEERING_TRADEOFFS.md)
- [AI-assisted build history and export checklist](docs/AI_BUILD_HISTORY.md)
- [Final submission audit and release gates](docs/FINAL_SUBMISSION_CHECKLIST.md)
- [Covering email draft](docs/COVERING_EMAIL.md)

The final audit currently marks the project **not ready for external
submission**: the public repository, deployed URL, actual agent-session
exports, and authenticated end-to-end workflows are still outstanding.

## Security and privacy

- Private endpoints validate JWT signatures, issuer, audience, expiry, user
  provisioning, and workspace membership.
- Production startup fails closed if PostgreSQL, exact HTTPS CORS origins, or
  HTTPS Auth issuer/JWKS settings are missing/invalid.
- Do not use real network contacts in the prototype. Demo identities and links
  are fictional.
- Production PostgreSQL RLS, rate limiting, secure sign-in/session management,
  backup/restore testing, and production security monitoring are outstanding.
- Browser bearer tokens currently use `sessionStorage`; do not treat this as a
  production session design.
- Source URLs, source timestamps, and synthetic labels should be preserved;
  missing information must remain unavailable rather than guessed.

## Data-source limitations

yfinance and public NSE/BSE endpoints may be delayed, rate-limited, or
unavailable. The application does not promise live intraday data. Issuer
document discovery is best-effort; primary documents must support research
claims. PDF table extraction, OCR, period/unit matching, entity resolution, and
model generation require review. Failures should be visible and should not be
replaced with fabricated facts.

## Future improvements

- Add a complete Supabase sign-in/session flow and secure server-side session
  handling.
- Add and verify PostgreSQL RLS policies and cross-tenant integration tests.
- Deploy a separately operated, bounded ingestion worker after live source
  permissions and scheduling are established.
- Add authorized live-source monitoring, freshness alerts, and provider cost
  budgets.
- Capture reviewed screenshots and run authenticated browser/mobile acceptance
  tests against the deployed environment.

## Public repository preparation

The official assignment PDFs under `docs/` are excluded from Git by exact
filename. Keep them local unless you have explicit permission to republish them.
Check the stage before pushing:

```powershell
git status --short
git ls-files
git diff --cached --check
```

After creating an empty public GitHub repository, publish the local `main`
branch with:

```powershell
git remote add origin https://github.com/<GITHUB_OWNER>/<REPOSITORY>.git
git push -u origin main
```

Replace the placeholders with the actual GitHub repository URL. A successful
local commit is not a successful GitHub publication; confirm the push output
and remote repository page.
