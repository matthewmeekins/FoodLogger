# Food Log Implementation Plan

## Project Pivot: OpenAI-Only Calorie Estimation

**Goal:** Simplify the system to use OpenAI for direct calorie and macro estimation, eliminating complex nutrition provider lookups and clarification loops.

**Status:** Phase 0 and Phase 1 completed, ready for Phase 2

---

## Configuration Answers

1. **Email:** Using Gmail for digests
2. **Push Notifications:** Will revisit platform selection in Phase 5
3. **Macros:** Important - include protein/carbs/fat in all phases
4. **Testing:** User will test in actual UI after each phase

---

## Phase 0: OpenAI-Only Estimation + Original Input Logging

**Status:** ✅ COMPLETED

**What changes:**
- Remove complex nutrition provider system (USDA, OpenFoodFacts, WebSearch)
- Single OpenAI call estimates calories + macros for any food
- Direct logging (no clarification loops, no pending_entries)
- Preserve original user input in raw_entries
- Add reasoning/breakdown field to show OpenAI's component analysis
- Keep trace data for transparency

**Database changes:**
- Remove: pending_entries usage, clarification flow
- Keep: raw_entries (audit trail with original input)
- Modify resolved_entries: Add `reasoning` TEXT field for OpenAI breakdown
- Keep: parsed_entries (for historical compatibility)

**Code changes:**
1. `llm.py`: New function `estimate_nutrition(input_text, api_key)` 
   - Returns: {food_items: [{name, calories, protein_g, carbs_g, fat_g, reasoning}], ...}
2. `main.py`: Simplify `/log` endpoint
   - Remove: nutrition provider orchestration
   - Remove: confidence scoring, clarification logic
   - Remove: pending_entries creation
   - Add: Direct OpenAI → resolved_entries flow
3. Remove: `/clarify` and `/manual-estimate` endpoints (no longer needed)
4. Keep: `/log/today`, `/log/summary`, `/log/{id}/trace`

**OpenAI Response Structure:**
```json
{
  "items": [
    {
      "name": "Naan Bread Pizza",
      "calories": 500,
      "protein_g": 20,
      "carbs_g": 50,
      "fat_g": 22,
      "meal": "lunch",
      "reasoning": "2oz pizza sauce (~30 cal), gluten-free naan (~220 cal), Mexican cheese (~110 cal), 14 pepperoni (~140 cal)"
    }
  ],
  "logged_date": "2026-05-01"
}
```

**Testing scenarios:**
- "I had a banana" → ~105 cal, macros
- "20 Zaxby's wings" → ~1800 cal with reasoning
- "Small pizza with 2oz sauce, naan, cheese, 14 pepperoni" → ~500 cal with component breakdown
- "Banana and coffee for breakfast" → 2 items, meal=breakfast

**Git commit:** `"feat: pivot to OpenAI-only calorie estimation with original input logging"`

**Git tag:** `phase-0-openai-estimation`

**Documentation updates:**
- README.md (remove clarification flow, update API endpoints)
- PROJECT_SUMMARY.md (update architecture, remove nutrition providers)
- AGENTS.md (update workflow)

**Estimated time:** 1-2 hours

**Rollback:** Previous stable point is `checkpoint-2026-04-12-stability`

---

## Phase 1: Edit Old Entries

**Status:** ✅ COMPLETED

**What it does:**
- Edit any logged entry's calories, name, macros, date, meal type
- Keep edit history (audit trail)

**Scope:**
1. New table: `entry_edits` (entry_id, field_name, old_value, new_value, edited_at)
2. New endpoint: `PUT /log/{entry_id}` (accepts partial updates)
3. UI: Add "Edit" button to each entry in Today/Summary views
4. UI: Modal form for editing fields

**Fields editable:**
- `calories`, `food_name`, `meal`, `logged_date`, `protein_g`, `carbs_g`, `fat_g`, `reasoning`

**Testing:**
- Edit banana from 105 → 89 calories
- Change meal from null → "breakfast"
- Verify edit history saved in entry_edits table
- View edit history in trace panel

**Git commit:** `"feat: enable editing of logged entries with audit trail"`

**Git tag:** `phase-1-edit-entries`

**Documentation updates:**
- README.md (new PUT endpoint)
- PROJECT_SUMMARY.md (new entry_edits table)

**Estimated time:** 45 minutes

---

## Phase 2: Meal/Snack Categorization Enhancement

**Status:** ✅ COMPLETED

**What it does:**
- Tag entries as breakfast/lunch/dinner/snack
- Auto-detect based on time of day and user input
- Manual override available
- UI filtering and grouping by meal

**Scope:**
1. `meal` field already exists in resolved_entries (keep it)
2. Enhance OpenAI estimation prompt to infer meal from context and time
3. UI: Meal filter dropdown in Today/Summary views
4. UI: Group entries by meal in display
5. UI: Visual meal indicators (icons/colors)

**Meal types:**
- breakfast, lunch, dinner, snack, (null/unspecified)

**Auto-detection logic:**
- Parse user input: "breakfast: banana" → meal=breakfast
- Use current time: 7am → breakfast, 12pm → lunch, 6pm → dinner, 3pm → snack
- User can always override

**Testing:**
- "Breakfast: banana" → meal=breakfast
- "I had a snack" → meal=snack
- Entry at 7am without meal in text → auto-tagged breakfast
- Entry at 3pm → auto-tagged snack
- Filter Today view by "breakfast" → see only breakfast items

**Git commit:** `"feat: enhanced meal categorization with auto-detection and UI filters"`

**Git tag:** `phase-2-meal-categorization`

**Documentation updates:**
- README.md (meal field usage, auto-detection rules)

**Estimated time:** 30 minutes

---

## Phase 3: Daily & Weekly Summary Views

**Status:** ✅ COMPLETED

**What it does:**
- Daily: Total calories, meal breakdown, macros summary
- Weekly: 7-day totals, averages, trends, macro tracking

**Scope:**
1. Enhance `GET /log/summary` with date range and grouping options
2. New endpoint: `GET /log/weekly?start_date=YYYY-MM-DD`
3. UI: New "Weekly" tab with chart/table
4. Show: Total cal, avg cal/day, protein/carbs/fat totals and averages, meal distribution

**Daily view enhancement:**
- Add macro totals (protein/carbs/fat grams)
- Add macro percentages
- Meal-by-meal breakdown

**Weekly view shows:**
- Bar chart: Calories per day (7 bars)
- Table: Each day's totals with macros
- Weekly totals and averages
- Macro breakdown (total grams and avg per day)
- Meal frequency (how many breakfasts/lunches/dinners/snacks)

**Testing:**
- Log entries across 7 days with various meals
- View daily summary → verify macro totals
- View weekly summary → verify 7-day calculations
- Check averages and trends

**Git commit:** `"feat: daily and weekly summary views with macro tracking"`

**Git tag:** `phase-3-summaries`

**Documentation updates:**
- README.md (new endpoints, query parameters)

**Estimated time:** 1 hour

---

## Phase 4: Favorites System

**Status:** ✅ COMPLETED

**What it does:**
- Save common meals with nicknames
- Quick log: "I had my usual breakfast" or "I had my naan pizza"
- Supports multi-item favorites with full macro tracking
- Can reference favorites by name in natural language

**Scope:**
1. New table: `favorites` (id, name, items_json, created_at)
2. `items_json`: Array of {food_name, calories, protein_g, carbs_g, fat_g, reasoning, quantity_value, quantity_unit, per_unit_*}
3. New endpoints:
   - `POST /favorites` (save new favorite)
   - `GET /favorites` (list all with computed totals)
   - `POST /favorites/{id}/log` (log all items from favorite as today's entries)
   - `DELETE /favorites/{id}` (delete favorite)
4. UI: Favorites section in Log Food tab (search bar + quick-log cards)
5. UI: ★ button on each Today entry to save as single-item favorite
6. UI: "Save meal" button on meal group headers to save all items as multi-item favorite

**Note:** Favorites are immutable after creation (create/delete only, no PUT). Natural language recognition of favorites was deferred.

**Example:**
- Save favorite: "My Naan Pizza" = sauce(30 cal) + naan(220 cal) + cheese(110 cal) + pepperoni(140 cal) = 500 cal total
- Log: "I had my naan pizza" → OpenAI recognizes favorite → logs all components
- Alternative: "Log favorite #3" → direct favorite logging

**Integration with OpenAI:**
- Include favorites list in context when estimating
- If user says "my [favorite name]", use favorite data instead of estimating
- Can still modify: "my naan pizza but extra cheese" → adjust macros

**Testing:**
- Save "Standard Breakfast" = banana (105 cal) + coffee (5 cal)
- Log via favorite button → both items logged with correct macros
- Delete favorite → verify removal
- View favorites list in UI with search filtering
- Save single entry as favorite with ★ button
- Save whole meal group as multi-item favorite

**Git commit:** `"feat: favorites system for quick re-logging common meals"`

**Git tag:** `phase-4-favorites`

**Documentation updates:**
- README.md (favorites endpoints and usage)
- PROJECT_SUMMARY.md (new favorites table)

**Estimated time:** 1.5 hours

---

## Phase 5: Email Digests

**Status:** ⏸️ Waiting

**What it does:**
- Daily/weekly summary via email
- Includes calories, macros, meal breakdown
- Optional scheduling via cron/launchd

**Scope:**

**Email Implementation:**
1. Use Python `smtplib` with Gmail SMTP
2. New module: `digest.py` with email templates
3. Endpoints: 
   - `POST /digest/send-daily` (trigger daily digest)
   - `POST /digest/send-weekly` (trigger weekly digest)
4. Config in .env:
   - `DIGEST_EMAIL` (recipient)
   - `GMAIL_USER` (sender)
   - `GMAIL_APP_PASSWORD` (app-specific password, not main password)
5. Email template: HTML with summary stats, macro breakdown

**Daily Digest Content:**
- Date
- Total calories
- Macro breakdown (protein/carbs/fat)
- Meal-by-meal list
- Top 3 highest calorie items

**Weekly Digest Content:**
- Date range
- Total calories for week
- Average calories per day
- Macro totals and averages
- Daily breakdown chart (ASCII or link to web view)
- Most logged foods

**Scheduling (Optional):**
- macOS: `launchd` plist for daily 8pm, weekly Sunday 8pm
- Triggers digest endpoints automatically
- Include setup script

**Testing:**
- Trigger daily digest manually → receive email
- Trigger weekly digest manually → receive email
- Verify email formatting and content accuracy
- Test with empty days (no entries)

**Push Notification Platform (Deferred):**
- Revisit options: Apple Push (via Shortcuts), Telegram Bot, Discord Webhook
- Decision needed before implementation

**Git commit:** `"feat: email digest for daily/weekly summaries"`

**Git tag:** `phase-5-digests`

**Documentation updates:**
- README.md (digest setup and endpoints)
- New file: DIGEST_SETUP.md (Gmail app password instructions)

**Estimated time:** 1 hour

---

## Summary Timeline

| Phase | Feature | Status | Time Estimate |
|-------|---------|--------|---------------|
| 0 | OpenAI estimation + original input | 🔄 In Progress | 1-2h |
| 1 | Edit entries | ⏸️ Waiting | 45m |
| 2 | Meal categorization | ⏸️ Waiting | 30m |
| 3 | Weekly summaries | ⏸️ Waiting | 1h |
| 4 | Favorites | ⏸️ Waiting | 1.5h |
| 5 | Email digests | ⏸️ Waiting | 1h |
| **Total** | | | **~6-7 hours** |

---

## Git Strategy

After each phase:
1. ✅ Complete implementation
2. ✅ User tests in UI
3. ✅ Run regression tests (update if needed)
4. ✅ Update documentation files
5. ✅ Git commit with descriptive message
6. ✅ Git tag: `phase-{N}-{feature-name}`
7. ⏸️ **Wait for user approval before next phase**

---

## Rollback Strategy

Each phase creates a git tag for easy rollback:
- `phase-0-openai-estimation`
- `phase-1-edit-entries`
- `phase-2-meal-categorization`
- `phase-3-summaries`
- `phase-4-favorites`
- `phase-5-digests`

**To rollback:** `git checkout phase-N-feature-name`

**Previous stable checkpoint:** `checkpoint-2026-04-12-stability`

---

## Current Branch

Working on: `feature/openai-pivot` (to be created)

Main branch will be updated only after full phase completion and user approval.

---

## Notes

- All phases include macro tracking (protein/carbs/fat)
- Testing performed by user in actual UI
- OpenAI response structure must support database schema
- Original user input always preserved in raw_entries
- Each phase is independently functional and testable

---

## Phase 0 Specific Requirements

**Critical:** Ensure OpenAI response structure maps cleanly to database schema:

**Database fields in resolved_entries:**
- `food_name` (TEXT)
- `calories` (INTEGER)
- `protein_g` (REAL)
- `carbs_g` (REAL)
- `fat_g` (REAL)
- `meal` (TEXT)
- `logged_date` (TEXT)
- `reasoning` (TEXT) ← NEW FIELD

**OpenAI must return per-item:**
- Clear food name
- Integer calories
- Macro values in grams (can be null if uncertain)
- Optional meal type
- Reasoning/breakdown text

**Validation:**
- Calories must be positive integer
- Macros must be non-negative or null
- Food name must be non-empty string
- Date must be valid ISO format

---

**Last Updated:** May 1, 2026  
**Current Phase:** 0 (Ready to start)  
**Next Checkpoint:** After Phase 0 completion
