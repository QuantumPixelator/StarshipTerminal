"""
server/handlers/messaging.py

Handlers for player messaging and galactic news:
  has_unseen_galactic_news, get_unseen_galactic_news, mark_galactic_news_seen,
  send_message, mark_message_read, delete_message,
  gift_cargo_to_orbit_target, get_other_players
"""


def _h_has_unseen_galactic_news(server, session, gm, params):
    lookback_days = params.get("lookback_days")
    has_unseen = gm.has_unseen_galactic_news(lookback_days=lookback_days)
    return {"success": True, "has_unseen": bool(has_unseen)}


def _h_get_unseen_galactic_news(server, session, gm, params):
    lookback_days = params.get("lookback_days")
    entries = gm.get_unseen_galactic_news(lookback_days=lookback_days)
    return {"success": True, "entries": entries}


def _h_mark_galactic_news_seen(server, session, gm, params):
    gm.mark_galactic_news_seen()
    return {"success": True}


def _h_send_message(server, session, gm, params):
    recipient = str(params.get("recipient") or "").strip()
    subject = str(params.get("subject") or "").strip()
    body = str(params.get("body") or "").strip()
    sender_name = str(params.get("sender_name") or gm.player.name)

    if not recipient or not subject or not body:
        return {
            "success": False,
            "message": "Recipient, subject, and body are required.",
        }

    if recipient.lower() != str(gm.player.name).lower() and server._deliver_mail_to_online_player(
        recipient, sender_name, subject, body
    ):
        success = True
        msg = "Message sent."
    else:
        send_result = gm.send_message(recipient, subject, body, sender_name)
        if isinstance(send_result, tuple):
            success, msg = send_result
        else:
            success = bool(send_result)
            msg = "Message sent." if success else "Failed to send message."

    return {"success": success, "message": msg}


def _h_mark_message_read(server, session, gm, params):
    msg_id = str(params.get("msg_id") or "")
    if not msg_id:
        return {"success": False, "message": "Message ID is required."}
    updated = False
    for message in list(getattr(gm.player, "messages", []) or []):
        if str(getattr(message, "id", "")) == msg_id:
            message.is_read = True
            updated = True
            break
    if updated:
        try:
            gm.save_game()
        except Exception:
            pass
    return {
        "success": bool(updated),
        "message": "OK" if updated else "Message not found.",
    }


def _h_delete_message(server, session, gm, params):
    msg_id = params.get("msg_id")
    gm.player.delete_message(msg_id)
    return {"success": True}


def _h_gift_cargo_to_orbit_target(server, session, gm, params):
    target_data = params.get("target_data", {})
    item_name = params.get("item_name")
    qty = int(params.get("qty", 1))
    success, msg = gm.gift_cargo_to_orbit_target(target_data, item_name, qty)
    return {"success": bool(success), "message": str(msg)}


def _h_get_other_players(server, session, gm, params):
    others = gm.get_other_players()
    return {"success": True, "players": others}


def register():
    return {
        "has_unseen_galactic_news": _h_has_unseen_galactic_news,
        "get_unseen_galactic_news": _h_get_unseen_galactic_news,
        "mark_galactic_news_seen": _h_mark_galactic_news_seen,
        "send_message": _h_send_message,
        "mark_message_read": _h_mark_message_read,
        "delete_message": _h_delete_message,
        "gift_cargo_to_orbit_target": _h_gift_cargo_to_orbit_target,
        "get_other_players": _h_get_other_players,
    }
