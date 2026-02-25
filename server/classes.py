import os
import time

# Upgrade price constants (kept in sync with client/constants.py)
UPGRADE_PRICE_CARGO = 75
UPGRADE_PRICE_SHIELD = 200
UPGRADE_PRICE_DEFENDER = 75


class Spaceship:
    ROLE_TAGS = ["Hauler", "Interceptor", "Siege", "Runner"]

    def __init__(
        self,
        model,
        cost,
        starting_cargo_pods,
        starting_shields,
        starting_defenders,
        max_cargo_pods,
        max_shields,
        max_defenders,
        special_weapon=None,
        integrity=100,
        role_tags=None,
        module_slots=None,
        installed_modules=None,
    ):
        self.model = model
        self.cost = cost
        self.starting_cargo_pods = starting_cargo_pods
        self.starting_shields = starting_shields
        self.starting_defenders = starting_defenders
        self.max_cargo_pods = max_cargo_pods
        self.max_shields = max_shields
        self.max_defenders = max_defenders
        self.current_cargo_pods = starting_cargo_pods
        self.current_shields = starting_shields
        self.current_defenders = starting_defenders
        self.special_weapon = special_weapon
        self.integrity = integrity
        self.max_integrity = (
            integrity  # Store the maximum possible integrity for this ship class
        )

        # Scale fuel stats by ship class
        # Smallest is 50, largest is 175+. We'll use max_cargo as the scale.
        self.max_fuel = max_cargo_pods * 2
        self.fuel = self.max_fuel
        self.fuel_burn_rate = 0.5 + (
            max_cargo_pods / 400
        )  # Reduced 50% — lower fuel burn for all ship types

        self.role_tags = self._normalize_role_tags(role_tags)
        if not self.role_tags:
            self.role_tags = self._infer_role_tags()

        # Crew slots: Independence and Nova Cruiser (first two) get 0.
        # Check by model name or cost (Independence and Nova Cruiser are cheapest)
        # Better: use a boolean or explicit count.
        self.crew_slots = {"weapons": 0, "engineer": 0}
        if cost >= 50000:  # Quantum Vanguard and up
            self.crew_slots = {"weapons": 1, "engineer": 1}

        if module_slots is None:
            self.module_slots = self._default_module_slots()
        else:
            self.module_slots = max(1, int(module_slots))

        self.installed_modules = self._normalize_modules(installed_modules)
        if not self.installed_modules:
            self.installed_modules = self._default_modules_for_roles()

        self.installed_modules = self.installed_modules[: self.module_slots]

        self.last_refuel_time = 0

    def _normalize_role_tags(self, tags):
        cleaned = []
        for tag in tags or []:
            normalized = str(tag).strip().title()
            if normalized in self.ROLE_TAGS and normalized not in cleaned:
                cleaned.append(normalized)
        return cleaned

    def _infer_role_tags(self):
        score = {
            "Hauler": float(self.max_cargo_pods) * 1.0
            + float(self.max_integrity) * 0.06,
            "Interceptor": float(self.max_defenders) * 0.60
            + float(self.max_shields) * 0.30
            + (130.0 / max(0.65, self.fuel_burn_rate)),
            "Siege": float(self.max_defenders) * 0.55
            + float(self.max_shields) * 0.35
            + float(self.max_integrity) * 0.26,
            "Runner": (180.0 / max(0.65, self.fuel_burn_rate))
            + float(self.max_shields) * 0.20
            + float(self.max_cargo_pods) * 0.15,
        }
        ordered = sorted(score.items(), key=lambda it: it[1], reverse=True)
        primary = ordered[0][0]
        secondary = ordered[1][0]
        tags = [primary]
        if ordered[1][1] >= ordered[0][1] * 0.88:
            tags.append(secondary)
        return tags

    def _default_module_slots(self):
        if self.cost < 12000:
            return 1
        if self.cost < 200000:
            return 2
        if self.cost < 1200000:
            return 3
        return 4

    def _normalize_modules(self, modules):
        allowed = {"scanner", "jammer", "cargo_optimizer"}
        cleaned = []
        for module in modules or []:
            name = str(module).strip().lower()
            if name in allowed and name not in cleaned:
                cleaned.append(name)
        return cleaned

    def _default_modules_for_roles(self):
        picks = []
        for role in self.role_tags:
            if role == "Hauler" and "cargo_optimizer" not in picks:
                picks.append("cargo_optimizer")
            elif role == "Interceptor" and "scanner" not in picks:
                picks.append("scanner")
            elif role == "Siege" and "jammer" not in picks:
                picks.append("jammer")
            elif role == "Runner":
                if "jammer" not in picks:
                    picks.append("jammer")
                elif "scanner" not in picks:
                    picks.append("scanner")
        if not picks:
            picks = ["scanner"]
        return picks[: self.module_slots]

    def has_module(self, module_name):
        return str(module_name).strip().lower() in self.installed_modules

    def get_role_bonus(self, role_name):
        role = str(role_name or "").strip().title()
        if role not in self.role_tags:
            return 0.0
        if role == "Hauler":
            return 0.10
        if role == "Interceptor":
            return 0.08
        if role == "Siege":
            return 0.10
        if role == "Runner":
            return 0.08
        return 0.0

    def get_module_bonus(self, module_name):
        module = str(module_name or "").strip().lower()
        if not self.has_module(module):
            return 0.0
        if module == "cargo_optimizer":
            return 0.12
        if module == "jammer":
            return 0.12
        if module == "scanner":
            return 0.10
        return 0.0

    def get_effective_max_cargo(self):
        role_bonus = self.get_role_bonus("Hauler")
        module_bonus = self.get_module_bonus("cargo_optimizer")
        total_mult = 1.0 + role_bonus + module_bonus
        return max(
            self.current_cargo_pods, int(round(self.current_cargo_pods * total_mult))
        )

    def get_effective_fuel_burn_rate(self):
        burn = float(self.fuel_burn_rate)
        burn *= 1.0 - self.get_role_bonus("Runner")
        burn *= 1.0 - self.get_module_bonus("cargo_optimizer") * 0.35
        return max(0.25, burn)

    def get_effective_combat_power_multiplier(self):
        mult = 1.0
        mult += self.get_role_bonus("Interceptor")
        mult += self.get_role_bonus("Siege")
        mult += self.get_module_bonus("scanner") * 0.20
        return max(0.80, mult)

    def get_effective_scan_evasion_multiplier(self):
        mult = 1.0
        mult *= 1.0 - self.get_role_bonus("Runner")
        mult *= 1.0 - self.get_module_bonus("jammer")
        return max(0.60, mult)

    def get_role_strength_score(self, role_name):
        role = str(role_name or "").strip().title()
        if role == "Hauler":
            base = float(self.max_cargo_pods) * 1.0 + float(self.max_integrity) * 0.06
            mult = (
                1.0
                + self.get_role_bonus("Hauler")
                + self.get_module_bonus("cargo_optimizer")
            )
            return base * mult
        if role == "Interceptor":
            base = (
                float(self.max_defenders) * 0.60
                + float(self.max_shields) * 0.30
                + (130.0 / max(0.65, self.get_effective_fuel_burn_rate()))
            )
            mult = (
                1.0
                + self.get_role_bonus("Interceptor")
                + self.get_module_bonus("scanner") * 0.35
            )
            return base * mult
        if role == "Siege":
            base = (
                float(self.max_defenders) * 0.55
                + float(self.max_shields) * 0.35
                + float(self.max_integrity) * 0.26
            )
            mult = (
                1.0
                + self.get_role_bonus("Siege")
                + self.get_module_bonus("jammer") * 0.30
            )
            return base * mult
        if role == "Runner":
            base = (
                (180.0 / max(0.65, self.get_effective_fuel_burn_rate()))
                + float(self.max_shields) * 0.20
                + float(self.max_cargo_pods) * 0.15
            )
            mult = (
                1.0
                + self.get_role_bonus("Runner")
                + self.get_module_bonus("jammer") * 0.40
            )
            return base * mult
        return 0.0

    def calculate_value(self):
        """Calculate total purchase cost of ship and installed upgrades."""
        cargo_upgrades = self.current_cargo_pods - self.starting_cargo_pods
        shield_upgrades = (self.current_shields - self.starting_shields) // 10
        defender_upgrades = self.current_defenders - self.starting_defenders

        upgrade_cost = (
            cargo_upgrades * UPGRADE_PRICE_CARGO
            + shield_upgrades * UPGRADE_PRICE_SHIELD
            + defender_upgrades * UPGRADE_PRICE_DEFENDER
        )

        return self.cost + upgrade_cost

    def get_trade_in_info(self):
        """Returns a breakdown of value for UI factoring in integrity penalty."""
        # Ensure upgrades are never negative by using max(0, ...)
        # Damage to starting systems is handled by the integrity penalty
        cargo_upgrades = max(0, self.current_cargo_pods - self.starting_cargo_pods)
        shield_upgrades = max(0, (self.current_shields - self.starting_shields) // 10)
        defender_upgrades = max(0, self.current_defenders - self.starting_defenders)

        upgrades_cost = (
            cargo_upgrades * UPGRADE_PRICE_CARGO
            + shield_upgrades * UPGRADE_PRICE_SHIELD
            + defender_upgrades * UPGRADE_PRICE_DEFENDER
        )
        total_value = self.cost + upgrades_cost

        # Base trade-in factor is 0.5 (50%)
        # It scales linearly with integrity: Full integrity = 0.5, Half = 0.25
        integrity_factor = (
            self.integrity / self.max_integrity if self.max_integrity > 0 else 1.0
        )
        trade_in_factor = 0.5 * integrity_factor

        trade_in = int(total_value * trade_in_factor)

        return {
            "model": self.model,
            "base_cost": self.cost,
            "upgrades_cost": upgrades_cost,
            "total_value": total_value,
            "trade_in": trade_in,
            "integrity_penalty_percent": 1.0 - integrity_factor,
        }

    def upgrade_cargo_pods(self, additional_cargo_pods):
        # Increase properties up to their maximum
        new_val = self.current_cargo_pods + additional_cargo_pods
        if new_val <= self.max_cargo_pods:
            self.current_cargo_pods = new_val
            return True, f"Installed {additional_cargo_pods} cargo pods."
        return False, f"Maximum cargo pod capacity ({self.max_cargo_pods}) reached."

    def upgrade_shields(self, additional_shields):
        new_val = self.current_shields + additional_shields
        if new_val <= self.max_shields:
            self.current_shields = new_val
            return True, f"Shields enhanced by {additional_shields} units."
        return False, f"Maximum shield strength ({self.max_shields}) reached."

    def upgrade_defenders(self, additional_defenders):
        new_val = self.current_defenders + additional_defenders
        if new_val <= self.max_defenders:
            self.current_defenders = new_val
            return True, f"Added {additional_defenders} fighter(s)."
        return False, f"Maximum fighter capacity ({self.max_defenders}) reached."

    def install_special_weapon(self, special_weapon):
        # Set the special weapon for the spaceship
        self.special_weapon = special_weapon

    def take_damage(self, damage):
        # Round damage to nearest whole number
        damage = round(damage)

        # Damage applies to shields first, then integrity
        if self.current_shields > 0:
            if damage <= self.current_shields:
                self.current_shields -= damage
                damage = 0
            else:
                damage -= self.current_shields
                self.current_shields = 0
            # Ensure shields stay as integers
            self.current_shields = int(self.current_shields)

        if damage > 0:
            self.integrity -= damage
            if self.integrity < 0:
                self.integrity = 0
            # Ensure integrity stay as integers
            self.integrity = int(self.integrity)

    def repair_ship(self):
        # Restore the ship's health to its maximum value
        self.integrity = self.max_integrity

    def clone(self):
        """Returns a fresh instance of this ship model with template stats."""
        return Spaceship(
            self.model,
            self.cost,
            self.starting_cargo_pods,
            self.starting_shields,
            self.starting_defenders,
            self.max_cargo_pods,
            self.max_shields,
            self.max_defenders,
            special_weapon=self.special_weapon,
            integrity=self.max_integrity,
            role_tags=list(self.role_tags),
            module_slots=int(self.module_slots),
            installed_modules=list(self.installed_modules),
        )

    def get_ship_info(self):
        return {
            "model": self.model,
            "cargo_pods": f"{self.current_cargo_pods}/{self.max_cargo_pods}",
            "shields": f"{self.current_shields}/{self.max_shields}",
            "defenders": f"{self.current_defenders}/{self.max_defenders}",
            "special_weapon": self.special_weapon,
            "integrity": self.integrity,
            "max_integrity": self.max_integrity,
            "fuel": self.fuel,
            "max_fuel": self.max_fuel,
            "effective_cargo": self.get_effective_max_cargo(),
            "effective_fuel_burn_rate": round(self.get_effective_fuel_burn_rate(), 3),
            "role_tags": list(self.role_tags),
            "module_slots": int(self.module_slots),
            "installed_modules": list(self.installed_modules),
        }


class Message:
    def __init__(
        self,
        sender,
        recipient,
        subject,
        body,
        timestamp=None,
        is_read=False,
        is_saved=False,
        msg_id=None,
    ):
        import uuid

        self.sender = sender
        self.recipient = recipient
        self.subject = subject
        self.body = body[:500]  # Enforce 500 character limit
        self.timestamp = timestamp or time.time()
        self.is_read = is_read
        self.is_saved = is_saved
        self.id = msg_id or str(uuid.uuid4())[:8]

    def to_dict(self):
        return {
            "sender": self.sender,
            "recipient": self.recipient,
            "subject": self.subject,
            "body": self.body,
            "timestamp": self.timestamp,
            "is_read": self.is_read,
            "is_saved": self.is_saved,
            "msg_id": self.id,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(**data)


class Player:
    def __init__(self, name, spaceship, credits=200):
        self.name = name
        self.spaceship = spaceship
        self.credits = round(credits)
        self.bank_balance = 0
        self.inventory = {}  # item_name: quantity
        self.owned_planets = {}  # planet_name: last_payout_time
        self.barred_planets = {}  # planet_name: expiry_time
        self.attacked_planets = {}  # planet_name: last_attack_timestamp
        self.crew = {}  # specialty: CrewMember object
        import time

        self.last_crew_pay_time = time.time()
        self.messages = []  # List of Message objects
        self.combat_win_streak = 0
        self.combat_lifetime_wins = 0
        self.last_special_weapon_time = 0.0

    def add_message(self, message):
        """Adds a message to the mailbox, respecting the 20-message limit for non-saved mail."""
        # Count non-saved messages
        inbox_count = sum(1 for m in self.messages if not m.is_saved)
        if inbox_count >= 20:
            # Remove oldest non-saved message
            for i, m in enumerate(self.messages):
                if not m.is_saved:
                    self.messages.pop(i)
                    break
        self.messages.append(message)

    def delete_message(self, msg_id):
        self.messages = [m for m in self.messages if m.id != msg_id]

    def save_message(self, index):
        if 0 <= index < len(self.messages):
            msg = self.messages[index]
            saved_count = sum(1 for m in self.messages if m.is_saved)
            if saved_count < 20:
                msg.is_saved = True
                return True, "Message saved."
            return False, "Archive limit reached (20 slots)."
        return False, "Message not found."

    def buy_item(self, item_name, price, quantity=1):
        cost = price * quantity
        if self.credits >= cost:
            # Check cargo space
            ship = self.spaceship
            current_cargo = sum(self.inventory.values())
            cargo_limit = int(
                ship.get_effective_max_cargo()
                if hasattr(ship, "get_effective_max_cargo")
                else ship.current_cargo_pods
            )
            if current_cargo + quantity <= cargo_limit:
                self.credits -= cost
                self.inventory[item_name] = self.inventory.get(item_name, 0) + quantity
                return True, f"Purchased {quantity}x {item_name}."
            return False, "Not enough cargo space!"
        return False, "Insufficient credits!"

    def sell_item(self, item_name, price, quantity=1):
        if self.inventory.get(item_name, 0) >= quantity:
            self.credits += price * quantity
            self.inventory[item_name] -= quantity
            if self.inventory[item_name] == 0:
                del self.inventory[item_name]
            return True, f"Sold {quantity}x {item_name}."
        return False, f"You don't have enough {item_name}!"

    def buy_upgrade(self, upgrade_type, value, cost):
        if self.credits < cost:
            return False, "Not enough credits!"
        if upgrade_type == "cargo_pods":
            self.spaceship.upgrade_cargo_pods(value)
        elif upgrade_type == "shields":
            self.spaceship.upgrade_shields(value)
        elif upgrade_type == "special_weapon":
            self.spaceship.install_special_weapon(value)
        self.credits -= cost
        return True, "Upgrade successful!"

    def take_damage(self, damage):
        # Apply engineer bonus if present to reduce all incoming damage
        if "engineer" in self.crew:
            damage *= 1.0 - self.crew["engineer"].get_bonus()
        self.spaceship.take_damage(damage)

    def hire_crew(self, crew_member):
        specialty = crew_member.specialty
        if self.spaceship.crew_slots.get(specialty, 0) > 0:
            self.crew[specialty] = crew_member
            self.credits -= crew_member.hire_cost
            return True, f"Hired {crew_member.name} as {specialty.upper()} EXPERT."
        return False, f"This ship has no slots for a {specialty} expert."

    def fire_crew(self, specialty):
        if specialty in self.crew:
            member = self.crew.pop(specialty)
            return True, f"{member.name} has been dismissed."
        return False, "No such crew member found."

    def get_info(self):
        crew_info = {
            s: {"name": m.name, "level": m.level} for s, m in self.crew.items()
        }
        return {
            "name": self.name,
            "credits": self.credits,
            "bank": self.bank_balance,
            "spaceship": self.spaceship.get_ship_info(),
            "inventory": self.inventory,
            "owned_planets": list(self.owned_planets.keys()),
            "barred_planets": list(self.barred_planets.keys()),
            "crew": crew_info,
        }


class CrewMember:
    def __init__(self, name, specialty, level):
        self.name = name
        self.specialty = specialty  # "weapons" or "engineer"
        self.level = level  # 1 to 8

        # Hiring cost: level * 5000 (expensive)
        # Pay: level * 200 (24 hrs)
        self.hire_cost = self.level * 5000
        self.daily_pay = self.level * 200

        self.unpaid_cycles = 0  # If 7, they leave
        self.morale = 100
        self.fatigue = 0
        self.xp = 0
        self.perks = []
        self._ensure_milestone_perks()

    def _clamp_morale_fatigue(self):
        self.morale = int(max(0, min(100, int(self.morale))))
        self.fatigue = int(max(0, min(100, int(self.fatigue))))

    def _perk_catalog(self):
        return {
            "weapons": {
                3: ["precision_focus", "rapid_lock"],
                5: ["breach_tactics", "suppressive_fire"],
                7: ["ace_gunnery", "siege_pattern"],
            },
            "engineer": {
                3: ["fuel_saver", "stability_tuning"],
                5: ["hull_mesh", "shield_harmonics"],
                7: ["quantum_efficiency", "combat_reroute"],
            },
        }

    def _choose_perk_for_level(self, level):
        options = self._perk_catalog().get(self.specialty, {}).get(level, [])
        if not options:
            return None

        seed = sum(ord(ch) for ch in f"{self.name}:{self.specialty}:{level}")
        idx = seed % len(options)
        return options[idx]

    def _ensure_milestone_perks(self):
        milestones = self._perk_catalog().get(self.specialty, {})
        for lvl in sorted(milestones.keys()):
            if self.level < lvl:
                continue
            if any(p.startswith(f"L{lvl}:") for p in self.perks):
                continue
            choice = self._choose_perk_for_level(lvl)
            if choice:
                self.perks.append(f"L{lvl}:{choice}")

    def _perk_bonus(self):
        bonus = 0.0
        for perk in self.perks:
            if perk.endswith("precision_focus"):
                bonus += 0.010
            elif perk.endswith("rapid_lock"):
                bonus += 0.008
            elif perk.endswith("breach_tactics"):
                bonus += 0.012
            elif perk.endswith("suppressive_fire"):
                bonus += 0.010
            elif perk.endswith("ace_gunnery"):
                bonus += 0.015
            elif perk.endswith("siege_pattern"):
                bonus += 0.013
            elif perk.endswith("fuel_saver"):
                bonus += 0.010
            elif perk.endswith("stability_tuning"):
                bonus += 0.009
            elif perk.endswith("hull_mesh"):
                bonus += 0.012
            elif perk.endswith("shield_harmonics"):
                bonus += 0.011
            elif perk.endswith("quantum_efficiency"):
                bonus += 0.015
            elif perk.endswith("combat_reroute"):
                bonus += 0.013
        return bonus

    def gain_xp(self, amount):
        gain = max(0, int(amount))
        if gain <= 0:
            return 0

        self.xp = int(self.xp) + gain
        levels_gained = 0
        while self.level < 8:
            threshold = int(70 + (self.level * 35))
            if self.xp < threshold:
                break
            self.xp -= threshold
            self.level += 1
            levels_gained += 1
            self.hire_cost = self.level * 5000
            self.daily_pay = self.level * 200
            self.morale = min(100, int(self.morale) + 6)
            self._ensure_milestone_perks()

        return levels_gained

    def apply_activity(self, activity):
        activity_key = str(activity or "").lower()
        if activity_key == "travel":
            self.fatigue += 4
            self.morale = max(0, self.morale - 1)
            self.gain_xp(6)
        elif activity_key == "combat":
            self.fatigue += 8
            self.morale = max(0, self.morale - 2)
            self.gain_xp(10)
        elif activity_key == "victory":
            self.morale += 6
            self.gain_xp(14)
        elif activity_key == "rest":
            self.fatigue -= 8
            self.morale += 2
        self._clamp_morale_fatigue()

    def get_effective_rating(self):
        self._clamp_morale_fatigue()
        morale_mult = 0.75 + (self.morale / 400.0)
        fatigue_mult = 1.0 - ((self.fatigue / 100.0) * 0.45)
        return max(0.55, morale_mult * fatigue_mult)

    def get_perk_summary(self):
        if not self.perks:
            return "NONE"
        labels = [p.split(":", 1)[1].replace("_", " ").upper() for p in self.perks]
        return ", ".join(labels)

    def get_bonus(self):
        if self.specialty == "weapons":
            # 3% to 15% (linear scale over 7 steps)
            base = 0.03 + (self.level - 1) * (0.12 / 7)
            return max(0.0, (base + self._perk_bonus()) * self.get_effective_rating())
        elif self.specialty == "engineer":
            # 5% to 15% (linear scale over 7 steps)
            base = 0.05 + (self.level - 1) * (0.10 / 7)
            return max(0.0, (base + self._perk_bonus()) * self.get_effective_rating())
        return 0.0

    def get_remark(self, context="idle"):
        import random

        remarks = {
            "weapons": {
                "combat_win": [
                    "Target neutralized. Efficient work, Captain.",
                    "Another hunk of scrap for the void.",
                    "Precision hit! Level {} training pays off.",
                ],
                "combat_loss": [
                    "Shields are failing! We need more power!",
                    "We're taking heavy fire! Redirecting systems...",
                    "That's enough! Get us out of here!",
                ],
                "combat_start": [
                    "Locking on target.",
                    "Weapons hot. Just say the word.",
                    "Let's see what this bird can really do.",
                ],
                "idle": [
                    "Boresighting the blasters again.",
                    "Always ready for a scrap.",
                    "Scanning for potential threats.",
                ],
            },
            "engineer": {
                "travel": [
                    "Optimizing fuel flow. Warp looks stable.",
                    "We're siphoning every drop of efficiency today.",
                    "The engines are singing, Captain.",
                ],
                "combat_start": [
                    "Diverting auxiliary power to the plating.",
                    "Hope the hull holds, I just patched it!",
                    "Engineer's log: Ship is stressed, but sturdy.",
                ],
                "idle": [
                    "Just re-aligning the flux manifold.",
                    "Pass me that hydro-spanner.",
                    "She's a beauty, isn't she? Stable as a rock.",
                ],
            },
        }
        category = remarks.get(self.specialty, {}).get(context, ["..."])
        return random.choice(category).format(self.level)

    def to_dict(self):
        return {
            "name": self.name,
            "specialty": self.specialty,
            "level": self.level,
            "unpaid_cycles": self.unpaid_cycles,
            "morale": int(self.morale),
            "fatigue": int(self.fatigue),
            "xp": int(self.xp),
            "perks": list(self.perks),
        }

    @staticmethod
    def from_dict(data):
        c = CrewMember(data["name"], data["specialty"], data["level"])
        c.unpaid_cycles = data.get("unpaid_cycles", 0)
        c.morale = int(data.get("morale", 100))
        c.fatigue = int(data.get("fatigue", 0))
        c.xp = int(data.get("xp", 0))
        c.perks = list(data.get("perks", []))
        c._ensure_milestone_perks()
        c._clamp_morale_fatigue()
        return c


class NPCShip:
    def __init__(self, name, spaceship, personality, credits=500):
        self.name = name
        self.spaceship = spaceship
        self.personality = (
            personality  # "hostile", "friendly", "bribable", "dismissive"
        )
        self.credits = credits
        self.inventory = {}
        self.orbiting_planet = None

    def get_info(self):
        return {
            "name": self.name,
            "credits": self.credits,
            "spaceship": self.spaceship.get_ship_info(),
            "personality": self.personality,
            "inventory": self.inventory,
        }

    def take_damage(self, damage):
        self.spaceship.take_damage(damage)

    def get_remark(self):
        remarks = {
            "hostile": [
                "Prepare to be boarded!",
                "Hand over your cargo, spacer.",
                "You're in the wrong sector.",
            ],
            "friendly": [
                "Safe travels, Commander.",
                "Good to see a friendly face.",
                "Need a hand with anything?",
            ],
            "bribable": [
                "I might have some info... for a price.",
                "Everything is negotiable.",
                "Looking for a short-cut?",
            ],
            "dismissive": [
                "Clear the lane, I'm busy.",
                "Not another one...",
                "Scanning... move along.",
            ],
        }
        import random

        return random.choice(remarks.get(self.personality, ["..."]))


# Read spaceship data from the text file
def load_spaceships():
    spaceships = []
    current_dir = os.path.dirname(os.path.abspath(__file__))
    file_path = os.path.join(current_dir, "assets", "texts", "spaceships.txt")

    try:
        with open(file_path, "r", encoding="utf-8") as file:
            content = file.read()
            blocks = content.strip().split("\n\n")
            for block in blocks:
                lines = [
                    line.strip() for line in block.strip().split("\n") if line.strip()
                ]
                if len(lines) < 9:
                    continue

                # Helper to extract value after ':'
                def get_val(line):
                    if ":" in line:
                        return line.split(":", 1)[1].strip()
                    return ""

                try:
                    model = get_val(lines[0])
                    cost = int(get_val(lines[1]))
                    s_cargo = int(get_val(lines[2]))
                    s_shields = int(get_val(lines[3]))
                    s_defenders = int(get_val(lines[4]))
                    m_cargo = int(get_val(lines[5]))
                    m_shields = int(get_val(lines[6]))
                    m_defenders = int(get_val(lines[7]))

                    special_weapon = get_val(lines[8])
                    if special_weapon.lower() == "none":
                        special_weapon = None

                    integrity = 100
                    if len(lines) > 9:
                        try:
                            integrity = int(get_val(lines[9]))
                        except (ValueError, IndexError):
                            pass

                    role_tags = []
                    module_slots = None
                    installed_modules = []
                    for raw_line in lines[10:]:
                        key = raw_line.split(":", 1)[0].strip().lower()
                        val = get_val(raw_line)
                        if key in {"role tags", "roles"}:
                            role_tags = [
                                t.strip().title() for t in val.split(",") if t.strip()
                            ]
                        elif key in {"module slots", "slots"}:
                            try:
                                module_slots = int(val)
                            except ValueError:
                                module_slots = None
                        elif key in {"modules", "installed modules"}:
                            installed_modules = [
                                m.strip().lower().replace(" ", "_")
                                for m in val.split(",")
                                if m.strip()
                            ]

                    ship = Spaceship(
                        model,
                        cost,
                        s_cargo,
                        s_shields,
                        s_defenders,
                        m_cargo,
                        m_shields,
                        m_defenders,
                        special_weapon=special_weapon,
                        integrity=integrity,
                        role_tags=role_tags,
                        module_slots=module_slots,
                        installed_modules=installed_modules,
                    )
                    spaceships.append(ship)
                except (ValueError, IndexError) as e:
                    continue
    except Exception as e:
        print(f"Error loading spaceships.txt: {e}")

    if not spaceships:
        spaceships.append(Spaceship("Scout Class", 0, 10, 50, 1, 20, 100, 5))

    return spaceships
