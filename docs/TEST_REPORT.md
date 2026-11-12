# FINN QA and Engineering Review

**Review date:** 2026-11-12
**Environment:** Windows, Node/npm, Python 3.13.7; isolated test dependencies and a temporary SQLite database.

## Executive summary

The automated backend suite, frontend lint/typecheck/build, and Python compilation
all pass. The production frontend and current backend source were started locally.
All six app routes rendered, health checks passed against an initialized
38-table SQLite schema, and all 30 route/viewport combinations showed no
horizontal overflow. Private API requests without credentials correctly return
401.

This is a prototype-level verification, not production certification. PostgreSQL,
Alembic deployment, hosted auth, RLS, live market/exchange feeds, live issuer
document processing, and paid model-provider calls were not available for
verification. Authenticated end-to-end UI journeys therefore remain unverified.

## Validation results

| Area | Result | Evidence |
|---|---|---|
| Clean dependency installation | PASS | `npm ci` completed in an isolated temporary directory; production `backend/requirements.txt` installed into a fresh Python environment and `pip check` found no broken requirements. |
| Backend automated tests | PASS | `145 passed` in 10.14 seconds; one upstream Starlette/httpx deprecation warning. |
| Financial calculations | PASS | Calculation-focused tests independently verify daily moves, 20-session volume calculations, period comparisons including zero/negative bases, margin, debt/equity, cash flow, and missing values. |
| Backend syntax | PASS | `python -m compileall -q backend\\finn_api` completed successfully. |
| Frontend lint | PASS | `npm run lint`. |
| Frontend types | PASS | `npm run typecheck`. |
| Production build | PASS | `npm run build`; Next.js generated all app routes and API proxies. |
| Production configuration | PASS | Settings tests reject local/non-TLS DBs, wildcard/non-HTTPS CORS, and invalid/missing Auth URLs in production; development defaults remain accepted. |
| Deployment manifests | PASS | `render.yaml` parsed and its migration/readiness commands checked; Vercel JSON parsed. Provider deployment remains unverified. |
| Missing production API URL | PASS | The built production frontend returns `503` with `backend_not_configured` instead of silently targeting localhost. |
| External-source failures | PASS | Automated tests verify market-source errors are isolated per ticker and document/issuer failures are reported as unavailable. |
| Local API startup | PASS | Current source served on an isolated local port. `/health/live`, `/health/ready`, and versioned readiness returned 200 after initializing the temporary SQLite schema. |
| Missing-schema handling | PASS | Regression test verifies liveness remains independent and readiness returns 503 with `database_schema_unavailable` when core tables are absent. |
| Public company search | PASS | Against the empty QA database, the endpoint returned HTTP 200 with an empty result set rather than a database error. |
| Private API boundaries | PASS | Unauthenticated research discovery, RAG answer, and Push digest requests returned 401. Automated tests cover endpoint auth and user/workspace isolation. |
| Frontend route smoke | PASS | `/`, `/push`, `/research`, `/network`, `/copilot`, `/settings`, and `/api/health` returned HTTP 200 on the production frontend. |
| Responsive layout | PASS | Browser checks covered all six routes at 375, 390, 768, 1024, and 1440 CSS pixels: 30 combinations, each with a main region and no horizontal overflow. |
| Production dependency audit | PASS | `npm audit --omit=dev` reported zero production dependency vulnerabilities. |
| Full dependency audit | PARTIAL | Seven moderate advisories remain in the development toolchain, transitively involving `minimatch` through `typescript-eslint`; a dry-run remediation did not resolve them, and no dependency changes were made. |

## Requested test categories

| Category | Result | Summary |
|---|---|---|
| 1. Environment | PARTIAL | Isolated dependency installs, app startup, SQLite readiness, frontend health, and route smoke passed. PostgreSQL, Alembic deployment, and configured production environment variables were unavailable. |
| 2. Financial calculations | PASS | Independent expected-value tests cover price/volume formulas, QoQ/YoY edge cases, margins, leverage, free cash flow, and missing values. |
| 3. Push | PARTIAL | Automated coverage includes all 17 labels, deduplication, materiality, digest filtering, results comparisons, configured alert thresholds, history, and source links. No authenticated live-data UI journey. |
| 4. Pull | PARTIAL | Controlled PDF extraction, page preservation, retrieval/company filters, citations, missing evidence, and duplicate handling passed. No live issuer PDF or paid embedding/model provider was used. |
| 5. Network | PARTIAL | Search/matching/traversal/ranking and user/workspace authorization tests passed with synthetic records. No real contact data or PostgreSQL RLS was tested. |
| 6. Copilot | PARTIAL | Routing, tool invocation, cross-layer results, citation retention, missing-data behavior, and conversation isolation are covered by tests. No authenticated live-model query. |
| 7. Frontend | PARTIAL | Production build and all six routes passed; 30 responsive layout checks had no overflow. Private-data interactions were blocked by the absence of a configured sign-in/session. |
| 8. Security | PARTIAL | Anonymous private API access returned 401, and automated tests cover auth/ownership boundaries. No production RLS, penetration test, exhaustive fuzzing, or hosted-auth test. |

## Workflow verdicts

| Workflow | Verdict | What was verified | What remains unverified |
|---|---|---|---|
| Portfolio → announcement → materiality → explanation → network connection | PARTIAL | Push classification/materiality, source evidence, alert rules, Network matching, and integration behavior are covered by automated tests. | Authenticated browser journey with seeded portfolio data and a real filing. |
| Company search → primary documents → RAG → financial analysis → guidance → Network contacts | PARTIAL | Search, PDF extraction/page preservation, chunking, retrieval filters, citations, financial calculations, guidance logic, and Network services are covered by tests. | Live issuer documents, a configured embedding/LLM provider, PostgreSQL, and authenticated UI flow. |
| Copilot → intent routing → Push/Pull/Network → grounded answer | PARTIAL | Routing, multi-service calls, missing evidence, citation preservation, relationship evidence, and user/workspace conversation isolation are covered by tests. | A real authenticated conversation using live model/data providers. |
| Alert configuration → market data → threshold evaluation → alert history | PARTIAL | EOD calculations, configured thresholds, 20-session volume baselines, persistence, and deduplication are covered by tests. | Authenticated UI mutation against PostgreSQL and a live market-data feed. |
| Security and privacy | PARTIAL | Private endpoints reject anonymous requests; automated tests cover authorization and tenant ownership; demo contacts are synthetic. | PostgreSQL RLS, hosted identity/JWKS, production provisioning, rate limiting, and a complete browser sign-in/session flow. |

`PARTIAL` denotes unverified external/runtime conditions, not a failing
automated test.

## Measured local performance

Twenty sequential requests per route were timed against the current local
backend and temporary SQLite database. These are small-sample local observations,
not production service-level measurements.

| Endpoint | Median | Maximum observed |
|---|---:|---:|
| `GET /health/ready` | 15.01 ms | 46.25 ms |
| `GET /api/v1/research/companies/search?q=RELIANCE` | 10.09 ms | 28.18 ms |

No hosted latency, concurrency, cold-start, or production PostgreSQL benchmark
was run.

## Engineering changes made during review

- Conversation previews are fetched with a single ranked SQL query rather than
  one additional query per conversation.
- Unusual-volume lookup selects the latest NSE observation in SQL and obeys
  configured workspace thresholds; it does not invent a default threshold.
- Costly/mutating research operations (discovery, ingestion, extraction, and RAG
  answer generation) require authentication.
- Production API configuration rejects non-TLS database URLs, non-HTTPS or
  wildcard CORS origins, and missing/non-HTTPS Auth issuer/JWKS values.
- Production frontend proxy routes fail closed when `FINN_API_BASE_URL` is
  missing or invalid; development retains the local API default.
- The production requirements exclude pytest; `backend/requirements-dev.txt`
  adds test tooling for local/CI environments.
- Document ingestion reuses embeddings for repeated chunk hashes, submits
  unique pending chunks in batches of at most 64, and rejects invalid dimensions
  or non-finite vector values.
- PDF downloads no longer join the response buffer twice; extracted tables are
  formatted once per table.
- Readiness now checks database connectivity and presence of required core
  tables, rather than treating `SELECT 1` alone as sufficient.

## Security and dependency observations

- No application `.env` file or configured FINN environment variables were
  present for this review; only environment templates were found. No live
  credentials were used.
- The frontend stores access tokens in `sessionStorage`; there is no complete
  sign-in flow. Prefer an appropriately protected server session/HttpOnly cookie
  before using real accounts.
- API authentication depends on configured issuer/JWKS settings and a
  provisioned user. Missing configuration must remain fail-closed.
- PostgreSQL RLS is not configured or verified. Route-level checks do not
  replace database-enforced tenant isolation.
- Synthetic data and source fixtures must not be presented as company-reported
  financial information or live relationship data.

## Warnings and limits

- The test run emitted one upstream `StarletteDeprecationWarning` because
  `starlette.testclient` currently uses `httpx`; this did not fail tests.
- `npm audit --omit=dev` was clean, but the full development dependency tree
  still has seven moderate advisories.
- No production-readiness claim is made. See
  [known limitations](./KNOWN_LIMITATIONS.md) for the remaining blockers.
