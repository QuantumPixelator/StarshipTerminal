"""
Repeatable hot-path benchmark for StarshipTerminal server components.

Usage:
    c:/Users/dbowlin/Code/StarshipTerminal/venv/Scripts/python.exe server/perf_hotpaths_benchmark.py

Optional args:
    --accounts 300
    --chars-per-account 4
    --iterations 500
"""

import argparse
import os
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from sqlite_store import SQLiteStore
from game_manager_modules.persistence import PersistenceMixin
import game_server


class _PlayerStub:
    def __init__(self, name="Commander_0_0"):
        self.name = name


class _PersistenceHarness(PersistenceMixin):
    def __init__(self, store, player_name="Commander_0_0"):
        self.store = store
        self.player = _PlayerStub(player_name)


def _time_call(fn, iterations):
    start = time.perf_counter()
    for _ in range(iterations):
        fn()
    return time.perf_counter() - start


def _seed(store, accounts, chars_per_account):
    for a in range(accounts):
        acc = f"acct_{a}"
        blocked = a % 17 == 0
        store.upsert_account_payload(
            acc,
            {
                "account_name": acc,
                "account_disabled": blocked,
                "blacklisted": False,
            },
        )
        for c in range(chars_per_account):
            char = f"cmd_{a}_{c}"
            display = f"Commander_{a}_{c}"
            payload = {
                "player": {"name": display, "messages": []},
                "character_name": char,
            }
            store.upsert_character_payload(acc, char, payload, display_name=display)


def _bench_asset_sync(iterations):
    # Cold call (builds cache)
    t0 = time.perf_counter()
    files, deleted, manifest = game_server._build_asset_sync_payload({})
    cold = time.perf_counter() - t0

    # Warm calls (cache hit expected unless files change)
    warm_elapsed = _time_call(lambda: game_server._build_asset_sync_payload({}), iterations)

    return {
        "asset_manifest": len(manifest),
        "asset_updates": len(files),
        "asset_deleted": len(deleted),
        "asset_sync_cold_s": cold,
        "asset_sync_warm_total_s": warm_elapsed,
        "asset_sync_warm_avg_ms": (warm_elapsed / max(1, iterations)) * 1000.0,
    }


def run_benchmark(accounts, chars_per_account, iterations):
    fd, db_path = tempfile.mkstemp(prefix="perf_hotpaths_", suffix=".db")
    os.close(fd)
    store = None

    try:
        store = SQLiteStore(db_path)
        _seed(store, accounts, chars_per_account)

        harness = _PersistenceHarness(store)
        target = f"Commander_{accounts // 3}_{min(1, chars_per_account - 1)}"

        # SQLite summary/query timings
        t_summaries = _time_call(
            lambda: store.iter_character_summaries(active_only=True), iterations
        )
        t_find_refs = _time_call(
            lambda: store.find_character_refs_by_name(target, active_only=True), iterations
        )

        # Persistence hot paths
        t_other_players = _time_call(lambda: harness.get_other_players(), iterations)
        t_find_paths = _time_call(
            lambda: harness._find_commander_save_paths_by_name(target), iterations
        )

        results = {
            "accounts": accounts,
            "chars_per_account": chars_per_account,
            "iterations": iterations,
            "rows_total": len(store.iter_character_summaries(active_only=False)),
            "iter_character_summaries_total_s": t_summaries,
            "iter_character_summaries_avg_ms": (t_summaries / iterations) * 1000.0,
            "find_character_refs_total_s": t_find_refs,
            "find_character_refs_avg_ms": (t_find_refs / iterations) * 1000.0,
            "get_other_players_total_s": t_other_players,
            "get_other_players_avg_ms": (t_other_players / iterations) * 1000.0,
            "find_commander_paths_total_s": t_find_paths,
            "find_commander_paths_avg_ms": (t_find_paths / iterations) * 1000.0,
        }
        results.update(_bench_asset_sync(iterations))
        return results
    finally:
        if store is not None:
            store.close()
        try:
            os.remove(db_path)
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Benchmark server hot paths.")
    parser.add_argument("--accounts", type=int, default=300)
    parser.add_argument("--chars-per-account", type=int, default=4)
    parser.add_argument("--iterations", type=int, default=500)
    args = parser.parse_args()

    stats = run_benchmark(args.accounts, args.chars_per_account, args.iterations)
    for key in sorted(stats.keys()):
        print(f"{key}={stats[key]}")


if __name__ == "__main__":
    main()
