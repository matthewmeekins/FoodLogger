# Food Logging System

Natural-language food logging app with confidence-aware nutrition lookup, clarification loops, and a lightweight web UI.

## What It Does

- Parses free-text food input into structured intents (brand/item/modifiers/quantity/meal).
- Splits compound entries into component intents when needed (for example, broccoli + salt + butter).
- Looks up nutrition candidates via providers and scores confidence.
- Auto-logs high-confidence matches and asks targeted clarification questions for low-confidence matches.
- Falls back to manual calorie entry after max clarification rounds.
- Stores explainability trace data (raw input, parsed JSON, candidate list).
- Provides Today and Summary views with delete actions and entry timestamps.

## Tech Stack

- FastAPI backend
- SQLite persistence
- OpenAI for structured parsing and clarification question generation
- Static HTML/CSS/JS frontend served by FastAPI

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create a .env file:

```env
OPENAI_API_KEY=your-openai-key

# Optional tuning
USDA_API_KEY=your-usda-key
OPENAI_TIMEOUT_SECONDS=20
OPENAI_MAX_RETRIES=1
MAX_CLARIFICATION_ROUNDS=3
RATE_LIMIT_PER_MINUTE=40
```

3. Run the app:

```bash
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

4. Open the UI:

- http://localhost:8000/

## API Overview

### Core logging flow

- POST /log
   - Input: plain text body
   - Returns success with logged items, or needs_clarification with pending entries

- POST /clarify
   - Input JSON:

```json
{
   "pending_id": 123,
   "answer": "regular size"
}
```

   - Returns resolved, needs_clarification, or unresolved

- POST /manual-estimate
   - Input JSON:

```json
{
   "pending_id": 123,
   "calories": 450
}
```

### Read/list/delete

- GET /log/today
- GET /log/summary
   - Optional query params: start_date, end_date (YYYY-MM-DD)
- GET /log/date/{target_date}
- DELETE /log/{entry_id}

### Trace and ops

- GET /log/{entry_id}/trace
- GET /health
- GET /metrics

## Quick Curl Examples

### Log a food entry

```bash
curl -X POST http://localhost:8000/log \
   -H "Content-Type: text/plain" \
   -d "I had 1 pound of steamed broccoli with 1 tbsp salt and 3 tablespoons butter"
```

### Fetch today entries

```bash
curl http://localhost:8000/log/today
```

### Submit a clarification answer

```bash
curl -X POST http://localhost:8000/clarify \
   -H "Content-Type: application/json" \
   -d '{"pending_id": 45, "answer": "Jersey Mike\"s #13 regular"}'
```

### Save manual estimate

```bash
curl -X POST http://localhost:8000/manual-estimate \
   -H "Content-Type: application/json" \
   -d '{"pending_id": 45, "calories": 650}'
```

## UI Notes

- Return/Enter submits:
   - Main log input (Shift+Enter keeps newline)
   - Clarification answer
   - Manual calorie input
- Processing, success, and error states are shown in status messages.
- Today tab shows newest entries first.
- Entry macro line uses readable labels (Protein/Carbs/Fat) with capped decimal formatting.
- Entry timestamps are displayed in a subtle local-time format.

## Testing

Regression tests are included in test_regressions.py.

Run:

```bash
python -m unittest -v test_regressions.py
```

Current regression coverage:

- Component intent splitting
- Clarification drift guard
- Quantity scaling behavior
- Today ordering (newest first)
