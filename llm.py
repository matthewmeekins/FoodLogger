"""
OpenAI API integration for parsing food entries.
"""

import os
import json
import time
from datetime import date, datetime
from openai import OpenAI
from models import ParsedEntry, StructuredIntent


SYSTEM_PROMPT = """You are a food logging assistant. Your job is to extract structured food data
from a user's natural language input and provide reasonable calorie estimates.

Return a JSON object with this structure:
{
  "confidence": "high" | "medium" | "low",
  "logged_date": "YYYY-MM-DD",
  "foods": [
    {
      "food_name": "string",
      "calories": integer,
      "meal": "breakfast" | "lunch" | "dinner" | "snack" | null
    }
  ]
}

Rules for meal assignment:
- If explicitly stated (e.g., "for breakfast", "at lunch"), use that
- If time context given (e.g., "this morning", "at noon"), infer from that
- If current time is provided and no context given, infer based on time:
  * 5 AM - 10:30 AM → breakfast
  * 10:30 AM - 2:30 PM → lunch  
  * 2:30 PM - 8 PM → dinner
  * 8 PM - 5 AM → snack
- If clearly a snack item (chips, candy, cookie) and no meal context → "snack"
- Otherwise, use null

Other Rules:
- Always provide calorie estimates based on standard portion sizes and nutritional data
- Use typical serving sizes unless quantities are specified (e.g., "2 eggs" = 140 cal, "1 egg" = 70 cal)
- Set confidence to "high" for common foods with clear portions
- Set confidence to "medium" for items where portion size is unclear
- Set confidence to "low" only if the food is very unusual or ambiguous
- logged_date should be today's date unless the user implies otherwise
- Be consistent with standard calorie databases (e.g., USDA data)

Examples:
- "oatmeal with banana for breakfast" → oatmeal (150 cal, breakfast), banana (105 cal, breakfast)
- "chicken sandwich" at 12 PM → ~450 cal, lunch
- "2 eggs and toast" with no context → eggs (140 cal, null), toast (80 cal, null)
- "had chips" at 3 PM → 150 cal, snack"""


STRUCTURED_SYSTEM_PROMPT = """You are a food logging assistant. Your job is to extract structured intent
from a user's natural language input for nutrition lookup.

Return a JSON object with this structure:
{
  "confidence": "high" | "medium" | "low",
  "logged_date": "YYYY-MM-DD",
  "intents": [
    {
      "brand": "string or null",
      "item": "string",
      "modifiers": ["list of strings"],
      "quantity": "string or null",
      "meal": "breakfast" | "lunch" | "dinner" | "snack" | null,
      "unknowns": ["list of unclear aspects"]
    }
  ]
}

Rules for parsing:
- brand: Extract if explicitly mentioned (e.g., "Kellogg's" in "Kellogg's cornflakes")
- item: The main food item (e.g., "cornflakes", "chicken breast")
- modifiers: Adjectives, preparations, or descriptors (e.g., ["grilled", "skinless"])
- quantity: Amount specified (e.g., "1 cup", "2 pieces", "100g")
- meal: As before, inferred from time or context
- unknowns: List any ambiguous or missing details that would help nutrition lookup (e.g., "type of milk", "cooking method")

Component splitting rules:
- Split compound meal descriptions into separate intents when they include distinct ingredients/add-ins.
- Use one intent per lookup-target food component.
- Keep preparation words on the relevant base food only.
- Include add-ins like butter, oil, sauces, dressings, salt/sugar when explicitly consumed.

Example decomposition:
- Input: "I had 1 pound of steamed broccoli with about 1 tbsp of salt and 3 tablespoons of butter"
  - Intent 1: item="broccoli", quantity="1 pound", modifiers=["steamed"], meal inferred
  - Intent 2: item="salt", quantity="1 tbsp", modifiers=[]
  - Intent 3: item="butter", quantity="3 tablespoons", modifiers=[]

Set confidence based on clarity of the input.
logged_date: Today's date unless specified otherwise.

Examples:
- "Kellogg's cornflakes with skim milk for breakfast" → brand: "Kellogg's", item: "cornflakes", modifiers: [], quantity: null, meal: "breakfast", unknowns: ["what quantity of milk?"]
- "grilled chicken breast 6oz" → brand: null, item: "chicken breast", modifiers: ["grilled"], quantity: "6oz", meal: null, unknowns: []
"""


CLARIFICATION_SYSTEM_PROMPT = """You are a helpful food logging assistant.
Write exactly one natural, concise clarification question to help identify accurate nutrition.

Rules:
- Ask only one question.
- Keep it under 20 words.
- Use clinical tone: neutral, direct, and specific.
- Avoid conversational fillers, empathy phrases, or casual language.
- Prefer missing portion size first, then key prep details, then brand/menu specificity.
- Do not mention confidence scores or internal system details.
- Return plain text only, no JSON and no extra commentary.
"""


OPENAI_TIMEOUT_SECONDS = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))
OPENAI_MAX_RETRIES = max(0, int(os.getenv("OPENAI_MAX_RETRIES", "1")))

LLM_USAGE = {
  "requests": 0,
  "retries": 0,
  "prompt_tokens": 0,
  "completion_tokens": 0,
  "total_tokens": 0,
}


def _record_usage(response) -> None:
  usage = getattr(response, "usage", None)
  if usage is None:
    return

  LLM_USAGE["requests"] += 1
  LLM_USAGE["prompt_tokens"] += int(getattr(usage, "prompt_tokens", 0) or 0)
  LLM_USAGE["completion_tokens"] += int(getattr(usage, "completion_tokens", 0) or 0)
  LLM_USAGE["total_tokens"] += int(getattr(usage, "total_tokens", 0) or 0)


def _create_client(api_key: str) -> OpenAI:
  return OpenAI(api_key=api_key, timeout=OPENAI_TIMEOUT_SECONDS, max_retries=0)


def _chat_completion_with_retry(*, client: OpenAI, model: str, messages: list[dict], response_format: dict | None = None, temperature: float | None = None, max_tokens: int | None = None):
  last_error = None

  for attempt in range(OPENAI_MAX_RETRIES + 1):
    try:
      kwargs = {
        "model": model,
        "messages": messages,
      }
      if response_format is not None:
        kwargs["response_format"] = response_format
      if temperature is not None:
        kwargs["temperature"] = temperature
      if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens

      response = client.chat.completions.create(**kwargs)
      _record_usage(response)
      return response
    except Exception as exc:
      last_error = exc
      if attempt < OPENAI_MAX_RETRIES:
        LLM_USAGE["retries"] += 1
        time.sleep(0.25 * (attempt + 1))

  raise last_error


def parse_food_entry(input_text: str, api_key: str) -> ParsedEntry:
    """
    Send input text to OpenAI and return validated ParsedEntry.
    Raises exception if API call fails or validation fails.
    """
    client = _create_client(api_key)
    
    # Get today's date and current time for context
    today = date.today().isoformat()
    now = datetime.now()
    current_time = now.strftime("%I:%M %p")  # e.g., "02:30 PM"
    
    # Prepare user message with date and time context
    user_message = f"Today's date is {today}.\nCurrent time is {current_time}.\n\nUser input: {input_text}"
    
    # Call OpenAI API
    response = _chat_completion_with_retry(
      client=client,
      model="gpt-4o",
      messages=[
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
      ],
      response_format={"type": "json_object"},
    )
    
    # Extract JSON from response
    content = response.choices[0].message.content
    parsed_json = json.loads(content)
    
    # Validate with Pydantic
    parsed_entry = ParsedEntry(**parsed_json)
    
    return parsed_entry


def parse_structured_intent(input_text: str, api_key: str) -> StructuredIntent:
    """
    Send input text to OpenAI and return validated StructuredIntent.
    Raises exception if API call fails or validation fails.
    """
    client = _create_client(api_key)
    
    # Get today's date and current time for context
    today = date.today().isoformat()
    now = datetime.now()
    current_time = now.strftime("%I:%M %p")  # e.g., "02:30 PM"
    
    # Prepare user message with date and time context
    user_message = f"Today's date is {today}.\nCurrent time is {current_time}.\n\nUser input: {input_text}"
    
    # Call OpenAI API
    response = _chat_completion_with_retry(
      client=client,
      model="gpt-4o",
      messages=[
        {"role": "system", "content": STRUCTURED_SYSTEM_PROMPT},
        {"role": "user", "content": user_message}
      ],
      response_format={"type": "json_object"},
    )
    
    # Extract JSON from response
    content = response.choices[0].message.content
    parsed_json = json.loads(content)
    
    # Validate with Pydantic
    structured_intent = StructuredIntent(**parsed_json)
    
    return structured_intent


def generate_clarification_question(
    *,
    api_key: str,
    original_input: str,
    item: str,
    brand: str | None,
    modifiers: list[str],
    quantity: str | None,
    candidate_name: str | None,
    candidate_source: str | None,
    fallback_question: str,
) -> str:
    """Generate a natural clarification question with OpenAI, fallback to rule-based text."""
    try:
        client = _create_client(api_key)

        user_prompt = (
            f"Original user input: {original_input}\n"
            f"Parsed item: {item}\n"
            f"Brand: {brand or 'unknown'}\n"
            f"Modifiers: {', '.join(modifiers) if modifiers else 'none'}\n"
            f"Quantity: {quantity or 'missing'}\n"
            f"Top candidate: {candidate_name or 'none'}\n"
            f"Candidate source: {candidate_source or 'none'}\n"
            f"Fallback question: {fallback_question}\n"
            "Write the best single clarification question now."
        )

        response = _chat_completion_with_retry(
          client=client,
          model="gpt-4o",
          messages=[
            {"role": "system", "content": CLARIFICATION_SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
          ],
          temperature=0.2,
          max_tokens=60,
        )

        content = (response.choices[0].message.content or "").strip()
        if content:
            return content
        return fallback_question
    except Exception:
        return fallback_question
