"""
server/handlers/banking.py

Handlers for banking and crew operations:
  bank_deposit, bank_withdraw, payout_interest, get_planet_financials,
  planet_deposit, planet_withdraw, get_planet_crew_offers, process_crew_pay
"""


def _parse_positive_amount(params):
    try:
        amount = int(params.get("amount"))
    except Exception:
        return None
    return amount if amount > 0 else None


def _h_bank_deposit(server, session, gm, params):
    amount = _parse_positive_amount(params)
    if amount is None:
        return {"success": False, "message": "Invalid amount."}
    success, msg = gm.bank_deposit(amount)
    return {
        "success": success,
        "message": msg,
        "credits": gm.player.credits if success else None,
        "bank_balance": gm.player.bank_balance if success else None,
    }


def _h_bank_withdraw(server, session, gm, params):
    amount = _parse_positive_amount(params)
    if amount is None:
        return {"success": False, "message": "Invalid amount."}
    success, msg = gm.bank_withdraw(amount)
    return {
        "success": success,
        "message": msg,
        "credits": gm.player.credits if success else None,
        "bank_balance": gm.player.bank_balance if success else None,
    }


def _h_payout_interest(server, session, gm, params):
    success, msg = gm.payout_interest()
    return {"success": success, "message": msg}


def _h_get_planet_financials(server, session, gm, params):
    data = gm.get_planet_financials()
    return {"success": True, "data": data}


def _h_planet_deposit(server, session, gm, params):
    amount = _parse_positive_amount(params)
    if amount is None:
        return {"success": False, "message": "Invalid amount."}
    success, msg = gm.planet_deposit(amount)
    return {
        "success": success,
        "message": msg,
        "credits": gm.player.credits if success else None,
        "planet_balance": (
            int(getattr(gm.current_planet, "credit_balance", 0))
            if success and gm.current_planet
            else None
        ),
    }


def _h_planet_withdraw(server, session, gm, params):
    amount = _parse_positive_amount(params)
    if amount is None:
        return {"success": False, "message": "Invalid amount."}
    success, msg = gm.planet_withdraw(amount)
    return {
        "success": success,
        "message": msg,
        "credits": gm.player.credits if success else None,
        "planet_balance": (
            int(getattr(gm.current_planet, "credit_balance", 0))
            if success and gm.current_planet
            else None
        ),
    }


def _h_get_planet_crew_offers(server, session, gm, params):
    planet = gm.resolve_planet_from_params(params, default_current=True)
    offers = gm.get_planet_crew_offers(planet)
    return {"success": True, "offers": offers}


def _h_process_crew_pay(server, session, gm, params):
    success, msg = gm.process_crew_pay()
    return {"success": success, "message": msg}


def register():
    return {
        "bank_deposit": _h_bank_deposit,
        "bank_withdraw": _h_bank_withdraw,
        "payout_interest": _h_payout_interest,
        "get_planet_financials": _h_get_planet_financials,
        "planet_deposit": _h_planet_deposit,
        "planet_withdraw": _h_planet_withdraw,
        "get_planet_crew_offers": _h_get_planet_crew_offers,
        "process_crew_pay": _h_process_crew_pay,
    }
