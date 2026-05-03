"""
FastAPI application for food logging system.
"""

import os
import json
import time
from datetime import date, timedelta
from typing import Dict, Any
from collections import deque
from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

import database
import llm
from models import UpdateEntryRequest, FavoriteCreateRequest


# Load environment variables
load_dotenv()

RATE_LIMIT_PER_MINUTE = max(1, int(os.getenv("RATE_LIMIT_PER_MINUTE", "40")))

_RATE_WINDOW_SECONDS = 60
_REQUEST_HISTORY: dict[str, deque[float]] = {}


def _check_rate_limit(client_id: str) -> bool:
    now = time.time()
    window_start = now - _RATE_WINDOW_SECONDS

    history = _REQUEST_HISTORY.get(client_id)
    if history is None:
        history = deque()
        _REQUEST_HISTORY[client_id] = history

    while history and history[0] < window_start:
        history.popleft()

    if len(history) >= RATE_LIMIT_PER_MINUTE:
        return False

    history.append(now)
    return True


def _enforce_rate_limit(request: Request) -> None:
    client_host = request.client.host if request.client else "unknown"
    if not _check_rate_limit(client_host):
        raise HTTPException(status_code=429, detail="Rate limit exceeded. Please retry in a minute.")

# Initialize FastAPI app
app = FastAPI(title="Food Logging System")

# Enable CORS for local network access
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for local network
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Initialize database on startup
@app.on_event("startup")
def startup_event():
    database.init_db()


@app.post("/log")
async def log_food(request: Request) -> Dict[str, Any]:
    """
    Accept plain text food entry, estimate nutrition with OpenAI, and store in database.
    
    Returns a summary of what was logged.
    """
    # Get API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    
    # Read plain text body
    input_text = (await request.body()).decode("utf-8")

    _enforce_rate_limit(request)
    
    if not input_text.strip():
        raise HTTPException(status_code=400, detail="Empty input")
    
    try:
        # Step 1: Save raw input immediately (never modified)
        raw_id = database.insert_raw_entry(input_text)
        
        # Step 2: Use OpenAI to directly estimate nutrition
        from datetime import datetime
        nutrition_result = llm.estimate_nutrition(input_text, api_key, current_time=datetime.now())
        
        # Step 3: Save minimal parsed entry for compatibility
        parsed_json = {
            "logged_date": nutrition_result["logged_date"],
            "intents": []
        }
        parsed_id = database.insert_parsed_entry(
            raw_id=raw_id,
            parsed_json=parsed_json
        )
        
        # Step 4: Insert all estimated items into resolved_entries
        resolved_ids = []
        items_summary = []
        
        # Store the complete OpenAI response as JSON for audit trail
        openai_response_json = json.dumps(nutrition_result, indent=2)
        
        for item in nutrition_result["items"]:
            quantity_value = float(item.get("quantity_value") or 1.0)
            if quantity_value <= 0:
                quantity_value = 1.0
            quantity_unit = item.get("quantity_unit")

            calories = item["calories"]
            protein_g = item.get("protein_g")
            carbs_g = item.get("carbs_g")
            fat_g = item.get("fat_g")

            per_unit_calories = float(calories) / quantity_value
            per_unit_protein_g = (float(protein_g) / quantity_value) if protein_g is not None else None
            per_unit_carbs_g = (float(carbs_g) / quantity_value) if carbs_g is not None else None
            per_unit_fat_g = (float(fat_g) / quantity_value) if fat_g is not None else None

            resolved_id = database.insert_resolved_entry(
                parsed_id=parsed_id,
                food_name=item["name"],
                calories=calories,
                meal=item.get("meal"),
                logged_date=nutrition_result["logged_date"],
                protein_g=protein_g,
                carbs_g=carbs_g,
                fat_g=fat_g,
                source="openai",
                assumptions=[],
                reasoning=item.get("reasoning", ""),
                openai_response=openai_response_json,
                quantity_value=quantity_value,
                quantity_unit=quantity_unit,
                per_unit_calories=per_unit_calories,
                per_unit_protein_g=per_unit_protein_g,
                per_unit_carbs_g=per_unit_carbs_g,
                per_unit_fat_g=per_unit_fat_g,
            )
            resolved_ids.append(resolved_id)
            items_summary.append({
                "id": resolved_id,
                "name": item["name"],
                "calories": calories,
                "quantity_value": quantity_value,
                "quantity_unit": quantity_unit,
                "protein_g": protein_g,
                "carbs_g": carbs_g,
                "fat_g": fat_g,
                "meal": item.get("meal"),
            })
        
        # Step 5: Return success response
        return {
            "status": "success",
            "raw_id": raw_id,
            "parsed_id": parsed_id,
            "logged_date": nutrition_result["logged_date"],
            "items_logged": len(resolved_ids),
            "items": items_summary,
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.post("/clarify")
async def clarify_entry(request: Request) -> Dict[str, Any]:
    """DEPRECATED: Clarification flow removed in Phase 0 (OpenAI-only estimation)."""
    raise HTTPException(
        status_code=410,
        detail="Clarification endpoint deprecated. All entries are now logged directly via OpenAI estimation."
    )


@app.get("/log/today")
def get_today_entries() -> Dict[str, Any]:
    """
    Get all resolved entries for today's date.
    """
    today = date.today().isoformat()
    entries = database.get_entries_for_date(today)
    
    total_calories = sum(entry.get("calories") or 0 for entry in entries)
    
    return {
        "date": today,
        "entries": entries,
        "total_calories": total_calories,
        "entry_count": len(entries)
    }


@app.post("/manual-estimate")
async def manual_estimate(request: Request) -> Dict[str, Any]:
    """DEPRECATED: Manual estimate endpoint removed in Phase 0 (OpenAI-only estimation)."""
    raise HTTPException(
        status_code=410,
        detail="Manual estimate endpoint deprecated. All entries are now logged directly via OpenAI estimation."
    )


@app.get("/log/summary")
def get_summary(start_date: str | None = None, end_date: str | None = None, days: int = 7) -> Dict[str, Any]:
    """
    Get total calories by date.
    - If start_date and end_date are provided, use inclusive range.
    - Otherwise fallback to last N days.
    """
    if start_date and end_date:
        summary = database.get_summary_by_date_range(start_date, end_date)
        return {
            "start_date": start_date,
            "end_date": end_date,
            "summary": summary,
        }

    summary = database.get_summary_last_n_days(days)
    return {
        "days": days,
        "summary": summary,
    }


@app.get("/log/weekly")
def get_weekly(start_date: str | None = None) -> Dict[str, Any]:
    """
    Get a 7-day weekly summary starting from start_date (YYYY-MM-DD).
    Defaults to the most recent Monday if start_date is not provided.
    Returns per-day stats, weekly totals/averages, and meal frequency.
    """
    if start_date is None:
        today = date.today()
        # Most recent Monday (weekday 0 = Monday)
        start_date = (today - timedelta(days=today.weekday())).isoformat()

    return database.get_weekly_summary(start_date)


@app.get("/log/date/{target_date}")
def get_entries_for_specific_date(target_date: str) -> Dict[str, Any]:
    """Get all resolved entries for a specific date (YYYY-MM-DD)."""
    entries = database.get_entries_for_date(target_date)
    total_calories = sum(entry.get("calories") or 0 for entry in entries)

    return {
        "date": target_date,
        "entries": entries,
        "total_calories": total_calories,
        "entry_count": len(entries),
    }


@app.delete("/log/{entry_id}")
def delete_entry(entry_id: int) -> Dict[str, Any]:
    """
    Delete a food entry by ID.
    """
    deleted = database.delete_resolved_entry(entry_id)
    
    if not deleted:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    return {"status": "success", "message": "Entry deleted"}


@app.post("/log/{entry_id}/add-to-today")
def add_entry_to_today(entry_id: int) -> Dict[str, Any]:
    """Clone an existing entry into today's log."""
    new_entry_id = database.add_entry_to_today(entry_id)
    if new_entry_id is None:
        raise HTTPException(status_code=404, detail="Entry not found")

    return {
        "status": "success",
        "message": "Entry added to today",
        "entry_id": new_entry_id,
    }


@app.put("/log/{entry_id}")
def update_entry(entry_id: int, update_data: UpdateEntryRequest = Body(...)) -> Dict[str, Any]:
    """
    Update a food entry with edit history tracking.
    Only provided fields will be updated.
    """
    updated = database.update_resolved_entry(
        entry_id,
        food_name=update_data.food_name,
        calories=update_data.calories,
        quantity_value=update_data.quantity_value,
        quantity_unit=update_data.quantity_unit,
        meal=update_data.meal,
        logged_date=update_data.logged_date,
        protein_g=update_data.protein_g,
        carbs_g=update_data.carbs_g,
        fat_g=update_data.fat_g,
        reasoning=update_data.reasoning,
    )
    
    if not updated:
        raise HTTPException(status_code=404, detail="Entry not found")
    
    # Get edit history
    edits = database.get_entry_edits(entry_id)
    
    return {
        "status": "success",
        "message": "Entry updated",
        "entry_id": entry_id,
        "edits_count": len(edits),
    }


@app.get("/log/{entry_id}/edits")
def get_entry_edit_history(entry_id: int) -> Dict[str, Any]:
    """Return edit history for an entry."""
    edits = database.get_entry_edits(entry_id)
    
    return {
        "entry_id": entry_id,
        "edits": edits,
        "edit_count": len(edits),
    }


@app.get("/log/{entry_id}/details")
def get_entry_details(entry_id: int) -> Dict[str, Any]:
    """Return plain-language ready details for an entry disclosure panel."""
    details = database.get_entry_details(entry_id)
    if not details:
        raise HTTPException(status_code=404, detail="Entry not found")

    quantity_value = details.get("quantity_value") or 1
    quantity_unit = details.get("quantity_unit")
    quantity_text = f"{quantity_value:g}" if isinstance(quantity_value, (int, float)) else str(quantity_value)
    if quantity_unit:
        quantity_text = f"{quantity_text} {quantity_unit}"

    macro_parts = []
    if details.get("protein_g") is not None:
        macro_parts.append(f"protein {float(details['protein_g']):.1f}g")
    if details.get("carbs_g") is not None:
        macro_parts.append(f"carbs {float(details['carbs_g']):.1f}g")
    if details.get("fat_g") is not None:
        macro_parts.append(f"fat {float(details['fat_g']):.1f}g")
    macros_text = ", ".join(macro_parts) if macro_parts else "macros unavailable"

    assumptions = details.get("assumptions") or []

    lines: list[str] = []
    lines.append(f"This entry is for {details.get('food_name', 'Unknown item')}.")
    if details.get("calories") is not None:
        lines.append(f"Estimated calories: {details['calories']} cal for quantity {quantity_text}.")
    else:
        lines.append(f"Quantity recorded: {quantity_text}.")

    if details.get("meal"):
        lines.append(f"Meal tag: {details['meal']}.")
    lines.append(f"Logged date: {details.get('logged_date')}.")
    if details.get("created_at"):
        lines.append(f"Entry created at: {details['created_at']}.")
    lines.append(f"Macro estimate: {macros_text}.")

    if details.get("source"):
        lines.append(f"Source: {details['source']}.")

    if details.get("reasoning"):
        lines.append(f"How this was estimated: {details['reasoning']}")

    if assumptions:
        lines.append("Assumptions used:")
        lines.extend([f"- {assumption}" for assumption in assumptions])

    if details.get("original_input"):
        lines.append(f"Original journal input: {details['original_input']}")
    if details.get("original_input_timestamp"):
        lines.append(f"Original input timestamp: {details['original_input_timestamp']}.")

    return {
        "entry_id": entry_id,
        "title": "Entry details",
        "lines": lines,
    }


# ---------------------------------------------------------------------------
# Favorites endpoints
# ---------------------------------------------------------------------------

@app.post("/favorites")
def create_favorite(body: FavoriteCreateRequest) -> Dict[str, Any]:
    """Save a new favorite (single item or multi-item meal)."""
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="name is required")
    items = [item.model_dump() for item in body.items]
    fav_id = database.insert_favorite(name, items)
    return {"status": "success", "id": fav_id, "name": name, "item_count": len(items)}


@app.get("/favorites")
def list_favorites() -> Dict[str, Any]:
    """List all saved favorites with computed totals."""
    favorites = database.get_favorites()
    return {"favorites": favorites}


@app.delete("/favorites/{fav_id}")
def remove_favorite(fav_id: int) -> Dict[str, Any]:
    """Delete a favorite by id."""
    deleted = database.delete_favorite(fav_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {"status": "success", "message": "Favorite deleted"}


@app.post("/favorites/{fav_id}/log")
def log_favorite(fav_id: int) -> Dict[str, Any]:
    """Log all items from a favorite as new entries for today."""
    new_ids = database.log_favorite(fav_id)
    if not new_ids:
        raise HTTPException(status_code=404, detail="Favorite not found")
    return {
        "status": "success",
        "message": f"Logged {len(new_ids)} item(s) from favorite",
        "entry_ids": new_ids,
        "items_logged": len(new_ids),
    }


@app.get("/")
def root():
    """Serve the web UI."""
    return FileResponse("static/index.html")


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "Food Logging System"}


@app.get("/metrics")
def metrics() -> Dict[str, Any]:
    """Lightweight operational metrics for checkpoint 6 cost/latency controls."""
    active_clients = len(_REQUEST_HISTORY)
    return {
        "rate_limit_per_minute": RATE_LIMIT_PER_MINUTE,
        "tracked_clients": active_clients,
        "llm_usage": llm.LLM_USAGE,
    }
