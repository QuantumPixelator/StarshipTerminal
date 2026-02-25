"""
server/handlers/combat.py

Handlers for combat operations:
  get_orbit_targets, start_combat_session, resolve_combat_round,
  flee_combat_session, should_initialize_planet_auto_combat
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from logging_config import (
    get_combat_logger,
    log_special_weapon_usage,
    log_cooldown_check,
    handle_errors,
)


def _h_get_orbit_targets(server, session, gm, params):
    targets = gm.get_orbit_targets()
    serialized_targets = []
    for target in list(targets or []):
        target_type = str(target.get("type", "")).upper()
        if target_type == "NPC":
            npc_obj = target.get("obj")
            npc_info = {}
            if npc_obj is not None and hasattr(npc_obj, "get_info"):
                try:
                    npc_info = dict(npc_obj.get_info() or {})
                except Exception:
                    npc_info = {}
            npc_name = str(
                target.get("name")
                or npc_info.get("name")
                or getattr(npc_obj, "name", "Unknown")
            )
            npc_personality = str(
                target.get("personality")
                or npc_info.get("personality")
                or getattr(npc_obj, "personality", "neutral")
            )
            serialized_targets.append(
                {
                    "type": "NPC",
                    "name": npc_name,
                    "remark": str(target.get("remark", "...")),
                    "personality": npc_personality,
                    "raw_data": {"player": npc_info},
                }
            )
            continue
        serialized_targets.append(target)
    return {"success": True, "targets": serialized_targets}


def _h_start_combat_session(server, session, gm, params):
    target = params.get("target")
    started, msg, combat_session = gm.start_combat_session(target)
    gm.record_analytics_event(
        category="combat",
        event_name="combat_start",
        success=bool(started),
        metadata={"target": str(target)},
    )
    return {
        "success": bool(started),
        "message": str(msg),
        "session": combat_session,
    }


def _h_resolve_combat_round(server, session, gm, params):
    session_data = params.get("session")
    player_committed = int(params.get("player_committed", 0))
    success, msg, combat_session = gm.resolve_combat_round(
        session_data, player_committed
    )
    gm.record_analytics_event(
        category="combat",
        event_name="combat_round",
        success=bool(success),
        value=float(player_committed),
    )
    return {
        "success": bool(success),
        "message": str(msg),
        "session": combat_session,
    }


def _h_flee_combat_session(server, session, gm, params):
    session_data = params.get("session")
    gm.flee_combat_session(session_data)
    gm.record_analytics_event(
        category="combat",
        event_name="combat_flee",
        success=True,
    )
    return {"success": True}


def _h_should_initialize_planet_auto_combat(server, session, gm, params):
    planet = params.get("planet")
    triggered, msg = gm.should_initialize_planet_auto_combat(planet)
    return {"success": True, "triggered": triggered, "message": msg}


def _h_fire_special_weapon(server, session, gm, params):
    """Handler for firing special weapons with error handling and logging."""
    try:
        combat_session = params.get("session")
        player_name = getattr(gm.player, "name", "Unknown")
        weapon_name = getattr(gm.player.spaceship, "special_weapon", None)

        if not weapon_name:
            logger = get_combat_logger()
            logger.warning(f"[{player_name}] Attempted to fire special weapon but none equipped")
            return {
                "success": False,
                "message": "No special weapon equipped",
                "result": {},
                "session": combat_session,
            }

        success, msg, result = gm.fire_special_weapon(combat_session)
        gm.record_analytics_event(
            category="combat",
            event_name="combat_special_weapon",
            success=bool(success),
            metadata={"weapon": str(weapon_name or "")},
        )

        # Log the special weapon usage
        log_special_weapon_usage(player_name, weapon_name, success, result)

        return {
            "success": bool(success),
            "message": str(msg),
            "result": result if result else {},
            "session": combat_session,
        }
    except Exception as e:
        logger = get_combat_logger()
        logger.error(
            f"Error firing special weapon: {str(e)}", exc_info=True
        )
        return {
            "success": False,
            "message": "Failed to fire special weapon",
            "error": str(e),
            "result": {},
            "session": params.get("session"),
        }


def _h_get_special_weapon_status(server, session, gm, params):
    """Return cooldown status and whether special weapons are enabled."""
    import time

    try:
        player_name = getattr(gm.player, "name", "Unknown")
        enabled = bool(gm.config.get("enable_special_weapons", True))
        weapon_name = getattr(gm.player.spaceship, "special_weapon", None)
        cooldown_hours = float(gm.config.get("combat_special_weapon_cooldown_hours", 36.0))
        last_used = float(getattr(gm.player, "last_special_weapon_time", 0.0))
        now = time.time()
        elapsed_hours = (now - last_used) / 3600.0
        on_cooldown = elapsed_hours < cooldown_hours
        remaining_hours = max(0.0, cooldown_hours - elapsed_hours)

        # Log cooldown check
        if weapon_name:
            feature_name = f"Special weapon ({weapon_name})"
            log_cooldown_check(player_name, feature_name, remaining_hours * 3600)

        return {
            "success": True,
            "enabled": enabled,
            "weapon_name": weapon_name,
            "on_cooldown": on_cooldown,
            "remaining_hours": round(remaining_hours, 2),
            "cooldown_hours": cooldown_hours,
        }
    except Exception as e:
        logger = get_combat_logger()
        logger.error(
            f"Error getting special weapon status: {str(e)}", exc_info=True
        )
        return {
            "success": False,
            "message": "Failed to get special weapon status",
            "error": str(e),
        }


def register():
    return {
        "get_orbit_targets": _h_get_orbit_targets,
        "start_combat_session": _h_start_combat_session,
        "resolve_combat_round": _h_resolve_combat_round,
        "flee_combat_session": _h_flee_combat_session,
        "should_initialize_planet_auto_combat": _h_should_initialize_planet_auto_combat,
        "fire_special_weapon": _h_fire_special_weapon,
        "get_special_weapon_status": _h_get_special_weapon_status,
    }
