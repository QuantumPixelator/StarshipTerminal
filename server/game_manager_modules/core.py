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
        path = "game_config.json"
        if os.path.exists(path):
            with open(path, "r") as f:
                self.config = json.load(f)["settings"]
            self.config.setdefault("planet_auto_combat_threshold_pct", 65)
            self.config.setdefault("planet_price_penalty_multiplier", 1.75)
            self.config.setdefault("base_docking_fee", 10)
            self.config.setdefault("docking_fee_ship_level_multiplier", 1.0)
            self.config.setdefault("salvage_sell_multiplier", 0.55)
            self.config.setdefault("enable_trade_contracts", True)
            self.config.setdefault("trade_contract_hours", 4)
            self.config.setdefault("trade_contract_reward_multiplier", 1.1)
            self.config.setdefault("combat_enemy_scale_per_ship_level", 0.06)
            self.config.setdefault("combat_win_streak_bonus_per_win", 0.04)
            self.config.setdefault("combat_win_streak_bonus_cap", 0.25)
            self.config.setdefault("enable_travel_events", True)
            self.config.setdefault("travel_event_chance", 0.20)
            self.config.setdefault("fuel_usage_multiplier", 1.15)
            self.config.setdefault("refuel_timer_enabled", True)
            self.config.setdefault("refuel_timer_max_refuels", 3)
            self.config.setdefault("refuel_timer_window_hours", 12)
            self.config.setdefault("refuel_timer_cost_multiplier_pct", 200)
            self.config.setdefault("travel_time_reference_distance", 300.0)
            self.config.setdefault("travel_time_min_seconds", 0.8)
            self.config.setdefault("travel_time_max_seconds", 12.0)
            self.config.setdefault("contract_reroll_cost", 600)
            self.config.setdefault("commander_stipend_hours", 8)
            self.config.setdefault("commander_stipend_amount", 350)
            self.config.setdefault("port_spotlight_discount_min", 12)
            self.config.setdefault("port_spotlight_discount_max", 28)
            self.config.setdefault("contract_chain_bonus_per_completion", 0.05)
            self.config.setdefault("contract_chain_bonus_cap", 0.30)
            self.config.setdefault("reputation_bribe_penalty", 12)
            self.config.setdefault("reputation_contraband_trade_penalty", 2)
            self.config.setdefault("reputation_contract_completion_bonus", 8)
            self.config.setdefault("reputation_hostile_npc_bonus", 4)
            self.config.setdefault("reputation_docking_fee_step", 0.03)
            self.config.setdefault("frontier_bribe_bonus", 6)
            self.config.setdefault("frontier_contraband_trade_bonus", 1)
            self.config.setdefault("frontier_smuggling_detection_reduction_step", 0.01)
            self.config.setdefault("frontier_smuggling_discount_step", 0.005)
            self.config.setdefault("authority_bounty_bonus_step", 0.01)
            self.config.setdefault("law_heat_gain_trade", 2)
            self.config.setdefault("law_heat_gain_detected", 8)
            self.config.setdefault("law_heat_decay_per_hour", 3)
            self.config.setdefault("law_heat_scan_chance_step", 0.015)
            self.config.setdefault("law_heat_penalty_step", 0.20)
            self.config.setdefault("law_heat_detected_ship_level_step", 0.18)
            self.config.setdefault("contraband_price_tier_step", 0.14)
            self.config.setdefault("contraband_price_heat_step", 0.005)
            self.config.setdefault("contraband_detection_tier_step", 0.035)
            self.config.setdefault("contraband_detection_quantity_step", 0.03)
            self.config.setdefault("contraband_detection_ship_level_step", 0.08)
            self.config.setdefault("smuggle_nonhub_sell_penalty", 0.72)
            self.config.setdefault("bribe_base_duration_hours", 4)
            self.config.setdefault("bribe_duration_per_level_hours", 2)
            self.config.setdefault("bribe_cost_growth", 1.35)
            self.config.setdefault("bribe_price_heat_step", 0.015)
            self.config.setdefault("bribe_price_ship_level_step", 0.10)
            self.config.setdefault("bribe_max_level", 3)
            self.config.setdefault("bribe_detection_reduction_per_level", 0.08)
            self.config.setdefault("bribe_heat_reduction_per_level", 4)
            self.config.setdefault("bribe_smuggling_discount_per_level", 0.06)
            self.config.setdefault("bribe_smuggling_sell_bonus_per_level", 0.09)
            self.config.setdefault("bribe_authority_hit_per_level", 5)
            self.config.setdefault("bribe_frontier_gain_per_level", 4)
            self.config.setdefault("planet_event_chance", 0.24)
            self.config.setdefault("economy_momentum_trade_step", 0.018)
            self.config.setdefault("economy_momentum_decay_per_hour", 0.10)
            self.config.setdefault("economy_dampening_volume_step", 0.012)
            self.config.setdefault("economy_dampening_floor", 0.70)
            self.config.setdefault("sector_report_interval_hours", 24)
            self.config.setdefault("owned_planet_interest_rate", 0.000001)
            self.config.setdefault("galactic_news_window_days", 5)
            self.config.setdefault("audio_enabled", True)
            self.config.setdefault("audio_ui_volume", 0.70)
            self.config.setdefault("audio_combat_volume", 0.80)
            self.config.setdefault("audio_ambient_volume", 0.45)
            self.config.setdefault("reduced_effects_mode", False)
            self.config.setdefault("accessibility_large_text_mode", False)
            self.config.setdefault("accessibility_color_safe_palette", False)
            self.config.setdefault("allow_multiple_games", False)
            self.config.setdefault("enable_bank", True)
            self.config.setdefault("enable_analytics", True)
            self.config.setdefault("analytics_retention_days", 14)
            self.config.setdefault("analytics_max_events", 5000)
            self.config.setdefault("analytics_flush_interval_seconds", 15)
            self.config.setdefault("victory_planet_ownership_pct", 60)
            self.config.setdefault("victory_authority_min", -100)
            self.config.setdefault("victory_authority_max", 100)
            self.config.setdefault("victory_frontier_min", -100)
            self.config.setdefault("victory_frontier_max", 100)
            self.config.setdefault("victory_reset_days", 7)
        else:
            self.config = {
                "enable_combat": True,
                "enable_mail": True,
                "starting_credits": 200,
                "bank_interest_rate": 0.05,
                "enable_bank": True,
                "planet_price_penalty_multiplier": 1.75,
                "base_docking_fee": 10,
                "docking_fee_ship_level_multiplier": 1.0,
                "salvage_sell_multiplier": 0.55,
                "enable_trade_contracts": True,
                "trade_contract_hours": 4,
                "trade_contract_reward_multiplier": 1.1,
                "combat_enemy_scale_per_ship_level": 0.06,
                "combat_win_streak_bonus_per_win": 0.04,
                "combat_win_streak_bonus_cap": 0.25,
                "enable_travel_events": True,
                "travel_event_chance": 0.20,
                "fuel_usage_multiplier": 1.15,
                "refuel_timer_enabled": True,
                "refuel_timer_max_refuels": 3,
                "refuel_timer_window_hours": 12,
                "refuel_timer_cost_multiplier_pct": 200,
                "travel_time_reference_distance": 300.0,
                "travel_time_min_seconds": 0.8,
                "travel_time_max_seconds": 12.0,
                "contract_reroll_cost": 600,
                "commander_stipend_hours": 8,
                "commander_stipend_amount": 350,
                "port_spotlight_discount_min": 12,
                "port_spotlight_discount_max": 28,
                "contract_chain_bonus_per_completion": 0.05,
                "contract_chain_bonus_cap": 0.30,
                "reputation_bribe_penalty": 12,
                "reputation_contraband_trade_penalty": 2,
                "reputation_contract_completion_bonus": 8,
                "reputation_hostile_npc_bonus": 4,
                "reputation_docking_fee_step": 0.03,
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
                "contraband_price_tier_step": 0.14,
                "contraband_price_heat_step": 0.005,
                "contraband_detection_tier_step": 0.035,
                "contraband_detection_quantity_step": 0.03,
                "contraband_detection_ship_level_step": 0.08,
                "smuggle_nonhub_sell_penalty": 0.72,
                "bribe_base_duration_hours": 4,
                "bribe_duration_per_level_hours": 2,
                "bribe_cost_growth": 1.35,
                "bribe_price_heat_step": 0.015,
                "bribe_price_ship_level_step": 0.10,
                "bribe_max_level": 3,
                "bribe_detection_reduction_per_level": 0.08,
                "bribe_heat_reduction_per_level": 4,
                "bribe_smuggling_discount_per_level": 0.06,
                "bribe_smuggling_sell_bonus_per_level": 0.09,
                "bribe_authority_hit_per_level": 5,
                "bribe_frontier_gain_per_level": 4,
                "planet_event_chance": 0.24,
                "planet_auto_combat_threshold_pct": 65,
                "economy_momentum_trade_step": 0.018,
                "economy_momentum_decay_per_hour": 0.10,
                "economy_dampening_volume_step": 0.012,
                "economy_dampening_floor": 0.70,
                "sector_report_interval_hours": 24,
                "owned_planet_interest_rate": 0.000001,
                "galactic_news_window_days": 5,
                "audio_enabled": True,
                "audio_ui_volume": 0.70,
                "audio_combat_volume": 0.80,
                "audio_ambient_volume": 0.45,
                "reduced_effects_mode": False,
                "accessibility_large_text_mode": False,
                "accessibility_color_safe_palette": False,
                "allow_multiple_games": False,
                "enable_analytics": True,
                "analytics_retention_days": 14,
                "analytics_max_events": 5000,
                "analytics_flush_interval_seconds": 15,
                "victory_planet_ownership_pct": 60,
                "victory_authority_min": -100,
                "victory_authority_max": 100,
                "victory_frontier_min": -100,
                "victory_frontier_max": 100,
                "victory_reset_days": 7,
            }

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
