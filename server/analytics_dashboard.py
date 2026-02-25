"""
Simple CLI dashboard for Starship Terminal analytics.

Usage:
  python analytics_dashboard.py
  python analytics_dashboard.py --window-hours 48 --top 15
"""

import argparse
import json
import os
import time
from collections import defaultdict
from pathlib import Path


def load_analytics(path):
    if not os.path.exists(path):
        return {"events": [], "counters": {}}
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def summarize(events, window_hours=24):
    cutoff = time.time() - (int(window_hours) * 3600)
    window_events = [event for event in events if float(event.get("ts", 0)) >= cutoff]

    by_category = defaultdict(int)
    by_name = defaultdict(int)
    success_count = 0
    failure_count = 0

    for event in window_events:
        by_category[str(event.get("category", "unknown"))] += 1
        by_name[str(event.get("name", "unknown_event"))] += 1
        if bool(event.get("success", False)):
            success_count += 1
        else:
            failure_count += 1

    total = len(window_events)
    success_rate = (success_count / total) if total > 0 else 0.0

    return {
        "total": total,
        "success_count": success_count,
        "failure_count": failure_count,
        "success_rate": success_rate,
        "by_category": sorted(by_category.items(), key=lambda item: item[1], reverse=True),
        "by_name": sorted(by_name.items(), key=lambda item: item[1], reverse=True),
    }


def print_summary(summary, top=10):
    print("\n" + "=" * 72)
    print("STARSHIP TERMINAL ANALYTICS DASHBOARD")
    print("=" * 72)
    print(f"Events in window: {summary['total']}")
    print(
        f"Success: {summary['success_count']}  "
        f"Failure: {summary['failure_count']}  "
        f"Success Rate: {summary['success_rate'] * 100:.1f}%"
    )

    print("\nTop Categories:")
    for name, count in summary["by_category"][:top]:
        print(f"  - {name:<24} {count}")

    print("\nTop Events:")
    for name, count in summary["by_name"][:top]:
        print(f"  - {name:<24} {count}")


def print_recommendations(summary):
    by_name = dict(summary["by_name"])
    recommendations = []

    if summary["total"] >= 25 and summary["success_rate"] < 0.75:
        recommendations.append(
            "Failure rate is elevated; review handler error paths and balancing thresholds."
        )

    buy_count = int(by_name.get("economy_buy", 0)) + int(by_name.get("trade_buy", 0))
    sell_count = int(by_name.get("economy_sell", 0)) + int(by_name.get("trade_sell", 0))
    if buy_count > 0 and sell_count > 0:
        ratio = sell_count / float(buy_count)
        if ratio < 0.45:
            recommendations.append("Low sell-to-buy ratio; consider increasing sell-side rewards.")
        elif ratio > 1.6:
            recommendations.append("High sell-to-buy ratio; consider improving buy incentives.")

    if int(by_name.get("combat_special_weapon", 0)) == 0 and summary["total"] >= 30:
        recommendations.append("Special weapon usage is low; review cooldown or availability.")

    if not recommendations:
        recommendations.append("No urgent balancing actions detected.")

    print("\nRecommendations:")
    for rec in recommendations:
        print(f"  - {rec}")


def main():
    parser = argparse.ArgumentParser(description="Starship Terminal analytics dashboard")
    parser.add_argument("--window-hours", type=int, default=24)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument(
        "--file",
        type=str,
        default=str(Path(__file__).resolve().parent / "saves" / "analytics_metrics.json"),
    )
    args = parser.parse_args()

    payload = load_analytics(args.file)
    events = list(payload.get("events", []) or [])

    summary = summarize(events, window_hours=args.window_hours)
    print_summary(summary, top=max(1, int(args.top)))
    print_recommendations(summary)
    print("=" * 72)


if __name__ == "__main__":
    main()
