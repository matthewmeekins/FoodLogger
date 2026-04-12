"""
OpenAI API integration for parsing food entries.
"""

import os
import json
from datetime import date, datetime
from openai import OpenAI
from models import ParsedEntry


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
