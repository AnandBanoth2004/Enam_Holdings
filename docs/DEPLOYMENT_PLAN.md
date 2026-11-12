# FINN Deployment Plan

## Deployment status

**Not deployed.** At the time this plan was prepared, no Vercel, Render, or
Supabase credentials, authenticated provider CLIs, or Git remote were available.
There are no verified deployment URLs. Do not treat a local URL or checked-in
manifest as a completed deployment.

| Component | Target | Verified URL/status |
|---|---|---|
| Frontend | Vercel | Not deployed; no URL |
| API | Render Web Service | Not deployed; no URL |
| PostgreSQL/Auth | Supabase | No project configured |
| Worker | None yet | Not implemented as a deployable service |

## Deployment shape

| Component | Responsibility |
|---|---|
| Vercel | Next.js routes, browser UI, and same-origin server-side API proxy. |
| Render Web Service | FastAPI, deterministic intelligence services, source adapters, and short API operations. |
| Supabase | PostgreSQL, Supabase Auth/JWKS, and pgvector. |
| Optional model provider | Embeddings and bounded structured extraction/synthesis only. |

The Render manifest is [render.yaml](../render.yaml); it migrates the database
before deploy and uses `/health/ready` as its service health check. The Vercel
manifest is [vercel.json](../frontend/vercel.json); set the Vercel project root
directory to `frontend`. Production settings are stored with the providers,
not in local `.env` files.

There is no production worker process yet. Do not create a scheduled service
that calls ingestion endpoints until source permissions, idempotency, job
ownership, timeouts, and operating cadence have been approved.

## Provisioning sequence

1. **Create isolated provider projects.** Create the evaluation Supabase
   project and enable the `vector` extension. Use a separate production
   project for real data; do not copy demo credentials across environments.
2. **Create the Supabase Auth issuer.** Configure allowed redirect URLs for
   the intended Vercel origin. Create an evaluation user. Record its UUID
   (`sub`), project issuer, and JWKS URL. Never use a service-role key as a
   user token.
3. **Create the Render Web Service.** Connect the GitHub repository, use the
   repository root as the service root, and apply `render.yaml`. The
   pre-deploy command runs `python scripts/init_db.py`; that applies the
   checked-in Alembic chain before the API starts.
4. **Set Render environment values** in the Render dashboard:

   | Key | Value |
   |---|---|
   | `FINN_DATABASE_URL` | Supabase PostgreSQL connection URL from its Connect panel. Prefer the direct connection when the host can reach it; otherwise use a session pooler compatible with long-lived SQLAlchemy connections and DDL migrations. Require TLS as documented by Supabase. |
   | `FINN_AUTH_JWKS_URL` | Supabase project Auth JWKS URL, normally `https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json`. |
   | `FINN_AUTH_ISSUER` | `https://<project-ref>.supabase.co/auth/v1`. |
   | `FINN_CORS_ORIGINS` | Exact deployed frontend origin, e.g. `https://<project>.vercel.app`; no trailing slash, wildcard, or localhost origin. |
   | `FINN_RESEARCH_API_KEY` | Optional server-side provider key. Leave unset for extractive, keyword-ranked evidence responses. |

   `FINN_APP_ENVIRONMENT=production`, `FINN_LOG_LEVEL=INFO`, Python version,
   audience, API start command, and readiness path are declared in the
   manifest. Production startup rejects a local/non-PostgreSQL database, a
   non-HTTPS/invalid origin, or missing/invalid HTTPS issuer/JWKS values.
5. **Create the Vercel project.** Import the same repository, set its root
   directory to `frontend`, and use the included Vercel configuration. Set
   these server-side environment variables for Preview and Production:

   | Key | Value |
   |---|---|
   | `FINN_API_BASE_URL` | HTTPS origin of the Render API, without an API path. |
   | `FINN_WORKSPACE_ID` | `3c39b2f3-b3f3-4f34-9b20-5fd985e64301` for the synthetic demo workspace. |

   Never prefix these with `NEXT_PUBLIC_`. Missing backend URL in a production
   build returns a visible `503` configuration error rather than falling back
   to `localhost`.
6. **Close the CORS loop.** After Vercel assigns the final origin, set the exact
   same origin in Render `FINN_CORS_ORIGINS` and redeploy/restart the API.
   Preview deployments require explicit allowed origins if they call the API
   directly. The intended browser path uses the same-origin Next.js proxy.
7. **Seed only after migrations.** Create the Supabase evaluation user first,
   then run this one-time command in a Render shell from the repository root:

   ```powershell
   python scripts/seed_demo_data.py --auth-subject <SUPABASE_USER_UUID>
   ```

   This is non-destructive and idempotent. It seeds synthetic company, market,
   announcement, document, financial, alert, report, and network fixtures and
   maps the demo user to the existing Supabase Auth subject. It refuses to
   reassign a subject already associated with a different FINN user.
   `FINN_WORKSPACE_ID` must match the seeded synthetic workspace.
8. **Set the browser session.** The current frontend does not include a
   sign-in flow. The evaluator must obtain a user access token through an
   approved Supabase client and paste it into the Network page for that browser
   session. This is a prototype workaround, not a production session design.
9. **Verify deployment** using the acceptance checklist below. Record the
   actual URLs only after the endpoints respond from the deployed services.

If Render `preDeployCommand` is unavailable for the selected service plan, do
not start the application against an unmigrated schema. Run the same
`python scripts/init_db.py` command as an explicit one-off release step with
the Render service environment before enabling the new release.

## Environment and secret review

### Backend

- `FINN_APP_ENVIRONMENT=production`
- `FINN_DATABASE_URL`
- `FINN_CORS_ORIGINS`
- `FINN_AUTH_JWKS_URL`
- `FINN_AUTH_ISSUER`
- `FINN_AUTH_AUDIENCE=authenticated`
- `FINN_LOG_LEVEL=INFO`
- Optional `FINN_RESEARCH_API_KEY`
- Optional ticker/source controls, such as `FINN_MARKET_TICKERS` and
  `FINN_DOCUMENT_ALLOWED_HOSTS`

### Frontend server

- `FINN_API_BASE_URL`
- `FINN_WORKSPACE_ID`

No actual application `.env` files or provider credentials were available in
the reviewed workspace. `.env.example` contains local-only values and a
replace-me DB password; provider tokens and database URLs must be entered only
in secret managers. Do not commit provider access tokens, JWTs, database URLs,
Supabase service-role credentials, model keys, or contact exports.

## Database and seed strategy

- The Alembic chain ends at
  `0008_copilot_conversations`; use `python scripts/init_db.py` for
  `alembic upgrade head`.
- The initial migration enables pgvector. Validate the managed provider has
  the extension available before rollout.
- Migrations run as a pre-deploy/release operation, never independently on
  every API startup.
- Production is not seeded automatically on service startup. The
  one-shot `scripts/seed_demo_data.py` loader is repeatable and contains only
  clearly labeled synthetic demo data.
- The destructive `scripts/reset_and_seed_demo.py --confirm-reset` command is
  for local PostgreSQL only. It refuses production or non-local hosts; do not
  weaken that guard for hosted evaluation.
- Do not label fixture prices, announcements, financials, documents, or
  contacts as live or company-reported.

## CORS, API URL, health, and logging

- CORS allows exact configured origins, credentials, the API methods in use,
  and only the required authorization/content/request-ID headers.
- `FINN_API_BASE_URL` is consumed by server-side Next.js proxy routes; the
  production proxy refuses to silently target localhost when it is missing.
- Backend liveness: `/health/live`; database/schema readiness:
  `/health/ready`; frontend-to-backend liveness: `/api/health`.
- Readiness verifies that the database is reachable and required core tables
  exist. It does not prove that the migration revision is current, pgvector
  operations work, or all upstream sources are available.
- API logs are written to stdout with timestamp, severity, logger, request ID,
  method, path, status, and duration. Request query strings and bodies are not
  logged by the request middleware. Provider/DB credentials and authorization
  headers must never be logged.
- External adapters have bounded request timeouts and surface unavailable or
  partial results; they must not replace failures with fabricated live data.
  Model generation is optional; without provider credentials Pull uses
  extracted evidence and keyword retrieval.

## Local repeatable demonstration

See the exact Windows PowerShell setup in the root [README](../README.md).
The shortest local DB reset/fixture sequence is:

```powershell
docker run --name finn-postgres -e POSTGRES_PASSWORD=postgres -p 54322:5432 -d pgvector/pgvector:pg16
$env:FINN_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres"
$env:FINN_APP_ENVIRONMENT = "development"
python scripts\reset_and_seed_demo.py --confirm-reset
```

This resets only a local PostgreSQL database and seeds fictional/demo data.
Private API endpoints still require a valid configured identity-provider JWT;
without an Auth project/token, the UI loads but private requests correctly fail
closed.

## External-source failure behavior

- Market adapters return per-ticker retrieval status and log source failures;
  one unavailable ticker should not be treated as a successful live quote.
- Announcement adapters validate response schemas, report source errors, and
  retain original source metadata when available.
- Document download validates host, file type, size, and PDF integrity; a
  rejected/unavailable file is reported rather than indexed as evidence.
- LLM and embedding providers use timeouts and typed errors; failures must not
  produce uncited or success-shaped responses.
- Use manual/on-demand refresh for evaluation. A production background worker
  and scheduled retry system have not been implemented.

## Deployment acceptance checklist

- [ ] Vercel serves `/`, `/push`, `/research`, `/network`, and `/copilot` over
  HTTPS.
- [ ] `GET /api/health` reports the deployed API reachable.
- [ ] Render `/health/ready` returns 200 with migrated Supabase PostgreSQL.
- [ ] Private APIs return 401 without a JWT and enforce workspace membership
  with a valid user JWT.
- [ ] The evaluation user can read only its authorized synthetic workspace.
- [ ] Push digest, announcement details, materiality, alert history, and source
  links work against seeded records.
- [ ] Pull source discovery and research work where source/provider access is
  available; unavailable upstreams show explicit errors.
- [ ] Network search/paths and Copilot route to backend services with evidence.
- [ ] Browser tests at 375, 390, 768, 1024, and 1440 px show no overflow.
- [ ] No credential or source PDF is tracked or present in frontend build
  output.
- [ ] Logs expose request IDs/status/duration but no tokens or prompt bodies.
- [ ] A backup/restore test and PostgreSQL RLS verification are complete before
  any real private data is used.

## Verified URLs

No production URL is verified because no provider account or deployment
credential was available:

- Frontend: **not deployed**
- Backend API: **not deployed**
- Database: **not provisioned**
