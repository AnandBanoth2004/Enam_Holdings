# FINN User Flows

## Product-wide flow model

FINN has six navigable areas, but three shared intelligence layers:

- **Push** notices an event or unusual EOD movement.
- **Pull** investigates a company using primary-source evidence.
- **Network** identifies a relevant person and explains the relationship.

Command Centre is the daily entry point, not a fourth intelligence layer. Company Research is the primary Pull experience. Copilot is a contextual question interface over the same company, event, evidence, and Network context—not a separate chatbot product. Settings configures the portfolio, alerts, and privacy.

Every event/research path should preserve context as the user moves between layers:

`Command Centre -> Push item -> Company Research -> Network match -> cited source -> back to originating item`

The ticker and relevant event stay visible across transitions. Returning from a person/source detail restores the prior filters, scroll position, and selection.

## 1. Command Centre: start the day

**Goal:** See the few portfolio changes worth attention and decide what to inspect next.

1. Investor opens **Today**. The header shows portfolio name, number of companies, current market-data freshness, and the digest window.
2. A compact market summary reports the latest available EOD date and portfolio move context. It never implies intraday data.
3. Priority alerts and material announcements appear before routine filings.
4. Investor opens a results card; headline Revenue, EBITDA, PBT, and PAT show the reported quarter and available QoQ/YoY comparisons with unit, reporting basis, and source.
5. A contextual Network opportunity explains who may help and the concrete evidence (e.g. former employer, school, or verified intermediary).
6. Investor chooses:
   - **Open filing** to inspect primary evidence.
   - **Research company** to continue into Pull with ticker and event context.
   - **View connection** to inspect the person and relationship path.
7. Investor returns to Today; the same digest/filter state remains.

**Success signal:** user can identify an important item, understand why it matters, and reach evidence or a relevant person without re-entering the company.

## 2. Push Intelligence: triage the portfolio

1. Investor enters **Push** from the bottom navigation/rail or the Command Centre digest action.
2. The digest defaults to the last 24 hours. Presets and custom range update the displayed window explicitly.
3. Investor selects categories or priority filters. The result count and selected filters remain visible.
4. High-materiality items show a clear reason and source; routine/`unclassified` items are grouped with a count and can be expanded.
5. An EOD price/volume alert states the observed close/move/volume, baseline/lookback, configured threshold, market date, and freshness.
6. On a results filing, investor expands the financial comparison. QoQ means the previous quarter; YoY means the same quarter a year earlier. Missing or incompatible periods are labeled unavailable.
7. On a management-change/material event, the item offers an evidenced person/network match where one exists.
8. Investor drills to Research, Network, or filing source; browser back returns to the same digest.

**No-result path:** identify the selected window, last successful source poll, and provide an easy way to widen the window. Never present “no activity” if source data is stale without disclosing that state.

## 3. Company Research: investigate a ticker (Pull)

1. Investor opens **Research** and enters an NSE ticker, company name, or supported exchange symbol.
2. FINN resolves the symbol. If ambiguous, it asks the investor to choose a verified issuer. The seed list is not an allowlist.
3. The source availability panel reports annual reports, quarterly result filings, and concall transcripts found, with document periods and primary-source links.
4. Investor selects a concise view (default) or a research section: business snapshot, financial snapshot, trajectory, balance sheet, cash quality, narrative-vs-numbers, guidance, or bull/bear.
5. The research view leads with source-supported facts and reported metrics. Each claim opens a citation drawer with document, period, page, excerpt, and source link.
6. Deterministic calculations show compatible-basis QoQ/YoY comparisons. Missing periods, zero/negative comparison bases, and unavailable metrics receive explicit handling.
7. Narrative-vs-numbers compares management's explicit statements with observed results, ideally across the last four quarters. Quotes/claims and actuals remain separately cited; inference is labeled.
8. A Network panel suggests a relevant contact based on evidence in the investor's own network; opening it leads to profile/connection details without sending private contact data to an LLM.
9. Investor can ask a follow-up in Copilot; the question inherits the current issuer and allowed evidence context.

**Unsupported source path:** show which documents were unavailable and what research cannot be supported. Do not substitute outside knowledge, a news story, or a seeded company's report.

## 4. Network Intelligence: find context in relationships

1. Investor opens **Network** directly or follows a contextual match from Push/Research.
2. Search accepts a company, person, sector/topic, or explicit expertise query. Results are scoped to the current investor workspace.
3. A match card explains relevance using concrete evidence: company/employer experience, customer/supplier/competitor link, education overlap, or a verified second-degree path.
4. First- and second-degree status and known relationship strength are stated separately. A shared school/company is not presented as proof of closeness or expertise.
5. Investor opens a contact profile to inspect career/education timeline, provenance/synthetic label, and why the person matched.
6. The relationship graph is optional and secondary to the evidence list. If shown at wider sizes, selecting a node opens the same accessible profile card; at mobile, show a simple path such as `You -> Contact A -> Executive`.
7. A no-match result states “No known connection in this network,” not “no connection exists.”
8. From a profile, investor can return to the triggering company/event or mark a relationship as corrected/unknown.

**P0 demonstration:** one direct company-employment match and one management-person or second-degree example using clearly labeled synthetic data. Full expertise mapping and warm-reconnect recommendations are staged enhancements.

## 5. AI Research Copilot: ask in context

1. Investor selects **Ask** from global navigation or opens “Ask about this” from a company, announcement, metric, or contact card.
2. Copilot displays its scope before the question is sent: selected company/event and the primary documents it can use.
3. Investor asks a natural-language question, such as “What did management say about margins and what happened next quarter?” or “Why is this filing material?”
4. FINN retrieves only eligible primary-source passages for Pull questions; event explanation may use the underlying exchange filing. Network questions use the investor's private records through deterministic matching.
5. The answer is concise, separated into reported facts/calculations/interpretation, and includes citations beside claims.
6. The investor can open a cited source, refine the question, or jump into the relevant Research/Push screen.
7. If evidence is insufficient, FINN says so and identifies the missing source/period. It does not answer from model memory.

Copilot is a utility panel, not the home screen. Do not display a blank chat transcript as the main product experience.

## 6. Settings: configure the signal and trust boundary

1. Investor opens **Settings** from the account control.
2. **Portfolio:** add/remove supported companies and see the company count. Search resolves arbitrary listed symbols; validation prevents ambiguous instruments from being silently added.
3. **Alerts:** choose relevant announcement categories, price-move threshold, volume multiplier, and lookback window. Show that checks occur after EOD refresh.
4. **Data refresh:** show source-specific last success, current/stale state, and a manual refresh action only where allowed.
5. **Privacy:** show whether network profiles are synthetic or user-provided, what profile fields are stored, consent/source status, retention/deletion controls, and a delete-network action.
6. Investor saves changes and sees confirmation; invalid thresholds remain editable with inline explanation.

## Cross-layer transition rules

- Push -> Pull passes issuer, announcement, period, and selected question context.
- Push -> Network passes issuer/person/event context, but no unsupported identity assertion.
- Pull -> Network passes the issuer/topic and displays match evidence next to the research section.
- Network -> Pull/Push returns to related company/event when provenance exists.
- Copilot inherits only the current screen context and its permitted source scope; user can see and clear the context.
- Settings never silently alters current page filters or a completed research result.

## State and recovery flows

- **Loading:** preserve shell and request context, show actual progress only when known, and keep source freshness visible.
- **Partial source failure:** render successful sources and identify failed/unavailable sources; never turn partial data into a complete-sounding answer.
- **Expired authentication:** preserve the user's non-sensitive draft/filter state through re-auth, then re-check workspace authorization.
- **Ambiguous ticker/person:** stop before showing company-specific research or a network claim; ask for disambiguation.
- **No evidence:** explain the gap and offer a relevant next action (widen time window, check ticker, open available sources), not a hallucinated fallback.

## Priority mapping

- **P0:** Today/Command Centre, Push digest and EOD alert, one results comparison, ticker-based primary-source Research, contextual Network contact match, source drawer, Settings for portfolio/thresholds/privacy.
- **P1:** stronger four-quarter guidance tracker, management-change bio and second-degree path, broader category summaries and graph view.
- **P2:** full voice experience, comprehensive expertise map, warm-reconnection engine, production network imports, broad long-tail coverage.

This prioritization follows the challenge's “thin-but-working” guidance; the screen names in the proposed structure do not imply that every listed research module must be fully implemented in the prototype.
