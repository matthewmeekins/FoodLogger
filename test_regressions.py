import os
import tempfile
import unittest
from datetime import date, datetime
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from passlib.hash import bcrypt

import database
import main


class FoodLogRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self._orig_db_path = database.DB_PATH
        self._tmpdir = tempfile.TemporaryDirectory()
        database.DB_PATH = os.path.join(self._tmpdir.name, "test_food_log.db")
        database.init_db()
        main._REQUEST_HISTORY.clear()
        self.test_username = "regression-user"
        self.test_password = "regression-pass"
        self.user_id = database.create_user(
            username=self.test_username,
            display_name="Regression User",
            password_hash=bcrypt.hash(self.test_password),
            is_admin=1,
        )

    def _authed_client(self) -> TestClient:
        client = TestClient(main.app)
        login = client.post(
            "/auth/login",
            json={"username": self.test_username, "password": self.test_password},
        )
        self.assertEqual(login.status_code, 200)
        return client

    def tearDown(self) -> None:
        database.DB_PATH = self._orig_db_path
        self._tmpdir.cleanup()

    def test_today_endpoint_returns_newest_first(self) -> None:
        today = date.today().isoformat()

        raw_1 = database.insert_raw_entry("first")
        parsed_1 = database.insert_parsed_entry(raw_1, {"intents": []})
        database.insert_resolved_entry(
            user_id=self.user_id,
            parsed_id=parsed_1,
            food_name="FIRST",
            calories=100,
            meal=None,
            logged_date=today,
            source="manual",
        )

        raw_2 = database.insert_raw_entry("second")
        parsed_2 = database.insert_parsed_entry(raw_2, {"intents": []})
        database.insert_resolved_entry(
            user_id=self.user_id,
            parsed_id=parsed_2,
            food_name="SECOND",
            calories=200,
            meal=None,
            logged_date=today,
            source="manual",
        )

        client = self._authed_client()
        response = client.get("/log/today")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        names = [entry["food_name"] for entry in payload["entries"]]
        self.assertEqual(names[:2], ["SECOND", "FIRST"])

    def test_quantity_update_recalculates_totals(self) -> None:
        today = date.today().isoformat()

        raw_id = database.insert_raw_entry("two kombuchas")
        parsed_id = database.insert_parsed_entry(raw_id, {"intents": []})
        entry_id = database.insert_resolved_entry(
            user_id=self.user_id,
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
        )

        updated = database.update_resolved_entry(entry_id, self.user_id, quantity_value=1)
        self.assertTrue(updated)

        entries = database.get_entries_for_date(today, self.user_id)
        entry = next(e for e in entries if e["id"] == entry_id)
        self.assertEqual(entry["quantity_value"], 1)
        self.assertEqual(entry["calories"], 80)
        self.assertEqual(entry["carbs_g"], 18)

        edits = database.get_entry_edits(entry_id, self.user_id)
        edited_fields = {edit["field_name"] for edit in edits}
        self.assertIn("quantity_value", edited_fields)
        self.assertIn("calories", edited_fields)

    def test_entry_update_can_change_date_and_time(self) -> None:
        original_date = "2026-05-01"
        updated_date = "2026-05-03"
        updated_created_at = "2026-05-03T14:45:00+00:00"

        raw_id = database.insert_raw_entry("banana")
        parsed_id = database.insert_parsed_entry(raw_id, {"intents": []})
        entry_id = database.insert_resolved_entry(
            user_id=self.user_id,
            parsed_id=parsed_id,
            food_name="BANANA",
            calories=105,
            meal="breakfast",
            logged_date=original_date,
            source="manual",
        )

        updated = database.update_resolved_entry(
            entry_id,
            self.user_id,
            logged_date=updated_date,
            created_at=updated_created_at,
        )
        self.assertTrue(updated)

        updated_entries = database.get_entries_for_date(updated_date, self.user_id)
        updated_entry = next(e for e in updated_entries if e["id"] == entry_id)
        self.assertEqual(updated_entry["logged_date"], updated_date)
        self.assertEqual(updated_entry["created_at"], updated_created_at)

        original_entries = database.get_entries_for_date(original_date, self.user_id)
        self.assertFalse(any(e["id"] == entry_id for e in original_entries))

        edits = database.get_entry_edits(entry_id, self.user_id)
        fields = {edit["field_name"] for edit in edits}
        self.assertIn("logged_date", fields)
        self.assertIn("created_at", fields)

    def test_add_to_today_from_summary_entry(self) -> None:
        historical_date = "2026-05-01"

        raw_id = database.insert_raw_entry("historical banana")
        parsed_id = database.insert_parsed_entry(raw_id, {"intents": []})
        original_entry_id = database.insert_resolved_entry(
            user_id=self.user_id,
            parsed_id=parsed_id,
            food_name="BANANA",
            calories=105,
            meal="breakfast",
            logged_date=historical_date,
            source="manual",
            quantity_value=1,
        )

        client = self._authed_client()
        response = client.post(f"/log/{original_entry_id}/add-to-today")
        self.assertEqual(response.status_code, 200)

        payload = response.json()
        self.assertEqual(payload["status"], "success")
        self.assertIn("entry_id", payload)

        today = date.today().isoformat()
        today_entries = database.get_entries_for_date(today, self.user_id)
        self.assertTrue(any(e["food_name"] == "BANANA" and e["calories"] == 105 for e in today_entries))

    def test_entry_details_endpoint_returns_plain_language_lines(self) -> None:
        today = date.today().isoformat()

        raw_id = database.insert_raw_entry("I had 2 humm kombuchas")
        parsed_id = database.insert_parsed_entry(raw_id, {"intents": []})
        entry_id = database.insert_resolved_entry(
            user_id=self.user_id,
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
            reasoning="Two bottles at roughly 80 calories each.",
        )

        client = self._authed_client()
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
        client = self._authed_client()
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
            user_id=self.user_id,
            parsed_id=database.insert_parsed_entry(
                database.insert_raw_entry("breakfast"),
                {"intents": []}
            ),
            food_name="Oatmeal",
            calories=300,
            protein_g=10,
            carbs_g=50,
            fat_g=5,
            meal="breakfast",
            logged_date="2026-04-28",
            source="manual",
        )
        database.insert_resolved_entry(
            user_id=self.user_id,
            parsed_id=database.insert_parsed_entry(
                database.insert_raw_entry("lunch"),
                {"intents": []}
            ),
            food_name="Chicken Salad",
            calories=500,
            protein_g=40,
            carbs_g=20,
            fat_g=15,
            meal="lunch",
            logged_date="2026-04-29",
            source="manual",
        )

        client = self._authed_client()
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
            user_id=self.user_id,
            parsed_id=database.insert_parsed_entry(
                database.insert_raw_entry("test"),
                {"intents": []}
            ),
            food_name="Test Food",
            calories=200,
            protein_g=15,
            carbs_g=25,
            fat_g=8,
            meal=None,
            logged_date=today,
            source="manual",
        )

        client = self._authed_client()
        response = client.get("/log/summary")
        self.assertEqual(response.status_code, 200)

        data = response.json()
        day = next(d for d in data["summary"] if d["date"] == today)
        self.assertEqual(day["total_protein_g"], 15)
        self.assertEqual(day["total_carbs_g"], 25)
        self.assertEqual(day["total_fat_g"], 8)


    def test_favorites_create_list_delete(self) -> None:
        """Can create, list, and delete a single-item favorite."""
        client = self._authed_client()

        # Create
        payload = {
            "name": "Morning Banana",
            "items": [{"food_name": "Banana", "calories": 105, "protein_g": 1.3, "carbs_g": 27.0, "fat_g": 0.4, "meal": "breakfast", "quantity_value": 1}],
        }
        resp = client.post("/favorites", json=payload)
        self.assertEqual(resp.status_code, 200)
        fav_id = resp.json()["id"]

        # List
        resp = client.get("/favorites")
        self.assertEqual(resp.status_code, 200)
        names = [f["name"] for f in resp.json()["favorites"]]
        self.assertIn("Morning Banana", names)

        # Delete
        resp = client.delete(f"/favorites/{fav_id}")
        self.assertEqual(resp.status_code, 200)

        resp = client.get("/favorites")
        names = [f["name"] for f in resp.json()["favorites"]]
        self.assertNotIn("Morning Banana", names)

    def test_log_favorite_creates_today_entries(self) -> None:
        """POST /favorites/{id}/log creates resolved entries for today."""
        client = self._authed_client()

        payload = {
            "name": "Standard Breakfast",
            "items": [
                {"food_name": "Banana", "calories": 105, "meal": "breakfast", "quantity_value": 1},
                {"food_name": "Coffee", "calories": 5, "meal": "breakfast", "quantity_value": 1},
            ],
        }
        create_resp = client.post("/favorites", json=payload)
        fav_id = create_resp.json()["id"]

        log_resp = client.post(f"/favorites/{fav_id}/log")
        self.assertEqual(log_resp.status_code, 200)
        data = log_resp.json()
        self.assertEqual(data["items_logged"], 2)

        today = date.today().isoformat()
        entries = database.get_entries_for_date(today, self.user_id)
        logged_names = {e["food_name"] for e in entries}
        self.assertIn("Banana", logged_names)
        self.assertIn("Coffee", logged_names)

    def test_favorites_multi_item_totals(self) -> None:
        """Favorites list computes total_calories from all items."""
        client = self._authed_client()

        payload = {
            "name": "Big Meal",
            "items": [
                {"food_name": "Rice", "calories": 300, "protein_g": 6, "carbs_g": 65, "fat_g": 1},
                {"food_name": "Chicken", "calories": 250, "protein_g": 35, "carbs_g": 0, "fat_g": 8},
            ],
        }
        create_resp = client.post("/favorites", json=payload)
        fav_id = create_resp.json()["id"]

        list_resp = client.get("/favorites")
        fav = next(f for f in list_resp.json()["favorites"] if f["id"] == fav_id)
        self.assertEqual(fav["total_calories"], 550)
        self.assertEqual(fav["item_count"], 2)
        self.assertAlmostEqual(fav["total_protein_g"], 41.0)


if __name__ == "__main__":
    unittest.main()
