"""
Starship Terminal Multiplayer Server
Handles all game logic, player sessions, and universe state.
"""

import asyncio
import base64
import hashlib
import json
import logging
import threading
import time
import websockets
import sys
import os
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from game_manager import GameManager
from sqlite_store import SQLiteStore


LOGGER = logging.getLogger("game_server.legacy")


SERVER_ROOT = Path(__file__).parent
SYNC_SUBDIRS = [
    SERVER_ROOT / "assets" / "texts",
    SERVER_ROOT / "assets" / "planets" / "backgrounds",
    SERVER_ROOT / "assets" / "planets" / "thumbnails",
]

MAX_SYNC_FILE_BYTES = 12_000_000
ASSET_SYNC_REFRESH_INTERVAL_S = 1.0
_ASSET_SYNC_CACHE = {
    "fingerprint": None,
    "entries": {},
    "manifest": {},
    "last_refresh": 0.0,
}
_ASSET_SYNC_LOCK = threading.RLock()


def _build_file_sha256(file_path: Path):
    digest = hashlib.sha256()
    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(8192)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


def _iter_sync_asset_files():
    for folder in SYNC_SUBDIRS:
        if not folder.exists():
            continue
        for root, _, files in os.walk(folder):
            for name in files:
                file_path = Path(root) / name
                rel = file_path.relative_to(SERVER_ROOT).as_posix()
                if not rel.startswith("assets/"):
                    continue
                yield file_path, rel


def _build_asset_fingerprint(files):
    return tuple(
        sorted(
            (
                rel_path,
                int(file_path.stat().st_size),
                int(file_path.stat().st_mtime_ns),
            )
            for file_path, rel_path in files
            if file_path.exists()
        )
    )


def _refresh_asset_sync_cache():
    if _DB_STORE is not None:
        try:
            _DB_STORE.export_catalog_texts_to_files(SERVER_ROOT / "assets" / "texts")
        except Exception:
            pass

    with _ASSET_SYNC_LOCK:
        now = time.perf_counter()
        has_manifest = bool(_ASSET_SYNC_CACHE.get("manifest"))
        if has_manifest and (
            now - float(_ASSET_SYNC_CACHE.get("last_refresh") or 0.0)
        ) < ASSET_SYNC_REFRESH_INTERVAL_S:
            return

        files = list(_iter_sync_asset_files())
        fingerprint = _build_asset_fingerprint(files)
        if fingerprint == _ASSET_SYNC_CACHE.get("fingerprint"):
            _ASSET_SYNC_CACHE["last_refresh"] = now
            return

        entries = {}
        manifest = {}
        for file_path, rel_path in files:
            try:
                if not file_path.exists():
                    continue
                file_hash = _build_file_sha256(file_path)
                manifest[rel_path] = file_hash

                content_b64 = None
                if file_path.stat().st_size <= MAX_SYNC_FILE_BYTES:
                    content_b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")

                entries[rel_path] = {
                    "sha256": file_hash,
                    "content_b64": content_b64,
                }
            except Exception:
                continue

        _ASSET_SYNC_CACHE["fingerprint"] = fingerprint
        _ASSET_SYNC_CACHE["entries"] = entries
        _ASSET_SYNC_CACHE["manifest"] = manifest
        _ASSET_SYNC_CACHE["last_refresh"] = now


def _build_asset_sync_payload(client_manifest):
    if not isinstance(client_manifest, dict):
        client_manifest = {}

    _refresh_asset_sync_cache()

    updates = []
    with _ASSET_SYNC_LOCK:
        server_manifest = dict(_ASSET_SYNC_CACHE.get("manifest") or {})
        entries = dict(_ASSET_SYNC_CACHE.get("entries") or {})

    for rel_path, entry in entries.items():
        file_hash = str(entry.get("sha256") or "")
        if not file_hash:
            continue
        if client_manifest.get(rel_path) == file_hash:
            continue

        content_b64 = entry.get("content_b64")
        if not content_b64:
            continue
        updates.append(
            {
                "path": rel_path,
                "sha256": file_hash,
                "content_b64": content_b64,
            }
        )

    deleted = [
        rel_path
        for rel_path in client_manifest.keys()
        if rel_path.startswith("assets/") and rel_path not in server_manifest
    ]

    return updates, deleted, server_manifest


class PlayerSession:
    """Manages a single player's game session."""

    def __init__(self, player_name, websocket):
        self.player_name = player_name
        self.websocket = websocket
        self.gm = GameManager()
        self.authenticated = False

    def login(self, player_name):
        """Load or create player save."""
        self.player_name = player_name

        safe_name = str(player_name or "guest").lower().replace(" ", "_")
        if _DB_STORE is not None:
            try:
                if _DB_STORE.is_account_blocked(safe_name):
                    account_payload = _DB_STORE.get_account_payload(safe_name)
                    if isinstance(account_payload, dict) and bool(
                        account_payload.get("blacklisted", False)
                    ):
                        return {
                            "success": False,
                            "message": "Account is blacklisted",
                            "isNewGame": False,
                        }
                    return {
                        "success": False,
                        "message": "Account is disabled",
                        "isNewGame": False,
                    }
            except Exception:
                LOGGER.warning("Account block check failed for '%s'", safe_name, exc_info=True)

        result = self.gm.load_game(player_name)

        if result and result[0]:
            self.authenticated = True
            return {
                "success": True,
                "message": f"Welcome back, {player_name}!",
                "isNewGame": False,
            }
        else:
            # Create new game
            self.gm.new_game(player_name)
            self.authenticated = True
            return {
                "success": True,
                "message": f"New commander profile created: {player_name}",
                "isNewGame": True,
            }

    async def handle_action(self, action, params):
        """
        Route action to appropriate GameManager method.
        This is the core dispatcher that translates network actions to game logic.
        """
        if not self.authenticated and action != "login":
            return {"success": False, "error": "Not authenticated"}

        try:
            # ========== AUTHENTICATION ==========
            if action == "login":
                player_name = params.get("player_name", "guest")
                return self.login(player_name)

            elif action == "sync_assets":
                client_manifest = params.get("manifest", {})
                updates, deleted, manifest = _build_asset_sync_payload(client_manifest)
                return {
                    "success": True,
                    "files": updates,
                    "deleted": deleted,
                    "manifest": manifest,
                }

            # ========== PLAYER INFO ==========
            elif action == "get_player_info":
                result = self.gm.get_player_info()
                if isinstance(result, dict):
                    data = {
                        "name": result.get("name", ""),
                        "credits": result.get("credits", 0),
                        "ship": result.get("ship", ""),
                        "location": result.get("location", ""),
                        "bank_balance": result.get("bank_balance", 0),
                    }
                else:
                    data = {
                        "name": result[0],
                        "credits": result[1],
                        "ship": result[2],
                        "location": result[3],
                        "bank_balance": result[4] if len(result) > 4 else 0,
                    }
                return {
                    "success": True,
                    "data": data,
                }

            elif action == "get_config":
                return {
                    "success": True,
                    "config": (
                        self.gm.config if isinstance(self.gm.config, dict) else {}
                    ),
                }

            # ========== PLANET INFO ==========
            elif action == "get_current_planet_info":
                result = self.gm.get_current_planet_info()
                if isinstance(result, dict):
                    data = {
                        "name": result.get("name", ""),
                        "description": result.get("description", ""),
                        "tech_level": result.get("tech_level", 0),
                        "government": result.get("government", ""),
                        "population": result.get("population", 0),
                        "special_resources": result.get("special_resources", ""),
                    }
                else:
                    data = {
                        "name": result[0],
                        "description": result[1],
                        "tech_level": result[2],
                        "government": result[3],
                        "population": result[4] if len(result) > 4 else 0,
                        "special_resources": result[5] if len(result) > 5 else "",
                    }
                return {
                    "success": True,
                    "data": data,
                }

            elif action == "get_docking_fee":
                planet = self.gm.resolve_planet_from_params(params, default_current=True)
                fee = self.gm.get_docking_fee(planet, self.gm.player.spaceship)
                return {"success": True, "fee": fee}

            # ========== TRADING ==========
            elif action == "trade_item":
                item_name = params.get("item_name")
                trade_action = params.get("action")  # "buy" or "sell"
                quantity = params.get("quantity", 1)

                success, msg = self.gm.trade_item(item_name, trade_action, quantity)

                return {
                    "success": success,
                    "message": msg,
                    "credits": self.gm.player.credits,
                    "cargo": [
                        (item.name, item.quantity) for item in self.gm.player.ship.cargo
                    ],
                }

            elif action == "buy_item":
                item_name = params.get("item")
                quantity = params.get("quantity", 1)
                result = self.gm.buy_item(item_name, quantity)
                return {
                    "success": result[0],
                    "message": result[1],
                    "credits": self.gm.player.credits,
                    "cargo": [
                        (item.name, item.quantity) for item in self.gm.player.ship.cargo
                    ],
                }

            elif action == "sell_item":
                item_name = params.get("item")
                quantity = params.get("quantity", 1)
                result = self.gm.sell_item(item_name, quantity)
                return {
                    "success": result[0],
                    "message": result[1],
                    "credits": self.gm.player.credits,
                    "cargo": [
                        (item.name, item.quantity) for item in self.gm.player.ship.cargo
                    ],
                }

            # ========== MARKET DATA ==========
            elif action == "get_market_sell_price":
                item_name = params.get("item")
                planet = self.gm.resolve_planet_from_params(params, default_current=True)
                planet_name = getattr(planet, "name", None)
                price = self.gm.get_market_sell_price(item_name, planet_name)
                return {"success": True, "price": price}

            elif action == "get_effective_buy_price":
                item_name = params.get("item")
                base_price = params.get("base_price")
                planet = self.gm.resolve_planet_from_params(params, default_current=True)
                planet_name = getattr(planet, "name", None)
                price = self.gm.get_effective_buy_price(
                    item_name, base_price, planet_name
                )
                return {"success": True, "price": price}

            elif action == "get_item_market_snapshot":
                item_name = params.get("item")
                snapshot = self.gm.get_item_market_snapshot(item_name)
                return {"success": True, "data": snapshot}

            elif action == "get_best_trade_opportunities":
                from_planet = params.get("from_planet") or self.gm.current_planet.name
                limit = params.get("limit", 5)
                routes = self.gm.get_best_trade_opportunities(from_planet, limit)
                return {"success": True, "routes": routes}

            elif action == "get_bribe_market_snapshot":
                planet = self.gm.resolve_planet_from_params(params, default_current=True)
                snapshot = self.gm.get_bribe_market_snapshot(
                    getattr(planet, "planet_id", None)
                )
                return {"success": True, "data": snapshot}

            elif action == "get_contraband_market_context":
                item_name = params.get("item")
                planet = self.gm.resolve_planet_from_params(params, default_current=True)
                planet_name = getattr(planet, "name", None)
                quantity = int(params.get("quantity", 1) or 1)
                context = self.gm.get_contraband_market_context(
                    item_name, planet_name, quantity
                )
                return {"success": True, "data": context}

            # ========== SHIP OPERATIONS ==========
            elif action == "buy_fuel":
                amount = params.get("amount", 10)
                success, msg = self.gm.buy_fuel(amount)
                if success:
                    return {
                        "success": True,
                        "message": str(msg),
                        "credits": self.gm.player.credits,
                        "fuel": self.gm.player.ship.fuel,
                        "last_refuel_time": self.gm.player.ship.last_refuel_time,
                    }
                else:
                    return {
                        "success": False,
                        "error": str(msg),
                    }

            elif action == "get_refuel_quote":
                quote = self.gm.get_refuel_quote()
                return {"success": True, "quote": quote}

            elif action == "repair_hull":
                success, msg = self.gm.repair_hull()
                return {
                    "success": success,
                    "message": msg,
                    "credits": self.gm.player.credits if success else None,
                    "hull_integrity": (
                        self.gm.player.ship.hull_integrity if success else None
                    ),
                }

            elif action == "buy_ship":
                ship_name = params.get("ship")
                success, msg = self.gm.buy_ship(ship_name)
                return {
                    "success": success,
                    "message": msg,
                    "credits": self.gm.player.credits if success else None,
                    "ship": self.gm.player.spaceship if success else None,
                }

            elif action == "transfer_fighters":
                action_type = params.get("action")  # "load" or "unload"
                quantity = params.get("quantity", 1)
                success, msg = self.gm.transfer_fighters(quantity, action_type)
                return {"success": success, "message": msg}

            elif action == "transfer_shields":
                action_type = params.get("action")  # "load" or "unload"
                quantity = params.get("quantity", 1)
                success, msg = self.gm.transfer_shields(quantity, action_type)
                return {"success": success, "message": msg}

            elif action == "install_ship_upgrade":
                item_name = params.get("item_name")
                quantity = params.get("quantity", 1)
                success, msg = self.gm.install_ship_upgrade(item_name, quantity)
                return {
                    "success": success,
                    "message": msg,
                    "ship": self.gm.player.spaceship if success else None,
                    "inventory": self.gm.player.inventory if success else None
                }

            elif action == "check_auto_refuel":
                self.gm.check_auto_refuel()
                return {"success": True}

            # ========== NAVIGATION ==========
            elif action == "warp_to_planet":
                target_planet = self.gm.resolve_planet_from_params(params, default_current=False)
                planet_name = getattr(target_planet, "name", None)
                success, msg = self.gm.warp_to_planet(planet_name)
                return {"success": success, "message": msg}

            elif action == "get_known_planets":
                planets = [
                    (p.name, p.x, p.y, p.tech_level, p.government)
                    for p in self.gm.known_planets
                ]
                return {"success": True, "planets": planets}

            # ========== COMBAT ==========
            elif action == "get_orbit_targets":
                targets = self.gm.get_orbit_targets()
                return {"success": True, "targets": targets}

            elif action == "start_combat_session":
                target = params.get("target")
                session = self.gm.start_combat_session(target)
                return {"success": True, "session": session}

            elif action == "flee_combat_session":
                session_data = params.get("session")
                success, msg, updated_session = self.gm.flee_combat_session(session_data)
                return {"success": success, "message": msg, "session": updated_session}

            elif action == "should_initialize_planet_auto_combat":
                planet = params.get("planet")
                triggered, msg = self.gm.should_initialize_planet_auto_combat(planet)
                return {"success": True, "triggered": triggered, "message": msg}

            # ========== BANKING ==========
            elif action == "bank_deposit":
                amount = params.get("amount")
                success, msg = self.gm.bank_deposit(amount)
                return {
                    "success": success,
                    "message": msg,
                    "credits": self.gm.player.credits if success else None,
                    "bank_balance": self.gm.player.bank_balance if success else None,
                }

            elif action == "bank_withdraw":
                amount = params.get("amount")
                success, msg = self.gm.bank_withdraw(amount)
                return {
                    "success": success,
                    "message": msg,
                    "credits": self.gm.player.credits if success else None,
                    "bank_balance": self.gm.player.bank_balance if success else None,
                }

            elif action == "payout_interest":
                success, msg = self.gm.payout_interest()
                return {"success": success, "message": msg}

            elif action == "get_planet_financials":
                data = self.gm.get_planet_financials()
                return {"success": True, "data": data}

            elif action == "planet_deposit":
                amount = params.get("amount")
                success, msg = self.gm.planet_deposit(amount)
                return {
                    "success": success,
                    "message": msg,
                    "credits": self.gm.player.credits if success else None,
                    "planet_balance": (
                        int(getattr(self.gm.current_planet, "credit_balance", 0))
                        if success and self.gm.current_planet
                        else None
                    ),
                }

            elif action == "planet_withdraw":
                amount = params.get("amount")
                success, msg = self.gm.planet_withdraw(amount)
                return {
                    "success": success,
                    "message": msg,
                    "credits": self.gm.player.credits if success else None,
                    "planet_balance": (
                        int(getattr(self.gm.current_planet, "credit_balance", 0))
                        if success and self.gm.current_planet
                        else None
                    ),
                }

            # ========== CREW ==========
            elif action == "get_planet_crew_offers":
                planet = params.get("planet") or self.gm.current_planet
                offers = self.gm.get_planet_crew_offers(planet)
                return {"success": True, "offers": offers}

            elif action == "process_crew_pay":
                success, msg = self.gm.process_crew_pay()
                return {"success": success, "message": msg}

            # ========== FACTION/REPUTATION ==========
            elif action == "get_authority_standing_label":
                label = self.gm.get_authority_standing_label()
                return {"success": True, "label": label}

            elif action == "get_frontier_standing_label":
                label = self.gm.get_frontier_standing_label()
                return {"success": True, "label": label}

            # ========== CONTRACTS ==========
            elif action == "get_active_trade_contract":
                contract = self.gm.get_active_trade_contract()
                return {"success": True, "contract": contract}

            elif action == "reroll_trade_contract":
                success, msg = self.gm.reroll_trade_contract()
                return {"success": success, "message": msg}

            # ========== CONTRABAND ==========
            elif action == "get_smuggling_item_names":
                items = self.gm.get_smuggling_item_names()
                return {"success": True, "items": items}

            elif action == "check_contraband_detection":
                detected, msg = self.gm.check_contraband_detection()
                return {"success": True, "detected": detected, "message": msg}

            elif action == "bribe_npc":
                success, msg = self.gm.bribe_npc()
                return {"success": success, "message": msg}

            elif action == "sell_non_market_cargo":
                success, msg = self.gm.sell_non_market_cargo()
                return {"success": success, "message": msg}

            # ========== PLANET MANAGEMENT ==========
            elif action == "check_barred":
                planet = self.gm.resolve_planet_from_params(params, default_current=True)
                planet_id = str(getattr(planet, "planet_id", ""))
                is_barred, msg = self.gm.check_barred(planet_id)
                return {"success": True, "is_barred": is_barred, "message": msg}

            elif action == "bar_player":
                planet = self.gm.resolve_planet_from_params(params, default_current=False)
                if planet:
                    self.gm.bar_player(str(getattr(planet, "planet_id", "")))
                return {"success": True}

            elif action == "get_planet_event":
                planet = self.gm.resolve_planet_from_params(params, default_current=True)
                planet_name = getattr(planet, "name", None)
                event = self.gm.get_planet_event(planet_name)
                return {"success": True, "event": event}

            elif action == "is_planet_hostile_market":
                planet = self.gm.resolve_planet_from_params(params, default_current=True)
                planet_name = getattr(planet, "name", None)
                is_hostile = self.gm.is_planet_hostile_market(planet_name)
                return {"success": True, "is_hostile": is_hostile}

            elif action == "get_planet_price_penalty_seconds_remaining":
                planet = self.gm.resolve_planet_from_params(params, default_current=True)
                planet_name = getattr(planet, "name", None)
                seconds = self.gm.get_planet_price_penalty_seconds_remaining(
                    planet_name
                )
                return {"success": True, "seconds": seconds}

            elif action == "get_current_port_spotlight_deal":
                deal = self.gm.get_current_port_spotlight_deal()
                return {"success": True, "deal": deal}

            elif action == "process_conquered_planet_defense_regen":
                success, msg = self.gm.process_conquered_planet_defense_regen()
                return {"success": success, "message": msg}

            # ========== COMMANDER ==========
            elif action == "process_commander_stipend":
                success, msg = self.gm.process_commander_stipend()
                return {"success": success, "message": msg}

            elif action == "has_unseen_galactic_news":
                lookback_days = params.get("lookback_days")
                has_unseen = self.gm.has_unseen_galactic_news(
                    lookback_days=lookback_days
                )
                return {"success": True, "has_unseen": bool(has_unseen)}

            elif action == "get_unseen_galactic_news":
                lookback_days = params.get("lookback_days")
                entries = self.gm.get_unseen_galactic_news(lookback_days=lookback_days)
                return {"success": True, "entries": entries}

            elif action == "mark_galactic_news_seen":
                self.gm.mark_galactic_news_seen()
                return {"success": True}

            # ========== MESSAGING ==========
            elif action == "send_message":
                recipient = params.get("recipient")
                message = params.get("message")
                success, msg = self.gm.send_message(recipient, message)
                return {"success": success, "message": msg}

            elif action == "get_other_players":
                others = self.gm.get_other_players()
                return {"success": True, "players": others}

            # ========== MISC ==========
            elif action == "claim_abandoned_ship":
                ship = params.get("ship")
                success, msg = self.gm.claim_abandoned_ship(ship)
                return {"success": success, "message": msg}

            elif action == "get_ship_level":
                ship_name = params.get("ship")
                level = self.gm.get_ship_level(ship_name)
                return {"success": True, "level": level}

            elif action == "_get_target_stats":
                session = params.get("session")
                shields, defenders, integrity = self.gm._get_target_stats(session)
                return {
                    "success": True,
                    "shields": shields,
                    "defenders": defenders,
                    "integrity": integrity,
                }

            elif action == "_load_shared_planet_states":
                self.gm._load_shared_planet_states()
                return {"success": True}

            # ========== SAVE/LOAD ==========
            elif action == "save_game":
                success = self.gm.save_game()
                return {
                    "success": success,
                    "message": "Game saved" if success else "Save failed",
                }

            elif action == "list_saves":
                saves = self.gm.list_saves()
                return {"success": True, "saves": saves}

            else:
                return {"success": False, "error": f"Unknown action: {action}"}

        except Exception as e:
            LOGGER.exception(
                "Action dispatch failure player='%s' action='%s'",
                str(self.player_name or ""),
                str(action or ""),
            )
            return {"success": False, "error": str(e)}


# Active sessions: websocket → PlayerSession
_DB_STORE = None


def _initialize_sqlite_store():
    global _DB_STORE
    if _DB_STORE is not None:
        return _DB_STORE

    save_dir = SERVER_ROOT / "saves"
    save_dir.mkdir(parents=True, exist_ok=True)
    db_path = save_dir / "game_state.db"
    _DB_STORE = SQLiteStore(str(db_path))
    _DB_STORE.migrate_json_saves_once(
        save_dir=str(save_dir),
        server_root=str(SERVER_ROOT),
    )
    return _DB_STORE


active_sessions = {}


async def handle_client(websocket, path=None):
    """Handle a single client connection."""
    session = None
    player_name = "Unknown"

    try:
        print(f"\n[CONNECT] New connection from {websocket.remote_address}")

        # Create session
        session = PlayerSession(None, websocket)
        active_sessions[websocket] = session

        # Message loop
        async for message in websocket:
            try:
                data = json.loads(message)
                action = data.get("action")
                params = data.get("params", {})

                if action == "login":
                    player_name = params.get("player_name", "guest")
                    print(f"[LOGIN] {player_name} attempting login...")

                # Execute action
                result = await session.handle_action(action, params)

                # Send response
                await websocket.send(json.dumps(result))

                if action == "login" and result.get("success"):
                    print(f"[SUCCESS] {player_name} logged in")

            except json.JSONDecodeError as e:
                LOGGER.warning(
                    "Invalid JSON received from %s: %s",
                    str(websocket.remote_address),
                    str(e),
                )
                await websocket.send(
                    json.dumps({"success": False, "error": f"Invalid JSON: {str(e)}"})
                )

    except websockets.exceptions.ConnectionClosed:
        print(f"[DISCONNECT] {player_name} disconnected")
    except Exception as e:
        LOGGER.exception("Client session failure for player='%s'", str(player_name or ""))
    finally:
        # Save on disconnect
        if session and session.authenticated:
            print(f"[SAVING] {player_name}'s game...")
            session.gm.save_game()

        # Remove session
        if websocket in active_sessions:
            del active_sessions[websocket]


async def main():
    """Start the server."""
    _initialize_sqlite_store()
    print("=" * 70)
    print(" " * 20 + "STARSHIP TERMINAL")
    print(" " * 18 + "MULTIPLAYER SERVER v1.0")
    print("=" * 70)
    print()
    print("  Server starting on ws://localhost:8765")
    print("  Waiting for client connections...")
    print()
    print("  Press Ctrl+C to stop the server")
    print()
    print("-" * 70)

    async with websockets.serve(handle_client, "0.0.0.0", 8765, max_size=None):
        await asyncio.Future()  # Run forever


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n[SHUTDOWN] Server shutting down...")
        print("[SAVING] Saving all active sessions...")
        for session in active_sessions.values():
            if session.authenticated:
                session.gm.save_game()
                print(f"  ✓ Saved {session.player_name}")
        print("\n[STOPPED] Server stopped cleanly.")
