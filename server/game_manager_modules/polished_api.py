import random
import time
from typing import Any, Dict, List, Optional


class PolishedApiMixin:
    """Phase-5 API compatibility layer for server-authoritative multiplayer actions."""

    VALID_TACTICS = {"flank", "shield up", "board", "sabotage", "full burn"}

    def _normalize_tactic(self, tactic: Any) -> str:
        value = str(tactic or "").strip().lower()
        if value in self.VALID_TACTICS:
            return value
        return "full burn"

    def _seed_planets_table_if_empty(self) -> None:
        """Mirror runtime planets into the Phase-5 planets table if it is empty."""
        if getattr(self, "store", None) is None:
            return
        existing = self.store.list_planets_rows()
        if existing:
            return

        for planet in list(getattr(self, "planets", []) or []):
            owner_name = str(getattr(planet, "owner", "") or "").strip()
            owner_id = None
            if owner_name:
                refs = self.store.find_character_refs_by_name(owner_name, active_only=False)
                if refs:
                    ref = dict(refs[0] or {})
                    owner_id = self.store.get_character_player_id(
                        ref.get("account_name"),
                        ref.get("character_name"),
                    )
            self.store.upsert_planet_row(
                planet_id=int(getattr(planet, "planet_id", 0) or 0),
                name=str(getattr(planet, "name", "") or ""),
                owner_id=owner_id,
                credit_balance=int(getattr(planet, "credit_balance", 0) or 0),
                market_prices={},
                smuggling_inventory={},
                item_modifiers={},
            )

    def _upsert_player_row_from_runtime(self, player_id: int) -> None:
        """Ensure the requested player has a row in the Phase-5 players table."""
        if getattr(self, "store", None) is None:
            return
        row = self.store.get_player_row(player_id)
        if row:
            return

        name = self.store.get_player_name_by_id(player_id) or f"commander_{int(player_id)}"
        credits = int(self.store.get_player_resource_amount(player_id, "credits") or 5000)
        owned_ships = []
        try:
            if self.player and str(getattr(self.player, "name", "")).strip().lower() == str(name).strip().lower():
                ship_model = str(getattr(self.player.spaceship, "model", "Unknown") or "Unknown")
                owned_ships = [{"ship_id": ship_model, "hp": 100, "shields": 100}]
        except Exception:
            owned_ships = []

        self.store.upsert_player_row(
            player_id=int(player_id),
            name=str(name),
            credits=int(credits),
            commander_rank=1,
            owned_ships=owned_ships,
        )

    def _roll_damage(self, ship: Dict[str, Any]) -> int:
        base_hp = int(ship.get("hp", 100) or 100)
        base = max(5, min(40, int(base_hp * 0.15)))
        tactic = self._normalize_tactic(ship.get("tactic"))
        if tactic == "flank":
            base = int(round(base * 1.30))
        elif tactic == "full burn":
            base = int(round(base * 1.15))
        elif tactic == "sabotage":
            base = int(round(base * 0.90))
        return max(1, base + random.randint(-4, 6))

    def _apply_shield_penalty(self, ship: Dict[str, Any]) -> None:
        if bool(ship.get("pending_flank_penalty", False)):
            shields = int(ship.get("shields", 0) or 0)
            ship["shields"] = max(0, int(round(shields * 0.80)))
            ship["pending_flank_penalty"] = False

    async def claim_planet(self, player_id: int, planet_id: int) -> dict:
        """Claim a planet for a player and persist ownership in SQLite.

        Args:
            player_id: SQLite player identifier.
            planet_id: Target planet identifier.

        Returns:
            A result payload describing claim success and the resulting owner.
        """
        self._seed_planets_table_if_empty()
        self._upsert_player_row_from_runtime(int(player_id))

        planet = self.get_planet_by_id(int(planet_id))
        if not planet:
            return {"success": False, "message": "INVALID PLANET.", "planet_id": int(planet_id)}

        owner_name = self.store.get_player_name_by_id(int(player_id))
        if not owner_name:
            return {"success": False, "message": "INVALID PLAYER.", "planet_id": int(planet_id)}

        planet.owner = str(owner_name)
        self.store.upsert_planet_row(
            planet_id=int(getattr(planet, "planet_id", 0) or 0),
            name=str(getattr(planet, "name", "") or ""),
            owner_id=int(player_id),
            credit_balance=int(getattr(planet, "credit_balance", 0) or 0),
            market_prices={},
            smuggling_inventory={},
            item_modifiers={},
        )

        if self.player and str(getattr(self.player, "name", "")).strip().lower() == str(owner_name).strip().lower():
            self.player.owned_planets[str(int(planet_id))] = True
            self.mark_state_dirty()

        return {
            "success": True,
            "planet_id": int(planet_id),
            "owner_id": int(player_id),
            "owner_name": str(owner_name),
            "message": f"PLANET {str(getattr(planet, 'name', '')).upper()} CLAIMED.",
        }

    async def process_trade(self, player_id: int, planet_id: int, item: str, qty: int, buy: bool) -> dict:
        """Process a server-authoritative resource trade against a planet market."""
        self._upsert_player_row_from_runtime(int(player_id))
        resource = str(item or "").strip().lower()
        qty = int(max(1, qty or 1))
        action = "BUY" if bool(buy) else "SELL"

        valid = set(getattr(self, "RESOURCE_TYPES", ("fuel", "ore", "tech", "bio", "rare")))
        if resource not in valid:
            return {"success": False, "message": "INVALID RESOURCE ITEM.", "item": resource}

        ok, message = self.trade_with_planet(
            int(player_id),
            int(planet_id),
            action,
            resource,
            int(qty),
        )

        player_row = self.store.get_player_row(int(player_id)) or {}
        credits = int(getattr(self.player, "credits", player_row.get("credits", 5000)) or 5000)
        self.store.upsert_player_row(
            int(player_id),
            str(player_row.get("name") or self.store.get_player_name_by_id(int(player_id)) or f"commander_{int(player_id)}"),
            credits=credits,
            commander_rank=int(player_row.get("commander_rank", 1) or 1),
            owned_ships=list(player_row.get("owned_ships", []) or []),
        )

        self.mark_state_dirty()
        return {
            "success": bool(ok),
            "message": str(message),
            "player_id": int(player_id),
            "planet_id": int(planet_id),
            "item": resource,
            "qty": int(qty),
            "buy": bool(buy),
        }

    async def start_combat(self, attacker_id: int, defender_id: int, attacker_fleet: list) -> int:
        """Create a new multi-round combat session and return its combat_id."""
        self._upsert_player_row_from_runtime(int(attacker_id))
        self._upsert_player_row_from_runtime(int(defender_id))

        defender = self.store.get_player_row(int(defender_id)) or {}

        attack_ships: List[Dict[str, Any]] = []
        for idx, ship in enumerate(list(attacker_fleet or [])[:5], start=1):
            row = dict(ship or {})
            attack_ships.append(
                {
                    "ship_id": str(row.get("ship_id") or f"atk_{idx}"),
                    "hp": int(max(1, row.get("hp", 100) or 100)),
                    "shields": int(max(0, row.get("shields", 50) or 50)),
                    "tactic": self._normalize_tactic(row.get("tactic")),
                    "captured": False,
                }
            )

        if len(attack_ships) < 3:
            for idx in range(len(attack_ships), 3):
                attack_ships.append(
                    {
                        "ship_id": f"atk_default_{idx + 1}",
                        "hp": 100,
                        "shields": 50,
                        "tactic": "full burn",
                        "captured": False,
                    }
                )

        def_ships = []
        for idx, ship in enumerate(list(defender.get("owned_ships", []) or [])[:5], start=1):
            row = dict(ship or {})
            def_ships.append(
                {
                    "ship_id": str(row.get("ship_id") or f"def_{idx}"),
                    "hp": int(max(1, row.get("hp", 100) or 100)),
                    "shields": int(max(0, row.get("shields", 50) or 50)),
                    "tactic": self._normalize_tactic(row.get("tactic")),
                    "captured": False,
                }
            )
        if not def_ships:
            def_ships = [
                {"ship_id": "def_guard_1", "hp": 100, "shields": 60, "tactic": "shield up", "captured": False},
                {"ship_id": "def_guard_2", "hp": 90, "shields": 50, "tactic": "full burn", "captured": False},
                {"ship_id": "def_guard_3", "hp": 110, "shields": 40, "tactic": "sabotage", "captured": False},
            ]

        combat_id = self.store.create_combat_session(
            attacker_id=int(attacker_id),
            defender_id=int(defender_id),
            attacker_ships=attack_ships,
            defender_ships=def_ships,
            status="active",
            round_number=0,
        )
        self.mark_state_dirty()
        return int(combat_id)

    async def combat_round(self, combat_id: int) -> dict:
        """Run one combat round and persist updated session state."""
        session = self.store.get_combat_session(int(combat_id))
        if not session:
            return {"success": False, "message": "COMBAT SESSION NOT FOUND.", "combat_id": int(combat_id)}
        if str(session.get("status", "active")) != "active":
            return {"success": True, "message": "COMBAT ALREADY RESOLVED.", "state": session}

        attacker_ships = [dict(s or {}) for s in list(session.get("attacker_ships", []) or [])]
        defender_ships = [dict(s or {}) for s in list(session.get("defender_ships", []) or [])]
        round_no = int(session.get("round_number", 0) or 0) + 1
        log_lines: List[str] = [f"ROUND {round_no}"]

        for ship in attacker_ships + defender_ships:
            self._apply_shield_penalty(ship)

        if attacker_ships and defender_ships:
            a_ship = attacker_ships[(round_no - 1) % len(attacker_ships)]
            d_ship = defender_ships[(round_no - 1) % len(defender_ships)]

            atk_damage = self._roll_damage(a_ship)
            def_damage = self._roll_damage(d_ship)

            if self._normalize_tactic(a_ship.get("tactic")) == "sabotage" and random.random() < 0.30:
                def_damage = int(round(def_damage * 0.80))
                log_lines.append("ATTACKER SABOTAGE SUCCESS: DEFENDER DAMAGE REDUCED.")
            if self._normalize_tactic(d_ship.get("tactic")) == "sabotage" and random.random() < 0.30:
                atk_damage = int(round(atk_damage * 0.80))
                log_lines.append("DEFENDER SABOTAGE SUCCESS: ATTACKER DAMAGE REDUCED.")

            if self._normalize_tactic(a_ship.get("tactic")) == "flank":
                a_ship["pending_flank_penalty"] = True
            if self._normalize_tactic(d_ship.get("tactic")) == "flank":
                d_ship["pending_flank_penalty"] = True

            if random.random() < 0.10:
                atk_damage = int(round(atk_damage * 1.50))
                log_lines.append("CRITICAL HIT! ENGINES OFFLINE - SPEED -50%.")
            if random.random() < 0.10:
                def_damage = int(round(def_damage * 1.50))
                log_lines.append("CRITICAL HIT! ENGINES OFFLINE - SPEED -50%.")

            d_shields = int(d_ship.get("shields", 0) or 0)
            a_shields = int(a_ship.get("shields", 0) or 0)

            d_shield_block = min(d_shields, atk_damage)
            a_shield_block = min(a_shields, def_damage)
            d_ship["shields"] = max(0, d_shields - d_shield_block)
            a_ship["shields"] = max(0, a_shields - a_shield_block)

            d_hp_hit = atk_damage - d_shield_block
            a_hp_hit = def_damage - a_shield_block
            d_ship["hp"] = max(0, int(d_ship.get("hp", 0) or 0) - d_hp_hit)
            a_ship["hp"] = max(0, int(a_ship.get("hp", 0) or 0) - a_hp_hit)

            log_lines.append(
                f"ATTACKER {a_ship.get('ship_id')} DEALT {atk_damage} | DEFENDER {d_ship.get('ship_id')} DEALT {def_damage}."
            )

        attacker_ships = [s for s in attacker_ships if int(s.get("hp", 0) or 0) > 0]
        defender_ships = [s for s in defender_ships if int(s.get("hp", 0) or 0) > 0]

        a_initial = max(1, len(list(session.get("attacker_ships", []) or [])))
        d_initial = max(1, len(list(session.get("defender_ships", []) or [])))
        a_loss_pct = 1.0 - (len(attacker_ships) / float(a_initial))
        d_loss_pct = 1.0 - (len(defender_ships) / float(d_initial))

        status = "active"
        winner: Optional[str] = None
        if a_loss_pct > 0.70:
            status = "lost"
            winner = "defender"
            log_lines.append("ATTACKER MORALE COLLAPSED: AUTO-SURRENDER.")
        elif d_loss_pct > 0.70:
            status = "won"
            winner = "attacker"
            log_lines.append("DEFENDER MORALE COLLAPSED: AUTO-SURRENDER.")

        if status == "active" and round_no >= 6:
            a_score = sum(int(s.get("hp", 0) or 0) + int(s.get("shields", 0) or 0) for s in attacker_ships)
            d_score = sum(int(s.get("hp", 0) or 0) + int(s.get("shields", 0) or 0) for s in defender_ships)
            if a_score > d_score:
                status = "won"
                winner = "attacker"
            elif d_score > a_score:
                status = "lost"
                winner = "defender"
            else:
                status = "draw"
                winner = None
            log_lines.append("MAX ROUNDS REACHED: BATTLE RESOLVED.")

        if status == "active" and defender_ships:
            for a_ship in attacker_ships:
                if self._normalize_tactic(a_ship.get("tactic")) != "board":
                    continue
                if d_loss_pct < 0.30:
                    continue
                if random.random() < 0.25:
                    captured = defender_ships.pop(0)
                    captured["captured"] = True
                    attacker_ships.append(captured)
                    log_lines.append(f"BOARDING SUCCESS: CAPTURED {captured.get('ship_id')}.")
                    break

        self.store.update_combat_session(
            int(combat_id),
            int(round_no),
            attacker_ships,
            defender_ships,
            status,
        )

        # Simple loot transfer on resolved combat.
        if status in {"won", "lost"} and winner is not None:
            winner_id = int(session.get("attacker_id") if winner == "attacker" else session.get("defender_id"))
            loser_id = int(session.get("defender_id") if winner == "attacker" else session.get("attacker_id"))
            winner_row = self.store.get_player_row(winner_id) or {}
            loser_row = self.store.get_player_row(loser_id) or {}
            loot = int(max(100, int(loser_row.get("credits", 0) or 0) * 0.20))
            loser_remaining = max(0, int(loser_row.get("credits", 0) or 0) - loot)
            winner_total = int(winner_row.get("credits", 0) or 0) + loot

            self.store.upsert_player_row(
                winner_id,
                str(winner_row.get("name") or self.store.get_player_name_by_id(winner_id) or f"commander_{winner_id}"),
                credits=winner_total,
                commander_rank=int(winner_row.get("commander_rank", 1) or 1),
                owned_ships=list(winner_row.get("owned_ships", []) or []),
            )
            self.store.upsert_player_row(
                loser_id,
                str(loser_row.get("name") or self.store.get_player_name_by_id(loser_id) or f"commander_{loser_id}"),
                credits=loser_remaining,
                commander_rank=int(loser_row.get("commander_rank", 1) or 1),
                owned_ships=list(loser_row.get("owned_ships", []) or []),
            )
            log_lines.append(f"LOOT TRANSFERRED: {loot:,} CR.")

        self.mark_state_dirty()
        state = self.store.get_combat_session(int(combat_id))
        return {
            "success": True,
            "combat_id": int(combat_id),
            "log": log_lines,
            "state": state,
            "winner": winner,
        }

    async def daily_economy_tick(self):
        """Run one economy tick and persist cycle state."""
        turn = int(self.store.get_game_state_value("turn_number", 0) or 0) + 1
        self.store.set_game_state_value("turn_number", int(turn))
        self.store.set_game_state_value("last_daily_tick_ts", float(time.time()))

        if hasattr(self, "_apply_market_rotation_if_due"):
            self._apply_market_rotation_if_due()

        produced = False
        if hasattr(self, "produce_resources"):
            ok, _msg = self.produce_resources()
            produced = bool(ok)
        if hasattr(self, "payout_resource_interest"):
            self.payout_resource_interest()

        self.mark_state_dirty()
        return {
            "success": True,
            "turn_number": int(turn),
            "produced": bool(produced),
        }

    def get_full_state(self) -> dict:
        """Return full synchronized state payload for newly-connected clients."""
        self._seed_planets_table_if_empty()
        version = int(getattr(self, "state_version", 0) or 0)
        now = float(time.time())
        cache = getattr(self, "_phase5_full_state_cache", None)
        if isinstance(cache, dict):
            cached_version = int(cache.get("version", -1) or -1)
            cached_at = float(cache.get("cached_at", 0.0) or 0.0)
            if cached_version == version and (now - cached_at) <= 0.35:
                return dict(cache.get("payload", {}) or {})

        payload = {
            "state_version": version,
            "planets": self.store.list_planets_rows(),
            "players": self.store.list_player_rows(),
            "combat_sessions": [
                row for row in self.store.list_combat_sessions() if isinstance(row, dict)
            ],
            "game_state": self.store.get_all_game_state(),
        }
        self._phase5_full_state_cache = {
            "version": version,
            "cached_at": now,
            "payload": payload,
        }
        return dict(payload)
