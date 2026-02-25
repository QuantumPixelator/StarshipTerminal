"""
Authentication views for Starship Terminal client.
Contains CharacterSelectView and AuthenticationView for login/registration flow.
"""

import arcade
import os
import sys
import json
import math
import random
import importlib
from constants import SCREEN_WIDTH, SCREEN_HEIGHT
from components.dialogs import InputDialog, MessageBox
from utils.server_config import save_server_username, get_server_username
from sync_network_client import SyncNetworkClient


# Row height used by the visual character selection list
_CHAR_ROW_H = 48


def _load_intro_lines():
    lines = []
    intro_path = os.path.join("assets", "texts", "intro.txt")
    if not os.path.exists(intro_path):
        return lines
    try:
        with open(intro_path, "r", encoding="utf-8") as handle:
            for raw in handle:
                line = str(raw or "").strip()
                if not line or "=" not in line:
                    continue
                _, value = line.split("=", 1)
                text = str(value or "").strip()
                if text:
                    lines.append(text)
    except Exception:
        return []
    return lines


class CharacterSelectView(arcade.View):
    """
    Full-screen character selection view.
    Uses the same visual list style as the in-game market.
    Supports mouse hover/click and keyboard Up/Down/Enter navigation.
    """

    _C_BG = (10, 10, 15)
    _C_BORDER = (0, 200, 80)
    _C_HEADER = (0, 255, 100)
    _C_DIM = (120, 120, 130)
    _C_SEL_BG = (0, 60, 20, 160)
    _C_HOVER_BG = (0, 40, 10, 100)
    _C_ROW_ALT = (255, 255, 255, 8)
    _C_TEXT = (200, 240, 210)
    _C_NEW_TEXT = (180, 200, 255)
    _C_NEW_SEL = (20, 20, 80, 160)
    _C_INSTR = (80, 80, 90)

    def __init__(
        self,
        characters,
        on_select,
        on_cancel,
        account_name="",
        allow_new=False,
    ):
        """
        Parameters
        ----------
        characters  : list of {character_name, display_name} dicts
        on_select   : callable(character_dict | None) – None = new character
        on_cancel   : callable() – user pressed Escape
        account_name: displayed in the sub-header
        allow_new   : whether to show a "+ NEW CHARACTER" row at the bottom
        """
        super().__init__()
        self.characters = list(characters or [])
        self.on_select = on_select
        self.on_cancel = on_cancel
        self.account_name = str(account_name or "")
        self.allow_new = bool(allow_new)

        self._total_rows = len(self.characters) + (1 if self.allow_new else 0)
        self.selected_index = 0
        self.hover_index = -1

    def on_show_view(self):
        arcade.set_background_color(self._C_BG)
        try:
            self.window.set_mouse_visible(True)
        except Exception:
            pass

    def on_hide_view(self):
        pass

    def on_draw(self):
        self.clear()

        cx = SCREEN_WIDTH // 2
        cy = SCREEN_HEIGHT // 2

        arcade.draw_text(
            "SELECT COMMANDER PROFILE",
            cx,
            SCREEN_HEIGHT - 120,
            self._C_HEADER,
            36,
            anchor_x="center",
            anchor_y="center",
            font_name="Courier New",
            bold=True,
        )
        if self.account_name:
            arcade.draw_text(
                f"ACCOUNT: {self.account_name.upper()}",
                cx,
                SCREEN_HEIGHT - 165,
                self._C_DIM,
                14,
                anchor_x="center",
                anchor_y="center",
                font_name="Courier New",
            )

        n_rows = self._total_rows or 1
        list_h = n_rows * _CHAR_ROW_H + 32
        list_w = min(640, SCREEN_WIDTH - 120)
        list_x = cx - list_w // 2
        list_top = cy + list_h // 2

        arcade.draw_lbwh_rectangle_filled(
            list_x - 8,
            list_top - list_h - 8,
            list_w + 16,
            list_h + 16,
            (5, 8, 5, 140),
        )
        arcade.draw_lbwh_rectangle_outline(
            list_x - 8,
            list_top - list_h - 8,
            list_w + 16,
            list_h + 16,
            self._C_BORDER,
            1,
        )

        for idx in range(self._total_rows):
            row_y = list_top - 16 - idx * _CHAR_ROW_H
            is_sel = idx == self.selected_index
            is_hover = idx == self.hover_index
            is_new = idx == len(self.characters)

            if idx % 2 == 0:
                arcade.draw_lbwh_rectangle_filled(
                    list_x, row_y - _CHAR_ROW_H, list_w, _CHAR_ROW_H, self._C_ROW_ALT
                )

            if is_sel:
                bg_col = self._C_NEW_SEL if is_new else self._C_SEL_BG
                arcade.draw_lbwh_rectangle_filled(
                    list_x, row_y - _CHAR_ROW_H, list_w, _CHAR_ROW_H, bg_col
                )
                arcade.draw_lbwh_rectangle_filled(
                    list_x,
                    row_y - _CHAR_ROW_H,
                    4,
                    _CHAR_ROW_H,
                    self._C_BORDER if not is_new else (100, 150, 255),
                )
            elif is_hover:
                arcade.draw_lbwh_rectangle_filled(
                    list_x,
                    row_y - _CHAR_ROW_H,
                    list_w,
                    _CHAR_ROW_H,
                    self._C_NEW_SEL if is_new else self._C_HOVER_BG,
                )

            text_y = row_y - _CHAR_ROW_H // 2 - 1

            if is_new:
                c_text = self._C_NEW_TEXT
                arcade.draw_text(
                    "+ NEW CHARACTER",
                    list_x + 20,
                    text_y + 6,
                    c_text,
                    16,
                    font_name="Courier New",
                    bold=is_sel,
                )
                arcade.draw_text(
                    "start fresh with a new save",
                    list_x + 20,
                    text_y - 10,
                    self._C_DIM,
                    11,
                    font_name="Courier New",
                )
            else:
                entry = self.characters[idx]
                disp = str(
                    entry.get("display_name")
                    or entry.get("character_name")
                    or f"Character {idx+1}"
                ).upper()
                c_text = self._C_HEADER if is_sel else self._C_TEXT
                arcade.draw_text(
                    str(idx + 1),
                    list_x + 20,
                    text_y - 1,
                    self._C_DIM,
                    13,
                    font_name="Courier New",
                )
                arcade.draw_text(
                    disp,
                    list_x + 52,
                    text_y - 1,
                    c_text,
                    18,
                    font_name="Courier New",
                    bold=is_sel,
                )

        footer_y = list_top - list_h - 50
        arcade.draw_text(
            "[↑/↓] NAVIGATE  |  [ENTER] SELECT  |  [ESC] BACK",
            cx,
            footer_y,
            self._C_INSTR,
            13,
            anchor_x="center",
            font_name="Courier New",
        )

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
            self.on_cancel()
        elif key in (arcade.key.UP, arcade.key.W):
            self.selected_index = (self.selected_index - 1) % self._total_rows
        elif key in (arcade.key.DOWN, arcade.key.S):
            self.selected_index = (self.selected_index + 1) % self._total_rows
        elif key in (arcade.key.ENTER, arcade.key.NUM_ENTER, arcade.key.SPACE):
            self._confirm()

    def on_mouse_motion(self, x, y, dx, dy):
        self.hover_index = self._hit_row(x, y)

    def on_mouse_press(self, x, y, button, modifiers):
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        row = self._hit_row(x, y)
        if row is not None and row >= 0:
            self.selected_index = row
            self._confirm()

    def _list_geometry(self):
        cx = SCREEN_WIDTH // 2
        cy = SCREEN_HEIGHT // 2
        n_rows = self._total_rows or 1
        list_h = n_rows * _CHAR_ROW_H + 32
        list_w = min(640, SCREEN_WIDTH - 120)
        list_x = cx - list_w // 2
        list_top = cy + list_h // 2
        return list_x, list_top, list_w, list_h

    def _hit_row(self, mx, my):
        """Return the row index under the mouse position, or None."""
        list_x, list_top, list_w, _ = self._list_geometry()
        if not (list_x <= mx <= list_x + list_w):
            return None
        for idx in range(self._total_rows):
            row_top = list_top - 16 - idx * _CHAR_ROW_H
            row_bottom = row_top - _CHAR_ROW_H
            if row_bottom <= my <= row_top:
                return idx
        return None

    def _confirm(self):
        if self.selected_index >= len(self.characters):
            self.on_select(None)
        else:
            self.on_select(self.characters[self.selected_index])


class IntroCinematicView(arcade.View):
    _BG = (4, 8, 14)
    _ACCENT = (0, 255, 165)
    _TEXT = (186, 238, 220)
    _DIM = (100, 156, 138)

    def __init__(self, on_complete):
        super().__init__()
        self.on_complete = on_complete
        self.intro_lines = _load_intro_lines()
        if not self.intro_lines:
            self.intro_lines = ["WELCOME, COMMANDER. THE STARS AWAIT."]

        self.current_line_index = 0
        self.visible_chars = 0
        self.type_timer = 0.0
        self.type_interval = 0.016
        self.line_hold_timer = 0.0
        self.line_hold_duration = 1.1
        self.complete = False
        self.stars = []

        for _ in range(90):
            x = random.uniform(0, SCREEN_WIDTH)
            y = random.uniform(0, SCREEN_HEIGHT)
            self.stars.append(
                {
                    "x": x,
                    "y": y,
                    "size": random.uniform(1.0, 2.8),
                    "phase": random.uniform(0.0, 6.283),
                    "speed": random.uniform(0.8, 2.0),
                }
            )

    def on_show_view(self):
        arcade.set_background_color(self._BG)

    def _current_full_line(self):
        idx = min(self.current_line_index, len(self.intro_lines) - 1)
        return str(self.intro_lines[idx])

    def _advance_or_finish(self):
        if self.current_line_index >= len(self.intro_lines) - 1:
            self.complete = True
            return
        self.current_line_index += 1
        self.visible_chars = 0
        self.line_hold_timer = 0.0

    def _finish_now(self):
        if self.complete:
            if callable(self.on_complete):
                self.on_complete()
            return
        self.complete = True
        self.visible_chars = len(self._current_full_line())

    def on_update(self, delta_time):
        for star in self.stars:
            star["phase"] += float(delta_time) * star["speed"]

        if self.complete:
            return

        self.type_timer += delta_time
        full_line = self._current_full_line()
        if self.visible_chars < len(full_line):
            while self.type_timer >= self.type_interval and self.visible_chars < len(
                full_line
            ):
                self.type_timer -= self.type_interval
                self.visible_chars += 1
        else:
            self.line_hold_timer += delta_time
            if self.line_hold_timer >= self.line_hold_duration:
                self._advance_or_finish()

    def on_draw(self):
        self.clear()

        for star in self.stars:
            glow = 0.45 + (0.55 * (0.5 + 0.5 * math.sin(star["phase"])))
            color = (int(60 * glow), int(210 * glow), int(170 * glow), int(210 * glow))
            arcade.draw_circle_filled(
                float(star["x"]), float(star["y"]), float(star["size"]), color
            )

        arcade.draw_text(
            "GALACTIC COMMAND UPLINK",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 120,
            self._ACCENT,
            32,
            anchor_x="center",
            font_name="Courier New",
            bold=True,
        )

        y = SCREEN_HEIGHT - 210
        for idx in range(self.current_line_index + 1):
            full = str(self.intro_lines[idx])
            if idx == self.current_line_index and not self.complete:
                text = full[: self.visible_chars]
                if self.visible_chars < len(full):
                    text += "_"
            else:
                text = full

            arcade.draw_text(
                text,
                SCREEN_WIDTH // 2,
                y,
                self._TEXT if idx == self.current_line_index else self._DIM,
                15,
                anchor_x="center",
                multiline=True,
                width=SCREEN_WIDTH - 240,
                align="center",
                font_name="Courier New",
            )
            y -= 132

        arcade.draw_text(
            "PRESS ENTER TO CONTINUE" if self.complete else "PRESS ENTER TO SKIP",
            SCREEN_WIDTH // 2,
            88,
            self._DIM,
            13,
            anchor_x="center",
            font_name="Courier New",
        )

    def on_key_press(self, key, modifiers):
        if key in (
            arcade.key.ENTER,
            arcade.key.RETURN,
            arcade.key.SPACE,
            arcade.key.ESCAPE,
        ):
            if self.complete:
                if callable(self.on_complete):
                    self.on_complete()
            else:
                self._finish_now()

    def on_mouse_press(self, x, y, button, modifiers):
        if button != arcade.MOUSE_BUTTON_LEFT:
            return
        if self.complete:
            if callable(self.on_complete):
                self.on_complete()
        else:
            self._finish_now()


class AuthenticationView(arcade.View):
    """Authentication view handling login and account registration flow."""

    def __init__(self, server_url=None, offline=False):
        super().__init__()
        self.server_url = server_url
        self.offline = offline
        self.network = None

        self.state = "username"
        self.username = ""
        self.password = ""
        self.account_exists = False
        self.available_characters = []
        self.pending_character_name = ""
        self.character_prompt_mode = None
        self.play_intro_on_launch = False

        self.input_dialog = None
        self.message_box = None
        self.status = "Enter your commander name to begin"

    def _initialize_view(self):
        arcade.set_background_color((10, 10, 15))
        if not (self.input_dialog and self.input_dialog.active):
            self._prompt_username()

    def on_show(self):
        self._initialize_view()

    def on_show_view(self):
        self._initialize_view()

    def on_update(self, delta_time):
        if self.input_dialog and self.input_dialog.active:
            self.input_dialog.update(delta_time)

    def on_draw(self):
        self.clear()

        arcade.draw_text(
            "AUTHENTICATION",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 150,
            (0, 255, 100),
            48,
            anchor_x="center",
            font_name="Courier New",
            bold=True,
        )

        mode_text = "OFFLINE MODE" if self.offline else f"SERVER: {self.server_url}"
        arcade.draw_text(
            mode_text,
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 210,
            (150, 150, 150),
            14,
            anchor_x="center",
            font_name="Courier New",
        )

        arcade.draw_text(
            self.status,
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2 + 100,
            (180, 220, 200),
            16,
            anchor_x="center",
            font_name="Courier New",
        )

        if self.message_box and self.message_box.active:
            self.message_box.draw()
        elif self.input_dialog and self.input_dialog.active:
            self.input_dialog.draw()

    def on_key_press(self, key, modifiers):
        if self.message_box and self.message_box.active:
            if self.message_box.on_key_press(key, modifiers):
                self.message_box = None
            return

        if self.input_dialog and self.input_dialog.active:
            result = self.input_dialog.on_key_press(key, modifiers)
            if result != "continue":
                self._handle_input_result(result)
            return

        if key == arcade.key.ESCAPE:
            from views.connection_view import ConnectionView  # lazy

            self.window.show_view(ConnectionView())

    def on_text(self, text):
        if self.input_dialog and self.input_dialog.active:
            self.input_dialog.on_text(text)

    def _prompt_username(self):
        self.state = "username"
        saved_name = get_server_username(self.server_url)
        self.input_dialog = InputDialog(
            "Enter your commander name:", saved_name, max_length=30
        )

    def _prompt_password(self, is_new_account=False):
        self.state = "password"
        prompt = (
            "Create a password (min 4 chars):"
            if is_new_account
            else "Enter your password:"
        )
        self.input_dialog = InputDialog(prompt, "", max_length=50, password=True)

    def _prompt_confirm_password(self):
        self.state = "confirm_password"
        self.input_dialog = InputDialog(
            "Confirm your password:", "", max_length=50, password=True
        )

    def _prompt_character_selection(self):
        self.state = "character_select"
        if not self.available_characters:
            self.input_dialog = InputDialog(
                "No linked characters found. Enter a character name:",
                self.username,
                max_length=30,
            )
            return

        lines = ["Select character (number or name):"]
        for idx, entry in enumerate(self.available_characters, start=1):
            display_name = str(
                entry.get("display_name")
                or entry.get("character_name")
                or f"Character {idx}"
            )
            lines.append(f"{idx}. {display_name}")
        prompt = "\n".join(lines[:8])
        default_choice = str(
            self.available_characters[0].get("display_name")
            or self.available_characters[0].get("character_name")
            or ""
        )
        self.input_dialog = InputDialog(prompt, default_choice, max_length=40)

    def _show_character_select_view(self):
        """Show the visual character selection screen (mouse + keyboard)."""
        allow_multiple = bool(
            self.network
            and (self.network.config or {}).get("allow_multiple_games", False)
            if hasattr(self.network, "config")
            else False
        )

        auth_view_ref = self

        def on_select(entry):
            if entry is None:
                self.window.show_view(auth_view_ref)
                auth_view_ref._prompt_new_character_name(mode="create_after_login")
                return
            char_name = str(entry.get("character_name", ""))
            ok, message = auth_view_ref.network.select_character(char_name)
            if ok:
                auth_view_ref._launch_game()
            else:
                self.window.show_view(auth_view_ref)
                auth_view_ref.message_box = MessageBox(
                    "Load Failed",
                    message or "Unable to load selected character.",
                    "error",
                )
                auth_view_ref._show_character_select_view()

        def on_cancel():
            self.window.show_view(auth_view_ref)
            auth_view_ref._prompt_username()

        select_view = CharacterSelectView(
            characters=self.available_characters,
            on_select=on_select,
            on_cancel=on_cancel,
            account_name=self.username,
            allow_new=allow_multiple,
        )
        self.window.show_view(select_view)

    def _prompt_new_character_name(self, mode):
        self.state = "new_character_name"
        self.character_prompt_mode = mode
        self.input_dialog = InputDialog(
            "Enter your character name:",
            self.pending_character_name or self.username,
            max_length=30,
        )

    def _handle_input_result(self, result):
        if result is None:
            if self.state == "username":
                from views.connection_view import ConnectionView  # lazy

                self.window.show_view(ConnectionView())
            else:
                self._prompt_username()
            return

        if self.state == "username":
            self.username = result.strip()
            if len(self.username) < 3:
                self.message_box = MessageBox(
                    "Invalid Username",
                    "Username must be at least 3 characters.",
                    "error",
                )
                self._prompt_username()
                return
            self._check_account()

        elif self.state == "password":
            self.password = result
            if self.account_exists:
                self._authenticate()
            else:
                if len(self.password) < 4:
                    self.message_box = MessageBox(
                        "Weak Password",
                        "Password must be at least 4 characters.",
                        "error",
                    )
                    self._prompt_password(is_new_account=True)
                    return
                self._prompt_confirm_password()

        elif self.state == "confirm_password":
            confirm = result
            if confirm != self.password:
                self.message_box = MessageBox(
                    "Password Mismatch",
                    "Passwords do not match. Please try again.",
                    "error",
                )
                self._prompt_password(is_new_account=True)
                return
            self._prompt_new_character_name(mode="create_account")

        elif self.state == "new_character_name":
            character_name = str(result or "").strip()
            if len(character_name) < 2:
                self.message_box = MessageBox(
                    "Invalid Character Name",
                    "Character name must be at least 2 characters.",
                    "error",
                )
                self._prompt_new_character_name(mode=self.character_prompt_mode)
                return

            self.pending_character_name = character_name
            if self.character_prompt_mode == "create_account":
                self._create_account()
            else:
                self._create_character_for_account()

        elif self.state == "character_select":
            selection = str(result or "").strip()
            if not selection:
                self._prompt_character_selection()
                return

            chosen = None
            if selection.isdigit():
                idx = int(selection) - 1
                if 0 <= idx < len(self.available_characters):
                    chosen = self.available_characters[idx]

            if chosen is None:
                lowered = selection.lower()
                for entry in self.available_characters:
                    display_name = str(entry.get("display_name", "")).strip().lower()
                    character_name = (
                        str(entry.get("character_name", "")).strip().lower()
                    )
                    if lowered in (display_name, character_name):
                        chosen = entry
                        break

            if chosen is None:
                self.message_box = MessageBox(
                    "Invalid Selection",
                    "Enter a valid character number or name.",
                    "error",
                )
                self._prompt_character_selection()
                return

            ok, message = self.network.select_character(
                str(chosen.get("character_name", ""))
            )
            if ok:
                self.message_box = MessageBox(
                    "Character Loaded",
                    f"Commander {chosen.get('display_name', chosen.get('character_name', 'Unknown'))} ready for deployment.",
                    "success",
                )
                self._launch_game()
            else:
                self.message_box = MessageBox(
                    "Load Failed",
                    message or "Unable to load selected character.",
                    "error",
                )
                self._prompt_character_selection()

    def _check_account(self):
        """Check if the account exists on the server."""
        self.status = f"Checking account: {self.username}..."
        self.input_dialog = None

        try:
            if self.offline:
                server_path = os.path.join(
                    os.path.dirname(__file__), "..", "..", "server"
                )
                saves_path = os.path.join(server_path, "saves")
                safe_name = self.username.lower().replace(" ", "_")
                save_file = os.path.join(saves_path, f"{safe_name}.json")
                self.account_exists = os.path.exists(save_file)
            else:
                self.network = SyncNetworkClient(self.server_url)
                self.network.start()
                result = self.network.check_account(self.username)

                error_text = (
                    f"{result.get('error', '')} {result.get('message', '')}".lower()
                )
                if "unknown action: check_account" in error_text:
                    self.message_box = MessageBox(
                        "Server Configuration Error",
                        "This server does not support password authentication. Start the auth server (game_server_auth.py).",
                        "error",
                    )
                    self.status = "Password-auth server required"
                    self._prompt_username()
                    return

                if not result.get("success", False):
                    self.message_box = MessageBox(
                        "Connection Error",
                        result.get("message")
                        or result.get("error")
                        or "Failed to check account.",
                        "error",
                    )
                    self.status = "Connection failed"
                    self._prompt_username()
                    return

                self.account_exists = result.get("exists", False)

            if self.account_exists:
                self.status = f"Welcome back, {self.username}!"
                self._prompt_password(is_new_account=False)
            else:
                self.status = (
                    f"New commander detected. Create account for {self.username}"
                )
                self._prompt_password(is_new_account=True)

        except Exception as e:
            self.message_box = MessageBox(
                "Connection Error", f"Failed to connect to server: {str(e)}", "error"
            )
            self.status = "Connection failed"

    def _create_account(self):
        """Create a new account on the server."""
        self.status = "Creating account..."
        self.input_dialog = None

        try:
            if self.offline:
                self._create_offline_account()
            else:
                result = self.network.create_account(
                    self.username, self.password, self.pending_character_name
                )

                error_text = (
                    f"{result.get('error', '')} {result.get('message', '')}".lower()
                )
                if "unknown action: create_account" in error_text:
                    self.message_box = MessageBox(
                        "Server Configuration Error",
                        "This server does not support password authentication. Start the auth server (game_server_auth.py).",
                        "error",
                    )
                    self._prompt_username()
                    return

                if result.get("success"):
                    self.play_intro_on_launch = True
                    self.message_box = MessageBox(
                        "Account Created",
                        f"Welcome, Commander {self.username}! Your account has been created.",
                        "success",
                    )
                    self._launch_game()
                else:
                    error_msg = (
                        result.get("message") or result.get("error") or "Unknown error"
                    )
                    self.message_box = MessageBox(
                        "Account Creation Failed", error_msg, "error"
                    )
                    self._prompt_username()

        except Exception as e:
            self.message_box = MessageBox(
                "Error", f"Failed to create account: {str(e)}", "error"
            )
            self._prompt_username()

    def _create_offline_account(self):
        """Create an account for offline/local mode."""
        try:
            server_path = os.path.join(os.path.dirname(__file__), "..", "..", "server")
            if server_path not in sys.path:
                sys.path.insert(0, server_path)

            GameManager = importlib.import_module("game_manager").GameManager
            import bcrypt

            gm = GameManager()
            gm.new_game(self.username)

            save_result = gm.save_game()
            if save_result:
                saves_path = os.path.join(server_path, "saves")
                safe_name = self.username.lower().replace(" ", "_")
                save_path = os.path.join(saves_path, f"{safe_name}.json")

                with open(save_path, "r") as f:
                    save_data = json.load(f)

                salt = bcrypt.gensalt()
                password_hash = bcrypt.hashpw(
                    self.password.encode("utf-8"), salt
                ).decode("utf-8")

                save_data["password_hash"] = password_hash
                save_data["created_at"] = str(arcade.get_elapsed_time())

                with open(save_path, "w") as f:
                    json.dump(save_data, f, indent=2)

                self.message_box = MessageBox(
                    "Account Created",
                    f"Welcome, Commander {self.username}! Your offline account has been created.",
                    "success",
                )
                self.play_intro_on_launch = True
                self._launch_game()
            else:
                raise Exception("Failed to save game")

        except Exception as e:
            self.message_box = MessageBox(
                "Error", f"Failed to create offline account: {str(e)}", "error"
            )
            self._prompt_username()

    def _authenticate(self):
        """Authenticate with an existing account."""
        self.status = "Authenticating..."
        self.input_dialog = None

        try:
            if self.offline:
                self._authenticate_offline()
            else:
                result = self.network.authenticate(self.username, self.password)

                error_text = (
                    f"{result.get('error', '')} {result.get('message', '')}".lower()
                )
                if "unknown action: authenticate" in error_text:
                    self.message_box = MessageBox(
                        "Server Configuration Error",
                        "This server does not support password authentication. Start the auth server (game_server_auth.py).",
                        "error",
                    )
                    self._prompt_username()
                    return

                if result.get("success"):
                    self.available_characters = list(result.get("characters", []) or [])
                    if bool(result.get("requires_character_create", False)):
                        self.status = "Welcome, Commander. Start a new mission."
                        self.play_intro_on_launch = True
                        self._launch_game()
                        return
                    if bool(result.get("requires_character_select", False)):
                        self.status = "Select a commander profile"
                        self._show_character_select_view()
                        return

                    selected_character = result.get("selected_character")
                    if selected_character:
                        self.status = f"Loaded commander profile: {selected_character}"

                    self._launch_game()
                else:
                    error = result.get("error", "")
                    if error == "WRONG_PASSWORD":
                        self.message_box = MessageBox(
                            "Authentication Failed",
                            "Incorrect password. Please try again.",
                            "error",
                        )
                    else:
                        self.message_box = MessageBox(
                            "Authentication Failed",
                            result.get("message")
                            or result.get("error")
                            or "Authentication failed",
                            "error",
                        )
                    self._prompt_password(is_new_account=False)

        except Exception as e:
            self.message_box = MessageBox(
                "Error", f"Authentication error: {str(e)}", "error"
            )
            self._prompt_password(is_new_account=False)

    def _create_character_for_account(self):
        """Create first character for a logged-in account with no saves."""
        self.status = "Creating character..."
        self.input_dialog = None

        try:
            success, message = self.network.new_game(self.pending_character_name)
            if success:
                self.play_intro_on_launch = True
                self.message_box = MessageBox(
                    "Character Created",
                    f"Commander {self.pending_character_name} is ready.",
                    "success",
                )
                self._launch_game()
            else:
                self.message_box = MessageBox(
                    "Creation Failed",
                    message or "Unable to create character.",
                    "error",
                )
                self._prompt_new_character_name(mode="create_after_login")
        except Exception as e:
            self.message_box = MessageBox(
                "Error", f"Character creation error: {str(e)}", "error"
            )
            self._prompt_new_character_name(mode="create_after_login")

    def _authenticate_offline(self):
        """Authenticate against a local save file."""
        try:
            server_path = os.path.join(os.path.dirname(__file__), "..", "..", "server")
            if server_path not in sys.path:
                sys.path.insert(0, server_path)

            import bcrypt

            saves_path = os.path.join(server_path, "saves")
            safe_name = self.username.lower().replace(" ", "_")
            save_path = os.path.join(saves_path, f"{safe_name}.json")

            with open(save_path, "r") as f:
                save_data = json.load(f)

            stored_hash = save_data.get("password_hash")
            if not stored_hash:
                raise Exception("No password hash found")

            if bcrypt.checkpw(
                self.password.encode("utf-8"), stored_hash.encode("utf-8")
            ):
                self.message_box = MessageBox(
                    "Login Successful",
                    f"Welcome back, Commander {self.username}!",
                    "success",
                )
                self._launch_game()
            else:
                self.message_box = MessageBox(
                    "Authentication Failed",
                    "Incorrect password. Please try again.",
                    "error",
                )
                self._prompt_password(is_new_account=False)

        except Exception as e:
            self.message_box = MessageBox(
                "Error", f"Offline authentication error: {str(e)}", "error"
            )
            self._prompt_password(is_new_account=False)

    def _launch_game(self):
        """Launch game after successful authentication and character load."""
        save_server_username(self.server_url, self.username)
        try:
            if self.offline:
                server_path = os.path.join(
                    os.path.dirname(__file__), "..", "..", "server"
                )
                if server_path not in sys.path:
                    sys.path.insert(0, server_path)
                GameManager = importlib.import_module("game_manager").GameManager

                class LocalGameWrapper:
                    """Wraps GameManager to match the network client interface."""

                    def __init__(self, username):
                        self.gm = GameManager()
                        self.gm.load_game(username)

                    def __getattr__(self, name):
                        return getattr(self.gm, name)

                    def close(self):
                        pass

                self.window.network = LocalGameWrapper(self.username)
            else:
                self.window.network = self.network

            network = self.window.network
            player_name = getattr(getattr(network, "player", None), "name", None)
            if player_name:
                from views.menu import GalacticNewsView
                from views.gameplay import (
                    PlanetView,
                )  # gameplay.py acts as shim → planet_view.py

                show_wisdom = bool(getattr(self, "play_intro_on_launch", False))
                next_view = PlanetView(network, show_wisdom_modal=show_wisdom)
                if network.has_unseen_galactic_news():
                    launch_view = GalacticNewsView(network, next_view)
                else:
                    launch_view = next_view

                if bool(getattr(self, "play_intro_on_launch", False)):
                    self.play_intro_on_launch = False

                    def _show_launch_view():
                        self.window.show_view(launch_view)

                    self.window.show_view(IntroCinematicView(_show_launch_view))
                else:
                    self.window.show_view(launch_view)
            else:
                from views.menu import MainMenuView

                self.window.show_view(MainMenuView())

        except Exception as e:
            self.message_box = MessageBox(
                "Launch Error", f"Failed to launch game: {str(e)}", "error"
            )
