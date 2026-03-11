import arcade
import math
import random

from constants import SCREEN_WIDTH, SCREEN_HEIGHT, COLOR_PRIMARY, COLOR_SECONDARY, COLOR_TEXT_DIM, get_font
from .planet_detail_view import PlanetDetailView


class GalaxyMapView(arcade.View):
    """Phase-5 strategic galaxy map driven by get_full_state snapshots."""

    def __init__(self, network):
        super().__init__()
        self.network = network
        self.state = {}
        self.planets = []
        self.font_ui = get_font("ui")
        self.font_ui_bold = get_font("ui_bold")
        self.selected_index = 0
        self._refresh_elapsed = 0.0
        self._animation_time = 0.0
        self.status = ""
        self._poll_interval = 0.35
        self._poll_failures = 0
        self._last_state_version = -1
        self._stars = [
            (
                random.randint(0, SCREEN_WIDTH),
                random.randint(0, SCREEN_HEIGHT),
                random.uniform(0.25, 0.95),
                random.uniform(0.5, 1.8),
            )
            for _ in range(120)
        ]

    def on_show_view(self):
        arcade.set_background_color((6, 8, 14))
        self._refresh_state()

    def _refresh_state(self):
        try:
            fresh_state = self.network.get_full_state() or {}
            self._poll_failures = 0
            self._poll_interval = 0.35
        except Exception:
            self._poll_failures += 1
            self._poll_interval = min(1.5, 0.35 + (self._poll_failures * 0.25))
            self.status = "STATE SYNC DEGRADED, RETRYING..."
            return
        incoming_version = int(fresh_state.get("state_version", 0) or 0)
        if incoming_version == int(self._last_state_version):
            self.status = f"STATE STABLE | VERSION: {incoming_version} | POLL: {self._poll_interval:.2f}s"
            return

        self._last_state_version = incoming_version
        self.state = dict(fresh_state)
        self.planets = list(self.state.get("planets", []) or [])
        if not self.planets:
            self.status = "NO PLANETS RETURNED FROM FULL STATE SNAPSHOT."
            self.selected_index = 0
            return
        self.selected_index = max(0, min(int(self.selected_index), len(self.planets) - 1))
        active_combats = sum(
            1 for row in list(self.state.get("combat_sessions", []) or []) if str(row.get("status") or "") == "active"
        )
        self.status = (
            f"PLANETS: {len(self.planets)} | ACTIVE COMBATS: {active_combats} "
            f"| VERSION: {incoming_version} | POLL: {self._poll_interval:.2f}s"
        )

    def on_update(self, delta_time):
        self._animation_time += float(delta_time)
        self._refresh_elapsed += float(delta_time)
        if self._refresh_elapsed >= self._poll_interval:
            self._refresh_elapsed = 0.0
            self._refresh_state()

    def _selected_planet(self):
        if not self.planets:
            return None
        return dict(self.planets[int(self.selected_index)] or {})

    def on_draw(self):
        self.clear()
        for sx, sy, alpha_base, phase in self._stars:
            twinkle = alpha_base + (0.25 * math.sin(self._animation_time * phase))
            alpha = int(max(30, min(180, twinkle * 255)))
            arcade.draw_circle_filled(sx, sy, 1.2, (170, 190, 210, alpha))

        arcade.draw_text(
            "GALAXY MAP",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 80,
            COLOR_PRIMARY,
            30,
            anchor_x="center",
            font_name=self.font_ui_bold,
        )

        if not self.planets:
            arcade.draw_text("NO PLANETS AVAILABLE", SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2, COLOR_SECONDARY, 16, anchor_x="center", font_name=self.font_ui)
            return

        cols = 10
        spacing_x = max(70, SCREEN_WIDTH // (cols + 1))
        spacing_y = 90
        start_x = spacing_x
        start_y = SCREEN_HEIGHT - 170

        for idx, row in enumerate(self.planets):
            col = idx % cols
            r = idx // cols
            x = start_x + (col * spacing_x)
            y = start_y - (r * spacing_y)
            is_selected = idx == int(self.selected_index)
            owner = row.get("owner_id")
            if owner is None:
                color = (160, 160, 170)
            else:
                color = (80 + (int(owner) * 53) % 150, 120 + (int(owner) * 41) % 110, 220)
            base_radius = 18 if is_selected else 12
            pulse = 1.0 + (0.10 * math.sin((self._animation_time * 3.5) + idx))
            radius = max(8, int(base_radius * pulse))
            arcade.draw_circle_filled(x, y, radius, color)
            arcade.draw_circle_outline(x, y, radius + 5, (90, 120, 170, 80), 1)
            if is_selected:
                arcade.draw_circle_outline(x, y, radius + 5, COLOR_PRIMARY, 2)
            if owner is not None:
                glow_alpha = int(55 + (35 * (1.0 + math.sin(self._animation_time * 2.0 + idx))))
                arcade.draw_circle_outline(x, y, radius + 9, (color[0], color[1], color[2], max(20, min(120, glow_alpha))), 2)
            arcade.draw_text(
                str(row.get("name") or "?"),
                x,
                y - 28,
                COLOR_TEXT_DIM,
                10,
                anchor_x="center",
                font_name=self.font_ui,
            )

        selected = self._selected_planet() or {}
        arcade.draw_text(
            f"SELECTED: {str(selected.get('name') or '').upper()} | OWNER: {selected.get('owner_id', 'NEUTRAL')}",
            60,
            90,
            COLOR_SECONDARY,
            13,
            font_name=self.font_ui,
        )
        arcade.draw_text(self.status, 60, 64, COLOR_PRIMARY, 12, font_name=self.font_ui)
        arcade.draw_text("[LEFT/RIGHT] SELECT  [ENTER] DETAIL  [S] STATUS  [R] REFRESH  [ESC] MENU", 60, 40, COLOR_TEXT_DIM, 11, font_name=self.font_ui)

    def on_key_press(self, key, modifiers):
        if key == arcade.key.R:
            self._refresh_state()
            return
        if key == arcade.key.S:
            from .status_view import StatusView

            self.window.show_view(StatusView(self.network))
            return
        if key in (arcade.key.RIGHT, arcade.key.D):
            if self.planets:
                self.selected_index = (int(self.selected_index) + 1) % len(self.planets)
            return
        if key in (arcade.key.LEFT, arcade.key.A):
            if self.planets:
                self.selected_index = (int(self.selected_index) - 1) % len(self.planets)
            return
        if key in (arcade.key.ENTER, arcade.key.RETURN):
            selected = self._selected_planet()
            if selected:
                self.window.show_view(PlanetDetailView(self.network, selected, self.state))
            return
        if key == arcade.key.ESCAPE:
            from .menu import MainMenuView

            self.window.show_view(MainMenuView())
