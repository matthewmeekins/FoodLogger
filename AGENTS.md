# AGENTS

## Purpose

This file is a fast restart guide for coding agents and future sessions without prior chat context.

## Project Identity

- Name: Food Log
- Stack: FastAPI, SQLite, OpenAI, static HTML/CSS/JS
- Main branch in use: feature/nutrition-confidence-loop
- Current known-good checkpoint: checkpoint-2026-04-12-stability

## Current Functional Baseline

- Natural-language food logging with structured intent parsing
- Component splitting for compound entries
- Provider-based nutrition lookup with confidence gating
- Clarification loop for low-confidence intents
- Manual calorie fallback for unresolved items
- Today list sorted newest first
- Entry timestamps shown in UI
- Per-entry trace endpoint and trace panel in UI
- Regression tests in test_regressions.py

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

- main.py: request flow, confidence logic, clarify and manual flows, endpoints
- llm.py: prompts, retries, usage metrics
- database.py: schema, migrations, query helpers, indexes
- nutrition/service.py: provider ordering, gates, scoring
- static/index.html: UI interaction and status messaging
- test_regressions.py: key behavior protections
- PROJECT_SUMMARY.md: high-level project status
- README.md: setup and API usage

## Recommended Working Rules

- Keep changes incremental and checkpoint often.
- Run regression tests after touching parse, clarify, scaling, or ordering code.
- Preserve existing rollback tags; add new checkpoint tag before major UI or parser changes.
- Avoid broad refactors in the same commit as behavior changes.

## Suggested Prompt To Resume Work

Use this prompt in a new chat:

Review AGENTS.md and PROJECT_SUMMARY.md. Then run regression tests and report project health. If healthy, continue with the highest-priority next task and create a small checkpoint after completion.

## Rollback Quick Commands

- List tags:
  - git tag --list
- Move to known-good checkpoint in detached state:
  - git checkout checkpoint-2026-04-12-stability
- Create recovery branch from checkpoint:
  - git checkout -b recovery/stability checkpoint-2026-04-12-stability
