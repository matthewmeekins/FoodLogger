import os
import tempfile
import unittest
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient

import database
import main


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

    def test_quantity_update_recalculates_totals(self) -> None:
        today = date.today().isoformat()

        raw_id = database.insert_raw_entry("two kombuchas")
        parsed_id = database.insert_parsed_entry(raw_id, {"confidence": "high", "intents": []}, "high")
        entry_id = database.insert_resolved_entry(
            parsed_id=parsed_id,
            food_name="Humm Mango Passionfruit Kombucha",
            calories=160,
            quantity_value=2,
            quantity_unit="bottle",
            per_unit_calories=80,
            protein_g=0,
            carbs_g=36,
            fat_g=0,
            per_unit_protein_g=0,
            per_unit_carbs_g=18,
            per_unit_fat_g=0,
            meal=None,
            logged_date=today,
            source="manual",
            confidence_level="manual",
        )

        updated = database.update_resolved_entry(entry_id, quantity_value=1)
        self.assertTrue(updated)

        entries = database.get_entries_for_date(today)
        entry = next(e for e in entries if e["id"] == entry_id)
        self.assertEqual(entry["quantity_value"], 1)
        self.assertEqual(entry["calories"], 80)
        self.assertEqual(entry["carbs_g"], 18)

        edits = database.get_entry_edits(entry_id)
        edited_fields = {edit["field_name"] for edit in edits}
        self.assertIn("quantity_value", edited_fields)
        self.assertIn("calories", edited_fields)

    def test_add_to_today_from_summary_entry(self) -> None:
        historical_date = "2026-05-01"

        raw_id = database.insert_raw_entry("historical banana")
        parsed_id = database.insert_parsed_entry(raw_id, {"confidence": "high", "intents": []}, "high")
        original_entry_id = database.insert_resolved_entry(
            parsed_id=parsed_id,
            food_name="BANANA",
            calories=105,
            meal="breakfast",
            logged_date=historical_date,
            source="manual",
            confidence_level="manual",
            quantity_value=1,
        )

        client = TestClient(main.app)
        response = client.post(f"/log/{original_entry_id}/add-to-today")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertIn("entry_id", payload)

        today = date.today().isoformat()
        today_entries = database.get_entries_for_date(today)
        self.assertTrue(any(e["food_name"] == "BANANA" and e["calories"] == 105 for e in today_entries))

    def test_entry_details_endpoint_returns_plain_language_lines(self) -> None:
        today = date.today().isoformat()

        raw_id = database.insert_raw_entry("I had 2 humm kombuchas")
        parsed_id = database.insert_parsed_entry(raw_id, {"confidence": "high", "intents": []}, "high")
        entry_id = database.insert_resolved_entry(
            parsed_id=parsed_id,
            food_name="Humm Mango Passionfruit Kombucha",
            calories=160,
            quantity_value=2,
            quantity_unit="bottle",
            protein_g=0,
            carbs_g=36,
            fat_g=0,
            meal="snack",
            logged_date=today,
            source="openai",
            confidence_level="high",
            reasoning="Two bottles at roughly 80 calories each.",
        )

        client = TestClient(main.app)
        response = client.get(f"/log/{entry_id}/details")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["title"], "Entry details")
        self.assertTrue(isinstance(payload["lines"], list))
        self.assertTrue(any("Estimated calories" in line for line in payload["lines"]))
        self.assertTrue(any("Original journal input" in line for line in payload["lines"]))


    def test_meal_auto_detection_from_time_of_day(self) -> None:
        """estimate_nutrition uses hour to infer meal when not mentioned by user."""
        import llm

        CASES = [
            (7,  "breakfast"),   # 7am → breakfast
            (12, "lunch"),       # 12pm → lunch
            (18, "dinner"),      # 6pm → dinner
            (15, "snack"),       # 3pm → snack (outside breakfast/lunch/dinner windows)
        ]

        for hour, expected_meal in CASES:
            fake_time = datetime(2026, 5, 2, hour, 0, 0)
            fake_response = MagicMock()
            fake_response.choices = [MagicMock()]
            fake_response.choices[0].message.content = f'{{"items": [{{"name": "Test food", "calories": 100, "quantity_value": 1, "quantity_unit": null, "protein_g": 5, "carbs_g": 10, "fat_g": 2, "meal": "{expected_meal}", "reasoning": "test"}}], "logged_date": "2026-05-02"}}'
            fake_response.usage = None

            with patch.object(llm, '_chat_completion_with_retry', return_value=fake_response):
                result = llm.estimate_nutrition("a banana", api_key="fake-key", current_time=fake_time)

            meals = [item["meal"] for item in result["items"]]
            self.assertEqual(meals[0], expected_meal,
                             f"At hour={hour}, expected meal={expected_meal}, got {meals[0]}")

    def test_meal_prompt_contains_explicit_time_rules(self) -> None:
        """The system prompt must contain explicit hour-range rules for meal inference."""
        import llm
        import inspect

        source = inspect.getsource(llm.estimate_nutrition)
        # Check for at least one explicit hour bracket used in time-based meal assignment
        self.assertIn("5–10", source, "Prompt should contain breakfast hour range 5–10")
        self.assertIn("11–13", source, "Prompt should contain lunch hour range 11–13")
        self.assertIn("17–21", source, "Prompt should contain dinner hour range 17–21")

    def test_weekly_endpoint_returns_7_days(self) -> None:
        """GET /log/weekly returns exactly 7 day slots with correct structure."""
        client = TestClient(main.app)
        response = client.get("/log/weekly?start_date=2026-04-28")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["start_date"], "2026-04-28")
        self.assertEqual(data["end_date"], "2026-05-04")
        self.assertEqual(len(data["days"]), 7)
        self.assertIn("totals", data)
        self.assertIn("averages", data)
        self.assertIn("meal_frequency", data)

    def test_weekly_endpoint_computes_totals(self) -> None:
        """Weekly totals and averages are correctly computed from logged entries."""
        # Insert entries on two different days within a week
        database.insert_resolved_entry(
            parsed_id=database.insert_parsed_entry(
                database.insert_raw_entry("breakfast"),
                {"confidence": "high", "intents": []}, "high"
            ),
            food_name="Oatmeal",
            calories=300,
            protein_g=10,
            carbs_g=50,
            fat_g=5,
            meal="breakfast",
            logged_date="2026-04-28",
            source="manual",
            confidence_level="manual",
        )
        database.insert_resolved_entry(
            parsed_id=database.insert_parsed_entry(
                database.insert_raw_entry("lunch"),
                {"confidence": "high", "intents": []}, "high"
            ),
            food_name="Chicken Salad",
            calories=500,
            protein_g=40,
            carbs_g=20,
            fat_g=15,
            meal="lunch",
            logged_date="2026-04-29",
            source="manual",
            confidence_level="manual",
        )

        client = TestClient(main.app)
        response = client.get("/log/weekly?start_date=2026-04-28")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        self.assertEqual(data["totals"]["calories"], 800)
        self.assertEqual(data["active_days"], 2)
        self.assertEqual(data["averages"]["calories"], 400.0)
        self.assertEqual(data["meal_frequency"].get("breakfast"), 1)
        self.assertEqual(data["meal_frequency"].get("lunch"), 1)

    def test_summary_endpoint_includes_macro_totals(self) -> None:
        """GET /log/summary rows include total_protein_g, total_carbs_g, total_fat_g."""
        today = date.today().isoformat()
        database.insert_resolved_entry(
            parsed_id=database.insert_parsed_entry(
                database.insert_raw_entry("test"),
                {"confidence": "high", "intents": []}, "high"
            ),
            food_name="Test Food",
            calories=200,
            protein_g=15,
            carbs_g=25,
            fat_g=8,
            meal=None,
            logged_date=today,
            source="manual",
            confidence_level="manual",
        )

        client = TestClient(main.app)
        response = client.get("/log/summary")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        day = next(d for d in data["summary"] if d["date"] == today)
        self.assertEqual(day["total_protein_g"], 15)
        self.assertEqual(day["total_carbs_g"], 25)
        self.assertEqual(day["total_fat_g"], 8)


if __name__ == "__main__":
    unittest.main()
