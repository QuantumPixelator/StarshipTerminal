"""
Combat system helper module for PlanetView.

Handles all combat-related logic including:
- Combat window initialization and state management
- Combat rounds and special weapons
- Combat visual effects and feedback
- Post-combat actions and recommendations
"""

import math
from constants import *


class CombatManager:
    """Manages combat state and operations for a game view."""

    def __init__(self, view):
        """Initialize combat manager.
        
        Args:
            view: The parent PlanetView instance
        """
        self.view = view
        self.session = None
        self.commitment = 0
        self.impact_effects = []
        self.post_actions = []
        self.flash_timer = 0
        self.flash_color = (0, 0, 0)
        self.player_texture = None
        self.target_texture = None
        self.effects_enabled = True

    def has_active_combat(self):
        """Check if there's an active combat session."""
        return self.session and self.session.get("status") == "ACTIVE"

    def start_combat(self, target_data):
        """Start a new combat session.
        
        Args:
            target_data: Target information from network
        """
        if self.has_active_combat():
            return

        ok, msg, session = self.view.network.start_combat_session(target_data)
        if not ok:
            self.view.orbit_message = msg.upper()
            self.view.orbit_message_color = COLOR_ACCENT
            return

        self.session = session
        self.post_actions = []
        self.impact_effects = []
        self.view._play_sfx("combat", "combat_fire")
        
        fighters = int(self.view.network.player.spaceship.current_defenders)
        self.commitment = 1 if fighters > 0 else 0

        # Get opening combat remark from crew
        if "weapons" in self.view.network.player.crew:
            opener = self.view.network.player.crew["weapons"].get_remark("combat_start")
            self.session["log"].append(
                f"{self.view.network.player.crew['weapons'].name}: {opener}"
            )
        elif "engineer" in self.view.network.player.crew:
            opener = self.view.network.player.crew["engineer"].get_remark("combat_start")
            self.session["log"].append(
                f"{self.view.network.player.crew['engineer'].name}: {opener}"
            )

    def reset_commitment(self):
        """Reset combat commitment (called on mouse release)."""
        max_commit = max(0, int(self.view.network.player.spaceship.current_defenders))
        self.commitment = max(0, min(self.commitment, max_commit))

    def do_combat_round(self):
        """Execute a single combat round."""
        if not self.session:
            return

        pre_target = self.view.network._get_target_stats(self.session)
        p_ship = self.view.network.player.spaceship
        pre_player = (
            int(p_ship.current_shields),
            int(p_ship.current_defenders),
            int(p_ship.integrity),
        )

        ok, msg, session = self.view.network.resolve_combat_round(self.session, self.commitment)
        if not ok:
            self.view.orbit_message = msg.upper()
            self.view.orbit_message_color = COLOR_ACCENT
            return

        self.session = session
        self.view.network.save_game()
        self.view._play_sfx("combat", "combat_fire")

        # Calculate damage dealt
        post_target = self.view.network._get_target_stats(self.session)
        post_player = (
            int(self.view.network.player.spaceship.current_shields),
            int(self.view.network.player.spaceship.current_defenders),
            int(self.view.network.player.spaceship.integrity),
        )

        target_shield_hit = max(0, int(pre_target[0]) - int(post_target[0]))
        target_hull_hit = max(0, int(pre_target[2]) - int(post_target[2]))
        player_shield_hit = max(0, int(pre_player[0]) - int(post_player[0]))
        player_hull_hit = max(0, int(pre_player[2]) - int(post_player[2]))

        # Queue visual effects based on damage
        if target_shield_hit > 0 or target_hull_hit > 0:
            self.queue_effect("laser_to_target", duration=0.18)
        if player_shield_hit > 0 or player_hull_hit > 0:
            self.queue_effect("laser_to_player", duration=0.18)
        if target_shield_hit > 0:
            self.queue_effect("shield_target", duration=0.32)
        if player_shield_hit > 0:
            self.queue_effect("shield_player", duration=0.32)
        if target_hull_hit > 0:
            self.queue_effect("hull_target", duration=0.36)
        if player_hull_hit > 0:
            self.queue_effect("hull_player", duration=0.36)

        # Check for critical hits
        recent_lines = " ".join(self.session.get("log", [])[-3:]).upper()
        if "YOU [CRITICAL HIT]" in recent_lines:
            self.flash_timer = 0.18
            self.flash_color = COLOR_PRIMARY
            self.queue_effect("hull_target", duration=0.44)
            self.view._play_sfx("combat", "combat_hit")
        elif "ENEMY [CRITICAL HIT]" in recent_lines:
            self.flash_timer = 0.18
            self.flash_color = COLOR_ACCENT
            self.queue_effect("hull_player", duration=0.44)
            self.view._play_sfx("combat", "combat_hit")

        # Update commitment clamping
        if self.session.get("status") == "ACTIVE":
            max_commit = int(self.view.network.player.spaceship.current_defenders)
            self.commitment = min(self.commitment, max_commit)
            if max_commit > 0 and self.commitment == 0:
                self.commitment = 1

    def use_special_weapon(self):
        """Fire the player's special weapon."""
        if not self.session:
            return
        if self.session.get("target_type") != "PLANET":
            return

        result_data = self.view.network.fire_special_weapon(self.session)
        success = result_data.get("success", False)
        msg = result_data.get("message", "")
        result = result_data.get("result", {})

        if not success:
            self.session.setdefault("log", []).append(f"[SPECIAL WEAPON] FAILED: {msg.upper()}")
            self.view.orbit_message = msg.upper()
            self.view.orbit_message_color = COLOR_ACCENT
            return

        # Update session from server
        srv_session = result_data.get("session")
        if srv_session and isinstance(srv_session, dict):
            self.session = srv_session

        # Visual and audio feedback
        self.view._play_sfx("combat", "combat_special")
        self.view._play_sfx("combat", "combat_hit")
        self.flash_timer = 0.30
        self.flash_color = (255, 80, 40)
        self.queue_effect("hull_target", duration=0.55)
        self.queue_effect("laser_to_target", duration=0.28)

        self.view.network.save_game()

        # Update local cooldown
        import time as _time
        self.view.network.player.last_special_weapon_time = _time.time()

        # Log the result
        weapon_name = str(result.get("weapon_name", "SPECIAL WEAPON"))
        pop_before = int(result.get("pop_before", 0))
        pop_after = int(result.get("pop_after", 0))
        pop_pct = float(result.get("pop_reduction_pct", 0))
        treasury_before = int(result.get("treasury_before", 0))
        treasury_after = int(result.get("treasury_after", 0))

        log_line = (
            f"[{weapon_name.upper()} FIRED] Pop {pop_before:,}→{pop_after:,} "
            f"(-{pop_pct:.0f}%), Treasury {treasury_before:,}→{treasury_after:,}"
        )
        self.session.setdefault("log", []).append(log_line)

    def close_combat(self):
        """Close the combat window."""
        if not self.session:
            return

        summary = self.session.get("summary") or {}
        msg = summary.get("message", "Combat window closed.")
        end_status = self.session.get("status", "UNKNOWN")

        ok, outcome, rewards = self.view.network.close_combat_session(self.session)
        if not ok:
            self.view.orbit_message = msg.upper()
            self.view.orbit_message_color = COLOR_ACCENT
        else:
            self.view.network.save_game()
            self.view.orbit_message = outcome.upper()
            if end_status in ("WON", "PLAYER_WON"):
                self.view.orbit_message_color = COLOR_PRIMARY
                self.view._play_sfx("combat", "combat_victory")
            elif end_status in ("LOST", "PLAYER_LOST"):
                self.view.orbit_message_color = COLOR_ACCENT
                self.view._play_sfx("combat", "combat_defeat")

        self.session = None
        self.post_actions = []
        self.commitment = 0
        self.impact_effects = []

    def queue_effect(self, effect_type, duration=0.32):
        """Queue a visual combat effect."""
        if not self.effects_enabled:
            return
        self.impact_effects.append(
            {
                "type": str(effect_type),
                "ttl": float(duration),
                "max_ttl": float(duration),
            }
        )
        if len(self.impact_effects) > 16:
            self.impact_effects = self.impact_effects[-16:]

    def update_effects(self, delta_time):
        """Update combat effect timers."""
        for effect in self.impact_effects:
            effect["ttl"] -= delta_time
        self.impact_effects = [e for e in self.impact_effects if e["ttl"] > 0]

        if self.flash_timer > 0:
            self.flash_timer -= delta_time

    def snapshot_state(self):
        """Take a snapshot of current game state for delta tracking."""
        ship = self.view.network.player.spaceship
        return {
            "credits": int(self.view.network.player.credits),
            "integrity": int(ship.integrity),
            "shields": int(ship.current_shields),
            "fighters": int(ship.current_defenders),
            "cargo": int(sum(self.view.network.player.inventory.values())),
        }

    def record_action(self, label, before_state, after_state, result_msg):
        """Record a post-combat action with state deltas."""
        deltas = []

        def _delta(key, title):
            old = int(before_state.get(key, 0))
            new = int(after_state.get(key, 0))
            if old == new:
                return None
            diff = new - old
            sign = "+" if diff > 0 else ""
            return f"{title} {sign}{diff}"

        for key, title in [
            ("credits", "CR"),
            ("integrity", "HULL"),
            ("shields", "SHLD"),
            ("fighters", "FIG"),
            ("cargo", "CARGO"),
        ]:
            piece = _delta(key, title)
            if piece:
                deltas.append(piece)

        delta_text = " | ".join(deltas) if deltas else "NO SYSTEM DELTA"
        msg_part = self.view._clamp_text(str(result_msg or "").upper(), 56)
        if msg_part:
            line = f"{label}: {delta_text} :: {msg_part}"
        else:
            line = f"{label}: {delta_text}"

        self.post_actions.insert(0, line)
        self.post_actions = self.post_actions[:3]

    def get_repair_preview(self):
        """Get repair cost and availability info."""
        ship = self.view.network.player.spaceship
        planet = self.view.network.current_planet
        if planet.repair_multiplier is None:
            return False, "NO REPAIR FACILITY HERE"
        if ship.integrity >= ship.max_integrity:
            return False, "HULL ALREADY MAX"

        repair_needed = ship.max_integrity - ship.integrity
        cost_per_percent = (ship.cost * 0.002) * planet.repair_multiplier
        total_cost = int(
            (repair_needed / (ship.max_integrity / 100)) * cost_per_percent
        )
        if total_cost < 1:
            total_cost = 1

        if self.view.network.player.credits >= total_cost:
            return True, f"REPAIR PREVIEW: {total_cost:,} CR"
        shortfall = total_cost - int(self.view.network.player.credits)
        return False, f"REPAIR PREVIEW: {total_cost:,} CR (SHORT {shortfall:,})"

    def get_recommendations(self):
        """Get post-combat recommendations."""
        if not self.session:
            return []

        ship = self.view.network.player.spaceship
        recommendations = []

        if ship.integrity < ship.max_integrity * 0.4:
            recommendations.append(f"HULL REPAIR RECOMMENDED ({int(ship.integrity)}/{int(ship.max_integrity)})")

        if ship.current_shields < ship.shields * 0.3:
            recommendations.append(f"RECHARGE SHIELDS RECOMMENDED ({int(ship.current_shields)}/{int(ship.shields)})")

        if ship.current_defenders <= 1 and ship.fighters > 1:
            recommendations.append("DEPLOY ADDITIONAL FIGHTERS RECOMMENDED")

        if self.view.network.player.credits < 50000:
            recommendations.append("CREDITS LOW - TRADE/SMUGGLE TO EARN MORE")

        return recommendations

    def window_rects(self):
        """Get all combat window rectangles."""
        w, h = 920, 620  # COMBAT_WINDOW_W, COMBAT_WINDOW_H
        x = SCREEN_WIDTH // 2 - w // 2
        y = SCREEN_HEIGHT // 2 - h // 2
        return {
            "window": (x, y, w, h),
            "minus": (x + 40, y + 190, 60, 40),
            "plus": (x + 300, y + 190, 60, 40),
            "attack": (x + 390, y + 180, 190, 55),
            "cancel": (x + 600, y + 180, 220, 55),
            "special_weapon": (x + 390, y + 242, 430, 32),
            "sw_confirm_yes": (x + 140, y + 225, 300, 42),
            "sw_confirm_no": (x + 460, y + 225, 300, 42),
            "post_autofit": (x + 30, y + 200, 160, 40),
            "post_repair": (x + 205, y + 200, 160, 40),
            "post_close": (x + 30, y + 155, 335, 35),
            "post_systems": (x + 390, y + 155, 190, 35),
        }
