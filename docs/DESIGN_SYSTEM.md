# FINN Design System

## Design intent

FINN should feel like a quiet, high-conviction investment desk: compact, source-aware, and deliberate. It is not a consumer trading app and not a generic AI chat surface. Every screen should make it easy to answer:

1. What changed?
2. Why should I care?
3. What is the evidence?
4. Who in my network could help?

Push, Pull, and Network are product capabilities, not visual silos. Announcement and research views should bring network context forward when relevant; the network itself should offer a route back to the triggering event or company.

## Colour palette

Use a light institutional canvas as the default. Keep color semantic and restrained; do not use gradients, glow effects, or color alone to convey meaning.

| Token | Hex | Use |
|---|---|---|
| `canvas` | `#F4F6F8` | App background. |
| `surface` | `#FFFFFF` | Cards, sheets, navigation surfaces. |
| `surface-muted` | `#EEF2F5` | Quiet inset panels, chart plot area, selected filter background. |
| `ink` | `#17212B` | Primary text and high-emphasis figures. |
| `ink-secondary` | `#526171` | Supporting labels and descriptive text. |
| `ink-muted` | `#788695` | Metadata, timestamps, inactive labels. Maintain accessible contrast at intended size. |
| `line` | `#DCE3E9` | Dividers, card borders, table rules. |
| `brand` | `#173B57` | Primary actions, active navigation, links, focus accents. |
| `brand-strong` | `#0E2D45` | Pressed/hovered primary state. |
| `brand-tint` | `#E8F0F5` | Selected navigation and low-emphasis brand surfaces. |
| `positive` | `#18794E` | Positive movement and success. Pair with sign/label. |
| `positive-tint` | `#EAF5EF` | Subtle positive backgrounds. |
| `negative` | `#B54745` | Negative movement and critical event text. Pair with sign/label. |
| `negative-tint` | `#FAEEEE` | Subtle negative backgrounds. |
| `caution` | `#9A6700` | Warnings, stale source, incomplete periods. |
| `caution-tint` | `#FFF5D9` | Subtle warning backgrounds. |
| `info` | `#356A8A` | Neutral informational status. |
| `info-tint` | `#EAF2F7` | Subtle information backgrounds. |

### Semantic rules

- Positive/negative colors describe a measured movement, not a judgment about investment quality.
- Never use green/red as the only signal. Include `+/-`, words, icons with accessible names, or explicit status text.
- Materiality is a separate dimension from price direction. Use priority labels and a narrow side marker, not a red/green wash over a full card.
- `unclassified` and routine items use neutral tones and remain discoverable.
- Source freshness uses `Current`, `Delayed`, or `Stale` text with a timestamp and restrained status icon.

## Typography

Use **Inter** for interface text and figures, with system sans-serif fallbacks. Use tabular numerals for aligned financial values. Do not mix multiple display fonts.

| Style | Size / line height | Weight | Typical use |
|---|---|---|---|
| `display` | 30 / 36 px desktop; 26 / 32 mobile | 600 | Page heading only. |
| `title-lg` | 22 / 28 px | 600 | Company name or major screen title. |
| `title-md` | 18 / 24 px | 600 | Section heading. |
| `title-sm` | 15 / 20 px | 600 | Card heading, table group. |
| `body` | 14 / 20 px | 400 | Main copy and announcement summary. |
| `body-sm` | 13 / 18 px | 400 | Secondary details, evidence explanation. |
| `label` | 12 / 16 px | 500 | Field labels, category badges, chart legends. |
| `micro` | 11 / 14 px | 500 | Source timestamp and dense metadata; never for essential content. |
| `metric-lg` | 28 / 32 px | 600 | Primary portfolio or company metric. |
| `metric-md` | 20 / 24 px | 600 | Card metric. |
| `table-number` | 13 / 18 px | 500 | Financial table cells; tabular figures, right-aligned. |

Typography should create hierarchy through size, weight, and alignment, not all-caps labels. Use sentence case. Reserve uppercase for compact ticker/symbol labels only.

## Layout, spacing, and density

- Base spacing unit: **4 px**. Common scale: 4, 8, 12, 16, 20, 24, 32, 40, 48.
- Main content max-width: **1440 px**; desktop gutters 32 px, tablet 24 px, mobile 16 px.
- Card padding: 20 px desktop, 16 px mobile. Dense data rows: 12–16 px vertical padding.
- Use a 12-column desktop grid with consistent 16–24 px gutters. Avoid more than two competing primary columns.
- Separate sections with whitespace and alignment before adding borders. Use 1 px neutral lines; avoid heavy shadows.
- Cards use 8 px radius, popovers/sheets 10 px, pills fully rounded. No ornamental cards without a user action or decision purpose.
- Financial tables align labels left and numeric values right. Keep periods in columns and units/basis in the table header or adjacent metadata.
- Put source citations at the point of claim, not only in a page-level bibliography.

## Component styles

### Navigation

- Active navigation uses brand text and a soft tint/left marker, not a large filled tile.
- Primary actions use `brand` background with white text; secondary actions use white/surface with a neutral border.
- Destructive actions require explicit confirmation and use negative styling sparingly.
- Buttons: 40 px minimum desktop height, 44 px minimum touch height on mobile. Show clear disabled, focus, hover, pressed, and loading states.

### Information hierarchy

- **Priority marker:** `High`, `Watch`, or `Routine` text plus a slim marker; do not rely on color-only severity.
- **Category badge:** neutral outline/tint; preserve the source label for uncommon classes.
- **Ticker chip:** compact monospaced/tabular symbol, with company name always available nearby.
- **Metric tile:** label, large value, unit, period, and optional QoQ/YoY delta. All context remains visible at mobile widths.
- **Evidence citation:** inline source label + page/period; opens a source drawer with excerpt, full filing link, and data basis.
- **Network match card:** named person, synthetic/verified status, match type, relationship hops, and evidence sentence. Avoid unsupported labels such as “trusted” or “expert.”
- **Alert card:** trigger, observed value, threshold/baseline, market date, and freshness.
- **Routine filing group:** collapsed by default in Push but accessible with count and explicit expand control.

### Charts

- Recharts is appropriate for compact close/volume and financial trend charts.
- Prefer a single meaningful series plus a comparison series over dense multi-axis charts.
- Use zero lines, labeled axes, direct period labels, and hover/tap tooltips that include exact values and source basis.
- Maintain accessible text/table alternatives. Charts must not be the only presentation of material values.
- Avoid dual axes unless necessary and clearly labeled. No 3D, animated trading ticker, or decorative sparkline without scale context.
- Comparison charts must distinguish reported data from derived data and show missing periods as gaps, not zeros.

### Inputs and filters

- Search is a labeled input with ticker/company examples, validation, and an explicit empty/unsupported result.
- Date-window presets (24h, 7d, 30d, custom) should expose the actual selected range.
- Category filters are multi-select chips on wide screens and a filter sheet on narrow screens.
- Threshold settings always include units, lookback period, and a short explanation of EOD timing.

## Navigation model

### Desktop / wide tablet

- Persistent left rail: **Command Centre**, **Push**, **Research**, **Network**, **Copilot**.
- Settings is available from the account control in the rail/footer, not a peer investment workflow.
- Top utility bar: global ticker/company search, source freshness/last sync, and account control.
- Command Centre is the landing page. Push, Research, and Network keep ticker/company context in the URL or page state.

### Mobile

- Compact top bar: FINN wordmark, current page title, account/settings action.
- Five-item bottom navigation: **Today**, **Push**, **Research**, **Network**, **Ask** (Copilot).
- Settings opens from the account action/sheet. Avoid a hamburger menu as the only route to core flows.
- Keep persistent bottom navigation clear of safe areas and keyboard; forms move primary actions above the keyboard.
- Deep links from an announcement to research/network preserve a clear back path to the originating event.

## Responsive breakpoints

Use these as layout targets, not device detection rules:

| Token | Width | Behavior |
|---|---:|---|
| `mobile` | `< 640 px` | One column, bottom navigation, stacked KPI tiles, tables become labeled rows/cards, filters in sheet, charts with touch tooltip. |
| `tablet` | `640–1023 px` | Two-column where content allows, compact side rail or bottom nav depending on width, reduced gutters. |
| `desktop` | `1024–1439 px` | Full side rail, 12-column grid, two-column command centre and research layouts. |
| `wide` | `>= 1440 px` | Center content at 1440 px max width; do not stretch tables/cards across ultrawide displays. |

Test at 360 px, 390 px, 768 px, 1024 px, and 1440 px. No horizontal page scroll at mobile sizes; tables may scroll within a labeled region only when card conversion would harm comparison.

## Interaction, motion, and accessibility

- Use motion only for state transitions (drawer, filter, loading) and keep it short; honor reduced-motion preferences.
- Keyboard navigation and visible focus are required for desktop; touch targets should be at least 44 × 44 px when practical.
- Maintain WCAG AA text contrast for normal-size content and provide semantic landmarks/headings.
- Announce async completion/error status to assistive technology; chart points and source links need accessible names.
- Preserve filter/search state across a detail drawer and back navigation.
- Avoid modal stacking; use a single drawer/sheet for citations, filters, and profile details.

## Loading states

- Use skeletons that match the expected content geometry; avoid spinners for whole pages when stable shell content can render.
- Keep the page title/navigation visible while sections load independently.
- For source sync, show last successful timestamp and a compact updating state; do not imply that a skeleton represents live data.
- For research, show staged progress: `Finding primary sources`, `Reading documents`, `Preparing cited analysis`. Only show stages the backend actually reports.
- Keep prior validated content visible during refresh, marked with its source time; do not flash an empty state between refreshes.

## Empty states

- **No announcements:** identify the selected window and provide a control to widen it.
- **No portfolio:** prompt to add listed companies; do not fabricate holdings.
- **No supported company sources:** state that no primary documents were found for the ticker and suggest checking the symbol; do not display a demo company's research.
- **No network match:** say “No known connection in this network” and retain a way to ask a broader expertise query.
- **No matching alerts:** state the active thresholds and last data date.
- **No saved research:** show a focused ticker-search action, not an empty chat transcript.

## Error and degraded states

- Distinguish invalid ticker, ambiguous identity, upstream source unavailable, stale data, partial documents, and model failure.
- Preserve accessible source records when model enrichment fails. A failed summary must not erase the filing.
- Show retry only for transient failures; offer source link or a clear explanation for permanent/unavailable access.
- For partial research, list available/missing document types and still show verified metrics/citations.
- Never show success-colored empty cards for failed ingestion or unsupported data.
- If an API request fails, retain filters and user input; show a concise error with request ID where useful.

## Content and trust language

- Say **“reported”** for source values, **“calculated”** for deterministic metrics, and **“FINN interpretation”** for model synthesis.
- Every derived statement has evidence or a clear limitation; uncertainty is explicit and neutral.
- Label synthetic people and illustrative fixtures in the UI.
- Label market data as EOD and show market date, fetched time, and source.
- Network relevance is a lead, not a claim that someone is close, trusted, available, or willing to help.

## Deferred visual complexity

- No default dark trading-terminal theme, high-saturation red/green canvas, gradients, or animated market tape.
- No graph canvas as a required workflow; evidence-first relationship cards are the P0 design. A compact, accessible graph/map can be explored later.
- No conversational bubble UI as the home page. Copilot is a research utility within the investment workspace.
