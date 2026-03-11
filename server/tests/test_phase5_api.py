import asyncio
import os
import random
import sys
import tempfile
import unittest


SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from sqlite_store import SQLiteStore
from game_manager_modules.polished_api import PolishedApiMixin


class _Planet:
    def __init__(self, planet_id, name):
        self.planet_id = int(planet_id)
        self.name = str(name)
        self.owner = None
        self.credit_balance = 0


class _Ship:
    def __init__(self):
        self.model = "Scout"


class _Player:
    def __init__(self, name):
        self.name = str(name)
        self.owned_planets = {}
        self.credits = 5000
        self.spaceship = _Ship()


class _FakeGM(PolishedApiMixin):
    RESOURCE_TYPES = ("fuel", "ore", "tech", "bio", "rare")

    def __init__(self, store):
        self.store = store
        self.player = _Player("PilotOne")
        self.planets = [_Planet(1, "Aether"), _Planet(2, "Titan")]
        self._dirty_count = 0
        self._rotation_called = 0

    def get_planet_by_id(self, planet_id):
        pid = int(planet_id or 0)
        for planet in self.planets:
            if int(planet.planet_id) == pid:
                return planet
        return None

    def mark_state_dirty(self):
        self._dirty_count += 1
        return self._dirty_count

    def trade_with_planet(self, player_id, planet_id, trade_action, resource_type, amount):
        qty = int(max(1, amount or 1))
        unit_price = 10
        total = qty * unit_price
        current_credits = int(self.store.get_player_resource_amount(player_id, "credits") or 0)
        current_resource = int(self.store.get_player_resource_amount(player_id, resource_type) or 0)

        if str(trade_action).upper() == "BUY":
            if current_credits < total:
                return False, "INSUFFICIENT CREDITS"
            self.store.upsert_player_resource(player_id, "credits", current_credits - total)
            self.store.upsert_player_resource(player_id, resource_type, current_resource + qty)
            self.player.credits = current_credits - total
            return True, "BUY OK"

        if current_resource < qty:
            return False, "INSUFFICIENT RESOURCE"
        self.store.upsert_player_resource(player_id, resource_type, current_resource - qty)
        self.store.upsert_player_resource(player_id, "credits", current_credits + total)
        self.player.credits = current_credits + total
        return True, "SELL OK"

    def _apply_market_rotation_if_due(self):
        self._rotation_called += 1

    def produce_resources(self):
        return True, "PRODUCED"

    def payout_resource_interest(self):
        return True, "INTEREST"


class Phase5ApiTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "phase5_test.db")
        self.store = SQLiteStore(self.db_path)
        self.gm = _FakeGM(self.store)

        self.store.upsert_player_row(1, "PilotOne", credits=5000, commander_rank=1, owned_ships=[])
        self.store.upsert_player_row(2, "PilotTwo", credits=5000, commander_rank=1, owned_ships=[])
        self.store.upsert_player_resource(1, "credits", 5000)
        self.store.upsert_player_resource(2, "credits", 5000)
        for r in ("fuel", "ore", "tech", "bio", "rare"):
            self.store.upsert_player_resource(1, r, 50)
            self.store.upsert_player_resource(2, r, 50)

    def tearDown(self):
        try:
            self.store.close()
        finally:
            self._tmp.cleanup()

    def test_01_phase5_tables_exist(self):
        names = {
            row["name"]
            for row in self.store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        self.assertIn("planets", names)
        self.assertIn("players", names)
        self.assertIn("combat_sessions", names)
        self.assertIn("game_state", names)

    def test_02_planets_index_exists(self):
        names = {
            row["name"]
            for row in self.store.conn.execute(
                "SELECT name FROM sqlite_master WHERE type='index'"
            ).fetchall()
        }
        self.assertIn("idx_planets_owner_id", names)

    def test_03_upsert_planet_row_roundtrip(self):
        self.store.upsert_planet_row(1, "Aether", owner_id=1, credit_balance=123)
        planets = self.store.list_planets_rows()
        row = next(p for p in planets if int(p["planet_id"]) == 1)
        self.assertEqual(row["owner_id"], 1)
        self.assertEqual(row["credit_balance"], 123)

    def test_04_player_name_lookup_prefers_players_table(self):
        self.store.upsert_player_row(55, "FromPlayers", credits=1, commander_rank=1, owned_ships=[])
        self.assertEqual(self.store.get_player_name_by_id(55), "FromPlayers")

    def test_05_game_state_set_get(self):
        self.store.set_game_state_value("turn_number", 7)
        self.assertEqual(self.store.get_game_state_value("turn_number"), 7)

    def test_06_create_get_update_combat_session(self):
        cid = self.store.create_combat_session(1, 2, [{"ship_id": "a"}], [{"ship_id": "d"}])
        self.assertGreater(cid, 0)
        before = self.store.get_combat_session(cid)
        self.assertEqual(before["status"], "active")
        self.store.update_combat_session(cid, 1, [{"ship_id": "a2"}], [{"ship_id": "d2"}], "won")
        after = self.store.get_combat_session(cid)
        self.assertEqual(after["round_number"], 1)
        self.assertEqual(after["status"], "won")

    def test_07_claim_planet_success(self):
        result = asyncio.run(self.gm.claim_planet(1, 1))
        self.assertTrue(result["success"])
        planets = self.store.list_planets_rows()
        row = next(p for p in planets if int(p["planet_id"]) == 1)
        self.assertEqual(row["owner_id"], 1)

    def test_08_claim_planet_invalid_planet(self):
        result = asyncio.run(self.gm.claim_planet(1, 999))
        self.assertFalse(result["success"])

    def test_09_process_trade_invalid_resource(self):
        result = asyncio.run(self.gm.process_trade(1, 1, "widgets", 3, True))
        self.assertFalse(result["success"])

    def test_10_process_trade_buy(self):
        before_credits = self.store.get_player_resource_amount(1, "credits")
        before_ore = self.store.get_player_resource_amount(1, "ore")
        result = asyncio.run(self.gm.process_trade(1, 1, "ore", 2, True))
        self.assertTrue(result["success"])
        self.assertLess(self.store.get_player_resource_amount(1, "credits"), before_credits)
        self.assertGreater(self.store.get_player_resource_amount(1, "ore"), before_ore)

    def test_11_process_trade_sell(self):
        before_credits = self.store.get_player_resource_amount(1, "credits")
        before_ore = self.store.get_player_resource_amount(1, "ore")
        result = asyncio.run(self.gm.process_trade(1, 1, "ore", 2, False))
        self.assertTrue(result["success"])
        self.assertGreater(self.store.get_player_resource_amount(1, "credits"), before_credits)
        self.assertLess(self.store.get_player_resource_amount(1, "ore"), before_ore)

    def test_12_start_combat_returns_id(self):
        combat_id = asyncio.run(
            self.gm.start_combat(
                1,
                2,
                [{"ship_id": "alpha", "hp": 100, "shields": 50, "tactic": "flank"}],
            )
        )
        self.assertGreater(combat_id, 0)

    def test_13_start_combat_enforces_minimum_ships(self):
        combat_id = asyncio.run(self.gm.start_combat(1, 2, [{"ship_id": "solo"}]))
        row = self.store.get_combat_session(combat_id)
        self.assertGreaterEqual(len(row["attacker_ships"]), 3)

    def test_14_combat_round_missing_session(self):
        result = asyncio.run(self.gm.combat_round(9999))
        self.assertFalse(result["success"])

    def test_15_combat_round_advances_round_number(self):
        random.seed(3)
        combat_id = asyncio.run(
            self.gm.start_combat(
                1,
                2,
                [{"ship_id": "a1", "hp": 100, "shields": 50, "tactic": "full burn"}],
            )
        )
        result = asyncio.run(self.gm.combat_round(combat_id))
        self.assertTrue(result["success"])
        self.assertEqual(result["state"]["round_number"], 1)

    def test_16_combat_resolves_within_six_rounds(self):
        random.seed(5)
        combat_id = asyncio.run(
            self.gm.start_combat(
                1,
                2,
                [{"ship_id": "a1", "hp": 80, "shields": 40, "tactic": "flank"}],
            )
        )
        final = None
        for _ in range(6):
            final = asyncio.run(self.gm.combat_round(combat_id))
            if final["state"]["status"] != "active":
                break
        self.assertIn(final["state"]["status"], {"won", "lost", "draw"})

    def test_17_combat_loot_transfers_on_resolution(self):
        random.seed(9)
        self.store.upsert_player_row(1, "PilotOne", credits=7000, commander_rank=1, owned_ships=[])
        self.store.upsert_player_row(2, "PilotTwo", credits=7000, commander_rank=1, owned_ships=[])
        combat_id = self.store.create_combat_session(
            1,
            2,
            [{"ship_id": "atk", "hp": 120, "shields": 100, "tactic": "full burn"}],
            [{"ship_id": "def", "hp": 1, "shields": 0, "tactic": "shield up"}],
            status="active",
            round_number=0,
        )
        asyncio.run(self.gm.combat_round(combat_id))
        p1 = self.store.get_player_row(1)
        p2 = self.store.get_player_row(2)
        self.assertNotEqual(int(p1["credits"]), int(p2["credits"]))

    def test_18_daily_economy_tick_increments_turn(self):
        first = asyncio.run(self.gm.daily_economy_tick())
        second = asyncio.run(self.gm.daily_economy_tick())
        self.assertEqual(first["turn_number"], 1)
        self.assertEqual(second["turn_number"], 2)

    def test_19_daily_economy_tick_calls_market_rotation(self):
        self.assertEqual(self.gm._rotation_called, 0)
        asyncio.run(self.gm.daily_economy_tick())
        self.assertEqual(self.gm._rotation_called, 1)

    def test_20_get_full_state_has_required_sections(self):
        state = self.gm.get_full_state()
        self.assertIn("planets", state)
        self.assertIn("players", state)
        self.assertIn("combat_sessions", state)
        self.assertIn("game_state", state)

    def test_21_list_player_rows_returns_inserted_players(self):
        rows = self.store.list_player_rows()
        ids = {int(row["player_id"]) for row in rows}
        self.assertIn(1, ids)
        self.assertIn(2, ids)

    def test_22_get_all_game_state_roundtrip(self):
        self.store.set_game_state_value("victory_threshold", 35)
        all_state = self.store.get_all_game_state()
        self.assertEqual(int(all_state.get("victory_threshold", 0)), 35)


if __name__ == "__main__":
    unittest.main()
