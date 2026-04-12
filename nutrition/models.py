from dataclasses import dataclass, field
from typing import Optional, Dict, Any


@dataclass
class NutritionCandidate:
    """Normalized nutrition candidate from any upstream provider."""

    name: str
    brand: Optional[str]
    serving: Optional[str]
    calories: Optional[float]
    protein_g: Optional[float]
    carbs_g: Optional[float]
    fat_g: Optional[float]
    source: str
    source_url: Optional[str]
    source_confidence: float
    provider_item_id: Optional[str] = None
    extra_nutrients: Dict[str, Any] = field(default_factory=dict)


@dataclass
class QueryContext:
    """Input context used by providers and scoring."""

    query: str
    brand_hint: Optional[str] = None
    item_hint: Optional[str] = None
