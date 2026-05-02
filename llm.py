"""
OpenAI API integration for parsing food entries.
"""

import os
import json
import time
from datetime import datetime
from openai import OpenAI


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


def estimate_nutrition(input_text: str, api_key: str, current_time: datetime | None = None) -> dict:
    """
    Use OpenAI to directly estimate calories and macros from natural language input.
    Returns structured nutrition data ready for database logging.
    
    Returns:
    {
        "items": [
            {
                "name": str,
                "calories": int,
                "protein_g": float | None,
                "carbs_g": float | None,
                "fat_g": float | None,
                "meal": str | None,
                "reasoning": str  # Component breakdown explanation
            }
        ],
        "logged_date": str  # YYYY-MM-DD
    }
    """
    if current_time is None:
        current_time = datetime.now()
    
    today_date = current_time.date().isoformat()
    current_hour = current_time.hour
    
    client = _create_client(api_key)
    
    system_prompt = """You are a nutrition estimation assistant. Your job is to estimate calories and macronutrients for food items from natural language input.

Return a JSON object with this structure:
{
  "items": [
    {
      "name": "string",
      "calories": integer,
      "protein_g": float or null,
      "carbs_g": float or null,
      "fat_g": float or null,
      "meal": "breakfast" | "lunch" | "dinner" | "snack" | null,
      "reasoning": "string explaining the breakdown"
    }
  ],
  "logged_date": "YYYY-MM-DD"
}

Critical rules:
1. ALWAYS provide calorie estimates based on typical portions unless specific quantities given
2. Estimate macros (protein, carbs, fat in grams) when possible, use null if too uncertain
3. For compound items (e.g., "pizza with sauce, cheese, pepperoni"), provide component breakdown in reasoning
4. For restaurant/chain food, use typical menu item calories
5. Split multiple distinct foods into separate items
6. In reasoning, show your calculation (e.g., "2oz sauce ~30 cal, naan ~220 cal, cheese ~110 cal, 14 pepperoni ~140 cal = 500 cal total")

Meal assignment rules:
- Use user's explicit mention ("for breakfast", "at lunch")
- Missing explicit mention: Use time context if provided
- Use null if completely unclear

Examples:
1. "I had a banana" → name: "Banana", calories: 105, protein_g: 1.3, carbs_g: 27, fat_g: 0.4, reasoning: "Medium banana, standard USDA values"

2. "20 Zaxby's wings" → name: "Zaxby's Chicken Wings", calories: 1800, protein_g: 120, carbs_g: 20, fat_g: 140, reasoning: "Restaurant wings typically ~90 cal each, 20 pieces = 1800 cal. High fat from frying, moderate protein, minimal carbs from breading."

3. "Small pizza with 2oz sauce, gluten-free naan, mexican cheese, 14 pepperoni" → name: "Homemade Naan Pizza", calories: 500, protein_g: 25, carbs_g: 45, fat_g: 22, reasoning: "2oz pizza sauce (~30 cal, 1g protein, 7g carbs, 0g fat), gluten-free naan (~220 cal, 8g protein, 30g carbs, 6g fat), Mexican cheese blend ~1/4 cup (~110 cal, 8g protein, 1g carbs, 9g fat), 14 pepperoni slices (~140 cal, 8g protein, 1g carbs, 12g fat). Total: 500 cal, 25g protein, 39g carbs, 27g fat"

Be as accurate as possible. When in doubt, use standard nutritional database values (USDA, restaurant menus, food labels)."""

    user_prompt = f"""Current time: {current_time.strftime('%I:%M %p')} (hour: {current_hour})
Today's date: {today_date}

User input: {input_text}

Estimate the nutrition for all foods mentioned."""

    response = _chat_completion_with_retry(
        client=client,
        model="gpt-4o",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        response_format={"type": "json_object"},
        temperature=0.3,
    )
    
    _record_usage(response)
    
    content = response.choices[0].message.content
    if not content:
        raise ValueError("Empty response from OpenAI")
    
    result = json.loads(content)
    
    # Validate and clean the response
    if "items" not in result or not isinstance(result["items"], list):
        raise ValueError("Invalid response structure from OpenAI")
    
    # Ensure each item has required fields
    for item in result["items"]:
        if "name" not in item or "calories" not in item:
            raise ValueError(f"Missing required fields in item: {item}")
        
        # Ensure calories is an integer
        if not isinstance(item["calories"], int):
            item["calories"] = int(item["calories"])
        
        # Ensure reasoning exists
        if "reasoning" not in item:
            item["reasoning"] = f"Estimated {item['calories']} calories for {item['name']}"
    
    # Ensure logged_date exists
    if "logged_date" not in result:
        result["logged_date"] = today_date
    
    return result
