# Food Log Project Summary

## Overview
A personal food logging system that uses natural language input and OpenAI GPT-4o to parse and structure food entries. Features a responsive web UI optimized for mobile use.

---

## Current State (April 7, 2026)

### What's Working
- ✅ FastAPI backend running on local network
- ✅ OpenAI integration for natural language parsing
- ✅ SQLite database with 3-table structure
- ✅ Responsive web UI (mobile-optimized)
- ✅ Calorie estimation for all foods
- ✅ Meal type inference (breakfast/lunch/dinner/snack)
- ✅ Delete functionality for entries
- ✅ Today's view with totals
- ✅ 7-day summary view

### Server Details
- **Running at**: http://0.0.0.0:8001 (accessible on local network)
- **Local access**: http://localhost:8001
- **Network access**: http://192.168.1.170:8001 (or 172.28.208.1:8001)
- **iPhone access**: Same network IP on port 8001

---

## Key Features Implemented

### 1. Natural Language Parsing
- Input: "had oatmeal with banana for breakfast"
- Output: Structured data with food names, calories, meal type
- Uses OpenAI GPT-4o API
- Cost: ~$0.001-$0.002 per entry (very cheap)

### 2. Smart Calorie Estimation
**LLM Prompt Changes:**
- Updated to ALWAYS provide calorie estimates (not null)
- Uses standard USDA nutritional data
- Adjusts based on quantity (e.g., "10 wings" vs "wings")
- Confidence levels: high/medium/low

### 3. Meal Type Inference
**Priority order:**
1. Explicit mentions: "for breakfast", "at dinner"
2. Time context: "this morning", "earlier today"
3. Current time (when provided):
   - 5 AM - 10:30 AM → breakfast
   - 10:30 AM - 2:30 PM → lunch
   - 2:30 PM - 8 PM → dinner
   - 8 PM - 5 AM → snack
4. Food type: chips, candy → snack
5. Otherwise: null (optional)

### 4. Delete Functionality
- Red "Delete" button on each entry in Today view
- Confirmation prompt before deletion
- Deletes from database permanently
- Auto-refreshes the view

### 5. Duplicate Handling
**Decision: Allow duplicates**
- No automatic duplicate detection
- User manually deletes wrong entries
- Simple and flexible approach

### 6. Responsive Web UI
**Features:**
- Tab navigation: Log Food | Today | Summary
- Mobile-first design with gradient background
- Meal badges (colored by meal type)
- Total calorie display
- Auto-refresh after logging

---

## Database Structure

### Tables

#### 1. `raw_entries`
- Stores original user input (never modified)
- Fields: id, timestamp, input_text

#### 2. `parsed_entries`
- Stores LLM output (JSON)
- Fields: id, raw_id, parsed_json, confidence, created_at

#### 3. `resolved_entries`
- Individual food items (one row per food)
- Fields: id, parsed_id, food_name, calories, meal, logged_date
- This is what the UI displays

---

## File Structure

```
food-log/
├── .env                    # OpenAI API key (not in git)
├── .env.example           # Template for .env
├── .gitignore
├── .venv/                 # Python virtual environment
├── database.py            # SQLite operations
├── llm.py                 # OpenAI integration
├── main.py                # FastAPI application
├── models.py              # Pydantic models
├── requirements.txt       # Python dependencies
├── food_log.db           # SQLite database (created on first run)
├── static/
│   └── index.html        # Web UI
└── README.md             # Original readme

Dependencies:
- fastapi
- uvicorn
- pydantic
- openai
- python-dotenv
```

---

## Important Code Changes Made

### 1. LLM System Prompt (llm.py)
- **Changed**: From conservative (use null if unsure) to proactive (always estimate)
- **Includes**: Current time context for meal inference
- **Format**: JSON with confidence, logged_date, foods array

### 2. FastAPI Endpoints (main.py)
**Added:**
- `POST /log` - Log food entry (simplified, no duplicate detection)
- `DELETE /log/{entry_id}` - Delete specific entry
- `GET /log/today` - Get today's entries with totals
- `GET /log/summary` - Get 7-day summary
- `GET /` - Serves web UI
- `GET /health` - Health check

**CORS enabled** for local network access

**Static files** mounted at /static

### 3. Database Functions (database.py)
**Added:**
- `delete_resolved_entry(entry_id)` - Delete by ID
- `get_recent_entries_by_meal()` - Query by meal type (unused now)
- `delete_entries_by_meal_and_date()` - Bulk delete (unused now)

### 4. Web UI (static/index.html)
**Features:**
- Three-tab interface
- Purple gradient theme
- Delete buttons with confirmation
- Enter key to submit
- Auto-switch to Today tab after logging
- Meal badges (colored by type)
- Empty states with icons
- Mobile-responsive (works on iPhone)

### 5. Models (models.py)
**Current state:**
- `FoodItem`: food_name (required), calories (optional), meal (optional)
- `ParsedEntry`: confidence, logged_date, foods[]

---

## Setup Instructions (For New Session)

### 1. Start Server
```powershell
.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

### 2. Access Web UI
- **Computer**: http://localhost:8001
- **iPhone**: http://192.168.1.170:8001 (same WiFi)

### 3. Environment Variables
- Requires `.env` file with `OPENAI_API_KEY=sk-proj-...`
- Copy from `.env.example` if needed

---

## Common Operations

### View Today's Entries
```powershell
Invoke-RestMethod -Uri http://localhost:8001/log/today
```

### Log Food via API
```powershell
Invoke-RestMethod -Uri http://localhost:8001/log -Method POST -Body "had pizza for dinner" -ContentType "text/plain"
```

### Delete Entry
```powershell
Invoke-WebRequest -Uri http://localhost:8001/log/5 -Method DELETE -UseBasicParsing
```

### Check Database Directly
```powershell
sqlite3 food_log.db "SELECT * FROM resolved_entries WHERE logged_date = '2026-04-07';"
```

---

## iPhone Usage

### Add to Home Screen (PWA-like)
1. Open Safari → http://192.168.1.170:8001
2. Tap Share button
3. "Add to Home Screen"
4. Name it "Food Log"
5. Opens like a native app

### Best Practices
- Type naturally: "had eggs and toast"
- Include meal if relevant: "for breakfast"
- Include quantities when specific: "10 wings"
- Review in Today tab
- Delete mistakes with red button

---

## Future Deployment (Option B)

### Cloud Deployment Options
1. **Railway** - Easiest, free tier, auto-deploys
2. **Render** - Free tier, GitHub integration
3. **Fly.io** - Free tier, good for APIs

### Steps
1. Push code to GitHub
2. Connect to deployment service
3. Add `OPENAI_API_KEY` environment variable
4. Access from anywhere via HTTPS

---

## Known Issues / Notes

### Current Limitations
- ❌ No user authentication (single user only)
- ❌ No edit functionality (delete + re-add)
- ❌ No data export (CSV/JSON)
- ❌ No historical date picker (only today + 7-day summary)
- ❌ No offline support (requires internet for OpenAI)

### Design Decisions
- **Allow duplicates**: User manages via delete buttons
- **Optional meal types**: LLM infers but allows null
- **Simple UI**: Three tabs, minimal complexity
- **Mobile-first**: Designed for iPhone usage
- **Local-first**: Runs on local network initially

---

## OpenAI Costs

### Pricing (GPT-4o)
- Input: $2.50/1M tokens
- Output: $10.00/1M tokens

### Estimated Usage
- ~150 input tokens per entry
- ~100 output tokens per entry
- **Cost: $0.001-$0.002 per entry**
- **Monthly (10 entries/day): ~$0.30-$0.60**

Very affordable for personal use!

---

## Troubleshooting

### Server won't start
```powershell
# Check if port 8001 is in use
netstat -ano | findstr :8001

# Kill process if needed
taskkill /PID <pid> /F

# Restart server
.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

### Can't access from iPhone
1. Verify both devices on same WiFi
2. Check Windows Firewall (allow port 8001)
3. Get correct IP: `ipconfig | Select-String "IPv4"`
4. Try alternate IP (172.28.208.1 if 192.168.1.170 fails)

### OpenAI errors
- Check `.env` file exists
- Verify API key is valid
- Check OpenAI account has credits
- Review terminal logs for error details

### Database issues
- Delete `food_log.db` to reset (loses all data)
- Server creates tables automatically on startup

---

## Recent Changes Log

### Session: April 7, 2026
1. ✅ Set up project, installed dependencies
2. ✅ Configured OpenAI API key
3. ✅ Updated LLM prompt to always provide calories
4. ✅ Added time-based meal inference
5. ✅ Built responsive web UI
6. ✅ Added CORS for network access
7. ✅ Implemented delete functionality
8. ✅ Tested duplicate detection → Decided to remove it
9. ✅ Simplified to manual deletion only
10. ✅ Made calories/meal optional in models
11. ✅ Tested on iPhone (working)

---

## Next Steps (If Continuing)

### Possible Enhancements
- [ ] Edit entry functionality
- [ ] Multiple snacks per day support
- [ ] Date picker for viewing past days
- [ ] CSV export for data portability
- [ ] Nutritional macros (protein/fat/carbs)
- [ ] Photos of meals
- [ ] Voice input on mobile
- [ ] Dark mode toggle
- [ ] User accounts / authentication
- [ ] Deploy to cloud (Railway/Render)

---

## Quick Reference

### Start Command
```powershell
.venv\Scripts\python.exe -m uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

### Web UI URL
http://192.168.1.170:8001

### API Endpoints
- POST /log - Log food
- GET /log/today - Today's entries
- GET /log/summary - 7-day summary
- DELETE /log/{id} - Delete entry
- GET /health - Health check

### Environment
- Python 3.x in .venv
- OpenAI API key in .env
- SQLite database: food_log.db
- Server: FastAPI + Uvicorn
- Port: 8001 (accessible on local network)
