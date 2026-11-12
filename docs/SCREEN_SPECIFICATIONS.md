# FINN Screen Specifications

## Global application shell

### Desktop

- Left navigation rail: Command Centre, Push, Research, Network, Copilot.
- Bottom of rail: Settings/account, workspace/demo identity.
- Top utility bar: global ticker/company search, latest source freshness, account menu.
- Main content max width 1440 px, 32 px outer gutters, 16–24 px column gaps.
- Preserve selected issuer/event context while switching between related screens.

### Mobile

- Top bar: FINN mark, current section title, account/settings button.
- Bottom navigation: Today, Push, Research, Network, Ask.
- Use one-column content, 16 px side gutters, 44 px touch targets, safe-area padding.
- Settings opens as a dedicated page/sheet from the account action.
- Keep a visible back path from citation/profile details to the originating item.

## 1. Command Centre

**Purpose:** Daily entry point for portfolio-level signal.

### Desktop layout

- Header: `Good morning`/time-neutral greeting, portfolio selector/count, current source freshness.
- Main two-column grid:
  - Left/wide: Priority alerts and Important announcements.
  - Right: Market summary and Network opportunities.
- Latest Intelligence spans the main width below; routine items remain collapsed.
- Compact EOD portfolio chart can appear only if it answers a comparison question; include data date and source.

### Mobile layout

Stack in this order: priority alert, market freshness/summary, important announcements, network opportunities, latest intelligence. KPI tiles become a horizontally compact or two-column grid without hiding labels/units.

### Components and actions

- Portfolio summary shows count and a small set of explicit, dated EOD facts; not a promise of intraday portfolio valuation.
- Priority alert card shows trigger and threshold/baseline.
- Announcement preview includes category, materiality, company/ticker, timestamp, one-line summary, and source action.
- Network opportunity identifies the person, the match evidence, synthetic/verified provenance, and `View connection`.
- `View all Push` opens Push with the current time window; `Research` opens the issuer with context.

### Data and states

- Show a distinct last-success time for market prices and announcement sync.
- Empty announcements offer a wider window; stale sources disclose staleness instead of showing an unqualified empty state.
- Partial load renders independent sections and section-level errors.

## 2. Push Intelligence

**Purpose:** Triage all portfolio filings in a selected time window.

### Header and controls

- Page title and visible window selector: default 24h; presets 7d/30d and custom range.
- Category filter, materiality/priority filter, portfolio selector, and routine toggle.
- On mobile, controls collapse into a filter sheet; selected filters remain as removable chips.
- A result count and window start/end stay visible.

### Digest item

Each item displays:

- Ticker/company, category label, filed time, source freshness.
- Materiality/priority text and concise summary where useful.
- Original filing link and explanation of why prioritized where available.
- Contextual Network match when evidence exists.
- Results-specific metric comparison module for Revenue, EBITDA, PBT, PAT.
- Management-change profile snippet when the incoming person has supported profile data.

### Financial comparison module

- Period selector or explicit current quarter label.
- Four metric rows/cards with reported value, currency/unit, reporting basis, source/page.
- QoQ and YoY delta with comparison period. Missing periods show `Unavailable` plus reason.
- Expandable exact source excerpt. Do not use a mini chart in place of exact numbers.
- Explain percent movement only when meaningful; for zero/negative comparison bases show absolute change and a note.

### Alert card

Price alert shows EOD date, close, percent move, source, and configured threshold. Volume alert shows observed volume, recent average, multiplier, and lookback days. Stale or incomplete baselines suppress a definitive triggered state and show the limitation.

### Routine items

Routine/`unclassified` notices are grouped with count and a clear expand action. Expanded rows preserve source access. Filters must not silently remove material items without indicating active filters.

## 3. Company Research

**Purpose:** On-demand Pull research for a supported issuer, including a ticker outside the demo seed set.

### Search / resolution

- Prominent labeled ticker/company search.
- Support NSE symbol and `symbol.NS`; support BSE only when canonical mapping is available.
- Resolution result shows issuer name, ticker/exchange, and primary-source availability.
- Ambiguous ticker/name requires explicit choice. No seed-only suggestion behavior.
- Unsupported/no-source result explains the issue and does not render a different company's data.

### Research header

- Company name, ticker/exchange, sector if sourced, report basis selector where available.
- Source availability badges for annual report, quarterly results, transcripts, and investor presentation.
- `As of` date and research generation time.
- Short source-bounded company snapshot.

### Sections

Use tabs or anchored sections; on mobile use an accessible horizontal tab strip or section menu:

1. **Overview:** business snapshot and current financial snapshot.
2. **Performance:** trajectory and Recharts trend with a table alternative.
3. **Balance sheet:** debt/leverage, D/E, working-capital cycle where data supports the chosen convention.
4. **Cash flow:** cash from operations, cash conversion, and FCF (CFO minus capital spending).
5. **Guidance tracker:** management statements aligned to observed periods.
6. **Narrative vs. numbers:** claims and delivered metrics separated and cited, ideally last four quarters.
7. **Bull / bear:** concise, balanced cases grounded in company primary documents; distinguish inference from reported fact.

Sections are a product menu. The P0 implementation may provide a focused subset; deferred sections must not appear complete if unsupported.

### Evidence presentation

- Claim-level citation affordance includes document title/type, period, page, source URL, and excerpt.
- Citation drawer is a side panel on desktop and bottom sheet on mobile.
- Separate labels for `Reported`, `Calculated`, and `FINN interpretation`.
- Source filters are restricted to primary company/exchange documents for Pull.
- A document can be opened at its source URL; if no stable page anchor exists, retain page number and excerpt.

### Network integration

Place a compact `Who can help you understand this?` panel beside/after the relevant research section. Show direct evidence and a `View connection` action; do not turn it into a generic contact recommendation.

## 4. Network Intelligence

**Purpose:** Discover a useful relationship path without presenting a contact directory.

### Search and results

- Search by person, company, sector/topic, or explicit expertise.
- Filters: direct/second-degree, relationship type, current/former experience.
- Result cards prioritize the reason for the match and evidence over a numerical score.
- Show first/second-degree with hop count and source dates; indicate synthetic records.

### Relationship graph

- P0: relationship path rendered as a compact, keyboard-accessible sequence of labeled nodes/edges, e.g. `You -> Contact A -> Incoming CFO`.
- Do not require a canvas/React Flow implementation. A textual path is easier to inspect on mobile and better at disclosing the evidence.
- P1 optional: interactive graph/map at desktop widths. The list/path remains the accessible source of truth; graph nodes are not color-only.
- On mobile, graph becomes a vertical path or is hidden behind `View relationship path`.

### Contact profile

- Name (synthetic label where applicable), current/prior roles, organizations, education, tenure.
- Provenance/source and last verified date for each profile fact.
- Relationship to investor, match reason, and known-strength label only when user-confirmed.
- Relevant companies/sectors and linked events/research, without claiming willingness or endorsement.
- Actions: return to related event/company, correct relationship, or remove contact where permitted.

### Empty/ambiguous states

- No match: “No known connection in this network.”
- Ambiguous name: show possible matches with corroborating fields; do not join automatically.
- No expertise evidence: ask the user to broaden the topic or inspect company/sector connections.

## 5. AI Research Copilot

**Purpose:** Ask a bounded question against the current issuer/event/source set.

### Layout

- A right-side contextual panel on desktop, full-height or bottom sheet on mobile.
- Context header states selected company/event and allowed source scope.
- Suggested prompts are examples, not a substitute for a natural-language input.
- Answers are compact, with claim citations and clear `Reported`/`Calculated`/`Interpretation` sections.
- Follow-up input remains available after answer; source citations open the same evidence drawer used in Research.

### Behavior

- Starts only after explicit user action; no unsolicited chatbot greeting.
- Company research questions use primary documents only.
- Announcement explanations use the original filing and preserved filing metadata.
- Network questions use deterministic workspace-local matching and do not send private profiles to the LLM.
- If the context lacks evidence, answer with the gap and a useful next step.
- Copilot can link to Research, Push, or Network, carrying context without leaking it to unrelated screens.

## 6. Settings

Use focused sections with explicit save state:

### Portfolio

- Add/remove supported NSE/BSE companies, exchange and ticker confirmation, sector/size labels when sourced.
- Show portfolio count; prevent duplicate instruments and make the 15–20 demo portfolio clear.

### Alerts

- Announcement category preferences using the reference taxonomy.
- Price move threshold in percent and direction; volume multiplier and lookback days.
- State EOD evaluation timing and last available market date near the controls.
- Inline input errors and a test/example explanation; do not imply intraday watch.

### Data refresh

- Per-source last attempt, last success, and status: Current, Delayed, Stale, Unavailable.
- Manual refresh action only if source rules permit; show queued/completed/failure state.

### Privacy

- Label mock contacts as synthetic.
- Summarize stored fields, source/consent status, access boundary, and retention.
- Provide export/delete-network action for user-controlled records; confirm destructive deletion.

## Shared design tokens

See [DESIGN_SYSTEM.md](./DESIGN_SYSTEM.md) for exact palette, typography, spacing, responsive breakpoints, components, accessibility, and motion. No screen may redefine semantic colors or financial number formatting locally.

## Responsive specification

| Width | Navigation | Layout behavior |
|---:|---|---|
| `< 640 px` | Top bar + five-item bottom navigation | One column; tables convert to labeled metric rows or contained scroll regions; filters/profile/citations use sheets. |
| `640–1023 px` | Compact rail or bottom navigation based on available width | One or two columns; preserve readable table widths and chart labels. |
| `1024–1439 px` | Persistent left rail + utility bar | Two-column dashboard/research layouts; citation drawer. |
| `>= 1440 px` | Persistent rail + centered content | Content max-width 1440 px; do not stretch data cards. |

## Shared state specifications

### Loading

- Preserve shell/header and show section-level skeletons.
- Research shows factual stages only: finding sources, reading documents, preparing cited analysis.
- Keep validated prior data on screen during refresh with source time; avoid empty flashes.
- Push refresh shows last-success time alongside any in-progress indicator.

### Empty

- Command Centre: explain selected window and last source sync; allow widening the window.
- Push: distinguish no events from stale/unavailable announcement source.
- Research: distinguish unknown ticker, ambiguous issuer, no primary sources, and no data for a requested section.
- Network: no known match is not proof of no relationship.
- Copilot: prompt the user to select a company/event or provide a question; no fake conversation.

### Error

- Use section-level errors and preserve available sibling data.
- Show concise user action, retry only transient errors, and a request ID where relevant.
- Differentiate authentication, permission, source-rate-limit, parsing, model, and network failures.
- Never replace errors with empty success-shaped states.

### Partial data

- State which data is available, missing, stale, or unverified.
- Do not draw a line through missing chart periods; do not treat absent values as zero.
- Any derived metric exposes source basis, formula convention, and citation.

## Content hierarchy and formatting rules

- Price: show currency and EOD date; percentage includes sign and reference period.
- Volume: show unit/share convention and baseline lookback for multiple comparisons.
- Financials: show INR and source unit (for example, crore) consistently, period, standalone/consolidated basis, and source citation.
- QoQ is the immediately previous quarter; YoY is the same quarter a year earlier.
- Revenue, EBITDA, PBT, and PAT follow the reference glossary; do not relabel another profit measure as EBITDA.
- Percent comparisons with zero/negative bases or sign changes are replaced with absolute movement and an explanation when the percentage would mislead.
- Status/materiality labels use words and icons as well as color.
