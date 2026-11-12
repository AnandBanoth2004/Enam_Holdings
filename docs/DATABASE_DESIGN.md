# FINN Database Design

## Design principles

- PostgreSQL is the source of truth; Supabase provides managed Postgres, Auth, and pgvector.
- Separate shared public-company data from investor/workspace-private data.
- Private records carry workspace ownership and must be workspace-scoped by the API. RLS policies are a production deployment requirement and are not installed by the current SQLAlchemy migrations.
- Keep provenance for every source record, extracted metric, and RAG citation.
- Use relational edges for the small relationship graph; no graph database is justified.
- Use UTC timestamps (`timestamptz`), ISO exchange market dates (`date`), explicit currency/unit/basis, and UUID primary keys.

## Entity relationship diagram

```mermaid
erDiagram
  USERS ||--o{ WORKSPACE_MEMBERS : joins
  USERS ||--o{ COPILOT_CONVERSATIONS : owns
  WORKSPACES ||--o{ WORKSPACE_MEMBERS : contains
  WORKSPACES ||--o{ COPILOT_CONVERSATIONS : scopes
  COPILOT_CONVERSATIONS ||--o{ COPILOT_MESSAGES : contains
  WORKSPACES ||--o{ PORTFOLIOS : owns
  PORTFOLIOS ||--o{ PORTFOLIO_COMPANIES : includes
  COMPANIES ||--o{ PORTFOLIO_COMPANIES : tracked
  COMPANIES ||--o{ COMPANY_ALIASES : has
  COMPANIES ||--o{ MARKET_DAILY : priced
  COMPANIES ||--o{ ANNOUNCEMENTS : files
  COMPANIES ||--o{ DOCUMENTS : publishes
  DOCUMENTS ||--o{ DOCUMENT_CHUNKS : split_into
  COMPANIES ||--o{ FINANCIAL_STATEMENT_PERIODS : reports
  FINANCIAL_STATEMENT_PERIODS ||--o{ FINANCIAL_METRICS : contains
  ANNOUNCEMENTS ||--o{ NETWORK_MATCHES : contextualizes
  WORKSPACES ||--o{ NETWORK_PEOPLE : owns
  NETWORK_PEOPLE ||--o{ PERSON_EXPERIENCES : has
  NETWORK_PEOPLE ||--o{ NETWORK_EDGES : connected
  WORKSPACES ||--o{ ALERT_RULES : configures
  WORKSPACES ||--o{ RESEARCH_RUNS : requests
  RESEARCH_RUNS ||--o{ RESEARCH_CITATIONS : cites
  DOCUMENT_CHUNKS ||--o{ RESEARCH_CITATIONS : supports
  WORKSPACES ||--o{ INGESTION_JOBS : queues
```

Supabase Auth remains external and is not recreated by application migrations. `users` is the FINN application profile table; `auth_subject` stores the corresponding external Auth UUID. `workspace_members.user_id` references `users.id`, avoiding a cross-schema FK to `auth.users`.

## Tables

### Identity and tenant boundary

| Table | Important columns | Notes |
|---|---|---|
| `users` | `id`, `auth_subject`, `email`, `display_name`, `synthetic`, timestamps | Application profile keyed to external Supabase Auth through `auth_subject`. |
| `workspaces` | `id`, `name`, `created_at`, `synthetic` | Personal/demo tenant boundary. |
| `workspace_members` | `workspace_id`, `user_id`, `role`, `created_at` | FKs to workspace and application user; unique `(workspace_id,user_id)`. |

### Shared issuer and market data

| Table | Important columns | Notes |
|---|---|---|
| `companies` | `id`, `legal_name`, `display_name`, `sector`, `created_at`, `updated_at` | Global canonical listed issuer. |
| `company_aliases` | `id`, `company_id`, `exchange`, `symbol`, `normalized_symbol`, `alias`, `valid_from`, `valid_to` | Unique exchange + normalized symbol where active. Supports arbitrary supported NSE/BSE symbols. |
| `portfolios` | `id`, `workspace_id`, `name`, `is_default`, `created_at` | Private; RLS by workspace. |
| `portfolio_companies` | `portfolio_id`, `company_id`, `added_at`, `display_order` | Join table; unique `(portfolio_id,company_id)`. |
| `market_daily` | `id`, `company_id`, `exchange`, `market_date`, `open`, `high`, `low`, `close`, `adjusted_close`, `volume`, `daily_change`, `daily_change_pct`, `average_volume_20`, `volume_ratio`, `currency`, `adjusted`, `source`, `fetched_at` | Unique `(company_id,exchange,market_date,source)`. Store decimal OHLC/metrics, integer volume; EOD only. Historical return is range-dependent and computed by the service, not persisted as a canonical fact. |

### Announcements, documents, and financial metrics

| Table | Important columns | Notes |
|---|---|---|
| `announcements` | `id`, `company_id`, `source`, `source_key`, `source_url`, `headline`, `body_text`, `summary`, `filed_at`, `source_timestamp`, `category`, `category_confidence`, `materiality`, `materiality_score`, `materiality_reasons`, `source_payload_hash`, `source_payload`, `raw_document_path`, `retrieval_status`, `fetched_at` | Shared source facts plus derived Push fields. `category` uses the 17 reference labels; unmatched notices go to `unclassified`. Unique `(source,source_key)`. Preserve the original source headline, URL, and payload. Binary files are local-only and subject to source terms. |
| `documents` | `id`, `company_id`, `document_type`, `title`, `source_url`, `source_name`, `period_start`, `period_end`, `period_label`, `published_at`, `reporting_basis`, `language`, `content_hash`, `content_type`, `file_size_bytes`, `storage_path`, `extraction_method`, `extracted_at`, `is_primary_source`, `ingestion_status`, `fetched_at` | Pull accepts annual reports, quarterly results, earnings-call transcripts, and investor presentations only. Checksum is the downloaded PDF SHA-256; changed content creates a new document version. Binary paths are local-only and subject to source terms. |
| `document_chunks` | `id`, `document_id`, `chunk_index`, `page_start`, `page_end`, `section`, `text`, `token_count`, `embedding vector(1536)`, `embedding_model`, `content_hash` | Page-bounded chunks retain page/section provenance. Embeddings use the versioned configured model; a partial unique checksum index prevents duplicate processed document bytes per issuer. |
| `financial_statement_periods` | `id`, `company_id`, `document_id`, `fiscal_year`, `period_label`, start/end, `period_type`, `reporting_basis`, currency, `unit_scale` | Normalized statement period, unique by company/document/period/basis. |
| `financial_metrics` | `statement_period_id`, `document_id`, `metric_key`, `reported_value`, currency, `unit_scale`, `reporting_basis`, page/excerpt, extraction method, confidence, `data_source_id`, `is_synthetic` | One row per metric/period/basis; unique on period/key/basis. Keep reported values distinct from derived calculations and preserve source provenance. When the filing only reports current and non-current borrowings, store those reported lines separately; derive total debt in the report rather than storing the sum as a reported fact. |
| `financial_periods` | Legacy `metric_key`/value observations, period and document provenance | Retained for compatibility with the earlier ingestion pipeline. New normalized statement data uses `financial_statement_periods` and `financial_metrics`. |

Never treat synthetic financial values as company-reported data. Every demo document, period, metric, guidance record, assessment, citation, research result, and corresponding announcement has an explicit synthetic flag and explanatory text.

Store reported values, not calculated comparisons or ratios as authoritative facts. The Pull engine calculates from compatible `financial_statement_periods` and `financial_metrics` at request time. A calculation claim carries citations to every input. It never mixes standalone/consolidated basis, currency, or incompatible periods. Zero/negative prior-period bases suppress percentage growth and instead produce an absolute movement with a limitation. Cash conversion is CFO/PAT; FCF is CFO minus absolute capex; D/E is total debt/equity; ROE uses average opening/closing equity; ROCE uses EBIT divided by average capital employed (assets less current liabilities); working-capital days use closing balances when averages are unavailable.

### Private investor network, preferences, and research

| Table | Important columns | Notes |
|---|---|---|
| `network_people` | `id`, `workspace_id`, `display_name`, `synthetic`, `source_type`, `source_url`, `consent_status`, `created_at`, `updated_at` | Workspace-private PII. Demo rows must use `synthetic=true`. Keep the minimum fields needed. |
| `person_experiences` | `id`, `workspace_id`, `person_id`, `experience_type`, `organization`, `company_id nullable`, `sector`, `title`, `start_date`, `end_date`, `source_label`, `confidence` | Experience types: employment, education, expertise, meeting. Do not assert expertise from an employer alone. Synthetic fixtures remain explicitly labeled. |
| `network_edges` | `id`, `workspace_id`, `from_person_id`, `to_person_id`, `edge_type`, `relationship_strength`, `evidence`, `source_label`, `verified_by_user`, `created_at` | Optional known relationships for second-degree paths. Avoid inferred private links without evidence. |
| `organizations` | `canonical_name`, organization type, optional linked company, sector, source and synthetic flags | Canonical employers for normalized employment history. |
| `educational_institutions` | `canonical_name`, institution type, source and synthetic flags | Canonical education history entities; demo schools are clearly fictional. |
| `person_employment_history` | person, organization/company, title, dates, source, confidence, synthetic flag | Normalized employment records, workspace-scoped and provenance tagged. |
| `person_education_history` | person, institution, qualification/field, dates, source, confidence, synthetic flag | Normalized education records. |
| `network_relationships` | workspace, source/target people, type, strength, evidence, `last_interaction_at`, source, synthetic flag | Normalized relationship graph edge with a uniqueness constraint on the workspace and directed edge identity. Only explicitly evidenced records participate in relationship traversal. |
| `entity_matches` | source, source entity key, candidate key/entity FK, confidence, status, reviewer, rationale | Auditable entity-resolution candidates; a check constraint allows exactly one candidate entity type. |
| `alert_rules` | `id`, `workspace_id`, `company_id nullable`, `rule_type`, `enabled`, `category`, `price_pct_threshold`, `volume_multiplier`, `priority_threshold`, `volume_lookback_days`, `created_at`, `updated_at` | User-configurable announcement category/materiality and EOD thresholds. Volume baseline is fixed to 20 prior sessions. Validate units/ranges in API. |
| `announcement_categories` | unique category key, label, priority | Canonical taxonomy linked to announcements, rules and alerts. |
| `alerts` | workspace, company/announcement/rule links, type, status, unique dedupe key, source, synthetic flag | Materialized alert instances; dedupe keys prevent repeated delivery. |
| `research_runs` | `id`, `workspace_id`, `requested_ticker`, `company_id nullable`, `status`, `requested_at`, `completed_at`, `model_route`, `prompt_version`, `source_manifest jsonb`, `result jsonb`, `error_code` | Private user request/result. Do not store raw prompt by default. Cache keys must not leak across workspaces where prompts include private context. |
| `research_citations` | `id`, `research_run_id`, `chunk_id`, `claim_key`, `page_start`, `page_end`, `quoted_text`, `source_url` | Explicit citations from result claims to source passages. |
| `research_reports` | workspace/company/run, unique report key, status, summary/content, source manifest, model route, source, synthetic flag | Persisted research artifact. Demo content is a disclaimer-only fixture, not investment research. |
| `copilot_conversations` | `id`, `workspace_id`, `user_id`, `title`, timestamps | Private query history; indexed by user, workspace, and update time. Both user and workspace membership are checked on each API operation. |
| `copilot_messages` | `id`, `conversation_id`, `role`, `content`, `result jsonb`, `created_at` | Conversation messages and structured assistant response. Cascades on conversation deletion; relationship paths and citations remain scoped to the owning conversation. |
| `management_guidance` | company/document, guidance key/metric, statement, target range, period, source excerpt/page, confidence, source, synthetic flag | Guidance is source-backed; demo guidance is fabricated and is not an issuer statement. |
| `guidance_assessments` | guidance/document/metric links, outcome, expected/actual values, rationale, synthetic flag | Separately records outcome against later reported metrics; unique per guidance and assessment document. |
| `network_matches` | `id`, `workspace_id`, `announcement_id nullable`, `research_run_id nullable`, `person_id`, `match_type`, `score`, `rationale`, `evidence jsonb`, `created_at` | Private derived recommendation. Store the evidence path, not only a score. |
| `data_sources` | unique source key, source type, primary/terms URLs, enabled and synthetic flags | Stable provenance registry referenced by ingested and derived records. |
| `audit_logs` | workspace/user/source, action, entity reference, JSON metadata, timestamp, synthetic flag | Append-oriented audit history; never place secrets or private prompt text in metadata. |

### Operational ingestion

| Table | Important columns | Notes |
|---|---|---|
| `ingestion_jobs` | `id`, `workspace_id nullable`, `job_type`, `target_key`, `status`, `attempts`, `available_at`, `locked_at`, `locked_by`, `last_error_code`, `created_at`, `completed_at` | Postgres-backed queue. Source-wide public jobs may have null workspace; user-specific jobs must carry tenant scope. Claim jobs transactionally with `FOR UPDATE SKIP LOCKED`. Do not store secrets in job payloads. |
| `source_sync_state` | `id`, `source`, `scope_key`, `last_success_at`, `last_attempt_at`, `cursor`, `status`, `last_error_code` | Supports incremental, observable polling and freshness reporting. Keep source payloads out of logs. |

## Relationships and indexes

- `companies` to aliases, prices, announcements, documents, and financial periods: one-to-many.
- Portfolios to companies: many-to-many through `portfolio_companies`.
- Documents to chunks: one-to-many. Chunks to research citations: one-to-many.
- Workspaces to network, alert, portfolio, research, and recommendation records: one-to-many.
- Copilot conversations belong to one user and workspace; messages cascade with their conversation.
- Network experiences may point to a canonical company, but the original organization string remains for provenance.
- B-tree indexes: `company_aliases(normalized_symbol, exchange)`, `announcements(company_id,filed_at desc)`, `market_daily(company_id,market_date desc)`, `documents(company_id,document_type,period_end desc)`, `financial_periods(company_id,metric_key,period_end desc,reporting_basis)`, and all private tables' `workspace_id`.
- Unique constraints prevent duplicate source records and duplicate portfolio membership.
- `is_synthetic`/`synthetic` flags are set on generated demo records; fixture URLs and source registry entries are not presented as live exchange or issuer sources.
- `ix_documents_primary_period` scopes primary document retrieval by company, type, and period. `uq_documents_company_content_hash` prevents duplicates among successfully processed document versions; discovered URL fingerprints do not block later checksum replacement.
- HNSW/IVFFlat vector index only after expected chunk volume warrants it; start with a simple pgvector cosine query and verify query plans.

## RLS and privacy boundaries

The schema foundation establishes tenant keys and foreign-key relationships, but this implementation does not yet create PostgreSQL RLS policies. Do not expose this database directly to clients or treat API scoping alone as a production privacy boundary. Complete and test the policies below as part of authentication/deployment hardening before production use.

1. Enable RLS on every workspace-owned table. Policies require a matching membership for `auth.uid()` and the row's `workspace_id`. Avoid recursive membership-table policies: use a narrowly scoped `SECURITY DEFINER` membership-check function with a fixed `search_path`, or a carefully isolated membership policy, and grant function execution only to the required database roles.
2. Keep public issuer facts in shared tables. They contain no investor contact graph or preferences; use read-only grants where possible.
3. FastAPI validates the Supabase JWT and derives the user from the verified subject. If a request selects a workspace, the API verifies that user's membership and scopes every query. Never accept `workspace_id` as proof of authorization from a request body.
4. For direct Postgres access, use a restricted non-superuser application role and a transaction-local, JWT-derived user context so RLS policies can be applied. With Supabase's Postgres roles, the API transaction sets the authenticated role and the verified JWT subject claim locally before any private query; use transaction pooling safely and never rely on connection-global session state. Do not use a Supabase `service_role` key in the browser or as the normal API role.
5. The ingestion worker uses a separately held restricted role for public-source tables and job claiming. It does not read or export private network tables. If a job is workspace-specific, validate its tenant scope before work.
6. Keep real network information out of model prompts. Network matching is deterministic in the API; only synthetic demo data is used for testing.
7. Production deletion removes workspace-owned contacts, edges, recommendations, and research runs; retain public issuer documents only under source terms. Set explicit retention for operational logs and any cached private content.

## Migration and seed strategy

- Apply versioned SQL migrations; enable pgvector before creating the chunk embedding column. The current migration head is `0008_copilot_conversations`; it adds user/workspace-scoped conversation and message storage after the Pull and Network migrations.
- Use separate local/development and hosted projects. Never seed real personal contact data.
- Seed 18 provisional portfolio issuers, four ad-hoc issuers outside the portfolio, 36 fictional contacts and their histories, labeled announcement/financial/document fixtures, alerts, guidance, research placeholders and entity mappings. The 18-company list is a starter demo universe, not an official ENAM portfolio.
- To destructively reset and reproduce the local PostgreSQL demo database, run from the repository root with the backend virtual environment:

  ```powershell
  $env:FINN_DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:54322/postgres"
  $env:FINN_APP_ENVIRONMENT = "development"
  backend\.venv\Scripts\python.exe scripts\reset_and_seed_demo.py --confirm-reset
  ```

  The command requires `--confirm-reset`, refuses production and non-local PostgreSQL URLs, drops only tables in the FINN application's SQLAlchemy metadata plus `alembic_version`, and does not drop Supabase Auth tables or extensions. Use only a disposable local database.
- Keep production credentials and source/model keys in deployment secret stores, never in migrations, fixtures, or committed `.env` files.
