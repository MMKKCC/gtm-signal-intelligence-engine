# Project Summary — GTM Signal Intelligence Engine

## Executive Summary

The GTM Signal Intelligence Engine is a full-stack B2B demand generation platform that automates the workflow from raw buying signal detection to personalized, evidence-backed sales outreach. It combines configurable scoring engines, intelligent persona routing, and Claude AI-generated messaging with a human-in-the-loop review workflow — addressing the core RevOps problem of turning noisy market data into timely, relevant sales action.

The system is implemented as an MVP with complete end-to-end functionality: data ingestion, signal processing, AI outreach generation, and human review with export.

## Problem Statement

B2B sales and marketing teams face three compounding problems:

1. **Signal overload** — Buying signals (funding rounds, executive hires, technology installs, competitor reviews) arrive from multiple sources with no unified scoring or prioritization framework.
2. **Timing decay** — Signals lose relevance quickly. A funding round is most actionable within 90 days; a webcast attendance within 14 days. Most teams act on signals weeks or months too late.
3. **Generic outreach** — Even when signals are identified, outreach copy is generic. Reps lack the context to write evidence-backed messaging that references the specific signal and its business implications.

The result: low response rates, wasted pipeline, and sales teams that don't trust the data they're given.

## Solution Description

The engine solves these problems through three decoupled modules:

**Module 1: Account Intelligence Layer (The Spine)**
- Normalizes company identity through domain extraction (strips protocols, subdomains, paths)
- Maintains ICP tier classification (1-4) and account status tracking
- Enforces suppression rules: no signals processed for customers, open opportunities, or DNC accounts

**Module 2: Signal Detection & Timing Engine (The Heartbeat)**
- Deduplicates signals using MD5 hashing on (account_id + signal_type + date)
- Computes urgency scores: base_score x ICP_multiplier, capped at 100
- Calculates signal expiry dates based on configurable shelf-life per signal type
- Routes signals to buyer personas using a priority matrix with keyword-based overrides

**Module 3: Signal-Based Activation Generator (The Output)**
- Generates LinkedIn notes, email hooks, and SDR prep notes using Claude Haiku
- Enforces structured output via Anthropic tool use + Pydantic validation
- Caches LLM responses to prevent redundant API spend
- Presents results in a review queue with approve/edit/reject workflow and CSV export

## Target User

- RevOps teams managing signal-based outbound programs
- SDR/BDR managers who need prioritized, context-rich outreach queues
- Demand generation leaders connecting intent data to sales execution
- GTM engineers building automation between data providers and CRM systems


## Architecture Overview

- **Backend**: FastAPI with 10+ REST endpoints, async file upload handling
- **Database**: SQLite with 5 normalized tables (accounts, contacts, signals, activations, feedback_logs), all managed through SQLAlchemy ORM with UUID primary keys
- **Adapter Pattern**: `DataProviderInterface` ABC with `MockCSVProvider` implementation; designed for zero-change swapping to live API providers
- **Engine Layer**: Four independent engines (scoring, decay, dedup, persona router) with no cross-dependencies, all configurable via YAML
- **LLM Integration**: Anthropic SDK with tool use for structured output, Pydantic validation, and TTL-based caching
- **Frontend**: Streamlit with 3 tabs (Data Loader, Intelligence Dashboard, Review Queue)

## Key Technical Decisions

| Decision | Rationale |
|----------|-----------|
| SQLite over PostgreSQL | Faster local development, zero-config setup; ORM abstraction makes migration trivial |
| YAML configuration over database config | Operator-tunable without code changes; version-controllable scoring/routing rules |
| Tool use over prompt engineering for LLM output | Guarantees structured JSON output matching Pydantic schema; eliminates parsing failures |
| MD5 deduplication hash | Simple, deterministic, sufficient for the data volume; avoids complex fuzzy matching |
| Streamlit over React | Rapid UI development for HITL workflows; appropriate for internal tools and demos |
| Adapter pattern for data ingestion | Clean separation between data source and processing logic; enables Level 3 API integrations |
| UUID primary keys | Avoids ID collision across distributed systems; ready for eventual PostgreSQL migration |


## Architectural Advantages

- **Complete end-to-end pipeline** — Not a prototype of one piece; the full workflow works from data upload to CSV export
- **Configurable without code changes** — Scoring weights, decay periods, routing rules, and LLM prompts are all in YAML
- **Evidence-grounded AI** — LLM output is constrained to provided context via tool use; evidence tracking prevents hallucination
- **Structured rejection feedback** — Bad Timing / Wrong Persona / Bad AI categories create a feedback loop for prompt and routing tuning
- **48+ passing tests** — Comprehensive coverage of scoring, decay, dedup, persona routing, signal ingestion, and LLM generation with fully mocked Anthropic client
- **Clean architecture** — Three modules with clear boundaries; adapter pattern ready for extension

## Known Limitations

- SQLite limits concurrent access (single-writer)
- No live data provider integrations — CSV-only ingestion
- No CRM push — export is manual CSV download
- No authentication or authorization on API/UI
- Sequential LLM generation (no parallel API calls)
- No automated data retention or GDPR compliance

