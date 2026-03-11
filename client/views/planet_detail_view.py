import arcade

from constants import SCREEN_WIDTH, SCREEN_HEIGHT, COLOR_PRIMARY, COLOR_SECONDARY, COLOR_TEXT_DIM, get_font
from .market_view import MarketView
from .combat_view import CombatView


class PlanetDetailView(arcade.View):
    """Focused planet details view for the Phase-5 strategic map flow."""

    def __init__(self, network, planet_row, full_state):
        super().__init__()
        self.network = network
        self.planet_row = dict(planet_row or {})
        self.full_state = dict(full_state or {})
        self.font_ui = get_font("ui")
        self.font_ui_bold = get_font("ui_bold")
        self.status = ""

    def on_show_view(self):
        arcade.set_background_color((8, 10, 16))

    def on_draw(self):
        self.clear()
        name = str(self.planet_row.get("name") or "UNKNOWN")
        owner = self.planet_row.get("owner_id")
        credits = int(self.planet_row.get("credit_balance", 0) or 0)

        arcade.draw_text(
            f"PLANET DETAIL :: {name.upper()}",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 90,
            COLOR_PRIMARY,
            28,
            anchor_x="center",
            font_name=self.font_ui_bold,
        )

        lines = [
            f"PLANET ID: {int(self.planet_row.get('planet_id', 0) or 0)}",
            f"OWNER ID: {owner if owner is not None else 'NEUTRAL'}",
            f"TREASURY: {credits:,} CR",
            "",
            "[M] MARKET VIEW",
            "[C] START COMBAT (VS OWNER)",
            "[S] STRATEGIC STATUS",
            "[ESC] BACK TO GALAXY",
        ]
        y = SCREEN_HEIGHT - 170
        for line in lines:
            arcade.draw_text(
                line,
                80,
                y,
                COLOR_SECONDARY if line.startswith("[") else COLOR_TEXT_DIM,
                14,
                font_name=self.font_ui,
            )
            y -= 32

        if self.status:
            arcade.draw_text(
                self.status,
                80,
                90,
                COLOR_PRIMARY,
                13,
                font_name=self.font_ui,
            )

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
            from .galaxy_map_view import GalaxyMapView

            self.window.show_view(GalaxyMapView(self.network))
            return
        if key == arcade.key.M:
            self.window.show_view(MarketView(self.network, self.planet_row))
            return
        if key == arcade.key.C:
            self.window.show_view(CombatView(self.network, self.planet_row, self.full_state))
            return
        if key == arcade.key.S:
            from .status_view import StatusView

            self.window.show_view(StatusView(self.network))
