from typing import List
from nutrition.models import QueryContext, NutritionCandidate


class NutritionProvider:
    """Provider interface for nutrition source adapters."""

    source_name: str = "unknown"

    def search(self, context: QueryContext, limit: int = 5) -> List[NutritionCandidate]:
        raise NotImplementedError
