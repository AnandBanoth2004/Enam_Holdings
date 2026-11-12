# FINN AI and Model Strategy

## Operating principles

1. **Primary-source-only Pull:** company analysis retrieves only company/exchange filings, annual reports, quarterly results, investor presentations, and concall transcripts. No news, broker notes, research reports, or model memory as evidence.
2. **Deterministic facts first:** arithmetic, period matching, EOD thresholds, source eligibility, and network matching are ordinary Python logic, not LLM decisions.
3. **Evidence-bound synthesis:** every factual claim must cite retrieved source spans; unsupported output is withheld or labeled unavailable.
4. **No autonomous agent:** fixed server workflows call bounded tools. The model cannot browse, execute arbitrary code, trade, message contacts, or choose unapproved sources.
5. **Minimize personal data:** network recommendation/ranking is deterministic and stays inside the application boundary. Do not send contact names, edges, private notes, or relationship paths to external model providers.

## Model routing

Model provider and exact version are configuration, not hard-coded assumptions. Before implementation, select a provider/model with structured JSON output, a low-cost tier, acceptable latency, and data-processing terms suitable for the intended data. Pin the model identifier and schema/prompt version for each run.

| Task | Default route | LLM? | Controls |
|---|---|---|---|
| Ticker normalization and issuer resolution | Exchange/security aliases + deterministic source adapter | No | Require a valid symbol/issuer match; report ambiguity. |
| PDF text extraction and page association | Python PDF parser; OCR only if required | No | Keep page boundaries, hashes, extraction status; no model-generated values. |
| Financial metric extraction from diverse result tables | First use deterministic label/table parsing; use a low-cost JSON-capable model only for a bounded table/text excerpt when parsing fails | Optional | Request metric/value/period/unit/basis/page/excerpt/confidence; validate schema, numeric formats and provenance; do not accept a value without matching excerpt. |
| Financial arithmetic and QoQ/YoY | Python `Decimal` calculation service | No | Require same basis/currency/unit and correct periods; handle zero/negative bases explicitly. |
| Announcement category and priority | Rules for known labels, optionally a low-cost structured classifier for ambiguous descriptions | Optional | Fixed 17-label enum; confidence threshold; ambiguous result is `unclassified`; original filing always retained. |
| EOD threshold alerts | Python calculation service | No | Configured lookback/threshold, market date, freshness and adjustment policy. |
| RAG embeddings | One low-cost embedding model, versioned | Yes | Embed public primary-source chunks only; preserve model/version; re-embed when changing model. |
| Pull narrative summary / narrative-vs-numbers | Small structured-output LLM with retrieved primary evidence | Yes | Low-cost model first; schema validation and citation checks; abstain if evidence is inadequate. A stronger reasoning model is a manual fallback only for high-value, difficult runs, not an automatic multi-agent loop. |
| Network recommendations | SQL joins/rules over private profiles, company/entity aliases, and explicit graph edges | No | Evidence-backed rationale, relationship hop count, and confidence; no sensitive inferred traits. |
| UI rendering and saved results | Typed API response | No | Never execute model-generated markup or code. |

**Selection recommendation:** benchmark one economical JSON-capable model for extraction/synthesis and one economical embedding model during implementation. Do not bind the architecture to a model brand before verifying current November 2026 pricing, structured-output behavior, latency, retention settings, and regional availability. Provider changes require regression tests against a fixed set of verified source fixtures.

## RAG pipeline and grounding

1. Accept a normalized ticker; resolve it against exchange symbols/aliases and supported source discovery.
2. Discover only allowed primary documents. Persist issuer, type, period, source URL, publication date, reporting basis where applicable, checksum, and fetch status.
3. Extract text with page boundaries. Detect scanned/empty files and mark them unsupported until an approved OCR path exists.
4. Split into bounded chunks (e.g. 500–800 tokens with modest overlap), keeping page/section metadata. Avoid splitting numeric tables away from their headers/period labels.
5. Embed chunks with the configured embedding model and store vectors in pgvector with the model/version.
6. For a research request, construct a scoped query using issuer ID, allowed document types, requested periods, and reporting basis. Retrieve a small top-k set (initially 6–10) using vector similarity plus keyword/metadata filters.
7. Build an evidence bundle with source IDs, title, document period, page, and exact text spans. Exclude all secondary content.
8. Call the LLM with a strict JSON schema. The prompt requires it to use only supplied excerpts, distinguish reported fact/calculation/interpretation, cite every factual claim, and return `insufficient_evidence` where needed.
9. Validate JSON using Pydantic, verify cited chunk IDs belong to the bundle, reject missing/invalid citations, and independently compute any numeric comparisons.
10. Store the result, source manifest, model, prompt/schema version, and status. Render citations adjacent to claims.

Do not treat vector similarity as proof or as source validation. The issuer, document type, period, and source eligibility filters are mandatory before ranking chunks.

## Structured output contract

At minimum, each generated section contains:

```json
{
  "section": "narrative_vs_numbers",
  "status": "complete",
  "claims": [
    {
      "claim_type": "interpretation",
      "text": "Management described demand as improving; reported revenue increased in the cited period.",
      "citation_ids": ["chunk-uuid"],
      "confidence": 0.78
    }
  ],
  "limitations": []
}
```

Allowed `claim_type` values are `reported_fact`, `calculation`, and `interpretation`. Numeric facts and calculated values are populated/validated by backend functions where possible, not accepted from unconstrained prose. Citation validation is a hard gate, not a prompt suggestion.

## Prompt/data privacy boundary

- Public company filing excerpts may be sent to a configured model provider only after reviewing its retention and training policy.
- Do not send real investor network profiles, personal names, contact edges, or investor notes to external models.
- For contextual Network output, the API can combine a Pull/event summary with a locally generated, non-identifying need such as `sector expertise in specialty chemicals`; return the actual contact match locally after synthesis.
- If an LLM call cannot be made within privacy constraints, render extracted facts and citations without generated interpretation.
- Do not persist provider prompts containing private data. Log request IDs, model route, latency, token counts, and error codes; redact text.

## Failure behavior and quality gates

- Extraction/model unavailable: show source documents and supported deterministic data; label unavailable enrichment.
- Missing quarter or incompatible basis: no comparison; explain the absent/mismatched period.
- Invalid schema, unsupported citation, or low confidence: reject generated section and return a clear partial result.
- Classification ambiguity: keep filing visible as `unclassified`; never discard it.
- Entity ambiguity: do not assert a person-network match.
- Required offline/fixture tests: known metric extraction, negative/zero base, missing period, source-basis mismatch, unsupported question, incorrect citation ID, secondary-source injection, and a ticker outside the demo seed set.

## Cost controls

- Cache extraction, embeddings, and validated synthesis by content hash + model + prompt/schema version.
- Use deterministic parsers before LLM calls; send only relevant pages/tables, not whole reports.
- Batch embeddings where provider limits allow.
- Route to a more capable model only on explicit fallback; never run unbounded agent loops.
- Set per-user request and token limits; record usage for a cost report.

## Copilot implementation boundary

The initial Copilot uses a deterministic, bounded intent router and direct
calls to existing Push, Pull, and Network services. It is not an autonomous
agent and does not ask an LLM to choose or execute tools. Financial reports,
market observations, alert retrieval, and relationship paths are service
results; response blocks preserve their source metadata and synthetic flags.
Primary-source RAG may use the configured research model only on eligible
retrieved document chunks, and its quote/chunk citation checks remain
authoritative. Without a configured provider, the RAG layer returns validated
extractive evidence or an explicit insufficient-evidence status. Cross-layer
summaries are currently deterministic templates rather than LLM-written
narrative. This deliberately trades conversational flexibility for predictable
routing, evidence traceability, and Network privacy.

## Model cost estimate

For a modest demo assumption—roughly 10–30 research runs/month, 20–100 relevant chunks embedded per issuer and cached, and 5k–20k input tokens plus 0.5k–2k output tokens per uncached synthesis—expect **approximately $0–$10/month** for economical hosted-model usage, often less with free credits/tiers and cached outputs. This is an order-of-magnitude planning estimate, not a quote: actual model rates, free-tier rules, chunk volume, retries, and embedding dimensions may change. Re-estimate using the chosen vendor's current rate card and measured token usage before deployment.
