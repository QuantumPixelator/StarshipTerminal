"""
server/handlers/ship_ops.py

Handlers for ship operations:
  buy_fuel, get_refuel_quote, repair_hull, buy_ship,
  transfer_fighters, transfer_shields, check_auto_refuel,
  install_ship_upgrade (modules)
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from logging_config import get_module_logger_subsystem, log_module_installation


def _h_buy_fuel(server, session, gm, params):
    amount = params.get("amount", 10)
    success, msg = gm.buy_fuel(amount)
    gm.record_analytics_event(
        category="ship",
        event_name="buy_fuel",
        success=bool(success),
        value=float(amount or 0),
    )
    if success:
        return {
            "success": True,
            "message": str(msg),
            "credits": gm.player.credits,
            "fuel": gm.player.spaceship.fuel,
            "last_refuel_time": gm.player.spaceship.last_refuel_time,
        }
    return {"success": False, "error": str(msg)}


def _h_get_refuel_quote(server, session, gm, params):
    quote = gm.get_refuel_quote()
    return {"success": True, "quote": quote}


def _h_repair_hull(server, session, gm, params):
    success, msg = gm.repair_hull()
    gm.record_analytics_event(
        category="ship",
        event_name="repair_hull",
        success=bool(success),
    )
    return {
        "success": success,
        "message": msg,
        "credits": gm.player.credits if success else None,
        "hull_integrity": gm.player.spaceship.integrity if success else None,
    }


def _h_buy_ship(server, session, gm, params):
    ship_name = params.get("ship")
    catalog_ship = next(
        (
            s
            for s in list(getattr(gm, "spaceships", []) or [])
            if getattr(s, "model", None) == ship_name
        ),
        None,
    )
    if catalog_ship is None:
        gm.record_analytics_event(
            category="ship",
            event_name="buy_ship",
            success=False,
            metadata={"ship": str(ship_name or "")},
        )
        return {
            "success": False,
            "message": f"Ship model '{ship_name}' not found in catalog.",
        }
    success, msg = gm.buy_ship(catalog_ship)
    gm.record_analytics_event(
        category="ship",
        event_name="buy_ship",
        success=bool(success),
        metadata={"ship": str(ship_name or "")},
    )
    return {
        "success": success,
        "message": msg,
        "credits": gm.player.credits if success else None,
        "ship": gm.player.spaceship if success else None,
    }


def _h_transfer_fighters(server, session, gm, params):
    action_type = params.get("action")
    quantity = params.get("quantity", 1)
    success, msg = gm.transfer_fighters(quantity, action_type)
    gm.record_analytics_event(
        category="ship",
        event_name="transfer_fighters",
        success=bool(success),
        value=float(quantity or 0),
        metadata={"action": str(action_type or "")},
    )
    return {"success": success, "message": msg}


def _h_transfer_shields(server, session, gm, params):
    action_type = params.get("action")
    quantity = params.get("quantity", 1)
    success, msg = gm.transfer_shields(quantity, action_type)
    gm.record_analytics_event(
        category="ship",
        event_name="transfer_shields",
        success=bool(success),
        value=float(quantity or 0),
        metadata={"action": str(action_type or "")},
    )
    return {"success": success, "message": msg}


def _h_check_auto_refuel(server, session, gm, params):
    gm.check_auto_refuel()
    return {"success": True}


def _h_install_ship_upgrade(server, session, gm, params):
    """Install a ship upgrade (module, weapon, etc.) with error handling and logging."""
    try:
        item_name = params.get("item_name")
        quantity = params.get("quantity", 1)
        player_name = getattr(gm.player, "name", "Unknown")
        ship_model = getattr(gm.player.spaceship, "model", "Unknown")

        # Validate module name (common modules)
        valid_modules = {"scanner", "jammer", "cargo_optimizer"}
        is_module = item_name.lower() in valid_modules

        success, msg = gm.install_ship_upgrade(item_name, quantity)
        gm.record_analytics_event(
            category="ship",
            event_name="install_ship_upgrade",
            success=bool(success),
            value=float(quantity or 1),
            metadata={"item": str(item_name or "")},
        )

        # Log module installation if applicable
        if is_module:
            log_module_installation(
                player_name, ship_model, [item_name], success
            )
        
        # Log any errors
        if not success:
            logger = get_module_logger_subsystem()
            logger.warning(
                f"[{player_name}] Failed to install upgrade '{item_name}': {msg}"
            )

        return {
            "success": success,
            "message": msg,
            "ship": gm.player.spaceship if success else None,
            "inventory": gm.player.inventory if success else None,
        }
    except Exception as e:
        logger = get_module_logger_subsystem()
        logger.error(
            f"Error installing ship upgrade: {str(e)}", exc_info=True
        )
        return {
            "success": False,
            "message": "Failed to install upgrade",
            "error": str(e),
        }


def register():
    return {
        "buy_fuel": _h_buy_fuel,
        "get_refuel_quote": _h_get_refuel_quote,
        "repair_hull": _h_repair_hull,
        "buy_ship": _h_buy_ship,
        "transfer_fighters": _h_transfer_fighters,
        "transfer_shields": _h_transfer_shields,
        "check_auto_refuel": _h_check_auto_refuel,
        "install_ship_upgrade": _h_install_ship_upgrade,
    }
