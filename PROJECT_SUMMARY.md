# Food Log Project Summary

## Snapshot

- Last updated: April 28, 2026
- Branch: feature/nutrition-confidence-loop
- Commit: 4b2fd0c
- Latest checkpoint tag: checkpoint-2026-04-12-stability

## Project Overview

Food Log is a local-first FastAPI + SQLite app that turns natural language food journals into structured nutrition entries.

The system now supports:

- Multi-intent structured parsing
- Component splitting for compound entries
- Provider-based nutrition lookup with quality gates
- Confidence-based auto-log versus clarify workflow
- Manual calorie fallback after max clarify rounds
- Per-entry trace panel for explainability
- Today and Summary tabs with date range filtering and deletions
- Lightweight operational metrics and rate limiting

## Current State

### Backend

- FastAPI service in main.py
- OpenAI integration in llm.py
- Nutrition provider orchestration in nutrition/service.py
- SQLite persistence in database.py

### Frontend

- Single-page UI in static/index.html
- Tabs: Log Food, Today, Summary
- Enter key submit support in input, clarification, and manual estimate flows
- Status messages for processing and completion
- Subtle entry timestamps shown in Today and date-detail lists
- Macros displayed with readable labels and capped decimals

### Data Layer

Tables in active use:

- raw_entries
- parsed_entries
- resolved_entries
- pending_entries
- candidates

Recent schema and performance updates:

- resolved_entries.created_at timestamp support and backfill
- Indexes for hot query paths:
   - resolved_entries(logged_date, id desc)
   - pending_entries(parsed_id, id desc)
   - candidates(parsed_id, intent_index, score desc)

## End-to-End Flow

1. User submits free text to POST /log.
2. App parses structured intents via OpenAI.
3. Component expansion splits compound entries when needed.
4. Nutrition candidates are searched and scored.
5. High-confidence intents are inserted into resolved_entries.
6. Low-confidence intents are inserted into pending_entries with a targeted clarification question.
7. User answers via POST /clarify.
8. If still unresolved after max rounds, user can complete with POST /manual-estimate.

## API Surface

Core:

- POST /log
- POST /clarify
- POST /manual-estimate

Read and management:

- GET /log/today
- GET /log/summary
- GET /log/date/{target_date}
- DELETE /log/{entry_id}

Observability and health:

- GET /log/{entry_id}/trace
- GET /metrics
- GET /health
- GET /

## Configuration

Required:

- OPENAI_API_KEY

Optional:

- USDA_API_KEY
- OPENAI_TIMEOUT_SECONDS
- OPENAI_MAX_RETRIES
- MAX_CLARIFICATION_ROUNDS
- RATE_LIMIT_PER_MINUTE

## Testing and Quality

Regression test suite exists in test_regressions.py.

Current coverage:

- Component splitting into separate intents
- Clarification drift protection
- Quantity scaling behavior for USDA-style candidates
- Today endpoint ordering (newest first)

Run:

- python -m unittest -v test_regressions.py

## Git Checkpoints

Available tags:

- v0.1-baseline-before-nutrition
- v0.2-checkpoint-2
- v0.3-checkpoint-3
- v0.4-checkpoint-4
- v0.6-pre-cost-latency
- v0.6-checkpoint-cost-latency
- v0.7-pre-ui-work
- v0.8-pre-entry-trace
- checkpoint-2026-04-12-ui-flow
- checkpoint-2026-04-12-stability

## Known Gaps and Next Priorities

Current gaps:

- No auth or multi-user support
- No export/import workflow
- No background jobs for analytics
- No deployment automation documented in-repo

Recommended next priorities:

1. Add CSV or JSON export endpoint for portability.
2. Add basic auth or local passcode gate if used on shared networks.
3. Add smoke tests for clarify and manual-estimate flows against API responses.
4. Add deployment profile for Mac local development and optional cloud target.

## Quick Start Commands

Windows PowerShell:

- .venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

macOS terminal:

- source .venv/bin/activate
- python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000

## Handoff Notes

If starting without chat context, use AGENTS.md first. It contains:

- Current status
- Immediate verification commands
- Safe restart sequence
- Suggested first tasks
