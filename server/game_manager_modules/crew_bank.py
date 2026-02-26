import time


class CrewBankMixin:
    def _is_planet_owner(self, planet):
        if not self.player or not planet:
            return False
        owner_name = str(getattr(planet, "owner", "") or "").strip().lower()
        player_name = str(getattr(self.player, "name", "") or "").strip().lower()
        return bool(owner_name and owner_name == player_name)

    def _default_planet_credit_balance(self, planet):
        """Return 20% of the planet's population, rounded (minimum 0)."""
        pop = max(0, int(getattr(planet, "population", 0)))
        return max(0, round(pop * 0.20))

    def _get_owned_planets(self):
        if not self.player:
            return []
        return [p for p in self.planets if self._is_planet_owner(p)]

    def _ensure_planet_credit_state(self, planet, now=None):
        timestamp = float(now if now is not None else time.time())

        if int(getattr(planet, "credit_balance", 0)) <= 0:
            planet.credit_balance = int(self._default_planet_credit_balance(planet))
        
        if not getattr(planet, "credits_initialized", False):
            planet.credits_initialized = True

        last_interest_time = float(
            getattr(planet, "last_credit_interest_time", 0.0) or 0.0
        )
        if last_interest_time <= 0:
            planet.last_credit_interest_time = timestamp

    def _planet_interest_projection(self, planet):
        balance = max(0, int(getattr(planet, "credit_balance", 0)))
        rate = max(0.0, float(self.config.get("owned_planet_interest_rate")))
        if balance <= 0 or rate <= 0:
            return 0
        projected = int(round(balance * rate))
        return max(1, projected)

    def get_planet_financials(self):
        if not self.player or not self.current_planet:
            return {
                "can_manage": False,
                "current_planet": None,
            }

        planet = self.current_planet
        self._ensure_planet_credit_state(planet)

        owned = self._get_owned_planets()
        for p in owned:
            self._ensure_planet_credit_state(p)

        owned_total_balance = sum(int(getattr(p, "credit_balance", 0)) for p in owned)
        owned_total_interest = sum(self._planet_interest_projection(p) for p in owned)

        return {
            "can_manage": self._is_planet_owner(planet),
            "current_planet": {
                "name": planet.name,
                "owner": planet.owner,
                "population": int(getattr(planet, "population", 0)),
                "credit_balance": int(getattr(planet, "credit_balance", 0)),
                "projected_interest": int(self._planet_interest_projection(planet)),
            },
            "owned_count": int(len(owned)),
            "owned_total_balance": int(owned_total_balance),
            "owned_total_projected_interest": int(owned_total_interest),
        }

    def payout_interest(self):
        """Applies daily bank and colony interest. Colony interest compounds in planet treasuries."""
        if not self.player:
            return False, ""
        now = time.time()
        self._update_market_dynamics()
        self._send_sector_report_if_due()
        bank_total_payout = 0
        bank_paid = []
        planet_interest_total = 0
        planet_income_lines = []

        # Bank Interest (New)
        if not hasattr(self.player, "last_bank_interest_time"):
            self.player.last_bank_interest_time = now

        if now - self.player.last_bank_interest_time >= 86400:
            rate = self.config.get("bank_interest_rate")
            bank_payout = int(self.player.bank_balance * rate)
            if bank_payout > 0:
                self.player.bank_balance += bank_payout
                bank_total_payout += bank_payout
                bank_paid.append("Bank Savings")
            self.player.last_bank_interest_time = now

        pop_rate = max(
            0.0,
            float(self.config.get("owned_planet_interest_rate")),
        )
        for planet in self._get_owned_planets():
            self._ensure_planet_credit_state(planet, now=now)

            last_time = float(getattr(planet, "last_credit_interest_time", now) or now)
            elapsed = now - last_time
            if elapsed < 86400:
                continue

            cycles = int(elapsed // 86400)
            if cycles <= 0:
                continue

            original_balance = int(getattr(planet, "credit_balance", 0))
            running_balance = int(original_balance)
            earned = 0
            for _ in range(cycles):
                payout = int(round(running_balance * pop_rate))
                if payout <= 0 and pop_rate > 0 and running_balance > 0:
                    payout = 1
                running_balance += max(0, int(payout))
                earned += max(0, int(payout))

            planet.credit_balance = int(running_balance)
            planet.last_credit_interest_time = float(last_time + (cycles * 86400))

            if earned > 0:
                planet_interest_total += int(earned)
                planet_income_lines.append(
                    f"{planet.name} +{earned:,} CR (TREASURY {planet.credit_balance:,})"
                )

            self.player.owned_planets[planet.name] = now

        if bank_total_payout > 0:
            self._append_galactic_news(
                title=f"Bank Savings Growth: +{bank_total_payout:,} CR",
                body=(
                    "Interest applied to personal savings at Galaxy First National Bank."
                ),
                event_type="bank_interest",
                audience="player",
                player_name=self.player.name,
            )
            self.send_message(
                self.player.name,
                "Bank Interest Payment",
                f"Your savings account has earned {bank_total_payout:,} CR in interest.",
                sender_name="Galactic Bank"
            )

        if planet_interest_total > 0:
            self._append_galactic_news(
                title=f"Colony Treasury Growth: +{planet_interest_total:,} CR",
                body=(
                    "Daily colony interest retained in local treasuries: "
                    + " | ".join(planet_income_lines)
                ),
                event_type="daily_income",
                audience="player",
                player_name=self.player.name,
            )
            self.send_message(
                self.player.name,
                "Colony Interest Report",
                f"Your colonies have generated {planet_interest_total:,} CR in local treasury interest.\n\nDetails:\n" + "\n".join(planet_income_lines),
                sender_name="Colonial Admin"
            )

        if bank_total_payout > 0 or planet_interest_total > 0:
            self._save_shared_planet_states()

        if bank_total_payout > 0 and planet_interest_total > 0:
            return (
                True,
                f"Interest posted: BANK +{bank_total_payout:,} CR, COLONY TREASURIES +{planet_interest_total:,} CR.",
            )
        if bank_total_payout > 0:
            return (
                True,
                f"Collected {bank_total_payout:,} CR bank interest ({', '.join(bank_paid)}).",
            )
        if planet_interest_total > 0:
            return (
                True,
                f"Colony treasuries gained {planet_interest_total:,} CR in interest.",
            )
        return False, "No interest payouts available yet."

    def process_crew_pay(self):
        """Deducts crew salaries every 24 hours."""
        if not self.player or not self.player.crew:
            return False, ""

        now = time.time()
        if now - self.player.last_crew_pay_time >= 86400:
            for m in self.player.crew.values():
                level_based_pay = max(50, int(m.level) * 200)
                m.daily_pay = int(level_based_pay)

            total_pay = sum(int(m.daily_pay) for m in self.player.crew.values())
            self.player.last_crew_pay_time = now

            if self.player.credits >= total_pay:
                self.player.credits -= total_pay
                msg = f"Paid {total_pay:,} CR in crew salaries."
                for m in self.player.crew.values():
                    m.unpaid_cycles = 0
                    m.apply_activity("rest")
                    m.morale = min(100, int(m.morale) + 4)
                    m.fatigue = max(0, int(m.fatigue) - 6)
                return True, msg
            else:
                abandoned = []
                last_cycle = 0
                for s, m in list(self.player.crew.items()):
                    m.unpaid_cycles += 1
                    m.morale = max(0, int(getattr(m, "morale", 100)) - 8)
                    m.fatigue = min(100, int(getattr(m, "fatigue", 0)) + 5)
                    last_cycle = m.unpaid_cycles
                    if m.unpaid_cycles >= 7:
                        abandoned.append(m.name)
                        del self.player.crew[s]

                if abandoned:
                    return (
                        True,
                        f"UNPAID SALARIES: {', '.join(abandoned)} HAVE ABANDONED SHIP!",
                    )
                return (
                    True,
                    f"Insufficient funds to pay crew. Salaries are in arrears (Cycle {last_cycle}/7).",
                )
        return False, ""

    def _apply_crew_activity(self, activity, specialty=None):
        if not self.player or not self.player.crew:
            return

        if specialty:
            member = self.player.crew.get(specialty)
            if member:
                member.apply_activity(activity)
            return

        for member in self.player.crew.values():
            member.apply_activity(activity)

    def get_planet_crew_offers(self, planet=None):
        if not self.player:
            return []

        target = planet or self.current_planet
        if not target or not target.crew_services:
            return []

        authority = self._get_authority_standing()
        frontier = self._get_frontier_standing()
        offers = []

        for service in target.crew_services:
            crew_type = str(service.get("type", "")).lower()
            levels = sorted(int(lvl) for lvl in service.get("levels", []))
            if not levels:
                continue

            max_allowed_level = levels[-1]
            if crew_type == "engineer" and authority >= 35:
                max_allowed_level = max_allowed_level + 1
            if crew_type == "weapons" and frontier >= 35:
                max_allowed_level = max_allowed_level + 1

            for level in levels:
                if level > max_allowed_level:
                    continue

                base_cost = int(level * 5000)
                modifier = 1.0

                if crew_type == "engineer":
                    modifier *= max(0.72, 1.0 - (max(0, authority) / 220.0))
                elif crew_type == "weapons":
                    modifier *= max(0.72, 1.0 - (max(0, frontier) / 230.0))

                if getattr(target, "is_smuggler_hub", False):
                    if crew_type == "weapons":
                        modifier *= 0.88
                    else:
                        modifier *= 1.12

                if (
                    "Alliance" in str(getattr(target, "vendor", ""))
                    and crew_type == "engineer"
                ):
                    modifier *= 0.92

                hire_cost = max(500, int(round(base_cost * modifier)))
                daily_pay = max(50, int(round(level * 200 * modifier)))

                offers.append(
                    {
                        "type": crew_type,
                        "level": int(level),
                        "hire_cost": int(hire_cost),
                        "daily_pay": int(daily_pay),
                        "planet": target.name,
                    }
                )

        offers.sort(key=lambda o: (o["type"], o["level"], o["hire_cost"]))
        return offers

    def transfer_fighters(self, amount, direction):
        """
        direction: "TO_PLANET" or "TO_SHIP"
        """
        planet = self.current_planet
        ship = self.player.spaceship

        if planet.owner != self.player.name:
            return False, "You do not own this planet."

        if direction == "TO_PLANET":
            if ship.current_defenders < amount:
                return (
                    False,
                    f"Not enough fighters on ship! (Has {ship.current_defenders})",
                )

            if planet.defenders + amount > planet.max_defenders:
                room = planet.max_defenders - planet.defenders
                return (
                    False,
                    f"Planet hangar full! Max capacity: {planet.max_defenders} (Space left: {room})",
                )

            ship.current_defenders -= amount
            planet.defenders += amount
            self._save_shared_planet_states()
            self._append_galactic_news(
                title=f"{planet.name}: +{amount} Defenders Deployed",
                body=(
                    f"You transferred {amount} fighters to {planet.name}. "
                    f"Planet defenders now {int(planet.defenders)}/{int(planet.max_defenders)}."
                ),
                event_type="planet_defense_transfer",
                planet_name=planet.name,
                audience="player",
                player_name=self.player.name,
            )
            return True, f"Transferred {amount} fighters to {planet.name} hangars."

        elif direction == "TO_SHIP":
            if planet.defenders < amount:
                return False, f"Not enough fighters on planet! (Has {planet.defenders})"

            if ship.current_defenders + amount > ship.max_defenders:
                room = ship.max_defenders - ship.current_defenders
                return (
                    False,
                    f"Ship hangar full! Max capacity: {ship.max_defenders} (Space left: {room})",
                )

            planet.defenders -= amount
            ship.current_defenders += amount
            self._save_shared_planet_states()
            self._append_galactic_news(
                title=f"{planet.name}: -{amount} Defenders Withdrawn",
                body=(
                    f"You withdrew {amount} fighters from {planet.name}. "
                    f"Planet defenders now {int(planet.defenders)}/{int(planet.max_defenders)}."
                ),
                event_type="planet_defense_transfer",
                planet_name=planet.name,
                audience="player",
                player_name=self.player.name,
            )
            return True, f"Transferred {amount} fighters to ship hangars."

        return False, "Invalid transfer direction."

    def transfer_shields(self, amount, direction):
        """
        direction: "TO_PLANET" or "TO_SHIP"
        """
        planet = self.current_planet
        ship = self.player.spaceship
        amount = max(1, int(amount))

        if planet.owner != self.player.name:
            return False, "You do not own this planet."

        planet_max_shields = int(
            getattr(planet, "max_shields", max(1, planet.base_shields))
        )

        if direction == "TO_PLANET":
            if ship.current_shields < amount:
                return (
                    False,
                    f"Not enough shield units on ship! (Has {ship.current_shields})",
                )

            if planet.shields + amount > planet_max_shields:
                room = planet_max_shields - planet.shields
                return (
                    False,
                    f"Planet shield grid full! Max capacity: {planet_max_shields} (Space left: {room})",
                )

            ship.current_shields -= amount
            planet.shields += amount
            self._save_shared_planet_states()
            self._append_galactic_news(
                title=f"{planet.name}: +{amount} Shields Routed",
                body=(
                    f"You routed {amount} shield units to {planet.name}. "
                    f"Planet shields now {int(planet.shields)}/{int(planet_max_shields)}."
                ),
                event_type="planet_defense_transfer",
                planet_name=planet.name,
                audience="player",
                player_name=self.player.name,
            )
            return True, f"Transferred {amount} shield units to {planet.name} grid."

        elif direction == "TO_SHIP":
            if planet.shields < amount:
                return (
                    False,
                    f"Not enough shield units on planet! (Has {planet.shields})",
                )

            if ship.current_shields + amount > ship.max_shields:
                room = ship.max_shields - ship.current_shields
                return (
                    False,
                    f"Ship shields full! Max capacity: {ship.max_shields} (Space left: {room})",
                )

            planet.shields -= amount
            ship.current_shields += amount
            self._save_shared_planet_states()
            self._append_galactic_news(
                title=f"{planet.name}: -{amount} Shields Withdrawn",
                body=(
                    f"You withdrew {amount} shield units from {planet.name}. "
                    f"Planet shields now {int(planet.shields)}/{int(planet_max_shields)}."
                ),
                event_type="planet_defense_transfer",
                planet_name=planet.name,
                audience="player",
                player_name=self.player.name,
            )
            return True, f"Transferred {amount} shield units to ship systems."

        return False, "Invalid transfer direction."

    def process_conquered_planet_defense_regen(self):
        if not self.player:
            return False, ""

        now = time.time()
        events = []

        for planet in self.planets:
            if planet.owner != self.player.name:
                continue

            has_fighter_prod = "Fighter Squadron" in planet.items
            has_shield_prod = "Energy Shields" in planet.items
            if not (has_fighter_prod or has_shield_prod):
                continue

            last_regen = float(getattr(planet, "last_defense_regen_time", 0) or 0)
            if last_regen <= 0:
                planet.last_defense_regen_time = now
                continue

            elapsed = now - last_regen
            if elapsed < self.planet_defense_regen_interval:
                continue

            cycles = int(elapsed // self.planet_defense_regen_interval)
            if cycles <= 0:
                continue

            fighters_added = 0
            shields_added = 0

            if has_fighter_prod and planet.defenders < planet.max_defenders:
                target_def = min(
                    planet.max_defenders,
                    planet.defenders + (cycles * self.planet_defense_regen_fighters),
                )
                fighters_added = int(target_def - planet.defenders)
                planet.defenders = int(target_def)

            planet_max_shields = int(
                getattr(planet, "max_shields", max(1, planet.base_shields))
            )
            if has_shield_prod and planet.shields < planet_max_shields:
                target_sh = min(
                    planet_max_shields,
                    planet.shields + (cycles * self.planet_defense_regen_shields),
                )
                shields_added = int(target_sh - planet.shields)
                planet.shields = int(target_sh)

            planet.last_defense_regen_time = last_regen + (
                cycles * self.planet_defense_regen_interval
            )

            if fighters_added > 0 or shields_added > 0:
                events.append(
                    f"{planet.name}: +{fighters_added} fighters, +{shields_added} shields"
                )

        if events:
            self._save_shared_planet_states()
            self._append_galactic_news(
                title="Colony Defense Production Update",
                body=" | ".join(events),
                event_type="planet_regen",
                audience="player",
                player_name=self.player.name,
            )
            return True, f"COLONY DEFENSE PRODUCTION UPDATED: {' | '.join(events)}"
        return False, ""

    def bank_deposit(self, amount):
        amount = int(amount or 0)
        if amount <= 0:
            return False, "Deposit amount must be greater than zero."
        if self.player.credits >= amount:
            self.player.credits -= amount
            self.player.bank_balance += amount
            return True, f"Deposited {amount:,} CR into your account."
        return False, "Insufficient credits on hand!"

    def bank_withdraw(self, amount):
        amount = int(amount or 0)
        if amount <= 0:
            return False, "Withdrawal amount must be greater than zero."
        if self.player.bank_balance >= amount:
            self.player.bank_balance -= amount
            self.player.credits += amount
            return True, f"Withdrew {amount:,} CR from your account."
        return False, "Insufficient bank balance!"

    def planet_deposit(self, amount):
        amount = int(amount or 0)
        if amount <= 0:
            return False, "Deposit amount must be greater than zero."
        if not self.player or not self.current_planet:
            return False, "No active planet session."

        planet = self.current_planet
        if not self._is_planet_owner(planet):
            return False, "Only the planet owner can deposit to this treasury."
        if self.player.credits < amount:
            return False, "Insufficient credits on hand!"

        self._ensure_planet_credit_state(planet)
        self.player.credits -= amount
        planet.credit_balance = int(getattr(planet, "credit_balance", 0)) + amount
        self._save_shared_planet_states()
        return True, f"Deposited {amount:,} CR into {planet.name} treasury."

    def planet_withdraw(self, amount):
        amount = int(amount or 0)
        if amount <= 0:
            return False, "Withdrawal amount must be greater than zero."
        if not self.player or not self.current_planet:
            return False, "No active planet session."

        planet = self.current_planet
        if not self._is_planet_owner(planet):
            return False, "Only the planet owner can withdraw from this treasury."

        self._ensure_planet_credit_state(planet)
        if int(getattr(planet, "credit_balance", 0)) < amount:
            return False, "Insufficient planet treasury balance!"

        planet.credit_balance = int(getattr(planet, "credit_balance", 0)) - amount
        self.player.credits += amount
        self._save_shared_planet_states()
        return True, f"Withdrew {amount:,} CR from {planet.name} treasury."
