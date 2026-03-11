import json
import sqlite3
import threading
import time
from pathlib import Path


def _default_db_path():
    return Path(__file__).resolve().parent / "saves" / "game_state.db"


def read_default_catalog_text(file_name):
    """Best-effort catalog read for bootstrap modules before GameManager exists."""
    db_path = _default_db_path()
    if not db_path.exists():
        return None
    try:
        conn = sqlite3.connect(str(db_path))
        row = conn.execute(
            "SELECT value_json FROM kv_store WHERE namespace=? AND key=?",
            ("catalog_texts", str(file_name)),
        ).fetchone()
        conn.close()
        if not row:
            return None
        payload = json.loads(row[0])
        text = payload.get("text") if isinstance(payload, dict) else None
        return text if isinstance(text, str) else None
    except Exception:
        return None


def _safe_json_loads(raw_value, default_value):
    if raw_value is None:
        return default_value
    if isinstance(raw_value, (dict, list, int, float, bool)):
        return raw_value
    try:
        return json.loads(raw_value)
    except Exception:
        return default_value


class SQLiteStore:
    """Single SQLite authority for runtime/server data."""

    SCHEMA_VERSION = 2
    DEFAULT_SETTINGS = {
        "server_port": 8765,
        "planet_price_penalty_multiplier": 1.0,
    }
    DEFAULT_CATALOG_FILES = (
        "planets.txt",
        "items.txt",
        "spaceships.txt",
        "smuggle_items.txt",
        "absurd_wisdom.txt",
        "engineer_phrases.txt",
        "intro.txt",
    )

    def __init__(self, db_path):
        self.db_path = str(db_path)
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._write_lock = threading.RLock()
        self._configure()
        self._init_schema()

    def _configure(self):
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.execute("PRAGMA busy_timeout=5000")

    def _init_schema(self):
        with self._write_lock:
            with self.conn:
                self.conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS kv_store (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (namespace, key)
                );

                CREATE TABLE IF NOT EXISTS accounts (
                    account_name TEXT PRIMARY KEY,
                    password_hash TEXT,
                    account_disabled INTEGER NOT NULL DEFAULT 0,
                    blacklisted INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT,
                    last_login TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS characters (
                    account_name TEXT NOT NULL,
                    character_name TEXT NOT NULL,
                    display_name TEXT,
                    payload_json TEXT NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (account_name, character_name),
                    FOREIGN KEY (account_name) REFERENCES accounts(account_name) ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS idx_characters_account ON characters(account_name);
                CREATE INDEX IF NOT EXISTS idx_characters_name ON characters(character_name);
                CREATE INDEX IF NOT EXISTS idx_characters_display_name ON characters(display_name);

                CREATE TABLE IF NOT EXISTS resources (
                    player_id INTEGER NOT NULL,
                    resource_type TEXT NOT NULL CHECK(resource_type IN ('fuel','ore','tech','bio','rare','credits')),
                    amount INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (player_id, resource_type)
                );

                CREATE TABLE IF NOT EXISTS ship_cargo (
                    player_id INTEGER NOT NULL,
                    ship_model TEXT NOT NULL,
                    resource_type TEXT NOT NULL CHECK(resource_type IN ('fuel','ore','tech','bio','rare')),
                    amount INTEGER NOT NULL DEFAULT 0,
                    max_capacity INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (player_id, ship_model, resource_type)
                );

                CREATE TABLE IF NOT EXISTS planet_production (
                    planet_id INTEGER NOT NULL,
                    resource_type TEXT NOT NULL CHECK(resource_type IN ('fuel','ore','tech','bio','rare')),
                    base_rate INTEGER NOT NULL DEFAULT 0,
                    upgrade_level INTEGER NOT NULL DEFAULT 0,
                    last_production REAL NOT NULL,
                    PRIMARY KEY (planet_id, resource_type)
                );

                CREATE TABLE IF NOT EXISTS market_prices (
                    planet_id INTEGER NOT NULL,
                    resource_type TEXT NOT NULL CHECK(resource_type IN ('fuel','ore','tech','bio','rare')),
                    current_price REAL NOT NULL,
                    last_update REAL NOT NULL,
                    PRIMARY KEY (planet_id, resource_type)
                );

                CREATE TABLE IF NOT EXISTS economy_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    start_time REAL NOT NULL,
                    end_time REAL NOT NULL,
                    multiplier REAL NOT NULL,
                    affected_resource TEXT
                );

                CREATE INDEX IF NOT EXISTS idx_resources_player_type ON resources(player_id, resource_type);
                CREATE INDEX IF NOT EXISTS idx_ship_cargo_player_type ON ship_cargo(player_id, resource_type);
                CREATE INDEX IF NOT EXISTS idx_planet_production_planet_type ON planet_production(planet_id, resource_type);
                CREATE INDEX IF NOT EXISTS idx_market_prices_planet_type ON market_prices(planet_id, resource_type);
                CREATE INDEX IF NOT EXISTS idx_economy_events_active ON economy_events(start_time, end_time);

                CREATE TABLE IF NOT EXISTS planets (
                    planet_id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE,
                    owner_id INTEGER,
                    credit_balance INTEGER DEFAULT 0,
                    market_prices JSON,
                    smuggling_inventory JSON,
                    item_modifiers JSON,
                    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS players (
                    player_id INTEGER PRIMARY KEY,
                    name TEXT UNIQUE,
                    credits INTEGER DEFAULT 5000,
                    commander_rank INTEGER DEFAULT 1,
                    owned_ships JSON
                );

                CREATE TABLE IF NOT EXISTS combat_sessions (
                    combat_id INTEGER PRIMARY KEY,
                    attacker_id INTEGER,
                    defender_id INTEGER,
                    round_number INTEGER DEFAULT 0,
                    attacker_ships JSON,
                    defender_ships JSON,
                    status TEXT DEFAULT 'active',
                    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                );

                CREATE TABLE IF NOT EXISTS game_state (
                    key TEXT PRIMARY KEY,
                    value JSON
                );

                CREATE INDEX IF NOT EXISTS idx_planets_owner_id ON planets(owner_id);
                CREATE INDEX IF NOT EXISTS idx_combat_sessions_combat_id ON combat_sessions(combat_id);
                """
                )
                self.conn.execute(
                    "INSERT OR IGNORE INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                    (self.SCHEMA_VERSION, float(time.time())),
                )

    def get_character_player_id(self, account_name, character_name):
        account = str(account_name or "").strip().lower().replace(" ", "_")
        character = str(character_name or "").strip().lower().replace(" ", "_")
        if not account or not character:
            return None
        row = self.conn.execute(
            """
            SELECT rowid FROM characters
            WHERE account_name=? AND character_name=?
            LIMIT 1
            """,
            (account, character),
        ).fetchone()
        if not row:
            return None
        try:
            return int(row["rowid"])
        except Exception:
            return None

    def get_player_name_by_id(self, player_id):
        try:
            pid = int(player_id)
        except Exception:
            return None

        row = self.conn.execute(
            "SELECT name FROM players WHERE player_id=?",
            (pid,),
        ).fetchone()
        if row and str(row["name"] or "").strip():
            return str(row["name"])

        char_row = self.conn.execute(
            """
            SELECT display_name, character_name
            FROM characters
            WHERE rowid=?
            LIMIT 1
            """,
            (pid,),
        ).fetchone()
        if not char_row:
            return None
        display = str(char_row["display_name"] or "").strip()
        if display:
            return display
        name = str(char_row["character_name"] or "").strip()
        return name or None

    def upsert_planet_row(
        self,
        planet_id,
        name,
        owner_id=None,
        credit_balance=0,
        market_prices=None,
        smuggling_inventory=None,
        item_modifiers=None,
    ):
        payload_prices = json.dumps(dict(market_prices or {}))
        payload_smuggle = json.dumps(dict(smuggling_inventory or {}))
        payload_modifiers = json.dumps(dict(item_modifiers or {}))
        with self._write_lock:
            with self.conn:
                self.conn.execute(
                """
                INSERT INTO planets(
                    planet_id, name, owner_id, credit_balance,
                    market_prices, smuggling_inventory, item_modifiers, last_updated
                ) VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(planet_id) DO UPDATE SET
                    name=excluded.name,
                    owner_id=excluded.owner_id,
                    credit_balance=excluded.credit_balance,
                    market_prices=excluded.market_prices,
                    smuggling_inventory=excluded.smuggling_inventory,
                    item_modifiers=excluded.item_modifiers,
                    last_updated=CURRENT_TIMESTAMP
                """,
                (
                    int(planet_id),
                    str(name or ""),
                    (int(owner_id) if owner_id is not None else None),
                    int(credit_balance or 0),
                    payload_prices,
                    payload_smuggle,
                    payload_modifiers,
                ),
                )

    def list_planets_rows(self):
        rows = self.conn.execute(
            """
            SELECT planet_id, name, owner_id, credit_balance,
                   market_prices, smuggling_inventory, item_modifiers, last_updated
            FROM planets
            ORDER BY planet_id ASC
            """
        ).fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "planet_id": int(row["planet_id"]),
                    "name": str(row["name"] or ""),
                    "owner_id": (
                        int(row["owner_id"]) if row["owner_id"] is not None else None
                    ),
                    "credit_balance": int(row["credit_balance"] or 0),
                    "market_prices": _safe_json_loads(row["market_prices"], {}),
                    "smuggling_inventory": _safe_json_loads(
                        row["smuggling_inventory"], {}
                    ),
                    "item_modifiers": _safe_json_loads(row["item_modifiers"], {}),
                    "last_updated": row["last_updated"],
                }
            )
        return out

    def upsert_player_row(self, player_id, name, credits=5000, commander_rank=1, owned_ships=None):
        with self._write_lock:
            with self.conn:
                self.conn.execute(
                """
                INSERT INTO players(player_id, name, credits, commander_rank, owned_ships)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(player_id) DO UPDATE SET
                    name=excluded.name,
                    credits=excluded.credits,
                    commander_rank=excluded.commander_rank,
                    owned_ships=excluded.owned_ships
                """,
                (
                    int(player_id),
                    str(name or ""),
                    int(credits or 0),
                    int(commander_rank or 1),
                    json.dumps(list(owned_ships or [])),
                ),
                )

    def get_player_row(self, player_id):
        row = self.conn.execute(
            """
            SELECT player_id, name, credits, commander_rank, owned_ships
            FROM players WHERE player_id=?
            """,
            (int(player_id),),
        ).fetchone()
        if not row:
            return None
        return {
            "player_id": int(row["player_id"]),
            "name": str(row["name"] or ""),
            "credits": int(row["credits"] or 0),
            "commander_rank": int(row["commander_rank"] or 1),
            "owned_ships": json.loads(row["owned_ships"] or "[]"),
        }

    def list_player_rows(self):
        rows = self.conn.execute(
            """
            SELECT player_id, name, credits, commander_rank, owned_ships
            FROM players ORDER BY player_id ASC
            """
        ).fetchall()
        return [
            {
                "player_id": int(row["player_id"]),
                "name": str(row["name"] or ""),
                "credits": int(row["credits"] or 0),
                "commander_rank": int(row["commander_rank"] or 1),
                "owned_ships": json.loads(row["owned_ships"] or "[]"),
            }
            for row in rows
        ]

    def create_combat_session(
        self,
        attacker_id,
        defender_id,
        attacker_ships,
        defender_ships,
        status="active",
        round_number=0,
    ):
        with self._write_lock:
            with self.conn:
                cursor = self.conn.execute(
                """
                INSERT INTO combat_sessions(
                    attacker_id, defender_id, round_number,
                    attacker_ships, defender_ships, status
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    int(attacker_id),
                    int(defender_id),
                    int(round_number or 0),
                    json.dumps(list(attacker_ships or [])),
                    json.dumps(list(defender_ships or [])),
                    str(status or "active"),
                ),
                )
                return int(cursor.lastrowid)

    def get_combat_session(self, combat_id):
        row = self.conn.execute(
            """
            SELECT combat_id, attacker_id, defender_id, round_number,
                   attacker_ships, defender_ships, status, started_at
            FROM combat_sessions WHERE combat_id=?
            """,
            (int(combat_id),),
        ).fetchone()
        if not row:
            return None
        return {
            "combat_id": int(row["combat_id"]),
            "attacker_id": int(row["attacker_id"] or 0),
            "defender_id": int(row["defender_id"] or 0),
            "round_number": int(row["round_number"] or 0),
            "attacker_ships": json.loads(row["attacker_ships"] or "[]"),
            "defender_ships": json.loads(row["defender_ships"] or "[]"),
            "status": str(row["status"] or "active"),
            "started_at": row["started_at"],
        }

    def update_combat_session(self, combat_id, round_number, attacker_ships, defender_ships, status):
        with self._write_lock:
            with self.conn:
                self.conn.execute(
                """
                UPDATE combat_sessions
                SET round_number=?, attacker_ships=?, defender_ships=?, status=?
                WHERE combat_id=?
                """,
                (
                    int(round_number or 0),
                    json.dumps(list(attacker_ships or [])),
                    json.dumps(list(defender_ships or [])),
                    str(status or "active"),
                    int(combat_id),
                ),
                )

    def list_combat_sessions(self):
        rows = self.conn.execute(
            """
            SELECT combat_id, attacker_id, defender_id, round_number,
                   attacker_ships, defender_ships, status, started_at
            FROM combat_sessions
            ORDER BY combat_id ASC
            """
        ).fetchall()
        out = []
        for row in rows:
            out.append(
                {
                    "combat_id": int(row["combat_id"]),
                    "attacker_id": int(row["attacker_id"] or 0),
                    "defender_id": int(row["defender_id"] or 0),
                    "round_number": int(row["round_number"] or 0),
                    "attacker_ships": json.loads(row["attacker_ships"] or "[]"),
                    "defender_ships": json.loads(row["defender_ships"] or "[]"),
                    "status": str(row["status"] or "active"),
                    "started_at": row["started_at"],
                }
            )
        return out

    def set_game_state_value(self, key, value):
        with self._write_lock:
            with self.conn:
                self.conn.execute(
                """
                INSERT INTO game_state(key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value
                """,
                (str(key), json.dumps(value)),
                )

    def get_game_state_value(self, key, default=None):
        row = self.conn.execute(
            "SELECT value FROM game_state WHERE key=?",
            (str(key),),
        ).fetchone()
        if not row:
            return default
        raw = row["value"]
        if raw is None:
            return default
        if isinstance(raw, (int, float, bool, dict, list)):
            return raw
        try:
            return json.loads(raw)
        except Exception:
            return raw

    def get_all_game_state(self):
        rows = self.conn.execute("SELECT key, value FROM game_state").fetchall()
        out = {}
        for row in rows:
            key = str(row["key"])
            raw = row["value"]
            if isinstance(raw, (int, float, bool, dict, list)):
                out[key] = raw
                continue
            try:
                out[key] = json.loads(raw)
            except Exception:
                out[key] = raw
        return out

    def upsert_player_resource(self, player_id, resource_type, amount):
        if player_id is None:
            return False
        resource = str(resource_type or "").strip().lower()
        if resource not in {"fuel", "ore", "tech", "bio", "rare", "credits"}:
            return False
        with self._write_lock:
            with self.conn:
                self.conn.execute(
                """
                INSERT INTO resources(player_id, resource_type, amount, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(player_id, resource_type) DO UPDATE SET
                    amount=excluded.amount,
                    updated_at=excluded.updated_at
                """,
                (int(player_id), resource, int(amount), float(time.time())),
                )
        return True

    def adjust_player_resource(self, player_id, resource_type, delta):
        if player_id is None:
            return 0
        resource = str(resource_type or "").strip().lower()
        if resource not in {"fuel", "ore", "tech", "bio", "rare", "credits"}:
            return 0

        step = int(delta or 0)
        now_ts = float(time.time())
        with self._write_lock:
            with self.conn:
                self.conn.execute(
                    """
                    INSERT INTO resources(player_id, resource_type, amount, updated_at)
                    VALUES (?, ?, MAX(0, ?), ?)
                    ON CONFLICT(player_id, resource_type) DO UPDATE SET
                        amount=MAX(0, resources.amount + excluded.amount),
                        updated_at=excluded.updated_at
                    """,
                    (int(player_id), resource, step, now_ts),
                )
                row = self.conn.execute(
                    """
                    SELECT amount FROM resources
                    WHERE player_id=? AND resource_type=?
                    """,
                    (int(player_id), resource),
                ).fetchone()
        if not row:
            return 0
        return int(row["amount"] or 0)

    def get_player_resource_amount(self, player_id, resource_type):
        if player_id is None:
            return 0
        resource = str(resource_type or "").strip().lower()
        row = self.conn.execute(
            """
            SELECT amount FROM resources WHERE player_id=? AND resource_type=?
            """,
            (int(player_id), resource),
        ).fetchone()
        if not row:
            return 0
        try:
            return int(row["amount"])
        except Exception:
            return 0

    def get_player_resources(self, player_id):
        if player_id is None:
            return {}
        rows = self.conn.execute(
            """
            SELECT resource_type, amount FROM resources WHERE player_id=?
            """,
            (int(player_id),),
        ).fetchall()
        out = {}
        for row in rows:
            out[str(row["resource_type"])] = int(row["amount"])
        return out

    def upsert_ship_cargo(self, player_id, ship_model, resource_type, amount, max_capacity):
        if player_id is None:
            return False
        ship = str(ship_model or "").strip()
        resource = str(resource_type or "").strip().lower()
        if not ship or resource not in {"fuel", "ore", "tech", "bio", "rare"}:
            return False
        with self._write_lock:
            with self.conn:
                self.conn.execute(
                """
                INSERT INTO ship_cargo(player_id, ship_model, resource_type, amount, max_capacity, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(player_id, ship_model, resource_type) DO UPDATE SET
                    amount=excluded.amount,
                    max_capacity=excluded.max_capacity,
                    updated_at=excluded.updated_at
                """,
                (
                    int(player_id),
                    ship,
                    resource,
                    int(max(0, amount)),
                    int(max(0, max_capacity)),
                    float(time.time()),
                ),
                )
        return True

    def get_ship_cargo(self, player_id, ship_model):
        if player_id is None:
            return {}
        ship = str(ship_model or "").strip()
        rows = self.conn.execute(
            """
            SELECT resource_type, amount, max_capacity
            FROM ship_cargo
            WHERE player_id=? AND ship_model=?
            """,
            (int(player_id), ship),
        ).fetchall()
        out = {}
        for row in rows:
            out[str(row["resource_type"])] = {
                "amount": int(row["amount"]),
                "max_capacity": int(row["max_capacity"]),
            }
        return out

    def upsert_planet_production(self, planet_id, resource_type, base_rate, upgrade_level=0, last_production=None):
        resource = str(resource_type or "").strip().lower()
        if resource not in {"fuel", "ore", "tech", "bio", "rare"}:
            return False
        last_ts = float(last_production if last_production is not None else time.time())
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO planet_production(planet_id, resource_type, base_rate, upgrade_level, last_production)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(planet_id, resource_type) DO UPDATE SET
                    base_rate=excluded.base_rate,
                    upgrade_level=excluded.upgrade_level,
                    last_production=excluded.last_production
                """,
                (int(planet_id), resource, int(base_rate), int(upgrade_level), last_ts),
            )
        return True

    def get_planet_production(self, planet_id=None):
        if planet_id is None:
            rows = self.conn.execute(
                "SELECT planet_id, resource_type, base_rate, upgrade_level, last_production FROM planet_production"
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT planet_id, resource_type, base_rate, upgrade_level, last_production
                FROM planet_production
                WHERE planet_id=?
                """,
                (int(planet_id),),
            ).fetchall()
        out = {}
        for row in rows:
            p_id = int(row["planet_id"])
            bucket = out.setdefault(p_id, {})
            bucket[str(row["resource_type"])] = {
                "base_rate": int(row["base_rate"]),
                "upgrade_level": int(row["upgrade_level"]),
                "last_production": float(row["last_production"]),
            }
        return out

    def touch_planet_production_timestamp(self, planet_id, resource_type, ts=None):
        when = float(ts if ts is not None else time.time())
        with self.conn:
            self.conn.execute(
                """
                UPDATE planet_production
                SET last_production=?
                WHERE planet_id=? AND resource_type=?
                """,
                (when, int(planet_id), str(resource_type or "").strip().lower()),
            )

    def upsert_market_price(self, planet_id, resource_type, current_price, last_update=None):
        resource = str(resource_type or "").strip().lower()
        if resource not in {"fuel", "ore", "tech", "bio", "rare"}:
            return False
        last_ts = float(last_update if last_update is not None else time.time())
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO market_prices(planet_id, resource_type, current_price, last_update)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(planet_id, resource_type) DO UPDATE SET
                    current_price=excluded.current_price,
                    last_update=excluded.last_update
                """,
                (int(planet_id), resource, float(current_price), last_ts),
            )
        return True

    def get_market_prices(self, planet_id=None):
        if planet_id is None:
            rows = self.conn.execute(
                "SELECT planet_id, resource_type, current_price, last_update FROM market_prices"
            ).fetchall()
        else:
            rows = self.conn.execute(
                """
                SELECT planet_id, resource_type, current_price, last_update
                FROM market_prices WHERE planet_id=?
                """,
                (int(planet_id),),
            ).fetchall()
        out = {}
        for row in rows:
            p_id = int(row["planet_id"])
            bucket = out.setdefault(p_id, {})
            bucket[str(row["resource_type"])] = {
                "current_price": float(row["current_price"]),
                "last_update": float(row["last_update"]),
            }
        return out

    def add_economy_event(self, event_type, start_time, end_time, multiplier, affected_resource=None):
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO economy_events(event_type, start_time, end_time, multiplier, affected_resource)
                VALUES (?, ?, ?, ?, ?)
                """,
                (
                    str(event_type or "").strip().upper(),
                    float(start_time),
                    float(end_time),
                    float(multiplier),
                    (str(affected_resource).strip().lower() if affected_resource else None),
                ),
            )
        return True

    def get_active_economy_events(self, now_ts=None):
        now = float(now_ts if now_ts is not None else time.time())
        rows = self.conn.execute(
            """
            SELECT id, event_type, start_time, end_time, multiplier, affected_resource
            FROM economy_events
            WHERE start_time <= ? AND end_time >= ?
            ORDER BY end_time ASC
            """,
            (now, now),
        ).fetchall()
        return [
            {
                "id": int(row["id"]),
                "event_type": str(row["event_type"]),
                "start_time": float(row["start_time"]),
                "end_time": float(row["end_time"]),
                "multiplier": float(row["multiplier"]),
                "affected_resource": (
                    str(row["affected_resource"]).lower()
                    if row["affected_resource"] is not None
                    else None
                ),
            }
            for row in rows
        ]

    def close(self):
        try:
            self.conn.close()
        except Exception:
            pass

    def set_kv(self, namespace, key, payload):
        with self._write_lock:
            with self.conn:
                self.conn.execute(
                """
                INSERT INTO kv_store(namespace, key, value_json, updated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(namespace, key) DO UPDATE SET
                    value_json=excluded.value_json,
                    updated_at=excluded.updated_at
                """,
                (
                    str(namespace),
                    str(key),
                    json.dumps(payload, ensure_ascii=True),
                    float(time.time()),
                ),
                )

    def get_kv(self, namespace, key, default=None):
        row = self.conn.execute(
            "SELECT value_json FROM kv_store WHERE namespace=? AND key=?",
            (str(namespace), str(key)),
        ).fetchone()
        if not row:
            return default
        try:
            return json.loads(row["value_json"])
        except Exception:
            return default

    def delete_kv(self, namespace, key):
        with self._write_lock:
            with self.conn:
                self.conn.execute(
                "DELETE FROM kv_store WHERE namespace=? AND key=?",
                (str(namespace), str(key)),
                )

    def seed_settings_from_file(self, game_config_path):
        path = Path(game_config_path)
        if not path.exists():
            return False
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return False
        settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
        if not isinstance(settings, dict):
            return False

        for key, value in settings.items():
            self.set_kv("settings", str(key), value)
        return True

    def seed_default_settings(self):
        rows = self.conn.execute(
            "SELECT key FROM kv_store WHERE namespace='settings'"
        ).fetchall()
        existing = {str(row["key"]) for row in rows}
        for key, value in self.DEFAULT_SETTINGS.items():
            if str(key) in existing:
                continue
            self.set_kv("settings", str(key), value)
        return True

    def get_all_settings(self):
        rows = self.conn.execute(
            "SELECT key, value_json FROM kv_store WHERE namespace='settings'"
        ).fetchall()
        result = {}
        for row in rows:
            try:
                result[str(row["key"])] = json.loads(row["value_json"])
            except Exception:
                continue
        return result

    def set_catalog_text(self, file_name, content):
        self.set_kv("catalog_texts", str(file_name), {"text": str(content or "")})

    def get_catalog_text(self, file_name, default=None):
        payload = self.get_kv("catalog_texts", str(file_name), default=None)
        if isinstance(payload, dict) and isinstance(payload.get("text"), str):
            return payload["text"]
        return default

    def export_catalog_texts_to_files(self, texts_dir, file_names=None):
        root = Path(texts_dir)
        root.mkdir(parents=True, exist_ok=True)
        names = tuple(file_names or self.DEFAULT_CATALOG_FILES)
        exported = 0
        for file_name in names:
            text = self.get_catalog_text(file_name, default=None)
            if not isinstance(text, str):
                continue
            try:
                (root / str(file_name)).write_text(text, encoding="utf-8")
                exported += 1
            except Exception:
                continue
        return exported

    def upsert_account_payload(self, account_name, payload):
        account = str(account_name or "").strip().lower().replace(" ", "_")
        if not account:
            return False
        data = dict(payload or {})
        with self._write_lock:
            with self.conn:
                self.conn.execute(
                """
                INSERT INTO accounts(
                    account_name, password_hash, account_disabled, blacklisted,
                    created_at, last_login, payload_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(account_name) DO UPDATE SET
                    password_hash=excluded.password_hash,
                    account_disabled=excluded.account_disabled,
                    blacklisted=excluded.blacklisted,
                    created_at=excluded.created_at,
                    last_login=excluded.last_login,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    account,
                    str(data.get("password_hash") or "") or None,
                    1 if bool(data.get("account_disabled", False)) else 0,
                    1 if bool(data.get("blacklisted", False)) else 0,
                    data.get("created_at"),
                    data.get("last_login"),
                    json.dumps(data, ensure_ascii=True),
                    float(time.time()),
                ),
                )
        return True

    def get_account_payload(self, account_name):
        account = str(account_name or "").strip().lower().replace(" ", "_")
        if not account:
            return None
        row = self.conn.execute(
            "SELECT payload_json FROM accounts WHERE account_name=?", (account,)
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["payload_json"])
        except Exception:
            return None

    def account_exists(self, account_name):
        account = str(account_name or "").strip().lower().replace(" ", "_")
        if not account:
            return False
        row = self.conn.execute(
            "SELECT 1 FROM accounts WHERE account_name=? LIMIT 1", (account,)
        ).fetchone()
        return bool(row)

    def _safe_key(self, value):
        return str(value or "").strip().lower().replace(" ", "_")

    def is_account_blocked(self, account_name):
        account = str(account_name or "").strip().lower().replace(" ", "_")
        if not account:
            return False
        row = self.conn.execute(
            "SELECT account_disabled, blacklisted FROM accounts WHERE account_name=?",
            (account,),
        ).fetchone()
        if not row:
            return False
        return bool(int(row["account_disabled"] or 0)) or bool(
            int(row["blacklisted"] or 0)
        )

    def delete_account(self, account_name):
        account = str(account_name or "").strip().lower().replace(" ", "_")
        if not account:
            return False
        with self._write_lock:
            with self.conn:
                self.conn.execute("DELETE FROM accounts WHERE account_name=?", (account,))
        return True

    def upsert_character_payload(self, account_name, character_name, payload, display_name=None):
        account = str(account_name or "").strip().lower().replace(" ", "_")
        character = str(character_name or "").strip().lower().replace(" ", "_")
        if not account or not character:
            return False

        if not self.account_exists(account):
            self.upsert_account_payload(account, {"account_name": account, "characters": []})

        data = dict(payload or {})
        name = str(display_name or data.get("player", {}).get("name") or character)
        with self._write_lock:
            with self.conn:
                self.conn.execute(
                """
                INSERT INTO characters(account_name, character_name, display_name, payload_json, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(account_name, character_name) DO UPDATE SET
                    display_name=excluded.display_name,
                    payload_json=excluded.payload_json,
                    updated_at=excluded.updated_at
                """,
                (
                    account,
                    character,
                    name,
                    json.dumps(data, ensure_ascii=True),
                    float(time.time()),
                ),
                )
        return True

    def get_character_payload(self, account_name, character_name):
        account = str(account_name or "").strip().lower().replace(" ", "_")
        character = str(character_name or "").strip().lower().replace(" ", "_")
        if not account or not character:
            return None
        row = self.conn.execute(
            """
            SELECT payload_json FROM characters
            WHERE account_name=? AND character_name=?
            """,
            (account, character),
        ).fetchone()
        if not row:
            return None
        try:
            return json.loads(row["payload_json"])
        except Exception:
            return None

    def find_character_payload_by_name(self, character_name):
        character = str(character_name or "").strip().lower().replace(" ", "_")
        if not character:
            return None
        row = self.conn.execute(
            """
            SELECT account_name, character_name, payload_json
            FROM characters
            WHERE character_name=?
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (character,),
        ).fetchone()
        if not row:
            return None
        try:
            payload = json.loads(row["payload_json"])
        except Exception:
            return None
        return {
            "account_name": row["account_name"],
            "character_name": row["character_name"],
            "payload": payload,
        }

    def delete_character(self, account_name, character_name):
        account = str(account_name or "").strip().lower().replace(" ", "_")
        character = str(character_name or "").strip().lower().replace(" ", "_")
        if not account or not character:
            return False
        with self.conn:
            self.conn.execute(
                "DELETE FROM characters WHERE account_name=? AND character_name=?",
                (account, character),
            )
        return True

    def list_characters(self, account_name):
        account = str(account_name or "").strip().lower().replace(" ", "_")
        if not account:
            return []
        rows = self.conn.execute(
            """
            SELECT character_name, display_name, payload_json, updated_at
            FROM characters
            WHERE account_name=?
            ORDER BY updated_at DESC
            """,
            (account,),
        ).fetchall()
        output = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                payload = {}
            output.append(
                {
                    "character_name": row["character_name"],
                    "display_name": row["display_name"],
                    "payload": payload,
                    "updated_at": float(row["updated_at"] or 0.0),
                }
            )
        return output

    def iter_accounts(self):
        rows = self.conn.execute(
            "SELECT account_name, payload_json, updated_at FROM accounts ORDER BY account_name ASC"
        ).fetchall()
        output = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                payload = {}
            output.append(
                {
                    "account_name": row["account_name"],
                    "payload": payload,
                    "updated_at": float(row["updated_at"] or 0.0),
                }
            )
        return output

    def iter_all_characters(self):
        rows = self.conn.execute(
            "SELECT account_name, character_name, display_name, payload_json FROM characters"
        ).fetchall()
        output = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except Exception:
                continue
            output.append(
                {
                    "account_name": row["account_name"],
                    "character_name": row["character_name"],
                    "display_name": row["display_name"],
                    "payload": payload,
                }
            )
        return output

    def iter_character_summaries(self, active_only=False):
        where = ""
        if active_only:
            where = "WHERE COALESCE(a.account_disabled, 0)=0 AND COALESCE(a.blacklisted, 0)=0"
        rows = self.conn.execute(
            f"""
            SELECT c.account_name, c.character_name, c.display_name
            FROM characters c
            LEFT JOIN accounts a ON a.account_name = c.account_name
            {where}
            ORDER BY c.account_name ASC, c.character_name ASC
            """
        ).fetchall()
        return [
            {
                "account_name": row["account_name"],
                "character_name": row["character_name"],
                "display_name": row["display_name"],
            }
            for row in rows
        ]

    def find_character_refs_by_name(self, name, active_only=False):
        target_display = str(name or "").strip().lower()
        target_key = self._safe_key(name)
        if not target_display and not target_key:
            return []

        filters = []
        if active_only:
            filters.append("COALESCE(a.account_disabled, 0)=0")
            filters.append("COALESCE(a.blacklisted, 0)=0")
        where_tail = ""
        if filters:
            where_tail = " AND " + " AND ".join(filters)

        rows = self.conn.execute(
            f"""
            SELECT c.account_name, c.character_name
            FROM characters c
            LEFT JOIN accounts a ON a.account_name = c.account_name
            WHERE (LOWER(COALESCE(c.display_name, '')) = ? OR c.character_name = ?)
            {where_tail}
            """,
            (target_display, target_key),
        ).fetchall()

        return [
            {
                "account_name": row["account_name"],
                "character_name": row["character_name"],
            }
            for row in rows
        ]

    def commander_name_exists(self, name):
        return bool(self.find_character_refs_by_name(name, active_only=False))

    def migrate_json_saves_once(self, save_dir, game_config_path=None, server_root=None):
        already_migrated = bool(self.get_kv("meta", "json_migrated_v1", default=False))

        self.seed_default_settings()

        if game_config_path:
            self.seed_settings_from_file(game_config_path)

        if server_root is not None:
            root_dir = Path(server_root).resolve()
        elif game_config_path:
            root_dir = Path(game_config_path).resolve().parent
        else:
            root_dir = Path(save_dir).resolve().parent

        texts_dir = root_dir / "assets" / "texts"
        for file_name in self.DEFAULT_CATALOG_FILES:
            text_path = texts_dir / file_name
            if not text_path.exists():
                continue
            try:
                self.set_catalog_text(file_name, text_path.read_text(encoding="utf-8"))
            except Exception:
                continue

        # Keep text assets mirrored from SQLite so client/server asset sync remains DB-driven.
        self.export_catalog_texts_to_files(texts_dir, file_names=self.DEFAULT_CATALOG_FILES)

        if already_migrated:
            return False

        root = Path(save_dir)
        if root.exists():
            shared_map = {
                "universe_planets.json": "universe_planets",
                "galactic_news.json": "galactic_news",
                "winner_board.json": "winner_board",
                "analytics_metrics.json": "analytics_metrics",
            }
            for filename, key in shared_map.items():
                path = root / filename
                if not path.exists():
                    continue
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                self.set_kv("shared", key, payload)

            for entry in root.iterdir():
                if not entry.is_dir():
                    continue
                account = str(entry.name).strip().lower().replace(" ", "_")
                auth_path = entry / "ACCOUNT.json"
                if auth_path.exists():
                    try:
                        auth_payload = json.loads(auth_path.read_text(encoding="utf-8"))
                        self.upsert_account_payload(account, auth_payload)
                    except Exception:
                        pass
                for char_file in entry.glob("*.json"):
                    if char_file.name.lower() == "account.json":
                        continue
                    try:
                        payload = json.loads(char_file.read_text(encoding="utf-8"))
                    except Exception:
                        continue
                    character = str(payload.get("character_name") or char_file.stem).strip().lower().replace(" ", "_")
                    display_name = str(payload.get("player", {}).get("name") or character)
                    self.upsert_character_payload(account, character, payload, display_name)

            for json_path in root.glob("*.json"):
                low = json_path.name.lower()
                if low in {
                    "universe_planets.json",
                    "galactic_news.json",
                    "winner_board.json",
                    "analytics_metrics.json",
                }:
                    continue
                try:
                    payload = json.loads(json_path.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                if str(payload.get("password_hash") or "").strip():
                    account = str(payload.get("account_name") or json_path.stem).strip().lower().replace(" ", "_")
                    if account:
                        self.upsert_account_payload(account, payload)
                    continue
                account = str(payload.get("account_name") or json_path.stem).strip().lower().replace(" ", "_")
                character = str(payload.get("character_name") or json_path.stem).strip().lower().replace(" ", "_")
                display_name = str(payload.get("player", {}).get("name") or character)
                self.upsert_character_payload(account, character, payload, display_name)

        self.set_kv("meta", "json_migrated_v1", True)
        self.set_kv("meta", "json_migrated_at", float(time.time()))
        return True

    def _infer_planet_resource_type(self, planet_name):
        name = str(planet_name or "").lower()
        if any(token in name for token in ("gas", "nebula", "aurora", "pyro", "nova")):
            return "fuel"
        if any(token in name for token in ("mine", "aster", "mast", "rock", "titan")):
            return "ore"
        if any(token in name for token in ("zephyr", "cyber", "tech", "quant", "celest")):
            return "tech"
        if any(token in name for token in ("atlant", "bio", "flora", "gaia", "eden")):
            return "bio"
        if any(token in name for token in ("shadow", "void", "shad", "euph", "rare")):
            return "rare"
        return "ore"

    def migrate_economy_seed(self, dry_run=False):
        seeded_key = "economy_seeded_v1"
        if bool(self.get_kv("meta", seeded_key, default=False)):
            return {"ok": True, "changed": False, "reason": "already-seeded"}

        changed = {
            "players": 0,
            "resources": 0,
            "ship_cargo": 0,
            "planet_production": 0,
            "market_prices": 0,
        }

        base_prices = {
            "fuel": 11.0,
            "ore": 18.0,
            "tech": 42.0,
            "bio": 24.0,
            "rare": 95.0,
        }

        # Seed per-player resources from existing character payloads.
        for row in list(self.iter_all_characters()):
            account_name = str(row.get("account_name", ""))
            character_name = str(row.get("character_name", ""))
            payload = dict(row.get("payload") or {})
            p_data = dict(payload.get("player") or {})
            s_data = dict(p_data.get("spaceship") or {})

            player_id = self.get_character_player_id(account_name, character_name)
            if player_id is None:
                continue
            changed["players"] += 1

            credits = int(p_data.get("credits", 0) or 0)
            defaults = {
                "fuel": int(max(20, float(s_data.get("fuel", 0) or 0))),
                "ore": 30,
                "tech": 10,
                "bio": 10,
                "rare": 2,
                "credits": credits,
            }

            for resource_type, amount in defaults.items():
                if not dry_run:
                    self.upsert_player_resource(player_id, resource_type, int(amount))
                changed["resources"] += 1

            ship_model = str(s_data.get("model") or "Unknown")
            max_fuel = int(max(40, float(s_data.get("max_fuel", defaults["fuel"] * 1.2) or 40)))
            cargo_defaults = {
                "fuel": (defaults["fuel"], max_fuel),
                "ore": (defaults["ore"], max(20, int(float(s_data.get("current_cargo", 20) or 20) * 2))),
                "tech": (defaults["tech"], max(10, int(float(s_data.get("current_cargo", 20) or 20)))),
                "bio": (defaults["bio"], max(10, int(float(s_data.get("current_cargo", 20) or 20)))),
                "rare": (defaults["rare"], max(8, int(float(s_data.get("current_cargo", 20) or 20) * 0.5))),
            }
            for resource_type, (amount, cap) in cargo_defaults.items():
                if not dry_run:
                    self.upsert_ship_cargo(
                        player_id,
                        ship_model,
                        resource_type,
                        int(max(0, amount)),
                        int(max(1, cap)),
                    )
                changed["ship_cargo"] += 1

        # Seed planet production + market prices from shared universe if present.
        universe = self.get_kv("shared", "universe_planets", default={}) or {}
        if isinstance(universe, dict):
            for key, state in universe.items():
                try:
                    planet_id = int(key)
                except Exception:
                    continue
                name = str((state or {}).get("name", f"planet-{planet_id}"))
                main_resource = self._infer_planet_resource_type(name)

                for resource in ("fuel", "ore", "tech", "bio", "rare"):
                    if resource == main_resource:
                        base_rate = 72
                    else:
                        base_rate = 16
                    if not dry_run:
                        self.upsert_planet_production(
                            planet_id,
                            resource,
                            int(base_rate),
                            upgrade_level=0,
                            last_production=float(time.time()),
                        )
                    changed["planet_production"] += 1

                    modifier = 1.0
                    if resource == main_resource:
                        modifier = 0.82
                    price = float(base_prices[resource]) * modifier
                    if not dry_run:
                        self.upsert_market_price(
                            planet_id,
                            resource,
                            float(price),
                            last_update=float(time.time()),
                        )
                    changed["market_prices"] += 1

        if not dry_run:
            self.set_kv("meta", seeded_key, True)
            self.set_kv("meta", "economy_seeded_at", float(time.time()))

        return {"ok": True, "changed": True, "details": changed, "dry_run": bool(dry_run)}
