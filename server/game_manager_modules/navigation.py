import math
import time
import json
import os
import random


class NavigationMixin:
    def _get_fuel_usage_multiplier(self):
        try:
            mult = float(self.config.get("fuel_usage_multiplier", 1.15))
        except Exception:
            mult = 1.15
        # Global balance adjustment: -10% fuel usage across the board.
        return max(0.0, mult * 0.90)

    def _scale_and_round_fuel_usage(self, amount, minimum=0.0):
        scaled = max(0.0, float(amount)) * self._get_fuel_usage_multiplier()
        rounded = float(int(round(scaled)))
        if scaled > 0.0:
            rounded = max(1.0, rounded)
        if minimum > 0.0:
            rounded = max(float(minimum), rounded)
        return rounded

    def _calculate_travel_fuel_cost(self, dist):
        burn_rate = (
            self.player.spaceship.get_effective_fuel_burn_rate()
            if hasattr(self.player.spaceship, "get_effective_fuel_burn_rate")
            else self.player.spaceship.fuel_burn_rate
        )
        fuel_cost = (float(dist) / 10.0) * float(burn_rate)

        if "engineer" in self.player.crew:
            engineer_bonus = max(0.0, min(0.95, self.player.crew["engineer"].get_bonus()))
            fuel_cost *= 1.0 - engineer_bonus

        return self._scale_and_round_fuel_usage(fuel_cost, minimum=1.0)

    def _roll_travel_event(self, new_planet, dist):
        event = self.roll_travel_event_payload(new_planet, dist)
        if not event:
            return ""
        return str(self.resolve_travel_event_payload(event, "AUTO"))

    def roll_travel_event_payload(self, new_planet, dist):
        if not self.config.get("enable_travel_events"):
            return None
        chance = float(self.config.get("travel_event_chance"))
        chance = max(0.0, min(1.0, chance))
        if random.random() > chance:
            return None

        event_type = random.choice(["CACHE", "PIRATES", "DRIFT", "LEAK"])
        ship = self.player.spaceship
        planet_name = new_planet.name if new_planet else "UNKNOWN"

        if event_type == "CACHE":
            reward = random.randint(120, 900)
            return {
                "type": "CACHE",
                "title": "DERELICT CACHE DETECTED",
                "detail": (
                    f"Scanners mark a derelict cache while en route to {planet_name}. "
                    "Secure it for credits or keep formation and continue."
                ),
                "choices": ["SECURE", "SKIP"],
                "cache_reward": int(reward),
                "arrival_line": "CACHE CONTACT RECORDED. COMMAND DECISION PENDING.",
            }

        if event_type == "PIRATES":
            loss = min(self.player.credits, random.randint(60, 550))
            return {
                "type": "PIRATES",
                "title": "RAIDER INTERCEPTION",
                "detail": (
                    f"A pirate patrol blocks your lane near {planet_name}. "
                    "You can pay their toll or fight through the blockade."
                ),
                "choices": ["PAY", "FIGHT"],
                "pay_loss": int(loss),
                "arrival_line": "RAIDER CONTACT LOCKED. COMMAND DECISION PENDING.",
            }

        if event_type == "DRIFT":
            item = random.choice(["Titanium", "Fuel Cells", "Nanobot Repair Kits"])
            return {
                "type": "DRIFT",
                "title": "SALVAGE DRIFT",
                "detail": (
                    f"Free-floating cargo fragments drift near {planet_name}. "
                    "Attempt salvage pickup or ignore to preserve route timing."
                ),
                "choices": ["SALVAGE", "IGNORE"],
                "drift_item": str(item),
                "arrival_line": "DRIFT CONTACT MARKED. COMMAND DECISION PENDING.",
            }

        leak = min(max(1.0, dist / 600.0), max(1.0, ship.fuel * 0.25))
        return {
            "type": "LEAK",
            "title": "MICRO-LEAK DETECTED",
            "detail": (
                f"Fuel manifold instability detected on approach to {planet_name}. "
                "Patch now or keep moving and accept full loss."
            ),
            "choices": ["PATCH", "PUSH"],
            "leak_loss": float(leak),
            "arrival_line": "LEAK ALERT CONFIRMED. COMMAND DECISION PENDING.",
        }

    def resolve_travel_event_payload(self, event_payload, choice="AUTO"):
        payload = dict(event_payload or {})
        event_type = str(payload.get("type", "")).upper()
        selected = str(choice or "AUTO").upper()

        if event_type == "CACHE":
            if selected == "AUTO":
                selected = "SECURE"

            reward = max(0, int(payload.get("cache_reward", 0)))
            if selected == "SECURE":
                self.player.credits += reward
                flavor = random.choice(
                    [
                        "Cargo clamps lock with a metallic thunk as the cache reels in.",
                        "Your scanner crew cheers while encrypted chits decode on-screen.",
                        "Beacon lights fade behind you as the prize is stowed safely.",
                    ]
                )
                return f"DERELICT CACHE SECURED: +{reward:,} CR. {flavor}"
            flavor = random.choice(
                [
                    "You hold formation and keep engines in the green.",
                    "The cache drifts astern as you prioritize a clean arrival.",
                    "No detour taken; the lane stays stable and quiet.",
                ]
            )
            return f"CACHE BYPASSED. ROUTE INTEGRITY MAINTAINED. {flavor}"

        if event_type == "DRIFT":
            if selected == "AUTO":
                selected = "SALVAGE"

            item = str(payload.get("drift_item", "Titanium"))
            if selected == "SALVAGE":
                self.player.inventory[item] = self.player.inventory.get(item, 0) + 1
                self._adjust_frontier_standing(1)
                flavor = random.choice(
                    [
                        "Mag-claws bite into the debris stream and pull it aboard.",
                        "A quick EVA drone pass secures the drifting container.",
                        "Recovered cargo thumps into bay storage as alarms clear.",
                    ]
                )
                return f"SALVAGE DRIFT CAPTURED: +1 {item.upper()}. {flavor}"
            flavor = random.choice(
                [
                    "You let the debris field pass and keep your vector true.",
                    "No recovery attempt; transit discipline remains tight.",
                    "The drift is logged for others as you press onward.",
                ]
            )
            return f"DRIFT IGNORED. FORMATION HELD ON PRIMARY ROUTE. {flavor}"

        if event_type == "LEAK":
            if selected == "AUTO":
                selected = "PATCH"

            base_loss = max(0.0, float(payload.get("leak_loss", 1.0)))
            full_loss = self._scale_and_round_fuel_usage(base_loss, minimum=1.0)
            if selected == "PATCH":
                kit_qty = int(self.player.inventory.get("Nanobot Repair Kits", 0))
                if kit_qty > 0:
                    self.player.inventory["Nanobot Repair Kits"] = kit_qty - 1
                    if self.player.inventory["Nanobot Repair Kits"] <= 0:
                        del self.player.inventory["Nanobot Repair Kits"]
                    actual_loss = self._scale_and_round_fuel_usage(
                        max(0.2, base_loss * 0.35), minimum=1.0
                    )
                    self.player.spaceship.fuel = max(
                        0.0, self.player.spaceship.fuel - actual_loss
                    )
                    self._adjust_authority_standing(1)
                    flavor = random.choice(
                        [
                            "Nanobots weave a silver lattice over the ruptured seam.",
                            "Pressure stabilizes as repair foam flashes into a hard seal.",
                            "Flow meters settle back into nominal bands.",
                        ]
                    )
                    return (
                        f"LEAK PATCHED WITH NANOBOTS: -{actual_loss:.1f} FUEL "
                        f"(AVOIDED {max(0.0, full_loss - actual_loss):.1f}). {flavor}"
                    )

                improvised = self._scale_and_round_fuel_usage(
                    max(0.4, base_loss * 0.65), minimum=1.0
                )
                self.player.spaceship.fuel = max(
                    0.0, self.player.spaceship.fuel - improvised
                )
                flavor = random.choice(
                    [
                        "You jury-rig a seal with cargo straps and stubborn optimism.",
                        "Temporary patch holds, but pressure still bleeds at the edges.",
                        "Manual bypass keeps the manifold alive just long enough.",
                    ]
                )
                return (
                    f"FIELD PATCH APPLIED: -{improvised:.1f} FUEL "
                    f"(NANOBOT KIT UNAVAILABLE). {flavor}"
                )

            self.player.spaceship.fuel = max(0.0, self.player.spaceship.fuel - full_loss)
            flavor = random.choice(
                [
                    "You ride the leak and trust the remaining burn margin.",
                    "Warning klaxons fade as the tank level drops to compensate.",
                    "The ship shudders, but your course lock remains intact.",
                ]
            )
            return f"MICRO-LEAK PERSISTED: -{full_loss:.1f} FUEL. {flavor}"

        if event_type != "PIRATES":
            return str(payload.get("arrival_line", ""))

        pay_loss = max(0, int(payload.get("pay_loss", 0)))
        inventory_before_raiders = dict(getattr(self.player, "inventory", {}) or {})

        def _finalize_raider_result(result_line):
            current_inventory = getattr(self.player, "inventory", None)
            if not isinstance(current_inventory, dict):
                self.player.inventory = {}
                current_inventory = self.player.inventory
            if (
                inventory_before_raiders
                and not current_inventory
                and sum(inventory_before_raiders.values()) > 0
            ):
                self.player.inventory = dict(inventory_before_raiders)
            return result_line

        if selected == "AUTO":
            selected = "PAY"

        if selected == "FIGHT":
            ship = self.player.spaceship
            defenders = max(0, int(getattr(ship, "current_defenders", 0)))
            shields = max(0, int(getattr(ship, "current_shields", 0)))

            weapons_bonus = 0.0
            if self.player and "weapons" in self.player.crew:
                weapons_bonus = float(self.player.crew["weapons"].get_bonus())

            player_power = (
                (defenders * 1.35) + (shields * 0.28) + (18 * (1.0 + weapons_bonus))
            )
            raider_power = random.uniform(25.0, 85.0)

            if player_power >= raider_power:
                reward = random.randint(90, 420)
                self.player.credits += reward
                self._adjust_frontier_standing(1)
                if random.random() < 0.35:
                    self._adjust_authority_standing(-1)
                flavor = random.choice(
                    [
                        "Tracer fire cuts a corridor and the raiders break formation.",
                        "Your attack run cracks their line; survivors scatter.",
                        "A final broadside sends the blockade spinning into darkness.",
                    ]
                )
                return _finalize_raider_result(
                    f"RAIDER BLOCKADE BROKEN: +{reward:,} CR SALVAGED. {flavor}"
                )

            loss = min(self.player.credits, max(pay_loss, random.randint(80, 620)))
            self.player.credits -= loss
            dmg = random.randint(4, 16)
            self.player.take_damage(dmg)
            flavor = random.choice(
                [
                    "You disengage under heavy fire and limp back to safe vector.",
                    "Counterfire shreds your approach, forcing a hard retreat.",
                    "The raiders rake your hull before you punch free.",
                ]
            )
            return _finalize_raider_result(
                f"FAILED TO BREAK BLOCKADE: -{loss:,} CR. "
                f"HULL INTEGRITY -{dmg}% DURING WITHDRAWAL. {flavor}"
            )

        loss = min(self.player.credits, pay_loss)
        self.player.credits -= loss
        flavor = random.choice(
            [
                "The pirate captain clears your lane with a mocking salute.",
                "Encrypted payment accepted; the blockade opens just enough to pass.",
                "You keep your hull intact and bank the grudge for later.",
            ]
        )
        return _finalize_raider_result(f"RAIDER TOLL PAID: -{loss:,} CR. {flavor}")

    def process_random_signals(self):
        """Occasionally injects flavor text or market tips into the player's inbox."""
        if not hasattr(self, "last_signal_check"):
            self.last_signal_check = time.time()

        # Check every 3 minutes (180s)
        if time.time() - self.last_signal_check < 180:
            return

        self.last_signal_check = time.time()

        # 20% chance to actually receive something
        if random.random() > 0.20:
            return

        signal_type = random.choice(["MARKET_TIP", "SMUGGLER_PSST", "FLAVOR", "SPAM"])

        sender = "DEEP SPACE RELAY"
        subject = "ENCRYPTED SIGNAL"
        body = "..."

        if signal_type == "MARKET_TIP":
            p = random.choice(self.planets)
            items = list(p.item_modifiers.keys())
            if items:
                item = random.choice(items)
                mod = p.item_modifiers[item]
                sender = "SECTOR DATA BURST"
                subject = f"MKT REPORT: {p.name.upper()}"
                if mod < 90:
                    body = f"Trend Analysis: {item} prices on {p.name} are currently below sector averages ({mod}%). High profit potential for export."
                elif mod > 120:
                    body = f"Market Alert: {item} is in high demand on {p.name} ({mod}%). Recommend immediate supply run."
                else:
                    body = f"Intermittent data shows {item} market stability on {p.name} at {mod}%."

        elif signal_type == "SMUGGLER_PSST":
            # Only if player has bribed someone or visited a hub
            smug_planets = [
                p
                for p in self.planets
                if p.is_smuggler_hub or p.name in self.bribed_planets
            ]
            if smug_planets:
                p = random.choice(smug_planets)
                sender = p.npc_name.upper()
                subject = "A LITTLE SOMETHING"
                if p.smuggling_inventory:
                    item = random.choice(list(p.smuggling_inventory.keys()))
                    body = f"Hey spacer. I just got a shipment of {item} in. Get to {p.name} before the Alliance snoops around. Mention my name for a 'discount'."
                else:
                    body = f"Quiet day at {p.name}. Come by for a drink, I might have a job for you later."
            else:
                signal_type = "FLAVOR"  # Fallback

        if signal_type == "FLAVOR":
            sender = "GNN NEWS WIRE"
            subject = "SECTOR HEADLINES"
            options = [
                f"The Galactic Alliance has increased patrols around {random.choice(self.planets).name}. Security level remains at high alert.",
                f"Economic boom reported in the {random.choice(self.planets).name} system. Investors are flocking to local markets.",
                "Rumors of a 'Phantom Ship' sighted near the asteroid belt. Pilots are advised to stay in well-lit lanes.",
                "New record set for the Urth-Mastodrun run. 4.2 cycles. Can you beat it?",
            ]
            body = random.choice(options)

        elif signal_type == "SPAM":
            sender = "UNKNOWN TRANSMITTER"
            subject = "UNSOLICITED LOG"
            options = [
                "WE HAVE BEEN TRYING TO REACH YOU REGARDING YOUR SHIP'S EXTENDED WARRANTY.",
                "EASY CREDITS! WORK FROM YOUR COCKPIT! JOIN THE SYNDICATE TODAY!",
                "ENLARGE YOUR CARGO PODS WITH THIS ONE WEIRD TRICK. SCIENTISTS HATE HIM.",
                "You have won 1,000,000 CR! Click here to claim your prize (requires 500 CR processing fee).",
            ]
            body = random.choice(options)

        if body != "...":
            self.send_message(self.player.name, subject, body, sender_name=sender)

    def check_auto_refuel(self):
        if self.player and self.player.spaceship.fuel < self.player.spaceship.max_fuel:
            if self.player.spaceship.last_refuel_time > 0:
                elapsed = time.time() - self.player.spaceship.last_refuel_time
                # 4 hours = 14400 seconds
                if elapsed >= 14400:
                    self.player.spaceship.fuel = self.player.spaceship.max_fuel
                    self.player.spaceship.last_refuel_time = 0

    def get_orbit_targets(self):
        """Finds other players and NPC ships at the current planet."""
        targets = []

        # 1. NPC Ships
        for npc in self.npc_ships:
            if npc.orbiting_planet == self.current_planet.name:
                targets.append({"type": "NPC", "obj": npc, "remark": npc.get_remark()})

                # Chance of hostile NPC attacking immediately
                if npc.personality == "hostile" and random.random() < 0.3:
                    # We'll just return a flag or specific message
                    # But for now, let's keep it simple: the scan shows them.
                    pass

        # 2. Other Players (from all account save subdirectories)
        global_save_root = (
            os.path.dirname(getattr(self, "shared_planet_state_path", ""))
            or self.save_dir
        )
        seen_paths = set()
        for root, _, files in os.walk(global_save_root):
            for f in files:
                f_lower = str(f).lower()
                if not f_lower.endswith(".json"):
                    continue
                if f_lower in {
                    "universe_planets.json",
                    "galactic_news.json",
                    "account.json",
                }:
                    continue

                path = os.path.join(root, f)
                norm_path = os.path.normcase(os.path.abspath(path))
                if norm_path in seen_paths:
                    continue
                seen_paths.add(norm_path)

                try:
                    with open(path, "r", encoding="utf-8") as file:
                        data = json.load(file)
                except Exception:
                    continue

                if not isinstance(data, dict):
                    continue
                if str(data.get("password_hash") or "").strip():
                    continue
                if data.get("current_planet_name") != self.current_planet.name:
                    continue

                player_data = (
                    data.get("player") if isinstance(data.get("player"), dict) else {}
                )
                p_name = str(player_data.get("name", "")).strip()
                if not p_name or p_name == self.player.name:
                    continue

                is_abandoned = False
                if self.config.get("enable_abandonment"):
                    last_save = float(data.get("last_save_timestamp", 0) or 0)
                    days_limit = self.config.get("abandonment_days")
                    seconds_limit = float(days_limit) * 86400
                    if last_save > 0 and (time.time() - last_save) >= seconds_limit:
                        is_abandoned = True

                targets.append(
                    {
                        "type": "PLAYER",
                        "name": p_name,
                        "raw_data": data,
                        "is_abandoned": is_abandoned,
                        "save_path": path,
                    }
                )
        return targets

    def gift_cargo_to_orbit_target(self, target_data, item_name, qty=1):
        """Transfers cargo from current player to an orbit target."""
        if not self.player:
            return False, "No active commander."

        item = str(item_name)
        amount = max(1, int(qty))
        current_qty = int(self.player.inventory.get(item, 0))
        if current_qty < amount:
            return False, f"Insufficient {item} to transfer."

        target_type = str(target_data.get("type", "")).upper()
        target_name = ""
        if target_type == "NPC":
            target_obj = target_data.get("obj")
            target_name = str(getattr(target_obj, "name", "Unknown Target"))
        elif target_type == "PLAYER":
            target_name = str(target_data.get("name", "")).strip()
            if not target_name:
                return False, "Invalid target player."
            if target_name == self.player.name:
                return False, "Cannot transfer cargo to yourself."

            path = str(target_data.get("save_path", "")).strip()
            if not path:
                filename = f"{target_name.replace(' ', '_').lower()}.json"
                path = os.path.join(self.save_dir, filename)
            if not os.path.exists(path):
                return False, "Target player save not found."

            try:
                with open(path, "r") as f:
                    data = json.load(f)
                if "player" not in data:
                    return False, "Invalid target player data."

                target_inventory = data["player"].get("inventory")
                if not isinstance(target_inventory, dict):
                    target_inventory = {}

                target_inventory[item] = int(target_inventory.get(item, 0)) + amount
                data["player"]["inventory"] = target_inventory

                with open(path, "w") as f:
                    json.dump(data, f, indent=4)
            except Exception:
                return False, "Failed to transfer cargo to target ship."

            self.send_message(
                target_name,
                "CARGO TRANSFER",
                f"Commander {self.player.name} transferred {amount}x {item} to your ship.",
            )
        else:
            return False, "Invalid target type for cargo transfer."

        self.player.inventory[item] = current_qty - amount
        if self.player.inventory[item] <= 0:
            del self.player.inventory[item]

        return True, f"TRANSFERRED {amount}x {item} TO {target_name.upper()}."

    def claim_abandoned_ship(self, target_name, action, extras=None):
        """Handle interactions with abandoned player ships."""
        filename = f"{target_name.replace(' ', '_').lower()}.json"
        path = os.path.join(self.save_dir, filename)
        if not os.path.exists(path):
            return False, "Ship no longer exists."

        with open(path, "r") as f:
            data = json.load(f)
        ship_data = data["player"]["spaceship"]

        if action == "LOOT":
            # Just take cargo and credits
            loot_credits = data["player"].get("credits", 0)
            loot_items = data["player"].get("inventory", {})
            self.player.credits += loot_credits
            for item, qty in loot_items.items():
                self.player.inventory[item] = self.player.inventory.get(item, 0) + qty

            # Wipe the abandoned player's assets but keep the ship (as an empty husk)
            data["player"]["credits"] = 0
            data["player"]["inventory"] = {}
            with open(path, "w") as f:
                json.dump(data, f, indent=4)
            return (
                True,
                f"Looted {loot_credits} credits and cargo from {target_name}'s vessel.",
            )

        elif action == "DESTROY":
            os.remove(path)
            return True, f"Target vessel {target_name} has been vaporized."

        elif action == "SELL":
            # Sell based on model cost
            ship_val = 1000  # Default
            for s in self.spaceships:
                if s.model == ship_data["model"]:
                    ship_val = int(s.cost * 0.7)  # 70% resale
                    break
            self.player.credits += ship_val
            os.remove(path)
            return (
                True,
                f"Abandoned vessel sold to local scrappers for {ship_val} credits.",
            )

        elif action == "KEEP":
            # Transfer EVERYTHING to the new ship
            old_ship_val = 0
            for s in self.spaceships:
                if s.model == self.player.spaceship.model:
                    old_ship_val = int(s.calculate_value() * 0.7)
                    break

            # 1. Sell old ship
            self.player.credits += old_ship_val

            # 2. Update player spaceship to abandoned one
            # Find template for base stats
            template = self.spaceships[0]
            for s in self.spaceships:
                if s.model == ship_data["model"]:
                    template = s
                    break

            from classes import Spaceship

            new_ship = Spaceship(
                model=template.model,
                cost=template.cost,
                starting_cargo_pods=template.starting_cargo_pods,
                starting_shields=template.starting_shields,
                starting_defenders=template.starting_defenders,
                max_cargo_pods=template.max_cargo_pods,
                max_shields=template.max_shields,
                max_defenders=template.max_defenders,
                special_weapon=template.special_weapon,
                role_tags=ship_data.get(
                    "role_tags", getattr(template, "role_tags", [])
                ),
                module_slots=ship_data.get(
                    "module_slots", getattr(template, "module_slots", 2)
                ),
                installed_modules=ship_data.get(
                    "installed_modules", getattr(template, "installed_modules", [])
                ),
            )
            # Apply the specific levels from the abandoned ship
            new_ship.current_cargo_pods = ship_data["current_cargo"]
            new_ship.current_shields = ship_data["current_shields"]
            new_ship.current_defenders = ship_data["current_defenders"]
            new_ship.integrity = ship_data["integrity"]
            new_ship.fuel = ship_data["fuel"]

            self.player.spaceship = new_ship

            # Delete the abandoned save
            os.remove(path)
            return (
                True,
                f"You have moved your command to the abandoned vessel. Your old ship was scrapped for {old_ship_val} credits.",
            )

        elif action == "GIVE" and extras:
            recipient = extras.get("recipient")
            if not recipient:
                return False, "No recipient specified."

            r_filename = f"{recipient.replace(' ', '_').lower()}.json"
            r_path = os.path.join(self.save_dir, r_filename)
            if not os.path.exists(r_path):
                return False, "Recipient not found."

            # Transfer ownership: Basically overwrite recipient's ship with this one?
            # Or send a message to let them claim it?
            # Implementation: Overwrite recipient's ship but they get it next login
            with open(r_path, "r") as f:
                r_data = json.load(f)
            r_data["player"]["spaceship"] = ship_data
            with open(r_path, "w") as f:
                json.dump(r_data, f, indent=4)

            # Notify recipient
            self.send_message(
                recipient,
                "SHIP ACQUISITION",
                f"Commander {self.player.name} has gifted you an abandoned vessel: {ship_data['model']}.",
            )

            os.remove(path)
            return True, f"Vessel ownership transferred to {recipient}."

        return False, "Unknown action."

    def travel_to_planet(
        self,
        planet_index,
        skip_travel_event=False,
        travel_event_message=None,
    ):
        if 0 <= planet_index < len(self.planets):
            self._load_shared_planet_states()
            new_planet = self.planets[planet_index]

            is_barred, bar_msg = self.check_barred(new_planet.name)
            if is_barred:
                return False, f"NAV COMP LOCKED: {bar_msg}"

            dist = math.sqrt(
                (new_planet.x - self.current_planet.x) ** 2
                + (new_planet.y - self.current_planet.y) ** 2
            )

            fuel_cost = self._calculate_travel_fuel_cost(dist)

            if self.player.spaceship.fuel >= fuel_cost:
                self.player.spaceship.fuel -= fuel_cost

                # Integrity degradation: 1-5% based on travel distance
                # Max distance across map is ~1400 pixels
                dmg = max(1.0, (dist / 1400.0) * 5.0)
                self.player.take_damage(dmg)

                self.current_planet = new_planet
                self._apply_crew_activity("travel", specialty="engineer")

                if not hasattr(self.player, "port_visits"):
                    self.player.port_visits = {}
                self.player.port_visits[new_planet.name] = (
                    int(self.player.port_visits.get(new_planet.name, 0)) + 1
                )

                # Fluctuate prices across the sector on every jump
                for p in self.planets:
                    if hasattr(p, "fluctuate_prices"):
                        p.fluctuate_prices()

                rolled_event = self._maybe_roll_planet_event(new_planet)
                self._set_port_spotlight_deal(new_planet)

                # Apply docking fee (admin-configured, scaled by ship level)
                fee = self.get_docking_fee(new_planet, self.player.spaceship)
                visits = int(self.player.port_visits.get(new_planet.name, 0))
                if visits >= 5:
                    fee = int(round(fee * 0.9))
                self.player.credits -= fee

                # If fuel is now empty, start the recharge timer
                if self.player.spaceship.fuel <= 0:
                    self.player.spaceship.last_refuel_time = time.time()

                msg = f"ENGAGED WARP. CONSUMED {fuel_cost:.1f} FUEL. SHIP INTEGRITY -{dmg:.1f}%."
                if fee > 0:
                    msg += f" DOCKING FEE: {fee} CR PAID."

                event_msg = ""
                if travel_event_message:
                    event_msg = str(travel_event_message)
                elif not bool(skip_travel_event):
                    event_msg = self._roll_travel_event(new_planet, dist)
                if event_msg:
                    msg += f"\n{event_msg}"

                c_ok, c_msg = self._generate_trade_contract()
                if c_ok and c_msg:
                    msg += f"\n{c_msg}"

                deal = self.get_current_port_spotlight_deal()
                if deal:
                    msg += (
                        f"\nPORT SPOTLIGHT: {deal['item'].upper()} -{int(deal['discount_pct'])}% "
                        f"({int(deal['quantity'])} UNIT(S))."
                    )

                if rolled_event:
                    msg += (
                        f"\nPLANET EVENT: {rolled_event.get('label', 'Sector Disturbance').upper()} - "
                        f"{rolled_event.get('desc', 'Local market conditions shifted.')}"
                    )

                # Add crew insight
                if "engineer" in self.player.crew:
                    msg += f"\n\"{self.player.crew['engineer'].get_remark('travel')}\""
                elif "weapons" in self.player.crew:
                    msg += f"\n\"{self.player.crew['weapons'].get_remark('travel')}\""

                return True, msg
            else:
                return (
                    False,
                    f"Insufficient fuel! Need {fuel_cost:.1f}, have {self.player.spaceship.fuel:.1f}.",
                )
        return False, "Target coordinates invalid."
