# FINN Assignment Requirement Analysis

## Review scope and source verification

Reviewed every page of both official PDFs:

- `1. ENAM_Founding AI Engineer Build Challenge_Main.pdf` — 5 pages.
- `2. ENAM_Build_Challenge_Reference.pdf` — 3 pages.

Page text was extracted and checked page by page. The PDFs contain no embedded page images, file attachments, or annotations; the relevant category table was extracted and checked. The main brief contains three numbered pages of product requirements, two pages of architecture/evaluation/submission guidance; the reference contains the full announcement table and glossary.

The deadline printed in the brief is **15 November 2026** (release 8 November 2026). Check the actual submission window before relying on that date.

## A. Business problem

Investors face a continuous stream of prices, filings, announcements, results, and macro information, much of which is immaterial. FINN should filter that stream, surface what matters, and explain why it matters rather than merely aggregate information.

An investor's personal and professional relationships are an underused source of insight. FINN should reveal who knows a company, its sector, its competitors, or a person appearing in a filing, and why that connection may be useful. The product should become part of a daily workflow and save time.

## B. Expected product

FINN is a **mobile-first financial investment agent** with two modes and a cross-cutting third layer:

1. **Push** — proactively explains what changed and why the investor should care.
2. **Pull** — researches or analyses a company on demand.
3. **Network** — privately connects events and research to people who can add context. It should appear within Push and Pull when relevant, and may also answer direct questions; it is not a separate contact-list app.

The frontend, interaction model, product choices, and design are deliberately open. The expected outcome is an interactive, working prototype, not a complete production system. A focused, working demonstration is explicitly preferable to a broad, broken one.

## C. Push requirements

### Windowed digest

- Cover corporate filings/announcements across the selected portfolio.
- Default to the **last 24 hours**, and let the investor choose another period.
- Filter and prioritize important items; routine items may be collapsed or hidden.

### Triggered alerts

- Alert on a material announcement of a type the investor cares about.
- Alert on unusual end-of-day price/volume moves.
- Make thresholds configurable. Examples in the brief are volume greater than approximately **2× its recent average** and a daily price move beyond a user-selected ±X%.
- The examples illustrate thresholds; the brief does not prescribe a specific averaging window, X%, or real-time/intraday feed.

### Event enrichment and presentation

- **Management change:** for an incoming senior person, show a short background/bio and whether the investor's network has a direct work/study overlap or a one-connection-away link.
- **Quarterly results:** use the actual results filing to compare **Revenue, EBITDA, PBT, and PAT** for the current quarter against the immediately preceding quarter (**QoQ**) and the same quarter a year earlier (**YoY**).
- **Material events:** for events such as M&A, large capex, and litigation, surface the best-placed network contact and explain why they are relevant.
- For other announcement types, make a considered choice between a concise summary and surfacing the filing at an appropriate priority.

## D. Pull requirements

Pull is on-demand research of a company, grounded in primary company material—especially **annual reports and concall/earnings-call transcripts**. The pull analysis must not rely on broker notes, news, research reports, or the model's outside knowledge of the company.

The eight candidate outputs are a menu, not a compulsory checklist:

1. Business snapshot: activities, segments, revenue mix.
2. Financial snapshot: current headline numbers, margins, PAT, key ratios.
3. Trajectory: multi-year growth/compression trends.
4. Balance sheet: debt, leverage, working-capital cycle, funding structure.
5. Cash quality: cash-flow trend and cash conversion.
6. Narrative vs. numbers: management claims compared with financial results.
7. Guidance: management's explicit expectations for growth, margins, capex, etc.
8. Bull vs. bear: concise cases on each side.

The worked example proposes comparing the last four quarters' delivery with management's own headline guidance and growth commentary. The brief identifies this as especially valuable analysis, but the wider list is explicitly a menu. Research should generalize to any NSE ticker **where data is available**, rather than being hard-wired to demo companies.

## E. Network requirements

- Create a mock investor network and decide what starting information the investor provides. Suggested inputs include personal/professional acquaintances, companies and people met over the past 2–3 years, alma maters, and past employers.
- Ensure that the sample network overlaps with portfolio and research companies; this overlap is important to the demo.
- Profile people using role, employer, education, and tenure information.
- Demonstrate network connections in Push and/or Pull, and offer direct querying as an option.
- The brief's scenario ideas include: who to call for company/sector diligence; second-degree reach and link strength; diligence on a management team/promoter; expertise discovery; and a timely reason to reconnect.
- Make the network feel like a quiet analytical advantage, not a contact list. The scenario list is illustrative, not a requirement to build every scenario.
- Use only profile information that can legitimately be accessed, a public dataset, or realistic synthetic profiles. Disclose what was used and how real deployment would work. Respect platform terms of use.

## F. Backend and data-source requirements

The main brief guides the prototype toward four source types and calls this plumbing rather than the point of the assignment:

1. **End-of-day price and volume** for the portfolio. Yahoo Finance/yfinance is the suggested starting point; NSE tickers use `.NS` and BSE tickers `.BO`. Equivalent sources are allowed.
2. **NSE/BSE corporate announcements and filings** for the stocks.
3. **Company fundamentals:** annual-report and concall-transcript links, available via screener.in or company investor-relations sites.
4. **Network profiles:** public professional-profile information (roles, employers, education, tenure), subject to lawful access and platform terms, or realistic synthetic/public-dataset profiles.

Choose a **15–20-company NSE/BSE-listed mock portfolio**, spanning sectors and company sizes. Also choose a handful (suggested 3–5) of ad-hoc research companies, which may be outside the portfolio. The company counts are explicit choices/guidance in the brief; the source itself labels some research examples as suggestions.

## G. Financial calculations and terminology

Use the reference definitions, label periods and units, and preserve the source basis:

- **Revenue:** sales / top line.
- **EBITDA:** earnings before interest, tax, depreciation, and amortisation; an operating-profitability proxy.
- **PBT:** profit after costs and interest but before income tax.
- **PAT:** profit after tax / net profit.
- **Margin:** profit measure divided by revenue; e.g. EBITDA margin = EBITDA ÷ revenue.
- **QoQ:** current quarter vs. immediately previous quarter.
- **YoY:** current quarter vs. same quarter one year earlier, to reduce seasonality effects.
- **Debt-to-Equity (D/E):** total debt ÷ shareholders' equity.
- **FCF:** cash from operations minus capital spending.
- **Balance sheet:** point-in-time assets, liabilities, and shareholders' equity.
- **Cash conversion:** how well accounting profit turns into cash. The reference gives a concept, not a single mandated formula; disclose any chosen calculation.
- **Working-capital cycle:** cash tied up in inventory and receivables, less supplier payables; lengthening may consume cash.
- **ROCE/ROE:** return on capital employed / shareholders' equity; state the source convention if calculated.
- **Contingent liabilities:** potential obligations disclosed in notes, not yet on the balance sheet.
- **Related-party transactions (RPTs):** dealings with promoters/insiders or their other businesses.
- **Auditor qualification:** an auditor concern about accounts, rather than a clean sign-off.
- **Market capitalization:** share price × number of shares.
- **Promoter pledging:** promoter shares pledged as loan collateral; heavy pledging is a risk signal.
- **Guidance:** management's stated forward expectations.
- **EOD:** post-market-close close price and traded volume.

The reference defines dividends, record dates, bonus/splits, buybacks, rights issues, QIPs, and preferential allotments in the corporate-action glossary. These are useful for announcement interpretation, not alternative definitions of financial metrics.

For computed comparisons, require compatible periods, units, currency, and reporting basis (standalone or consolidated). Do not fabricate unavailable comparisons; state the missing period or source and show the reported values/period labels. If a number is extracted or calculated, retain a path to the primary filing and relevant page/table.

## H. AI/LLM requirements

- The brief does **not** mandate a particular model, vendor, or agent framework. Open-source, local, and commercial models are allowed.
- The architecture writeup must say which steps use a model, which model and why, and whether agents plan, call tools, or act autonomously.
- Pull must be grounded in primary sources only. Model outside knowledge must not fill evidence gaps.
- Efficient routing, caching, and chunking are called out as bonus-worthy cost-conscious instincts; free tiers are sufficient.
- Push enrichment about people and Network insights are explicitly distinguished from the primary-source-only constraint for Pull.
- Because hallucinations are a material product risk, proposed outputs should show evidence links/snippets, distinguish extracted facts from inference, and abstain when evidence is missing.

## I. UI/UX expectations

- Mobile-first and easy to try on a phone.
- Concise, beautifully presented, interactive; prioritize signal over raw volume.
- Show density and design together, with simplicity supported by technical depth.
- Interaction can be chat, voice, copilot, dashboard, network map, or another model. Experimentation is encouraged, not prescribed.
- Product judgment (what to emphasize, collapse, summarize, or omit) matters more than implementing every menu item.
- Avoid generic, repetitive AI-generated templates ("AI slop").

## J. Security and privacy requirements

The Network handles personal information. The architecture writeup must explain:

- How network information is private to its investor.
- What personal data is stored and for how long.
- How consent and access control would work in a real deployment.
- How profile-source terms and legitimate access are respected.

Use synthetic profiles in the prototype unless real profile access is authorized and appropriate.

## K. Architecture and cloud requirements

The required writeup should address:

- Data pipelines: fetch, refresh, store, and link market data, filings, fundamentals, and profile data (including matching filing names to network people).
- Models/agents: which steps use AI, model choice and rationale, and whether agents plan, invoke tools, or act independently.
- Cloud: what runs where and why.
- A simple architecture diagram is welcome, not mandatory.

No specific cloud provider or production-grade security architecture is mandated for the prototype.

## L. Final deliverables and submission

The brief asks for:

1. A working mobile-first prototype, accessible by deployed link, Expo/TestFlight, or responsive web, and easy to try on a phone.
2. A public GitHub repository.
3. AI build history: the coding-agent/LLM sessions used during the build (exports/share links) so reviewers can understand prompting, breakdown, course correction, and judgment.
4. A short covering email describing what was built, key decisions/tradeoffs, architecture (pipelines, privacy/security, AI/agents, cloud), deliberate exclusions, and next steps.

Send links/attachments to **assessment@enam.com** with subject **"IIT Kanpur – Founding AI Engineer - 2027"**. The printed subject and deadline are transcribed as in the document; confirm they remain current before sending.

## M. Evaluation criteria

The explicit evaluation signals are:

- Building ability, product instinct, creativity, and judgment.
- A coherent point of view about a real investor's daily workflow.
- All three layers—Push, Pull, and Network—present, with at least one working workflow each.
- Network woven into Push or Pull, not bolted on.
- A focused, working, beautiful/mobile-first prototype; thin-but-working beats broad-but-broken, and a demo that does not run is the worst outcome.
- Thoughtful architecture and privacy/security decisions.
- Efficient model and data choices; cost discipline earns bonus points.
- Deliberate selection of what to build and what to leave out. Completeness/polish are not the primary grading target.

## Mandatory vs. optional interpretation

**Must satisfy for a credible submission:** working phone-accessible mobile-first prototype; Push, Pull, and Network workflows; network integration into Push/Pull; 15–20-company mock portfolio; generalizable research for available NSE tickers; four guided data-source types; primary-source-only Pull; clear privacy/data/model/cloud writeup; submission artifacts and covering email.

**Guidance/examples, not a rigid checklist:** the exact interaction modality; every one of the eight Pull outputs; every Network scenario; exact source provider; exact announcement taxonomy (the brief permits adapting or ignoring it); exact threshold values/window; production-grade deployment architecture. The supplied 17 labels are all accounted for in the traceability plan as the sensible default taxonomy, while preserving the brief's statement that this taxonomy is guidance.

## Requirement trace

The row-by-row implementation and verification plan is in [REQUIREMENT_TRACEABILITY.md](./REQUIREMENT_TRACEABILITY.md). Risk mitigations are in [RISK_REGISTER.md](./RISK_REGISTER.md), and the smallest compelling product and suggested priority order are in [PRODUCT_SPECIFICATION.md](./PRODUCT_SPECIFICATION.md).
