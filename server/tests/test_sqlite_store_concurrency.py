import os
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor


SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from sqlite_store import SQLiteStore


class SQLiteStoreConcurrencyTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test_game_state.db")
        self.store = SQLiteStore(self.db_path)
        self.store.upsert_player_resource(1, "credits", 0)

    def tearDown(self):
        try:
            self.store.close()
        finally:
            self._tmp.cleanup()

    def test_adjust_player_resource_is_atomic_under_threads(self):
        per_worker = 250
        worker_count = 12

        def add_credits(_):
            for _i in range(per_worker):
                self.store.adjust_player_resource(1, "credits", 1)

        with ThreadPoolExecutor(max_workers=worker_count) as pool:
            list(pool.map(add_credits, range(worker_count)))

        expected = per_worker * worker_count
        actual = self.store.get_player_resource_amount(1, "credits")
        self.assertEqual(actual, expected)


if __name__ == "__main__":
    unittest.main()
