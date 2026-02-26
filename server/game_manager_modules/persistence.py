import time
import json
import os
from datetime import datetime, timedelta
from classes import Player, Spaceship


class PersistenceMixin:
    def _default_winner_board_state(self):
        return {
            "current_winner": None,
            "scheduled_reset_ts": None,
            "last_reset_ts": None,
            "history": [],
        }

    def _load_winner_board_state(self):
        path = getattr(self, "winner_board_path", "")
        if not path or not os.path.exists(path):
            return self._default_winner_board_state()
        try:
            with open(path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if not isinstance(payload, dict):
                return self._default_winner_board_state()
            state = self._default_winner_board_state()
            state.update(payload)
            history = state.get("history", [])
            state["history"] = history if isinstance(history, list) else []
            return state
        except Exception:
            return self._default_winner_board_state()

    def _save_winner_board_state(self, state):
        path = getattr(self, "winner_board_path", "")
        if not path:
            return False
        try:
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(state, fh, indent=4)
            return True
        except Exception:
            return False

    def _build_faction_rankings(self, commanders):
        authority_sorted = sorted(
            commanders,
            key=lambda row: (
                int(row.get("authority", 0)),
                int(row.get("owned_planets", 0)),
                int(row.get("total_credits", 0)),
            ),
            reverse=True,
        )
        frontier_sorted = sorted(
            commanders,
            key=lambda row: (
                int(row.get("frontier", 0)),
                int(row.get("owned_planets", 0)),
                int(row.get("total_credits", 0)),
            ),
            reverse=True,
        )

        authority_ranking = []
        frontier_ranking = []
        for idx, row in enumerate(authority_sorted, start=1):
            authority_ranking.append(
                {
                    "rank": idx,
                    "name": str(row.get("name", "")),
                    "value": int(row.get("authority", 0)),
                }
            )
        for idx, row in enumerate(frontier_sorted, start=1):
            frontier_ranking.append(
                {
                    "rank": idx,
                    "name": str(row.get("name", "")),
                    "value": int(row.get("frontier", 0)),
                }
            )

        return {"authority": authority_ranking, "frontier": frontier_ranking}

    def _compute_winner_board_snapshot(self):
        planet_state_map = self._collect_planet_states()
        total_planets = max(1, len(self.planets))

        by_owner = {}
        for planet_name, state in (planet_state_map or {}).items():
            owner = str(state.get("owner") or "").strip()
            if not owner:
                continue
            owner_key = owner.lower()
            by_owner.setdefault(owner_key, {"owner_name": owner, "planets": []})
            by_owner[owner_key]["planets"].append((planet_name, state))

        commanders = []
        seen = set()
        for path in self._iter_commander_save_paths():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                continue

            if not isinstance(data, dict):
                continue
            p_data = data.get("player") if isinstance(data.get("player"), dict) else {}
            name = str(p_data.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)

            owned_records = by_owner.get(key, {}).get("planets", [])
            owned_planets = len(owned_records)
            personal_credits = int(p_data.get("credits", 0) or 0)
            bank_balance = int(p_data.get("bank_balance", 0) or 0)
            colony_credits = sum(
                int((st or {}).get("credit_balance", 0) or 0) for _, st in owned_records
            )
            total_credits = personal_credits + bank_balance + colony_credits

            authority = int(
                p_data.get(
                    "authority_standing",
                    p_data.get("sector_reputation", 0),
                )
                or 0
            )
            frontier = int(p_data.get("frontier_standing", 0) or 0)
            pct = (owned_planets / float(total_planets)) * 100.0

            commanders.append(
                {
                    "name": name,
                    "owned_planets": owned_planets,
                    "planet_ownership_pct": round(pct, 2),
                    "personal_credits": personal_credits,
                    "bank_balance": bank_balance,
                    "colony_credits": colony_credits,
                    "total_credits": int(total_credits),
                    "authority": authority,
                    "frontier": frontier,
                }
            )

        commanders.sort(
            key=lambda row: (
                int(row.get("owned_planets", 0)),
                float(row.get("planet_ownership_pct", 0.0)),
                int(row.get("total_credits", 0)),
            ),
            reverse=True,
        )

        rankings = self._build_faction_rankings(commanders)
        winner_state = self._load_winner_board_state()
        return {
            "total_planets": int(total_planets),
            "commanders": commanders,
            "faction_rankings": rankings,
            "winner_state": winner_state,
        }

    def _next_reset_timestamp(self, days_from_now):
        days = max(0, int(days_from_now or 0))
        now_dt = datetime.now()
        target_date = (now_dt + timedelta(days=days)).date()
        target_dt = datetime(
            target_date.year,
            target_date.month,
            target_date.day,
            0,
            1,
            0,
        )
        return float(target_dt.timestamp())

    def _broadcast_system_mail(self, subject, body, sender_name="GALACTIC COUNCIL"):
        recipients = []
        for path in self._iter_commander_save_paths():
            try:
                with open(path, "r", encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                continue
            p_data = data.get("player") if isinstance(data.get("player"), dict) else {}
            name = str(p_data.get("name") or "").strip()
            if name:
                recipients.append(name)

        sent = 0
        seen = set()
        for recipient in recipients:
            key = recipient.lower()
            if key in seen:
                continue
            seen.add(key)
            success, _msg = self.send_message(
                recipient,
                str(subject),
                str(body),
                sender_name=str(sender_name),
            )
            if success:
                sent += 1
        return sent

    def _evaluate_and_record_winner(self):
        snapshot = self._compute_winner_board_snapshot()
        commanders = list(snapshot.get("commanders", []) or [])
        if not commanders:
            return None

        winner_state = dict(snapshot.get("winner_state") or {})
        if winner_state.get("current_winner"):
            return winner_state.get("current_winner")

        min_planet_pct = float(self.config.get("victory_planet_ownership_pct"))
        authority_min = int(self.config.get("victory_authority_min"))
        authority_max = int(self.config.get("victory_authority_max"))
        frontier_min = int(self.config.get("victory_frontier_min"))
        frontier_max = int(self.config.get("victory_frontier_max"))

        candidates = []
        for row in commanders:
            pct = float(row.get("planet_ownership_pct", 0.0))
            authority = int(row.get("authority", 0))
            frontier = int(row.get("frontier", 0))
            if pct < min_planet_pct:
                continue
            if not (authority_min <= authority <= authority_max):
                continue
            if not (frontier_min <= frontier <= frontier_max):
                continue
            candidates.append(row)

        if not candidates:
            return None

        winner = max(
            candidates,
            key=lambda row: (
                int(row.get("owned_planets", 0)),
                float(row.get("planet_ownership_pct", 0.0)),
                int(row.get("total_credits", 0)),
                int(row.get("authority", 0)) + int(row.get("frontier", 0)),
            ),
        )

        rankings = snapshot.get("faction_rankings", {})
        authority_rank = next(
            (
                int(entry.get("rank", 0))
                for entry in list(rankings.get("authority", []) or [])
                if str(entry.get("name", "")).lower()
                == str(winner.get("name", "")).lower()
            ),
            0,
        )
        frontier_rank = next(
            (
                int(entry.get("rank", 0))
                for entry in list(rankings.get("frontier", []) or [])
                if str(entry.get("name", "")).lower()
                == str(winner.get("name", "")).lower()
            ),
            0,
        )

        reset_days = int(self.config.get("victory_reset_days"))
        reset_ts = self._next_reset_timestamp(reset_days)

        winner_record = {
            "name": str(winner.get("name", "")),
            "owned_planets": int(winner.get("owned_planets", 0)),
            "planet_ownership_pct": float(winner.get("planet_ownership_pct", 0.0)),
            "total_credits": int(winner.get("total_credits", 0)),
            "personal_credits": int(winner.get("personal_credits", 0)),
            "bank_balance": int(winner.get("bank_balance", 0)),
            "colony_credits": int(winner.get("colony_credits", 0)),
            "authority": int(winner.get("authority", 0)),
            "frontier": int(winner.get("frontier", 0)),
            "authority_rank": int(authority_rank),
            "frontier_rank": int(frontier_rank),
            "won_at": float(time.time()),
            "reset_at": float(reset_ts),
        }

        history = list(winner_state.get("history", []) or [])
        history.append(dict(winner_record))
        if len(history) > 50:
            history = history[-50:]

        next_state = {
            "current_winner": winner_record,
            "scheduled_reset_ts": float(reset_ts),
            "last_reset_ts": winner_state.get("last_reset_ts"),
            "history": history,
        }
        self._save_winner_board_state(next_state)

        reset_dt_text = datetime.fromtimestamp(reset_ts).strftime("%Y-%m-%d 12:01 AM")
        subject = "GALACTIC CHAMPION DECLARED"
        body = (
            f"Commander {winner_record['name']} has won the current campaign. "
            f"Owned planets: {winner_record['owned_planets']} ({winner_record['planet_ownership_pct']:.1f}%). "
            f"Total credits: {winner_record['total_credits']:,}. "
            f"Universe reset is scheduled for {reset_dt_text}."
        )
        self._broadcast_system_mail(subject, body)
        self._append_galactic_news(
            title="Campaign Winner Declared",
            body=body,
            event_type="winner",
            audience="global",
        )
        return winner_record

    def _reset_galaxy_state(self):
        for planet in list(self.planets):
            planet.owner = None
            planet.defenders = int(getattr(planet, "base_defenders", planet.defenders))
            planet.shields = int(getattr(planet, "base_shields", planet.shields))
            planet.max_shields = int(
                getattr(
                    planet,
                    "base_max_shields",
                    getattr(planet, "base_shields", planet.shields),
                )
            )
            planet.max_defenders = int(
                getattr(
                    planet,
                    "base_max_defenders",
                    getattr(planet, "base_defenders", planet.defenders),
                )
            )
            planet.last_defense_regen_time = 0.0
            planet.credits_initialized = False
            planet.credit_balance = int(
                max(
                    0,
                    getattr(
                        planet,
                        "base_credit_balance",
                        round(getattr(planet, "population", 0) * 0.20),
                    ),
                )
            )
            planet.last_credit_interest_time = 0.0
        self._save_shared_planet_states()

    def _purge_commander_saves_for_reset(self):
        removed = 0
        for path in self._iter_commander_save_paths():
            try:
                os.remove(path)
                removed += 1
            except Exception:
                continue
        return removed

    def reset_current_campaign(self, reason="scheduled"):
        """Reset the active universe while preserving account auth records.

        - Removes all commander save files from all accounts.
        - Restores all planet ownership/state to defaults.
        - Clears current winner and scheduled reset marker.
        """
        self._reset_galaxy_state()
        removed_commanders = self._purge_commander_saves_for_reset()

        state = self._load_winner_board_state()
        state["current_winner"] = None
        state["scheduled_reset_ts"] = None
        state["last_reset_ts"] = float(time.time())
        self._save_winner_board_state(state)

        reason_label = str(reason or "scheduled").strip().lower()
        if reason_label == "admin":
            self._append_galactic_news(
                title="Campaign Reset Executed",
                body=(
                    f"An administrator reset the current game state. "
                    f"Commander saves removed: {removed_commanders}."
                ),
                event_type="admin_reset",
                audience="global",
            )

        return {
            "success": True,
            "removed_commanders": int(removed_commanders),
            "accounts_preserved": True,
            "reason": reason_label,
        }

    def _process_scheduled_game_reset_if_due(self):
        state = self._load_winner_board_state()
        reset_ts = state.get("scheduled_reset_ts")
        if not reset_ts:
            return False

        try:
            reset_ts = float(reset_ts)
        except Exception:
            return False

        if time.time() < reset_ts:
            return False

        self.reset_current_campaign(reason="scheduled")
        return True

    def get_winner_board(self):
        snapshot = self._compute_winner_board_snapshot()
        winner_state = snapshot.get("winner_state", {})
        current_winner = winner_state.get("current_winner")
        rankings = snapshot.get("faction_rankings", {})

        return {
            "current_winner": current_winner,
            "scheduled_reset_ts": winner_state.get("scheduled_reset_ts"),
            "last_reset_ts": winner_state.get("last_reset_ts"),
            "history": list(winner_state.get("history", []) or []),
            "leaderboard": list(snapshot.get("commanders", []) or []),
            "faction_rankings": {
                "authority": list(rankings.get("authority", []) or []),
                "frontier": list(rankings.get("frontier", []) or []),
            },
            "total_planets": int(snapshot.get("total_planets", 0)),
        }

    def _collect_planet_states(self):
        return {
            p.name: {
                "owner": p.owner,
                "defenders": int(p.defenders),
                "shields": int(p.shields),
                "credit_balance": int(getattr(p, "credit_balance", 0)),
                "credits_initialized": bool(getattr(p, "credits_initialized", False)),
                "last_credit_interest_time": float(
                    getattr(p, "last_credit_interest_time", 0.0)
                ),
                "max_shields": int(getattr(p, "max_shields", p.base_shields)),
                "max_defenders": int(getattr(p, "max_defenders", p.base_defenders)),
                "last_defense_regen_time": float(
                    getattr(p, "last_defense_regen_time", 0)
                ),
            }
            for p in self.planets
        }

    def _apply_planet_states(self, planet_states, apply_ownership=True):
        """Restore planet runtime state.  Pass apply_ownership=False when loading
        from a per-character save so that universe_planets.json remains the sole
        source of truth for ownership."""
        if not isinstance(planet_states, dict):
            return

        for p in self.planets:
            state = planet_states.get(p.name)
            if not isinstance(state, dict):
                continue

            if apply_ownership:
                p.owner = state.get("owner")
            p.defenders = max(0, int(state.get("defenders", p.defenders)))
            p.shields = max(0, int(state.get("shields", p.shields)))
            credits_already_init = bool(state.get("credits_initialized", False))
            saved_credits = int(state.get("credit_balance", -1))
            if credits_already_init:
                # Planet was already seeded – always honour the saved balance (even 0)
                p.credit_balance = (
                    max(0, saved_credits) if saved_credits >= 0 else p.credit_balance
                )
                p.credits_initialized = True
            else:
                # First load ever (old save or key absent) – seed once to 20% of population
                p.credit_balance = round(getattr(p, "population", 0) * 0.20)
                p.credits_initialized = True
            p.last_credit_interest_time = float(
                state.get(
                    "last_credit_interest_time",
                    getattr(p, "last_credit_interest_time", 0.0),
                )
            )
            p.max_shields = max(
                1,
                int(
                    state.get("max_shields", getattr(p, "max_shields", p.base_shields))
                ),
            )
            p.max_defenders = max(
                1,
                int(
                    state.get(
                        "max_defenders",
                        getattr(p, "max_defenders", max(1, p.base_defenders)),
                    )
                ),
            )
            p.last_defense_regen_time = float(
                state.get(
                    "last_defense_regen_time",
                    getattr(p, "last_defense_regen_time", 0),
                )
            )

    def _save_shared_planet_states(self):
        try:
            payload = {
                "updated_at": float(time.time()),
                "planet_states": self._collect_planet_states(),
            }
            with open(self.shared_planet_state_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=4)
            return True
        except Exception:
            return False

    def _load_shared_planet_states(self):
        try:
            if not os.path.exists(self.shared_planet_state_path):
                return False
            with open(self.shared_planet_state_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            self._apply_planet_states(payload.get("planet_states", {}))
            return True
        except Exception:
            return False

    def _load_galactic_news(self):
        try:
            if not os.path.exists(self.galactic_news_path):
                return {"items": []}
            with open(self.galactic_news_path, "r", encoding="utf-8") as fh:
                payload = json.load(fh)
            if not isinstance(payload, dict):
                return {"items": []}
            items = payload.get("items", [])
            if not isinstance(items, list):
                items = []
            return {"items": items}
        except Exception:
            return {"items": []}

    def _save_galactic_news(self, payload):
        try:
            with open(self.galactic_news_path, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, indent=4)
            return True
        except Exception:
            return False

    def _append_galactic_news(
        self,
        title,
        body,
        event_type="general",
        planet_name=None,
        audience="global",
        player_name=None,
    ):
        news = self._load_galactic_news()
        items = list(news.get("items", []))

        now = float(time.time())
        keep_after = now - (86400 * int(self.galactic_news_retention_days))
        items = [
            item for item in items if float(item.get("timestamp", 0)) >= keep_after
        ]

        entry_id = int(now * 1000)
        items.append(
            {
                "id": entry_id,
                "timestamp": now,
                "event_type": str(event_type),
                "title": str(title),
                "body": str(body),
                "planet": str(planet_name) if planet_name else None,
                "audience": str(audience),
                "player": str(player_name) if player_name else None,
            }
        )

        if len(items) > 1200:
            items = items[-1200:]

        news["items"] = items
        self._save_galactic_news(news)

    def get_unseen_galactic_news(self, lookback_days=None):
        if not self.player:
            return []

        days = int(
            lookback_days
            if lookback_days is not None
            else self.config.get("galactic_news_window_days")
        )
        days = max(1, min(30, days))

        now = float(time.time())
        since = now - (86400 * days)
        seen_after = float(getattr(self.player, "last_seen_news_timestamp", 0.0) or 0.0)
        player_name = str(self.player.name)

        entries = []
        for item in self._load_galactic_news().get("items", []):
            ts = float(item.get("timestamp", 0.0))
            if ts < since or ts <= seen_after:
                continue

            audience = str(item.get("audience", "global"))
            target_player = item.get("player")
            if audience == "player" and str(target_player) != player_name:
                continue

            entries.append(item)

        entries.sort(key=lambda e: float(e.get("timestamp", 0.0)), reverse=True)
        return entries

    def has_unseen_galactic_news(self, lookback_days=None):
        return len(self.get_unseen_galactic_news(lookback_days=lookback_days)) > 0

    def mark_galactic_news_seen(self):
        if not self.player:
            return False
        self.player.last_seen_news_timestamp = float(time.time())
        self.save_game()
        return True

    def new_game(self, player_name):
        self._process_scheduled_game_reset_if_due()
        # Create a new player with configured starting credits
        starting_credits = self.config.get("starting_credits")
        first_spaceship = self.spaceships[0].clone()
        self.player = Player(
            name=player_name, spaceship=first_spaceship, credits=starting_credits
        )
        if not hasattr(self, "account_name") or not self.account_name:
            self.account_name = str(player_name or "").strip().lower().replace(" ", "_")
        self.character_name = str(player_name or "").strip().lower().replace(" ", "_")
        self.player.combat_win_streak = 0
        self.player.combat_lifetime_wins = 0
        self.player.port_visits = {}
        self.player.last_commander_stipend_time = time.time()
        self.player.sector_reputation = 0
        self.player.authority_standing = 0
        self.player.frontier_standing = 0
        self.player.contract_chain_streak = 0
        self.player.last_seen_news_timestamp = 0.0
        self.player.last_sector_report_time = time.time()
        self.planet_heat = {}
        self.last_heat_decay_time = time.time()
        self.planet_events = {}
        self.market_momentum = {}
        self.market_trade_volume = {}
        self.last_market_update_time = time.time()
        self.bribe_registry = {}
        self.bribed_planets = set()
        self._load_shared_planet_states()
        self.current_planet = self.planets[0]  # Start at first planet
        self._maybe_roll_planet_event(self.current_planet)
        self._set_port_spotlight_deal(self.current_planet)
        self._generate_trade_contract(force=True)
        self.save_game()

        # Return welcome data
        return {
            "message": f"Welcome to Galactic Trader, Commander {self.player.name}!",
            "ship_info": self.player.spaceship.get_ship_info(),
            "credits": self.player.credits,
            "planet_count": len(self.planets),
        }

    def save_game(self):
        if not self.player:
            return False

        data = {
            "last_save_timestamp": time.time(),
            "account_name": str(getattr(self, "account_name", "") or "")
            .strip()
            .lower(),
            "character_name": str(
                getattr(self, "character_name", self.player.name) or self.player.name
            )
            .strip()
            .lower()
            .replace(" ", "_"),
            "player": {
                "name": self.player.name,
                "credits": self.player.credits,
                "bank_balance": self.player.bank_balance,
                "inventory": self.player.inventory,
                "owned_planets": self.player.owned_planets,
                "barred_planets": self.player.barred_planets,
                "attacked_planets": getattr(self.player, "attacked_planets", {}),
                "combat_win_streak": int(getattr(self.player, "combat_win_streak", 0)),
                "combat_lifetime_wins": int(
                    getattr(self.player, "combat_lifetime_wins", 0)
                ),
                "last_special_weapon_time": float(
                    getattr(self.player, "last_special_weapon_time", 0.0)
                ),
                "port_visits": getattr(self.player, "port_visits", {}),
                "last_commander_stipend_time": float(
                    getattr(self.player, "last_commander_stipend_time", time.time())
                ),
                "last_sector_report_time": float(
                    getattr(self.player, "last_sector_report_time", time.time())
                ),
                "sector_reputation": int(getattr(self.player, "sector_reputation", 0)),
                "authority_standing": int(
                    getattr(
                        self.player,
                        "authority_standing",
                        int(getattr(self.player, "sector_reputation", 0)),
                    )
                ),
                "frontier_standing": int(getattr(self.player, "frontier_standing", 0)),
                "contract_chain_streak": int(
                    getattr(self.player, "contract_chain_streak", 0)
                ),
                "last_seen_news_timestamp": float(
                    getattr(self.player, "last_seen_news_timestamp", 0.0)
                ),
                "refuel_uses_in_window": int(
                    getattr(self.player, "refuel_uses_in_window", 0)
                ),
                "refuel_window_started_at": float(
                    getattr(self.player, "refuel_window_started_at", 0.0)
                ),
                "crew": {s: m.to_dict() for s, m in self.player.crew.items()},
                "last_crew_pay_time": self.player.last_crew_pay_time,
                "messages": [m.to_dict() for m in self.player.messages],
                "spaceship": {
                    "model": self.player.spaceship.model,
                    "max_cargo": self.player.spaceship.max_cargo_pods,
                    "max_shields": self.player.spaceship.max_shields,
                    "max_defenders": self.player.spaceship.max_defenders,
                    "current_cargo": self.player.spaceship.current_cargo_pods,
                    "current_shields": self.player.spaceship.current_shields,
                    "current_defenders": self.player.spaceship.current_defenders,
                    "integrity": self.player.spaceship.integrity,
                    "max_integrity": self.player.spaceship.max_integrity,
                    "fuel": self.player.spaceship.fuel,
                    "special_weapon": self.player.spaceship.special_weapon,
                    "role_tags": list(getattr(self.player.spaceship, "role_tags", [])),
                    "module_slots": int(
                        getattr(self.player.spaceship, "module_slots", 2)
                    ),
                    "installed_modules": list(
                        getattr(self.player.spaceship, "installed_modules", [])
                    ),
                    "last_refuel_time": self.player.spaceship.last_refuel_time,
                },
            },
            "current_planet_name": (
                self.current_planet.name
                if self.current_planet
                else self.planets[0].name
            ),
            "bribed_planets": list(self.bribed_planets),
            "bribe_registry": self.bribe_registry,
            "planets_smuggling": {
                p.name: p.smuggling_inventory
                for p in self.planets
                if p.smuggling_inventory
            },
            "planet_states": self._collect_planet_states(),
            "active_trade_contract": self.active_trade_contract,
            "current_port_spotlight": self.current_port_spotlight,
            "law_heat": {
                "levels": {k: int(v) for k, v in self.planet_heat.items()},
                "last_decay": float(self.last_heat_decay_time),
            },
            "planet_events": self.planet_events,
            "economy_state": {
                "momentum": self.market_momentum,
                "volume": self.market_trade_volume,
                "last_update": float(self.last_market_update_time),
            },
        }

        filename = f"{self.player.name.replace(' ', '_').lower()}.json"
        path = os.path.join(self.save_dir, filename)
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
        self._save_shared_planet_states()
        self._evaluate_and_record_winner()
        if hasattr(self, "_persist_analytics_snapshot"):
            self._persist_analytics_snapshot(force=True)
        return True

    def load_game(self, player_name):
        self._process_scheduled_game_reset_if_due()
        filename = f"{player_name.replace(' ', '_').lower()}.json"
        path = os.path.join(self.save_dir, filename)
        if not os.path.exists(path):
            return False, "Save file not found."

        try:
            with open(path, "r") as f:
                data = json.load(f)

            p_data = data["player"]
            s_data = p_data["spaceship"]

            # Find the ship template from templates to restore starting stats
            templates = self.spaceships
            template = next(
                (t for t in templates if t.model == s_data["model"]), templates[0]
            )

            ship = Spaceship(
                model=s_data["model"],
                cost=template.cost,
                starting_cargo_pods=template.starting_cargo_pods,
                starting_shields=template.starting_shields,
                starting_defenders=template.starting_defenders,
                max_cargo_pods=int(s_data["max_cargo"]),
                max_shields=int(s_data["max_shields"]),
                max_defenders=int(s_data["max_defenders"]),
                special_weapon=s_data.get("special_weapon"),
                role_tags=s_data.get("role_tags", getattr(template, "role_tags", [])),
                module_slots=s_data.get(
                    "module_slots", getattr(template, "module_slots", 2)
                ),
                installed_modules=s_data.get(
                    "installed_modules", getattr(template, "installed_modules", [])
                ),
            )
            ship.current_cargo_pods = int(s_data["current_cargo"])
            ship.current_shields = int(s_data["current_shields"])
            ship.current_defenders = int(s_data["current_defenders"])
            ship.integrity = int(s_data["integrity"])
            # Load max_integrity if available, else use template default
            ship.max_integrity = int(s_data.get("max_integrity", ship.max_integrity))
            ship.fuel = s_data["fuel"]
            ship.last_refuel_time = s_data["last_refuel_time"]

            self.player = Player(
                name=p_data["name"], spaceship=ship, credits=int(p_data["credits"])
            )
            self.account_name = (
                str(data.get("account_name") or data.get("player", {}).get("name", ""))
                .strip()
                .lower()
                .replace(" ", "_")
            )
            self.character_name = (
                str(
                    data.get("character_name") or data.get("player", {}).get("name", "")
                )
                .strip()
                .lower()
                .replace(" ", "_")
            )
            self.player.bank_balance = int(p_data.get("bank_balance", 0))
            self.player.inventory = p_data["inventory"]
            self._normalize_player_inventory()
            self.player.owned_planets = p_data.get("owned_planets", {})
            self.player.barred_planets = p_data.get("barred_planets", {})
            self.player.attacked_planets = p_data.get("attacked_planets", {})
            self.player.combat_win_streak = int(p_data.get("combat_win_streak", 0))
            self.player.combat_lifetime_wins = int(
                p_data.get("combat_lifetime_wins", 0)
            )
            self.player.last_special_weapon_time = float(
                p_data.get("last_special_weapon_time", 0.0)
            )
            self.player.port_visits = p_data.get("port_visits", {})
            self.player.last_commander_stipend_time = float(
                p_data.get("last_commander_stipend_time", time.time())
            )
            self.player.last_sector_report_time = float(
                p_data.get("last_sector_report_time", time.time())
            )
            legacy_rep = int(p_data.get("sector_reputation", 0))
            self.player.authority_standing = int(
                p_data.get("authority_standing", legacy_rep)
            )
            self.player.frontier_standing = int(p_data.get("frontier_standing", 0))
            self.player.sector_reputation = int(self.player.authority_standing)
            self.player.contract_chain_streak = int(
                p_data.get("contract_chain_streak", 0)
            )
            self.player.last_seen_news_timestamp = float(
                p_data.get("last_seen_news_timestamp", 0.0)
            )
            self.player.refuel_uses_in_window = int(
                p_data.get("refuel_uses_in_window", 0)
            )
            self.player.refuel_window_started_at = float(
                p_data.get("refuel_window_started_at", 0.0)
            )
            from classes import CrewMember, Message

            self.player.crew = {
                s: CrewMember.from_dict(d) for s, d in p_data.get("crew", {}).items()
            }
            self.player.last_crew_pay_time = p_data.get(
                "last_crew_pay_time", time.time()
            )
            self.player.messages = [
                Message.from_dict(m) for m in p_data.get("messages", [])
            ]

            # Load smuggling and bribe state
            self.bribe_registry = {}
            raw_registry = data.get("bribe_registry", {}) or {}
            if isinstance(raw_registry, dict):
                for p_name, state in raw_registry.items():
                    if not isinstance(state, dict):
                        continue
                    level = max(0, int(state.get("level", 0)))
                    expires_at = float(state.get("expires_at", 0.0))
                    if level <= 0:
                        continue
                    self.bribe_registry[str(p_name)] = {
                        "level": int(level),
                        "expires_at": float(expires_at),
                    }

            legacy_bribed = set(data.get("bribed_planets", []))
            if legacy_bribed and not self.bribe_registry:
                now = time.time()
                base_h = max(
                    1.0, float(self.config.get("bribe_base_duration_hours"))
                )
                for p_name in legacy_bribed:
                    self.bribe_registry[str(p_name)] = {
                        "level": 1,
                        "expires_at": now + (base_h * 3600.0),
                    }

            self._refresh_bribe_registry()
            p_smug_data = data.get("planets_smuggling", {})
            for p in self.planets:
                if p.name in p_smug_data:
                    p.smuggling_inventory = p_smug_data[p.name]

            # Character saves must not override ownership – universe_planets.json
            # is loaded immediately after and is the sole authority for that field.
            self._apply_planet_states(
                data.get("planet_states", {}), apply_ownership=False
            )
            self._load_shared_planet_states()

            # Find current planet
            p_name = data.get("current_planet_name")
            self.current_planet = next(
                (p for p in self.planets if p.name == p_name), self.planets[0]
            )

            self.active_trade_contract = data.get("active_trade_contract")
            self.current_port_spotlight = data.get("current_port_spotlight")

            heat_state = data.get("law_heat", {})
            self.planet_heat = {
                str(k): int(v)
                for k, v in (heat_state.get("levels", {}) or {}).items()
                if int(v) > 0
            }
            self.last_heat_decay_time = float(heat_state.get("last_decay", time.time()))
            self._update_law_heat_decay()

            self.planet_events = data.get("planet_events", {}) or {}
            self._update_planet_events()

            economy_state = data.get("economy_state", {}) or {}
            self.market_momentum = {
                str(p): {
                    str(i): float(v)
                    for i, v in (items or {}).items()
                    if abs(float(v)) > 0
                }
                for p, items in (economy_state.get("momentum", {}) or {}).items()
                if items
            }
            self.market_trade_volume = {
                str(p): {
                    str(i): float(v) for i, v in (items or {}).items() if float(v) > 0
                }
                for p, items in (economy_state.get("volume", {}) or {}).items()
                if items
            }
            self.last_market_update_time = float(
                economy_state.get("last_update", time.time())
            )
            self._update_market_dynamics()

            self.get_active_trade_contract()
            if not self.active_trade_contract:
                self._generate_trade_contract(force=True)
            if not self.get_current_port_spotlight_deal():
                self._set_port_spotlight_deal(self.current_planet)

            return True, "Game loaded successfully."
        except Exception as e:
            return False, f"Error loading save: {e}"

    def list_saves(self):
        if not os.path.exists(self.save_dir):
            return []
        saves = []
        for f in os.listdir(self.save_dir):
            if f.endswith(".json"):
                # We can read the name from the file if we want, or use filename
                saves.append(f.replace(".json", "").replace("_", " ").upper())
        return saves

    def _iter_commander_save_paths(self):
        """Yield all commander save file paths across root and account subdirs."""
        global_save_root = (
            os.path.dirname(getattr(self, "shared_planet_state_path", ""))
            or self.save_dir
        )
        seen = set()
        ignored = {
            "universe_planets.json",
            "galactic_news.json",
            "winner_board.json",
            "account.json",
        }

        if not os.path.exists(global_save_root):
            return []

        paths = []
        for root, _, files in os.walk(global_save_root):
            for file_name in files:
                file_lower = str(file_name).lower()
                if not file_lower.endswith(".json"):
                    continue
                if file_lower in ignored:
                    continue

                full_path = os.path.join(root, file_name)
                norm = os.path.normcase(os.path.abspath(full_path))
                if norm in seen:
                    continue
                seen.add(norm)
                paths.append(full_path)

        return paths

    def _find_commander_save_path_by_name(self, recipient_name):
        target = str(recipient_name or "").strip().lower()
        if not target:
            return ""

        for path in self._iter_commander_save_paths():
            try:
                with open(path, "r", encoding="utf-8") as file:
                    data = json.load(file)
            except Exception:
                continue

            if not isinstance(data, dict):
                continue
            if str(data.get("password_hash") or "").strip():
                continue

            player_data = (
                data.get("player") if isinstance(data.get("player"), dict) else {}
            )
            name = str(player_data.get("name") or "").strip()
            if name and name.lower() == target:
                return path

        return ""

    def get_other_players(self):
        """Returns names of all commanders except the current commander."""
        players = []
        seen = set()
        current_name = str(getattr(self.player, "name", "") or "").strip().lower()

        for path in self._iter_commander_save_paths():
            try:
                with open(path, "r", encoding="utf-8") as file:
                    data = json.load(file)
            except Exception:
                continue

            if not isinstance(data, dict):
                continue
            if str(data.get("password_hash") or "").strip():
                continue

            player_data = (
                data.get("player") if isinstance(data.get("player"), dict) else {}
            )
            name = str(player_data.get("name") or "").strip()
            if not name:
                continue

            key = name.lower()
            if key == current_name or key in seen:
                continue

            seen.add(key)
            players.append(name)

        return sorted(players, key=lambda value: value.lower())

    def _ship_level_for_model(self, ship_model):
        model_key = str(ship_model or "").strip().lower()
        if not model_key:
            return 1
        for idx, ship in enumerate(
            list(getattr(self, "spaceships", []) or []), start=1
        ):
            if str(getattr(ship, "model", "")).strip().lower() == model_key:
                return int(idx)
        return 1

    def get_all_commander_statuses(self):
        """Return full commander status rows for commander overview UI."""
        planet_states = self._collect_planet_states()
        owned_by_commander = {}
        colony_credits_by_commander = {}
        for planet_name, state in (planet_states or {}).items():
            owner = str((state or {}).get("owner") or "").strip()
            if not owner:
                continue
            owner_key = owner.lower()
            owned_by_commander.setdefault(owner_key, []).append(str(planet_name))
            colony_credits_by_commander[owner_key] = int(
                colony_credits_by_commander.get(owner_key, 0)
            ) + int((state or {}).get("credit_balance", 0) or 0)

        active_name = (
            str(getattr(getattr(self, "player", None), "name", "") or "")
            .strip()
            .lower()
        )
        rows = []
        seen = set()

        for path in self._iter_commander_save_paths():
            try:
                with open(path, "r", encoding="utf-8") as file:
                    data = json.load(file)
            except Exception:
                continue

            if not isinstance(data, dict):
                continue
            if str(data.get("password_hash") or "").strip():
                continue

            player_data = (
                data.get("player") if isinstance(data.get("player"), dict) else {}
            )
            name = str(player_data.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)

            ship_data = (
                player_data.get("spaceship")
                if isinstance(player_data.get("spaceship"), dict)
                else {}
            )
            ship_model = str(ship_data.get("model") or "Unknown")
            ship_level = self._ship_level_for_model(ship_model)
            location = str(data.get("current_planet_name") or "Unknown")

            credits = int(player_data.get("credits", 0) or 0)
            bank_balance = int(player_data.get("bank_balance", 0) or 0)
            colony_credits = int(colony_credits_by_commander.get(key, 0) or 0)
            owned_planets = sorted(
                [str(p) for p in owned_by_commander.get(key, [])],
                key=lambda value: value.lower(),
            )

            rows.append(
                {
                    "name": name,
                    "status": "ACTIVE" if key == active_name else "OFFLINE",
                    "level": int(ship_level),
                    "ship": ship_model,
                    "location": location,
                    "owned_planets_count": int(len(owned_planets)),
                    "owned_planets": owned_planets,
                    "credits": credits,
                    "bank_balance": bank_balance,
                    "colony_credits": colony_credits,
                    "total_credits": int(credits + bank_balance + colony_credits),
                }
            )

        rows.sort(
            key=lambda row: (
                int(row.get("owned_planets_count", 0)),
                int(row.get("total_credits", 0)),
                str(row.get("name", "")).lower(),
            ),
            reverse=True,
        )
        return rows

    def _ship_level_for_model(self, ship_model):
        model_key = str(ship_model or "").strip().lower()
        if not model_key:
            return 1
        for idx, ship in enumerate(
            list(getattr(self, "spaceships", []) or []), start=1
        ):
            if str(getattr(ship, "model", "")).strip().lower() == model_key:
                return int(idx)
        return 1

    def get_all_commander_statuses(self):
        """Return full commander status rows for admin/overview UI."""
        planet_states = self._collect_planet_states()
        owned_by_commander = {}
        colony_credits_by_commander = {}
        for planet_name, state in (planet_states or {}).items():
            owner = str((state or {}).get("owner") or "").strip()
            if not owner:
                continue
            owner_key = owner.lower()
            owned_by_commander.setdefault(owner_key, []).append(str(planet_name))
            colony_credits_by_commander[owner_key] = int(
                colony_credits_by_commander.get(owner_key, 0)
            ) + int((state or {}).get("credit_balance", 0) or 0)

        active_name = (
            str(getattr(getattr(self, "player", None), "name", "") or "")
            .strip()
            .lower()
        )
        rows = []
        seen = set()

        for path in self._iter_commander_save_paths():
            try:
                with open(path, "r", encoding="utf-8") as file:
                    data = json.load(file)
            except Exception:
                continue

            if not isinstance(data, dict):
                continue
            if str(data.get("password_hash") or "").strip():
                continue

            player_data = (
                data.get("player") if isinstance(data.get("player"), dict) else {}
            )
            name = str(player_data.get("name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)

            ship_data = (
                player_data.get("spaceship")
                if isinstance(player_data.get("spaceship"), dict)
                else {}
            )
            ship_model = str(ship_data.get("model") or "Unknown")
            ship_level = self._ship_level_for_model(ship_model)
            location = str(data.get("current_planet_name") or "Unknown")

            credits = int(player_data.get("credits", 0) or 0)
            bank_balance = int(player_data.get("bank_balance", 0) or 0)
            colony_credits = int(colony_credits_by_commander.get(key, 0) or 0)

            owned_planets = sorted(
                [str(p) for p in owned_by_commander.get(key, [])],
                key=lambda value: value.lower(),
            )

            rows.append(
                {
                    "name": name,
                    "status": "ACTIVE" if key == active_name else "OFFLINE",
                    "level": int(ship_level),
                    "ship": ship_model,
                    "location": location,
                    "owned_planets_count": int(len(owned_planets)),
                    "owned_planets": owned_planets,
                    "credits": credits,
                    "bank_balance": bank_balance,
                    "colony_credits": colony_credits,
                    "total_credits": int(credits + bank_balance + colony_credits),
                }
            )

        rows.sort(
            key=lambda row: (
                int(row.get("owned_planets_count", 0)),
                int(row.get("total_credits", 0)),
                str(row.get("name", "")).lower(),
            ),
            reverse=True,
        )
        return rows

    def send_message(self, recipient_name, subject, body, sender_name=None):
        """Sends a text message to another player's mailbox."""
        from classes import Message

        actual_sender = sender_name or self.player.name
        msg = Message(actual_sender, recipient_name, subject, body)

        if recipient_name == self.player.name:
            self.player.add_message(msg)
        else:
            path = self._find_commander_save_path_by_name(recipient_name)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if "player" in data:
                    if "messages" not in data["player"]:
                        data["player"]["messages"] = []
                    data["player"]["messages"].append(msg.to_dict())
                    with open(path, "w", encoding="utf-8") as f:
                        json.dump(data, f, indent=4)
                    return True, "Message sent."
        return False, "Failed to send message."

    def get_player_info(self):
        if self.player:
            self._normalize_player_inventory()
            # Automatic refuel check
            self.check_auto_refuel()
            # Payout interest
            self.payout_interest()
            # Crew pay
            self.process_crew_pay()
            # Random signals
            self.process_random_signals()
            self.process_commander_stipend()
            self._send_sector_report_if_due()
            self.get_active_trade_contract()
            return self.player.get_info()
        return None
