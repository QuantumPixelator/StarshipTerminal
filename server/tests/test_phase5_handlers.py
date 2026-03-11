import asyncio
import os
import sys
import tempfile
import unittest


SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from sqlite_store import SQLiteStore
from handlers.phase5_api import register


class _FakeGM:
    def __init__(self, store):
        self.store = store
        self._dirty = 0
        self._combat_started = []
        self._reset_calls = []
        self._tick_calls = 0

    async def claim_planet(self, player_id: int, planet_id: int) -> dict:
        return {
            "success": True,
            "player_id": int(player_id),
            "planet_id": int(planet_id),
        }

    async def process_trade(self, player_id: int, planet_id: int, item: str, qty: int, buy: bool) -> dict:
        return {
            "success": True,
            "player_id": int(player_id),
            "planet_id": int(planet_id),
            "item": str(item),
            "qty": int(qty),
            "buy": bool(buy),
        }

    async def start_combat(self, attacker_id: int, defender_id: int, attacker_fleet: list) -> int:
        self._combat_started.append((int(attacker_id), int(defender_id), list(attacker_fleet or [])))
        return 777

    async def combat_round(self, combat_id: int) -> dict:
        return {"success": True, "combat_id": int(combat_id), "state": {"status": "active"}}

    async def daily_economy_tick(self):
        self._tick_calls += 1
        return {"success": True, "turn_number": self._tick_calls}

    def get_full_state(self) -> dict:
        return {"planets": [], "players": [], "combat_sessions": [], "game_state": {}}

    def reset_current_campaign(self, reason="admin"):
        self._reset_calls.append(str(reason))
        return True, "RESET OK"

    def mark_state_dirty(self):
        self._dirty += 1

    def _upsert_player_row_from_runtime(self, player_id):
        self.store.upsert_player_row(int(player_id), f"Player{int(player_id)}", credits=0, commander_rank=1, owned_ships=[])


class Phase5HandlerTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self._tmp.name, "phase5_handlers_test.db")
        self.store = SQLiteStore(self.db_path)
        self.gm = _FakeGM(self.store)
        self.dispatch = register()

    def tearDown(self):
        try:
            self.store.close()
        finally:
            self._tmp.cleanup()

    def test_01_register_contains_phase5_actions(self):
        for action in (
            "claim_planet",
            "process_trade",
            "start_combat",
            "combat_round",
            "daily_economy_tick",
            "get_full_state",
            "reset_campaign",
            "force_combat",
            "give_credits",
            "admin_command",
        ):
            self.assertIn(action, self.dispatch)

    def test_02_claim_planet_handler(self):
        result = asyncio.run(self.dispatch["claim_planet"](None, None, self.gm, {"player_id": 3, "planet_id": 9}))
        self.assertTrue(result["success"])
        self.assertEqual(result["player_id"], 3)
        self.assertEqual(result["planet_id"], 9)

    def test_03_force_combat_handler_starts_session(self):
        result = asyncio.run(self.dispatch["force_combat"](None, None, self.gm, {"attacker_id": 1, "defender_id": 2}))
        self.assertTrue(result["success"])
        self.assertEqual(result["combat_id"], 777)
        self.assertEqual(len(self.gm._combat_started), 1)

    def test_04_give_credits_handler_updates_store(self):
        self.store.upsert_player_row(5, "PilotFive", credits=1000, commander_rank=1, owned_ships=[])
        result = asyncio.run(self.dispatch["give_credits"](None, None, self.gm, {"player_id": 5, "amount": 250}))
        self.assertTrue(result["success"])
        row = self.store.get_player_row(5)
        self.assertEqual(int(row["credits"]), 1250)

    def test_05_admin_command_routes_to_reset_campaign(self):
        result = asyncio.run(self.dispatch["admin_command"](None, None, self.gm, {"command": "/reset_campaign"}))
        self.assertTrue(result["success"])
        self.assertEqual(self.gm._reset_calls, ["admin_command"])

    def test_06_admin_command_routes_to_force_combat(self):
        result = asyncio.run(self.dispatch["admin_command"](None, None, self.gm, {"command": "/force_combat 11 22"}))
        self.assertTrue(result["success"])
        self.assertEqual(result["combat_id"], 777)
        self.assertEqual(self.gm._combat_started[0][0], 11)
        self.assertEqual(self.gm._combat_started[0][1], 22)

    def test_07_admin_command_routes_to_give_credits(self):
        self.store.upsert_player_row(7, "PilotSeven", credits=600, commander_rank=1, owned_ships=[])
        result = asyncio.run(self.dispatch["admin_command"](None, None, self.gm, {"command": "/give_credits 7 400"}))
        self.assertTrue(result["success"])
        row = self.store.get_player_row(7)
        self.assertEqual(int(row["credits"]), 1000)

    def test_08_admin_command_unknown(self):
        result = asyncio.run(self.dispatch["admin_command"](None, None, self.gm, {"command": "/unknown"}))
        self.assertFalse(result["success"])


if __name__ == "__main__":
    unittest.main()
