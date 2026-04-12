import os
from typing import Any, Dict, List, Optional

from nutrition.http_client import HttpClient
from nutrition.models import QueryContext, NutritionCandidate
from nutrition.providers.base import NutritionProvider


class USDAProvider(NutritionProvider):
    source_name = "usda"

    def __init__(self, http_client: Optional[HttpClient] = None, api_key: Optional[str] = None) -> None:
        self.http_client = http_client or HttpClient()
        self.api_key = api_key or os.getenv("USDA_API_KEY")

    def _extract_nutrient(self, nutrients: List[Dict[str, Any]], nutrient_name: str) -> Optional[float]:
        for item in nutrients:
            name = (item.get("nutrientName") or "").lower()
            if nutrient_name.lower() in name:
                value = item.get("value")
                if value is None:
                    continue
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return None
        return None

    def search(self, context: QueryContext, limit: int = 5) -> List[NutritionCandidate]:
        if not self.api_key:
            return []
        queries: List[str] = []
        if context.item_hint:
            queries.append(context.item_hint)
        if context.query and context.query not in queries:
            queries.append(context.query)

        foods: List[Dict[str, Any]] = []
        seen_ids = set()
        for q in queries:
            payload = {
                "query": q,
                "pageSize": limit,
                "dataType": ["Branded", "Foundation", "SR Legacy", "Survey (FNDDS)"]
            }

            response = self.http_client.post_json(
                "https://api.nal.usda.gov/fdc/v1/foods/search",
                payload=payload,
                params={"api_key": self.api_key},
            )

            for food in response.get("foods", []):
                fdc_id = food.get("fdcId")
                if fdc_id in seen_ids:
                    continue
                seen_ids.add(fdc_id)
                foods.append(food)

        results: List[NutritionCandidate] = []

        for food in foods:
            nutrients = food.get("foodNutrients", [])
            calories = self._extract_nutrient(nutrients, "Energy")
            protein = self._extract_nutrient(nutrients, "Protein")
            carbs = self._extract_nutrient(nutrients, "Carbohydrate")
            fat = self._extract_nutrient(nutrients, "Total lipid")

            serving = None
            serving_size = food.get("servingSize")
            serving_unit = food.get("servingSizeUnit")
            if serving_size and serving_unit:
                serving = f"{serving_size} {serving_unit}"

            results.append(
                NutritionCandidate(
                    name=food.get("description") or context.query,
                    brand=food.get("brandOwner") or food.get("brandName"),
                    serving=serving,
                    calories=calories,
                    protein_g=protein,
                    carbs_g=carbs,
                    fat_g=fat,
                    source=self.source_name,
                    source_url=f"https://fdc.nal.usda.gov/fdc-app.html#/food-details/{food.get('fdcId')}/nutrients",
                    source_confidence=0.88,
                    provider_item_id=str(food.get("fdcId")) if food.get("fdcId") else None,
                    extra_nutrients={
                        "fiber_g": self._extract_nutrient(nutrients, "Fiber"),
                        "sugar_g": self._extract_nutrient(nutrients, "Sugars"),
                        "sodium_mg": self._extract_nutrient(nutrients, "Sodium"),
                    },
                )
            )

        return results
