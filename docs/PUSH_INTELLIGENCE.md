# FINN Push Intelligence

## Status and scope

Push now has a deterministic announcement classification/materiality engine, a
portfolio digest, financial-results comparisons, configurable alert rules, and
REST endpoints. It is an application prototype: these routes currently accept
`workspace_id` directly and do not enforce authenticated workspace membership.
Do not expose them to the public internet or use real private workspace data
until authentication and authorization middleware are implemented.

The engine never describes cached EOD data as live or intraday data. Exchange
filing category, source URL, filing timestamp, retrieval metadata, and the
synthetic/demo flag remain available to clients.

## Announcement categories

The taxonomy matches the 17 labels in the assignment reference:

`results`, `M&A`, `fund_raise`, `management_change`, `litigation`,
`insider_trading`, `earnings_call`, `investor_meetings`, `credit_rating`,
`dividend`, `bonus_split`, `capex`, `press_release`, `postal_ballot`,
`agm_egm`, `pledging`, and `unclassified`.

Classification uses ordered, versioned phrase/regular-expression rules, not an
LLM. More specific categories (for example pledging and management changes)
are checked before broader labels. No match returns `unclassified` with lower
confidence. The response includes matched terms and a concise summary; it does
not claim a full PDF extraction. Exchange-source labels remain provenance and
are not overwritten by the classifier. The confidence field is a heuristic:
0.82 for one matched phrase, +0.06 per additional match, capped at 0.99; an
unclassified result is 0.55. It is not a calibrated probability or OCR/PDF
extraction confidence.

## Materiality rubric (`deterministic_rules_v1`)

Every score is clamped to 0–100 and carries reasons for its category base,
amount band (or missing amount), applicable modifiers, portfolio relevance,
and priority band.

| Category | Base points |
|---|---:|
| results | 24 |
| M&A | 30 |
| fund_raise | 18 |
| management_change | 28 |
| litigation | 26 |
| insider_trading | 20 |
| earnings_call | 10 |
| investor_meetings | 6 |
| credit_rating | 22 |
| dividend | 14 |
| bonus_split | 12 |
| capex | 20 |
| press_release | 9 |
| postal_ballot | 7 |
| agm_egm | 7 |
| pledging | 24 |
| unclassified | 0 |

An explicitly stated amount with a recognized unit is normalized to crore-units
for an amount-size band: `<1` adds 0; `1–<10` adds 10; `10–<100` adds 20;
`100–<1,000` adds 30; and `>=1,000` adds 40. The engine does not infer a missing
amount or currency. Explicit foreign-currency amounts are excluded from this
band rather than treated as INR. Recognized INR markers are retained in the
explanation; without an explicit INR marker the reason says `crore-units`.

Additional deterministic signals:

- Credit-rating downgrade, negative outlook, or rating watch: +12.
- Adverse litigation, penalty, restructuring, or insolvency signal: +8.
- Increased, newly created, or invoked pledge: +8.
- Issuer in the workspace's default portfolio: +15.
- Scores are capped at 100.

| Priority | Score |
|---|---:|
| Critical | 80–100 |
| High | 60–79 |
| Medium | 35–59 |
| Low | 0–34 |

These are transparent prototype heuristics, not investment advice or a
statistically calibrated estimate of price impact. The explanation is returned
with the score so users can inspect each contributing rule.

## Digest, results, and alerts

- Digest supports the rolling `24h` default, `48h`, `7d`, and timezone-aware
  custom start/end timestamps. Filters include NSE ticker, category, and
  priority; results are portfolio-scoped and ordered by score then filing time.
- Results fields follow the reference terminology: Revenue, EBITDA, PBT, PAT,
  QoQ, and YoY. Comparisons require exact quarter ends three or twelve months
  earlier, the same reporting basis, and compatible currency. Values are
  normalized across supported scales before differences are calculated.
- Percentage change is withheld if the comparison value is zero or negative;
  absolute movement remains available. Missing metrics/periods remain missing,
  with an explanatory note; a nonadjacent quarter is not substituted.
- Announcement rules can trigger by selected category or minimum materiality
  score. EOD market rules can trigger on absolute daily close movement and
  volume multiple. Volume uses exactly the prior 20 matching exchange/source
  sessions; with fewer than 20 sessions the baseline and volume alert are
  withheld. Alert deduplication is by workspace and stable rule/event key.
- Market evaluation can be run after EOD ingestion with `POST
  /api/v1/push/alerts/evaluate`. The response identifies `end_of_day` semantics.

## API routes

All routes are under `/api/v1/push`:

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/digest` | Windowed portfolio digest; `window`, `start`, `end`, repeated `ticker`, `category`, and `priority` query filters. |
| `GET` | `/announcements/{announcement_id}` | Announcement details, source metadata, materiality, and bounded network context. |
| `POST` | `/classify` | Classify/score supplied headline/body, or reclassify a persisted announcement by ID. |
| `GET` | `/announcements/{announcement_id}/materiality` | Stored score and reasons. |
| `GET` | `/alerts/config` | Read workspace-level or ticker-level active rule configuration. |
| `PUT` | `/alerts/config` | Replace rule configuration; validates categories and numeric ranges. |
| `GET` | `/alerts/history` | Persisted alert history; optional ticker/type filters and bounded limit. |
| `PATCH` | `/alerts/{alert_id}/status` | Persist `read` or `unread` state within the supplied workspace. |
| `POST` | `/alerts/evaluate` | Evaluate latest eligible EOD market bars for a workspace/ticker/date. |
| `GET` | `/results/{ticker}/comparisons` | Latest financial metric comparisons; optional standalone/consolidated basis. |

Classification returns category, confidence, matched terms, summary, score,
priority, reasons, and the rule version. Alerts include the triggering rule,
materiality explanation or EOD measurements, source, timestamp, and synthetic
flag. Results comparison values include period, currency, unit scale, basis,
source URL, absolute change, percentage change where valid, and a missing/edge
case note. Period values also expose `is_synthetic`, derived from the source
period/metric.

## End-to-end demonstration

The ingestion path persists a source filing and provenance, maps its ticker to
a company, classifies it, computes the materiality score/reasons, and evaluates
enabled portfolio category/priority rules. In the test fixture, an explicitly
synthetic NSE-shaped record titled “Board approves acquisition of a subsidiary”
for a monitored company matches `M&A`. The category base is 30 and portfolio
relevance adds 15, producing 45/100 (`Medium`) when no amount or adverse
modifier is disclosed; the configured M&A category rule creates one persisted,
deduplicated alert linked to the filing. Separately, classifying the same type
of announcement with an explicit INR 250 crore value adds 30 size points for
75/100 (`High`). The ingestion test verifies that repeating the same source
record does not create a duplicate alert.
