"""
server/handlers/navigation.py

Handlers for travel and navigation:
  warp_to_planet, get_known_planets, get_planets, travel_to_planet,
  roll_travel_event_payload, resolve_travel_event_payload
"""


def _h_warp_to_planet(server, session, gm, params):
    planet_name = params.get("planet_name")
    success, msg = gm.warp_to_planet(planet_name)
    gm.record_analytics_event(
        category="navigation",
        event_name="warp_to_planet",
        success=bool(success),
        metadata={"planet": str(planet_name or "")},
    )
    return {"success": success, "message": msg}


def _h_get_known_planets(server, session, gm, params):
    planets = [
        (p.name, p.x, p.y, p.tech_level, p.government)
        for p in gm.known_planets
    ]
    return {"success": True, "planets": planets}


def _h_get_planets(server, session, gm, params):
    planets = [
        server._serialize_planet(p)
        for p in list(getattr(gm, "planets", []) or [])
    ]
    return {"success": True, "planets": planets}


def _h_travel_to_planet(server, session, gm, params):
    target_idx = params.get("target_planet_index")
    skip_travel_event = bool(params.get("skip_travel_event", False))
    travel_event_message = params.get("travel_event_message")
    success, msg = gm.travel_to_planet(
        target_idx,
        skip_travel_event=skip_travel_event,
        travel_event_message=travel_event_message,
    )
    gm.record_analytics_event(
        category="navigation",
        event_name="travel_to_planet",
        success=bool(success),
        metadata={"target_index": target_idx},
    )
    return {"success": bool(success), "message": str(msg)}


def _h_roll_travel_event_payload(server, session, gm, params):
    planet_name = params.get("planet_name")
    dist = float(params.get("dist", 0.0))
    target_planet = None
    for p in list(getattr(gm, "planets", []) or []):
        if getattr(p, "name", "") == planet_name:
            target_planet = p
            break
    payload = (
        gm.roll_travel_event_payload(target_planet, dist)
        if target_planet
        else None
    )
    return {"success": True, "payload": payload}


def _h_resolve_travel_event_payload(server, session, gm, params):
    event_payload = params.get("event_payload")
    choice = params.get("choice", "AUTO")
    result_line = gm.resolve_travel_event_payload(event_payload, choice)
    gm.record_analytics_event(
        category="navigation",
        event_name="resolve_travel_event",
        success=True,
        metadata={"choice": str(choice or "AUTO")},
    )
    return {"success": True, "result_line": str(result_line)}


def register():
    return {
        "warp_to_planet": _h_warp_to_planet,
        "get_known_planets": _h_get_known_planets,
        "get_planets": _h_get_planets,
        "travel_to_planet": _h_travel_to_planet,
        "roll_travel_event_payload": _h_roll_travel_event_payload,
        "resolve_travel_event_payload": _h_resolve_travel_event_payload,
    }
