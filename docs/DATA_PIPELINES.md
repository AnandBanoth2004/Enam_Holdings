# FINN Data Pipelines

## Scope and trust boundary

The data layer provides independent source adapters, validation, provenance, local fixtures, cache/persistence hooks, and command-line entry points. Push classifies and scores persisted announcements. Pull discovers, downloads, validates, extracts, chunks, indexes, retrieves, and cites eligible company primary documents. Network matching, explicit relationship traversal, ranking, and the Company Research UI are implemented; production sign-in and database RLS remain incomplete.

All source-derived records carry a source identifier and retrieval time. The 18-symbol starter set and the contact/announcement fixtures are demo inputs, not an official ENAM portfolio or real-world data. Demo fixtures carry `demo_fixture` / `synthetic_fixture` labels. They must not be presented as live exchange data or real people.

## Module layout

| Module | Responsibility |
|---|---|
| `finn_api.data_pipeline.validation` | NSE ticker normalization, OHLCV validation, duplicate-session handling, and deterministic market metric calculations. |
| `finn_api.data_pipeline.market_data` | yfinance EOD adapter, configurable symbols/date range, warm-up fetch, per-ticker result/error statuses, and cache interface. |
| `finn_api.data_pipeline.market_repository` | PostgreSQL cache upserts into `market_daily` and per-ticker freshness in `source_sync_state`. |
| `finn_api.data_pipeline.announcements` | Independent NSE/BSE public adapters, metadata normalization/deduplication, explicit demo fallback, PDF storage policy, and persistence. |
| `finn_api.data_pipeline.company_documents` | Bounded same-issuer-site crawler, document type discovery, source validation, and discovery freshness persistence. |
| `finn_api.pull.pdf_processing` | Page-preserving PDF text/table extraction, issuer/type/period checks, and OCR for sparse/scanned pages. |
| `finn_api.pull.ingestion` | Checksum deduplication, document versioning, page-bounded chunk persistence, and optional versioned embeddings. |
| `finn_api.pull.retrieval` | Company/type/period-filtered pgvector or lexical retrieval with context limits and an in-process cache. |
| `finn_api.pull.answering` | Structured evidence-only responses and hard validation of retrieved chunk IDs and verbatim citation quotes. |
| `finn_api.data_pipeline.network_seed` | Fictional profile fixture validation and workspace-scoped, idempotent seed loading. |
| `scripts/ingest_market_data.py` | Fetches and caches EOD market history. |
| `scripts/ingest_announcements.py` | Polls NSE and BSE public announcement endpoints and stores results/status. |
| `scripts/discover_company_documents.py` | Discovers primary issuer documents for any syntactically supported NSE ticker. |
| `scripts/demo_pull_research.py` | Reproduces discovery, ingestion, retrieval, and citation from a selected issuer document. |
| `scripts/seed_network_data.py` | Seeds 36 explicitly fictional profiles into a specified workspace. |

No separate cache, queue, graph database, or model is introduced.

## A. EOD market data

### Symbols and requests

The provisional demo universe is in `FINN_MARKET_TICKERS` in `.env`, defaulting to 18 NSE symbols also represented by `data/seed/demo_seed.json`. The list is configurable; the market service accepts any ticker that passes symbol validation and does not enforce that list as an allowlist.

```powershell
python scripts\init_db.py
python scripts\seed_data.py
python scripts\ingest_market_data.py --start 2026-10-01 --end 2026-11-10
python scripts\ingest_market_data.py --start 2026-10-01 --end 2026-11-10 --tickers RELIANCE,TCS
```

`start` and `end` are inclusive exchange-session dates. yfinance's exclusive end is advanced by one calendar day. The adapter requests daily history (`interval=1d`, `auto_adjust=False`) only. It does not claim or supply live/intraday prices. Before 16:00 Asia/Kolkata, a bar dated today is excluded so an unfinished session is not presented as an EOD close. `fetched_at` records retrieval time; `market_date` is the source session date.

The adapter preserves Open, High, Low, Close, Volume, and `Adj Close` when supplied. Missing adjusted close remains null; it is never fabricated from Close. Incomplete OHLCV rows are excluded, invalid/non-positive prices, negative or fractional volume, and inconsistent OHLC bounds raise a validation error. Duplicate normalized session dates retain the last source row.

### Deterministic calculations

- `daily_change = Close(t) - Close(t-1)`.
- `daily_change_pct = (Close(t) / Close(t-1) - 1) * 100`.
- `average_volume_20` is the mean volume of the **20 preceding completed sessions**, not including the current row.
- `volume_ratio = current Volume / average_volume_20`; it is unavailable when the full baseline is absent or zero.
- `historical_return_pct` is cumulative from the first session in the requested date range, using adjusted close where it is available and Close otherwise.

The service fetches at least 60 calendar days before `start` to warm the 20-session volume baseline. The result contains only the requested inclusive range, while the cache can retain warm-up bars. PostgreSQL's unique key `(company_id, exchange, market_date, source)` prevents duplicate market rows across retries. PostgreSQL is the durable cache; the in-memory cache is for local/test use only. Default freshness TTL is six hours, configurable with `FINN_MARKET_CACHE_TTL_SECONDS`.

The repository expects an NSE alias to resolve the ticker to a canonical company before persistence. A missing alias is a mapping error, not a silently created company. Each successful or failed source attempt records status and timestamps in `source_sync_state`.

## B. Corporate announcements

`NSEAnnouncementsAdapter` uses `https://www.nseindia.com/api/corporate-announcements`. `BSEAnnouncementsAdapter` uses `https://api.bseindia.com/BseIndiaAPI/api/AnnSubCategoryGetData/w`. They use standard HTTPS requests, bounded timeouts, ordinary public headers, and no cookie harvesting, CAPTCHA evasion, proxy rotation, or access-control bypass. Endpoint availability/response shape is not guaranteed; source failures are returned as `source_unavailable` or `invalid_response_schema`.

The adapters normalize source identity, exchange, ticker/scrip, headline, filing timestamp, original attachment URL, raw source payload hash, and fetched timestamp. Naive exchange filing timestamps are interpreted in `Asia/Kolkata`; timestamp offsets are retained. Results are deduplicated by `(source, source_key)` and company mapping is resolved through `(exchange, normalized_symbol)`. Unmapped filings are not inserted into the company-linked table.

The discovery service records per-source status and falls back to `data/fixtures/announcements.json` only when live adapters return no records. Each fixture is clearly marked `[DEMO ONLY]`, stored with `source=demo_fixture`, and never labeled as an exchange response. Source freshness is written to `source_sync_state`; filing records store `retrieval_status`, original source URL/timestamp, fetch time, source payload/hash, and local raw-document path when downloaded. Retrieved records are passed through deterministic Push classification/materiality and enabled announcement rules before the ingestion command completes. Demo fallback records retain their synthetic marker.

Public attachments are downloaded only when the caller configures `RawAnnouncementDocumentStore`. It accepts HTTPS hosts under `nseindia.com` / `bseindia.com`, checks the final response host and PDF signature, enforces a 20 MiB limit, hashes content, and uses a hash-only filename under `data/documents/`. That directory is git-ignored; source licensing and retention terms still apply.

```powershell
python scripts\ingest_announcements.py --start 2026-11-01 --end 2026-11-10
python scripts\ingest_announcements.py --start 2026-11-01 --end 2026-11-10 --ticker RELIANCE
```

An endpoint returning an empty list is a successful retrieval with zero records, not proof that no filing exists. A fallback fixture remains visibly synthetic.

## C. Primary company document discovery

`CompanyDocumentDiscoveryService.discover(ticker, issuer_website=...)` accepts any valid NSE symbol, including symbols not in the demo universe. It starts from a company website, follows a bounded number of relevant same-site IR links, and recognizes annual reports, quarterly results, earnings-call transcripts, and investor presentations. The crawl is depth-limited to two links, capped at 12 pages and 3 MiB per HTML page. External domains are excluded unless explicitly allowed by the caller as company-authorized document hosts.

If no issuer URL is supplied, `YFinanceIssuerWebsiteResolver` may use the yfinance company-profile `website` field **only as a discovery pointer**. The resulting evidence links must still be on the issuer's website/explicitly authorized host; Yahoo Finance content is not returned as company research evidence. If no primary issuer website can be resolved, the result is `unavailable`, not a canned company result.

Discovery records preserve the document URL, source hostname, link title, discovery page, type, URL fingerprint, and retrieval time. Download/parse/embedding happens in the separate Pull ingestion service. The API can resolve an unmapped NSE ticker from verified yfinance metadata, creating a canonical company mapping; yfinance remains a discovery pointer, not research evidence. Persistence is idempotent across repeated discovery calls.

```powershell
python scripts\discover_company_documents.py --ticker RELIANCE
python scripts\discover_company_documents.py --ticker NEWCO --issuer-website https://investors.example.com
```

If a company's filings are hosted on a separate authorized CDN, specify its hostname with `--allowed-document-host` or configure `FINN_DOCUMENT_ALLOWED_HOSTS`. Do not use secondary research pages as the source for extracted financial evidence.

### Pull document processing and retrieval

`POST /api/v1/research/documents/{id}/ingest` accepts only a discovered primary-source document in one of the four research types. The downloader enforces HTTPS, a verified source host, PDF MIME/signature, a 30 MiB default size ceiling, and final issuer/type/optional-period validation. It records the actual PDF SHA-256, file size/type, extracted period, extraction/OCR method, and local ignored storage path. Repeated unchanged downloads reuse the indexed version; changed content creates a new document version and preserves prior chunks/citations.

`pdfplumber` keeps page boundaries and extracts tables. Empty/scanned pages alone use PyMuPDF + `pytesseract`; if the system Tesseract executable is not installed, ingestion returns `ocr_unavailable`. Chunks remain within one page and retain section, source URL (through the parent document), period, type, and content hash. Optional OpenAI-compatible embeddings use `text-embedding-3-small` / 1,536 dimensions and pgvector. Without a configured model key, documents remain `extracted`, and the answer endpoint explicitly uses keyword retrieval and verbatim excerpts rather than claiming vector search or generated analysis.

`POST /api/v1/research/answer` scopes candidates by canonical issuer before filtering to primary source, supported type, requested period, and non-synthetic evidence. It limits top-k/context and caches retrieval for five minutes in process. Every output citation is built by the API from a retrieved chunk and contains document title, period, one-based page number, original URL, and an exact quote. Unknown chunk IDs and non-verbatim quotes fail validation; missing evidence produces no claims.

Run the end-to-end live-source demonstration using the commands and official Reliance annual-report URL in `docs/RAG_ARCHITECTURE.md`. Model keys are optional; source documents and model credentials are not committed. The live example requires the configured PostgreSQL/pgvector database and an authorized CDN host.

## D. Synthetic network data

`data/fixtures/network_contacts.json` contains 36 fictional profiles across 10+ overlapping sectors. Experiences cover provisional portfolio issuers and competitor/peer organizations. There are no emails, phone numbers, imported profiles, or claimed real identities. Each profile is explicitly `synthetic=true`; the dataset notice says all information is fictional. A small set of direct and contact-to-contact edges has explicit fictional evidence and interaction dates.

The loader rejects datasets outside 30–50 profiles, duplicate profile IDs/names, missing experience fields, invalid dates/tickers, relationships without explicitly fictional evidence, and any unmarked profile. It stores `source_type=synthetic_fixture`, `consent_status=synthetic`, and source labels on experiences. A deterministic synthetic investor anchor supports direct paths. Employer and sector overlaps are expertise context only and never create relationship links. Legacy `synthetic_peer` links are removed by seeding.

```powershell
python scripts\seed_network_data.py --workspace-id <workspace-uuid>
```

The explicit workspace argument prevents accidental global seeding. If that ID does not exist, the command creates a workspace with the supplied/default demo name. Loading twice into one workspace is idempotent.

## Database changes

- Revision `0002_market_retrieval` adds OHLC/adjusted-close and derived EOD columns to `market_daily`, plus announcement source timestamp, retrieval status, raw path, and raw payload.
- Revision `0003_experience_sector` adds sector provenance to `person_experiences`.
- Revision `0005_push_intelligence` adds announcement summaries, numeric materiality scores/reasons, and priority thresholds on alert rules.
- Revision `0007_network_interaction` adds the last explicitly recorded interaction time to `network_relationships`.
- Revision `0006_pull_document_processing` adds document period/file/extraction metadata and content-checksum indexes.
- Existing unique constraints remain the duplicate-prevention keys. Raw source timestamps and `fetched_at` are separate fields.

Apply with `python scripts\init_db.py` after configuring PostgreSQL with pgvector. This environment did not have a PostgreSQL service, so database migrations/upserts were not exercised against a live database here.

## E. Push processing

The announcement CLI persists source records, then classifies, scores, and
creates enabled category/priority alerts through the Push service. It preserves
the filing URL, source key, source timestamps, retrieval status, payload hash,
and synthetic flag. The 17 supported labels and materiality rubric are
documented in `docs/PUSH_INTELLIGENCE.md`.

After market EOD data is ingested, call
`POST /api/v1/push/alerts/evaluate?workspace_id=<uuid>` to evaluate price and
volume rules. Volume requires 20 earlier stored sessions for the same company,
exchange, and source. No alert is generated from an incomplete baseline.
Evaluation is currently an explicit API operation, not a scheduled background
job.

The engine and endpoint contracts are covered by `tests/test_push_intelligence.py`,
`tests/test_push_api.py`, and `tests/test_announcement_pipeline.py`. These use
SQLite/injected inputs and do not establish production PostgreSQL or live
exchange compatibility.

Raw announcement PDFs are stored in the local `data/documents/` directory by default. Hosted deployments need an approved durable object-storage target and retention policy before relying on those files; the current local path is not a production archive.

## Verification and observed source access

Unit tests use injected yfinance data and HTTPX mock transports; tests do not depend on external services. They cover OHLCV validation, deduplication, 20-session calculations, inclusive date behavior/cache reuse, NSE/BSE parsing and fallback labels, bounded PDF storage, issuer-site filtering/document classification, synthetic fixture validation, workspace scoping, and idempotent persistence using SQLite.

An ordinary live yfinance EOD request returned six daily rows for RELIANCE in a ten-calendar-day window during development; this is a point-in-time smoke check, not an availability guarantee. The public NSE request completed but returned no rows for its tested window. The public BSE request was unavailable. The adapter preserves these outcomes; when both live sources yield no records, demo fixtures are explicitly labeled.
