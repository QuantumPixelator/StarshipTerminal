"""
server/handlers/economy.py

Handlers for trading, market data, contraband, and contracts:
  trade_item, buy_item, sell_item, jettison_cargo,
  get_market_sell_price, get_effective_buy_price, get_item_market_snapshot,
  get_best_trade_opportunities, get_bribe_market_snapshot,
  get_contraband_market_context, get_smuggling_item_names,
  check_contraband_detection, bribe_npc, sell_non_market_cargo,
  get_active_trade_contract, reroll_trade_contract
"""


def _h_trade_item(server, session, gm, params):
    item_name = params.get("item_name")
    trade_action = params.get("action")
    quantity = params.get("quantity", 1)
    success, msg = gm.trade_item(item_name, trade_action, quantity)
    gm.record_analytics_event(
        category="economy",
        event_name=f"trade_{str(trade_action or '').strip().lower()}",
        success=bool(success),
        value=float(quantity or 1),
        metadata={"item": str(item_name or "")},
    )
    return {
        "success": success,
        "message": msg,
        "credits": gm.player.credits,
        "cargo": list((gm.player.inventory or {}).items()),
    }


def _h_buy_item(server, session, gm, params):
    item_name = params.get("item")
    quantity = params.get("quantity", 1)
    result = gm.trade_item(item_name, "BUY", quantity)
    gm.record_analytics_event(
        category="economy",
        event_name="economy_buy",
        success=bool(result[0]),
        value=float(quantity or 1),
        metadata={"item": str(item_name or "")},
    )
    return {
        "success": result[0],
        "message": result[1],
        "credits": gm.player.credits,
        "cargo": list((gm.player.inventory or {}).items()),
    }


def _h_sell_item(server, session, gm, params):
    item_name = params.get("item")
    quantity = params.get("quantity", 1)
    result = gm.trade_item(item_name, "SELL", quantity)
    gm.record_analytics_event(
        category="economy",
        event_name="economy_sell",
        success=bool(result[0]),
        value=float(quantity or 1),
        metadata={"item": str(item_name or "")},
    )
    return {
        "success": result[0],
        "message": result[1],
        "credits": gm.player.credits,
        "cargo": list((gm.player.inventory or {}).items()),
    }


def _h_jettison_cargo(server, session, gm, params):
    item_name = str(params.get("item", "")).strip()
    qty_in_hold = int((gm.player.inventory or {}).get(item_name, 0))
    if not item_name or qty_in_hold <= 0:
        gm.record_analytics_event(
            category="economy",
            event_name="cargo_jettison",
            success=False,
            metadata={"item": str(item_name or "")},
        )
        return {"success": False, "message": "Item not found in cargo hold."}
    gm.player.inventory[item_name] = qty_in_hold - 1
    if gm.player.inventory[item_name] <= 0:
        del gm.player.inventory[item_name]
    cargo_used = sum(gm.player.inventory.values())
    cargo_max = int(gm.player.spaceship.current_cargo_pods)
    gm.record_analytics_event(
        category="economy",
        event_name="cargo_jettison",
        success=True,
        value=1,
        metadata={"item": item_name},
    )
    return {
        "success": True,
        "message": f"1 unit of {item_name} jettisoned. Cargo: {cargo_used}/{cargo_max}.",
        "cargo": list((gm.player.inventory or {}).items()),
    }


def _h_get_market_sell_price(server, session, gm, params):
    item_name = params.get("item")
    planet_name = params.get("planet_name") or gm.current_planet.name
    price = gm.get_market_sell_price(item_name, planet_name)
    return {"success": True, "price": price}


def _h_get_effective_buy_price(server, session, gm, params):
    item_name = params.get("item")
    base_price = params.get("base_price")
    planet_name = params.get("planet_name") or gm.current_planet.name
    price = gm.get_effective_buy_price(item_name, base_price, planet_name)
    return {"success": True, "price": price}


def _h_get_item_market_snapshot(server, session, gm, params):
    item_name = params.get("item")
    snapshot = gm.get_item_market_snapshot(item_name)
    return {"success": True, "data": snapshot}


def _h_get_best_trade_opportunities(server, session, gm, params):
    from_planet = params.get("from_planet") or gm.current_planet.name
    limit = params.get("limit", 5)
    routes = gm.get_best_trade_opportunities(from_planet, limit)
    return {"success": True, "routes": routes}


def _h_get_bribe_market_snapshot(server, session, gm, params):
    planet_name = params.get("planet_name") or gm.current_planet.name
    snapshot = gm.get_bribe_market_snapshot(planet_name)
    return {"success": True, "data": snapshot}


def _h_get_contraband_market_context(server, session, gm, params):
    item_name = params.get("item")
    planet_name = params.get("planet_name") or gm.current_planet.name
    quantity = int(params.get("quantity", 1) or 1)
    context = gm.get_contraband_market_context(item_name, planet_name, quantity)
    return {"success": True, "data": context}


def _h_get_smuggling_item_names(server, session, gm, params):
    items = gm.get_smuggling_item_names()
    return {"success": True, "items": items}


def _h_check_contraband_detection(server, session, gm, params):
    detected, msg = gm.check_contraband_detection()
    return {"success": True, "detected": detected, "message": msg}


def _h_bribe_npc(server, session, gm, params):
    success, msg = gm.bribe_npc()
    gm.record_analytics_event(
        category="economy",
        event_name="bribe_npc",
        success=bool(success),
    )
    return {"success": success, "message": msg}


def _h_sell_non_market_cargo(server, session, gm, params):
    success, msg = gm.sell_non_market_cargo()
    gm.record_analytics_event(
        category="economy",
        event_name="sell_non_market_cargo",
        success=bool(success),
    )
    return {"success": success, "message": msg}


def _h_get_active_trade_contract(server, session, gm, params):
    contract = gm.get_active_trade_contract()
    return {"success": True, "contract": contract}


def _h_reroll_trade_contract(server, session, gm, params):
    success, msg = gm.reroll_trade_contract()
    gm.record_analytics_event(
        category="economy",
        event_name="reroll_trade_contract",
        success=bool(success),
    )
    return {"success": success, "message": msg}


def register():
    return {
        "trade_item": _h_trade_item,
        "buy_item": _h_buy_item,
        "sell_item": _h_sell_item,
        "jettison_cargo": _h_jettison_cargo,
        "get_market_sell_price": _h_get_market_sell_price,
        "get_effective_buy_price": _h_get_effective_buy_price,
        "get_item_market_snapshot": _h_get_item_market_snapshot,
        "get_best_trade_opportunities": _h_get_best_trade_opportunities,
        "get_bribe_market_snapshot": _h_get_bribe_market_snapshot,
        "get_contraband_market_context": _h_get_contraband_market_context,
        "get_smuggling_item_names": _h_get_smuggling_item_names,
        "check_contraband_detection": _h_check_contraband_detection,
        "bribe_npc": _h_bribe_npc,
        "sell_non_market_cargo": _h_sell_non_market_cargo,
        "get_active_trade_contract": _h_get_active_trade_contract,
        "reroll_trade_contract": _h_reroll_trade_contract,
    }
