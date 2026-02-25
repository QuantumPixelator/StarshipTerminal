"""
TravelEventView — in-transit event encounter screen for Starship Terminal.
Handles CACHE, DRIFT, LEAK, PIRATES and other mid-jump events.
"""

import arcade
import textwrap
from constants import (
    SCREEN_WIDTH, SCREEN_HEIGHT,
    COLOR_PRIMARY, COLOR_SECONDARY, COLOR_ACCENT,
    COLOR_BG, COLOR_TEXT_DIM,
    get_font,
)


class TravelEventView(arcade.View):
    """
    Interactive event overlay shown when a travel event fires mid-warp.
    Player selects a response (PAY, SALVAGE, FIGHT, IGNORE, etc.) and
    the continue_callback is invoked to resume travel.
    """

    def __init__(self, game_manager, event_payload, continue_callback):
        super().__init__()
        self.network = game_manager
        self.payload = dict(event_payload or {})
        self.continue_callback = continue_callback
        self.font_ui = get_font("ui")
        self.font_ui_bold = get_font("ui_bold")
        choices = [str(c).upper() for c in self.payload.get("choices", [])]
        self.choice_options = choices if choices else ["CONTINUE"]
        self.choice_index = 0
        if "PAY" in self.choice_options:
            self.choice_index = self.choice_options.index("PAY")
        elif "SECURE" in self.choice_options:
            self.choice_index = self.choice_options.index("SECURE")
        elif "SALVAGE" in self.choice_options:
            self.choice_index = self.choice_options.index("SALVAGE")
        elif "PATCH" in self.choice_options:
            self.choice_index = self.choice_options.index("PATCH")

        # Cargo-full sub-mode
        self.cargo_full_mode = False
        self.cargo_drop_index = 0
        self.cargo_items_list: list[tuple[str, int]] = []
        self.cargo_full_status = ""

        self.event_sound = self._load_event_sound()
        self.event_sound_played = False

    def _wrap_event_text(self, text, max_chars, max_lines):
        normalized = " ".join(str(text or "").split())
        if not normalized:
            return []
        lines = textwrap.wrap(
            normalized,
            width=max(10, int(max_chars)),
            break_long_words=True,
            break_on_hyphens=True,
        )
        if len(lines) > max_lines:
            lines = lines[:max_lines]
            lines[-1] = lines[-1].rstrip(" .") + "..."
        return lines

    def _is_commander_response_line(self, line):
        normalized = str(line or "").upper()
        return (
            " RESPONSE:" in normalized
            or normalized.startswith("COMMANDER ")
            or normalized.startswith("CMDR ")
        )

    def _load_event_sound(self):
        event_type = str(self.payload.get("type", "")).upper()
        sound_path = {
            "CACHE": ":resources:sounds/upgrade5.wav",
            "DRIFT": ":resources:sounds/coin1.wav",
            "LEAK": ":resources:sounds/jump1.wav",
            "PIRATES": ":resources:sounds/hit5.wav",
        }.get(event_type, ":resources:sounds/jump1.wav")
        try:
            return arcade.load_sound(sound_path)
        except Exception:
            return None

    def on_show(self):
        arcade.set_background_color(COLOR_BG)
        if not bool(self.network.config.get("audio_enabled", True)):
            return
        if self.event_sound_played or not self.event_sound:
            return
        try:
            volume = max(
                0.0, min(1.0, float(self.network.config.get("audio_ui_volume", 0.70)))
            )
            arcade.play_sound(self.event_sound, volume=volume)
            self.event_sound_played = True
        except Exception:
            return

    def _continue_travel(self):
        selected = self.choice_options[self.choice_index]
        event_type = str(self.payload.get("type", "")).upper()

        if event_type == "DRIFT" and selected == "SALVAGE":
            ship = self.network.player.spaceship
            cargo_used = sum(self.network.player.inventory.values())
            cargo_max = int(ship.current_cargo_pods)
            if cargo_used >= cargo_max:
                self._enter_cargo_full_mode()
                return

        if event_type == "PIRATES" and selected == "FIGHT":
            from views.travel_combat_view import TravelCombatView  # lazy
            self.window.show_view(
                TravelCombatView(
                    self.network, self.payload, continue_callback=self.continue_callback
                )
            )
            return
        result_line = self.network.resolve_travel_event_payload(self.payload, selected)
        if callable(self.continue_callback):
            self.continue_callback(result_line)

    def _enter_cargo_full_mode(self):
        """Activate the cargo-full sub-mode so the player can drop an item or skip."""
        inv = dict(self.network.player.inventory or {})
        self.cargo_items_list = sorted(inv.items())
        self.cargo_drop_index = 0
        self.cargo_full_status = ""
        self.cargo_full_mode = True

    def _handle_drop_cargo(self):
        """Jettison 1 unit of the selected cargo item, then retry salvage."""
        if not self.cargo_items_list:
            self.cargo_full_mode = False
            return
        item_name, _ = self.cargo_items_list[self.cargo_drop_index]
        ok, msg = self.network.jettison_cargo(item_name)
        if not ok:
            self.cargo_full_status = msg or "Drop failed."
            return
        inv = dict(self.network.player.inventory or {})
        self.cargo_items_list = sorted(inv.items())
        if self.cargo_items_list:
            self.cargo_drop_index = min(
                self.cargo_drop_index, len(self.cargo_items_list) - 1
            )
        ship = self.network.player.spaceship
        cargo_used = sum(self.network.player.inventory.values())
        cargo_max = int(ship.current_cargo_pods)
        if cargo_used < cargo_max:
            self.cargo_full_mode = False
            result_line = self.network.resolve_travel_event_payload(
                self.payload, "SALVAGE"
            )
            if callable(self.continue_callback):
                self.continue_callback(result_line)
        else:
            self.cargo_full_status = (
                f"Dropped {item_name}. Still full — drop another or skip."
            )

    def _handle_skip_salvage(self):
        self.cargo_full_mode = False
        result_line = self.network.resolve_travel_event_payload(self.payload, "IGNORE")
        if callable(self.continue_callback):
            self.continue_callback(result_line)

    def _draw_cargo_full_mode(self):
        """Render the cargo-full prompt."""
        box_w, box_h = 900, 430
        bx = SCREEN_WIDTH // 2 - box_w // 2
        by = SCREEN_HEIGHT // 2 - box_h // 2

        arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (10, 16, 26, 245))
        arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_ACCENT, 2)

        arcade.Text(
            "CARGO HOLD FULL",
            SCREEN_WIDTH // 2,
            by + box_h - 60,
            COLOR_ACCENT,
            28,
            anchor_x="center",
            font_name=self.font_ui_bold,
        ).draw()

        drift_item = str(self.payload.get("drift_item", "item")).upper()
        arcade.Text(
            f"NOT ENOUGH SPACE TO SALVAGE: {drift_item}",
            SCREEN_WIDTH // 2,
            by + box_h - 100,
            COLOR_PRIMARY,
            16,
            anchor_x="center",
            font_name=self.font_ui_bold,
        ).draw()
        arcade.Text(
            "SELECT A CARGO ITEM TO DROP (1 UNIT), OR SKIP THE SALVAGE",
            SCREEN_WIDTH // 2,
            by + box_h - 126,
            COLOR_TEXT_DIM,
            12,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()

        list_x = bx + 40
        list_y = by + box_h - 158
        row_h = 28
        ship = self.network.player.spaceship
        cargo_used = sum(self.network.player.inventory.values())
        cargo_max = int(ship.current_cargo_pods)
        arcade.Text(
            f"CARGO: {cargo_used}/{cargo_max}",
            list_x,
            list_y + 4,
            COLOR_TEXT_DIM,
            11,
            font_name=self.font_ui,
        ).draw()
        list_y -= row_h + 4

        for i, (name, qty) in enumerate(self.cargo_items_list):
            is_sel = i == self.cargo_drop_index
            row_y = list_y - i * row_h
            if row_y < by + 120:
                break
            if is_sel:
                arcade.draw_lbwh_rectangle_filled(
                    list_x - 6, row_y - 4, box_w - 80, row_h - 2, (*COLOR_ACCENT, 60)
                )
            color = COLOR_ACCENT if is_sel else COLOR_TEXT_DIM
            tag = "► " if is_sel else "  "
            arcade.Text(
                f"{tag}{name.upper()}: {qty} UNIT{'S' if qty > 1 else ''}",
                list_x,
                row_y,
                color,
                14,
                font_name=self.font_ui,
            ).draw()

        if self.cargo_full_status:
            arcade.Text(
                self.cargo_full_status.upper(),
                SCREEN_WIDTH // 2,
                by + 120,
                COLOR_SECONDARY,
                12,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

        btn_w, btn_h = 200, 44
        gap = 24
        total = 2 * btn_w + gap
        bx1 = SCREEN_WIDTH // 2 - total // 2
        bx2 = bx1 + btn_w + gap
        btn_y = by + 64

        arcade.draw_lbwh_rectangle_filled(
            bx1, btn_y, btn_w, btn_h, (*COLOR_ACCENT, 200)
        )
        arcade.draw_lbwh_rectangle_outline(bx1, btn_y, btn_w, btn_h, COLOR_ACCENT, 2)
        arcade.Text(
            "DROP 1 UNIT",
            bx1 + btn_w // 2,
            btn_y + btn_h // 2,
            COLOR_BG,
            14,
            anchor_x="center",
            anchor_y="center",
            font_name=self.font_ui_bold,
        ).draw()

        arcade.draw_lbwh_rectangle_filled(
            bx2, btn_y, btn_w, btn_h, (*COLOR_TEXT_DIM, 150)
        )
        arcade.draw_lbwh_rectangle_outline(bx2, btn_y, btn_w, btn_h, COLOR_TEXT_DIM, 2)
        arcade.Text(
            "SKIP SALVAGE",
            bx2 + btn_w // 2,
            btn_y + btn_h // 2,
            COLOR_BG,
            14,
            anchor_x="center",
            anchor_y="center",
            font_name=self.font_ui_bold,
        ).draw()

        arcade.Text(
            "[UP/DOWN] SELECT | [ENTER/D] DROP | [S/ESC] SKIP",
            SCREEN_WIDTH // 2,
            by + 30,
            COLOR_TEXT_DIM,
            11,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()

    def on_key_press(self, key, modifiers):
        if self.cargo_full_mode:
            if key in (arcade.key.UP, arcade.key.W):
                if self.cargo_items_list:
                    self.cargo_drop_index = (self.cargo_drop_index - 1) % len(
                        self.cargo_items_list
                    )
            elif key in (arcade.key.DOWN, arcade.key.S, arcade.key.ESCAPE):
                if key == arcade.key.ESCAPE or key == arcade.key.S:
                    self._handle_skip_salvage()
                else:
                    if self.cargo_items_list:
                        self.cargo_drop_index = (self.cargo_drop_index + 1) % len(
                            self.cargo_items_list
                        )
            elif key in (
                arcade.key.ENTER,
                arcade.key.RETURN,
                arcade.key.SPACE,
                arcade.key.D,
            ):
                self._handle_drop_cargo()
            return

        if key in (arcade.key.LEFT, arcade.key.A, arcade.key.UP, arcade.key.W):
            self.choice_index = (self.choice_index - 1) % len(self.choice_options)
            return
        if key in (arcade.key.RIGHT, arcade.key.D, arcade.key.DOWN, arcade.key.S):
            self.choice_index = (self.choice_index + 1) % len(self.choice_options)
            return
        for idx, option in enumerate(self.choice_options):
            first_char = str(option).strip()[:1].upper()
            if first_char and key == ord(first_char):
                self.choice_index = idx
                return
        if key in (
            arcade.key.ENTER,
            arcade.key.RETURN,
            arcade.key.SPACE,
            arcade.key.ESCAPE,
        ):
            self._continue_travel()

    def on_mouse_press(self, x, y, button, modifiers):
        box_w, box_h = 900, 430
        by = SCREEN_HEIGHT // 2 - box_h // 2

        if self.cargo_full_mode:
            btn_w, btn_h = 200, 44
            gap = 24
            total = 2 * btn_w + gap
            bx1 = SCREEN_WIDTH // 2 - total // 2
            bx2 = bx1 + btn_w + gap
            btn_y = by + 64
            if bx1 <= x <= bx1 + btn_w and btn_y <= y <= btn_y + btn_h:
                self._handle_drop_cargo()
            elif bx2 <= x <= bx2 + btn_w and btn_y <= y <= btn_y + btn_h:
                self._handle_skip_salvage()
            else:
                list_y = by + box_h - 190
                row_h = 28
                for i in range(len(self.cargo_items_list)):
                    row_y = list_y - i * row_h
                    if row_y < by + 120:
                        break
                    if by + 120 <= y <= row_y + row_h:
                        self.cargo_drop_index = i
                        break
            return

        btn_y = by + 78
        btn_w, btn_h = 180, 44
        start_x = (
            SCREEN_WIDTH // 2
            - (
                (len(self.choice_options) * btn_w)
                + ((len(self.choice_options) - 1) * 24)
            )
            // 2
        )
        for i in range(len(self.choice_options)):
            x1 = start_x + i * (btn_w + 24)
            if x1 <= x <= x1 + btn_w and btn_y <= y <= btn_y + btn_h:
                self.choice_index = i
                self._continue_travel()
                return

    def on_draw(self):
        self.clear()
        arcade.draw_lbwh_rectangle_filled(
            0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 180)
        )

        if self.cargo_full_mode:
            self._draw_cargo_full_mode()
            return

        box_w, box_h = 900, 430
        bx = SCREEN_WIDTH // 2 - box_w // 2
        by = SCREEN_HEIGHT // 2 - box_h // 2

        title_y = by + box_h - 110
        detail_top_y = by + box_h - 180
        detail_bottom_y = by + 224
        outcome_y = by + 176
        hint_y = by + 146
        btn_y = by + 78
        footer_y = by + 42
        btn_w, btn_h = 180, 44
        total_w = (len(self.choice_options) * btn_w) + (
            (len(self.choice_options) - 1) * 24
        )
        start_x = SCREEN_WIDTH // 2 - total_w // 2

        arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (10, 16, 26, 245))
        arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_SECONDARY, 2)

        title = str(self.payload.get("title", "IN-TRANSIT EVENT")).upper()
        detail = str(
            self.payload.get("detail", "Unexpected activity detected during warp.")
        )
        outcome = str(self.payload.get("arrival_line", "")).upper()

        arcade.Text(
            "WARP INTERRUPTED",
            SCREEN_WIDTH // 2,
            by + box_h - 62,
            COLOR_SECONDARY,
            30,
            anchor_x="center",
            font_name=self.font_ui_bold,
        ).draw()
        arcade.Text(
            title,
            SCREEN_WIDTH // 2,
            title_y,
            COLOR_PRIMARY,
            20,
            anchor_x="center",
            font_name=self.font_ui_bold,
        ).draw()

        detail_max_lines = max(1, int((detail_top_y - detail_bottom_y) // 24))
        detail_lines = self._wrap_event_text(
            detail, max_chars=78, max_lines=detail_max_lines
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

        shortcut_hints = " | ".join(
            [f"[{str(opt)[:1].upper()}] {opt}" for opt in self.choice_options]
        )
        arcade.Text(
            shortcut_hints,
            SCREEN_WIDTH // 2,
            hint_y,
            COLOR_TEXT_DIM,
            11,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()

        if outcome:
            outcome_lines = self._wrap_event_text(
                f"OUTCOME: {outcome}", max_chars=82, max_lines=2
            )
            response_mode = False
            for idx, line in enumerate(outcome_lines):
                if self._is_commander_response_line(line):
                    response_mode = True
                line_color = COLOR_SECONDARY if response_mode else COLOR_PRIMARY
                arcade.Text(
                    line,
                    bx + 48,
                    outcome_y - (idx * 18),
                    line_color,
                    14,
                    width=box_w - 96,
                    font_name=self.font_ui_bold,
                ).draw()

        for i, option in enumerate(self.choice_options):
            x1 = start_x + i * (btn_w + 24)
            is_sel = i == self.choice_index
            btn_color = COLOR_PRIMARY if is_sel else COLOR_SECONDARY
            arcade.draw_lbwh_rectangle_filled(
                x1, btn_y, btn_w, btn_h, (*btn_color, 210 if is_sel else 120)
            )
            arcade.draw_lbwh_rectangle_outline(
                x1, btn_y, btn_w, btn_h, COLOR_PRIMARY, 2
            )
            arcade.Text(
                option,
                x1 + btn_w // 2,
                btn_y + btn_h // 2,
                COLOR_BG if is_sel else COLOR_TEXT_DIM,
                14,
                anchor_x="center",
                anchor_y="center",
                font_name=self.font_ui_bold,
            ).draw()

        arcade.Text(
            "SELECT ACTION (ARROWS/A-D/SHORTCUT KEY OR CLICK), THEN ENTER/SPACE/ESC TO CONTINUE",
            SCREEN_WIDTH // 2,
            footer_y,
            COLOR_TEXT_DIM,
            12,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()
