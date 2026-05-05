import re
from typing import List, Set

from nutrition.cache import TTLCache
from nutrition.models import QueryContext, NutritionCandidate
from nutrition.providers.base import NutritionProvider
from nutrition.providers.open_food_facts import OpenFoodFactsProvider
from nutrition.providers.usda import USDAProvider
from nutrition.providers.web_search import WebSearchProvider


class NutritionService:
    """Orchestrates provider fallback, scoring, and cache for nutrition lookups."""

    _STOP_WORDS: Set[str] = {
        "a", "an", "the", "with", "and", "or", "of", "to", "for", "in", "on",
        "no", "without", "extra", "add", "added", "with", "from", "my", "i", "had",
    }

    def __init__(self, providers: List[NutritionProvider] | None = None, cache_ttl_seconds: int = 3600) -> None:
        self.providers = providers or [USDAProvider(), OpenFoodFactsProvider()]
        self.web_provider = WebSearchProvider()
        self.cache = TTLCache(ttl_seconds=cache_ttl_seconds)

    def _determine_provider_order(self, context: QueryContext) -> List[NutritionProvider]:
        """Determine the order of providers based on query characteristics."""
        query_lower = context.query.lower()
        brand_hint = (context.brand_hint or "").strip()

        usda_first = sorted(self.providers, key=lambda p: 0 if p.source_name == "usda" else 1)
        off_first = sorted(self.providers, key=lambda p: 0 if p.source_name == "open_food_facts" else 1)

        # Indicators that suggest web search should be prioritized
        web_search_indicators = [
            bool(brand_hint),  # Has a brand/restaurant name
            '#' in query_lower,  # Menu item numbers like #13
            any(term in query_lower for term in ['bowl', 'sandwich', 'burger', 'pizza', 'taco', 'burrito']),  # Common menu items
            any(term in query_lower for term in ['mcdonald', 'burger king', 'wendy', 'starbucks', 'subway', 'chipotle']),  # Known chains
        ]

        packaged_indicators = [
            any(term in query_lower for term in ["barcode", "upc", "ean", "package", "packaged", "bottle", "can", "bar"]),
            any(term in query_lower for term in ["oz", "g", "gram", "ml", "serving", "fl oz"]),
        ]

        # If any web search indicators are present, prioritize web search
        if any(web_search_indicators):
            return [self.web_provider] + usda_first  # Web search first, then nutrition APIs

        if any(packaged_indicators):
            return off_first  # Packaged products: Open Food Facts first

        # Generic foods: USDA first
        return usda_first

    def _tokenize(self, text: str) -> Set[str]:
        tokens = set(re.findall(r"[a-z0-9']+", (text or "").lower()))
        return {t for t in tokens if t and t not in self._STOP_WORDS and len(t) > 1}

    def _token_overlap(self, left: str, right: str) -> float:
        left_tokens = self._tokenize(left)
        right_tokens = self._tokenize(right)
        if not left_tokens:
            return 0.0
        return len(left_tokens.intersection(right_tokens)) / len(left_tokens)

    def _has_brand_match(self, context: QueryContext, candidate: NutritionCandidate) -> bool:
        brand_hint = (context.brand_hint or "").strip().lower()
        if not brand_hint:
            return False

        candidate_brand = (candidate.brand or "").strip().lower()
        candidate_name = (candidate.name or "").strip().lower()
        if brand_hint in candidate_brand or brand_hint in candidate_name:
            return True

        brand_tokens = self._tokenize(brand_hint)
        if not brand_tokens:
            return False

        candidate_tokens = self._tokenize(f"{candidate_brand} {candidate_name}")
        return len(brand_tokens.intersection(candidate_tokens)) >= 1

    def _passes_quality_gate(self, context: QueryContext, candidate: NutritionCandidate) -> bool:
        """Accept only candidates that are strong enough for this query type."""
        has_macros = all(v is not None for v in [candidate.calories, candidate.protein_g, candidate.carbs_g, candidate.fat_g])
        if not has_macros:
            return False

        if candidate.source == "web" and not (candidate.source_url or "").strip():
            return False

        branded_query = bool((context.brand_hint or "").strip())
        overlap = self._token_overlap(context.query, candidate.name)
        item_anchor = context.item_hint or context.query
        item_overlap = self._token_overlap(item_anchor, candidate.name)
        brand_match = self._has_brand_match(context, candidate)

        if branded_query:
            # For branded/menu items, require explicit brand match or a very strong item-name overlap.
            if candidate.source == "web":
                official_brand_source = bool(candidate.extra_nutrients.get("official_brand_source"))
                if not official_brand_source:
                    return False

            if brand_match:
                return (overlap >= 0.2 and item_overlap >= 0.2) or candidate.source == "web"
            return candidate.source == "web" and overlap >= 0.6 and item_overlap >= 0.3

        # For generic foods, allow moderate textual overlap.
        return overlap >= 0.25 and item_overlap >= 0.34

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

        item_anchor = (context.item_hint or context.query).lower()
        item_overlap = self._token_overlap(item_anchor, name)
        if item_overlap >= 0.5:
            score += 0.12
        elif item_overlap == 0:
            score -= 0.18

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

        # Determine provider order based on query characteristics
        providers_to_try = self._determine_provider_order(context)

        for provider in providers_to_try:
            try:
                results = provider.search(context, limit=limit)
                candidates.extend(results)
            except Exception:
                # Provider errors are non-fatal; continue to next provider.
                continue

        scored = sorted(candidates, key=lambda c: self._score_candidate(context, c), reverse=True)
        accepted = [c for c in scored if self._passes_quality_gate(context, c)]
        final = accepted[:limit]
        self.cache.set(key, final)

        return final
