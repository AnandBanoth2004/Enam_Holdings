# FINN AI and Agent Design

## Design boundary

FINN is a deterministic application workflow with optional LLM support. It is
not an autonomous agent that can browse freely, execute code, trade, message
contacts, or invent data. This document describes the code paths in the
repository, not only the earlier proposed strategy.

## Model routes actually implemented

| Capability | Implemented route | Model or deterministic method | Current verification |
|---|---|---|---|
| Copilot intent detection | `classify_query` maps recognized phrases to fixed intents/layers. | Python keyword and regular-expression rules; no LLM router. | Automated classification/routing tests; real model routing is not involved. |
| Tool/service selection | Fixed dispatch to Push digest/alerts, Pull financial research/RAG, or Network search/recommendation services. | Deterministic Python calls and typed service results. | Backend tests include single- and multi-service intents. |
| Announcement labels | Ordered patterns classify the 17 reference labels. | Deterministic rules; ambiguous items become `unclassified`. | Automated label/classification tests. |
| Materiality and alerts | Category/amount/adverse-signal/portfolio points; configured EOD rules. | Deterministic Python calculations and fixed score bands. | Rule and threshold tests; no LLM score. |
| Market and financial calculations | Prices, volume baseline, financial period comparisons, margins, cash/leverage metrics, and guidance assessment. | Deterministic Python/Decimal logic over stored values. | Independent expected-value unit tests; real issuer extraction remains unverified. |
| Network entity matching and ranking | Normalized exact matching, high-threshold fuzzy candidate matching, relationship path and evidence ranking. | Deterministic Python and SQL; no model. | Matching, traversal, ranking, and authorization tests. |
| Document embeddings | Optional provider adapter using configured embedding model. | Default identifier: `text-embedding-3-small`, 1,536 dimensions. | Shape/validation code and tests exist; no provider key or live embedding call was used in final QA. |
| Pull answer synthesis | Optional structured answer from retrieved primary-source excerpts. | OpenAI-compatible chat-completions adapter; default identifier: `gpt-4o-mini`. | Citation/schema guards are tested. No paid/live model call was made in final QA. |
| Pull without a model key | Extractive evidence response from retrieved chunks. | Deterministic keyword-ranked verbatim quotes, marked `evidence_only`. | Testable without external model access. |
| Copilot final narration | Service result blocks and cross-layer templates. | Deterministic templates; model is not used to invent or narrate tool results. | Service status and citation preservation are tested. |

The model identifiers are defaults in settings, not a guarantee that those
models were called. The provider is only instantiated when a research API key
is configured. No model provider, embedding API key, model cost, or model
latency was verified in the reviewed environment.

## Copilot query lifecycle

1. The authenticated request is checked for user and workspace access.
2. The deterministic classifier normalizes the query and extracts a known
   ticker/executive/expertise term where possible.
3. The classifier returns a fixed intent, one or more allowed layers, and
   whether company clarification is required.
4. The service calls existing backend functions. For example, a cross-company
   context request can gather Push announcements, Pull research, and Network
   recommendations. No arbitrary model-selected tool name is executed.
5. Each result becomes a typed block with status, source/citation information,
   synthetic marker, and limitations. Missing data/errors remain visible;
   the system does not report a successful action without service output.
6. The response and messages are stored under user and workspace ownership.
   Conversation list/read/delete paths apply both ownership dimensions.

Intent detection is rule-based and may fail on ambiguous wording. Cross-layer
answer text is currently composed with deterministic templates; the
integration report explicitly distinguishes this from LLM reasoning.

## Pull generation and evidence controls

- Retrieval must be scoped to the issuer, supported primary document type,
  optional reporting period, and eligible source status before ranking.
- The four allowed Pull types are annual reports, quarterly results,
  earnings-call transcripts, and investor presentations.
- The optional model receives the user question and retrieved evidence
  excerpts; it is instructed to produce structured claims with quote-level
  evidence references.
- Pydantic validates the structured result. The backend rejects unknown chunk
  IDs and quotes that do not occur in the retrieved chunk, then builds
  citations from its own database metadata (document, period, page, URL).
- The model does not choose citation URLs or page numbers. Missing evidence
  returns `insufficient_evidence`; no-model responses are marked
  `evidence_only`.
- Financial arithmetic and period comparisons are calculated independently
  by Python. The model cannot override those values.

The code-level evidence checks reduce unsupported citations, but they do not
prove that a model's prose interpretation is correct. Human review and live
issuer validation remain necessary.

## Network privacy boundary

Network profile data, employer/education histories, direct relationship edges,
and contact recommendations stay in SQL/application logic. They are not placed
in the model evidence payload. A cross-layer response can combine a
non-identifying research context with a locally generated Network result.

Employer or school overlap can explain a contact's relevant experience; it
does not create a friendship or introduction edge. Second-degree paths only
use explicitly recorded relationship edges and are limited to two hops.
Fuzzy person matching proposes candidates and evidence; it does not assert
identity without validation.

## Failure behavior and quality limits

- Missing API key: use the extractive evidence path; do not imply a generated
  analysis or semantic embedding exists.
- Provider error, invalid schema, unknown evidence ID, or unsupported quote:
  return an explicit error/partial status rather than silently accepting
  ungrounded output.
- No eligible source evidence: return an insufficient-evidence result.
- Unknown Copilot intent or missing company identity: ask for clarification or
  return an unsupported result; do not invoke unrelated tools.
- External-source error: preserve the service failure/status and source
  metadata; a demo fallback remains labeled synthetic.

Unit tests exercise deterministic services and mocked model responses. They do
not establish live model factuality, provider safety/retention, current model
pricing, or response quality across a production query distribution.

## Future agent work (not implemented)

Do not add autonomous planning until there is an evaluation set and safe
rollback/approval boundary. A useful next step is improved deterministic
intent/entity resolution with explicit ambiguity handling, followed by
measured evaluation of a model-based router against the current rules. Any
future model route should retain bounded service schemas, user approval for
external actions, evidence checks, privacy filtering, and per-call budget
limits.
