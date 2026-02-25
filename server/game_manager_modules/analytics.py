import json
import os
import time
from collections import defaultdict


class AnalyticsMixin:
    def initialize_analytics(self):
        """Initialize analytics storage and in-memory counters."""
        self.analytics_enabled = bool(self.config.get("enable_analytics", True))
        self.analytics_retention_days = int(self.config.get("analytics_retention_days", 14))
        self.analytics_max_events = int(self.config.get("analytics_max_events", 5000))
        self.analytics_flush_interval_seconds = int(
            self.config.get("analytics_flush_interval_seconds", 15)
        )

        self.analytics_path = os.path.join(self.save_dir, "analytics_metrics.json")
        self.analytics_events = []
        self.analytics_counters = {
            "total_events": 0,
            "events_by_category": {},
            "events_by_name": {},
            "success_count": 0,
            "failure_count": 0,
        }
        self._analytics_dirty = False
        self._analytics_last_flush = time.time()

        self._load_analytics_snapshot()
        self._prune_analytics_events()

    def _load_analytics_snapshot(self):
        if not os.path.exists(self.analytics_path):
            return
        try:
            with open(self.analytics_path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
            events = list(data.get("events", []))
            counters = dict(data.get("counters", {}))

            self.analytics_events = events[-self.analytics_max_events :]
            self.analytics_counters = {
                "total_events": int(counters.get("total_events", len(self.analytics_events))),
                "events_by_category": dict(counters.get("events_by_category", {})),
                "events_by_name": dict(counters.get("events_by_name", {})),
                "success_count": int(counters.get("success_count", 0)),
                "failure_count": int(counters.get("failure_count", 0)),
            }
        except Exception:
            self.analytics_events = []
            self.analytics_counters = {
                "total_events": 0,
                "events_by_category": {},
                "events_by_name": {},
                "success_count": 0,
                "failure_count": 0,
            }

    def _persist_analytics_snapshot(self, force=False):
        if not self.analytics_enabled:
            return
        if (not force) and (not self._analytics_dirty):
            return

        now = time.time()
        if (not force) and (now - self._analytics_last_flush < self.analytics_flush_interval_seconds):
            return

        payload = {
            "updated_at": now,
            "events": self.analytics_events,
            "counters": self.analytics_counters,
        }

        try:
            with open(self.analytics_path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, indent=2)
            self._analytics_dirty = False
            self._analytics_last_flush = now
        except Exception:
            return

    def _prune_analytics_events(self):
        retention_seconds = max(1, self.analytics_retention_days) * 86400
        cutoff = time.time() - retention_seconds
        kept = [event for event in self.analytics_events if float(event.get("ts", 0)) >= cutoff]
        self.analytics_events = kept[-self.analytics_max_events :]

    def _bump_counter(self, bucket_key, name, amount=1):
        bucket = dict(self.analytics_counters.get(bucket_key, {}))
        bucket[name] = int(bucket.get(name, 0)) + int(amount)
        self.analytics_counters[bucket_key] = bucket

    def record_analytics_event(self, category, event_name, success=True, value=0, metadata=None):
        """Record a structured analytics event."""
        if not self.analytics_enabled:
            return

        cat = str(category or "unknown").strip().lower()[:48]
        name = str(event_name or "unknown_event").strip().lower()[:72]
        player_name = getattr(getattr(self, "player", None), "name", None)
        current_planet = getattr(getattr(self, "current_planet", None), "name", None)

        event = {
            "ts": time.time(),
            "category": cat,
            "name": name,
            "success": bool(success),
            "value": float(value or 0),
            "player": player_name,
            "planet": current_planet,
            "meta": dict(metadata or {}),
        }

        self.analytics_events.append(event)
        if len(self.analytics_events) > self.analytics_max_events:
            self.analytics_events = self.analytics_events[-self.analytics_max_events :]

        self.analytics_counters["total_events"] = int(self.analytics_counters.get("total_events", 0)) + 1
        self._bump_counter("events_by_category", cat, 1)
        self._bump_counter("events_by_name", name, 1)

        if bool(success):
            self.analytics_counters["success_count"] = int(self.analytics_counters.get("success_count", 0)) + 1
        else:
            self.analytics_counters["failure_count"] = int(self.analytics_counters.get("failure_count", 0)) + 1

        self._analytics_dirty = True
        self._prune_analytics_events()
        self._persist_analytics_snapshot(force=False)

    def get_analytics_events(self, limit=100, category=None):
        limit = max(1, min(1000, int(limit or 100)))
        events = list(self.analytics_events)
        if category:
            c = str(category).strip().lower()
            events = [event for event in events if str(event.get("category", "")).lower() == c]
        return events[-limit:]

    def get_analytics_summary(self, window_hours=24):
        window_hours = max(1, int(window_hours or 24))
        cutoff = time.time() - (window_hours * 3600)
        window_events = [event for event in self.analytics_events if float(event.get("ts", 0)) >= cutoff]

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
        success_rate = (float(success_count) / total) if total > 0 else 0.0

        top_events = sorted(by_name.items(), key=lambda item: item[1], reverse=True)[:10]

        return {
            "window_hours": window_hours,
            "events_in_window": total,
            "success_count": success_count,
            "failure_count": failure_count,
            "success_rate": round(success_rate, 4),
            "events_by_category": dict(sorted(by_category.items(), key=lambda item: item[1], reverse=True)),
            "top_events": [{"name": name, "count": count} for name, count in top_events],
            "lifetime_counters": dict(self.analytics_counters),
        }

    def get_analytics_recommendations(self, window_hours=24):
        summary = self.get_analytics_summary(window_hours=window_hours)
        by_name = {item["name"]: int(item["count"]) for item in summary.get("top_events", [])}
        recommendations = []

        total = int(summary.get("events_in_window", 0))
        success_rate = float(summary.get("success_rate", 0.0))
        if total >= 25 and success_rate < 0.75:
            recommendations.append(
                "Failure rate is elevated; review recent handler errors and tune economy/combat thresholds."
            )

        buy_count = int(by_name.get("economy_buy", 0)) + int(by_name.get("trade_buy", 0))
        sell_count = int(by_name.get("economy_sell", 0)) + int(by_name.get("trade_sell", 0))
        if buy_count > 0 and sell_count > 0:
            ratio = sell_count / float(buy_count)
            if ratio < 0.45:
                recommendations.append(
                    "Sell activity is low compared to buys; consider boosting sell multipliers or reducing penalties."
                )
            elif ratio > 1.6:
                recommendations.append(
                    "Sell activity dominates buys; evaluate market scarcity and buy-side incentives."
                )

        special_weapon_uses = int(by_name.get("combat_special_weapon", 0))
        if total >= 30 and special_weapon_uses == 0:
            recommendations.append(
                "Special weapon usage is near zero; review cooldown/cost to improve mechanic adoption."
            )

        if not recommendations:
            recommendations.append("Analytics look healthy in this window; no immediate balance changes suggested.")

        return {
            "window_hours": window_hours,
            "recommendations": recommendations,
        }

    def reset_analytics(self):
        self.analytics_events = []
        self.analytics_counters = {
            "total_events": 0,
            "events_by_category": {},
            "events_by_name": {},
            "success_count": 0,
            "failure_count": 0,
        }
        self._analytics_dirty = True
        self._persist_analytics_snapshot(force=True)

