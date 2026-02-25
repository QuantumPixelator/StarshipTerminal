"""
server/handlers/auth_session.py

Handlers for character/session management and save-game operations:
  list_characters, select_character, logout_commander,
  new_game, load_game, save_game, list_saves
"""

from game_manager import GameManager  # server/ is on sys.path at runtime
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from logging_config import (
    get_session_logger,
    get_validation_logger,
    log_validation_error,
)


# ---------------------------------------------------------------------------
# Helpers (private to this module)
# ---------------------------------------------------------------------------

def _h_list_characters(server, session, gm, params):
    auth_account = getattr(session, "_auth_account", None)
    account_safe = getattr(session, "_account_safe", None)
    account_name = auth_account or server._safe_name(params.get("account_name", ""))
    if not account_name:
        return {
            "success": False,
            "error": "NO_ACCOUNT",
            "message": "Account context is missing.",
        }
    chars = server._get_account_characters(account_name)
    return {"success": True, "characters": chars}


def _h_select_character(server, session, gm, params):
    auth_account = getattr(session, "_auth_account", None)
    account_name = auth_account
    character_name = server._safe_name(params.get("character_name", ""))
    if not account_name or not character_name:
        return {
            "success": False,
            "error": "INVALID_INPUT",
            "message": "Character name is required.",
        }
    allowed = {
        server._safe_name(entry.get("character_name"))
        for entry in server._get_account_characters(account_name)
    }
    if character_name not in allowed:
        return {
            "success": False,
            "error": "CHARACTER_NOT_LINKED",
            "message": "Character does not belong to this account.",
        }
    if not gm:
        gm = GameManager()
        session.gm = gm
    server._set_gm_char_dir(gm, account_name)
    success, message = gm.load_game(character_name)
    if success:
        session.character_name = character_name
        session.player_name = str(
            getattr(getattr(gm, "player", None), "name", character_name)
        )
        server._link_character_to_account(account_name, character_name)
        return {
            "success": True,
            "message": str(message),
            "selected_character": character_name,
        }
    return {"success": False, "message": str(message)}


def _h_logout_commander(server, session, gm, params):
    import logging
    auth_account = getattr(session, "_auth_account", None)
    if gm and getattr(gm, "player", None):
        character_name = str(getattr(gm.player, "name", "")).strip()
        eff_account = auth_account or server._safe_name(
            getattr(gm, "account_name", "")
        )
        if eff_account and character_name:
            try:
                server._set_gm_char_dir(gm, eff_account)
                gm.save_game()
                server._link_character_to_account(eff_account, character_name)
            except Exception as e:
                logging.error(f"Logout save failed for {character_name}: {e}")

    session.character_name = None
    session.player_name = str(getattr(session, "account_name", "") or "")
    if gm is not None:
        try:
            gm.player = None
        except Exception:
            pass
    return {
        "success": True,
        "message": "Commander logged out. Account session remains active.",
    }


def _h_new_game(server, session, gm, params):
    """Create a new game character with server-side validation and logging."""
    try:
        account_safe = getattr(session, "_account_safe", None)
        requested_name = str(params.get("player_name", "")).strip()
        player_name = requested_name or str(getattr(getattr(gm, "player", None), "name", "")).strip()
        
        if not player_name:
            log_validation_error("empty_player_name", {"requested": requested_name})
            return {"success": False, "message": "Player name is required."}
        
        eff_account = account_safe or server._safe_name(player_name)
        allow_multiple_games = bool(gm.config.get("allow_multiple_games", False))
        linked_chars = server._get_account_characters(eff_account)
        linked_names = {
            server._safe_name(entry.get("character_name"))
            for entry in linked_chars
        }
        requested_safe = server._safe_name(player_name)
        
        # Check single save limit
        if (
            not allow_multiple_games
            and len(linked_names) >= 1
            and requested_safe not in linked_names
        ):
            log_validation_error(
                "single_save_limit_exceeded",
                {"account": eff_account, "requested_name": player_name},
                player_name
            )
            return {
                "success": False,
                "error": "SINGLE_SAVE_LIMIT",
                "message": "Multiple saves are disabled. This account can only use one commander profile.",
            }
        
        # Server-side: prevent overwriting an existing commander save
        char_save_path = server._get_char_save_path(eff_account, requested_safe)
        if os.path.exists(char_save_path):
            log_validation_error(
                "duplicate_character_name",
                {"account": eff_account, "name": player_name},
                player_name
            )
            return {
                "success": False,
                "error": "NAME_TAKEN",
                "message": f"Commander name '{player_name}' is already in use. Please choose a different name.",
            }
        
        # Create new game
        server._set_gm_char_dir(gm, eff_account)
        gm.account_name = eff_account
        gm.character_name = server._safe_name(player_name)
        gm.new_game(player_name)
        server._link_character_to_account(eff_account, player_name)
        session.character_name = server._safe_name(player_name)
        session.player_name = str(getattr(gm.player, "name", player_name))
        
        # Log successful character creation
        logger = get_session_logger()
        logger.info(f"[{player_name}] New character created in account {eff_account}")
        
        return {"success": True, "message": "New mission initialized."}
    except Exception as e:
        logger = get_session_logger()
        logger.error(f"Error creating new game: {str(e)}", exc_info=True)
        return {
            "success": False,
            "message": "Failed to create new game",
            "error": str(e),
        }


def _h_load_game(server, session, gm, params):
    account_safe = getattr(session, "_account_safe", None)
    player_name = str(params.get("player_name", "")).strip()
    if not player_name:
        return {"success": False, "message": "Save name is required."}
    if account_safe:
        allowed = {
            server._safe_name(entry.get("character_name"))
            for entry in server._get_account_characters(account_safe)
        }
        if server._safe_name(player_name) not in allowed:
            return {
                "success": False,
                "error": "CHARACTER_NOT_LINKED",
                "message": "Character does not belong to this account.",
            }
        server._set_gm_char_dir(gm, account_safe)
    success, message = gm.load_game(player_name)
    if success and account_safe:
        server._link_character_to_account(account_safe, player_name)
        session.character_name = server._safe_name(player_name)
        session.player_name = str(getattr(gm.player, "name", player_name))
    return {"success": bool(success), "message": str(message)}


def _h_save_game(server, session, gm, params):
    success = gm.save_game()
    return {"success": success, "message": "Game saved" if success else "Save failed"}


def _h_list_saves(server, session, gm, params):
    account_safe = getattr(session, "_account_safe", None)
    if account_safe:
        saves = [
            str(
                entry.get("display_name")
                or entry.get("character_name")
                or ""
            ).upper()
            for entry in server._get_account_characters(account_safe)
        ]
    else:
        saves = gm.list_saves()
    return {"success": True, "saves": saves}


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

def register():
    return {
        "list_characters": _h_list_characters,
        "select_character": _h_select_character,
        "logout_commander": _h_logout_commander,
        "new_game": _h_new_game,
        "load_game": _h_load_game,
        "save_game": _h_save_game,
        "list_saves": _h_list_saves,
    }
