"""
Network Client for Starship Terminal
Provides GameManager-compatible interface that communicates with remote server.
"""

import asyncio
import base64
import hashlib
import json
from pathlib import Path
import websockets
from typing import Any, Optional, Tuple, List
from classes import Spaceship, Player, Message, CrewMember


class NetworkClient:
    """
    Replacement for GameManager that routes all calls to remote server.

    This class maintains the same interface as GameManager so views don't need major changes.
    All methods that previously called self.gm.method() now call self.network.method().
    """

    def __init__(self, server_url: str = "ws://localhost:8765"):
        self.server_url = server_url
        self.websocket = None
        self.connected = False
        self.player_name = None
        self.account_name = None
        self._auth_password = None
        self.config = {}
        self.client_root = Path(__file__).parent
        self.asset_manifest_path = self.client_root / "assets" / "asset_manifest.json"

        # Cache for frequently accessed data
        self.player = None
        self.current_planet = None
        self.known_planets = []
        self.planets = []
        self.spaceships = []
        self.bribed_planets = set()
        self.planet_price_penalty_multiplier = None

    async def connect(self, player_name: str) -> bool:
        """Connect to server and authenticate."""
        try:
            if not self.websocket:
                self.websocket = await websockets.connect(
                    self.server_url, max_size=None
                )
                self.connected = True
            self.player_name = player_name

            # Send login
            result = await self._request("login", {"player_name": player_name})

            if result.get("success"):
                print(f"Connected to server: {result.get('message')}")
                await self._sync_assets_from_server()
                # Load initial data
                await self._refresh_player_data()
                await self._refresh_world_data()
                await self._refresh_config()
                return True
            else:
                print(f"Login failed: {result.get('error')}")
                return False

        except Exception as e:
            print(f"Connection failed: {e}")
            self.connected = False
            return False

    async def check_account(self, player_name: str) -> dict:
        """Check if a player account exists."""
        return await self._request("check_account", {"player_name": player_name})

    async def create_account(
        self, player_name: str, password: str, character_name: str | None = None
    ) -> dict:
        """Create a new player account with password."""
        result = await self._request(
            "create_account",
            {
                "player_name": player_name,
                "password": password,
                "character_name": character_name or player_name,
            },
        )
        if result.get("success"):
            self.player_name = player_name
            self.account_name = player_name
            self._auth_password = password
            await self._sync_assets_from_server()
            await self._refresh_player_data()
            await self._refresh_world_data()
            await self._refresh_config()
        return result

    async def authenticate(self, player_name: str, password: str) -> dict:
        """Authenticate with existing account."""
        result = await self._request(
            "authenticate", {"player_name": player_name, "password": password}
        )
        if result.get("success"):
            self.player_name = player_name
            self.account_name = player_name
            self._auth_password = password
            await self._sync_assets_from_server()
            # Always fetch config so the UI (e.g. CharacterSelectView) knows settings.
            await self._refresh_config()
            if not bool(result.get("requires_character_select", False)):
                await self._refresh_player_data()
                await self._refresh_world_data()
        return result

    async def list_characters(self) -> List[dict]:
        """Get characters linked to authenticated account."""
        account_name = self.account_name or self.player_name or ""
        result = await self._request("list_characters", {"account_name": account_name})
        if result.get("success"):
            return list(result.get("characters", []) or [])
        message = str(result.get("message") or result.get("error") or "").strip()
        raise RuntimeError(message or "Failed to list characters")

    async def select_character(self, character_name: str) -> Tuple[bool, str]:
        """Select/load a character for the authenticated account."""
        result = await self._request(
            "select_character", {"character_name": character_name}
        )
        if result.get("success"):
            await self._refresh_player_data()
            await self._refresh_world_data()
            await self._refresh_config()
        return (result.get("success", False), str(result.get("message", "")))

    async def _refresh_config(self):
        """Refresh server config snapshot used by UI defaults."""
        result = await self._request("get_config")
        if result.get("success") and isinstance(result.get("config"), dict):
            self.config = result.get("config")
            if "planet_price_penalty_multiplier" in self.config:
                self.planet_price_penalty_multiplier = float(
                    self.config.get("planet_price_penalty_multiplier")
                )

    def _build_spaceship(self, payload: dict) -> Spaceship:
        ship_data = payload or {}
        ship = Spaceship(
            model=ship_data.get("model", "Independence"),
            cost=int(ship_data.get("cost", 0)),
            starting_cargo_pods=int(ship_data.get("starting_cargo_pods", 10)),
            starting_shields=int(ship_data.get("starting_shields", 20)),
            starting_defenders=int(ship_data.get("starting_defenders", 5)),
            max_cargo_pods=int(ship_data.get("max_cargo_pods", 20)),
            max_shields=int(ship_data.get("max_shields", 100)),
            max_defenders=int(ship_data.get("max_defenders", 20)),
            special_weapon=ship_data.get("special_weapon"),
            integrity=int(
                ship_data.get("max_integrity", ship_data.get("integrity", 100))
            ),
            role_tags=ship_data.get("role_tags", []),
            module_slots=int(ship_data.get("module_slots", 1)),
            installed_modules=ship_data.get("installed_modules", []),
        )
        ship.current_cargo_pods = int(
            ship_data.get("current_cargo_pods", ship.current_cargo_pods)
        )
        ship.current_shields = int(
            ship_data.get("current_shields", ship.current_shields)
        )
        ship.current_defenders = int(
            ship_data.get("current_defenders", ship.current_defenders)
        )
        ship.integrity = int(ship_data.get("integrity", ship.integrity))
        ship.max_integrity = int(ship_data.get("max_integrity", ship.max_integrity))
        ship.fuel = float(ship_data.get("fuel", ship.fuel))
        ship.max_fuel = float(ship_data.get("max_fuel", ship.max_fuel))
        ship.fuel_burn_rate = float(
            ship_data.get("fuel_burn_rate", ship.fuel_burn_rate)
        )
        ship.last_refuel_time = float(ship_data.get("last_refuel_time", 0.0))
        ship.crew_slots = dict(
            ship_data.get("crew_slots", ship.crew_slots) or ship.crew_slots
        )
        return ship

    def _build_player(self, payload: dict) -> Player:
        player_data = payload or {}
        ship = self._build_spaceship(player_data.get("spaceship", {}))
        player = Player(
            player_data.get("name", self.player_name or "Commander"),
            ship,
            credits=int(player_data.get("credits", 0)),
        )
        player.bank_balance = int(player_data.get("bank_balance", 0))
        player.inventory = dict(player_data.get("inventory", {}) or {})
        player.owned_planets = dict(player_data.get("owned_planets", {}) or {})
        player.barred_planets = dict(player_data.get("barred_planets", {}) or {})
        player.attacked_planets = dict(player_data.get("attacked_planets", {}) or {})
        player.authority_standing = int(
            player_data.get(
                "authority_standing", player_data.get("sector_reputation", 0)
            )
        )
        player.frontier_standing = int(player_data.get("frontier_standing", 0))
        player.sector_reputation = int(
            player_data.get("sector_reputation", player.authority_standing)
        )
        player.combat_win_streak = int(player_data.get("combat_win_streak", 0))
        player.contract_chain_streak = int(player_data.get("contract_chain_streak", 0))
        player.last_special_weapon_time = float(
            player_data.get("last_special_weapon_time", 0.0)
        )

        player.crew = {}
        for specialty, member_data in (player_data.get("crew", {}) or {}).items():
            crew_member = CrewMember(
                name=member_data.get("name", str(specialty).title()),
                specialty=member_data.get("specialty", specialty),
                level=int(member_data.get("level", 1)),
            )
            crew_member.morale = int(member_data.get("morale", crew_member.morale))
            crew_member.fatigue = int(member_data.get("fatigue", crew_member.fatigue))
            crew_member.xp = int(member_data.get("xp", crew_member.xp))
            crew_member.perks = list(
                member_data.get("perks", crew_member.perks) or crew_member.perks
            )
            player.crew[str(specialty)] = crew_member

        player.messages = []
        for message_data in list(player_data.get("messages", []) or []):
            message = Message(
                sender=message_data.get("sender", ""),
                recipient=message_data.get("recipient", player.name),
                subject=message_data.get("subject", ""),
                body=message_data.get("body", ""),
                timestamp=message_data.get("timestamp"),
                is_read=bool(message_data.get("is_read", False)),
                is_saved=bool(message_data.get("is_saved", False)),
                msg_id=message_data.get("msg_id"),
            )
            player.messages.append(message)
        return player

    def _build_planet(self, payload: dict):
        from types import SimpleNamespace

        planet_data = payload or {}
        npc_remarks = list(planet_data.get("npc_remarks", []) or [])
        if not npc_remarks:
            npc_remarks = ["Good day.", "What do you need?", "Let's trade."]
        smuggling_inventory = dict(planet_data.get("smuggling_inventory", {}) or {})
        local_items = dict(planet_data.get("items", {}) or {})

        def _resolve_smuggling_price(item_name):
            entry = smuggling_inventory.get(item_name)
            if not isinstance(entry, dict):
                return None

            explicit_price = entry.get("price")
            if explicit_price is not None:
                try:
                    value = int(explicit_price)
                except (TypeError, ValueError):
                    value = 0
                return value if value > 0 else None

            if "modifier" in entry:
                try:
                    modifier = int(entry.get("modifier", 0))
                    if modifier <= 0:
                        return None
                    local_price = int(local_items.get(item_name, 0))
                    if local_price <= 0:
                        return None
                    inferred = int(round(local_price * (100.0 / float(modifier))))
                    return inferred if inferred > 0 else None
                except (TypeError, ValueError, ZeroDivisionError):
                    return None

            return None

        return SimpleNamespace(
            name=planet_data.get("name", ""),
            x=float(planet_data.get("x", 0.0)),
            y=float(planet_data.get("y", 0.0)),
            description=planet_data.get("description", ""),
            tech_level=int(planet_data.get("tech_level", 0)),
            government=planet_data.get("government", ""),
            population=int(planet_data.get("population", 0)),
            special_resources=planet_data.get("special_resources", ""),
            vendor=planet_data.get("vendor", "UNKNOWN"),
            bank=bool(planet_data.get("bank", False)),
            crew_services=bool(planet_data.get("crew_services", False)),
            is_smuggler_hub=bool(planet_data.get("is_smuggler_hub", False)),
            npc_name=planet_data.get("npc_name", "Unknown"),
            npc_personality=planet_data.get("npc_personality", "neutral"),
            docking_fee=int(planet_data.get("docking_fee", 0)),
            bribe_cost=int(planet_data.get("bribe_cost", 0)),
            security_level=int(planet_data.get("security_level", 0)),
            owner=planet_data.get("owner", "UNCLAIMED"),
            defenders=int(planet_data.get("defenders", 0)),
            max_defenders=int(planet_data.get("max_defenders", 0)),
            shields=int(planet_data.get("shields", 0)),
            base_shields=int(planet_data.get("base_shields", 0)),
            credit_balance=int(planet_data.get("credit_balance", 0)),
            repair_multiplier=planet_data.get("repair_multiplier"),
            items=dict(planet_data.get("items", {}) or {}),
            smuggling_inventory=smuggling_inventory,
            welcome_msg=planet_data.get("welcome_msg", "Docking request approved."),
            unwelcome_msg=planet_data.get(
                "unwelcome_msg", "Identity confirmed. Proceed with caution."
            ),
            npc_remarks=npc_remarks,
            get_smuggling_price=_resolve_smuggling_price,
        )

    async def _refresh_world_data(self):
        planets_result = await self._request("get_planets")
        if planets_result.get("success"):
            self.planets = [
                self._build_planet(p)
                for p in list(planets_result.get("planets", []) or [])
            ]
            self.known_planets = list(self.planets)

        ships_result = await self._request("get_spaceships")
        if ships_result.get("success"):
            self.spaceships = [
                self._build_spaceship(s)
                for s in list(ships_result.get("spaceships", []) or [])
            ]

    def _load_local_asset_manifest(self) -> dict:
        if not self.asset_manifest_path.exists():
            return {}
        try:
            return json.loads(self.asset_manifest_path.read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _save_local_asset_manifest(self, manifest: dict):
        self.asset_manifest_path.parent.mkdir(parents=True, exist_ok=True)
        self.asset_manifest_path.write_text(
            json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8"
        )

    def _is_safe_asset_path(self, relative_path: str) -> bool:
        normalized = Path(relative_path)
        if normalized.is_absolute():
            return False
        if ".." in normalized.parts:
            return False
        return str(relative_path).replace("\\", "/").startswith("assets/")

    def _apply_asset_updates(self, files: list, deleted: list, manifest: dict):
        for rel_path in deleted:
            if not self._is_safe_asset_path(rel_path):
                continue
            local_path = self.client_root / Path(rel_path)
            if local_path.exists() and local_path.is_file():
                try:
                    local_path.unlink()
                except Exception:
                    pass

        for file_info in files:
            rel_path = file_info.get("path", "")
            content_b64 = file_info.get("content_b64", "")
            expected_hash = file_info.get("sha256", "")

            if not self._is_safe_asset_path(rel_path):
                continue

            try:
                payload = base64.b64decode(content_b64)
            except Exception:
                continue

            actual_hash = hashlib.sha256(payload).hexdigest()
            if expected_hash and actual_hash != expected_hash:
                continue

            local_path = self.client_root / Path(rel_path)
            local_path.parent.mkdir(parents=True, exist_ok=True)
            local_path.write_bytes(payload)

        if isinstance(manifest, dict):
            self._save_local_asset_manifest(manifest)

    async def _sync_assets_from_server(self):
        local_manifest = self._load_local_asset_manifest()
        result = await self._request("sync_assets", {"manifest": local_manifest})
        if not result.get("success"):
            return

        files = result.get("files", [])
        deleted = result.get("deleted", [])
        manifest = result.get("manifest", {})
        self._apply_asset_updates(files, deleted, manifest)

        if files or deleted:
            print(f"Asset sync complete ({len(files)} updated, {len(deleted)} removed)")

    async def _request(self, action: str, params: dict = None) -> dict:
        """Send request to server and wait for response."""
        auth_actions = {"check_account", "create_account", "authenticate", "login"}
        if not self.websocket:
            if action not in auth_actions:
                return {
                    "success": False,
                    "error": "CONNECTION_LOST",
                    "message": "Connection lost. Reconnect and sign in.",
                }
            try:
                self.websocket = await websockets.connect(
                    self.server_url, max_size=None
                )
                self.connected = True
            except Exception as e:
                return {"success": False, "error": f"Connection failed: {str(e)}"}

        message = {"action": action, "params": params or {}}

        try:
            await self.websocket.send(json.dumps(message))
            response = await self.websocket.recv()
            parsed = json.loads(response)

            return parsed
        except Exception as e:
            print(f"Request error: {e}")
            self.connected = False
            self.websocket = None
            return {"success": False, "error": str(e)}

    async def _refresh_player_data(self):
        """Refresh cached player and planet data."""
        # Get player info
        result = await self._request("get_player_info")
        if result.get("success"):
            data = result.get("data", {})
            self.bribed_planets = set(data.get("bribed_planets", []) or [])
            if "planet_price_penalty_multiplier" in data:
                self.planet_price_penalty_multiplier = float(
                    data.get("planet_price_penalty_multiplier")
                )
            player_payload = (
                data.get("player") if isinstance(data.get("player"), dict) else None
            )
            if player_payload:
                self.player = self._build_player(player_payload)
            else:
                from types import SimpleNamespace

                self.player = SimpleNamespace(
                    name=data.get("name"),
                    credits=data.get("credits"),
                    spaceship=SimpleNamespace(
                        model=data.get("ship", ""),
                        current_defenders=0,
                        current_shields=0,
                        integrity=100,
                        max_integrity=100,
                        fuel=0.0,
                        fuel_burn_rate=1.0,
                        get_effective_fuel_burn_rate=lambda: 1.0,
                    ),
                    bank_balance=data.get("bank_balance", 0),
                    inventory={},
                    crew={},
                    messages=[],
                    delete_message=lambda msg_id: None,
                )

        # Get current planet
        result = await self._request("get_current_planet_info")
        if result.get("success"):
            data = result.get("data", {})
            planet_payload = (
                data.get("planet") if isinstance(data.get("planet"), dict) else None
            )
            if planet_payload:
                self.current_planet = self._build_planet(planet_payload)
            else:
                from types import SimpleNamespace

                self.current_planet = SimpleNamespace(
                    name=data.get("name"),
                    description=data.get("description"),
                    tech_level=data.get("tech_level"),
                    government=data.get("government"),
                    population=data.get("population", 0),
                    special_resources=data.get("special_resources", ""),
                    bank=False,
                    crew_services=False,
                    is_smuggler_hub=False,
                    items={},
                    owner="UNCLAIMED",
                    defenders=0,
                    max_defenders=0,
                    shields=0,
                    base_shields=0,
                    repair_multiplier=None,
                    x=0.0,
                    y=0.0,
                    vendor="UNKNOWN",
                )

    # ========== PLAYER INFO ==========
    async def get_player_info(self) -> Tuple:
        """Get player information."""
        result = await self._request("get_player_info")
        if result.get("success"):
            data = result.get("data", {})
            return (
                data.get("name"),
                data.get("credits"),
                data.get("ship"),
                data.get("location"),
                data.get("bank_balance", 0),
            )
        return ("", 0, "", "", 0)

    # ========== PLANET INFO ==========
    async def get_current_planet_info(self) -> Tuple:
        """Get current planet information."""
        result = await self._request("get_current_planet_info")
        if result.get("success"):
            data = result.get("data", {})
            return (
                data.get("name"),
                data.get("description"),
                data.get("tech_level"),
                data.get("government"),
                data.get("population", 0),
                data.get("special_resources", ""),
            )
        return ("", "", 0, "", 0, "")

    async def get_docking_fee(self, planet, ship) -> int:
        """Get docking fee for planet."""
        result = await self._request(
            "get_docking_fee",
            {"planet_name": planet.name if hasattr(planet, "name") else str(planet)},
        )
        return result.get("fee", 0) if result.get("success") else 0

    async def get_winner_board(self) -> dict:
        """Get winner board and campaign reset schedule."""
        result = await self._request("get_winner_board")
        if result.get("success"):
            return dict(result.get("board", {}) or {})
        return {"error": str(result.get("message") or result.get("error") or "")}

    # ========== TRADING ==========
    async def trade_item(
        self, item_name: str, action: str, quantity: int
    ) -> Tuple[bool, str]:
        """Buy or sell item."""
        result = await self._request(
            "trade_item",
            {"item_name": item_name, "action": action, "quantity": quantity},
        )
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def buy_item(self, item_name: str, quantity: int) -> Tuple[bool, str]:
        """Buy item."""
        result = await self._request(
            "buy_item", {"item": item_name, "quantity": quantity}
        )
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def sell_item(self, item_name: str, quantity: int) -> Tuple[bool, str]:
        """Sell item."""
        result = await self._request(
            "sell_item", {"item": item_name, "quantity": quantity}
        )
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def jettison_cargo(self, item_name: str) -> Tuple[bool, str]:
        """Jettison (destroy) 1 unit of an item from the cargo hold."""
        result = await self._request("jettison_cargo", {"item": item_name})
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    # ========== MARKET DATA ==========
    async def get_market_sell_price(self, item_name: str, planet_name: str) -> int:
        """Get sell price for item at planet."""
        result = await self._request(
            "get_market_sell_price", {"item": item_name, "planet_name": planet_name}
        )
        return result.get("price", 0) if result.get("success") else 0

    async def get_effective_buy_price(
        self, item_name: str, base_price: int, planet_name: str
    ) -> int:
        """Get effective buy price for item at planet."""
        result = await self._request(
            "get_effective_buy_price",
            {"item": item_name, "base_price": base_price, "planet_name": planet_name},
        )
        return result.get("price", 0) if result.get("success") else 0

    async def get_item_market_snapshot(
        self, item_name: str, planet_name: str = None
    ) -> dict:
        """Get market snapshot for item."""
        result = await self._request(
            "get_item_market_snapshot", {"item": item_name, "planet_name": planet_name}
        )
        return result.get("data", {}) if result.get("success") else {}

    async def get_best_trade_opportunities(
        self, from_planet: str = None, limit: int = 5
    ) -> List:
        """Get best trade routes."""
        result = await self._request(
            "get_best_trade_opportunities", {"from_planet": from_planet, "limit": limit}
        )
        return result.get("routes", []) if result.get("success") else []

    async def get_bribe_market_snapshot(self, planet_name: str = None) -> dict:
        """Get bribe market snapshot."""
        result = await self._request(
            "get_bribe_market_snapshot", {"planet_name": planet_name}
        )
        return result.get("data", {}) if result.get("success") else {}

    async def get_contraband_market_context(
        self, item_name: str, planet_name: str = None, quantity: int = 1
    ) -> dict:
        """Get contraband market context."""
        result = await self._request(
            "get_contraband_market_context",
            {
                "item": item_name,
                "planet_name": planet_name,
                "quantity": int(max(1, quantity)),
            },
        )
        return result.get("data", {}) if result.get("success") else {}

    # ========== SHIP OPERATIONS ==========
    async def buy_fuel(self, amount: int) -> Tuple[bool, str]:
        """Buy fuel."""
        result = await self._request("buy_fuel", {"amount": amount})
        message = str(
            result.get("message") or result.get("error") or "Fuel purchase failed."
        )
        if result.get("success"):
            await self._refresh_player_data()
            return True, message
        return False, message

    async def get_refuel_quote(self) -> dict:
        """Get refuel quote."""
        result = await self._request("get_refuel_quote")
        return result.get("quote", {}) if result.get("success") else {}

    async def repair_hull(self) -> Tuple[bool, str]:
        """Repair hull."""
        result = await self._request("repair_hull")
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def buy_ship(self, ship_name: str) -> Tuple[bool, str]:
        """Buy new ship."""
        ship_model = ship_name.model if hasattr(ship_name, "model") else ship_name
        result = await self._request("buy_ship", {"ship": ship_model})
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def transfer_fighters(self, action: str, quantity: int) -> Tuple[bool, str]:
        """Transfer fighters."""
        result = await self._request(
            "transfer_fighters", {"action": action, "quantity": quantity}
        )
        return (result.get("success", False), result.get("message", ""))

    async def transfer_shields(self, action: str, quantity: int) -> Tuple[bool, str]:
        """Transfer shields."""
        result = await self._request(
            "transfer_shields", {"action": action, "quantity": quantity}
        )
        return (result.get("success", False), result.get("message", ""))

    async def check_auto_refuel(self):
        """Check and perform auto refuel."""
        await self._request("check_auto_refuel")

    async def install_ship_upgrade(self, item_name: str, quantity: int) -> dict:
        """Install ship upgrade from cargo."""
        result = await self._request(
            "install_ship_upgrade", {"item_name": item_name, "quantity": int(quantity)}
        )
        if result.get("success"):
            await self._refresh_player_data()
        return result

    async def travel_to_planet(
        self,
        target_planet_index: int,
        skip_travel_event: bool = False,
        travel_event_message: str = None,
    ) -> Tuple[bool, str]:
        result = await self._request(
            "travel_to_planet",
            {
                "target_planet_index": int(target_planet_index),
                "skip_travel_event": bool(skip_travel_event),
                "travel_event_message": travel_event_message,
            },
        )
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def roll_travel_event_payload(self, target_planet, dist: float):
        planet_name = (
            target_planet.name if hasattr(target_planet, "name") else str(target_planet)
        )
        result = await self._request(
            "roll_travel_event_payload",
            {"planet_name": planet_name, "dist": float(dist)},
        )
        return result.get("payload") if result.get("success") else None

    async def resolve_travel_event_payload(
        self, event_payload, choice: str = "AUTO"
    ) -> str:
        result = await self._request(
            "resolve_travel_event_payload",
            {"event_payload": event_payload, "choice": choice},
        )
        await self._refresh_player_data()
        return str(result.get("result_line", ""))

    def _sanitize_orbit_target_for_request(self, target):
        if not isinstance(target, dict):
            return target

        sanitized = dict(target)
        raw_data = sanitized.get("raw_data")
        if isinstance(raw_data, dict):
            sanitized_raw = dict(raw_data)
            player_raw = sanitized_raw.get("player")
            if isinstance(player_raw, dict):
                sanitized_raw["player"] = dict(player_raw)
            sanitized["raw_data"] = sanitized_raw

        if "obj" in sanitized:
            sanitized.pop("obj", None)

        return sanitized

    def _hydrate_orbit_target_for_ui(self, target):
        if not isinstance(target, dict):
            return target

        target_type = str(target.get("type", "")).upper()
        if target_type != "NPC" or target.get("obj") is not None:
            return target

        raw_data = (
            target.get("raw_data") if isinstance(target.get("raw_data"), dict) else {}
        )
        npc_info = (
            raw_data.get("player") if isinstance(raw_data.get("player"), dict) else {}
        )

        class _OrbitNpcProxy:
            def __init__(self, info_payload, fallback_name, fallback_personality):
                self._info = dict(info_payload or {})
                self.name = str(self._info.get("name") or fallback_name or "Unknown")
                self.personality = str(
                    self._info.get("personality") or fallback_personality or "neutral"
                )

            def get_info(self):
                data = dict(self._info)
                if "name" not in data:
                    data["name"] = self.name
                if "personality" not in data:
                    data["personality"] = self.personality
                return data

        hydrated = dict(target)
        hydrated["obj"] = _OrbitNpcProxy(
            npc_info,
            hydrated.get("name"),
            hydrated.get("personality"),
        )
        if not hydrated.get("name"):
            hydrated["name"] = hydrated["obj"].name
        if not hydrated.get("personality"):
            hydrated["personality"] = hydrated["obj"].personality
        return hydrated

    # ========== COMBAT ==========
    async def get_orbit_targets(self) -> List:
        """Get targets in orbit."""
        result = await self._request("get_orbit_targets")
        if not result.get("success"):
            return []
        targets = []
        for target in list(result.get("targets", []) or []):
            targets.append(self._hydrate_orbit_target_for_ui(target))
        return targets

    async def start_combat_session(self, target) -> dict:
        """Start combat with target."""
        safe_target = self._sanitize_orbit_target_for_request(target)
        result = await self._request("start_combat_session", {"target": safe_target})
        return result

    async def resolve_combat_round(self, session, player_committed: int):
        result = await self._request(
            "resolve_combat_round",
            {"session": session, "player_committed": int(player_committed)},
        )
        await self._refresh_player_data()
        return (
            result.get("success", False),
            result.get("message", ""),
            result.get("session", session),
        )

    async def flee_combat_session(self, session) -> dict:
        """Flee from combat."""
        result = await self._request("flee_combat_session", {"session": session})
        return result.get("session", {}) if result.get("success") else session

    async def fire_special_weapon(self, session) -> dict:
        """Fire the player's special weapon during planet combat."""
        result = await self._request("fire_special_weapon", {"session": session})
        if result.get("success"):
            await self._refresh_player_data()
        return {
            "success": bool(result.get("success", False)),
            "message": str(result.get("message", "")),
            "result": result.get("result", {}),
            "session": result.get("session", session),
        }

    async def get_special_weapon_status(self) -> dict:
        """Get special weapon cooldown and availability status."""
        result = await self._request("get_special_weapon_status")
        return result if result.get("success") else {
            "success": False,
            "enabled": False,
            "weapon_name": None,
            "on_cooldown": False,
            "remaining_hours": 0.0,
            "cooldown_hours": 36.0,
        }

    async def should_initialize_planet_auto_combat(self, planet) -> Tuple[bool, str]:
        """Check if should initialize planet auto combat."""
        result = await self._request(
            "should_initialize_planet_auto_combat", {"planet": planet}
        )
        return (result.get("triggered", False), result.get("message", ""))

    # ========== BANKING ==========
    async def bank_deposit(self, amount: int) -> Tuple[bool, str]:
        """Deposit credits to bank."""
        result = await self._request("bank_deposit", {"amount": amount})
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def bank_withdraw(self, amount: int) -> Tuple[bool, str]:
        """Withdraw credits from bank."""
        result = await self._request("bank_withdraw", {"amount": amount})
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def payout_interest(self) -> Tuple[bool, str]:
        """Pay out bank interest."""
        result = await self._request("payout_interest")
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def get_planet_financials(self) -> dict:
        """Get current-planet and owned-planet treasury summary."""
        result = await self._request("get_planet_financials")
        return result.get("data", {}) if result.get("success") else {}

    async def planet_deposit(self, amount: int) -> Tuple[bool, str]:
        """Deposit player credits into current planet treasury."""
        result = await self._request("planet_deposit", {"amount": amount})
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def planet_withdraw(self, amount: int) -> Tuple[bool, str]:
        """Withdraw credits from current planet treasury."""
        result = await self._request("planet_withdraw", {"amount": amount})
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    # ========== CREW ==========
    async def get_planet_crew_offers(self, planet) -> List:
        """Get crew offers at planet."""
        planet_name = planet.name if hasattr(planet, "name") else str(planet)
        result = await self._request(
            "get_planet_crew_offers", {"planet_name": planet_name}
        )
        return result.get("offers", []) if result.get("success") else []

    async def process_crew_pay(self) -> Tuple[bool, str]:
        """Process crew payroll."""
        result = await self._request("process_crew_pay")
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    # ========== FACTION/REPUTATION ==========
    async def get_authority_standing_label(self) -> str:
        """Get authority standing label."""
        result = await self._request("get_authority_standing_label")
        return result.get("label", "") if result.get("success") else ""

    async def get_frontier_standing_label(self) -> str:
        """Get frontier standing label."""
        result = await self._request("get_frontier_standing_label")
        return result.get("label", "") if result.get("success") else ""

    async def _get_authority_standing(self) -> int:
        result = await self._request("_get_authority_standing")
        return int(result.get("value", 0)) if result.get("success") else 0

    async def _get_frontier_standing(self) -> int:
        result = await self._request("_get_frontier_standing")
        return int(result.get("value", 0)) if result.get("success") else 0

    async def _adjust_authority_standing(self, delta: int) -> int:
        result = await self._request(
            "_adjust_authority_standing", {"delta": int(delta)}
        )
        await self._refresh_player_data()
        return int(result.get("value", 0)) if result.get("success") else 0

    async def _adjust_frontier_standing(self, delta: int) -> int:
        result = await self._request("_adjust_frontier_standing", {"delta": int(delta)})
        await self._refresh_player_data()
        return int(result.get("value", 0)) if result.get("success") else 0

    # ========== CONTRACTS ==========
    async def get_active_trade_contract(self) -> Optional[dict]:
        """Get active trade contract."""
        result = await self._request("get_active_trade_contract")
        return result.get("contract") if result.get("success") else None

    async def reroll_trade_contract(self) -> Tuple[bool, str]:
        """Reroll trade contract."""
        result = await self._request("reroll_trade_contract")
        return (result.get("success", False), result.get("message", ""))

    # ========== ANALYTICS ==========
    async def get_analytics_summary(self, window_hours: int = 24) -> dict:
        """Get analytics summary for the selected time window."""
        result = await self._request(
            "get_analytics_summary", {"window_hours": int(window_hours)}
        )
        return result.get("summary", {}) if result.get("success") else {}

    async def get_analytics_events(self, limit: int = 100, category: str = None) -> List[dict]:
        """Get recent analytics events."""
        params = {"limit": int(limit)}
        if category:
            params["category"] = str(category)
        result = await self._request("get_analytics_events", params)
        return list(result.get("events", []) or []) if result.get("success") else []

    async def get_analytics_recommendations(self, window_hours: int = 24) -> dict:
        """Get balancing recommendations based on analytics."""
        result = await self._request(
            "get_analytics_recommendations", {"window_hours": int(window_hours)}
        )
        return result.get("data", {}) if result.get("success") else {}

    async def reset_analytics(self) -> Tuple[bool, str]:
        """Reset analytics store on the server."""
        result = await self._request("reset_analytics")
        return (result.get("success", False), result.get("message", ""))

    # ========== CONTRABAND ==========
    async def get_smuggling_item_names(self) -> List[str]:
        """Get smuggling item names."""
        result = await self._request("get_smuggling_item_names")
        return result.get("items", []) if result.get("success") else []

    async def check_contraband_detection(self) -> Tuple[bool, str]:
        """Check for contraband detection."""
        result = await self._request("check_contraband_detection")
        return (result.get("detected", False), result.get("message", ""))

    async def bribe_npc(self) -> Tuple[bool, str]:
        """Bribe NPC."""
        result = await self._request("bribe_npc")
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def sell_non_market_cargo(self) -> Tuple[bool, str]:
        """Sell non-market cargo."""
        result = await self._request("sell_non_market_cargo")
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    # ========== PLANET MANAGEMENT ==========
    async def check_barred(self, planet_name: str) -> Tuple[bool, str]:
        """Check if barred from planet."""
        result = await self._request("check_barred", {"planet_name": planet_name})
        return (result.get("is_barred", False), result.get("message", ""))

    async def bar_player(self, planet_name: str):
        """Bar player from planet."""
        await self._request("bar_player", {"planet_name": planet_name})

    async def get_planet_event(self, planet_name: str):
        """Get planet event."""
        result = await self._request("get_planet_event", {"planet_name": planet_name})
        return result.get("event") if result.get("success") else None

    async def is_planet_hostile_market(self, planet_name: str) -> bool:
        """Check if planet has hostile market."""
        result = await self._request(
            "is_planet_hostile_market", {"planet_name": planet_name}
        )
        return result.get("is_hostile", False) if result.get("success") else False

    async def get_planet_price_penalty_seconds_remaining(self, planet_name: str) -> int:
        """Get planet price penalty seconds remaining."""
        result = await self._request(
            "get_planet_price_penalty_seconds_remaining", {"planet_name": planet_name}
        )
        return result.get("seconds", 0) if result.get("success") else 0

    async def get_current_port_spotlight_deal(self) -> Optional[dict]:
        """Get current port spotlight deal."""
        result = await self._request("get_current_port_spotlight_deal")
        return result.get("deal") if result.get("success") else None

    async def process_conquered_planet_defense_regen(self) -> Tuple[bool, str]:
        """Process conquered planet defense regeneration."""
        result = await self._request("process_conquered_planet_defense_regen")
        return (result.get("success", False), result.get("message", ""))

    # ========== COMMANDER ==========
    async def process_commander_stipend(self) -> Tuple[bool, str]:
        """Process commander stipend."""
        result = await self._request("process_commander_stipend")
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def has_unseen_galactic_news(self, lookback_days: int = None) -> bool:
        """Check if there are unseen galactic news entries."""
        params = {}
        if lookback_days is not None:
            params["lookback_days"] = lookback_days
        result = await self._request("has_unseen_galactic_news", params)
        return result.get("has_unseen", False) if result.get("success") else False

    async def get_unseen_galactic_news(self, lookback_days: int = None) -> List[dict]:
        """Fetch unseen galactic news entries."""
        params = {}
        if lookback_days is not None:
            params["lookback_days"] = lookback_days
        result = await self._request("get_unseen_galactic_news", params)
        if result.get("success"):
            return result.get("entries", [])
        return []

    async def mark_galactic_news_seen(self) -> bool:
        """Mark current unseen galactic news entries as seen."""
        result = await self._request("mark_galactic_news_seen")
        return result.get("success", False)

    # ========== MESSAGING ==========
    async def send_message(
        self, recipient: str, subject: str, body: str, sender_name: str = None
    ) -> Tuple[bool, str]:
        """Send message to another player."""
        result = await self._request(
            "send_message",
            {
                "recipient": recipient,
                "subject": subject,
                "body": body,
                "sender_name": sender_name,
            },
        )
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def gift_cargo_to_orbit_target(
        self, target_data, item_name: str, qty: int = 1
    ):
        safe_target = self._sanitize_orbit_target_for_request(target_data)
        result = await self._request(
            "gift_cargo_to_orbit_target",
            {"target_data": safe_target, "item_name": item_name, "qty": int(qty)},
        )
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def delete_message(self, msg_id: str) -> bool:
        result = await self._request("delete_message", {"msg_id": msg_id})
        await self._refresh_player_data()
        return result.get("success", False)

    async def mark_message_read(self, msg_id: str) -> bool:
        result = await self._request("mark_message_read", {"msg_id": msg_id})
        await self._refresh_player_data()
        return result.get("success", False)

    async def get_other_players(self) -> List:
        """Get list of other players."""
        result = await self._request("get_other_players")
        return result.get("players", []) if result.get("success") else []

    async def get_all_commander_statuses(self) -> List[dict]:
        """Get all commander status rows for overview UI."""
        result = await self._request("get_all_commander_statuses")
        if result.get("success"):
            return list(result.get("commanders", []) or [])
        return []

    # ========== MISC ==========
    async def claim_abandoned_ship(
        self, target_name: str, action: str = "LOOT", extras: dict = None
    ) -> Tuple[bool, str]:
        """Claim abandoned ship."""
        result = await self._request(
            "claim_abandoned_ship",
            {
                "target_name": target_name,
                "action": action,
                "extras": extras or {},
            },
        )
        await self._refresh_player_data()
        return (result.get("success", False), result.get("message", ""))

    async def get_ship_level(self, ship_name: str) -> int:
        """Get ship level."""
        ship_model = ship_name.model if hasattr(ship_name, "model") else ship_name
        result = await self._request("get_ship_level", {"ship": ship_model})
        return result.get("level", 1) if result.get("success") else 1

    async def _get_target_stats(self, session) -> Tuple[int, int, int]:
        """Get target stats."""
        result = await self._request("_get_target_stats", {"session": session})
        if result.get("success"):
            return (
                result.get("shields", 0),
                result.get("defenders", 0),
                result.get("integrity", 100),
            )
        return (0, 0, 100)

    async def _load_shared_planet_states(self):
        """Load shared planet states."""
        await self._request("_load_shared_planet_states")

    async def refresh_player_state(self) -> bool:
        """Refresh cached player and current planet state from server."""
        await self._refresh_player_data()
        return self.player is not None

    # ========== SAVE/LOAD ==========
    async def new_game(self, player_name: str) -> Tuple[bool, str]:
        """Initialize new game state for a player."""
        result = await self._request("new_game", {"player_name": player_name})
        if result.get("success"):
            await self._refresh_player_data()
            await self._refresh_world_data()
            await self._refresh_config()
        return result.get("success", False), result.get("message", "")

    async def load_game(self, player_name: str) -> Tuple[bool, str]:
        """Load a saved game by player name."""
        result = await self._request("load_game", {"player_name": player_name})
        if result.get("success"):
            await self._refresh_player_data()
        return result.get("success", False), result.get("message", "")

    async def save_game(self) -> bool:
        """Save game."""
        result = await self._request("save_game")
        return result.get("success", False)

    async def list_saves(self) -> List[str]:
        """Get list of saves."""
        result = await self._request("list_saves")
        return result.get("saves", []) if result.get("success") else []

    async def logout_commander(self) -> Tuple[bool, str]:
        """Logout current commander while keeping account session authenticated."""
        result = await self._request("logout_commander")
        if result.get("success"):
            self.player = None
            self.current_planet = None
            if self.account_name:
                self.player_name = self.account_name
            return True, str(result.get("message", "Commander logged out."))
        return False, str(
            result.get("message") or result.get("error") or "Commander logout failed."
        )

    async def close(self):
        """Close connection to server."""
        if self.websocket:
            # Save before closing
            await self.save_game()
            await self.websocket.close()
            self.connected = False
