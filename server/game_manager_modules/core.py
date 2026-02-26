import time
import json
import os
import random
from pathlib import Path
from classes import load_spaceships
from planets import generate_planets


class CoreMixin:
    def load_global_config(self):
        """Loads non-player-specific settings from game_config.json."""
        path = Path(__file__).resolve().parent.parent / "game_config.json"
        if not path.exists():
            raise FileNotFoundError(
                f"Required config file not found: {path}. Server settings must come from game_config.json."
            )

        with path.open("r", encoding="utf-8") as f:
            payload = json.load(f)
        settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
        if not isinstance(settings, dict):
            raise ValueError("Invalid game_config.json: 'settings' must be an object")
        self.config = dict(settings)

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
        }
        for key, value in legacy_defaults.items():
            if key not in self.config:
                self.config[key] = value

    def __init__(self):
        self.load_global_config()
        self.planets = generate_planets()
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
        server_root = Path(__file__).resolve().parents[1]
        self.save_dir = str(server_root / "saves")
        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
        self.shared_planet_state_path = os.path.join(
            self.save_dir, "universe_planets.json"
        )
        self.galactic_news_path = os.path.join(self.save_dir, "galactic_news.json")
        self.winner_board_path = os.path.join(self.save_dir, "winner_board.json")
        self.galactic_news_retention_days = 14

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
        if planet_name in self.player.barred_planets:
            expiry = self.player.barred_planets[planet_name]
            if time.time() < expiry:
                rem = (expiry - time.time()) / 3600
                return (
                    True,
                    f"You are barred from this quadrant for another {rem:.1f} hours.",
                )
            else:
                del self.player.barred_planets[planet_name]
        return False, ""

    def get_smuggling_item_names(self):
        """Returns a list of all item names that are considered contraband."""
        self._load_smuggling_item_cache()
        return list(self._smuggling_item_cache or [])
