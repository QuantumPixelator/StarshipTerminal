import argparse
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from planets import generate_planets
from sqlite_store import SQLiteStore

UNIVERSE_SCHEMA_VERSION = 2
COMMANDER_SCHEMA_VERSION = 2


@dataclass
class MigrationReport:
    scanned_files: int = 0
    updated_files: int = 0
    unknown_keys: list = field(default_factory=list)

    def add_unknown(self, path, field_name, key):
        self.unknown_keys.append({"path": str(path), "field": field_name, "key": str(key)})


def load_mapping():
    planets = generate_planets()
    id_by_name = {}
    name_by_id = {}
    for planet in planets:
        pid = int(getattr(planet, "planet_id", 0))
        if pid <= 0:
            raise RuntimeError(f"Invalid planet_id generated for planet {getattr(planet, 'name', '?')}")
        pname = str(getattr(planet, "name", "")).strip()
        if not pname:
            raise RuntimeError(f"Blank planet name for id {pid}")
        key = pname.lower()
        if key in id_by_name and id_by_name[key] != pid:
            raise RuntimeError(f"Non-bijective mapping for name '{pname}'")
        if pid in name_by_id and name_by_id[pid].lower() != key:
            raise RuntimeError(f"Non-bijective mapping for id {pid}")
        id_by_name[key] = pid
        name_by_id[pid] = pname
    return id_by_name, name_by_id


def resolve_planet_id(raw_key, id_by_name):
    try:
        direct = int(raw_key)
        if direct > 0:
            return direct
    except Exception:
        pass
    key = str(raw_key or "").strip().lower()
    if not key:
        return None
    return id_by_name.get(key)


def convert_dict_keys(payload, id_by_name, report, path, field_name):
    converted = {}
    if not isinstance(payload, dict):
        return converted
    for raw_key, value in payload.items():
        pid = resolve_planet_id(raw_key, id_by_name)
        if pid is None:
            report.add_unknown(path, field_name, raw_key)
            continue
        converted[str(pid)] = value
    return converted


def convert_list_keys(payload, id_by_name, report, path, field_name):
    converted = []
    if not isinstance(payload, list):
        return converted
    for raw_key in payload:
        pid = resolve_planet_id(raw_key, id_by_name)
        if pid is None:
            report.add_unknown(path, field_name, raw_key)
            continue
        converted.append(str(pid))
    return converted


def migrate_universe_payload(payload, id_by_name, report, path_label):
    if not isinstance(payload, dict):
        payload = {}

    states = payload.get("planet_states", {})
    migrated_states = convert_dict_keys(states, id_by_name, report, path_label, "planet_states")
    payload["schema_version"] = UNIVERSE_SCHEMA_VERSION
    payload["updated_at"] = float(time.time())
    payload["planet_states"] = migrated_states
    return payload


def migrate_commander_payload(payload, id_by_name, report, path_label):
    if not isinstance(payload, dict):
        return False, payload

    # Skip auth/account payloads.
    if str(payload.get("password_hash") or "").strip():
        return False, payload
    if not isinstance(payload.get("player"), dict):
        return False, payload

    changed = False
    payload["schema_version"] = COMMANDER_SCHEMA_VERSION

    current_id = resolve_planet_id(payload.get("current_planet_id"), id_by_name)
    if current_id is None:
        current_id = resolve_planet_id(payload.get("current_planet_name"), id_by_name)
    if current_id is None:
        report.add_unknown(path_label, "current_planet", payload.get("current_planet_name"))
    else:
        payload["current_planet_id"] = int(current_id)
        changed = True
    payload.pop("current_planet_name", None)

    player = payload.get("player") if isinstance(payload.get("player"), dict) else {}
    if player:
        player["barred_planets"] = convert_dict_keys(
            player.get("barred_planets", {}), id_by_name, report, path_label, "player.barred_planets"
        )
        player["attacked_planets"] = convert_dict_keys(
            player.get("attacked_planets", {}), id_by_name, report, path_label, "player.attacked_planets"
        )
        # Ownership must not be authoritative in commander saves.
        player.pop("owned_planets", None)
        payload["player"] = player
        changed = True

    payload["bribed_planets"] = convert_list_keys(
        payload.get("bribed_planets", []), id_by_name, report, path_label, "bribed_planets"
    )
    payload["bribe_registry"] = convert_dict_keys(
        payload.get("bribe_registry", {}), id_by_name, report, path_label, "bribe_registry"
    )
    payload["planets_smuggling"] = convert_dict_keys(
        payload.get("planets_smuggling", {}), id_by_name, report, path_label, "planets_smuggling"
    )

    law_heat = payload.get("law_heat") if isinstance(payload.get("law_heat"), dict) else {}
    if law_heat:
        law_heat["levels"] = convert_dict_keys(
            law_heat.get("levels", {}), id_by_name, report, path_label, "law_heat.levels"
        )
        payload["law_heat"] = law_heat

    payload["planet_events"] = convert_dict_keys(
        payload.get("planet_events", {}), id_by_name, report, path_label, "planet_events"
    )

    economy_state = payload.get("economy_state") if isinstance(payload.get("economy_state"), dict) else {}
    if economy_state:
        economy_state["momentum"] = convert_dict_keys(
            economy_state.get("momentum", {}), id_by_name, report, path_label, "economy_state.momentum"
        )
        economy_state["volume"] = convert_dict_keys(
            economy_state.get("volume", {}), id_by_name, report, path_label, "economy_state.volume"
        )
        payload["economy_state"] = economy_state

    # Universe file is authoritative for shared planet ownership/defense state.
    payload.pop("planet_states", None)
    changed = True
    return changed, payload


def main():
    parser = argparse.ArgumentParser(description="Migrate save schemas from planet_name to planet_id.")
    parser.add_argument("--apply", action="store_true", help="Apply migration changes in-place")
    parser.add_argument("--dry-run", action="store_true", help="Run checks without writing files")
    parser.add_argument(
        "--db-path",
        default=str(Path(__file__).resolve().parent / "saves" / "game_state.db"),
        help="Path to SQLite game state database",
    )
    args = parser.parse_args()

    if not args.apply and not args.dry_run:
        parser.error("Specify --dry-run or --apply")

    db_path = Path(args.db_path).resolve()
    if not db_path.exists():
        raise RuntimeError(f"SQLite database not found: {db_path}")

    id_by_name, _name_by_id = load_mapping()
    report = MigrationReport()
    store = SQLiteStore(str(db_path))

    universe_payload = store.get_kv("shared", "universe_planets", default={})
    if not isinstance(universe_payload, dict):
        universe_payload = {}

    commander_rows = list(store.iter_all_characters())
    report.scanned_files = 1 + len(commander_rows)

    migrated_universe = migrate_universe_payload(
        dict(universe_payload), id_by_name, report, "shared/universe_planets"
    )
    if args.apply:
        store.set_kv("shared", "universe_planets", migrated_universe)
        report.updated_files += 1

    for row in commander_rows:
        account_name = str(row.get("account_name") or "").strip()
        character_name = str(row.get("character_name") or "").strip()
        payload = row.get("payload") if isinstance(row, dict) else None
        if not account_name or not character_name:
            continue
        label = f"characters/{account_name}/{character_name}"
        changed, migrated_payload = migrate_commander_payload(
            dict(payload or {}), id_by_name, report, label
        )
        if changed and args.apply:
            display_name = str(
                row.get("display_name")
                or ((migrated_payload.get("player") or {}).get("name"))
                or character_name
            )
            store.upsert_character_payload(
                account_name, character_name, migrated_payload, display_name
            )
        if changed:
            report.updated_files += 1

    store.close()

    if report.unknown_keys:
        details = "\n".join(
            f"- {row['path']} :: {row['field']} :: {row['key']}" for row in report.unknown_keys
        )
        raise RuntimeError(
            "Migration aborted due to unknown/non-bijective planet mappings:\n" + details
        )

    print(json.dumps({
        "mode": "apply" if args.apply else "dry-run",
        "scanned_files": report.scanned_files,
        "updated_files": report.updated_files,
        "unknown_mappings": len(report.unknown_keys),
    }, indent=2))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        sys.exit(1)
