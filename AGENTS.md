# AGENTS

## Purpose

This file is a fast restart guide for coding agents and future sessions without prior chat context.

## Project Identity

- Name: Food Log
- Stack: FastAPI, SQLite, OpenAI, static HTML/CSS/JS
- Main branch in use: feature/openai-pivot
- Current known-good checkpoint: phase-1-edit-entries

## Current Functional Baseline

- Natural-language food logging with direct OpenAI calorie estimation
- Component breakdowns with reasoning for complex meals (e.g., "wings, fries, and a coke")
- Automatic meal type detection (breakfast, lunch, dinner, snack)
- Immediate logging to resolved_entries (no clarification loops)
- **NEW: Entry editing** with audit trail (calories, name, macros, meal, date)
- Edit history tracking in entry_edits table
- Manual entry deletion if needed
- Today list sorted newest first
- Entry timestamps shown in UI
- Per-entry trace endpoint showing original input and OpenAI response
- Regression tests in test_regressions.py
- Remote access via Tailscale
- iPhone/Siri voice input via Apple Shortcuts

## First 10 Minutes Checklist

1. Verify environment and deps:
   - pip install -r requirements.txt
2. Confirm .env has at least OPENAI_API_KEY.
3. Start app:
   - python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
4. Run regression tests:
   - python -m unittest -v test_regressions.py
5. Quick endpoint smoke checks:
   - GET /health
   - GET /log/today

## Important Files

- main.py: request flow, OpenAI estimation via /log endpoint, PUT /log/{id} for editing
- llm.py: estimate_nutrition() function with OpenAI GPT-4o integration, prompts, retries, usage metrics
- database.py: schema, migrations, query helpers, indexes
  - reasoning and openai_response fields in resolved_entries
  - entry_edits table for audit trail
  - update_resolved_entry() and get_entry_edits() functions
- static/index.html: UI interaction, edit modal, meal dropdown selector
- test_regressions.py: key behavior protections
- PROJECT_SUMMARY.md: high-level project status
- README.md: setup and API usage
- ignored-docs/IMPLEMENTATION_PLAN.md: 6-phase improvement roadmap
- AGENTS.md (this file): fast restart guide for AI coding agents

## Recommended Working Rules

- Keep changes incremental and checkpoint often.
- Run regression tests after touching parse or estimation code.
- Preserve existing rollback tags; add new checkpoint tag before major changes.
- Avoid broad refactors in the same commit as behavior changes.
- Follow ignored-docs/IMPLEMENTATION_PLAN.md phase sequence (currently completed Phase 0 and Phase 1).

## Suggested Prompt To Resume Work

Use this prompt in a new chat:

Review AGENTS.md and PROJECT_SUMMARY.md. Then run regression tests and report project health. If healthy, continue with the highest-priority next task and create a small checkpoint after completion.

## Rollback Quick Commands

- List tags:
  - git tag --list
- Move to known-good checkpoint in detached state:
  - git checkout phase-1-edit-entries
- Create recovery branch from checkpoint:
  - git checkout -b recovery/phase1 phase-1-edit-entries
- Rollback to Phase 0:
  - git checkout phase-0-openai-estimation
