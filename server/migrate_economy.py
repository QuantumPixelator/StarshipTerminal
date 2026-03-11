import argparse
import json
from pathlib import Path

from sqlite_store import SQLiteStore


def main():
    parser = argparse.ArgumentParser(description="Seed economy resource tables from existing SQLite state.")
    parser.add_argument("--db", dest="db_path", default=None, help="Path to game_state.db")
    parser.add_argument("--dry-run", dest="dry_run", action="store_true", help="Preview changes without writing")
    args = parser.parse_args()

    if args.db_path:
        db_path = Path(args.db_path)
    else:
        db_path = Path(__file__).resolve().parent / "saves" / "game_state.db"

    store = SQLiteStore(str(db_path))
    try:
        result = store.migrate_economy_seed(dry_run=bool(args.dry_run))
        print(json.dumps(result, indent=2))
    finally:
        store.close()


if __name__ == "__main__":
    main()
