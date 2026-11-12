# FINN Product Specification

## Product proposition

**FINN turns a market day's noise into a short, evidence-backed action brief—and shows who in the investor's own network can help interpret it.**

The smallest compelling product is a phone-first responsive web app with three connected surfaces:

1. **Today (Push):** a 24-hour portfolio digest, prioritized event cards, and one configurable EOD alert.
2. **Research (Pull):** an on-demand, source-cited primary-document company brief, usable for a non-demo NSE ticker when data exists.
3. **People (Network layer):** contact matches embedded in event and research cards, with a small direct “Who can help?” query. This is not a separate contact directory.

Use a 15–20-company synthetic/demo portfolio and synthetic network profiles with intentional overlap. Include around 3–5 additional research examples, but allow a ticker not in the seeded list to resolve dynamically when source data is available. Label any seeded/cached/mock records honestly.

## Core workflows

### 1. Morning signal: results plus context

1. Investor opens Today; the 24-hour digest is preselected.
2. Material announcements appear first; routine paperwork is collapsed but reachable.
3. A results card shows Revenue, EBITDA, PBT, and PAT for the reported quarter, with QoQ and YoY comparisons where matching data exists.
4. Each number shows period, unit, reporting basis, and link to the actual results filing.
5. The card reveals a relevant network contact and why their experience is useful, with a clear relationship/evidence path.

This demonstrates filtering, primary-source extraction, correct financial comparisons, and Network integration in one compact workflow.

### 2. A named executive: management-change diligence

1. A management-change alert shows the filing and incoming executive.
2. The profile summary describes role, prior employers, education, and tenure only from permitted or clearly labeled synthetic/public information.
3. FINN shows direct work/study overlap or a second-degree path if it has evidence; otherwise it says no known match.
4. The investor can open the filing/profile source or initiate a follow-up research action.

### 3. Ad-hoc company research: narrative versus delivery

1. Investor enters an NSE ticker that may not be in the sample portfolio.
2. FINN discovers available annual reports, quarterly results, and concall transcripts from primary sources.
3. A concise brief presents a business/financial snapshot and one carefully scoped narrative-vs-numbers comparison.
4. It compares available quarters with explicit management guidance/commentary, ideally the last four quarters, and cites each claim.
5. Missing periods or unsupported claims are marked unavailable rather than filled from model memory.
6. The Network panel names a contact with relevant company/sector/competitor/customer/supplier experience and explains the match.

### 4. Threshold alert (small, reliable slice)

Investor configures a daily price move and/or volume-multiple threshold. After the EOD refresh, the app evaluates the chosen threshold against a disclosed recent-average window. It shows the source date, baseline, observed value, and why the alert fired. Do not imply intraday or real-time monitoring.

## Announcement taxonomy

Use the reference's 17 labels as the initial scheme, while recognizing that the challenge permits adapting or ignoring it:

`results`, `M&A`, `fund_raise`, `management_change`, `litigation`, `insider_trading`, `earnings_call`, `investor_meetings`, `credit_rating`, `dividend`, `bonus_split`, `capex`, `press_release`, `postal_ballot`, `agm_egm`, `pledging`, `unclassified`.

The practical demo should reliably cover results, management changes, M&A/capex/litigation, price/volume moves, and low-priority/unclassified collapse. All 17 labels should have a mapping/fallback, even if not all have rich AI summaries. See [REQUIREMENT_TRACEABILITY.md](./REQUIREMENT_TRACEABILITY.md) for all label meanings and treatments.

## Financial behavior

- Use reported Revenue, EBITDA, PBT, and PAT; preserve period, unit/currency, source, and standalone/consolidated basis.
- QoQ compares the immediately prior quarter; YoY compares the same quarter a year earlier.
- EBITDA margin = EBITDA / Revenue. D/E = total debt / shareholders' equity. FCF = cash from operations minus capital spending.
- Label derived values. For zero/negative comparison bases or sign changes, do not show misleading percentage growth; provide absolute movement and an explanation.
- Do not interpolate a missing period or mix reporting bases. Show unavailable values and the missing period/source.
- For cash conversion, working-capital cycle, ROCE, and ROE, disclose the selected calculation convention because the reference defines the concepts but not a single formula.

## Experience and interaction principles

- **Phone first:** one-hand, responsive layouts; prioritize legibility and actionable cards.
- **Signal before volume:** material items above routine items; explain ranking in plain language.
- **Evidence at the point of use:** filing links and period/source labels next to summaries and metrics.
- **Network is contextual:** show the person and match rationale within Push/Pull, not on an isolated directory screen.
- **Trust through limits:** distinguish reported facts, calculations, and interpretation; show missing/stale/uncertain data.
- **Concise but not generic:** a short human-readable takeaway, tailored to the filing/research question, with drill-down evidence.
- The brief invites experimentation in chat, voice, dashboard, copilot, or network-map interaction. A focused digest + research workspace is the lowest-risk choice; richer modalities are not prerequisites.

## Architecture and data approach (prototype recommendation)

**Recommended stack:** TypeScript with a Next.js responsive web app, server-side route handlers, and managed Postgres (e.g. Supabase) for straightforward hosted persistence and row-level access controls. Use Zod or equivalent input validation, server-only secrets, and a typed source-adapter boundary. Use a small extraction/classification model only where deterministic parsing is insufficient; use a stronger model selectively for cited synthesis. Choose the exact model provider after checking available free tiers, data-handling terms, and latency.

High-level pipeline:

`Yahoo Finance/equivalent EOD + NSE/BSE filing links + issuer/screener primary documents + synthetic/authorized network profiles`
→ source adapters and timestamped cache
→ issuer/person identity resolution with evidence/confidence
→ deterministic period/metric extraction and calculations
→ bounded, citation-grounded model summaries where useful
→ Today, Research, and contextual Network views.

For a real deployment, enforce user/tenant isolation for network information, least privilege, consent and deletion workflows, retention limits, encryption in transit/at rest, and audited access. Use only permitted profile sources. The prototype can demonstrate with synthetic people and avoid handling real personal data.

Keep agent autonomy bounded: models may classify/summarize retrieved evidence, but should not place trades, contact people, or autonomously make investment decisions. Deterministic code owns arithmetic and alert thresholds.

## Scope and priorities

### P0 — Essential for submission

- Phone-accessible, functioning responsive web prototype.
- Push: portfolio digest with 24-hour default/period selection, material-first ordering, low-priority collapse, and one configurable EOD threshold alert.
- At least one real end-to-end announcement workflow; ideally results or management change.
- Pull: on-demand research for an arbitrary NSE ticker where data exists, using primary sources only, with source citations and missing-data behavior.
- Network: synthetic, clearly disclosed investor network; one embedded contact recommendation in Push and one in Pull or a direct “Who can help?” query.
- Seed 15–20 listed companies and ensure network overlap.
- Account for all 17 announcement labels, even if some render a filing-only card.
- Reference-correct Revenue/EBITDA/PBT/PAT and QoQ/YoY comparisons for the results workflow.
- Explain pipelines, privacy/consent/retention/access controls, model/agent choices, and cloud in the covering writeup.
- Submission-ready repository, demo link/run instructions, AI build history, and covering email.

### P1 — Important differentiators

- Narrative-vs-numbers comparison for the last four quarters against explicit management guidance.
- Management-change bio with network work/study/second-degree evidence.
- Strong explanations for M&A, capex, or litigation contact recommendations.
- More complete classification and useful summaries for the 17 labels.
- Source-backed balance sheet/cash quality indicators, trajectory, bull/bear, expertise map, or warm-reconnection scenario.
- Cost-aware caching, source freshness/quality indicators, and robust failure states.

### P2 — Optional enhancements

- Voice interaction, elaborate graph visualization, or a full conversational agent.
- Intraday alerts (the brief asks for EOD price/volume).
- Deep execution of every Pull menu item and every Network scenario.
- Production integrations with real personal networks, brokerage systems, portfolio sync, or autonomous actions.
- Broad coverage of every exchange issuer and historical document.

## Suggested implementation sequence

1. **Lock demo story and data contract:** choose 15–20 portfolio issuers, 3–5 ad-hoc examples, one results case, one management-change/material-event case, and synthetic network overlaps.
2. **Build reliable source and fixture layer:** issuer/ticker identity, source timestamps, filing links, EOD rows, quarterly values, primary reports/transcripts, and 17-label mapping. Prefer deterministic fixtures where live integrations are brittle, clearly labeled.
3. **Implement deterministic Push and calculations:** digest period/filter/ranking, routine collapse, configurable EOD threshold, and verified QoQ/YoY calculations.
4. **Implement Pull retrieval and evidence:** accept arbitrary ticker input; retrieve only primary sources; produce a concise cited snapshot and narrative-vs-numbers workflow with explicit missing-data states.
5. **Add Network matching:** synthetic profiles, company/person aliases, evidence-backed direct/second-degree matches, and embedded recommendations.
6. **Design and connect mobile-first interaction:** polish the key journeys, loading/error/stale states, and source drill-downs.
7. **Validate and deploy:** phone viewport smoke tests, financial arithmetic fixtures, citation audit, privacy review, cost check, public demo/repository, and AI build-history export.
8. **Prepare the covering email:** summarize product, decisions/tradeoffs, architecture, privacy, model/cloud choices, omissions, and next steps; verify the printed recipient/subject/deadline are still current.

## Deliberate non-goals

Do not build an investment execution/trading product, promise real-time prices, scrape restricted professional profiles, represent synthetic contacts as real, claim comprehensive market coverage, or let model-generated analysis replace primary-source evidence.
