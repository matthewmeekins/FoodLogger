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
from models import ParsedEntry, StructuredIntent, IntentItem
from nutrition.service import NutritionService
from nutrition.models import QueryContext, NutritionCandidate


def evaluate_confidence(intent: IntentItem, candidate: NutritionCandidate, query: str) -> float:
    """Evaluate confidence score for a candidate based on multiple factors."""
    score = 0.0
    
    query_lower = query.lower()
    name_lower = (candidate.name or "").lower()
    
    # Match quality: substring match (more important)
    if query_lower in name_lower:
        score += 0.4
    elif any(word in name_lower for word in query_lower.split()):
        score += 0.2
    
    # Quantity certainty (more important)
    if intent.quantity:
        score += 0.3
    # else: 0
    
    # Modifier coverage
    if intent.modifiers:
        covered_modifiers = sum(1 for mod in intent.modifiers if mod.lower() in name_lower)
        score += 0.2 * (covered_modifiers / len(intent.modifiers))
    else:
        score += 0.2
    
    # Source quality
    score += 0.1 * candidate.source_confidence
    
    return min(score, 1.0)


def get_confidence_level(score: float) -> str:
    """Convert score to confidence level."""
    if score > 0.7:
        return "high"
    elif score > 0.4:
        return "medium"
    else:
        return "low"


def generate_question(intent: IntentItem, candidate: NutritionCandidate) -> str:
    """Generate a targeted follow-up question for clarification."""
    # Priority: quantity > modifiers > general
    if not intent.quantity:
        return f"How much {intent.item} did you eat?"
    
    if intent.modifiers:
        name_lower = (candidate.name or "").lower()
        uncovered = [mod for mod in intent.modifiers if mod.lower() not in name_lower]
        if uncovered:
            return f"How was the {intent.item} prepared? (e.g., {', '.join(uncovered)})"
    
    if intent.unknowns:
        return intent.unknowns[0]  # Use first unknown
    
    return f"Can you provide more details about the {intent.item}?"


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
    Accept plain text food entry, parse with LLM, lookup nutrition, and store in database.
    
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
        
        # Step 2: Parse structured intent with LLM
        structured_intent: StructuredIntent = llm.parse_structured_intent(input_text, api_key)
        
        # Step 3: Save parsed entry (store as JSON)
        parsed_json = structured_intent.model_dump()
        parsed_id = database.insert_parsed_entry(
            raw_id=raw_id,
            parsed_json=parsed_json,
            confidence=structured_intent.confidence
        )
        
        # Step 4: For each intent, lookup nutrition candidates
        nutrition_service = NutritionService()
        resolved_ids = []
        intent_summaries = []
        
        for intent_index, intent in enumerate(structured_intent.intents):
            # Build query from intent
            query_parts = [intent.item]
            if intent.modifiers:
                query_parts.extend(intent.modifiers)
            if intent.quantity:
                query_parts.append(intent.quantity)
            query = " ".join(query_parts)
            
            context = QueryContext(query=query, brand_hint=intent.brand)
            
            # Get candidates
            candidates = nutrition_service.search(context, limit=5)
            
            # Calculate scores (service already sorts by score)
            scores = [nutrition_service._score_candidate(context, c) for c in candidates]
            
            # Persist candidates
            database.insert_candidates(parsed_id, intent_index, candidates, scores)
            
            # Evaluate confidence for top candidate
            confidence_score = 0.0
            confidence_level = "low"
            question = None
            assumptions = []
            
            if candidates:
                top_candidate = candidates[0]
                confidence_score = evaluate_confidence(intent, top_candidate, query)
                confidence_level = get_confidence_level(confidence_score)
                
                # Generate assumptions
                if not intent.quantity:
                    assumptions.append("Assumed standard serving size")
                if intent.modifiers:
                    name_lower = (top_candidate.name or "").lower()
                    for mod in intent.modifiers:
                        if mod.lower() not in name_lower:
                            assumptions.append(f"Assumed {mod} preparation")
                
                # Generate question if not high confidence
                if confidence_level != "high":
                    question = generate_question(intent, top_candidate)
                
                # Always save for now (will change in Checkpoint 4)
                resolved_id = database.insert_resolved_entry(
                    parsed_id=parsed_id,
                    food_name=top_candidate.name,
                    calories=int(top_candidate.calories) if top_candidate.calories else None,
                    meal=intent.meal,
                    logged_date=structured_intent.logged_date,
                    protein_g=top_candidate.protein_g,
                    carbs_g=top_candidate.carbs_g,
                    fat_g=top_candidate.fat_g,
                    # Other nutrients from extra_nutrients if needed, but for now skip
                )
                resolved_ids.append(resolved_id)
            
            # Collect summary
            intent_summaries.append({
                "item": intent.item,
                "modifiers": intent.modifiers,
                "quantity": intent.quantity,
                "meal": intent.meal,
                "candidates_found": len(candidates),
                "confidence_score": confidence_score,
                "confidence_level": confidence_level,
                "question": question,
                "assumptions": assumptions
            })
        
        # Step 5: Return summary
        return {
            "status": "success",
            "raw_id": raw_id,
            "parsed_id": parsed_id,
            "confidence": structured_intent.confidence,
            "logged_date": structured_intent.logged_date,
            "intents_parsed": len(structured_intent.intents),
            "foods_logged": len(resolved_ids),
            "intents": intent_summaries
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


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
