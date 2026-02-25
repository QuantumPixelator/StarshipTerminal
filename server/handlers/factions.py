"""
server/handlers/factions.py

Handlers for faction standings, planet events, and commander stipend:
  get_authority_standing_label, get_frontier_standing_label,
  _get_authority_standing, _get_frontier_standing,
  _adjust_authority_standing, _adjust_frontier_standing,
  check_barred, bar_player, get_planet_event,
  is_planet_hostile_market, get_planet_price_penalty_seconds_remaining,
  get_current_port_spotlight_deal, process_conquered_planet_defense_regen,
  process_commander_stipend
"""


def _h_get_authority_standing_label(server, session, gm, params):
    label = gm.get_authority_standing_label()
    return {"success": True, "label": label}


def _h_get_frontier_standing_label(server, session, gm, params):
    label = gm.get_frontier_standing_label()
    return {"success": True, "label": label}


def _h__get_authority_standing(server, session, gm, params):
    value = gm._get_authority_standing()
    return {"success": True, "value": int(value)}


def _h__get_frontier_standing(server, session, gm, params):
    value = gm._get_frontier_standing()
    return {"success": True, "value": int(value)}


def _h__adjust_authority_standing(server, session, gm, params):
    delta = int(params.get("delta", 0))
    value = gm._adjust_authority_standing(delta)
    return {"success": True, "value": int(value)}


def _h__adjust_frontier_standing(server, session, gm, params):
    delta = int(params.get("delta", 0))
    value = gm._adjust_frontier_standing(delta)
    return {"success": True, "value": int(value)}


def _h_check_barred(server, session, gm, params):
    planet_name = params.get("planet_name") or gm.current_planet.name
    is_barred, msg = gm.check_barred(planet_name)
    return {"success": True, "is_barred": is_barred, "message": msg}


def _h_bar_player(server, session, gm, params):
    planet_name = params.get("planet_name")
    gm.bar_player(planet_name)
    return {"success": True}


def _h_get_planet_event(server, session, gm, params):
    planet_name = params.get("planet_name")
    event = gm.get_planet_event(planet_name)
    return {"success": True, "event": event}


def _h_is_planet_hostile_market(server, session, gm, params):
    planet_name = params.get("planet_name")
    is_hostile = gm.is_planet_hostile_market(planet_name)
    return {"success": True, "is_hostile": is_hostile}


def _h_get_planet_price_penalty_seconds_remaining(server, session, gm, params):
    planet_name = params.get("planet_name")
    seconds = gm.get_planet_price_penalty_seconds_remaining(planet_name)
    return {"success": True, "seconds": seconds}


def _h_get_current_port_spotlight_deal(server, session, gm, params):
    deal = gm.get_current_port_spotlight_deal()
    return {"success": True, "deal": deal}


def _h_process_conquered_planet_defense_regen(server, session, gm, params):
    success, msg = gm.process_conquered_planet_defense_regen()
    return {"success": success, "message": msg}


def _h_process_commander_stipend(server, session, gm, params):
    success, msg = gm.process_commander_stipend()
    return {"success": success, "message": msg}


def register():
    return {
        "get_authority_standing_label": _h_get_authority_standing_label,
        "get_frontier_standing_label": _h_get_frontier_standing_label,
        "_get_authority_standing": _h__get_authority_standing,
        "_get_frontier_standing": _h__get_frontier_standing,
        "_adjust_authority_standing": _h__adjust_authority_standing,
        "_adjust_frontier_standing": _h__adjust_frontier_standing,
        "check_barred": _h_check_barred,
        "bar_player": _h_bar_player,
        "get_planet_event": _h_get_planet_event,
        "is_planet_hostile_market": _h_is_planet_hostile_market,
        "get_planet_price_penalty_seconds_remaining": _h_get_planet_price_penalty_seconds_remaining,
        "get_current_port_spotlight_deal": _h_get_current_port_spotlight_deal,
        "process_conquered_planet_defense_regen": _h_process_conquered_planet_defense_regen,
        "process_commander_stipend": _h_process_commander_stipend,
    }
