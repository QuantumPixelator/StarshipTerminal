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

import time
import random


def _as_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return int(default)


def _require_non_empty_text(value, field_name):
    text = str(value or "").strip()
    if not text:
        return None, f"Invalid {field_name}."
    return text, None


def _resource_offer_queue(server):
    if getattr(server, "store", None) is None:
        return []
    offers = server.store.get_kv("shared", "resource_trade_offers", default=[])
    return list(offers) if isinstance(offers, list) else []


def _save_resource_offer_queue(server, offers):
    if getattr(server, "store", None) is None:
        return
    trimmed = list(offers or [])[-500:]
    server.store.set_kv("shared", "resource_trade_offers", trimmed)


def _resolve_player_id_by_name(server, player_name):
    if getattr(server, "store", None) is None:
        return None
    refs = server.store.find_character_refs_by_name(player_name, active_only=False)
    if not refs:
        return None
    first = dict(refs[0] or {})
    account_name = str(first.get("account_name") or "").strip()
    character_name = str(first.get("character_name") or "").strip()
    if not account_name or not character_name:
        return None
    return server.store.get_character_player_id(account_name, character_name)


def _h_trade_item(server, session, gm, params):
    item_name, err = _require_non_empty_text(params.get("item_name"), "item_name")
    if err:
        return {"success": False, "message": err}

    trade_action = str(params.get("action") or "").strip().upper()
    if trade_action not in {"BUY", "SELL"}:
        return {"success": False, "message": "Invalid action."}

    quantity = max(1, _as_int(params.get("quantity", 1), default=1))
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
    item_name, err = _require_non_empty_text(params.get("item"), "item")
    if err:
        return {"success": False, "message": err}
    quantity = max(1, _as_int(params.get("quantity", 1), default=1))
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
    item_name, err = _require_non_empty_text(params.get("item"), "item")
    if err:
        return {"success": False, "message": err}
    quantity = max(1, _as_int(params.get("quantity", 1), default=1))
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
    planet = gm.resolve_planet_from_params(params, default_current=True)
    planet_name = getattr(planet, "name", None)
    price = gm.get_market_sell_price(item_name, planet_name)
    return {"success": True, "price": price}


def _h_get_effective_buy_price(server, session, gm, params):
    item_name, err = _require_non_empty_text(params.get("item"), "item")
    if err:
        return {"success": False, "message": err}
    base_price = params.get("base_price")
    try:
        base_price = float(base_price)
    except Exception:
        return {"success": False, "message": "Invalid base_price."}
    planet = gm.resolve_planet_from_params(params, default_current=True)
    planet_name = getattr(planet, "name", None)
    price = gm.get_effective_buy_price(item_name, base_price, planet_name)
    return {"success": True, "price": price}


def _h_get_item_market_snapshot(server, session, gm, params):
    item_name, err = _require_non_empty_text(params.get("item"), "item")
    if err:
        return {"success": False, "message": err}
    snapshot = gm.get_item_market_snapshot(item_name)
    return {"success": True, "data": snapshot}


def _h_get_best_trade_opportunities(server, session, gm, params):
    from_planet = params.get("from_planet") or gm.current_planet.name
    from_planet_obj = gm.get_planet_by_id(from_planet) or gm.get_planet_by_name(from_planet)
    if from_planet_obj:
        from_planet = from_planet_obj.name
    limit = max(1, min(50, _as_int(params.get("limit", 5), default=5)))
    routes = gm.get_best_trade_opportunities(from_planet, limit)
    return {"success": True, "routes": routes}


def _h_get_bribe_market_snapshot(server, session, gm, params):
    planet = gm.resolve_planet_from_params(params, default_current=True)
    snapshot = gm.get_bribe_market_snapshot(getattr(planet, "planet_id", None))
    return {"success": True, "data": snapshot}


def _h_get_contraband_market_context(server, session, gm, params):
    item_name, err = _require_non_empty_text(params.get("item"), "item")
    if err:
        return {"success": False, "message": err}
    planet = gm.resolve_planet_from_params(params, default_current=True)
    planet_name = getattr(planet, "name", None)
    quantity = max(1, _as_int(params.get("quantity", 1), default=1))
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


def _h_get_planet_market_prices(server, session, gm, params):
    """Return buy and sell prices for all items at a planet in one response.

    This replaces the pattern of calling get_effective_buy_price / get_market_sell_price
    once per item, which caused 20+ sequential network round-trips every time the
    player opened the market tab.
    """
    planet_name = params.get("planet_name") or gm.current_planet.name
    planet = next(
        (p for p in (getattr(gm, "planets", []) or []) if p.name == planet_name),
        gm.current_planet,
    )
    if not planet:
        return {"success": False, "message": "Planet not found"}

    prices = {}

    # Standard market items
    for item_name, base_price in dict(getattr(planet, "items", {}) or {}).items():
        try:
            buy_price = gm.get_effective_buy_price(item_name, base_price, planet_name)
            sell_price = gm.get_market_sell_price(item_name, planet_name)
            prices[item_name] = {"buy": int(buy_price), "sell": int(sell_price)}
        except Exception:
            pass

    # Smuggling / contraband items
    for item_name, data in dict(getattr(planet, "smuggling_inventory", {}) or {}).items():
        if item_name in prices:
            continue
        try:
            smuggle_base = int(data.get("price") or 0)
            if smuggle_base <= 0:
                continue
            buy_price = gm.get_effective_buy_price(item_name, smuggle_base, planet_name)
            sell_price = gm.get_market_sell_price(item_name, planet_name)
            prices[item_name] = {"buy": int(buy_price), "sell": int(sell_price)}
        except Exception:
            pass

    return {"success": True, "prices": prices, "planet": planet_name}


def _h_get_resource_snapshot(server, session, gm, params):
    snapshot = gm.get_resource_snapshot()
    return {"success": True, "data": snapshot}


def _h_trade_planet_resource(server, session, gm, params):
    resource_type = params.get("resource_type")
    trade_action = params.get("action")
    amount = int(params.get("amount", 1) or 1)
    planet = gm.resolve_planet_from_params(params, default_current=True)
    planet_id = int(getattr(planet, "planet_id", 0) or 0)
    player_id = gm._active_player_id() if hasattr(gm, "_active_player_id") else None
    success, msg = gm.trade_with_planet(
        player_id,
        planet_id,
        trade_action,
        resource_type,
        amount,
    )
    gm.record_analytics_event(
        category="economy",
        event_name=f"resource_trade_{str(trade_action or '').lower()}",
        success=bool(success),
        value=float(max(1, amount)),
        metadata={"resource": str(resource_type or "")},
    )
    if success:
        try:
            server._append_economy_alert(
                getattr(getattr(gm, "player", None), "name", ""),
                f"resource_trade_{str(trade_action or '').lower()}",
                str(msg),
                resource_type=str(resource_type or "").lower(),
            )
        except Exception:
            pass
    return {
        "success": bool(success),
        "message": str(msg),
        "data": gm.get_resource_snapshot(),
    }


def _h_refuel_ship_resource(server, session, gm, params):
    amount = int(params.get("amount", 0) or 0)
    ship_id = params.get("ship_id")
    planet = gm.resolve_planet_from_params(params, default_current=True)
    planet_id = int(getattr(planet, "planet_id", 0) or 0)
    success, msg = gm.refuel_ship(ship_id=ship_id, planet_id=planet_id, amount=amount)
    gm.record_analytics_event(
        category="economy",
        event_name="resource_refuel",
        success=bool(success),
        value=float(max(1, amount or 1)),
    )
    if success:
        try:
            server._append_economy_alert(
                getattr(getattr(gm, "player", None), "name", ""),
                "resource_refuel",
                str(msg),
                resource_type="fuel",
            )
        except Exception:
            pass
    return {
        "success": bool(success),
        "message": str(msg),
        "data": gm.get_resource_snapshot(),
    }


def _h_player_trade_offer(server, session, gm, params):
    to_player = str(params.get("to_player") or "").strip()
    offer = dict(params.get("offer") or {})
    request = dict(params.get("request") or {})
    recipient_session = server._find_online_session_by_player_name(to_player)
    if not recipient_session or not getattr(recipient_session, "gm", None):
        return {"success": False, "message": "TARGET COMMANDER OFFLINE."}

    success, msg = gm.player_trade_offer(
        getattr(gm.player, "name", ""),
        recipient_session.gm,
        offer,
        request,
    )

    if success:
        try:
            recipient_session.gm.save_game()
            recipient_session.gm.flush_pending_save(force=True)
        except Exception:
            pass
        try:
            server._append_economy_alert(
                getattr(getattr(gm, "player", None), "name", ""),
                "player_trade",
                str(msg),
            )
        except Exception:
            pass

    return {"success": bool(success), "message": str(msg)}


def _h_create_resource_trade_offer(server, session, gm, params):
    to_player = str(params.get("to_player") or "").strip()
    offer = dict(params.get("offer") or {})
    request = dict(params.get("request") or {})
    from_player = str(getattr(getattr(gm, "player", None), "name", "") or "").strip()

    if not from_player or not to_player:
        return {"success": False, "message": "INVALID TRADE OFFER PARTICIPANTS."}
    if from_player.lower() == to_player.lower():
        return {"success": False, "message": "CANNOT SEND TRADE OFFER TO YOURSELF."}

    offer_resource = str(offer.get("resource") or "").strip().lower()
    request_resource = str(request.get("resource") or "").strip().lower()
    offer_amount = int(max(1, offer.get("amount") or 0))
    request_amount = int(max(1, request.get("amount") or 0))
    valid_resources = set(getattr(gm, "RESOURCE_TYPES", ("fuel", "ore", "tech", "bio", "rare")))
    if offer_resource not in valid_resources or request_resource not in valid_resources:
        return {"success": False, "message": "INVALID RESOURCE TYPES IN OFFER."}

    from_player_id = _resolve_player_id_by_name(server, from_player)
    if from_player_id is None:
        return {"success": False, "message": "UNABLE TO RESOLVE OFFERING COMMANDER."}

    available_offer = int(gm.store.get_player_resource_amount(from_player_id, offer_resource))
    if available_offer < offer_amount:
        return {"success": False, "message": "INSUFFICIENT RESOURCE FOR OFFER."}

    offers = _resource_offer_queue(server)
    offer_id = int(time.time() * 1000) + int(random.randint(1, 999))
    offers.append(
        {
            "id": int(offer_id),
            "created_at": float(time.time()),
            "from_player": from_player,
            "to_player": to_player,
            "offer": {"resource": offer_resource, "amount": int(offer_amount)},
            "request": {"resource": request_resource, "amount": int(request_amount)},
            "status": "pending",
        }
    )
    _save_resource_offer_queue(server, offers)
    try:
        server._append_economy_alert(
            from_player,
            "resource_trade_offer_created",
            f"TRADE OFFER SENT TO {to_player}: {offer_amount} {offer_resource.upper()} FOR {request_amount} {request_resource.upper()}.",
            resource_type=offer_resource,
        )
    except Exception:
        pass
    return {"success": True, "message": "RESOURCE TRADE OFFER SENT.", "offer_id": int(offer_id)}


def _h_get_resource_trade_offers(server, session, gm, params):
    player_name = str(getattr(getattr(gm, "player", None), "name", "") or "").strip().lower()
    if not player_name:
        return {"success": True, "offers": []}
    offers = _resource_offer_queue(server)
    pending = []
    for entry in offers:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("status") or "").strip().lower() != "pending":
            continue
        to_player = str(entry.get("to_player") or "").strip().lower()
        if to_player != player_name:
            continue
        pending.append(dict(entry))
    pending.sort(key=lambda item: float(item.get("created_at", 0.0) or 0.0), reverse=True)
    return {"success": True, "offers": pending[:25]}


def _h_respond_resource_trade_offer(server, session, gm, params):
    offer_id = int(params.get("offer_id", 0) or 0)
    decision = str(params.get("decision") or "").strip().lower()
    player_name = str(getattr(getattr(gm, "player", None), "name", "") or "").strip()
    if offer_id <= 0 or decision not in {"accept", "reject"}:
        return {"success": False, "message": "INVALID TRADE OFFER RESPONSE."}

    offers = _resource_offer_queue(server)
    target = None
    for entry in offers:
        if not isinstance(entry, dict):
            continue
        if int(entry.get("id", 0) or 0) != offer_id:
            continue
        if str(entry.get("status") or "").strip().lower() != "pending":
            continue
        if str(entry.get("to_player") or "").strip().lower() != player_name.lower():
            continue
        target = entry
        break

    if not target:
        return {"success": False, "message": "TRADE OFFER NOT FOUND."}

    if decision == "reject":
        target["status"] = "rejected"
        target["resolved_at"] = float(time.time())
        _save_resource_offer_queue(server, offers)
        try:
            server._append_economy_alert(
                player_name,
                "resource_trade_offer_rejected",
                f"TRADE OFFER #{offer_id} REJECTED.",
            )
        except Exception:
            pass
        return {"success": True, "message": "TRADE OFFER REJECTED."}

    from_player = str(target.get("from_player") or "").strip()
    to_player = str(target.get("to_player") or "").strip()
    offer = dict(target.get("offer") or {})
    request = dict(target.get("request") or {})

    from_player_id = _resolve_player_id_by_name(server, from_player)
    to_player_id = _resolve_player_id_by_name(server, to_player)
    if from_player_id is None or to_player_id is None:
        return {"success": False, "message": "UNABLE TO RESOLVE TRADE PLAYERS."}

    offer_resource = str(offer.get("resource") or "").strip().lower()
    request_resource = str(request.get("resource") or "").strip().lower()
    offer_amount = int(max(1, offer.get("amount") or 0))
    request_amount = int(max(1, request.get("amount") or 0))
    valid_resources = set(getattr(gm, "RESOURCE_TYPES", ("fuel", "ore", "tech", "bio", "rare")))
    if offer_resource not in valid_resources or request_resource not in valid_resources:
        return {"success": False, "message": "TRADE OFFER HAS INVALID RESOURCES."}

    from_available = int(gm.store.get_player_resource_amount(from_player_id, offer_resource))
    to_available = int(gm.store.get_player_resource_amount(to_player_id, request_resource))
    if from_available < offer_amount:
        return {"success": False, "message": "SENDER NO LONGER HAS OFFERED RESOURCES."}
    if to_available < request_amount:
        return {"success": False, "message": "YOU NO LONGER HAVE REQUESTED RESOURCES."}

    gm.store.adjust_player_resource(from_player_id, offer_resource, -offer_amount)
    gm.store.adjust_player_resource(from_player_id, request_resource, request_amount)
    gm.store.adjust_player_resource(to_player_id, request_resource, -request_amount)
    gm.store.adjust_player_resource(to_player_id, offer_resource, offer_amount)

    target["status"] = "accepted"
    target["resolved_at"] = float(time.time())
    _save_resource_offer_queue(server, offers)

    msg = (
        f"TRADE ACCEPTED: RECEIVED {offer_amount} {offer_resource.upper()} "
        f"FOR {request_amount} {request_resource.upper()}."
    )
    try:
        server._append_economy_alert(
            player_name,
            "resource_trade_offer_accepted",
            f"TRADE OFFER #{offer_id} ACCEPTED. {msg}",
            resource_type=offer_resource,
        )
    except Exception:
        pass
    return {"success": True, "message": msg}


def _h_process_resource_production(server, session, gm, params):
    success, msg = gm.produce_resources()
    if success and msg:
        try:
            server._append_economy_alert(
                getattr(getattr(gm, "player", None), "name", ""),
                "resource_production",
                str(msg),
            )
        except Exception:
            pass
    return {
        "success": bool(success),
        "message": str(msg),
        "data": gm.get_resource_snapshot(),
    }


def _h_payout_resource_interest(server, session, gm, params):
    success, msg = gm.payout_resource_interest()
    if success and msg:
        try:
            server._append_economy_alert(
                getattr(getattr(gm, "player", None), "name", ""),
                "resource_interest",
                str(msg),
            )
        except Exception:
            pass
    return {
        "success": bool(success),
        "message": str(msg),
        "data": gm.get_resource_snapshot(),
    }


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
        "get_planet_market_prices": _h_get_planet_market_prices,
        "get_resource_snapshot": _h_get_resource_snapshot,
        "trade_planet_resource": _h_trade_planet_resource,
        "refuel_ship_resource": _h_refuel_ship_resource,
        "player_trade_offer": _h_player_trade_offer,
        "create_resource_trade_offer": _h_create_resource_trade_offer,
        "get_resource_trade_offers": _h_get_resource_trade_offers,
        "respond_resource_trade_offer": _h_respond_resource_trade_offer,
        "process_resource_production": _h_process_resource_production,
        "payout_resource_interest": _h_payout_resource_interest,
    }
