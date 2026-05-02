import os
import tempfile
import unittest
from datetime import date

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


if __name__ == "__main__":
    unittest.main()
