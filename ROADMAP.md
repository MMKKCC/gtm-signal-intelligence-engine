# Roadmap — GTM Signal Intelligence Engine

## MVP: Completed

- [x] FastAPI backend with SQLAlchemy ORM and SQLite
- [x] Account normalization and identity resolution via domain extraction
- [x] CSV data ingestion with flexible column mapping
- [x] ICP tier classification (1–4) with account status tracking
- [x] Account suppression rules (customer, open_opp, dnc)
- [x] Signal deduplication via MD5 hashing
- [x] Urgency scoring engine with configurable base scores and ICP multipliers
- [x] Signal decay engine with configurable shelf-life per signal type
- [x] Persona routing matrix with keyword-based override for exec_hire signals
- [x] Claude Haiku integration via tool use for structured outreach generation
- [x] Pydantic validation for LLM output (LinkedIn note, email hook, prep note, evidence)
- [x] LLM response caching with configurable TTL
- [x] Streamlit HITL UI with Data Loader, Dashboard, and Review Queue tabs
- [x] Approve / edit / reject workflow with structured rejection categories
- [x] CSV export of approved activations
- [x] YAML-based configuration for scoring, decay, routing, and prompts
- [x] 48+ unit and integration tests with mocked Anthropic client
- [x] Sample data for end-to-end demo

## Alpha Improvements (Completed)

- [x] Adapter pattern (`DataProviderInterface` ABC) for data source extensibility
- [x] Evidence tracking with `evidence_json` field and LLM evidence merge
- [x] LinkedIn note graceful truncation (297 chars + "..." instead of validation error)
- [x] Activation funnel visualization in dashboard
- [x] Signal framing hints in LLM prompts for business context
- [x] Queue metrics bar in Review Queue tab
- [x] REST API with pagination and filters

## Beta Ideas

- [ ] **Authentication and authorization** — API key or OAuth for the REST API; role-based access (viewer vs. editor)
- [ ] **PostgreSQL migration** — Replace SQLite for multi-user concurrent access; SQLAlchemy ORM makes this a config change
- [ ] **Async LLM generation** — Parallel API calls for batch generation instead of sequential processing
- [ ] **Signal trending** — Track signal velocity per account (multiple signals in short window = higher urgency)
- [ ] **Feedback-driven prompt tuning** — Use rejection categories (bad timing, wrong persona, hallucination) to improve prompt templates
- [ ] **Bulk review actions** — Select multiple activations and approve/reject in one action
- [ ] **Contact enrichment fallback** — When persona routing finds no match, suggest contacts to add
- [ ] **API rate limiting** — Protect against accidental CSV re-upload or generation spam
- [ ] **Logging and observability** — Structured logging with correlation IDs for pipeline tracing

## Production / V1 Ideas (Future)

- [ ] **Live data provider adapters** — Apollo, Clearbit, Bombora, 6sense webhooks replacing CSV upload
- [ ] **Bi-directional CRM sync** — Salesforce/HubSpot OAuth for pulling opportunity status and pushing approved activations as tasks
- [ ] **Website deanonymization** — Merge 1st-party IP-reveal data with 3rd-party scraped signals
- [ ] **ML lookalike models** — Surface "quiet" accounts with firmographic similarity to high-scoring active accounts
- [ ] **Browser extension** — Chrome extension surfacing the Review Queue inside Salesloft/Outreach/HubSpot
- [ ] **GDPR/CCPA compliance** — TTL hard-delete jobs for PII after configurable inactivity period
- [ ] **Multi-tenant architecture** — Separate data per team or organization
- [ ] **Webhook outbound** — Push approved activations to Slack, email, or sales engagement platforms
- [ ] **A/B testing framework** — Compare different prompt templates and measure approval rates
- [ ] **Signal source reliability scoring** — Weight signals differently based on source accuracy history

## Technical Debt

| Item | Impact | Effort |
|------|--------|--------|
| `datetime.utcnow()` is deprecated in Python 3.12+ — migrate to `datetime.now(UTC)` | Low | Low |
| No database migration tool (Alembic) — schema changes require manual recreation | Medium | Low |
| Sequential LLM API calls in batch generation | Medium | Medium |
| No structured logging — uses print/default logger | Low | Low |
| `evidence_json` stored as untyped JSON column — no schema validation at DB level | Low | Low |
| Streamlit session management could leak DB sessions on error | Low | Medium |

## Priority Order for Next Work

1. **PostgreSQL migration + Alembic** — Unblocks multi-user and deployment
2. **Authentication** — Required for any non-local deployment
3. **Async LLM generation** — Direct cost and latency improvement
4. **Structured logging** — Required for production debugging
5. **Feedback-driven prompt tuning** — Closes the human feedback loop
6. **Live data provider adapters** — Transitions from demo to real-world use
7. **CRM sync** — Connects output to existing sales workflows

