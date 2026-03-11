"""Phase-5 compatibility handlers that forward directly to GameManager API methods."""


async def _h_claim_planet(server, session, gm, params):
    result = await gm.claim_planet(
        int(params.get("player_id", 0) or 0),
        int(params.get("planet_id", 0) or 0),
    )
    return dict(result or {})


async def _h_process_trade(server, session, gm, params):
    result = await gm.process_trade(
        int(params.get("player_id", 0) or 0),
        int(params.get("planet_id", 0) or 0),
        str(params.get("item", "") or ""),
        int(params.get("qty", 1) or 1),
        bool(params.get("buy", True)),
    )
    return dict(result or {})


async def _h_start_combat(server, session, gm, params):
    combat_id = await gm.start_combat(
        int(params.get("attacker_id", 0) or 0),
        int(params.get("defender_id", 0) or 0),
        list(params.get("attacker_fleet", []) or []),
    )
    return {"success": True, "combat_id": int(combat_id)}


async def _h_combat_round(server, session, gm, params):
    result = await gm.combat_round(int(params.get("combat_id", 0) or 0))
    return dict(result or {})


async def _h_daily_economy_tick(server, session, gm, params):
    result = await gm.daily_economy_tick()
    return dict(result or {})


async def _h_get_full_state(server, session, gm, params):
    return {"success": True, "state": gm.get_full_state()}


async def _h_reset_campaign(server, session, gm, params):
    reason = str(params.get("reason") or "admin")
    ok = False
    msg = ""
    if hasattr(gm, "reset_current_campaign"):
        ok, msg = gm.reset_current_campaign(reason=reason)
    return {
        "success": bool(ok),
        "message": str(msg or "CAMPAIGN RESET REQUEST PROCESSED."),
    }


async def _h_force_combat(server, session, gm, params):
    combat_id = await gm.start_combat(
        int(params.get("attacker_id", 0) or 0),
        int(params.get("defender_id", 0) or 0),
        list(params.get("attacker_fleet", []) or []),
    )
    return {"success": True, "combat_id": int(combat_id)}


async def _h_give_credits(server, session, gm, params):
    player_id = int(params.get("player_id", 0) or 0)
    amount = int(params.get("amount", 0) or 0)
    if player_id <= 0 or amount == 0:
        return {"success": False, "message": "INVALID CREDIT GRANT PAYLOAD."}

    player_row = gm.store.get_player_row(player_id) if getattr(gm, "store", None) else None
    if player_row is None:
        if hasattr(gm, "_upsert_player_row_from_runtime"):
            gm._upsert_player_row_from_runtime(player_id)
            player_row = gm.store.get_player_row(player_id)
    if player_row is None:
        return {"success": False, "message": "PLAYER NOT FOUND."}

    updated_credits = int(player_row.get("credits", 0) or 0) + amount
    updated_credits = max(0, updated_credits)
    gm.store.upsert_player_row(
        player_id,
        str(player_row.get("name") or ""),
        credits=updated_credits,
        commander_rank=int(player_row.get("commander_rank", 1) or 1),
        owned_ships=list(player_row.get("owned_ships", []) or []),
    )
    gm.store.upsert_player_resource(player_id, "credits", int(updated_credits))
    if hasattr(gm, "mark_state_dirty"):
        gm.mark_state_dirty()
    return {
        "success": True,
        "message": f"CREDITS UPDATED FOR PLAYER {player_id}: {updated_credits:,}.",
        "player_id": int(player_id),
        "credits": int(updated_credits),
    }


async def _h_admin_command(server, session, gm, params):
    command = str(params.get("command") or "").strip()
    if not command:
        return {"success": False, "message": "EMPTY ADMIN COMMAND."}

    parts = command.split()
    head = parts[0].lower()
    if head == "/reset_campaign":
        return await _h_reset_campaign(server, session, gm, {"reason": "admin_command"})
    if head == "/force_combat":
        if len(parts) < 3:
            return {"success": False, "message": "USAGE: /force_combat <attacker_id> <defender_id>"}
        return await _h_force_combat(
            server,
            session,
            gm,
            {
                "attacker_id": int(parts[1]),
                "defender_id": int(parts[2]),
                "attacker_fleet": [],
            },
        )
    if head == "/give_credits":
        if len(parts) < 3:
            return {"success": False, "message": "USAGE: /give_credits <id> <amount>"}
        return await _h_give_credits(
            server,
            session,
            gm,
            {"player_id": int(parts[1]), "amount": int(parts[2])},
        )
    return {"success": False, "message": f"UNKNOWN ADMIN COMMAND: {command}"}


def register():
    return {
        "claim_planet": _h_claim_planet,
        "process_trade": _h_process_trade,
        "start_combat": _h_start_combat,
        "combat_round": _h_combat_round,
        "daily_economy_tick": _h_daily_economy_tick,
        "get_full_state": _h_get_full_state,
        "reset_campaign": _h_reset_campaign,
        "force_combat": _h_force_combat,
        "give_credits": _h_give_credits,
        "admin_command": _h_admin_command,
    }
