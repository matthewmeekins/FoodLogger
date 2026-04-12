"""
Pydantic models for validation.
"""

from pydantic import BaseModel
from typing import Optional, List


class FoodItem(BaseModel):
    """Individual food item with calorie and meal info."""
    food_name: str
    calories: Optional[int] = None  # LLM should estimate, but make optional for flexibility
    meal: Optional[str] = None  # "breakfast", "lunch", "dinner", "snack" - optional
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    fiber_g: Optional[float] = None
    sugar_g: Optional[float] = None
    sodium_mg: Optional[float] = None
    potassium_mg: Optional[float] = None
    cholesterol_mg: Optional[float] = None
    saturated_fat_g: Optional[float] = None
    trans_fat_g: Optional[float] = None
    calcium_mg: Optional[float] = None
    iron_mg: Optional[float] = None
    vitamin_c_mg: Optional[float] = None
    vitamin_d_iu: Optional[float] = None


class ParsedEntry(BaseModel):
    """Structure returned by LLM after parsing raw input."""
    confidence: str  # "high", "medium", "low"
    logged_date: str  # YYYY-MM-DD inferred from context or today
    foods: List[FoodItem]
