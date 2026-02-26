# REFACTORED FOR NETWORK CLIENT - All game logic runs on server
import arcade
import arcade.types
import math
import time
from constants import *

# GameManager runs on server
from classes import load_spaceships


class MainMenuView(arcade.View):
    def __init__(self):
        super().__init__()
        self.network = None
        existing_saves = []
        self.selected_option = 1 if existing_saves else 0
        self.menu_options = [
            "NEW GAME",
            "LOAD GAME",
            "SYSTEM DIAGNOSTICS",
            "WINNER BOARD",
            "DISCONNECT",
        ]
        self.font_title = get_font("title")
        self.font_ui = get_font("ui")

        # UI Text Objects for stability/performance
        self.title_text = arcade.Text(
            "S T A R S H I P   T E R M I N A L",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 150,
            COLOR_PRIMARY,
            54,
            anchor_x="center",
            font_name=self.font_title,
        )
        self.version_text = arcade.Text(
            "v0.1.0 NEURAL-OS CONSOLE",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 200,
            COLOR_SECONDARY,
            14,
            anchor_x="center",
            font_name=self.font_ui,
        )
        self.footer_text = arcade.Text(
            "MISSION DATA DETECTED" if existing_saves else "UPLINK ESTABLISHED",
            SCREEN_WIDTH // 2,
            50,
            COLOR_TEXT_DIM,
            12,
            anchor_x="center",
            font_name=self.font_ui,
        )
        self.session_text = arcade.Text(
            "",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 228,
            COLOR_TEXT_DIM,
            12,
            anchor_x="center",
            font_name=self.font_ui,
        )

        self.option_texts = []
        start_y = SCREEN_HEIGHT // 2 - 50
        for i, opt in enumerate(self.menu_options):
            y = start_y - i * 80
            txt = arcade.Text(
                opt,
                SCREEN_WIDTH // 2,
                y,
                COLOR_TEXT_DIM,
                20,
                anchor_x="center",
                font_name=self.font_ui,
            )
            self.option_texts.append(txt)

    def _resolve_network(self):
        if not self.network and hasattr(self.window, "network"):
            self.network = self.window.network

    def _refresh_menu_state(self):
        self._resolve_network()
        if not self.network and hasattr(self.window, "network"):
            self.network = self.window.network
        existing_saves = []
        account_name = ""
        commander_name = ""
        if self.network:
            try:
                existing_saves = list(self.network.list_characters() or [])
            except Exception:
                existing_saves = []
            account_name = str(
                getattr(self.network, "account_name", None)
                or getattr(self.network, "player_name", None)
                or ""
            ).strip()
            commander_name = str(
                getattr(getattr(self.network, "player", None), "name", "")
            ).strip()
        self.selected_option = 1 if existing_saves else 0
        self.footer_text.text = (
            "MISSION DATA DETECTED" if existing_saves else "UPLINK ESTABLISHED"
        )
        if account_name and commander_name:
            self.session_text.text = f"ACCOUNT: {account_name.upper()}  |  COMMANDER: {commander_name.upper()}"
        elif account_name:
            self.session_text.text = f"ACCOUNT: {account_name.upper()}"
        else:
            self.session_text.text = "NO ACTIVE ACCOUNT SESSION"

    def on_show(self):
        self._refresh_menu_state()
        arcade.set_background_color(COLOR_BG)

    def on_show_view(self):
        self._refresh_menu_state()
        arcade.set_background_color(COLOR_BG)

    def on_draw(self):
        self.clear()

        # Scanline effect
        for y in range(0, SCREEN_HEIGHT, 4):
            arcade.draw_line(0, y, SCREEN_WIDTH, y, (0, 0, 0, 40))

        self.title_text.draw()
        self.version_text.draw()
        self.session_text.draw()

        # Draw menu options
        start_y = SCREEN_HEIGHT // 2 - 50
        for i, txt in enumerate(self.option_texts):
            is_sel = i == self.selected_option
            if is_sel:
                y = start_y - i * 80
                # Glitchy selection bar
                alpha = 60 + int(30 * math.sin(time.time() * 10))
                arcade.draw_lbwh_rectangle_filled(
                    SCREEN_WIDTH // 2 - 200, y - 13, 400, 50, (*COLOR_PRIMARY, alpha)
                )
                txt.color = COLOR_PRIMARY
                txt.text = f"> {self.menu_options[i]} <"
            else:
                txt.color = COLOR_TEXT_DIM
                txt.text = self.menu_options[i]
            txt.draw()

        self.footer_text.draw()

    def on_key_press(self, key, modifiers):
        if key == arcade.key.UP:
            self.selected_option = (self.selected_option - 1) % len(self.menu_options)
        elif key == arcade.key.DOWN:
            self.selected_option = (self.selected_option + 1) % len(self.menu_options)
        elif key == arcade.key.ENTER:
            self.handle_selection()

    def on_mouse_motion(self, x, y, dx, dy):
        start_y = SCREEN_HEIGHT // 2 - 50
        for i in range(len(self.menu_options)):
            y_pos = start_y - i * 80
            if (SCREEN_WIDTH // 2 - 170) < x < (SCREEN_WIDTH // 2 + 170) and (
                y_pos - 13
            ) < y < (y_pos + 37):
                self.selected_option = i

    def on_mouse_press(self, x, y, button, modifiers):
        self.on_mouse_motion(x, y, 0, 0)
        self.handle_selection()

    def handle_selection(self):
        self._resolve_network()
        if self.selected_option == 0:
            self.window.show_view(CommanderCreationView())
        elif self.selected_option == 1:
            self.window.show_view(LoadMissionView(self.network))
        elif self.selected_option == 2:
            pass  # System Diagnostics
        elif self.selected_option == 3:
            self.window.show_view(WinnerBoardView(self.network))
        elif self.selected_option == 4:
            if hasattr(self.window, "network") and self.window.network:
                try:
                    self.window.network.close()
                except:
                    pass
            self.window.network = None
            # Go back to connection view logic
            import sys

            if "main" in sys.modules:
                ConnectionView = getattr(sys.modules["main"], "ConnectionView", None)
                if ConnectionView:
                    self.window.show_view(ConnectionView())
                else:
                    arcade.exit()
            else:
                arcade.exit()


class WinnerBoardView(arcade.View):
    def __init__(self, network):
        super().__init__()
        self.network = network
        self.font_ui = get_font("ui")
        self.board = {}
        self.error_message = ""

        self.header_text = arcade.Text(
            "WINNER BOARD",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 110,
            COLOR_PRIMARY,
            30,
            anchor_x="center",
            font_name=self.font_ui,
        )
        self.footer_text = arcade.Text(
            "ESC OR ENTER TO RETURN",
            SCREEN_WIDTH // 2,
            70,
            COLOR_TEXT_DIM,
            13,
            anchor_x="center",
            font_name=self.font_ui,
        )

    def _load_board(self):
        self.error_message = ""
        if not self.network:
            self.board = {}
            self.error_message = "NO ACTIVE SESSION. CONNECT TO VIEW WINNER BOARD."
            return
        try:
            self.board = dict(self.network.get_winner_board() or {})
        except Exception as exc:
            self.board = {}
            self.error_message = str(exc).strip() or "FAILED TO LOAD WINNER BOARD"
            return
        if self.board.get("error"):
            self.error_message = str(self.board.get("error") or "")

    def on_show(self):
        arcade.set_background_color(COLOR_BG)
        self._load_board()

    def on_show_view(self):
        arcade.set_background_color(COLOR_BG)
        self._load_board()

    def _draw_row(self, text, x, y, color=COLOR_TEXT_DIM, size=12):
        arcade.Text(
            str(text),
            x,
            y,
            color,
            size,
            font_name=self.font_ui,
        ).draw()

    def on_draw(self):
        self.clear()
        for y in range(0, SCREEN_HEIGHT, 4):
            arcade.draw_line(0, y, SCREEN_WIDTH, y, (0, 0, 0, 28))

        box_x, box_y = 80, 120
        box_w, box_h = SCREEN_WIDTH - 160, SCREEN_HEIGHT - 220
        arcade.draw_lbwh_rectangle_filled(box_x, box_y, box_w, box_h, (10, 16, 26, 230))
        arcade.draw_lbwh_rectangle_outline(box_x, box_y, box_w, box_h, COLOR_SECONDARY, 2)

        self.header_text.draw()
        self.footer_text.draw()

        if self.error_message:
            arcade.Text(
                self.error_message.upper(),
                SCREEN_WIDTH // 2,
                SCREEN_HEIGHT // 2,
                COLOR_ACCENT,
                16,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            return

        winner = (self.board or {}).get("current_winner") or {}
        rankings = (self.board or {}).get("faction_rankings") or {}
        authority_rows = list(rankings.get("authority", []) or [])[:5]
        frontier_rows = list(rankings.get("frontier", []) or [])[:5]
        scheduled_reset_ts = (self.board or {}).get("scheduled_reset_ts")

        y = SCREEN_HEIGHT - 180
        self._draw_row("CURRENT CAMPAIGN WINNER", box_x + 22, y, COLOR_PRIMARY, 16)
        y -= 34

        if winner:
            winner_name = str(winner.get("name", "UNKNOWN COMMANDER")).upper()
            owned_planets = int(winner.get("owned_planets", 0))
            total_credits = int(winner.get("total_credits", 0))
            personal_credits = int(winner.get("personal_credits", 0))
            bank_credits = int(winner.get("bank_balance", 0))
            colony_credits = int(winner.get("colony_credits", 0))
            authority_rank = int(winner.get("authority_rank", 0))
            frontier_rank = int(winner.get("frontier_rank", 0))

            self._draw_row(f"COMMANDER: {winner_name}", box_x + 26, y, COLOR_SECONDARY, 14)
            y -= 24
            self._draw_row(f"PLANETS OWNED: {owned_planets}", box_x + 26, y)
            y -= 22
            self._draw_row(
                f"TOTAL CREDITS: {total_credits:,} (PERSONAL {personal_credits:,} | BANK {bank_credits:,} | PLANETS {colony_credits:,})",
                box_x + 26,
                y,
            )
            y -= 22
            self._draw_row(
                f"FACTION RANKINGS: AUTHORITY #{max(0, authority_rank)} | FRONTIER #{max(0, frontier_rank)}",
                box_x + 26,
                y,
            )
            y -= 22
        else:
            self._draw_row("NO WINNER DECLARED YET.", box_x + 26, y, COLOR_TEXT_DIM, 13)
            y -= 24

        if scheduled_reset_ts:
            try:
                reset_text = time.strftime("%Y-%m-%d 12:01 AM", time.localtime(float(scheduled_reset_ts)))
                self._draw_row(f"SCHEDULED RESET: {reset_text}", box_x + 26, y, COLOR_ACCENT, 12)
            except Exception:
                self._draw_row("SCHEDULED RESET: PENDING", box_x + 26, y, COLOR_ACCENT, 12)
        y -= 44

        col_mid = SCREEN_WIDTH // 2
        self._draw_row("AUTHORITY RANKING", box_x + 26, y, COLOR_PRIMARY, 14)
        self._draw_row("FRONTIER RANKING", col_mid + 10, y, COLOR_PRIMARY, 14)
        y -= 28

        max_rows = max(len(authority_rows), len(frontier_rows), 1)
        for idx in range(max_rows):
            if idx < len(authority_rows):
                row = authority_rows[idx]
                self._draw_row(
                    f"#{int(row.get('rank', 0)):>2}  {str(row.get('name', '')).upper():<18}  {int(row.get('value', 0)):>4}",
                    box_x + 26,
                    y,
                    COLOR_TEXT_DIM,
                    12,
                )
            if idx < len(frontier_rows):
                row = frontier_rows[idx]
                self._draw_row(
                    f"#{int(row.get('rank', 0)):>2}  {str(row.get('name', '')).upper():<18}  {int(row.get('value', 0)):>4}",
                    col_mid + 10,
                    y,
                    COLOR_TEXT_DIM,
                    12,
                )
            y -= 24

    def on_key_press(self, key, modifiers):
        if key in (arcade.key.ESCAPE, arcade.key.ENTER, arcade.key.RETURN):
            self.window.show_view(MainMenuView())

    def on_mouse_press(self, x, y, button, modifiers):
        self.window.show_view(MainMenuView())


class LoadMissionView(arcade.View):
    def __init__(self, network):
        super().__init__()
        self.network = network
        self.characters = []  # full dicts from list_characters()
        self.saves = []  # display names shown in the list
        self.selected_save = 0
        self.font_ui = get_font("ui")

        # UI Text Objects
        self.header_text = arcade.Text(
            ">>> SELECT COMMANDER PROFILE",
            120,
            SCREEN_HEIGHT - 140,
            COLOR_PRIMARY,
            18,
            font_name=self.font_ui,
        )
        self.instr_text = arcade.Text(
            "UP/DOWN TO SELECT | ENTER TO LOAD | ESC TO ABORT",
            SCREEN_WIDTH // 2,
            80,
            COLOR_TEXT_DIM,
            14,
            anchor_x="center",
            font_name=self.font_ui,
        )
        self.no_saves_text = arcade.Text(
            "NO COMMANDERS FOUND FOR THIS ACCOUNT",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2,
            COLOR_ACCENT,
            24,
            anchor_x="center",
            font_name=self.font_ui,
        )

        self.save_texts = []
        self.fetch_error_message = ""
        self._refresh_saves()

    def _refresh_saves(self):
        if not self.network:
            self.characters = []
            self.saves = []
            self.save_texts = []
            self.selected_save = 0
            self.fetch_error_message = "NO ACTIVE SESSION. RETURN TO MAIN MENU."
            return

        self.fetch_error_message = ""

        def _list_characters_with_error():
            try:
                return list(self.network.list_characters() or []), ""
            except Exception as exc:
                return [], str(exc).strip()

        self.characters, fetch_error = _list_characters_with_error()

        if fetch_error:
            self.fetch_error_message = (
                "CONNECTION/AUTH LOST. RECONNECT AND SIGN IN AGAIN."
            )

        self.no_saves_text.text = (
            self.fetch_error_message or "NO COMMANDERS FOUND FOR THIS ACCOUNT"
        )

        self.saves = [
            str(
                c.get("display_name") or c.get("character_name") or f"Commander {i+1}"
            ).upper()
            for i, c in enumerate(self.characters)
        ]
        self.selected_save = (
            0 if not self.saves else min(self.selected_save, len(self.saves) - 1)
        )
        self.save_texts = []
        start_y = SCREEN_HEIGHT - 250
        for i, name in enumerate(self.saves):
            y = start_y - i * 50
            txt = arcade.Text(
                name,
                SCREEN_WIDTH // 2,
                y,
                COLOR_TEXT_DIM,
                20,
                anchor_x="center",
                font_name=self.font_ui,
            )
            self.save_texts.append(txt)

    def on_show(self):
        if not self.network and hasattr(self.window, "network"):
            self.network = self.window.network
        self._refresh_saves()
        arcade.set_background_color(COLOR_BG)

    def on_show_view(self):
        if not self.network and hasattr(self.window, "network"):
            self.network = self.window.network
        self._refresh_saves()
        arcade.set_background_color(COLOR_BG)

    def on_draw(self):
        self.clear()
        for y in range(0, SCREEN_HEIGHT, 4):
            arcade.draw_line(0, y, SCREEN_WIDTH, y, (0, 0, 0, 30))
        arcade.draw_lbwh_rectangle_outline(
            100, 100, SCREEN_WIDTH - 200, SCREEN_HEIGHT - 200, COLOR_SECONDARY, 2
        )
        arcade.draw_line(
            100,
            SCREEN_HEIGHT - 160,
            SCREEN_WIDTH - 100,
            SCREEN_HEIGHT - 160,
            COLOR_SECONDARY,
            1,
        )

        self.header_text.draw()
        self.instr_text.draw()

        if not self.saves:
            self.no_saves_text.draw()
        else:
            start_y = SCREEN_HEIGHT - 250
            for i, txt in enumerate(self.save_texts):
                is_sel = i == self.selected_save
                if is_sel:
                    y = start_y - i * 50
                    arcade.draw_lbwh_rectangle_filled(
                        SCREEN_WIDTH // 2 - 250, y - 10, 500, 40, (*COLOR_PRIMARY, 40)
                    )
                    txt.color = COLOR_PRIMARY
                else:
                    txt.color = COLOR_TEXT_DIM
                txt.draw()

        if self.fetch_error_message:
            arcade.Text(
                self.fetch_error_message,
                SCREEN_WIDTH // 2,
                120,
                COLOR_ACCENT,
                13,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

    def on_key_press(self, key, modifiers):
        if key == arcade.key.UP:
            if self.saves:
                self.selected_save = (self.selected_save - 1) % len(self.saves)
        elif key == arcade.key.DOWN:
            if self.saves:
                self.selected_save = (self.selected_save + 1) % len(self.saves)
        elif key == arcade.key.ENTER or key == arcade.key.RETURN:
            self._load_selected()
        elif key == arcade.key.ESCAPE:
            self.window.show_view(MainMenuView())

    def _load_selected(self):
        if not self.characters:
            self.fetch_error_message = "NO COMMANDER PROFILE SELECTED."
            self.no_saves_text.text = self.fetch_error_message
            return
        entry = self.characters[self.selected_save]
        char_name = str(entry.get("character_name", "")).strip()
        if not char_name:
            self.fetch_error_message = "INVALID COMMANDER PROFILE DATA."
            self.no_saves_text.text = self.fetch_error_message
            return

        self.fetch_error_message = ""

        ok, msg = False, ""
        try:
            ok, msg = self.network.select_character(char_name)
        except Exception as exc:
            msg = str(exc).strip() or "SELECT CHARACTER FAILED"

        if not ok:
            try:
                legacy_ok, legacy_msg = self.network.load_game(char_name)
                if legacy_ok:
                    ok, msg = legacy_ok, legacy_msg
            except Exception:
                pass

        if ok:
            from views.gameplay import PlanetView

            next_view = PlanetView(self.network)
            if self.network.has_unseen_galactic_news():
                self.window.show_view(GalacticNewsView(self.network, next_view))
            else:
                self.window.show_view(next_view)
            return

        self.fetch_error_message = (
            str(msg).strip() or "UNABLE TO LOAD COMMANDER. RECONNECT AND TRY AGAIN."
        ).upper()
        self.no_saves_text.text = self.fetch_error_message

    def on_mouse_motion(self, x, y, dx, dy):
        start_y = SCREEN_HEIGHT - 250
        for i in range(len(self.saves)):
            y_pos = start_y - i * 50
            if (SCREEN_WIDTH // 2 - 250) < x < (SCREEN_WIDTH // 2 + 250) and (
                y_pos - 10
            ) < y < (y_pos + 30):
                self.selected_save = i

    def on_mouse_press(self, x, y, button, modifiers):
        self.on_mouse_motion(x, y, 0, 0)
        self._load_selected()


class GalacticNewsView(arcade.View):
    def __init__(self, network, next_view):
        super().__init__()
        self.network = network
        self.next_view = next_view
        self.font_ui = get_font("ui")
        self.lookback_days = max(
            1, int(self.network.config.get("galactic_news_window_days"))
        )
        self.entries = self.network.get_unseen_galactic_news(
            lookback_days=self.lookback_days
        )
        self.scroll = 0
        self.visible_rows = 8

        self.header_text = arcade.Text(
            f"GALACTIC NEWS // LAST {self.lookback_days} DAYS",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 110,
            COLOR_PRIMARY,
            26,
            anchor_x="center",
            font_name=self.font_ui,
        )
        self.footer_text = arcade.Text(
            "UP/DOWN SCROLL | ENTER OR ESC TO CONTINUE",
            SCREEN_WIDTH // 2,
            80,
            COLOR_TEXT_DIM,
            13,
            anchor_x="center",
            font_name=self.font_ui,
        )

    def _close_news(self):
        self.network.mark_galactic_news_seen()
        self.window.show_view(self.next_view)

    def on_show(self):
        if not self.network and hasattr(self.window, "network"):
            self.network = self.window.network
        arcade.set_background_color(COLOR_BG)

    def on_draw(self):
        self.clear()
        for y in range(0, SCREEN_HEIGHT, 4):
            arcade.draw_line(0, y, SCREEN_WIDTH, y, (0, 0, 0, 28))

        box_x, box_y = 90, 120
        box_w, box_h = SCREEN_WIDTH - 180, SCREEN_HEIGHT - 220
        arcade.draw_lbwh_rectangle_filled(box_x, box_y, box_w, box_h, (10, 16, 26, 230))
        arcade.draw_lbwh_rectangle_outline(
            box_x, box_y, box_w, box_h, COLOR_SECONDARY, 2
        )

        self.header_text.draw()
        self.footer_text.draw()

        if not self.entries:
            arcade.Text(
                "NO NEW GALACTIC BULLETINS.",
                SCREEN_WIDTH // 2,
                SCREEN_HEIGHT // 2,
                COLOR_TEXT_DIM,
                20,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            return

        start = max(0, self.scroll)
        end = min(len(self.entries), start + self.visible_rows)
        y = SCREEN_HEIGHT - 180

        for idx in range(start, end):
            item = self.entries[idx]
            ts = float(item.get("timestamp", 0.0))
            dt = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
            audience = (
                "PERSONAL"
                if str(item.get("audience", "global")) == "player"
                else "GALACTIC"
            )
            planet = item.get("planet")
            title = str(item.get("title", "UPDATE"))
            body = str(item.get("body", ""))

            item_h = 74
            arcade.draw_lbwh_rectangle_filled(
                box_x + 18, y - 10, box_w - 36, item_h, (18, 26, 38, 220)
            )
            arcade.draw_lbwh_rectangle_outline(
                box_x + 18, y - 10, box_w - 36, item_h, (70, 100, 140), 1
            )

            meta = f"[{audience}] {dt}" + (f" :: {planet.upper()}" if planet else "")
            arcade.Text(
                meta,
                box_x + 30,
                y + 46,
                COLOR_SECONDARY,
                10,
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                title.upper(),
                box_x + 30,
                y + 26,
                COLOR_PRIMARY,
                13,
                font_name=self.font_ui,
                width=box_w - 80,
            ).draw()
            arcade.Text(
                body,
                box_x + 30,
                y + 8,
                COLOR_TEXT_DIM,
                10,
                font_name=self.font_ui,
                width=box_w - 80,
            ).draw()
            y -= 82

    def on_key_press(self, key, modifiers):
        if key == arcade.key.UP:
            self.scroll = max(0, self.scroll - 1)
            return
        if key == arcade.key.DOWN:
            max_scroll = max(0, len(self.entries) - self.visible_rows)
            self.scroll = min(max_scroll, self.scroll + 1)
            return
        if key in (arcade.key.ENTER, arcade.key.RETURN, arcade.key.ESCAPE):
            self._close_news()

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        if scroll_y == 0:
            return
        max_scroll = max(0, len(self.entries) - self.visible_rows)
        if scroll_y > 0:
            self.scroll = max(0, self.scroll - 1)
        else:
            self.scroll = min(max_scroll, self.scroll + 1)

    def on_mouse_press(self, x, y, button, modifiers):
        self._close_news()


class CommanderCreationView(arcade.View):
    def __init__(self):
        super().__init__()
        self.network = None
        self.player_name = ""
        self.time_elapsed = 0.0
        self.font_ui = get_font("ui")

        # UI Text Objects
        self.header_text = arcade.Text(
            ">>> NEURAL LINK ESTABLISHED",
            120,
            SCREEN_HEIGHT - 140,
            COLOR_PRIMARY,
            18,
            font_name=self.font_ui,
        )
        self.prompt_text = arcade.Text(
            "INPUT COMMANDER IDENTIFIER:",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2 + 80,
            COLOR_SECONDARY,
            20,
            anchor_x="center",
            font_name=self.font_ui,
        )
        self.input_text = arcade.Text(
            "",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2,
            COLOR_PRIMARY,
            36,
            anchor_x="center",
            anchor_y="center",
            font_name=self.font_ui,
        )
        self.instr_text = arcade.Text(
            "PRESS [ENTER] TO COMMIT | [ESC] TO ABORT",
            SCREEN_WIDTH // 2,
            150,
            COLOR_TEXT_DIM,
            14,
            anchor_x="center",
            font_name=self.font_ui,
        )
        self.error_msg_txt = arcade.Text(
            "",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2 - 80,
            COLOR_ACCENT,
            16,
            anchor_x="center",
            font_name=self.font_ui,
        )
        self.error_timer = 0.0

    def on_show(self):
        if not self.network and hasattr(self.window, "network"):
            self.network = self.window.network
        arcade.set_background_color(COLOR_BG)

    def on_update(self, delta_time: float):
        self.time_elapsed += delta_time
        if self.error_timer > 0:
            self.error_timer -= delta_time
            if self.error_timer <= 0:
                self.error_msg_txt.text = ""

    def on_draw(self):
        self.clear()
        for y in range(0, SCREEN_HEIGHT, 4):
            arcade.draw_line(0, y, SCREEN_WIDTH, y, (0, 0, 0, 30))
        arcade.draw_lbwh_rectangle_outline(
            100, 100, SCREEN_WIDTH - 200, SCREEN_HEIGHT - 200, COLOR_SECONDARY, 2
        )
        arcade.draw_line(
            100,
            SCREEN_HEIGHT - 160,
            SCREEN_WIDTH - 100,
            SCREEN_HEIGHT - 160,
            COLOR_SECONDARY,
            1,
        )

        self.header_text.draw()
        self.prompt_text.draw()

        box_width = 600
        box_height = 80
        box_x = SCREEN_WIDTH // 2 - box_width // 2
        box_y = SCREEN_HEIGHT // 2 - 40
        arcade.draw_lbwh_rectangle_filled(
            box_x, box_y, box_width, box_height, (15, 15, 25)
        )
        arcade.draw_lbwh_rectangle_outline(
            box_x, box_y, box_width, box_height, COLOR_PRIMARY, 1
        )

        cursor = "_" if int(self.time_elapsed * 2.5) % 2 == 0 else " "
        self.input_text.text = f"{self.player_name}{cursor}"
        self.input_text.draw()

        self.instr_text.draw()
        if self.error_timer > 0:
            self.error_msg_txt.draw()

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ENTER or key == arcade.key.RETURN:
            if len(self.player_name.strip()) > 0:
                self.window.show_view(ShipSelectionView(self.player_name.strip()))
        elif key == arcade.key.BACKSPACE:
            self.player_name = self.player_name[:-1]
        elif key == arcade.key.ESCAPE:
            self.window.show_view(MainMenuView())
        elif key == arcade.key.SPACE:
            if len(self.player_name) < 20:
                self.player_name += " "
        elif 32 <= key <= 126:
            if len(self.player_name) < 20:
                char = chr(key).upper()
                if char.isalnum() or char == " ":
                    self.player_name += char

    def on_mouse_press(self, x, y, button, modifiers):
        if len(self.player_name.strip()) > 0:
            self.window.show_view(ShipSelectionView(self.player_name.strip()))


class ShipSelectionView(arcade.View):
    def __init__(self, player_name):
        super().__init__()
        self.network = None
        self.player_name = player_name
        self.ships = load_spaceships()
        self.selected_index = 0
        self.time_elapsed = 0.0
        self.font_ui = get_font("ui")

        # Optimization
        self.header_txt = arcade.Text(
            f"COMMANDER {self.player_name}",
            50,
            SCREEN_HEIGHT - 50,
            COLOR_PRIMARY,
            20,
            font_name=self.font_ui,
        )
        self.asset_txt = arcade.Text(
            ">>> SELECT MISSION ASSET",
            50,
            SCREEN_HEIGHT - 80,
            COLOR_SECONDARY,
            14,
            font_name=self.font_ui,
        )

        self.ship_list_texts = []
        start_y = SCREEN_HEIGHT - 180
        for i, ship in enumerate(self.ships):
            label = ship.model.upper()
            if i == 0:
                label += " [ENTRY CLASS]"
            else:
                label += " [LOCKED]"
            txt = arcade.Text(
                label, 90, start_y - i * 60, COLOR_TEXT_DIM, 18, font_name=self.font_ui
            )
            self.ship_list_texts.append(txt)

        # Error/Locked Message
        self.error_msg_txt = arcade.Text(
            "",
            SCREEN_WIDTH // 2,
            100,
            COLOR_ACCENT,
            20,
            anchor_x="center",
            font_name=self.font_ui,
        )
        self.error_timer = 0

        # Stats Labels
        detail_x, detail_y = 550, SCREEN_HEIGHT - 180
        self.stat_labels = []
        self.stat_values = []
        for i in range(4):
            y = detail_y - 40 - i * 70
            self.stat_labels.append(
                arcade.Text("", detail_x, y, COLOR_TEXT_DIM, 12, font_name=self.font_ui)
            )
            self.stat_values.append(
                arcade.Text(
                    "",
                    detail_x + 540,
                    y,
                    COLOR_PRIMARY,
                    16,
                    anchor_x="right",
                    font_name=self.font_ui,
                )
            )

        self.locked_text = arcade.Text(
            "UNAUTHORIZED ACCESS",
            detail_x + 310,
            detail_y - 400,
            (255, 50, 50),
            24,
            anchor_x="center",
            font_name=self.font_ui,
        )

        self.ship_textures = []
        for i in range(1, 5):
            try:
                self.ship_textures.append(
                    arcade.load_texture(
                        f":resources:images/space_shooter/playerShip{i}_blue.png"
                    )
                )
            except Exception:
                pass

    def on_show(self):
        if not self.network and hasattr(self.window, "network"):
            self.network = self.window.network
        arcade.set_background_color(COLOR_BG)

    def on_update(self, delta_time: float):
        self.time_elapsed += delta_time
        if self.error_timer > 0:
            self.error_timer -= delta_time
            if self.error_timer <= 0:
                self.error_msg_txt.text = ""

    def on_draw(self):
        self.clear()
        header_y = SCREEN_HEIGHT - 60
        self.header_txt.draw()
        self.asset_txt.draw()
        arcade.draw_line(
            50, header_y - 35, SCREEN_WIDTH - 50, header_y - 35, COLOR_SECONDARY, 2
        )

        start_y = SCREEN_HEIGHT - 180
        for i, ship in enumerate(self.ships):
            is_selected = i == self.selected_index
            is_locked = i > 0
            y_pos = start_y - i * 60

            if is_selected:
                color = COLOR_ACCENT if is_locked else COLOR_PRIMARY
                alpha = int(60 + 30 * math.sin(self.time_elapsed * 4))
                arcade.draw_lbwh_rectangle_filled(
                    70, y_pos - 15, 350, 50, (*color, alpha)
                )

            txt = self.ship_list_texts[i]
            if is_selected:
                txt.color = COLOR_ACCENT if is_locked else COLOR_PRIMARY
            else:
                txt.color = (100, 50, 50) if is_locked else COLOR_TEXT_DIM
            txt.draw()

        current_ship = self.ships[self.selected_index]
        is_locked = self.selected_index > 0
        detail_x, detail_y = 550, SCREEN_HEIGHT - 180

        # Dim overall details if locked
        rect_color = (150, 50, 50) if is_locked else COLOR_SECONDARY
        arcade.draw_lbwh_rectangle_outline(
            detail_x - 40, detail_y - 480, 620, 550, rect_color, 1
        )

        stats = [
            (
                "CARGO",
                f"{current_ship.max_cargo_pods}",
                current_ship.max_cargo_pods / 2000,
            ),
            ("SHIELDS", f"{current_ship.max_shields}", current_ship.max_shields / 5000),
            (
                "DEFENDERS",
                f"{current_ship.max_defenders}",
                current_ship.max_defenders / 5000,
            ),
            ("INTEGRITY", "100%", 1.0),
        ]

        for i, (label, val, perc) in enumerate(stats):
            y = detail_y - 40 - i * 70
            lbl = self.stat_labels[i]
            val_txt = self.stat_values[i]
            lbl.text = label
            val_txt.text = val

            # Dim text if locked
            lbl.color = (120, 120, 120) if is_locked else COLOR_TEXT_DIM
            val_txt.color = (150, 70, 70) if is_locked else COLOR_PRIMARY

            lbl.draw()
            val_txt.draw()
            arcade.draw_lbwh_rectangle_filled(detail_x, y - 25, 540, 8, (20, 20, 30))
            bar_color = (100, 40, 40) if is_locked else COLOR_PRIMARY
            arcade.draw_lbwh_rectangle_filled(
                detail_x, y - 25, 540 * min(1.0, perc), 8, bar_color
            )

        if self.ship_textures:
            tex = self.ship_textures[self.selected_index % len(self.ship_textures)]
            # Silhouette locked ships
            if is_locked:
                tex_color = arcade.types.Color(50, 20, 20, 255)
            else:
                tex_color = arcade.types.Color(255, 255, 255, 255)

            arcade.draw_texture_rect(
                tex,
                arcade.XYWH(detail_x + 450, detail_y - 350, 180, 180),
                angle=math.sin(self.time_elapsed) * 5,
                color=tex_color,
            )

        if is_locked:
            self.locked_text.draw()

        self.error_msg_txt.draw()

    def on_key_press(self, key, modifiers):
        if key == arcade.key.UP:
            self.selected_index = (self.selected_index - 1) % len(self.ships)
        elif key == arcade.key.DOWN:
            self.selected_index = (self.selected_index + 1) % len(self.ships)
        elif key == arcade.key.ENTER or key == arcade.key.RETURN:
            if self.selected_index != 0:
                self.error_msg_txt.text = "ERROR: AUTHORIZATION LEVEL INSUFFICIENT"
                self.error_timer = 2.0
                return
            if not self.network and hasattr(self.window, "network"):
                self.network = self.window.network
            if not self.network:
                self.error_msg_txt.text = "ERROR: NETWORK SESSION NOT READY"
                self.error_timer = 2.0
                return
            try:
                success, msg = self.network.new_game(self.player_name)
                if not success:
                    err_text = str(msg).upper() if msg else "ERROR: MISSION INIT FAILED"
                    creation_view = CommanderCreationView()
                    creation_view.error_msg_txt.text = err_text
                    creation_view.error_timer = 5.0
                    creation_view.network = self.network
                    self.window.show_view(creation_view)
                    return
                from views.gameplay import PlanetView

                next_view = PlanetView(self.network)
                if self.network.has_unseen_galactic_news():
                    self.window.show_view(GalacticNewsView(self.network, next_view))
                else:
                    self.window.show_view(next_view)
            except Exception as e:
                import traceback

                traceback.print_exc()
                self.error_msg_txt.text = f"ERROR: LAUNCH FAILED ({type(e).__name__})"
                self.error_timer = 3.0
        elif key == arcade.key.ESCAPE:
            self.window.show_view(CommanderCreationView())

    def on_mouse_motion(self, x, y, dx, dy):
        start_y = SCREEN_HEIGHT - 180
        for i in range(len(self.ships)):
            y_pos = start_y - i * 60
            if 70 < x < 420 and (y_pos - 15) < y < (y_pos + 35):
                self.selected_index = i

    def on_mouse_press(self, x, y, button, modifiers):
        self.on_mouse_motion(x, y, 0, 0)
        self.on_key_press(arcade.key.ENTER, 0)
