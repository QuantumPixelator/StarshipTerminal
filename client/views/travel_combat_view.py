"""
TravelCombatView — pirate combat encounter during warp travel.
Shows combat resolution and a summary before returning to the travel chain.
"""

import arcade
import textwrap
from constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    COLOR_PRIMARY, COLOR_SECONDARY, COLOR_ACCENT,
    COLOR_BG, COLOR_TEXT_DIM,
    get_font,
)
from .effects_orchestrator import trigger_effect, draw_effects


class TravelCombatView(arcade.View):
    """
    Full-screen combat overlay triggered when PIRATES event selects FIGHT.
    Resolves the engagement via the network and displays results before
    invoking continue_callback to resume the travel chain.
    """

    def __init__(self, game_manager, event_payload, continue_callback):
        super().__init__()
        self.network = game_manager
        self.payload = dict(event_payload or {})
        self.continue_callback = continue_callback
        self.font_ui = get_font("ui")
        self.font_ui_bold = get_font("ui_bold")
        self.resolved = False
        self.result_line = ""
        self.combat_log_line = "PIRATE SQUADRON INTERCEPTED. READY TO ENGAGE."

    def _wrap_combat_text(self, text, max_chars, max_lines):
        normalized = " ".join(str(text or "").split())
        if not normalized:
            return []
        lines = textwrap.wrap(
            normalized,
            width=max(12, int(max_chars)),
            break_long_words=True,
            break_on_hyphens=True,
        )
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip(" .") + "..."
        return lines

    def on_show(self):
        arcade.set_background_color(COLOR_BG)

    def _resolve_combat(self):
        if self.resolved:
            return
        self.result_line = str(
            self.network.resolve_travel_event_payload(self.payload, choice="FIGHT")
        )
        self.combat_log_line = "COMBAT RESOLVED. REVIEW OUTCOME AND CONTINUE TRANSIT."
        self.resolved = True
        # Trigger simple effects based on outcome text
        try:
            rl = str(self.result_line or "").upper()
            if "VICTORY" in rl or "WIN" in rl:
                trigger_effect('combat', 'combat_victory', (SCREEN_WIDTH//2, SCREEN_HEIGHT//2), 1.2)
            elif "DEFEAT" in rl or "LOSS" in rl:
                trigger_effect('combat', 'combat_defeat', (SCREEN_WIDTH//2, SCREEN_HEIGHT//2), 1.1)
            else:
                # generic resolved UI confirm
                trigger_effect('ui', 'confirm', (SCREEN_WIDTH//2, SCREEN_HEIGHT//2), 0.8)
        except Exception:
            pass

    def _continue_travel(self):
        if not self.resolved:
            return
        if callable(self.continue_callback):
            self.continue_callback(self.result_line)

    def on_key_press(self, key, modifiers):
        if key in (
            arcade.key.ENTER,
            arcade.key.RETURN,
            arcade.key.SPACE,
            arcade.key.ESCAPE,
        ):
            if self.resolved:
                self._continue_travel()
            else:
                self._resolve_combat()

    def on_mouse_press(self, x, y, button, modifiers):
        box_w, box_h = 920, 470
        by = SCREEN_HEIGHT // 2 - box_h // 2
        btn_w, btn_h = 220, 48
        btn_x = SCREEN_WIDTH // 2 - btn_w // 2
        btn_y = by + 64
        if btn_x <= x <= btn_x + btn_w and btn_y <= y <= btn_y + btn_h:
            if self.resolved:
                self._continue_travel()
            else:
                self._resolve_combat()

    def on_draw(self):
        self.clear()
        box_w, box_h = 920, 470
        bx = SCREEN_WIDTH // 2 - box_w // 2
        by = SCREEN_HEIGHT // 2 - box_h // 2

        title_y = by + box_h - 64
        subtitle_y = by + box_h - 110
        detail_top_y = by + box_h - 168
        detail_bottom_y = by + 292
        summary_x, summary_y, summary_w, summary_h = bx + 42, by + 128, box_w - 84, 140
        button_y = by + 64
        footer_y = by + 36

        arcade.draw_lbwh_rectangle_filled(
            0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 180)
        )
        arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (9, 14, 24, 245))
        arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_ACCENT, 2)

        arcade.Text(
            "IN-FLIGHT COMBAT",
            SCREEN_WIDTH // 2,
            title_y,
            COLOR_ACCENT,
            32,
            anchor_x="center",
            font_name=self.font_ui_bold,
        ).draw()
        arcade.Text(
            "PIRATE BLOCKADE ENGAGEMENT",
            SCREEN_WIDTH // 2,
            subtitle_y,
            COLOR_SECONDARY,
            18,
            anchor_x="center",
            font_name=self.font_ui_bold,
        ).draw()

        detail_lines = self._wrap_combat_text(
            self.combat_log_line,
            max_chars=84,
            max_lines=max(1, int((detail_top_y - detail_bottom_y) // 24)),
        )
        if detail_lines:
            arcade.Text(
                "\n".join(detail_lines),
                bx + 48,
                detail_top_y,
                COLOR_TEXT_DIM,
                15,
                width=box_w - 96,
                multiline=True,
                font_name=self.font_ui,
            ).draw()

        arcade.draw_lbwh_rectangle_filled(
            summary_x, summary_y, summary_w, summary_h, (8, 20, 16, 238)
        )
        arcade.draw_lbwh_rectangle_outline(
            summary_x, summary_y, summary_w, summary_h, COLOR_PRIMARY, 1
        )
        arcade.Text(
            "COMBAT SUMMARY",
            summary_x + 12,
            summary_y + summary_h - 24,
            COLOR_PRIMARY,
            13,
            font_name=self.font_ui_bold,
        ).draw()

        summary_text = (
            self.result_line if self.result_line else "Awaiting combat resolution..."
        )
        summary_lines = self._wrap_combat_text(
            f"OUTCOME: {summary_text}",
            max_chars=80,
            max_lines=max(1, int((summary_h - 40) // 20)),
        )
        arcade.Text(
            "\n".join(summary_lines),
            summary_x + 12,
            summary_y + summary_h - 46,
            COLOR_PRIMARY if self.result_line else COLOR_TEXT_DIM,
            13,
            width=summary_w - 24,
            multiline=True,
            font_name=self.font_ui_bold if self.result_line else self.font_ui,
        ).draw()

        btn_w, btn_h = 220, 48
        btn_x = SCREEN_WIDTH // 2 - btn_w // 2
        btn_label = "CONTINUE" if self.resolved else "ENGAGE"
        btn_color = COLOR_PRIMARY if self.resolved else COLOR_ACCENT
        arcade.draw_lbwh_rectangle_filled(
            btn_x, button_y, btn_w, btn_h, (*btn_color, 210)
        )
        arcade.draw_lbwh_rectangle_outline(
            btn_x, button_y, btn_w, btn_h, COLOR_PRIMARY, 2
        )
        arcade.Text(
            btn_label,
            btn_x + btn_w // 2,
            button_y + btn_h // 2,
            COLOR_BG,
            15,
            anchor_x="center",
            anchor_y="center",
            font_name=self.font_ui_bold,
        ).draw()

        footer = (
            "PRESS ENTER/SPACE OR CLICK TO CONTINUE"
            if self.resolved
            else "PRESS ENTER/SPACE OR CLICK TO ENGAGE"
        )
        arcade.Text(
            footer,
            SCREEN_WIDTH // 2,
            footer_y,
            COLOR_TEXT_DIM,
            12,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()

        # Draw global effects on top
        try:
            draw_effects()
        except Exception:
            pass
