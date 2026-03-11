"""
server/handlers/misc.py

Miscellaneous handlers:
  claim_abandoned_ship, get_ship_level, get_spaceships,
  _get_target_stats, _load_shared_planet_states, sync_assets
"""

import logging


logger = logging.getLogger(__name__)


def _h_claim_abandoned_ship(server, session, gm, params):
    target_name = params.get("target_name")
    claim_action = params.get("action", "LOOT")
    extras = params.get("extras")
    success, msg = gm.claim_abandoned_ship(target_name, claim_action, extras)
    return {"success": success, "message": msg}


def _h_get_ship_level(server, session, gm, params):
    ship_name = params.get("ship")
    level = gm.get_ship_level(ship_name)
    return {"success": True, "level": level}


def _h_get_spaceships(server, session, gm, params):
    ships = [
        server._serialize_ship(ship)
        for ship in list(getattr(gm, "spaceships", []) or [])
    ]
    return {"success": True, "spaceships": ships}


def _h__get_target_stats(server, session, gm, params):
    session_data = params.get("session")
    shields, defenders, integrity = gm._get_target_stats(session_data)
    return {
        "success": True,
        "shields": shields,
        "defenders": defenders,
        "integrity": integrity,
    }


def _h__load_shared_planet_states(server, session, gm, params):
    gm._load_shared_planet_states()
    return {"success": True}


def _h_sync_assets(server, session, gm, params):
    client_manifest = params.get("manifest", {})
    if not isinstance(client_manifest, dict):
        return {
            "success": False,
            "files": [],
            "deleted": [],
            "manifest": {},
            "message": "Invalid manifest payload.",
        }
    updates, deleted, manifest = server._build_asset_sync_payload(client_manifest)
    return {
        "success": True,
        "files": updates,
        "deleted": deleted,
        "manifest": manifest,
    }


def _h_get_all_planet_events(server, session, gm, params):
    """Return all active planet events as a dict keyed by planet name.

    Called once when the client enters the travel/navigation view so that
    per-planet event icons can be drawn entirely from the local cache without
    issuing one network round-trip per planet per rendered frame.
    """
    try:
        # Evict expired events first
        if hasattr(gm, "_update_planet_events"):
            gm._update_planet_events()
        events = dict(getattr(gm, "planet_events", {}) or {})
        # Sanitise: only serialisable primitives
        safe = {}
        for planet_name, evt in events.items():
            if isinstance(evt, dict):
                safe[str(planet_name)] = evt
        return {"success": True, "events": safe}
    except Exception:
        logger.exception("Failed to build all planet events snapshot")
        return {
            "success": False,
            "events": {},
            "message": "Failed to retrieve planet events.",
        }


def register():
    return {
        "claim_abandoned_ship": _h_claim_abandoned_ship,
        "get_ship_level": _h_get_ship_level,
        "get_spaceships": _h_get_spaceships,
        "_get_target_stats": _h__get_target_stats,
        "_load_shared_planet_states": _h__load_shared_planet_states,
        "sync_assets": _h_sync_assets,
        "get_all_planet_events": _h_get_all_planet_events,
    }
