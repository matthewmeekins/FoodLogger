# Food Log Project Summary

## Snapshot

- Last updated: May 1, 2026
- Branch: feature/openai-pivot
- Phase: 0 (OpenAI-only estimation) - COMPLETED
- Latest checkpoint tag: phase-0-openai-estimation

## Project Overview

Food Log is a local-first FastAPI + SQLite app that uses OpenAI to estimate calories and macronutrients from natural language food descriptions.

**Major pivot completed (Phase 0):** Simplified from complex nutrition provider lookups to direct OpenAI estimation.

The system now supports:

- Direct OpenAI calorie and macro estimation for any food
- Component breakdowns with reasoning for complex meals
- Automatic meal type detection (breakfast, lunch, dinner, snack)
- Full audit trail (original input + complete OpenAI response)
- Today and Summary tabs with date range filtering and deletions
- Lightweight operational metrics and rate limiting
- Remote access via Tailscale from iPhone/Siri Shortcuts

## Current State

### Backend

- FastAPI service in main.py
- OpenAI integration in llm.py (GPT-4o for nutrition estimation)
- SQLite persistence in database.py
- **REMOVED:** Complex nutrition provider system (USDA, OpenFoodFacts, WebSearch)
- **REMOVED:** Clarification loop logic
- **REMOVED:** Confidence scoring and gating

### Frontend

- Single-page UI in static/index.html
- Tabs: Log Food, Today, Summary
- Enter key submit support in main input
- Status messages for processing and completion
- Entry timestamps shown in Today and date-detail lists
- Macros displayed with readable labels (Protein/Carbs/Fat)
- OpenAI reasoning/breakdown shown per entry

### Data Layer

Tables in active use:

- **raw_entries** - Original user input (audit trail)
- **parsed_entries** - Minimal compatibility record
- **resolved_entries** - Logged food items with macros
  - NEW: `reasoning` field - OpenAI's component breakdown
  - NEW: `openai_response` field - Complete OpenAI JSON response

Tables deprecated (not deleted, but no longer used):

- pending_entries - Previously for clarification flow
- candidates - Previously for nutrition provider results

Recent schema updates:

- Added `reasoning` TEXT field to resolved_entries
- Added `openai_response` TEXT field to resolved_entries
- Indexes retained for performance:
   - resolved_entries(logged_date, id desc)

## End-to-End Flow

1. User submits free text to POST /log (via UI, curl, or iPhone Siri Shortcut)
2. App saves original input to raw_entries
3. OpenAI estimates calories and macros with component breakdown
4. All items logged immediately to resolved_entries
5. User can view in Today/Summary tabs or delete if needed

**Simplified:** No clarification loops, no confidence scoring, no nutrition provider lookups.

## API Surface

Core:

- **POST /log** - Log food via natural language
- **GET /log/today** - Today's entries
- **GET /log/summary** - Multi-day summary
- **GET /log/date/{date}** - Specific date entries
- **DELETE /log/{id}** - Remove entry
- **GET /log/{id}/trace** - View audit trail

Deprecated (return 410 Gone):

- POST /clarify
- POST /manual-estimate

Observability:

- GET /metrics
- GET /health
- GET /

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
