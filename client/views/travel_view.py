"""
TravelView — sector navigation map for Starship Terminal.
Displays the galaxy map for selecting a destination planet and
initiating warp jumps.
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
from views.travel_helpers import _calculate_travel_fuel_cost, _get_warp_travel_duration_seconds
from .effects_orchestrator import update_effects, draw_effects


class TravelView(arcade.View):
    """
    Interactive galaxy map screen.
    Arrow keys or mouse targeting selects planets; ENTER initiates warp jump.
    """

    def __init__(self, game_manager):
        super().__init__()
        self.network = game_manager
        self.selected_planet = 0
        self.font_ui = get_font("ui")
        self.font_ui_bold = get_font("ui_bold")
        self.message = ""
        self.time_elapsed = 0.0

        self.header_txt = arcade.Text(
            "SECTOR NAVIGATION GRID",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 50,
            COLOR_PRIMARY,
            28,
            anchor_x="center",
            font_name=self.font_ui,
        )
        self.status_txt = arcade.Text(
            "", 30, 70, COLOR_PRIMARY, 14, font_name=self.font_ui
        )
        self.msg_txt = arcade.Text("", 30, 30, COLOR_ACCENT, 16, font_name=self.font_ui)
        self.instr_txt = arcade.Text(
            "KEYS: ARROWS TO TARGET | ENTER TO ENGAGE | ESC TO ABORT",
            30,
            30,
            COLOR_TEXT_DIM,
            14,
            font_name=self.font_ui,
        )
        self.fuel_req_txt = arcade.Text(
            "", 0, 0, COLOR_ACCENT, 10, anchor_x="center", font_name=self.font_ui
        )

        self.planet_labels = []
        for p in self.network.planets:
            txt = arcade.Text(
                p.name.upper(),
                p.x,
                p.y - 20,
                (0, 150, 255, 180),
                10,
                anchor_x="center",
                font_name=self.font_ui,
            )
            self.planet_labels.append(txt)

        star_rng = random.Random("travel-map-stars")
        self.map_stars = []
        for _ in range(240):
            self.map_stars.append(
                {
                    "x": star_rng.uniform(0, SCREEN_WIDTH),
                    "y": star_rng.uniform(110, SCREEN_HEIGHT - 20),
                    "size": star_rng.uniform(0.7, 2.3),
                    "alpha": star_rng.randint(60, 200),
                    "twinkle": star_rng.uniform(1.4, 4.5),
                    "phase": star_rng.uniform(0, math.tau),
                    "drift_x": star_rng.uniform(-2.8, 2.8),
                    "drift_y": star_rng.uniform(-1.4, 1.4),
                }
            )

        nebula_rng = random.Random("travel-map-nebula")
        self.nebulae = []
        for _ in range(6):
            self.nebulae.append(
                {
                    "x": nebula_rng.uniform(180, SCREEN_WIDTH - 180),
                    "y": nebula_rng.uniform(170, SCREEN_HEIGHT - 140),
                    "r": nebula_rng.uniform(120, 240),
                    "phase": nebula_rng.uniform(0, math.tau),
                    "drift": nebula_rng.uniform(4.0, 12.0),
                }
            )

    def on_update(self, delta_time):
        self.time_elapsed += delta_time
        try:
            update_effects(delta_time)
        except Exception:
            pass

    def on_draw(self):
        self.clear()

        # Animated nebula background
        for cloud in self.nebulae:
            pulse = 0.7 + 0.3 * math.sin(self.time_elapsed * 0.45 + cloud["phase"])
            cloud_alpha = int(22 + (20 * pulse))
            drift_x = (
                math.sin(self.time_elapsed * 0.05 + cloud["phase"]) * cloud["drift"]
            )
            drift_y = math.cos(self.time_elapsed * 0.04 + cloud["phase"]) * (
                cloud["drift"] * 0.5
            )
            arcade.draw_circle_filled(
                cloud["x"] + drift_x,
                cloud["y"] + drift_y,
                cloud["r"],
                (35, 70, 120, cloud_alpha),
            )

        # Twinkling star field
        for star in self.map_stars:
            sx = (star["x"] + self.time_elapsed * star["drift_x"]) % SCREEN_WIDTH
            sy = 110 + (
                (star["y"] - 110 + self.time_elapsed * star["drift_y"])
                % (SCREEN_HEIGHT - 120)
            )
            twinkle = 0.55 + 0.45 * math.sin(
                self.time_elapsed * star["twinkle"] + star["phase"]
            )
            alpha = max(25, int(star["alpha"] * twinkle))
            arcade.draw_circle_filled(
                sx,
                sy,
                star["size"] + (0.2 if twinkle > 0.9 else 0),
                (185, 220, 255, alpha),
            )

        # Draw global effects on top
        try:
            draw_effects()
        except Exception:
            pass

        self.header_txt.draw()

        # Animated grid
        grid_alpha = int(24 + 12 * (0.5 + 0.5 * math.sin(self.time_elapsed * 0.8)))
        for i in range(0, SCREEN_WIDTH, 100):
            arcade.draw_line(i, 0, i, SCREEN_HEIGHT, (*COLOR_SECONDARY, grid_alpha))
        for i in range(0, SCREEN_HEIGHT, 100):
            arcade.draw_line(0, i, SCREEN_WIDTH, i, (*COLOR_SECONDARY, grid_alpha))

        # Ambient route web showing sector topology
        for i, p1 in enumerate(self.network.planets):
            for p2 in self.network.planets[i + 1:]:
                dist = math.sqrt((p2.x - p1.x) ** 2 + (p2.y - p1.y) ** 2)
                if dist > 360:
                    continue
                line_alpha = int(max(14, 52 - (dist / 360) * 38))
                arcade.draw_line(
                    p1.x,
                    p1.y,
                    p2.x,
                    p2.y,
                    (35, 120, 190, line_alpha),
                    1,
                )

        # Draw planets
        current_p = self.network.current_planet
        for i, p in enumerate(self.network.planets):
            is_sel = i == self.selected_planet
            is_here = p == current_p
            route_has_fuel = None

            map_x = p.x
            map_y = p.y

            if is_sel and not is_here:
                dist = math.sqrt((p.x - current_p.x) ** 2 + (p.y - current_p.y) ** 2)
                fuel_cost = _calculate_travel_fuel_cost(self.network, dist)

                has_fuel = self.network.player.spaceship.fuel >= fuel_cost
                route_has_fuel = has_fuel
                route_color = COLOR_PRIMARY if has_fuel else COLOR_ACCENT
                arcade.draw_line(current_p.x, current_p.y, p.x, p.y, route_color, 2)

                docking_fee = self.network.get_docking_fee(
                    p, self.network.player.spaceship
                )

                self.fuel_req_txt.text = (
                    f"EST. FUEL: {fuel_cost:.1f} | EST. DOCKING: {docking_fee:,} CR"
                )
                self.fuel_req_txt.color = route_color
                self.fuel_req_txt.x = (p.x + current_p.x) // 2
                self.fuel_req_txt.y = (p.y + current_p.y) // 2 + 10
                self.fuel_req_txt.draw()

            color = COLOR_PRIMARY if is_sel else COLOR_TEXT_DIM
            if is_here:
                color = COLOR_SECONDARY

            size = 8 if is_sel else 5
            arcade.draw_circle_filled(map_x, map_y, size, color)

            if is_here:
                here_radius = 13 + 1.8 * math.sin(self.time_elapsed * 2.2)
                arcade.draw_circle_outline(
                    map_x,
                    map_y,
                    here_radius,
                    (*COLOR_SECONDARY, 210),
                    2,
                )

            if is_sel:
                pulse_radius = 15 + 3.2 * math.sin(self.time_elapsed * 5.0)
                arcade.draw_circle_outline(
                    map_x,
                    map_y,
                    pulse_radius,
                    (*COLOR_PRIMARY, 220),
                    2,
                )
                orbit_x = map_x + math.cos(self.time_elapsed * 4.0) * (pulse_radius + 4)
                orbit_y = map_y + math.sin(self.time_elapsed * 4.0) * (pulse_radius + 4)
                arcade.draw_circle_filled(orbit_x, orbit_y, 2.8, COLOR_ACCENT)

            lbl = self.planet_labels[i]
            if is_here:
                if "(LOCATED)" not in lbl.text:
                    lbl.text = f"{p.name.upper()} (LOCATED)"
                lbl.color = COLOR_SECONDARY
                lbl.font_size = 12
            elif is_sel:
                lbl.text = p.name.upper()
                lbl.color = (
                    COLOR_PRIMARY if route_has_fuel is not False else COLOR_ACCENT
                )
                lbl.font_size = 14
            else:
                lbl.text = p.name.upper()
                lbl.color = (0, 150, 255, 180)
                lbl.font_size = 10

            lbl.draw()

            evt = self.network.get_planet_event(p.name)
            if evt:
                arcade.draw_circle_outline(
                    map_x, map_y, size + 6, (255, 180, 60, 180), 1
                )

        # Bottom status bar
        arcade.draw_lbwh_rectangle_filled(0, 0, SCREEN_WIDTH, 100, (10, 10, 20, 230))
        arcade.draw_line(0, 100, SCREEN_WIDTH, 100, COLOR_SECONDARY, 2)

        ship = self.network.player.spaceship
        self.status_txt.text = (
            f"FUEL: {ship.fuel:.1f} / {ship.max_fuel} | POSITION: {current_p.name}"
        )
        self.status_txt.draw()

        if self.message:
            self.msg_txt.text = self.message
            self.msg_txt.draw()
        else:
            self.instr_txt.draw()

        selected_event = self.network.get_planet_event(
            self.network.planets[self.selected_planet].name
        )
        if selected_event:
            arcade.Text(
                f"EVENT @ {self.network.planets[self.selected_planet].name.upper()}: {str(selected_event.get('label', 'SECTOR SHIFT')).upper()}",
                30,
                12,
                COLOR_SECONDARY,
                11,
                font_name=self.font_ui_bold,
                width=SCREEN_WIDTH - 60,
            ).draw()

    def on_key_press(self, key, modifiers):
        if key == arcade.key.UP:
            self.selected_planet = (self.selected_planet - 1) % len(
                self.network.planets
            )
        elif key == arcade.key.DOWN:
            self.selected_planet = (self.selected_planet + 1) % len(
                self.network.planets
            )
        elif key == arcade.key.LEFT:
            self.selected_planet = (self.selected_planet - 1) % len(
                self.network.planets
            )
        elif key == arcade.key.RIGHT:
            self.selected_planet = (self.selected_planet + 1) % len(
                self.network.planets
            )
        elif key == arcade.key.ENTER or key == arcade.key.RETURN:
            if (
                self.network.planets[self.selected_planet]
                == self.network.current_planet
            ):
                return

            target_p = self.network.planets[self.selected_planet]
            current_p = self.network.current_planet
            diff_x = target_p.x - current_p.x
            diff_y = target_p.y - current_p.y
            dist = math.sqrt(diff_x * diff_x + diff_y * diff_y)
            fuel_cost = _calculate_travel_fuel_cost(self.network, dist)

            if self.network.player.spaceship.fuel < fuel_cost:
                self.message = f"INSUFFICIENT FUEL! NEED {fuel_cost:.1f} UNITS".upper()
                return

            duration = _get_warp_travel_duration_seconds(
                self.network,
                dist,
                default_value=3.0,
                refresh_config=True,
            )
            from views.warp_view import WarpView  # lazy to avoid circular import
            self.window.show_view(
                WarpView(self.network, self.selected_planet, duration)
            )

        elif key == arcade.key.ESCAPE:
            from views.planet_view import PlanetView  # lazy to avoid circular import
            self.window.show_view(PlanetView(self.network, suppress_arrival_popup=True))

    def on_mouse_motion(self, x, y, dx, dy):
        """Target the nearest planet to the mouse cursor."""
        closest_idx = 0
        min_dist = 999999
        for i, p in enumerate(self.network.planets):
            dist = math.sqrt((x - p.x) ** 2 + (y - p.y) ** 2)
            if dist < min_dist:
                min_dist = dist
                closest_idx = i

        if min_dist < 65:
            self.selected_planet = closest_idx

    def on_mouse_press(self, x, y, button, modifiers):
        self.on_mouse_motion(x, y, 0, 0)
        self.on_key_press(arcade.key.ENTER, 0)
