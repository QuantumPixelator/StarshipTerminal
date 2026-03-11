import os
import sys
import tempfile
import unittest


SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from sqlite_store import SQLiteStore
from game_server_auth import GameServer
from game_manager_modules.economy import EconomyMixin


class _Ship:
    def __init__(self):
        self.model = "Scout"
        self.fuel = 40.0
        self.max_fuel = 80.0
        self.current_cargo_pods = 20


class _Player:
    def __init__(self):
        self.name = "Tester"
        self.credits = 5000
        self.spaceship = _Ship()
        self.owned_planets = {}


class _Planet:
    def __init__(self):
        self.planet_id = 1
        self.name = "Gas Haven"
        self.bank = True


class _FakeEconomyGM(EconomyMixin):
    def __init__(self, store):
        self.store = store
        self.player = _Player()
        self.current_planet = _Planet()
        self.planets = [self.current_planet]
        self.config = {
            "resource_interest_rate": 0.01,
            "economy_event_chance": 0.0,
            "market_update_interval_minutes": 20,
        }

    def _active_player_id(self):
        return 1

    def get_planet_by_id(self, planet_id):
        return self.current_planet if int(planet_id or 0) == 1 else None


class EconomySystemTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "test_game_state.db")
        self.store = SQLiteStore(self.db_path)

    def tearDown(self):
        try:
            self.store.close()
        finally:
            self._tmp.cleanup()

    def test_economy_alert_roundtrip(self):
        server = GameServer.__new__(GameServer)
        server.store = self.store
        server._presence_banner_seconds = lambda: 5.0

        GameServer._append_economy_alert(
            server,
            commander_name="Tester",
            event_name="resource_trade_buy",
            message="Purchased 3 ORE",
            resource_type="ore",
        )
        rows = GameServer._get_economy_alerts_since(server, 0.0, limit=8)

        self.assertGreaterEqual(len(rows), 1)
        latest = rows[-1]
        self.assertEqual(latest["commander"], "Tester")
        self.assertEqual(latest["event"], "resource_trade_buy")
        self.assertEqual(latest["resource"], "ore")

    def test_economy_seed_migration_populates_resources(self):
        account = "acct"
        character = "pilot"
        self.store.upsert_account_payload(account, {"password_hash": "x"})
        self.store.upsert_character_payload(
            account,
            character,
            {
                "account_name": account,
                "character_name": character,
                "player": {
                    "name": "Pilot",
                    "credits": 1234,
                    "spaceship": {
                        "model": "Scout",
                        "fuel": 44,
                        "max_fuel": 80,
                        "current_cargo": 20,
                    },
                },
            },
            display_name="Pilot",
        )
        self.store.set_kv(
            "shared",
            "universe_planets",
            {
                "1": {"name": "Gas Haven"},
            },
        )

        result = self.store.migrate_economy_seed(dry_run=False)
        self.assertTrue(result.get("ok"))

        player_id = self.store.get_character_player_id(account, character)
        resources = self.store.get_player_resources(player_id)
        cargo = self.store.get_ship_cargo(player_id, "Scout")
        prices = self.store.get_market_prices(1)

        self.assertIn("credits", resources)
        self.assertEqual(int(resources["credits"]), 1234)
        self.assertIn("fuel", resources)
        self.assertIn("fuel", cargo)
        self.assertIn("fuel", prices.get(1, {}))

    def test_resource_trade_and_refuel_paths(self):
        gm = _FakeEconomyGM(self.store)

        self.store.upsert_player_resource(1, "credits", 5000)
        self.store.upsert_player_resource(1, "fuel", 40)
        self.store.upsert_player_resource(1, "ore", 25)
        self.store.upsert_player_resource(1, "tech", 10)
        self.store.upsert_player_resource(1, "bio", 10)
        self.store.upsert_player_resource(1, "rare", 5)

        self.store.upsert_ship_cargo(1, "Scout", "fuel", 40, 80)
        self.store.upsert_ship_cargo(1, "Scout", "ore", 25, 40)
        self.store.upsert_ship_cargo(1, "Scout", "tech", 10, 20)
        self.store.upsert_ship_cargo(1, "Scout", "bio", 10, 20)
        self.store.upsert_ship_cargo(1, "Scout", "rare", 5, 10)

        for r_key, price in {
            "fuel": 12.0,
            "ore": 18.0,
            "tech": 42.0,
            "bio": 24.0,
            "rare": 95.0,
        }.items():
            self.store.upsert_market_price(1, r_key, price)

        ok_buy, _ = gm.trade_with_planet(1, 1, "BUY", "ore", 3)
        self.assertTrue(ok_buy)
        self.assertGreaterEqual(self.store.get_player_resource_amount(1, "ore"), 28)

        ok_sell, _ = gm.trade_with_planet(1, 1, "SELL", "ore", 2)
        self.assertTrue(ok_sell)

        ok_refuel, _ = gm.refuel_ship(ship_id="Scout", planet_id=1, amount=10)
        self.assertTrue(ok_refuel)
        self.assertGreaterEqual(int(gm.player.spaceship.fuel), 50)


if __name__ == "__main__":
    unittest.main()
