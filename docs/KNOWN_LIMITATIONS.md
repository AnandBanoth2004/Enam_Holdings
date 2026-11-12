# FINN Known Limitations

These are material gaps for a hiring prototype and a production deployment.
Passing automated tests does not remove these constraints.

## Authentication and privacy

- There is no complete user sign-in, provisioning, or session lifecycle in the
  frontend. Private endpoints require a valid bearer JWT, configured issuer and
  JWKS, and a provisioned database user.
- The current client stores access tokens in `sessionStorage`. Production
  should use a reviewed session design, preferably an appropriately protected
  HttpOnly cookie.
- PostgreSQL row-level security is not configured or verified. Keep real
  personal/network data out of the system until database-enforced tenant
  policies, access reviews, retention, and deletion controls are in place.
- The Network demo is synthetic. A production contact data source requires
  documented user authorization/consent, lawful access, and retention rules.
- Rate limiting, abuse controls, and production security monitoring have not
  been validated.

## Database and deployment

- PostgreSQL, pgvector, and the Alembic migration chain were not exercised in
  this review. Runtime API checks used a temporary SQLite database initialized
  from SQLAlchemy metadata; this does not prove PostgreSQL compatibility or
  migration correctness.
- The readiness probe checks database connectivity and required core table
  presence, not the exact Alembic revision or successful availability of every
  optional extension.
- No hosted deployment, production secrets manager, TLS configuration, backup
  restore, or horizontal-scaling test was performed.
- No Vercel, Render, or Supabase deployment was performed; this workspace
  lacked provider credentials, an authenticated CLI, and a Git remote. There
  are no deployed URLs to verify.
- The production Render/Vercel configuration is prepared but has not been
  applied to provider accounts. No PostgreSQL migration or seed was run against
  hosted infrastructure.
- The demo seed can bind its synthetic user to an existing Auth subject, but
  the application still has no sign-in page and requires a user token to be
  supplied to the current session manually.
- Scheduled ingestion and a production background worker are not implemented;
  source refresh is manual/on-demand.
- Retrieval caching is process-local; it is not a shared/distributed cache.
- The Command Centre contains illustrative UI values, and some settings are
  explicitly not persisted.

## Data sources and freshness

- No live yfinance, NSE/BSE announcement, or issuer-document pipeline was
  validated against the isolated QA environment. Access, freshness, coverage,
  legal terms, and rate limits depend on deployment configuration and upstream
  availability.
- EOD prices are not intraday prices. Market signals must retain their source
  timestamp and delay semantics.
- The demo company list is provisional and synthetic fixtures must remain
  explicitly labelled; it is not an official portfolio or issuer disclosure.
- Document discovery can return incomplete results. A discovered link is not
  proof that the file is accessible, current, or correctly classified.
- PDF tests use generated/controlled inputs; this review did not validate
  scanned, rotated, malformed, or unusually complex live issuer reports with
  OCR.
- Company/person entity matching remains probabilistic where evidence is
  incomplete. Shared employers or schools do not establish that people know
  one another.

## AI and financial research

- No paid LLM or embedding provider was configured or called. Live structured
  generation, provider latency, token costs, quotas, and rate-limit behavior
  remain unmeasured.
- Without a configured provider, retrieval can return keyword-ranked evidence;
  that is not equivalent to semantic retrieval or generated synthesis.
- Automated tests validate grounded-answer contracts and citations against
  fixtures, not the factual accuracy of live model output.
- Financial extraction and calculations are covered by tests, but real issuer
  table layouts, restatements, accounting-basis differences, and footnote
  interpretation require ongoing validation.
- The application must continue to distinguish reported facts, deterministic
  calculations, and model-generated interpretation; missing evidence must not
  be filled with inferred figures.

## UI and operational verification

- Browser layout was checked at 375, 390, 768, 1024, and 1440 pixels; all six
  routes had no horizontal overflow. Authenticated data mutations and complete
  browser workflows could not be exercised without valid credentials and
  provisioned workspace data.
- The public health proxy reports process liveness; it should not be read as
  proof of database readiness or private API availability.
- Local latency measurements use an empty SQLite database and 20 sequential
  requests per endpoint. They are not production capacity or SLO evidence.
- The full npm audit reports seven moderate development-toolchain advisories,
  despite a clean production-only audit. Re-evaluate the dependency tree before
  a production release.
- The backend test run currently includes one upstream Starlette/httpx
  deprecation warning.

## Required before production

1. Configure and test hosted authentication, user provisioning, and a secure
   browser session.
2. Deploy PostgreSQL/pgvector migrations and verify RLS with cross-tenant
   integration tests.
3. Establish authorized data-source access and validate freshness, coverage,
   and failure handling on live data.
4. Configure model/embedding providers with privacy, budget, token, and
   rate-limit controls.
5. Add operational monitoring, rate limiting, backups, restore drills, and
   production load/security testing.
6. Resolve or formally accept the development dependency advisories.
7. Re-run the complete suite and authenticated browser workflows against the
   actual deployment environment.
