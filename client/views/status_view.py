import arcade

from constants import SCREEN_WIDTH, SCREEN_HEIGHT, COLOR_PRIMARY, COLOR_SECONDARY, COLOR_TEXT_DIM, get_font


class StatusView(arcade.View):
    """Phase-5 commander/system status dashboard."""

    def __init__(self, network):
        super().__init__()
        self.network = network
        self.state = {}
        self.font_ui = get_font("ui")
        self.font_ui_bold = get_font("ui_bold")
        self._refresh_elapsed = 0.0
        self._poll_interval = 0.50
        self._poll_failures = 0
        self._last_state_version = -1

    def on_show_view(self):
        arcade.set_background_color((8, 10, 14))
        self.state = self.network.get_full_state() or {}
        self._last_state_version = int(self.state.get("state_version", 0) or 0)

    def on_update(self, delta_time):
        self._refresh_elapsed += delta_time
        if self._refresh_elapsed >= self._poll_interval:
            self._refresh_elapsed = 0.0
            try:
                fresh_state = self.network.get_full_state() or {}
                incoming_version = int(fresh_state.get("state_version", 0) or 0)
                if incoming_version != int(self._last_state_version):
                    self.state = dict(fresh_state)
                    self._last_state_version = incoming_version
                self._poll_failures = 0
                self._poll_interval = 0.50
            except Exception:
                self._poll_failures += 1
                self._poll_interval = min(1.5, 0.50 + (self._poll_failures * 0.2))

    def on_draw(self):
        self.clear()
        arcade.draw_text(
            "COMMANDER STATUS BOARD",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 80,
            COLOR_PRIMARY,
            28,
            anchor_x="center",
            font_name=self.font_ui_bold,
        )

        players = list(self.state.get("players", []) or [])
        planets = list(self.state.get("planets", []) or [])
        combats = list(self.state.get("combat_sessions", []) or [])

        arcade.draw_text(f"PLAYERS ONLINE SNAPSHOT: {len(players)}", 80, SCREEN_HEIGHT - 150, COLOR_SECONDARY, 14, font_name=self.font_ui)
        arcade.draw_text(f"PLANETS TRACKED: {len(planets)}", 80, SCREEN_HEIGHT - 180, COLOR_SECONDARY, 14, font_name=self.font_ui)
        active_combats = sum(
            1 for row in combats if str(row.get('status', '')) == 'active'
        )
        arcade.draw_text(f"ACTIVE COMBATS: {active_combats}", 80, SCREEN_HEIGHT - 210, COLOR_SECONDARY, 14, font_name=self.font_ui)
        arcade.draw_text(
            f"STATE VERSION: {int(self.state.get('state_version', 0) or 0)}",
            80,
            SCREEN_HEIGHT - 240,
            COLOR_TEXT_DIM,
            12,
            font_name=self.font_ui,
        )

        y = SCREEN_HEIGHT - 290
        arcade.draw_text("PLAYER CREDIT RANKINGS", 80, y, COLOR_PRIMARY, 16, font_name=self.font_ui_bold)
        y -= 30
        sorted_players = sorted(players, key=lambda row: int(row.get("credits", 0) or 0), reverse=True)
        for row in sorted_players[:12]:
            arcade.draw_text(
                f"{str(row.get('name') or '').upper():<16}  CR {int(row.get('credits', 0) or 0):,}",
                80,
                y,
                COLOR_TEXT_DIM,
                13,
                font_name=self.font_ui,
            )
            y -= 24

        arcade.draw_text("[ESC] BACK TO GALAXY", 80, 70, COLOR_TEXT_DIM, 12, font_name=self.font_ui)

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
            from .galaxy_map_view import GalaxyMapView

            self.window.show_view(GalaxyMapView(self.network))
