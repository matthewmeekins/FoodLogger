# Food Logging System

Natural-language food logging app with OpenAI-powered calorie and macro estimation.

## What It Does

- Accepts plain text food descriptions via voice (Siri Shortcuts) or typing
- Uses OpenAI to directly estimate calories and macronutrients (protein, carbs, fat)
- Handles any food: home cooking, restaurant meals, packaged items, generic ingredients
- Provides component breakdowns for complex meals (shows reasoning)
- Automatically detects meal types (breakfast, lunch, dinner, snack)
- Logs everything immediately with full audit trail
- Stores original input text and complete OpenAI responses for transparency
- Provides Today and Summary views with delete actions and entry timestamps

## Tech Stack

- FastAPI backend
- SQLite persistence  
- OpenAI (GPT-4o) for nutrition estimation and meal parsing
- Static HTML/CSS/JS frontend served by FastAPI
- Tailscale for remote access from iPhone

## Setup

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Create a .env file:

```env
OPENAI_API_KEY=your-openai-key

# Optional tuning
OPENAI_TIMEOUT_SECONDS=20
OPENAI_MAX_RETRIES=1
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

- **POST /log**
   - Input: plain text body (e.g., "I had a banana and coffee for breakfast")
   - Uses OpenAI to estimate calories and macros
   - Returns: `{"status": "success", "items": [...], "logged_date": "2026-05-01"}`
   - All items are logged immediately - no clarification needed

### Edit entries

- **PUT /log/{entry_id}**
   - Request body: JSON with optional fields: `food_name`, `calories`, `meal`, `logged_date`, `protein_g`, `carbs_g`, `fat_g`, `reasoning`
   - Returns: `{"status": "success", "message": "Entry updated", "edits_count": N}`
   - Tracks all edits in audit trail
- **GET /log/{entry_id}/edits**
   - Returns full edit history for an entry

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

### Log Zaxby's wings (restaurant food)

```bash
curl -X POST http://localhost:8000/log \
   -H "Content-Type: text/plain" \
   -d "20 chicken wings from Zaxby's"
```

### Fetch today entries

```bash
curl http://localhost:8000/log/today
```

## UI Notes

- Return/Enter submits main log input (Shift+Enter keeps newline)
- Processing, success, and error states are shown in status messages
- Today tab shows newest entries first
- Entry macro line shows Protein/Carbs/Fat with capped decimal formatting
- Entry timestamps displayed in local-time format
- Each entry shows OpenAI's component breakdown reasoning

## Testing

Regression tests are included in test_regressions.py.

Run:

```bash
python -m unittest -v test_regressions.py
```

Current regression coverage:

- OpenAI nutrition estimation
- Today ordering (newest first)
- Date-based summaries
