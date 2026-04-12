from typing import List

from nutrition.cache import TTLCache
from nutrition.models import QueryContext, NutritionCandidate
from nutrition.providers.base import NutritionProvider
from nutrition.providers.open_food_facts import OpenFoodFactsProvider
from nutrition.providers.usda import USDAProvider


class NutritionService:
    """Orchestrates provider fallback, scoring, and cache for nutrition lookups."""

    def __init__(self, providers: List[NutritionProvider] | None = None, cache_ttl_seconds: int = 3600) -> None:
        self.providers = providers or [USDAProvider(), OpenFoodFactsProvider()]
        self.cache = TTLCache(ttl_seconds=cache_ttl_seconds)

    def _cache_key(self, context: QueryContext, limit: int) -> str:
        brand = (context.brand_hint or "").strip().lower()
        return f"{context.query.strip().lower()}|{brand}|{limit}"

    def _score_candidate(self, context: QueryContext, candidate: NutritionCandidate) -> float:
        score = candidate.source_confidence

        query = context.query.lower()
        name = (candidate.name or "").lower()
        brand_hint = (context.brand_hint or "").lower().strip()
        brand = (candidate.brand or "").lower()

        if name and query in name:
            score += 0.08

        if brand_hint and brand_hint in brand:
            score += 0.12

        has_macros = all(v is not None for v in [candidate.calories, candidate.protein_g, candidate.carbs_g, candidate.fat_g])
        if has_macros:
            score += 0.08

        return min(score, 0.99)

    def search(self, context: QueryContext, limit: int = 5) -> List[NutritionCandidate]:
        key = self._cache_key(context, limit)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        candidates: List[NutritionCandidate] = []

        for provider in self.providers:
            try:
                results = provider.search(context, limit=limit)
                candidates.extend(results)
                # Use first provider with data as primary; still keep fallback-only behavior when empty.
                if results:
                    break
            except Exception:
                # Provider errors are non-fatal; continue to next provider.
                continue

        scored = sorted(candidates, key=lambda c: self._score_candidate(context, c), reverse=True)
        final = scored[:limit]
        self.cache.set(key, final)

        return final
