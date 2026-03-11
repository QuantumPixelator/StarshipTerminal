import time
import os
import random
from pathlib import Path
from sqlite_store import SQLiteStore
from classes import load_spaceships
from planets import generate_planets


class CoreMixin:
    def load_global_config(self):
        """Loads non-player-specific settings from SQLite."""
        settings = {}

        if getattr(self, "store", None) is not None:
            db_settings = self.store.get_all_settings()
            if isinstance(db_settings, dict) and db_settings:
                settings = dict(db_settings)

        if not settings:
            raise RuntimeError("Missing SQLite settings payload; initialize DB migration first.")

        self.config = dict(settings)

        # Client-only audio controls are persisted locally per commander.
        for key in [
            "audio_enabled",
            "audio_ui_volume",
            "audio_combat_volume",
            "audio_ambient_volume",
        ]:
            self.config.pop(key, None)

        legacy_defaults = {
            "fuel_usage_multiplier": 1.15,
            "travel_time_reference_distance": 300.0,
            "travel_time_min_seconds": 0.8,
            "travel_time_max_seconds": 12.0,
            "frontier_bribe_bonus": 6,
            "frontier_contraband_trade_bonus": 1,
            "frontier_smuggling_detection_reduction_step": 0.01,
            "frontier_smuggling_discount_step": 0.005,
            "authority_bounty_bonus_step": 0.01,
            "law_heat_gain_trade": 2,
            "law_heat_gain_detected": 8,
            "law_heat_decay_per_hour": 3,
            "law_heat_scan_chance_step": 0.015,
            "law_heat_penalty_step": 0.20,
            "law_heat_detected_ship_level_step": 0.18,
            "contraband_detection_ship_level_step": 0.08,
            "bribe_price_ship_level_step": 0.10,
            "planet_event_chance": 0.24,
            "economy_momentum_trade_step": 0.018,
            "economy_momentum_decay_per_hour": 0.10,
            "economy_dampening_volume_step": 0.012,
            "economy_dampening_floor": 0.70,
            "sector_report_interval_hours": 24,
            "enable_bank": True,
            "enable_analytics": True,
            "analytics_retention_days": 14,
            "analytics_max_events": 5000,
            "analytics_flush_interval_seconds": 15,
            "planet_loss_travel_ban_hours": 6,
            "commander_presence_banner_seconds": 5,
            "market_update_interval_minutes": 20,
            "authority_bribe_cost_step": 0.004,
            "authority_detection_step": 0.004,
            "authority_legal_buy_discount_step": 0.0025,
            "authority_legal_buy_discount_cap": 0.18,
            "frontier_legal_buy_surcharge_step": 0.0020,
            "frontier_legal_buy_surcharge_cap": 0.15,
            "authority_negative_docking_step": 0.010,
            "authority_negative_docking_cap": 0.35,
            "authority_positive_docking_discount_step": 0.004,
            "authority_positive_docking_discount_cap": 0.20,
            "resource_interest_rate": 0.01,
            "jump_fuel_use_base": 1.0,
            "combat_fuel_use_per_round": 6,
            "victory_resource_share_pct": 35,
            "victory_credit_hoard": 250000,
        }
        for key, value in legacy_defaults.items():
            if key not in self.config:
                self.config[key] = value

    def __init__(self):
        server_root = Path(__file__).resolve().parents[1]
        self.save_dir = str(server_root / "saves")
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
        self.db_path = str(Path(self.save_dir) / "game_state.db")
        self.store = SQLiteStore(self.db_path)
        self.store.migrate_json_saves_once(
            save_dir=self.save_dir,
            server_root=str(server_root),
        )
        self.store.migrate_economy_seed(dry_run=False)

        self.load_global_config()
        self.planets = generate_planets()
        self._rebuild_planet_registry()
        # Apply global bank switch
        enable_bank = self.config.get("enable_bank", True)
        for planet in self.planets:
            planet.bank = planet.bank and enable_bank
            # Enable basic repair facilities on all bank planets that don't have specific multipliers
            if planet.bank and planet.repair_multiplier is None:
                planet.repair_multiplier = 1.0
        self.spaceships = load_spaceships()
        self.item_aliases = {
            "Standard Fuel": "Fuel Cells",
            "Standard Fuel Cell": "Fuel Cells",
            "Fuel Cell": "Fuel Cells",
        }
        self.planet_price_penalty_duration = 86400
        self.planet_price_penalty_multiplier = float(
            self.config["planet_price_penalty_multiplier"]
        )
        self.planet_defense_regen_interval = 14400
        self.planet_defense_regen_fighters = 1
        self.planet_defense_regen_shields = 10
        self.player = None
        self.current_planet = None
        self.active_trade_contract = None
        self.current_port_spotlight = None
        self.planet_heat = {}
        self.last_heat_decay_time = time.time()
        self.planet_events = {}
        self.market_momentum = {}
        self.market_trade_volume = {}
        self.last_market_update_time = time.time()
        self.last_market_rotation_time = 0.0
        self.shared_planet_state_path = os.path.join(
            self.save_dir, "universe_planets.json"
        )
        self.galactic_news_path = os.path.join(self.save_dir, "galactic_news.json")
        self.winner_board_path = os.path.join(self.save_dir, "winner_board.json")
        self.galactic_news_retention_days = 14

        # Mutable state tracking used by server snapshots and client-side caching.
        self.state_version = 0
        self.last_state_update_ts = 0.0

        # Deferred save controls. save_game() marks dirty, and the server flushes writes.
        self.save_debounce_seconds = float(self.config.get("save_debounce_seconds", 2.5))
        self._save_dirty = False
        self._save_requested_at = 0.0
        self._last_save_completed_at = 0.0

        # Analytics
        self.initialize_analytics()

        # Bribed list per session or saved (should be saved)
        self.bribed_planets = set()
        self.bribe_registry = {}
        self._smuggling_item_cache = None
        self._smuggling_item_meta_cache = {}
        self._contraband_profile_cache = {}

        # NPC Ships
        self.npc_ships = self._init_npc_ships()
        if hasattr(self, "_process_scheduled_game_reset_if_due"):
            self._process_scheduled_game_reset_if_due()
        self._load_shared_planet_states()

    def _rebuild_planet_registry(self):
        self.planet_by_id = {}
        self.planet_id_by_name = {}
        seen_ids = set()

        for idx, planet in enumerate(list(self.planets or []), start=1):
            raw_id = getattr(planet, "planet_id", None)
            try:
                planet_id = int(raw_id)
            except Exception:
                planet_id = idx

            if planet_id <= 0 or planet_id in seen_ids:
                planet_id = idx

            seen_ids.add(planet_id)
            planet.planet_id = int(planet_id)
            self.planet_by_id[int(planet_id)] = planet
            self.planet_id_by_name[str(getattr(planet, "name", "")).strip().lower()] = int(
                planet_id
            )

    def normalize_planet_id(self, planet_id):
        try:
            normalized = int(planet_id)
        except Exception:
            return None
        if normalized <= 0:
            return None
        return normalized

    def get_planet_by_id(self, planet_id):
        normalized = self.normalize_planet_id(planet_id)
        if normalized is None:
            return None
        return self.planet_by_id.get(normalized)

    def get_planet_id_by_name(self, planet_name):
        key = str(planet_name or "").strip().lower()
        if not key:
            return None
        return self.planet_id_by_name.get(key)

    def get_planet_by_name(self, planet_name):
        planet_id = self.get_planet_id_by_name(planet_name)
        if planet_id is None:
            return None
        return self.get_planet_by_id(planet_id)

    def get_current_planet_id(self):
        if not getattr(self, "current_planet", None):
            return None
        return self.normalize_planet_id(getattr(self.current_planet, "planet_id", None))

    def resolve_planet_from_params(self, params, default_current=True):
        payload = params if isinstance(params, dict) else {}
        planet_id = self.normalize_planet_id(payload.get("planet_id"))
        if planet_id is not None:
            planet = self.get_planet_by_id(planet_id)
            if planet:
                return planet

        # Temporary migration fallback while clients migrate to planet_id.
        legacy_name = payload.get("planet_name")
        if legacy_name is not None:
            legacy_planet = self.get_planet_by_name(legacy_name)
            if legacy_planet:
                return legacy_planet

        if default_current:
            return getattr(self, "current_planet", None)
        return None

    def mark_state_dirty(self):
        """Advance state version so clients can trust snapshot freshness."""
        self.state_version = int(getattr(self, "state_version", 0)) + 1
        self.last_state_update_ts = float(time.time())
        return self.state_version

    def _init_npc_ships(self):
        from classes import NPCShip, Spaceship

        npcs = []
        ship_templates = self.spaceships
        personalities = ["hostile", "friendly", "bribable", "dismissive"]

        names = [
            "The Marauder",
            "Trade Prince",
            "Iron Shield",
            "Shadow Stalker",
            "Bounty Hunter X",
            "Old Miner",
            "Diplomat V",
            "Rogue Bot",
            "Starlight Voyager",
            "Void Reaver",
        ]

        for name in names:
            # Pick a ship template
            template = random.choice(ship_templates)
            ship = Spaceship(
                model=template.model,
                cost=template.cost,
                starting_cargo_pods=template.current_cargo_pods,
                starting_shields=template.current_shields,
                starting_defenders=template.current_defenders,
                max_cargo_pods=template.max_cargo_pods,
                max_shields=template.max_shields,
                max_defenders=template.max_defenders,
                special_weapon=template.special_weapon,
                role_tags=list(getattr(template, "role_tags", [])),
                module_slots=int(getattr(template, "module_slots", 2)),
                installed_modules=list(getattr(template, "installed_modules", [])),
            )

            # Randomize stats slightly for variety
            ship.current_shields = random.randint(
                ship.starting_shields, ship.max_shields
            )
            ship.current_defenders = random.randint(
                ship.starting_defenders, ship.max_defenders
            )

            personality = (
                "hostile"
                if "Marauder" in name or "Reaver" in name
                else random.choice(personalities)
            )
            npc = NPCShip(name, ship, personality, credits=random.randint(500, 5000))

            # Populate some inventory
            npc.inventory = {
                "Titanium": random.randint(1, 5),
                "Fuel Cells": random.randint(5, 15),
            }

            # Place at random planet
            npc.orbiting_planet = random.choice(self.planets).name
            npcs.append(npc)

        return npcs

    def _canonical_item_name(self, item_name):
        return self.item_aliases.get(item_name, item_name)

    def _normalize_player_inventory(self):
        if not self.player or not isinstance(self.player.inventory, dict):
            return

        normalized = {}
        changed = False
        for item_name, quantity in self.player.inventory.items():
            canonical_name = self._canonical_item_name(item_name)
            normalized[canonical_name] = normalized.get(canonical_name, 0) + int(
                quantity
            )
            if canonical_name != item_name:
                changed = True

        if changed:
            self.player.inventory = normalized

    def check_barred(self, planet_name):
        """Checks if the player is currently barred from a planet."""
        if not self.player:
            return False, ""

        keys_to_check = [str(planet_name)]
        resolved_planet = self.get_planet_by_id(planet_name) or self.get_planet_by_name(
            planet_name
        )
        if resolved_planet is not None:
            keys_to_check.append(str(getattr(resolved_planet, "planet_id", "")))
            keys_to_check.append(str(getattr(resolved_planet, "name", "")))

        for key in [k for k in keys_to_check if str(k).strip()]:
            if key not in self.player.barred_planets:
                continue
            expiry = float(self.player.barred_planets.get(key, 0.0) or 0.0)
            if time.time() < expiry:
                rem = (expiry - time.time()) / 3600
                return (
                    True,
                    f"You are barred from this quadrant for another {rem:.1f} hours.",
                )
            del self.player.barred_planets[key]
        return False, ""

    def get_smuggling_item_names(self):
        """Returns a list of all item names that are considered contraband."""
        self._load_smuggling_item_cache()
        return list(self._smuggling_item_cache or [])
