# FINN Engineering Trade-offs

## Current decisions

| Decision | Why it fits this prototype | Cost or limitation accepted |
|---|---|---|
| FastAPI modular monolith | One deployable API with clear Push, Pull, Network, Copilot, and data-pipeline modules; straightforward local testing. | No independent scaling or failure isolation between service domains. |
| Next.js same-origin proxy | Keeps the browser on one origin and keeps `FINN_API_BASE_URL` server-side. | Adds proxy routes and requires correct provider configuration; a missing production URL intentionally returns an error. |
| SQLAlchemy + PostgreSQL | Relational constraints and joins suit users/workspaces, companies, filings, metrics, alerts, contacts, and provenance. | Hosted PostgreSQL migrations, RLS, backup/restore, and production performance were not verified. |
| pgvector in the same PostgreSQL service | Optional semantic retrieval without operating a separate vector database; vectors can be filtered with relational issuer/document metadata. | Requires extension support and embedding configuration. Without them, the implemented fallback is lexical, not semantic. |
| Python rules and deterministic calculations | Explainable classification, score reasons, alert thresholds, financial arithmetic, identity matching, and bounded routing are cheap to test and do not delegate arithmetic to an LLM. | Rules and regex parsing have coverage gaps and can miss ambiguous or unusual language/layouts. |
| Optional OpenAI-compatible provider | Existing adapter supports structured, evidence-bound Pull answers and embeddings without requiring a model for app startup. | Model IDs and costs are not measured; behavior/provider terms vary. No live model call was verified. |
| Issuer/exchange primary-source boundary for Pull | Aligns with the assignment and limits secondary-source leakage. | Documents are harder to discover/parse than normalized third-party research; data coverage can be incomplete. |
| Local PDF filesystem for prototype | Simple hash-based deduplication and easy local demonstration. | Not durable/shared/managed object storage; no production retention lifecycle. |
| In-process retrieval cache | Avoids extra infrastructure and repeated local retrieval work. | Per-process only; not shared across instances and evicted on process restart. |
| In-memory, bounded Network graph traversal | Explicit two-hop paths without another graph service; relationship edges remain distinct from employer/school metadata. | Requires loading graph data and does not provide graph-database scale or advanced analytics. |
| Synthetic network and clearly marked fixtures | Demonstrates relationships without scraping or exposing real personal data. | Cannot establish the quality of real contact data or source permission workflows. |
| Manual ingestion scripts | Makes source fetches inspectable and avoids claiming that a scheduler is operational. | Data becomes stale unless an operator runs refresh commands; no retry queue or worker. |
| Vercel + Render + Supabase as intended deployment | Hosted Next.js, Python API, relational/auth/vector stack matches the code and keeps responsibilities separated. | These are prepared targets only. Deployment, cloud pricing, hosted auth and DB behavior are unverified. |

## Why no LLM-first agent

The assignment rewards judgment and efficiency, not the number of agents.
FINN therefore keeps high-impact operations deterministic:

- Filing label and materiality are rules with explicit reasons.
- EOD thresholds, volume averages, period comparisons, ratios, and guidance
  status use backend calculations.
- Network matching/ranking and relationship traversal remain local and
  evidence-based.
- Copilot intent classification uses a fixed rule router and service calls.
- The optional model is limited to primary-document embeddings and structured
  Pull synthesis after retrieval; output citations are checked by the API.

This avoids sending personal contact data to a model and reduces
hallucination/cost exposure. The trade-off is less flexible language
understanding and more abstentions when the available evidence is weak.

## Why the implementation is deliberately small

FINN has no queue, event bus, microservices fleet, separate cache cluster,
separate vector store, graph database, or custom model. Those would add
operations cost before a live, authenticated, multi-user workload is proven.
The present code uses:

- one FastAPI service and one relational database;
- an optional pgvector extension in that database;
- explicit CLI ingestion rather than unattended jobs;
- short-lived in-memory retrieval caching;
- structured backend functions rather than free-form model tool execution.

This is suitable for a local/hiring prototype, not a claim of production
capacity or availability.

## Deliberately excluded

- Intraday feeds, trading, portfolio optimization, price targets, and
  buy/sell recommendations.
- Scraping that bypasses authentication, CAPTCHAs, platform terms, or rate
  limits; no LinkedIn scraping or real-contact import.
- Broker reports, news, secondary analyst commentary, or model memory as Pull
  evidence.
- Real investor network PII in fixtures or external model payloads.
- Autonomous multi-agent planning, arbitrary tool calling, code execution,
  outbound messaging, or automatic investment actions.
- Production background workers, hosted PDF object storage, RLS, and a
  complete sign-in flow. These are gaps/next steps, not hidden capabilities.

## Cost and performance evidence

The intended infrastructure is Vercel, Render, and Supabase, with a possible
OpenAI-compatible embedding/research provider. No deployed service, paid model
call, or provider invoice exists in the verified project state. Therefore
there is no measured monthly cloud or token cost to report. The API settings
name `gpt-4o-mini` and `text-embedding-3-small` as defaults, but those names
must not be mistaken for models actually invoked during testing.

The QA report contains small-sample local SQLite timings and dependency/test
results. It explicitly does not establish hosted latency, concurrency,
capacity, production PostgreSQL performance, or LLM spend. Re-estimate only
after choosing provider plans, usage quotas, retention terms, and measured
request volumes.

## Next engineering steps

1. Complete secure user login and provisioning; replace manual token entry.
2. Deploy PostgreSQL/pgvector migrations and add/test RLS for every
   workspace-owned table.
3. Deploy staging services; run seeded authenticated Push, Pull, Network, and
   Copilot workflows in a browser against that deployment.
4. Validate live market, exchange, and issuer sources for permissions,
   freshness, issuer identity, parsing accuracy, and failure behavior.
5. Add approved object storage, retention/deletion controls, scheduled
   idempotent ingestion, bounded retries, and operational monitoring.
6. Evaluate extraction/retrieval on a manually verified primary-source set;
   measure citation accuracy, abstention quality, latency, and model cost
   before expanding LLM usage.
7. Resolve/accept the development dependency advisories and run
   security/load/backup-restore tests before production use.
