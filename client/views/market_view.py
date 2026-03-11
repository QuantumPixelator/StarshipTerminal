import arcade

from constants import SCREEN_WIDTH, SCREEN_HEIGHT, COLOR_PRIMARY, COLOR_SECONDARY, COLOR_TEXT_DIM, get_font


RESOURCE_ORDER = ["fuel", "ore", "tech", "bio", "rare"]


class MarketView(arcade.View):
    """Phase-5 strategic market view using process_trade API."""

    def __init__(self, network, planet_row):
        super().__init__()
        self.network = network
        self.planet_row = dict(planet_row or {})
        self.font_ui = get_font("ui")
        self.font_ui_bold = get_font("ui_bold")
        self.selected = 0
        self.qty = 1
        self.status = ""

    def on_show_view(self):
        arcade.set_background_color((10, 14, 18))

    def _active_player_id(self):
        state = self.network.get_full_state() or {}
        players = list(state.get("players", []) or [])
        player_name = str(getattr(getattr(self.network, "player", None), "name", "") or "").strip().lower()
        for row in players:
            if str(row.get("name") or "").strip().lower() == player_name:
                return int(row.get("player_id", 0) or 0)
        return int(players[0].get("player_id", 0) or 0) if players else 0

    def on_draw(self):
        self.clear()
        name = str(self.planet_row.get("name") or "UNKNOWN")
        planet_id = int(self.planet_row.get("planet_id", 0) or 0)
        selected_resource = RESOURCE_ORDER[self.selected]

        arcade.draw_text(
            f"MARKET :: {name.upper()} (ID {planet_id})",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 80,
            COLOR_PRIMARY,
            26,
            anchor_x="center",
            font_name=self.font_ui_bold,
        )

        y = SCREEN_HEIGHT - 170
        for idx, resource in enumerate(RESOURCE_ORDER):
            prefix = ">" if idx == self.selected else " "
            arcade.draw_text(
                f"{prefix} {resource.upper()}",
                120,
                y,
                COLOR_SECONDARY if idx == self.selected else COLOR_TEXT_DIM,
                15,
                font_name=self.font_ui,
            )
            y -= 34

        arcade.draw_text(
            f"QTY: {self.qty}",
            420,
            SCREEN_HEIGHT - 190,
            COLOR_SECONDARY,
            16,
            font_name=self.font_ui_bold,
        )
        arcade.draw_text(
            "[UP/DOWN] SELECT RESOURCE  [LEFT/RIGHT] QTY",
            420,
            SCREEN_HEIGHT - 230,
            COLOR_TEXT_DIM,
            12,
            font_name=self.font_ui,
        )
        arcade.draw_text(
            "[B] BUY  [V] SELL  [ESC] BACK",
            420,
            SCREEN_HEIGHT - 260,
            COLOR_TEXT_DIM,
            12,
            font_name=self.font_ui,
        )

        if self.status:
            arcade.draw_text(self.status, 120, 90, COLOR_PRIMARY, 13, font_name=self.font_ui)

        arcade.draw_text(
            f"SELECTED: {selected_resource.upper()}",
            120,
            140,
            COLOR_SECONDARY,
            14,
            font_name=self.font_ui_bold,
        )

    def _do_trade(self, buy):
        player_id = self._active_player_id()
        planet_id = int(self.planet_row.get("planet_id", 0) or 0)
        item = RESOURCE_ORDER[self.selected]
        if player_id <= 0 or planet_id <= 0:
            self.status = "TRADE FAILED: INVALID PLAYER/PLANET CONTEXT."
            return
        result = self.network.process_trade(player_id, planet_id, item, int(self.qty), bool(buy))
        self.status = str(result.get("message") or "").upper()

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
            from .planet_detail_view import PlanetDetailView

            self.window.show_view(PlanetDetailView(self.network, self.planet_row, self.network.get_full_state() or {}))
            return
        if key in (arcade.key.UP, arcade.key.W):
            self.selected = (self.selected - 1) % len(RESOURCE_ORDER)
            return
        if key in (arcade.key.DOWN, arcade.key.S):
            self.selected = (self.selected + 1) % len(RESOURCE_ORDER)
            return
        if key in (arcade.key.LEFT, arcade.key.A):
            self.qty = max(1, int(self.qty) - 1)
            return
        if key in (arcade.key.RIGHT, arcade.key.D):
            self.qty = min(999, int(self.qty) + 1)
            return
        if key == arcade.key.B:
            self._do_trade(True)
            return
        if key == arcade.key.V:
            self._do_trade(False)
