# FINN Network Intelligence

FINN's Network layer provides professional relationship intelligence for investment due diligence. All contact profiles in this demonstration are explicitly fictional and synthetically generated; they must never be represented as live network data.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│ Workspace-scoped relational records                 │
│ Contacts │ Experiences │ Explicit relationships     │
│ Education │ Company/entity match evidence            │
└───────────────────┬─────────────────────────────────┘
                    │ authenticated workspace queries
         ┌──────────▼──────────┐
         │   Service Layer     │
         │  service.py         │
         │  depth-2 BFS        │
         │  transparent ranks  │
         └──────────┬──────────┘
                    │
         ┌──────────▼──────────┐
         │  Matching Engine    │
         │  matching.py        │
         │ exact + conservative│
         │ fuzzy proposals     │
         └─────────────────────┘
```

## Contact Data Model

Each contact profile stores:

| Field | Description |
|-------|-------------|
| `display_name` | Full name (synthetic) |
| `current_role` | Most recent title (derived from open-ended experience) |
| `current_employer` | Most recent organisation |
| `previous_employers` | Ordered list of past organisations |
| `education` | Institutions and graduation years |
| `graduation_year` | Latest graduation year from education records |
| `expertise` | Titles held across career history |
| `industry_experience` | Sectors worked in |
| `companies_worked_with` | All organisations (current + prior) |
| `connection_type` | How the investor knows this contact |
| `connection_distance` | 1 = first degree, 2 = second degree |
| `last_interaction` | Date of last explicitly recorded contact |
| `relationship_strength` | `strong` / `moderate` / `light` |
| `relationship_evidence` | Quoted evidence; always says "fictional" for synthetic data |
| `is_synthetic` | Always `true` for demonstration contacts |

## Entity Matching

FINN matches network contacts against external entities (portfolio companies, executives in announcements, research report subjects).

### Matching Strategy

1. **Exact match** – normalised strings are equal; confidence = 1.0.
2. **Fuzzy person match** – SequenceMatcher ratio ≥ 0.96 and token similarity ≥ 0.8; method = `fuzzy_proposed`. Requires human confirmation before use.
3. **Fuzzy company match** – SequenceMatcher ratio ≥ 0.94 and token similarity ≥ 0.8; method = `fuzzy_proposed`. Requires human confirmation before use.
4. **No match** – single-token person queries or scores below the threshold produce no candidate.

### What Matching Does NOT Do

- Career-history overlap does **not** create a relationship edge.
- A name match is a *proposed* identity link only; it does not assert the person knows anybody in the network.
- Fuzzy matches are stored as `status = "proposed"` in `entity_matches` and must be confirmed by a user before acting on them.

### Matching Targets

| Target | Source |
|--------|--------|
| Supported NSE companies | Exact `company_aliases` ticker, linked experience IDs, then conservative employer-name matching against that company's legal/display names |
| Competitor/supplier/customer employers | Explicit `PersonExperience` organization labels; canonical company matches are accepted only on exact evidence and fuzzy matches remain proposed |
| Executives in announcements | Exact full-name occurrence in management-change `announcements.headline` + `body_text` |
| Executives in research reports | Exact full-name occurrence in same-workspace `research_reports.content` / summary |

## Network Graph

The relationship traversal in `finn_api/network/service.py` builds a bounded
in-memory adjacency list from same-workspace `NetworkRelationship` records.
`NetworkEdge` compatibility rows and employment/education records are not
traversed.

### Node Kinds

| Kind | Description |
|------|-------------|
| `investor` | The workspace anchor (the FINN user) |
| `contact` | A network contact (1st or 2nd degree) |
| `organisation` | A company or employer entity |
| `institution` | An educational institution |
| `executive` | An incoming executive matched from an announcement |

### Edge Kinds

| Kind | Traversed by default BFS? | Description |
|------|--------------------------|-------------|
| `direct_relationship` | ✅ Yes | Explicitly recorded 1st-degree relationship |
| `second_degree` | ✅ Yes | Explicitly recorded 2nd-degree path |
| `employment` | ❌ No | Career history link (not a relationship) |
| `education` | ❌ No | Education history link (not a relationship) |
| `executive_match` | ❌ No | Proposed executive–contact name match |

### Key Design Decisions

- **BFS is bounded at depth 2.** FINN does not compute 3rd-degree paths.
- **Career overlap is expertise context, not acquaintance.** Experience records are used to find relevant expertise and company matches, never to create relationship edges.
- **All synthetic relationship evidence must contain the word "fictional"** (enforced at load time).

## Intelligence Workflows

### 1. Who Should I Call? (`who_to_call`)
Ranks all reachable contacts by relationship strength, recency, and company relevance. Supply `ticker` to focus on a portfolio position.

### 2. Second-Degree Reach (`second_degree_reach`)
Returns only 2nd-degree contacts, useful for identifying warm-introduction opportunities.

### 3. Management Diligence (`management_diligence`)
Matches an incoming executive name against the contact network. Fuzzy matches are proposed but not asserted. Requires `ticker` or `executive` parameter.

### 4. Sector Expertise Mapping (`sector_expertise`)
Filters contacts by explicit expertise query. Supply `expertise` parameter (e.g., "pharma" or "fintech").

### 5. Keeping the Network Warm (`keep_warm`)
Surfaces 1st-degree contacts whose last recorded interaction was ≥ 180 days ago.

## Ranking

Contacts are scored 0–100 using explicit signals only:

| Signal | Points |
|--------|--------|
| 1st-degree connection | +20 |
| 2nd-degree connection | +10 |
| Strong relationship | +15 |
| Moderate relationship | +8 |
| Light relationship | +3 |
| Portfolio company employer match | +35 |
| Sector match | +18 |
| Expertise query match | +25 |
| Executive name match (confidence-weighted) | up to +35 |

Every recommendation includes a `reasons` list explaining each point contribution.

## APIs

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/v1/network/contacts` | Contact search |
| GET | `/api/v1/network/contacts/{id}` | Contact detail |
| GET | `/api/v1/network/expertise` | Expertise search |
| GET | `/api/v1/network/companies/{ticker}/connections` | Company connections |
| GET | `/api/v1/network/second-degree` | Second-degree contacts |
| GET | `/api/v1/network/paths/{id}` | Relationship path |
| GET | `/api/v1/network/recommendations` | Ranked recommendations |

All endpoints require `workspace_id` and enforce workspace-scoped access control. A user may not access contacts from another workspace.

## Frontend Workspace

The Network workspace uses the typed client in `frontend/src/lib/network-api.ts` and a same-origin API proxy. It provides contact, NSE ticker/company-name, and expertise search; company names are resolved through the company-search API and ambiguous matches require a ticker. It also provides first-/second-degree filters, ranked recommendation workflows, an interactive React Flow graph, and a selected-contact panel with the backend relationship path, career history, education, and evidence.

The graph renders only explicit relationship paths. If a second-degree path intermediary is not part of the current search result, the UI shows that person as a non-selectable path node rather than drawing a misleading direct edge. Shared employers and institutions are displayed only as background overlap, not as relationship evidence.

The same recommendation panel is embedded in Company Research and management-change announcement details. Private endpoints require a user JWT: the Network screen has a session-only access-token entry control, but this is not a full sign-in or user-provisioning flow. The browser sends the token only to FINN's same-origin proxy; workspace membership remains enforced by the backend.

## Security

- Network records are **workspace-scoped**; cross-workspace access returns HTTP 403.
- Authentication uses a JWT verified by configured Supabase-compatible JWKS/issuer/audience settings and maps its subject to a provisioned application user; unauthenticated requests return HTTP 401. Missing verifier configuration fails closed.
- Synthetic data is flagged with `is_synthetic: true` in all API responses.
- Executive name matches are stored as `status = "proposed"` and require human review.

## Seeding Synthetic Data

```powershell
# Requires: PostgreSQL running and FINN_DATABASE_URL configured
python scripts/seed_network_data.py --workspace-id <uuid>
```

The seed script loads `data/fixtures/network_contacts.json`, which contains 36 fictional professional profiles with diverse sector exposure and explicitly recorded investor/contact and contact/contact relationships. It also creates a deterministic synthetic investor anchor. It no longer creates same-sector `synthetic_peer` links.

## Demonstration Scenario: Incoming Executive Match

The fixture includes a synthetic announcement:
> *"[DEMO ONLY] Fictional appointment of Mira Deshpande as chief strategy officer"*

Running `GET /api/v1/network/recommendations?workflow=management_diligence&ticker=ICICIBANK` will:
1. Discover the announcement from ICICI Bank
2. Match the executive name "Mira Deshpande" against contacts
3. Return Mira Deshpande (synthetic-002) as the top recommendation
4. Store an `entity_match` record with `status = "proposed"` and `confidence` score
5. The response includes `evidence_quality = "explicit_synthetic_fixture"`

This demonstrates the full pipeline: announcement → executive extraction → name matching → contact recommendation → evidence storage.

## Limitations

- JWT verification and API membership checks are implemented. PostgreSQL RLS, real user provisioning, rate limiting, and a complete frontend sign-in flow remain outstanding; do not use real private contact data until they are complete.
- pgvector is required only for the Pull (RAG) layer; the Network layer works with standard PostgreSQL.
- Relationship evidence is never inferred from career history; only explicitly recorded fixture links are used.
