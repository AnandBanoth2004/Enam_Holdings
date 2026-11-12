# FINN Data Security and Privacy

## Scope

This document describes controls visible in the current repository and
separates them from controls still required before real investor or contact
data is used. It is not a security certification. The test report and
[known limitations](./KNOWN_LIMITATIONS.md) remain authoritative for what was
actually verified.

## Data classes and current demo

| Data class | Current source and treatment | Real or synthetic? |
|---|---|---|
| Company names, legal names, and NSE symbols | Catalog/aliases in the demo seed identify public companies. | Company identifiers correspond to real issuers; the seeded portfolio is provisional, not ENAM's portfolio. |
| Price, announcement, results, metrics, and report values in demo seed | Fixture records are marked as demo/synthetic and are intended to exercise UI and service behavior. | Synthetic; not company-reported, not live, and not investment evidence. |
| Document examples under `data/fixtures/documents` | Fabricated text outlines and sample statements. | Synthetic; not issuer documents or primary-source evidence. |
| Network contacts and career/education histories | Seeded fictional profiles and relationships, with explicit synthetic markers. | Synthetic; not real people, LinkedIn exports, or verified professional records. |
| External market/filing/document records | Adapters can retrieve data from yfinance, public exchange endpoints, and issuer-authorized sites when run. | Potentially real source data when retrieved; live coverage, correctness, permissions, and freshness were not verified in the final QA environment. |
| Investor network data in a future deployment | Not collected from a real investor in the reviewed prototype. | Not present. Obtain consent and define retention before collection. |
| Authentication token | A user-provided bearer token is held in browser `sessionStorage` by the prototype. | Sensitive credential; avoid using real production credentials in this prototype. |

The original ENAM PDFs are present locally and excluded from Git by exact-name
ignore rules. Do not publish them unless redistribution is authorized.

## Implemented access controls

- Private API routers require bearer JWT validation. `PyJWT` resolves signing
  keys from configured JWKS and validates signature, allowed algorithm,
  expiration, subject, issuer, and audience.
- The subject must map to a provisioned FINN user. Private requests also check
  that the user is a member of the requested workspace.
- Research, Push, Network, and Copilot data access is scoped through user or
  workspace identity in service queries. Copilot conversation reads and
  writes include both authenticated user and workspace.
- CORS is restricted to configured origins. Production configuration rejects
  wildcard/non-HTTPS origins, local database URLs, and missing/invalid HTTPS
  authentication issuer/JWKS settings.
- Backend request logs include a request ID, method, path, status, and
  duration; access tokens and prompt bodies are not intentionally logged by
  the request middleware.
- Document fetching is HTTPS-only, validates discovered/allowed hosts across
  redirects, checks PDF signature and size, and stores content by hash.
- Pull rejects synthetic documents by default. Synthetic fixtures remain
  explicitly labeled in API results.
- Network recommendations are computed inside the application; names,
  profiles, contact edges, and relationship paths are not passed to the
  external model provider.
- Optional model requests use public primary-source document excerpts only.
  Review provider retention and training terms before enabling them with any
  non-public content.

These are application-level controls. They do not establish production-grade
tenant isolation.

## Known gaps and risks

1. **No production sign-in flow.** The current UI has manual bearer-token
   entry and stores the token in `sessionStorage`, which is accessible to
   same-origin JavaScript. Replace it with a reviewed OAuth/OIDC flow and
   appropriately protected HttpOnly cookies before production.
2. **No PostgreSQL RLS.** The database does not currently enforce tenant
   boundaries independently of API code. Add and test RLS policies for
   workspace-owned tables, including negative cross-tenant tests.
3. **No real contact data.** There is no consent workflow, provenance review,
   contact correction/deletion process, retention schedule, or import/export
   policy. Do not load real investor contacts until those exist.
4. **No defined retention/deletion policy.** Local PDF content, derived
   chunks, reports, audit events, and conversations have no deployed
   retention job or verified deletion lifecycle. Specify deletion propagation
   before production.
5. **No deployed secrets manager or hosted service.** No Vercel, Render, or
   Supabase project has been configured. Production variables are documented
   as provider-side settings but have not been set or verified.
6. **No production rate limiting or security monitoring.** Access controls,
   request logging, and bounded operations do not replace abuse detection,
   alerting, backups, incident response, and penetration testing.
7. **Local document storage only.** `data/documents` is not encrypted object
   storage, and source retention/licensing obligations are not automatically
   enforced.
8. **Potentially external disclosure.** If the optional model provider is
   enabled, retrieved public filing excerpts leave the application boundary.
   The code avoids sending network contact data, but provider terms and
   regional processing still require approval.

## Production privacy requirements

Before accepting private contact data or investor research:

- Implement hosted identity and a secure session lifecycle; remove manual
  token handling from the normal UI.
- Add PostgreSQL RLS and test direct SQL/API cross-tenant access, including
  background jobs and report/document relationships.
- Collect only necessary fields, with documented purpose, consent, correction,
  export, retention, and deletion controls.
- Set explicit retention periods for raw documents, extracted text, prompts,
  reports, and conversation history; deletion must cover files, chunks,
  embeddings, caches, and backups according to policy.
- Configure and rotate secrets only through provider secret stores; restrict
  database and model-provider credentials to least privilege.
- Establish approved source terms, model-provider terms, logging redaction,
  rate limits, monitoring, incident response, and tested backup/restore.
- Keep synthetic fixture markers in all development and evaluation
  environments so demonstration data cannot be mistaken for real records.

## Verification status

The repository's automated tests cover authentication and ownership logic,
and the QA report records anonymous private-route requests returning 401.
The report does **not** show deployed identity verification, PostgreSQL RLS,
cross-tenant SQL isolation, real-contact handling, production key management,
or a penetration test. Those remain open release gates.
