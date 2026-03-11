"""
TimedPopupView — auto-dismissing message overlay for Starship Terminal.
Used for brief sector alerts and travel arrival messages.
"""

import arcade
import textwrap
from constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    COLOR_PRIMARY, COLOR_SECONDARY, COLOR_TEXT_DIM,
    COLOR_BG,
    get_font,
)


class TimedPopupView(arcade.View):
    """
    Full-screen overlay that displays a message for a set duration,
    then returns to the previous view (or calls an on_complete callback).
    """

    def __init__(
        self,
        return_view,
        message,
        duration=3.0,
        accent_color=COLOR_PRIMARY,
        on_complete=None,
    ):
        super().__init__()
        self.return_view = return_view
        self.message = str(message or "")
        self.duration = max(0.8, float(duration))
        self.time_left = float(self.duration)
        self.accent_color = accent_color
        self.on_complete = on_complete
        self.font_ui = get_font("ui")
        self.font_ui_bold = get_font("ui_bold")
        self._finished = False

    def _finish(self):
        if self._finished:
            return
        self._finished = True
        if callable(self.on_complete):
            self.on_complete()
            if self.window and self.return_view and self.window.current_view is self:
                self.window.show_view(self.return_view)
        elif self.window and self.return_view:
            self.window.show_view(self.return_view)

    def on_update(self, delta_time):
        self.time_left = max(0.0, float(self.time_left) - float(delta_time))
        if self.time_left <= 0.0:
            self._finish()

    def on_key_press(self, key, modifiers):
        return

    def on_mouse_press(self, x, y, button, modifiers):
        return

    def _is_commander_response_line(self, line):
        normalized = str(line or "").upper().strip()
        return (
            " RESPONSE:" in normalized
            or normalized.startswith("COMMANDER ")
            or normalized.startswith("CMDR ")
        )

    def on_draw(self):
        self.clear()

        LINE_H = 22
        _raw_lines = [ln.strip() for ln in str(self.message).splitlines() if ln.strip()]
        if not _raw_lines:
            _raw_lines = [" ".join(str(self.message).split())]
        lines: list[str] = []
        for _rl in _raw_lines:
            _wrapped = textwrap.wrap(
                _rl, width=74, break_long_words=True, break_on_hyphens=True
            )
            lines.extend(_wrapped or [_rl])
        lines = lines[:10]  # Hard cap at 10 visible lines

        HEADER_CHROME = 92
        FOOTER_CHROME = 78
        body_h = max(LINE_H + 8, len(lines) * LINE_H + 8)
        box_h = HEADER_CHROME + body_h + FOOTER_CHROME
        box_h = max(230, min(box_h, SCREEN_HEIGHT - 80))
        box_w = 980

        bx = SCREEN_WIDTH // 2 - box_w // 2
        by = SCREEN_HEIGHT // 2 - box_h // 2
        body_top = by + box_h - HEADER_CHROME
        timer_y = by + 36

        arcade.draw_lbwh_rectangle_filled(
            0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 195)
        )
        arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (10, 16, 26, 248))
        arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, self.accent_color, 2)

        arcade.Text(
            "SECTOR ALERT",
            SCREEN_WIDTH // 2,
            by + box_h - 50,
            self.accent_color,
            28,
            anchor_x="center",
            font_name=self.font_ui_bold,
        ).draw()

        response_mode = False
        for idx, line in enumerate(lines):
            if self._is_commander_response_line(line):
                response_mode = True
            line_color = COLOR_SECONDARY if response_mode else COLOR_PRIMARY
            arcade.Text(
                line,
                bx + 32,
                body_top - (idx * LINE_H),
                line_color,
                15,
                width=box_w - 64,
                font_name=self.font_ui,
            ).draw()

        arcade.Text(
            f"RESUMING IN {max(0.0, self.time_left):.1f}s",
            SCREEN_WIDTH // 2,
            timer_y,
            COLOR_TEXT_DIM,
            12,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()
