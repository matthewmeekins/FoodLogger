"""
OpenAI API integration for parsing food entries.
"""

import os
import json
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

Set confidence based on clarity of the input.
logged_date: Today's date unless specified otherwise.

Examples:
- "Kellogg's cornflakes with skim milk for breakfast" → brand: "Kellogg's", item: "cornflakes", modifiers: [], quantity: null, meal: "breakfast", unknowns: ["what quantity of milk?"]
- "grilled chicken breast 6oz" → brand: null, item: "chicken breast", modifiers: ["grilled"], quantity: "6oz", meal: null, unknowns: []
"""


def parse_food_entry(input_text: str, api_key: str) -> ParsedEntry:
    """
    Send input text to OpenAI and return validated ParsedEntry.
    Raises exception if API call fails or validation fails.
    """
    client = OpenAI(api_key=api_key)
    
    # Get today's date and current time for context
    today = date.today().isoformat()
    now = datetime.now()
    current_time = now.strftime("%I:%M %p")  # e.g., "02:30 PM"
    
    # Prepare user message with date and time context
    user_message = f"Today's date is {today}.\nCurrent time is {current_time}.\n\nUser input: {input_text}"
    
    # Call OpenAI API
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        response_format={"type": "json_object"}
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
    client = OpenAI(api_key=api_key)
    
    # Get today's date and current time for context
    today = date.today().isoformat()
    now = datetime.now()
    current_time = now.strftime("%I:%M %p")  # e.g., "02:30 PM"
    
    # Prepare user message with date and time context
    user_message = f"Today's date is {today}.\nCurrent time is {current_time}.\n\nUser input: {input_text}"
    
    # Call OpenAI API
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": STRUCTURED_SYSTEM_PROMPT},
            {"role": "user", "content": user_message}
        ],
        response_format={"type": "json_object"}
    )
    
    # Extract JSON from response
    content = response.choices[0].message.content
    parsed_json = json.loads(content)
    
    # Validate with Pydantic
    structured_intent = StructuredIntent(**parsed_json)
    
    return structured_intent
