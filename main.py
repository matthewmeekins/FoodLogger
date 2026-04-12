"""
FastAPI application for food logging system.
"""

import os
from datetime import date
from typing import Dict, Any
from fastapi import FastAPI, Request, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

import database
import llm
from models import ParsedEntry

# Load environment variables
load_dotenv()

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
    Accept plain text food entry, parse with LLM, and store in database.
    
    Returns a summary of what was logged.
    """
    # Get API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    
    # Read plain text body
    input_text = (await request.body()).decode("utf-8")
    
    if not input_text.strip():
        raise HTTPException(status_code=400, detail="Empty input")
    
    try:
        # Step 1: Save raw input immediately (never modified)
        raw_id = database.insert_raw_entry(input_text)
        
        # Step 2: Parse with LLM
        parsed_entry: ParsedEntry = llm.parse_food_entry(input_text, api_key)
        
        # Step 3: Save parsed entry
        parsed_json = parsed_entry.model_dump()
        parsed_id = database.insert_parsed_entry(
            raw_id=raw_id,
            parsed_json=parsed_json,
            confidence=parsed_entry.confidence
        )
        
        # Step 4: Expand and save individual food items
        resolved_ids = []
        for food in parsed_entry.foods:
            resolved_id = database.insert_resolved_entry(
                parsed_id=parsed_id,
                food_name=food.food_name,
                calories=food.calories,
                meal=food.meal,
                logged_date=parsed_entry.logged_date
            )
            resolved_ids.append(resolved_id)
        
        # Step 5: Return summary
        return {
            "status": "success",
            "raw_id": raw_id,
            "parsed_id": parsed_id,
            "confidence": parsed_entry.confidence,
            "logged_date": parsed_entry.logged_date,
            "foods_logged": len(parsed_entry.foods),
            "foods": [
                {
                    "food_name": food.food_name,
                    "calories": food.calories,
                    "meal": food.meal
                }
                for food in parsed_entry.foods
            ]
        }
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing entry: {str(e)}")


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


@app.get("/log/summary")
def get_summary() -> Dict[str, Any]:
    """
    Get total calories by date for the last 7 days.
    """
    summary = database.get_summary_last_n_days(7)
    
    return {
        "days": 7,
        "summary": summary
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


@app.get("/")
def root():
    """Serve the web UI."""
    return FileResponse("static/index.html")


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "Food Logging System"}
