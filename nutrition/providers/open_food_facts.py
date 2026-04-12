from typing import Any, Dict, List, Optional

from nutrition.http_client import HttpClient
from nutrition.models import QueryContext, NutritionCandidate
from nutrition.providers.base import NutritionProvider


class OpenFoodFactsProvider(NutritionProvider):
    source_name = "open_food_facts"

    def __init__(self, http_client: Optional[HttpClient] = None) -> None:
        self.http_client = http_client or HttpClient()

    def _float_or_none(self, value: Any) -> Optional[float]:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def search(self, context: QueryContext, limit: int = 5) -> List[NutritionCandidate]:
        response = self.http_client.get_json(
            "https://world.openfoodfacts.org/cgi/search.pl",
            params={
                "search_terms": context.query,
                "search_simple": 1,
                "action": "process",
                "json": 1,
                "page_size": limit,
            },
        )

        products = response.get("products", [])
        results: List[NutritionCandidate] = []

        for product in products:
            nutriments: Dict[str, Any] = product.get("nutriments", {})

            calories = self._float_or_none(nutriments.get("energy-kcal_100g") or nutriments.get("energy-kcal"))
            protein = self._float_or_none(nutriments.get("proteins_100g") or nutriments.get("proteins"))
            carbs = self._float_or_none(nutriments.get("carbohydrates_100g") or nutriments.get("carbohydrates"))
            fat = self._float_or_none(nutriments.get("fat_100g") or nutriments.get("fat"))

            product_name = (
                product.get("product_name")
                or product.get("generic_name")
                or context.query
            )

            code = product.get("code")
            source_url = f"https://world.openfoodfacts.org/product/{code}" if code else None

            results.append(
                NutritionCandidate(
                    name=product_name,
                    brand=product.get("brands"),
                    serving=product.get("serving_size") or "100 g",
                    calories=calories,
                    protein_g=protein,
                    carbs_g=carbs,
                    fat_g=fat,
                    source=self.source_name,
                    source_url=source_url,
                    source_confidence=0.72,
                    provider_item_id=code,
                    extra_nutrients={
                        "fiber_g": self._float_or_none(nutriments.get("fiber_100g") or nutriments.get("fiber")),
                        "sugar_g": self._float_or_none(nutriments.get("sugars_100g") or nutriments.get("sugars")),
                        "sodium_mg": self._float_or_none(nutriments.get("sodium_100g") or nutriments.get("sodium")),
                    },
                )
            )

        return results
