import time

class FactionMixin:
    def _get_combat_win_streak(self):
            if not self.player:
                return 0
            return int(getattr(self.player, "combat_win_streak", 0))

    def _set_combat_win_streak(self, value):
            if not self.player:
                return
            self.player.combat_win_streak = max(0, int(value))

    def _get_sector_reputation(self):
            return self._get_authority_standing()

    def _get_authority_standing(self):
            if not self.player:
                return 0
            if hasattr(self.player, "authority_standing"):
                return int(getattr(self.player, "authority_standing", 0))
            return int(getattr(self.player, "sector_reputation", 0))

    def _get_frontier_standing(self):
            if not self.player:
                return 0
            return int(getattr(self.player, "frontier_standing", 0))

    def _set_standing(self, attr_name, value):
            if not self.player:
                return 0
            clamped = max(-100, min(100, int(value)))
            setattr(self.player, attr_name, clamped)
            if attr_name == "authority_standing":
                self.player.sector_reputation = int(clamped)
            return int(clamped)

    def _adjust_authority_standing(self, delta):
            return self._set_standing(
                "authority_standing", self._get_authority_standing() + int(delta)
            )

    def _adjust_frontier_standing(self, delta):
            return self._set_standing(
                "frontier_standing", self._get_frontier_standing() + int(delta)
            )

    def _adjust_sector_reputation(self, delta):
            return self._adjust_authority_standing(delta)

    def get_sector_standing_label(self):
            rep = self._get_authority_standing()
            if rep >= 60:
                return "HEROIC"
            if rep >= 25:
                return "TRUSTED"
            if rep <= -60:
                return "WANTED"
            if rep <= -25:
                return "SUSPECT"
            return "NEUTRAL"

    def get_authority_standing_label(self):
            return self.get_sector_standing_label()

    def get_frontier_standing_label(self):
            rep = self._get_frontier_standing()
            if rep >= 60:
                return "LEGENDARY"
            if rep >= 25:
                return "CONNECTED"
            if rep <= -60:
                return "OUTCAST"
            if rep <= -25:
                return "UNTRUSTED"
            return "NEUTRAL"

    def _get_contract_chain_streak(self):
            if not self.player:
                return 0
            return int(getattr(self.player, "contract_chain_streak", 0))

    def _set_contract_chain_streak(self, value):
            if not self.player:
                return
            self.player.contract_chain_streak = max(0, int(value))

    def _get_contract_chain_bonus_factor(self):
            streak = self._get_contract_chain_streak()
            per_completion = float(
                self.config.get("contract_chain_bonus_per_completion", 0.05)
            )
            cap = float(self.config.get("contract_chain_bonus_cap", 0.30))
            return max(0.0, min(cap, streak * per_completion))

    def _update_law_heat_decay(self):
            now = time.time()
            elapsed = max(0.0, now - float(getattr(self, "last_heat_decay_time", now)))
            if elapsed < 3600:
                return

            decay_per_hour = max(0, int(self.config.get("law_heat_decay_per_hour", 3)))
            ticks = int(elapsed // 3600)
            if ticks <= 0 or decay_per_hour <= 0:
                self.last_heat_decay_time = now
                return

            for planet_name in list(self.planet_heat.keys()):
                value = max(0, int(self.planet_heat.get(planet_name, 0)) - (ticks * decay_per_hour))
                if value <= 0:
                    self.planet_heat.pop(planet_name, None)
                else:
                    self.planet_heat[planet_name] = int(min(100, value))

            self.last_heat_decay_time = now

    def _get_law_heat(self, planet_name):
            self._update_law_heat_decay()
            return int(max(0, min(100, self.planet_heat.get(planet_name, 0))))

    def _adjust_law_heat(self, planet_name, delta):
            self._update_law_heat_decay()
            current = int(self.planet_heat.get(planet_name, 0))
            updated = max(0, min(100, current + int(delta)))
            if updated <= 0:
                self.planet_heat.pop(planet_name, None)
            else:
                self.planet_heat[planet_name] = int(updated)
            return int(updated)

    def bar_player(self, planet_name):
            """Bar player for fleeing combat with a planet."""
            # 24 hours = 86400 seconds (matching interest cycle)
            self.player.barred_planets[planet_name] = time.time() + 86400
