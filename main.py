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
        pending_summaries = []
        
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
                
                if confidence_level == "high":
                    # Save to resolved
                    resolved_id = database.insert_resolved_entry(
                        parsed_id=parsed_id,
                        food_name=top_candidate.name,
                        calories=int(top_candidate.calories) if top_candidate.calories else None,
                        meal=intent.meal,
                        logged_date=structured_intent.logged_date,
                        protein_g=top_candidate.protein_g,
                        carbs_g=top_candidate.carbs_g,
                        fat_g=top_candidate.fat_g,
                        confidence_score=confidence_score,
                        confidence_level=confidence_level,
                        source=top_candidate.source,
                        assumptions=assumptions,
                    )
                    resolved_ids.append(resolved_id)
                else:
                    # Generate question and save to pending
                    question = generate_question(intent, top_candidate)
                    pending_id = database.insert_pending_entry(
                        parsed_id=parsed_id,
                        intent_index=intent_index,
                        input_text=input_text,
                        food_name=top_candidate.name,
                        brand=intent.brand,
                        modifiers=intent.modifiers,
                        quantity=intent.quantity,
                        meal=intent.meal,
                        logged_date=structured_intent.logged_date,
                        confidence_score=confidence_score,
                        confidence_level=confidence_level,
                        source=top_candidate.source,
                        assumptions=assumptions,
                        question=question,
                    )
                    pending_summaries.append({
                        "pending_id": pending_id,
                        "food_name": top_candidate.name,
                        "question": question,
                        "confidence_level": confidence_level,
                    })
        
        # Step 5: Return appropriate response
        if pending_summaries:
            return {
                "status": "needs_clarification",
                "raw_id": raw_id,
                "parsed_id": parsed_id,
                "logged_date": structured_intent.logged_date,
                "resolved_count": len(resolved_ids),
                "pending_entries": pending_summaries,
            }
        else:
            return {
                "status": "success",
                "raw_id": raw_id,
                "parsed_id": parsed_id,
                "confidence": structured_intent.confidence,
                "logged_date": structured_intent.logged_date,
                "intents_parsed": len(structured_intent.intents),
                "foods_logged": len(resolved_ids),
                "intents": [],  # No pending, so empty
            }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")


@app.post("/clarify")
async def clarify_entry(request: Request) -> Dict[str, Any]:
    """
    Submit an answer to a clarification question and re-resolve the entry.
    
    Expects: {"pending_id": int, "answer": str}
    """
    # Get API key
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY not configured")
    
    # Read JSON body
    data = await request.json()
    pending_id = data.get("pending_id")
    answer = data.get("answer", "").strip()
    
    if not pending_id or not isinstance(pending_id, int):
        raise HTTPException(status_code=400, detail="pending_id must be an integer")
    if not answer:
        raise HTTPException(status_code=400, detail="answer cannot be empty")
    
    try:
        # Get pending entry
        pending = database.get_pending_entry(pending_id)
        if not pending:
            raise HTTPException(status_code=404, detail="Pending entry not found")
        
        # Re-process with answer: append answer to original input
        updated_input = f"{pending['input_text']} {answer}"
        
        # Re-parse structured intent
        structured_intent: StructuredIntent = llm.parse_structured_intent(updated_input, api_key)
        
        # For simplicity, assume single intent and take the first
        if not structured_intent.intents:
            raise HTTPException(status_code=400, detail="No intents found in updated input")
        
        intent = structured_intent.intents[0]  # Assume one for now
        
        # Re-lookup nutrition
        query_parts = [intent.item]
        if intent.modifiers:
            query_parts.extend(intent.modifiers)
        if intent.quantity:
            query_parts.append(intent.quantity)
        query = " ".join(query_parts)
        
        context = QueryContext(query=query, brand_hint=intent.brand)
        nutrition_service = NutritionService()
        candidates = nutrition_service.search(context, limit=5)
        
        if not candidates:
            raise HTTPException(status_code=400, detail="No nutrition candidates found")
        
        top_candidate = candidates[0]
        confidence_score = evaluate_confidence(intent, top_candidate, query)
        confidence_level = get_confidence_level(confidence_score)
        
        if confidence_level != "high":
            # Still not confident, return new question
            question = generate_question(intent, top_candidate)
            # Update pending entry with new question
            # For simplicity, just return needs_clarification again
            return {
                "status": "needs_clarification",
                "pending_id": pending_id,
                "question": question,
                "message": "Still need more clarification"
            }
        
        # Now confident, save to resolved
        assumptions = []
        if not intent.quantity:
            assumptions.append("Assumed standard serving size")
        if intent.modifiers:
            name_lower = (top_candidate.name or "").lower()
            for mod in intent.modifiers:
                if mod.lower() not in name_lower:
                    assumptions.append(f"Assumed {mod} preparation")
        
        resolved_id = database.insert_resolved_entry(
            parsed_id=pending['parsed_id'],
            food_name=top_candidate.name,
            calories=int(top_candidate.calories) if top_candidate.calories else None,
            meal=intent.meal,
            logged_date=pending['logged_date'],
            protein_g=top_candidate.protein_g,
            carbs_g=top_candidate.carbs_g,
            fat_g=top_candidate.fat_g,
            confidence_score=confidence_score,
            confidence_level=confidence_level,
            source=top_candidate.source,
            assumptions=assumptions,
        )
        
        # Delete pending
        database.delete_pending_entry(pending_id)
        
        # Persist new candidates
        scores = [nutrition_service._score_candidate(context, c) for c in candidates]
        database.insert_candidates(pending['parsed_id'], pending['intent_index'], candidates, scores)
        
        return {
            "status": "resolved",
            "resolved_id": resolved_id,
            "food_name": top_candidate.name,
            "calories": top_candidate.calories,
            "confidence_level": confidence_level,
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Clarification failed: {str(e)}")


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
