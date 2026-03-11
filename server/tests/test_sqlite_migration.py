import tempfile
import unittest
from pathlib import Path
import sys

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from migrate_planet_ids import (
    MigrationReport,
    load_mapping,
    migrate_commander_payload,
    migrate_universe_payload,
)
from sqlite_store import SQLiteStore


class TestSqliteMigration(unittest.TestCase):
    def test_migrates_universe_and_commander_payloads(self):
        id_by_name, name_by_id = load_mapping()
        first_planet_name = next(iter(id_by_name.keys()))
        first_planet_id = id_by_name[first_planet_name]

        universe_payload = {
            "planet_states": {
                first_planet_name: {
                    "owner": "tester",
                    "fighters": 3,
                }
            }
        }

        commander_payload = {
            "account_name": "tester",
            "character_name": "captain",
            "current_planet_name": first_planet_name,
            "player": {
                "name": "Captain",
                "barred_planets": {first_planet_name: True},
                "attacked_planets": {first_planet_name: 1},
                "owned_planets": [first_planet_name],
            },
            "bribed_planets": [first_planet_name],
            "bribe_registry": {first_planet_name: 2},
            "planets_smuggling": {first_planet_name: True},
            "law_heat": {"levels": {first_planet_name: 3}},
            "planet_events": {first_planet_name: {"event": "pirates"}},
            "economy_state": {
                "momentum": {first_planet_name: 0.2},
                "volume": {first_planet_name: 11},
            },
            "planet_states": {first_planet_name: {"owner": "Captain"}},
        }

        report = MigrationReport()
        migrated_universe = migrate_universe_payload(
            universe_payload, id_by_name, report, "shared/universe_planets"
        )
        changed, migrated_commander = migrate_commander_payload(
            commander_payload, id_by_name, report, "characters/tester/captain"
        )

        self.assertTrue(changed)
        self.assertEqual(report.unknown_keys, [])
        self.assertIn(str(first_planet_id), migrated_universe["planet_states"])

        self.assertEqual(migrated_commander["current_planet_id"], first_planet_id)
        self.assertNotIn("current_planet_name", migrated_commander)
        self.assertNotIn("owned_planets", migrated_commander["player"])
        self.assertNotIn("planet_states", migrated_commander)
        self.assertIn(
            str(first_planet_id), migrated_commander["player"]["barred_planets"]
        )

    def test_sqlite_round_trip_after_migration(self):
        id_by_name, _name_by_id = load_mapping()
        first_planet_name = next(iter(id_by_name.keys()))
        first_planet_id = id_by_name[first_planet_name]

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "game_state.db"
            store = SQLiteStore(str(db_path))

            report = MigrationReport()
            migrated_universe = migrate_universe_payload(
                {"planet_states": {first_planet_name: {"owner": "pilot"}}},
                id_by_name,
                report,
                "shared/universe_planets",
            )
            store.set_kv("shared", "universe_planets", migrated_universe)

            changed, migrated_commander = migrate_commander_payload(
                {
                    "account_name": "pilot",
                    "character_name": "pilot",
                    "current_planet_name": first_planet_name,
                    "player": {"name": "Pilot"},
                },
                id_by_name,
                report,
                "characters/pilot/pilot",
            )
            self.assertTrue(changed)
            store.upsert_account_payload("pilot", {"account_name": "pilot", "password_hash": "x"})
            store.upsert_character_payload("pilot", "pilot", migrated_commander, "Pilot")

            round_trip_universe = store.get_kv("shared", "universe_planets", default={})
            round_trip_commander = store.get_character_payload("pilot", "pilot")
            store.close()

        self.assertIn(str(first_planet_id), round_trip_universe.get("planet_states", {}))
        self.assertEqual(round_trip_commander.get("current_planet_id"), first_planet_id)


if __name__ == "__main__":
    unittest.main()
