# FINN Data Provenance

## Purpose

FINN records should tell the user what data was used, where it came from, when
it was retrieved, whether it is synthetic, and what transformations were
applied. This document describes current provenance fields and behavior. It
does not certify any live upstream dataset; the final QA report did not use
live issuer, exchange, or model-provider data.

## Source classes

| Source class | Producer | Typical provenance retained | Status and caveat |
|---|---|---|---|
| Market bars | yfinance market adapter, called by `scripts/ingest_market_data.py`. | Ticker/company alias, source, session date, fetch time, OHLCV, source-sync status. | EOD only; manual refresh. No live/intraday or live data accuracy validation in the final QA run. |
| Exchange announcements | Public NSE/BSE endpoints, called by `scripts/ingest_announcements.py`. | Exchange/source key, company/ticker mapping, filing timestamp, original URL, raw payload hash, fetch time, retrieval status. | Endpoint shape/availability can change; unmapped or invalid records are not silently presented as company filings. |
| Exchange attachment PDFs | Optional NSE/BSE attachment downloader. | Original URL, HTTPS host, content hash, PDF validation outcome, local storage path. | Limited to approved exchange hosts, PDF signature and file-size checks. Retention/license review is still required. |
| Company primary documents | Bounded discovery from issuer sites and explicitly configured authorized hosts. | Issuer, document type, title, source/discovery URL, source host, period, fetch time, content type/size/hash, ingestion status. | Four allowed types: annual report, quarterly result, earnings-call transcript, investor presentation. External documents were not live-validated in QA. |
| Extracted PDF passages | pdfplumber, optional OCR, and page-bounded chunking. | Document ID, one-based page number, section, source URL via document, chunk hash, text and optional embedding model. | Extraction may be incomplete on complex/scanned reports; failed validation is explicit. |
| Financial metric and guidance records | Deterministic extraction/parsing and research services over stored documents/metrics. | Company, period, reporting basis, value, currency/unit, synthetic flag, source document/chunk/page and quotation where available. | Calculated values remain distinguishable from reported values; missing values are not filled. |
| Network profiles | `data/fixtures/network_contacts.json` and network seed loader. | Workspace/person IDs, employment/education records, explicit synthetic flag and relationship evidence. | Fictional demonstration identities only; no real contact-profile source is used. |
| Demo seed and fixtures | Checked-in JSON and text under `data/`. | `is_synthetic`/demo source markers, source labels, seeded period/source metadata. | Artificial values and narratives are UI/test fixtures, not a representation of company disclosures or actual market outcomes. |

## Synthetic versus real data

- The 18-company starter portfolio is a **provisional demo universe**, not the
  official ENAM portfolio. Names and symbols identify public issuers; seed
  prices, announcements, financial values, report text, and derived results
  must not be described as reported by those issuers.
- The contact set contains 36 synthetic fictional profiles. Names and
  professional histories are not asserted to represent actual people.
- The document fixture files explicitly state that their text and sample
  financial statements are fabricated. They are for database/UI/testing only
  and are excluded from normal primary-source retrieval.
- Real external source data can enter only when the corresponding adapter or
  document pipeline is executed successfully and passes validation. A real
  source URL is not sufficient proof that its content is current, complete, or
  accurately extracted.
- The final QA report records that live yfinance, NSE/BSE, live issuer PDFs,
  embeddings, and paid model calls were not exercised. Therefore no claim is
  made that the demo dataset contains a verified real-time or current
  company-reported feed.

## Normalization, matching, and lineage

### Company identity

Market/announcement records resolve through canonical companies and exchange
aliases. NSE ticker normalization removes expected suffix/case variations.
Announcement adapters retain the source exchange and map symbol/scrip
identities rather than creating a company silently for every unrecognized
filing. Pull discovery resolves a ticker to an issuer and candidate
investor-relations site; downloaded content is then checked for issuer
identity, document class, PDF integrity, and reporting period when requested.

### Person and organization identity

Network name matching normalizes punctuation/case and checks exact names
first. Fuzzy person matching requires multi-token candidates, a high
similarity threshold, and token overlap; the result is a candidate with a
confidence/method, not a confirmed identity. Company matching normalizes
company suffixes and records evidence. Network career and education overlaps
are useful expertise context but never imply a personal relationship.

An incoming executive-to-contact match is a possible name match with evidence
and confidence. Personal relationship paths are sourced from explicit stored
edges; shared employer, education, sector, or name alone cannot create a path.

### Document and calculation lineage

Downloaded PDFs are hashed and stored by company/hash locally. Duplicate
content can reuse chunks and embeddings; changed content can be represented as
a new document version. Each chunk preserves the document ID, page, section,
text hash, and retrieval metadata. Citation URLs and pages are populated from
the stored document/chunk, never accepted as arbitrary model output.

Financial facts preserve value, unit/currency, reporting period, and reporting
basis. Calculations identify their inputs and are computed in Python. If
periods, units, basis, or evidence are not compatible, the result should be
unavailable rather than fabricated.

## Refresh and source status

- EOD market bars are refreshed by a manual script; the configured market
  cache freshness is six hours by default. Source sync rows record last
  attempt/status. No scheduled refresh worker is present.
- Exchange filings are fetched when the announcement ingestion script runs.
  The source key/hash supports idempotent retry behavior; source retrieval
  errors and empty responses are distinct statuses.
- Issuer document discovery and ingestion are explicit pipeline operations.
  There is no scheduled crawler or hosted object-store lifecycle.
- Retrieval has a bounded process-local TTL cache keyed by query, scope,
  filters, model and current document manifest; ingestion invalidates it.
  It is not a shared cache across API instances.
- Synthetic data is loaded through repeatable demo seed commands and must
  remain marked synthetic through API responses and reports.

## Provenance requirements for future sources

Before adding another data source, record its permitted access method and
terms, source URL/identifier, fetch and effective timestamps, entity mapping
evidence, content hash/version, transformation code version, confidence,
synthetic status, and error/refresh state. Keep raw source payloads only as
long as policy permits. Do not log secrets, bearer tokens, private profile
payloads, or model prompts.
