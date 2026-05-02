"""
FastAPI application for food logging system.
"""

import os
import json
import time
from datetime import date
from typing import Dict, Any
from collections import deque
from fastapi import FastAPI, Request, HTTPException, Body
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

import database
import llm
from models import UpdateEntryRequest


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
            "confidence": "high",  # OpenAI estimates are always used
            "logged_date": nutrition_result["logged_date"],
            "intents": []  # No longer using structured intents
        }
        parsed_id = database.insert_parsed_entry(
            raw_id=raw_id,
            parsed_json=parsed_json,
            confidence="high"
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
                confidence_score=1.0,  # OpenAI estimation is trusted
                confidence_level="high",
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
