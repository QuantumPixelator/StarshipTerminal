"""
server/handlers/player_info.py

Handlers for basic player/planet info queries:
  get_player_info, get_config, get_current_planet_info, get_docking_fee
"""


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
    planet_name = params.get("planet_name") or gm.current_planet.name
    planet_pool = list(getattr(gm, "known_planets", []) or [])
    if not planet_pool:
        planet_pool = list(getattr(gm, "planets", []) or [])
    planet = next(
        (p for p in planet_pool if p.name == planet_name),
        gm.current_planet,
    )
    fee = gm.get_docking_fee(planet, gm.player.spaceship)
    return {"success": True, "fee": fee}


def _h_get_winner_board(server, session, gm, params):
    board = gm.get_winner_board()
    return {"success": True, "board": board}


def _h_get_all_commander_statuses(server, session, gm, params):
    rows = gm.get_all_commander_statuses()
    return {"success": True, "commanders": rows}


def register():
    return {
        "get_player_info": _h_get_player_info,
        "get_config": _h_get_config,
        "get_current_planet_info": _h_get_current_planet_info,
        "get_docking_fee": _h_get_docking_fee,
        "get_winner_board": _h_get_winner_board,
        "get_all_commander_statuses": _h_get_all_commander_statuses,
    }
