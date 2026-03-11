"""
AnalyticsView — in-game analytics/admin dashboard.

Displays server analytics summary, top events, and balancing recommendations.
Supports refresh and reset controls for admin use.
"""

import time
import arcade
from constants import (
    SCREEN_WIDTH,
    SCREEN_HEIGHT,
    COLOR_PRIMARY,
    COLOR_SECONDARY,
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_TEXT_DIM,
    get_font,
)

COLOR_TEXT = COLOR_PRIMARY


class AnalyticsView(arcade.View):
    """Lightweight in-game analytics dashboard."""

    def __init__(self, game_manager, return_view):
        super().__init__()
        self.network = game_manager
        self.return_view = return_view

        self.font_ui = get_font("ui")
        self.font_ui_bold = get_font("ui_bold")

        self.window_options = [24, 72, 168]
        self.window_index = 0

        self.summary = {}
        self.recommendations = {}
        self.events = []

        self.message = ""
        self.message_color = COLOR_TEXT_DIM
        self.last_refresh_ts = 0.0
        self.reset_armed = False

    @property
    def selected_window_hours(self):
        return int(self.window_options[self.window_index])

    def on_show_view(self):
        self.refresh_data()

    def refresh_data(self):
        """Fetch summary/events/recommendations from server."""
        try:
            wh = self.selected_window_hours
            self.summary = self.network.get_analytics_summary(window_hours=wh) or {}
            self.recommendations = (
                self.network.get_analytics_recommendations(window_hours=wh) or {}
            )
            self.events = self.network.get_analytics_events(limit=12) or []
            self.last_refresh_ts = time.time()
            self.message = f"REFRESHED ({wh}H WINDOW)."
            self.message_color = COLOR_PRIMARY
            self.reset_armed = False
        except Exception as exc:
            self.message = f"ANALYTICS FETCH FAILED: {str(exc).upper()}"
            self.message_color = COLOR_ACCENT

    def _format_ts(self, ts):
        try:
            return time.strftime("%H:%M:%S", time.localtime(float(ts)))
        except Exception:
            return "--:--:--"

    def on_key_press(self, key, modifiers):
        if key in (arcade.key.ESCAPE, arcade.key.B):
            self.window.show_view(self.return_view)
            return

        if key in (arcade.key.R, arcade.key.F5):
            self.refresh_data()
            return

        if key == arcade.key.C:
            self.window_index = (self.window_index + 1) % len(self.window_options)
            self.refresh_data()
            return

        if key == arcade.key.X:
            if not self.reset_armed:
                self.reset_armed = True
                self.message = "PRESS X AGAIN TO CONFIRM ANALYTICS RESET."
                self.message_color = COLOR_ACCENT
                return
            success, msg = self.network.reset_analytics()
            self.message = str(msg or "").upper()
            self.message_color = COLOR_PRIMARY if success else COLOR_ACCENT
            self.reset_armed = False
            self.refresh_data()
            return

        if key in (arcade.key.KEY_1, arcade.key.NUM_1):
            self.window_index = 0
            self.refresh_data()
        elif key in (arcade.key.KEY_2, arcade.key.NUM_2):
            if len(self.window_options) > 1:
                self.window_index = 1
                self.refresh_data()
        elif key in (arcade.key.KEY_3, arcade.key.NUM_3):
            if len(self.window_options) > 2:
                self.window_index = 2
                self.refresh_data()

    def on_draw(self):
        self.clear()
        arcade.set_background_color(COLOR_BG)

        arcade.Text(
            "ANALYTICS DASHBOARD",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 44,
            COLOR_PRIMARY,
            26,
            anchor_x="center",
            font_name=self.font_ui_bold,
        ).draw()

        subtitle = (
            "[R/F5] REFRESH  [C] CYCLE WINDOW  [X] RESET ANALYTICS  "
            "[1/2/3] WINDOW  [ESC/B] BACK"
        )
        arcade.Text(
            subtitle,
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 75,
            COLOR_TEXT_DIM,
            12,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()

        arcade.draw_lbwh_rectangle_outline(30, 110, SCREEN_WIDTH - 60, SCREEN_HEIGHT - 220, COLOR_SECONDARY, 2)

        summary = self.summary or {}
        rec_data = self.recommendations or {}

        left_x = 50
        right_x = SCREEN_WIDTH // 2 + 20
        top_y = SCREEN_HEIGHT - 120

        arcade.Text(
            f"WINDOW: {self.selected_window_hours}H",
            left_x,
            top_y,
            COLOR_SECONDARY,
            14,
            font_name=self.font_ui_bold,
        ).draw()
        arcade.Text(
            f"EVENTS: {int(summary.get('events_in_window', 0))}",
            left_x,
            top_y - 26,
            COLOR_TEXT,
            13,
            font_name=self.font_ui,
        ).draw()
        arcade.Text(
            f"SUCCESS: {int(summary.get('success_count', 0))}   FAILURE: {int(summary.get('failure_count', 0))}",
            left_x,
            top_y - 50,
            COLOR_TEXT,
            13,
            font_name=self.font_ui,
        ).draw()
        arcade.Text(
            f"SUCCESS RATE: {float(summary.get('success_rate', 0.0)) * 100:.1f}%",
            left_x,
            top_y - 74,
            COLOR_TEXT,
            13,
            font_name=self.font_ui,
        ).draw()

        arcade.Text(
            "TOP EVENTS",
            left_x,
            top_y - 112,
            COLOR_SECONDARY,
            13,
            font_name=self.font_ui_bold,
        ).draw()
        y = top_y - 136
        for event in list(summary.get("top_events", []) or [])[:8]:
            name = str(event.get("name", "unknown"))
            count = int(event.get("count", 0))
            arcade.Text(
                f"- {name}: {count}",
                left_x,
                y,
                COLOR_TEXT_DIM,
                12,
                font_name=self.font_ui,
            ).draw()
            y -= 20

        arcade.Text(
            "RECOMMENDATIONS",
            right_x,
            top_y,
            COLOR_SECONDARY,
            13,
            font_name=self.font_ui_bold,
        ).draw()
        y = top_y - 24
        for rec in list(rec_data.get("recommendations", []) or [])[:6]:
            text = str(rec)
            wrapped = []
            remaining = text
            while len(remaining) > 58:
                cut = remaining.rfind(" ", 0, 58)
                if cut <= 0:
                    cut = 58
                wrapped.append(remaining[:cut])
                remaining = remaining[cut:].strip()
            if remaining:
                wrapped.append(remaining)

            for idx, line in enumerate(wrapped[:3]):
                prefix = "- " if idx == 0 else "  "
                arcade.Text(
                    f"{prefix}{line}",
                    right_x,
                    y,
                    COLOR_TEXT,
                    12,
                    font_name=self.font_ui,
                ).draw()
                y -= 18
            y -= 8

        arcade.Text(
            "RECENT EVENTS",
            right_x,
            SCREEN_HEIGHT // 2 - 40,
            COLOR_SECONDARY,
            13,
            font_name=self.font_ui_bold,
        ).draw()
        y = SCREEN_HEIGHT // 2 - 64
        for evt in list(self.events or [])[-8:][::-1]:
            t = self._format_ts(evt.get("ts", 0))
            cat = str(evt.get("category", "?"))
            name = str(evt.get("name", "?"))
            ok = "OK" if bool(evt.get("success", False)) else "FAIL"
            color = COLOR_PRIMARY if ok == "OK" else COLOR_ACCENT
            arcade.Text(
                f"[{t}] {cat}/{name} {ok}",
                right_x,
                y,
                color,
                11,
                font_name=self.font_ui,
            ).draw()
            y -= 18

        refresh_text = "NEVER" if self.last_refresh_ts <= 0 else self._format_ts(self.last_refresh_ts)
        arcade.Text(
            f"LAST REFRESH: {refresh_text}",
            40,
            72,
            COLOR_TEXT_DIM,
            11,
            font_name=self.font_ui,
        ).draw()
        arcade.Text(
            self.message,
            40,
            44,
            self.message_color,
            12,
            font_name=self.font_ui,
        ).draw()
