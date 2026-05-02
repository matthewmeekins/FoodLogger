"""
FastAPI application for food logging system.
"""

import os
import json
import re
import time
from dataclasses import replace
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
from models import ParsedEntry, StructuredIntent, IntentItem, UpdateEntryRequest
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

    # Strong anchor bonus when candidate name semantically matches the core item.
    item_overlap = _text_overlap_ratio(intent.item, candidate.name)
    score += 0.2 * item_overlap
    
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


_NUMBER_WORDS = {
    "a": 1.0,
    "an": 1.0,
    "half": 0.5,
    "quarter": 0.25,
    "one": 1.0,
    "two": 2.0,
    "three": 3.0,
    "four": 4.0,
    "five": 5.0,
    "six": 6.0,
    "seven": 7.0,
    "eight": 8.0,
    "nine": 9.0,
    "ten": 10.0,
}


def _parse_amount(value: str) -> float | None:
    token = (value or "").strip().lower()
    if token in _NUMBER_WORDS:
        return _NUMBER_WORDS[token]
    try:
        return float(token)
    except ValueError:
        frac = re.match(r"^(\d+)\s*/\s*(\d+)$", token)
        if frac:
            num = float(frac.group(1))
            den = float(frac.group(2))
            if den != 0:
                return num / den
    return None


def _parse_amount_and_unit(text: str) -> tuple[float, str] | None:
    if not text:
        return None
    m = re.search(
        r"(?P<amount>\d+(?:\.\d+)?|\d+\s*/\s*\d+|a|an|half|quarter|one|two|three|four|five|six|seven|eight|nine|ten)"
        r"\s*(?P<unit>pounds?|lbs?|oz|ounces?|g|grams?|kg|ml|cups?|tbsp|tablespoons?|tsp|teaspoons?|servings?)",
        text.strip().lower(),
    )
    if not m:
        return None
    amount = _parse_amount(m.group("amount"))
    if amount is None:
        return None
    unit = m.group("unit")
    unit_map = {
        "pound": "lb", "pounds": "lb", "lb": "lb", "lbs": "lb",
        "ounce": "oz", "ounces": "oz", "oz": "oz",
        "gram": "g", "grams": "g", "g": "g",
        "kg": "kg",
        "cup": "cup", "cups": "cup",
        "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp",
        "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp",
        "ml": "ml",
        "serving": "serving", "servings": "serving",
    }
    return amount, unit_map.get(unit, unit)


def _to_grams(amount: float, unit: str) -> float | None:
    if unit == "g":
        return amount
    if unit == "kg":
        return amount * 1000.0
    if unit == "oz":
        return amount * 28.3495
    if unit == "lb":
        return amount * 453.592
    return None


def _apply_quantity_scale(intent: IntentItem, candidate: NutritionCandidate) -> tuple[NutritionCandidate, bool]:
    quantity = _parse_amount_and_unit(intent.quantity or "")
    if not quantity:
        return candidate, False
    qty_amount, qty_unit = quantity

    serving = _parse_amount_and_unit(candidate.serving or "")
    serving_grams = None
    if serving:
        serving_amount, serving_unit = serving
        serving_grams = _to_grams(serving_amount, serving_unit)

    quantity_grams = _to_grams(qty_amount, qty_unit)

    # Heuristic: if quantity is tbsp/tsp/serving and serving is weight, treat one serving as one such unit.
    if quantity_grams is None and serving_grams is not None:
        if qty_unit in {"tbsp", "tsp", "serving"}:
            quantity_grams = qty_amount * serving_grams

    if quantity_grams is None:
        return candidate, False

    baseline_grams = 100.0 if candidate.source == "usda" else serving_grams
    if not baseline_grams or baseline_grams <= 0:
        return candidate, False

    scale = quantity_grams / baseline_grams
    if scale <= 0:
        return candidate, False

    def _scale(v: float | None) -> float | None:
        return None if v is None else float(v) * scale

    return replace(
        candidate,
        calories=_scale(candidate.calories),
        protein_g=_scale(candidate.protein_g),
        carbs_g=_scale(candidate.carbs_g),
        fat_g=_scale(candidate.fat_g),
    ), True


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


def _split_component_chunks(text: str) -> list[str]:
    chunks = re.split(r"\s+(?:and|&)\s+|\s*,\s*", text)
    return [c.strip() for c in chunks if c.strip()]


def _parse_component_phrase(phrase: str) -> tuple[str, str | None] | None:
    p = (phrase or "").strip().lower()
    if not p:
        return None

    p = re.sub(r"^(with|about|approximately|approx\.?|plus)\s+", "", p).strip()
    p = re.sub(r"\s+", " ", p)

    cooking_words = {
        "steamed", "grilled", "baked", "fried", "roasted", "boiled", "raw", "sauteed", "sautéed"
    }
    if p in cooking_words:
        return None

    qty_match = re.match(
        r"^(?P<qty>(?:half|quarter|one|two|three|four|five|six|seven|eight|nine|ten|\d+(?:\.\d+)?)\s*"
        r"(?:tbsp|tablespoons?|tsp|teaspoons?|cups?|oz|ounces?|g|grams?|pounds?|lbs?|ml|slices?|pieces?|servings?))"
        r"\s*(?:of\s+)?(?P<item>[a-z][a-z\s\-']+)$",
        p,
    )
    if qty_match:
        item = qty_match.group("item").strip()
        quantity = qty_match.group("qty").strip()
        if item and item not in cooking_words:
            return item, quantity

    simple_match = re.match(r"^(?:of\s+)?(?P<item>[a-z][a-z\s\-']+)$", p)
    if simple_match:
        item = simple_match.group("item").strip()
        if item and item not in cooking_words and len(item.split()) <= 3:
            return item, None

    return None


def _normalize_primary_item(item_text: str) -> str:
    p = (item_text or "").strip().lower()
    if not p:
        return item_text

    p = re.sub(
        r"^(?:half|quarter|one|two|three|four|five|six|seven|eight|nine|ten|\d+(?:\.\d+)?)\s*"
        r"(?:pounds?|lbs?|oz|ounces?|g|grams?|kg|cups?|tbsp|tablespoons?|tsp|teaspoons?|ml|servings?)\s*(?:of\s+)?",
        "",
        p,
    ).strip()

    p = re.sub(r"^(?:steamed|grilled|baked|fried|roasted|boiled|raw|sauteed|sautéed)\s+", "", p).strip()

    return p or item_text


def _expand_component_intents(structured_intent: StructuredIntent) -> StructuredIntent:
    expanded: list[IntentItem] = []
    seen_keys: set[tuple[str, str | None, str | None]] = set()

    for intent in structured_intent.intents:
        base_item = intent.item or ""
        extra_component_phrases: list[str] = []

        # If parser leaves "with ..." inside item text, split it.
        if " with " in base_item.lower():
            parts = re.split(r"\s+with\s+", base_item, maxsplit=1, flags=re.IGNORECASE)
            if len(parts) == 2:
                base_item = parts[0].strip()
                extra_component_phrases.extend(_split_component_chunks(parts[1]))

        base_modifiers: list[str] = []
        component_intents: list[IntentItem] = []

        for mod in intent.modifiers:
            parsed = _parse_component_phrase(mod)
            if parsed:
                item_name, qty = parsed
                component_intents.append(
                    IntentItem(
                        brand=intent.brand,
                        item=item_name,
                        modifiers=[],
                        quantity=qty,
                        meal=intent.meal,
                        unknowns=[],
                    )
                )
            else:
                base_modifiers.append(mod)

        for phrase in extra_component_phrases:
            parsed = _parse_component_phrase(phrase)
            if parsed:
                item_name, qty = parsed
                component_intents.append(
                    IntentItem(
                        brand=intent.brand,
                        item=item_name,
                        modifiers=[],
                        quantity=qty,
                        meal=intent.meal,
                        unknowns=[],
                    )
                )

        primary = intent.model_copy(deep=True)
        primary.item = _normalize_primary_item(base_item.strip() or intent.item)
        primary.modifiers = base_modifiers

        primary_key = (primary.item.lower(), primary.quantity, primary.brand)
        if primary_key not in seen_keys:
            expanded.append(primary)
            seen_keys.add(primary_key)

        for comp in component_intents:
            if comp.item.lower() == primary.item.lower():
                continue
            key = (comp.item.lower(), comp.quantity, comp.brand)
            if key in seen_keys:
                continue
            expanded.append(comp)
            seen_keys.add(key)

    structured_intent.intents = expanded
    return structured_intent


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


def _safe_clarification_question(
    *,
    api_key: str,
    original_input: str,
    intent: IntentItem,
    candidate_name: str | None,
    candidate_source: str | None,
    fallback_question: str,
) -> str:
    question = llm.generate_clarification_question(
        api_key=api_key,
        original_input=original_input,
        item=intent.item,
        brand=intent.brand,
        modifiers=intent.modifiers,
        quantity=intent.quantity,
        candidate_name=candidate_name,
        candidate_source=candidate_source,
        fallback_question=fallback_question,
    )

    item_tokens = set(re.findall(r"[a-z0-9']+", (intent.item or "").lower()))
    question_tokens = set(re.findall(r"[a-z0-9']+", (question or "").lower()))
    if not question or not item_tokens.intersection(question_tokens):
        return fallback_question
    return question


# Load environment variables
load_dotenv()

MAX_CLARIFICATION_ROUNDS = max(1, int(os.getenv("MAX_CLARIFICATION_ROUNDS", "3")))
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
            resolved_id = database.insert_resolved_entry(
                parsed_id=parsed_id,
                food_name=item["name"],
                calories=item["calories"],
                meal=item.get("meal"),
                logged_date=nutrition_result["logged_date"],
                protein_g=item.get("protein_g"),
                carbs_g=item.get("carbs_g"),
                fat_g=item.get("fat_g"),
                confidence_score=1.0,  # OpenAI estimation is trusted
                confidence_level="high",
                source="openai",
                assumptions=[],
                reasoning=item.get("reasoning", ""),
                openai_response=openai_response_json,
            )
            resolved_ids.append(resolved_id)
            items_summary.append({
                "id": resolved_id,
                "name": item["name"],
                "calories": item["calories"],
                "protein_g": item.get("protein_g"),
                "carbs_g": item.get("carbs_g"),
                "fat_g": item.get("fat_g"),
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


@app.get("/log/{entry_id}/trace")
def get_entry_trace(entry_id: int) -> Dict[str, Any]:
    """Return prompt/response trace context for a resolved entry."""
    trace = database.get_entry_trace(entry_id)
    if not trace:
        raise HTTPException(status_code=404, detail="Entry trace not found")

    return {
        "entry_id": entry_id,
        "prompt_context": {
            "structured_system_prompt": llm.STRUCTURED_SYSTEM_PROMPT,
            "raw_input_text": trace.get("raw_input_text"),
            "raw_timestamp": trace.get("raw_timestamp"),
        },
        "response_context": {
            "parsed_confidence": trace.get("parsed_confidence"),
            "parsed_json": trace.get("parsed_json"),
            "candidates": trace.get("candidates", []),
        },
        "resolved_entry": {
            "food_name": trace.get("food_name"),
            "calories": trace.get("calories"),
            "meal": trace.get("meal"),
            "logged_date": trace.get("logged_date"),
            "source": trace.get("resolved_source"),
            "confidence_level": trace.get("confidence_level"),
        },
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
