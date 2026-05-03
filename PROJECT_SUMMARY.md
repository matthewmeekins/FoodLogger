# Food Log Project Summary

## Snapshot

- Last updated: May 2, 2026
- Branch: feature/nutrition-confidence-loop
- Phase: 4 (Favorites) - COMPLETED
- Latest checkpoint tag: phase-1-edit-entries (phases 2–4 committed, not individually tagged)

## Project Overview

Food Log is a local-first FastAPI + SQLite app that uses OpenAI to estimate calories and macronutrients from natural language food descriptions.

**Major pivot completed (Phase 0):** Simplified from complex nutrition provider lookups to direct OpenAI estimation.

The system now supports:

- Direct OpenAI calorie and macro estimation for any food
- Component breakdowns with reasoning for complex meals
- Automatic meal type detection (breakfast, lunch, dinner, snack) from time of day
- Full audit trail (original input + complete OpenAI response)
- Today, Weekly, and Summary tabs with date range filtering, editing, and deletions
- Favorites system: save common meals/items and quick-log them with one tap
- Lightweight operational metrics and rate limiting
- Remote access via Tailscale from iPhone/Siri Shortcuts

## Current State

### Backend

- FastAPI service in main.py
- OpenAI integration in llm.py (GPT-4o for nutrition estimation)
- SQLite persistence in database.py
- **REMOVED:** Complex nutrition provider system (USDA, OpenFoodFacts, WebSearch)
- **REMOVED:** Clarification loop logic
- **REMOVED:** Confidence scoring (confidence_score, confidence_level fields)

### Frontend

- Single-page UI in static/index.html
- Tabs: Log Food, Today, Weekly, Summary
- Log Food tab: text input + favorites quick-log section (search bar + cards)
- Today tab: entries grouped by meal, newest first; star button to save as favorite
- Weekly tab: 7-day bar chart and macro summary table
- Summary tab: date range selector with macro totals per day
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
  - `reasoning` field - OpenAI's component breakdown
  - `openai_response` field - Complete OpenAI JSON response
  - `quantity_value`, `quantity_unit`, `per_unit_*` fields for scaling
- **entry_edits** - Audit trail for entry modifications
  - Tracks field_name, old_value, new_value, edited_at
- **favorites** - Saved meals/items for quick re-logging
  - `name`, `items_json` (array of nutrition dicts), `created_at`

Tables deprecated (not deleted, but no longer used):

- None (pending_entries and candidates removed in Phase 0 cleanup)

Recent schema updates:

- Added `entry_edits` table for edit history tracking
- Maintained indexes for performance:
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
- **PUT /log/{id}** - Edit existing entry (calories, name, macros, meal, date)
- **GET /log/today** - Today's entries
- **GET /log/summary** - Multi-day summary with macro totals
- **GET /log/weekly** - 7-day summary with bar chart data, totals, averages
- **GET /log/date/{date}** - Specific date entries
- **DELETE /log/{id}** - Remove entry
- **GET /log/{id}/details** - Plain-language audit view with original input
- **GET /log/{id}/edits** - View edit history
- **POST /log/{id}/add-to-today** - Clone historical entry to today

Favorites:

- **POST /favorites** - Save a new favorite
- **GET /favorites** - List all favorites with totals
- **DELETE /favorites/{id}** - Delete a favorite
- **POST /favorites/{id}/log** - Log all favorite items as today's entries

Deprecated (return 410 Gone):

- POST /clarify
- POST /manual-estimate

Observability:

- GET /metrics
- GET /health
- GET /

## Configuration

Required:

- OPENAI_API_KEY

Optional:

- OPENAI_TIMEOUT_SECONDS
- OPENAI_MAX_RETRIES
- RATE_LIMIT_PER_MINUTE

## Testing and Quality

Regression test suite in test_regressions.py. 12 tests, all passing.

Coverage:

- Today endpoint ordering (newest first)
- Quantity update recalculates calories/macros proportionally
- Add-to-today clones historical entries
- Entry details endpoint returns plain-language lines
- Meal auto-detection from time of day
- System prompt contains explicit meal time rules
- Weekly endpoint returns 7-day structure
- Weekly endpoint computes totals and averages
- Summary endpoint includes macro totals
- Favorites create, list, delete
- Log favorite creates today entries
- Favorites multi-item total computation

Run:

- python -m unittest -v test_regressions.py

## Git Checkpoints

Available tags:

- phase-0-openai-estimation
- phase-1-edit-entries

Recent commits on feature/nutrition-confidence-loop:

- Phase 2: meal categorization and UI filters
- Phase 3: weekly summary with bar chart and macro tracking
- Phase 4: favorites system
- chore: remove confidence_score/confidence_level fields

## Known Gaps and Next Priorities

Current gaps:

- No auth or multi-user support
- No export/import workflow
- No background jobs for analytics
- Favorites not yet recognized in natural language input (deferred from Phase 4)

Recommended next priorities (see IMPLEMENTATION_PLAN.md Phase 5+):

1. Email digests (daily/weekly summary)
2. Natural language favorite recognition ("I had my naan pizza")
3. CSV/JSON export endpoint for portability

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
