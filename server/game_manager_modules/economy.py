import math
import time
import os
import random
from planets import base_prices, active_item_names


class EconomyMixin:
    def _refresh_bribe_registry(self):
        now = time.time()
        active = {}
        for planet_name, state in (self.bribe_registry or {}).items():
            if not isinstance(state, dict):
                continue
            level = max(0, int(state.get("level", 0)))
            expires_at = float(state.get("expires_at", 0.0))
            if level <= 0:
                continue
            if expires_at > 0 and expires_at < now:
                continue
            active[str(planet_name)] = {
                "level": int(level),
                "expires_at": float(expires_at),
            }

        self.bribe_registry = active
        self.bribed_planets = set(active.keys())

    def _get_bribe_level(self, planet_name=None):
        self._refresh_bribe_registry()
        p_name = planet_name or (
            self.current_planet.name if self.current_planet else None
        )
        if not p_name:
            return 0
        state = self.bribe_registry.get(str(p_name), {})
        return max(0, int(state.get("level", 0)))

    def _get_bribe_time_remaining_seconds(self, planet_name=None):
        self._refresh_bribe_registry()
        p_name = planet_name or (
            self.current_planet.name if self.current_planet else None
        )
        if not p_name:
            return 0
        state = self.bribe_registry.get(str(p_name), {})
        expires_at = float(state.get("expires_at", 0.0))
        if expires_at <= 0:
            return 0
        return max(0, int(expires_at - time.time()))

    def _get_bribe_quote(self, planet=None):
        target = planet or self.current_planet
        if not target:
            return {
                "can_bribe": False,
                "reason": "No active port contact.",
            }

        base_cost = max(0, int(getattr(target, "bribe_cost", 0)))
        if base_cost <= 0:
            return {
                "can_bribe": False,
                "reason": "This contact is not bribable.",
                "base_cost": 0,
                "current_level": self._get_bribe_level(target.name),
                "max_level": int(self.config.get("bribe_max_level")),
            }

        max_level = max(1, int(self.config.get("bribe_max_level")))
        level = self._get_bribe_level(target.name)
        if level >= max_level:
            return {
                "can_bribe": False,
                "reason": "Maximum contact influence reached.",
                "base_cost": base_cost,
                "current_level": level,
                "max_level": max_level,
            }

        growth = max(1.01, float(self.config.get("bribe_cost_growth")))
        heat = self._get_law_heat(target.name)
        heat_step = max(0.0, float(self.config.get("bribe_price_heat_step")))
        heat_mult = 1.0 + (heat * heat_step)
        ship_level = max(1, int(self.get_ship_level()))
        ship_price_step = max(
            0.0, float(self.config.get("bribe_price_ship_level_step", 0.10))
        )
        ship_mult = 1.0 + ((ship_level - 1) * ship_price_step)
        frontier = max(0, self._get_frontier_standing())
        frontier_discount = min(0.25, frontier / 500.0)

        raw_cost = (
            float(base_cost)
            * (growth**level)
            * heat_mult
            * ship_mult
            * (1.0 - frontier_discount)
        )
        cost = max(1, int(round(raw_cost)))
        return {
            "can_bribe": True,
            "reason": "",
            "base_cost": int(base_cost),
            "cost": int(cost),
            "current_level": int(level),
            "next_level": int(level + 1),
            "max_level": int(max_level),
            "heat": int(heat),
        }

    def get_bribe_market_snapshot(self, planet_name=None):
        target = next(
            (
                p
                for p in self.planets
                if p.name
                == (
                    planet_name
                    or (self.current_planet.name if self.current_planet else "")
                )
            ),
            self.current_planet,
        )
        if not target:
            return {
                "available": False,
                "can_bribe": False,
                "reason": "No active port contact.",
            }

        quote = self._get_bribe_quote(target)
        remaining = self._get_bribe_time_remaining_seconds(target.name)
        return {
            "available": int(getattr(target, "bribe_cost", 0)) > 0,
            "can_bribe": bool(quote.get("can_bribe", False)),
            "reason": str(quote.get("reason", "")),
            "cost": int(quote.get("cost", 0)) if quote.get("cost") is not None else 0,
            "level": int(self._get_bribe_level(target.name)),
            "max_level": int(
                quote.get("max_level", self.config.get("bribe_max_level"))
            ),
            "remaining_seconds": int(remaining),
            "heat": int(self._get_law_heat(target.name)),
            "npc_name": str(getattr(target, "npc_name", "Contact")),
        }

    def _load_smuggling_item_cache(self):
        if isinstance(self._smuggling_item_cache, list):
            return

        path = os.path.join(
            os.path.dirname(__file__), "assets", "texts", "smuggle_items.txt"
        )
        metadata = {}
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                item_names = []
                for line in f:
                    raw = str(line or "").strip()
                    if not raw:
                        continue
                    parts = [p.strip() for p in raw.split(",")]
                    name = parts[0]
                    if not name or name not in active_item_names:
                        continue
                    if name not in item_names:
                        item_names.append(name)

                    base_price = int(base_prices.get(name, 500))
                    if len(parts) >= 2 and parts[1]:
                        try:
                            base_price = max(1, int(parts[1]))
                        except ValueError:
                            base_price = int(base_prices.get(name, 500))

                    required_bribe_level = None
                    if len(parts) >= 3 and parts[2]:
                        try:
                            required_bribe_level = max(0, min(3, int(parts[2])))
                        except ValueError:
                            required_bribe_level = None

                    metadata[name] = {
                        "base_price": int(base_price),
                        "required_bribe_level": required_bribe_level,
                    }
                self._smuggling_item_cache = item_names
        else:
            self._smuggling_item_cache = []
        self._smuggling_item_meta_cache = metadata

    def _get_smuggling_item_metadata(self, item_name):
        self._load_smuggling_item_cache()
        item = str(item_name or "").strip()
        if not item:
            return {
                "base_price": 500,
                "required_bribe_level": 0,
            }
        data = dict((self._smuggling_item_meta_cache or {}).get(item, {}) or {})
        base_price = int(data.get("base_price", base_prices.get(item, 500) or 500))
        required = data.get("required_bribe_level")
        required = self._normalize_required_smuggling_level(required)
        return {
            "base_price": int(max(1, base_price)),
            "required_bribe_level": required,
        }

    def _get_configured_bribe_max_level(self):
        return max(1, int(self.config.get("bribe_max_level") or 3))

    def _normalize_required_smuggling_level(self, required_level):
        if required_level is None:
            return None
        try:
            raw_level = max(0, int(required_level))
        except (TypeError, ValueError):
            return None

        max_level = self._get_configured_bribe_max_level()
        if max_level != 3 and raw_level <= 3:
            scaled = int(round((float(raw_level) / 3.0) * float(max_level)))
            raw_level = max(0, scaled)
        return int(max(0, min(max_level, raw_level)))

    def _get_required_smuggling_bribe_level(self, item_name, planet=None):
        target = planet or self.current_planet
        base_meta = self._get_smuggling_item_metadata(item_name)
        explicit = base_meta.get("required_bribe_level")
        if explicit is not None:
            return int(self._normalize_required_smuggling_level(explicit) or 0)

        security_level = int(getattr(target, "security_level", 0)) if target else 0
        is_hub = bool(getattr(target, "is_smuggler_hub", False)) if target else False
        base_price = int(
            base_meta.get("base_price", base_prices.get(item_name, 500) or 500)
        )

        if base_price >= 16000:
            level = 3
        elif base_price >= 7000:
            level = 2
        elif base_price >= 2200:
            level = 1
        else:
            level = 0

        if security_level >= 2:
            level = min(3, level + 1)
        if is_hub:
            level = max(0, level - 1)
        return int(self._normalize_required_smuggling_level(level) or 0)

    def _is_smuggling_item_access_open(self, item_name, planet=None):
        target = planet or self.current_planet
        if not target:
            return False
        required_level = self._get_required_smuggling_bribe_level(item_name, target)
        current_level = self._get_bribe_level(target.name)
        if required_level <= 0 and bool(getattr(target, "is_smuggler_hub", False)):
            return True
        return int(current_level) >= int(required_level)

    def is_contraband_item(self, item_name):
        normalized = str(item_name or "").strip()
        if not normalized:
            return False
        self._load_smuggling_item_cache()
        return normalized in set(self._smuggling_item_cache or [])

    def _get_contraband_profile(self, item_name):
        name = str(item_name or "").strip()
        if not name:
            return {
                "tier": "LOW",
                "tier_rank": 1,
                "price_mult": 1.10,
                "detection_mult": 0.95,
                "heat_mult": 0.90,
            }

        cached = self._contraband_profile_cache.get(name)
        if cached:
            return dict(cached)

        seed = sum((idx + 1) * ord(ch) for idx, ch in enumerate(name.lower()))
        tier_idx = seed % 4
        tier_map = ["LOW", "MED", "HIGH", "BLACK"]
        price_curve = [1.12, 1.36, 1.78, 2.30]
        detection_curve = [0.90, 1.00, 1.18, 1.38]
        heat_curve = [0.85, 1.00, 1.25, 1.55]

        keyword_boost = 0
        hot_keywords = [
            "quantum",
            "singularity",
            "ai",
            "artifact",
            "void",
            "alien",
            "wormhole",
            "antimatter",
        ]
        lowered = name.lower()
        if any(k in lowered for k in hot_keywords):
            keyword_boost = 1

        tier_idx = min(3, tier_idx + keyword_boost)
        profile = {
            "tier": tier_map[tier_idx],
            "tier_rank": int(tier_idx + 1),
            "price_mult": float(price_curve[tier_idx]),
            "detection_mult": float(detection_curve[tier_idx]),
            "heat_mult": float(heat_curve[tier_idx]),
        }
        self._contraband_profile_cache[name] = dict(profile)
        return dict(profile)

    def _get_contraband_detection_chance(self, item_name, planet=None, quantity=1):
        target = planet or self.current_planet
        if not target or int(getattr(target, "security_level", 0)) <= 0:
            return 0.0

        base = 0.22 if int(target.security_level) >= 2 else 0.08
        profile = self._get_contraband_profile(item_name)
        chance = base * float(profile.get("detection_mult", 1.0))

        qty = max(1, int(quantity))
        qty_step = max(
            0.0, float(self.config.get("contraband_detection_quantity_step"))
        )
        chance *= 1.0 + (math.sqrt(qty) * qty_step)

        heat = self._get_law_heat(target.name)
        heat_scan_step = float(self.config.get("law_heat_scan_chance_step", 0.015))
        chance *= 1.0 + (heat * heat_scan_step)

        tier_step = float(self.config.get("contraband_detection_tier_step"))
        chance *= 1.0 + ((int(profile.get("tier_rank", 1)) - 1) * tier_step)

        item_meta = self._get_smuggling_item_metadata(item_name)
        contraband_base = max(1.0, float(item_meta.get("base_price", 500)))
        price_ratio = max(0.0, min(2.5, (contraband_base / 4000.0) - 0.25))
        value_step = max(
            0.0, float(self.config.get("contraband_detection_value_step", 0.18))
        )
        chance *= 1.0 + (price_ratio * value_step)

        frontier_rep = max(0, self._get_frontier_standing())
        detection_step = float(
            self.config.get("frontier_smuggling_detection_reduction_step", 0.01)
        )
        chance *= max(0.35, 1.0 - (frontier_rep * detection_step))

        bribe_level = self._get_bribe_level(target.name)
        bribe_reduction = float(
            self.config.get("bribe_detection_reduction_per_level")
        )
        chance *= max(0.35, 1.0 - (bribe_level * bribe_reduction))

        ship_level = max(1, int(self.get_ship_level()))
        ship_detection_step = max(
            0.0,
            float(self.config.get("contraband_detection_ship_level_step", 0.08)),
        )
        chance *= 1.0 + ((ship_level - 1) * ship_detection_step)

        ship = self.player.spaceship if self.player else None
        if ship and hasattr(ship, "get_effective_scan_evasion_multiplier"):
            chance *= float(ship.get_effective_scan_evasion_multiplier())

        return max(0.01, min(0.95, float(chance)))

    def get_contraband_market_context(self, item_name, planet_name=None, quantity=1):
        item = str(item_name or "").strip()
        if not self.is_contraband_item(item):
            return None

        p_name = planet_name or (
            self.current_planet.name if self.current_planet else ""
        )
        planet = next(
            (p for p in self.planets if p.name == p_name), self.current_planet
        )
        if not planet:
            return None

        profile = self._get_contraband_profile(item)
        local_modifier = None
        if item in getattr(planet, "smuggling_inventory", {}):
            local_modifier = int(planet.smuggling_inventory[item].get("modifier", 100))

        chance = self._get_contraband_detection_chance(
            item, planet=planet, quantity=quantity
        )
        heat = self._get_law_heat(planet.name)
        required_bribe_level = self._get_required_smuggling_bribe_level(item, planet)
        access_open = self._is_smuggling_item_access_open(item, planet)

        return {
            "item": item,
            "tier": str(profile.get("tier", "LOW")),
            "tier_rank": int(profile.get("tier_rank", 1)),
            "heat": int(heat),
            "security_level": int(getattr(planet, "security_level", 0)),
            "detection_chance": float(chance),
            "local_modifier_pct": (
                int(local_modifier) if local_modifier is not None else None
            ),
            "access_open": bool(access_open),
            "bribe_level": int(self._get_bribe_level(planet.name)),
            "required_bribe_level": int(required_bribe_level),
            "buy_price": (
                int(
                    self.get_effective_buy_price(
                        item,
                        planet.get_smuggling_price(item) or base_prices.get(item, 800),
                        planet.name,
                    )
                )
                if item in getattr(planet, "smuggling_inventory", {}) and access_open
                else None
            ),
            "sell_price": int(self.get_market_sell_price(item, planet.name)),
        }

    def _update_planet_events(self):
        now = time.time()
        for planet_name in list(self.planet_events.keys()):
            evt = self.planet_events.get(planet_name) or {}
            if float(evt.get("expires_at", 0)) <= now:
                self.planet_events.pop(planet_name, None)

    def _maybe_roll_planet_event(self, planet):
        if not planet:
            return None

        self._update_planet_events()
        current = self.planet_events.get(planet.name)
        if current:
            return current

        chance = float(self.config.get("planet_event_chance", 0.24))
        chance = max(0.0, min(1.0, chance))
        if random.random() > chance:
            return None

        templates = [
            {
                "type": "FESTIVAL",
                "label": "Festival Surge",
                "desc": "Crowds and celebration spike commodity flow.",
                "buy_mult": 0.92,
                "docking_mult": 1.08,
                "contract_mult": 1.10,
            },
            {
                "type": "EMBARGO",
                "label": "Trade Embargo",
                "desc": "Restrictions tighten supply and docking access.",
                "buy_mult": 1.24,
                "docking_mult": 1.28,
                "contract_mult": 1.24,
            },
            {
                "type": "SHORTAGE",
                "label": "Critical Shortage",
                "desc": "Essential goods are scarce and margins jump.",
                "buy_mult": 1.18,
                "docking_mult": 1.06,
                "contract_mult": 1.16,
            },
            {
                "type": "STRIKE",
                "label": "Dockworkers Strike",
                "desc": "Port throughput drops and schedules destabilize.",
                "buy_mult": 1.12,
                "docking_mult": 0.94,
                "contract_mult": 1.08,
            },
        ]

        pick = random.choice(templates)
        duration_hours = random.randint(2, 6)
        event = {
            **pick,
            "planet": planet.name,
            "created_at": time.time(),
            "expires_at": time.time() + (duration_hours * 3600),
        }
        self.planet_events[planet.name] = event
        return event

    def get_planet_event(self, planet_name=None):
        self._update_planet_events()
        p_name = planet_name or (
            self.current_planet.name if self.current_planet else None
        )
        if not p_name:
            return None
        return self.planet_events.get(p_name)

    def _set_port_spotlight_deal(self, planet):
        if not planet or not planet.items:
            self.current_port_spotlight = None
            return

        item_name = random.choice(list(planet.items.keys()))
        min_discount = int(self.config.get("port_spotlight_discount_min"))
        max_discount = int(self.config.get("port_spotlight_discount_max"))
        if max_discount < min_discount:
            max_discount = min_discount
        discount_pct = max(5, random.randint(min_discount, max_discount))

        self.current_port_spotlight = {
            "planet": planet.name,
            "item": item_name,
            "discount_pct": int(discount_pct),
            "quantity": int(random.randint(4, 12)),
            "expires_at": time.time() + 21600,
        }

    def get_current_port_spotlight_deal(self):
        deal = self.current_port_spotlight
        if not deal or not self.current_planet:
            return None
        if deal.get("planet") != self.current_planet.name:
            return None
        if int(deal.get("quantity", 0)) <= 0:
            return None
        if float(deal.get("expires_at", 0)) <= time.time():
            return None
        return dict(deal)

    def _consume_port_spotlight_quantity(self, item_name, amount):
        deal = self.get_current_port_spotlight_deal()
        if not deal:
            return
        if deal.get("item") != item_name:
            return
        remaining = max(0, int(deal.get("quantity", 0)) - int(amount))
        self.current_port_spotlight["quantity"] = remaining

    def process_commander_stipend(self):
        if not self.player:
            return False, ""

        if not hasattr(self.player, "last_commander_stipend_time"):
            self.player.last_commander_stipend_time = time.time()
            return False, ""

        hours = max(1, int(self.config.get("commander_stipend_hours")))
        interval = hours * 3600
        now = time.time()
        elapsed = now - float(self.player.last_commander_stipend_time)
        if elapsed < interval:
            return False, ""

        cycles = int(elapsed // interval)
        if cycles <= 0:
            return False, ""

        amount = max(100, int(self.config.get("commander_stipend_amount")))
        payout = int(amount * cycles)
        self.player.credits += payout
        self.player.last_commander_stipend_time = float(
            self.player.last_commander_stipend_time
        ) + (cycles * interval)
        return True, f"COMMAND STIPEND RECEIVED: +{payout:,} CR."

    def _mark_planet_attacked(self, planet_name):
        if not self.player:
            return
        if not hasattr(self.player, "attacked_planets"):
            self.player.attacked_planets = {}
        self.player.attacked_planets[planet_name] = time.time()

    def _clear_planet_attack_state(self, planet_name):
        if not self.player or not hasattr(self.player, "attacked_planets"):
            return
        if planet_name in self.player.attacked_planets:
            del self.player.attacked_planets[planet_name]

    def has_attacked_planet(self, planet_name):
        if not self.player or not hasattr(self.player, "attacked_planets"):
            return False
        return planet_name in self.player.attacked_planets

    def _is_planet_price_penalty_active(self, planet_name):
        if not self.player:
            return False
        if not hasattr(self.player, "attacked_planets"):
            self.player.attacked_planets = {}

        ts = self.player.attacked_planets.get(planet_name)
        if ts is None:
            return False

        # If conquered, no hostility surcharge.
        if self.current_planet and self.current_planet.name == planet_name:
            if self.current_planet.owner == self.player.name:
                return False

        return (time.time() - float(ts)) <= self.planet_price_penalty_duration

    def _update_market_dynamics(self):
        now = time.time()
        elapsed_hours = max(0.0, (now - float(self.last_market_update_time)) / 3600.0)
        if elapsed_hours <= 0.0:
            return

        decay_per_hour = max(
            0.01,
            min(0.95, float(self.config.get("economy_momentum_decay_per_hour", 0.10))),
        )
        decay_factor = max(0.0, 1.0 - (decay_per_hour * elapsed_hours))

        cleaned_momentum = {}
        for planet_name, items in self.market_momentum.items():
            planet_bucket = {}
            for item_name, value in (items or {}).items():
                decayed = float(value) * decay_factor
                if abs(decayed) >= 0.0008:
                    planet_bucket[str(item_name)] = max(-0.45, min(0.45, decayed))
            if planet_bucket:
                cleaned_momentum[str(planet_name)] = planet_bucket
        self.market_momentum = cleaned_momentum

        cleaned_volume = {}
        for planet_name, items in self.market_trade_volume.items():
            planet_bucket = {}
            for item_name, value in (items or {}).items():
                decayed = float(value) * decay_factor
                if decayed >= 0.10:
                    planet_bucket[str(item_name)] = decayed
            if planet_bucket:
                cleaned_volume[str(planet_name)] = planet_bucket
        self.market_trade_volume = cleaned_volume

        self.last_market_update_time = now

    def _get_market_momentum_value(self, planet_name, item_name):
        self._update_market_dynamics()
        return float(
            self.market_momentum.get(str(planet_name), {}).get(str(item_name), 0.0)
        )

    def _get_market_volume_value(self, planet_name, item_name):
        self._update_market_dynamics()
        return float(
            self.market_trade_volume.get(str(planet_name), {}).get(str(item_name), 0.0)
        )

    def _apply_market_trade_impact(self, planet_name, item_name, action, quantity):
        self._update_market_dynamics()
        p_name = str(planet_name or "")
        i_name = str(item_name or "")
        if not p_name or not i_name:
            return

        qty = max(1, int(quantity))
        step = max(
            0.003,
            min(0.08, float(self.config.get("economy_momentum_trade_step", 0.018))),
        )
        impact = step * math.sqrt(float(qty))
        if str(action).upper() == "SELL":
            impact *= -1.0

        p_bucket = self.market_momentum.setdefault(p_name, {})
        p_bucket[i_name] = max(
            -0.45, min(0.45, float(p_bucket.get(i_name, 0.0)) + impact)
        )

        v_bucket = self.market_trade_volume.setdefault(p_name, {})
        v_bucket[i_name] = max(0.0, float(v_bucket.get(i_name, 0.0)) + qty)

    def _get_market_price_multiplier(self, planet_name, item_name, action):
        momentum = self._get_market_momentum_value(planet_name, item_name)
        volume = self._get_market_volume_value(planet_name, item_name)

        if str(action).upper() == "SELL":
            mult = 1.0 + (momentum * 0.60)
            damp_step = max(
                0.001,
                min(
                    0.08, float(self.config.get("economy_dampening_volume_step", 0.012))
                ),
            )
            damp_floor = max(
                0.45,
                min(0.95, float(self.config.get("economy_dampening_floor", 0.70))),
            )
            damp = max(damp_floor, 1.0 - (volume * damp_step))
            mult *= damp
            return max(0.45, min(1.45, mult))

        mult = 1.0 + momentum
        mult *= min(1.45, 1.0 + (volume * 0.004))
        return max(0.65, min(1.85, mult))

    def _send_sector_report_if_due(self):
        if not self.player:
            return

        now = time.time()
        if not hasattr(self.player, "last_sector_report_time"):
            self.player.last_sector_report_time = now
            return

        interval_hours = max(
            1.0, float(self.config.get("sector_report_interval_hours", 24))
        )
        interval = interval_hours * 3600.0
        if (now - float(self.player.last_sector_report_time)) < interval:
            return

        self._update_market_dynamics()
        trend_rows = []
        for planet_name, items in self.market_momentum.items():
            for item_name, value in items.items():
                trend_rows.append(
                    (abs(float(value)), str(planet_name), str(item_name), float(value))
                )
        trend_rows.sort(reverse=True)

        lines = ["END-OF-DAY EXCHANGE BRIEF:"]
        if not trend_rows:
            lines.append("- MARKETS HELD STABLE. NO STRONG PRICE MOMENTUM DETECTED.")
        else:
            for _, planet_name, item_name, value in trend_rows[:4]:
                direction = "HEATING" if value > 0 else "COOLING"
                lines.append(
                    f"- {planet_name.upper()}: {item_name.upper()} {direction} ({abs(value) * 100:.1f}% PRESSURE)."
                )

        volume_rows = []
        for planet_name, items in self.market_trade_volume.items():
            for item_name, value in items.items():
                volume_rows.append((float(value), str(planet_name), str(item_name)))
        volume_rows.sort(reverse=True)
        if volume_rows:
            vol, p_name, i_name = volume_rows[0]
            lines.append(
                f"- REBALANCE WATCH: {i_name.upper()} @ {p_name.upper()} ({vol:.0f} RECENT TRADE UNITS)."
            )

        self.send_message(
            self.player.name,
            "SECTOR REPORT",
            "\n".join(lines),
            sender_name="SECTOR EXCHANGE",
        )
        self.player.last_sector_report_time = now

    def get_effective_buy_price(self, item_name, base_price, planet_name=None):
        if not self.player:
            return int(base_price)

        p_name = planet_name or (
            self.current_planet.name if self.current_planet else ""
        )
        price = int(base_price)
        if self._is_planet_price_penalty_active(p_name):
            price = int(round(price * self.planet_price_penalty_multiplier))

        spotlight = self.get_current_port_spotlight_deal()
        if (
            spotlight
            and spotlight.get("planet") == p_name
            and spotlight.get("item") == item_name
        ):
            discount = max(
                0.0, min(0.90, float(spotlight.get("discount_pct", 0)) / 100.0)
            )
            price = int(round(price * (1.0 - discount)))

        evt = self.get_planet_event(p_name)
        if evt:
            price = int(round(price * float(evt.get("buy_mult", 1.0))))

        price = int(
            round(
                price
                * self._get_market_price_multiplier(p_name, item_name, action="BUY")
            )
        )
        return max(1, price)

    def get_market_sell_price(self, item_name, planet_name=None):
        p_name = planet_name or (
            self.current_planet.name if self.current_planet else None
        )
        planet = next(
            (p for p in self.planets if p.name == p_name), self.current_planet
        )

        if planet:
            if item_name in planet.items:
                base_market = self.get_effective_buy_price(
                    item_name, planet.items[item_name], planet.name
                )
                sell_mult = self._get_market_price_multiplier(
                    planet.name, item_name, action="SELL"
                )
                return max(1, int(round(base_market * sell_mult)))
            if item_name in planet.smuggling_inventory:
                smuggle_base = planet.get_smuggling_price(item_name) or 800
                base_market = self.get_effective_buy_price(
                    item_name, smuggle_base, planet.name
                )
                sell_mult = self._get_market_price_multiplier(
                    planet.name, item_name, action="SELL"
                )
                profile = self._get_contraband_profile(item_name)
                tier_step = float(self.config.get("contraband_price_tier_step"))
                contraband_mult = 1.0 + (
                    (int(profile.get("tier_rank", 1)) - 1) * tier_step * 0.55
                )
                item_meta = self._get_smuggling_item_metadata(item_name)
                value_ratio = max(
                    0.0, min(2.0, float(item_meta.get("base_price", 500)) / 4000.0)
                )
                contraband_mult *= 1.0 + (value_ratio * 0.10)
                bribe_level = self._get_bribe_level(planet.name)
                bribe_sell_bonus = float(
                    self.config.get("bribe_smuggling_sell_bonus_per_level")
                )
                contraband_mult *= 1.0 + (max(0, bribe_level) * bribe_sell_bonus)
                return max(1, int(round(base_market * sell_mult * contraband_mult)))

        base_value = int(base_prices.get(item_name, 200))
        salvage_multiplier = float(self.config.get("salvage_sell_multiplier"))
        salvage_multiplier = max(0.05, min(1.0, salvage_multiplier))
        raw_price = int(round(base_value * salvage_multiplier))
        if p_name:
            raw_price = int(
                round(
                    raw_price
                    * self._get_market_price_multiplier(
                        p_name, item_name, action="SELL"
                    )
                )
            )
        return max(1, raw_price)

    def is_planet_hostile_market(self, planet_name=None):
        p_name = planet_name or (
            self.current_planet.name if self.current_planet else None
        )
        if not p_name:
            return False
        return self._is_planet_price_penalty_active(p_name)

    def get_planet_price_penalty_seconds_remaining(self, planet_name=None):
        if not self.player:
            return 0

        p_name = planet_name or (
            self.current_planet.name if self.current_planet else None
        )
        if not p_name:
            return 0

        if not hasattr(self.player, "attacked_planets"):
            self.player.attacked_planets = {}

        ts = self.player.attacked_planets.get(p_name)
        if ts is None:
            return 0

        elapsed = time.time() - float(ts)
        remaining = int(self.planet_price_penalty_duration - elapsed)
        if remaining <= 0:
            return 0

        if self.current_planet and self.current_planet.name == p_name:
            if self.current_planet.owner == self.player.name:
                return 0

        return remaining

    def get_best_trade_opportunities(self, planet_name=None, limit=3):
        origin_name = planet_name or (
            self.current_planet.name if self.current_planet else None
        )
        if not origin_name:
            return []

        origin_planet = next((p for p in self.planets if p.name == origin_name), None)
        if not origin_planet:
            return []

        opportunities = []
        for item_name, origin_base_price in origin_planet.items.items():
            buy_price = self.get_effective_buy_price(
                item_name, origin_base_price, origin_planet.name
            )

            best_destination = None
            best_sell_price = 0
            best_profit = 0

            for destination in self.planets:
                if destination.name == origin_planet.name:
                    continue
                if item_name not in destination.items:
                    continue

                sell_price = self.get_effective_buy_price(
                    item_name, destination.items[item_name], destination.name
                )
                profit = sell_price - buy_price
                if profit > best_profit:
                    best_profit = profit
                    best_destination = destination.name
                    best_sell_price = sell_price

            if best_destination and best_profit > 0:
                opportunities.append(
                    {
                        "item": item_name,
                        "buy_price": int(buy_price),
                        "sell_planet": best_destination,
                        "sell_price": int(best_sell_price),
                        "profit": int(best_profit),
                    }
                )

        opportunities.sort(key=lambda o: (o["profit"], o["sell_price"]), reverse=True)
        return opportunities[: max(1, int(limit))]

    def get_active_trade_contract(self):
        contract = self.active_trade_contract
        if not contract:
            return None

        expires_at = float(contract.get("expires_at", 0))
        if expires_at > 0 and time.time() >= expires_at:
            self.active_trade_contract = None
            self._set_contract_chain_streak(0)
            return None

        remaining = max(
            0, int(contract.get("quantity", 0) - contract.get("delivered", 0))
        )
        if remaining <= 0:
            self.active_trade_contract = None
            return None

        contract_view = dict(contract)
        contract_view.setdefault("arc_total_steps", 1)
        contract_view.setdefault("arc_step", 1)
        contract_view.setdefault("route_type", "LEGAL")
        contract_view["remaining_qty"] = remaining
        contract_view["remaining_seconds"] = max(0, int(expires_at - time.time()))
        return contract_view

    def _pick_contract_route(self):
        authority = self._get_authority_standing()
        frontier = self._get_frontier_standing()
        if frontier > authority + 8:
            return "SMUGGLING"
        return "LEGAL"

    def _generate_trade_contract(self, force=False, arc_state=None):
        if not self.player or not self.current_planet:
            return False, ""
        if not self.config.get("enable_trade_contracts"):
            return False, ""

        if self.get_active_trade_contract() and not force:
            return False, ""

        opportunities = self.get_best_trade_opportunities(
            self.current_planet.name, limit=8
        )
        if not opportunities:
            return False, ""

        route_type = "LEGAL"
        arc_step = 1
        arc_total_steps = 1
        arc_id = f"arc-{int(time.time())}-{random.randint(100, 999)}"
        if arc_state:
            route_type = str(arc_state.get("route_type", "LEGAL")).upper()
            arc_step = max(1, int(arc_state.get("arc_step", 1)))
            arc_total_steps = max(1, int(arc_state.get("arc_total_steps", 1)))
            arc_id = str(arc_state.get("arc_id", arc_id))
        else:
            route_type = self._pick_contract_route()
            arc_total_steps = random.randint(2, 4)
            arc_step = 1

        smuggling_items = set(self.get_smuggling_item_names())
        if route_type == "SMUGGLING":
            route_filtered = [o for o in opportunities if o["item"] in smuggling_items]
        else:
            route_filtered = [
                o for o in opportunities if o["item"] not in smuggling_items
            ]
        if route_filtered:
            opportunities = route_filtered

        pick_pool = opportunities[: max(1, min(4, len(opportunities)))]
        pick = random.choice(pick_pool)

        ship_cargo = max(
            5,
            int(
                self.player.spaceship.get_effective_max_cargo()
                if hasattr(self.player.spaceship, "get_effective_max_cargo")
                else self.player.spaceship.current_cargo_pods
            ),
        )
        qty_low = max(3, min(8, ship_cargo // 6))
        qty_high = max(qty_low, min(20, ship_cargo // 3))
        quantity = random.randint(qty_low, qty_high)

        reward_mult = float(self.config.get("trade_contract_reward_multiplier"))
        chain_bonus = self._get_contract_chain_bonus_factor()
        event_mult = 1.0
        evt = self.get_planet_event(self.current_planet.name)
        if evt:
            event_mult = max(0.75, min(1.8, float(evt.get("contract_mult", 1.0))))
        reward = int(
            max(
                200,
                pick["profit"]
                * quantity
                * reward_mult
                * (1.0 + chain_bonus)
                * event_mult,
            )
        )
        hours = max(1, int(self.config.get("trade_contract_hours")))
        now = time.time()

        self.active_trade_contract = {
            "item": pick["item"],
            "source_planet": self.current_planet.name,
            "destination_planet": pick["sell_planet"],
            "quantity": int(quantity),
            "delivered": 0,
            "reward": int(reward),
            "chain_bonus_pct": int(round(chain_bonus * 100)),
            "created_at": now,
            "expires_at": now + (hours * 3600),
            "route_type": route_type,
            "arc_id": arc_id,
            "arc_step": int(arc_step),
            "arc_total_steps": int(arc_total_steps),
        }
        return (
            True,
            f"NEW CONTRACT [{route_type}] STEP {arc_step}/{arc_total_steps}: DELIVER {quantity}x {pick['item'].upper()} TO {pick['sell_planet'].upper()} FOR {reward:,} CR.",
        )

    def reroll_trade_contract(self):
        if not self.player:
            return False, ""

        cost = max(0, int(self.config.get("contract_reroll_cost")))
        if self.player.credits < cost:
            return False, f"NEED {cost:,} CR TO REROLL CONTRACT."

        self.player.credits -= cost
        self.active_trade_contract = None
        self._set_contract_chain_streak(0)
        ok, msg = self._generate_trade_contract(force=True)
        if ok:
            return True, f"CONTRACT REROLLED (-{cost:,} CR). {msg}"
        return False, "UNABLE TO GENERATE NEW CONTRACT RIGHT NOW."

    def _apply_trade_contract_progress(self, item_name, sold_qty):
        contract = self.get_active_trade_contract()
        if not contract:
            return False, ""

        if self.current_planet.name != contract.get("destination_planet"):
            return False, ""
        if item_name != contract.get("item"):
            return False, ""

        remaining = int(contract.get("remaining_qty", 0))
        if remaining <= 0:
            return False, ""

        delivered = min(int(sold_qty), remaining)
        self.active_trade_contract["delivered"] = int(
            self.active_trade_contract.get("delivered", 0) + delivered
        )

        left = int(
            self.active_trade_contract["quantity"]
            - self.active_trade_contract["delivered"]
        )
        if left <= 0:
            completed = dict(self.active_trade_contract)
            reward = int(completed.get("reward", 0))
            self.player.credits += reward
            self.active_trade_contract = None
            self._set_contract_chain_streak(self._get_contract_chain_streak() + 1)

            route_type = str(completed.get("route_type", "LEGAL")).upper()
            arc_step = int(completed.get("arc_step", 1))
            arc_total_steps = int(completed.get("arc_total_steps", 1))

            rep_bonus = int(self.config.get("reputation_contract_completion_bonus"))
            if route_type == "SMUGGLING":
                new_frontier = self._adjust_frontier_standing(max(2, rep_bonus // 2))
                new_auth = self._adjust_authority_standing(-max(1, rep_bonus // 4))
            else:
                new_auth = self._adjust_authority_standing(rep_bonus)
                new_frontier = self._adjust_frontier_standing(1)

            milestone_parts = []
            if route_type == "SMUGGLING":
                milestone_parts.append("MILESTONE: FRONTIER NETWORK FAVOR")
            else:
                legal_bonus = max(100, int(round(reward * 0.20)))
                self.player.credits += legal_bonus
                milestone_parts.append(f"MILESTONE BONUS +{legal_bonus:,} CR")

            next_arc_msg = ""
            if arc_step < arc_total_steps:
                arc_state = {
                    "route_type": route_type,
                    "arc_id": completed.get("arc_id"),
                    "arc_step": arc_step + 1,
                    "arc_total_steps": arc_total_steps,
                }
                next_ok, next_msg = self._generate_trade_contract(
                    force=True, arc_state=arc_state
                )
                if next_ok and next_msg:
                    next_arc_msg = f" NEXT ARC READY. {next_msg}"

            next_chain_bonus = int(round(self._get_contract_chain_bonus_factor() * 100))
            milestone_text = " | ".join(milestone_parts)
            return (
                True,
                f"CONTRACT COMPLETE [{route_type}] STEP {arc_step}/{arc_total_steps}! RECEIVED {reward:,} CR. CHAIN x{self._get_contract_chain_streak()} ({next_chain_bonus}% NEXT BONUS). AUTH {new_auth:+d} | FRONTIER {new_frontier:+d}. {milestone_text}.{next_arc_msg}",
            )

        return True, f"CONTRACT PROGRESS: {left} UNIT(S) REMAINING."

    def get_item_market_snapshot(
        self, item_name, origin_planet_name=None, compare_planet_name=None
    ):
        origin_name = origin_planet_name or (
            self.current_planet.name if self.current_planet else None
        )
        if not origin_name:
            return None

        origin_planet = next((p for p in self.planets if p.name == origin_name), None)
        if not origin_planet:
            return None
        if item_name not in origin_planet.items:
            return None

        origin_price = self.get_effective_buy_price(
            item_name, origin_planet.items[item_name], origin_planet.name
        )

        offers = []
        for p in self.planets:
            if item_name not in p.items:
                continue
            eff = self.get_effective_buy_price(item_name, p.items[item_name], p.name)
            offers.append((p.name, int(eff)))

        if not offers:
            return None

        avg_price = int(sum(price for _, price in offers) / len(offers))

        best_sell_planet = None
        best_sell_price = origin_price
        best_profit = 0
        for p_name, sell_price in offers:
            if p_name == origin_name:
                continue
            profit = sell_price - origin_price
            if profit > best_profit:
                best_profit = profit
                best_sell_planet = p_name
                best_sell_price = sell_price

        compare_price = None
        compare_delta = 0
        if compare_planet_name:
            compare_planet = next(
                (p for p in self.planets if p.name == compare_planet_name), None
            )
            if compare_planet and item_name in compare_planet.items:
                compare_price = self.get_effective_buy_price(
                    item_name, compare_planet.items[item_name], compare_planet.name
                )
                compare_delta = int(compare_price - origin_price)

        return {
            "item": item_name,
            "origin_planet": origin_name,
            "origin_price": int(origin_price),
            "avg_price": int(avg_price),
            "best_sell_planet": best_sell_planet,
            "best_sell_price": int(best_sell_price),
            "best_profit": int(best_profit),
            "compare_price": int(compare_price) if compare_price is not None else None,
            "compare_delta": int(compare_delta),
        }

    def bribe_npc(self):
        planet = self.current_planet
        self._refresh_bribe_registry()
        quote = self._get_bribe_quote(planet)
        if not quote.get("can_bribe", False):
            reason = str(quote.get("reason", "This individual cannot be bribed."))
            return False, reason

        cost = int(quote.get("cost", 0))
        if self.player.credits < cost:
            return False, f"Not enough credits! {planet.npc_name} wants {cost:,} CR."

        self.player.credits -= cost

        current_level = int(quote.get("current_level", 0))
        next_level = int(quote.get("next_level", current_level + 1))
        duration_h = max(
            1.0,
            float(self.config.get("bribe_base_duration_hours"))
            + (
                next_level * float(self.config.get("bribe_duration_per_level_hours"))
            ),
        )
        expires_at = time.time() + (duration_h * 3600.0)
        self.bribe_registry[planet.name] = {
            "level": int(next_level),
            "expires_at": float(expires_at),
        }
        self._refresh_bribe_registry()

        auth_hit = max(1, int(self.config.get("bribe_authority_hit_per_level")))
        front_gain = max(1, int(self.config.get("bribe_frontier_gain_per_level")))
        new_auth = self._adjust_authority_standing(-auth_hit * max(1, next_level))
        new_frontier = self._adjust_frontier_standing(front_gain * max(1, next_level))

        heat_drop = int(self.config.get("bribe_heat_reduction_per_level")) * max(
            1, next_level
        )
        heat_after = self._adjust_law_heat(planet.name, -heat_drop)
        remaining = self._get_bribe_time_remaining_seconds(planet.name)

        return (
            True,
            f"Bribe accepted. {planet.npc_name} grants market access level {next_level}/{int(quote.get('max_level', 3))}. AUTH {new_auth:+d} | FRONTIER {new_frontier:+d} | HEAT {heat_after}% | ACCESS {remaining // 3600}H {(remaining % 3600) // 60:02d}M.",
        )

    def trade_item(self, item_name, action, quantity=1):
        """Action: 'BUY' or 'SELL'"""
        planet = self.current_planet
        player = self.player
        self._refresh_bribe_registry()
        self._update_law_heat_decay()
        self._normalize_player_inventory()
        item_name = self._canonical_item_name(item_name)

        # Security Check for Smuggling
        smuggling_item_names = self.get_smuggling_item_names()

        is_contraband = item_name in smuggling_item_names
        contraband_profile = (
            self._get_contraband_profile(item_name) if is_contraband else None
        )

        if is_contraband and planet.security_level > 0:
            chance = self._get_contraband_detection_chance(
                item_name,
                planet=planet,
                quantity=max(1, int(quantity)),
            )
            if random.random() < chance:
                ship_level = max(1, int(self.get_ship_level()))
                heat_ship_step = max(
                    0.0,
                    float(self.config.get("law_heat_detected_ship_level_step", 0.18)),
                )
                detected_heat = int(
                    round(
                        int(self.config.get("law_heat_gain_detected", 8))
                        * (1.0 + ((ship_level - 1) * heat_ship_step))
                    )
                )
                heat_after = self._adjust_law_heat(planet.name, max(1, detected_heat))
                if planet.security_level == 2:
                    return (
                        False,
                        f"SECURITY ALERT! {planet.vendor} DEFENSES DETECTED {contraband_profile.get('tier', 'HIGH')} CONTRABAND! HEAT {heat_after}%! PREPARE TO BE BOARDED!",
                    )
                else:
                    return (
                        False,
                        f"SECURITY WARNING: {planet.vendor} scanners flagged contraband signatures. HEAT {heat_after}%. Transaction blocked.",
                    )

        # Check standard items
        price = 0
        is_smuggling = False
        used_salvage_buyback = False

        if item_name in planet.items:
            price = self.get_effective_buy_price(
                item_name, planet.items[item_name], planet.name
            )
        elif item_name in planet.smuggling_inventory:
            required_level = self._get_required_smuggling_bribe_level(item_name, planet)
            current_level = self._get_bribe_level(planet.name)
            if self._is_smuggling_item_access_open(item_name, planet):
                base_smuggle_price = planet.get_smuggling_price(item_name)
                price = self.get_effective_buy_price(
                    item_name, base_smuggle_price, planet.name
                )
                is_smuggling = True
            else:
                return (
                    False,
                    f"CONTACT LEVEL TOO LOW. {item_name.upper()} REQUIRES BRIBE LVL {required_level} (CURRENT {current_level}).",
                )
        else:
            # Maybe they are selling a smuggling item back to someone else?
            if action == "SELL" and item_name in player.inventory:
                if is_contraband:
                    # Can sell if it's a hub OR they already have it in smuggling_inventory
                    if (
                        planet.is_smuggler_hub
                        or item_name in planet.smuggling_inventory
                    ):
                        # Use existing smuggling price or generate one
                        price = planet.get_smuggling_price(item_name) or 800
                    else:
                        price = self.get_market_sell_price(item_name, planet.name)
                        used_salvage_buyback = True
                else:
                    price = self.get_market_sell_price(item_name, planet.name)
                    used_salvage_buyback = True
            else:
                return False, "Item not available or restricted."

        if action == "BUY":
            if is_smuggling:
                frontier_rep = max(0, self._get_frontier_standing())
                discount_step = float(
                    self.config.get("frontier_smuggling_discount_step", 0.005)
                )
                bribe_level = self._get_bribe_level(planet.name)
                bribe_discount_step = float(
                    self.config.get("bribe_smuggling_discount_per_level")
                )
                smuggle_discount = min(
                    0.40,
                    (frontier_rep * discount_step)
                    + (bribe_level * bribe_discount_step),
                )
                if smuggle_discount > 0:
                    price = max(1, int(round(price * (1.0 - smuggle_discount))))
                # Check supply
                if planet.smuggling_inventory[item_name]["quantity"] < quantity:
                    return (
                        False,
                        f"Only {planet.smuggling_inventory[item_name]['quantity']} units available.",
                    )

                success, msg = player.buy_item(item_name, price, quantity)
                if success:
                    planet.smuggling_inventory[item_name]["quantity"] -= quantity
                    if planet.smuggling_inventory[item_name]["quantity"] <= 0:
                        del planet.smuggling_inventory[item_name]
                    self._consume_port_spotlight_quantity(item_name, quantity)
                    self._apply_market_trade_impact(
                        planet.name, item_name, "BUY", quantity
                    )
                    heat_delta = int(self.config.get("law_heat_gain_trade", 2))
                    if contraband_profile:
                        heat_delta = int(
                            round(
                                heat_delta
                                * float(contraband_profile.get("heat_mult", 1.0))
                            )
                        )
                    item_meta = self._get_smuggling_item_metadata(item_name)
                    value_ratio = max(
                        0.0, min(2.5, float(item_meta.get("base_price", 500)) / 4000.0)
                    )
                    heat_delta = int(
                        round(float(heat_delta) * (1.0 + (value_ratio * 0.45)))
                    )
                    heat_after = self._adjust_law_heat(
                        planet.name, max(1, heat_delta * max(1, int(quantity)))
                    )
                    tier = (
                        str(contraband_profile.get("tier", "LOW"))
                        if contraband_profile
                        else "LOW"
                    )
                    msg += f" {tier} CONTRABAND ACQUIRED. HEAT {heat_after}%."
                return success, msg
            else:
                success, msg = player.buy_item(item_name, price, quantity)
                if success:
                    self._consume_port_spotlight_quantity(item_name, quantity)
                    self._apply_market_trade_impact(
                        planet.name, item_name, "BUY", quantity
                    )
                return success, msg
        elif action == "SELL":
            # If we sell a smuggling item to a planet that has it in its inventory, increase its quantity
            if is_contraband:
                bribe_level = self._get_bribe_level(planet.name)
                sell_bonus_step = float(
                    self.config.get("bribe_smuggling_sell_bonus_per_level")
                )
                sell_mult = 1.0 + (max(0, bribe_level) * sell_bonus_step)
                if not planet.is_smuggler_hub and bribe_level <= 0:
                    sell_mult *= max(
                        0.35,
                        float(self.config.get("smuggle_nonhub_sell_penalty")),
                    )
                price = max(1, int(round(price * sell_mult)))

            success, msg = player.sell_item(item_name, price, quantity)
            if success and is_contraband and item_name in planet.smuggling_inventory:
                planet.smuggling_inventory[item_name]["quantity"] += quantity
            if success:
                self._apply_market_trade_impact(
                    planet.name, item_name, "SELL", quantity
                )
            if success and is_contraband:
                rep_penalty_per_unit = abs(
                    int(self.config.get("reputation_contraband_trade_penalty"))
                )
                if contraband_profile:
                    rep_penalty_per_unit = max(
                        1,
                        int(
                            round(
                                rep_penalty_per_unit
                                * (
                                    1.0
                                    + (
                                        (
                                            int(contraband_profile.get("tier_rank", 1))
                                            - 1
                                        )
                                        * 0.35
                                    )
                                )
                            )
                        ),
                    )
                item_meta = self._get_smuggling_item_metadata(item_name)
                value_ratio = max(
                    0.0, min(2.5, float(item_meta.get("base_price", 500)) / 3500.0)
                )
                rep_penalty_per_unit = max(
                    rep_penalty_per_unit,
                    int(round(rep_penalty_per_unit * (1.0 + (value_ratio * 0.55)))),
                )
                heat_after = self._adjust_law_heat(
                    planet.name,
                    max(1, int(self.config.get("law_heat_gain_trade", 2)))
                    * max(1, int(quantity)),
                )
                heat_after = self._adjust_law_heat(
                    planet.name,
                    max(
                        0,
                        int(
                            round(
                                max(0.0, value_ratio - 0.35)
                                * 4.0
                                * max(1, int(quantity))
                            )
                        ),
                    ),
                )
                heat_penalty_step = float(
                    self.config.get("law_heat_penalty_step", 0.20)
                )
                heat_penalty_mult = 1.0 + ((heat_after / 100.0) * heat_penalty_step)
                rep_hit = max(
                    1,
                    int(
                        round(int(quantity) * rep_penalty_per_unit * heat_penalty_mult)
                    ),
                )
                frontier_gain_per_unit = abs(
                    int(self.config.get("frontier_contraband_trade_bonus", 1))
                )
                if contraband_profile:
                    frontier_gain_per_unit = max(
                        1,
                        int(
                            round(
                                frontier_gain_per_unit
                                * (
                                    1.0
                                    + (
                                        (
                                            int(contraband_profile.get("tier_rank", 1))
                                            - 1
                                        )
                                        * 0.20
                                    )
                                )
                            )
                        ),
                    )
                frontier_gain = max(1, int(quantity) * frontier_gain_per_unit)
                new_auth = self._adjust_authority_standing(-rep_hit)
                new_frontier = self._adjust_frontier_standing(frontier_gain)
                tier = (
                    str(contraband_profile.get("tier", "LOW"))
                    if contraband_profile
                    else "LOW"
                )
                msg += f" {tier} TRADE LOGGED. AUTH {new_auth:+d} | FRONTIER {new_frontier:+d} | HEAT {heat_after}%."
            if success and used_salvage_buyback:
                msg += " OFFLOADED VIA LOCAL SALVAGE BROKER."
            if success:
                c_prog, c_msg = self._apply_trade_contract_progress(item_name, quantity)
                if c_prog and c_msg:
                    msg += f" {c_msg}"
            return success, msg

        return False, "Invalid action."

    def sell_non_market_cargo(self):
        if not self.player or not self.current_planet:
            return False, ""

        planet = self.current_planet
        buyable = set(planet.items.keys())
        for smuggle_item, data in dict(
            getattr(planet, "smuggling_inventory", {}) or {}
        ).items():
            if int((data or {}).get("quantity", 0)) <= 0:
                continue
            if self._is_smuggling_item_access_open(smuggle_item, planet):
                buyable.add(smuggle_item)

        sold_items = 0
        sold_units = 0
        start_credits = int(self.player.credits)
        messages = []

        for item_name, qty in list(self.player.inventory.items()):
            if qty <= 0 or item_name in buyable:
                continue
            success, msg = self.trade_item(item_name, "SELL", int(qty))
            if success:
                sold_items += 1
                sold_units += int(qty)
                if msg:
                    messages.append(msg)

        if sold_items <= 0:
            return False, "NO NON-MARKET CARGO TO QUICK-SELL."

        earned = int(self.player.credits - start_credits)
        summary = f"QUICK-SOLD {sold_units} UNIT(S) ACROSS {sold_items} ITEM TYPE(S) FOR {earned:,} CR."
        if messages:
            return True, f"{summary}"
        return True, summary

    def check_contraband_detection(self):
        """Checks if current planet security detects contraband in player's hold."""
        self._refresh_bribe_registry()
        if self.current_planet.security_level <= 0:
            return False, ""

        contraband_names = set(self.get_smuggling_item_names())
        contraband_in_hold = {
            item: int(qty)
            for item, qty in self.player.inventory.items()
            if item in contraband_names and int(qty) > 0
        }
        has_contraband = bool(contraband_in_hold)

        if not has_contraband:
            return False, ""

        highest_item = max(
            contraband_in_hold.keys(),
            key=lambda item: (
                int(self._get_contraband_profile(item).get("tier_rank", 1)),
                int(contraband_in_hold.get(item, 0)),
            ),
        )
        total_qty = max(1, sum(int(v) for v in contraband_in_hold.values()))
        chance = self._get_contraband_detection_chance(
            highest_item,
            planet=self.current_planet,
            quantity=total_qty,
        )
        if random.random() < chance:
            ship_level = max(1, int(self.get_ship_level()))
            heat_ship_step = max(
                0.0,
                float(self.config.get("law_heat_detected_ship_level_step", 0.18)),
            )
            detected_heat = int(
                round(
                    int(self.config.get("law_heat_gain_detected", 8))
                    * (1.0 + ((ship_level - 1) * heat_ship_step))
                )
            )
            heat_after = self._adjust_law_heat(
                self.current_planet.name, max(1, detected_heat)
            )
            profile = self._get_contraband_profile(highest_item)
            if self.current_planet.security_level == 2:
                return (
                    True,
                    f"SECURITY ALERT! {self.current_planet.vendor} SCANNERS DETECTED {profile.get('tier', 'HIGH')} CONTRABAND ({highest_item.upper()}). HEAT {heat_after}%! PREPARE TO BE BOARDED!",
                )
            else:
                return (
                    True,
                    f"SECURITY WARNING: {self.current_planet.vendor} flagged your vessel for contraband signatures ({highest_item.upper()}). HEAT {heat_after}%.",
                )

        return False, ""
