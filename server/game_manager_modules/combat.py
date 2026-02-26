import time
import json
import os
import random


class CombatMixin:
    def _get_combat_enemy_scale(self):
        ship_level = self.get_ship_level(self.player.spaceship if self.player else None)
        per_level = float(self.config.get("combat_enemy_scale_per_ship_level"))
        scale = 1.0 + (max(0, ship_level - 1) * per_level)

        # Small pressure from active win streak to keep combat engaging.
        streak = self._get_combat_win_streak()
        scale += min(0.15, streak * 0.01)
        return max(1.0, scale)

    def get_planet_conquest_progress(self, planet_name=None):
        p_name = planet_name or (
            self.current_planet.name if self.current_planet else None
        )
        if not p_name:
            return 0.0

        planet = next((p for p in self.planets if p.name == p_name), None)
        if not planet:
            return 0.0

        base_shields = max(
            1.0, float(getattr(planet, "base_shields", max(1, planet.shields)))
        )
        base_defenders = max(
            1.0, float(getattr(planet, "base_defenders", max(1, planet.defenders)))
        )
        shield_ratio = min(1.0, max(0.0, float(planet.shields) / base_shields))
        defender_ratio = min(1.0, max(0.0, float(planet.defenders) / base_defenders))
        progress = 1.0 - ((shield_ratio + defender_ratio) / 2.0)
        return min(1.0, max(0.0, progress))

    def should_initialize_planet_auto_combat(self, planet_name=None):
        if not self.player:
            return False, ""

        p_name = planet_name or (
            self.current_planet.name if self.current_planet else None
        )
        if not p_name:
            return False, ""

        planet = next((p for p in self.planets if p.name == p_name), None)
        if not planet:
            return False, ""
        if planet.owner == self.player.name:
            return False, ""
        if not self.has_attacked_planet(p_name):
            return False, ""

        progress = self.get_planet_conquest_progress(p_name)
        threshold_pct = float(self.config.get("planet_auto_combat_threshold_pct"))
        threshold = max(0.0, min(1.0, threshold_pct / 100.0))
        if progress <= threshold:
            return False, ""

        chance = min(0.55, 0.20 + ((progress - threshold) * 1.0))
        if random.random() < chance:
            pct = int(progress * 100)
            return (
                True,
                f"PLANETARY COUNTERASSAULT DETECTED ({pct}% BREACH). DEFENSE GRID SCRAMBLE INCOMING!",
            )
        return False, ""

    def start_combat_session(self, target_data):
        """Creates a round-based combat session payload used by the gameplay modal."""
        target_type = target_data.get("type")
        if target_type not in {"NPC", "PLAYER", "PLANET"}:
            return False, "Invalid combat target.", None

        session = {
            "status": "ACTIVE",
            "round": 0,
            "target_type": target_type,
            "log": [],
            "summary": None,
            "enemy_scale": float(self._get_combat_enemy_scale()),
            "starting_streak": int(self._get_combat_win_streak()),
        }

        p_ship = self.player.spaceship
        session["player_start"] = {
            "shields": int(p_ship.current_shields),
            "defenders": int(p_ship.current_defenders),
            "integrity": int(p_ship.integrity),
            "credits": int(self.player.credits),
        }

        if target_type == "NPC":
            target = target_data.get("obj")
            if target is None:
                raw_data = (
                    target_data.get("raw_data")
                    if isinstance(target_data.get("raw_data"), dict)
                    else {}
                )
                npc_raw = (
                    raw_data.get("player")
                    if isinstance(raw_data.get("player"), dict)
                    else {}
                )
                ship_raw = (
                    npc_raw.get("spaceship")
                    if isinstance(npc_raw.get("spaceship"), dict)
                    else {}
                )

                class _CombatShipProxy:
                    def __init__(self, payload):
                        self.current_shields = int(payload.get("current_shields", payload.get("shields", 0)))
                        self.current_defenders = int(payload.get("current_defenders", payload.get("defenders", 0)))
                        self.integrity = int(payload.get("integrity", payload.get("max_integrity", 100)))

                class _CombatNpcProxy:
                    def __init__(self, npc_payload, fallback_name, fallback_personality):
                        self.name = str(npc_payload.get("name") or fallback_name or "Unknown")
                        self.personality = str(
                            npc_payload.get("personality")
                            or fallback_personality
                            or "neutral"
                        )
                        self.credits = int(npc_payload.get("credits", 0))
                        self.inventory = dict(npc_payload.get("inventory", {}) or {})
                        self.spaceship = _CombatShipProxy(ship_raw)

                    def get_remark(self):
                        return "Maintain formation."

                target = _CombatNpcProxy(
                    npc_raw,
                    target_data.get("name"),
                    target_data.get("personality"),
                )

            session["target_name"] = target.name
            session["target_ref"] = target
            session["target_credits"] = int(target.credits)
            session["target_inventory"] = dict(target.inventory)
            session["target_start"] = {
                "shields": int(target.spaceship.current_shields),
                "defenders": int(target.spaceship.current_defenders),
                "integrity": int(target.spaceship.integrity),
                "credits": int(target.credits),
            }
        elif target_type == "PLAYER":
            target_name = target_data["name"]
            raw = target_data["raw_data"]["player"]
            s_raw = raw["spaceship"]

            session["target_name"] = target_name
            session["target_ref"] = None
            session["target_ship"] = {
                "shields": int(s_raw.get("current_shields", 0)),
                "defenders": int(s_raw.get("current_defenders", 0)),
                "integrity": int(s_raw.get("integrity", 100)),
            }
            session["target_credits"] = int(raw.get("credits", 0))
            session["target_inventory"] = dict(raw.get("inventory", {}))
            session["target_start"] = {
                "shields": int(session["target_ship"]["shields"]),
                "defenders": int(session["target_ship"]["defenders"]),
                "integrity": int(session["target_ship"]["integrity"]),
                "credits": int(session["target_credits"]),
            }

            target_file = str(target_data.get("save_path", "")).strip()
            if target_file:
                session["target_file"] = target_file
            else:
                filename = f"{target_name.replace(' ', '_').lower()}.json"
                session["target_file"] = os.path.join(self.save_dir, filename)
        else:
            planet = self.current_planet
            self._mark_planet_attacked(planet.name)
            session["target_name"] = planet.name
            session["target_ref"] = None
            session["target_credits"] = min(
                50000, max(2000, int(planet.population / 200000))
            )
            session["target_inventory"] = {"Planetary Core": 1}
            session["target_start"] = {
                "shields": int(planet.shields),
                "defenders": int(planet.defenders),
                "integrity": 0,
                "credits": int(session["target_credits"]),
            }

        session["log"].append(
            f"ENGAGEMENT STARTED: {session['target_name'].upper()} [{target_type}]"
        )
        session["log"].append(
            f"THREAT MODIFIER: x{session['enemy_scale']:.2f} | WIN STREAK: {session['starting_streak']}"
        )
        return True, "Combat window initialized.", session

    def _get_target_stats(self, session):
        t_type = session["target_type"]
        if t_type == "NPC":
            ship = session["target_ref"].spaceship
            return (
                int(ship.current_shields),
                int(ship.current_defenders),
                int(ship.integrity),
            )
        if t_type == "PLAYER":
            ship = session["target_ship"]
            return int(ship["shields"]), int(ship["defenders"]), int(ship["integrity"])
        planet = self.current_planet
        return int(planet.shields), int(planet.defenders), 0

    def _set_target_stats(self, session, shields, defenders, integrity):
        t_type = session["target_type"]
        shields = max(0, int(shields))
        defenders = max(0, int(defenders))
        integrity = max(0, int(integrity))

        if t_type == "NPC":
            ship = session["target_ref"].spaceship
            ship.current_shields = shields
            ship.current_defenders = defenders
            ship.integrity = integrity
            return
        if t_type == "PLAYER":
            session["target_ship"]["shields"] = shields
            session["target_ship"]["defenders"] = defenders
            session["target_ship"]["integrity"] = integrity
            return

        self.current_planet.shields = shields
        self.current_planet.defenders = defenders

    def _apply_damage_profile(self, shields, defenders, integrity, raw_damage):
        """Apply raw damage to shields first, then fighters, then integrity."""
        dmg = max(0, int(raw_damage))
        out = {"shield": 0, "fighters": 0, "integrity": 0}

        shield_hit = min(shields, dmg)
        shields -= shield_hit
        dmg -= shield_hit
        out["shield"] = int(shield_hit)

        if dmg > 0 and defenders > 0:
            fighter_loss = min(defenders, max(1, (dmg // 10) + random.randint(0, 2)))
            defenders -= fighter_loss
            dmg -= fighter_loss * 8
            out["fighters"] = int(fighter_loss)

        if dmg > 0 and integrity > 0:
            integ_loss = min(integrity, max(1, dmg // 2))
            integrity -= integ_loss
            out["integrity"] = int(integ_loss)

        return max(0, shields), max(0, defenders), max(0, integrity), out

    def _roll_attack(self, committed_fighters, attack_bonus=0.0):
        committed = max(0, int(committed_fighters))
        if committed <= 0:
            return {"hit": False, "crit": False, "damage": 0}

        hit_chance = max(0.2, min(0.9, 0.55 + attack_bonus))
        hit = random.random() < hit_chance

        if hit:
            dmg = random.randint(committed * 8, committed * 14)
            crit = random.random() < 0.12
            if crit:
                dmg = int(dmg * 1.5)
            return {"hit": True, "crit": crit, "damage": int(dmg)}

        # Grazing fire even on miss.
        return {"hit": False, "crit": False, "damage": random.randint(0, committed * 2)}

    def _finish_combat_session(self, session, player_won):
        p_ship = self.player.spaceship
        target_name = session["target_name"]
        target_type = session["target_type"]

        credits_delta = 0
        item_report = []
        stolen_item_report = []
        looted_credits = 0
        stolen_credits = 0
        bounty_bonus = 0
        rare_loot = []
        result_text = ""

        if player_won:
            loot_factor = random.uniform(0.25, 0.60)
            steal_credits = int(session["target_credits"] * loot_factor)
            credits_delta += steal_credits
            looted_credits = steal_credits

            enemy_scale = float(session.get("enemy_scale", 1.0))
            streak_before = int(self._get_combat_win_streak())
            per_win_bonus = float(
                self.config.get("combat_win_streak_bonus_per_win")
            )
            bonus_cap = float(self.config.get("combat_win_streak_bonus_cap"))
            streak_bonus_factor = min(bonus_cap, streak_before * per_win_bonus)
            challenge_bonus_factor = max(0.0, (enemy_scale - 1.0) * 0.75)
            payout_bonus_factor = streak_bonus_factor + challenge_bonus_factor
            payout_bonus = int(max(0, looted_credits * payout_bonus_factor))
            if payout_bonus > 0:
                credits_delta += payout_bonus
                looted_credits += payout_bonus

            self._set_combat_win_streak(streak_before + 1)
            self.player.combat_lifetime_wins = (
                int(getattr(self.player, "combat_lifetime_wins", 0)) + 1
            )

            if target_type == "NPC":
                target = session["target_ref"]
                if getattr(target, "personality", "") == "hostile":
                    base_bounty = int(
                        max(200, session["target_start"]["credits"] * 0.15)
                    )
                    authority_rep = max(0, self._get_authority_standing())
                    bounty_step = float(
                        self.config.get("authority_bounty_bonus_step", 0.01)
                    )
                    bounty_mult = 1.0 + min(0.60, authority_rep * bounty_step)
                    bounty_bonus = int(round(base_bounty * bounty_mult))
                    credits_delta += bounty_bonus
                    looted_credits += bounty_bonus
                    self._adjust_authority_standing(
                        int(self.config.get("reputation_hostile_npc_bonus"))
                    )
                    self._apply_crew_activity("victory", specialty="weapons")

            # Credits transfer from target source
            if target_type == "NPC":
                target = session["target_ref"]
                target.credits = max(0, target.credits - steal_credits)
            elif target_type == "PLAYER":
                session["target_credits"] = max(
                    0, session["target_credits"] - steal_credits
                )
            elif target_type == "PLANET":
                pass

            # Loot inventory
            for item, qty in list(session["target_inventory"].items()):
                if qty <= 0:
                    continue
                amount = max(0, int(qty * random.uniform(0.10, 0.45)))
                if amount <= 0:
                    continue
                cargo_used = sum(self.player.inventory.values())
                cargo_limit = int(
                    p_ship.get_effective_max_cargo()
                    if hasattr(p_ship, "get_effective_max_cargo")
                    else p_ship.current_cargo_pods
                )
                if cargo_used + amount > cargo_limit:
                    continue
                self.player.inventory[item] = (
                    self.player.inventory.get(item, 0) + amount
                )
                item_report.append(f"{amount}x {item}")
                session["target_inventory"][item] = max(0, qty - amount)

            if random.random() < 0.12:
                rare_item = random.choice(
                    [
                        "Quantum Data Chips",
                        "Hyperdrive Stabilizers",
                        "Neural Interface Upgrades",
                    ]
                )
                cargo_used = sum(self.player.inventory.values())
                cargo_limit = int(
                    p_ship.get_effective_max_cargo()
                    if hasattr(p_ship, "get_effective_max_cargo")
                    else p_ship.current_cargo_pods
                )
                if cargo_used + 1 <= cargo_limit:
                    self.player.inventory[rare_item] = (
                        self.player.inventory.get(rare_item, 0) + 1
                    )
                    item_report.append(f"1x {rare_item}")
                    rare_loot.append(rare_item)

            if target_type == "PLANET":
                old_owner = self.current_planet.owner
                self.current_planet.owner = self.player.name
                self.player.owned_planets[target_name] = time.time()
                self.current_planet.last_defense_regen_time = time.time()
                self._clear_planet_attack_state(target_name)
                self._save_shared_planet_states()
                self._append_galactic_news(
                    title=f"Planet Captured: {target_name}",
                    body=f"{self.player.name} seized control of {target_name}.",
                    event_type="planet_conquest",
                    planet_name=target_name,
                    audience="global",
                )
                result_text = f"PLANET CONQUERED: {target_name}."
                if old_owner and old_owner != self.player.name:
                    self._append_galactic_news(
                        title=f"Colony Lost: {target_name}",
                        body=f"Your colony on {target_name} was captured by {self.player.name}.",
                        event_type="planet_loss",
                        planet_name=target_name,
                        audience="player",
                        player_name=old_owner,
                    )
                    self.send_message(
                        old_owner,
                        "PLANET LOST",
                        f"Attention: Your colony on {target_name} has been captured by {self.player.name}.",
                    )
            else:
                result_text = f"TARGET DISABLED: {target_name}."

            if target_type == "PLAYER":
                path = session.get("target_file")
                if path and os.path.exists(path):
                    try:
                        with open(path, "r") as f:
                            data = json.load(f)
                        data["player"]["credits"] = int(session["target_credits"])
                        data["player"]["inventory"] = session["target_inventory"]
                        data["player"]["spaceship"]["current_shields"] = int(
                            session["target_ship"]["shields"]
                        )
                        data["player"]["spaceship"]["current_defenders"] = int(
                            session["target_ship"]["defenders"]
                        )
                        data["player"]["spaceship"]["integrity"] = int(
                            session["target_ship"]["integrity"]
                        )
                        with open(path, "w") as f:
                            json.dump(data, f, indent=4)
                    except Exception:
                        pass

                self.send_message(
                    target_name,
                    "Vessel Boarded",
                    f"Alert: Your ship at {self.current_planet.name} was overpowered by {self.player.name}.",
                )

            self.player.credits += credits_delta
        else:
            loss_factor = random.uniform(0.15, 0.40)
            loss = int(self.player.credits * loss_factor)
            self.player.credits = max(0, self.player.credits - loss)
            credits_delta -= loss
            stolen_credits = loss

            # Combat loss can include cargo theft.
            for item, qty in list(self.player.inventory.items()):
                if qty <= 0:
                    continue
                if random.random() < 0.40:
                    taken = max(1, int(qty * random.uniform(0.05, 0.30)))
                    taken = min(taken, self.player.inventory.get(item, 0))
                    if taken <= 0:
                        continue
                    self.player.inventory[item] -= taken
                    if self.player.inventory[item] <= 0:
                        del self.player.inventory[item]
                    stolen_item_report.append(f"{taken}x {item}")
                if len(stolen_item_report) >= 3:
                    break

            result_text = f"COMBAT LOST AGAINST {target_name}."
            self._set_combat_win_streak(0)
            self._apply_crew_activity("combat")

        session["status"] = "WON" if player_won else "LOST"
        session["summary"] = {
            "result": session["status"],
            "target": target_name,
            "credits_delta": int(credits_delta),
            "items": item_report,
            "looted_credits": int(looted_credits),
            "stolen_credits": int(stolen_credits),
            "looted_items": item_report,
            "stolen_items": stolen_item_report,
            "player_end": {
                "shields": int(self.player.spaceship.current_shields),
                "defenders": int(self.player.spaceship.current_defenders),
                "integrity": int(self.player.spaceship.integrity),
                "credits": int(self.player.credits),
            },
            "target_end": {
                "shields": int(self._get_target_stats(session)[0]),
                "defenders": int(self._get_target_stats(session)[1]),
                "integrity": int(self._get_target_stats(session)[2]),
            },
            "message": result_text,
            "enemy_scale": float(session.get("enemy_scale", 1.0)),
            "win_streak": int(self._get_combat_win_streak()),
            "bounty_bonus": int(bounty_bonus if player_won else 0),
            "rare_loot": rare_loot if player_won else [],
        }

        outcome = "WON" if player_won else "LOST"
        self._append_galactic_news(
            title=f"Combat Outcome: You {outcome}",
            body=(
                f"Engagement vs {target_name} [{target_type}] at "
                f"{self.current_planet.name if self.current_planet else 'UNKNOWN'} "
                f"ended {outcome.lower()} with net {int(credits_delta):+d} CR."
            ),
            event_type="combat_outcome",
            planet_name=self.current_planet.name if self.current_planet else None,
            audience="player",
            player_name=self.player.name,
        )

        if target_type in {"PLAYER", "PLANET"}:
            self._append_galactic_news(
                title=f"Combat Outcome: {self.player.name} {outcome}",
                body=(
                    f"{self.player.name} {outcome.lower()} engagement vs {target_name} "
                    f"[{target_type}] with net {int(credits_delta):+d} CR."
                ),
                event_type="combat_outcome",
                planet_name=self.current_planet.name if self.current_planet else None,
                audience="global",
            )

            if target_type == "PLAYER":
                self._append_galactic_news(
                    title=f"Combat Report: {target_name}",
                    body=(
                        f"Engagement with {self.player.name} resulted in a {outcome.lower()} outcome "
                        f"for opposing commander {target_name}."
                    ),
                    event_type="combat_outcome",
                    planet_name=(
                        self.current_planet.name if self.current_planet else None
                    ),
                    audience="player",
                    player_name=target_name,
                )

        session["log"].append(result_text)
        return session

    def resolve_combat_round(self, session, player_committed):
        """Executes one full round: player attack + target counterattack."""
        if not session or session.get("status") != "ACTIVE":
            return False, "Combat session is not active.", session

        p_ship = self.player.spaceship
        p_shields = int(p_ship.current_shields)
        p_defenders = int(p_ship.current_defenders)
        p_integrity = int(p_ship.integrity)

        t_shields, t_defenders, t_integrity = self._get_target_stats(session)

        if p_shields <= 0 and p_defenders <= 0:
            self._finish_combat_session(session, player_won=False)
            return True, "Player combat capacity depleted.", session
        if t_shields <= 0 and t_defenders <= 0:
            self._finish_combat_session(session, player_won=True)
            return True, "Target combat capacity depleted.", session

        session["round"] += 1
        round_lines = [f"ROUND {session['round']}"]

        player_committed = max(0, min(int(player_committed), p_defenders))
        if p_defenders > 0 and player_committed == 0:
            player_committed = 1

        # Target committed fighters
        if t_defenders > 0:
            if session["target_type"] == "PLANET":
                target_committed = random.randint(1, max(1, t_defenders))
            else:
                target_committed = random.randint(1, t_defenders)

            enemy_scale = float(session.get("enemy_scale", 1.0))
            scaled_commit = int(round(target_committed * enemy_scale))
            target_committed = max(1, min(t_defenders, scaled_commit))
        else:
            target_committed = 0

        # Flavor / NPC chatter
        if session["target_type"] == "NPC":
            remark = session["target_ref"].get_remark()
            round_lines.append(f"{session['target_name'].upper()}: {remark}")
        elif session["target_type"] == "PLANET":
            round_lines.append(
                f"{self.current_planet.vendor.upper()} DEFENSE GRID: FIRING SOLUTIONS LOCKED."
            )
        else:
            round_lines.append(
                f"{session['target_name'].upper()}: HOLD FAST! RETURN FIRE!"
            )

        p_bonus = 0.0
        if "weapons" in self.player.crew:
            p_bonus += self.player.crew["weapons"].get_bonus() * 0.6

        t_bonus = 0.0
        if session["target_type"] == "NPC":
            personality = session["target_ref"].personality
            if personality == "hostile":
                t_bonus += 0.10
            elif personality == "friendly":
                t_bonus -= 0.05
        elif session["target_type"] == "PLANET":
            t_bonus += 0.08

        enemy_scale = float(session.get("enemy_scale", 1.0))
        t_bonus += max(0.0, (enemy_scale - 1.0) * 0.12)

        player_attack = self._roll_attack(player_committed, attack_bonus=p_bonus)
        target_attack = self._roll_attack(target_committed, attack_bonus=t_bonus)

        # Simultaneous exchange: apply both results regardless of immediate disable.
        t_new = self._apply_damage_profile(
            t_shields, t_defenders, t_integrity, player_attack["damage"]
        )
        p_new = self._apply_damage_profile(
            p_shields, p_defenders, p_integrity, target_attack["damage"]
        )

        t_shields, t_defenders, t_integrity, t_report = t_new
        p_shields, p_defenders, p_integrity, p_report = p_new

        self._set_target_stats(session, t_shields, t_defenders, t_integrity)
        p_ship.current_shields = p_shields
        p_ship.current_defenders = p_defenders
        p_ship.integrity = p_integrity

        player_hit_tag = (
            "CRITICAL HIT"
            if player_attack["crit"]
            else ("HIT" if player_attack["hit"] else "GRAZE")
        )
        target_hit_tag = (
            "CRITICAL HIT"
            if target_attack["crit"]
            else ("HIT" if target_attack["hit"] else "GRAZE")
        )

        round_lines.append(
            f"YOU [{player_hit_tag}] committed {player_committed} fighters, damage {player_attack['damage']} (enemy shields -{t_report['shield']}, fighters -{t_report['fighters']})."
        )
        round_lines.append(
            f"ENEMY [{target_hit_tag}] committed {target_committed} fighters, damage {target_attack['damage']} (your shields -{p_report['shield']}, fighters -{p_report['fighters']})."
        )

        session["log"].extend(round_lines)

        target_defeated = t_shields <= 0 and t_defenders <= 0
        player_defeated = p_shields <= 0 and p_defenders <= 0

        if target_defeated and not player_defeated:
            self._finish_combat_session(session, player_won=True)
            return True, "Target defeated.", session
        if player_defeated:
            self._finish_combat_session(session, player_won=False)
            return True, "Player defeated.", session

        return True, "Round resolved.", session

    def flee_combat_session(self, session):
        if not session or session.get("status") != "ACTIVE":
            return False, "No active combat to flee.", session

        penalty = int(self.player.credits * random.uniform(0.05, 0.15))
        self.player.credits = max(0, self.player.credits - penalty)

        if session["target_type"] == "PLANET":
            p = self.current_planet
            self._mark_planet_attacked(p.name)
            if p.owner and p.owner != self.player.name:
                self.bar_player(p.name)

            self._set_combat_win_streak(0)

        session["status"] = "FLED"
        session["summary"] = {
            "result": "FLED",
            "target": session["target_name"],
            "credits_delta": -penalty,
            "items": [],
            "looted_credits": 0,
            "stolen_credits": int(penalty),
            "looted_items": [],
            "stolen_items": [],
            "player_end": {
                "shields": int(self.player.spaceship.current_shields),
                "defenders": int(self.player.spaceship.current_defenders),
                "integrity": int(self.player.spaceship.integrity),
                "credits": int(self.player.credits),
            },
            "target_end": {
                "shields": int(self._get_target_stats(session)[0]),
                "defenders": int(self._get_target_stats(session)[1]),
                "integrity": int(self._get_target_stats(session)[2]),
            },
            "message": f"You warped away from combat with {session['target_name']}.",
        }
        session["log"].append(session["summary"]["message"])
        return True, "Fled from combat.", session

    def fire_special_weapon(self, session):
        """
        Fire the player's special weapon during planet combat.
        - Blocked if server has enable_special_weapons = False.
        - Blocked if cooldown hasn't elapsed.
        - Deals damage_multiplier * normal round damage to planet defenses.
        - Reduces planet population and treasury by a random percentage
          between combat_special_weapon_pop_reduction_min and
          combat_special_weapon_pop_reduction_max.
        Returns (success, message, result_dict).
        """
        import time

        # Config gates
        if not self.config.get("enable_special_weapons"):
            return False, "Special weapons are disabled on this server.", {}

        if not session or session.get("status") != "ACTIVE":
            return False, "No active combat session.", {}

        if session.get("target_type") != "PLANET":
            return False, "Special weapon can only be used in planet combat.", {}

        weapon_name = getattr(self.player.spaceship, "special_weapon", None)
        if not weapon_name:
            return False, "Your ship has no special weapon installed.", {}

        # Cooldown check
        cooldown_hours = float(self.config.get("combat_special_weapon_cooldown_hours"))
        last_used = float(getattr(self.player, "last_special_weapon_time", 0.0))
        now = time.time()
        elapsed_hours = (now - last_used) / 3600.0
        if elapsed_hours < cooldown_hours:
            remaining_hours = cooldown_hours - elapsed_hours
            remaining_mins = int(remaining_hours * 60)
            if remaining_hours >= 1.0:
                remaining_str = f"{remaining_hours:.1f} HOURS"
            else:
                remaining_str = f"{remaining_mins} MINUTES"
            return False, f"SPECIAL WEAPON ON COOLDOWN — {remaining_str} REMAINING.", {}

        planet = self.current_planet
        if planet is None:
            return False, "No current planet for combat target.", {}

        # Config values
        dmg_mult = float(self.config.get("combat_special_weapon_damage_multiplier"))
        pop_min = float(self.config.get("combat_special_weapon_pop_reduction_min"))
        pop_max = float(self.config.get("combat_special_weapon_pop_reduction_max"))
        pop_pct = random.uniform(pop_min, pop_max)

        # Snapshot before
        pop_before = int(planet.population)
        treasury_before = int(getattr(planet, "credit_balance", 0))

        # Apply population reduction
        pop_reduction = int(pop_before * pop_pct)
        planet.population = max(0, pop_before - pop_reduction)

        # Apply treasury reduction (same percentage)
        treasury_reduction = int(treasury_before * pop_pct)
        planet.credit_balance = max(0, treasury_before - treasury_reduction)

        # Apply boosted defense damage (multiplier × normal attack damage)
        player_ship = self.player.spaceship
        p_committed = max(1, int(player_ship.current_defenders // 3))
        attack_bonus = 0.0
        if "weapons" in self.player.crew:
            attack_bonus = float(self.player.crew["weapons"].get_bonus())
        raw_attack = self._roll_attack(p_committed, attack_bonus)
        boosted_damage = int(raw_attack["damage"] * dmg_mult)

        # Apply boosted damage to planet defenses
        shield_taken = min(int(planet.shields), boosted_damage)
        planet.shields = max(0, int(planet.shields) - shield_taken)
        spillover = boosted_damage - shield_taken
        if spillover > 0 and planet.shields <= 0:
            planet.defenders = max(0, int(planet.defenders) - int(spillover // 6))

        self._save_shared_planet_states()

        # Update cooldown timestamp on player
        self.player.last_special_weapon_time = now

        # Build result
        pop_after = int(planet.population)
        treasury_after = int(getattr(planet, "credit_balance", 0))
        result = {
            "weapon_name": str(weapon_name),
            "pop_before": pop_before,
            "pop_after": pop_after,
            "pop_reduction_pct": round(pop_pct * 100, 1),
            "treasury_before": treasury_before,
            "treasury_after": treasury_after,
            "damage_dealt": boosted_damage,
            "shields_after": int(planet.shields),
            "defenders_after": int(planet.defenders),
        }

        log_line = (
            f"[SPECIAL WEAPON: {weapon_name.upper()}] "
            f"Population reduced {result['pop_reduction_pct']}% "
            f"({pop_before:,} → {pop_after:,}). "
            f"Treasury reduced {result['pop_reduction_pct']}% "
            f"({treasury_before:,} → {treasury_after:,}). "
            f"Defense damage: {boosted_damage} (shields: {result['shields_after']}, defenders: {result['defenders_after']})."
        )
        session.setdefault("log", []).append(log_line)

        return True, f"{weapon_name.upper()} FIRED.", result

    def resolve_combat(self, target_data):
        """
        target_data can be an NPC ship entry or a Player entry.
        Returns (success, message, loot_report)
        """
        player_ship = self.player.spaceship
        is_planet_target = target_data["type"] == "PLANET"
        if is_planet_target:
            self._mark_planet_attacked(self.current_planet.name)

        # Determine target stats
        if target_data["type"] == "NPC":
            target = target_data["obj"]
            target_name = target.name
            t_ship = target.spaceship
            t_credits = target.credits
            t_inv = target.inventory
            t_defenders = t_ship.current_defenders
        elif target_data["type"] == "PLAYER":
            target_name = target_data["name"]
            raw = target_data["raw_data"]["player"]
            s_raw = raw["spaceship"]
            t_credits = raw["credits"]
            t_inv = raw["inventory"]
            t_defenders = s_raw["current_defenders"]
            # Mock ship for calc
            from classes import Spaceship

            t_ship = Spaceship(s_raw["model"], 0, 0, 0, 0, 0, 0, 0)
            t_ship.current_shields = s_raw["current_shields"]
            t_ship.current_defenders = s_raw["current_defenders"]
            t_ship.integrity = s_raw["integrity"]
        elif is_planet_target:
            target_name = self.current_planet.name
            t_credits = min(
                50000,
                max(2000, int(self.current_planet.population / 200000)),
            )
            t_inv = {"Planetary Core": 1}
            t_defenders = self.current_planet.defenders
            t_ship = None
        else:
            return False, "Invalid target.", {}

        # Basic Combat Simulation
        # Odds based on fighters and ship class/weapons
        p_power = player_ship.current_defenders * 10 + 20  # Base power
        if hasattr(player_ship, "get_effective_combat_power_multiplier"):
            p_power *= float(player_ship.get_effective_combat_power_multiplier())

        # Weapons Expert bonus
        if "weapons" in self.player.crew:
            p_power *= 1.0 + self.player.crew["weapons"].get_bonus()

        if is_planet_target:
            t_power = int(
                self.current_planet.defenders * 1.5
                + (self.current_planet.shields / 40)
                + 40
            )
        else:
            t_power = t_defenders * 10 + 20

        # Ensure integers for random.randint
        p_power = int(p_power)
        t_power = int(t_power)

        # Random variance
        p_roll = random.randint(p_power // 2, p_power)
        t_roll = random.randint(t_power // 2, t_power)

        if p_roll >= t_roll:
            # Player Wins
            # Take loot
            loot_factor = random.uniform(0.1, 0.75)

            # Credits
            earned_credits = round(t_credits * loot_factor)
            self.player.credits += earned_credits

            # Inventory
            lost_items = []
            for item, qty in list(t_inv.items()):
                amount = int(qty * loot_factor)
                if amount > 0:
                    # Check cargo space
                    current_cargo = sum(self.player.inventory.values())
                    cargo_limit = int(
                        player_ship.get_effective_max_cargo()
                        if hasattr(player_ship, "get_effective_max_cargo")
                        else player_ship.current_cargo_pods
                    )
                    if current_cargo + amount <= cargo_limit:
                        self.player.inventory[item] = (
                            self.player.inventory.get(item, 0) + amount
                        )
                        lost_items.append(f"{amount}x {item}")

            msg = (
                f"Victory against {target_name}! You pillaged their cargo and credits."
            )
            if is_planet_target:
                planet = self.current_planet

                # Planet assaults are progressive: each victory weakens defenses.
                shield_damage = random.randint(120, 260) + (
                    player_ship.current_defenders * 2
                )
                defender_damage = random.randint(10, 35) + max(
                    0, player_ship.current_defenders // 4
                )

                if planet.shields > 0:
                    absorbed = min(planet.shields, shield_damage)
                    planet.shields -= absorbed
                    spillover = shield_damage - absorbed
                    if spillover > 0:
                        planet.defenders = max(0, planet.defenders - (spillover // 8))

                if planet.shields <= 0:
                    planet.defenders = max(0, planet.defenders - defender_damage)

                # Ground batteries still inflict some damage during successful raids.
                self.player.take_damage(random.randint(8, 22))

                raid_credits = round(t_credits * random.uniform(0.05, 0.25))
                self.player.credits += raid_credits

                if planet.shields == 0 and planet.defenders == 0:
                    old_owner = planet.owner
                    self.player.owned_planets[target_name] = time.time()
                    planet.owner = self.player.name
                    planet.last_defense_regen_time = time.time()
                    self._clear_planet_attack_state(target_name)
                    self._save_shared_planet_states()
                    self._append_galactic_news(
                        title=f"Planet Captured: {target_name}",
                        body=f"{self.player.name} conquered {target_name} after breaching all defenses.",
                        event_type="planet_conquest",
                        planet_name=target_name,
                        audience="global",
                    )
                    msg = f"You have conquered {target_name}! You now draw interest from its economy."

                    if old_owner and old_owner != self.player.name:
                        self._append_galactic_news(
                            title=f"Colony Lost: {target_name}",
                            body=(
                                f"Your colony on {target_name} fell to {self.player.name}. "
                                f"Final defense state reached 0 shields / 0 defenders."
                            ),
                            event_type="planet_loss",
                            planet_name=target_name,
                            audience="player",
                            player_name=old_owner,
                        )
                        self.send_message(
                            old_owner,
                            "PLANET LOST",
                            f"Attention: Your colony on {target_name} has been captured by {self.player.name}. Our defenses were overwhelmed.",
                        )
                else:
                    msg = (
                        f"Assault successful on {target_name}. Defenses weakened "
                        f"(Shields: {planet.shields}, Defenders: {planet.defenders})."
                    )
                    self._save_shared_planet_states()
                    if planet.owner and planet.owner != self.player.name:
                        self._append_galactic_news(
                            title=f"Under Attack: {target_name}",
                            body=(
                                f"{self.player.name} damaged defenses at {target_name}. "
                                f"Current state: Shields {int(planet.shields)}, Defenders {int(planet.defenders)}."
                            ),
                            event_type="planet_attack",
                            planet_name=target_name,
                            audience="player",
                            player_name=planet.owner,
                        )

                self._append_galactic_news(
                    title="Combat Outcome: You WON",
                    body=(
                        f"Engagement vs {target_name} [PLANET] at "
                        f"{self.current_planet.name if self.current_planet else 'UNKNOWN'} "
                        f"ended won."
                    ),
                    event_type="combat_outcome",
                    planet_name=(
                        self.current_planet.name if self.current_planet else None
                    ),
                    audience="player",
                    player_name=self.player.name,
                )

                return True, msg, {"credits": raid_credits, "items": []}

            # Damage non-planet targets
            dmg_to_target = random.randint(20, 50)
            t_ship.take_damage(dmg_to_target)

            if target_data["type"] == "PLAYER":
                # Notify the loser and update their file
                self.send_message(
                    target_name,
                    "Vessel Boarded",
                    f"Alert: Your ship at {self.current_planet.name} was attacked and boarded by {self.player.name}. They made off with {earned_credits:,} credits.",
                )
                # We update the file by subtracting the stolen credits
                filename = f"{target_name.replace(' ', '_').lower()}.json"
                path = os.path.join(self.save_dir, filename)
                try:
                    with open(path, "r") as f:
                        data = json.load(f)
                    data["player"]["credits"] = max(
                        0, int(data["player"]["credits"]) - earned_credits
                    )
                    with open(path, "w") as f:
                        json.dump(data, f, indent=4)
                except:
                    pass

            self._append_galactic_news(
                title="Combat Outcome: You WON",
                body=(
                    f"Engagement vs {target_name} [{target_data['type']}] at "
                    f"{self.current_planet.name if self.current_planet else 'UNKNOWN'} "
                    f"ended won with +{int(earned_credits):,} CR."
                ),
                event_type="combat_outcome",
                planet_name=self.current_planet.name if self.current_planet else None,
                audience="player",
                player_name=self.player.name,
            )

            return True, msg, {"credits": earned_credits, "items": lost_items}
        else:
            # Player Loses
            loot_factor = random.uniform(0.1, 0.75)
            lost_credits = round(self.player.credits * loot_factor)
            self.player.credits -= lost_credits

            # Integrity Damage
            dmg = random.randint(15, 40)
            self.player.take_damage(dmg)

            if is_planet_target:
                # Even failed assaults can chip planetary shields.
                chip_damage = random.randint(20, 80)
                self.current_planet.shields = max(
                    0, self.current_planet.shields - chip_damage
                )
                msg = (
                    f"Planetary defenses held! You lost {lost_credits} credits. "
                    f"Remaining defenses - Shields: {self.current_planet.shields}, "
                    f"Defenders: {self.current_planet.defenders}. YOU HAVE BEEN BARRED FROM {target_name}!"
                )
                self._append_galactic_news(
                    title="Combat Outcome: You LOST",
                    body=(
                        f"Engagement vs {target_name} [PLANET] at "
                        f"{self.current_planet.name if self.current_planet else 'UNKNOWN'} "
                        f"ended lost with -{int(lost_credits):,} CR."
                    ),
                    event_type="combat_outcome",
                    planet_name=(
                        self.current_planet.name if self.current_planet else None
                    ),
                    audience="player",
                    player_name=self.player.name,
                )
                # Enforce ban immediately
                self.bar_player(target_name)
                session["status"] = "LOST_AND_FLED"  # Force immediate travel
                session["summary"] = {
                    "result": "LOST",
                    "target": target_name,
                    "credits_delta": -lost_credits,
                    "items": [],
                    "looted_credits": 0,
                    "stolen_credits": int(stolen_credits),
                    "looted_items": [],
                    "stolen_items": stolen_item_report,
                    "player_end": {
                        "shields": int(self.player.spaceship.current_shields),
                        "defenders": int(self.player.spaceship.current_defenders),
                        "integrity": int(self.player.spaceship.integrity),
                        "credits": int(self.player.credits),
                    },
                    "target_end": {
                        "shields": int(self._get_target_stats(session)[0]),
                        "defenders": int(self._get_target_stats(session)[1]),
                        "integrity": int(self._get_target_stats(session)[2]),
                    },
                    "message": msg,
                    "enemy_scale": float(session.get("enemy_scale", 1.0)),
                    "win_streak": int(self._get_combat_win_streak()),
                    "bounty_bonus": 0,
                    "rare_loot": [],
                }
                session["log"].append(msg)
                return session

            msg = f"Defeat! {target_name} boarded your ship and pillaged {lost_credits} credits. Hull integrity: {player_ship.integrity}%."
            self._append_galactic_news(
                title="Combat Outcome: You LOST",
                body=(
                    f"Engagement vs {target_name} [{target_data['type']}] at "
                    f"{self.current_planet.name if self.current_planet else 'UNKNOWN'} "
                    f"ended lost with -{int(lost_credits):,} CR."
                ),
                event_type="combat_outcome",
                planet_name=self.current_planet.name if self.current_planet else None,
                audience="player",
                player_name=self.player.name,
            )
            return False, msg, {"credits": lost_credits}
