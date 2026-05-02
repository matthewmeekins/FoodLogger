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


if __name__ == "__main__":
    unittest.main()
