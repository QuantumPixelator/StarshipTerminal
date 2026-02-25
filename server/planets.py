import random
import os
import math


def get_absolute_path(relative_path):
    """Helper to get absolute path relative to this file's directory."""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    # Assets are now in assets/texts folder
    path = os.path.join(current_dir, "assets", "texts", relative_path)
    return path


def load_base_prices():
    base_prices = {}
    active_item_names = set()
    file_path = get_absolute_path("items.txt")

    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as file:
                lines = file.readlines()

            for line in lines:
                try:
                    line = line.strip()
                    if not line or "," not in line:
                        continue
                    parts = [p.strip() for p in line.split(",")]
                    if len(parts) < 2:
                        continue

                    item = parts[0].strip()
                    if not item:
                        continue

                    price_val = int(parts[1].strip())
                    is_active = True
                    if len(parts) >= 3 and parts[2]:
                        is_active = parts[2].strip().lower() in (
                            "1",
                            "true",
                            "yes",
                            "on",
                        )

                    if is_active:
                        base_prices[item] = price_val
                        active_item_names.add(item)
                except (ValueError, IndexError):
                    pass
    except Exception as e:
        print(f"Error loading items.txt: {e}")

    if not base_prices:
        base_prices = {"Standard Fuel": 10, "Rations": 5}
        active_item_names = set(base_prices.keys())

    return base_prices, active_item_names


# Global base prices loaded once
base_prices, active_item_names = load_base_prices()


def _estimate_contraband_tier(item_name):
    name = str(item_name or "").strip().lower()
    if not name:
        return 1

    seed = sum((idx + 1) * ord(ch) for idx, ch in enumerate(name))
    tier = (seed % 4) + 1

    high_markers = [
        "quantum",
        "artifact",
        "void",
        "wormhole",
        "antimatter",
        "alien",
    ]
    if any(marker in name for marker in high_markers):
        tier = min(4, tier + 1)
    return int(max(1, min(4, tier)))


def _roll_smuggle_modifier(item_name, security_level, is_hub):
    tier = _estimate_contraband_tier(item_name)
    base_price = max(1, int(base_prices.get(item_name, 500)))

    tier_ranges = {
        1: (95, 165),
        2: (120, 230),
        3: (150, 300),
        4: (185, 380),
    }
    low, high = tier_ranges.get(tier, (110, 240))

    if security_level >= 2:
        low = int(round(low * 1.12))
        high = int(round(high * 1.20))
    elif security_level <= 0:
        low = int(round(low * 0.92))
        high = int(round(high * 0.95))

    if is_hub:
        low = int(round(low * 0.92))
        high = int(round(high * 0.98))

    # Ensure expensive contraband trends higher than low-value contraband.
    price_scale = max(0.85, min(1.28, (base_price / 1200.0) + 0.78))
    low = int(round(low * price_scale))
    high = int(round(high * price_scale))

    low = max(85, min(low, 520))
    high = max(low + 5, min(high, 620))
    modifier = random.randint(low, high)

    # Small deterministic jitter from item name keeps variety without chaos.
    jitter = (sum(ord(c) for c in str(item_name)) % 9) - 4
    modifier = max(80, min(650, int(modifier + jitter)))
    return int(modifier), int(tier)


def _required_bribe_level_for_item(item_name, base_price, security_level, is_hub):
    price = max(1, int(base_price or base_prices.get(item_name, 500)))
    if price >= 16000:
        level = 3
    elif price >= 7000:
        level = 2
    elif price >= 2200:
        level = 1
    else:
        level = 0

    if int(security_level) >= 2:
        level = min(3, level + 1)
    if bool(is_hub):
        level = max(0, level - 1)
    return int(max(0, min(3, level)))


def _load_smuggling_item_pool():
    items = []
    metadata = {}
    s_path = get_absolute_path("smuggle_items.txt")
    try:
        if os.path.exists(s_path):
            with open(s_path, "r", encoding="utf-8") as f:
                for line in f:
                    raw = line.strip()
                    if not raw:
                        continue
                    parts = [part.strip() for part in raw.split(",")]
                    item = parts[0]
                    if not item:
                        continue
                    if item not in active_item_names:
                        continue
                    if item not in items:
                        items.append(item)
                    base_price = int(base_prices.get(item, 500))
                    if len(parts) >= 2 and parts[1]:
                        try:
                            base_price = max(1, int(parts[1]))
                        except ValueError:
                            base_price = int(base_prices.get(item, 500))

                    required_level = None
                    if len(parts) >= 3 and parts[2]:
                        try:
                            required_level = max(0, min(3, int(parts[2])))
                        except ValueError:
                            required_level = None

                    metadata[item] = {
                        "base_price": int(base_price),
                        "required_bribe_level": required_level,
                    }
    except Exception:
        pass
    return items, metadata


def _ensure_smuggling_distribution(planets, smuggle_items, smuggle_metadata=None):
    if not planets or not smuggle_items:
        return

    eligible = [p for p in planets if hasattr(p, "smuggling_inventory")]
    if not eligible:
        return

    min_planets_per_item = min(3, len(eligible))

    for item in smuggle_items:
        current_holders = [p for p in eligible if item in p.smuggling_inventory]
        needed = max(0, min_planets_per_item - len(current_holders))

        if needed > 0:
            candidates = [p for p in eligible if item not in p.smuggling_inventory]
            candidates.sort(
                key=lambda p: (
                    0 if bool(getattr(p, "is_smuggler_hub", False)) else 1,
                    int(getattr(p, "security_level", 0)),
                    str(getattr(p, "name", "")),
                )
            )

            for planet in candidates[:needed]:
                item_meta = dict((smuggle_metadata or {}).get(item, {}) or {})
                base_price = int(
                    item_meta.get("base_price", base_prices.get(item, 500))
                )
                modifier, tier = _roll_smuggle_modifier(
                    item,
                    int(getattr(planet, "security_level", 0)),
                    bool(getattr(planet, "is_smuggler_hub", False)),
                )
                name_jitter = (sum(ord(c) for c in planet.name) % 27) - 13
                modifier = max(80, min(650, int(modifier + name_jitter)))

                required_level = item_meta.get("required_bribe_level")
                if required_level is None:
                    required_level = _required_bribe_level_for_item(
                        item,
                        base_price,
                        int(getattr(planet, "security_level", 0)),
                        bool(getattr(planet, "is_smuggler_hub", False)),
                    )

                if planet.is_smuggler_hub:
                    qty_low = 2
                    qty_high = max(3, 8 - tier)
                else:
                    qty_low = 1
                    qty_high = max(1, 4 - tier)

                planet.smuggling_inventory[item] = {
                    "modifier": int(modifier),
                    "quantity": int(random.randint(qty_low, qty_high)),
                    "tier": int(tier),
                    "base_price": int(base_price),
                    "required_bribe_level": int(required_level),
                }

        holders = [p for p in eligible if item in p.smuggling_inventory]
        if len(holders) > 1:
            seen_modifiers = set()
            for idx, planet in enumerate(holders):
                data = planet.smuggling_inventory.get(item, {})
                modifier = int(data.get("modifier", 100))
                if modifier in seen_modifiers:
                    data["modifier"] = int(
                        max(80, min(650, modifier + (12 * (idx + 1))))
                    )
                seen_modifiers.add(int(data.get("modifier", modifier)))


class Planet:
    def __init__(
        self,
        name,
        population,
        description,
        vendor,
        tradecenter,
        defenders,
        shields,
        bank,
        items,
        max_defenders=None,
        max_shields=None,
        base_credits=None,
        x=0,
        y=0,
    ):
        self.name = name
        self.population = population
        self.description = description
        self.vendor = vendor
        self.tradecenter = tradecenter
        self.defenders = defenders
        self.shields = shields
        self.base_defenders = defenders
        self.base_shields = shields
        self.max_shields = max(int(shields), int(max_shields or (shields * 2)))
        self.max_defenders = max(int(defenders), int(max_defenders or (defenders * 2)))
        self.base_max_shields = int(self.max_shields)
        self.base_max_defenders = int(self.max_defenders)
        self.bank = bank

        # Convert absolute prices to percentages of base prices
        self.item_modifiers = {}
        for item, price in items.items():
            base = base_prices.get(item, price)
            modifier = int((price / base) * 100) if base > 0 else 100
            self.item_modifiers[item] = modifier

        self.x = x
        self.y = y
        self.repair_multiplier = None  # None means no repairs at this planet

        # New NPC and Market attributes
        self.npc_name = "Unknown"
        self.npc_personality = "neutral"
        self.docking_fee = 0
        self.welcome_msg = "Docking request approved."
        self.unwelcome_msg = "Identity confirmed. Proceed with caution."
        self.bribe_cost = 0
        self.is_smuggler_hub = False
        self.npc_remarks = ["Good day.", "What do you need?", "Let's trade."]
        self.owner = None  # Player name who owns the planet
        # Starting treasury = 20% of population (rounded)
        if base_credits is None:
            self.credit_balance = int(round(population * 0.20))
        else:
            self.credit_balance = max(0, int(base_credits))
        self.base_credit_balance = int(self.credit_balance)
        self.credits_initialized = (
            True  # Set once; prevents re-seeding on server restart
        )
        self.last_credit_interest_time = 0.0
        self.crew_services = []  # List of {"type": "weapons", "levels": [1, 2, 3]}
        self.smuggling_inventory = {}  # {item_name: {"modifier": p_mod, "quantity": q}}
        self.security_level = 0  # 0: None, 1: Moderate, 2: High (Urth, Celestia)

        self.last_defense_regen_time = 0
        self.specializations = {"exports": [], "imports": []}

    @property
    def items(self):
        """Calculates absolute prices based on current modifiers and global base prices."""
        prices = {}
        for item, mod in self.item_modifiers.items():
            base = base_prices.get(item, 0)
            prices[item] = int(round(base * (mod / 100)))
        return prices

    def get_smuggling_price(self, item_name):
        """Calculates absolute price for a smuggling item."""
        if item_name in self.smuggling_inventory:
            data = self.smuggling_inventory[item_name]
            base = base_prices.get(item_name)
            # Support both old absolute price and new modifier for compatibility
            if "modifier" in data:
                if base is None or int(base) <= 0:
                    return None
                return int(round(base * (data["modifier"] / 100)))
            raw_price = data.get("price")
            try:
                raw_price = int(raw_price)
            except (TypeError, ValueError):
                return None
            return raw_price if raw_price > 0 else None
        return None

    def fluctuate_prices(self):
        """Randomly fluctuate item price modifiers. Standard +/- 15%, Smuggling +/- 40%."""
        import random

        # Standard items: Fluctuate modifier between 85% and 115% of current modifier
        for item in self.item_modifiers:
            variance = random.uniform(0.85, 1.15)
            self.item_modifiers[item] = max(
                50, int(self.item_modifiers[item] * variance)
            )

        # Smuggling items
        for item, data in self.smuggling_inventory.items():
            # Wildly fluctuating modifiers
            variance = random.uniform(0.5, 1.5)
            if "modifier" not in data:
                # Initialize modifier if it was absolute price before
                base = base_prices.get(item, 1000)
                data["modifier"] = int((data.get("price", 1000) / base) * 100)

            data["modifier"] = max(100, int(data["modifier"] * variance))
            # Occasionally restock a small amount (5% chance)
            if random.random() < 0.05:
                data["quantity"] += random.randint(1, 2)

    def get_info(self):
        bank_status = "available" if self.bank else "not available"

        return {
            "name": self.name,
            "population": self.population,
            "description": self.description,
            "vendor": self.vendor,
            "tradecenter": self.tradecenter,
            "defenders": self.defenders,
            "shields": self.shields,
            "bank": bank_status,
            "owner": self.owner,
            "credit_balance": int(getattr(self, "credit_balance", 0)),
            "items": self.items,
            "x": self.x,
            "y": self.y,
        }


def _rebalance_planet_economy(planets):
    if not planets:
        return

    rng = random.Random(424242)
    all_items = [item for item in base_prices.keys() if item]

    role_biases = {
        "Urth": {
            "must": ["Fuel Cells", "Cargo Pod", "Nanobot Repair Kits"],
            "discount": ["Fuel Cells", "Nanobot Repair Kits", "Cheap Plastic Toys"],
            "premium": ["Stealth Cloaking Devices"],
        },
        "Mastodrun": {
            "must": ["Warp Drives", "Cargo Pod", "Energy Shields"],
            "discount": ["Warp Drives", "Cargo Pod", "Quantum Data Chips"],
            "premium": ["Solar Seafood Platter"],
        },
        "Zephyrion": {
            "must": [
                "Neural Interface Upgrades",
                "Cybernetic Implants",
                "Energy Shields",
            ],
            "discount": [
                "Neural Interface Upgrades",
                "Cybernetic Implants",
                "Holographic Projectors",
            ],
            "premium": ["Cheap Plastic Toys"],
        },
        "Novos": {
            "must": [
                "Stealth Cloaking Devices",
                "Photon Destabilizer",
                "Fighter Squadron",
            ],
            "discount": [
                "Stealth Cloaking Devices",
                "Photon Destabilizer",
                "Fighter Squadron",
            ],
            "premium": ["Purified Water Extractor"],
        },
        "Shadien": {
            "must": [
                "Stealth Cloaking Devices",
                "Quantum Data Chips",
                "Hyperdrive Stabilizers",
            ],
            "discount": ["Stealth Cloaking Devices", "Quantum Data Chips"],
            "premium": ["Purified Water Extractor"],
        },
        "Asterudor": {
            "must": ["Fuel Cells", "Asteroid Mining Drones", "Fusion Reactors"],
            "discount": ["Fuel Cells", "Asteroid Mining Drones", "Fusion Reactors"],
            "premium": ["Bio-Regeneration Serums"],
        },
        "Atlantiz": {
            "must": [
                "Purified Water Extractor",
                "Solar Seafood Platter",
                "Bio-Regeneration Serums",
            ],
            "discount": ["Purified Water Extractor", "Solar Seafood Platter"],
            "premium": ["Nuclear Heater Core"],
        },
        "Pyrothos": {
            "must": ["Fighter Squadron", "Nuclear Heater Core", "Photon Destabilizer"],
            "discount": [
                "Fighter Squadron",
                "Nuclear Heater Core",
                "Photon Destabilizer",
            ],
            "premium": ["Frigid Air Appliance"],
        },
        "Aurora": {
            "must": [
                "Cryogenic Stasis Pods",
                "Frigid Air Appliance",
                "Nuclear Heater Core",
            ],
            "discount": ["Cryogenic Stasis Pods", "Frigid Air Appliance"],
            "premium": ["Solar Seafood Platter"],
        },
        "Celestia": {
            "must": ["Universal Language Translators", "Energy Shields", "Warp Drives"],
            "discount": ["Universal Language Translators"],
            "premium": ["Stealth Cloaking Devices", "Photon Destabilizer"],
        },
    }

    for planet in planets:
        for item in list(planet.item_modifiers.keys()):
            planet.item_modifiers[item] = max(
                45, min(220, int(planet.item_modifiers[item]))
            )

        role = role_biases.get(planet.name)
        if not role:
            continue

        for item in role.get("must", []):
            if item in base_prices and item not in planet.item_modifiers:
                planet.item_modifiers[item] = rng.randint(85, 125)

        for item in role.get("discount", []):
            if item in planet.item_modifiers:
                tuned = int(planet.item_modifiers[item] * rng.uniform(0.65, 0.9))
                planet.item_modifiers[item] = max(45, min(220, tuned))

        for item in role.get("premium", []):
            if item in planet.item_modifiers:
                tuned = int(planet.item_modifiers[item] * rng.uniform(1.15, 1.45))
                planet.item_modifiers[item] = max(55, min(260, tuned))

    min_overlap = 3
    planet_pool = sorted(planets, key=lambda p: (len(p.item_modifiers), p.population))
    for item in all_items:
        holders = [p for p in planets if item in p.item_modifiers]
        needed = max(0, min_overlap - len(holders))
        if needed <= 0:
            continue
        candidates = [p for p in planet_pool if item not in p.item_modifiers]
        for p in candidates[:needed]:
            p.item_modifiers[item] = rng.randint(90, 135)

    anchor_targets = {
        "Fuel Cells": 8,
        "Cargo Pod": 7,
        "Nanobot Repair Kits": 7,
        "Energy Shields": 7,
        "Fighter Squadron": 7,
        "Warp Drives": 6,
    }
    popularity_sorted = sorted(planets, key=lambda p: p.population, reverse=True)
    for item, target_count in anchor_targets.items():
        if item not in base_prices:
            continue
        holders = [p for p in planets if item in p.item_modifiers]
        need = max(0, target_count - len(holders))
        if need <= 0:
            continue
        for p in popularity_sorted:
            if item in p.item_modifiers:
                continue
            p.item_modifiers[item] = rng.randint(85, 125)
            need -= 1
            if need <= 0:
                break

    min_items_per_planet = 9
    for planet in planets:
        if len(planet.item_modifiers) >= min_items_per_planet:
            continue

        rarity_sorted = sorted(
            all_items,
            key=lambda itm: sum(1 for p in planets if itm in p.item_modifiers),
        )
        for item in rarity_sorted:
            if item in planet.item_modifiers:
                continue
            planet.item_modifiers[item] = rng.randint(92, 145)
            if len(planet.item_modifiers) >= min_items_per_planet:
                break

    # Ensure every planet has explicit specialization lanes:
    # - at least one export item priced clearly below market
    # - at least one import item priced clearly above market
    for planet in planets:
        if not planet.item_modifiers:
            continue

        seeded_rng = random.Random(f"spec-{planet.name}")
        available_items = [i for i in all_items if i in base_prices]
        if not available_items:
            continue

        # Make sure this planet has enough items to specialize.
        if len(planet.item_modifiers) < 2:
            needed_items = [
                i for i in available_items if i not in planet.item_modifiers
            ]
            for itm in needed_items[: 2 - len(planet.item_modifiers)]:
                planet.item_modifiers[itm] = seeded_rng.randint(95, 120)

        candidate_items = list(planet.item_modifiers.keys())
        if len(candidate_items) < 2:
            continue

        # Pick export from lower-priced half, import from upper-priced half.
        sorted_by_mod = sorted(
            candidate_items, key=lambda itm: planet.item_modifiers[itm]
        )
        split_idx = max(1, len(sorted_by_mod) // 2)
        export_pool = sorted_by_mod[:split_idx]
        import_pool = sorted_by_mod[split_idx:] or sorted_by_mod

        export_item = seeded_rng.choice(export_pool)
        import_item = seeded_rng.choice(import_pool)
        if import_item == export_item:
            alt_imports = [itm for itm in import_pool if itm != export_item]
            if alt_imports:
                import_item = seeded_rng.choice(alt_imports)
            else:
                alt_any = [itm for itm in candidate_items if itm != export_item]
                if alt_any:
                    import_item = seeded_rng.choice(alt_any)

        # Enforce strong specialization bands.
        planet.item_modifiers[export_item] = min(
            planet.item_modifiers[export_item], seeded_rng.randint(58, 82)
        )
        planet.item_modifiers[import_item] = max(
            planet.item_modifiers[import_item], seeded_rng.randint(128, 170)
        )

        planet.specializations = {
            "exports": [export_item],
            "imports": [import_item],
        }

    # Ensure there is always spread for profitable routes per item.
    for item in all_items:
        holders = [p for p in planets if item in p.item_modifiers]
        if not holders:
            continue

        cheap = min(holders, key=lambda p: p.item_modifiers[item])
        expensive = max(holders, key=lambda p: p.item_modifiers[item])

        if cheap.item_modifiers[item] > 90:
            cheap.item_modifiers[item] = rng.randint(68, 88)
        if expensive.item_modifiers[item] < 120:
            expensive.item_modifiers[item] = rng.randint(122, 155)

    # Hand-authored trade lanes to make travel decisions interesting.
    trade_lanes = [
        ("Fuel Cells", "Asterudor", "Titan Station"),
        ("Cargo Pod", "Mastodrun", "Titanica"),
        ("Nanobot Repair Kits", "Urth", "Aurora"),
        ("Energy Shields", "Zephyrion", "Pyrothos"),
        ("Fighter Squadron", "Pyrothos", "Aphelion"),
        ("Quantum Data Chips", "Asterudor", "Euphorin"),
        ("Purified Water Extractor", "Atlantiz", "Pyrothos"),
        ("Solar Seafood Platter", "Atlantiz", "Mastodrun"),
        ("Cryogenic Stasis Pods", "Aurora", "Elysium"),
        ("Nuclear Heater Core", "Pyrothos", "Aurora"),
    ]
    by_name = {p.name: p for p in planets}
    for item, source_name, sink_name in trade_lanes:
        source = by_name.get(source_name)
        sink = by_name.get(sink_name)
        if not source or not sink or item not in base_prices:
            continue

        if item not in source.item_modifiers:
            source.item_modifiers[item] = rng.randint(70, 85)
        else:
            source.item_modifiers[item] = min(
                source.item_modifiers[item], rng.randint(70, 85)
            )

        if item not in sink.item_modifiers:
            sink.item_modifiers[item] = rng.randint(125, 160)
        else:
            sink.item_modifiers[item] = max(
                sink.item_modifiers[item], rng.randint(125, 160)
            )


def _spread_planet_coordinates(planets):
    if len(planets) < 2:
        return

    map_min_x, map_max_x = 150, 1250
    map_min_y, map_max_y = 170, 770
    min_distance = 155.0
    min_distance_sq = min_distance * min_distance

    coords = [[float(p.x), float(p.y)] for p in planets]

    for _ in range(72):
        offsets = [[0.0, 0.0] for _ in planets]
        overlap_found = False

        for i in range(len(coords)):
            for j in range(i + 1, len(coords)):
                dx = coords[j][0] - coords[i][0]
                dy = coords[j][1] - coords[i][1]
                dist_sq = dx * dx + dy * dy
                if dist_sq >= min_distance_sq:
                    continue

                overlap_found = True
                if dist_sq < 1e-6:
                    angle = ((i * 97) + (j * 53)) % 360
                    rad = math.radians(angle)
                    nx, ny = math.cos(rad), math.sin(rad)
                    dist = 0.001
                else:
                    dist = math.sqrt(dist_sq)
                    nx, ny = dx / dist, dy / dist

                push = (min_distance - dist) * 0.52
                offsets[i][0] -= nx * push
                offsets[i][1] -= ny * push
                offsets[j][0] += nx * push
                offsets[j][1] += ny * push

        for idx in range(len(coords)):
            coords[idx][0] = min(
                map_max_x, max(map_min_x, coords[idx][0] + offsets[idx][0])
            )
            coords[idx][1] = min(
                map_max_y, max(map_min_y, coords[idx][1] + offsets[idx][1])
            )

        if not overlap_found:
            break

    for idx, planet in enumerate(planets):
        planet.x = int(round(coords[idx][0]))
        planet.y = int(round(coords[idx][1]))


def generate_planets():
    planets = []
    file_path = get_absolute_path("planets.txt")
    smuggle_item_pool, smuggle_item_meta = _load_smuggling_item_pool()

    try:
        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as file:
                content = file.read()
                # Split by double newline to handle blocks correctly
                blocks = [b.strip() for b in content.split("\n\n") if b.strip()]

                for block in blocks:
                    lines = [line.strip() for line in block.split("\n") if line.strip()]
                    if len(lines) < 9:
                        continue

                    def get_val(line):
                        if ":" in line:
                            return line.split(":", 1)[1].strip()
                        return ""

                    fields = {}
                    for line in lines:
                        if ":" not in line:
                            continue
                        k, v = line.split(":", 1)
                        fields[str(k).strip().lower()] = str(v).strip()

                    name = fields.get("name", "")

                    population_str = fields.get("population", "0").replace(",", "")
                    population = int(population_str) if population_str.isdigit() else 0

                    description = fields.get("description", "")
                    vendor = fields.get("vendor", "")
                    tradecenter = fields.get("trade center", "")

                    defenders_str = fields.get("defenders", "0").replace(",", "")
                    defenders = int(defenders_str) if defenders_str.isdigit() else 0

                    shields_str = fields.get("shields", "0").replace(",", "")
                    shields = int(shields_str) if shields_str.isdigit() else 0

                    max_defenders_val = None
                    max_defenders_str = fields.get("max defenders", "").replace(",", "")
                    if max_defenders_str.isdigit():
                        max_defenders_val = int(max_defenders_str)

                    max_shields_val = None
                    max_shields_str = fields.get("max shields", "").replace(",", "")
                    if max_shields_str.isdigit():
                        max_shields_val = int(max_shields_str)

                    base_credits_val = None
                    base_credits_str = fields.get("base credits", "").replace(",", "")
                    if base_credits_str.isdigit():
                        base_credits_val = int(base_credits_str)

                    bank = fields.get("bank", "").strip().lower() in (
                        "1",
                        "true",
                        "yes",
                        "on",
                    )
                    items_str = fields.get("items", "")

                    is_active = fields.get("active", "on").strip().lower() in (
                        "1",
                        "true",
                        "yes",
                        "on",
                    )

                    if not is_active:
                        continue

                    items = {}
                    if items_str:
                        item_pairs = items_str.split(";")
                        for pair in item_pairs:
                            if "," in pair:
                                item_parts = pair.split(",", 1)
                                if len(item_parts) == 2:
                                    item_name, price = item_parts
                                    clean_name = item_name.strip()
                                    if clean_name and clean_name in active_item_names:
                                        items[clean_name] = int(price.strip())

                    fixed_x, fixed_y = get_planet_map_coordinates(name)

                    planet = Planet(
                        name,
                        population,
                        description,
                        vendor,
                        tradecenter,
                        defenders,
                        shields,
                        bank,
                        items,
                        max_defenders=max_defenders_val,
                        max_shields=max_shields_val,
                        base_credits=base_credits_val,
                        x=fixed_x,
                        y=fixed_y,
                    )

                    # All planets with banks have basic repair facilities
                    if bank:
                        planet.repair_multiplier = 1.0

                    # Assign Repair Multipliers to 5 specific planets
                    repair_stations = {
                        "Urth": 1.0,  # Standard hub
                        "Mastodrun": 0.8,  # Competitive metropolis
                        "Zephyrion": 1.5,  # High-tech/Premium
                        "Novos": 0.6,  # Cheap/Dirty (smuggler port)
                        "Nebula Vista": 1.3,  # Remote/High-logistic cost
                    }
                    if name in repair_stations:
                        planet.repair_multiplier = repair_stations[name]

                    # Crew Services Configuration
                    if name == "Mastodrun":
                        # Metropolis - Full range
                        planet.crew_services = [
                            {"type": "weapons", "levels": [1, 2, 3, 4, 5]},
                            {"type": "engineer", "levels": [1, 2, 3, 4, 5]},
                        ]
                    elif name == "Zephyrion":
                        # Tech hub - Engineers
                        planet.crew_services = [
                            {"type": "engineer", "levels": [3, 4, 5, 6, 7, 8]}
                        ]
                    elif name == "Novos":
                        # Smugglers/War - Weapons
                        planet.crew_services = [
                            {"type": "weapons", "levels": [4, 5, 6, 7, 8]}
                        ]
                    elif name == "Urth":
                        # Traditional hub - Basic
                        planet.crew_services = [
                            {"type": "weapons", "levels": [1, 2]},
                            {"type": "engineer", "levels": [1, 2]},
                        ]

                    # NPC and Personality Data
                    npc_data = {
                        "Novos": (
                            "Vex",
                            "shady",
                            50,
                            "You here for the goods? Keep it quiet.",
                            500,
                            True,
                            [
                                "Keep your voice down...",
                                "Don't attract the Syndicate's eye.",
                                "The heat is on today...",
                            ],
                        ),
                        "Urth": (
                            "Old Teddy",
                            "tired",
                            10,
                            "Urth ain't what she used to be, kid. Welcome back.",
                            0,
                            False,
                            [
                                "Things were better in the old days.",
                                "Take a load off, spacer.",
                                "Spare some credits?",
                            ],
                        ),
                        "Mastodrun": (
                            "Elder Orion",
                            "arrogant",
                            250,
                            "You've reached the pinnacle of trade. Don't waste my time.",
                            1000,
                            False,
                            [
                                "Marvel at our wealth.",
                                "Everything has a price here.",
                                "You look... underfunded.",
                            ],
                        ),
                        "Zephyrion": (
                            "Unit 7B",
                            "robotic",
                            150,
                            "Optimization protocols engaged. Welcome, organic trader.",
                            0,
                            False,
                            [
                                "Efficiency is paramount.",
                                "Calculating market trends...",
                                "Beep. Trade confirmed.",
                            ],
                        ),
                        "Shadien": (
                            "Jax the Ghost",
                            "slick",
                            100,
                            "I see you, spacer. Looking for something... exclusive?",
                            300,
                            True,
                            [
                                "Whatever you need, I can find.",
                                "The Alliance doesn't know half of it.",
                                "Don't tell 'em where you got this.",
                            ],
                        ),
                        "Pyrothos": (
                            "Ignis",
                            "aggressive",
                            80,
                            "Too hot for you? Buy something or get out!",
                            0,
                            False,
                            [
                                "The forge never stops.",
                                "Our blades are the sharpest.",
                                "Don't stand too close to the vents.",
                            ],
                        ),
                        "Celestia": (
                            "High Officer Vale",
                            "formal",
                            500,
                            "The Galactic Alliance welcomes you. Please present your permits.",
                            2000,
                            False,
                            [
                                "Order must be maintained.",
                                "Security is our top priority.",
                                "Declare all cargo immediately.",
                            ],
                        ),
                    }

                    if name in npc_data:
                        d = npc_data[name]
                        planet.npc_name = d[0]
                        planet.npc_personality = d[1]
                        planet.docking_fee = d[2]
                        planet.welcome_msg = d[3]
                        planet.bribe_cost = d[4]
                        planet.is_smuggler_hub = d[5]
                        planet.npc_remarks = d[6]

                    # Security Levels
                    if name in ["Urth", "Celestia"]:
                        planet.security_level = 2
                    elif name in ["Mastodrun", "Zephyrion"]:
                        planet.security_level = 1

                    # Initialize Smuggling Inventory
                    # 10% chance for any planet to have a smuggling item available randomly,
                    # or 100% if it's a dedicated hub.
                    if planet.is_smuggler_hub or random.random() < 0.10:
                        if smuggle_item_pool:
                            # Pick 1-3 random smuggling items
                            num_items = (
                                random.randint(1, 3) if planet.is_smuggler_hub else 1
                            )
                            selected = random.sample(
                                smuggle_item_pool,
                                min(num_items, len(smuggle_item_pool)),
                            )
                            for s_item in selected:
                                item_meta = dict(
                                    smuggle_item_meta.get(s_item, {}) or {}
                                )
                                base_price = int(
                                    item_meta.get(
                                        "base_price", base_prices.get(s_item, 500)
                                    )
                                )
                                modifier, tier = _roll_smuggle_modifier(
                                    s_item,
                                    int(planet.security_level),
                                    bool(planet.is_smuggler_hub),
                                )
                                required_level = item_meta.get("required_bribe_level")
                                if required_level is None:
                                    required_level = _required_bribe_level_for_item(
                                        s_item,
                                        base_price,
                                        int(planet.security_level),
                                        bool(planet.is_smuggler_hub),
                                    )
                                if planet.is_smuggler_hub:
                                    qty_low = 2
                                    qty_high = max(3, 8 - tier)
                                else:
                                    qty_low = 1
                                    qty_high = max(1, 4 - tier)
                                planet.smuggling_inventory[s_item] = {
                                    "modifier": modifier,
                                    "quantity": random.randint(qty_low, qty_high),
                                    "tier": int(tier),
                                    "base_price": int(base_price),
                                    "required_bribe_level": int(required_level),
                                }

                    planets.append(planet)
    except Exception as e:
        print(f"Error loading planets.txt: {e}")

    if not planets:
        # Final fallback
        planets.append(
            Planet(
                "Urth",
                8000000000,
                "The cradle of humanity.",
                "Global Trade",
                "Central Network",
                1000,
                100,
                True,
                {"Water": 1, "Bread": 2},
                x=600,
                y=400,
            )
        )

    _spread_planet_coordinates(planets)
    _rebalance_planet_economy(planets)
    _ensure_smuggling_distribution(planets, smuggle_item_pool, smuggle_item_meta)

    return planets


def count_planets():
    return len(generate_planets())


def get_planet_map_coordinates(name):
    """Deterministic map coordinates keyed by planet name.

    This keeps travel mapping stable even when planets are added/removed.
    """
    safe_name = str(name or "").strip().lower() or "unknown"
    coord_rng = random.Random(f"coord::{safe_name}")
    name_seed = sum((idx + 1) * ord(ch) for idx, ch in enumerate(safe_name))

    map_min_x, map_max_x = 150, 1250
    map_min_y, map_max_y = 170, 770
    map_w = map_max_x - map_min_x
    map_h = map_max_y - map_min_y

    base_x = map_min_x + (name_seed % map_w)
    base_y = map_min_y + ((name_seed * 7) % map_h)

    fixed_x = max(
        map_min_x,
        min(map_max_x, int(base_x + coord_rng.randint(-35, 35))),
    )
    fixed_y = max(
        map_min_y,
        min(map_max_y, int(base_y + coord_rng.randint(-28, 28))),
    )
    return int(fixed_x), int(fixed_y)
