# Covering Email — FINN Build Challenge

**To:** assessment@enam.com  
**Subject:** IIT Kanpur – Founding AI Engineer - 2027

Dear ENAM Hiring Team,

I built FINN, a mobile-first investment-intelligence prototype connecting
portfolio announcements (Push), primary-source company research (Pull), and
evidence-backed professional-network context (Network). The application
includes a responsive Next.js interface, FastAPI services, deterministic
announcement/materiality and financial calculations, PDF retrieval with
page-level citations, synthetic relationship intelligence, and a bounded
Copilot router that calls the existing services.

The main technical decision was to keep financial arithmetic, alert
thresholds, materiality rules, and relationship traversal deterministic and
explainable. Optional LLM use is limited to retrieved primary-source Pull
answers and embeddings; citations are validated against retrieved document
chunks, and network contact data is not sent to the model. The intended
architecture uses Next.js, FastAPI, PostgreSQL with optional pgvector, and
Vercel/Render/Supabase. These cloud services have not yet been deployed.

The demonstration portfolio values, filings, financial/document examples, and
fictional network profiles are explicitly synthetic and are not company-
reported data or real contact records. I deliberately excluded secondary
research as Pull evidence, automated LinkedIn scraping, intraday market data,
autonomous model actions, and unsupported investment recommendations. Before
production, I would prioritize hosted authentication and database-enforced
tenant isolation, live-source validation, retention controls, scheduled
ingestion, and verified end-to-end workflows.

The repository test report records 145 passing backend tests and passing
frontend lint, type checking, and production build. Authenticated complete
workflows and hosted services remain to be verified; I will provide links
only after they are available and tested.

- **Application:** [INSERT VERIFIED DEPLOYED URL — currently not deployed]
- **Public GitHub repository:** [INSERT URL AFTER SUCCESSFUL PUBLIC PUSH]
- **AI build history:** [INSERT ACTUAL SESSION EXPORT/SHARE LINK(S)]

Regards,  
[Your Name]  
[Your Contact Information]
