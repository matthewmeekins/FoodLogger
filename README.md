# Food Logging System

Natural-language food logging app with OpenAI-powered calorie and macro estimation.

## What It Does

- Accepts plain text food descriptions via voice (Siri Shortcuts) or typing
- Uses OpenAI to directly estimate calories and macronutrients (protein, carbs, fat)
- Handles any food: home cooking, restaurant meals, packaged items, generic ingredients
- Provides component breakdowns for complex meals (shows reasoning)
- Automatically detects meal types (breakfast, lunch, dinner, snack) from time of day and context
- Logs everything immediately with full audit trail
- Stores original input text and complete OpenAI responses for transparency
- Today, Weekly, and Summary views with edit, delete, and re-log actions
- Favorites system: save common meals and quick-log them from the Log Food tab

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
- **GET /log/{entry_id}/details**
   - Returns plain-language summary of entry with original input and OpenAI response
- **POST /log/{entry_id}/add-to-today**
   - Clones any historical entry onto today's date

### Read/list/delete

- GET /log/today
- GET /log/summary
   - Optional query params: start_date, end_date (YYYY-MM-DD)
- GET /log/weekly
   - Optional query param: start_date (YYYY-MM-DD, defaults to 7 days ago)
- GET /log/date/{target_date}
- DELETE /log/{entry_id}

### Favorites

- **POST /favorites** — save a new favorite (name + list of nutrition items)
- **GET /favorites** — list all favorites with computed totals
- **DELETE /favorites/{id}** — delete a favorite
- **POST /favorites/{id}/log** — log all items from a favorite as today's entries

### Health and metrics

- GET /health
- GET /metrics

### Deprecated endpoints (return 410 Gone)

- POST /clarify - All entries now logged directly via OpenAI
- POST /manual-estimate - All entries now logged directly via OpenAI

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
- **Log Food tab:** text input + favorites section (search bar + quick-log cards)
- **Daily tab:** entries newest-first; Qty −/+ scaling, edit ✎, delete ✕, and favorite ★ per entry
- **Weekly tab:** 7-day bar chart and macro summary table; same entry controls as Daily
- **Summary tab:** calendar-based date range with macro totals
- Entry macro line shows Protein/Carbs/Fat
- Entry timestamps displayed in local-time format
- ★ button on any entry saves it as a favorite for quick re-logging

## Testing
## Remote Access

The app uses [Tailscale](https://tailscale.com) for private remote access from iPhone.

**Setup (5 minutes):**
1. Install Tailscale on Mac: `brew install tailscale && sudo tailscale up`
2. Install the Tailscale app on iPhone and sign in with the same account
3. Your Mac gets a persistent private IP (`100.x.x.x`) and a machine DNS name (e.g. `your-machine.your-tailnet.ts.net`)
4. Start the app bound to all interfaces: `uvicorn main:app --host 0.0.0.0 --port 8000`
5. Access from iPhone at `http://your-machine.your-tailnet.ts.net:8000`

**Siri Shortcut:** See `APPLE_SHORTCUT_GUIDE.md` for step-by-step instructions to create a voice-activated logging shortcut.

**Security:** Tailscale uses WireGuard encryption. Only devices in your tailnet can reach the server — no router config or public exposure needed.

## Testing

Regression tests are included in test_regressions.py.

Run:

```bash
.venv/bin/python -m unittest -v test_regressions.py
```

Current regression coverage:

- Today endpoint ordering (newest first)
- Quantity update recalculates calories and macros proportionally
- Add-to-today clones historical entries correctly
- Entry details endpoint returns plain-language lines
- Meal auto-detection from time of day
- System prompt contains explicit meal time rules
- Weekly endpoint returns 7-day structure
- Weekly endpoint computes totals and averages
- Summary endpoint includes macro totals
- Favorites create, list, and delete
- Log favorite creates today entries
- Favorites multi-item total computation
