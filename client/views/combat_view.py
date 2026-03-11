import arcade
import math
import random
import threading
from pathlib import Path

from constants import SCREEN_WIDTH, SCREEN_HEIGHT, COLOR_PRIMARY, COLOR_SECONDARY, COLOR_ACCENT, COLOR_TEXT_DIM, get_font


class CombatView(arcade.View):
    """Phase-5 tactical combat renderer backed by strategic combat API."""

    ROUND_INTERVAL_SECONDS = 8.0
    MAX_FLOATING_DAMAGE = 24
    MAX_IMPACT_EFFECTS = 18
    STAR_COUNT = 100

    def __init__(self, network, planet_row, full_state):
        super().__init__()
        self.network = network
        self.planet_row = dict(planet_row or {})
        self.full_state = dict(full_state or {})
        self.font_ui = get_font("ui")
        self.font_ui_bold = get_font("ui_bold")
        self.combat_id = None
        self.state = {}
        self.log = []
        self.round_timer = 0.0
        self.animation_time = 0.0
        self.flash_timer = 0.0
        self.floating_damage = []
        self.last_attacker_hit = 0
        self.last_defender_hit = 0
        self._texture_cache = {}
        self._impact_effects = []
        self._asset_root = Path(__file__).resolve().parents[1] / "assets"
        self._laser_texture = None
        self._explosion_texture = None
        self._shield_hit_texture = None
        self._round_lock = threading.Lock()
        self._round_result = None
        self._round_request_in_flight = False
        self._screen_shake = 0.0
        self._stars = []
        self._grid_lines = []
        self._ship_positions = {"attacker": (SCREEN_WIDTH // 4, SCREEN_HEIGHT // 2), "defender": ((SCREEN_WIDTH * 3) // 4, SCREEN_HEIGHT // 2)}
        self.show_perf_hud = False
        self._perf_accum = 0.0
        self._perf_frames = 0
        self._fps_estimate = 0.0
        self._frame_ms_estimate = 0.0
        self.status = "INITIALIZING COMBAT..."

    def on_show_view(self):
        arcade.set_background_color((6, 8, 12))
        self._load_effect_textures()
        self._build_static_background_data()
        self._preload_ship_textures()
        self._start_combat()

    def _build_static_background_data(self):
        rng = random.Random(42)
        self._stars = []
        for _ in range(self.STAR_COUNT):
            self._stars.append(
                (
                    rng.randint(0, SCREEN_WIDTH),
                    rng.randint(0, SCREEN_HEIGHT),
                    rng.uniform(0.5, 1.7),
                    rng.uniform(0.2, 1.0),
                )
            )

        self._grid_lines = []
        for y in range(140, SCREEN_HEIGHT - 140, 24):
            self._grid_lines.append((80, y, SCREEN_WIDTH - 80, y))
        for x in range(80, SCREEN_WIDTH - 80, 42):
            self._grid_lines.append((x, 140, x, SCREEN_HEIGHT - 140))

    def _preload_ship_textures(self):
        for cls in ("fighter", "bomber", "cruiser", "freighter", "flagship"):
            for side in (True, False):
                self._ship_texture(cls, side)

    def _load_effect_textures(self):
        try:
            self._laser_texture = arcade.load_texture(str(self._asset_root / "effects" / "laser.png"))
        except Exception:
            self._laser_texture = None
        try:
            self._explosion_texture = arcade.load_texture(str(self._asset_root / "effects" / "explosion.png"))
        except Exception:
            self._explosion_texture = None
        try:
            self._shield_hit_texture = arcade.load_texture(str(self._asset_root / "effects" / "shield_hit.png"))
        except Exception:
            self._shield_hit_texture = None

    def _ship_class_from_id(self, ship_id: str) -> str:
        name = str(ship_id or "").lower()
        for cls in ("fighter", "bomber", "cruiser", "freighter", "flagship"):
            if cls in name:
                return cls
        # deterministic fallback based on identifier
        options = ["fighter", "bomber", "cruiser", "freighter", "flagship"]
        return options[abs(hash(name)) % len(options)]

    def _ship_texture(self, ship_id: str, is_attacker: bool):
        cls = self._ship_class_from_id(ship_id)
        side = "player" if is_attacker else "npc"
        key = f"{cls}_{side}"
        if key in self._texture_cache:
            return self._texture_cache[key]
        path = self._asset_root / "ships" / f"{cls}_{side}.png"
        try:
            tex = arcade.load_texture(str(path))
        except Exception:
            tex = None
        self._texture_cache[key] = tex
        return tex

    def _request_round_in_background(self, combat_id: int):
        if self._round_request_in_flight:
            return
        self._round_request_in_flight = True

        def _worker():
            try:
                result = self.network.combat_round_phase5(int(combat_id))
            except Exception as exc:
                result = {"success": False, "message": f"COMBAT ROUND FAILED: {exc}"}
            with self._round_lock:
                self._round_result = result
            self._round_request_in_flight = False

        threading.Thread(target=_worker, daemon=True).start()

    def _resolve_player_ids(self):
        players = list((self.full_state or {}).get("players", []) or [])
        if not players:
            return (0, 0)
        me_name = str(getattr(getattr(self.network, "player", None), "name", "") or "").strip().lower()
        attacker = 0
        defender = 0
        owner_id = self.planet_row.get("owner_id")
        for row in players:
            pid = int(row.get("player_id", 0) or 0)
            pname = str(row.get("name") or "").strip().lower()
            if pname and pname == me_name:
                attacker = pid
            if owner_id is not None and int(owner_id) == pid:
                defender = pid
        if attacker <= 0:
            attacker = int(players[0].get("player_id", 0) or 0)
        if defender <= 0:
            for row in players:
                pid = int(row.get("player_id", 0) or 0)
                if pid != attacker:
                    defender = pid
                    break
        return (attacker, defender)

    def _start_combat(self):
        attacker_id, defender_id = self._resolve_player_ids()
        if attacker_id <= 0 or defender_id <= 0:
            self.status = "UNABLE TO RESOLVE ATTACKER/DEFENDER IDS."
            return
        attacker_fleet = [
            {"ship_id": "fighter_alpha", "hp": 100, "shields": 60, "tactic": "flank"},
            {"ship_id": "bomber_beta", "hp": 110, "shields": 50, "tactic": "board"},
            {"ship_id": "cruiser_gamma", "hp": 130, "shields": 70, "tactic": "shield up"},
        ]
        result = self.network.start_phase5_combat(attacker_id, defender_id, attacker_fleet)
        if not result.get("success"):
            self.status = str(result.get("message") or "FAILED TO START COMBAT.")
            return
        self.combat_id = int(result.get("combat_id", 0) or 0)
        self.status = f"COMBAT SESSION #{self.combat_id} ACTIVE."

    def on_update(self, delta_time):
        self._perf_accum += float(delta_time)
        self._perf_frames += 1
        if self._perf_accum >= 0.4:
            self._fps_estimate = self._perf_frames / self._perf_accum
            self._frame_ms_estimate = 1000.0 / max(1e-6, self._fps_estimate)
            self._perf_accum = 0.0
            self._perf_frames = 0

        self.animation_time += float(delta_time)
        self.flash_timer = max(0.0, self.flash_timer - float(delta_time))
        self._screen_shake = max(0.0, self._screen_shake - (3.5 * float(delta_time)))
        updated_floats = []
        for fx, fy, value, ttl, color in list(self.floating_damage):
            ttl -= float(delta_time)
            if ttl > 0.0:
                updated_floats.append((fx, fy + (38.0 * float(delta_time)), value, ttl, color))
        self.floating_damage = updated_floats
        effects = []
        for ex, ey, ttl, kind in list(self._impact_effects):
            ttl -= float(delta_time)
            if ttl > 0:
                effects.append((ex, ey, ttl, kind))
        self._impact_effects = effects

        round_result = None
        with self._round_lock:
            if self._round_result is not None:
                round_result = dict(self._round_result)
                self._round_result = None
        if round_result is not None:
            self._apply_round_result(round_result)

        if not self.combat_id:
            return
        self.round_timer += float(delta_time)
        if self._round_request_in_flight or self.round_timer < self.ROUND_INTERVAL_SECONDS:
            return
        self.round_timer = 0.0
        self._request_round_in_background(int(self.combat_id))

    def _apply_round_result(self, result):
        if not result.get("success"):
            self.status = str(result.get("message") or "COMBAT ROUND FAILED")
            return
        self.state = dict(result.get("state", {}) or {})
        new_lines = list(result.get("log", []) or [])
        self.log.extend(new_lines)
        self.log = self.log[-20:]
        self._extract_damage_markers(new_lines)
        status = str(self.state.get("status") or "active")
        if status != "active":
            self.status = f"COMBAT RESOLVED: {status.upper()}"

    def _extract_damage_markers(self, lines):
        for line in lines:
            text = str(line or "")
            if "DEALT" not in text:
                if "CRITICAL HIT" in text.upper():
                    self.flash_timer = 0.9
                continue
            try:
                left = text.split("DEALT", 1)[1].split("|", 1)[0].strip()
                right = text.rsplit("DEALT", 1)[1].split(".", 1)[0].strip()
                self.last_attacker_hit = int(left)
                self.last_defender_hit = int(right)
                self.floating_damage.append((SCREEN_WIDTH * 0.33, SCREEN_HEIGHT * 0.52, self.last_attacker_hit, 1.2, COLOR_PRIMARY))
                self.floating_damage.append((SCREEN_WIDTH * 0.67, SCREEN_HEIGHT * 0.52, self.last_defender_hit, 1.2, COLOR_SECONDARY))
                self._impact_effects.append((SCREEN_WIDTH * 0.67, SCREEN_HEIGHT * 0.52, 0.55, "explosion"))
                self._impact_effects.append((SCREEN_WIDTH * 0.33, SCREEN_HEIGHT * 0.52, 0.55, "shield"))
                self._screen_shake = min(8.0, self._screen_shake + 2.5)
                self.floating_damage = self.floating_damage[-self.MAX_FLOATING_DAMAGE :]
                self._impact_effects = self._impact_effects[-self.MAX_IMPACT_EFFECTS :]
            except Exception:
                continue

    def _draw_ship_column(self, ships, x, title, color, is_attacker):
        arcade.draw_text(title, x, SCREEN_HEIGHT - 160, color, 15, anchor_x="center", font_name=self.font_ui_bold)
        y = SCREEN_HEIGHT - 210
        for row in list(ships or [])[:6]:
            hp = int(row.get("hp", 0) or 0)
            shields = int(row.get("shields", 0) or 0)
            ship_id = str(row.get("ship_id") or "SHIP")
            arcade.draw_rectangle_filled(x, y, 250, 78, (18, 24, 34, 228))
            arcade.draw_rectangle_outline(x, y, 250, 78, color, 1)

            tex = self._ship_texture(ship_id, is_attacker)
            if tex:
                angle = -4 if is_attacker else 184
                arcade.draw_texture_rect(
                    tex,
                    arcade.XYWH(x - 86 if is_attacker else x + 86, y + 2, 58, 58),
                    angle=angle,
                )

            arcade.draw_text(ship_id.upper(), x - 44, y + 16, color, 10, font_name=self.font_ui)
            arcade.draw_text(f"HP {hp}", x - 44, y + 1, COLOR_TEXT_DIM, 10, font_name=self.font_ui)
            arcade.draw_text(f"SH {shields}", x + 20, y + 1, COLOR_TEXT_DIM, 10, font_name=self.font_ui)

            hp_ratio = max(0.0, min(1.0, hp / 130.0))
            sh_ratio = max(0.0, min(1.0, shields / 100.0))
            arcade.draw_lrtb_rectangle_filled(x - 44, x + 62, y - 12, y - 18, (30, 35, 46, 220))
            arcade.draw_lrtb_rectangle_filled(x - 44, x - 44 + (106 * hp_ratio), y - 12, y - 18, (232, 92, 88, 240))
            arcade.draw_lrtb_rectangle_filled(x - 44, x + 62, y - 21, y - 27, (30, 35, 46, 220))
            arcade.draw_lrtb_rectangle_filled(x - 44, x - 44 + (106 * sh_ratio), y - 21, y - 27, (90, 204, 255, 240))
            y -= 70

    def on_draw(self):
        self.clear()

        shake_x = 0.0
        shake_y = 0.0
        if self._screen_shake > 0.0:
            shake_x = math.sin(self.animation_time * 45.0) * self._screen_shake
            shake_y = math.cos(self.animation_time * 40.0) * self._screen_shake

        for sx, sy, twinkle_speed, brightness in self._stars:
            alpha = int(70 + (110 * brightness * (0.5 + 0.5 * math.sin(self.animation_time * twinkle_speed))))
            arcade.draw_circle_filled(sx, sy, 1.3, (150, 180, 210, max(35, min(200, alpha))))

        grid_color = (20, 35, 46, 120)
        for x1, y1, x2, y2 in self._grid_lines:
            arcade.draw_line(x1 + shake_x * 0.2, y1 + shake_y * 0.2, x2 + shake_x * 0.2, y2 + shake_y * 0.2, grid_color, 1)

        arcade.draw_text(
            "TACTICAL COMBAT",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 80,
            COLOR_ACCENT,
            30,
            anchor_x="center",
            font_name=self.font_ui_bold,
        )

        attacker_ships = list(self.state.get("attacker_ships", []) or [])
        defender_ships = list(self.state.get("defender_ships", []) or [])
        round_no = int(self.state.get("round_number", 0) or 0)

        arcade.draw_text(
            f"ROUND {round_no} | STATUS: {str(self.state.get('status', 'active')).upper()}",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 120,
            COLOR_PRIMARY,
            14,
            anchor_x="center",
            font_name=self.font_ui,
        )

        self._draw_ship_column(attacker_ships, int(SCREEN_WIDTH // 4 + shake_x), "ATTACKER", COLOR_PRIMARY, True)
        self._draw_ship_column(defender_ships, int((SCREEN_WIDTH * 3) // 4 + shake_x), "DEFENDER", COLOR_SECONDARY, False)

        beam_wave = abs(math.sin(self.animation_time * 5.0))
        beam_alpha = int(45 + (110 * beam_wave))
        if attacker_ships and defender_ships:
            if self._laser_texture:
                arcade.draw_texture_rect(
                    self._laser_texture,
                    arcade.XYWH(SCREEN_WIDTH // 2 + shake_x * 0.4, SCREEN_HEIGHT // 2 + shake_y * 0.4, 360 + (80 * beam_wave), 26),
                    color=arcade.types.Color(255, 255, 255, beam_alpha),
                )
            else:
                arcade.draw_line(
                    SCREEN_WIDTH // 4 + 80,
                    SCREEN_HEIGHT // 2,
                    (SCREEN_WIDTH * 3) // 4 - 80,
                    SCREEN_HEIGHT // 2,
                    (240, 245, 255, beam_alpha),
                    2,
                )
            arcade.draw_circle_filled(
                SCREEN_WIDTH // 2 + shake_x * 0.4,
                SCREEN_HEIGHT // 2 + shake_y * 0.4,
                8 + (6 * beam_wave),
                (120, 220, 255, 110),
            )

        # Thruster trails near fleet lanes.
        for lane_x in (SCREEN_WIDTH // 4 - 90, (SCREEN_WIDTH * 3) // 4 + 90):
            for i in range(4):
                drift = (self.animation_time * 90.0 + i * 15.0) % 70.0
                arcade.draw_circle_filled(lane_x + shake_x * 0.2, 520 - drift + shake_y * 0.2, 3 + i * 0.7, (110, 210, 255, 70 - i * 12))

        for ex, ey, ttl, kind in self._impact_effects:
            alpha = int(max(30, min(255, 255 * (ttl / 0.55))))
            if kind == "explosion" and self._explosion_texture:
                arcade.draw_texture_rect(
                    self._explosion_texture,
                    arcade.XYWH(ex, ey, 72, 72),
                    color=arcade.types.Color(255, 255, 255, alpha),
                )
            elif kind == "shield" and self._shield_hit_texture:
                arcade.draw_texture_rect(
                    self._shield_hit_texture,
                    arcade.XYWH(ex, ey, 72, 72),
                    color=arcade.types.Color(255, 255, 255, alpha),
                )

        for fx, fy, value, ttl, color in self.floating_damage:
            alpha = int(max(40, min(255, 255 * (ttl / 1.2))))
            arcade.draw_text(
                f"-{int(value)}",
                fx,
                fy,
                (color[0], color[1], color[2], alpha),
                16,
                anchor_x="center",
                font_name=self.font_ui_bold,
            )

        arcade.draw_line(SCREEN_WIDTH // 2, 120, SCREEN_WIDTH // 2, SCREEN_HEIGHT - 170, COLOR_TEXT_DIM, 1)

        arcade.draw_text("COMBAT LOG", 70, 220, COLOR_ACCENT, 13, font_name=self.font_ui_bold)
        y = 195
        for line in reversed(self.log[-8:]):
            color = COLOR_ACCENT if "CRITICAL HIT" in str(line).upper() else COLOR_TEXT_DIM
            arcade.draw_text(str(line), 70, y, color, 11, font_name=self.font_ui)
            y -= 20

        arcade.draw_text(self.status, 70, 88, COLOR_PRIMARY, 12, font_name=self.font_ui)
        arcade.draw_text("[N] NEXT ROUND NOW  [ESC] BACK", 70, 62, COLOR_TEXT_DIM, 11, font_name=self.font_ui)

        if self.flash_timer > 0.0:
            overlay_alpha = int(60 + 120 * abs(math.sin(self.animation_time * 22.0)))
            arcade.draw_lrtb_rectangle_filled(0, SCREEN_WIDTH, SCREEN_HEIGHT, 0, (170, 20, 20, overlay_alpha))
            arcade.draw_text(
                "CRITICAL HIT!",
                SCREEN_WIDTH // 2,
                SCREEN_HEIGHT - 155,
                (255, 210, 210),
                26,
                anchor_x="center",
                font_name=self.font_ui_bold,
            )

        if self.show_perf_hud:
            self._draw_perf_hud()

    def _draw_perf_hud(self):
        lines = [
            "PERF HUD [F3 TOGGLE]",
            f"FPS: {self._fps_estimate:5.1f}",
            f"FRAME: {self._frame_ms_estimate:5.2f} ms",
            f"FLOATING DAMAGE: {len(self.floating_damage)}",
            f"IMPACT FX: {len(self._impact_effects)}",
            f"ROUND REQUEST: {'YES' if self._round_request_in_flight else 'NO'}",
            f"TEXTURE CACHE: {len(self._texture_cache)}",
        ]
        x = SCREEN_WIDTH - 300
        y_top = SCREEN_HEIGHT - 18
        panel_h = 20 + len(lines) * 18
        arcade.draw_lrtb_rectangle_filled(
            x,
            SCREEN_WIDTH - 12,
            y_top,
            y_top - panel_h,
            (8, 14, 22, 200),
        )
        arcade.draw_lrtb_rectangle_outline(
            x,
            SCREEN_WIDTH - 12,
            y_top,
            y_top - panel_h,
            (95, 155, 215, 220),
            1,
        )
        y = y_top - 22
        for i, line in enumerate(lines):
            color = COLOR_PRIMARY if i == 0 else COLOR_TEXT_DIM
            arcade.draw_text(
                line,
                x + 10,
                y,
                color,
                11,
                font_name=self.font_ui,
            )
            y -= 18

    def on_key_press(self, key, modifiers):
        if key == arcade.key.ESCAPE:
            from .planet_detail_view import PlanetDetailView

            self.window.show_view(PlanetDetailView(self.network, self.planet_row, self.full_state))
            return
        if key == arcade.key.N and self.combat_id:
            self.round_timer = self.ROUND_INTERVAL_SECONDS
            if not self._round_request_in_flight:
                self._request_round_in_background(int(self.combat_id))
            return
        if key == arcade.key.F3:
            self.show_perf_hud = not bool(self.show_perf_hud)
