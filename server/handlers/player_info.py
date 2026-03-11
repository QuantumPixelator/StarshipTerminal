"""
server/handlers/player_info.py

Handlers for basic player/planet info queries:
  get_player_info, get_config, get_current_planet_info, get_docking_fee
"""


def _as_float(value, default=None):
    try:
        return float(value)
    except Exception:
        return default


def _h_get_player_info(server, session, gm, params):
    result = gm.get_player_info()
    if isinstance(result, dict):
        data = {
            "name": result.get("name", ""),
            "credits": result.get("credits", 0),
            "ship": result.get("ship", ""),
            "location": result.get("location", ""),
            "bank_balance": result.get("bank_balance", 0),
        }
    else:
        data = {
            "name": result[0],
            "credits": result[1],
            "ship": result[2],
            "location": result[3],
            "bank_balance": result[4] if len(result) > 4 else 0,
        }
    data["player"] = server._serialize_player(gm)
    data["bribed_planets"] = list(getattr(gm, "bribed_planets", set()) or [])
    data["planet_price_penalty_multiplier"] = getattr(
        gm, "planet_price_penalty_multiplier", None
    )
    return {"success": True, "data": data}


def _h_get_config(server, session, gm, params):
    return {
        "success": True,
        "config": gm.config if isinstance(gm.config, dict) else {},
    }


def _h_get_current_planet_info(server, session, gm, params):
    result = gm.get_current_planet_info()
    if isinstance(result, dict):
        data = {
            "name": result.get("name", ""),
            "description": result.get("description", ""),
            "tech_level": result.get("tech_level", 0),
            "government": result.get("government", ""),
            "population": result.get("population", 0),
            "special_resources": result.get("special_resources", ""),
        }
    else:
        data = {
            "name": result[0],
            "description": result[1],
            "tech_level": result[2],
            "government": result[3],
            "population": result[4] if len(result) > 4 else 0,
            "special_resources": result[5] if len(result) > 5 else "",
        }
    data["planet"] = server._serialize_planet(getattr(gm, "current_planet", None))
    return {"success": True, "data": data}


def _h_get_docking_fee(server, session, gm, params):
    planet = gm.resolve_planet_from_params(params, default_current=True)
    if planet is None:
        return {"success": False, "message": "Invalid planet.", "fee": 0}
    fee = gm.get_docking_fee(planet, gm.player.spaceship)
    return {"success": True, "fee": fee}


def _h_get_winner_board(server, session, gm, params):
    board = gm.get_winner_board()
    return {"success": True, "board": board}


def _h_get_all_commander_statuses(server, session, gm, params):
    rows = gm.get_all_commander_statuses()
    return {"success": True, "commanders": rows}


def _h_get_presence_alerts(server, session, gm, params):
    since_ts = _as_float(params.get("since_ts", 0.0), default=None)
    if since_ts is None:
        return {"success": False, "alerts": [], "message": "Invalid since_ts."}
    alerts = server._get_presence_alerts_since(since_ts)
    return {"success": True, "alerts": alerts}


def _h_get_economy_alerts(server, session, gm, params):
    since_ts = _as_float(params.get("since_ts", 0.0), default=None)
    if since_ts is None:
        return {"success": False, "alerts": [], "message": "Invalid since_ts."}
    alerts = server._get_economy_alerts_since(since_ts)
    return {"success": True, "alerts": alerts}


def register():
    return {
        "get_player_info": _h_get_player_info,
        "get_config": _h_get_config,
        "get_current_planet_info": _h_get_current_planet_info,
        "get_docking_fee": _h_get_docking_fee,
        "get_winner_board": _h_get_winner_board,
        "get_all_commander_statuses": _h_get_all_commander_statuses,
        "get_presence_alerts": _h_get_presence_alerts,
        "get_economy_alerts": _h_get_economy_alerts,
    }
