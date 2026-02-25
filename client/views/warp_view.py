"""
WarpView — hyperspace jump animation for Starship Terminal.
Displayed during inter-planet travel; transitions to TravelEventView
or PlanetView on arrival.
"""

import arcade
import math
import random
from constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    COLOR_PRIMARY, COLOR_SECONDARY, COLOR_ACCENT,
    COLOR_BG, COLOR_TEXT_DIM,
    get_font,
)
from .effects_orchestrator import update_effects, draw_effects


class WarpView(arcade.View):
    """Animated warp/hyperspace travel screen shown between planets."""

    def __init__(self, game_manager, target_planet_index, duration):
        super().__init__()
        self.network = game_manager
        self.target_idx = target_planet_index
        self.duration = duration
        self.time_left = duration
        self.target_p = self.network.planets[target_planet_index]
        self.font_ui = get_font("ui")

        self.stars = []
        for _ in range(200):
            self.stars.append(
                {
                    "x": random.uniform(-SCREEN_WIDTH, SCREEN_WIDTH),
                    "y": random.uniform(-SCREEN_HEIGHT, SCREEN_HEIGHT),
                    "z": random.uniform(1, 1000),
                }
            )

    def _complete_arrival(self, travel_event_line=""):
        """Finalize the jump and transition to PlanetView."""
        # Lazy imports to avoid circular dependency
        from views.planet_view import PlanetView

        is_barred, bar_msg = self.network.check_barred(self.target_p.name)

        success, msg = self.network.travel_to_planet(
            self.target_idx,
            skip_travel_event=True,
            travel_event_message=travel_event_line,
        )
        self.network.save_game()
        view = PlanetView(self.network)
        if is_barred:
            view.mode = "INFO"
            view.arrival_msg = bar_msg
            view.arrival_msg_timer = 10.0
        elif success and msg:
            view.arrival_msg = msg
            view.arrival_msg_timer = 10.0
        self.window.show_view(view)

    def on_update(self, delta_time):
        self.time_left -= delta_time
        try:
            update_effects(delta_time)
        except Exception:
            pass
        if self.time_left <= 0:
            current_p = self.network.current_planet
            dist = math.sqrt(
                (self.target_p.x - current_p.x) ** 2
                + (self.target_p.y - current_p.y) ** 2
            )
            event_payload = self.network.roll_travel_event_payload(self.target_p, dist)
            if event_payload:
                from views.travel_event_view import TravelEventView  # lazy
                self.window.show_view(
                    TravelEventView(
                        self.network,
                        event_payload,
                        continue_callback=self._complete_arrival,
                    )
                )
                return

            self._complete_arrival("")
            return

        warp_speed = 700.0
        for s in self.stars:
            s["z"] -= delta_time * warp_speed
            if s["z"] <= 1:
                s["z"] = 1000
                s["x"] = random.uniform(-SCREEN_WIDTH, SCREEN_WIDTH)
                s["y"] = random.uniform(-SCREEN_HEIGHT, SCREEN_HEIGHT)

    def on_draw(self):
        self.clear()
        cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2

        for s in self.stars:
            f = 400 / max(1, s["z"])
            sx = cx + s["x"] * f
            sy = cy + s["y"] * f

            if 0 <= sx <= SCREEN_WIDTH and 0 <= sy <= SCREEN_HEIGHT:
                size = max(0.5, 3 * f)
                alpha = int(255 * (1 - s["z"] / 1000))
                color = (200, 230, 255, alpha)
                arcade.draw_circle_filled(sx, sy, size, color)

        arcade.draw_lbwh_rectangle_filled(0, cy - 80, SCREEN_WIDTH, 160, (0, 0, 0, 180))
        arcade.draw_line(0, cy - 80, SCREEN_WIDTH, cy - 80, COLOR_SECONDARY, 2)
        arcade.draw_line(0, cy + 80, SCREEN_WIDTH, cy + 80, COLOR_SECONDARY, 2)

        arcade.Text(
            f"HYPERSPACE JUMP: {self.target_p.name.upper()}",
            cx,
            cy + 20,
            COLOR_PRIMARY,
            30,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()
        arcade.Text(
            f"ARRIVAL IN {max(0.0, self.time_left):.1f} SECONDS",
            cx,
            cy - 30,
            COLOR_ACCENT,
            16,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()
        try:
            draw_effects()
        except Exception:
            pass
