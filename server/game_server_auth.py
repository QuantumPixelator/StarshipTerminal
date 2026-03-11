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
from sqlite_store import SQLiteStore

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
        self.db_path = str(Path(self.save_dir) / "game_state.db")
        self.assets_dir = self.server_root / "assets"
        self.sync_subdirs = [
            self.assets_dir / "texts",
            self.assets_dir / "planets" / "backgrounds",
            self.assets_dir / "planets" / "thumbnails",
        ]
        self.max_sync_file_bytes = 12_000_000
        self._asset_cache_index = {}
        self._asset_manifest_cache = {}

        if not os.path.exists(self.save_dir):
            os.makedirs(self.save_dir)
            logging.info(f"Created save directory: {self.save_dir}")

        self.store = SQLiteStore(self.db_path)
        migrated = self.store.migrate_json_saves_once(
            save_dir=self.save_dir,
            server_root=str(self.server_root),
        )
        if migrated:
            logging.info("Initialized SQLite DB and imported existing JSON/text state.")

        # Modular action dispatch table (built from server/handlers/ package)
        self._action_dispatch = build_dispatch()
        self._phase5_tick_task = None

    def _build_file_sha256(self, file_path: Path):
        digest = hashlib.sha256()
        with file_path.open("rb") as handle:
            while True:
                chunk = handle.read(8192)
                if not chunk:
                    break
                digest.update(chunk)
        return digest.hexdigest()

    def _build_asset_cache_key(self, file_path: Path):
        stat = file_path.stat()
        return f"{int(stat.st_mtime_ns)}:{int(stat.st_size)}"

    def _refresh_asset_manifest_cache(self):
        if getattr(self, "store", None) is not None:
            try:
                self.store.export_catalog_texts_to_files(
                    self.assets_dir / "texts"
                )
            except Exception:
                pass

        cache_index = {}
        manifest = {}
        for file_path, rel_path in self._iter_sync_asset_files():
            cache_key = self._build_asset_cache_key(file_path)
            old_entry = self._asset_cache_index.get(rel_path, {})
            if old_entry.get("cache_key") == cache_key and old_entry.get("sha256"):
                sha256 = old_entry.get("sha256")
            else:
                sha256 = self._build_file_sha256(file_path)
            cache_index[rel_path] = {
                "path": file_path,
                "cache_key": cache_key,
                "sha256": sha256,
            }
            manifest[rel_path] = sha256

        self._asset_cache_index = cache_index
        self._asset_manifest_cache = manifest

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

        self._refresh_asset_manifest_cache()

        updates = []
        server_manifest = dict(self._asset_manifest_cache)

        for rel_path, entry in self._asset_cache_index.items():
            file_hash = entry.get("sha256")
            if client_manifest.get(rel_path) == file_hash:
                continue

            file_path = entry.get("path")
            if not file_path or not file_path.exists():
                continue
            if file_path.stat().st_size > self.max_sync_file_bytes:
                continue

            content_b64 = base64.b64encode(file_path.read_bytes()).decode("ascii")
            updates.append({"path": rel_path, "sha256": file_hash, "content_b64": content_b64})

        deleted = [
            rel_path
            for rel_path in client_manifest.keys()
            if rel_path.startswith("assets/") and rel_path not in server_manifest
        ]

        return updates, deleted, server_manifest

    def _get_account_auth_path(self, account_name):
        """Get SQLite auth reference for an account."""
        safe_name = self._safe_name(account_name)
        return f"dbauth://{safe_name}"

    def _ensure_account_structure(self, account_name):
        """
        Return the canonical SQLite auth reference for an account.
        """
        safe_name = self._safe_name(account_name)
<<<<<<< HEAD
        return f"dbauth://{safe_name}"
=======
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
            except Exception:
                logging.exception(
                    "Failed to migrate account file path='%s'",
                    str(legacy_auth_path),
                )

        return str(new_auth_path)
>>>>>>> 1511b0b46872728130faad7a264914cb11dc1818

    def _safe_name(self, value):
        return str(value or "").strip().lower().replace(" ", "_")

    def _is_account_name_taken(self, account_name):
        key = self._safe_name(account_name)
        if not key:
            return False
        if getattr(self, "store", None) is None:
            return False
        return bool(self.store.account_exists(key))

    def _is_commander_name_taken(self, commander_name):
        key = self._safe_name(commander_name)
        if not key:
            return False
        if getattr(self, "store", None) is None:
            return False
        return bool(self.store.commander_name_exists(commander_name))

    def _iter_player_save_paths(self):
        refs = []
        for row in self.store.iter_all_characters():
            account_name = str(row.get("account_name") or "").strip()
            character_name = str(row.get("character_name") or "").strip()
            if account_name and character_name:
                refs.append(f"db://{account_name}/{character_name}")
        return refs

    def _load_save_json(self, path):
        if getattr(self, "store", None) is None:
            return None
        try:
            target = str(path or "").strip()
            if target.startswith("db://"):
                _, _, remainder = target.partition("db://")
                account_name, _, character_name = remainder.partition("/")
                payload = self.store.get_character_payload(account_name, character_name)
                return payload if isinstance(payload, dict) else None
            if target.startswith("dbauth://"):
                account_name = str(target.partition("dbauth://")[2] or "").strip()
                payload = self.store.get_account_payload(account_name)
                return payload if isinstance(payload, dict) else None

            shared_map = {
                "universe_planets.json": "universe_planets",
                "galactic_news.json": "galactic_news",
                "winner_board.json": "winner_board",
                "analytics_metrics.json": "analytics_metrics",
            }
            save_root = Path(self.save_dir).resolve()
            target_path = Path(path).resolve()
            rel_parts = target_path.relative_to(save_root).parts

            if len(rel_parts) == 1:
                file_name = str(rel_parts[0]).lower()
                if file_name in shared_map:
                    payload = self.store.get_kv(
                        "shared", shared_map[file_name], default=None
                    )
                    if isinstance(payload, dict):
                        return payload
                if file_name.endswith(".json"):
                    stem = Path(file_name).stem
                    account_payload = self.store.get_account_payload(stem)
                    if isinstance(account_payload, dict):
                        return account_payload
                    found = self.store.find_character_payload_by_name(stem)
                    if isinstance(found, dict):
                        payload = found.get("payload")
                        if isinstance(payload, dict):
                            return payload

            if len(rel_parts) == 2:
                account_name = self._safe_name(rel_parts[0])
                file_name = str(rel_parts[1]).lower()
                if file_name == "account.json":
                    account_payload = self.store.get_account_payload(account_name)
                    if isinstance(account_payload, dict):
                        return account_payload
                elif file_name.endswith(".json"):
                    char_name = self._safe_name(Path(file_name).stem)
                    char_payload = self.store.get_character_payload(
                        account_name, char_name
                    )
                    if isinstance(char_payload, dict):
                        return char_payload
            return None
        except Exception:
            return None

    def _write_save_json(self, path, payload):
        if getattr(self, "store", None) is None:
            return
        try:
            target = str(path or "").strip()
            body = dict(payload or {})
            if target.startswith("db://"):
                _, _, remainder = target.partition("db://")
                account_name, _, character_name = remainder.partition("/")
                display_name = str((body.get("player") or {}).get("name") or character_name)
                self.store.upsert_character_payload(
                    account_name, character_name, body, display_name
                )
                return
            if target.startswith("dbauth://"):
                account_name = str(target.partition("dbauth://")[2] or "").strip()
                self.store.upsert_account_payload(account_name, body)
                return

            shared_map = {
                "universe_planets.json": "universe_planets",
                "galactic_news.json": "galactic_news",
                "winner_board.json": "winner_board",
                "analytics_metrics.json": "analytics_metrics",
            }
            save_root = Path(self.save_dir).resolve()
            target_path = Path(path).resolve()
            rel_parts = target_path.relative_to(save_root).parts

            if len(rel_parts) == 1:
                file_name = str(rel_parts[0]).lower()
                if file_name in shared_map:
                    self.store.set_kv("shared", shared_map[file_name], dict(payload or {}))
                    return
                if file_name.endswith(".json"):
                    stem = self._safe_name(Path(file_name).stem)
                    body = dict(payload or {})
                    if str(body.get("password_hash") or "").strip():
                        self.store.upsert_account_payload(stem, body)
                    else:
                        account_name = self._safe_name(body.get("account_name") or stem)
                        character_name = self._safe_name(body.get("character_name") or stem)
                        display_name = str((body.get("player") or {}).get("name") or character_name)
                        self.store.upsert_character_payload(
                            account_name, character_name, body, display_name
                        )
                    return

            if len(rel_parts) == 2:
                account_name = self._safe_name(rel_parts[0])
                file_name = str(rel_parts[1]).lower()
                if file_name == "account.json":
                    self.store.upsert_account_payload(account_name, body)
                    return
                if file_name.endswith(".json"):
                    character_name = self._safe_name(Path(file_name).stem)
                    display_name = str((body.get("player") or {}).get("name") or character_name)
                    self.store.upsert_character_payload(
                        account_name, character_name, body, display_name
                    )
                    return
            logging.warning("Skipped legacy file write outside DB namespace: %s", path)
            return
        except Exception:
            return

    def _collect_active_commander_names(self):
        """Collect commander display names from active (not blocked) accounts."""
        active_names = set()
        for row in self.store.iter_character_summaries(active_only=True):
            commander_name = str(row.get("display_name") or "").strip()
            if not commander_name:
                commander_name = str(row.get("character_name") or "").strip()
            if commander_name:
                active_names.add(commander_name.lower())
        return active_names

    def _reconcile_universe_planet_owners(self):
        """Clear stale planet owners for deleted, disabled, or blacklisted accounts."""
        data = self.store.get_kv("shared", "universe_planets", default=None)
        if not isinstance(data, dict):
            return

        states = data.get("planet_states", {})
        if not isinstance(states, dict):
            return

        active_names = self._collect_active_commander_names()
        changed = False
        cleared_count = 0

        for _, state in states.items():
            if not isinstance(state, dict):
                continue
            owner_name = str(state.get("owner") or "").strip()
            if not owner_name:
                continue
            if owner_name.lower() in active_names:
                continue
            state["owner"] = None
            changed = True
            cleared_count += 1

        if changed:
            data["updated_at"] = datetime.now().timestamp()
            self.store.set_kv("shared", "universe_planets", data)
            logging.info(
                "Reconciled universe ownership: cleared %s stale owner entries",
                cleared_count,
            )

    # â”€â”€ Per-account character save directory helpers â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _get_char_save_dir(self, account_name):
        """Legacy helper retained for compatibility; SQLite mode uses root save dir."""
        return str(self.save_dir)

    def _ensure_char_save_dir(self, account_name):
        """SQLite mode does not require per-account directories."""
        return str(self.save_dir)

    def _set_gm_char_dir(self, gm, account_name):
        """
        Keep GameManager save_dir rooted at saves/ in SQLite mode.
        """
        gm.save_dir = str(self.save_dir)
        return gm.save_dir

    def _get_char_save_path(self, account_name, character_name):
        """Canonical SQLite reference for a character payload."""
        account_safe = self._safe_name(account_name)
        char_safe = self._safe_name(character_name)
        return f"db://{account_safe}/{char_safe}"

    def _migrate_char_save_to_account_dir(self, account_name, character_name):
        """Legacy no-op: character payloads are persisted in SQLite."""
        return False

    # â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

    def _get_account_characters(self, account_name):
        """
        Return list of {character_name, display_name, file} dicts for account.
        Scans saves/<account>/*.json, ignoring ACCOUNT.json.
        """
        account_safe = self._safe_name(account_name)

        linked = []
        seen = set()

        def add_character(character_safe, display_name=None, path=None):
            c_safe = self._safe_name(character_safe)
            if not c_safe or c_safe in seen:
                return
            if c_safe.lower() == "account":
                return  # Block listing the auth file as a character

            c_display = str(display_name or "").strip() or c_safe
            linked.append(
                {
                    "character_name": c_safe,
                    "display_name": c_display,
                    "file": os.path.basename(path) if path else f"{c_safe}.json",
                }
            )
            seen.add(c_safe)

        for row in self.store.list_characters(account_safe):
            character_name = str(row.get("character_name") or "").strip()
            display_name = str(
                row.get("display_name") or row.get("character_name") or ""
            ).strip()
            if character_name:
                add_character(
                    character_name,
                    display_name,
                    f"db://{account_safe}/{character_name}",
                )

        account_path = self._get_account_auth_path(account_name)
        account_data = self._load_save_json(account_path)
        if isinstance(account_data, dict):
            for item in list(account_data.get("characters", []) or []):
                if isinstance(item, dict):
                    add_character(
                        item.get("character_name") or item.get("name"),
                        item.get("display_name"),
                    )
                else:
                    add_character(item)

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

        # Character payloads are SQLite-backed; this is just the canonical save reference path.
        subdir_path = self._get_char_save_path(account_safe, char_safe)
        char_path = subdir_path

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

    def _serialize_player(self, gm, include_messages=True):
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

        payload = {
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
            "is_docked": bool(getattr(player, "is_docked", False)),
            "smuggling_runs": int(getattr(player, "smuggling_runs", 0)),
            "smuggling_units_moved": int(getattr(player, "smuggling_units_moved", 0)),
            "bribes_paid_total": int(getattr(player, "bribes_paid_total", 0)),
            "spaceship": self._serialize_ship(getattr(player, "spaceship", None)),
            "crew": crew_payload,
        }
        if include_messages:
            payload["messages"] = [
                self._serialize_message(message)
                for message in list(getattr(player, "messages", []) or [])
            ]
        return payload

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
            "planet_id": int(getattr(planet, "planet_id", 0)),
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

    def _is_mutating_action(self, action):
        mutating_actions = {
            "new_game",
            "load_game",
            "save_game",
            "trade_item",
            "buy_item",
            "sell_item",
            "jettison_cargo",
            "buy_fuel",
            "repair_hull",
            "buy_ship",
            "transfer_fighters",
            "transfer_shields",
            "check_auto_refuel",
            "install_ship_upgrade",
            "travel_to_planet",
            "resolve_travel_event_payload",
            "resolve_combat_round",
            "flee_combat_session",
            "fire_special_weapon",
            "bank_deposit",
            "bank_withdraw",
            "payout_interest",
            "planet_deposit",
            "planet_withdraw",
            "process_crew_pay",
            "_adjust_authority_standing",
            "_adjust_frontier_standing",
            "bar_player",
            "process_conquered_planet_defense_regen",
            "process_commander_stipend",
            "mark_galactic_news_seen",
            "send_message",
            "delete_message",
            "mark_message_read",
            "gift_cargo_to_orbit_target",
            "claim_abandoned_ship",
            "bribe_npc",
            "sell_non_market_cargo",
            "reroll_trade_contract",
            "reset_analytics",
            "logout_commander",
            "select_character",
            "claim_planet",
            "process_trade",
            "start_combat",
            "combat_round",
            "daily_economy_tick",
            "reset_campaign",
            "force_combat",
            "give_credits",
            "admin_command",
        }
        return str(action or "") in mutating_actions

    async def _phase5_daily_tick_loop(self):
        """Run strategic economy tick every 60 seconds for active sessions."""
        while True:
            await asyncio.sleep(60.0)
            for session in list(self.active_sessions.values()):
                gm = getattr(session, "gm", None)
                if not gm or not getattr(gm, "player", None):
                    continue
                if not hasattr(gm, "daily_economy_tick"):
                    continue
                try:
                    await gm.daily_economy_tick()
                    gm.flush_pending_save()
                except Exception:
                    continue

    def _build_state_snapshot(self, gm):
        if not gm:
            return {}
        # Messages are excluded from hot-path state snapshots — they are
        # only needed when the player opens the inbox, and arrive via the
        # full get_player_info response.  Omitting them cuts snapshot size
        # by 30-60% for accounts with pending messages.
        return {
            "version": int(getattr(gm, "state_version", 0)),
            "updated_at": float(getattr(gm, "last_state_update_ts", 0.0)),
            "player": self._serialize_player(gm, include_messages=False),
            "current_planet": self._serialize_planet(getattr(gm, "current_planet", None)),
            "bribed_planets": list(getattr(gm, "bribed_planets", set()) or []),
            "planet_price_penalty_multiplier": getattr(gm, "planet_price_penalty_multiplier", None),
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
        if getattr(self, "store", None) is not None:
            recipient_account = str(
                getattr(recipient_session, "account_name", "") or ""
            ).strip()
            if recipient_account and self.store.is_account_blocked(recipient_account):
                return False
        from classes import Message

        recipient_player = getattr(recipient_session.gm, "player", None)
        if not recipient_player:
            return False

        msg = Message(sender_name, recipient_name, subject, body)
        recipient_player.add_message(msg)
        try:
            recipient_session.gm.save_game()
            recipient_session.gm.flush_pending_save(force=True)
        except Exception:
            logging.warning(
                "Failed to persist mailbox update recipient='%s'",
                str(recipient_name or ""),
                exc_info=True,
            )
        return True

    def _presence_banner_seconds(self):
        default_seconds = 5.0
        try:
            if getattr(self, "store", None) is not None:
                raw = self.store.get_kv(
                    "settings", "commander_presence_banner_seconds", default_seconds
                )
                seconds = float(raw)
            else:
                seconds = default_seconds
        except Exception:
            seconds = default_seconds
        return max(1.0, min(30.0, float(seconds)))

    def _append_presence_alert(self, commander_name, event_name):
        if getattr(self, "store", None) is None:
            return
        commander = str(commander_name or "").strip()
        event = str(event_name or "").strip().lower()
        if not commander or event not in {"login", "logout"}:
            return

        now = float(datetime.now().timestamp())
        keep_after = now - (72 * 3600.0)
        alerts = self.store.get_kv("shared", "presence_alerts", default=[])
        if not isinstance(alerts, list):
            alerts = []

        cleaned = []
        for entry in alerts:
            if not isinstance(entry, dict):
                continue
            try:
                ts = float(entry.get("timestamp", 0.0) or 0.0)
            except Exception:
                continue
            if ts >= keep_after:
                cleaned.append(entry)

        cleaned.append(
            {
                "event_id": int(now * 1000),
                "timestamp": now,
                "commander": commander,
                "event": event,
                "display_seconds": float(self._presence_banner_seconds()),
            }
        )
        if len(cleaned) > 512:
            cleaned = cleaned[-512:]
        self.store.set_kv("shared", "presence_alerts", cleaned)

    def _get_presence_alerts_since(self, since_ts, limit=24):
        if getattr(self, "store", None) is None:
            return []
        try:
            since = float(since_ts or 0.0)
        except Exception:
            since = 0.0
        max_items = max(1, min(128, int(limit or 24)))
        alerts = self.store.get_kv("shared", "presence_alerts", default=[])
        if not isinstance(alerts, list):
            return []

        rows = []
        for entry in alerts:
            if not isinstance(entry, dict):
                continue
            try:
                ts = float(entry.get("timestamp", 0.0) or 0.0)
            except Exception:
                continue
            if ts <= since:
                continue
            rows.append(
                {
                    "event_id": int(entry.get("event_id", int(ts * 1000))),
                    "timestamp": ts,
                    "commander": str(entry.get("commander", "")),
                    "event": str(entry.get("event", "")).lower(),
                    "display_seconds": float(
                        entry.get("display_seconds", self._presence_banner_seconds())
                    ),
                }
            )
        rows.sort(key=lambda item: float(item.get("timestamp", 0.0)))
        return rows[-max_items:]

    def _append_economy_alert(self, commander_name, event_name, message, resource_type=None):
        if getattr(self, "store", None) is None:
            return
        commander = str(commander_name or "").strip()
        evt = str(event_name or "").strip().lower()
        msg = str(message or "").strip()
        resource = str(resource_type or "").strip().lower()
        if not msg:
            return

        now = float(datetime.now().timestamp())
        retain_seconds = 3600.0 * 8.0
        keep_after = now - retain_seconds

        alerts = self.store.get_kv("shared", "economy_alerts", default=[])
        if not isinstance(alerts, list):
            alerts = []

        cleaned = []
        for entry in alerts:
            if not isinstance(entry, dict):
                continue
            try:
                ts = float(entry.get("timestamp", 0.0) or 0.0)
            except Exception:
                ts = 0.0
            if ts < keep_after:
                continue
            cleaned.append(entry)

        cleaned.append(
            {
                "timestamp": now,
                "commander": commander,
                "event": evt,
                "message": msg,
                "resource": resource,
                "display_seconds": float(self._presence_banner_seconds()),
            }
        )
        cleaned = cleaned[-400:]
        self.store.set_kv("shared", "economy_alerts", cleaned)

    def _get_economy_alerts_since(self, since_ts, limit=32):
        if getattr(self, "store", None) is None:
            return []

        try:
            cursor = float(since_ts or 0.0)
        except Exception:
            cursor = 0.0

        alerts = self.store.get_kv("shared", "economy_alerts", default=[])
        if not isinstance(alerts, list):
            return []

        filtered = []
        for entry in alerts:
            if not isinstance(entry, dict):
                continue
            try:
                ts = float(entry.get("timestamp", 0.0) or 0.0)
            except Exception:
                continue
            if ts <= cursor:
                continue
            filtered.append(
                {
                    "timestamp": ts,
                    "commander": str(entry.get("commander", "") or ""),
                    "event": str(entry.get("event", "") or ""),
                    "message": str(entry.get("message", "") or ""),
                    "resource": str(entry.get("resource", "") or ""),
                    "display_seconds": float(
                        entry.get("display_seconds", self._presence_banner_seconds())
                    ),
                }
            )

        return sorted(filtered, key=lambda item: item["timestamp"])[: max(1, int(limit))]
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
        except Exception:
            logging.exception("Password verification error")
            return False

    def _player_exists(self, player_name):
        """Check if a player account exists."""
        # Use ensure logic to check if new structure exists or old one can be migrated
        save_path = self._ensure_account_structure(player_name)
        return isinstance(self._load_save_json(save_path), dict)

    def _create_account(self, player_name, password, character_name=None):
        """Create a new player account and initial character in SQLite."""
        save_path = self._ensure_account_structure(player_name)

        if self._is_account_name_taken(player_name) or isinstance(
            self._load_save_json(save_path), dict
        ):
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

            if self._is_commander_name_taken(first_character):
                return {
                    "success": False,
                    "error": "NAME_TAKEN",
                    "message": f"Commander name '{first_character}' is already in use. Please choose a different name.",
                }

            account_safe = self._safe_name(player_name)

            # Save character payload via SQLite-backed GameManager persistence
            gm = GameManager()
            self._set_gm_char_dir(gm, account_safe)
            gm.account_name = account_safe
            gm.character_name = first_character_safe
            gm.new_game(first_character)

            # Verify it saved successfully
            char_save_path = self._get_char_save_path(
                account_safe, first_character_safe
            )
            if not isinstance(self._load_save_json(char_save_path), dict):
                return {
                    "success": False,
                    "error": "SAVE_FAILED",
                    "message": "Failed to create initial character save",
                }

            created_at = datetime.now().isoformat()
            last_login = datetime.now().isoformat()
            password_hash = self._hash_password(password)

            # Account auth payload is stored in SQLite.
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
            logging.exception(
                "Failed to create account account='%s'",
                str(player_name or ""),
            )
            return {"success": False, "error": "SAVE_FAILED", "message": str(e)}

    def _authenticate_player(self, player_name, password):
        """Authenticate a player with username and password."""
        self._reconcile_universe_planet_owners()
        save_path = self._ensure_account_structure(player_name)

        if not isinstance(self._load_save_json(save_path), dict):
            return {
                "success": False,
                "error": "NO_ACCOUNT",
                "message": "Account does not exist",
            }

        try:
            save_data = self._load_save_json(save_path)

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
            self._write_save_json(save_path, save_data)

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
            logging.exception(
                "Authentication error account='%s'",
                str(player_name or ""),
            )
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
                    request_id = data.get("request_id")

                    async def _send_response(payload):
                        if isinstance(payload, dict) and request_id is not None:
                            payload.setdefault("request_id", request_id)
                        await websocket.send(json.dumps(payload))

                    if not isinstance(params, dict):
                        params = {}

                    # Authentication actions (don't require active session)
                    if action == "check_account":
                        player_name_check = str(
                            params.get("player_name", data.get("player_name", ""))
                        ).strip()
                        exists = self._player_exists(player_name_check)
                        response = {"success": True, "exists": exists}
                        await _send_response(response)
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
                            await _send_response(
                                {
                                    "success": False,
                                    "error": "INVALID_INPUT",
                                    "message": "Username and password required",
                                }
                            )
                            if session.gm:
                                session.gm.flush_pending_save()
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
                                    saved = self._load_save_json(save_path)
                                    session.password_hash = saved.get("password_hash")
                                    session.created_at = saved.get("created_at")
                                except Exception:
                                    logging.warning(
                                        "Failed to load account metadata account='%s'",
                                        str(player_name or ""),
                                        exc_info=True,
                                    )
                                self.active_sessions[session_id] = session
                                self._append_presence_alert(session.player_name, "login")
                                logging.info(
                                    f"Session created for new player: {player_name}"
                                )
                            else:
                                result = {
                                    "success": False,
                                    "error": "LOAD_FAILED",
                                    "message": "Account was created but initial character failed to load.",
                                }

                        await _send_response(result)
                        if session.gm:
                            session.gm.flush_pending_save()
                        continue

                    elif action == "authenticate":
                        player_name = str(
                            params.get("player_name", data.get("player_name", ""))
                        ).strip()
                        password = str(params.get("password", data.get("password", "")))

                        if not player_name or not password:
                            await _send_response(
                                {
                                    "success": False,
                                    "error": "INVALID_INPUT",
                                    "message": "Username and password required",
                                }
                            )
                            if session.gm:
                                session.gm.flush_pending_save()
                            continue

                        result = self._authenticate_player(player_name, password)

                        if result["success"]:
                            account_safe = self._safe_name(player_name)
                            gm = GameManager()
                            # Point save_dir at the account's character subdir
                            self._set_gm_char_dir(gm, account_safe)
                            allow_multiple_games = bool(
                                gm.config.get("allow_multiple_games")
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
                                saved = self._load_save_json(save_path)
                                session.password_hash = saved.get("password_hash")
                                session.created_at = saved.get("created_at")
                            except Exception:
                                logging.warning(
                                    "Failed to load account metadata account='%s'",
                                    str(player_name or ""),
                                    exc_info=True,
                                )

                            await _send_response(response)
                            if response.get("success"):
                                self.active_sessions[session_id] = session
                                if (
                                    not bool(response.get("requires_character_select", False))
                                    and str(getattr(session, "player_name", "")).strip()
                                ):
                                    self._append_presence_alert(session.player_name, "login")
                                logging.info(
                                    f"Session authenticated for account: {player_name}"
                                )
                            if session.gm:
                                session.gm.flush_pending_save()
                            continue

                        await _send_response(result)
                        if session.gm:
                            session.gm.flush_pending_save()
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
                        await _send_response(
                            {
                                "success": False,
                                "error": "NOT_AUTHENTICATED",
                                "message": "Must authenticate first",
                            }
                        )
                        if session.gm:
                            session.gm.flush_pending_save()
                        continue

                    # Route game actions
                    response = await self._handle_game_action(session, action, data)
                    await _send_response(response)
                    if session.gm:
                        session.gm.flush_pending_save()

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
                    logging.exception(
                        "Error handling message client='%s'",
                        str(client_addr),
                    )
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
                        session.gm.flush_pending_save(force=True)
                        self._link_character_to_account(account_name, character_name)

                        logging.info(f"Auto-saved character for account {account_name}")
                except Exception:
                    logging.exception(
                        "Failed to auto-save session account='%s' character='%s'",
                        str(getattr(session, "account_name", "") or ""),
                        str(getattr(session, "character_name", "") or ""),
                    )

                del self.active_sessions[session_id]
                if str(getattr(session, "player_name", "")).strip() and getattr(session, "character_name", None):
                    self._append_presence_alert(session.player_name, "logout")
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
                    response = handler(self, session, gm, params)
                    if asyncio.iscoroutine(response):
                        response = await response
                    gm_after = getattr(session, "gm", gm)
                    if isinstance(response, dict) and bool(response.get("success")):
                        if action in {"select_character"}:
                            active_name = str(
                                getattr(getattr(gm_after, "player", None), "name", "")
                            ).strip()
                            if active_name:
                                self._append_presence_alert(active_name, "login")
                        elif action == "logout_commander":
                            logout_name = str(
                                response.get("logged_out_commander")
                                or getattr(session, "character_name", "")
                            ).strip()
                            if logout_name:
                                self._append_presence_alert(logout_name, "logout")
                    if (
                        isinstance(response, dict)
                        and self._is_mutating_action(action)
                        and gm_after is not None
                    ):
                        if bool(response.get("success")):
                            gm_after.mark_state_dirty()
                        response["state"] = self._build_state_snapshot(gm_after)
                    return response

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
                response = handler(self, session, gm, params)
                if asyncio.iscoroutine(response):
                    response = await response
                if isinstance(response, dict) and bool(response.get("success")):
                    if action in {"new_game", "load_game"}:
                        active_name = str(
                            getattr(getattr(gm, "player", None), "name", "")
                        ).strip()
                        if active_name:
                            self._append_presence_alert(active_name, "login")
                if (
                    isinstance(response, dict)
                    and self._is_mutating_action(action)
                    and gm is not None
                ):
                    if bool(response.get("success")):
                        gm.mark_state_dirty()
                    response["state"] = self._build_state_snapshot(gm)
                return response

            return {"success": False, "error": f"Unknown action: {action}"}

        except Exception as e:
            logging.exception(
                "Error in game action action='%s' account='%s' character='%s'",
                str(action or ""),
                str(getattr(player_session, "account_name", "") or ""),
                str(getattr(player_session, "character_name", "") or ""),
            )
            return {"success": False, "error": "ACTION_FAILED", "message": str(e)}

    # =========================================================================
    # LEGACY _handle_game_action body (kept here for reference until next cleanup)
    # The method above replaces all the if/elif action == ... branches.
    # =========================================================================
    async def start(self):
        """Start the WebSocket server."""
        self._reconcile_universe_planet_owners()
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
            compression="deflate",
        ):
            logging.info(f"Server listening on port {self.port}...")
            self._phase5_tick_task = asyncio.create_task(self._phase5_daily_tick_loop())
            try:
                await asyncio.Future()
            finally:
                if self._phase5_tick_task:
                    self._phase5_tick_task.cancel()


def _load_server_bind_settings():
    host = "0.0.0.0"
    port = 8765
    db_path = Path(__file__).parent / "saves" / "game_state.db"

    try:
<<<<<<< HEAD
        save_dir = db_path.parent
        save_dir.mkdir(parents=True, exist_ok=True)
        store = SQLiteStore(str(db_path))
        store.seed_default_settings()
        candidate = store.get_kv("settings", "server_port", default=port)
        parsed = int(str(candidate).strip())
        if 1 <= parsed <= 65535:
            port = parsed
        store.close()
=======
        if db_path.exists():
            store = SQLiteStore(str(db_path))
            candidate = store.get_kv("settings", "server_port", default=port)
            parsed = int(str(candidate).strip())
            if 1 <= parsed <= 65535:
                port = parsed
            store.close()
            return host, port
    except Exception:
        logging.warning("Failed loading server port from sqlite settings", exc_info=True)

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
>>>>>>> 1511b0b46872728130faad7a264914cb11dc1818
    except Exception as ex:
        logging.warning("Failed to load server_port from SQLite settings: %s", ex)

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
