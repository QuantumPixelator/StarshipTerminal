import time
import json
import os
from datetime import datetime, timedelta
from classes import Player, Spaceship


class PersistenceMixin:
    UNIVERSE_SCHEMA_VERSION = 2
    COMMANDER_SCHEMA_VERSION = 2

    def _default_winner_board_state(self):
        return {
            "current_winner": None,
            "scheduled_reset_ts": None,
            "last_reset_ts": None,
            "history": [],
        }

    def _load_commander_payload_by_ref(self, path):
        ref = str(path or "").strip()
        if not ref:
            return None
        try:
            if not ref.startswith("db://") or getattr(self, "store", None) is None:
                return None
            _, _, remainder = ref.partition("db://")
            account_name, _, character_name = remainder.partition("/")
            payload = self.store.get_character_payload(account_name, character_name)
            return payload if isinstance(payload, dict) else None
        except Exception:
            return None

    def _load_winner_board_state(self):
        if getattr(self, "store", None) is None:
            return self._default_winner_board_state()

        payload = self.store.get_kv("shared", "winner_board", default=None)
        if not isinstance(payload, dict):
            return self._default_winner_board_state()
        state = self._default_winner_board_state()
        state.update(payload)
        history = state.get("history", [])
        state["history"] = history if isinstance(history, list) else []
        return state

    def _save_winner_board_state(self, state):
        if getattr(self, "store", None) is None:
            return False
        try:
            self.store.set_kv("shared", "winner_board", dict(state or {}))
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
        total_strategic_resources = 0
        for path in self._iter_commander_save_paths():
            data = self._load_commander_payload_by_ref(path)
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
            player_id = None
            resource_total = 0
            resources_map = {
                "fuel": 0,
                "ore": 0,
                "tech": 0,
                "bio": 0,
                "rare": 0,
            }
            if getattr(self, "store", None) is not None:
                try:
                    ref = str(path or "")
                    ref_account = ""
                    ref_character = ""
                    if ref.startswith("db://"):
                        _, _, remainder = ref.partition("db://")
                        ref_account, _, ref_character = remainder.partition("/")
                    player_id = self.store.get_character_player_id(
                        data.get("account_name") or ref_account,
                        data.get("character_name") or ref_character,
                    )
                except Exception:
                    player_id = None
            if player_id is not None and getattr(self, "store", None) is not None:
                stored_resources = self.store.get_player_resources(player_id)
                for r_key in ("fuel", "ore", "tech", "bio", "rare"):
                    amount = int(stored_resources.get(r_key, 0) or 0)
                    resources_map[r_key] = amount
                    resource_total += amount
            total_strategic_resources += int(resource_total)

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
                    "resource_total": int(resource_total),
                    "resources": resources_map,
                }
            )

        strategic_total = max(1, int(total_strategic_resources))
        for row in commanders:
            own_total = int(row.get("resource_total", 0) or 0)
            row["resource_share_pct"] = round((own_total / float(strategic_total)) * 100.0, 2)

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
            "total_strategic_resources": int(total_strategic_resources),
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
            data = self._load_commander_payload_by_ref(path)
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
        min_resource_share = float(self.config.get("victory_resource_share_pct", 0) or 0)
        min_credit_hoard = int(self.config.get("victory_credit_hoard", 0) or 0)

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
            if min_resource_share > 0.0:
                if float(row.get("resource_share_pct", 0.0) or 0.0) < min_resource_share:
                    continue
            if min_credit_hoard > 0:
                if int(row.get("total_credits", 0) or 0) < min_credit_hoard:
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
            "resource_total": int(winner.get("resource_total", 0)),
            "resource_share_pct": float(winner.get("resource_share_pct", 0.0)),
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
            f"Strategic resource share: {winner_record['resource_share_pct']:.1f}% (total {winner_record['resource_total']:,}). "
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
                ref = str(path or "").strip()
                if ref.startswith("db://") and getattr(self, "store", None) is not None:
                    _, _, remainder = ref.partition("db://")
                    account_name, _, character_name = remainder.partition("/")
                    if self.store.delete_character(account_name, character_name):
                        removed += 1
                    continue
                os.remove(ref)
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
            str(getattr(p, "planet_id", 0)): {
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
            state = planet_states.get(str(getattr(p, "planet_id", "")))
            if not isinstance(state, dict):
                # Legacy compatibility for pre-migration name-keyed states.
                state = planet_states.get(getattr(p, "name", ""))
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
        if getattr(self, "store", None) is None:
            return False
        try:
            payload = {
                "schema_version": int(self.UNIVERSE_SCHEMA_VERSION),
                "updated_at": float(time.time()),
                "planet_states": self._collect_planet_states(),
            }
            self.store.set_kv("shared", "universe_planets", payload)
            return True
        except Exception:
            return False

    def _load_shared_planet_states(self):
        if getattr(self, "store", None) is None:
            return False
        try:
            payload = self.store.get_kv("shared", "universe_planets", default=None)
            if not isinstance(payload, dict):
                raise ValueError("Invalid universe state payload")
            schema_version = int(payload.get("schema_version", 1) or 1)
            if schema_version < int(self.UNIVERSE_SCHEMA_VERSION):
                # Allow legacy files to load only for migration mode.
                pass
            self._apply_planet_states(payload.get("planet_states", {}))
            return True
        except Exception:
            return False

    def _load_galactic_news(self):
        if getattr(self, "store", None) is None:
            return {"items": []}
        try:
            payload = self.store.get_kv("shared", "galactic_news", default=None)
            if not isinstance(payload, dict):
                return {"items": []}
            items = payload.get("items", [])
            if not isinstance(items, list):
                items = []
            return {"items": items}
        except Exception:
            return {"items": []}

    def _save_galactic_news(self, payload):
        if getattr(self, "store", None) is None:
            return False
        try:
            self.store.set_kv("shared", "galactic_news", payload)
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

    def _resolve_planet_id_from_any_key(self, raw_key):
        normalized = self.normalize_planet_id(raw_key)
        if normalized is not None and self.get_planet_by_id(normalized):
            return normalized
        return self.get_planet_id_by_name(raw_key)

    def _convert_dict_keys_to_planet_ids(self, payload):
        converted = {}
        if not isinstance(payload, dict):
            return converted
        for raw_key, value in payload.items():
            planet_id = self._resolve_planet_id_from_any_key(raw_key)
            if planet_id is None:
                continue
            converted[str(planet_id)] = value
        return converted

    def _planet_name_from_id_key(self, key):
        planet_id = self._resolve_planet_id_from_any_key(key)
        if planet_id is None:
            return None
        planet = self.get_planet_by_id(planet_id)
        if not planet:
            return None
        return str(getattr(planet, "name", ""))

    def _sync_player_owned_planets_from_universe(self):
        if not getattr(self, "player", None):
            return
        owner_key = str(getattr(self.player, "name", "") or "").strip().lower()
        if not owner_key:
            self.player.owned_planets = {}
            return
        owned = {}
        for planet in list(getattr(self, "planets", []) or []):
            if str(getattr(planet, "owner", "") or "").strip().lower() != owner_key:
                continue
            owned[str(getattr(planet, "planet_id", ""))] = True
        self.player.owned_planets = owned

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
        self.player.last_resource_interest_time = time.time()
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
        self.mark_state_dirty()
        self.save_game(force=True)

        # Return welcome data
        return {
            "message": f"Welcome to Galactic Trader, Commander {self.player.name}!",
            "ship_info": self.player.spaceship.get_ship_info(),
            "credits": self.player.credits,
            "planet_count": len(self.planets),
        }

    def _build_save_payload(self):
        if not self.player:
            return None

        return {
            "schema_version": int(self.COMMANDER_SCHEMA_VERSION),
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
                "last_resource_interest_time": float(
                    getattr(self.player, "last_resource_interest_time", time.time())
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
                "is_docked": bool(getattr(self.player, "is_docked", False)),
                "smuggling_runs": int(getattr(self.player, "smuggling_runs", 0)),
                "smuggling_units_moved": int(
                    getattr(self.player, "smuggling_units_moved", 0)
                ),
                "bribes_paid_total": int(getattr(self.player, "bribes_paid_total", 0)),
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
            "current_planet_id": int(
                self.get_current_planet_id()
                or getattr(self.planets[0], "planet_id", 1)
            ),
            "bribed_planets": [
                str(pid)
                for pid in [self._resolve_planet_id_from_any_key(v) for v in list(self.bribed_planets)]
                if pid is not None
            ],
            "bribe_registry": self._convert_dict_keys_to_planet_ids(self.bribe_registry),
            "planets_smuggling": {
                str(getattr(p, "planet_id", "")): p.smuggling_inventory
                for p in self.planets
                if p.smuggling_inventory
            },
            "active_trade_contract": self.active_trade_contract,
            "current_port_spotlight": self.current_port_spotlight,
            "law_heat": {
                "levels": {
                    str(pid): int(v)
                    for k, v in self.planet_heat.items()
                    for pid in [self._resolve_planet_id_from_any_key(k)]
                    if pid is not None
                },
                "last_decay": float(self.last_heat_decay_time),
            },
            "planet_events": self._convert_dict_keys_to_planet_ids(self.planet_events),
            "economy_state": {
                "momentum": {
                    str(pid): dict(items or {})
                    for key, items in (self.market_momentum or {}).items()
                    for pid in [self._resolve_planet_id_from_any_key(key)]
                    if pid is not None
                },
                "volume": {
                    str(pid): dict(items or {})
                    for key, items in (self.market_trade_volume or {}).items()
                    for pid in [self._resolve_planet_id_from_any_key(key)]
                    if pid is not None
                },
                "last_update": float(self.last_market_update_time),
            },
        }

    def _save_game_now(self):
        if not self.player:
            return False

        data = self._build_save_payload()
        if data is None:
            return False

        char_safe = str(
            getattr(self, "character_name", self.player.name) or self.player.name
        ).strip().lower().replace(" ", "_")
        account_safe = str(
            getattr(self, "account_name", char_safe) or char_safe
        ).strip().lower().replace(" ", "_")

        if getattr(self, "store", None) is None:
            return False
        self.store.upsert_character_payload(
            account_safe,
            char_safe,
            data,
            display_name=str(self.player.name),
        )
        self._save_shared_planet_states()
        self._evaluate_and_record_winner()
        if hasattr(self, "_persist_analytics_snapshot"):
            self._persist_analytics_snapshot(force=True)
        self._save_dirty = False
        self._last_save_completed_at = float(time.time())
        return True

    def save_game(self, force=False):
        if not self.player:
            return False

        if force:
            return self._save_game_now()

        self._save_dirty = True
        self._save_requested_at = float(time.time())
        return True

    def flush_pending_save(self, force=False):
        if not self.player:
            return False
        if not bool(getattr(self, "_save_dirty", False)):
            return True

        if not force:
            requested_at = float(getattr(self, "_save_requested_at", 0.0) or 0.0)
            debounce = float(getattr(self, "save_debounce_seconds", 2.5) or 2.5)
            if (time.time() - requested_at) < debounce:
                return True

        return self._save_game_now()

    def load_game(self, player_name):
        self._process_scheduled_game_reset_if_due()
        data = None
        account_safe = str(getattr(self, "account_name", "") or "").strip().lower().replace(" ", "_")
        character_safe = str(player_name or "").strip().lower().replace(" ", "_")

        if getattr(self, "store", None) is not None:
            if account_safe and character_safe:
                data = self.store.get_character_payload(account_safe, character_safe)
            if not isinstance(data, dict) and character_safe:
                lookup = self.store.find_character_payload_by_name(character_safe)
                if isinstance(lookup, dict):
                    data = dict(lookup.get("payload") or {})
                    self.account_name = str(lookup.get("account_name") or account_safe)
                    self.character_name = str(lookup.get("character_name") or character_safe)

        if not isinstance(data, dict):
            return False, "Save profile not found."

        try:
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
            self.player.owned_planets = {}
            self.player.barred_planets = self._convert_dict_keys_to_planet_ids(
                p_data.get("barred_planets", {})
            )
            self.player.attacked_planets = self._convert_dict_keys_to_planet_ids(
                p_data.get("attacked_planets", {})
            )
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
            self.player.last_resource_interest_time = float(
                p_data.get("last_resource_interest_time", time.time())
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
            self.player.is_docked = bool(p_data.get("is_docked", False))
            self.player.smuggling_runs = int(p_data.get("smuggling_runs", 0))
            self.player.smuggling_units_moved = int(
                p_data.get("smuggling_units_moved", 0)
            )
            self.player.bribes_paid_total = int(p_data.get("bribes_paid_total", 0))
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
                for raw_key, state in raw_registry.items():
                    if not isinstance(state, dict):
                        continue
                    planet_id = self._resolve_planet_id_from_any_key(raw_key)
                    if planet_id is None:
                        continue
                    level = max(0, int(state.get("level", 0)))
                    expires_at = float(state.get("expires_at", 0.0))
                    if level <= 0:
                        continue
                    self.bribe_registry[str(planet_id)] = {
                        "level": int(level),
                        "expires_at": float(expires_at),
                    }

            legacy_bribed = set(data.get("bribed_planets", []))
            if legacy_bribed and not self.bribe_registry:
                now = time.time()
                base_h = max(
                    1.0, float(self.config.get("bribe_base_duration_hours"))
                )
                for raw_key in legacy_bribed:
                    planet_id = self._resolve_planet_id_from_any_key(raw_key)
                    if planet_id is None:
                        continue
                    self.bribe_registry[str(planet_id)] = {
                        "level": 1,
                        "expires_at": now + (base_h * 3600.0),
                    }

            self._refresh_bribe_registry()
            p_smug_data = data.get("planets_smuggling", {})
            for p in self.planets:
                state = p_smug_data.get(str(getattr(p, "planet_id", "")))
                if state is None:
                    state = p_smug_data.get(str(getattr(p, "name", "")))
                if isinstance(state, dict):
                    p.smuggling_inventory = state

            # Character saves must not carry authoritative ownership/planet state.
            self._load_shared_planet_states()
            self._sync_player_owned_planets_from_universe()

            # Find current planet
            current_planet_id = self._resolve_planet_id_from_any_key(
                data.get("current_planet_id")
            )
            if current_planet_id is None:
                current_planet_id = self._resolve_planet_id_from_any_key(
                    data.get("current_planet_name")
                )
            self.current_planet = self.get_planet_by_id(current_planet_id) or self.planets[0]

            self.active_trade_contract = data.get("active_trade_contract")
            self.current_port_spotlight = data.get("current_port_spotlight")

            heat_state = data.get("law_heat", {})
            self.planet_heat = {
                str(self._planet_name_from_id_key(k) or k): int(v)
                for k, v in (heat_state.get("levels", {}) or {}).items()
                if int(v) > 0
                and (self._planet_name_from_id_key(k) is not None)
            }
            self.last_heat_decay_time = float(heat_state.get("last_decay", time.time()))
            self._update_law_heat_decay()

            self.planet_events = {
                str(self._planet_name_from_id_key(k) or ""): dict(v or {})
                for k, v in (data.get("planet_events", {}) or {}).items()
                if self._planet_name_from_id_key(k) is not None and isinstance(v, dict)
            }
            self._update_planet_events()

            economy_state = data.get("economy_state", {}) or {}
            self.market_momentum = {
                str(self._planet_name_from_id_key(p) or ""): {
                    str(i): float(v)
                    for i, v in (items or {}).items()
                    if abs(float(v)) > 0
                }
                for p, items in (economy_state.get("momentum", {}) or {}).items()
                if items and self._planet_name_from_id_key(p) is not None
            }
            self.market_trade_volume = {
                str(self._planet_name_from_id_key(p) or ""): {
                    str(i): float(v) for i, v in (items or {}).items() if float(v) > 0
                }
                for p, items in (economy_state.get("volume", {}) or {}).items()
                if items and self._planet_name_from_id_key(p) is not None
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

            self.mark_state_dirty()

            return True, "Game loaded successfully."
        except Exception as e:
            return False, f"Error loading save: {e}"

    def list_saves(self):
        if getattr(self, "store", None) is None:
            return []
        account_safe = str(getattr(self, "account_name", "") or "").strip().lower().replace(" ", "_")
        if account_safe:
            rows = self.store.list_characters(account_safe)
        else:
            rows = self.store.iter_all_characters()
        saves = []
        for row in rows:
            display = str(row.get("display_name") or row.get("character_name") or "").strip()
            if display:
                saves.append(display.upper())
        return sorted(saves)

    def _iter_commander_save_paths(self):
        """Yield all commander save file paths across root and account subdirs."""
        if getattr(self, "store", None) is None:
            return []
        refs = []
        for row in self.store.iter_all_characters():
            account_name = str(row.get("account_name") or "").strip()
            character_name = str(row.get("character_name") or "").strip()
            if account_name and character_name:
                refs.append(f"db://{account_name}/{character_name}")
        return refs

    def _find_commander_save_path_by_name(self, recipient_name):
        target = str(recipient_name or "").strip().lower()
        if not target:
            return ""

        if getattr(self, "store", None) is not None:
            matches = []
            for row in self.store.find_character_refs_by_name(recipient_name, active_only=True):
                account_name = str(row.get("account_name") or "").strip()
                character_name = str(row.get("character_name") or "").strip()
                if account_name and character_name:
                    matches.append(f"db://{account_name}/{character_name}")
            if len(matches) == 1:
                return matches[0]
            return ""

        return ""

    def _find_commander_save_paths_by_name(self, recipient_name):
        target = str(recipient_name or "").strip().lower()
        if not target or getattr(self, "store", None) is None:
            return []

        refs = []
        for row in self.store.find_character_refs_by_name(recipient_name, active_only=True):
            account_name = str(row.get("account_name") or "").strip()
            character_name = str(row.get("character_name") or "").strip()
            if account_name and character_name:
                refs.append(f"db://{account_name}/{character_name}")
        return refs

    def get_other_players(self):
        """Returns names of all commanders except the current commander."""
        players = []
        seen = set()
        current_name = str(getattr(self.player, "name", "") or "").strip().lower()

        if getattr(self, "store", None) is not None:
            for row in self.store.iter_character_summaries(active_only=True):
                account_name = str(row.get("account_name") or "").strip()
                if not account_name:
                    continue
                name = str(row.get("display_name") or row.get("character_name") or "").strip()
                if not name:
                    continue
                key = name.lower()
                if key == current_name or key in seen:
                    continue
                seen.add(key)
                players.append(name)
            return sorted(players, key=lambda value: value.lower())
        return []

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
        for planet_id, state in (planet_states or {}).items():
            owner = str((state or {}).get("owner") or "").strip()
            if not owner:
                continue
            owner_key = owner.lower()
            owned_by_commander.setdefault(owner_key, []).append(str(planet_id))
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

        if getattr(self, "store", None) is not None:
            source_rows = self.store.iter_all_characters()
            for entry in source_rows:
                data = entry.get("payload") if isinstance(entry, dict) else None
                if not isinstance(data, dict):
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
                location = str(
                    self._planet_name_from_id_key(data.get("current_planet_id"))
                    or data.get("current_planet_name")
                    or "Unknown"
                )

                credits = int(player_data.get("credits", 0) or 0)
                bank_balance = int(player_data.get("bank_balance", 0) or 0)
                colony_credits = int(colony_credits_by_commander.get(key, 0) or 0)

                owned_planets = sorted(
                    [
                        str(self._planet_name_from_id_key(p) or p)
                        for p in owned_by_commander.get(key, [])
                    ],
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

        return []

    def send_message(self, recipient_name, subject, body, sender_name=None):
        """Sends a text message to another player's mailbox."""
        from classes import Message

        actual_sender = sender_name or self.player.name
        msg = Message(actual_sender, recipient_name, subject, body)

        if recipient_name == self.player.name:
            self.player.add_message(msg)
            return True, "Message sent."
        else:
            candidate_paths = self._find_commander_save_paths_by_name(recipient_name)
            if len(candidate_paths) > 1:
                return (
                    False,
                    "Multiple commanders match that name. Ask the recipient to choose a unique commander name.",
                )
            path = candidate_paths[0] if candidate_paths else ""
            if path.startswith("db://") and getattr(self, "store", None) is not None:
                _, _, remainder = path.partition("db://")
                account_name, _, character_name = remainder.partition("/")
                data = self.store.get_character_payload(account_name, character_name)
                if isinstance(data, dict) and "player" in data:
                    if "messages" not in data["player"]:
                        data["player"]["messages"] = []
                    data["player"]["messages"].append(msg.to_dict())
                    self.store.upsert_character_payload(
                        account_name,
                        character_name,
                        data,
                        display_name=str(data.get("player", {}).get("name") or character_name),
                    )
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
