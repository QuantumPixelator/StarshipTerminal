import time


class ShipOpsMixin:
    def _get_refuel_timer_config(self):
        enabled = bool(self.config.get("refuel_timer_enabled"))
        try:
            max_refuels = int(float(self.config.get("refuel_timer_max_refuels")))
        except Exception:
            max_refuels = int(float(self.config.get("refuel_timer_max_refuels") or 0))
        try:
            window_hours = float(self.config.get("refuel_timer_window_hours"))
        except Exception:
            window_hours = float(self.config.get("refuel_timer_window_hours") or 0.0)
        try:
            cost_multiplier_pct = float(
                self.config.get("refuel_timer_cost_multiplier_pct")
            )
        except Exception:
            cost_multiplier_pct = float(
                self.config.get("refuel_timer_cost_multiplier_pct") or 0.0
            )

        max_refuels = max(1, max_refuels)
        window_hours = max(0.25, window_hours)
        cost_multiplier_pct = max(0.0, min(500.0, cost_multiplier_pct))

        return {
            "enabled": enabled,
            "max_refuels": max_refuels,
            "window_hours": window_hours,
            "window_seconds": window_hours * 3600.0,
            "cost_multiplier_pct": cost_multiplier_pct,
            "cost_multiplier": cost_multiplier_pct / 100.0,
        }

    def _get_refuel_timer_state(self, now=None, mutate=True):
        cfg = self._get_refuel_timer_config()
        if not self.player:
            return {
                "enabled": cfg["enabled"],
                "max_refuels": cfg["max_refuels"],
                "used_refuels": 0,
                "remaining_refuels": cfg["max_refuels"],
                "window_seconds": cfg["window_seconds"],
                "seconds_until_reset": 0.0,
                "window_started_at": 0.0,
                "cost_multiplier_pct": cfg["cost_multiplier_pct"],
            }

        if now is None:
            now = time.time()

        used = int(getattr(self.player, "refuel_uses_in_window", 0) or 0)
        started_at = float(getattr(self.player, "refuel_window_started_at", 0.0) or 0.0)
        if used < 0:
            used = 0
        if started_at < 0:
            started_at = 0.0

        if cfg["enabled"] and used > 0 and started_at > 0:
            elapsed = max(0.0, now - started_at)
            if elapsed >= cfg["window_seconds"]:
                used = 0
                started_at = 0.0
                if mutate:
                    self.player.refuel_uses_in_window = 0
                    self.player.refuel_window_started_at = 0.0

        remaining = max(0, cfg["max_refuels"] - used)
        seconds_until_reset = 0.0
        if cfg["enabled"] and used > 0 and started_at > 0:
            seconds_until_reset = max(0.0, cfg["window_seconds"] - (now - started_at))

        return {
            "enabled": cfg["enabled"],
            "max_refuels": cfg["max_refuels"],
            "used_refuels": used,
            "remaining_refuels": remaining,
            "window_seconds": cfg["window_seconds"],
            "seconds_until_reset": seconds_until_reset,
            "window_started_at": started_at,
            "cost_multiplier_pct": cfg["cost_multiplier_pct"],
        }

    def _format_seconds_compact(self, seconds):
        total = max(0, int(round(float(seconds))))
        hours = total // 3600
        minutes = (total % 3600) // 60
        return f"{hours}h {minutes:02d}m"

    def _get_ship_fuel_tier(self, ship):
        if ship.cost < 20000:
            return 1, "STANDARD"
        if ship.cost < 50000:
            return 2, "REFINED"
        if ship.cost < 100000:
            return 3, "HIGH-GRADE"
        if ship.cost < 200000:
            return 4, "MIL-SPEC"
        return 5, "QUANTUM"

    def get_ship_level(self, ship=None):
        active_ship = ship or (self.player.spaceship if self.player else None)
        if isinstance(active_ship, str):
            ship_name = active_ship.strip().lower()
            # Try to match with player's ship first
            player_ship = self.player.spaceship if self.player else None
            if (
                player_ship
                and str(getattr(player_ship, "model", "")).lower() == ship_name
            ):
                active_ship = player_ship
            else:
                # Look up in catalog
                active_ship = next(
                    (
                        s
                        for s in list(getattr(self, "spaceships", []) or [])
                        if str(getattr(s, "model", "")).lower() == ship_name
                    ),
                    None,
                )

        if not active_ship:
            return 1

        # Level based on list index (1-based)
        if hasattr(self, "spaceships"):
            for i, s in enumerate(self.spaceships):
                if s.model == active_ship.model:
                    return i + 1

        # Fallback if not found in list (shouldn't happen for valid ships)
        tier, _ = self._get_ship_fuel_tier(active_ship)
        return int(max(1, tier))

    def get_docking_fee(self, planet=None, ship=None):
        base_fee = float(self.config.get("base_docking_fee"))
        level_multiplier = float(
            self.config.get("docking_fee_ship_level_multiplier")
        )
        ship_level = self.get_ship_level(ship)
        rep = self._get_sector_reputation()
        rep_step = float(self.config.get("reputation_docking_fee_step"))
        rep_tiers = int(rep // 20)
        rep_modifier = 1.0 - (rep_tiers * rep_step)
        rep_modifier = max(0.70, min(1.40, rep_modifier))

        event_modifier = 1.0
        target_planet = planet or self.current_planet
        evt = self.get_planet_event(target_planet.name if target_planet else None)
        if evt:
            event_modifier = max(0.70, min(1.60, float(evt.get("docking_mult", 1.0))))

        fee = int(
            round(
                base_fee * ship_level * level_multiplier * rep_modifier * event_modifier
            )
        )
        return max(0, fee)

    def get_refuel_quote(self):
        ship = self.player.spaceship
        needed = max(0.0, ship.max_fuel - ship.fuel)
        tier, fuel_grade = self._get_ship_fuel_tier(ship)
        timer_state = self._get_refuel_timer_state()

        base_unit_cost = 2.5
        tier_multipliers = {
            1: 1.00,
            2: 1.28,
            3: 1.65,
            4: 2.15,
            5: 2.80,
        }
        unit_cost = base_unit_cost * tier_multipliers.get(tier, 1.0)
        if timer_state["enabled"]:
            unit_cost *= timer_state["cost_multiplier_pct"] / 100.0

        total_cost = int(round(needed * unit_cost))
        if needed > 0 and total_cost < 1:
            total_cost = 1

        refuel_locked = bool(
            timer_state["enabled"] and timer_state["remaining_refuels"] <= 0
        )

        return {
            "needed": needed,
            "unit_cost": unit_cost,
            "total_cost": total_cost,
            "tier": tier,
            "fuel_grade": fuel_grade,
            "refuel_timer_enabled": timer_state["enabled"],
            "refuel_uses_remaining": int(timer_state["remaining_refuels"]),
            "refuel_uses_max": int(timer_state["max_refuels"]),
            "refuel_window_seconds": float(timer_state["window_seconds"]),
            "seconds_until_refuel_reset": float(timer_state["seconds_until_reset"]),
            "refuel_locked": refuel_locked,
        }

    def buy_fuel(self, amount, cost=None):
        quote = self.get_refuel_quote()
        needed = quote["needed"]

        timer_state = self._get_refuel_timer_state()
        if timer_state["enabled"] and timer_state["remaining_refuels"] <= 0:
            wait_text = self._format_seconds_compact(timer_state["seconds_until_reset"])
            return (
                False,
                (
                    "REFUEL LIMIT REACHED. "
                    f"WAIT {wait_text} FOR THE NEXT REFUEL WINDOW."
                ),
            )

        purchase_amount = max(0.0, min(float(amount), float(needed)))
        if purchase_amount <= 0:
            return False, "FUEL CELLS ALREADY AT MAXIMUM CAPACITY."

        computed_cost = int(round(purchase_amount * quote["unit_cost"]))
        if computed_cost < 1:
            computed_cost = 1

        if cost is not None:
            computed_cost = int(cost)

        if self.player.credits >= computed_cost:
            self.player.credits -= computed_cost
            self.player.spaceship.fuel = min(
                self.player.spaceship.max_fuel,
                self.player.spaceship.fuel + purchase_amount,
            )
            self.player.spaceship.last_refuel_time = time.time()

            if timer_state["enabled"]:
                now = time.time()
                used = int(getattr(self.player, "refuel_uses_in_window", 0) or 0)
                started_at = float(
                    getattr(self.player, "refuel_window_started_at", 0.0) or 0.0
                )
                if used <= 0 or started_at <= 0:
                    self.player.refuel_window_started_at = now
                    self.player.refuel_uses_in_window = 1
                else:
                    self.player.refuel_uses_in_window = used + 1

            return (
                True,
                f"Purchased {purchase_amount:.1f} units of {quote['fuel_grade']} fuel for {computed_cost:,} CR.",
            )
        return False, "Insufficient credits for fuel!"

    def repair_hull(self):
        ship = self.player.spaceship
        planet = self.current_planet

        if planet.repair_multiplier is None:
            return False, f"NO REPAIR FACILITIES AVAILABLE ON {planet.name.upper()}."

        if ship.integrity >= ship.max_integrity:
            return False, "HULL IS ALREADY AT MAXIMUM INTEGRITY."

        # Cost per 1% integrity = 0.2% of ship base cost * planet multiplier
        repair_needed = ship.max_integrity - ship.integrity
        # Normalize repair cost to be per 1% of total capacity
        cost_per_percent = (ship.cost * 0.002) * planet.repair_multiplier
        # If integrity is 200, 1% is 2 points.
        total_cost = int(
            (repair_needed / (ship.max_integrity / 100)) * cost_per_percent
        )
        if total_cost < 1:
            total_cost = 1

        if self.player.credits >= total_cost:
            self.player.credits -= total_cost
            ship.integrity = ship.max_integrity
            return (
                True,
                f"REPAIRED HULL TO 100% FOR {total_cost:,} CR AT {planet.name.upper()}.",
            )

        return False, f"INSUFFICIENT CREDITS! NEED {total_cost:,} CR FOR REPAIR."

    def get_current_planet_info(self):
        if self.current_planet:
            return self.current_planet.get_info()
        return None

    def buy_ship(self, new_ship):
        # Handle string input (ship model name)
        if isinstance(new_ship, str):
            ship_name = new_ship.strip().lower()
            found = next(
                (s for s in self.spaceships if s.model.lower() == ship_name), None
            )
            if not found:
                return False, f"Ship model '{new_ship}' not found."
            new_ship = found

        info = self.player.spaceship.get_trade_in_info()
        trade_in_value = info["trade_in"]
        net_cost = new_ship.cost - trade_in_value

        # Check total liquidity (Wallet + Bank)
        total_available = self.player.credits + self.player.bank_balance

        if total_available >= net_cost:
            # Deduct from wallet first, then bank
            if self.player.credits >= net_cost:
                self.player.credits -= net_cost
            else:
                remaining = net_cost - self.player.credits
                self.player.credits = 0
                self.player.bank_balance -= remaining

            # Transfer inventory to new ship
            old_inventory = self.player.inventory
            self.player.spaceship = new_ship.clone()
            self.player.inventory = old_inventory
            return (
                True,
                f"Purchased {new_ship.model}! Net cost: {net_cost:,} CR (Trade-in: {trade_in_value:,})",
            )

        needed = net_cost - total_available
        return (
            False,
            f"Insufficient total funds! Need {needed:,} CR more (including Bank).",
        )

    def install_ship_upgrade(self, item_name, quantity=1):
        if not self.player:
            return False, "No active player."

        ship = self.player.spaceship
        qty = max(1, int(quantity))

        # Verify inventory
        in_stock = int(self.player.inventory.get(item_name, 0))
        if in_stock < qty:
            return False, f"Insufficient {item_name} in cargo (Have {in_stock})."

        success = False
        msg = ""

        if item_name == "Cargo Pod":
            success, msg = ship.upgrade_cargo_pods(qty)
        elif item_name == "Energy Shields":
            success, msg = ship.upgrade_shields(qty)
        elif item_name == "Fighter Squadron":
            success, msg = ship.upgrade_defenders(qty)
        elif item_name == "Nanobot Repair Kits":
            # Server-side repair logic using kits
            if ship.integrity >= ship.max_integrity:
                return False, "Hull already at maximum integrity."

            # Logic similar to client's _auto_install but authoritative
            integrity_missing = max(0, int(ship.max_integrity - ship.integrity))
            # 1 kit = 50 integrity
            kits_needed = (integrity_missing + 49) // 50
            use_kits = min(qty, kits_needed)

            repaired = min(50 * use_kits, integrity_missing)
            ship.integrity = min(ship.max_integrity, ship.integrity + repaired)

            # We consume only the kits used
            qty = use_kits
            success = True
            msg = f"Automated nanobots repaired hull (+{repaired})."
        else:
            return False, "Item is not installable."

        if success:
            self.player.inventory[item_name] = in_stock - qty
            if self.player.inventory[item_name] <= 0:
                del self.player.inventory[item_name]
            return True, msg

        return False, msg
