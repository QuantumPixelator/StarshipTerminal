import os
import sys
import unittest


SERVER_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if SERVER_DIR not in sys.path:
    sys.path.insert(0, SERVER_DIR)

from handlers import (
    auth_session,
    banking,
    combat,
    economy,
    factions,
    messaging,
    misc,
    navigation,
    player_info,
    ship_ops,
)


class _Ship:
    def __init__(self):
        self.fuel = 50
        self.last_refuel_time = None
        self.integrity = 100
        self.model = "Scout"


class _Player:
    def __init__(self):
        self.name = "Tester"
        self.credits = 1000
        self.bank_balance = 200
        self.inventory = {"ore": 3}
        self.spaceship = _Ship()
        self.messages = []

    def delete_message(self, _msg_id):
        return None


class _Planet:
    def __init__(self):
        self.name = "Aether"
        self.planet_id = 1
        self.credit_balance = 500
        self.x = 0
        self.y = 0
        self.tech_level = 1
        self.government = "Federation"


class _FakeGM:
    def __init__(self):
        self.player = _Player()
        self.current_planet = _Planet()
        self.planets = [self.current_planet]
        self.known_planets = [self.current_planet]
        self.spaceships = [type("S", (), {"model": "Scout"})()]
        self.config = {"server_port": 8765}

    def record_analytics_event(self, **kwargs):
        return None

    def trade_item(self, item_name, action, quantity):
        return True, f"{action}:{item_name}:{quantity}"

    def get_planet_by_id(self, _planet_id):
        return None

    def get_planet_by_name(self, _planet_name):
        return self.current_planet

    def resolve_planet_from_params(self, _params, default_current=True):
        if _params.get("force_missing"):
            return None
        return self.current_planet if default_current else None

    def warp_to_planet(self, planet_name):
        if not planet_name:
            return False, "invalid"
        return True, "ok"

    def travel_to_planet(self, target_idx, skip_travel_event=False, travel_event_message=None):
        return True, f"travel:{target_idx}"

    def dock_current_planet(self):
        return True, "dock"

    def undock_current_planet(self):
        return True, "undock"

    def roll_travel_event_payload(self, target_planet, dist):
        return {"planet": target_planet.name, "dist": float(dist)}

    def resolve_travel_event_payload(self, event_payload, choice):
        return f"resolved:{choice}"

    def get_orbit_targets(self):
        return []

    def start_combat_session(self, target):
        return True, "combat", {"id": 1, "target": target}

    def resolve_combat_round(self, session_data, player_committed):
        return True, "round", {"id": 1, "committed": int(player_committed)}

    def flee_combat_session(self, session_data):
        return None

    def should_initialize_planet_auto_combat(self, planet):
        return False, "noop"

    def _adjust_authority_standing(self, delta):
        return int(delta)

    def _adjust_frontier_standing(self, delta):
        return int(delta)

    def check_barred(self, planet_id):
        return False, f"{planet_id}"

    def bar_player(self, planet_id):
        return None

    def get_planet_event(self, planet_name):
        return {"planet": planet_name}

    def is_planet_hostile_market(self, planet_name):
        return False

    def get_planet_price_penalty_seconds_remaining(self, planet_name):
        return 0

    def has_unseen_galactic_news(self, lookback_days=None):
        return True

    def get_unseen_galactic_news(self, lookback_days=None):
        return []

    def mark_galactic_news_seen(self):
        return None

    def send_message(self, recipient, subject, body, sender_name=None):
        return True, "ok"

    def gift_cargo_to_orbit_target(self, target_data, item_name, qty):
        return True, "gifted"

    def transfer_fighters(self, quantity, action):
        return True, f"{action}:{quantity}"

    def transfer_shields(self, quantity, action):
        return True, f"{action}:{quantity}"

    def save_game(self, force=False):
        return True

    def list_saves(self):
        return ["TESTER"]

    def get_player_info(self):
        return {
            "name": self.player.name,
            "credits": self.player.credits,
            "ship": self.player.spaceship.model,
            "location": self.current_planet.name,
            "bank_balance": self.player.bank_balance,
        }

    def get_current_planet_info(self):
        return {
            "name": self.current_planet.name,
            "description": "desc",
            "tech_level": self.current_planet.tech_level,
            "government": self.current_planet.government,
            "population": 1,
            "special_resources": "none",
        }

    def get_docking_fee(self, planet, ship):
        return 12

    def get_winner_board(self):
        return []

    def get_all_commander_statuses(self):
        return []


class _FakeServer:
    def _serialize_player(self, _gm):
        return {"name": "Tester"}

    def _serialize_planet(self, planet):
        return {"name": getattr(planet, "name", "")}

    def _get_presence_alerts_since(self, _since_ts):
        return []

    def _get_economy_alerts_since(self, _since_ts):
        return []

    def _build_asset_sync_payload(self, manifest):
        return [], [], dict(manifest or {})


class _FakeSession:
    def __init__(self):
        self._account_safe = None

    def get_effective_buy_price(self, item_name, base_price, planet_name):
        return int(float(base_price))

    def get_item_market_snapshot(self, item_name):
        return {"item": item_name}

    def get_best_trade_opportunities(self, from_planet, limit):
        return [{"from": from_planet, "limit": int(limit)}]

    def get_contraband_market_context(self, item_name, planet_name, quantity):
        return {"item": item_name, "planet": planet_name, "qty": int(quantity)}

    def buy_fuel(self, amount):
        return True, f"bought {int(amount)}"

    def buy_ship(self, ship):
        self.player.spaceship = ship
        return True, "ok"

    def transfer_fighters(self, quantity, action):
        return True, f"{action}:{quantity}"

    def transfer_shields(self, quantity, action):
        return True, f"{action}:{quantity}"

    def install_ship_upgrade(self, item_name, quantity):
        return True, f"{item_name}:{quantity}"

    def bank_deposit(self, amount):
        return True, f"{amount}"

    def bank_withdraw(self, amount):
        return True, f"{amount}"

    def planet_deposit(self, amount):
        return True, f"{amount}"

    def planet_withdraw(self, amount):
        return True, f"{amount}"


class HandlerInputValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = _FakeGM()
        self.session = _FakeSession()
        self.server = _FakeServer()

    def test_banking_amount_validation(self):
        resp = banking._h_bank_deposit(None, None, self.gm, {"amount": "abc"})
        self.assertFalse(resp["success"])

        resp = banking._h_planet_withdraw(None, None, self.gm, {"amount": -3})
        self.assertFalse(resp["success"])

    def test_economy_item_and_quantity_validation(self):
        resp = economy._h_buy_item(None, None, self.gm, {"item": "", "quantity": 1})
        self.assertFalse(resp["success"])

        resp = economy._h_trade_item(
            None,
            None,
            self.gm,
            {"item_name": "ore", "action": "INVALID", "quantity": 2},
        )
        self.assertFalse(resp["success"])

        resp = economy._h_get_effective_buy_price(
            None,
            None,
            self.gm,
            {"item": "ore", "base_price": "bad"},
        )
        self.assertFalse(resp["success"])

    def test_ship_ops_validation(self):
        resp = ship_ops._h_buy_ship(None, None, self.gm, {"ship": ""})
        self.assertFalse(resp["success"])

        resp = ship_ops._h_transfer_fighters(None, None, self.gm, {"action": "TO_PLANET", "quantity": 2})
        self.assertTrue(resp["success"])

        resp = ship_ops._h_transfer_fighters(None, None, self.gm, {"action": "weird", "quantity": 2})
        self.assertFalse(resp["success"])

        resp = ship_ops._h_install_ship_upgrade(None, None, self.gm, {"item_name": "", "quantity": 1})
        self.assertFalse(resp["success"])

    def test_navigation_validation(self):
        resp = navigation._h_travel_to_planet(None, None, self.gm, {"target_planet_index": "bad"})
        self.assertFalse(resp["success"])

        resp = navigation._h_roll_travel_event_payload(None, None, self.gm, {"dist": "nanx"})
        self.assertFalse(resp["success"])

        resp = navigation._h_warp_to_planet(None, None, self.gm, {})
        self.assertFalse(resp["success"])

    def test_combat_validation(self):
        resp = combat._h_start_combat_session(None, None, self.gm, {"target": None})
        self.assertFalse(resp["success"])

        resp = combat._h_resolve_combat_round(None, None, self.gm, {"session": {}, "player_committed": "oops"})
        self.assertFalse(resp["success"])

        resp = combat._h_flee_combat_session(None, None, self.gm, {"session": None})
        self.assertFalse(resp["success"])

        resp = combat._h_should_initialize_planet_auto_combat(None, None, self.gm, {"planet": None})
        self.assertFalse(resp["success"])

    def test_factions_validation(self):
        resp = factions._h__adjust_authority_standing(None, None, self.gm, {"delta": "bad"})
        self.assertFalse(resp["success"])

        resp = factions._h_check_barred(None, None, self.gm, {"force_missing": True})
        self.assertFalse(resp["success"])

    def test_messaging_validation(self):
        resp = messaging._h_has_unseen_galactic_news(None, None, self.gm, {"lookback_days": "bad"})
        self.assertFalse(resp["success"])

        resp = messaging._h_delete_message(None, None, self.gm, {"msg_id": ""})
        self.assertFalse(resp["success"])

        resp = messaging._h_gift_cargo_to_orbit_target(None, None, self.gm, {"target_data": [], "item_name": "ore", "qty": 1})
        self.assertFalse(resp["success"])

    def test_auth_session_validation(self):
        resp = auth_session._h_save_game(None, self.session, None, {})
        self.assertFalse(resp["success"])

        resp = auth_session._h_list_saves(None, self.session, None, {})
        self.assertFalse(resp["success"])

    def test_player_info_validation(self):
        resp = player_info._h_get_docking_fee(self.server, None, self.gm, {"force_missing": True})
        self.assertFalse(resp["success"])

        resp = player_info._h_get_presence_alerts(self.server, None, self.gm, {"since_ts": "bad"})
        self.assertFalse(resp["success"])

        resp = player_info._h_get_economy_alerts(self.server, None, self.gm, {"since_ts": "bad"})
        self.assertFalse(resp["success"])

    def test_misc_validation(self):
        resp = misc._h_sync_assets(self.server, None, self.gm, {"manifest": []})
        self.assertFalse(resp["success"])

        def _raise_update():
            raise RuntimeError("boom")

        self.gm._update_planet_events = _raise_update
        resp = misc._h_get_all_planet_events(self.server, None, self.gm, {})
        self.assertFalse(resp["success"])


if __name__ == "__main__":
    unittest.main()
