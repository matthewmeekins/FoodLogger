import os
import tempfile
import unittest
from unittest.mock import patch
from datetime import date

from fastapi.testclient import TestClient

import database
import main
from models import StructuredIntent, IntentItem
from nutrition.models import NutritionCandidate


class FoodLogRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_db_path = database.DB_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        database.DB_PATH = os.path.join(self._tmpdir.name, "test_food_log.db")
        database.init_db()
        main._REQUEST_HISTORY.clear()

    def tearDown(self) -> None:
        database.DB_PATH = self._orig_db_path
        self._tmpdir.cleanup()

    def test_component_split_into_three_intents(self) -> None:
        structured = StructuredIntent(
            confidence="high",
            logged_date="2026-04-12",
            intents=[
                IntentItem(
                    brand=None,
                    item="1 pound steamed broccoli with 1 tbsp salt and 3 tablespoons butter",
                    modifiers=[],
                    quantity=None,
                    meal=None,
                    unknowns=[],
                )
            ],
        )

        expanded = main._expand_component_intents(structured)
        items = [intent.item for intent in expanded.intents]
        self.assertEqual(items, ["broccoli", "salt", "butter"])

        quantities = {intent.item: intent.quantity for intent in expanded.intents}
        self.assertEqual(quantities["salt"], "1 tbsp")
        self.assertEqual(quantities["butter"], "3 tablespoons")

    def test_safe_clarification_question_blocks_cross_item_drift(self) -> None:
        intent = IntentItem(
            brand=None,
            item="broccoli",
            modifiers=["steamed"],
            quantity="1 pound",
            meal=None,
            unknowns=[],
        )

        fallback = "Please confirm the exact item name for broccoli and provide the serving amount."
        with patch.object(main.llm, "generate_clarification_question", return_value="Was the butter salted or unsalted?"):
            question = main._safe_clarification_question(
                api_key="fake",
                original_input="I had broccoli with butter",
                intent=intent,
                candidate_name="BROCCOLI",
                candidate_source="usda",
                fallback_question=fallback,
            )

        self.assertEqual(question, fallback)

    def test_quantity_scaling_for_usda_candidate(self) -> None:
        intent = IntentItem(
            brand=None,
            item="butter",
            modifiers=[],
            quantity="3 tablespoons",
            meal=None,
            unknowns=[],
        )
        candidate = NutritionCandidate(
            name="BUTTER",
            brand=None,
            serving="14.0 GRM",
            calories=714.0,
            protein_g=0.0,
            carbs_g=0.0,
            fat_g=78.6,
            source="usda",
            source_url=None,
            source_confidence=0.88,
        )

        adjusted, scaled = main._apply_quantity_scale(intent, candidate)

        self.assertTrue(scaled)
        self.assertAlmostEqual(adjusted.calories or 0.0, 299.88, places=2)
        self.assertAlmostEqual(adjusted.fat_g or 0.0, 33.012, places=3)

    def test_today_endpoint_returns_newest_first(self) -> None:
        today = date.today().isoformat()

        raw_1 = database.insert_raw_entry("first")
        parsed_1 = database.insert_parsed_entry(raw_1, {"confidence": "high", "intents": []}, "high")
        database.insert_resolved_entry(
            parsed_id=parsed_1,
            food_name="FIRST",
            calories=100,
            meal=None,
            logged_date=today,
            source="manual",
            confidence_level="manual",
        )

        raw_2 = database.insert_raw_entry("second")
        parsed_2 = database.insert_parsed_entry(raw_2, {"confidence": "high", "intents": []}, "high")
        database.insert_resolved_entry(
            parsed_id=parsed_2,
            food_name="SECOND",
            calories=200,
            meal=None,
            logged_date=today,
            source="manual",
            confidence_level="manual",
        )

        client = TestClient(main.app)
        response = client.get("/log/today")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        names = [entry["food_name"] for entry in payload["entries"]]
        self.assertEqual(names[:2], ["SECOND", "FIRST"])


if __name__ == "__main__":
    unittest.main()
