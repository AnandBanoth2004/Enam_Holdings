# FINN API Specification

## Conventions

- Base path: `/api/v1`.
- Transport: HTTPS JSON REST. FastAPI publishes the authoritative OpenAPI document for generated client/type checks.
- Browser calls go through Next.js server-side BFF routes. The BFF forwards a Supabase Auth access token to FastAPI as `Authorization: Bearer <JWT>`.
- FastAPI validates the JWT, derives the user from the verified subject, and validates membership for the requested workspace. A client-supplied workspace ID is never authorization.
- IDs are UUIDs; timestamps are ISO-8601 UTC. Market periods use exchange-local market dates.
- JSON fields use `snake_case`; amounts include currency/unit and period/basis metadata.
- Long-running ingestion/research jobs return `202 Accepted` and a status URL. UI polls; no WebSocket/SSE requirement.

## Common error envelope

```json
{
  "error": {
    "code": "data_unavailable",
    "message": "No supported primary documents were found for this ticker.",
    "request_id": "uuid",
    "details": {
      "ticker": "EXAMPLE"
    }
  }
}
```

Use standard HTTP status codes: `400` invalid input, `401` missing/invalid token, `403` not authorized, `404` resource absent, `409` duplicate/conflicting operation, `422` validation failure, `429` rate limit, `502` upstream source failure, `503` temporarily unavailable. Do not return stack traces, provider secrets, or success-shaped empty data for failures.

## Authentication

Supabase Auth owns sign-in, session refresh, and user identity. The browser receives a secure, HttpOnly/SameSite session cookie managed by the Next.js BFF. The BFF forwards a short-lived access JWT; FastAPI checks signature, issuer, audience, and expiry using Supabase JWKS. The API checks workspace membership on every private operation.

For a review/demo environment, provide a read-only demo account or public synthetic fixtures through a restricted demo workspace. Do not disable auth or expose private workspace endpoints anonymously.

**Implementation status:** FastAPI validates Supabase-compatible JWT signatures
against the configured JWKS URL and checks issuer, audience, expiry, and subject.
The verified `sub` must map to a provisioned `users.auth_subject`; workspace
membership is checked for private Push, Network, and saved research-report
operations, including Copilot conversations. Document discovery, ingestion,
financial extraction, and RAG answer generation also require a valid user JWT;
they operate on shared company-source data and do not accept a workspace ID.
Company search and non-workspace financial reads remain public. The caller may
select a workspace for private operations but cannot gain access by merely
supplying its UUID. Configure `FINN_AUTH_JWKS_URL`, `FINN_AUTH_ISSUER`, and
`FINN_AUTH_AUDIENCE`; without issuer/JWKS configuration, protected routes fail
closed with `503`. Production RLS remains a separate required defense-in-depth
step.

## Implemented Push endpoints

The current FastAPI implementation exposes the following routes under
`/api/v1/push`:

| Method and path | Purpose |
|---|---|
| `GET /digest` | Portfolio announcement digest; `window=24h` (default), `48h`, `7d`, or `custom`; custom uses timezone-aware `start` and `end`. Repeat `ticker`, `category`, and `priority` to filter. |
| `GET /announcements/{announcement_id}` | Filing details, source metadata, explanation, synthetic marker, and bounded workspace network context. |
| `POST /classify` | Classify/score a headline and optional body, or an existing `announcement_id`. |
| `GET /announcements/{announcement_id}/materiality` | Stored score and rule reasons. |
| `GET /alerts/config` | Get alert rules for a workspace and optional portfolio ticker. |
| `PUT /alerts/config` | Configure EOD price move, volume, announcement categories, and materiality thresholds. |
| `GET /alerts/history` | Persisted alert history, optionally filtered by ticker and type. |
| `PATCH /alerts/{alert_id}/status` | Mark an alert `read` or `unread`; the alert must belong to the supplied workspace. |
| `POST /alerts/evaluate` | Evaluate latest eligible end-of-day market bars. |
| `GET /results/{ticker}/comparisons` | Revenue, EBITDA, PBT, and PAT period comparisons from persisted source-backed metrics. |

The `GET /digest` `limit` is bounded from 1 to 500. Alert configuration
thresholds are positive and capped at 100; category values are restricted to
the 17 reference labels. Market evaluation is EOD-only and uses a fixed
20-session volume baseline. `docs/PUSH_INTELLIGENCE.md` defines scoring,
missing-period behavior, response semantics, and limitations.

Announcement details include the original source headline and a boolean
`is_synthetic` marker. Financial period values include `is_synthetic`, derived
from their source period/metric, so clients can visibly label demonstration
figures without inferring their status.

## Implemented Copilot endpoints

The authenticated Copilot routes are under `/api/v1/copilot`. All conversation
operations require workspace membership and additionally scope saved
conversations by both `user_id` and `workspace_id`.

| Method and path | Purpose |
|---|---|
| `POST /query` | Route a bounded question to Push, Pull, Network, or a supported combination; return answer blocks, tool statuses, citations, and limitations; persist the exchange. |
| `GET /conversations?workspace_id=...&limit=30` | List only the caller's conversations in the selected workspace. |
| `GET /conversations/{conversation_id}?workspace_id=...` | Return ordered messages and the validated structured result for assistant messages. |
| `DELETE /conversations/{conversation_id}?workspace_id=...` | Delete only a conversation owned by the caller in that workspace. |

`POST /query` accepts `workspace_id`, a 3–2,000 character `query`, and an
optional `conversation_id`. The response identifies the selected intent/layers,
each invoked service and its `complete`/`partial`/`unavailable` status, source
citations, synthetic markers, and limitations. It does not claim unavailable
tool results succeeded. Private history responses use `Cache-Control:
private, no-store`. The current router uses deterministic intent rules; it
does not pass private Network profiles or relationship paths to a model.

## Endpoint catalog

| Method and path | Purpose | Authorization / notes |
|---|---|---|
| `GET /health/live` | Process liveness | No sensitive details; no DB dependency. |
| `GET /health/ready` | DB/source readiness | Protected or minimal public response; do not expose connection details. |
| `GET /portfolio` | List current workspace portfolios and company counts | Authenticated workspace member. |
| `GET /portfolio/{portfolio_id}/digest` | Windowed announcement digest | `from`/`to` ISO timestamps; default last 24 hours; supports category, importance, and `include_routine`. |
| `GET /companies/resolve?ticker=...` | Resolve NSE/BSE ticker dynamically | Authenticated; returns canonical issuer and supported source availability. Not restricted to demo list. |
| `GET /companies/{company_id}/market` | EOD close/volume history | `from`, `to`, `interval=1d`; returns timestamp/freshness/source metadata. |
| `GET /announcements` | Search workspace portfolio announcements | Filters `ticker`, `category`, `from`, `to`, `materiality`, cursor pagination. |
| `GET /alert-rules` | List current workspace alert preferences | Authenticated. |
| `POST /alert-rules` | Create configurable filing/EOD threshold | Validate threshold bounds and allowed category values. |
| `PATCH /alert-rules/{rule_id}` | Update or disable a rule | Workspace ownership required. |
| `GET /alerts` | List fired alerts | Cursor pagination; includes evaluated values and source freshness. |
| `POST /research` | Start company research for any supported ticker | Returns `202` run ID; only primary sources are eligible for Pull retrieval. |
| `GET /research/{run_id}` | Poll research status/result | Workspace ownership required. |
| `GET /research/{run_id}/sources` | Get citation/source manifest | Workspace ownership required. |
| `POST /network/matches` | Find useful contacts for a company/event/person | Uses deterministic private graph matching; may accept `company_id`, `announcement_id`, `person_name`, `sector`, or a bounded `query_type`. |
| `GET /network/people/{person_id}` | Read a contact profile and evidence path | Workspace ownership required; synthetic status/source visible. |
| `POST /network/people` | Add a user-authorized or synthetic contact | Explicit source and consent fields; never accept scraped restricted-profile data. |
| `POST /internal/ingestion/jobs` | Queue an ingestion task | Internal worker/admin credential only; not exposed through browser BFF. |

## Representative contracts

### Portfolio digest

`GET /api/v1/portfolio/{portfolio_id}/digest?from=2026-11-10T00:00:00Z&to=2026-11-11T00:00:00Z&include_routine=false`

```json
{
  "portfolio_id": "uuid",
  "window": {
    "from": "2026-11-10T00:00:00Z",
    "to": "2026-11-11T00:00:00Z",
    "timezone": "Asia/Kolkata"
  },
  "as_of": "2026-11-11T00:15:00Z",
  "items": [
    {
      "announcement_id": "uuid",
      "ticker": "EXAMPLE",
      "company_name": "Example Industries Ltd.",
      "category": "results",
      "category_confidence": 0.98,
      "priority": "high",
      "headline": "Unaudited financial results for the quarter ended ...",
      "summary": null,
      "filed_at": "2026-11-10T13:15:00Z",
      "source_url": "https://issuer.example/filing.pdf",
      "freshness": "current",
      "financial_comparison": null,
      "network_matches": []
    }
  ],
  "collapsed_count": 4
}
```

The client may request `include_routine=true` to expand `unclassified`/low-priority items. Digest ordering and alert thresholds are computed server-side.

### EOD alert rule

`POST /api/v1/alert-rules`

```json
{
  "name": "Unusual volume",
  "rule_type": "volume_multiple",
  "portfolio_id": "uuid",
  "enabled": true,
  "volume_multiplier": 2.0,
  "volume_lookback_days": 20
}
```

Alternative `rule_type: "price_move_pct"` uses a signed threshold or absolute direction fields explicitly. Validation rejects zero/negative lookback, out-of-range multipliers, and ambiguous units. Response includes generated ID, normalized configuration, and `effective_after` market date. The rule is evaluated after EOD data is available; it is not an intraday alert.

### Financial result data

Each metric object carries provenance:

```json
{
  "metric": "EBITDA",
  "reported_value": "1250.00",
  "currency": "INR",
  "unit_scale": "crore",
  "period": {
    "label": "Q2 FY2026-27",
    "start": "2026-07-01",
    "end": "2026-09-30",
    "basis": "consolidated"
  },
  "source": {
    "document_id": "uuid",
    "url": "https://issuer.example/results.pdf",
    "page": 4,
    "excerpt": "..."
  },
  "comparison": {
    "qoq": {
      "period_label": "Q1 FY2026-27",
      "value": "1100.00",
      "absolute_change": "150.00",
      "percent_change": "13.64"
    },
    "yoy": null
  }
}
```

Use decimal strings in transport to avoid client floating-point errors. If comparison is missing or not meaningful (e.g. zero/negative base), return an explicit reason and absolute change where valid; do not fabricate percentages. `Revenue`, `EBITDA`, `PBT`, and `PAT` use the reference PDF definitions. QoQ means preceding quarter; YoY means same quarter a year earlier.

### Research run

`POST /api/v1/research`

```json
{
  "ticker": "EXAMPLE",
  "sections": ["business_snapshot", "financial_snapshot", "narrative_vs_numbers"],
  "reporting_basis": "consolidated",
  "as_of": "2026-11-11"
}
```

`202 Accepted` response:

```json
{
  "research_run_id": "uuid",
  "status": "queued",
  "status_url": "/api/v1/research/uuid",
  "resolved_company": {
    "company_id": "uuid",
    "ticker": "EXAMPLE",
    "company_name": "Example Industries Ltd."
  },
  "source_availability": {
    "annual_reports": "available",
    "quarterly_results": "partial",
    "earnings_call_transcripts": "unavailable"
  }
}
```

Completed runs return sections as structured claims, each with `claim_type` (`reported_fact`, `calculation`, `interpretation`), text, citation IDs, and confidence/status. If no primary documents exist, return `status: "data_unavailable"` plus source discovery details; never substitute outside model knowledge.

### Network matches

Network endpoints require a valid bearer JWT and a workspace membership:

| Method and path | Purpose |
|---|---|
| `GET /api/v1/network/contacts?workspace_id={uuid}&q={text}&limit={n}` | Search workspace-private synthetic or consented contacts, experience, expertise, and explicitly evidenced connection paths. |
| `GET /api/v1/network/contacts/{contact_id}?workspace_id={uuid}` | Read a contact only within the authorized workspace. |
| `GET /api/v1/network/expertise?workspace_id={uuid}&q={text}` | Find contacts by recorded role, sector, employer, or expertise text. |
| `GET /api/v1/network/companies/{ticker}/connections?workspace_id={uuid}` | Find matching company experience by NSE ticker and return match evidence. Employer overlap is not represented as a personal connection. |
| `GET /api/v1/network/second-degree?workspace_id={uuid}` | Traverse only explicitly recorded first-/second-degree relationships. |
| `GET /api/v1/network/paths/{contact_id}?workspace_id={uuid}` | Explain the recorded one- or two-hop relationship path, or report no path. |
| `GET /api/v1/network/recommendations?workspace_id={uuid}&workflow={workflow}` | Rank `who_to_call`, `second_degree_reach`, `management_diligence`, `sector_expertise`, or `keep_warm` recommendations with reasons and evidence. Optional parameters: `ticker`, `executive`, `expertise`, and `limit`. |

Executive name matches from management-change announcements or saved research
reports are persisted as `entity_matches` with confidence and rationale. Exact
matches are preferred; fuzzy person-name matches require at least 0.96
similarity, are marked proposed, and do not establish identity or acquaintance.
Company-name fuzzy matching uses stricter multi-token matching; a match is not a
relationship. Synthetic fixture responses explicitly identify themselves as
fictional.

`POST /api/v1/network/matches` remains the documented target for richer
company-context and topic-expertise match payloads; the current implementation
uses the routes listed above.

```json
{
  "company_id": "uuid",
  "announcement_id": "uuid",
  "query_type": "company_context",
  "topic": null,
  "limit": 3
}
```

For a direct expertise query, use `query_type: "topic_expertise"` and provide a bounded `topic` such as `"specialty chemicals"`; the backend matches explicit experience/expertise records, not arbitrary model inference.

Response:

```json
{
  "matches": [
    {
      "person_id": "uuid",
      "display_name": "Synthetic Contact A",
      "synthetic": true,
      "match_type": "former_employer",
      "relationship_hops": 1,
      "relevance_score": 0.86,
      "rationale": "Worked at this issuer from 2021 to 2024.",
      "evidence": [
        {
          "kind": "employment",
          "organization": "Example Industries Ltd.",
          "start_date": "2021-01-01",
          "end_date": "2024-01-01",
          "source_label": "synthetic demo profile"
        }
      ]
    }
  ]
}
```

Scores rank evidence; they do not represent verified closeness or willingness to advise. Identity ambiguity returns no asserted match and a review-required status.

## Validation and operational behavior

- Pydantic request models enforce allowed categories, date ordering, maximum time range, result section names, and alert bounds.
- Use cursor pagination and bounded result sizes for feeds.
- Add idempotency keys for research submission and ingestion enqueue where client retries could duplicate work.
- Upstream failures return an explicit error or partial-source status; preserve available data and mark missing sources.
- Redact tokens, full network payloads, and raw personal details from structured logs.
- Apply per-user and per-IP rate limits to costly research operations; cache completed evidence-grounded runs where safe.

## Implemented Pull document and research endpoints

The current FastAPI implementation exposes the following routes under
`/api/v1/research`:

| Method and path | Purpose |
|---|---|
| `POST /discover` | Resolve an NSE ticker to its issuer site and persist discovered annual reports, quarterly results, earnings-call transcripts, and investor presentations. |
| `POST /documents/{document_id}/ingest` | Download and validate a discovered PDF, extract page text/tables, chunk it, and embed it when a model provider is configured. |
| `POST /answer` | Retrieve primary-source passages using ticker/type/period filters and return structured claims with verified citations or an explicit insufficient-evidence response. |

`POST /discover` accepts `{"ticker":"RELIANCE"}`. Ticker resolution is not an
allowlist: an unseeded NSE symbol may be added after the profile's ticker,
issuer name, and HTTPS company website are validated. yfinance profile data is
used only as an issuer-site pointer, never as research evidence. Additional
company-authorized CDN hosts can be configured through
`FINN_DOCUMENT_ALLOWED_HOSTS`.

`POST /documents/{document_id}/ingest` accepts an optional `expected_period`
and `max_chunk_tokens` (40–1,400; default 700). The response includes processing
status, page/chunk counts, embedding status, extracted period, and duplicate
version information. PDFs over the configured 30 MiB limit, non-PDF content,
company/type/period mismatches, and scanned pages without an available OCR
engine fail explicitly.

`POST /answer` accepts:

```json
{
  "ticker": "RELIANCE",
  "question": "What does management say about retail operations?",
  "document_types": ["annual_report", "earnings_call_transcript"],
  "period_start": "2025-04-01",
  "period_end": "2026-03-31",
  "top_k": 8
}
```

Allowed document types are `annual_report`, `quarterly_result`,
`earnings_call_transcript`, and `investor_presentation`. Each factual claim
contains one or more citation objects with `document_name`,
`reporting_period`, one-based `page_number`, original `source_url`, verbatim
`quote`, and `is_synthetic`. Citations are constructed from retrieved database
rows, not model-generated URLs or page references. The API rejects unreturned
chunk IDs and quotes that do not appear in the referenced chunk.

Without `FINN_RESEARCH_API_KEY`, the answer status is `evidence_only`; claims
are source excerpts and retrieval is lexical. With a configured compatible
provider, the default embedding model is `text-embedding-3-small` (1,536
dimensions) and the configured structured-output model is used for synthesis.
No-key operation does not generate placeholder vectors or claim semantic
ranking. An empty evidence set returns `insufficient_evidence` with no claims.

## Implemented financial research endpoints

The deterministic financial engine exposes these additional routes under
`/api/v1/research`:

| Method and path | Purpose |
|---|---|
| `GET /companies/search?q=...&limit=20` | Search canonical company names and supported NSE tickers, including ad-hoc companies. |
| `POST /documents/{document_id}/extract-financials` | Extract uniquely labeled, single-value financial rows from an ingested primary document and persist source-backed metrics. |
| `GET /companies/{ticker}/financial-metrics?reporting_basis=consolidated` | List extracted metrics by financial period, with units and provenance. |
| `POST /companies/{ticker}/report` | Build and persist all eight research dimensions for the requested reporting basis and up to four guidance quarters. |
| `GET /companies/{ticker}/report?workspace_id={uuid}` | Read the latest saved non-synthetic report in the supplied workspace. |
| `GET /companies/{ticker}/financial-trajectory?reporting_basis=consolidated` | Read annual revenue/EBITDA/PAT trajectory and deterministic comparisons. |
| `GET /companies/{ticker}/guidance?quarters=4&reporting_basis=consolidated` | Read commentary and explicit numerical guidance from the latest available transcript periods. |
| `GET /companies/{ticker}/narrative-comparison?reporting_basis=consolidated` | Read management statements, explicit targets, actuals, variances, assessment, and citations. |
| `GET /companies/{ticker}/bull-bear?reporting_basis=consolidated` | Read source-backed bull/bear considerations, explicitly not recommendations. |
| `GET /companies/{ticker}/sources` | List eligible primary-source documents and their provenance. |

Financial extraction request:

```json
{
  "period_label": "Q1 FY2026",
  "period_start": "2025-04-01",
  "period_end": "2025-06-30",
  "period_type": "quarter",
  "reporting_basis": "consolidated",
  "currency": "INR",
  "unit_scale": "crore"
}
```

The caller supplies period, basis, currency, and default unit; the service does
not infer these from a comparative table. A response reports extracted metric
keys and values plus ambiguous metric keys that were withheld. Multi-value
rows are not guessed.

Research report request:

```json
{
  "workspace_id": "uuid",
  "reporting_basis": "consolidated",
  "quarters": 4
}
```

Every section separates reported facts, calculations, and interpretations.
Claims include source document, reporting period, page, URL, and excerpt where
available. Ratio conventions and unavailable inputs are surfaced in the
section's observations/limitations. Reported financial values preserve their
currency, unit scale, period, and reporting basis; calculated values do not
replace reported values.

**Remaining security limitations:** PostgreSQL RLS, rate limiting, production
user provisioning, and an end-user sign-in/session-cookie flow are not yet
implemented. Private Push, Network, and saved-report API routes reject missing
or invalid JWTs and enforce membership, but do not deploy with real user data
until the remaining controls are complete.
