# REFACTORED FOR NETWORK CLIENT - All game logic runs on server
import arcade
import arcade.types
import math
import os
import time
import random
import textwrap
from constants import *

# Helper managers for modular gameplay
from .combat_helper import CombatManager
from .trading_helper import TradingManager
from .modules_helper import ModuleManager
from .audio_helper import AudioManager
from .effects_orchestrator import get_orchestrator, update_effects, draw_effects

# GameManager runs on server


TOP_BAND_Y = SCREEN_HEIGHT - 150
LIST_START_Y = SCREEN_HEIGHT - 250
FOOTER_Y = 102

MARKET_ROW_HEIGHT = 40
MARKET_LIST_PAD_BOTTOM = 20
MARKET_LIST_FRAME_EXTRA = 60
MARKET_FOOTER_RESERVED = 92
MARKET_CONTRACT_PANEL_HEIGHT = 124
MARKET_CONTRACT_GAP = 12

COMBAT_WINDOW_W = 920
COMBAT_WINDOW_H = 620


# â”€â”€ Travel helpers (shared with TravelView, WarpView) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
from .travel_helpers import (
    _get_arrival_pause_seconds,
    _get_fuel_usage_multiplier,
    _calculate_travel_fuel_cost,
    _get_warp_travel_duration_seconds,
)


class PlanetView(arcade.View):
    def __init__(
        self,
        game_manager,
        suppress_arrival_popup=False,
        show_wisdom_modal=False,
    ):
        super().__init__()
        self.network = game_manager
        self.time_elapsed = 0.0
        self.font_ui = get_font("ui")
        self.font_ui_bold = get_font("ui_bold")
        self.large_text_mode = bool(
            self.network.config.get("accessibility_large_text_mode", False)
        )
        self.ui_text_scale = 1.18 if self.large_text_mode else 1.0
        self.color_safe_palette = bool(
            self.network.config.get("accessibility_color_safe_palette", False)
        )
        if self.color_safe_palette:
            global COLOR_PRIMARY, COLOR_SECONDARY, COLOR_ACCENT, COLOR_TEXT_DIM
            COLOR_PRIMARY = (64, 220, 255)
            COLOR_SECONDARY = (255, 196, 64)
            COLOR_ACCENT = (255, 92, 92)
            COLOR_TEXT_DIM = (190, 190, 190)

        self.audio_enabled = bool(self.network.config.get("audio_enabled", True))
        self.sfx_channel_volume = {
            "ui": max(
                0.0, min(1.0, float(self.network.config.get("audio_ui_volume", 0.70)))
            ),
            "combat": max(
                0.0,
                min(1.0, float(self.network.config.get("audio_combat_volume", 0.80))),
            ),
            "ambient": max(
                0.0,
                min(1.0, float(self.network.config.get("audio_ambient_volume", 0.45))),
            ),
        }
        self.sfx_assets = {}
        self.mode = "INFO"

        if hasattr(self.network, "_load_shared_planet_states"):
            self.network._load_shared_planet_states()

        p_name = self.network.current_planet.name
        self.bg_texture = None
        bg_path = f"assets/planets/backgrounds/{p_name}.png"
        if os.path.exists(bg_path):
            self.bg_texture = arcade.load_texture(bg_path)

        self.thumb_texture = None
        thumb_path = f"assets/planets/thumbnails/sm_{p_name}.png"
        if os.path.exists(thumb_path):
            self.thumb_texture = arcade.load_texture(thumb_path)

        self.menu_options = ["MARKET", "TRAVEL", "REFUEL", "SYSTEMS"]

        if self.network.config.get("enable_combat", True):
            self.menu_options.insert(1, "ORBIT SCAN")

        if self.network.config.get("enable_mail", True):
            self.menu_options.append("MAIL")

        if self.network.current_planet.name == "Urth":
            idx = (
                self.menu_options.index("MAIL")
                if "MAIL" in self.menu_options
                else len(self.menu_options)
            )
            self.menu_options.insert(idx, "SHIPYARD")

        if self.network.current_planet.bank:
            self.menu_options.insert(self.menu_options.index("TRAVEL"), "BANK")

        if self.network.current_planet.crew_services:
            self.menu_options.insert(self.menu_options.index("SYSTEMS"), "CREW")

        self.menu_options.append("ANALYTICS")
        self.menu_options.append("SAVE")
        self.menu_options.append("LOGOUT")

        self.selected_menu = 0
        self.selected_item_index = 0
        self.market_item_locked = False
        self.selected_target_index = 0
        self.orbit_give_cargo_index = 0
        self.market_scroll = 0
        self.shipyard_scroll = 0
        self.orbital_targets = []
        self.orbit_message = ""
        self.orbit_message_color = COLOR_SECONDARY
        self.orbit_message_type = "info"
        self.orbit_message_timer = 0.0
        self.orbit_message_last = ""
        self.combat_session = None
        self.combat_commitment = 1
        self.combat_report = None
        self.combat_flash_timer = 0.0
        self.combat_flash_color = COLOR_SECONDARY
        self.post_combat_actions = []
        self.combat_effects_enabled = not bool(
            self.network.config.get("reduced_effects_mode", False)
        )
        self.combat_impact_effects = []
        self.combat_spec_weapon_confirm = False
        self.combat_spec_weapon_status = {}  # cached cooldown status from server

        self.combat_player_texture = None
        self.combat_target_texture = None
        if self.combat_effects_enabled:
            try:
                self.combat_player_texture = arcade.load_texture(
                    ":resources:images/space_shooter/playerShip1_blue.png"
                )
            except Exception:
                self.combat_player_texture = None
            try:
                self.combat_target_texture = arcade.load_texture(
                    ":resources:images/space_shooter/playerShip1_red.png"
                )
            except Exception:
                self.combat_target_texture = None

        self.market_message = ""
        self.market_message_timer = 0.0
        self.market_message_last = ""
        self.market_message_type = "info"
        self._timed_popup_queue = []
        self._timed_popup_active = False
        self.compare_mode = False
        self.compare_planet_index = 0
        self.trade_item_name = ""
        self.trade_item_qty = 1
        self.mouse_x = 0
        self.mouse_y = 0
        self.system_message = ""
        self.bank_message = ""
        self.bank_input_mode: str | None = (
            None  # "deposit","withdraw","p_deposit","p_withdraw"
        )
        self.bank_input_text = ""
        self.planet_finance_cache = {}
        self.planet_finance_refresh_elapsed = 0.0
        self.crew_message = ""
        self.selected_ship_index = 0
        self.shipyard_message = ""
        self.prompt_mode = (
            None  # "INSTALL_CHOICE", "CREW_NAMING", "DISPOSAL_CHOICE", "MAIL_COMPOSE"
        )
        self.show_help_overlay = False
        self.naming_crew_member = None
        self.naming_name_input = ""
        self.disposal_specialty = None
        self.action_slider_context = None
        self.action_slider_kind = None
        self.action_slider_item_name = ""
        self.action_slider_direction = None
        self.action_slider_max = 0
        self.action_slider_value = 0
        self.action_slider_dragging = False
        self.commander_status_rows = []
        self.commander_status_error = ""
        self.commander_status_scroll = 0

        # Mail variables
        self.selected_mail_index = 0
        self.viewing_message = None
        self.mail_dropdown_open = False
        self.selected_recipient_index = 0
        self.mail_subject_input = ""
        self.mail_body_input = ""
        self.mail_input_field = "SUBJECT"  # "SUBJECT" or "BODY"
        self.mail_message = ""
        self.last_read_message_id = None
        self.wisdom_modal_active = False
        self.wisdom_modal_text = ""
        self.wisdom_ok_button_rect = (0, 0, 0, 0)
        self._wisdom_lines = self._load_text_asset_lines("absurd_wisdom.txt")
        self._engineer_phrase_lines = self._load_text_asset_lines(
            "engineer_phrases.txt"
        )

        # NPC and Arrival logic
        planet = self.network.current_planet
        planet_npc_remarks = list(getattr(planet, "npc_remarks", []) or [])
        if not planet_npc_remarks:
            planet_npc_remarks = ["Good day.", "What do you need?", "Let's trade."]
        self.npc_remark = random.choice(planet_npc_remarks)
        self.arrival_msg = getattr(planet, "welcome_msg", "Docking request approved.")

        # Add crew remark if available
        pl = self.network.player
        remark = ""
        if "engineer" in pl.crew:
            remark = pl.crew["engineer"].get_remark("arrival")
        elif "weapons" in pl.crew:
            remark = pl.crew["weapons"].get_remark("arrival")

        engineer_phrase = self._get_random_engineer_phrase()
        if engineer_phrase and "engineer" in pl.crew and random.random() < 0.60:
            remark = str(engineer_phrase)

        if suppress_arrival_popup:
            self.arrival_msg = ""
            self.arrival_msg_timer = 0.0
        else:
            if remark:
                self.arrival_msg += f'\n"{remark}"'

            docking_fee = self.network.get_docking_fee(
                planet, self.network.player.spaceship
            )
            if docking_fee > 0:
                self.arrival_msg += f" (DOCKING FEE: {docking_fee} CR)"
            self.arrival_msg_timer = 5.0  # Message stays for 5 seconds

        # Arrival Pause Logic
        self.arrival_pause_timer = 0.0
        pause_duration = _get_arrival_pause_seconds(
            self.network, default_value=0.0, refresh_config=True
        )
        if self.arrival_msg and pause_duration > 0 and not suppress_arrival_popup:
            self.arrival_pause_timer = pause_duration

        if bool(show_wisdom_modal):
            wisdom_text = (
                random.choice(self._wisdom_lines) if self._wisdom_lines else ""
            )
            if wisdom_text:
                self.wisdom_modal_text = wisdom_text
                self.wisdom_modal_active = True

        # UI Text Objects for stability and performance
        self.planet_name_txt = arcade.Text(
            self.network.current_planet.name.upper(),
            150,
            SCREEN_HEIGHT - 230,
            COLOR_PRIMARY,
            24,
            anchor_x="center",
            font_name=self.font_ui,
        )
        self.menu_texts = [
            arcade.Text(
                opt, 40, 500 - i * 45, COLOR_TEXT_DIM, 18, font_name=self.font_ui
            )
            for i, opt in enumerate(self.menu_options)
        ]

        self.status_bar_txt = arcade.Text(
            "", 310, 18, COLOR_PRIMARY, 12, anchor_y="center", font_name=self.font_ui
        )
        self.fuel_label = arcade.Text(
            "FUEL:",
            SCREEN_WIDTH - 240,
            46,
            COLOR_TEXT_DIM,
            12,
            anchor_y="center",
            font_name=self.font_ui,
        )

        # Content texts
        content_x, content_y = 350, SCREEN_HEIGHT - 80
        self.header_txt = arcade.Text(
            "", content_x, content_y, COLOR_SECONDARY, 24, font_name=self.font_ui
        )
        self.desc_txt = arcade.Text(
            self.network.current_planet.description,
            content_x,
            content_y - 60,
            COLOR_PRIMARY,
            16,
            width=SCREEN_WIDTH - 400,
            font_name=self.font_ui,
            multiline=True,
        )
        self.vendor_txt = arcade.Text(
            "", content_x, content_y - 40, COLOR_TEXT_DIM, 14, font_name=self.font_ui
        )

        self.market_instr = arcade.Text(
            "KEYS: [W/S] SELECT | [B] BUY | [V] SELL | [C] COMPARE | [ESC] BACK",
            content_x,
            120,
            COLOR_SECONDARY,
            14,
            font_name=self.font_ui,
        )
        self.market_msg_txt = arcade.Text(
            "", content_x, 68, COLOR_ACCENT, 16, font_name=self.font_ui_bold
        )

        # Market side panel buttons
        self.market_buttons = []
        # Buy/Sell buttons will be defined by their rects during draw/logic

        # Info/Refuel specific (6 stat lines: owner, pop, governance, defenders, shields, treasury)
        self.info_stat_texts = [
            arcade.Text("", content_x, 0, COLOR_TEXT_DIM, 14, font_name=self.font_ui)
            for _ in range(6)
        ]
        self.refuel_status_txt = arcade.Text(
            "", content_x, content_y - 100, COLOR_PRIMARY, 20, font_name=self.font_ui
        )
        self.refuel_cost_txt = arcade.Text(
            "", content_x, content_y - 120, COLOR_PRIMARY, 20, font_name=self.font_ui
        )
        self.refuel_instr_txt = arcade.Text(
            "PRESS [F] TO PURCHASE FUEL",
            content_x,
            content_y - 180,
            (255, 255, 255),
            16,
            font_name=self.font_ui,
        )
        self.refuel_timer_txt = arcade.Text(
            "", content_x, content_y - 240, COLOR_SECONDARY, 14, font_name=self.font_ui
        )

        # Market Headers
        y_off = content_y - 100
        self.m_hdr_item = arcade.Text(
            "ITEM", content_x, y_off, COLOR_SECONDARY, 14, font_name=self.font_ui_bold
        )
        self.m_hdr_price = arcade.Text(
            "PRICE",
            content_x + 390,
            y_off,
            COLOR_SECONDARY,
            14,
            anchor_x="right",
            font_name=self.font_ui_bold,
        )
        self.m_hdr_cargo = arcade.Text(
            "CARGO",
            content_x + 500,
            y_off,
            COLOR_SECONDARY,
            14,
            anchor_x="right",
            font_name=self.font_ui_bold,
        )
        self.m_hdr_compare = arcade.Text(
            "",
            content_x + 650,
            y_off,
            COLOR_SECONDARY,
            14,
            anchor_x="right",
            font_name=self.font_ui_bold,
        )

        # Pool for market rows
        self.market_row_texts = []
        for i in range(40):  # Support up to 40 items
            row = {
                "name": arcade.Text(
                    "", content_x, 0, COLOR_TEXT_DIM, 14, font_name=self.font_ui
                ),
                "price": arcade.Text(
                    "",
                    content_x + 390,
                    0,
                    COLOR_TEXT_DIM,
                    14,
                    anchor_x="right",
                    font_name=self.font_ui,
                ),
                "cargo": arcade.Text(
                    "",
                    content_x + 500,
                    0,
                    COLOR_TEXT_DIM,
                    14,
                    anchor_x="right",
                    font_name=self.font_ui,
                ),
                "compare": arcade.Text(
                    "",
                    content_x + 650,
                    0,
                    COLOR_TEXT_DIM,
                    14,
                    anchor_x="right",
                    font_name=self.font_ui,
                ),
            }
            self.market_row_texts.append(row)

        # Sidebar Stat Texts
        y_sidebar = SCREEN_HEIGHT - 265
        self.sidebar_label_texts = []
        self.sidebar_val_texts = []
        for i, lbl in enumerate(
            ["INTEGRITY", "SHIELDS", "CARGO", "DEFENDERS", "AUTH", "FRONT"]
        ):
            y = y_sidebar - i * 22
            self.sidebar_label_texts.append(
                arcade.Text(lbl, 40, y, COLOR_TEXT_DIM, 10, font_name=self.font_ui)
            )
            self.sidebar_val_texts.append(
                arcade.Text(
                    "",
                    260,
                    y,
                    COLOR_PRIMARY,
                    12,
                    anchor_x="right",
                    font_name=self.font_ui_bold,
                )
            )

        self._load_audio_assets()
        self._apply_accessibility_text_scale()

    def _load_audio_assets(self):
        if not self.audio_enabled:
            self.sfx_assets = {}
            return

        def _try_load(path):
            try:
                return arcade.load_sound(path)
            except Exception:
                return None

        self.sfx_assets = {
            "ui_move": _try_load(":resources:sounds/coin1.wav"),
            "ui_confirm": _try_load(":resources:sounds/upgrade5.wav"),
            "combat_fire": _try_load(":resources:sounds/laser2.wav"),
            "combat_hit": _try_load(":resources:sounds/hit5.wav"),
            "ambient_dock": _try_load(":resources:sounds/jump1.wav"),
            "combat_special": _try_load(":resources:sounds/explosion2.wav"),
        }

    def _play_sfx(self, channel, sound_key):
        if not self.audio_enabled:
            return
        sound = self.sfx_assets.get(str(sound_key))
        if not sound:
            return
        volume = float(self.sfx_channel_volume.get(str(channel), 0.7))
        if volume <= 0.0:
            return
        try:
            arcade.play_sound(sound, volume=volume)
        except Exception:
            return

    def _apply_accessibility_text_scale(self):
        if self.ui_text_scale <= 1.0:
            return

        def _scale_text(obj):
            if isinstance(obj, arcade.Text):
                try:
                    obj.font_size = int(
                        max(8, round(float(obj.font_size) * self.ui_text_scale))
                    )
                except Exception:
                    return

        for value in self.__dict__.values():
            if isinstance(value, arcade.Text):
                _scale_text(value)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, arcade.Text):
                        _scale_text(item)
                    elif isinstance(item, dict):
                        for d_val in item.values():
                            if isinstance(d_val, arcade.Text):
                                _scale_text(d_val)
            elif isinstance(value, dict):
                for item in value.values():
                    if isinstance(item, arcade.Text):
                        _scale_text(item)

    def on_show(self):
        arcade.set_background_color(COLOR_BG)
        self._play_sfx("ambient", "ambient_dock")

    def _draw_sidebar_stats(self):
        ship = self.network.player.spaceship
        cargo_used = sum(self.network.player.inventory.values())

        # Calculate integrity percentage
        integ_perc = (
            int((ship.integrity / ship.max_integrity) * 100)
            if ship.max_integrity > 0
            else 0
        )

        stats = [
            (f"{integ_perc}%", COLOR_PRIMARY if integ_perc > 30 else COLOR_ACCENT),
            (f"{int(ship.current_shields)}/{int(ship.max_shields)}", COLOR_PRIMARY),
            (
                f"{int(cargo_used)}/{int(ship.current_cargo_pods)}",
                COLOR_PRIMARY if cargo_used < ship.current_cargo_pods else COLOR_ACCENT,
            ),
            (
                f"{int(ship.current_defenders)}/{int(ship.max_defenders)}",
                COLOR_PRIMARY if int(ship.current_defenders) > 0 else COLOR_ACCENT,
            ),
            (
                f"{int(getattr(self.network.player, 'authority_standing', getattr(self.network.player, 'sector_reputation', 0))):+d} {self.network.get_authority_standing_label()}",
                COLOR_SECONDARY,
            ),
            (
                f"{int(getattr(self.network.player, 'frontier_standing', 0)):+d} {self.network.get_frontier_standing_label()}",
                COLOR_SECONDARY,
            ),
        ]

        for i, (val, color) in enumerate(stats):
            self.sidebar_label_texts[i].draw()
            # Update specific properties for the current frame
            self.sidebar_val_texts[i].text = val
            self.sidebar_val_texts[i].color = color
            self.sidebar_val_texts[i].draw()

    def _draw_btn(self, x, y, w, h, text, color, enabled=True):
        # Hover check
        hover = enabled and (x <= self.mouse_x <= x + w and y <= self.mouse_y <= y + h)

        alpha = 255 if hover else (180 if enabled else 60)
        bg_color = (*color, alpha)
        arcade.draw_lbwh_rectangle_filled(x, y, w, h, bg_color)
        arcade.draw_lbwh_rectangle_outline(
            x, y, w, h, COLOR_PRIMARY if enabled else COLOR_TEXT_DIM, 2
        )

        text_color = (
            COLOR_BG if hover else (COLOR_PRIMARY if enabled else COLOR_TEXT_DIM)
        )

        arcade.Text(
            text,
            x + w / 2,
            y + h / 2,
            text_color,
            11,
            anchor_x="center",
            anchor_y="center",
            font_name=self.font_ui_bold,
        ).draw()

    def _load_text_asset_lines(self, filename):
        lines = []
        path = os.path.join("assets", "texts", str(filename or "").strip())
        if not os.path.exists(path):
            return lines
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for raw in handle:
                    line = str(raw or "").strip().strip('"')
                    if line:
                        lines.append(line)
        except Exception:
            return []
        return lines

    def _get_random_engineer_phrase(self):
        if not self._engineer_phrase_lines:
            return ""
        return str(random.choice(self._engineer_phrase_lines))

    def _normalize_market_required_level(self, required_level, max_level):
        try:
            raw = max(0, int(required_level))
        except (TypeError, ValueError):
            raw = 0

        try:
            max_lv = max(1, int(max_level))
        except (TypeError, ValueError):
            max_lv = 3

        if max_lv != 3 and raw <= 3:
            raw = int(round((float(raw) / 3.0) * float(max_lv)))

        return max(0, min(max_lv, raw))

    def _draw_wisdom_modal(self):
        if not self.wisdom_modal_active:
            return

        arcade.draw_lbwh_rectangle_filled(
            0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 205)
        )

        box_w, box_h = 920, 360
        bx = SCREEN_WIDTH // 2 - box_w // 2
        by = SCREEN_HEIGHT // 2 - box_h // 2
        arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (6, 14, 24, 248))
        arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_PRIMARY, 2)

        arcade.Text(
            "ABSURD WISDOM FEED",
            bx + box_w // 2,
            by + box_h - 52,
            COLOR_PRIMARY,
            22,
            anchor_x="center",
            font_name=self.font_ui_bold,
        ).draw()

        wisdom_text = self._wrap_market_text(
            self.wisdom_modal_text, max_chars=74, max_lines=6
        )
        arcade.Text(
            wisdom_text,
            bx + box_w // 2,
            by + box_h // 2 + 24,
            (220, 236, 255),
            18,
            anchor_x="center",
            anchor_y="center",
            multiline=True,
            width=box_w - 120,
            align="center",
            font_name=self.font_ui,
        ).draw()

        ok_w, ok_h = 180, 44
        ok_x = bx + box_w // 2 - ok_w // 2
        ok_y = by + 34
        self.wisdom_ok_button_rect = (ok_x, ok_y, ok_w, ok_h)
        self._draw_btn(ok_x, ok_y, ok_w, ok_h, "OK", COLOR_ACCENT, enabled=True)

    def _get_visible_market_items(self):
        planet = self.network.current_planet
        items = []
        seen = set()
        bribe_level = 0
        bribe_max_level = 3
        try:
            snapshot = self.network.get_bribe_market_snapshot(planet.name) or {}
            bribe_level = int(snapshot.get("level", 0))
            bribe_max_level = max(1, int(snapshot.get("max_level", 3) or 3))
        except Exception:
            bribe_level = 0
            bribe_max_level = 3

        for item_name, base_price in dict(getattr(planet, "items", {}) or {}).items():
            effective_price = self.network.get_effective_buy_price(
                item_name, base_price, planet.name
            )
            items.append((item_name, effective_price))
            seen.add(item_name)

        smuggling_inventory = dict(getattr(planet, "smuggling_inventory", {}) or {})
        for s_item, data in smuggling_inventory.items():
            if s_item in seen:
                continue
            if int(data.get("quantity", 0)) <= 0:
                continue
            required_level = self._normalize_market_required_level(
                data.get("required_bribe_level", 0), bribe_max_level
            )
            if bool(getattr(planet, "is_smuggler_hub", False)) and required_level <= 0:
                pass
            elif bribe_level < required_level:
                continue

            smuggle_base = data.get("price")
            if smuggle_base is None:
                continue
            try:
                smuggle_base = int(smuggle_base)
            except (TypeError, ValueError):
                continue
            if smuggle_base <= 0:
                continue
            effective_smuggle = self.network.get_effective_buy_price(
                s_item, smuggle_base, planet.name
            )
            items.append((s_item, effective_smuggle))
            seen.add(s_item)

        # Ensure loot-only cargo can be selected and sold in market.
        for inv_item in sorted(self.network.player.inventory.keys()):
            if inv_item in seen:
                continue
            salvage_price = self.network.get_market_sell_price(inv_item, planet.name)
            items.append((inv_item, salvage_price))

        items.sort(key=lambda pair: str(pair[0]).lower())
        return items

    def _is_item_buyable_in_market(self, item_name):
        planet = self.network.current_planet
        if item_name in dict(getattr(planet, "items", {}) or {}):
            return True
        smuggling_inventory = dict(getattr(planet, "smuggling_inventory", {}) or {})
        if item_name in smuggling_inventory:
            data = dict(smuggling_inventory.get(item_name, {}) or {})
            max_level = 3
            try:
                snapshot = self.network.get_bribe_market_snapshot(planet.name) or {}
                current_level = int(snapshot.get("level", 0))
                max_level = max(1, int(snapshot.get("max_level", 3) or 3))
            except Exception:
                current_level = 0
                max_level = 3
            required_level = self._normalize_market_required_level(
                data.get("required_bribe_level", 0), max_level
            )
            if bool(getattr(planet, "is_smuggler_hub", False)) and required_level <= 0:
                return True
            return current_level >= required_level
        return False

    def _format_duration_hm(self, total_seconds):
        total_seconds = max(0, int(total_seconds))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}H {minutes:02d}M"

    def _clamp_text(self, text, max_chars):
        value = str(text or "").replace("\n", " ").strip()
        if max_chars <= 3:
            return value[:max_chars]
        return value if len(value) <= max_chars else (value[: max_chars - 3] + "...")

    def _wrap_market_text(self, text, max_chars=72, max_lines=2):
        value = str(text or "").replace("\n", " ").strip()
        if not value:
            return ""
        lines = textwrap.wrap(value, width=max(12, int(max_chars)))
        if len(lines) <= max_lines:
            return "\n".join(lines)
        kept = lines[:max_lines]
        last = kept[-1]
        if len(last) > 3:
            kept[-1] = last[:-3].rstrip() + "..."
        else:
            kept[-1] = "..."
        return "\n".join(kept)

    def _refresh_planet_finance_cache(self, force=False):
        if (not force) and self.planet_finance_refresh_elapsed < 0.75:
            return
        try:
            self.planet_finance_cache = self.network.get_planet_financials() or {}
        except Exception:
            self.planet_finance_cache = {}
        self.planet_finance_refresh_elapsed = 0.0

    def _digit_from_key(self, key):
        key_0 = getattr(arcade.key, "_0", getattr(arcade.key, "KEY_0", None))
        key_9 = getattr(arcade.key, "_9", getattr(arcade.key, "KEY_9", None))
        if key_0 is not None and key_9 is not None and key_0 <= key <= key_9:
            return str(key - key_0)

        num_0 = getattr(arcade.key, "NUM_0", None)
        num_9 = getattr(arcade.key, "NUM_9", None)
        if num_0 is not None and num_9 is not None and num_0 <= key <= num_9:
            return str(key - num_0)

        return None

    def _confirm_bank_input(self):
        """Execute the bank transaction entered via the custom-amount input overlay."""
        try:
            amount = int(self.bank_input_text)
        except (ValueError, TypeError):
            self.bank_message = "INVALID AMOUNT."
            return
        if amount <= 0:
            self.bank_message = "AMOUNT MUST BE GREATER THAN ZERO."
            return

        mode = self.bank_input_mode
        if mode == "deposit":
            success, msg = self.network.bank_deposit(amount)
        elif mode == "withdraw":
            success, msg = self.network.bank_withdraw(amount)
        elif mode == "p_deposit":
            success, msg = self.network.planet_deposit(amount)
        elif mode == "p_withdraw":
            success, msg = self.network.planet_withdraw(amount)
        else:
            return

        self.bank_message = msg
        if success:
            if mode in ("p_deposit", "p_withdraw"):
                self._refresh_planet_finance_cache(force=True)
            self.network.save_game()

        self.prompt_mode = None
        self.bank_input_mode = None
        self.bank_input_text = ""

    def _market_visible_rows(self):
        return 11

    def _classify_message_type(self, message, default_type="info"):
        msg = str(message or "").upper()
        if not msg:
            return default_type

        error_markers = [
            "ERROR",
            "FAILED",
            "INSUFFICIENT",
            "DENIED",
            "INVALID",
            "BLOCKED",
            "NOT ENOUGH",
            "NO ",
            "UNABLE",
        ]
        warning_markers = [
            "WARNING",
            "ALERT",
            "LOCKED",
            "SANCTION",
            "HOSTILE",
            "RISK",
            "DETECTED",
        ]
        success_markers = [
            "SUCCESS",
            "SOLD",
            "PURCHASED",
            "COMPLETE",
            "INSTALLED",
            "TRANSFERRED",
            "PAID",
            "UNLOCKED",
            "ACCEPTED",
            "CLAIMED",
            "STORED",
        ]

        if any(marker in msg for marker in error_markers):
            return "error"
        if any(marker in msg for marker in warning_markers):
            return "warning"
        if any(marker in msg for marker in success_markers):
            return "success"
        return default_type

    def _message_style(self, message_type):
        styles = {
            "success": {"color": COLOR_PRIMARY, "duration": 2.4},
            "warning": {"color": COLOR_ACCENT, "duration": 3.0},
            "error": {"color": COLOR_ACCENT, "duration": 3.5},
            "info": {"color": COLOR_SECONDARY, "duration": 2.8},
        }
        return styles.get(message_type, styles["info"])

    def _get_market_layout(self, item_count):
        min_rows = 4
        row_h = MARKET_ROW_HEIGHT
        top_band_y = TOP_BAND_Y
        list_start_y = LIST_START_Y
        footer_y = FOOTER_Y
        contract_h = MARKET_CONTRACT_PANEL_HEIGHT

        min_list_bottom = (
            footer_y + MARKET_FOOTER_RESERVED + contract_h + MARKET_CONTRACT_GAP
        )
        max_rows_fit = max(
            min_rows,
            int((list_start_y - (min_list_bottom + MARKET_LIST_PAD_BOTTOM)) // row_h),
        )

        visible_rows = min(self._market_visible_rows(), max_rows_fit)
        if item_count > 0:
            visible_rows = max(min_rows, min(visible_rows, item_count))
        else:
            visible_rows = min_rows

        list_bottom = list_start_y - (visible_rows * row_h) - MARKET_LIST_PAD_BOTTOM
        contract_y = max(
            footer_y + MARKET_FOOTER_RESERVED,
            list_bottom - (contract_h + MARKET_CONTRACT_GAP),
        )

        return {
            "top_band_y": top_band_y,
            "list_start_y": list_start_y,
            "footer_y": footer_y,
            "visible_rows": visible_rows,
            "list_bottom": list_bottom,
            "contract_y": contract_y,
        }

    def _draw_trade_contract_panel(self, x, y):
        contract = self.network.get_active_trade_contract()
        panel_w, panel_h = 520, MARKET_CONTRACT_PANEL_HEIGHT
        reroll_cost = int(self.network.config.get("contract_reroll_cost", 600))

        arcade.draw_lbwh_rectangle_filled(x, y, panel_w, panel_h, (8, 14, 20, 220))
        arcade.draw_lbwh_rectangle_outline(x, y, panel_w, panel_h, COLOR_SECONDARY, 1)

        if not contract:
            arcade.Text(
                "NO ACTIVE TRADE CONTRACT",
                x + 12,
                y + panel_h - 28,
                COLOR_TEXT_DIM,
                11,
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                f"TRAVEL FOR NEW CONTRACTS OR PRESS [K] TO REROLL ({reroll_cost:,} CR).",
                x + 12,
                y + 16,
                COLOR_TEXT_DIM,
                10,
                font_name=self.font_ui,
            ).draw()
            return

        qty = int(contract.get("quantity", 0))
        delivered = int(contract.get("delivered", 0))
        remaining = int(contract.get("remaining_qty", max(0, qty - delivered)))
        reward = int(contract.get("reward", 0))
        chain_bonus_pct = int(contract.get("chain_bonus_pct", 0))
        item = contract.get("item", "Cargo")
        destination = contract.get("destination_planet", "Unknown")
        remaining_time = self._format_duration_hm(contract.get("remaining_seconds", 0))
        route_type = str(contract.get("route_type", "LEGAL")).upper()
        arc_step = int(contract.get("arc_step", 1))
        arc_total = int(contract.get("arc_total_steps", 1))
        contract_title = self._clamp_text(
            f"CONTRACT: DELIVER {str(item).upper()} TO {str(destination).upper()}",
            64,
        )
        progress_line = self._clamp_text(
            f"{route_type} ARC {arc_step}/{arc_total}  |  PROGRESS: {delivered}/{qty}  |  REMAINING: {remaining}  |  BONUS: {reward:,} CR  |  CHAIN: +{chain_bonus_pct}%  |  ETA: {remaining_time}",
            86,
        )
        contract_title_wrapped = self._wrap_market_text(contract_title, 48, 2)
        progress_wrapped = self._wrap_market_text(progress_line, 88, 2)

        arcade.Text(
            contract_title_wrapped,
            x + 12,
            y + panel_h - 24,
            COLOR_PRIMARY,
            11,
            font_name=self.font_ui_bold,
            width=panel_w - 24,
            multiline=True,
        ).draw()
        arcade.Text(
            progress_wrapped,
            x + 12,
            y + 36,
            COLOR_TEXT_DIM,
            10,
            font_name=self.font_ui,
            width=panel_w - 24,
            multiline=True,
        ).draw()
        arcade.Text(
            f"[K] REROLL CONTRACT ({reroll_cost:,} CR)",
            x + panel_w - 12,
            y + 16,
            COLOR_SECONDARY,
            10,
            anchor_x="right",
            font_name=self.font_ui,
        ).draw()

    def _get_market_row_colors(self, item_name, current_price, comparison_planet=None):
        neutral_color = COLOR_SECONDARY

        if comparison_planet and item_name in comparison_planet.items:
            compare_price = self.network.get_effective_buy_price(
                item_name,
                comparison_planet.items[item_name],
                comparison_planet.name,
            )
            delta = compare_price - current_price
            if delta > 0:
                return COLOR_PRIMARY, COLOR_PRIMARY
            if delta < 0:
                return COLOR_ACCENT, COLOR_ACCENT
            return neutral_color, neutral_color

        snapshot = self.network.get_item_market_snapshot(
            item_name, self.network.current_planet.name
        )
        if not snapshot:
            return neutral_color, neutral_color

        avg_price = max(1, int(snapshot.get("avg_price", current_price)))
        if current_price <= int(avg_price * 0.92):
            return COLOR_PRIMARY, neutral_color
        if current_price >= int(avg_price * 1.08):
            return COLOR_ACCENT, neutral_color
        return neutral_color, neutral_color

    def _draw_help_overlay(self):
        box_w, box_h = 980, 620
        bx = SCREEN_WIDTH // 2 - box_w // 2
        by = SCREEN_HEIGHT // 2 - box_h // 2

        arcade.draw_lbwh_rectangle_filled(
            0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 210)
        )
        arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (12, 18, 28, 248))
        arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_PRIMARY, 2)

        arcade.Text(
            "COMMAND REFERENCE",
            bx + box_w // 2,
            by + box_h - 45,
            COLOR_PRIMARY,
            22,
            anchor_x="center",
            font_name=self.font_ui_bold,
        ).draw()

        common_lines = [
            "GLOBAL: [UP/DOWN] MENU | [ENTER] SELECT | [ESC] BACK TO INFO",
            "GLOBAL: [F1] TOGGLE THIS HELP | [F8] OPEN ANALYTICS DASHBOARD",
            "GLOBAL: [MOUSE] HOVER + CLICK INTERACTIVE PANELS",
        ]

        mode_lines = {
            "MARKET": [
                "MARKET: [W/S] SELECT ITEM | [B] BUY | [V] SELL | [C] COMPARE",
                "MARKET: [A/D] CYCLE COMPARE PLANET | [ENTER] BUY SELECTED",
                "MARKET: [R] BRIBE CONTACT (WHERE AVAILABLE) | [J] QUICK-SELL SALVAGE | [K] REROLL CONTRACT",
                "MARKET: CLICK SELECTED ROW TO LOCK/UNLOCK ITEM SCROLL",
            ],
            "ORBIT": [
                "ORBIT: [W/S] SELECT TARGET | [ENTER] ENGAGE TARGET",
                "ORBIT: USE ACTION BUTTONS IN TARGET DETAIL PANEL",
                "ORBIT (OWNED PLANET): [â†] LEAVE FIGHTERS | [â†’] TAKE FIGHTERS | [â†‘] ASSIGN SHIELDS | [â†“] TAKE SHIELDS",
            ],
            "SYSTEMS": [
                "SYSTEMS: CLICK INSTALL / INSTALL MAX FOR SHIP COMPONENTS",
                "SYSTEMS: PRESS [I] TO AUTO-FIT ALL POSSIBLE CARGO UPGRADES",
                "SYSTEMS: CLICK REPAIR BUTTON WHEN FACILITIES ARE AVAILABLE",
            ],
            "MAIL": [
                "MAIL: [â†/â†’] SELECT MESSAGE | [N] COMPOSE | [R] REPLY | [DELETE] REMOVE",
                "MAIL: [F5] REFRESH INBOX",
                "MAIL COMPOSE: [LEFT/RIGHT] RECIPIENT | [TAB] SWITCH FIELD | [ENTER] SEND",
            ],
            "SHIPYARD": [
                "SHIPYARD: [W/S] SELECT SHIP | [ENTER] PURCHASE",
            ],
            "REFUEL": [
                "REFUEL: [F] PURCHASE REQUIRED FUEL",
            ],
            "BANK": [
                "BANK: USE ON-SCREEN BUTTONS FOR DEPOSIT/WITHDRAW",
            ],
            "CREW": [
                "CREW: USE ON-SCREEN BUTTONS TO HIRE OR DISMISS CREW",
            ],
        }

        lines = common_lines + mode_lines.get(
            self.mode, ["INFO: SELECT A MENU OPTION TO BEGIN"]
        )

        y = by + box_h - 95
        for line in lines:
            arcade.Text(
                line,
                bx + 30,
                y,
                COLOR_TEXT_DIM,
                13,
                font_name=self.font_ui,
                width=box_w - 60,
            ).draw()
            y -= 36

        arcade.Text(
            "TIP: INSTALL MAX IN SYSTEMS APPLIES ALL POSSIBLE UPGRADES FROM CARGO.",
            bx + 30,
            by + 70,
            COLOR_SECONDARY,
            12,
            font_name=self.font_ui_bold,
            width=box_w - 60,
        ).draw()
        arcade.Text(
            "[ESC] OR [F1] TO CLOSE",
            bx + box_w // 2,
            by + 28,
            COLOR_TEXT_DIM,
            12,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()

    def _combat_window_rects(self):
        w, h = COMBAT_WINDOW_W, COMBAT_WINDOW_H
        x = SCREEN_WIDTH // 2 - w // 2
        y = SCREEN_HEIGHT // 2 - h // 2
        return {
            "window": (x, y, w, h),
            "minus": (x + 40, y + 190, 60, 40),
            "plus": (x + 300, y + 190, 60, 40),
            "attack": (x + 390, y + 180, 190, 55),
            "cancel": (x + 600, y + 180, 220, 55),
            "special_weapon": (x + 390, y + 242, 430, 32),
            "sw_confirm_yes": (x + 140, y + 225, 300, 42),
            "sw_confirm_no": (x + 460, y + 225, 300, 42),
            "post_autofit": (x + 30, y + 200, 160, 40),
            "post_repair": (x + 205, y + 200, 160, 40),
            "post_close": (x + 30, y + 155, 335, 35),
            "post_systems": (x + 390, y + 155, 190, 35),
        }

    def _snapshot_post_combat_state(self):
        ship = self.network.player.spaceship
        return {
            "credits": int(self.network.player.credits),
            "integrity": int(ship.integrity),
            "shields": int(ship.current_shields),
            "fighters": int(ship.current_defenders),
            "cargo": int(sum(self.network.player.inventory.values())),
        }

    def _record_post_combat_action(self, label, before_state, after_state, result_msg):
        deltas = []

        def _delta(key, title):
            old = int(before_state.get(key, 0))
            new = int(after_state.get(key, 0))
            if old == new:
                return None
            diff = new - old
            sign = "+" if diff > 0 else ""
            return f"{title} {sign}{diff}"

        for key, title in [
            ("credits", "CR"),
            ("integrity", "HULL"),
            ("shields", "SHLD"),
            ("fighters", "FIG"),
            ("cargo", "CARGO"),
        ]:
            piece = _delta(key, title)
            if piece:
                deltas.append(piece)

        delta_text = " | ".join(deltas) if deltas else "NO SYSTEM DELTA"
        msg_part = self._clamp_text(str(result_msg or "").upper(), 56)
        if msg_part:
            line = f"{label}: {delta_text} :: {msg_part}"
        else:
            line = f"{label}: {delta_text}"

        self.post_combat_actions.insert(0, line)
        self.post_combat_actions = self.post_combat_actions[:3]

    def _get_repair_preview(self):
        ship = self.network.player.spaceship
        planet = self.network.current_planet
        if planet.repair_multiplier is None:
            return False, "NO REPAIR FACILITY HERE"
        if ship.integrity >= ship.max_integrity:
            return False, "HULL ALREADY MAX"

        repair_needed = ship.max_integrity - ship.integrity
        cost_per_percent = (ship.cost * 0.002) * planet.repair_multiplier
        total_cost = int(
            (repair_needed / (ship.max_integrity / 100)) * cost_per_percent
        )
        if total_cost < 1:
            total_cost = 1

        if self.network.player.credits >= total_cost:
            return True, f"REPAIR PREVIEW: {total_cost:,} CR"
        shortfall = total_cost - int(self.network.player.credits)
        return False, f"REPAIR PREVIEW: {total_cost:,} CR (SHORT {shortfall:,})"

    def _queue_combat_effect(self, effect_type, duration=0.32):
        if not self.combat_effects_enabled:
            return
        self.combat_impact_effects.append(
            {
                "type": str(effect_type),
                "ttl": float(duration),
                "max_ttl": float(duration),
            }
        )
        if len(self.combat_impact_effects) > 16:
            self.combat_impact_effects = self.combat_impact_effects[-16:]

    def _draw_combat_visual_layer(self, rects):
        if not self.combat_effects_enabled:
            return

        x, y, w, h = rects["window"]
        p_x = x + 220
        p_y = y + 365 + math.sin(self.time_elapsed * 2.8) * 5
        t_x = x + w - 220
        t_y = y + 365 + math.sin((self.time_elapsed * 2.8) + 1.2) * 5

        arcade.draw_line(p_x + 40, p_y - 30, t_x - 40, t_y - 30, (40, 60, 84), 1)

        if self.combat_player_texture:
            arcade.draw_texture_rect(
                self.combat_player_texture,
                arcade.XYWH(p_x, p_y, 120, 120),
                angle=-8 + math.sin(self.time_elapsed * 2.0) * 3,
            )
        else:
            arcade.draw_triangle_filled(
                p_x - 42,
                p_y - 20,
                p_x - 42,
                p_y + 20,
                p_x + 48,
                p_y,
                COLOR_PRIMARY,
            )

        if self.combat_target_texture:
            arcade.draw_texture_rect(
                self.combat_target_texture,
                arcade.XYWH(t_x, t_y, 120, 120),
                angle=170 + math.sin((self.time_elapsed * 2.0) + 0.7) * 3,
            )
        else:
            arcade.draw_triangle_filled(
                t_x + 42,
                t_y - 20,
                t_x + 42,
                t_y + 20,
                t_x - 48,
                t_y,
                COLOR_ACCENT,
            )

        arcade.Text(
            "PLAYER VESSEL",
            p_x,
            y + 285,
            COLOR_SECONDARY,
            10,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()
        arcade.Text(
            "TARGET",
            t_x,
            y + 285,
            COLOR_SECONDARY,
            10,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()

        for idx, effect in enumerate(self.combat_impact_effects):
            ttl = float(effect.get("ttl", 0.0))
            max_ttl = max(0.001, float(effect.get("max_ttl", 0.001)))
            life = max(0.0, min(1.0, ttl / max_ttl))
            alpha = int(255 * life)
            e_type = str(effect.get("type", ""))

            if e_type == "laser_to_target":
                arcade.draw_line(
                    p_x + 38,
                    p_y,
                    t_x - 34,
                    t_y,
                    (120, 220, 255, alpha),
                    max(1, int(4 * life)),
                )
            elif e_type == "laser_to_player":
                arcade.draw_line(
                    t_x - 38,
                    t_y,
                    p_x + 34,
                    p_y,
                    (255, 130, 110, alpha),
                    max(1, int(4 * life)),
                )
            elif e_type == "shield_target":
                arcade.draw_circle_outline(
                    t_x,
                    t_y,
                    40 + (12 * (1.0 - life)),
                    (110, 210, 255, alpha),
                    3,
                )
            elif e_type == "shield_player":
                arcade.draw_circle_outline(
                    p_x,
                    p_y,
                    40 + (12 * (1.0 - life)),
                    (110, 210, 255, alpha),
                    3,
                )
            elif e_type == "hull_target":
                for spark in range(3):
                    offset = 10 + (spark * 8)
                    arcade.draw_line(
                        t_x - offset,
                        t_y + 6,
                        t_x - (offset - 12),
                        t_y + 20,
                        (255, 180, 70, alpha),
                        2,
                    )
            elif e_type == "hull_player":
                for spark in range(3):
                    offset = 10 + (spark * 8)
                    arcade.draw_line(
                        p_x + offset,
                        p_y + 6,
                        p_x + (offset - 12),
                        p_y + 20,
                        (255, 180, 70, alpha),
                        2,
                    )

    def _draw_combat_window(self):
        if not self.combat_session:
            return

        s = self.combat_session
        p_ship = self.network.player.spaceship
        t_shields, t_defenders, t_integrity = self.network._get_target_stats(s)
        rects = self._combat_window_rects()
        x, y, w, h = rects["window"]

        # Dim background and draw top-most modal
        arcade.draw_lbwh_rectangle_filled(
            0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 150)
        )
        arcade.draw_lbwh_rectangle_filled(x, y, w, h, (10, 16, 24, 245))
        arcade.draw_lbwh_rectangle_outline(x, y, w, h, COLOR_PRIMARY, 3)
        if self.combat_flash_timer > 0:
            alpha = int(120 * min(1.0, self.combat_flash_timer / 0.18))
            arcade.draw_lbwh_rectangle_filled(
                x, y, w, h, (*self.combat_flash_color, alpha)
            )

        title = (
            f"TACTICAL COMBAT WINDOW :: {s['target_name'].upper()} [{s['target_type']}]"
        )
        arcade.Text(
            title,
            x + 30,
            y + h - 40,
            COLOR_PRIMARY,
            16,
            font_name=self.font_ui_bold,
        ).draw()

        status_color = COLOR_PRIMARY if s["status"] == "ACTIVE" else COLOR_ACCENT
        has_summary = bool(s.get("summary"))
        arcade.Text(
            f"STATUS: {s['status']} | ROUND: {s['round']}",
            x + 30,
            y + h - 70,
            status_color,
            13,
            font_name=self.font_ui,
        ).draw()
        arcade.Text(
            f"THREAT x{float(s.get('enemy_scale', 1.0)):.2f} | STREAK {int(getattr(self.network.player, 'combat_win_streak', 0))}",
            x + 330,
            y + h - 70,
            COLOR_SECONDARY,
            12,
            font_name=self.font_ui,
        ).draw()

        if not has_summary:
            self._draw_combat_visual_layer(rects)

        # Side-by-side combat stats
        arcade.Text(
            f"PLAYER  SHIELDS: {int(p_ship.current_shields)}  FIGHTERS: {int(p_ship.current_defenders)}  INTEGRITY: {int(p_ship.integrity)}",
            x + 30,
            y + h - 110,
            COLOR_TEXT_DIM,
            13,
            font_name=self.font_ui,
        ).draw()
        arcade.Text(
            f"TARGET  SHIELDS: {int(t_shields)}  FIGHTERS: {int(t_defenders)}  INTEGRITY: {int(t_integrity)}",
            x + 30,
            y + h - 140,
            COLOR_TEXT_DIM,
            13,
            font_name=self.font_ui,
        ).draw()

        if not has_summary:
            # Fighter commitment controls
            max_commit = max(0, int(p_ship.current_defenders))
            self.combat_commitment = max(
                0, min(int(self.combat_commitment), max_commit)
            )

            arcade.Text(
                "COMMIT FIGHTERS THIS ROUND:",
                x + 40,
                y + 245,
                COLOR_SECONDARY,
                12,
                font_name=self.font_ui,
            ).draw()

            recommended_commit = 0
            if int(t_defenders) > 0:
                recommended_commit = max(1, int(round(int(t_defenders) * 0.30)))
            recommended_commit = min(max_commit, recommended_commit)
            arcade.Text(
                f"TACTICAL SUGGESTION: COMMIT ~{recommended_commit} FIGHTERS",
                x + 40,
                y + 225,
                COLOR_TEXT_DIM,
                10,
                font_name=self.font_ui,
            ).draw()

            # Slider for fighter commitment
            sx1, sx2 = x + 40, x + 360
            sy = y + 205
            arcade.draw_line(sx1, sy, sx2, sy, COLOR_SECONDARY, 3)

            if max_commit > 0:
                knob_x = sx1 + int((self.combat_commitment / max_commit) * (sx2 - sx1))
            else:
                knob_x = sx1

            arcade.draw_circle_filled(knob_x, sy, 10, COLOR_PRIMARY)
            arcade.draw_circle_outline(knob_x, sy, 10, COLOR_SECONDARY, 2)

            arcade.Text(
                "0",
                sx1,
                sy - 20,
                COLOR_TEXT_DIM,
                10,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"MAX {max_commit}",
                sx2,
                sy - 20,
                COLOR_TEXT_DIM,
                10,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"{self.combat_commitment}",
                (sx1 + sx2) // 2,
                sy - 20,
                COLOR_PRIMARY,
                14,
                anchor_x="center",
                font_name=self.font_ui_bold,
            ).draw()

            attack_label = "ATTACK ROUND" if s["status"] == "ACTIVE" else "COMBAT ENDED"
            self._draw_btn(
                *rects["attack"],
                attack_label,
                COLOR_ACCENT,
                enabled=s["status"] == "ACTIVE",
            )

            cancel_label = "WARP AWAY" if s["status"] == "ACTIVE" else "CLOSE"
            self._draw_btn(*rects["cancel"], cancel_label, COLOR_PRIMARY, enabled=True)

            # Special weapon button — only for active PLANET combat when enabled
            if (
                s.get("status") == "ACTIVE"
                and s.get("target_type") == "PLANET"
                and self.network.config.get("enable_special_weapons", True)
                and getattr(self.network.player.spaceship, "special_weapon", None)
            ):
                import time as _time

                weapon_name = str(self.network.player.spaceship.special_weapon)
                cooldown_hours = float(
                    self.network.config.get(
                        "combat_special_weapon_cooldown_hours", 36.0
                    )
                )
                last_used = float(
                    getattr(self.network.player, "last_special_weapon_time", 0.0)
                )
                elapsed = (_time.time() - last_used) / 3600.0
                on_cooldown = elapsed < cooldown_hours
                remaining = max(0.0, cooldown_hours - elapsed)
                if on_cooldown:
                    if remaining >= 1.0:
                        cd_str = f"{remaining:.1f}H"
                    else:
                        cd_str = f"{int(remaining * 60)}M"
                    sw_label = f"[COOLDOWN: {cd_str}] {weapon_name.upper()}"
                    sw_color = COLOR_TEXT_DIM
                else:
                    sw_label = f"[SPECIAL WEAPON] {weapon_name.upper()}"
                    sw_color = (255, 80, 40)
                self._draw_btn(
                    *rects["special_weapon"],
                    sw_label,
                    sw_color,
                    enabled=not on_cooldown,
                )

        # Dedicated final summary area in main combat panel (not in log box)
        if has_summary:
            summary = s["summary"]
            cr = int(summary.get("credits_delta", 0))
            cr_str = f"+{cr}" if cr >= 0 else str(cr)
            looted_credits = int(summary.get("looted_credits", 0))
            stolen_credits = int(summary.get("stolen_credits", 0))
            looted_items = ", ".join(summary.get("looted_items", [])[:3]) or "none"
            stolen_items = ", ".join(summary.get("stolen_items", [])[:3]) or "none"

            summary_x, summary_y, summary_w, summary_h = x + 390, y + 250, 430, 156
            arcade.draw_lbwh_rectangle_filled(
                summary_x, summary_y, summary_w, summary_h, (12, 24, 20, 245)
            )
            arcade.draw_lbwh_rectangle_outline(
                summary_x, summary_y, summary_w, summary_h, COLOR_PRIMARY, 1
            )

            header_color = (
                COLOR_PRIMARY if summary.get("result") == "WON" else COLOR_ACCENT
            )
            arcade.Text(
                f"[RESULT] {summary.get('message', '')}",
                summary_x + 12,
                summary_y + 126,
                header_color,
                11,
                font_name=self.font_ui_bold,
                width=summary_w - 24,
            ).draw()
            arcade.Text(
                f"[NET] {cr_str}   [LOOT] +{looted_credits}",
                summary_x + 12,
                summary_y + 104,
                COLOR_PRIMARY,
                10,
                font_name=self.font_ui,
                width=summary_w - 24,
            ).draw()
            arcade.Text(
                f"[THREAT] x{float(summary.get('enemy_scale', 1.0)):.2f}   [STREAK] {int(summary.get('win_streak', 0))}",
                summary_x + 12,
                summary_y + 88,
                COLOR_SECONDARY,
                10,
                font_name=self.font_ui,
                width=summary_w - 24,
            ).draw()
            bounty_bonus = int(summary.get("bounty_bonus", 0))
            rare_loot = ", ".join(summary.get("rare_loot", [])[:2]) or "none"
            arcade.Text(
                f"[LOSS] -{stolen_credits} credits   [BOUNTY] +{bounty_bonus}",
                summary_x + 12,
                summary_y + 72,
                COLOR_ACCENT,
                10,
                font_name=self.font_ui,
                width=summary_w - 24,
            ).draw()
            arcade.Text(
                f"[SALVAGE] {looted_items}",
                summary_x + 12,
                summary_y + 56,
                COLOR_PRIMARY,
                10,
                font_name=self.font_ui,
                width=summary_w - 24,
            ).draw()
            arcade.Text(
                f"[STOLEN] {stolen_items}   [RARE] {rare_loot}",
                summary_x + 12,
                summary_y + 40,
                COLOR_ACCENT,
                10,
                font_name=self.font_ui,
                width=summary_w - 24,
            ).draw()

            if self.post_combat_actions:
                arcade.draw_line(
                    summary_x + 12,
                    summary_y + 30,
                    summary_x + summary_w - 12,
                    summary_y + 30,
                    COLOR_SECONDARY,
                    1,
                )
                arcade.Text(
                    "POST ACTIONS:",
                    summary_x + 12,
                    summary_y + 16,
                    COLOR_SECONDARY,
                    9,
                    font_name=self.font_ui_bold,
                ).draw()
                action_preview = self._clamp_text(self.post_combat_actions[0], 58)
                arcade.Text(
                    action_preview,
                    summary_x + 110,
                    summary_y + 16,
                    COLOR_TEXT_DIM,
                    9,
                    font_name=self.font_ui,
                    width=summary_w - 126,
                ).draw()

            rec_lines = self._get_post_combat_recommendations()
            if rec_lines:
                rec_x, rec_y, rec_w, rec_h = x + 30, y + 250, 340, 130
                arcade.draw_lbwh_rectangle_filled(
                    rec_x, rec_y, rec_w, rec_h, (16, 20, 30, 240)
                )
                arcade.draw_lbwh_rectangle_outline(
                    rec_x, rec_y, rec_w, rec_h, COLOR_SECONDARY, 1
                )
                arcade.Text(
                    "POST-COMBAT RECOMMENDATIONS",
                    rec_x + 10,
                    rec_y + rec_h - 20,
                    COLOR_SECONDARY,
                    10,
                    font_name=self.font_ui_bold,
                ).draw()

                wrapped_recs = []
                max_rec_lines = max(1, int((rec_h - 44) // 14))
                for line in rec_lines:
                    chunks = textwrap.wrap(
                        str(line),
                        width=42,
                        break_long_words=True,
                        break_on_hyphens=True,
                    )
                    if not chunks:
                        continue
                    wrapped_recs.append(f"â€¢ {chunks[0]}")
                    for extra in chunks[1:]:
                        wrapped_recs.append(f"  {extra}")
                    if len(wrapped_recs) >= max_rec_lines:
                        break

                if len(wrapped_recs) > max_rec_lines:
                    wrapped_recs = wrapped_recs[:max_rec_lines]
                if wrapped_recs and len(wrapped_recs[-1]) > 3:
                    wrapped_recs[-1] = (
                        wrapped_recs[-1][: max(0, 41)].rstrip(" .") + "..."
                    )

                for idx, line in enumerate(wrapped_recs):
                    arcade.Text(
                        line,
                        rec_x + 10,
                        rec_y + rec_h - 40 - (idx * 14),
                        COLOR_TEXT_DIM,
                        10,
                        font_name=self.font_ui,
                        width=rec_w - 20,
                    ).draw()

                can_autofit = any(
                    int(self.network.player.inventory.get(item, 0)) > 0
                    for item in [
                        "Cargo Pod",
                        "Energy Shields",
                        "Fighter Squadron",
                        "Nanobot Repair Kits",
                    ]
                )
                can_repair = (
                    self.network.player.spaceship.integrity
                    < self.network.player.spaceship.max_integrity
                    and self.network.current_planet.repair_multiplier is not None
                )

                self._draw_btn(
                    *rects["post_autofit"],
                    "AUTO-FIT [I]",
                    COLOR_SECONDARY,
                    enabled=can_autofit,
                )
                self._draw_btn(
                    *rects["post_repair"],
                    "REPAIR [R]",
                    COLOR_ACCENT,
                    enabled=can_repair,
                )
                self._draw_btn(
                    *rects["post_close"],
                    "CLOSE [C]",
                    COLOR_PRIMARY,
                    enabled=True,
                )
                self._draw_btn(
                    *rects["post_systems"],
                    "SYSTEMS [T]",
                    COLOR_SECONDARY,
                    enabled=True,
                )

                preview_ok, preview_text = self._get_repair_preview()
                arcade.Text(
                    self._clamp_text(preview_text, 54),
                    rects["post_repair"][0],
                    rects["post_repair"][1] + 52,
                    COLOR_PRIMARY if preview_ok else COLOR_ACCENT,
                    9,
                    font_name=self.font_ui,
                    width=rects["post_repair"][2] + 180,
                ).draw()

        # Rolling combat log area
        if has_summary:
            log_x, log_y, log_w, log_h = x + 30, y + 20, w - 60, 118
        else:
            log_x, log_y, log_w, log_h = x + 30, y + 25, w - 60, 145
        arcade.draw_lbwh_rectangle_filled(log_x, log_y, log_w, log_h, (6, 10, 16, 240))
        arcade.draw_lbwh_rectangle_outline(
            log_x, log_y, log_w, log_h, COLOR_SECONDARY, 1
        )

        arcade.Text(
            "COMBAT LOG",
            log_x + 10,
            log_y + log_h - 18,
            COLOR_SECONDARY,
            9,
            font_name=self.font_ui_bold,
        ).draw()
        arcade.draw_line(
            log_x + 96,
            log_y + log_h - 14,
            log_x + log_w - 10,
            log_y + log_h - 14,
            COLOR_SECONDARY,
            1,
        )

        max_lines = 5 if s.get("summary") else 8
        visible_log = s.get("log", [])[-max_lines:]
        start_y = log_y + log_h - 34
        for i, line in enumerate(visible_log):
            clipped = line if len(line) <= 120 else (line[:117] + "...")
            arcade.Text(
                clipped,
                log_x + 10,
                start_y - (i * 15),
                COLOR_TEXT_DIM,
                10,
                font_name=self.font_ui,
                width=log_w - 20,
            ).draw()

        # Special weapon confirmation overlay — drawn last to appear on top
        if self.combat_spec_weapon_confirm and self.combat_session:
            weapon_name = str(
                getattr(
                    self.network.player.spaceship, "special_weapon", "SPECIAL WEAPON"
                )
            )
            dmg_mult = float(
                self.network.config.get("combat_special_weapon_damage_multiplier", 2.0)
            )
            pop_min_pct = int(
                float(
                    self.network.config.get(
                        "combat_special_weapon_pop_reduction_min", 0.10
                    )
                )
                * 100
            )
            pop_max_pct = int(
                float(
                    self.network.config.get(
                        "combat_special_weapon_pop_reduction_max", 0.45
                    )
                )
                * 100
            )
            cd_h = self.network.config.get("combat_special_weapon_cooldown_hours", 36)

            # Modal box centered in the combat window
            box_w, box_h = 680, 210
            bx = x + (COMBAT_WINDOW_W // 2) - (box_w // 2)
            by = y + 205

            arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (6, 8, 14, 252))
            arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, (255, 80, 40), 3)

            cx_modal = bx + box_w // 2
            arcade.Text(
                f"// CONFIRM: FIRE {weapon_name.upper()} //",
                cx_modal,
                by + box_h - 28,
                (255, 80, 40),
                14,
                anchor_x="center",
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                f"x{dmg_mult:.0f} COMBAT DAMAGE THIS ROUND (FIGHTERS STILL COMMITTED)",
                cx_modal,
                by + box_h - 54,
                COLOR_PRIMARY,
                11,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"REDUCES PLANET POPULATION & TREASURY BY {pop_min_pct}\u2013{pop_max_pct}% (RANDOM)",
                cx_modal,
                by + box_h - 76,
                COLOR_ACCENT,
                11,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"COOLDOWN: {float(cd_h):.0f} REAL-TIME HOURS AFTER FIRING",
                cx_modal,
                by + box_h - 98,
                COLOR_TEXT_DIM,
                10,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                "THIS ACTION CANNOT BE UNDONE  \u2014  FIRE THE WEAPON?",
                cx_modal,
                by + box_h - 120,
                COLOR_SECONDARY,
                11,
                anchor_x="center",
                font_name=self.font_ui_bold,
            ).draw()
            self._draw_btn(
                *rects["sw_confirm_yes"],
                "[ CONFIRM FIRE ]",
                (255, 80, 40),
                enabled=True,
            )
            self._draw_btn(
                *rects["sw_confirm_no"], "[ CANCEL ]", COLOR_PRIMARY, enabled=True
            )

    def _get_post_combat_recommendations(self):
        ship = self.network.player.spaceship
        inventory = self.network.player.inventory
        planet = self.network.current_planet
        recs = []

        shield_missing = max(0, int(ship.max_shields - ship.current_shields))
        shield_cargo = int(inventory.get("Energy Shields", 0))
        if shield_missing > 0 and shield_cargo > 0:
            install = min(shield_missing, shield_cargo)
            recs.append(f"[I] AUTO-FIT +{install} SHIELD UNIT(S) FROM CARGO")
        elif shield_missing > 0:
            recs.append(f"SHIELDS DOWN {shield_missing}. BUY OR LOOT ENERGY SHIELDS")

        fighter_missing = max(0, int(ship.max_defenders - ship.current_defenders))
        fighter_cargo = int(inventory.get("Fighter Squadron", 0))
        if fighter_missing > 0 and fighter_cargo > 0:
            install = min(fighter_missing, fighter_cargo)
            recs.append(f"[I] AUTO-FIT +{install} FIGHTER SQUADRON(S)")

        integrity_missing = max(0, int(ship.max_integrity - ship.integrity))
        if integrity_missing > 0:
            if planet.repair_multiplier is not None:
                cost_per_percent = (ship.cost * 0.002) * planet.repair_multiplier
                repair_cost = int(
                    (integrity_missing / (ship.max_integrity / 100)) * cost_per_percent
                )
                if repair_cost < 1:
                    repair_cost = 1
                recs.append(f"[R] REPAIR HULL NOW FOR {repair_cost:,} CR")
            else:
                recs.append("NO DOCK REPAIR HERE. SEEK A PORT WITH FACILITIES")

        if not recs:
            recs.append("SYSTEMS OPTIMAL. READY FOR NEXT ENGAGEMENT")
            recs.append("PRESS [C] TO CLOSE")

        return recs

    def _get_market_message_duration(self, message):
        if not message:
            return 0.0

        msg_type = self._classify_message_type(message, default_type="info")
        return float(self._message_style(msg_type)["duration"])

    def _enqueue_timed_popup(
        self,
        message,
        duration=3.0,
        message_type="info",
        color=None,
        on_complete=None,
    ):
        if not message:
            return

        style = self._message_style(message_type)
        payload = {
            "message": str(message),
            "duration": max(0.8, float(duration)),
            "color": color or style["color"],
            "on_complete": on_complete,
        }
        self._timed_popup_queue.append(payload)
        self._show_next_timed_popup()

    def _show_next_timed_popup(self):
        if self._timed_popup_active or not self._timed_popup_queue or not self.window:
            return

        payload = self._timed_popup_queue.pop(0)
        self._timed_popup_active = True

        def _resume_after_popup():
            self._timed_popup_active = False
            callback = payload.get("on_complete")
            if callable(callback):
                callback()
            if self.window and self.window.current_view is not self:
                return
            if self.window:
                self.window.show_view(self)
            self._show_next_timed_popup()

        self.window.show_view(
            TimedPopupView(
                self,
                payload["message"],
                duration=payload["duration"],
                accent_color=payload["color"],
                on_complete=_resume_after_popup,
            )
        )

    def _draw_bank_input_overlay(self):
        arcade.draw_lbwh_rectangle_filled(
            0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 200)
        )
        cx, cy = SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2

        arcade.draw_lbwh_rectangle_filled(cx - 250, cy - 100, 500, 200, (20, 26, 36))
        arcade.draw_lbwh_rectangle_outline(
            cx - 250, cy - 100, 500, 200, COLOR_PRIMARY, 2
        )

        title = (
            "DEPOSIT TO TREASURY"
            if "deposit" in str(self.bank_input_mode)
            else "WITHDRAW FROM TREASURY"
        )
        arcade.Text(
            title,
            cx,
            cy + 50,
            COLOR_PRIMARY,
            18,
            anchor_x="center",
            font_name=self.font_ui_bold,
        ).draw()

        arcade.Text(
            f"AMOUNT: {self.bank_input_text}_",
            cx,
            cy,
            COLOR_SECONDARY,
            24,
            anchor_x="center",
            font_name=self.font_ui_bold,
        ).draw()

        arcade.Text(
            "[ENTER] CONFIRM  |  [ESC] CANCEL",
            cx,
            cy - 60,
            COLOR_TEXT_DIM,
            12,
            anchor_x="center",
            font_name=self.font_ui,
        ).draw()

        if self.bank_message:
            arcade.Text(
                self.bank_message,
                cx,
                cy - 85,
                COLOR_ACCENT,
                12,
                anchor_x="center",
                font_name=self.font_ui_bold,
            ).draw()

    def on_update(self, delta_time):
        if self.arrival_pause_timer > 0:
            self.arrival_pause_timer -= delta_time
            if self.arrival_pause_timer <= 0:
                self.arrival_pause_timer = 0
            return

        self.time_elapsed += delta_time
        self.planet_finance_refresh_elapsed += delta_time
        # Check auto-refuel and interest
        self.network.check_auto_refuel()
        success, msg = self.network.payout_interest()
        if success:
            self.arrival_msg = msg
            self.arrival_msg_timer = 5.0

        regen_success, regen_msg = self.network.process_conquered_planet_defense_regen()
        if regen_success:
            self.arrival_msg = regen_msg
            self.arrival_msg_timer = 4.0

        stipend_success, stipend_msg = self.network.process_commander_stipend()
        if stipend_success:
            self.arrival_msg = stipend_msg
            self.arrival_msg_timer = 4.0

        crew_pay_success, crew_pay_msg = self.network.process_crew_pay()
        if crew_pay_success and crew_pay_msg:
            self.arrival_msg = crew_pay_msg
            self.arrival_msg_timer = 5.0

        if self.mode in ("BANK", "MARKET", "ORBIT"):
            self._refresh_planet_finance_cache(force=False)

        if self.combat_flash_timer > 0:
            self.combat_flash_timer = max(0.0, self.combat_flash_timer - delta_time)

        if self.combat_impact_effects:
            kept = []
            for effect in self.combat_impact_effects:
                effect["ttl"] = float(effect.get("ttl", 0.0)) - float(delta_time)
                if effect["ttl"] > 0:
                    kept.append(effect)
            self.combat_impact_effects = kept

        if self.market_message != self.market_message_last:
            self.market_message_last = self.market_message
            if self.market_message:
                self.market_message_type = self._classify_message_type(
                    self.market_message, default_type="info"
                )
                style = self._message_style(self.market_message_type)
                self.market_msg_txt.color = style["color"]
                self._enqueue_timed_popup(
                    self.market_message,
                    duration=float(style["duration"]),
                    message_type=self.market_message_type,
                    color=style["color"],
                )
                self.market_message = ""
                self.market_message_last = ""
                self.market_message_timer = 0.0

        if self.market_message_timer > 0:
            self.market_message_timer = max(0.0, self.market_message_timer - delta_time)
            if self.market_message_timer <= 0 and self.market_message:
                self.market_message = ""
                self.market_message_last = ""

        if self.orbit_message != self.orbit_message_last:
            self.orbit_message_last = self.orbit_message
            if self.orbit_message:
                if self.orbit_message_color == COLOR_PRIMARY:
                    self.orbit_message_type = "success"
                elif self.orbit_message_color == COLOR_ACCENT:
                    self.orbit_message_type = "error"
                else:
                    self.orbit_message_type = self._classify_message_type(
                        self.orbit_message, default_type="info"
                    )
                    self.orbit_message_color = self._message_style(
                        self.orbit_message_type
                    )["color"]

                self.orbit_message_timer = float(
                    self._message_style(self.orbit_message_type)["duration"]
                )
                self._enqueue_timed_popup(
                    self.orbit_message,
                    duration=float(self.orbit_message_timer),
                    message_type=self.orbit_message_type,
                    color=self.orbit_message_color,
                )
                self.orbit_message = ""
                self.orbit_message_last = ""
                self.orbit_message_timer = 0.0

        if self.orbit_message_timer > 0:
            self.orbit_message_timer = max(0.0, self.orbit_message_timer - delta_time)
            if self.orbit_message_timer <= 0 and self.orbit_message:
                self.orbit_message = ""
                self.orbit_message_last = ""

        if self.arrival_msg_timer > 0:
            self.arrival_msg_timer = max(0.0, self.arrival_msg_timer - delta_time)
            if self.arrival_msg_timer <= 0:
                self.arrival_msg = ""

        # Update global effects orchestrator
        try:
            update_effects(delta_time)
        except Exception:
            pass

    def on_draw(self):
        self.clear()

        if self.arrival_pause_timer > 0:
            arcade.draw_lbwh_rectangle_filled(
                0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 255)
            )
            arcade.Text(
                f"ARRIVING AT {self.network.current_planet.name.upper()}...",
                SCREEN_WIDTH // 2,
                SCREEN_HEIGHT // 2 + 20,
                COLOR_PRIMARY,
                24,
                anchor_x="center",
                font_name=self.font_ui_bold,
            ).draw()

            # Show the arrival message

        # Draw global effects on top of UI
        try:
            draw_effects()
        except Exception:
            pass
            if self.arrival_msg:
                arcade.Text(
                    self.arrival_msg,
                    SCREEN_WIDTH // 2,
                    SCREEN_HEIGHT // 2 - 40,
                    COLOR_SECONDARY,
                    14,
                    anchor_x="center",
                    multiline=True,
                    width=600,
                    align="center",
                    font_name=self.font_ui,
                ).draw()

            arcade.Text(
                f"ESTABLISHING LINK... {self.arrival_pause_timer:.1f}",
                SCREEN_WIDTH // 2,
                100,
                COLOR_TEXT_DIM,
                12,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            return

        if self.combat_session:
            self._draw_combat_window()

        if self.wisdom_modal_active:
            self._draw_wisdom_modal()
            return

        if self.bg_texture:
            arcade.draw_texture_rect(
                self.bg_texture,
                arcade.LBWH(0, 0, SCREEN_WIDTH, SCREEN_HEIGHT),
                color=arcade.types.Color(255, 255, 255, 100),
            )

        sidebar_w = 300
        arcade.draw_lbwh_rectangle_filled(
            0, 0, sidebar_w, SCREEN_HEIGHT, (10, 15, 20, 230)
        )
        arcade.draw_line(sidebar_w, 0, sidebar_w, SCREEN_HEIGHT, COLOR_SECONDARY, 2)

        if self.thumb_texture:
            arcade.draw_texture_rect(
                self.thumb_texture,
                arcade.XYWH(sidebar_w // 2, SCREEN_HEIGHT - 120, 180, 180),
            )

        self.planet_name_txt.draw()

        # Sidebar Statistics (New location for Hull, Shields, Cargo)
        self._draw_sidebar_stats()

        for i, opt in enumerate(self.menu_options):
            is_sel = i == self.selected_menu
            y = 500 - i * 45
            txt = self.menu_texts[i]
            if is_sel:
                arcade.draw_lbwh_rectangle_filled(
                    20, y - 10, 260, 38, (*COLOR_PRIMARY, 50)
                )
                txt.text = f"> {opt}"
                txt.color = COLOR_PRIMARY
            else:
                txt.text = opt
                txt.color = COLOR_TEXT_DIM
            txt.y = y
            txt.draw()

        arcade.draw_lbwh_rectangle_filled(
            sidebar_w, 0, SCREEN_WIDTH - sidebar_w, 60, (5, 5, 10, 240)
        )
        arcade.draw_line(sidebar_w, 60, SCREEN_WIDTH, 60, COLOR_SECONDARY, 1)

        ship = self.network.player.spaceship
        bank = self.network.player.bank_balance
        ship_level = self.network.get_ship_level(ship)
        authority_rep = int(
            getattr(
                self.network.player,
                "authority_standing",
                getattr(self.network.player, "sector_reputation", 0),
            )
        )
        frontier_rep = int(getattr(self.network.player, "frontier_standing", 0))
        authority_label = self.network.get_authority_standing_label()
        frontier_label = self.network.get_frontier_standing_label()
        status_mode = f"{self.mode}*" if self.prompt_mode else self.mode
        self.status_bar_txt.text = self._clamp_text(
            f"CMDR: {self.network.player.name} | {ship.model} (LVL {ship_level}) | CR: {self.network.player.credits:,} | BANK: {bank:,} | AUTH: {authority_rep:+d} {authority_label} | FRONT: {frontier_rep:+d} {frontier_label} | MODE: {status_mode}",
            176,
        )
        self.status_bar_txt.draw()
        arcade.Text(
            "[F1] HELP  [F8] ANALYTICS",
            10,
            SCREEN_HEIGHT - 20,
            COLOR_SECONDARY,
            11,
            anchor_y="top",
            font_name=self.font_ui_bold,
        ).draw()

        # Mail Notification Icon
        unread_count = sum(1 for m in self.network.player.messages if not m.is_read)
        if unread_count > 0:
            # Flashing mail icon
            if (time.time() % 1.0) > 0.5:
                arcade.draw_lbwh_rectangle_filled(265, 35, 30, 20, COLOR_ACCENT)
                arcade.draw_triangle_filled(265, 55, 295, 55, 280, 45, (20, 20, 30))
                arcade.Text(
                    "!",
                    280,
                    45,
                    COLOR_PRIMARY,
                    12,
                    anchor_x="center",
                    anchor_y="center",
                    font_name=self.font_ui_bold,
                ).draw()

            arcade.Text(
                f"{unread_count} NEW SIGNAL(S)",
                310,
                45,
                COLOR_ACCENT,
                10,
                font_name=self.font_ui,
            ).draw()

        # Fuel Display
        fuel_perc = ship.fuel / ship.max_fuel
        fuel_bar_w = 170
        self.fuel_label.draw()
        arcade.draw_lbwh_rectangle_filled(
            SCREEN_WIDTH - 190, 36, fuel_bar_w, 15, (20, 20, 30)
        )
        arcade.draw_lbwh_rectangle_filled(
            SCREEN_WIDTH - 190,
            36,
            fuel_bar_w * fuel_perc,
            15,
            COLOR_ACCENT if fuel_perc < 0.2 else COLOR_PRIMARY,
        )
        arcade.draw_lbwh_rectangle_outline(
            SCREEN_WIDTH - 190, 36, fuel_bar_w, 15, (100, 100, 100), 1
        )

        content_x, content_y = sidebar_w + 50, SCREEN_HEIGHT - 80
        if self.mode == "INFO":
            self.header_txt.text = "PLANETARY RECON DATA"
            self.header_txt.draw()
            self.desc_txt.draw()

            stats_start_y = content_y - 250
            owner_display = self.network.current_planet.owner or "UNCLAIMED"
            planet_shields = int(
                getattr(
                    self.network.current_planet,
                    "max_shields",
                    self.network.current_planet.base_shields,
                )
            )
            stats = [
                f"OWNER: {owner_display}",
                f"POPULATION: {self.network.current_planet.population:,}",
                f"GOVERNANCE: {self.network.current_planet.vendor}",
                f"DEFENDERS: {self.network.current_planet.defenders} / {self.network.current_planet.max_defenders}",
                f"SHIELDS: {self.network.current_planet.shields} / {planet_shields}",
                f"TREASURY: {int(getattr(self.network.current_planet, 'credit_balance', 0)):,} CR",
            ]
            for i, s in enumerate(stats):
                txt = self.info_stat_texts[i]
                txt.text = s
                txt.y = stats_start_y - i * 40
                txt.draw()

        elif self.mode == "MARKET":
            self.header_txt.text = "LOCAL COMMERCE HUB"
            self.header_txt.draw()

            planet = self.network.current_planet
            planet_items = self._get_visible_market_items()

            # Crash protection: ensure index is valid
            if not planet_items:
                self.mode = "INFO"
                return

            if self.selected_item_index >= len(planet_items):
                self.selected_item_index = 0
                self.market_item_locked = False

            # Enforce scroll limits
            layout = self._get_market_layout(len(planet_items))
            visible_rows = layout["visible_rows"]
            max_scroll = max(0, len(planet_items) - visible_rows)
            if self.market_scroll > max_scroll:
                self.market_scroll = max_scroll

            # Area 1: Planet Info & Local Greeting
            desc_line = self._clamp_text(planet.description, 112)
            arcade.Text(
                desc_line,
                content_x,
                layout["top_band_y"],
                COLOR_PRIMARY,
                11,
                font_name=self.font_ui,
                width=max(800, SCREEN_WIDTH - content_x - 70),
            ).draw()

            self.vendor_txt.text = f"LOCAL AUTHORITY: {planet.vendor}"
            self.vendor_txt.y = layout["top_band_y"] - 35
            self.vendor_txt.draw()

            arcade.Text(
                f"POPULATION: {int(getattr(planet, 'population', 0)):,}",
                content_x,
                layout["top_band_y"] - 52,
                COLOR_TEXT_DIM,
                11,
                font_name=self.font_ui,
            ).draw()

            planet_event = self.network.get_planet_event(planet.name)
            if planet_event:
                arcade.Text(
                    f"PORT EVENT: {str(planet_event.get('label', 'SECTOR SHIFT')).upper()}",
                    content_x,
                    layout["top_band_y"] - 69,
                    COLOR_SECONDARY,
                    11,
                    font_name=self.font_ui_bold,
                ).draw()

            if self.network.is_planet_hostile_market(planet.name):
                remaining = self.network.get_planet_price_penalty_seconds_remaining(
                    planet.name
                )
                multiplier = int(
                    round((self.network.planet_price_penalty_multiplier - 1.0) * 100)
                )
                arcade.Text(
                    f"PORT SANCTIONS ACTIVE: +{multiplier}% BUY PRICES ({self._format_duration_hm(remaining)} REMAINING)",
                    content_x,
                    layout["top_band_y"] - 86,
                    COLOR_ACCENT,
                    12,
                    font_name=self.font_ui_bold,
                ).draw()

            y_offset = layout["list_start_y"]
            # Draw a subtle background for the market list (Dynamic height based on items)
            visible_items = min(len(planet_items), visible_rows)
            rect_w = 760 if self.compare_mode else 560
            list_bottom = layout["list_bottom"]
            arcade.draw_lbwh_rectangle_filled(
                content_x - 15,
                list_bottom,
                rect_w,
                (visible_items * MARKET_ROW_HEIGHT) + MARKET_LIST_FRAME_EXTRA,
                (5, 5, 10, 150),
            )
            arcade.draw_lbwh_rectangle_outline(
                content_x - 15,
                list_bottom,
                rect_w,
                (visible_items * MARKET_ROW_HEIGHT) + MARKET_LIST_FRAME_EXTRA,
                COLOR_SECONDARY,
                1,
            )

            self.m_hdr_item.y = y_offset + 10
            self.m_hdr_price.y = y_offset + 10
            self.m_hdr_cargo.y = y_offset + 10
            self.m_hdr_item.draw()
            self.m_hdr_price.draw()
            self.m_hdr_cargo.draw()

            comparison_planet = None
            if self.compare_mode:
                comparison_planet = self.network.planets[self.compare_planet_index]
                self.m_hdr_compare.text = f"AT {comparison_planet.name.upper()}"
                self.m_hdr_compare.y = y_offset + 10
                self.m_hdr_compare.draw()
                arcade.draw_line(
                    content_x,
                    y_offset - 5,
                    content_x + 600,
                    y_offset - 5,
                    COLOR_SECONDARY,
                    1,
                )
                self.market_instr.text = "KEYS: [W/S] SELECT | [C] TOGGLE | [A/D] CYCLE PLANET | [J] QUICK-SELL | [K] REROLL"
            else:
                arcade.draw_line(
                    content_x,
                    y_offset - 5,
                    content_x + 470,
                    y_offset - 5,
                    COLOR_SECONDARY,
                    1,
                )
                self.market_instr.text = "KEYS: [W/S] SELECT | [B] BUY | [V] SELL | [J] QUICK-SELL | [K] REROLL | [C] COMPARE | [ESC] BACK"

            for i, (item, price) in enumerate(planet_items):
                display_idx = i - self.market_scroll
                if display_idx < 0 or display_idx >= visible_rows:
                    continue

                is_sel = i == self.selected_item_index
                y = y_offset - 40 - display_idx * MARKET_ROW_HEIGHT

                # Alternating row background
                if i % 2 == 0:
                    row_rect_w = 760 if self.compare_mode else 560
                    arcade.draw_lbwh_rectangle_filled(
                        content_x - 10, y - 10, row_rect_w, 35, (255, 255, 255, 5)
                    )

                if is_sel:
                    row_rect_w = 760 if self.compare_mode else 560
                    lock_color = (
                        COLOR_ACCENT if self.market_item_locked else COLOR_PRIMARY
                    )
                    arcade.draw_lbwh_rectangle_filled(
                        content_x - 10, y - 10, row_rect_w, 35, (*lock_color, 70)
                    )

                row_color, compare_color = self._get_market_row_colors(
                    item, price, comparison_planet if self.compare_mode else None
                )
                row_idx = display_idx
                if row_idx >= len(self.market_row_texts):
                    break
                row = self.market_row_texts[row_idx]

                row["name"].text = item
                row["name"].y = y
                row["name"].color = row_color
                row["name"].draw()

                row["price"].text = f"{price:,} CR"
                row["price"].y = y
                row["price"].color = row_color
                row["price"].draw()

                qty = self.network.player.inventory.get(item, 0)
                row["cargo"].text = f"{qty}"
                row["cargo"].y = y
                row["cargo"].color = COLOR_PRIMARY if is_sel else COLOR_TEXT_DIM
                row["cargo"].draw()

                if self.compare_mode:
                    if item in comparison_planet.items:
                        comp_price = self.network.get_effective_buy_price(
                            item,
                            comparison_planet.items[item],
                            comparison_planet.name,
                        )
                        row["compare"].text = f"{comp_price:,} CR"
                        row["compare"].color = compare_color
                    else:
                        row["compare"].text = "N/A"
                        row["compare"].color = COLOR_TEXT_DIM
                    row["compare"].y = y
                    row["compare"].draw()

            # --- Visual Scroll Bar (Market) ---
            if len(planet_items) > visible_rows:
                sb_x = content_x + rect_w + 5
                sb_y = (
                    y_offset
                    - (visible_rows * MARKET_ROW_HEIGHT)
                    - MARKET_LIST_PAD_BOTTOM
                )
                sb_h = (visible_rows * MARKET_ROW_HEIGHT) + MARKET_LIST_FRAME_EXTRA
                arcade.draw_lbwh_rectangle_filled(
                    sb_x, sb_y, 10, sb_h, (20, 30, 40, 150)
                )

                # Thumb
                thumb_h = max(20, (visible_rows / len(planet_items)) * sb_h)
                scroll_perc = self.market_scroll / (len(planet_items) - visible_rows)
                thumb_y = (y_offset + 40 - thumb_h) - (scroll_perc * (sb_h - thumb_h))
                arcade.draw_lbwh_rectangle_filled(
                    sb_x + 1, thumb_y, 8, thumb_h, COLOR_SECONDARY
                )

            # Draw contract panel after list so it stays readable above rows.
            self._draw_trade_contract_panel(content_x, layout["contract_y"])

            # Area 3: Transaction Panel
            panel_x = content_x + (790 if self.compare_mode else 600)
            panel_w, panel_h = 390, 390
            panel_y = SCREEN_HEIGHT - 620

            # Area 2: NPC Vendor Panel (Greeting / Dialog)
            # Pre-wrap the remark so the box height can be computed exactly.
            _remark_raw = f'"{self.npc_remark}"'
            _remark_lines = textwrap.wrap(_remark_raw, width=50)[:5]
            remark_display = "\n".join(_remark_lines) if _remark_lines else _remark_raw
            npc_line_count = max(1, len(_remark_lines))
            npc_h = 52 + npc_line_count * 18  # header (32) + padding (20) + text lines
            npc_h = max(90, npc_h)
            npc_y = SCREEN_HEIGHT - 250  # Below the planet description
            arcade.draw_lbwh_rectangle_filled(
                panel_x, npc_y, panel_w, npc_h, (20, 30, 40, 200)
            )
            arcade.draw_lbwh_rectangle_outline(
                panel_x, npc_y, panel_w, npc_h, COLOR_SECONDARY, 1
            )

            arcade.Text(
                f"CONTACT: {planet.npc_name.upper()}",
                panel_x + 15,
                npc_y + npc_h - 30,
                COLOR_PRIMARY,
                14,
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                remark_display,
                panel_x + 15,
                npc_y + npc_h - 55,
                COLOR_TEXT_DIM,
                12,
                font_name=self.font_ui,
                italic=True,
                multiline=True,
                width=panel_w - 30,
            ).draw()

            # Transaction Panel Drawing
            arcade.draw_lbwh_rectangle_filled(
                panel_x, panel_y, panel_w, panel_h, (10, 15, 20, 240)
            )
            arcade.draw_lbwh_rectangle_outline(
                panel_x, panel_y, panel_w, panel_h, COLOR_PRIMARY, 2
            )

            sel_item, sel_price = planet_items[self.selected_item_index]
            ship = self.network.player.spaceship
            cargo_used = sum(self.network.player.inventory.values())
            cargo_max = ship.current_cargo_pods

            inv_qty = self.network.player.inventory.get(sel_item, 0)
            is_buyable = self._is_item_buyable_in_market(sel_item)
            can_afford = self.network.player.credits // sel_price if is_buyable else 0
            space_left = cargo_max - cargo_used
            max_buy = min(can_afford, space_left) if is_buyable else 0
            bribe_snapshot = self.network.get_bribe_market_snapshot(planet.name)
            configured_bribe_cap = max(1, int(bribe_snapshot.get("max_level", 3) or 3))
            contraband_ctx = self.network.get_contraband_market_context(
                sel_item,
                planet.name,
                quantity=max(1, inv_qty if inv_qty > 0 else 1),
            )

            # Panel Header
            arcade.Text(
                "TRANSACTION HUB",
                panel_x + 20,
                panel_y + panel_h - 40,
                COLOR_PRIMARY,
                15,
                font_name=self.font_ui_bold,
            ).draw()
            arcade.draw_line(
                panel_x + 20,
                panel_y + panel_h - 50,
                panel_x + panel_w - 20,
                panel_y + panel_h - 50,
                COLOR_SECONDARY,
                1,
            )

            intel_box_x = panel_x + 20
            intel_box_y = panel_y + panel_h - 128
            intel_box_w = panel_w - 40
            intel_box_h = 62
            arcade.draw_lbwh_rectangle_filled(
                intel_box_x, intel_box_y, intel_box_w, intel_box_h, (12, 22, 30, 210)
            )
            arcade.draw_lbwh_rectangle_outline(
                intel_box_x, intel_box_y, intel_box_w, intel_box_h, COLOR_SECONDARY, 1
            )

            if bribe_snapshot.get("available", False):
                bribe_level = int(bribe_snapshot.get("level", 0))
                max_level = int(bribe_snapshot.get("max_level", 3))
                remaining = int(bribe_snapshot.get("remaining_seconds", 0))
                remaining_label = self._format_duration_hm(remaining)
                can_bribe_now = bool(bribe_snapshot.get("can_bribe", False))
                quote_cost = int(bribe_snapshot.get("cost", 0))

                arcade.Text(
                    f"CONTACT INFLUENCE: LVL {bribe_level}/{max_level}",
                    intel_box_x + 10,
                    intel_box_y + 40,
                    COLOR_PRIMARY,
                    11,
                    font_name=self.font_ui_bold,
                ).draw()
                arcade.Text(
                    f"ACCESS WINDOW: {remaining_label} | PORT HEAT: {int(bribe_snapshot.get('heat', 0))}%",
                    intel_box_x + 10,
                    intel_box_y + 24,
                    COLOR_TEXT_DIM,
                    10,
                    font_name=self.font_ui,
                ).draw()
                arcade.Text(
                    f"CONFIG BRIBE CAP: LVL {configured_bribe_cap}",
                    intel_box_x + 10,
                    intel_box_y + 8,
                    COLOR_TEXT_DIM,
                    10,
                    font_name=self.font_ui,
                ).draw()

                if can_bribe_now:
                    self._draw_btn(
                        intel_box_x + intel_box_w - 154,
                        intel_box_y + 14,
                        144,
                        28,
                        f"BRIBE ({quote_cost:,})",
                        COLOR_ACCENT,
                        enabled=True,
                    )
                else:
                    arcade.Text(
                        self._clamp_text(
                            str(bribe_snapshot.get("reason", "")), 38
                        ).upper(),
                        intel_box_x + intel_box_w - 12,
                        intel_box_y + 20,
                        COLOR_ACCENT,
                        10,
                        anchor_x="right",
                        font_name=self.font_ui,
                    ).draw()
            else:
                arcade.Text(
                    "CONTACT CANNOT BE BRIBED AT THIS PORT",
                    intel_box_x + 10,
                    intel_box_y + 46,
                    COLOR_TEXT_DIM,
                    10,
                    font_name=self.font_ui,
                ).draw()
                arcade.Text(
                    f"CONFIG BRIBE CAP: LVL {configured_bribe_cap}",
                    intel_box_x + 10,
                    intel_box_y + 24,
                    COLOR_TEXT_DIM,
                    10,
                    font_name=self.font_ui,
                ).draw()

            arcade.Text(
                sel_item.upper(),
                panel_x + 20,
                panel_y + panel_h - 162,
                COLOR_ACCENT,
                16,
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                f"PRICE: {sel_price:,} CR",
                panel_x + 20,
                panel_y + panel_h - 190,
                COLOR_TEXT_DIM,
                13,
                font_name=self.font_ui,
            ).draw()
            if not is_buyable:
                arcade.Text(
                    "SELL-ONLY SALVAGE CARGO",
                    panel_x + 20,
                    panel_y + panel_h - 208,
                    COLOR_ACCENT,
                    10,
                    font_name=self.font_ui_bold,
                ).draw()
            arcade.Text(
                f"CARGO: {inv_qty} UNIT(S)",
                panel_x + 20,
                panel_y + panel_h - 228,
                COLOR_TEXT_DIM,
                13,
                font_name=self.font_ui,
            ).draw()
            spotlight = self.network.get_current_port_spotlight_deal()
            if spotlight:
                arcade.Text(
                    f"SPOTLIGHT: {spotlight['item'].upper()} -{int(spotlight['discount_pct'])}% ({int(spotlight['quantity'])} LEFT)",
                    panel_x + 20,
                    panel_y + panel_h - 246,
                    COLOR_PRIMARY,
                    10,
                    font_name=self.font_ui_bold,
                    width=panel_w - 34,
                    multiline=True,
                ).draw()

            if contraband_ctx:
                risk_pct = int(
                    round(float(contraband_ctx.get("detection_chance", 0.0)) * 100.0)
                )
                modifier = contraband_ctx.get("local_modifier_pct")
                required_level = int(contraband_ctx.get("required_bribe_level", 0) or 0)
                modifier_text = (
                    f"MARKET MOD: {int(modifier)}%"
                    if modifier is not None
                    else "MARKET MOD: DYNAMIC"
                )
                arcade.Text(
                    f"CONTRABAND {str(contraband_ctx.get('tier', 'LOW')).upper()} | BRIBE LVL {required_level}+ | SCAN RISK {risk_pct}% | {modifier_text}",
                    panel_x + 20,
                    panel_y + panel_h - 266,
                    COLOR_ACCENT,
                    10,
                    font_name=self.font_ui_bold,
                    width=panel_w - 34,
                    multiline=True,
                ).draw()

            # Constraints Info
            arcade.Text(
                f"AFFORDABLE: {can_afford}",
                panel_x + 20,
                panel_y + 124,
                COLOR_PRIMARY if can_afford > 0 else COLOR_ACCENT,
                12,
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"SPACE AVAIL: {space_left}",
                panel_x + 20,
                panel_y + 104,
                COLOR_PRIMARY if space_left > 0 else COLOR_ACCENT,
                12,
                font_name=self.font_ui,
            ).draw()

            # Buttons
            btn_w, btn_h = 160, 40

            # Buy Buttons
            bx, by = panel_x + 20, panel_y + 56
            self._draw_btn(bx, by, btn_w, btn_h, "BUY...", COLOR_PRIMARY, max_buy >= 1)
            self._draw_btn(
                bx + 190,
                by,
                btn_w,
                btn_h,
                f"BUY MAX ({max_buy})",
                COLOR_PRIMARY,
                max_buy > 0,
            )

            # Sell Buttons
            sx, sy = panel_x + 20, panel_y + 8
            self._draw_btn(sx, sy, btn_w, btn_h, "SELL...", COLOR_ACCENT, inv_qty >= 1)
            self._draw_btn(
                sx + 190,
                sy,
                btn_w,
                btn_h,
                f"SELL ALL ({inv_qty})",
                COLOR_ACCENT,
                inv_qty > 0,
            )

            # Best Trade Opportunities Panel
            trade_panel_h = 86
            trade_panel_y = panel_y - trade_panel_h - 8
            arcade.draw_lbwh_rectangle_filled(
                panel_x, trade_panel_y, panel_w, trade_panel_h, (8, 14, 20, 235)
            )
            arcade.draw_lbwh_rectangle_outline(
                panel_x, trade_panel_y, panel_w, trade_panel_h, COLOR_SECONDARY, 1
            )

            arcade.Text(
                "BEST TRADE LEADS",
                panel_x + 15,
                trade_panel_y + trade_panel_h - 28,
                COLOR_PRIMARY,
                13,
                font_name=self.font_ui_bold,
            ).draw()

            top_routes = self.network.get_best_trade_opportunities(planet.name, limit=2)
            if not top_routes:
                arcade.Text(
                    "NO STRONG EXPORT MARGINS DETECTED.",
                    panel_x + 15,
                    trade_panel_y + trade_panel_h - 52,
                    COLOR_TEXT_DIM,
                    11,
                    font_name=self.font_ui,
                ).draw()
            else:
                for idx, route in enumerate(top_routes):
                    line_y = trade_panel_y + trade_panel_h - 52 - idx * 22
                    arcade.Text(
                        self._clamp_text(
                            f"{idx + 1}. {route['item']} -> {route['sell_planet']}  (+{route['profit']:,} CR)",
                            48,
                        ),
                        panel_x + 15,
                        line_y,
                        COLOR_SECONDARY,
                        11,
                        font_name=self.font_ui_bold,
                    ).draw()

            self.market_instr.y = layout["footer_y"] + 18
            self.market_instr.draw()
            arcade.Text(
                "PRICE COLORS: GREEN=PROFITABLE | RED=OVERPRICED | BLUE=NEUTRAL",
                content_x,
                layout["footer_y"],
                COLOR_TEXT_DIM,
                10,
                font_name=self.font_ui,
            ).draw()
            if self.market_message:
                display_market_msg = self._clamp_text(self.market_message, 128)
                self.market_msg_txt.text = display_market_msg
                self.market_msg_txt.y = layout["footer_y"] - 34
                fade_window = 0.45
                fade_alpha = 255
                if 0 < self.market_message_timer < fade_window:
                    fade_alpha = int(255 * (self.market_message_timer / fade_window))
                base_market_color = self._message_style(self.market_message_type)[
                    "color"
                ]
                self.market_msg_txt.color = (*base_market_color, max(80, fade_alpha))
                self.market_msg_txt.draw()

        elif self.mode == "ORBIT":
            self.header_txt.text = "LONG-RANGE ORBITAL SCAN"
            self.header_txt.draw()

            if not self.orbital_targets:
                arcade.Text(
                    "NO OTHER VESSELS DETECTED IN LOCAL ORBIT.",
                    content_x,
                    content_y - 100,
                    COLOR_TEXT_DIM,
                    14,
                    font_name=self.font_ui,
                ).draw()
            else:
                for i, target in enumerate(self.orbital_targets):
                    is_sel = i == self.selected_target_index
                    y = content_y - 120 - i * 60

                    if is_sel:
                        arcade.draw_lbwh_rectangle_filled(
                            content_x - 10, y - 10, 500, 50, (*COLOR_PRIMARY, 40)
                        )

                    name = (
                        target["obj"].name
                        if target["type"] == "NPC"
                        else target["name"]
                    )
                    tag = f"[{target['type']}]"
                    if target.get("is_abandoned"):
                        tag += " - ABANDONED"

                    color = COLOR_PRIMARY if is_sel else COLOR_TEXT_DIM
                    if target.get("is_abandoned"):
                        color = (255, 100, 100) if is_sel else (150, 70, 70)

                    arcade.Text(
                        self._clamp_text(f"{name} {tag}", 44),
                        content_x,
                        y + 20,
                        color,
                        16,
                        font_name=self.font_ui_bold,
                    ).draw()

                    # Interacting check
                    if is_sel:
                        # Detail Panel
                        panel_x = content_x + 550
                        panel_y = content_y - 300
                        arcade.draw_lbwh_rectangle_filled(
                            panel_x, panel_y, 400, 300, (10, 15, 20, 240)
                        )
                        arcade.draw_lbwh_rectangle_outline(
                            panel_x, panel_y, 400, 300, COLOR_PRIMARY, 2
                        )

                        arcade.Text(
                            "VESSEL DIAGNOSTIC",
                            panel_x + 20,
                            panel_y + 260,
                            COLOR_PRIMARY,
                            16,
                            font_name=self.font_ui_bold,
                        ).draw()

                        info = (
                            target["obj"].get_info()
                            if target["type"] == "NPC"
                            else target["raw_data"]["player"]
                        )
                        ship_info = info["spaceship"]

                        if target["type"] == "NPC":
                            s_model = ship_info.get("model", "Unknown")
                            s_integ_val = ship_info.get("integrity", 0)
                            s_max_integ = ship_info.get("max_integrity", 100)
                            s_integ = (
                                int((s_integ_val / s_max_integ) * 100)
                                if s_max_integ > 0
                                else 0
                            )
                            s_shields = ship_info.get("shields", "0/0")
                            s_defenders = ship_info.get("defenders", "0/0")
                        else:
                            # Other players from JSON
                            s_model = ship_info.get("model", "Unknown")
                            s_integ_val = ship_info.get("integrity", 100)
                            s_max_integ = ship_info.get("max_integrity", 100)
                            s_integ = (
                                int((s_integ_val / s_max_integ) * 100)
                                if s_max_integ > 0
                                else 0
                            )
                            s_shields = f"{ship_info.get('current_shields', 0)} / {ship_info.get('max_shields', 0)}"
                            s_defenders = f"{ship_info.get('current_defenders', 0)} / {ship_info.get('max_defenders', 0)}"

                        arcade.Text(
                            self._clamp_text(f"MODEL: {s_model}", 36),
                            panel_x + 20,
                            panel_y + 220,
                            COLOR_TEXT_DIM,
                            14,
                            font_name=self.font_ui,
                        ).draw()
                        arcade.Text(
                            f"INTEGRITY: {int(s_integ)}%",
                            panel_x + 20,
                            panel_y + 195,
                            COLOR_TEXT_DIM,
                            14,
                            font_name=self.font_ui,
                        ).draw()
                        arcade.Text(
                            self._clamp_text(f"SHIELDS: {s_shields}", 36),
                            panel_x + 20,
                            panel_y + 170,
                            COLOR_TEXT_DIM,
                            14,
                            font_name=self.font_ui,
                        ).draw()
                        arcade.Text(
                            self._clamp_text(f"FIGHTERS: {s_defenders}", 36),
                            panel_x + 20,
                            panel_y + 145,
                            COLOR_TEXT_DIM,
                            14,
                            font_name=self.font_ui,
                        ).draw()

                        if target["type"] == "NPC":
                            remark = target.get("remark", "...")
                            remark_y = (
                                panel_y + 130
                                if not target.get("is_abandoned")
                                else panel_y + 100
                            )
                            arcade.Text(
                                f'"{self._clamp_text(str(remark), 46)}"',
                                panel_x + 20,
                                remark_y,
                                COLOR_ACCENT,
                                12,
                                font_name=self.font_ui,
                                italic=True,
                            ).draw()

                        # Buttons
                        if target.get("is_abandoned"):
                            self._draw_btn(
                                panel_x + 20,
                                panel_y + 80,
                                110,
                                40,
                                "CLAIM SHIP",
                                COLOR_PRIMARY,
                            )
                            self._draw_btn(
                                panel_x + 140,
                                panel_y + 80,
                                110,
                                40,
                                "SCRAP SHIP",
                                COLOR_ACCENT,
                            )
                            self._draw_btn(
                                panel_x + 260,
                                panel_y + 80,
                                110,
                                40,
                                "LOOT SHIP",
                                (200, 200, 50),
                            )
                            self._draw_btn(
                                panel_x + 20,
                                panel_y + 20,
                                110,
                                40,
                                "ATTACK",
                                COLOR_ACCENT,
                            )
                            self._draw_btn(
                                panel_x + 140,
                                panel_y + 20,
                                110,
                                40,
                                "GIVE SHIP",
                                (100, 200, 100),
                            )
                        else:
                            cargo_items = [
                                (name, int(qty))
                                for name, qty in sorted(
                                    self.network.player.inventory.items(),
                                    key=lambda pair: str(pair[0]).lower(),
                                )
                                if int(qty) > 0
                            ]
                            if cargo_items:
                                self.orbit_give_cargo_index = max(
                                    0,
                                    min(
                                        int(self.orbit_give_cargo_index),
                                        len(cargo_items) - 1,
                                    ),
                                )
                            else:
                                self.orbit_give_cargo_index = 0

                            arcade.Text(
                                "CARGO TO GIVE:",
                                panel_x + 20,
                                panel_y + 122,
                                COLOR_SECONDARY,
                                11,
                                font_name=self.font_ui_bold,
                            ).draw()

                            if cargo_items:
                                visible_rows = 3
                                start_idx = max(
                                    0,
                                    min(
                                        int(self.orbit_give_cargo_index),
                                        len(cargo_items) - visible_rows,
                                    ),
                                )
                                end_idx = min(
                                    len(cargo_items), start_idx + visible_rows
                                )

                                for display_idx, item_idx in enumerate(
                                    range(start_idx, end_idx)
                                ):
                                    item_name, item_qty = cargo_items[item_idx]
                                    row_y = panel_y + 104 - display_idx * 18
                                    is_sel_item = item_idx == int(
                                        self.orbit_give_cargo_index
                                    )
                                    if is_sel_item:
                                        arcade.draw_lbwh_rectangle_filled(
                                            panel_x + 16,
                                            row_y - 3,
                                            356,
                                            16,
                                            (*COLOR_PRIMARY, 40),
                                        )
                                    arcade.Text(
                                        self._clamp_text(
                                            f"{item_name} x{item_qty}", 34
                                        ),
                                        panel_x + 20,
                                        row_y,
                                        (
                                            COLOR_PRIMARY
                                            if is_sel_item
                                            else COLOR_TEXT_DIM
                                        ),
                                        11,
                                        font_name=self.font_ui,
                                    ).draw()
                            else:
                                arcade.Text(
                                    "NO CARGO AVAILABLE",
                                    panel_x + 20,
                                    panel_y + 100,
                                    COLOR_TEXT_DIM,
                                    11,
                                    font_name=self.font_ui,
                                ).draw()

                            arcade.Text(
                                "[Q/E] SELECT CARGO ITEM",
                                panel_x + 20,
                                panel_y + 72,
                                COLOR_TEXT_DIM,
                                10,
                                font_name=self.font_ui,
                            ).draw()

                            self._draw_btn(
                                panel_x + 20,
                                panel_y + 20,
                                110,
                                40,
                                "COMBAT",
                                COLOR_ACCENT,
                            )
                            self._draw_btn(
                                panel_x + 140,
                                panel_y + 20,
                                110,
                                40,
                                "GIVE CARGO",
                                COLOR_PRIMARY,
                            )
                            if (
                                target["type"] == "NPC"
                                and target["obj"].personality == "bribable"
                            ):
                                self._draw_btn(
                                    panel_x + 260,
                                    panel_y + 20,
                                    110,
                                    40,
                                    "BRIBE SHIP",
                                    (200, 200, 50),
                                )

            # Planet Defense Section
            arcade.draw_line(content_x, 250, SCREEN_WIDTH - 50, 250, COLOR_SECONDARY, 1)
            arcade.Text(
                "LOCAL PLANETARY DEFENSE STRATUM",
                content_x,
                220,
                COLOR_SECONDARY,
                16,
                font_name=self.font_ui_bold,
            ).draw()

            p = self.network.current_planet
            owner_text = f"OWNER: {p.owner if p.owner else 'UNCLAIMED'}"
            arcade.Text(
                owner_text, content_x, 190, COLOR_PRIMARY, 14, font_name=self.font_ui
            ).draw()
            arcade.Text(
                f"SHIELDS: {p.shields} / {getattr(p, 'max_shields', p.base_shields)} | DEFENDERS: {p.defenders}",
                content_x,
                165,
                COLOR_TEXT_DIM,
                14,
                font_name=self.font_ui,
            ).draw()

            finance = self.planet_finance_cache or {}
            planet_fin = finance.get("current_planet") or {}
            if planet_fin and str(planet_fin.get("name", "")) == str(p.name):
                treasury_x = SCREEN_WIDTH - 400
                treasury_y = 150
                treasury_w = 380
                treasury_h = 100
                arcade.draw_lbwh_rectangle_filled(
                    treasury_x,
                    treasury_y,
                    treasury_w,
                    treasury_h,
                    (10, 18, 28, 215),
                )
                arcade.draw_lbwh_rectangle_outline(
                    treasury_x,
                    treasury_y,
                    treasury_w,
                    treasury_h,
                    COLOR_SECONDARY,
                    1,
                )
                arcade.Text(
                    "PLANET TREASURY",
                    treasury_x + 12,
                    treasury_y + 66,
                    COLOR_PRIMARY,
                    12,
                    font_name=self.font_ui_bold,
                ).draw()
                arcade.Text(
                    f"POP: {int(planet_fin.get('population', 0)):,} | BASE: {int(planet_fin.get('credit_balance', 0)):,} CR",
                    treasury_x + 12,
                    treasury_y + 44,
                    COLOR_TEXT_DIM,
                    11,
                    font_name=self.font_ui,
                ).draw()
                arcade.Text(
                    f"DAILY +{int(planet_fin.get('projected_interest', 0)):,} CR | OWNED TOTAL: {int(finance.get('owned_total_balance', 0)):,} CR",
                    treasury_x + 12,
                    treasury_y + 24,
                    COLOR_SECONDARY,
                    11,
                    font_name=self.font_ui,
                ).draw()

            conquer_btn_color = COLOR_ACCENT
            conquer_btn_text = "CONQUER PLANET"

            if p.owner != self.network.player.name:
                base_shields = max(1, getattr(p, "base_shields", p.shields or 1))
                base_defenders = max(1, getattr(p, "base_defenders", p.max_defenders))

                shield_depletion = int(
                    max(0, min(100, (1 - (p.shields / base_shields)) * 100))
                )
                defender_depletion = int(
                    max(0, min(100, (1 - (p.defenders / base_defenders)) * 100))
                )
                readiness = int((shield_depletion * 0.6) + (defender_depletion * 0.4))

                if p.shields == 0 and p.defenders == 0:
                    readiness = 100

                # Progress color: red -> yellow -> green
                if readiness < 50:
                    ratio = readiness / 50
                    progress_color = (255, int(220 * ratio), 80)
                else:
                    ratio = (readiness - 50) / 50
                    progress_color = (int(255 - (135 * ratio)), 220, 80)

                if readiness < 25:
                    defense_state = "DEFENSE STATE: HARDENED"
                elif readiness < 60:
                    defense_state = "DEFENSE STATE: BREACHED"
                elif readiness < 100:
                    defense_state = "DEFENSE STATE: COLLAPSING"
                else:
                    defense_state = "DEFENSE STATE: EXPOSED"

                arcade.Text(
                    defense_state,
                    content_x,
                    108,
                    progress_color,
                    12,
                    font_name=self.font_ui_bold,
                ).draw()

                arcade.Text(
                    f"ASSAULT PROGRESS: {readiness}%  (SHIELD BREACH {shield_depletion}% | DEFENDER SUPPRESSION {defender_depletion}%)",
                    content_x,
                    142,
                    progress_color,
                    12,
                    font_name=self.font_ui,
                ).draw()

                bar_x, bar_y = content_x, 124
                bar_w, bar_h = 340, 12
                arcade.draw_lbwh_rectangle_filled(
                    bar_x, bar_y, bar_w, bar_h, (25, 30, 40, 220)
                )
                arcade.draw_lbwh_rectangle_outline(
                    bar_x, bar_y, bar_w, bar_h, COLOR_SECONDARY, 1
                )
                filled_w = int((readiness / 100) * bar_w)
                if filled_w > 0:
                    arcade.draw_lbwh_rectangle_filled(
                        bar_x, bar_y, filled_w, bar_h, progress_color
                    )

                conquer_btn_color = progress_color
                conquer_btn_text = f"CONQUER ({readiness}%)"

            if p.owner == self.network.player.name:
                # Fighter Transfer Controls
                self._draw_btn(content_x, 100, 150, 40, "LEAVE FIGHTERS", COLOR_PRIMARY)
                self._draw_btn(
                    content_x + 160, 100, 150, 40, "TAKE FIGHTERS", COLOR_ACCENT
                )
                self._draw_btn(content_x, 52, 150, 40, "ASSIGN SHIELDS", COLOR_PRIMARY)
                self._draw_btn(
                    content_x + 160, 52, 150, 40, "TAKE SHIELDS", COLOR_ACCENT
                )
            else:
                conquer_btn_x = content_x + 500
                self._draw_btn(
                    conquer_btn_x,
                    100,
                    200,
                    40,
                    conquer_btn_text,
                    conquer_btn_color,
                )

            if self.orbit_message:
                display_orbit_msg = self._clamp_text(self.orbit_message.upper(), 150)
                fade_window = 0.55
                fade_alpha = 255
                if 0 < self.orbit_message_timer < fade_window:
                    fade_alpha = int(255 * (self.orbit_message_timer / fade_window))
                orbit_color = (
                    *self.orbit_message_color[:3],
                    max(90, fade_alpha),
                )
                arcade.Text(
                    display_orbit_msg,
                    content_x,
                    50,
                    orbit_color,
                    14,
                    font_name=self.font_ui_bold,
                    multiline=True,
                    width=700,
                ).draw()

        elif self.mode == "REFUEL":
            self.header_txt.text = "FUEL SYNTHESIS STATION"
            self.header_txt.draw()

            ship = self.network.player.spaceship
            quote = self.network.get_refuel_quote() or {}
            timer_mode_enabled = bool(quote.get("refuel_timer_enabled", False))
            if ship.fuel >= ship.max_fuel:
                self.refuel_status_txt.text = "FUEL CELLS AT MAXIMUM CAPACITY."
                self.refuel_status_txt.color = COLOR_PRIMARY
                self.refuel_status_txt.draw()
                self.refuel_timer_txt.text = (
                    "TIMER MODE: ON" if timer_mode_enabled else "TIMER MODE: OFF"
                )
                self.refuel_timer_txt.draw()
            else:
                self.refuel_status_txt.text = (
                    f"CURRENT FUEL: {ship.fuel:.1f} / {ship.max_fuel}"
                )
                self.refuel_status_txt.color = COLOR_TEXT_DIM
                self.refuel_status_txt.draw()

                total_cost = int(quote.get("total_cost", 0) or 0)
                fuel_grade = str(quote.get("fuel_grade", "STANDARD") or "STANDARD")
                unit_cost = float(quote.get("unit_cost", 0.0) or 0.0)
                self.refuel_cost_txt.text = (
                    f"COST TO TOP OFF: {total_cost:,} CR "
                    f"({fuel_grade} FUEL, {unit_cost:.2f}/UNIT)"
                )
                self.refuel_cost_txt.draw()

                timer_lines = [
                    "TIMER MODE: ON" if timer_mode_enabled else "TIMER MODE: OFF"
                ]
                if timer_mode_enabled:
                    max_refuels = max(1, int(quote.get("refuel_uses_max", 1) or 1))
                    remaining_refuels = max(
                        0,
                        min(
                            max_refuels,
                            int(quote.get("refuel_uses_remaining", max_refuels) or 0),
                        ),
                    )
                    used_refuels = max_refuels - remaining_refuels
                    is_locked = bool(quote.get("refuel_locked", False))
                    seconds_until_reset = max(
                        0.0,
                        float(quote.get("seconds_until_refuel_reset", 0.0) or 0.0),
                    )

                    timer_lines.append(
                        f"REFUEL WINDOW: {used_refuels}/{max_refuels} USED ({remaining_refuels} LEFT)"
                    )
                    if used_refuels > 0:
                        hrs = int(seconds_until_reset // 3600)
                        mins = int((seconds_until_reset % 3600) // 60)
                        timer_lines.append(f"WINDOW RESETS IN: {hrs}h {mins:02d}m")

                    if is_locked:
                        self.refuel_instr_txt.text = (
                            "REFUEL WINDOW LOCKED - WAIT FOR RESET"
                        )
                        self.refuel_instr_txt.color = COLOR_ACCENT
                    else:
                        self.refuel_instr_txt.text = "PRESS [F] TO PURCHASE FUEL"
                        self.refuel_instr_txt.color = (255, 255, 255)
                else:
                    self.refuel_instr_txt.text = "PRESS [F] TO PURCHASE FUEL"
                    self.refuel_instr_txt.color = (255, 255, 255)

                self.refuel_instr_txt.draw()

                if ship.last_refuel_time > 0:
                    remaining = 14400 - (time.time() - ship.last_refuel_time)
                    if remaining > 0:
                        hrs = int(remaining // 3600)
                        mins = int((remaining % 3600) // 60)
                        timer_lines.append(
                            f"AUTO-RECHARGE IN PROGRESS: {hrs}h {mins:02d}m REMAINING"
                        )

                if timer_lines:
                    self.refuel_timer_txt.text = " | ".join(timer_lines)
                    self.refuel_timer_txt.draw()
                else:
                    self.refuel_timer_txt.text = ""

        elif self.mode == "SYSTEMS":
            self.header_txt.text = "SHIP SYSTEMS DIAGNOSTIC"
            self.header_txt.draw()

            ship = self.network.player.spaceship
            integ_perc = (
                (ship.integrity / ship.max_integrity) * 100
                if ship.max_integrity > 0
                else 100
            )
            stats = [
                f"MODEL: {ship.model}",
                f"INTEGRITY: {integ_perc:.1f}% ({ship.integrity}/{ship.max_integrity})",
                f"CARGO PODS: {ship.current_cargo_pods} / {ship.max_cargo_pods}",
                f"SHIELD STRENGTH: {ship.current_shields} / {ship.max_shields}",
                f"FIGHTER SQUADRONS: {ship.current_defenders} / {ship.max_defenders}",
                f"SPECIAL WEAPON: {ship.special_weapon or 'NONE'}",
            ]

            for i, s in enumerate(stats):
                arcade.Text(
                    s,
                    content_x,
                    content_y - 120 - i * 40,
                    COLOR_PRIMARY,
                    16,
                    font_name=self.font_ui,
                ).draw()

            # --- Cargo Inventory Display ---
            cargo_x = content_x + 400
            arcade.Text(
                "MANIFESTED CARGO:",
                cargo_x,
                content_y - 120,
                COLOR_SECONDARY,
                14,
                font_name=self.font_ui_bold,
            ).draw()

            inventory = self.network.player.inventory
            if not inventory:
                arcade.Text(
                    "NO CARGO IN BAY.",
                    cargo_x,
                    content_y - 150,
                    (100, 100, 100),
                    12,
                    font_name=self.font_ui,
                ).draw()
            else:
                for j, (item, qty) in enumerate(inventory.items()):
                    if j < 10:  # Limit display to preserve lower action space
                        arcade.Text(
                            f"{item.upper()}: {qty}",
                            cargo_x,
                            content_y - 150 - j * 25,
                            COLOR_TEXT_DIM,
                            12,
                            font_name=self.font_ui,
                        ).draw()

            # Repair button
            planet = self.network.current_planet
            if ship.integrity < ship.max_integrity:
                if planet.repair_multiplier is not None:
                    # Cost per 1% integrity = 0.2% of ship base cost * planet multiplier
                    repair_needed = ship.max_integrity - ship.integrity
                    cost_per_percent = (ship.cost * 0.002) * planet.repair_multiplier
                    repair_cost = int(
                        (repair_needed / (ship.max_integrity / 100)) * cost_per_percent
                    )
                    if repair_cost < 1:
                        repair_cost = 1
                    repair_btn_x = content_x + 520
                    repair_btn_y = 130
                    self._draw_btn(
                        repair_btn_x,
                        repair_btn_y,
                        220,
                        40,
                        f"REPAIR ({repair_cost:,} CR)",
                        COLOR_ACCENT,
                    )
                else:
                    alert_x = content_x
                    alert_y = 130
                    alert_w = 620
                    alert_h = 44
                    arcade.draw_lbwh_rectangle_filled(
                        alert_x, alert_y, alert_w, alert_h, (70, 20, 20, 220)
                    )
                    arcade.draw_lbwh_rectangle_outline(
                        alert_x, alert_y, alert_w, alert_h, COLOR_ACCENT, 2
                    )
                    arcade.Text(
                        "REPAIR UNAVAILABLE AT THIS PORT",
                        alert_x + alert_w / 2,
                        alert_y + alert_h / 2,
                        COLOR_ACCENT,
                        14,
                        anchor_x="center",
                        anchor_y="center",
                        font_name=self.font_ui_bold,
                    ).draw()

            # Show installable items in inventory
            arcade.Text(
                "INVENTORY INSTALLABLES:",
                content_x,
                content_y - 370,
                COLOR_SECONDARY,
                14,
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                "[I] AUTO-FIT ALL",
                content_x + 710,
                content_y - 370,
                COLOR_SECONDARY,
                11,
                anchor_x="right",
                font_name=self.font_ui_bold,
            ).draw()
            y_off = content_y - 400
            installables = [
                "Cargo Pod",
                "Energy Shields",
                "Fighter Squadron",
                "Nanobot Repair Kits",
            ]
            found = False
            for item in installables:
                qty = self.network.player.inventory.get(item, 0)
                if qty > 0:
                    found = True
                    label = item.upper()
                    if item == "Nanobot Repair Kits":
                        label = "REPAIR KITS"
                    arcade.Text(
                        f"{label}: {qty} UNIT(S)",
                        content_x,
                        y_off,
                        COLOR_TEXT_DIM,
                        14,
                        font_name=self.font_ui,
                    ).draw()
                    btn_label = "REPAIR" if item == "Nanobot Repair Kits" else "INSTALL"
                    self._draw_btn(
                        content_x + 430, y_off - 10, 100, 30, btn_label, COLOR_PRIMARY
                    )
                    self._draw_btn(
                        content_x + 540,
                        y_off - 10,
                        150,
                        30,
                        "INSTALL MAX",
                        COLOR_SECONDARY,
                    )
                    y_off -= 45

            if not found:
                arcade.Text(
                    "NO INSTALLABLE COMPONENTS IN CARGO.",
                    content_x,
                    y_off,
                    (100, 100, 100),
                    12,
                    font_name=self.font_ui,
                ).draw()

            owned_planets = self._get_owned_planets_current_commander()
            owned_x = cargo_x
            owned_y = 212
            owned_w = 360
            owned_h = 124
            arcade.draw_lbwh_rectangle_filled(
                owned_x,
                owned_y,
                owned_w,
                owned_h,
                (10, 18, 28, 220),
            )
            arcade.draw_lbwh_rectangle_outline(
                owned_x,
                owned_y,
                owned_w,
                owned_h,
                COLOR_SECONDARY,
                1,
            )
            arcade.Text(
                f"PLANETS OWNED ({len(owned_planets)})",
                owned_x + 12,
                owned_y + owned_h - 24,
                COLOR_PRIMARY,
                12,
                font_name=self.font_ui_bold,
            ).draw()

            max_owned_rows = 3
            if not owned_planets:
                arcade.Text(
                    "NONE",
                    owned_x + 12,
                    owned_y + owned_h - 46,
                    COLOR_TEXT_DIM,
                    11,
                    font_name=self.font_ui,
                ).draw()
            else:
                for idx, planet_name in enumerate(owned_planets[:max_owned_rows]):
                    arcade.Text(
                        self._clamp_text(str(planet_name).upper(), 24),
                        owned_x + 12,
                        owned_y + owned_h - 46 - idx * 18,
                        COLOR_TEXT_DIM,
                        11,
                        font_name=self.font_ui,
                    ).draw()
                if len(owned_planets) > max_owned_rows:
                    arcade.Text(
                        f"+{len(owned_planets) - max_owned_rows} MORE",
                        owned_x + 12,
                        owned_y + owned_h - 46 - max_owned_rows * 18,
                        COLOR_SECONDARY,
                        10,
                        font_name=self.font_ui_bold,
                    ).draw()

            self._draw_btn(
                owned_x + 12,
                owned_y + 10,
                owned_w - 24,
                28,
                "ALL COMMANDERS [L]",
                COLOR_SECONDARY,
                True,
            )

            if self.system_message:
                arcade.Text(
                    self.system_message,
                    content_x,
                    72,
                    COLOR_ACCENT,
                    14,
                    width=760,
                    multiline=True,
                    font_name=self.font_ui_bold,
                ).draw()

            # Planet Treasury (for owned planets)
            if self.network.current_planet.owner == self.network.player.name:
                self._refresh_planet_finance_cache(force=False)
                finance = self.planet_finance_cache or {}
                planet_fin = finance.get("current_planet") or {}

                treasury_y = 100
                TBOX_W = 680
                TBOX_H = 100

                # Draw treasury box
                arcade.draw_lbwh_rectangle_filled(
                    content_x,
                    treasury_y,
                    TBOX_W,
                    TBOX_H,
                    (10, 18, 28, 215),
                )
                arcade.draw_lbwh_rectangle_outline(
                    content_x,
                    treasury_y,
                    TBOX_W,
                    TBOX_H,
                    COLOR_SECONDARY,
                    1,
                )

                arcade.Text(
                    f"PLANET TREASURY: {int(planet_fin.get('credit_balance', 0)):,} CR",
                    content_x + 16,
                    treasury_y + 66,
                    COLOR_PRIMARY,
                    12,
                    font_name=self.font_ui_bold,
                ).draw()
                arcade.Text(
                    f"DAILY: +{int(planet_fin.get('projected_interest', 0)):,} CR",
                    content_x + 16,
                    treasury_y + 44,
                    COLOR_SECONDARY,
                    11,
                    font_name=self.font_ui,
                ).draw()

                # Buttons
                p = self.network.player
                can_deposit = p.credits > 0
                can_withdraw = int(planet_fin.get("credit_balance", 0)) > 0

                self._draw_btn(
                    content_x + 200,
                    treasury_y + 30,
                    140,
                    40,
                    "P-DEPOSIT",
                    COLOR_PRIMARY,
                    can_deposit,
                )
                self._draw_btn(
                    content_x + 360,
                    treasury_y + 30,
                    140,
                    40,
                    "P-WITHDRAW",
                    COLOR_ACCENT,
                    can_withdraw,
                )

        if self.mode == "BANK":
            self.header_txt.text = "GALAXY FIRST NATIONAL BANK"
            self.header_txt.draw()

            self._refresh_planet_finance_cache(force=False)

            p = self.network.player
            arcade.Text(
                f"LIQUID CREDITS: {p.credits:,} CR",
                content_x,
                content_y - 120,
                COLOR_PRIMARY,
                18,
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"SECURE SAVINGS: {p.bank_balance:,} CR",
                content_x,
                content_y - 160,
                COLOR_PRIMARY,
                18,
                font_name=self.font_ui,
            ).draw()

            arcade.Text(
                "CHOOSE AN ACTION AND AMOUNT:",
                content_x,
                content_y - 220,
                COLOR_TEXT_DIM,
                14,
                font_name=self.font_ui,
            ).draw()

            # Buttons for Deposit/Withdraw
            btn_y = content_y - 320
            # Deposit
            self._draw_btn(
                content_x,
                btn_y,
                180,
                50,
                "DEPOSIT...",
                COLOR_PRIMARY,
                p.credits > 0,
            )
            self._draw_btn(
                content_x,
                btn_y - 70,
                180,
                50,
                "DEPOSIT ALL",
                COLOR_PRIMARY,
                p.credits > 0,
            )

            # Withdraw
            self._draw_btn(
                content_x + 200,
                btn_y,
                180,
                50,
                "WITHDRAW...",
                COLOR_ACCENT,
                p.bank_balance > 0,
            )
            self._draw_btn(
                content_x + 200,
                btn_y - 70,
                180,
                50,
                "WITHDRAW ALL",
                COLOR_ACCENT,
                p.bank_balance > 0,
            )

            finance = self.planet_finance_cache or {}
            planet_fin = finance.get("current_planet") or {}
            can_manage_planet = bool(finance.get("can_manage", False))

            treasury_y = btn_y - 340
            TBOX_W = 680
            TBOX_H = 240
            arcade.draw_lbwh_rectangle_filled(
                content_x,
                treasury_y,
                TBOX_W,
                TBOX_H,
                (10, 18, 28, 215),
            )
            arcade.draw_lbwh_rectangle_outline(
                content_x,
                treasury_y,
                TBOX_W,
                TBOX_H,
                COLOR_SECONDARY,
                1,
            )

            arcade.Text(
                f"PLANET TREASURY: {str(getattr(self.network.current_planet, 'name', 'UNKNOWN')).upper()}",
                content_x + 16,
                treasury_y + TBOX_H - 30,
                COLOR_PRIMARY,
                14,
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                f"POPULATION: {int(planet_fin.get('population', getattr(self.network.current_planet, 'population', 0))):,}",
                content_x + 16,
                treasury_y + TBOX_H - 54,
                COLOR_TEXT_DIM,
                12,
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"BASE CREDITS: {int(planet_fin.get('credit_balance', 0)):,} CR",
                content_x + 16,
                treasury_y + TBOX_H - 78,
                COLOR_PRIMARY,
                12,
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"PROJECTED DAILY INTEREST: +{int(planet_fin.get('projected_interest', 0)):,} CR",
                content_x + 16,
                treasury_y + TBOX_H - 102,
                COLOR_SECONDARY,
                12,
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"ALL OWNED PLANETS: {int(finance.get('owned_total_balance', 0)):,} CR | +{int(finance.get('owned_total_projected_interest', 0)):,} CR/DAY",
                content_x + 16,
                treasury_y + TBOX_H - 126,
                COLOR_TEXT_DIM,
                11,
                font_name=self.font_ui,
            ).draw()

            # TREASURY ACCESS LOCKED label (above the action buttons)
            if not can_manage_planet:
                owner_name = str(
                    planet_fin.get("owner")
                    or getattr(self.network.current_planet, "owner", "UNCLAIMED")
                )
                arcade.Text(
                    f"TREASURY ACCESS LOCKED (OWNER: {owner_name.upper()})",
                    content_x + 16,
                    treasury_y + 94,
                    COLOR_ACCENT,
                    11,
                    font_name=self.font_ui_bold,
                ).draw()

            # Action buttons row (4 buttons, each 150 wide, 10 gap)
            self._draw_btn(
                content_x + 16,
                treasury_y + 50,
                150,
                36,
                "P-DEPOSIT...",
                COLOR_PRIMARY,
                can_manage_planet and p.credits > 0,
            )
            self._draw_btn(
                content_x + 176,
                treasury_y + 50,
                150,
                36,
                "P-DEPOSIT ALL",
                COLOR_PRIMARY,
                can_manage_planet and p.credits > 0,
            )
            self._draw_btn(
                content_x + 336,
                treasury_y + 50,
                150,
                36,
                "P-WITHDRAW...",
                COLOR_ACCENT,
                can_manage_planet and int(planet_fin.get("credit_balance", 0)) > 0,
            )
            self._draw_btn(
                content_x + 496,
                treasury_y + 50,
                150,
                36,
                "P-WITHDRAW ALL",
                COLOR_ACCENT,
                can_manage_planet and int(planet_fin.get("credit_balance", 0)) > 0,
            )

            if self.bank_message:
                arcade.Text(
                    self.bank_message.upper(),
                    content_x,
                    treasury_y - 30,
                    COLOR_ACCENT,
                    16,
                    font_name=self.font_ui_bold,
                ).draw()

        elif self.mode == "CREW":
            self.header_txt.text = "CREW QUARTERS"
            self.header_txt.draw()

            # Dark overlay so text is readable regardless of planet background
            arcade.draw_lbwh_rectangle_filled(
                sidebar_w,
                62,
                SCREEN_WIDTH - sidebar_w,
                SCREEN_HEIGHT - 130,
                (5, 8, 12, 195),
            )

            p = self.network.player
            ship = p.spaceship

            # Current Crew
            arcade.Text(
                "CURRENT CREW",
                content_x,
                content_y - 80,
                COLOR_SECONDARY,
                16,
                font_name=self.font_ui_bold,
            ).draw()
            y_off = content_y - 125

            for spec in ["weapons", "engineer"]:
                slots = ship.crew_slots.get(spec, 0)
                member = p.crew.get(spec)

                if slots > 0:
                    if member:
                        arcade.Text(
                            f"{spec.upper()} EXPERT: {member.name} (LVL {member.level})",
                            content_x,
                            y_off,
                            COLOR_PRIMARY,
                            14,
                            font_name=self.font_ui,
                        ).draw()
                        arcade.Text(
                            f"MORALE {int(getattr(member, 'morale', 100))}% | FATIGUE {int(getattr(member, 'fatigue', 0))}% | PERKS: {member.get_perk_summary()}",
                            content_x + 20,
                            y_off - 18,
                            COLOR_TEXT_DIM,
                            10,
                            font_name=self.font_ui,
                            width=600,
                        ).draw()
                        self._draw_btn(
                            content_x + 650,
                            y_off - 10,
                            100,
                            30,
                            "DISMISS",
                            COLOR_ACCENT,
                        )
                    else:
                        arcade.Text(
                            f"{spec.upper()} EXPERT: VACANT",
                            content_x,
                            y_off,
                            COLOR_TEXT_DIM,
                            14,
                            font_name=self.font_ui,
                        ).draw()
                    y_off -= 58
                else:
                    arcade.Text(
                        f"{spec.upper()} EXPERT: NO SLOTS AVAILABLE FOR THIS SHIP",
                        content_x,
                        y_off,
                        (100, 50, 50),
                        12,
                        font_name=self.font_ui,
                    ).draw()
                    y_off -= 40

            # Hireable Crew at this Planet
            y_off -= 30
            arcade.draw_line(
                content_x, y_off + 15, SCREEN_WIDTH - 50, y_off + 15, COLOR_SECONDARY, 1
            )
            arcade.Text(
                "AVAILABLE FOR HIRE",
                content_x,
                y_off - 15,
                COLOR_SECONDARY,
                16,
                font_name=self.font_ui_bold,
            ).draw()
            y_off -= 60

            offers = self.network.get_planet_crew_offers(self.network.current_planet)
            if not offers:
                arcade.Text(
                    "NO CREW CANDIDATES AVAILABLE AT THIS PORT.",
                    content_x,
                    y_off,
                    COLOR_TEXT_DIM,
                    14,
                    font_name=self.font_ui,
                ).draw()
            else:
                for offer in offers:
                    s_type = offer["type"]
                    level = int(offer["level"])
                    cost = int(offer["hire_cost"])
                    daily_pay = int(offer["daily_pay"])
                    can_afford = p.credits >= cost

                    arcade.Text(
                        f"LVL {level} {s_type.upper()} EXPERT",
                        content_x,
                        y_off,
                        COLOR_PRIMARY,
                        14,
                        font_name=self.font_ui,
                    ).draw()
                    arcade.Text(
                        f"COST: {cost:,} CR | PAY: {daily_pay:,} CR / 24H",
                        content_x + 250,
                        y_off,
                        COLOR_TEXT_DIM,
                        12,
                        font_name=self.font_ui,
                    ).draw()

                    has_slot = ship.crew_slots.get(s_type, 0) > 0
                    has_already = s_type in p.crew

                    enabled = can_afford and has_slot and not has_already
                    label = "HIRE" if not has_already else "ALREADY HIRED"
                    if not has_slot:
                        label = "NO SLOT"

                    self._draw_btn(
                        content_x + 650,
                        y_off - 10,
                        150,
                        30,
                        label,
                        COLOR_PRIMARY,
                        enabled,
                    )
                    y_off -= 50

            if self.crew_message:
                arcade.Text(
                    self.crew_message.upper(),
                    content_x,
                    80,
                    COLOR_ACCENT,
                    16,
                    font_name=self.font_ui_bold,
                ).draw()

        elif self.mode == "MAIL":
            self.header_txt.text = "SECURE MESSAGING TERMINAL"
            self.header_txt.draw()

            messages = self.network.player.messages
            content_x = sidebar_w + 50

            # Inbox/Outbox list
            arcade.draw_lbwh_rectangle_filled(
                content_x - 10, 150, 400, SCREEN_HEIGHT - 350, (10, 15, 20, 200)
            )
            arcade.draw_lbwh_rectangle_outline(
                content_x - 10, 150, 400, SCREEN_HEIGHT - 350, COLOR_SECONDARY, 1
            )

            if not messages:
                arcade.Text(
                    "INBOX EMPTY",
                    content_x + 20,
                    SCREEN_HEIGHT - 250,
                    COLOR_TEXT_DIM,
                    14,
                    font_name=self.font_ui,
                ).draw()
            else:
                for i, msg in enumerate(messages):
                    is_sel = i == self.selected_mail_index
                    y = SCREEN_HEIGHT - 230 - i * 40
                    if is_sel:
                        arcade.draw_lbwh_rectangle_filled(
                            content_x, y - 5, 380, 30, (*COLOR_PRIMARY, 50)
                        )

                    color = COLOR_PRIMARY if not msg.is_read else COLOR_TEXT_DIM
                    if is_sel:
                        color = COLOR_PRIMARY

                    unread_mark = "*" if not msg.is_read else " "
                    txt = f"{unread_mark} {msg.sender[:12]:<12} | {msg.subject[:15]}"
                    arcade.Text(
                        txt, content_x + 10, y, color, 14, font_name=self.font_ui
                    ).draw()

            # Message Detail View
            detail_x = content_x + 420
            detail_w = 600
            arcade.draw_lbwh_rectangle_filled(
                detail_x, 150, detail_w, SCREEN_HEIGHT - 350, (5, 10, 15, 230)
            )
            arcade.draw_lbwh_rectangle_outline(
                detail_x, 150, detail_w, SCREEN_HEIGHT - 350, COLOR_PRIMARY, 1
            )

            if self.selected_mail_index < len(messages):
                msg = messages[self.selected_mail_index]
                if not msg.is_read:
                    msg_id = str(getattr(msg, "id", "") or "")
                    if msg_id and msg_id != self.last_read_message_id:
                        if self.network.mark_message_read(msg_id):
                            self.last_read_message_id = msg_id
                            msg.is_read = True

                arcade.Text(
                    f"FROM: {msg.sender}",
                    detail_x + 20,
                    SCREEN_HEIGHT - 230,
                    COLOR_ACCENT,
                    14,
                    font_name=self.font_ui_bold,
                ).draw()
                arcade.Text(
                    f"SENT: {msg.timestamp}",
                    detail_x + 20,
                    SCREEN_HEIGHT - 255,
                    COLOR_TEXT_DIM,
                    10,
                    font_name=self.font_ui,
                ).draw()
                arcade.Text(
                    f"SUBJECT: {msg.subject}",
                    detail_x + 20,
                    SCREEN_HEIGHT - 285,
                    COLOR_PRIMARY,
                    16,
                    font_name=self.font_ui_bold,
                ).draw()
                arcade.draw_line(
                    detail_x + 20,
                    SCREEN_HEIGHT - 300,
                    detail_x + detail_w - 20,
                    SCREEN_HEIGHT - 300,
                    COLOR_SECONDARY,
                    1,
                )

                arcade.Text(
                    msg.body,
                    detail_x + 20,
                    SCREEN_HEIGHT - 330,
                    COLOR_PRIMARY,
                    14,
                    width=detail_w - 40,
                    multiline=True,
                    font_name=self.font_ui,
                ).draw()
            else:
                arcade.Text(
                    "SELECT A MESSAGE TO VIEW CONTENTS",
                    detail_x + detail_w // 2,
                    SCREEN_HEIGHT // 2,
                    COLOR_TEXT_DIM,
                    14,
                    anchor_x="center",
                    font_name=self.font_ui,
                ).draw()

            # Compose Button
            has_selected_message = messages and self.selected_mail_index < len(messages)
            self._draw_btn(content_x, 80, 140, 40, "COMPOSE [N]", COLOR_PRIMARY)
            self._draw_btn(
                content_x + 160,
                80,
                140,
                40,
                "REPLY [R]",
                COLOR_SECONDARY,
                bool(has_selected_message),
            )
            self._draw_btn(content_x + 320, 80, 140, 40, "DELETE [DEL]", COLOR_ACCENT)

            if self.mail_message:
                arcade.Text(
                    self.mail_message,
                    content_x + 480,
                    95,
                    COLOR_ACCENT,
                    12,
                    font_name=self.font_ui,
                ).draw()

        elif self.mode == "SHIPYARD":
            self.header_txt.text = "URTH ORBITAL SHIPYARD"
            self.header_txt.draw()

            # Current Ship Value / Trade-In Panel
            ship = self.network.player.spaceship
            info = ship.get_trade_in_info()
            trade_in = info["trade_in"]

            panel_x = content_x
            panel_y = content_y - 100

            # Draw Detailed Trade-in Box
            arcade.draw_lbwh_rectangle_filled(
                panel_x, panel_y - 105, 600, 115, (20, 30, 40, 240)
            )
            arcade.draw_lbwh_rectangle_outline(
                panel_x, panel_y - 105, 600, 115, COLOR_SECONDARY, 1
            )

            # Calculate exact credit penalty for display
            # Max possible trade-in is 50% of total value.
            # Current trade-in is (0.5 * integrity/100) * total_value
            max_possible = info["total_value"] * 0.5
            credit_penalty = int(max_possible - trade_in)

            arcade.Text(
                f"CURRENT VESSEL: {ship.model}",
                panel_x + 15,
                panel_y - 20,
                COLOR_PRIMARY,
                14,
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                f"BASE VAL: {info['base_cost']:,} CR | UPGRADES: {info['upgrades_cost']:,} CR",
                panel_x + 15,
                panel_y - 45,
                COLOR_TEXT_DIM,
                12,
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"INTEGRITY PENALTY: -{credit_penalty:,} CR ({ship.integrity}/{ship.max_integrity})",
                panel_x + 15,
                panel_y - 70,
                (255, 100, 100),
                12,
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"FINAL TRADE-IN OFFER: {trade_in:,} CR",
                panel_x + 15,
                panel_y - 95,
                COLOR_ACCENT,
                14,
                font_name=self.font_ui_bold,
            ).draw()

            # Scroll limits for shipyard
            max_s_scroll = max(0, len(self.network.spaceships) - 4)
            if self.shipyard_scroll > max_s_scroll:
                self.shipyard_scroll = max_s_scroll

            y_off = panel_y - 210
            for i, catalog_ship in enumerate(self.network.spaceships):
                display_idx = i - self.shipyard_scroll
                if display_idx < 0 or display_idx >= 4:
                    continue

                is_sel = i == self.selected_ship_index
                y = y_off - display_idx * 110

                if is_sel:
                    arcade.draw_lbwh_rectangle_filled(
                        content_x - 10, y - 10, 600, 100, (*COLOR_PRIMARY, 30)
                    )

                color = COLOR_PRIMARY if is_sel else COLOR_TEXT_DIM
                arcade.Text(
                    catalog_ship.model.upper(),
                    content_x,
                    y + 60,
                    color,
                    18,
                    font_name=self.font_ui_bold,
                ).draw()

                # Show Price vs Net Cost
                net = catalog_ship.cost - trade_in
                arcade.Text(
                    f"NET COST: {net:,} CR (LIST: {catalog_ship.cost:,} CR)",
                    content_x,
                    y + 35,
                    COLOR_ACCENT,
                    14,
                    font_name=self.font_ui,
                ).draw()
                arcade.Text(
                    f"CARGO: {catalog_ship.max_cargo_pods} | SHIELDS: {catalog_ship.max_shields} | FIGHTERS: {catalog_ship.max_defenders}",
                    content_x,
                    y + 15,
                    COLOR_TEXT_DIM,
                    12,
                    font_name=self.font_ui,
                ).draw()

                if is_sel:
                    # Check total funds (Wallet + Bank) for purchase button enablement
                    total_funds = (
                        self.network.player.credits + self.network.player.bank_balance
                    )
                    self._draw_btn(
                        content_x + 450,
                        y + 25,
                        120,
                        40,
                        "PURCHASE",
                        COLOR_PRIMARY,
                        total_funds >= (catalog_ship.cost - trade_in),
                    )

            # --- Visual Scroll Bar (Shipyard) ---
            if len(self.network.spaceships) > 4:
                sb_x = content_x + 605
                sb_y = y_off - (3 * 110) - 10
                sb_h = (4 * 110) + 10
                arcade.draw_lbwh_rectangle_filled(
                    sb_x, sb_y, 10, sb_h, (20, 30, 40, 150)
                )

                # Thumb
                thumb_h = max(20, (4 / len(self.network.spaceships)) * sb_h)
                scroll_perc = self.shipyard_scroll / (len(self.network.spaceships) - 4)
                thumb_y = (y_off + 90 - thumb_h) - (scroll_perc * (sb_h - thumb_h))
                arcade.draw_lbwh_rectangle_filled(
                    sb_x + 1, thumb_y, 8, thumb_h, COLOR_SECONDARY
                )

            selected_ship = self.network.spaceships[self.selected_ship_index]
            compare_x = content_x + 640
            compare_y = panel_y - 425
            compare_w = 420
            compare_h = 430
            arcade.draw_lbwh_rectangle_filled(
                compare_x,
                compare_y,
                compare_w,
                compare_h,
                (14, 24, 34, 230),
            )
            arcade.draw_lbwh_rectangle_outline(
                compare_x, compare_y, compare_w, compare_h, COLOR_SECONDARY, 1
            )

            sel_roles = ", ".join(
                getattr(selected_ship, "role_tags", []) or ["UNASSIGNED"]
            )
            sel_modules = ", ".join(
                [
                    m.replace("_", " ").upper()
                    for m in getattr(selected_ship, "installed_modules", [])
                ]
            )
            if not sel_modules:
                sel_modules = "NONE"

            arcade.Text(
                "ROLE COMPARE",
                compare_x + 15,
                compare_y + compare_h - 30,
                COLOR_PRIMARY,
                14,
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                f"{selected_ship.model.upper()} VS {ship.model.upper()}",
                compare_x + 15,
                compare_y + compare_h - 55,
                COLOR_TEXT_DIM,
                11,
                font_name=self.font_ui,
                width=compare_w - 20,
            ).draw()
            arcade.Text(
                f"ROLES: {sel_roles.upper()}",
                compare_x + 15,
                compare_y + compare_h - 82,
                COLOR_SECONDARY,
                11,
                font_name=self.font_ui,
                width=compare_w - 20,
            ).draw()
            arcade.Text(
                f"MODULES ({int(getattr(selected_ship, 'module_slots', 0))}): {sel_modules}",
                compare_x + 15,
                compare_y + compare_h - 104,
                COLOR_ACCENT,
                11,
                font_name=self.font_ui,
                width=compare_w - 20,
            ).draw()

            role_order = ["Hauler", "Interceptor", "Siege", "Runner"]
            for idx, role_name in enumerate(role_order):
                y_role = compare_y + compare_h - 150 - idx * 58
                sel_score = (
                    float(selected_ship.get_role_strength_score(role_name))
                    if hasattr(selected_ship, "get_role_strength_score")
                    else 0.0
                )
                cur_score = (
                    float(ship.get_role_strength_score(role_name))
                    if hasattr(ship, "get_role_strength_score")
                    else 0.0
                )
                total_score = max(1.0, sel_score + cur_score)
                sel_ratio = max(0.0, min(1.0, sel_score / total_score))
                delta_pct = ((sel_score - cur_score) / max(1.0, cur_score)) * 100.0
                delta_color = COLOR_ACCENT if delta_pct >= 0 else (255, 105, 105)

                arcade.Text(
                    role_name.upper(),
                    compare_x + 15,
                    y_role + 16,
                    COLOR_TEXT_DIM,
                    11,
                    font_name=self.font_ui_bold,
                ).draw()
                arcade.draw_lbwh_rectangle_filled(
                    compare_x + 120,
                    y_role + 10,
                    250,
                    12,
                    (32, 40, 52),
                )
                arcade.draw_lbwh_rectangle_filled(
                    compare_x + 120,
                    y_role + 10,
                    int(250 * sel_ratio),
                    12,
                    COLOR_PRIMARY,
                )
                arcade.draw_lbwh_rectangle_filled(
                    compare_x + 120 + int(250 * sel_ratio),
                    y_role + 10,
                    int(250 * (1.0 - sel_ratio)),
                    12,
                    COLOR_SECONDARY,
                )
                arcade.Text(
                    f"{delta_pct:+.0f}%",
                    compare_x + 380,
                    y_role + 9,
                    delta_color,
                    11,
                    anchor_x="right",
                    font_name=self.font_ui_bold,
                ).draw()

            sel_cargo = (
                int(selected_ship.get_effective_max_cargo())
                if hasattr(selected_ship, "get_effective_max_cargo")
                else int(selected_ship.current_cargo_pods)
            )
            cur_cargo = (
                int(ship.get_effective_max_cargo())
                if hasattr(ship, "get_effective_max_cargo")
                else int(ship.current_cargo_pods)
            )
            sel_burn = (
                float(selected_ship.get_effective_fuel_burn_rate())
                if hasattr(selected_ship, "get_effective_fuel_burn_rate")
                else float(selected_ship.fuel_burn_rate)
            )
            cur_burn = (
                float(ship.get_effective_fuel_burn_rate())
                if hasattr(ship, "get_effective_fuel_burn_rate")
                else float(ship.fuel_burn_rate)
            )

            arcade.Text(
                f"EFFECTIVE CARGO: {sel_cargo} VS {cur_cargo}",
                compare_x + 15,
                compare_y + 48,
                COLOR_TEXT_DIM,
                11,
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"FUEL BURN: {sel_burn:.2f} VS {cur_burn:.2f} (LOWER IS BETTER)",
                compare_x + 15,
                compare_y + 26,
                COLOR_TEXT_DIM,
                11,
                font_name=self.font_ui,
            ).draw()

            if self.shipyard_message:
                arcade.Text(
                    self.shipyard_message.upper(),
                    content_x,
                    80,
                    COLOR_ACCENT,
                    16,
                    font_name=self.font_ui_bold,
                ).draw()

        if self.prompt_mode == "ACTION_SLIDER":
            arcade.draw_lbwh_rectangle_filled(
                0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 200)
            )
            box_w, box_h = 520, 260
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2
            arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (10, 15, 20, 250))
            arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_PRIMARY, 2)

            context_label = (
                f"{self.action_slider_kind} {self.action_slider_item_name}".strip()
                if self.action_slider_context == "MARKET"
                else f"TRANSFER {str(self.action_slider_kind or '').upper()}"
            )
            direction_label = ""
            if self.action_slider_context == "ORBIT":
                direction_label = (
                    "TO PLANET"
                    if self.action_slider_direction == "TO_PLANET"
                    else "TO SHIP"
                )
            max_val = max(0, int(self.action_slider_max))
            cur_val = max(0, min(max_val, int(self.action_slider_value)))

            arcade.Text(
                context_label.upper(),
                bx + box_w // 2,
                by + box_h - 56,
                COLOR_PRIMARY,
                20,
                anchor_x="center",
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                (
                    f"DIRECTION: {direction_label}"
                    if direction_label
                    else "ADJUST QUANTITY USING SLIDER"
                ),
                bx + box_w // 2,
                by + box_h - 86,
                COLOR_TEXT_DIM,
                12,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

            sx1, sx2 = bx + 48, bx + box_w - 48
            sy = by + box_h // 2
            arcade.draw_line(sx1, sy, sx2, sy, COLOR_SECONDARY, 3)

            if max_val > 0:
                knob_x = sx1 + int((cur_val / max_val) * (sx2 - sx1))
            else:
                knob_x = sx1
            arcade.draw_circle_filled(knob_x, sy, 11, COLOR_PRIMARY)
            arcade.draw_circle_outline(knob_x, sy, 11, COLOR_SECONDARY, 2)

            arcade.Text(
                "0",
                sx1,
                sy - 24,
                COLOR_TEXT_DIM,
                10,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"MAX {max_val}",
                sx2,
                sy - 24,
                COLOR_TEXT_DIM,
                10,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                f"QTY: {cur_val}",
                bx + box_w // 2,
                sy + 28,
                COLOR_ACCENT,
                30,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

            self._draw_btn(
                bx + 78,
                by + 26,
                160,
                42,
                "CONFIRM",
                COLOR_PRIMARY,
                enabled=cur_val > 0,
            )
            self._draw_btn(
                bx + box_w - 238,
                by + 26,
                160,
                42,
                "CANCEL",
                COLOR_SECONDARY,
                enabled=True,
            )
            arcade.Text(
                "[LEFT/RIGHT] ADJUST | [ENTER] CONFIRM | [ESC] CANCEL",
                bx + box_w // 2,
                by + 10,
                COLOR_TEXT_DIM,
                11,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

        if self.prompt_mode == "INSTALL_CHOICE":
            arcade.draw_lbwh_rectangle_filled(
                0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 200)
            )
            box_w, box_h = 500, 250
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2
            arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (10, 15, 20, 250))
            arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_PRIMARY, 2)

            arcade.Text(
                f"PURCHASED: {self.trade_item_name}",
                bx + box_w // 2,
                by + box_h - 50,
                COLOR_PRIMARY,
                20,
                anchor_x="center",
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                "WOULD YOU LIKE TO INSTALL IT NOW OR PUT IT IN CARGO?",
                bx + box_w // 2,
                by + box_h - 90,
                COLOR_TEXT_DIM,
                12,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

            self._draw_btn(bx + 80, by + 50, 150, 50, "INSTALL", COLOR_PRIMARY)
            self._draw_btn(bx + 270, by + 50, 150, 50, "CARGO", COLOR_SECONDARY)

        if self.prompt_mode == "COMMANDER_STATUS_BOARD":
            arcade.draw_lbwh_rectangle_filled(
                0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 210)
            )
            box_w, box_h = 1040, 560
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2

            arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (10, 15, 20, 250))
            arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_PRIMARY, 2)

            arcade.Text(
                "COMMANDER STATUS BOARD",
                bx + 20,
                by + box_h - 34,
                COLOR_PRIMARY,
                20,
                font_name=self.font_ui_bold,
            ).draw()
            self._draw_btn(
                bx + box_w - 132, by + box_h - 44, 112, 30, "CLOSE", COLOR_ACCENT, True
            )

            list_x = bx + 20
            list_y = by + 46
            list_w = box_w - 40
            list_h = box_h - 100
            arcade.draw_lbwh_rectangle_filled(
                list_x, list_y, list_w, list_h, (6, 10, 16, 220)
            )
            arcade.draw_lbwh_rectangle_outline(
                list_x, list_y, list_w, list_h, COLOR_SECONDARY, 1
            )

            header_y = list_y + list_h - 26
            col_name = list_x + 10
            col_status = list_x + 190
            col_level = list_x + 280
            col_ship = list_x + 330
            col_location = list_x + 520
            col_owned = list_x + 660
            col_planets = list_x + 730

            for title, cx in [
                ("COMMANDER", col_name),
                ("STATUS", col_status),
                ("LVL", col_level),
                ("SHIP", col_ship),
                ("LOCATION", col_location),
                ("OWNED", col_owned),
                ("OWNED PLANETS", col_planets),
            ]:
                arcade.Text(
                    title,
                    cx,
                    header_y,
                    COLOR_SECONDARY,
                    11,
                    font_name=self.font_ui_bold,
                ).draw()

            arcade.draw_line(
                list_x + 8,
                header_y - 4,
                list_x + list_w - 8,
                header_y - 4,
                COLOR_SECONDARY,
                1,
            )

            if self.commander_status_error:
                arcade.Text(
                    self._clamp_text(self.commander_status_error, 140),
                    bx + box_w // 2,
                    by + box_h // 2,
                    COLOR_ACCENT,
                    14,
                    anchor_x="center",
                    font_name=self.font_ui_bold,
                ).draw()
            else:
                rows = list(self.commander_status_rows or [])
                visible_rows = 12
                row_h = 36
                max_scroll = max(0, len(rows) - visible_rows)
                self.commander_status_scroll = max(
                    0, min(int(self.commander_status_scroll), max_scroll)
                )

                start = int(self.commander_status_scroll)
                end = min(len(rows), start + visible_rows)
                y = header_y - 30
                for idx in range(start, end):
                    row = rows[idx]
                    if (idx - start) % 2 == 0:
                        arcade.draw_lbwh_rectangle_filled(
                            list_x + 8, y - 6, list_w - 16, row_h - 2, (14, 22, 34, 180)
                        )

                    planets_summary = ", ".join(
                        list(row.get("owned_planets", []) or [])
                    )
                    arcade.Text(
                        self._clamp_text(str(row.get("name", "")).upper(), 22),
                        col_name,
                        y,
                        COLOR_PRIMARY,
                        11,
                        font_name=self.font_ui,
                    ).draw()
                    arcade.Text(
                        self._clamp_text(str(row.get("status", "")).upper(), 10),
                        col_status,
                        y,
                        COLOR_TEXT_DIM,
                        11,
                        font_name=self.font_ui,
                    ).draw()
                    arcade.Text(
                        str(int(row.get("level", 1))),
                        col_level,
                        y,
                        COLOR_TEXT_DIM,
                        11,
                        font_name=self.font_ui,
                    ).draw()
                    arcade.Text(
                        self._clamp_text(str(row.get("ship", "")).upper(), 22),
                        col_ship,
                        y,
                        COLOR_TEXT_DIM,
                        11,
                        font_name=self.font_ui,
                    ).draw()
                    arcade.Text(
                        self._clamp_text(str(row.get("location", "")).upper(), 16),
                        col_location,
                        y,
                        COLOR_TEXT_DIM,
                        11,
                        font_name=self.font_ui,
                    ).draw()
                    arcade.Text(
                        str(int(row.get("owned_planets_count", 0))),
                        col_owned,
                        y,
                        COLOR_TEXT_DIM,
                        11,
                        font_name=self.font_ui,
                    ).draw()
                    arcade.Text(
                        self._clamp_text(planets_summary.upper(), 32),
                        col_planets,
                        y,
                        COLOR_TEXT_DIM,
                        11,
                        font_name=self.font_ui,
                    ).draw()
                    y -= row_h

                arcade.Text(
                    f"ROWS {start + 1 if rows else 0}-{end} / {len(rows)}  |  [UP/DOWN] SCROLL  [ESC] CLOSE",
                    bx + box_w // 2,
                    by + 16,
                    COLOR_TEXT_DIM,
                    10,
                    anchor_x="center",
                    font_name=self.font_ui,
                ).draw()

        if self.prompt_mode == "MAIL_COMPOSE":
            # Darken Background
            arcade.draw_lbwh_rectangle_filled(
                0,
                0,
                SCREEN_WIDTH,
                SCREEN_HEIGHT,
                (0, 0, 0, 180),
            )

            box_w, box_h = 700, 500
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2

            arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (10, 15, 20, 250))
            arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_PRIMARY, 2)

            arcade.Text(
                "COMPOSE INTERSTELLAR SIGNAL",
                bx + 30,
                by + box_h - 50,
                COLOR_PRIMARY,
                20,
                font_name=self.font_ui_bold,
            ).draw()

            # Recipient Selector
            others = self.network.get_other_players()
            arcade.Text(
                "RECIPIENT:",
                bx + 30,
                by + box_h - 110,
                COLOR_TEXT_DIM,
                14,
                font_name=self.font_ui,
            ).draw()

            if not others:
                arcade.Text(
                    "NO OTHER CMDRS DETECTED IN SECTOR",
                    bx + 150,
                    by + box_h - 110,
                    COLOR_ACCENT,
                    14,
                    font_name=self.font_ui,
                ).draw()
            else:
                # Dropdown-like display
                target_name = others[self.selected_recipient_index % len(others)]
                arcade.draw_lbwh_rectangle_filled(
                    bx + 150, by + box_h - 120, 300, 30, (30, 40, 50)
                )
                arcade.Text(
                    self._clamp_text(target_name.upper(), 28),
                    bx + 160,
                    by + box_h - 110,
                    COLOR_PRIMARY,
                    14,
                    font_name=self.font_ui_bold,
                ).draw()
                arcade.Text(
                    "< [LEFT/RIGHT] CYCLE >",
                    bx + 470,
                    by + box_h - 110,
                    COLOR_TEXT_DIM,
                    10,
                    font_name=self.font_ui,
                ).draw()

            # Subject Input
            is_sub = self.mail_input_field == "SUBJECT"
            arcade.Text(
                "SUBJECT:",
                bx + 30,
                by + box_h - 160,
                COLOR_TEXT_DIM,
                14,
                font_name=self.font_ui,
            ).draw()
            arcade.draw_lbwh_rectangle_filled(
                bx + 150,
                by + box_h - 170,
                500,
                30,
                (30, 40, 50) if not is_sub else (50, 60, 80),
            )
            if is_sub:
                arcade.draw_lbwh_rectangle_outline(
                    bx + 150, by + box_h - 170, 500, 30, COLOR_PRIMARY, 1
                )
            arcade.Text(
                self.mail_subject_input
                + ("_" if is_sub and (time.time() % 1 > 0.5) else ""),
                bx + 160,
                by + box_h - 160,
                COLOR_PRIMARY,
                14,
                font_name=self.font_ui,
            ).draw()

            # Body Input
            is_body = self.mail_input_field == "BODY"
            arcade.Text(
                "MESSAGE:",
                bx + 30,
                by + box_h - 210,
                COLOR_TEXT_DIM,
                14,
                font_name=self.font_ui,
            ).draw()
            arcade.draw_lbwh_rectangle_filled(
                bx + 150,
                by + box_h - 430,
                500,
                240,
                (30, 40, 50) if not is_body else (50, 60, 80),
            )
            if is_body:
                arcade.draw_lbwh_rectangle_outline(
                    bx + 150, by + box_h - 430, 500, 240, COLOR_PRIMARY, 1
                )

            # Multi-line text wrapping for display
            wrap_text = ""
            chars = 0
            for word in self.mail_body_input.split(" "):
                if chars + len(word) > 45:
                    wrap_text += "\n"
                    chars = 0
                wrap_text += word + " "
                chars += len(word) + 1

            arcade.Text(
                wrap_text + ("_" if is_body and (time.time() % 1 > 0.5) else ""),
                bx + 160,
                by + box_h - 230,
                COLOR_PRIMARY,
                14,
                width=480,
                multiline=True,
                font_name=self.font_ui,
            ).draw()

            # Char count
            color = COLOR_PRIMARY if len(self.mail_body_input) < 450 else COLOR_ACCENT
            arcade.Text(
                f"{len(self.mail_body_input)}/500",
                bx + 650,
                by + box_h - 450,
                color,
                12,
                anchor_x="right",
                font_name=self.font_ui,
            ).draw()

            # Instructions
            arcade.Text(
                "[LEFT/RIGHT] RECIPIENT | [TAB] SWITCH FIELD\n[ENTER] TRANSMIT | [ESC] ABORT",
                bx + box_w // 2,
                by + 30,
                COLOR_TEXT_DIM,
                12,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

        if self.prompt_mode == "CREW_NAMING":
            arcade.draw_lbwh_rectangle_filled(
                0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 200)
            )
            box_w, box_h = 500, 250
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2
            arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (10, 15, 20, 250))
            arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_PRIMARY, 2)

            arcade.Text(
                "NAME YOUR NEW CREW MEMBER:",
                bx + box_w // 2,
                by + box_h - 60,
                COLOR_PRIMARY,
                18,
                anchor_x="center",
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                f"{self.naming_name_input}_",
                bx + box_w // 2,
                by + box_h // 2,
                COLOR_ACCENT,
                30,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                "[ENTER] TO CONFIRM | [ESC] TO CANCEL",
                bx + box_w // 2,
                by + 40,
                COLOR_TEXT_DIM,
                12,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

        if self.prompt_mode == "GIVE_SHIP_RECIPIENT":
            arcade.draw_lbwh_rectangle_filled(
                0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 200)
            )
            box_w, box_h = 500, 300
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2
            arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (10, 15, 20, 250))
            arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_PRIMARY, 2)

            arcade.Text(
                "TRANSFER SHIP OWNERSHIP",
                bx + box_w // 2,
                by + box_h - 50,
                COLOR_PRIMARY,
                20,
                anchor_x="center",
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                "SELECT RECIPIENT COMMANDER:",
                bx + box_w // 2,
                by + box_h - 90,
                COLOR_TEXT_DIM,
                14,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

            others = self.network.get_other_players()
            if not others:
                arcade.Text(
                    "NO OTHER CMDRS DETECTED",
                    bx + box_w // 2,
                    by + box_h // 2,
                    COLOR_ACCENT,
                    16,
                    anchor_x="center",
                    font_name=self.font_ui,
                ).draw()
            else:
                target = others[self.selected_recipient_index % len(others)]
                arcade.Text(
                    self._clamp_text(target.upper(), 24),
                    bx + box_w // 2,
                    by + box_h // 2,
                    COLOR_PRIMARY,
                    24,
                    anchor_x="center",
                    font_name=self.font_ui_bold,
                ).draw()
                arcade.Text(
                    "< [LEFT/RIGHT] CYCLE RECIPIENTS >",
                    bx + box_w // 2,
                    by + box_h // 2 - 40,
                    COLOR_TEXT_DIM,
                    12,
                    anchor_x="center",
                    font_name=self.font_ui,
                ).draw()
                self._draw_btn(
                    bx + box_w // 2 - 75,
                    by + 40,
                    150,
                    40,
                    "CONFIRM GIFT",
                    COLOR_PRIMARY,
                )

            arcade.Text(
                "[ESC] TO ABORT",
                bx + box_w // 2,
                by + 15,
                COLOR_TEXT_DIM,
                10,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

        if self.prompt_mode == "DISPOSAL_CHOICE":
            arcade.draw_lbwh_rectangle_filled(
                0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 200)
            )
            box_w, box_h = 560, 260
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2
            arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (10, 15, 20, 250))
            arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_PRIMARY, 2)

            member = self.network.player.crew.get(self.disposal_specialty)
            name = member.name if member else "CREW"
            arcade.Text(
                f"DISPOSE OF {name.upper()}?",
                bx + box_w // 2,
                by + box_h - 50,
                COLOR_PRIMARY,
                20,
                anchor_x="center",
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                "CHOOSE THEIR FATE. THIS CANNOT BE UNDONE.",
                bx + box_w // 2,
                by + box_h - 90,
                COLOR_TEXT_DIM,
                12,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

            self._draw_btn(
                bx + 40, by + 50, 220, 50, "LEAVE ON PLANET", COLOR_SECONDARY
            )
            self._draw_btn(
                bx + 300, by + 50, 220, 50, "PUSH OUT AIRLOCK", (150, 50, 50)
            )
            arcade.Text(
                "[ESC] OR CLICK OUTSIDE TO CANCEL",
                bx + box_w // 2,
                by + 20,
                COLOR_TEXT_DIM,
                10,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

        if self.prompt_mode == "CONFIRM_LOGOUT":
            arcade.draw_lbwh_rectangle_filled(
                0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 210)
            )
            box_w, box_h = 560, 250
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2
            arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (10, 15, 20, 250))
            arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_PRIMARY, 2)

            arcade.Text(
                "CONFIRM LOGOUT",
                bx + box_w // 2,
                by + box_h - 55,
                COLOR_PRIMARY,
                22,
                anchor_x="center",
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                "RETURN TO MAIN MENU? UNSAVED PROGRESS MAY BE LOST.",
                bx + box_w // 2,
                by + box_h - 98,
                COLOR_TEXT_DIM,
                12,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            self._draw_btn(bx + 70, by + 52, 180, 48, "CANCEL", COLOR_SECONDARY)
            self._draw_btn(bx + 310, by + 52, 180, 48, "LOGOUT", COLOR_ACCENT)
            arcade.Text(
                "[ESC] CANCEL | [ENTER] LOGOUT",
                bx + box_w // 2,
                by + 20,
                COLOR_TEXT_DIM,
                10,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

        if self.prompt_mode == "BANK_INPUT":
            _mode_labels = {
                "deposit": (
                    "DEPOSIT TO BANK",
                    "AVAILABLE CREDITS",
                    lambda: self.network.player.credits,
                ),
                "withdraw": (
                    "WITHDRAW FROM BANK",
                    "BANK BALANCE",
                    lambda: self.network.player.bank_balance,
                ),
                "p_deposit": (
                    "DEPOSIT TO PLANET TREASURY",
                    "AVAILABLE CREDITS",
                    lambda: self.network.player.credits,
                ),
                "p_withdraw": (
                    "WITHDRAW FROM PLANET TREASURY",
                    "TREASURY BALANCE",
                    lambda: int(
                        (self.planet_finance_cache or {})
                        .get("current_planet", {})
                        .get("credit_balance", 0)
                    ),
                ),
            }
            _title, _bal_label, _bal_fn = _mode_labels.get(
                self.bank_input_mode, ("ENTER AMOUNT", "BALANCE", lambda: 0)
            )
            _max_val = int(_bal_fn())
            arcade.draw_lbwh_rectangle_filled(
                0, 0, SCREEN_WIDTH, SCREEN_HEIGHT, (0, 0, 0, 200)
            )
            box_w, box_h = 520, 280
            bx = SCREEN_WIDTH // 2 - box_w // 2
            by = SCREEN_HEIGHT // 2 - box_h // 2
            arcade.draw_lbwh_rectangle_filled(bx, by, box_w, box_h, (10, 15, 20, 250))
            arcade.draw_lbwh_rectangle_outline(bx, by, box_w, box_h, COLOR_PRIMARY, 2)
            arcade.Text(
                _title,
                bx + box_w // 2,
                by + box_h - 50,
                COLOR_PRIMARY,
                18,
                anchor_x="center",
                font_name=self.font_ui_bold,
            ).draw()
            arcade.Text(
                f"{_bal_label}: {_max_val:,} CR",
                bx + box_w // 2,
                by + box_h - 90,
                COLOR_TEXT_DIM,
                13,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            arcade.Text(
                "ENTER AMOUNT:",
                bx + box_w // 2,
                by + box_h - 130,
                COLOR_TEXT_DIM,
                13,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            _disp = self.bank_input_text if self.bank_input_text else "0"
            arcade.Text(
                f"{int(_disp):,}_" if _disp.isdigit() and _disp else f"{_disp}_",
                bx + box_w // 2,
                by + box_h // 2 - 10,
                COLOR_ACCENT,
                34,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()
            self._draw_btn(
                bx + 30, by + 60, 100, 36, "ALL", COLOR_SECONDARY, _max_val > 0
            )
            self._draw_btn(
                bx + 145, by + 60, 100, 36, "HALF", COLOR_SECONDARY, _max_val > 0
            )
            self._draw_btn(
                bx + 260,
                by + 60,
                140,
                36,
                "CONFIRM",
                COLOR_PRIMARY,
                bool(self.bank_input_text),
            )
            self._draw_btn(bx + 415, by + 60, 80, 36, "CANCEL", COLOR_ACCENT)
            arcade.Text(
                "[0-9] TYPE  [BKSP] DEL  [ENTER] CONFIRM  [ESC] CANCEL",
                bx + box_w // 2,
                by + 22,
                COLOR_TEXT_DIM,
                10,
                anchor_x="center",
                font_name=self.font_ui,
            ).draw()

        if self.show_help_overlay:
            self._draw_help_overlay()

        # Arrival Message Overlay
        if self.arrival_msg_timer > 0:
            alpha = int(min(255, self.arrival_msg_timer * 100))
            box_h = 60 if "\n" in self.arrival_msg else 40
            arcade.draw_lbwh_rectangle_filled(
                sidebar_w,
                SCREEN_HEIGHT - box_h,
                SCREEN_WIDTH - sidebar_w,
                box_h,
                (20, 40, 60, alpha),
            )
            arcade.draw_line(
                sidebar_w,
                SCREEN_HEIGHT - box_h,
                SCREEN_WIDTH,
                SCREEN_HEIGHT - box_h,
                (*COLOR_ACCENT, alpha),
                2,
            )
            arcade.Text(
                self.arrival_msg.upper(),
                sidebar_w + (SCREEN_WIDTH - sidebar_w) // 2,
                SCREEN_HEIGHT - box_h // 2,
                (*COLOR_PRIMARY, alpha),
                12 if "\n" in self.arrival_msg else 14,
                anchor_x="center",
                anchor_y="center",
                font_name=self.font_ui_bold,
                multiline=True,
                width=SCREEN_WIDTH - sidebar_w - 40,
            ).draw()

        if self.combat_session:
            self._draw_combat_window()

    def _execute_menu_selection(self):
        """Logic for triggering the currently selected menu option."""
        is_barred, _ = self.network.check_barred(self.network.current_planet.name)
        opt = self.menu_options[self.selected_menu]
        self._play_sfx("ui", "ui_confirm")

        if is_barred and opt not in ["TRAVEL", "LOGOUT", "ANALYTICS"]:
            self.arrival_msg = "ACCESS DENIED: PLANETARY BAN IN EFFECT."
            self.arrival_msg_timer = 3.0
            return

        if opt == "LOGOUT":
            self.prompt_mode = "CONFIRM_LOGOUT"
            return
        elif opt == "CREW":
            self.mode = "CREW"
            self.crew_message = ""
        elif opt == "TRAVEL":
            # Check for fleeing during orbital confrontation with planet
            if self.mode == "ORBIT":
                p = self.network.current_planet
                # If this planet has an owner and we were in orbit mode, we flee
                if p.owner and p.owner != self.network.player.name:
                    self.network.bar_player(p.name)
                    self.network.save_game()
            self.window.show_view(TravelView(self.network))
        elif opt == "ORBIT SCAN":
            self.mode = "ORBIT"
            self._refresh_planet_finance_cache(force=True)
            self.orbital_targets = self.network.get_orbit_targets()
            self.selected_target_index = 0
            self.orbit_message = ""
            triggered, msg = self.network.should_initialize_planet_auto_combat(
                self.network.current_planet.name
            )
            if triggered:
                self._start_combat(
                    {"type": "PLANET", "name": self.network.current_planet.name}
                )
                self.orbit_message = msg
                self.orbit_message_color = COLOR_ACCENT
                return
        elif opt == "BANK":
            self.mode = "BANK"
            self.bank_message = ""
            self.bank_input_mode = None
            self.bank_input_text = ""
            self._refresh_planet_finance_cache(force=True)
        elif opt == "REFUEL":
            self.mode = "REFUEL"
        elif opt == "MARKET":
            # Check for contraband detection before opening market
            detected, msg = self.network.check_contraband_detection()
            if detected:
                if "BOARDED" in msg:
                    self.mode = "ORBIT"
                    self._start_combat(
                        {"type": "PLANET", "name": self.network.current_planet.name}
                    )
                    self.orbit_message = msg.upper()
                    return
                else:
                    self.arrival_msg = msg.upper()
                    self.arrival_msg_timer = 5.0

            self.mode = "MARKET"
            self.selected_item_index = 0
            self.market_item_locked = False
            self.market_message = ""
        elif opt == "SYSTEMS":
            self.mode = "SYSTEMS"
            self.system_message = ""
        elif opt == "SHIPYARD":
            self.mode = "SHIPYARD"
            self.selected_ship_index = 0
            self.shipyard_message = ""
        elif opt == "MAIL":
            self.mode = "MAIL"
            self.network.refresh_player_state()
            self.selected_mail_index = 0
            self.mail_message = ""
            self.last_read_message_id = None
        elif opt == "ANALYTICS":
            from .analytics_view import AnalyticsView

            self.window.show_view(AnalyticsView(self.network, self))
        elif opt == "INFO":
            self.mode = "INFO"
        elif opt == "SAVE":
            self.network.save_game()
            self.arrival_msg = "SYSTEM STATE PERSISTED TO DISK."
            self.arrival_msg_timer = 2.0
        else:
            self.mode = "INFO"

    def _open_mail_compose(self):
        self.prompt_mode = "MAIL_COMPOSE"
        self.mail_dropdown_open = True
        self.mail_subject_input = ""
        self.mail_body_input = ""
        self.mail_input_field = "SUBJECT"
        self.mail_message = ""
        self.selected_recipient_index = 0

    def _open_mail_reply(self, message):
        if not message:
            self.mail_message = "ERROR: NO MESSAGE SELECTED"
            return

        self._open_mail_compose()
        subject_text = str(getattr(message, "subject", "") or "").strip()
        sender_text = str(getattr(message, "sender", "") or "").strip()

        self.mail_subject_input = (
            subject_text
            if subject_text.upper().startswith("RE:")
            else f"RE: {subject_text}" if subject_text else "RE:"
        )[:30]

        others = self.network.get_other_players()
        if not others:
            self.mail_message = "ERROR: NO RECEIVER"
            return

        sender_idx = next(
            (
                i
                for i, name in enumerate(others)
                if str(name).lower() == sender_text.lower()
            ),
            None,
        )
        if sender_idx is None:
            self.mail_message = "ERROR: SENDER UNAVAILABLE"
            return
        self.selected_recipient_index = sender_idx

    def _get_owned_planets_current_commander(self):
        owner_key = str(getattr(self.network.player, "name", "") or "").strip().lower()
        if not owner_key:
            return []

        owned = []
        for planet in list(getattr(self.network, "planets", []) or []):
            if str(getattr(planet, "owner", "") or "").strip().lower() == owner_key:
                owned.append(str(getattr(planet, "name", "UNKNOWN")))

        if not owned:
            owned_dict = getattr(self.network.player, "owned_planets", {}) or {}
            for planet_name in owned_dict.keys():
                owned.append(str(planet_name))

        return sorted(set(owned), key=lambda value: value.lower())

    def _open_commander_status_board(self):
        self.commander_status_error = ""
        self.commander_status_scroll = 0
        try:
            rows = self.network.get_all_commander_statuses()
            if isinstance(rows, list):
                self.commander_status_rows = rows
            else:
                self.commander_status_rows = []
                self.commander_status_error = "FAILED TO LOAD COMMANDER STATUS DATA."
        except Exception as exc:
            self.commander_status_rows = []
            self.commander_status_error = (
                str(exc).strip().upper() or "FAILED TO LOAD COMMANDER STATUS DATA."
            )
        self.prompt_mode = "COMMANDER_STATUS_BOARD"

    def on_key_press(self, key, modifiers):
        if self.wisdom_modal_active:
            if key in (
                arcade.key.ENTER,
                arcade.key.RETURN,
                arcade.key.SPACE,
                arcade.key.ESCAPE,
            ):
                self.wisdom_modal_active = False
            return

        if key == arcade.key.F8 and not self.combat_session:
            from .analytics_view import AnalyticsView

            self.window.show_view(AnalyticsView(self.network, self))
            return

        if key == arcade.key.F1 and not self.combat_session:
            self.show_help_overlay = not self.show_help_overlay
            return

        if self.show_help_overlay:
            if key in (arcade.key.ESCAPE, arcade.key.F1):
                self.show_help_overlay = False
            return

        if self.combat_session:
            s = self.combat_session
            max_commit = max(0, int(self.network.player.spaceship.current_defenders))

            # ESC dismisses special weapon confirmation if it's open
            if key == arcade.key.ESCAPE and self.combat_spec_weapon_confirm:
                self.combat_spec_weapon_confirm = False
                return

            if key in (arcade.key.LEFT, arcade.key.A):
                self.combat_commitment = max(0, self.combat_commitment - 1)
                self._play_sfx("ui", "ui_move")
                return
            if key in (arcade.key.RIGHT, arcade.key.D):
                self.combat_commitment = min(max_commit, self.combat_commitment + 1)
                self._play_sfx("ui", "ui_move")
                return

            if key in (arcade.key.ENTER, arcade.key.RETURN, arcade.key.SPACE):
                if s.get("status") == "ACTIVE":
                    self._combat_do_round()
                return

            if s.get("status") != "ACTIVE":
                if key == arcade.key.I:
                    before_state = self._snapshot_post_combat_state()
                    success, msg = self._auto_install_systems_cargo()
                    s.setdefault("log", []).append(
                        f"POST-COMBAT AUTO-FIT: {msg.upper()}"
                    )
                    after_state = self._snapshot_post_combat_state()
                    self._record_post_combat_action(
                        "AUTO-FIT", before_state, after_state, msg
                    )
                    if success:
                        self.network.save_game()
                    return
                if key == arcade.key.R:
                    before_state = self._snapshot_post_combat_state()
                    success, msg = self.network.repair_hull()
                    s.setdefault("log", []).append(f"POST-COMBAT REPAIR: {msg.upper()}")
                    after_state = self._snapshot_post_combat_state()
                    self._record_post_combat_action(
                        "REPAIR", before_state, after_state, msg
                    )
                    if success:
                        self.network.save_game()
                    return
                if key == arcade.key.T:
                    self._close_combat_window()
                    self.mode = "SYSTEMS"
                    self.system_message = "RETURNED TO SYSTEMS FROM COMBAT."
                    return

            if key in (arcade.key.C, arcade.key.ESCAPE):
                if s.get("status") == "ACTIVE":
                    self.network.flee_combat_session(s)
                    self.network.save_game()
                    self._play_sfx("combat", "combat_hit")
                else:
                    self._close_combat_window()
                return

        if self.prompt_mode == "ACTION_SLIDER":
            if key == arcade.key.ESCAPE:
                self.prompt_mode = None
                self.action_slider_dragging = False
                return
            if key in (arcade.key.LEFT, arcade.key.A):
                self.action_slider_value = max(0, int(self.action_slider_value) - 1)
                return
            if key in (arcade.key.RIGHT, arcade.key.D):
                self.action_slider_value = min(
                    int(self.action_slider_max), int(self.action_slider_value) + 1
                )
                return
            if key in (arcade.key.ENTER, arcade.key.RETURN):
                self._confirm_action_slider()
                return
            return

        if self.prompt_mode == "COMMANDER_STATUS_BOARD":
            visible_rows = 12
            max_scroll = max(0, len(self.commander_status_rows) - visible_rows)
            if key in (arcade.key.ESCAPE, arcade.key.ENTER, arcade.key.RETURN):
                self.prompt_mode = None
                return
            if key in (arcade.key.UP, arcade.key.W):
                self.commander_status_scroll = max(
                    0, int(self.commander_status_scroll) - 1
                )
                return
            if key in (arcade.key.DOWN, arcade.key.S):
                self.commander_status_scroll = min(
                    max_scroll, int(self.commander_status_scroll) + 1
                )
                return
            return

        if self.prompt_mode == "GIVE_SHIP_RECIPIENT":
            if key == arcade.key.ESCAPE:
                self.prompt_mode = None
            elif key == arcade.key.LEFT:
                others = self.network.get_other_players()
                if others:
                    self.selected_recipient_index = (
                        self.selected_recipient_index - 1
                    ) % len(others)
            elif key == arcade.key.RIGHT:
                others = self.network.get_other_players()
                if others:
                    self.selected_recipient_index = (
                        self.selected_recipient_index + 1
                    ) % len(others)
            elif key == arcade.key.ENTER or key == arcade.key.RETURN:
                others = self.network.get_other_players()
                if others:
                    target = self.orbital_targets[self.selected_target_index]
                    recipient = others[self.selected_recipient_index % len(others)]
                    success, self.orbit_message = self.network.claim_abandoned_ship(
                        target["name"], "GIVE", {"recipient": recipient}
                    )
                    if success:
                        self.orbital_targets = self.network.get_orbit_targets()
                        self.prompt_mode = None
            return

        if self.prompt_mode == "CONFIRM_LOGOUT":
            if key == arcade.key.ESCAPE:
                self.prompt_mode = None
                return
            if key == arcade.key.ENTER or key == arcade.key.RETURN:
                from views.menu import MainMenuView

                if hasattr(self.network, "logout_commander"):
                    try:
                        self.network.logout_commander()
                    except Exception:
                        pass
                self.prompt_mode = None
                self.window.show_view(MainMenuView())
                return
            return

        if self.prompt_mode == "MAIL_COMPOSE":
            if key == arcade.key.ESCAPE:
                self.prompt_mode = None
            elif key == arcade.key.TAB:
                self.mail_input_field = (
                    "BODY" if self.mail_input_field == "SUBJECT" else "SUBJECT"
                )
            elif key == arcade.key.LEFT and self.mail_dropdown_open:
                others = self.network.get_other_players()
                if others:
                    self.selected_recipient_index = (
                        self.selected_recipient_index - 1
                    ) % len(others)
            elif key == arcade.key.RIGHT and self.mail_dropdown_open:
                others = self.network.get_other_players()
                if others:
                    self.selected_recipient_index = (
                        self.selected_recipient_index + 1
                    ) % len(others)
            elif key == arcade.key.ENTER or key == arcade.key.RETURN:
                others = self.network.get_other_players()
                if not others:
                    self.mail_message = "ERROR: NO RECEIVER"
                else:
                    recipient = others[self.selected_recipient_index % len(others)]
                    if (
                        not self.mail_subject_input.strip()
                        or not self.mail_body_input.strip()
                    ):
                        self.mail_message = "ERROR: EMPTY FIELDS"
                    else:
                        success, msg = self.network.send_message(
                            recipient,
                            self.mail_subject_input,
                            self.mail_body_input,
                            sender_name=self.network.player.name,
                        )
                        self.mail_message = msg
                        if success:
                            self.prompt_mode = None
            elif key == arcade.key.BACKSPACE:
                if self.mail_input_field == "SUBJECT":
                    self.mail_subject_input = self.mail_subject_input[:-1]
                else:
                    self.mail_body_input = self.mail_body_input[:-1]
            elif 32 <= key <= 126:
                try:
                    char = chr(key)
                    if self.mail_input_field == "SUBJECT":
                        if len(self.mail_subject_input) < 30:
                            self.mail_subject_input += char
                    else:
                        if len(self.mail_body_input) < 500:
                            self.mail_body_input += char
                except:
                    pass
            return

        if self.prompt_mode == "DISPOSAL_CHOICE":
            if key == arcade.key.ESCAPE:
                self.prompt_mode = None
                self.disposal_specialty = None
            return

        if self.prompt_mode == "CREW_NAMING":
            if key == arcade.key.ESCAPE:
                self.prompt_mode = None
                self.naming_crew_member = None
            elif key == arcade.key.ENTER or key == arcade.key.RETURN:
                if self.naming_name_input.strip():
                    self.naming_crew_member.name = (
                        self.naming_name_input.strip().upper()
                    )
                    success, msg = self.network.player.hire_crew(
                        self.naming_crew_member
                    )
                    self.crew_message = msg
                    if success:
                        self.network.save_game()
                    self.prompt_mode = None
                    self.naming_crew_member = None
            elif key == arcade.key.BACKSPACE:
                self.naming_name_input = self.naming_name_input[:-1]
            else:
                # Basic char input
                if len(self.naming_name_input) < 15:
                    try:
                        char = chr(key).upper() if 32 <= key <= 126 else ""
                        self.naming_name_input += char
                    except:
                        pass
            return

        if self.prompt_mode == "BANK_INPUT":
            if key == arcade.key.ESCAPE:
                self.prompt_mode = None
                self.bank_input_mode = None
                self.bank_input_text = ""
            elif key in (arcade.key.ENTER, arcade.key.RETURN):
                if self.bank_input_text:
                    self._confirm_bank_input()
            elif key == arcade.key.BACKSPACE:
                self.bank_input_text = self.bank_input_text[:-1]
            else:
                digit = self._digit_from_key(key)
                if digit is None:
                    return
                if len(self.bank_input_text) < 12:
                    self.bank_input_text += digit
            return

        if self.mode == "MAIL":
            messages = self.network.player.messages
            if key == arcade.key.LEFT:
                if messages:
                    self.selected_mail_index = (self.selected_mail_index - 1) % len(
                        messages
                    )
            elif key == arcade.key.RIGHT:
                if messages:
                    self.selected_mail_index = (self.selected_mail_index + 1) % len(
                        messages
                    )
            elif key == arcade.key.F5:
                self.network.refresh_player_state()
            elif key == arcade.key.N:  # New Message
                self._open_mail_compose()
            elif key == arcade.key.R:
                if messages and self.selected_mail_index < len(messages):
                    self._open_mail_reply(messages[self.selected_mail_index])
            elif key == arcade.key.DELETE:
                if messages and self.selected_mail_index < len(messages):
                    self.network.delete_message(messages[self.selected_mail_index].id)
                    self.selected_mail_index = max(0, self.selected_mail_index - 1)
                    self.network.save_game()
            elif key == arcade.key.ESCAPE:
                self.mode = "INFO"
            return

        if self.mode == "MARKET":
            planet = self.network.current_planet
            planet_items = self._get_visible_market_items()
            visible_rows = self._get_market_layout(len(planet_items))["visible_rows"]

            if key == arcade.key.W or key == arcade.key.UP:
                if self.market_item_locked:
                    return
                self.selected_item_index = (self.selected_item_index - 1) % len(
                    planet_items
                )
                if self.selected_item_index < self.market_scroll:
                    self.market_scroll = self.selected_item_index
                elif self.selected_item_index >= self.market_scroll + visible_rows:
                    self.market_scroll = max(
                        0, self.selected_item_index - (visible_rows - 1)
                    )
                return
            elif key == arcade.key.S or key == arcade.key.DOWN:
                if self.market_item_locked:
                    return
                self.selected_item_index = (self.selected_item_index + 1) % len(
                    planet_items
                )
                if self.selected_item_index < self.market_scroll:
                    self.market_scroll = self.selected_item_index
                elif self.selected_item_index >= self.market_scroll + visible_rows:
                    self.market_scroll = max(
                        0, self.selected_item_index - (visible_rows - 1)
                    )
                return
            elif key == arcade.key.ENTER or key == arcade.key.RETURN:
                if self.selected_item_index < len(planet_items):
                    sel_item = planet_items[self.selected_item_index][0]
                    sel_price = max(1, int(planet_items[self.selected_item_index][1]))
                    if not self._is_item_buyable_in_market(sel_item):
                        self.market_message = "ITEM IS SELL-ONLY AT THIS PORT."
                        return
                    ship = self.network.player.spaceship
                    cargo_used = sum(self.network.player.inventory.values())
                    cargo_max = ship.current_cargo_pods
                    can_afford = self.network.player.credits // sel_price
                    space_left = max(0, cargo_max - cargo_used)
                    max_buy = min(can_afford, space_left)
                    self._open_market_slider_prompt("BUY", sel_item, max_buy)
                return
            elif key == arcade.key.B:
                if self.selected_item_index < len(planet_items):
                    sel_item = planet_items[self.selected_item_index][0]
                    sel_price = max(1, int(planet_items[self.selected_item_index][1]))
                    if not self._is_item_buyable_in_market(sel_item):
                        self.market_message = "ITEM IS SELL-ONLY AT THIS PORT."
                        return
                    ship = self.network.player.spaceship
                    cargo_used = sum(self.network.player.inventory.values())
                    cargo_max = ship.current_cargo_pods
                    can_afford = self.network.player.credits // sel_price
                    space_left = max(0, cargo_max - cargo_used)
                    max_buy = min(can_afford, space_left)
                    self._open_market_slider_prompt("BUY", sel_item, max_buy)
                return
            elif key == arcade.key.V:
                if self.selected_item_index < len(planet_items):
                    sel_item = planet_items[self.selected_item_index][0]
                    inv_qty = int(self.network.player.inventory.get(sel_item, 0))
                    self._open_market_slider_prompt("SELL", sel_item, inv_qty)
                return
            elif key == arcade.key.R:  # R for bribe (Grease the Wheels)
                success, msg = self.network.bribe_npc()
                self.market_message = msg.upper()
                if success:
                    self.network.save_game()
                    self.npc_remark = (
                        "I knew you were a person of culture. Check the list now."
                    )
                return
            elif key == arcade.key.J:
                success, msg = self.network.sell_non_market_cargo()
                self.market_message = msg.upper()
                if success:
                    self.network.save_game()
                return
            elif key == arcade.key.K:
                success, msg = self.network.reroll_trade_contract()
                self.market_message = msg.upper()
                if success:
                    self.network.save_game()
                return
            elif key == arcade.key.C:
                self.compare_mode = not self.compare_mode
                return
            elif key == arcade.key.A:
                self.compare_planet_index = (self.compare_planet_index - 1) % len(
                    self.network.planets
                )
                return
            elif key == arcade.key.D:
                self.compare_planet_index = (self.compare_planet_index + 1) % len(
                    self.network.planets
                )
                return
            elif key == arcade.key.ESCAPE:
                self.mode = "INFO"
                self.market_message = ""
                return

        if self.mode == "ORBIT":
            p = self.network.current_planet
            if p.owner == self.network.player.name:
                if key == arcade.key.LEFT:
                    self._open_orbit_transfer_prompt("fighters", "TO_PLANET")
                    return
                elif key == arcade.key.RIGHT:
                    self._open_orbit_transfer_prompt("fighters", "TO_SHIP")
                    return
                elif key == arcade.key.UP:
                    self._open_orbit_transfer_prompt("shields", "TO_PLANET")
                    return
                elif key == arcade.key.DOWN:
                    self._open_orbit_transfer_prompt("shields", "TO_SHIP")
                    return

            if key == arcade.key.LEFT:
                cargo_items = [
                    name
                    for name, qty in sorted(
                        self.network.player.inventory.items(),
                        key=lambda pair: str(pair[0]).lower(),
                    )
                    if int(qty) > 0
                ]
                if cargo_items:
                    self.orbit_give_cargo_index = (
                        int(self.orbit_give_cargo_index) - 1
                    ) % len(cargo_items)
                else:
                    self.orbit_give_cargo_index = 0
                return
            elif key == arcade.key.RIGHT:
                cargo_items = [
                    name
                    for name, qty in sorted(
                        self.network.player.inventory.items(),
                        key=lambda pair: str(pair[0]).lower(),
                    )
                    if int(qty) > 0
                ]
                if cargo_items:
                    self.orbit_give_cargo_index = (
                        int(self.orbit_give_cargo_index) + 1
                    ) % len(cargo_items)
                else:
                    self.orbit_give_cargo_index = 0
                return

            if key == arcade.key.W or key == arcade.key.UP:
                if self.orbital_targets:
                    self.selected_target_index = (self.selected_target_index - 1) % len(
                        self.orbital_targets
                    )
                return
            elif key == arcade.key.S or key == arcade.key.DOWN:
                if self.orbital_targets:
                    self.selected_target_index = (self.selected_target_index + 1) % len(
                        self.orbital_targets
                    )
                return
            elif key == arcade.key.ENTER or key == arcade.key.RETURN:
                if self.mouse_x >= 300:  # Only if not trying to click menu
                    if self.orbital_targets:
                        self._start_combat(
                            self.orbital_targets[self.selected_target_index]
                        )
                        return
            elif key == arcade.key.ESCAPE:
                self.mode = "INFO"
                self.orbit_message = ""
                return

        if self.mode == "SHIPYARD":
            if key == arcade.key.W or key == arcade.key.UP:
                self.selected_ship_index = (self.selected_ship_index - 1) % len(
                    self.network.spaceships
                )
                if self.selected_ship_index < self.shipyard_scroll:
                    self.shipyard_scroll = self.selected_ship_index
                elif self.selected_ship_index >= self.shipyard_scroll + 4:
                    self.shipyard_scroll = max(0, self.selected_ship_index - 3)
                return
            elif key == arcade.key.S or key == arcade.key.DOWN:
                self.selected_ship_index = (self.selected_ship_index + 1) % len(
                    self.network.spaceships
                )
                if self.selected_ship_index < self.shipyard_scroll:
                    self.shipyard_scroll = self.selected_ship_index
                elif self.selected_ship_index >= self.shipyard_scroll + 4:
                    self.shipyard_scroll = max(0, self.selected_ship_index - 3)
                return
            elif key == arcade.key.ENTER or key == arcade.key.RETURN:
                if self.mouse_x >= 300:
                    ship = self.network.spaceships[self.selected_ship_index]
                    success, msg = self.network.buy_ship(ship)
                    self.shipyard_message = msg
                    if success:
                        self.network.save_game()
                    return
            elif key == arcade.key.ESCAPE:
                self.mode = "INFO"
                return

        if self.mode == "SYSTEMS" or self.mode == "CREW":
            if self.mode == "SYSTEMS" and key == arcade.key.I:
                success, msg = self._auto_install_systems_cargo()
                self.system_message = msg.upper()
                if success:
                    self.network.save_game()
                return
            if self.mode == "SYSTEMS" and key == arcade.key.L:
                self._open_commander_status_board()
                return
            if key == arcade.key.ESCAPE:
                self.mode = "INFO"
                return

        # Main Menu Navigation
        if key == arcade.key.UP:
            self.selected_menu = (self.selected_menu - 1) % len(self.menu_options)
            self._play_sfx("ui", "ui_move")
        elif key == arcade.key.DOWN:
            self.selected_menu = (self.selected_menu + 1) % len(self.menu_options)
            self._play_sfx("ui", "ui_move")
        elif key == arcade.key.ENTER or key == arcade.key.RETURN:
            self._execute_menu_selection()
        elif key == arcade.key.F and self.mode == "REFUEL":
            ship = self.network.player.spaceship
            needed = ship.max_fuel - ship.fuel
            success, msg = self.network.buy_fuel(needed)
            msg_text = str(msg or "").upper()
            if success and "engineer" in self.network.player.crew:
                phrase = self._get_random_engineer_phrase()
                if phrase:
                    msg_text = f'{msg_text}\n"{phrase}"'
            self.arrival_msg = msg_text
            self.arrival_msg_timer = 2.5
            if success:
                self.network.save_game()
        elif key == arcade.key.ESCAPE:
            self.mode = "INFO"

    def _auto_install_systems_cargo(self):
        ship = self.network.player.spaceship
        inventory = self.network.player.inventory
        applied = []

        installables = [
            ("Cargo Pod", ship.max_cargo_pods - ship.current_cargo_pods),
            ("Energy Shields", ship.max_shields - ship.current_shields),
            ("Fighter Squadron", ship.max_defenders - ship.current_defenders),
            ("Nanobot Repair Kits", 9999),  # Limit handled by server
        ]

        for item_name, capacity in installables:
            qty_in_cargo = int(inventory.get(item_name, 0))
            if qty_in_cargo > 0 and capacity > 0:
                # For repair kits, check if repair needed
                if (
                    item_name == "Nanobot Repair Kits"
                    and ship.integrity >= ship.max_integrity
                ):
                    continue

                # Try to install all available
                install_qty = qty_in_cargo
                if item_name != "Nanobot Repair Kits":
                    install_qty = min(qty_in_cargo, int(capacity))

                if install_qty > 0:
                    res = self.network.install_ship_upgrade(item_name, install_qty)
                    if isinstance(res, dict) and res.get("success"):
                        applied.append(f"{res.get('message').upper()}")
                    elif isinstance(res, tuple) and res[0]:
                        applied.append(f"{res[1].upper()}")

        if not applied:
            return False, "NO INSTALLABLE COMPONENTS INSTALLED."

        return True, f"AUTO-FIT REPORT: {' | '.join(applied)}"

    def _open_orbit_transfer_prompt(self, transfer_kind, direction):
        planet = self.network.current_planet
        ship = self.network.player.spaceship

        transfer_kind = str(transfer_kind)
        direction = str(direction)

        if transfer_kind == "fighters":
            if direction == "TO_PLANET":
                max_qty = min(
                    int(ship.current_defenders),
                    max(0, int(planet.max_defenders - planet.defenders)),
                )
            else:
                max_qty = min(
                    int(planet.defenders),
                    max(0, int(ship.max_defenders - ship.current_defenders)),
                )
        else:
            planet_max_shields = int(
                getattr(planet, "max_shields", max(1, planet.base_shields))
            )
            if direction == "TO_PLANET":
                max_qty = min(
                    int(ship.current_shields),
                    max(0, int(planet_max_shields - planet.shields)),
                )
            else:
                max_qty = min(
                    int(planet.shields),
                    max(0, int(ship.max_shields - ship.current_shields)),
                )

        max_qty = max(0, int(max_qty))
        if max_qty <= 0:
            self.orbit_message = "NO TRANSFER CAPACITY AVAILABLE"
            self.orbit_message_color = COLOR_ACCENT
            return

        self.action_slider_context = "ORBIT"
        self.action_slider_kind = transfer_kind
        self.action_slider_item_name = transfer_kind.upper()
        self.action_slider_direction = direction
        self.action_slider_max = max_qty
        self.action_slider_value = max(1, min(max_qty, 1))
        self.action_slider_dragging = False
        self.prompt_mode = "ACTION_SLIDER"

    def _open_market_slider_prompt(self, action, item_name, max_qty):
        max_qty = max(0, int(max_qty))
        if max_qty <= 0:
            self.market_message = "NO AVAILABLE QUANTITY FOR THIS ACTION."
            return

        self.action_slider_context = "MARKET"
        self.action_slider_kind = str(action).upper()
        self.action_slider_item_name = str(item_name)
        self.action_slider_direction = None
        self.action_slider_max = max_qty
        self.action_slider_value = max(1, min(max_qty, 1))
        self.action_slider_dragging = False
        self.prompt_mode = "ACTION_SLIDER"

    def _format_market_trade_feedback(self, action, item_name, qty):
        qty = max(1, int(qty))
        item_label = str(item_name)
        if str(action).upper() == "BUY":
            return f"Great, the {qty} of {item_label} are being transferred to your ship immediately."
        return f"Great, the {qty} of {item_label} are being transferred from your ship to the market immediately."

    def _confirm_action_slider(self):
        qty = max(0, min(int(self.action_slider_max), int(self.action_slider_value)))
        if qty <= 0:
            return

        if self.action_slider_context == "ORBIT":
            if self.action_slider_kind == "fighters":
                success, msg = self.network.transfer_fighters(
                    self.action_slider_direction, qty
                )
            else:
                success, msg = self.network.transfer_shields(
                    self.action_slider_direction, qty
                )
            self.orbit_message = msg
            self.orbit_message_color = COLOR_PRIMARY if success else COLOR_ACCENT
            if success:
                self.network.save_game()

        elif self.action_slider_context == "MARKET":
            action = str(self.action_slider_kind)
            item_name = str(self.action_slider_item_name)

            if action == "BUY" and item_name in [
                "Cargo Pod",
                "Energy Shields",
                "Fighter Squadron",
            ]:
                # Always buy first
                success, msg = self.network.trade_item(item_name, action, int(qty))

                if success:
                    # If purchase successful, prompt for install
                    self.trade_item_name = item_name
                    self.trade_item_qty = int(qty)
                    self.prompt_mode = "INSTALL_CHOICE"
                    self.action_slider_context = None
                    self.action_slider_kind = None
                    self.action_slider_item_name = ""
                    self.action_slider_direction = None
                    self.action_slider_max = 0
                    self.action_slider_value = 0
                    self.action_slider_dragging = False
                    return

                self.market_message = str(msg).upper()
            else:
                success, msg = self.network.trade_item(item_name, action, int(qty))
                self.market_message = str(msg).upper()
                if success:
                    self.market_message = self._format_market_trade_feedback(
                        action, item_name, qty
                    )
                    self.network.save_game()
                elif "PREPARE TO BE BOARDED" in str(msg):
                    self.mode = "ORBIT"
                    self._start_combat(
                        {"type": "PLANET", "name": self.network.current_planet.name}
                    )
                    self.orbit_message = str(msg).upper()

        self.prompt_mode = None
        self.action_slider_context = None
        self.action_slider_kind = None
        self.action_slider_item_name = ""
        self.action_slider_direction = None
        self.action_slider_max = 0
        self.action_slider_value = 0
        self.action_slider_dragging = False

    def on_mouse_motion(self, x, y, dx, dy):
        self.mouse_x, self.mouse_y = x, y

        if self.combat_session and self.action_slider_dragging:
            rects = self._combat_window_rects()
            win_x, win_y, _, _ = rects["window"]
            sx1, sx2 = win_x + 40, win_x + 360
            clamped_x = max(sx1, min(sx2, x))

            max_commit = max(0, int(self.network.player.spaceship.current_defenders))
            if max_commit > 0:
                ratio = (clamped_x - sx1) / max(1, (sx2 - sx1))
                self.combat_commitment = int(round(ratio * max_commit))
            else:
                self.combat_commitment = 0
            return

        if self.prompt_mode == "ACTION_SLIDER":
            if self.action_slider_dragging:
                box_w, box_h = 520, 260
                bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2
                sx1, sx2 = bx + 48, bx + box_w - 48
                clamped_x = max(sx1, min(sx2, x))
                if self.action_slider_max > 0:
                    ratio = (clamped_x - sx1) / max(1, (sx2 - sx1))
                    self.action_slider_value = int(
                        round(ratio * int(self.action_slider_max))
                    )
                else:
                    self.action_slider_value = 0
            return

        if self.mode == "MARKET":
            content_x = 350
            planet = self.network.current_planet
            planet_items = self._get_visible_market_items()
            layout = self._get_market_layout(len(planet_items))
            visible_rows = layout["visible_rows"]
            y_offset = layout["list_start_y"]

            if self.market_item_locked:
                return

            rect_w = 760 if self.compare_mode else 560
            for i in range(len(planet_items)):
                # Adjust for scroll
                display_idx = i - self.market_scroll
                if display_idx < 0 or display_idx >= visible_rows:
                    continue

                item_y = y_offset - 40 - display_idx * MARKET_ROW_HEIGHT
                # Expanded selection box slightly for easier clicking
                if (
                    content_x - 15 < x < content_x + rect_w
                    and item_y - 12 < y < item_y + 28
                ):
                    self.selected_item_index = i
                    return  # Stop after finding match
            return

        elif self.mode == "SHIPYARD":
            content_x = 350
            panel_y = (SCREEN_HEIGHT - 80) - 100
            y_off = panel_y - 210
            for i in range(len(self.network.spaceships)):
                display_idx = i - self.shipyard_scroll
                if display_idx < 0 or display_idx >= 4:
                    continue

                ship_y = y_off - display_idx * 110
                # Use ship_y instead of shadowing the 'y' parameter for hit detection
                if (
                    content_x - 10 < x < content_x + 600
                    and ship_y - 10 < y < ship_y + 100
                ):
                    self.selected_ship_index = i
                    return
            return

        if x < 300:
            for i in range(len(self.menu_options)):
                y_pos = 500 - i * 45
                if (y_pos - 10) < y < (y_pos + 40):
                    self.selected_menu = i

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        if self.prompt_mode == "COMMANDER_STATUS_BOARD":
            visible_rows = 12
            max_scroll = max(0, len(self.commander_status_rows) - visible_rows)
            self.commander_status_scroll = max(
                0,
                min(max_scroll, int(self.commander_status_scroll) - int(scroll_y)),
            )
            return

        if self.mode == "MARKET":
            if self.market_item_locked:
                return
            self.market_scroll -= int(scroll_y)
            if self.market_scroll < 0:
                self.market_scroll = 0
        elif self.mode == "SHIPYARD":
            self.shipyard_scroll -= int(scroll_y)
            if self.shipyard_scroll < 0:
                self.shipyard_scroll = 0
            # Cap scroll to ensure hit detection matches drawing
            max_s_scroll = max(0, len(self.network.spaceships) - 4)
            if self.shipyard_scroll > max_s_scroll:
                self.shipyard_scroll = max_s_scroll

    def on_mouse_press(self, x, y, button, modifiers):
        content_x = 350
        content_y = SCREEN_HEIGHT - 80

        if self.wisdom_modal_active:
            if button == arcade.MOUSE_BUTTON_LEFT:
                bx, by, bw, bh = self.wisdom_ok_button_rect
                if bx <= x <= bx + bw and by <= y <= by + bh:
                    self.wisdom_modal_active = False
            return

        if self.combat_session:
            s = self.combat_session
            rects = self._combat_window_rects()

            def _in(rect):
                rx, ry, rw, rh = rect
                return rx <= x <= rx + rw and ry <= y <= ry + rh

            max_commit = max(0, int(self.network.player.spaceship.current_defenders))

            # --- Special weapon confirmation overlay intercept ---
            if self.combat_spec_weapon_confirm:
                if _in(rects["sw_confirm_yes"]):
                    self.combat_spec_weapon_confirm = False
                    self._combat_do_special_weapon()
                else:
                    # Any other click dismisses confirmation
                    self.combat_spec_weapon_confirm = False
                return

            if s.get("status") == "ACTIVE":
                win_x, win_y, _, _ = rects["window"]
                sx1, sx2 = win_x + 40, win_x + 360
                sy = win_y + 205
                if sx1 - 10 <= x <= sx2 + 10 and sy - 15 <= y <= sy + 15:
                    self.action_slider_dragging = True
                    # Immediate update on click
                    clamped_x = max(sx1, min(sx2, x))
                    if max_commit > 0:
                        ratio = (clamped_x - sx1) / max(1, (sx2 - sx1))
                        self.combat_commitment = int(round(ratio * max_commit))
                    else:
                        self.combat_commitment = 0
                    return

            if _in(rects["attack"]):
                if s.get("status") == "ACTIVE":
                    self._combat_do_round()
                return
            if _in(rects["cancel"]):
                if s.get("status") == "ACTIVE":
                    updated_s = self.network.flee_combat_session(s)
                    self.combat_session = updated_s
                    self.network.save_game()

                    if (
                        s.get("target_type") == "PLANET"
                        or updated_s.get("status") == "LOST_AND_FLED"
                    ):
                        self.arrival_msg = "RETREATING FROM HOSTILE SECTOR."
                        self.arrival_msg_timer = 3.0
                        self.window.show_view(TravelView(self.network))
                        return
                else:
                    self._close_combat_window()
                return

            # Special weapon button click — open confirmation dialog
            if (
                _in(rects["special_weapon"])
                and s.get("status") == "ACTIVE"
                and s.get("target_type") == "PLANET"
                and self.network.config.get("enable_special_weapons", True)
                and getattr(self.network.player.spaceship, "special_weapon", None)
            ):
                import time as _time

                cooldown_hours = float(
                    self.network.config.get(
                        "combat_special_weapon_cooldown_hours", 36.0
                    )
                )
                last_used = float(
                    getattr(self.network.player, "last_special_weapon_time", 0.0)
                )
                elapsed = (_time.time() - last_used) / 3600.0
                if elapsed >= cooldown_hours:
                    self.combat_spec_weapon_confirm = True
                    self._play_sfx("ui", "ui_confirm")
                return

            if s.get("status") != "ACTIVE":
                if _in(rects["post_autofit"]):
                    before_state = self._snapshot_post_combat_state()
                    success, msg = self._auto_install_systems_cargo()
                    s.setdefault("log", []).append(
                        f"POST-COMBAT AUTO-FIT: {msg.upper()}"
                    )
                    after_state = self._snapshot_post_combat_state()
                    self._record_post_combat_action(
                        "AUTO-FIT", before_state, after_state, msg
                    )
                    if success:
                        self.network.save_game()
                    return

                if _in(rects["post_repair"]):
                    before_state = self._snapshot_post_combat_state()
                    success, msg = self.network.repair_hull()
                    s.setdefault("log", []).append(f"POST-COMBAT REPAIR: {msg.upper()}")
                    after_state = self._snapshot_post_combat_state()
                    self._record_post_combat_action(
                        "REPAIR", before_state, after_state, msg
                    )
                    if success:
                        self.network.save_game()
                    return

                if _in(rects["post_close"]):
                    self._close_combat_window()
                    return

                if _in(rects["post_systems"]):
                    self._close_combat_window()
                    self.mode = "SYSTEMS"
                    self.system_message = "RETURNED TO SYSTEMS FROM COMBAT."
                    return

            # Swallow clicks outside modal controls while active.
            return

        if self.show_help_overlay:
            self.show_help_overlay = False
            return

        if self.prompt_mode == "BANK_INPUT":
            _bal_fn_map = {
                "deposit": lambda: self.network.player.credits,
                "withdraw": lambda: self.network.player.bank_balance,
                "p_deposit": lambda: self.network.player.credits,
                "p_withdraw": lambda: int(
                    (self.planet_finance_cache or {})
                    .get("current_planet", {})
                    .get("credit_balance", 0)
                ),
            }
            _max_val = int(_bal_fn_map.get(self.bank_input_mode, lambda: 0)())
            box_w, box_h = 520, 280
            bx = SCREEN_WIDTH // 2 - box_w // 2
            by = SCREEN_HEIGHT // 2 - box_h // 2
            # ALL button
            if bx + 30 <= x <= bx + 130 and by + 60 <= y <= by + 96 and _max_val > 0:
                self.bank_input_text = str(_max_val)
                return
            # HALF button
            if bx + 145 <= x <= bx + 245 and by + 60 <= y <= by + 96 and _max_val > 0:
                self.bank_input_text = str(max(1, _max_val // 2))
                return
            # CONFIRM button
            if (
                bx + 260 <= x <= bx + 400
                and by + 60 <= y <= by + 96
                and self.bank_input_text
            ):
                self._confirm_bank_input()
                return
            # CANCEL button
            if bx + 415 <= x <= bx + 495 and by + 60 <= y <= by + 96:
                self.prompt_mode = None
                self.bank_input_mode = None
                self.bank_input_text = ""
                return
            # Click outside box cancels
            if not (bx <= x <= bx + box_w and by <= y <= by + box_h):
                self.prompt_mode = None
                self.bank_input_mode = None
                self.bank_input_text = ""
            return

        if self.prompt_mode == "CONFIRM_LOGOUT":
            box_w, box_h = 560, 250
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2

            if bx + 70 <= x <= bx + 250 and by + 52 <= y <= by + 100:
                self.prompt_mode = None
                return
            if bx + 310 <= x <= bx + 490 and by + 52 <= y <= by + 100:
                from views.menu import MainMenuView

                if hasattr(self.network, "logout_commander"):
                    try:
                        self.network.logout_commander()
                    except Exception:
                        pass
                self.prompt_mode = None
                self.window.show_view(MainMenuView())
                return
            if not (bx <= x <= bx + box_w and by <= y <= by + box_h):
                self.prompt_mode = None
                return
            return

        if self.prompt_mode == "ACTION_SLIDER":
            box_w, box_h = 520, 260
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2
            if bx + 78 <= x <= bx + 238 and by + 26 <= y <= by + 68:
                self._confirm_action_slider()
                return
            if bx + box_w - 238 <= x <= bx + box_w - 78 and by + 26 <= y <= by + 68:
                self.prompt_mode = None
                self.action_slider_dragging = False
                return

            sx1, sx2 = bx + 48, bx + box_w - 48
            sy = by + box_h // 2
            if sx1 <= x <= sx2 and sy - 16 <= y <= sy + 16:
                self.action_slider_dragging = True
                clamped_x = max(sx1, min(sx2, x))
                if self.action_slider_max > 0:
                    ratio = (clamped_x - sx1) / max(1, (sx2 - sx1))
                    self.action_slider_value = int(
                        round(ratio * int(self.action_slider_max))
                    )
                else:
                    self.action_slider_value = 0
                return

            if not (bx <= x <= bx + box_w and by <= y <= by + box_h):
                self.prompt_mode = None
                self.action_slider_dragging = False
            return

        if self.prompt_mode == "COMMANDER_STATUS_BOARD":
            box_w, box_h = 1040, 560
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2
            close_x, close_y, close_w, close_h = (
                bx + box_w - 132,
                by + box_h - 44,
                112,
                30,
            )
            if close_x <= x <= close_x + close_w and close_y <= y <= close_y + close_h:
                self.prompt_mode = None
                return
            if not (bx <= x <= bx + box_w and by <= y <= by + box_h):
                self.prompt_mode = None
                return
            return

        # Sidebar Menu Clicks (Priority)
        if x < 300:
            for i in range(len(self.menu_options)):
                y_pos = 500 - i * 45
                if (y_pos - 10) < y < (y_pos + 30):
                    self.selected_menu = i
                    self._execute_menu_selection()
                    return

        if self.prompt_mode == "GIVE_SHIP_RECIPIENT":
            box_w, box_h = 500, 300
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2
            # Confirm button
            if (
                bx + box_w // 2 - 75 <= x <= bx + box_w // 2 + 75
                and by + 40 <= y <= by + 80
            ):
                others = self.network.get_other_players()
                if others:
                    target = self.orbital_targets[self.selected_target_index]
                    recipient = others[self.selected_recipient_index % len(others)]
                    success, self.orbit_message = self.network.claim_abandoned_ship(
                        target["name"], "GIVE", {"recipient": recipient}
                    )
                    if success:
                        self.orbital_targets = self.network.get_orbit_targets()
                        self.prompt_mode = None
                return
            if not (bx <= x <= bx + box_w and by <= y <= by + box_h):
                self.prompt_mode = None
            return

        if self.prompt_mode == "DISPOSAL_CHOICE":
            box_w, box_h = 560, 260
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2

            # Check buttons
            if by + 50 <= y <= by + 100:
                # Leave on Planet
                if bx + 40 <= x <= bx + 260:
                    success, msg = self.network.player.fire_crew(
                        self.disposal_specialty
                    )
                    self.crew_message = (
                        f"{msg} - LEFT AT {self.network.current_planet.name.upper()}."
                    )
                    if success:
                        self.network.save_game()
                    self.prompt_mode = None
                    self.disposal_specialty = None
                    return
                # Airlock
                if bx + 300 <= x <= bx + 520:
                    success, msg = self.network.player.fire_crew(
                        self.disposal_specialty
                    )
                    self.crew_message = f"{msg} - JETTISONED INTO THE VOID."
                    if success:
                        self.network.save_game()
                    self.prompt_mode = None
                    self.disposal_specialty = None
                    return

            # Click outside to cancel
            if not (bx <= x <= bx + box_w and by <= y <= by + box_h):
                self.prompt_mode = None
                self.disposal_specialty = None
            return

        if self.prompt_mode == "INSTALL_CHOICE":
            box_w, box_h = 500, 250
            bx, by = SCREEN_WIDTH // 2 - box_w // 2, SCREEN_HEIGHT // 2 - box_h // 2
            # Install
            if bx + 80 <= x <= bx + 230 and by + 50 <= y <= by + 100:
                ship = self.network.player.spaceship
                qty = self.trade_item_qty
                item_name = str(self.trade_item_name)

                pre_inventory = int(self.network.player.inventory.get(item_name, 0))
                pre_cargo = int(getattr(ship, "current_cargo_pods", 0))
                pre_shields = int(getattr(ship, "current_shields", 0))
                pre_defenders = int(getattr(ship, "current_defenders", 0))
                pre_integrity = int(getattr(ship, "integrity", 0))

                res = self.network.install_ship_upgrade(item_name, qty)

                success = False
                msg = ""
                if isinstance(res, dict):
                    success = res.get("success", False)
                    msg = str(res.get("message", ""))
                elif isinstance(res, tuple):
                    success = res[0]
                    msg = str(res[1])

                post_ship = self.network.player.spaceship
                post_inventory = int(self.network.player.inventory.get(item_name, 0))
                post_cargo = int(getattr(post_ship, "current_cargo_pods", 0))
                post_shields = int(getattr(post_ship, "current_shields", 0))
                post_defenders = int(getattr(post_ship, "current_defenders", 0))
                post_integrity = int(getattr(post_ship, "integrity", 0))

                installation_applied = (
                    post_inventory < pre_inventory
                    or post_cargo > pre_cargo
                    or post_shields > pre_shields
                    or post_defenders > pre_defenders
                    or post_integrity > pre_integrity
                )
                if installation_applied and not success:
                    success = True
                    if not msg:
                        msg = "Install completed."

                if success:
                    suffix = " (BULK)" if qty > 1 else ""
                    self.market_message = f"{msg.upper()}{suffix}"
                else:
                    self.market_message = (
                        f"INSTALL FAILED: {msg.upper()}. KEPT IN CARGO."
                    )
                self.prompt_mode = None
                return
            # Cargo
            if bx + 270 <= x <= bx + 420 and by + 50 <= y <= by + 100:
                # Already purchased and in inventory
                qty = self.trade_item_qty
                bulk_suffix = " (BULK)" if qty > 1 else ""
                self.market_message = f"KEPT {qty}x IN CARGO.{bulk_suffix}"
                self.prompt_mode = None
                return

        if self.mode == "MAIL":
            messages = self.network.player.messages

            content_x = 350
            compose_x, compose_y, compose_w, compose_h = content_x, 80, 140, 40
            reply_x, reply_y, reply_w, reply_h = content_x + 160, 80, 140, 40
            delete_x, delete_y, delete_w, delete_h = content_x + 320, 80, 140, 40

            if (
                compose_x <= x <= compose_x + compose_w
                and compose_y <= y <= compose_y + compose_h
            ):
                self._open_mail_compose()
                return

            if reply_x <= x <= reply_x + reply_w and reply_y <= y <= reply_y + reply_h:
                if messages and self.selected_mail_index < len(messages):
                    self._open_mail_reply(messages[self.selected_mail_index])
                return

            if (
                delete_x <= x <= delete_x + delete_w
                and delete_y <= y <= delete_y + delete_h
            ):
                if messages and self.selected_mail_index < len(messages):
                    self.network.delete_message(messages[self.selected_mail_index].id)
                    self.selected_mail_index = max(0, self.selected_mail_index - 1)
                    self.network.save_game()
                return

            for i, _ in enumerate(messages):
                row_y = SCREEN_HEIGHT - 230 - i * 40
                if content_x <= x <= content_x + 380 and row_y - 5 <= y <= row_y + 25:
                    self.selected_mail_index = i
                    break
            return

        if self.mode == "SYSTEMS":
            ship = self.network.player.spaceship
            owned_x = content_x + 400
            owned_y = 212
            owned_w = 360

            if (
                owned_x + 12 <= x <= owned_x + owned_w - 12
                and owned_y + 10 <= y <= owned_y + 38
            ):
                self._open_commander_status_board()
                return

            # Check repair button
            if ship.integrity < ship.max_integrity:
                repair_btn_x = content_x + 520
                repair_btn_y = 130
                if (
                    repair_btn_x <= x <= repair_btn_x + 220
                    and repair_btn_y <= y <= repair_btn_y + 40
                ):
                    success, msg = self.network.repair_hull()
                    self.system_message = msg
                    if success:
                        self.network.save_game()
                    return

            y_off = content_y - 400
            installables = [
                "Cargo Pod",
                "Energy Shields",
                "Fighter Squadron",
                "Nanobot Repair Kits",
            ]
            for item in installables:
                qty = self.network.player.inventory.get(item, 0)
                if qty > 0:
                    # Install button
                    if (
                        content_x + 430 <= x <= content_x + 530
                        and y_off - 10 <= y <= y_off + 20
                    ):
                        res = self.network.install_ship_upgrade(item, 1)
                        if isinstance(res, dict):
                            self.system_message = str(res.get("message", "")).upper()
                            if res.get("success"):
                                self.network.save_game()
                        elif isinstance(res, tuple):
                            self.system_message = str(res[1]).upper()
                            if res[0]:
                                self.network.save_game()
                        else:
                            self.system_message = "INSTALL COMPLETE."
                            self.network.save_game()
                        return

                    # Install max button
                    if (
                        content_x + 540 <= x <= content_x + 690
                        and y_off - 10 <= y <= y_off + 20
                    ):
                        # Determine max possible locally to send correct qty request,
                        # or just send a large number and let server clamp?
                        # Server clamps to inventory, but we should calculate logical max to avoid "Insufficient" errors
                        # if we ask for inventory amount but ship is full.

                        max_install = qty  # Default to all inventory

                        if item == "Cargo Pod":
                            space = max(
                                0, int(ship.max_cargo_pods - ship.current_cargo_pods)
                            )
                            max_install = min(qty, space)
                        elif item == "Energy Shields":
                            space = max(0, int(ship.max_shields - ship.current_shields))
                            max_install = min(qty, space)
                        elif item == "Fighter Squadron":
                            space = max(
                                0, int(ship.max_defenders - ship.current_defenders)
                            )
                            max_install = min(qty, space)
                        elif item == "Nanobot Repair Kits":
                            if ship.integrity >= ship.max_integrity:
                                max_install = 0
                            else:
                                needed = (
                                    ship.max_integrity - ship.integrity + 49
                                ) // 50
                                max_install = min(qty, int(needed))

                        if max_install <= 0:
                            self.system_message = "NO CAPACITY FOR INSTALL."
                            return

                        res = self.network.install_ship_upgrade(item, max_install)
                        if isinstance(res, dict):
                            self.system_message = str(res.get("message", "")).upper()
                            if res.get("success"):
                                self.network.save_game()
                        elif isinstance(res, tuple):
                            self.system_message = str(res[1]).upper()
                            if res[0]:
                                self.network.save_game()
                        else:
                            self.system_message = "INSTALL COMPLETE."
                            self.network.save_game()
                        return
                    y_off -= 45

            # Planet Treasury Buttons (SYSTEMS Mode)
            if self.network.current_planet.owner == self.network.player.name:
                treasury_y = 100
                # Deposit
                if (
                    content_x + 200 <= x <= content_x + 340
                    and treasury_y + 30 <= y <= treasury_y + 70
                ):
                    self.bank_input_mode = "p_deposit"
                    self.bank_input_text = ""
                    self.prompt_mode = "BANK_INPUT"
                    return
                # Withdraw
                if (
                    content_x + 360 <= x <= content_x + 500
                    and treasury_y + 30 <= y <= treasury_y + 70
                ):
                    self.bank_input_mode = "p_withdraw"
                    self.bank_input_text = ""
                    self.prompt_mode = "BANK_INPUT"
                    return

        if self.mode == "BANK":
            btn_y = content_y - 320
            # Deposit custom amount
            if content_x <= x <= content_x + 180 and btn_y <= y <= btn_y + 50:
                self.bank_input_mode = "deposit"
                self.bank_input_text = ""
                self.prompt_mode = "BANK_INPUT"
                return
            # Deposit All
            if content_x <= x <= content_x + 180 and btn_y - 70 <= y <= btn_y - 20:
                success, msg = self.network.bank_deposit(self.network.player.credits)
                self.bank_message = msg
                if success:
                    self.network.save_game()
                return
            # Withdraw custom amount
            if content_x + 200 <= x <= content_x + 380 and btn_y <= y <= btn_y + 50:
                self.bank_input_mode = "withdraw"
                self.bank_input_text = ""
                self.prompt_mode = "BANK_INPUT"
                return
            # Withdraw All
            if (
                content_x + 200 <= x <= content_x + 380
                and btn_y - 70 <= y <= btn_y - 20
            ):
                success, msg = self.network.bank_withdraw(
                    self.network.player.bank_balance
                )
                self.bank_message = msg
                if success:
                    self.network.save_game()
                return

            finance = self.planet_finance_cache or {}
            planet_fin = finance.get("current_planet") or {}
            can_manage_planet = bool(finance.get("can_manage", False))
            treasury_y = btn_y - 340

            # Planet deposit custom amount
            if (
                content_x + 16 <= x <= content_x + 166
                and treasury_y + 50 <= y <= treasury_y + 86
                and can_manage_planet
            ):
                self.bank_input_mode = "p_deposit"
                self.bank_input_text = ""
                self.prompt_mode = "BANK_INPUT"
                return

            # Planet deposit all
            if (
                content_x + 176 <= x <= content_x + 326
                and treasury_y + 50 <= y <= treasury_y + 86
                and can_manage_planet
            ):
                success, msg = self.network.planet_deposit(
                    int(self.network.player.credits)
                )
                self.bank_message = msg
                if success:
                    self._refresh_planet_finance_cache(force=True)
                    self.network.save_game()
                return

            # Planet withdraw custom amount
            if (
                content_x + 336 <= x <= content_x + 486
                and treasury_y + 50 <= y <= treasury_y + 86
                and can_manage_planet
            ):
                self.bank_input_mode = "p_withdraw"
                self.bank_input_text = ""
                self.prompt_mode = "BANK_INPUT"
                return

            # Planet withdraw all
            if (
                content_x + 496 <= x <= content_x + 646
                and treasury_y + 50 <= y <= treasury_y + 86
                and can_manage_planet
            ):
                success, msg = self.network.planet_withdraw(
                    int(planet_fin.get("credit_balance", 0))
                )
                self.bank_message = msg
                if success:
                    self._refresh_planet_finance_cache(force=True)
                    self.network.save_game()
                return

        if self.mode == "CREW":
            p = self.network.player
            ship = p.spaceship

            # Dismiss Buttons
            y_off = content_y - 125
            for spec in ["weapons", "engineer"]:
                slots = ship.crew_slots.get(spec, 0)
                if slots > 0:
                    if spec in p.crew:
                        if (
                            content_x + 650 <= x <= content_x + 750
                            and y_off - 10 <= y <= y_off + 20
                        ):
                            self.disposal_specialty = spec
                            self.prompt_mode = "DISPOSAL_CHOICE"
                            return
                    y_off -= 58
                else:
                    y_off -= 40

            # Hire Buttons - Matches spacing in on_draw
            y_off -= 30
            y_off -= 60
            offers = self.network.get_planet_crew_offers(self.network.current_planet)
            if offers:
                for offer in offers:
                    s_type = offer["type"]
                    level = int(offer["level"])
                    cost = int(offer["hire_cost"])
                    daily_pay = int(offer["daily_pay"])
                    has_slot = ship.crew_slots.get(s_type, 0) > 0
                    has_already = s_type in p.crew
                    can_afford = p.credits >= cost

                    if can_afford and has_slot and not has_already:
                        if (
                            content_x + 650 <= x <= content_x + 800
                            and y_off - 10 <= y <= y_off + 20
                        ):
                            from classes import CrewMember

                            self.naming_crew_member = CrewMember(
                                "UNNAMED", s_type, level
                            )
                            self.naming_crew_member.hire_cost = cost
                            self.naming_crew_member.daily_pay = daily_pay
                            self.naming_name_input = ""
                            self.prompt_mode = "CREW_NAMING"
                            return
                    y_off -= 50

        if self.mode == "SHIPYARD":
            panel_y = content_y - 100
            y_off = panel_y - 210
            for i, ship in enumerate(self.network.spaceships):
                # Adjust for scroll
                display_idx = i - self.shipyard_scroll
                if display_idx < 0 or display_idx >= 4:
                    continue

                ship_y = y_off - display_idx * 110
                # Select ship (using ship_y to avoid shadowing 'y' parameter)
                if (
                    content_x - 10 <= x <= content_x + 600
                    and ship_y - 10 <= y <= ship_y + 90
                ):
                    self.selected_ship_index = i
                    # Purchase button
                    if (
                        content_x + 450 <= x <= content_x + 570
                        and ship_y + 25 <= y <= ship_y + 65
                    ):
                        success, msg = self.network.buy_ship(ship)
                        self.shipyard_message = msg
                        if success:
                            self.network.save_game()
                    return

        if self.mode == "ORBIT":
            self.orbit_message_color = COLOR_SECONDARY
            content_x = 350
            content_y = SCREEN_HEIGHT - 80
            p = self.network.current_planet
            # Select target
            for i in range(len(self.orbital_targets)):
                target_y = content_y - 120 - i * 60
                if (
                    content_x - 10 <= x <= content_x + 490
                    and target_y - 10 <= y <= target_y + 40
                ):
                    self.selected_target_index = i
                    self.orbit_message = ""
                    return

            # Buttons in detail panel
            if self.orbital_targets:
                target = self.orbital_targets[self.selected_target_index]
                panel_x = content_x + 550
                panel_y = content_y - 300

                if not target.get("is_abandoned"):
                    cargo_items = [
                        (name, int(qty))
                        for name, qty in sorted(
                            self.network.player.inventory.items(),
                            key=lambda pair: str(pair[0]).lower(),
                        )
                        if int(qty) > 0
                    ]
                    if cargo_items:
                        self.orbit_give_cargo_index = max(
                            0,
                            min(
                                int(self.orbit_give_cargo_index),
                                len(cargo_items) - 1,
                            ),
                        )
                        visible_rows = 3
                        start_idx = max(
                            0,
                            min(
                                int(self.orbit_give_cargo_index),
                                len(cargo_items) - visible_rows,
                            ),
                        )
                        end_idx = min(len(cargo_items), start_idx + visible_rows)
                        for display_idx, item_idx in enumerate(
                            range(start_idx, end_idx)
                        ):
                            row_y = panel_y + 104 - display_idx * 18
                            if (
                                panel_x + 16 <= x <= panel_x + 372
                                and row_y - 3 <= y <= row_y + 13
                            ):
                                self.orbit_give_cargo_index = int(item_idx)
                                return

                if target.get("is_abandoned"):
                    # CLAIM SHIP (KEEP)
                    if (
                        panel_x + 20 <= x <= panel_x + 130
                        and panel_y + 80 <= y <= panel_y + 120
                    ):
                        success, self.orbit_message = self.network.claim_abandoned_ship(
                            target["name"], "KEEP"
                        )
                        if success:
                            self.orbital_targets = self.network.get_orbit_targets()
                        return
                    # SCRAP SHIP (SELL)
                    if (
                        panel_x + 140 <= x <= panel_x + 250
                        and panel_y + 80 <= y <= panel_y + 120
                    ):
                        success, self.orbit_message = self.network.claim_abandoned_ship(
                            target["name"], "SELL"
                        )
                        if success:
                            self.orbital_targets = self.network.get_orbit_targets()
                        return
                    # LOOT SHIP
                    if (
                        panel_x + 260 <= x <= panel_x + 370
                        and panel_y + 80 <= y <= panel_y + 120
                    ):
                        success, self.orbit_message = self.network.claim_abandoned_ship(
                            target["name"], "LOOT"
                        )
                        return
                    # ATTACK
                    if (
                        panel_x + 20 <= x <= panel_x + 130
                        and panel_y + 20 <= y <= panel_y + 60
                    ):
                        self._start_combat(target)
                        return
                    # GIVE SHIP
                    if (
                        panel_x + 140 <= x <= panel_x + 250
                        and panel_y + 20 <= y <= panel_y + 60
                    ):
                        self.prompt_mode = "GIVE_SHIP_RECIPIENT"
                        self.selected_recipient_index = 0
                        return
                else:
                    # Combat
                    if (
                        panel_x + 20 <= x <= panel_x + 130
                        and panel_y + 20 <= y <= panel_y + 60
                    ):
                        self._start_combat(target)
                        return
                    # Give Cargo
                    if (
                        panel_x + 140 <= x <= panel_x + 250
                        and panel_y + 20 <= y <= panel_y + 60
                    ):
                        self._give_cargo(target)
                        return
                    # Bribe Ship
                    if (
                        panel_x + 260 <= x <= panel_x + 370
                        and panel_y + 20 <= y <= panel_y + 60
                    ):
                        if (
                            target["type"] == "NPC"
                            and target["obj"].personality == "bribable"
                        ):
                            self._bribe_ship(target)
                        return

            # Conquer or Transfer Buttons
            if p.owner == self.network.player.name:
                # Leave 5
                if content_x <= x <= content_x + 150 and 100 <= y <= 140:
                    self._open_orbit_transfer_prompt("fighters", "TO_PLANET")
                    return
                # Take 5
                if content_x + 160 <= x <= content_x + 310 and 100 <= y <= 140:
                    self._open_orbit_transfer_prompt("fighters", "TO_SHIP")
                    return
                # Assign 10 shields
                if content_x <= x <= content_x + 150 and 52 <= y <= 92:
                    self._open_orbit_transfer_prompt("shields", "TO_PLANET")
                    return
                # Take 10 shields
                if content_x + 160 <= x <= content_x + 310 and 52 <= y <= 92:
                    self._open_orbit_transfer_prompt("shields", "TO_SHIP")
                    return
            else:
                conquer_btn_x = content_x + 500
                if conquer_btn_x <= x <= conquer_btn_x + 200 and 100 <= y <= 140:
                    self._start_combat({"type": "PLANET", "name": p.name})
                    return

        if self.mode == "MARKET":
            content_x = 350

            planet = self.network.current_planet
            planet_items = self._get_visible_market_items()
            layout = self._get_market_layout(len(planet_items))
            visible_rows = layout["visible_rows"]
            y_offset = layout["list_start_y"]

            # SELECT ITEM IN LIST (Respect Scroll)
            rect_w = 760 if self.compare_mode else 560
            for i in range(len(planet_items)):
                display_idx = i - self.market_scroll
                if display_idx < 0 or display_idx >= visible_rows:
                    continue

                item_y = y_offset - 40 - display_idx * MARKET_ROW_HEIGHT
                if (
                    content_x - 15 < x < content_x + rect_w
                    and item_y - 12 < y < item_y + 28
                ):
                    if self.market_item_locked:
                        if i == self.selected_item_index:
                            self.market_item_locked = False
                        return

                    if i == self.selected_item_index:
                        self.market_item_locked = True
                    else:
                        self.selected_item_index = i
                        self.market_message = ""
                    return

            # Button regions
            panel_x = content_x + (790 if self.compare_mode else 600)
            panel_y = SCREEN_HEIGHT - 620
            panel_h = 390

            # Check Bribe button
            intel_box_x = panel_x + 20
            intel_box_y = panel_y + panel_h - 128
            intel_box_w = 350
            bribe_snapshot = self.network.get_bribe_market_snapshot(planet.name)
            b_bx, b_by = intel_box_x + intel_box_w - 154, intel_box_y + 14
            if (
                b_bx <= x <= b_bx + 144
                and b_by <= y <= b_by + 28
                and bool(bribe_snapshot.get("can_bribe", False))
            ):
                success, msg = self.network.bribe_npc()
                self.market_message = msg.upper()
                if success:
                    self.network.save_game()
                    self.npc_remark = "Don't tell established authorities about our... specialized catalog."
                return

            btn_w, btn_h = 120, 40
            sel_item, sel_price = planet_items[self.selected_item_index]
            ship = self.network.player.spaceship
            cargo_used = sum(self.network.player.inventory.values())
            cargo_max = ship.current_cargo_pods
            inv_qty = self.network.player.inventory.get(sel_item, 0)
            is_buyable = self._is_item_buyable_in_market(sel_item)
            can_afford = self.network.player.credits // sel_price if is_buyable else 0
            space_left = cargo_max - cargo_used
            max_buy = min(can_afford, space_left) if is_buyable else 0

            # Buy 1
            bx, by = panel_x + 20, panel_y + 56
            btn_w = 160
            if bx <= x <= bx + btn_w and by <= y <= by + btn_h and max_buy >= 1:
                self._open_market_slider_prompt("BUY", sel_item, max_buy)
                return

            # Buy Max
            bx2 = bx + 190
            if bx2 <= x <= bx2 + btn_w and by <= y <= by + btn_h and max_buy > 0:
                # Specialized logic for installable items (Bulk support)
                if sel_item in ["Cargo Pod", "Energy Shields", "Fighter Squadron"]:
                    success, msg = self.network.trade_item(sel_item, "BUY", max_buy)
                    self.market_message = str(msg).upper()
                    if success:
                        self.trade_item_name = sel_item
                        self.trade_item_qty = max_buy
                        self.prompt_mode = "INSTALL_CHOICE"
                        self.network.save_game()
                    elif "PREPARE TO BE BOARDED" in str(msg):
                        self.mode = "ORBIT"
                        self._start_combat(
                            {"type": "PLANET", "name": self.network.current_planet.name}
                        )
                        self.orbit_message = str(msg).upper()
                    return

                success, msg = self.network.trade_item(sel_item, "BUY", max_buy)
                self.market_message = msg.upper()
                if success:
                    self.market_message = self._format_market_trade_feedback(
                        "BUY", sel_item, max_buy
                    )
                    self.network.save_game()
                elif "PREPARE TO BE BOARDED" in msg:
                    self.mode = "ORBIT"
                    self._start_combat(
                        {"type": "PLANET", "name": self.network.current_planet.name}
                    )
                    self.orbit_message = msg.upper()
                return

            # Sell 1
            sx, sy = panel_x + 20, panel_y + 8
            if sx <= x <= sx + btn_w and sy <= y <= sy + btn_h and inv_qty >= 1:
                self._open_market_slider_prompt("SELL", sel_item, inv_qty)
                return

            # Sell All
            sx2 = sx + 190
            if sx2 <= x <= sx2 + btn_w and sy <= y <= sy + btn_h and inv_qty > 0:
                success, msg = self.network.trade_item(sel_item, "SELL", inv_qty)
                self.market_message = msg.upper()
                if success:
                    self.market_message = self._format_market_trade_feedback(
                        "SELL", sel_item, inv_qty
                    )
                    self.network.save_game()
                elif "PREPARE TO BE BOARDED" in msg:
                    self.mode = "ORBIT"
                    self._start_combat(
                        {"type": "PLANET", "name": self.network.current_planet.name}
                    )
                    self.orbit_message = msg.upper()
                return

    def _start_combat(self, target_data):
        if self.combat_session and self.combat_session.get("status") == "ACTIVE":
            return

        ok, msg, session = self.network.start_combat_session(target_data)
        if not ok:
            self.orbit_message = msg.upper()
            self.orbit_message_color = COLOR_ACCENT
            return

        self.combat_session = session
        self.post_combat_actions = []
        self.combat_impact_effects = []
        self._play_sfx("combat", "combat_fire")
        fighters = int(self.network.player.spaceship.current_defenders)
        self.combat_commitment = 1 if fighters > 0 else 0

        if "weapons" in self.network.player.crew:
            opener = self.network.player.crew["weapons"].get_remark("combat_start")
            self.combat_session["log"].append(
                f"{self.network.player.crew['weapons'].name}: {opener}"
            )
        elif "engineer" in self.network.player.crew:
            opener = self.network.player.crew["engineer"].get_remark("combat_start")
            self.combat_session["log"].append(
                f"{self.network.player.crew['engineer'].name}: {opener}"
            )

    def on_mouse_release(self, x, y, button, modifiers):
        self.action_slider_dragging = False
        if self.combat_session:
            # Ensure commitment is clamped on release
            max_commit = max(0, int(self.network.player.spaceship.current_defenders))
            self.combat_commitment = max(0, min(self.combat_commitment, max_commit))

    def _combat_do_round(self):
        if not self.combat_session:
            return

        pre_target = self.network._get_target_stats(self.combat_session)
        p_ship = self.network.player.spaceship
        pre_player = (
            int(p_ship.current_shields),
            int(p_ship.current_defenders),
            int(p_ship.integrity),
        )

        ok, msg, session = self.network.resolve_combat_round(
            self.combat_session, self.combat_commitment
        )
        if not ok:
            self.orbit_message = msg.upper()
            self.orbit_message_color = COLOR_ACCENT
            return

        self.combat_session = session
        self.network.save_game()
        self._play_sfx("combat", "combat_fire")

        post_target = self.network._get_target_stats(self.combat_session)
        post_player = (
            int(self.network.player.spaceship.current_shields),
            int(self.network.player.spaceship.current_defenders),
            int(self.network.player.spaceship.integrity),
        )

        target_shield_hit = max(0, int(pre_target[0]) - int(post_target[0]))
        target_hull_hit = max(0, int(pre_target[2]) - int(post_target[2]))
        player_shield_hit = max(0, int(pre_player[0]) - int(post_player[0]))
        player_hull_hit = max(0, int(pre_player[2]) - int(post_player[2]))

        if target_shield_hit > 0 or target_hull_hit > 0:
            self._queue_combat_effect("laser_to_target", duration=0.18)
        if player_shield_hit > 0 or player_hull_hit > 0:
            self._queue_combat_effect("laser_to_player", duration=0.18)
        if target_shield_hit > 0:
            self._queue_combat_effect("shield_target", duration=0.32)
        if player_shield_hit > 0:
            self._queue_combat_effect("shield_player", duration=0.32)
        if target_hull_hit > 0:
            self._queue_combat_effect("hull_target", duration=0.36)
        if player_hull_hit > 0:
            self._queue_combat_effect("hull_player", duration=0.36)

        recent_lines = " ".join(self.combat_session.get("log", [])[-3:]).upper()
        if "YOU [CRITICAL HIT]" in recent_lines:
            self.combat_flash_timer = 0.18
            self.combat_flash_color = COLOR_PRIMARY
            self._queue_combat_effect("hull_target", duration=0.44)
            self._play_sfx("combat", "combat_hit")
        elif "ENEMY [CRITICAL HIT]" in recent_lines:
            self.combat_flash_timer = 0.18
            self.combat_flash_color = COLOR_ACCENT
            self._queue_combat_effect("hull_player", duration=0.44)
            self._play_sfx("combat", "combat_hit")

        if self.combat_session.get("status") == "ACTIVE":
            max_commit = int(self.network.player.spaceship.current_defenders)
            self.combat_commitment = min(self.combat_commitment, max_commit)
            if max_commit > 0 and self.combat_commitment == 0:
                self.combat_commitment = 1

        # Trigger orchestrated audio-visual effects for combat
        try:
            from .effects_orchestrator import get_orchestrator

            orch = get_orchestrator()
            # compute approximate effect locations based on combat window
            rects = self._combat_window_rects()
            x, y, w, h = rects["window"]
            p_x = x + 220
            p_y = y + 365
            t_x = x + w - 220
            t_y = y + 365

            # Player firing / enemy firing
            orch.trigger_player_fires(location=(p_x, p_y))
            orch.trigger_enemy_fires(location=(t_x, t_y))

            # Shield/hull hits
            if target_shield_hit > 0:
                orch.trigger_shield_hit(
                    location=(t_x, t_y), is_player=False, intensity=1.0
                )
            if target_hull_hit > 0:
                orch.trigger_hull_damage(
                    location=(t_x, t_y), is_player=False, intensity=1.0
                )
            if player_shield_hit > 0:
                orch.trigger_shield_hit(
                    location=(p_x, p_y), is_player=True, intensity=1.0
                )
            if player_hull_hit > 0:
                orch.trigger_hull_damage(
                    location=(p_x, p_y), is_player=True, intensity=1.0
                )

            # Critical hit flash handled via existing UI; trigger critical if present
            recent_lines = " ".join(self.combat_session.get("log", [])[-3:]).upper()
            if "YOU [CRITICAL HIT]" in recent_lines:
                orch.trigger_critical_hit(location=(t_x, t_y))
            elif "ENEMY [CRITICAL HIT]" in recent_lines:
                orch.trigger_critical_hit(location=(p_x, p_y))
        except Exception:
            pass

    def _combat_do_special_weapon(self):
        """Execute the player's special weapon against the current planet target."""
        if not self.combat_session:
            return
        if self.combat_session.get("target_type") != "PLANET":
            return

        result_data = self.network.fire_special_weapon(self.combat_session)
        success = result_data.get("success", False)
        msg = result_data.get("message", "")
        result = result_data.get("result", {})

        if not success:
            self.combat_session.setdefault("log", []).append(
                f"[SPECIAL WEAPON] FAILED: {msg.upper()}"
            )
            self.orbit_message = msg.upper()
            self.orbit_message_color = COLOR_ACCENT
            return

        # Update the local session log from server-refreshed session if provided
        srv_session = result_data.get("session")
        if srv_session and isinstance(srv_session, dict):
            self.combat_session = srv_session

        # Sound & visual effects
        self._play_sfx("combat", "combat_special")
        self._play_sfx("combat", "combat_hit")
        self.combat_flash_timer = 0.30
        self.combat_flash_color = (255, 80, 40)
        self._queue_combat_effect("hull_target", duration=0.55)
        self._queue_combat_effect("laser_to_target", duration=0.28)

        # Orchestrated special weapon effects
        try:
            from .effects_orchestrator import get_orchestrator

            orch = get_orchestrator()
            rects = self._combat_window_rects()
            x, y, w, h = rects["window"]
            t_x = x + w - 220
            t_y = y + 365
            orch.trigger_special_weapon(location=(t_x, t_y), intensity=1.4)
            orch.trigger_hull_damage(
                location=(t_x, t_y), is_player=False, intensity=1.4
            )
        except Exception:
            pass

        self.network.save_game()

        # Update local player cooldown timestamp
        import time as _time

        self.network.player.last_special_weapon_time = _time.time()

        # Log the result
        weapon_name = str(result.get("weapon_name", "SPECIAL WEAPON"))
        pop_before = int(result.get("pop_before", 0))
        pop_after = int(result.get("pop_after", 0))
        pop_pct = float(result.get("pop_reduction_pct", 0))
        treasury_before = int(result.get("treasury_before", 0))
        treasury_after = int(result.get("treasury_after", 0))

        log_line = (
            f"[{weapon_name.upper()} FIRED] Pop {pop_before:,}\u2192{pop_after:,} "
            f"(-{pop_pct:.0f}%), Treasury {treasury_before:,}\u2192{treasury_after:,}"
        )
        self.combat_session.setdefault("log", []).append(log_line)

    def _close_combat_window(self):
        if not self.combat_session:
            return

        summary = self.combat_session.get("summary") or {}
        msg = summary.get("message", "Combat window closed.")
        credits_delta = int(summary.get("credits_delta", 0))
        if credits_delta != 0:
            sign = "+" if credits_delta > 0 else ""
            msg = f"{msg}  CREDITS {sign}{credits_delta}."

        self.orbit_message = msg.upper()
        result = summary.get("result", "")
        status = self.combat_session.get("status", "")

        if status == "LOST_AND_FLED":
            self.combat_session = None
            self.combat_commitment = 1
            self.combat_flash_timer = 0.0
            self.combat_impact_effects = []
            self.combat_spec_weapon_confirm = False
            self.post_combat_actions = []
            self.prompt_mode = None
            self.arrival_msg = "COMBAT LOST. IMMEDIATE EVACUATION INITIATED."
            self.arrival_msg_timer = 5.0
            self.window.show_view(TravelView(self.network))
            return

        if result == "WON":
            self.orbit_message_color = COLOR_PRIMARY
        elif result in ("LOST", "FLED"):
            self.orbit_message_color = COLOR_ACCENT
            self.mode = "ORBIT"
        else:
            self.orbit_message_color = COLOR_SECONDARY

        self.combat_session = None
        self.combat_commitment = 1
        self.combat_flash_timer = 0.0
        self.combat_impact_effects = []
        self.combat_spec_weapon_confirm = False
        self.post_combat_actions = []
        self.prompt_mode = None

        if 0 <= self.selected_menu < len(self.menu_options):
            if self.menu_options[self.selected_menu] == "LOGOUT":
                self.selected_menu = 0

        if self.mode == "ORBIT":
            self.orbital_targets = self.network.get_orbit_targets()
            if self.orbital_targets:
                self.selected_target_index = min(
                    self.selected_target_index, len(self.orbital_targets) - 1
                )
            else:
                self.selected_target_index = 0

    def _give_cargo(self, target_data):
        if not self.network.player.inventory:
            self.orbit_message = "YOU HAVE NO CARGO TO GIVE."
            self.orbit_message_color = COLOR_SECONDARY
            return

        cargo_items = [
            name
            for name, qty in sorted(
                self.network.player.inventory.items(),
                key=lambda pair: str(pair[0]).lower(),
            )
            if int(qty) > 0
        ]
        if not cargo_items:
            self.orbit_message = "YOU HAVE NO CARGO TO GIVE."
            self.orbit_message_color = COLOR_SECONDARY
            return

        self.orbit_give_cargo_index = max(
            0, min(int(self.orbit_give_cargo_index), len(cargo_items) - 1)
        )
        item = cargo_items[int(self.orbit_give_cargo_index)]
        qty = 1

        target_type = str(target_data.get("type", "")).upper()
        if target_type == "NPC":
            target_name = str(getattr(target_data.get("obj"), "name", "UNKNOWN"))
            personality = str(
                getattr(target_data.get("obj"), "personality", "neutral")
            ).lower()
        else:
            target_name = str(target_data.get("name", "UNKNOWN"))
            personality = "player"

        success, msg = self.network.gift_cargo_to_orbit_target(target_data, item, qty)
        self.orbit_message = str(msg).upper()
        self.orbit_message_color = COLOR_PRIMARY if success else COLOR_ACCENT
        if not success:
            return

        auth_delta = 0
        frontier_delta = 0
        if personality == "friendly":
            auth_delta = 1
        elif personality == "hostile":
            auth_delta = -1
            frontier_delta = 1
        elif personality in ("bribable", "dismissive", "player"):
            frontier_delta = 1
        else:
            frontier_delta = 1

        new_auth = int(self.network._get_authority_standing())
        new_frontier = int(self.network._get_frontier_standing())
        if auth_delta != 0:
            new_auth = int(self.network._adjust_authority_standing(auth_delta))
        if frontier_delta != 0:
            new_frontier = int(self.network._adjust_frontier_standing(frontier_delta))

        response_templates = {
            "friendly": [
                "APPRECIATED, COMMANDER. YOUR SUPPORT HELPS KEEP OUR ROUTE SAFE.",
                "RECEIVED WITH THANKS. WE'LL PUT THIS CARGO TO GOOD USE.",
            ],
            "hostile": [
                "WE TAKE WHAT WE WANT. THIS TIME, YOU OFFERED.",
                "TRIBUTE ACCEPTED. STAY OUT OF OUR FLIGHT LANE.",
            ],
            "bribable": [
                "NICE DOING BUSINESS WITH YOU. I OWE YOU A FAVOR.",
                "NOW THAT'S A FAIR TRADE. YOUR NAME IS GOOD HERE.",
            ],
            "dismissive": [
                "TRANSFER LOGGED. MOVE ALONG.",
                "FINE. CARGO RECEIVED.",
            ],
            "player": [
                "CARGO RECEIVED. THANKS FOR THE ASSIST.",
                "TRANSFER CONFIRMED. YOU HAVE MY GRATITUDE.",
            ],
        }
        response_text = random.choice(
            response_templates.get(personality, response_templates["player"])
        )

        rep_segments = []
        if auth_delta != 0:
            rep_segments.append(
                f"AUTH {auth_delta:+d} => {new_auth:+d} {self.network.get_authority_standing_label()}"
            )
        if frontier_delta != 0:
            rep_segments.append(
                f"FRONT {frontier_delta:+d} => {new_frontier:+d} {self.network.get_frontier_standing_label()}"
            )
        rep_line = "REP UPDATE: " + (
            " | ".join(rep_segments) if rep_segments else "NO CHANGE"
        )

        self.orbit_message = (
            f"{str(msg).upper()}\n"
            f"{target_name.upper()} RESPONSE: {response_text}\n"
            f"{rep_line}"
        )
        if auth_delta < 0:
            self.orbit_message_color = COLOR_ACCENT
        else:
            self.orbit_message_color = COLOR_PRIMARY

        self.network.send_message(
            self.network.player.name,
            "CARGO ACKNOWLEDGED",
            response_text,
            sender_name=target_name.upper(),
        )

        remaining_items = [
            name
            for name, qty in sorted(
                self.network.player.inventory.items(),
                key=lambda pair: str(pair[0]).lower(),
            )
            if int(qty) > 0
        ]
        if remaining_items:
            self.orbit_give_cargo_index = max(
                0,
                min(int(self.orbit_give_cargo_index), len(remaining_items) - 1),
            )
        else:
            self.orbit_give_cargo_index = 0

        self.network.save_game()

    def _bribe_ship(self, target_data):
        npc = target_data["obj"]
        cost = 100
        if self.network.player.credits >= cost:
            self.network.player.credits -= cost
            # Chance to get information or a gift back
            npc.personality = "friendly"
            gift = "Titanium"
            self.network.player.inventory[gift] = (
                self.network.player.inventory.get(gift, 0) + 1
            )
            self.orbit_message = f"BRIBE ACCEPTED. {npc.name.upper()} IS NOW FRIENDLY AND GAVE YOU 1x {gift}."
            self.orbit_message_color = COLOR_PRIMARY
            self.network.save_game()

            # Follow up mail tip
            if random.random() < 0.6:
                p = random.choice(self.network.planets)
                self.network.send_message(
                    self.network.player.name,
                    "SECTOR TIP",
                    f"Since we're on the same side now, keep an eye on {p.name.upper()}. I hear the prices are fluctuating in a very profitable way.",
                    sender_name=npc.name.upper(),
                )
        else:
            self.orbit_message = "NOT ENOUGH CREDITS FOR BRIBE (100 CR)."
            self.orbit_message_color = COLOR_ACCENT


# â”€â”€ Standalone view modules (extracted for modularity) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
# These classes are defined in their own files; imported here so that any
# existing code doing `from views.gameplay import WarpView` continues to work.
from .warp_view import WarpView  # noqa: E402,F401
from .popup_view import TimedPopupView  # noqa: E402,F401
from .travel_event_view import TravelEventView  # noqa: E402,F401
from .travel_combat_view import TravelCombatView  # noqa: E402,F401
from .travel_view import TravelView  # noqa: E402,F401
