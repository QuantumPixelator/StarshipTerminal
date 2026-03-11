import sys
import tempfile
import unittest
from pathlib import Path

SERVER_DIR = Path(__file__).resolve().parents[1]
if str(SERVER_DIR) not in sys.path:
    sys.path.insert(0, str(SERVER_DIR))

from sqlite_store import SQLiteStore

try:
    from config import ConfigApp, messagebox as config_messagebox
except Exception:  # pragma: no cover
    ConfigApp = None
    config_messagebox = None


class _BoolVar:
    def __init__(self, value=False):
        self._value = bool(value)

    def get(self):
        return bool(self._value)

    def set(self, value):
        self._value = bool(value)


class _DummyLabel:
    def configure(self, **kwargs):
        return None


@unittest.skipIf(ConfigApp is None, "config module unavailable in test environment")
class TestConfigDbAdmin(unittest.TestCase):
    def setUp(self):
        self._orig_messagebox = config_messagebox

    def tearDown(self):
        if ConfigApp is not None:
            import config as config_module

            config_module.messagebox = self._orig_messagebox

    def _build_app(self, store, saves_dir):
        app = ConfigApp.__new__(ConfigApp)
        app.store = store
        app.saves_dir = str(saves_dir)
        app.selected_account_auth_path = None
        app.selected_account_name = None
        app.selected_commander_record = None
        app.selected_player_path = None
        app.player_disabled_var = _BoolVar(False)
        app.player_blacklisted_var = _BoolVar(False)
        app.players_selected_info = _DummyLabel()
        app.commander_selected_info = _DummyLabel()
        app._clear_planet_owner_references = lambda *args, **kwargs: None
        app._clear_account_owner_references = lambda *args, **kwargs: None
        app._set_player_action_mode = lambda *args, **kwargs: None
        app.refresh_players_list = lambda *args, **kwargs: None
        app._set_section_dirty = lambda *args, **kwargs: None
        return app

    def test_delete_commander_record_db_path_updates_auth_payload(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            saves_dir = Path(tmpdir) / "saves"
            saves_dir.mkdir(parents=True, exist_ok=True)
            store = SQLiteStore(str(saves_dir / "game_state.db"))

            store.upsert_account_payload(
                "pilot",
                {
                    "account_name": "pilot",
                    "password_hash": "hash",
                    "characters": [
                        {"character_name": "captain", "display_name": "Captain"},
                        {"character_name": "wing", "display_name": "Wing"},
                    ],
                },
            )
            store.upsert_character_payload(
                "pilot",
                "captain",
                {
                    "account_name": "pilot",
                    "character_name": "captain",
                    "player": {"name": "Captain", "owned_planets": {}},
                },
                "Captain",
            )

            app = self._build_app(store, saves_dir)
            app.selected_account_auth_path = "dbauth://pilot"

            ok, name, reason = ConfigApp._delete_commander_record(
                app,
                {
                    "path": "db://pilot/captain",
                    "character_name": "captain",
                    "display_name": "Captain",
                },
                prompt=False,
            )

            self.assertTrue(ok)
            self.assertEqual(reason, "ok")
            self.assertEqual(name, "Captain")
            self.assertIsNone(store.get_character_payload("pilot", "captain"))

            auth = store.get_account_payload("pilot")
            chars = list(auth.get("characters", []) or [])
            self.assertEqual(len(chars), 1)
            self.assertEqual(str(chars[0].get("character_name")), "wing")
            store.close()

    def test_delete_selected_player_uses_dbauth_path(self):
        import config as config_module

        class _Msg:
            @staticmethod
            def askyesno(*args, **kwargs):
                return True

            @staticmethod
            def showinfo(*args, **kwargs):
                return None

            @staticmethod
            def showerror(*args, **kwargs):
                raise AssertionError(f"Unexpected showerror call: {args}")

        config_module.messagebox = _Msg

        with tempfile.TemporaryDirectory() as tmpdir:
            saves_dir = Path(tmpdir) / "saves"
            saves_dir.mkdir(parents=True, exist_ok=True)
            store = SQLiteStore(str(saves_dir / "game_state.db"))
            store.upsert_account_payload(
                "pilot",
                {
                    "account_name": "pilot",
                    "password_hash": "hash",
                    "characters": [],
                },
            )

            app = self._build_app(store, saves_dir)
            app.selected_account_name = "pilot"
            app._collect_player_account_records = lambda: [
                {
                    "account_name": "pilot",
                    "auth_path": "dbauth://pilot",
                    "commanders": [],
                }
            ]

            ConfigApp.delete_selected_player(app)

            self.assertIsNone(store.get_account_payload("pilot"))
            self.assertIsNone(app.selected_account_name)
            store.close()

    def test_delete_commander_record_rejects_non_db_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            saves_dir = Path(tmpdir) / "saves"
            saves_dir.mkdir(parents=True, exist_ok=True)
            store = SQLiteStore(str(saves_dir / "game_state.db"))

            app = self._build_app(store, saves_dir)
            ok, _name, reason = ConfigApp._delete_commander_record(
                app,
                {
                    "path": str(saves_dir / "pilot" / "captain.json"),
                    "character_name": "captain",
                    "display_name": "Captain",
                },
                prompt=False,
            )

            self.assertFalse(ok)
            self.assertIn("Unsupported non-database commander path", str(reason))
            store.close()


if __name__ == "__main__":
    unittest.main()
