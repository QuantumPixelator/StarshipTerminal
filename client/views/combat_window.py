"""combat_window.py — Dedicated Full-Screen Tactical Combat View
================================================================
ALL visuals, animation, and audio run entirely client-side.
The server is contacted only to compute round outcomes, flee, or
fire the special weapon.  Results are returned to the caller via
an ``on_combat_end(session)`` callback when the view closes.

Layout (1680 × 900)
───────────────────
  ┌──────────────────────────────────────────────────────────────────┐ ← 900
  │  TACTICAL COMBAT :: <TARGET>  [TYPE]  — ROUND N    THREAT ×1.20 │ header 56px
  ├──────────────────────────────────────────────────────────────────┤ ← 844
  │ PLAYER SHIP (left)   ══ projectiles ══   ENEMY SHIP (right+glow) │
  │  stat-bars                                         stat-bars     │
  │                                                                  │
  │              [combat effects: particles, flashes]                │
  │                                                                  │
  │                               ┊ ← LOG right strip (X 1080–1660) │
  ├──────────────────────────────────────────────────────────────────┤ ← 130
  │  ○────────●──────────────○  COMMIT: 3/8  [ATTACK] [FLEE] [NOVA] │ control bar
  └──────────────────────────────────────────────────────────────────┘ ← 0
"""

from __future__ import annotations

import math
import os
import pathlib
import random
import threading
from typing import Callable, Optional

import arcade

from constants import (
    COLOR_ACCENT,
    COLOR_BG,
    COLOR_PRIMARY,
    COLOR_SECONDARY,
    COLOR_TEXT_DIM,
    SCREEN_HEIGHT,
    SCREEN_WIDTH,
    get_font,
)

# ── Layout ────────────────────────────────────────────────────────────────────
_PLAYER_X   = int(SCREEN_WIDTH * 0.20)   # player ship centre-X
_ENEMY_X    = int(SCREEN_WIDTH * 0.72)   # enemy ship centre-X
_SHIP_Y     = 490                         # ship centre-Y (gameplay area)
_SHIP_SCALE = 1.9                         # draw scale for ship sprites

_LOG_X      = 1090                        # left edge of right-side log strip
_CTRL_H     = 130                         # height of bottom control bar
_HDR_H      = 56                          # height of top header bar

# Slider geometry
_SL_X   = int(SCREEN_WIDTH * 0.12)
_SL_W   = int(SCREEN_WIDTH * 0.36)
_SL_Y   = 68

# ── Phase constants ───────────────────────────────────────────────────────────
_PH_IDLE      = "idle"       # waiting for player input
_PH_ANIMATING = "animating"  # bolts in flight → server call fires when done
_PH_RESOLVING = "resolving"  # waiting for server response
_PH_RESULT    = "result"     # brief display pause showing what happened
_PH_SUMMARY   = "summary"    # combat ended; post-battle screen

# ── Visual palette ────────────────────────────────────────────────────────────
_GLOW_PLAYER  = (0,   210, 140)   # subtle cyan-green halo for player
_GLOW_ENEMY   = (255, 55,  30)    # hot-red halo for enemies (commanders etc.)
_BOLT_PLAYER  = (0,   255, 210)   # outgoing laser colour
_BOLT_ENEMY   = (255, 80,  50)    # incoming laser colour

_STAR_COUNT   = 180
_MAX_BOLTS    = 10
_MAX_PARTICLES = 140


# ═══════════════════════════════════════════════════════════════════════════════
# Particle / effect helpers
# ═══════════════════════════════════════════════════════════════════════════════

class _Star:
    __slots__ = ("x", "y", "spd", "sz", "alpha")

    def __init__(self) -> None:
        self.x     = random.uniform(0, SCREEN_WIDTH)
        self.y     = random.uniform(0, SCREEN_HEIGHT)
        self.spd   = random.uniform(10, 55)
        self.sz    = random.uniform(0.5, 2.2)
        self.alpha = random.randint(50, 200)

    def update(self, dt: float) -> None:
        self.x -= self.spd * dt
        if self.x < -2:
            self.x = SCREEN_WIDTH + 2
            self.y = random.uniform(0, SCREEN_HEIGHT)


class _Bolt:
    """A single weapon bolt flying from one ship to the other."""
    __slots__ = ("x", "y", "vx", "vy", "color", "ttl", "fired_by_player")

    def __init__(self, sx: float, sy: float, tx: float, ty: float,
                 fired_by_player: bool) -> None:
        self.fired_by_player = fired_by_player
        self.x, self.y = sx, sy
        dx = tx - sx
        dy = ty - sy
        dist = math.hypot(dx, dy) or 1.0
        spd = 1100.0
        self.vx = dx / dist * spd
        self.vy = dy / dist * spd
        self.ttl = dist / spd + 0.08
        self.color = _BOLT_PLAYER if fired_by_player else _BOLT_ENEMY

    def update(self, dt: float) -> None:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.ttl -= dt

    @property
    def alive(self) -> bool:
        return self.ttl > 0

    def draw(self) -> None:
        tail_len = 32.0
        tail_x = self.x - self.vx / 1100.0 * tail_len
        tail_y = self.y - self.vy / 1100.0 * tail_len
        r, g, b = self.color
        # wide dim glow
        arcade.draw_line(tail_x, tail_y, self.x, self.y, (r, g, b, 35), line_width=7)
        # mid glow
        arcade.draw_line(tail_x, tail_y, self.x, self.y, (r, g, b, 130), line_width=3)
        # bright core
        arcade.draw_line(tail_x, tail_y, self.x, self.y, (r, g, b, 230), line_width=1)
        # tip flare
        arcade.draw_circle_filled(self.x, self.y, 4.5, (255, 255, 255, 200))


class _ShieldRing:
    """Expanding ring that appears when shields absorb a hit."""
    __slots__ = ("x", "y", "r", "r_max", "ttl", "ttl_max", "color")

    def __init__(self, x: float, y: float, color: tuple) -> None:
        self.x, self.y = x, y
        self.r = 32.0
        self.r_max = 100.0
        self.ttl = self.ttl_max = 0.60
        self.color = color

    def update(self, dt: float) -> None:
        self.ttl -= dt
        frac = max(0.0, self.ttl / self.ttl_max)
        self.r = 32.0 + (1.0 - frac) * (self.r_max - 32.0)

    @property
    def alive(self) -> bool:
        return self.ttl > 0

    def draw(self) -> None:
        frac = max(0.0, self.ttl / self.ttl_max)
        r, g, b = self.color
        for width, a_mul in ((5, 0.18), (3, 0.50), (1, 1.0)):
            alpha = int(frac * 230 * a_mul)
            arcade.draw_circle_outline(self.x, self.y, self.r,
                                       (r, g, b, alpha), line_width=width)


class _Particle:
    """A single explosion or hull-damage fragment."""
    __slots__ = ("x", "y", "vx", "vy", "clr", "sz", "ttl", "ttl_max")

    _PALETTES = {
        "explosion": [(255, 160, 30), (255, 80, 20), (255, 220, 70), (200, 200, 255), (0, 220, 255)],
        "spark":     [(255, 230, 50), (255, 180, 30), (220, 220, 220), (0, 200, 255)],
    }

    def __init__(self, x: float, y: float, kind: str = "explosion") -> None:
        angle = random.uniform(0, math.tau)
        spd   = random.uniform(50, 310) if kind == "explosion" else random.uniform(20, 110)
        self.x, self.y = x, y
        self.vx = math.cos(angle) * spd
        self.vy = math.sin(angle) * spd
        self.clr = random.choice(self._PALETTES.get(kind, self._PALETTES["spark"]))
        self.sz  = random.uniform(2.5, 9.0) if kind == "explosion" else random.uniform(1.5, 3.5)
        self.ttl = self.ttl_max = random.uniform(0.4, 1.4) if kind == "explosion" else random.uniform(0.2, 0.6)

    def update(self, dt: float) -> None:
        self.x  += self.vx * dt
        self.y  += self.vy * dt
        self.vx *= 0.90
        self.vy *= 0.90
        self.ttl -= dt

    @property
    def alive(self) -> bool:
        return self.ttl > 0

    def draw(self) -> None:
        frac  = max(0.0, self.ttl / self.ttl_max)
        alpha = int(frac * 255)
        r, g, b = self.clr
        arcade.draw_circle_filled(self.x, self.y, self.sz * frac, (r, g, b, alpha))


# ═══════════════════════════════════════════════════════════════════════════════
# Main view
# ═══════════════════════════════════════════════════════════════════════════════

class CombatWindow(arcade.View):
    """Full-screen tactical combat view.

    All rendering, animation and audio are handled here.
    The server is called only to resolve rounds / flee / fire special weapon.

    Parameters
    ----------
    network      : SyncNetworkClient — used to call server endpoints
    session      : dict              — active session from start_combat_session
    on_combat_end: callable          — called with final session when view closes
    player_tex   : arcade.Texture|None
    enemy_tex    : arcade.Texture|None
    spec_status  : dict|None         — {enabled, on_cooldown, remaining_hours}
    """

    def __init__(
        self,
        network,
        session: dict,
        on_combat_end: Callable[[dict], None],
        player_tex: Optional[arcade.Texture] = None,
        enemy_tex:  Optional[arcade.Texture] = None,
        spec_status: Optional[dict] = None,
    ) -> None:
        super().__init__()
        self.network       = network
        self.session       = session
        self.on_combat_end = on_combat_end
        self.player_tex    = player_tex
        self.enemy_tex     = enemy_tex
        self.spec_status   = dict(spec_status or {})

        # ── Combat positions ──────────────────────────────────────────────
        self._px = _PLAYER_X
        self._ex = _ENEMY_X
        self._sy = _SHIP_Y

        # ── Stat tracking (updated from server after each round) ──────────
        ps = session.get("player_start", {})
        ts = session.get("target_start", {})
        self._p_sh  = int(ps.get("shields",   0))
        self._p_def = int(ps.get("defenders", 0))
        self._p_hp  = int(ps.get("integrity", 100))
        self._p_sh_max  = max(1, self._p_sh)
        self._p_def_max = max(1, self._p_def)
        self._p_hp_max  = max(1, self._p_hp)

        self._e_sh  = int(ts.get("shields",   0))
        self._e_def = int(ts.get("defenders", 0))
        self._e_hp  = int(ts.get("integrity", 100))
        self._e_sh_max  = max(1, self._e_sh)
        self._e_def_max = max(1, self._e_def)
        self._e_hp_max  = max(1, self._e_hp)

        # ── Sync live player stats from ship object ────────────────────────
        sp = network.player.spaceship
        self._p_sh  = int(sp.current_shields)
        self._p_def = int(sp.current_defenders)
        self._p_hp  = int(sp.integrity)
        self._p_sh_max  = self._p_sh_max  or max(1, self._p_sh)
        self._p_def_max = self._p_def_max or max(1, self._p_def)
        self._p_hp_max  = self._p_hp_max  or max(1, self._p_hp)

        # ── UI / commitment ───────────────────────────────────────────────
        self._max_commit  = int(sp.current_defenders)
        self.commitment   = max(1, min(1, self._max_commit)) if self._max_commit > 0 else 0
        self._sl_dragging = False

        # ── Phase & timing ────────────────────────────────────────────────
        self._phase       = _PH_IDLE
        self._phase_timer = 0.0
        self._t           = 0.0
        self._bob         = 0.0

        # ── Effects ───────────────────────────────────────────────────────
        self._bolts:    list[_Bolt]      = []
        self._rings:    list[_ShieldRing]= []
        self._parts:    list[_Particle]  = []
        self._stars:    list[_Star]      = [_Star() for _ in range(_STAR_COUNT)]
        self._shake     = 0.0
        self._flash_t   = 0.0
        self._flash_clr = COLOR_PRIMARY

        # ── Ship destroyed flags ──────────────────────────────────────────
        self._player_dead = False
        self._enemy_dead  = False

        # ── Log ───────────────────────────────────────────────────────────
        self._log: list[str] = list(session.get("log", []))

        # ── Spec-weapon confirmation overlay ──────────────────────────────
        self._spec_confirm = False

        # ── Background thread plumbing ────────────────────────────────────
        self._rlock       = threading.Lock()
        self._rresult: Optional[dict] = None
        self._in_flight   = False

        # ── Sound loading ─────────────────────────────────────────────────
        self._sfx: dict[str, Optional[arcade.Sound]] = {}
        self._audio_vol = 0.70

    # ─────────────────────────────────────────────────────────────────────────
    # Lifecycle
    # ─────────────────────────────────────────────────────────────────────────

    def on_show_view(self) -> None:
        arcade.set_background_color(COLOR_BG)
        self._load_sounds()
        self._play("combat_start")

    def on_hide_view(self) -> None:
        pass

    # ─────────────────────────────────────────────────────────────────────────
    # Sound
    # ─────────────────────────────────────────────────────────────────────────

    def _load_sounds(self) -> None:
        asset_dir = pathlib.Path(__file__).resolve().parents[1] / "assets" / "audio" / "combat"
        names = [
            "combat_start", "combat_fire", "combat_hit", "combat_miss",
            "shield_hit", "hull_damage", "critical_hit",
            "combat_victory", "combat_defeat", "combat_retreat",
            "special_weapon_fire", "special_weapon_ready",
        ]
        for name in names:
            for ext in (".wav", ".mp3", ".ogg"):
                p = asset_dir / f"{name}{ext}"
                if p.exists():
                    try:
                        self._sfx[name] = arcade.load_sound(str(p))
                    except Exception:
                        pass
                    break

    def _play(self, name: str, volume: Optional[float] = None) -> None:
        vol = volume if volume is not None else self._audio_vol
        snd = self._sfx.get(name)
        if snd:
            try:
                arcade.play_sound(snd, volume=vol)
            except Exception:
                pass
        else:
            # Fallback via integration layer (silent if unavailable)
            try:
                from .audio_playback_integration import play_effect_sound
                play_effect_sound(name, vol)
            except Exception:
                pass

    # ─────────────────────────────────────────────────────────────────────────
    # Background server calls
    # ─────────────────────────────────────────────────────────────────────────

    def _fire_round(self) -> None:
        if self._in_flight:
            return
        self._in_flight = True
        commitment = self.commitment

        def _worker() -> None:
            try:
                ok, msg, updated = self.network.resolve_combat_round(
                    self.session, commitment
                )
                with self._rlock:
                    self._rresult = {"ok": ok, "msg": msg, "session": updated}
            except Exception as exc:  # noqa: BLE001
                with self._rlock:
                    self._rresult = {"ok": False, "msg": str(exc), "session": self.session}
            finally:
                self._in_flight = False

        threading.Thread(target=_worker, daemon=True).start()

    def _fire_flee(self) -> None:
        if self._in_flight:
            return
        self._in_flight = True
        self._phase = _PH_RESOLVING
        self._phase_timer = 0.0
        self._play("combat_retreat")

        def _worker() -> None:
            try:
                updated = self.network.flee_combat_session(self.session)
                with self._rlock:
                    self._rresult = {"ok": True, "session": updated, "_fled": True}
            except Exception as exc:  # noqa: BLE001
                with self._rlock:
                    self._rresult = {"ok": False, "session": self.session, "_fled": True,
                                     "msg": str(exc)}
            finally:
                self._in_flight = False

        threading.Thread(target=_worker, daemon=True).start()

    def _fire_special(self) -> None:
        if self._in_flight:
            return
        self._in_flight = True
        self._spec_confirm = False
        self._phase = _PH_RESOLVING
        self._phase_timer = 0.0
        self._play("special_weapon_fire")

        def _worker() -> None:
            try:
                res = self.network.fire_special_weapon(self.session)
                with self._rlock:
                    self._rresult = {
                        "ok": res.get("success", False),
                        "msg": res.get("message", ""),
                        "session": res.get("session", self.session),
                        "_special": True,
                    }
            except Exception as exc:  # noqa: BLE001
                with self._rlock:
                    self._rresult = {"ok": False, "session": self.session,
                                     "_special": True, "msg": str(exc)}
            finally:
                self._in_flight = False

        threading.Thread(target=_worker, daemon=True).start()

    # ─────────────────────────────────────────────────────────────────────────
    # Update
    # ─────────────────────────────────────────────────────────────────────────

    def on_update(self, dt: float) -> None:
        dt = min(dt, 0.05)
        self._t           += dt
        self._phase_timer += dt
        self._bob          = math.sin(self._t * 2.2) * 8.0
        self._shake        = max(0.0, self._shake - dt * 7.0)
        self._flash_t      = max(0.0, self._flash_t - dt)

        # Stars
        for s in self._stars:
            s.update(dt)

        # Particles / effects
        for b in self._bolts:
            b.update(dt)
        self._bolts = [b for b in self._bolts if b.alive]

        for r in self._rings:
            r.update(dt)
        self._rings = [r for r in self._rings if r.alive]

        for p in self._parts:
            p.update(dt)
        self._parts = [p for p in self._parts if p.alive]

        # Phase machine
        if self._phase == _PH_ANIMATING:
            if not self._bolts:
                # All bolts have reached target — now ask server
                self._phase = _PH_RESOLVING
                self._phase_timer = 0.0
                self._fire_round()

        elif self._phase == _PH_RESOLVING:
            self._poll_result()

        elif self._phase == _PH_RESULT:
            if self._phase_timer > 1.8:
                if self.session.get("status") != "ACTIVE":
                    self._phase = _PH_SUMMARY
                    self._phase_timer = 0.0
                else:
                    self._phase = _PH_IDLE
                    self._phase_timer = 0.0

    def _poll_result(self) -> None:
        with self._rlock:
            result = self._rresult
            self._rresult = None
        if result is None:
            return
        self._apply_result(result)

    def _apply_result(self, result: dict) -> None:
        if not result.get("ok"):
            self._log.append(f"! {result.get('msg', 'ERROR')}")
            self._phase = _PH_IDLE
            self._phase_timer = 0.0
            return

        session = result.get("session", self.session)
        self.session = session

        # Fled: just go to summary
        if result.get("_fled"):
            self._phase = _PH_SUMMARY
            self._phase_timer = 0.0
            return

        # Read new live stats from enhanced server payload (if present)
        live_p = session.get("live_player", {})
        live_t = session.get("live_target", {})

        # Fallback: read player stats from spaceship object
        sp = self.network.player.spaceship
        new_p_sh  = int(live_p.get("shields",   sp.current_shields))
        new_p_def = int(live_p.get("defenders", sp.current_defenders))
        new_p_hp  = int(live_p.get("integrity", sp.integrity))

        new_e_sh  = int(live_t.get("shields",   self._e_sh))
        new_e_def = int(live_t.get("defenders", self._e_def))
        new_e_hp  = int(live_t.get("integrity", self._e_hp))

        # Deltas for visuals
        p_sh_dmg = max(0, self._p_sh  - new_p_sh)
        p_hp_dmg = max(0, self._p_hp  - new_p_hp)
        e_sh_dmg = max(0, self._e_sh  - new_e_sh)
        e_hp_dmg = max(0, self._e_hp  - new_e_hp)

        bob = self._bob
        # Enemy hit effects
        if e_sh_dmg > 0:
            self._rings.append(_ShieldRing(self._ex, self._sy + bob, COLOR_ACCENT))
            self._play("shield_hit")
        if e_hp_dmg > 0:
            self._spawn_sparks(self._ex, self._sy + bob, 14)
            self._play("hull_damage")
            self._shake = max(self._shake, 0.35)
        # Player hit effects
        if p_sh_dmg > 0:
            self._rings.append(_ShieldRing(self._px, self._sy + bob, COLOR_SECONDARY))
            if e_sh_dmg == 0:
                self._play("shield_hit")
        if p_hp_dmg > 0:
            self._spawn_sparks(self._px, self._sy + bob, 14)
            if e_hp_dmg == 0:
                self._play("hull_damage")
            self._shake = max(self._shake, 0.30)

        # Critical-hit flash
        recent = " ".join(session.get("log", [])[-3:]).upper()
        if "CRITICAL HIT" in recent:
            self._play("critical_hit")
            self._flash_t   = 0.28
            self._flash_clr = COLOR_PRIMARY if "YOU [CRITICAL HIT]" in recent else COLOR_ACCENT
            self._shake     = max(self._shake, 0.70)

        # Destruction events
        if new_e_hp <= 0 and not self._enemy_dead:
            self._enemy_dead = True
            self._spawn_explosion(self._ex, self._sy)
            self._play("combat_victory")
            self._shake = 1.2

        if new_p_hp <= 0 and not self._player_dead:
            self._player_dead = True
            self._spawn_explosion(self._px, self._sy)
            self._play("combat_defeat")
            self._shake = max(self._shake, 0.8)

        # Special-weapon hit (big flash)
        if result.get("_special"):
            self._flash_t   = 0.40
            self._flash_clr = (255, 140, 0)
            self._spawn_explosion(self._ex, self._sy)
            self._spawn_sparks(self._ex, self._sy, 20)
            self._shake = max(self._shake, 1.0)

        # Update tracked stats
        self._p_sh  = max(0, new_p_sh)
        self._p_def = max(0, new_p_def)
        self._p_hp  = max(0, new_p_hp)
        self._e_sh  = max(0, new_e_sh)
        self._e_def = max(0, new_e_def)
        self._e_hp  = max(0, new_e_hp)
        self._max_commit = self._p_def
        self.commitment  = min(self.commitment, self._max_commit)
        if self._max_commit > 0 and self.commitment == 0:
            self.commitment = 1

        self._log = list(session.get("log", []))
        self._phase = _PH_RESULT
        self._phase_timer = 0.0

        if session.get("status") != "ACTIVE":
            self._phase = _PH_SUMMARY
            self._phase_timer = 0.0

    # ─────────────────────────────────────────────────────────────────────────
    # Effect spawners
    # ─────────────────────────────────────────────────────────────────────────

    def _launch_volley(self) -> None:
        """Spawn two simultaneous bolts, player → enemy and enemy → player."""
        bob = self._bob
        if len(self._bolts) < _MAX_BOLTS:
            self._bolts.append(_Bolt(
                self._px + 45, self._sy + bob,
                self._ex - 45, self._sy + bob,
                fired_by_player=True,
            ))
        if len(self._bolts) < _MAX_BOLTS:
            self._bolts.append(_Bolt(
                self._ex - 45, self._sy + bob,
                self._px + 45, self._sy + bob,
                fired_by_player=False,
            ))
        self._play("combat_fire")

    def _spawn_explosion(self, x: float, y: float) -> None:
        cap = min(_MAX_PARTICLES, _MAX_PARTICLES - len(self._parts))
        for _ in range(min(60, cap)):
            self._parts.append(_Particle(x, y, "explosion"))

    def _spawn_sparks(self, x: float, y: float, n: int = 12) -> None:
        for _ in range(min(n, _MAX_PARTICLES)):
            self._parts.append(_Particle(x, y, "spark"))

    # ─────────────────────────────────────────────────────────────────────────
    # Input
    # ─────────────────────────────────────────────────────────────────────────

    def on_key_press(self, symbol: int, modifiers: int) -> None:
        if self._phase == _PH_SUMMARY:
            if symbol in (arcade.key.RETURN, arcade.key.SPACE, arcade.key.ESCAPE):
                self._close()
            return

        if self._phase != _PH_IDLE:
            return

        if symbol == arcade.key.RETURN:
            self._attack()
        elif symbol == arcade.key.ESCAPE:
            self._fire_flee()
        elif symbol == arcade.key.LEFT:
            self.commitment = max(0, self.commitment - 1)
        elif symbol == arcade.key.RIGHT:
            self.commitment = min(self._max_commit, self.commitment + 1)

    def on_mouse_press(self, x: int, y: int, button: int, modifiers: int) -> None:
        if self._phase == _PH_SUMMARY:
            self._close()
            return

        # Spec-weapon confirm modal
        if self._spec_confirm:
            cx = SCREEN_WIDTH // 2
            cy = SCREEN_HEIGHT // 2
            yes = (cx - 160, cy - 50, 140, 46)
            no  = (cx + 20,  cy - 50, 140, 46)
            if _inr(x, y, yes):
                self._fire_special()
            elif _inr(x, y, no):
                self._spec_confirm = False
            return

        if self._phase not in (_PH_IDLE, _PH_RESULT):
            return

        if self.session.get("status") != "ACTIVE":
            return

        rects = self._button_rects()

        if _inr(x, y, rects["slider_hit"]):
            self._sl_dragging = True
            self._update_slider(x)

        if _inr(x, y, rects["attack"]):
            self._attack()
        elif _inr(x, y, rects["flee"]):
            self._fire_flee()
        elif _inr(x, y, rects["special"]):
            if self.spec_status.get("enabled") and not self.spec_status.get("on_cooldown"):
                self._spec_confirm = True
                self._play("special_weapon_ready")

    def on_mouse_drag(self, x: int, y: int,
                      dx: int, dy: int, buttons: int, modifiers: int) -> None:
        if self._sl_dragging:
            self._update_slider(x)

    def on_mouse_release(self, x: int, y: int, button: int, modifiers: int) -> None:
        self._sl_dragging = False

    def _update_slider(self, mx: int) -> None:
        ratio = max(0.0, min(1.0, (mx - _SL_X) / _SL_W))
        self.commitment = round(ratio * self._max_commit)
        if self._max_commit > 0 and self.commitment == 0:
            self.commitment = 1

    def _attack(self) -> None:
        if self._phase != _PH_IDLE or self._in_flight:
            return
        if self.session.get("status") != "ACTIVE":
            return
        self._phase = _PH_ANIMATING
        self._phase_timer = 0.0
        self._launch_volley()

    def _close(self) -> None:
        self.on_combat_end(self.session)

    # ─────────────────────────────────────────────────────────────────────────
    # Draw
    # ─────────────────────────────────────────────────────────────────────────

    def on_draw(self) -> None:
        self.clear()

        # Screen-shake offset
        sk = self._shake
        sx = random.uniform(-sk * 7, sk * 7) if sk > 0.05 else 0.0
        sy = random.uniform(-sk * 4, sk * 4) if sk > 0.05 else 0.0

        self._draw_stars(sx, sy)
        self._draw_grid(sx, sy)
        self._draw_header()

        bob = self._bob
        if not self._player_dead:
            self._draw_ship(self._px + sx, self._sy + bob + sy, player=True)
        if not self._enemy_dead:
            self._draw_ship(self._ex + sx, self._sy + bob + sy, player=False)

        self._draw_stat_bars(sx, sy)

        # Particles / effects on top of ships
        for p in self._parts:
            p.draw()
        for r in self._rings:
            r.draw()
        for b in self._bolts:
            b.draw()

        # Screen flash
        if self._flash_t > 0:
            alpha = int(self._flash_t * 90)
            r, g, b = self._flash_clr
            arcade.draw_lrbt_rectangle_filled(
                0, SCREEN_WIDTH, 0, SCREEN_HEIGHT, (r, g, b, min(255, alpha))
            )

        # Log strip (right side)
        self._draw_log()

        # Vertical separator for log area
        arcade.draw_line(_LOG_X - 6, _CTRL_H, _LOG_X - 6, SCREEN_HEIGHT - _HDR_H,
                         (40, 40, 40, 180), 1)

        # Bottom control bar
        if self._phase == _PH_SUMMARY:
            self._draw_summary()
        elif self._phase in (_PH_ANIMATING, _PH_RESOLVING):
            self._draw_status_bar(
                "FIRING . . ." if self._phase == _PH_ANIMATING else "COMPUTING . . ."
            )
        else:
            self._draw_controls()

        # Spec-weapon confirm overlay
        if self._spec_confirm:
            self._draw_spec_confirm()

    # ── Sub-draw helpers ────────────────────────────────────────────────────

    def _draw_stars(self, sx: float, sy: float) -> None:
        for s in self._stars:
            arcade.draw_circle_filled(
                s.x + sx, s.y + sy, s.sz, (255, 255, 255, s.alpha)
            )

    def _draw_grid(self, sx: float, sy: float) -> None:
        """Subtle tactical-grid lines in the combat area."""
        area_w = _LOG_X - 12
        for gx in range(0, area_w, 90):
            arcade.draw_line(
                gx + sx, _CTRL_H, gx + sx, SCREEN_HEIGHT - _HDR_H,
                (0, 55, 35, 18)
            )
        for gy in range(_CTRL_H, SCREEN_HEIGHT - _HDR_H, 60):
            arcade.draw_line(
                0 + sx, gy + sy, area_w + sx, gy + sy,
                (0, 55, 35, 12)
            )

    def _draw_header(self) -> None:
        target = self.session.get("target_name", "UNKNOWN")
        t_type = self.session.get("target_type", "NPC")
        rnd    = int(self.session.get("round", 0))
        scale  = float(self.session.get("enemy_scale", 1.0))

        arcade.draw_lrbt_rectangle_filled(
            0, SCREEN_WIDTH,
            SCREEN_HEIGHT - _HDR_H, SCREEN_HEIGHT,
            (0, 0, 0, 220)
        )
        arcade.draw_line(
            0, SCREEN_HEIGHT - _HDR_H,
            SCREEN_WIDTH, SCREEN_HEIGHT - _HDR_H,
            COLOR_PRIMARY, 1
        )
        arcade.draw_text(
            f"TACTICAL COMBAT  ::  {target.upper()}  [{t_type}]  —  ROUND {rnd}",
            SCREEN_WIDTH // 2, SCREEN_HEIGHT - _HDR_H // 2,
            COLOR_PRIMARY, font_size=13,
            anchor_x="center", anchor_y="center",
            font_name=get_font(),
        )
        arcade.draw_text(
            f"THREAT ×{scale:.2f}",
            SCREEN_WIDTH - 18, SCREEN_HEIGHT - _HDR_H // 2,
            COLOR_TEXT_DIM, font_size=10,
            anchor_x="right", anchor_y="center",
            font_name=get_font(),
        )

    def _draw_ship(self, x: float, y: float, player: bool) -> None:
        tex   = self.player_tex if player else self.enemy_tex
        glow  = _GLOW_PLAYER if player else _GLOW_ENEMY
        r, g, b = glow

        # Glow layers — enemies get a stronger, wider halo
        layers = 3 if player else 6
        step_r = 18 if player else 22
        step_a = 12 if player else 20

        for i in range(layers, 0, -1):
            radius = 46 + i * step_r
            alpha  = step_a * i
            arcade.draw_circle_filled(x, y, radius, (r, g, b, alpha))

        # Ship sprite
        if tex:
            angle = 0.0 if player else 180.0
            draw_w = tex.width  * _SHIP_SCALE
            draw_h = tex.height * _SHIP_SCALE
            arcade.draw_texture_rect(
                tex,
                arcade.XYWH(x, y, draw_w, draw_h),
                angle=angle,
            )
        else:
            # Fallback polygon
            clr = COLOR_PRIMARY if player else COLOR_ACCENT
            if player:
                pts = [(x - 22, y - 20), (x + 32, y), (x - 22, y + 20)]
            else:
                pts = [(x + 22, y - 20), (x - 32, y), (x + 22, y + 20)]
            arcade.draw_polygon_filled(pts, clr)
            arcade.draw_polygon_outline(pts, (255, 255, 255, 140), 1)

        # Label under ship
        label = "PLAYER VESSEL" if player else self.session.get("target_name", "ENEMY").upper()
        color = COLOR_PRIMARY if player else COLOR_ACCENT
        arcade.draw_text(
            label, x, y - 90, color, font_size=9,
            anchor_x="center", font_name=get_font(),
        )

    def _draw_stat_bars(self, sx: float, sy: float) -> None:
        bw = 200
        bh = 10
        gap = 15

        def bar(lx: float, by: float, val: int, mx: int, clr: tuple) -> None:
            ratio = max(0.0, min(1.0, val / max(1, mx)))
            arcade.draw_lrbt_rectangle_filled(
                lx, lx + bw, by, by + bh, (25, 25, 25, 170)
            )
            if ratio > 0:
                arcade.draw_lrbt_rectangle_filled(
                    lx, lx + bw * ratio, by, by + bh, clr
                )
            arcade.draw_lrbt_rectangle_outline(
                lx, lx + bw, by, by + bh, (70, 70, 70, 160), 1
            )

        base_y = self._sy - 110
        # ── Player bars (left-aligned) ──
        px = self._px - bw // 2
        bar(px, base_y + gap, self._p_sh,  self._p_sh_max,  COLOR_SECONDARY)
        arcade.draw_text(
            f"SH {self._p_sh:>4}", px - 5, base_y + gap + bh // 2,
            COLOR_SECONDARY, font_size=8, anchor_x="right", anchor_y="center",
            font_name=get_font(),
        )
        bar(px, base_y, self._p_hp, self._p_hp_max, COLOR_PRIMARY)
        arcade.draw_text(
            f"HP {self._p_hp:>4}", px - 5, base_y + bh // 2,
            COLOR_PRIMARY, font_size=8, anchor_x="right", anchor_y="center",
            font_name=get_font(),
        )
        arcade.draw_text(
            f"FTR {self._p_def:>3}", px - 5, base_y - 14,
            COLOR_TEXT_DIM, font_size=8, anchor_x="right", anchor_y="center",
            font_name=get_font(),
        )

        # ── Enemy bars (right-aligned) ──
        ex = self._ex - bw // 2
        bar(ex, base_y + gap, self._e_sh,  self._e_sh_max,  COLOR_SECONDARY)
        arcade.draw_text(
            f"{self._e_sh:>4} SH", ex + bw + 5, base_y + gap + bh // 2,
            COLOR_SECONDARY, font_size=8, anchor_x="left", anchor_y="center",
            font_name=get_font(),
        )
        bar(ex, base_y, self._e_hp, self._e_hp_max, COLOR_ACCENT)
        arcade.draw_text(
            f"{self._e_hp:>4} HP", ex + bw + 5, base_y + bh // 2,
            COLOR_ACCENT, font_size=8, anchor_x="left", anchor_y="center",
            font_name=get_font(),
        )
        arcade.draw_text(
            f"{self._e_def:>3} FTR", ex + bw + 5, base_y - 14,
            COLOR_TEXT_DIM, font_size=8, anchor_x="left", anchor_y="center",
            font_name=get_font(),
        )

    def _draw_controls(self) -> None:
        arcade.draw_lrbt_rectangle_filled(
            0, SCREEN_WIDTH, 0, _CTRL_H, (0, 0, 0, 215)
        )
        arcade.draw_line(0, _CTRL_H, SCREEN_WIDTH, _CTRL_H, COLOR_PRIMARY, 1)

        # Slider track
        arcade.draw_line(_SL_X, _SL_Y, _SL_X + _SL_W, _SL_Y, (70, 70, 70, 200), 3)
        # Tick marks
        if self._max_commit > 0:
            for i in range(self._max_commit + 1):
                tx = _SL_X + i / self._max_commit * _SL_W
                arcade.draw_line(tx, _SL_Y - 6, tx, _SL_Y + 6, (50, 50, 50, 160), 1)
        # Knob
        ratio = self.commitment / max(1, self._max_commit)
        kx = _SL_X + ratio * _SL_W
        arcade.draw_circle_filled(kx, _SL_Y, 11, COLOR_PRIMARY)
        arcade.draw_circle_outline(kx, _SL_Y, 11, (255, 255, 255, 100), 1)
        # Label
        arcade.draw_text(
            f"COMMIT FIGHTERS: {self.commitment} / {self._max_commit}",
            _SL_X + _SL_W // 2, _SL_Y + 30, COLOR_SECONDARY,
            font_size=11, anchor_x="center", font_name=get_font(),
        )
        arcade.draw_text(
            "← LEFT / RIGHT → or drag",
            _SL_X + _SL_W // 2, _SL_Y + 46, COLOR_TEXT_DIM,
            font_size=8, anchor_x="center", font_name=get_font(),
        )

        # Buttons
        rects = self._button_rects()
        self._btn(rects["attack"],  "ATTACK ROUND",  COLOR_PRIMARY,  13)
        self._btn(rects["flee"],    "WARP AWAY",     COLOR_ACCENT,   11)
        if self.spec_status.get("enabled"):
            if self.spec_status.get("on_cooldown"):
                rem = float(self.spec_status.get("remaining_hours", 0))
                self._btn(rects["special"], f"NOVA CANNON [{rem:.1f}h]", COLOR_TEXT_DIM, 9)
            else:
                self._btn(rects["special"], "NOVA CANNON", (255, 155, 20), 10)

    def _draw_status_bar(self, text: str) -> None:
        arcade.draw_lrbt_rectangle_filled(0, SCREEN_WIDTH, 0, _CTRL_H, (0, 0, 0, 215))
        arcade.draw_line(0, _CTRL_H, SCREEN_WIDTH, _CTRL_H, COLOR_PRIMARY, 1)
        arcade.draw_text(
            text, SCREEN_WIDTH // 2, _CTRL_H // 2,
            COLOR_TEXT_DIM, font_size=14,
            anchor_x="center", anchor_y="center",
            font_name=get_font(),
        )

    def _draw_log(self) -> None:
        """Right-side rolling combat log."""
        lines  = self._log[-14:]
        top_y  = SCREEN_HEIGHT - _HDR_H - 14
        line_h = 17
        for i, line in enumerate(reversed(lines)):
            y = top_y - i * line_h
            if y < _CTRL_H + 8:
                break
            frac  = 1.0 - i / max(1, len(lines))
            alpha = int(max(60, frac * 210))
            line_u = line.upper()
            if "CRITICAL HIT" in line_u:
                clr = (*COLOR_PRIMARY, alpha)
            elif "YOU [HIT]" in line_u:
                clr = (*COLOR_SECONDARY, alpha)
            elif "ENEMY [HIT]" in line_u:
                clr = (*COLOR_ACCENT, alpha)
            elif "ROUND" in line_u and len(line) < 14:
                clr = (180, 180, 180, alpha)
            else:
                clr = (*COLOR_TEXT_DIM, alpha)
            arcade.draw_text(
                line[:65], _LOG_X + 8, y, clr,
                font_size=9, anchor_x="left", anchor_y="center",
                font_name=get_font(),
            )

    def _draw_summary(self) -> None:
        """Post-combat summary panel (replaces control bar + overlays screen)."""
        summary = self.session.get("summary") or {}
        result  = str(summary.get("result", "")).upper()
        credits_delta = int(summary.get("credits_delta", 0))

        # Dim backdrop
        arcade.draw_lrbt_rectangle_filled(
            0, SCREEN_WIDTH, 0, SCREEN_HEIGHT, (0, 0, 0, 155)
        )

        # Summary box
        bw, bh = 720, 380
        bx = SCREEN_WIDTH // 2 - bw // 2
        by = SCREEN_HEIGHT // 2 - bh // 2
        arcade.draw_lrbt_rectangle_filled(bx, bx + bw, by, by + bh, (5, 8, 14, 240))
        border = COLOR_PRIMARY if result == "WON" else COLOR_ACCENT
        arcade.draw_lrbt_rectangle_outline(bx, bx + bw, by, by + bh, border, 2)

        cx = SCREEN_WIDTH // 2
        y  = by + bh - 42

        # Title
        titles = {"WON": "VICTORY", "LOST": "DEFEAT", "FLED": "RETREATED"}
        title  = titles.get(result, "COMBAT ENDED")
        arcade.draw_text(
            title, cx, y, border, font_size=24,
            anchor_x="center", anchor_y="center",
            font_name=get_font("title"),
        )
        y -= 46

        # Credits
        sign = "+" if credits_delta >= 0 else ""
        arcade.draw_text(
            f"CREDITS CHANGE:  {sign}{credits_delta:,}",
            cx, y, COLOR_SECONDARY, font_size=13,
            anchor_x="center", font_name=get_font(),
        )
        y -= 30

        # Stats comparison
        s_end = summary.get("player_end", {})
        t_end = summary.get("target_end", {})
        if s_end or t_end:
            p_hp_end = int(s_end.get("integrity", self._p_hp))
            e_hp_end = int(t_end.get("integrity", self._e_hp))
            arcade.draw_text(
                f"YOUR HULL: {p_hp_end} / {self._p_hp_max}    "
                f"ENEMY HULL: {e_hp_end} / {self._e_hp_max}",
                cx, y, COLOR_TEXT_DIM, font_size=10,
                anchor_x="center", font_name=get_font(),
            )
            y -= 24

        # Streak / threat
        streak = int(summary.get("win_streak", 0))
        scale  = float(summary.get("enemy_scale", float(self.session.get("enemy_scale", 1.0))))
        arcade.draw_text(
            f"THREAT ×{scale:.2f}   |   WIN STREAK: {streak}",
            cx, y, COLOR_TEXT_DIM, font_size=10,
            anchor_x="center", font_name=get_font(),
        )
        y -= 24

        # Rare loot
        rare = summary.get("rare_loot")
        if rare:
            arcade.draw_text(
                f"RARE LOOT: {rare}", cx, y, (255, 215, 0),
                font_size=11, anchor_x="center", font_name=get_font(),
            )
            y -= 24

        # Bounty
        bounty = int(summary.get("bounty_bonus", 0))
        if bounty:
            arcade.draw_text(
                f"AUTHORITY BOUNTY: +{bounty}", cx, y, COLOR_ACCENT,
                font_size=10, anchor_x="center", font_name=get_font(),
            )
            y -= 22

        # Message
        msg = str(summary.get("message", ""))
        if msg:
            arcade.draw_text(
                msg[:90], cx, y, COLOR_TEXT_DIM, font_size=9,
                anchor_x="center", font_name=get_font(),
            )
            y -= 20

        # Prompt
        arcade.draw_text(
            "[CLICK  OR  SPACE]  TO  CONTINUE",
            cx, by + 20, (80, 80, 80, 200), font_size=9,
            anchor_x="center", font_name=get_font(),
        )

    def _draw_spec_confirm(self) -> None:
        cx = SCREEN_WIDTH // 2
        cy = SCREEN_HEIGHT // 2
        arcade.draw_lrbt_rectangle_filled(cx - 230, cx + 230, cy - 90, cy + 90, (0, 0, 0, 240))
        arcade.draw_lrbt_rectangle_outline(cx - 230, cx + 230, cy - 90, cy + 90, (255, 155, 20), 2)
        arcade.draw_text(
            "FIRE NOVA CANNON?", cx, cy + 50, (255, 155, 20),
            font_size=15, anchor_x="center", anchor_y="center",
            font_name=get_font(),
        )
        arcade.draw_text(
            "Delivers devastating damage to the target.", cx, cy + 18,
            COLOR_TEXT_DIM, font_size=10,
            anchor_x="center", anchor_y="center", font_name=get_font(),
        )
        self._btn((cx - 160, cy - 50, 140, 46), "CONFIRM", COLOR_ACCENT, 11)
        self._btn((cx + 20,  cy - 50, 140, 46), "CANCEL",  COLOR_SECONDARY, 11)

    def _btn(self, rect: tuple, label: str, color: tuple, font_size: int = 11) -> None:
        x, y, w, h = rect
        arcade.draw_lrbt_rectangle_filled(x, x + w, y, y + h, (0, 0, 0, 190))
        r, g, b = color
        arcade.draw_lrbt_rectangle_outline(x, x + w, y, y + h, (r, g, b, 210), 1)
        arcade.draw_text(
            label, x + w // 2, y + h // 2, color,
            font_size=font_size, anchor_x="center", anchor_y="center",
            font_name=get_font(),
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    def _button_rects(self) -> dict:
        """Named (x, y, w, h) rects for clickable elements."""
        bh = 54
        bot = 28
        bw_atk = 210
        bw_fle = 160
        bw_spc = 190
        gap    = 18
        total  = bw_atk + bw_fle + bw_spc + gap * 2
        start  = (SCREEN_WIDTH - 80 - total)      # right-aligned cluster
        return {
            "attack":     (start,                           bot, bw_atk, bh),
            "flee":       (start + bw_atk + gap,           bot, bw_fle, bh),
            "special":    (start + bw_atk + bw_fle + gap*2, bot, bw_spc, bh),
            "slider_hit": (_SL_X - 10, _SL_Y - 16, _SL_W + 20, 32),
        }


# ── Module-level helpers ──────────────────────────────────────────────────────

def _inr(mx: int, my: int, rect: tuple) -> bool:
    """Point-in-rect test for (x, y, w, h) tuples."""
    x, y, w, h = rect
    return x <= mx <= x + w and y <= my <= y + h


def load_ship_texture(ship_key: str, cache: dict) -> Optional[arcade.Texture]:
    """Load a ship texture by its asset key (e.g. 'fighter_player').

    Results are memoised in the supplied *cache* dict.
    """
    safe = str(ship_key or "").strip().lower()
    if safe in cache:
        return cache[safe]
    path = os.path.join("assets", "ships", f"{safe}.png")
    try:
        tex = arcade.load_texture(path)
    except Exception:
        tex = None
    cache[safe] = tex
    return tex
