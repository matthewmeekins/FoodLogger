import json
import os
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlparse

from nutrition.http_client import HttpClient
from nutrition.models import QueryContext, NutritionCandidate
from nutrition.providers.base import NutritionProvider


class WebSearchProvider(NutritionProvider):
    """Provider that uses web search to find restaurant menu nutrition data."""

    source_name = "web"

    def __init__(self, http_client: Optional[HttpClient] = None) -> None:
        self.http_client = http_client or HttpClient()
        self.openai_timeout_seconds = float(os.getenv("OPENAI_TIMEOUT_SECONDS", "20"))
        self.openai_max_retries = max(0, int(os.getenv("OPENAI_MAX_RETRIES", "1")))

    def _create_openai_client(self, api_key: str):
        import openai
        return openai.OpenAI(api_key=api_key, timeout=self.openai_timeout_seconds, max_retries=0)

    def _brand_tokens(self, brand_hint: str) -> List[str]:
        tokens = re.findall(r"[a-z0-9]+", (brand_hint or "").lower())
        stop_words = {"the", "and", "of", "inc", "llc", "co", "company"}
        return [t for t in tokens if t not in stop_words and len(t) > 2]

    def _domain_matches_brand(self, source_url: str, brand_hint: Optional[str]) -> bool:
        if not source_url:
            return False
        if not brand_hint:
            return True

        try:
            host = (urlparse(source_url).netloc or "").lower().replace("www.", "")
        except Exception:
            return False

        tokens = self._brand_tokens(brand_hint)
        if not tokens:
            return False

        return any(token in host for token in tokens)

    def _extract_output_text(self, response: Any) -> str:
        text = getattr(response, "output_text", None)
        if text:
            return text

        parts: List[str] = []
        output_items = getattr(response, "output", []) or []
        for item in output_items:
            content = getattr(item, "content", []) or []
            for chunk in content:
                maybe_text = getattr(chunk, "text", None)
                if maybe_text:
                    parts.append(maybe_text)
        return "\n".join(parts)

    def _extract_json_block(self, text: str) -> Optional[dict[str, Any]]:
        """Best-effort extraction of a JSON object from raw model text."""
        if not text:
            return None

        cleaned = text.strip()
        # Remove markdown fences if present
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r"\s*```$", "", cleaned)

        try:
            parsed = json.loads(cleaned)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass

        # Extract first balanced {...} block
        start = cleaned.find("{")
        if start == -1:
            return None

        depth = 0
        for idx in range(start, len(cleaned)):
            ch = cleaned[idx]
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    snippet = cleaned[start:idx + 1]
                    try:
                        parsed = json.loads(snippet)
                        return parsed if isinstance(parsed, dict) else None
                    except Exception:
                        return None
        return None

    def _structure_web_text(self, api_key: str, raw_text: str) -> dict[str, Any]:
        """Convert prose web-search output into strict JSON nutrition_data format."""
        if not raw_text.strip():
            return {"nutrition_data": []}

        client = self._create_openai_client(api_key)
        last_error = None
        response = None
        for attempt in range(self.openai_max_retries + 1):
            try:
                response = client.chat.completions.create(
                    model="gpt-4o",
                    messages=[
                        {
                            "role": "system",
                            "content": (
                                "Extract nutrition candidates from the text. "
                                "Return ONLY JSON object: {\"nutrition_data\": [...]} with fields "
                                "name, serving, calories, protein_g, carbs_g, fat_g, source_url, citation. "
                                "Drop entries without explicit numeric macros and source_url."
                            ),
                        },
                        {"role": "user", "content": raw_text},
                    ],
                    response_format={"type": "json_object"},
                    temperature=0,
                    max_tokens=600,
                )
                break
            except Exception as exc:
                last_error = exc
                if attempt < self.openai_max_retries:
                    time.sleep(0.25 * (attempt + 1))

        if response is None:
            if last_error:
                raise last_error
            return {"nutrition_data": []}

        content = (response.choices[0].message.content or "").strip()
        try:
            parsed = json.loads(content)
            return parsed if isinstance(parsed, dict) else {"nutrition_data": []}
        except Exception:
            return {"nutrition_data": []}

    def _normalize_items(self, items: Any, context: QueryContext, limit: int) -> List[NutritionCandidate]:
        if not isinstance(items, list):
            return []

        candidates: List[NutritionCandidate] = []
        for item in items:
            if not isinstance(item, dict):
                continue

            required = ["name", "calories", "protein_g", "carbs_g", "fat_g", "source_url"]
            if any(key not in item for key in required):
                continue

            source_url = str(item.get("source_url") or "").strip()
            if not source_url.startswith("http"):
                continue

            official_match = self._domain_matches_brand(source_url, context.brand_hint)
            branded_query = bool((context.brand_hint or "").strip())
            if branded_query and not official_match:
                # For branded lookups, require source URL to align with brand domain.
                continue

            try:
                calories = float(item["calories"])
                protein_g = float(item["protein_g"])
                carbs_g = float(item["carbs_g"])
                fat_g = float(item["fat_g"])
            except (TypeError, ValueError):
                continue

            source_confidence = 0.9 if official_match else 0.8
            candidates.append(
                NutritionCandidate(
                    name=str(item["name"]).strip(),
                    brand=context.brand_hint,
                    serving=str(item.get("serving") or "1 serving").strip(),
                    calories=calories,
                    protein_g=protein_g,
                    carbs_g=carbs_g,
                    fat_g=fat_g,
                    source=self.source_name,
                    source_url=source_url,
                    source_confidence=source_confidence,
                    provider_item_id=None,
                    extra_nutrients={
                        "citation": str(item.get("citation") or "").strip(),
                        "official_brand_source": official_match,
                    },
                )
            )

            if len(candidates) >= limit:
                break

        return candidates

    def search(self, context: QueryContext, limit: int = 5) -> List[NutritionCandidate]:
        """Search for nutrition data using grounded web search with citations."""
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            return []

        try:
            client = self._create_openai_client(api_key)

            search_query = self._build_search_query(context)
            prompt = (
                "Find nutrition facts for the requested food. Use web search. "
                "Return STRICT JSON with key 'nutrition_data' containing a list of objects. "
                "Each object must include: name, serving, calories, protein_g, carbs_g, fat_g, source_url, citation. "
                "Only include items with explicit numeric values and an explicit source URL. "
                f"Food query: {search_query}."
            )

            last_error = None
            response = None
            for attempt in range(self.openai_max_retries + 1):
                try:
                    response = client.responses.create(
                        model="gpt-4.1-mini",
                        input=prompt,
                        tools=[{"type": "web_search_preview"}],
                        temperature=0,
                    )
                    break
                except Exception as exc:
                    last_error = exc
                    if attempt < self.openai_max_retries:
                        time.sleep(0.25 * (attempt + 1))

            if response is None:
                if last_error:
                    raise last_error
                return []

            output_text = self._extract_output_text(response)
            parsed = self._extract_json_block(output_text)
            if parsed is None:
                parsed = self._structure_web_text(api_key, output_text)

            items = parsed.get("nutrition_data", []) if isinstance(parsed, dict) else []
            return self._normalize_items(items, context, limit)

        except Exception as e:
            print(f"Web search failed: {e}")
            return []

    def _build_search_query(self, context: QueryContext) -> str:
        """Build an effective search query for restaurant menu nutrition."""
        query_parts = []

        if context.brand_hint:
            query_parts.append(f"{context.brand_hint}")

        query_parts.append(context.query)

        # Add nutrition-specific terms
        query_parts.append("nutrition facts calories protein carbs fat")

        return " ".join(query_parts)