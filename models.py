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


class IntentItem(BaseModel):
    """Structured intent for a single food item."""
    brand: Optional[str] = None
    item: str
    modifiers: List[str] = []
    quantity: Optional[str] = None
    meal: Optional[str] = None
    unknowns: List[str] = []


class StructuredIntent(BaseModel):
    """Structure returned by LLM for structured parsing."""
    confidence: str  # "high", "medium", "low"
    logged_date: str  # YYYY-MM-DD
    intents: List[IntentItem]


class ParsedEntry(BaseModel):
    """Structure returned by LLM after parsing raw input."""
    confidence: str  # "high", "medium", "low"
    logged_date: str  # YYYY-MM-DD inferred from context or today
    foods: List[FoodItem]


class UpdateEntryRequest(BaseModel):
    """Request to update a specific entry field."""
    food_name: Optional[str] = None
    calories: Optional[int] = None
    quantity_value: Optional[float] = None
    quantity_unit: Optional[str] = None
    meal: Optional[str] = None
    logged_date: Optional[str] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    reasoning: Optional[str] = None


class FavoriteItem(BaseModel):
    """A single item stored inside a favorite."""
    food_name: str
    calories: Optional[int] = None
    meal: Optional[str] = None
    protein_g: Optional[float] = None
    carbs_g: Optional[float] = None
    fat_g: Optional[float] = None
    reasoning: Optional[str] = None
    quantity_value: Optional[float] = 1.0
    quantity_unit: Optional[str] = None
    per_unit_calories: Optional[float] = None
    per_unit_protein_g: Optional[float] = None
    per_unit_carbs_g: Optional[float] = None
    per_unit_fat_g: Optional[float] = None


class FavoriteCreateRequest(BaseModel):
    """Request to create a new favorite."""
    name: str
    items: List[FavoriteItem]
