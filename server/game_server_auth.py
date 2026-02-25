"""
Starship Terminal - Multiplayer Game Server with Authentication
Handles all game logic, player authentication, and save management.
"""

import asyncio
import base64
import hashlib
import websockets
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from game_manager import GameManager
import bcrypt
from handlers import build_dispatch

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)


class PlayerSession:
    """Manages a single player's game session with authentication."""

    def __init__(self, websocket):
        self.websocket = websocket
        self.gm = None
        self.account_name = None
        self.character_name = None
        self.player_name = None
        self.authenticated = False
        self.password_hash = None
        self.created_at = None


class GameServer:
    """WebSocket server managing multiplayer game sessions with password authentication."""

    def __init__(self, host="0.0.0.0", port=8765):
        self.host = host
        self.port = port
        self.active_sessions = {}
        self.server_root = Path(__file__).parent
        self.save_dir = str(self.server_root / "saves")
        self.assets_dir = self.server_root / "assets"
        self.sync_subdirs = [
            self.assets_dir / "texts",
            self.assets_dir / "planets" / "backgrounds",
            self.assets_dir / "planets" / "thumbnails",
        ]
        self.max_sync_file_bytes = 12_000_000

        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
            logging.info(f"Created save directory: {self.save_dir}")

        # Modular action dispatch table (built from server/handlers/ package)
        self._action_dispatch = build_dispatch()

    def _build_file_sha256(self, file_path: Path):
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _iter_sync_asset_files(self):
        for folder in self.sync_subdirs:
            if not folder.exists():
                continue
            for root, _, files in os.walk(folder):
                for name in files:
                    file_path = Path(root) / name
                    rel = file_path.relative_to(self.server_root).as_posix()
                    if not rel.startswith("assets/"):
                        continue
                    yield file_path, rel

    def _build_asset_sync_payload(self, client_manifest):
        if not isinstance(client_manifest, dict):
            client_manifest = {}

        updates = []
        server_manifest = {}

        for file_path, rel_path in self._iter_sync_asset_files():
            file_hash = self._build_file_sha256(file_path)
            server_manifest[rel_path] = file_hash

            if client_manifest.get(rel_path) == file_hash:
                continue

            # Guard against unexpectedly huge binary payloads.
            if file_path.stat().st_size > self.max_sync_file_bytes:
                continue

            content_b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
            updates.append(
                {
                    "path": rel_path,
                    "sha256": file_hash,
                    "content_b64": content_b64,
                }
            )

        deleted = [
            rel_path
            for rel_path in client_manifest.keys()
            if rel_path.startswith("assets/") and rel_path not in server_manifest
        ]

        return updates, deleted, server_manifest

    def _get_account_auth_path(self, account_name):
        """Get path to the ACCOUNT.json file for an account."""
        safe_name = self._safe_name(account_name)
        return str(Path(self.save_dir) / safe_name / "ACCOUNT.json")

    def _get_legacy_account_auth_path(self, account_name):
        safe_name = self._safe_name(account_name)
        return str(Path(self.save_dir) / f"{safe_name}.json")

    def _ensure_account_structure(self, account_name):
        """
        Ensure the account folder exists and the auth file is in the new location.
        Migrates legacy saves/<account>.json to saves/<account>/ACCOUNT.json.
        Returns the path to the ACCOUNT.json file.
        """
        safe_name = self._safe_name(account_name)
        account_dir = Path(self.save_dir) / safe_name
        new_auth_path = account_dir / "ACCOUNT.json"

        # Legacy path: saves/<account>.json
        legacy_auth_path = Path(self.save_dir) / f"{safe_name}.json"

        # If already migrated/correct
        if new_auth_path.exists():
            return str(new_auth_path)

        # Create directory if missing
        if not account_dir.exists():
            account_dir.mkdir(parents=True, exist_ok=True)
            logging.info(f"Created account directory: {account_dir}")

        # Migration: Move legacy auth file if it exists
        if legacy_auth_path.exists():
            try:
                # Load legacy data to verify it is actually an auth file (has password_hash)
                data = self._load_save_json(str(legacy_auth_path))
                if (
                    isinstance(data, dict)
                    and str(data.get("password_hash") or "").strip()
                ):
                    # It is an auth file, move it
                    import shutil

                    shutil.move(str(legacy_auth_path), str(new_auth_path))
                    logging.info(
                        f"Migrated account file: {legacy_auth_path} -> {new_auth_path}"
                    )
                else:
                    # It might be a legacy root save file (character save), NOT an auth file.
                    # We leave it alone; _get_account_characters logic will handle claiming it later.
                    pass
            except Exception as e:
                logging.error(f"Failed to migrate account file {legacy_auth_path}: {e}")

        return str(new_auth_path)

    def _safe_name(self, value):
        return str(value or "").strip().lower().replace(" ", "_")

    def _iter_player_save_paths(self):
        if not os.path.exists(self.save_dir):
            return []
        paths = []
        for file_name in os.listdir(self.save_dir):
            if not str(file_name).lower().endswith(".json"):
                continue
            if str(file_name).lower() in (
                "universe_planets.json",
                "galactic_news.json",
            ):
                continue
            paths.append(os.path.join(self.save_dir, file_name))
        return paths

    def _load_save_json(self, path):
        try:
            with open(path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            return data if isinstance(data, dict) else None
        except Exception:
            return None

    def _write_save_json(self, path, payload):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    # â”€â”€ Per-account character save directory helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _get_char_save_dir(self, account_name):
        """Return the path to saves/<account>/ where character saves live."""
        account_safe = self._safe_name(account_name)
        return str(Path(self.save_dir) / account_safe)

    def _ensure_char_save_dir(self, account_name):
        """Create saves/<account>/ if it doesn't exist. Returns the path."""
        char_dir = self._get_char_save_dir(account_name)
        if not os.path.exists(char_dir):
            os.makedirs(char_dir)
            logging.info(f"Created character save directory: {char_dir}")
        return char_dir

    def _set_gm_char_dir(self, gm, account_name):
        """
        Point a GameManager's save_dir at the account's character subdir.
        The planet-state and galactic-news paths were set in __init__ and DO
        NOT move â€“ they stay in the root saves/ folder which is correct.
        """
        char_dir = self._ensure_char_save_dir(account_name)
        gm.save_dir = char_dir
        return char_dir

    def _get_char_save_path(self, account_name, character_name):
        """Full path for saves/<account>/<character>.json."""
        char_dir = self._get_char_save_dir(account_name)
        char_safe = self._safe_name(character_name)
        return str(Path(char_dir) / f"{char_safe}.json")

    def _migrate_char_save_to_account_dir(self, account_name, character_name):
        """
        If a character save exists in the root saves/ but not in saves/<account>/,
        move it (copy + delete) into the account subdir and update its metadata.
        """
        account_safe = self._safe_name(account_name)
        char_safe = self._safe_name(character_name)
        legacy_path = os.path.join(self.save_dir, f"{char_safe}.json")
        new_path = self._get_char_save_path(account_safe, char_safe)

        if not os.path.exists(legacy_path):
            return False  # nothing to migrate
        if os.path.exists(new_path):
            return False  # already migrated

        data = self._load_save_json(legacy_path)
        if not isinstance(data, dict):
            return False
        # Don't migrate account auth files (those have password_hash)
        if str(data.get("password_hash") or "").strip():
            return False

        data["account_name"] = account_safe
        data["character_name"] = char_safe
        self._ensure_char_save_dir(account_safe)
        self._write_save_json(new_path, data)
        try:
            os.remove(legacy_path)
            logging.info(
                f"Migrated {char_safe}.json â†’ saves/{account_safe}/{char_safe}.json"
            )
        except Exception as e:
            logging.warning(f"Could not remove legacy save {legacy_path}: {e}")
        return True

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _get_account_characters(self, account_name):
        """
        Return list of {character_name, display_name, file} dicts for account.
        Scans saves/<account>/*.json, ignoring ACCOUNT.json.
        """
        account_safe = self._safe_name(account_name)

        # Ensure migration occurred if needed so we are looking in the right place
        self._ensure_account_structure(account_name)

        account_path = self._get_account_auth_path(account_name)
        account_data = (
            self._load_save_json(account_path) if os.path.exists(account_path) else None
        )
        linked = []
        seen = set()

        def add_character(character_safe, display_name=None, path=None):
            c_safe = self._safe_name(character_safe)
            if not c_safe or c_safe in seen:
                return
            if c_safe.lower() == "account":
                return  # Block listing the auth file as a character

            # Resolve display name: prefer explicit arg, then read from file
            c_display = str(display_name or "").strip()
            if not c_display:
                candidate = path or self._get_char_save_path(account_safe, c_safe)
                c_data = (
                    self._load_save_json(candidate)
                    if os.path.exists(candidate)
                    else None
                )
                if not c_data:
                    # Fallback to root legacy
                    legacy = os.path.join(self.save_dir, f"{c_safe}.json")
                    c_data = (
                        self._load_save_json(legacy) if os.path.exists(legacy) else None
                    )
                c_display = str(
                    ((c_data or {}).get("player") or {}).get("name") or c_safe
                ).strip()
            linked.append(
                {
                    "character_name": c_safe,
                    "display_name": c_display,
                    "file": os.path.basename(path) if path else f"{c_safe}.json",
                }
            )
            seen.add(c_safe)

        # â”€â”€ Priority 1: scan saves/<account>/ (new layout) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        char_dir = self._get_char_save_dir(account_safe)
        if os.path.exists(char_dir):
            _ignore = {"universe_planets.json", "galactic_news.json", "account.json"}
            for filename in sorted(os.listdir(char_dir)):
                if not filename.lower().endswith(".json"):
                    continue
                if filename.lower() in _ignore:
                    continue
                c_safe = os.path.splitext(filename)[0].lower()
                c_path = os.path.join(char_dir, filename)
                c_data = self._load_save_json(c_path)
                if not isinstance(c_data, dict):
                    continue
                # Skip any file that somehow ended up with a password hash (should be ACCOUNT.json)
                if str(c_data.get("password_hash") or "").strip():
                    continue
                player_name = str(
                    (c_data.get("player") or {}).get("name") or c_safe
                ).strip()
                add_character(c_safe, player_name, c_path)

        # â”€â”€ Priority 2: characters list in account auth file â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        if isinstance(account_data, dict):
            for item in list(account_data.get("characters", []) or []):
                if isinstance(item, dict):
                    add_character(
                        item.get("character_name") or item.get("name"),
                        item.get("display_name"),
                    )
                else:
                    add_character(item)

        # â”€â”€ Priority 3: root saves/ with matching account_name (legacy) â”€â”€â”€â”€â”€â”€
        for save_path in self._iter_player_save_paths():
            save_data = self._load_save_json(save_path)
            if not isinstance(save_data, dict):
                continue
            # Skip account auth files (they have a password_hash)
            if str(save_data.get("password_hash") or "").strip():
                continue
            if self._safe_name(save_data.get("account_name")) != account_safe:
                continue
            player_name = str((save_data.get("player") or {}).get("name") or "").strip()
            add_character(
                self._safe_name(player_name)
                or os.path.splitext(os.path.basename(save_path))[0],
                player_name,
                save_path,
            )

        # â”€â”€ Priority 4: legacy migration for unowned root saves â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
        account_has_password = bool(
            isinstance(account_data, dict)
            and str(account_data.get("password_hash") or "").strip()
        )
        if len(linked) <= 1 and account_has_password:
            ignore_prefixes = (
                "auth_",
                "combat_",
                "loop_",
                "market_",
                "msg_",
                "travel_",
            )
            for save_path in self._iter_player_save_paths():
                file_stem = os.path.splitext(os.path.basename(save_path))[0].lower()
                if file_stem.startswith(ignore_prefixes):
                    continue
                if "_" in file_stem:
                    continue
                save_data = self._load_save_json(save_path)
                if not isinstance(save_data, dict):
                    continue
                # CRITICAL: Do not claim the auth file itself
                if str(save_data.get("password_hash") or "").strip():
                    continue
                if self._safe_name(save_data.get("account_name")):
                    continue
                player_name = str(
                    (save_data.get("player") or {}).get("name") or file_stem
                ).strip()
                if not player_name:
                    continue
                add_character(file_stem, player_name, save_path)

        # Stable sort: account-named char first, then alphabetical
        linked.sort(
            key=lambda entry: (
                0 if entry.get("character_name") == account_safe else 1,
                str(entry.get("display_name", "")).lower(),
            )
        )
        return linked

    def _link_character_to_account(self, account_name, character_name):
        account_safe = self._safe_name(account_name)
        char_safe = self._safe_name(character_name)
        if not account_safe or not char_safe:
            return False

        # Block "ACCOUNT" character name
        if char_safe.lower() == "account":
            return False

        # Prefer the account-subdir path, fall back to root saves/
        subdir_path = self._get_char_save_path(account_safe, char_safe)

        # If it doesn't exist there, maybe it's in root (legacy)?
        legacy_path = os.path.join(self.save_dir, f"{char_safe}.json")

        if os.path.exists(subdir_path):
            char_path = subdir_path
        elif os.path.exists(legacy_path):
            # Move it to correct spot!
            self._ensure_char_save_dir(account_safe)
            try:
                import shutil

                shutil.move(legacy_path, subdir_path)
                char_path = subdir_path
                logging.info(
                    f"Moved linked character to account dir: {legacy_path} -> {subdir_path}"
                )
            except Exception:
                char_path = legacy_path
        else:
            return False

        char_data = self._load_save_json(char_path)
        if not isinstance(char_data, dict):
            return False

        # Don't link the account auth file as a character
        if str(char_data.get("password_hash") or "").strip():
            return False

        char_display = str(
            (char_data.get("player") or {}).get("name") or char_safe
        ).strip()
        char_data["account_name"] = account_safe
        char_data["character_name"] = char_safe
        self._write_save_json(char_path, char_data)

        # Update the auth file (ACCOUNT.json)
        self._ensure_account_structure(account_name)
        account_path = self._get_account_auth_path(account_name)
        account_data = self._load_save_json(account_path)
        if isinstance(account_data, dict):
            chars = list(account_data.get("characters", []) or [])
            names = {
                self._safe_name(
                    (entry.get("character_name") if isinstance(entry, dict) else entry)
                )
                for entry in chars
            }
            if char_safe not in names:
                chars.append(
                    {"character_name": char_safe, "display_name": char_display}
                )
                account_data["characters"] = chars
                account_data["account_name"] = account_safe
                self._write_save_json(account_path, account_data)
        return True

    def _serialize_ship(self, ship):
        if ship is None:
            return {}
        return {
            "model": getattr(ship, "model", ""),
            "cost": int(getattr(ship, "cost", 0)),
            "starting_cargo_pods": int(getattr(ship, "starting_cargo_pods", 0)),
            "starting_shields": int(getattr(ship, "starting_shields", 0)),
            "starting_defenders": int(getattr(ship, "starting_defenders", 0)),
            "max_cargo_pods": int(getattr(ship, "max_cargo_pods", 0)),
            "max_shields": int(getattr(ship, "max_shields", 0)),
            "max_defenders": int(getattr(ship, "max_defenders", 0)),
            "current_cargo_pods": int(getattr(ship, "current_cargo_pods", 0)),
            "current_shields": int(getattr(ship, "current_shields", 0)),
            "current_defenders": int(getattr(ship, "current_defenders", 0)),
            "special_weapon": getattr(ship, "special_weapon", None),
            "integrity": int(getattr(ship, "integrity", 100)),
            "max_integrity": int(getattr(ship, "max_integrity", 100)),
            "fuel": float(getattr(ship, "fuel", 0.0)),
            "max_fuel": float(getattr(ship, "max_fuel", 0.0)),
            "fuel_burn_rate": float(getattr(ship, "fuel_burn_rate", 1.0)),
            "last_refuel_time": float(getattr(ship, "last_refuel_time", 0.0)),
            "role_tags": list(getattr(ship, "role_tags", []) or []),
            "module_slots": int(getattr(ship, "module_slots", 1)),
            "installed_modules": list(getattr(ship, "installed_modules", []) or []),
            "crew_slots": dict(getattr(ship, "crew_slots", {}) or {}),
        }

    def _serialize_message(self, msg):
        return {
            "sender": getattr(msg, "sender", ""),
            "recipient": getattr(msg, "recipient", ""),
            "subject": getattr(msg, "subject", ""),
            "body": getattr(msg, "body", ""),
            "timestamp": getattr(msg, "timestamp", 0),
            "is_read": bool(getattr(msg, "is_read", False)),
            "is_saved": bool(getattr(msg, "is_saved", False)),
            "msg_id": getattr(msg, "id", getattr(msg, "msg_id", "")),
        }

    def _serialize_player(self, gm):
        player = getattr(gm, "player", None)
        if player is None:
            return {}

        crew_payload = {}
        for specialty, member in (getattr(player, "crew", {}) or {}).items():
            crew_payload[str(specialty)] = {
                "name": getattr(member, "name", ""),
                "specialty": getattr(member, "specialty", str(specialty)),
                "level": int(getattr(member, "level", 1)),
                "morale": int(getattr(member, "morale", 100)),
                "fatigue": int(getattr(member, "fatigue", 0)),
                "xp": int(getattr(member, "xp", 0)),
                "perks": list(getattr(member, "perks", []) or []),
            }

        return {
            "name": getattr(player, "name", ""),
            "credits": int(getattr(player, "credits", 0)),
            "bank_balance": int(getattr(player, "bank_balance", 0)),
            "inventory": dict(getattr(player, "inventory", {}) or {}),
            "owned_planets": dict(getattr(player, "owned_planets", {}) or {}),
            "barred_planets": dict(getattr(player, "barred_planets", {}) or {}),
            "attacked_planets": dict(getattr(player, "attacked_planets", {}) or {}),
            "authority_standing": int(
                getattr(
                    player,
                    "authority_standing",
                    getattr(player, "sector_reputation", 0),
                )
            ),
            "frontier_standing": int(getattr(player, "frontier_standing", 0)),
            "sector_reputation": int(
                getattr(
                    player,
                    "sector_reputation",
                    getattr(player, "authority_standing", 0),
                )
            ),
            "combat_win_streak": int(getattr(player, "combat_win_streak", 0)),
            "contract_chain_streak": int(getattr(player, "contract_chain_streak", 0)),
            "spaceship": self._serialize_ship(getattr(player, "spaceship", None)),
            "crew": crew_payload,
            "messages": [
                self._serialize_message(message)
                for message in list(getattr(player, "messages", []) or [])
            ],
        }

    def _serialize_planet(self, planet):
        if planet is None:
            return {}
        smuggling_inventory = dict(getattr(planet, "smuggling_inventory", {}) or {})
        smuggling_payload = {}
        for item_name, data in smuggling_inventory.items():
            entry = dict(data or {}) if isinstance(data, dict) else {}
            try:
                resolved_price = planet.get_smuggling_price(item_name)
            except Exception:
                resolved_price = None
            if resolved_price is not None:
                entry["price"] = int(resolved_price)
            if "base_price" not in entry and resolved_price is not None:
                entry["base_price"] = int(resolved_price)
            if "required_bribe_level" not in entry:
                base_for_level = int(
                    entry.get("base_price", entry.get("price", 500)) or 500
                )
                if base_for_level >= 16000:
                    required_level = 3
                elif base_for_level >= 7000:
                    required_level = 2
                elif base_for_level >= 2200:
                    required_level = 1
                else:
                    required_level = 0
                if int(getattr(planet, "security_level", 0)) >= 2:
                    required_level = min(3, required_level + 1)
                if bool(getattr(planet, "is_smuggler_hub", False)):
                    required_level = max(0, required_level - 1)
                entry["required_bribe_level"] = int(required_level)
            smuggling_payload[item_name] = entry

        return {
            "name": getattr(planet, "name", ""),
            "x": float(getattr(planet, "x", 0.0)),
            "y": float(getattr(planet, "y", 0.0)),
            "description": getattr(planet, "description", ""),
            "tech_level": int(getattr(planet, "tech_level", 0)),
            "government": getattr(planet, "government", ""),
            "population": int(getattr(planet, "population", 0)),
            "special_resources": getattr(planet, "special_resources", ""),
            "vendor": getattr(planet, "vendor", "UNKNOWN"),
            "bank": bool(getattr(planet, "bank", False)),
            "crew_services": bool(getattr(planet, "crew_services", False)),
            "is_smuggler_hub": bool(getattr(planet, "is_smuggler_hub", False)),
            "npc_name": getattr(planet, "npc_name", "Unknown"),
            "npc_personality": getattr(planet, "npc_personality", "neutral"),
            "docking_fee": int(getattr(planet, "docking_fee", 0)),
            "bribe_cost": int(getattr(planet, "bribe_cost", 0)),
            "security_level": int(getattr(planet, "security_level", 0)),
            "owner": getattr(planet, "owner", "UNCLAIMED"),
            "defenders": int(getattr(planet, "defenders", 0)),
            "max_defenders": int(getattr(planet, "max_defenders", 0)),
            "shields": int(getattr(planet, "shields", 0)),
            "base_shields": int(getattr(planet, "base_shields", 0)),
            "credit_balance": int(getattr(planet, "credit_balance", 0)),
            "repair_multiplier": getattr(planet, "repair_multiplier", None),
            "items": dict(getattr(planet, "items", {}) or {}),
            "smuggling_inventory": smuggling_payload,
            "welcome_msg": getattr(planet, "welcome_msg", "Docking request approved."),
            "unwelcome_msg": getattr(
                planet,
                "unwelcome_msg",
                "Identity confirmed. Proceed with caution.",
            ),
            "npc_remarks": list(
                getattr(planet, "npc_remarks", [])
                or ["Good day.", "What do you need?", "Let's trade."]
            ),
        }

    def _find_online_session_by_player_name(self, player_name):
        target = str(player_name or "").strip().lower()
        if not target:
            return None
        for sess in list(self.active_sessions.values()):
            if not sess or not getattr(sess, "authenticated", False):
                continue
            if str(getattr(sess, "player_name", "")).strip().lower() == target:
                return sess
        return None

    def _deliver_mail_to_online_player(
        self, recipient_name, sender_name, subject, body
    ):
        recipient_session = self._find_online_session_by_player_name(recipient_name)
        if not recipient_session or not getattr(recipient_session, "gm", None):
            return False
        from classes import Message

        recipient_player = getattr(recipient_session.gm, "player", None)
        if not recipient_player:
            return False

        msg = Message(sender_name, recipient_name, subject, body)
        recipient_player.add_message(msg)
        try:
            recipient_session.gm.save_game()
        except Exception:
            pass
        return True

    def _hash_password(self, password):
        """Hash a password using bcrypt."""
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")

    def _verify_password(self, password, password_hash):
        """Verify a password against its hash."""
        try:
            return bcrypt.checkpw(
                password.encode("utf-8"), password_hash.encode("utf-8")
            )
        except Exception as e:
            logging.error(f"Password verification error: {e}")
            return False

    def _player_exists(self, player_name):
        """Check if a player account exists."""
        # Use ensure logic to check if new structure exists or old one can be migrated
        save_path = self._ensure_account_structure(player_name)
        return os.path.exists(save_path)

    def _create_account(self, player_name, password, character_name=None):
        """Create a new player account with a character save in saves/<account>/."""
        save_path = self._ensure_account_structure(player_name)

        if os.path.exists(save_path):
            return {
                "success": False,
                "error": "ACCOUNT_EXISTS",
                "message": "Account already exists",
            }

        try:
            first_character = (
                str(character_name or "").strip() or str(player_name).strip()
            )
            first_character_safe = self._safe_name(first_character)
            if not first_character_safe:
                return {
                    "success": False,
                    "error": "INVALID_CHARACTER_NAME",
                    "message": "Character name is required",
                }

            if first_character_safe.lower() == "account":
                return {
                    "success": False,
                    "error": "INVALID_CHARACTER_NAME",
                    "message": "Name 'ACCOUNT' is reserved.",
                }

            account_safe = self._safe_name(player_name)

            # Save character into saves/<account>/ subdirectory
            gm = GameManager()
            self._set_gm_char_dir(gm, account_safe)  # saves/<account>/
            gm.account_name = account_safe
            gm.character_name = first_character_safe
            gm.new_game(first_character)

            # Verify it saved successfully
            char_save_path = self._get_char_save_path(
                account_safe, first_character_safe
            )
            if not os.path.exists(char_save_path):
                return {
                    "success": False,
                    "error": "SAVE_FAILED",
                    "message": "Failed to create initial character save",
                }

            created_at = datetime.now().isoformat()
            last_login = datetime.now().isoformat()
            password_hash = self._hash_password(password)

            # Account auth file: saves/<account>/ACCOUNT.json
            account_data = {
                "account_name": account_safe,
                "player": {"name": str(player_name)},
                "password_hash": password_hash,
                "characters": [
                    {
                        "character_name": first_character_safe,
                        "display_name": str(first_character),
                    }
                ],
                "created_at": created_at,
                "last_login": last_login,
            }
            self._write_save_json(save_path, account_data)
            # Backward-compatibility shadow file expected by older tools/tests.
            # Keep only account-auth fields (no game-state payload).
            self._write_save_json(
                self._get_legacy_account_auth_path(account_safe),
                dict(account_data),
            )

            logging.info(
                f"Created new account: {player_name} with character: {first_character}"
            )
            return {
                "success": True,
                "message": "Account created successfully",
                "new_account": True,
                "selected_character": first_character_safe,
            }

        except Exception as e:
            logging.error(f"Failed to create account for {player_name}: {e}")
            return {"success": False, "error": "SAVE_FAILED", "message": str(e)}

    def _authenticate_player(self, player_name, password):
        """Authenticate a player with username and password."""
        save_path = self._ensure_account_structure(player_name)

        if not os.path.exists(save_path):
            return {
                "success": False,
                "error": "NO_ACCOUNT",
                "message": "Account does not exist",
            }

        try:
            with open(save_path, "r") as f:
                save_data = json.load(f)

            if bool(save_data.get("blacklisted", False)):
                return {
                    "success": False,
                    "error": "BLACKLISTED",
                    "message": "Account is blacklisted",
                }

            if bool(save_data.get("account_disabled", False)):
                return {
                    "success": False,
                    "error": "ACCOUNT_DISABLED",
                    "message": "Account is disabled",
                }

            stored_hash = save_data.get("password_hash")
            if not stored_hash:
                logging.error(f"Account {player_name} missing password hash")
                return {
                    "success": False,
                    "error": "CORRUPT_ACCOUNT",
                    "message": "Account data is corrupted",
                }

            if not self._verify_password(password, stored_hash):
                logging.warning(f"Failed login attempt for {player_name}")
                return {
                    "success": False,
                    "error": "WRONG_PASSWORD",
                    "message": "Incorrect password",
                }

            # Update last login time
            save_data["last_login"] = datetime.now().isoformat()
            with open(save_path, "w") as f:
                json.dump(save_data, f, indent=2)

            logging.info(f"Player authenticated: {player_name}")
            return {
                "success": True,
                "message": "Authentication successful",
                "new_account": False,
            }

        except json.JSONDecodeError:
            logging.error(f"Corrupted save file for {player_name}")
            return {
                "success": False,
                "error": "CORRUPT_SAVE",
                "message": "Save file is corrupted",
            }
        except Exception as e:
            logging.error(f"Authentication error for {player_name}: {e}")
            return {"success": False, "error": "AUTH_ERROR", "message": str(e)}

    async def handle_client(self, websocket, path=None):
        """Handle individual client connection."""
        client_addr = websocket.remote_address
        logging.info(f"New connection from {client_addr}")

        session = PlayerSession(websocket)
        session_id = id(websocket)

        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    action = data.get("action")
                    params = data.get("params", {})

                    if not isinstance(params, dict):
                        params = {}

                    # Authentication actions (don't require active session)
                    if action == "check_account":
                        player_name_check = str(
                            params.get("player_name", data.get("player_name", ""))
                        ).strip()
                        exists = self._player_exists(player_name_check)
                        response = {"success": True, "exists": exists}
                        await websocket.send(json.dumps(response))
                        continue

                    elif action == "create_account":
                        player_name = str(
                            params.get("player_name", data.get("player_name", ""))
                        ).strip()
                        password = str(params.get("password", data.get("password", "")))
                        character_name = str(
                            params.get("character_name", data.get("character_name", ""))
                        ).strip()

                        if not player_name or not password:
                            await websocket.send(
                                json.dumps(
                                    {
                                        "success": False,
                                        "error": "INVALID_INPUT",
                                        "message": "Username and password required",
                                    }
                                )
                            )
                            continue

                        if not character_name:
                            character_name = player_name

                        result = self._create_account(
                            player_name, password, character_name
                        )

                        if result["success"]:
                            # Load the new game session from saves/<account>/
                            session.gm = GameManager()
                            self._set_gm_char_dir(session.gm, player_name)
                            selected_character = str(
                                result.get("selected_character") or character_name
                            )
                            load_result = session.gm.load_game(selected_character)

                            if load_result and (
                                load_result[0]
                                if isinstance(load_result, tuple)
                                else load_result
                            ):
                                session.account_name = self._safe_name(player_name)
                                session.character_name = self._safe_name(
                                    selected_character
                                )
                                session.player_name = str(
                                    getattr(
                                        getattr(session.gm, "player", None),
                                        "name",
                                        selected_character,
                                    )
                                )
                                session.authenticated = True
                                try:
                                    save_path = self._ensure_account_structure(
                                        player_name
                                    )
                                    with open(save_path, "r", encoding="utf-8") as f:
                                        saved = json.load(f)
                                    session.password_hash = saved.get("password_hash")
                                    session.created_at = saved.get("created_at")
                                except Exception:
                                    pass
                                self.active_sessions[session_id] = session
                                logging.info(
                                    f"Session created for new player: {player_name}"
                                )
                            else:
                                result = {
                                    "success": False,
                                    "error": "LOAD_FAILED",
                                    "message": "Account was created but initial character failed to load.",
                                }

                        await websocket.send(json.dumps(result))
                        continue

                    elif action == "authenticate":
                        player_name = str(
                            params.get("player_name", data.get("player_name", ""))
                        ).strip()
                        password = str(params.get("password", data.get("password", "")))

                        if not player_name or not password:
                            await websocket.send(
                                json.dumps(
                                    {
                                        "success": False,
                                        "error": "INVALID_INPUT",
                                        "message": "Username and password required",
                                    }
                                )
                            )
                            continue

                        result = self._authenticate_player(player_name, password)

                        if result["success"]:
                            account_safe = self._safe_name(player_name)
                            gm = GameManager()
                            # Point save_dir at the account's character subdir
                            self._set_gm_char_dir(gm, account_safe)
                            allow_multiple_games = bool(
                                gm.config.get("allow_multiple_games", False)
                            )
                            characters = self._get_account_characters(player_name)

                            auto_entry = characters[0] if characters else None
                            # In multi-save mode, always show selection when at least one
                            # character exists. In single-save mode, auto-load when there is
                            # exactly one character, but still show selection if legacy data has
                            # multiple characters linked.
                            requires_character_select = (
                                len(characters) >= 1
                                if allow_multiple_games
                                else len(characters) > 1
                            )
                            requires_character_create = len(characters) == 0

                            session.gm = gm
                            session.account_name = account_safe
                            session.authenticated = False

                            if requires_character_create:
                                session.character_name = None
                                session.player_name = player_name
                                response = {
                                    "success": True,
                                    "message": "Authentication successful",
                                    "new_account": False,
                                    "allow_multiple_games": allow_multiple_games,
                                    "requires_character_create": True,
                                    "requires_character_select": False,
                                    "characters": [],
                                }
                                session.authenticated = True
                            elif requires_character_select:
                                session.character_name = None
                                session.player_name = player_name
                                response = {
                                    "success": True,
                                    "message": "Authentication successful",
                                    "new_account": False,
                                    "allow_multiple_games": allow_multiple_games,
                                    "requires_character_select": True,
                                    "characters": characters,
                                }
                                session.authenticated = True
                            else:
                                # Single character or multiple-games disabled: auto-load
                                selected_character = (
                                    auto_entry.get("character_name")
                                    if auto_entry
                                    else account_safe
                                )
                                load_result = gm.load_game(selected_character)
                                load_ok = (
                                    load_result[0]
                                    if isinstance(load_result, tuple)
                                    else bool(load_result)
                                )
                                if not load_ok:
                                    response = {
                                        "success": False,
                                        "error": "LOAD_FAILED",
                                        "message": (
                                            load_result[1]
                                            if isinstance(load_result, tuple)
                                            and len(load_result) > 1
                                            else "Failed to load character save."
                                        ),
                                    }
                                else:
                                    session.character_name = self._safe_name(
                                        selected_character
                                    )
                                    session.player_name = str(
                                        getattr(
                                            getattr(gm, "player", None),
                                            "name",
                                            player_name,
                                        )
                                    )
                                    self._link_character_to_account(
                                        player_name, selected_character
                                    )
                                    response = {
                                        "success": True,
                                        "message": "Authentication successful",
                                        "new_account": False,
                                        "allow_multiple_games": allow_multiple_games,
                                        "requires_character_select": False,
                                        "selected_character": session.character_name,
                                        "characters": characters,
                                    }
                                    session.authenticated = True

                            try:
                                save_path = self._ensure_account_structure(player_name)
                                with open(save_path, "r", encoding="utf-8") as f:
                                    saved = json.load(f)
                                session.password_hash = saved.get("password_hash")
                                session.created_at = saved.get("created_at")
                            except Exception:
                                pass

                            await websocket.send(json.dumps(response))
                            if response.get("success"):
                                self.active_sessions[session_id] = session
                                logging.info(
                                    f"Session authenticated for account: {player_name}"
                                )
                            continue

                        await websocket.send(json.dumps(result))
                        continue

                    # All other actions require active session.
                    # list_characters and select_character are allowed as long as
                    # the session has an account_name (i.e. the user authenticated
                    # but hasn't yet picked a character).
                    _pre_select_ok = (
                        action in ("list_characters", "select_character")
                        and bool(getattr(session, "account_name", None))
                        and session_id in self.active_sessions
                    )
                    if not _pre_select_ok and (
                        session_id not in self.active_sessions
                        or not session.authenticated
                    ):
                        await websocket.send(
                            json.dumps(
                                {
                                    "success": False,
                                    "error": "NOT_AUTHENTICATED",
                                    "message": "Must authenticate first",
                                }
                            )
                        )
                        continue

                    # Route game actions
                    response = await self._handle_game_action(session, action, data)
                    await websocket.send(json.dumps(response))

                except json.JSONDecodeError:
                    logging.error(f"Invalid JSON from {client_addr}")
                    await websocket.send(
                        json.dumps(
                            {
                                "success": False,
                                "error": "INVALID_JSON",
                                "message": "Malformed request",
                            }
                        )
                    )
                except Exception as e:
                    logging.error(f"Error handling message from {client_addr}: {e}")
                    await websocket.send(
                        json.dumps(
                            {
                                "success": False,
                                "error": "SERVER_ERROR",
                                "message": str(e),
                            }
                        )
                    )

        except websockets.exceptions.ConnectionClosed:
            logging.info(f"Connection closed: {client_addr}")
        finally:
            if session_id in self.active_sessions:
                # Auto-save on disconnect
                try:
                    if session.gm and getattr(session.gm, "player", None):
                        character_name = str(
                            getattr(session.gm.player, "name", "")
                        ).strip()
                        account_name = (
                            str(getattr(session, "account_name", "")).strip()
                            or character_name
                        )

                        # Ensure gm saves to the correct account character subdir
                        if account_name:
                            self._set_gm_char_dir(session.gm, account_name)

                        # Save the game
                        session.gm.save_game()
                        self._link_character_to_account(account_name, character_name)

                        logging.info(f"Auto-saved character for account {account_name}")
                except Exception as e:
                    logging.error(f"Failed to auto-save: {e}")

                del self.active_sessions[session_id]
                logging.info(
                    f"Session closed for {session.player_name if session.player_name else 'unauthenticated user'}"
                )

    async def _handle_game_action(self, player_session, action, data):
        """Route and handle game actions via modular dispatch table (server/handlers/)."""
        try:
            session = player_session
            gm = getattr(session, "gm", None)
            params = data.get("params", {})

            # Inject computed context so handler functions can read it off session.
            session._account_safe = self._safe_name(
                getattr(session, "account_name", None)
                or getattr(session, "player_name", None)
            )
            session._auth_account = self._safe_name(
                getattr(session, "account_name", None)
            )

            # --- Session-only actions (work without gm or gm.player) -----------
            _session_only = {"list_characters", "select_character", "logout_commander"}
            if action in _session_only:
                handler = self._action_dispatch.get(action)
                if handler:
                    return handler(self, session, gm, params)

            # --- Require an initialised GameManager for everything else --------
            if not gm:
                return {
                    "success": False,
                    "error": "SESSION_NOT_READY",
                    "message": "Session is not initialized.",
                }

            # --- Actions allowed before a character is selected ----------------
            _pre_select = {
                "get_config",
                "list_characters",
                "select_character",
                "new_game",
                "load_game",
                "list_saves",
                "logout_commander",
            }
            if action not in _pre_select:
                if not getattr(gm, "player", None):
                    return {
                        "success": False,
                        "error": "CHARACTER_NOT_SELECTED",
                        "message": "Select a character before continuing.",
                    }

            # --- Dispatch to handler -------------------------------------------
            handler = self._action_dispatch.get(action)
            if handler:
                return handler(self, session, gm, params)

            return {"success": False, "error": f"Unknown action: {action}"}

        except Exception as e:
            logging.error(f"Error in game action {action}: {e}")
            import traceback

            traceback.print_exc()
            return {"success": False, "error": "ACTION_FAILED", "message": str(e)}

    # =========================================================================
    # LEGACY _handle_game_action body (kept here for reference until next cleanup)
    # The method above replaces all the if/elif action == ... branches.
    # =========================================================================
    async def start(self):
        """Start the WebSocket server."""
        print("=" * 70)
        print(" " * 20 + "STARSHIP TERMINAL SERVER")
        print("=" * 70)
        print()
        print(f"  WebSocket server starting on ws://{self.host}:{self.port}")
        print("  [AUTH] Password authentication enabled")
        print("  Ready to accept player connections!")
        print()
        print("-" * 70)
        print()

        async with websockets.serve(
            self.handle_client,
            self.host,
            self.port,
            max_size=None,
        ):
            logging.info(f"Server listening on port {self.port}...")
            await asyncio.Future()


def _load_server_bind_settings():
    host = "0.0.0.0"
    port = 8765
    config_path = Path(__file__).parent / "game_config.json"

    try:
        if config_path.exists():
            with config_path.open("r", encoding="utf-8") as handle:
                payload = json.load(handle)
            settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
            candidate = settings.get("server_port", port)
            parsed = int(str(candidate).strip())
            if 1 <= parsed <= 65535:
                port = parsed
            else:
                logging.warning(
                    "Invalid server_port '%s' in game_config.json; using %s",
                    candidate,
                    port,
                )
    except Exception as ex:
        logging.warning("Failed to load server_port from config: %s", ex)

    return host, port


def main():
    """Run the game server."""
    host, port = _load_server_bind_settings()
    server = GameServer(host=host, port=port)
    try:
        asyncio.run(server.start())
    except KeyboardInterrupt:
        print("\n\nServer shutdown requested...")
        logging.info("Server stopped by user")


if __name__ == "__main__":
    main()
