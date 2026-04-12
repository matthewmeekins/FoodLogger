"""
FastAPI application for food logging system.
"""

import os
import json
import re
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


def _safe_json_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    if isinstance(value, str):
        try:
            decoded = json.loads(value)
            if isinstance(decoded, list):
                return [str(v) for v in decoded]
        except json.JSONDecodeError:
            return []
    return []


def _extract_quantity_from_text(text: str) -> str | None:
    """Best-effort quantity extraction from clarification answer text."""
    if not text:
        return None

    patterns = [
        r"\b(?:half|quarter|one|two|three|four|five|six|seven|eight|nine|ten|\d+(?:\.\d+)?)\s*(?:cup|cups|tbsp|tablespoon|tablespoons|tsp|teaspoon|teaspoons|oz|ounce|ounces|g|gram|grams|ml|slice|slices|bowl|bowls|piece|pieces|serving|servings|can|cans)\b",
        r"\b\d+(?:\.\d+)?\s*(?:oz|g|ml)\b",
    ]

    lowered = text.lower()
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return match.group(0).strip()

    return None


def _merge_modifiers(existing: list[str], answer: str) -> list[str]:
    """Merge concise modifier phrases from clarification answer."""
    merged = list(existing)
    if not answer:
        return merged

    candidates = []
    for part in re.split(r"[,;]", answer):
        phrase = part.strip().lower()
        if not phrase:
            continue
        if any(k in phrase for k in ["no ", "without ", "extra ", "with ", "homemade", "grilled", "fried", "baked", "skinless"]):
            candidates.append(phrase)

    for phrase in candidates:
        if phrase not in merged:
            merged.append(phrase)

    return merged


def _select_intent_for_pending(structured_intent: StructuredIntent, pending: Dict[str, Any]) -> IntentItem | None:
    """Pick the intent matching the pending row's intent index, with safe fallbacks."""
    intents = structured_intent.intents or []
    if not intents:
        return None

    idx = pending.get("intent_index")
    if isinstance(idx, int) and 0 <= idx < len(intents):
        return intents[idx]

    pending_name = (pending.get("food_name") or "").lower()
    for intent in intents:
        if intent.item and intent.item.lower() in pending_name:
            return intent

    return intents[0]


def _intent_matches_pending(intent: IntentItem, pending: Dict[str, Any]) -> bool:
    """Check whether selected intent is semantically aligned with the pending target item."""
    pending_name = (pending.get("food_name") or "").lower()
    item = (intent.item or "").lower()
    if not pending_name or not item:
        return False

    pending_tokens = set(re.findall(r"[a-z0-9']+", pending_name))
    item_tokens = set(re.findall(r"[a-z0-9']+", item))
    if not pending_tokens or not item_tokens:
        return False

    overlap = len(pending_tokens.intersection(item_tokens)) / max(1, len(item_tokens))
    return overlap >= 0.35 or item in pending_name or pending_name in item


def _text_overlap_ratio(left: str, right: str) -> float:
    left_tokens = set(re.findall(r"[a-z0-9']+", (left or "").lower()))
    right_tokens = set(re.findall(r"[a-z0-9']+", (right or "").lower()))
    if not left_tokens:
        return 0.0
    return len(left_tokens.intersection(right_tokens)) / len(left_tokens)


def _build_unresolved_response(pending_id: int, food_name: str, confidence_score: float) -> Dict[str, Any]:
    confidence_percent = int(round(max(0.0, min(confidence_score, 1.0)) * 100))
    return {
        "status": "unresolved",
        "pending_id": pending_id,
        "food_name": food_name,
        "confidence_score_percent": confidence_percent,
        "manual_required": True,
        "manual_prompt": "Confidence remained below auto-log threshold. Please estimate calories for this item.",
        "message": f"Max clarification rounds reached ({MAX_CLARIFICATION_ROUNDS}). Could not resolve this item automatically.",
    }


# Load environment variables
load_dotenv()

MAX_CLARIFICATION_ROUNDS = max(1, int(os.getenv("MAX_CLARIFICATION_ROUNDS", "3")))

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
                    fallback_question = generate_question(intent, top_candidate)
                    question = llm.generate_clarification_question(
                        api_key=api_key,
                        original_input=input_text,
                        item=intent.item,
                        brand=intent.brand,
                        modifiers=intent.modifiers,
                        quantity=intent.quantity,
                        candidate_name=top_candidate.name,
                        candidate_source=top_candidate.source,
                        fallback_question=fallback_question,
                    )
                    pending_id = database.insert_pending_entry(
                        parsed_id=parsed_id,
                        intent_index=intent_index,
                        input_text=input_text,
                        food_name=intent.item,
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
                        "food_name": intent.item,
                        "question": question,
                        "confidence_level": confidence_level,
                    })
            else:
                # No acceptable candidate found; force clarification instead of silent success.
                question = f"I could not find a confident match for '{intent.item}'. What portion size did you have?"
                pending_id = database.insert_pending_entry(
                    parsed_id=parsed_id,
                    intent_index=intent_index,
                    input_text=input_text,
                    food_name=intent.item,
                    brand=intent.brand,
                    modifiers=intent.modifiers,
                    quantity=intent.quantity,
                    meal=intent.meal,
                    logged_date=structured_intent.logged_date,
                    confidence_score=0.0,
                    confidence_level="low",
                    source=None,
                    assumptions=["Could not find a reliable nutrition source match"],
                    question=question,
                )
                pending_summaries.append({
                    "pending_id": pending_id,
                    "food_name": intent.item,
                    "question": question,
                    "confidence_level": "low",
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

        current_rounds = int(pending.get("clarification_rounds") or 0)
        next_round = current_rounds + 1
        database.update_pending_entry(pending_id, clarification_rounds=next_round)
        
        # Re-process with a targeted context for this pending intent only.
        context_parts = [pending.get("brand") or "", pending.get("food_name") or ""]
        context_parts.extend(_safe_json_list(pending.get("modifiers")))
        if pending.get("quantity"):
            context_parts.append(str(pending.get("quantity")))
        base_input = " ".join([p for p in context_parts if p]).strip()
        if not base_input:
            base_input = "food item"

        updated_input = f"{base_input}. Clarification: {answer}".strip()

        # Re-parse structured intent and select the specific pending intent by index.
        intent: IntentItem
        try:
            structured_intent: StructuredIntent = llm.parse_structured_intent(updated_input, api_key)
            selected = _select_intent_for_pending(structured_intent, pending)
            if not selected or not selected.item:
                raise ValueError("No valid targeted intent returned from parser")
            if not _intent_matches_pending(selected, pending):
                raise ValueError("Targeted intent drifted from pending item")
            intent = selected
        except Exception:
            fallback_item = (pending.get("food_name") or "food item").strip()
            intent = IntentItem(
                brand=pending.get("brand"),
                item=fallback_item,
                modifiers=_safe_json_list(pending.get("modifiers")),
                quantity=pending.get("quantity"),
                meal=pending.get("meal"),
                unknowns=[],
            )

        # Convergence enrichment: preserve known pending context and fill missing fields from answer.
        if not intent.brand and pending.get("brand"):
            intent.brand = pending.get("brand")
        if (not intent.quantity) and pending.get("quantity"):
            intent.quantity = pending.get("quantity")
        if not intent.quantity:
            extracted_quantity = _extract_quantity_from_text(answer)
            if extracted_quantity:
                intent.quantity = extracted_quantity

        merged_modifiers = _merge_modifiers(_safe_json_list(pending.get("modifiers")), answer)
        if intent.modifiers:
            merged_modifiers = _merge_modifiers(merged_modifiers, ", ".join(intent.modifiers))
        intent.modifiers = merged_modifiers
        if not intent.meal and pending.get("meal"):
            intent.meal = pending.get("meal")

        # Persist enriched pending context for subsequent clarification turns.
        database.update_pending_entry(
            pending_id,
            food_name=intent.item,
            brand=intent.brand,
            modifiers=intent.modifiers,
            quantity=intent.quantity,
            meal=intent.meal,
        )
        
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
            fallback_question = (
                f"What exact menu item name and portion size should be used for {intent.item}?"
                if (intent.brand or "") else f"What exact portion size did you consume for {intent.item}?"
            )
            question = llm.generate_clarification_question(
                api_key=api_key,
                original_input=updated_input,
                item=intent.item,
                brand=intent.brand,
                modifiers=intent.modifiers,
                quantity=intent.quantity,
                candidate_name=None,
                candidate_source=None,
                fallback_question=fallback_question,
            )
            database.update_pending_entry(
                pending_id,
                question=question,
                confidence_score=0.0,
                confidence_level="low",
                source=None,
            )
            if next_round >= MAX_CLARIFICATION_ROUNDS:
                return _build_unresolved_response(pending_id, intent.item, 0.0)
            return {
                "status": "needs_clarification",
                "pending_id": pending_id,
                "question": question,
                "message": "Still need more clarification"
            }
        
        top_candidate = candidates[0]
        semantic_overlap = _text_overlap_ratio(intent.item, top_candidate.name)
        if semantic_overlap < 0.25:
            fallback_question = f"Please confirm the exact item name for {intent.item} and provide the serving amount."
            question = llm.generate_clarification_question(
                api_key=api_key,
                original_input=updated_input,
                item=intent.item,
                brand=intent.brand,
                modifiers=intent.modifiers,
                quantity=intent.quantity,
                candidate_name=top_candidate.name,
                candidate_source=top_candidate.source,
                fallback_question=fallback_question,
            )
            database.update_pending_entry(
                pending_id,
                question=question,
                confidence_score=0.0,
                confidence_level="low",
                source=None,
            )
            if next_round >= MAX_CLARIFICATION_ROUNDS:
                return _build_unresolved_response(pending_id, intent.item, 0.0)
            return {
                "status": "needs_clarification",
                "pending_id": pending_id,
                "question": question,
                "message": "Still need more clarification"
            }

        confidence_score = evaluate_confidence(intent, top_candidate, query)
        confidence_level = get_confidence_level(confidence_score)
        
        if confidence_level != "high":
            # Still not confident, return new question
            fallback_question = generate_question(intent, top_candidate)
            question = llm.generate_clarification_question(
                api_key=api_key,
                original_input=updated_input,
                item=intent.item,
                brand=intent.brand,
                modifiers=intent.modifiers,
                quantity=intent.quantity,
                candidate_name=top_candidate.name,
                candidate_source=top_candidate.source,
                fallback_question=fallback_question,
            )
            database.update_pending_entry(
                pending_id,
                question=question,
                confidence_score=confidence_score,
                confidence_level=confidence_level,
                source=top_candidate.source,
            )
            if next_round >= MAX_CLARIFICATION_ROUNDS:
                return _build_unresolved_response(pending_id, intent.item, confidence_score)
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


@app.post("/manual-estimate")
async def manual_estimate(request: Request) -> Dict[str, Any]:
    """Finalize an unresolved pending entry using user-provided manual calories."""
    data = await request.json()
    pending_id = data.get("pending_id")
    calories = data.get("calories")

    if not pending_id or not isinstance(pending_id, int):
        raise HTTPException(status_code=400, detail="pending_id must be an integer")

    try:
        calories_value = int(calories)
    except (TypeError, ValueError):
        raise HTTPException(status_code=400, detail="calories must be a number")

    if calories_value <= 0:
        raise HTTPException(status_code=400, detail="calories must be greater than 0")

    pending = database.get_pending_entry(pending_id)
    if not pending:
        raise HTTPException(status_code=404, detail="Pending entry not found")

    resolved_id = database.insert_resolved_entry(
        parsed_id=pending["parsed_id"],
        food_name=pending.get("food_name") or "manual entry",
        calories=calories_value,
        meal=pending.get("meal"),
        logged_date=pending["logged_date"],
        confidence_score=0.0,
        confidence_level="manual",
        source="manual",
        assumptions=["Calories manually estimated by user after unresolved clarification"],
    )

    database.delete_pending_entry(pending_id)

    return {
        "status": "resolved_manual",
        "resolved_id": resolved_id,
        "food_name": pending.get("food_name"),
        "calories": calories_value,
        "message": "Manual calorie estimate saved.",
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
