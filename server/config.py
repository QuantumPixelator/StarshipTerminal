import customtkinter as ctk
import json
import os
import random
import re
import shutil
from tkinter import filedialog, messagebox, ttk
from sqlite_store import SQLiteStore

try:
    import bcrypt
except Exception:
    bcrypt = None


class ConfigApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Starship Terminal - Configuration")
        self.geometry("960x720")

        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # Load data
        base_dir = os.path.dirname(os.path.abspath(__file__))
        assets_text_candidates = [
            os.path.join(base_dir, "assets", "text"),
            os.path.join(base_dir, "assets", "texts"),
        ]
        selected_assets_text_dir = None
        best_score = -1
        for candidate in assets_text_candidates:
            score = sum(
                1
                for name in ("planets.txt", "items.txt", "spaceships.txt")
                if os.path.exists(os.path.join(candidate, name))
            )
            if score > best_score and (os.path.isdir(candidate) or score > 0):
                selected_assets_text_dir = candidate
                best_score = score
        if selected_assets_text_dir is None:
            selected_assets_text_dir = assets_text_candidates[0]

        self.assets_text_dir = selected_assets_text_dir
        self.planets_path = os.path.join(self.assets_text_dir, "planets.txt")
        self.items_path = os.path.join(self.assets_text_dir, "items.txt")
        self.ships_path = os.path.join(self.assets_text_dir, "spaceships.txt")

        # Planet editor and player-save directories
        saves_candidates = [
            os.path.join(base_dir, "saves"),
            os.path.join(os.path.dirname(base_dir), "saves"),
        ]
        self.saves_dir = max(
            saves_candidates,
            key=lambda p: (
                os.path.isdir(p),
                (
                    len([n for n in os.listdir(p) if n.lower().endswith(".json")])
                    if os.path.isdir(p)
                    else -1
                ),
            ),
        )
        self.db_path = os.path.join(self.saves_dir, "game_state.db")
        self.store = None
        self.bg_dir = os.path.join(base_dir, "assets", "planets", "backgrounds")
        self.thumb_dir = os.path.join(base_dir, "assets", "planets", "thumbnails")

        # Ensure required directories/files exist (server-authoritative assets)
        os.makedirs(self.assets_text_dir, exist_ok=True)
        os.makedirs(self.saves_dir, exist_ok=True)
        os.makedirs(self.bg_dir, exist_ok=True)
        os.makedirs(self.thumb_dir, exist_ok=True)
        try:
            self.store = SQLiteStore(self.db_path)
        except Exception:
            self.store = None
        for path in (self.planets_path, self.items_path, self.ships_path):
            if not os.path.exists(path):
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write("")

        self.load_config()
        self.load_planets()
        self.load_items()
        self.load_ships()
        self.default_settings_template = self._get_default_settings_template()
        self.default_settings_order = {
            key: idx for idx, key in enumerate(self.default_settings_template)
        }
        settings = self.config.setdefault("settings", {})
        for key, value in self.default_settings_template.items():
            settings.setdefault(key, value)

        self.original_config = json.loads(json.dumps(self.config))

        # UI Layout (tabbed sections)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        self.top_bar = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.top_bar.grid(row=0, column=0, sticky="ew", padx=10, pady=(8, 4))

        self.section_status_lbl = ctk.CTkLabel(
            self.top_bar,
            text="",
            text_color=("gray45", "gray70"),
            font=ctk.CTkFont(size=11),
        )
        self.section_status_lbl.pack(side="left", padx=(8, 0), pady=4)

        self.top_save_button = ctk.CTkButton(
            self.top_bar,
            text="SAVE ALL CHANGES",
            command=self.save_all,
            fg_color="#2ecc71",
            hover_color="#27ae60",
            width=190,
        )
        self.top_save_button.pack(side="right", padx=(6, 0), pady=4)

        self._configure_notebook_style()
        self.main_tabs = ttk.Notebook(self, style="Game.TNotebook")
        self.main_tabs.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 0))
        self.main_tabs.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Settings section
        self.general_frame = ctk.CTkFrame(
            self.main_tabs, corner_radius=0, fg_color=("#f3f3f3", "#1b1b1b")
        )
        self.main_tabs.add(self.general_frame, text="Settings")
        self.setup_general_tab()

        # Planets section
        self.planets_frame = ctk.CTkFrame(
            self.main_tabs, corner_radius=0, fg_color=("#f3f3f3", "#1b1b1b")
        )
        self.main_tabs.add(self.planets_frame, text="Planets")
        self.setup_planets_tab()

        # Items section
        self.items_frame = ctk.CTkFrame(
            self.main_tabs, corner_radius=0, fg_color=("#f3f3f3", "#1b1b1b")
        )
        self.main_tabs.add(self.items_frame, text="Items")
        self.setup_items_tab()

        # Spaceships section
        self.ships_frame = ctk.CTkFrame(
            self.main_tabs, corner_radius=0, fg_color=("#f3f3f3", "#1b1b1b")
        )
        self.main_tabs.add(self.ships_frame, text="Spaceships")
        self.setup_ships_tab()

        # Players section
        self.players_frame = ctk.CTkFrame(
            self.main_tabs, corner_radius=0, fg_color=("#f3f3f3", "#1b1b1b")
        )
        self.main_tabs.add(self.players_frame, text="Players")
        self.setup_players_tab()

        self._init_dirty_tracking()
        self._bind_dirty_handlers()

        self.select_frame_by_name("settings")
        self._update_section_status()

        self.protocol("WM_DELETE_WINDOW", self.on_closing)

    def _using_fallback(self):
        return False

    def _row_entry(self, parent, label_text):
        """Create a label + entry widget combo."""
        ctk.CTkLabel(parent, text=label_text).pack(padx=12, pady=(8, 0), anchor="w")
        entry = ctk.CTkEntry(parent, width=400)
        entry.pack(padx=12, pady=(2, 4), anchor="w")
        return entry

    def _row_switch(self, parent, label_text, value=True):
        """Create a label + switch widget combo and return bool widget metadata."""
        ctk.CTkLabel(parent, text=label_text).pack(padx=12, pady=(8, 0), anchor="w")
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(padx=12, pady=(2, 4), anchor="w")
        var = ctk.BooleanVar(value=bool(value))
        ctk.CTkSwitch(row, text="", variable=var).pack(side="left")
        ctk.CTkLabel(
            row,
            text="ON / OFF",
            text_color=("gray45", "gray70"),
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(8, 0))
        return {"kind": "bool", "var": var}

    def _row_file_picker(self, parent, label_text, browse_cmd):
        """Create a label + file path entry + browse button row."""
        ctk.CTkLabel(parent, text=label_text).pack(padx=12, pady=(8, 0), anchor="w")
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=(2, 4), anchor="w")
        entry = ctk.CTkEntry(row, width=420)
        entry.pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            row,
            text="Browse...",
            width=110,
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=browse_cmd,
        ).pack(side="left")
        return entry

    def _is_path_within(self, file_path, root_dir):
        try:
            abs_file = os.path.abspath(file_path)
            abs_root = os.path.abspath(root_dir)
            return os.path.commonpath([abs_file, abs_root]) == abs_root
        except Exception:
            return False

    def _choose_planet_image(self, image_kind):
        if image_kind == "background":
            root_dir = self.bg_dir
            title = "Select Background Image"
        else:
            root_dir = self.thumb_dir
            title = "Select Thumbnail Image"

        selected = filedialog.askopenfilename(
            title=title,
            initialdir=root_dir,
            filetypes=[("PNG Images", "*.png")],
        )
        if not selected:
            return

        if not self._is_path_within(selected, root_dir):
            messagebox.showerror(
                "Invalid Path",
                "Selected file must be inside server/assets/planets backgrounds or thumbnails.",
            )
            return

        target_entry = (
            self.link_bg_path if image_kind == "background" else self.link_thumb_path
        )
        target_entry.delete(0, "end")
        target_entry.insert(0, os.path.abspath(selected))

    def _configure_notebook_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        style.configure("Game.TNotebook", background="#1f1f1f", borderwidth=0)
        style.configure("TNotebook", background="#1f1f1f", borderwidth=0)
        style.configure(
            "Game.TNotebook.Tab",
            background="#2d2d2d",
            foreground="#e6e6e6",
            padding=(16, 8),
        )
        style.configure(
            "TNotebook.Tab",
            background="#2d2d2d",
            foreground="#f2f2f2",
            padding=(16, 8),
        )
        style.map(
            "Game.TNotebook.Tab",
            background=[("selected", "#34495e")],
            foreground=[("selected", "#ffffff")],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", "#34495e"), ("active", "#3a3a3a")],
            foreground=[("selected", "#ffffff"), ("active", "#ffffff")],
        )

    def _init_dirty_tracking(self):
        self._suspend_dirty_tracking = 0
        self._tab_base_names = {
            "settings": "Settings",
            "planets": "Planets",
            "items": "Items",
            "ships": "Spaceships",
            "players": "Players",
        }
        self._section_to_tab_index = {
            "settings": 0,
            "planets": 1,
            "items": 2,
            "ships": 3,
            "players": 4,
        }
        self._dirty_sections = {name: False for name in self._tab_base_names}
        self._refresh_tab_titles()

    def _refresh_tab_titles(self):
        if not hasattr(self, "main_tabs"):
            return
        for section, idx in self._section_to_tab_index.items():
            base = self._tab_base_names.get(section, section.title())
            is_dirty = bool(self._dirty_sections.get(section, False))
            label = f"*{base}" if is_dirty else base
            try:
                self.main_tabs.tab(idx, text=label)
            except Exception:
                continue

    def _set_section_dirty(self, section, dirty=True):
        if getattr(self, "_suspend_dirty_tracking", 0) > 0:
            return
        if section not in getattr(self, "_dirty_sections", {}):
            return
        next_value = bool(dirty)
        if self._dirty_sections.get(section) == next_value:
            return
        self._dirty_sections[section] = next_value
        self._refresh_tab_titles()

    def _clear_dirty_sections(self, sections=None):
        target = list(sections) if sections else list(self._dirty_sections.keys())
        for section in target:
            if section in self._dirty_sections:
                self._dirty_sections[section] = False
        self._refresh_tab_titles()

    def _begin_dirty_suspension(self):
        self._suspend_dirty_tracking = (
            int(getattr(self, "_suspend_dirty_tracking", 0)) + 1
        )

    def _end_dirty_suspension(self):
        current = int(getattr(self, "_suspend_dirty_tracking", 0))
        self._suspend_dirty_tracking = max(0, current - 1)

    def _has_unsaved_changes(self):
        if any(bool(v) for v in getattr(self, "_dirty_sections", {}).values()):
            return True
        return json.dumps(self.config) != json.dumps(self.original_config)

    def _bind_mark_dirty_entry(self, widget, section):
        if widget is None:
            return
        try:
            widget.bind(
                "<KeyRelease>", lambda _e, s=section: self._set_section_dirty(s)
            )
            widget.bind("<<Paste>>", lambda _e, s=section: self._set_section_dirty(s))
            widget.bind("<<Cut>>", lambda _e, s=section: self._set_section_dirty(s))
        except Exception:
            return

    def _bind_mark_dirty_text(self, widget, section):
        if widget is None:
            return
        try:
            widget.bind(
                "<KeyRelease>", lambda _e, s=section: self._set_section_dirty(s)
            )
            widget.bind("<<Paste>>", lambda _e, s=section: self._set_section_dirty(s))
            widget.bind("<<Cut>>", lambda _e, s=section: self._set_section_dirty(s))
        except Exception:
            return

    def _bind_mark_dirty_bool(self, widget_meta, section):
        if not isinstance(widget_meta, dict):
            return
        if widget_meta.get("kind") != "bool":
            return
        var = widget_meta.get("var")
        if var is None:
            return
        try:
            var.trace_add("write", lambda *_args, s=section: self._set_section_dirty(s))
        except Exception:
            return

    def _bind_dirty_handlers(self):
        for widget_info in getattr(self, "settings_widgets", {}).values():
            if widget_info.get("kind") == "bool":
                self._bind_mark_dirty_bool(widget_info, "settings")
            else:
                self._bind_mark_dirty_entry(widget_info.get("entry"), "settings")

        for widget in getattr(self, "planet_editor", {}).values():
            if isinstance(widget, dict):
                self._bind_mark_dirty_bool(widget, "planets")
            else:
                self._bind_mark_dirty_entry(widget, "planets")
        self._bind_mark_dirty_entry(getattr(self, "link_new_name", None), "planets")
        self._bind_mark_dirty_entry(getattr(self, "link_bg_path", None), "planets")
        self._bind_mark_dirty_entry(getattr(self, "link_thumb_path", None), "planets")

        for widget in getattr(self, "i_entries", {}).values():
            if isinstance(widget, dict):
                self._bind_mark_dirty_bool(widget, "items")
            else:
                self._bind_mark_dirty_entry(widget, "items")

        for widget in getattr(self, "s_entries", {}).values():
            if isinstance(widget, dict):
                self._bind_mark_dirty_bool(widget, "ships")
            else:
                self._bind_mark_dirty_entry(widget, "ships")

        for widget in getattr(self, "player_entries", {}).values():
            self._bind_mark_dirty_entry(widget, "players")
        self._bind_mark_dirty_entry(
            getattr(self, "player_new_password", None), "players"
        )
        try:
            self.player_disabled_var.trace_add(
                "write", lambda *_args: self._set_section_dirty("players")
            )
            self.player_blacklisted_var.trace_add(
                "write", lambda *_args: self._set_section_dirty("players")
            )
        except Exception:
            pass

    def _create_scrollable_area(self, parent, width=None):
        scroll = (
            ctk.CTkScrollableFrame(parent, width=width)
            if width
            else ctk.CTkScrollableFrame(parent)
        )
        return scroll, scroll

    def _catalog_file_key_for_path(self, path):
        name = os.path.basename(str(path or "")).strip().lower()
        if name in ("planets.txt", "items.txt", "spaceships.txt", "smuggle_items.txt"):
            return name
        return ""

    def _read_catalog_text(self, path):
        if getattr(self, "store", None) is None:
            return ""
        key = self._catalog_file_key_for_path(path)
        if key and getattr(self, "store", None) is not None:
            try:
                content = self.store.get_catalog_text(key, default=None)
                if isinstance(content, str):
                    return content
            except Exception:
                pass
        return ""

    def _write_catalog_text(self, path, content):
        if getattr(self, "store", None) is None:
            return
        text = str(content or "")
        key = self._catalog_file_key_for_path(path)
        if key and getattr(self, "store", None) is not None:
            try:
                self.store.set_catalog_text(key, text)
            except Exception:
                pass

    def _load_settings_payload(self):
        if getattr(self, "store", None) is not None:
            try:
                self.store.seed_default_settings()
                db_settings = self.store.get_all_settings()
                if isinstance(db_settings, dict) and db_settings:
                    return {"settings": dict(db_settings)}
            except Exception:
                pass
        return {"settings": self._get_default_settings_template()}

    def _persist_settings_payload(self, payload):
        body = dict(payload or {})
        settings = body.get("settings", {}) if isinstance(body.get("settings"), dict) else {}
        if getattr(self, "store", None) is None:
            return
        for key, value in settings.items():
            try:
                self.store.set_kv("settings", str(key), value)
            except Exception:
                continue

    def load_config(self):
        self.config = self._load_settings_payload()

    def _load_settings_template_from_disk(self):
        try:
            payload = self._load_settings_payload()
            settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
            return dict(settings) if isinstance(settings, dict) else {}
        except Exception:
            return {}

    def _normalize_planets_file_if_needed(self):
        try:
            raw = self._read_catalog_text(self.planets_path)
            if not raw:
                return
            if "\\nName:" not in raw and "\\n\\nName:" not in raw:
                return
            repaired = raw.replace("\\r\\n", "\n").replace("\\n", "\n")
            backup_path = self.planets_path + ".bak_corrupt"
            with open(backup_path, "w", encoding="utf-8") as handle:
                handle.write(raw)
            self._write_catalog_text(self.planets_path, repaired)
            print(f"[CONFIG] Repaired malformed planets file. Backup: {backup_path}")
        except Exception:
            pass

    def load_planets(self):
        self.planets = []
        self._normalize_planets_file_if_needed()
        text = self._read_catalog_text(self.planets_path)
        if not text.strip():
            return
        blocks = [
            b.strip() for b in re.split(r"\r?\n\r?\n", text.strip()) if b.strip()
        ]
        for block in blocks:
            lines = [l.strip() for l in block.split("\n") if l.strip()]
            if len(lines) < 9:
                continue

            def get_v(l):
                return l.split(":", 1)[1].strip() if ":" in l else ""

            self.planets.append(
                {
                    "name": get_v(lines[0]),
                    "active": "On",
                    "pop": get_v(lines[1]),
                    "desc": get_v(lines[2]),
                    "vendor": get_v(lines[3]),
                    "trade": get_v(lines[4]),
                    "defenders": get_v(lines[5]),
                    "shields": get_v(lines[6]),
                    "bank": get_v(lines[7]),
                    "items": get_v(lines[8]),
                }
            )

            for raw in lines[9:]:
                key = raw.split(":", 1)[0].strip().lower()
                if key == "active":
                    self.planets[-1]["active"] = get_v(raw) or "On"

    def load_items(self):
        self.items = []
        text = self._read_catalog_text(self.items_path)
        for line in text.splitlines():
            if "," in line:
                parts = [p.strip() for p in line.strip().split(",")]
                if len(parts) < 2:
                    continue
                name = parts[0]
                price = parts[1]
                active = parts[2] if len(parts) >= 3 and parts[2] else "On"
                default_pct = parts[3] if len(parts) >= 4 and parts[3] else "100"
                self.items.append(
                    {
                        "name": name,
                        "price": price,
                        "active": active,
                        "default_pct": default_pct,
                    }
                )

    def load_ships(self):
        self.ships = []
        text = self._read_catalog_text(self.ships_path)
        blocks = text.strip().split("\n\n") if text.strip() else []
        for block in blocks:
            lines = [l.strip() for l in block.split("\n") if l.strip()]
            if len(lines) < 9:
                continue

            def get_v(l):
                return l.split(":", 1)[1].strip() if ":" in l else ""

            self.ships.append(
                {
                    "model": get_v(lines[0]),
                    "cost": get_v(lines[1]),
                    "s_cargo": get_v(lines[2]),
                    "s_shields": get_v(lines[3]),
                    "s_defenders": get_v(lines[4]),
                    "m_cargo": get_v(lines[5]),
                    "m_shields": get_v(lines[6]),
                    "m_defenders": get_v(lines[7]),
                    "special": get_v(lines[8]),
                    "integrity": get_v(lines[9]) if len(lines) > 9 else "100",
                }
            )

    def _flush_editor_buffers(self):
        if hasattr(self, "cur_p"):
            self.save_state("planets")
        if hasattr(self, "cur_i"):
            self.save_state("items")
        if hasattr(self, "cur_s"):
            self.save_state("ships")

    def _sync_selected_planet_editor_to_memory(self):
        """Persist selected Planet Editor values using the same logic as Save Changes."""
        if not hasattr(self, "planet_editor") or not getattr(
            self, "planet_editor", None
        ):
            return None

        try:
            selected_name = str(self.planet_editor["name"].get().strip())
        except Exception:
            return None

        if not selected_name:
            return None

        # Only persist for active planets already present in data file.
        if selected_name not in getattr(self, "active_planets_data", {}):
            return None

        payload = self._build_planet_payload()
        ok, err, _synced = self._persist_planet_payload(payload, require_active=True)
        if not ok:
            return f"planet editor: {err}"
        return None

    def _persist_planet_payload(self, payload, require_active=True):
        """Persist a planet payload to planets.txt; returns (ok, message, synced_save_count)."""
        ok, err = self._validate_planet_payload(payload)
        if not ok:
            return False, err, 0

        raw_text = self._read_catalog_text(self.planets_path)
        raw_blocks = [b.strip() for b in raw_text.split("\n\n") if b.strip()]

        blocks = []
        updated = False
        for block in raw_blocks:
            vals = {}
            for ln in [ln.strip() for ln in block.split("\n") if ln.strip()]:
                if ":" not in ln:
                    continue
                k, v = ln.split(":", 1)
                vals[k.strip()] = v.strip()

            if vals.get("Name") == payload["Name"]:
                vals.update(payload)
                updated = True

            if vals.get("Name"):
                blocks.append(vals)

        if require_active and not updated:
            return (
                False,
                "This planet is not active yet. Use 'Activate / Add Planet' first.",
                0,
            )

        if not updated and not require_active:
            blocks.append(dict(payload))

        ordered_keys = [
            "Name",
            "Population",
            "Description",
            "Vendor",
            "Trade Center",
            "Defenders",
            "Shields",
            "Bank",
            "Items",
        ]

        rendered = []
        for vals in blocks:
            lines = []
            for key in ordered_keys:
                if key == "Name" and not vals.get("Name"):
                    continue
                lines.append(f"{key}: {vals.get(key, '')}")
            rendered.append("\n".join(lines).strip())

        self._write_catalog_text(
            self.planets_path, "\n\n".join([r for r in rendered if r]) + "\n"
        )

        synced = self._sync_planet_state_to_saves(payload["Name"], payload)
        self.load_planets()
        self.refresh_planet_catalog()
        return True, "", synced

    def _save_editor_files(self):
        os.makedirs(self.assets_text_dir, exist_ok=True)
        self._write_catalog_text(self.planets_path, self.get_planets_raw().strip() + "\n")
        self._write_catalog_text(self.items_path, self.get_items_raw().strip() + "\n")
        self._write_catalog_text(self.ships_path, self.get_ships_raw().strip() + "\n")

    def get_planets_raw(self):
        return "\n\n".join(
            [
                f"Name: {p['name']}\nPopulation: {p['pop']}\nDescription: {p['desc']}\nVendor: {p['vendor']}\nTrade Center: {p['trade']}\nDefenders: {p['defenders']}\nShields: {p['shields']}\nBank: {p['bank']}\nItems: {p['items']}\nActive: {p.get('active', 'On')}"
                for p in self.planets
            ]
        )

    def get_items_raw(self):
        return "\n".join(
            [
                f"{i['name']},{i['price']},{i.get('active', 'On')},{i.get('default_pct', '100')}"
                for i in self.items
            ]
        )

    def get_ships_raw(self):
        return "\n\n".join(
            [
                f"Model: {s['model']}\nCost: {s['cost']}\nStarting Cargo Pods: {s['s_cargo']}\nStarting Shields: {s['s_shields']}\nStarting Defenders: {s['s_defenders']}\nMax Cargo Pods: {s['m_cargo']}\nMax Shields: {s['m_shields']}\nMax Defenders: {s['m_defenders']}\nSpecial Weapon: {s['special']}\nShip Integrity: {s['integrity']}"
                for s in self.ships
            ]
        )

    # SETUP TABS
    def setup_general_tab(self):
        header = ctk.CTkLabel(
            self.general_frame,
            text="Server Configuration Console",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        header.pack(padx=20, pady=(20, 6), anchor="w")

        subtitle = ctk.CTkLabel(
            self.general_frame,
            text="Server-authoritative settings only, organized by control tabs. Client sound/accessibility is managed on the client.",
            font=ctk.CTkFont(size=13),
        )
        subtitle.pack(padx=22, pady=(0, 12), anchor="w")

        controls = ctk.CTkFrame(self.general_frame)
        controls.pack(fill="x", padx=16, pady=(0, 8))
        ctk.CTkButton(
            controls,
            text="Reset All Settings To Defaults",
            fg_color="#e67e22",
            hover_color="#d35400",
            command=self.reset_all_settings_to_defaults,
        ).pack(side="left", padx=10, pady=8)
        ctk.CTkButton(
            controls,
            text="RESET CURRENT GAME",
            fg_color="#c0392b",
            hover_color="#922b21",
            command=self.reset_current_game,
        ).pack(side="left", padx=10, pady=8)
        ctk.CTkButton(
            controls,
            text="Reconcile Planet Ownership",
            fg_color="#16a085",
            hover_color="#117a65",
            command=self.reconcile_planet_ownership,
        ).pack(side="left", padx=10, pady=8)
        ctk.CTkLabel(
            controls,
            text="Use row reset for one setting, global reset for all server settings, or reconcile ownership against active commanders.",
            text_color=("gray45", "gray70"),
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=10)

        self.settings_widgets = {}
        settings = self.config.setdefault("settings", {})

        grouped = {}
        for key, value in sorted(
            settings.items(),
            key=lambda kv: (
                self._setting_group_rank(kv[0]),
                self._setting_display_rank(kv[0]),
                kv[0],
            ),
        ):
            if self._is_client_only_setting(key):
                continue
            group = self._setting_group_name(key)
            grouped.setdefault(group, []).append((key, value))

        tabs_host = ctk.CTkFrame(self.general_frame)
        tabs_host.pack(fill="both", expand=True, padx=16, pady=0)
        setting_tabs = ttk.Notebook(tabs_host, style="Game.TNotebook")
        setting_tabs.pack(fill="both", expand=True)

        ordered_groups = [
            "Core Server",
            "Gameplay Rules",
            "Economy & Markets",
            "Travel, Contracts & Events",
            "Combat & Security",
            "Victory & Resets",
            "Other Settings",
        ]

        for group_name in ordered_groups:
            items = grouped.get(group_name, [])
            if not items:
                continue
            tab_frame = ctk.CTkFrame(setting_tabs, corner_radius=0)
            setting_tabs.add(tab_frame, text=group_name)
            tab_host, tab_scroll = self._create_scrollable_area(tab_frame)
            tab_host.pack(fill="both", expand=True, padx=10, pady=10)

            for key, value in items:
                row = ctk.CTkFrame(tab_scroll, fg_color="transparent")
                row.pack(fill="x", padx=14, pady=4)

                label_text = key.replace("_", " ").title()
                if key == "enable_bank":
                    label_text = "Global Bank / Repairs"
                label_block = ctk.CTkFrame(row, fg_color="transparent")
                label_block.pack(side="left", fill="x", expand=True, padx=(0, 6))

                ctk.CTkLabel(label_block, text=label_text, width=250, anchor="w").pack(
                    anchor="w"
                )

                help_text = self._setting_help_text(key)
                if help_text:
                    ctk.CTkLabel(
                        label_block,
                        text=help_text,
                        anchor="w",
                        justify="left",
                        wraplength=420,
                        text_color=("gray45", "gray70"),
                        font=ctk.CTkFont(size=11),
                    ).pack(anchor="w", pady=(0, 2))

                if isinstance(value, bool):
                    var = ctk.BooleanVar(value=bool(value))
                    ctk.CTkSwitch(row, text="", variable=var).pack(side="left")
                    ctk.CTkLabel(
                        row,
                        text="ON / OFF",
                        text_color=("gray45", "gray70"),
                        font=ctk.CTkFont(size=11),
                    ).pack(side="left", padx=(8, 0))
                    self.settings_widgets[key] = {
                        "kind": "bool",
                        "var": var,
                        "original_type": bool,
                    }
                else:
                    entry = ctk.CTkEntry(row, width=190)
                    entry.insert(0, str(value))
                    if key == "server_port":
                        entry.bind(
                            "<KeyRelease>",
                            lambda _e, en=entry: self._sanitize_server_port_entry(en),
                        )
                        entry.bind(
                            "<FocusOut>",
                            lambda _e, en=entry: self._sanitize_server_port_entry(en),
                        )
                        self._sanitize_server_port_entry(entry)
                    entry.pack(side="left")
                    ctk.CTkLabel(
                        row,
                        text=self._setting_value_hint(key, value),
                        text_color=("gray45", "gray70"),
                        font=ctk.CTkFont(size=11),
                    ).pack(side="left", padx=(8, 0))
                    self.settings_widgets[key] = {
                        "kind": "entry",
                        "entry": entry,
                        "original_type": type(value),
                    }

                ctk.CTkButton(
                    row,
                    text="Reset",
                    width=68,
                    fg_color="#8e44ad",
                    hover_color="#6c3483",
                    command=lambda k=key: self.reset_setting_to_default(k),
                ).pack(side="left", padx=(10, 0))

    def _is_client_only_setting(self, key):
        k = str(key or "").strip().lower()
        return k.startswith("audio_") or k.startswith("accessibility_") or k == "reduced_effects_mode"

    def reconcile_planet_ownership(self):
        if getattr(self, "store", None) is None:
            messagebox.showerror("Unavailable", "SQLite store is not available.")
            return

        universe_path = os.path.join(self.saves_dir, "universe_planets.json")
        payload = self._read_json_file(universe_path)
        if not isinstance(payload, dict):
            messagebox.showerror(
                "Unavailable",
                "Shared universe ownership state could not be loaded.",
            )
            return

        states = payload.get("planet_states", {})
        if not isinstance(states, dict):
            messagebox.showerror(
                "Invalid State",
                "Universe state is malformed (planet_states missing).",
            )
            return

        active_names = set()
        for row in self.store.iter_all_characters():
            account_name = str(row.get("account_name") or "").strip()
            if not account_name or self.store.is_account_blocked(account_name):
                continue
            data = row.get("payload") if isinstance(row, dict) else None
            if not isinstance(data, dict):
                continue
            player_data = data.get("player") if isinstance(data.get("player"), dict) else {}
            commander_name = str(player_data.get("name") or row.get("character_name") or "").strip()
            if commander_name:
                active_names.add(commander_name.lower())

        cleared = 0
        for state in states.values():
            if not isinstance(state, dict):
                continue
            owner = str(state.get("owner") or "").strip()
            if not owner:
                continue
            if owner.lower() in active_names:
                continue
            state["owner"] = None
            cleared += 1

        if cleared > 0:
            payload["planet_states"] = states
            self._write_json_file(universe_path, payload)
            messagebox.showinfo(
                "Ownership Reconciled",
                f"Cleared {cleared} stale planet owner assignment(s).",
            )
        else:
            messagebox.showinfo(
                "Ownership Reconciled",
                "No stale owner assignments were found.",
            )

    def _sanitize_server_port_entry(self, entry_widget):
        raw = entry_widget.get()
        filtered = "".join(ch for ch in raw if ch.isdigit())[:5]
        if filtered != raw:
            entry_widget.delete(0, "end")
            entry_widget.insert(0, filtered)

    def _get_default_settings_template(self):
        disk_settings = self._load_settings_template_from_disk()
        if disk_settings:
            disk_settings.setdefault("enable_bank", True)
            return disk_settings

        return {"enable_bank": True}

    def _set_setting_widget_value(self, key, value):
        widget = self.settings_widgets.get(key)
        if not widget:
            return False

        if widget["kind"] == "bool":
            widget["var"].set(bool(value))
            return True

        entry = widget["entry"]
        entry.delete(0, "end")
        entry.insert(0, str(value))
        return True

    def reset_setting_to_default(self, key):
        default_value = self.default_settings_template.get(key)
        if default_value is None:
            messagebox.showinfo(
                "No Default",
                f"No built-in default is defined for '{key}'.",
            )
            return

        self._set_setting_widget_value(key, default_value)
        self._set_section_dirty("settings")

    def reset_all_settings_to_defaults(self):
        if not messagebox.askyesno(
            "Reset Settings",
            "Reset all known settings to defaults? This only affects the editor until you click Save.",
        ):
            return

        reset_count = 0
        for key, value in self.default_settings_template.items():
            if self._set_setting_widget_value(key, value):
                reset_count += 1

        messagebox.showinfo(
            "Defaults Applied",
            f"Reset {reset_count} setting(s) to default values.",
        )
        if reset_count > 0:
            self._set_section_dirty("settings")

    def reset_current_game(self):
        first_confirm = messagebox.askyesno(
            "Reset Current Game",
            "This will remove ALL commander saves from ALL accounts and reset the universe to defaults.\n\nProceed?",
            icon="warning",
        )
        if not first_confirm:
            return

        second_confirm = messagebox.askyesno(
            "Confirm Reset Again",
            "Final confirmation: keep account login records, delete all commanders, and reset all planets to default no-owner state?",
            icon="warning",
        )
        if not second_confirm:
            return

        server_dir = os.path.dirname(os.path.abspath(__file__))
        previous_cwd = os.getcwd()
        try:
            os.chdir(server_dir)
            from game_manager_modules import GameManager

            gm = GameManager()
            result = gm.reset_current_campaign(reason="admin")
            removed = int(result.get("removed_commanders", 0))
            messagebox.showinfo(
                "Current Game Reset",
                (
                    "Reset completed successfully.\n\n"
                    f"Commander saves removed: {removed}\n"
                    "Accounts preserved: Yes\n"
                    "Planets reset to default no-owner state."
                ),
            )
        except Exception as exc:
            messagebox.showerror(
                "Reset Failed", f"Unable to reset current game:\n{exc}"
            )
        finally:
            try:
                os.chdir(previous_cwd)
            except Exception:
                pass

    def _setting_group_name(self, key):
        k = str(key).lower()
        if k in {"server_port", "galactic_news_window_days"}:
            return "Core Server"
        if k.startswith("enable_") or k.startswith("allow_"):
            return "Gameplay Rules"
        if k == "enable_bank":
            return "Economy & Markets"
        if k.startswith("victory_") or "winner" in k or "reset" in k:
            return "Victory & Resets"
        if "contract" in k or "trade" in k or "spotlight" in k:
            return "Travel, Contracts & Events"
        if "travel" in k or "docking" in k or "stipend" in k:
            return "Travel, Contracts & Events"
        if "refuel" in k:
            return "Travel, Contracts & Events"
        if "combat" in k:
            return "Combat & Security"
        if "reputation" in k or "bribe" in k or "contraband" in k:
            return "Combat & Security"
        if "planet" in k or "defense" in k or "abandon" in k:
            return "Gameplay Rules"
        if "credit" in k or "bank" in k or "interest" in k or "salvage" in k:
            return "Economy & Markets"
        return "Other Settings"

    def _setting_group_rank(self, key):
        order = {
            "Core Server": 0,
            "Gameplay Rules": 1,
            "Economy & Markets": 2,
            "Travel, Contracts & Events": 3,
            "Combat & Security": 4,
            "Victory & Resets": 5,
            "Other Settings": 6,
        }
        return order.get(self._setting_group_name(key), 99)

    def _setting_display_rank(self, key):
        if key == "enable_bank":
            return -100
        return self.default_settings_order.get(key, 10_000)

    def _setting_help_text(self, key):
        help_map = {
            "enable_bank": "Global master switch for all planet banking and repair access. OFF overrides every planet's Bank / Repairs toggle.",
            "enable_combat": "Master toggle for orbital and planetary combat systems.",
            "enable_mail": "Enables player-to-player and system mailbox messages.",
            "allow_multiple_games": "Allow multiple commander save profiles per account. Turn OFF to enforce one save profile per account.",
            "enable_abandonment": "Allows inactive ships to become claimable after inactivity.",
            "abandonment_days": "Number of real-world days before ship abandonment triggers.",
            "starting_credits": "Starting wallet credits for newly created commanders.",
            "bank_interest_rate": "Daily bank growth multiplier (0.05 = +5% per cycle).",
            "owned_planet_interest_rate": "Daily colony payout rate as a fraction of planet population (0.000001 = 0.0001%).",
            "planet_price_penalty_multiplier": "Hostile-market sell/buy price multiplier applied while planetary penalties are active.",
            "planet_arrival_pause_seconds": "Duration (seconds) of the information overlay when arriving at a new planet.",
            "planet_loss_travel_ban_hours": "Hours a commander is banned from returning to an unowned planet after losing a planet assault.",
            "commander_presence_banner_seconds": "How long (seconds) login/logout commander neon banners remain visible on clients.",
            "base_docking_fee": "Base docking price before ship level and modifiers.",
            "docking_fee_ship_level_multiplier": "Scales docking costs by ship class tier.",
            "salvage_sell_multiplier": "Sell-price multiplier for non-market salvage cargo.",
            "trade_contract_hours": "Contract expiration window in hours.",
            "trade_contract_reward_multiplier": "Global multiplier for contract rewards.",
            "contract_reroll_cost": "Credits consumed when manually rerolling a contract.",
            "combat_enemy_scale_per_ship_level": "Enemy scaling added per ship tier level.",
            "combat_win_streak_bonus_per_win": "Per-win payout boost while streaking.",
            "combat_win_streak_bonus_cap": "Maximum payout bonus from streak scaling.",
            "planet_auto_combat_threshold_pct": "Conquest pressure threshold for auto-counterattacks.",
            "enable_travel_events": "Toggles random travel encounters during interplanet jumps.",
            "travel_event_chance": "Chance (0-1) for each travel event roll.",
            "refuel_timer_enabled": "When enabled, limits manual refuel purchases to a fixed number per real-time window.",
            "refuel_timer_max_refuels": "How many manual refuel purchases are allowed per timer window.",
            "refuel_timer_window_hours": "Length of the real-time refuel window in hours.",
            "refuel_timer_cost_multiplier_pct": "Refuel cost multiplier percent while timer mode is enabled (0-500).",
            "commander_stipend_hours": "Hours between passive stipend payouts.",
            "commander_stipend_amount": "Credits paid per stipend interval.",
            "port_spotlight_discount_min": "Minimum discount percent for spotlight deals.",
            "port_spotlight_discount_max": "Maximum discount percent for spotlight deals.",
            "contract_chain_bonus_per_completion": "Bonus added per consecutive contract completion.",
            "contract_chain_bonus_cap": "Maximum chain bonus allowed.",
            "galactic_news_window_days": "Number of days of unseen galactic news shown at login.",
            "victory_planet_ownership_pct": "Campaign win threshold: percentage of total planets a commander must control.",
            "victory_authority_min": "Minimum Authority standing required to win the campaign.",
            "victory_authority_max": "Maximum Authority standing permitted for campaign victory checks.",
            "victory_frontier_min": "Minimum Frontier standing required to win the campaign.",
            "victory_frontier_max": "Maximum Frontier standing permitted for campaign victory checks.",
            "victory_reset_days": "Days after a winner is declared before automatic reset at 12:01 AM local time.",
            "reputation_bribe_penalty": "Reputation loss applied when bribing contacts.",
            "reputation_contraband_trade_penalty": "Per-unit reputation loss for contraband sales.",
            "reputation_contract_completion_bonus": "Reputation gain on completed contracts.",
            "reputation_hostile_npc_bonus": "Reputation gain for defeating hostile NPCs.",
            "reputation_docking_fee_step": "Docking fee adjustment step per reputation tier.",
            "contraband_price_tier_step": "Price premium step by contraband tier.",
            "contraband_price_heat_step": "Additional contraband price pressure per heat point.",
            "contraband_detection_tier_step": "Detection risk increase per contraband tier.",
            "contraband_detection_quantity_step": "Detection risk scaling by traded quantity.",
            "smuggle_nonhub_sell_penalty": "Sell multiplier applied when offloading contraband outside protected channels.",
            "bribe_base_duration_hours": "Base duration in hours for contact influence after a bribe.",
            "bribe_duration_per_level_hours": "Extra influence duration added per bribe level.",
            "bribe_cost_growth": "Cost multiplier for each next bribe level.",
            "bribe_price_heat_step": "Bribe cost increase per heat point.",
            "bribe_max_level": "Maximum bribe influence level per planet contact.",
            "bribe_detection_reduction_per_level": "Detection risk reduction applied per bribe level.",
            "bribe_heat_reduction_per_level": "Heat reduction applied when a bribe succeeds.",
            "bribe_smuggling_discount_per_level": "Buy-price discount for contraband per bribe level.",
            "bribe_smuggling_sell_bonus_per_level": "Sell-price bonus for contraband per bribe level.",
            "bribe_authority_hit_per_level": "Authority standing penalty per bribe level purchased.",
            "bribe_frontier_gain_per_level": "Frontier standing gain per bribe level purchased.",
        }
        return help_map.get(key, "")

    def _setting_value_hint(self, key, value):
        if isinstance(value, int):
            return "integer"
        if isinstance(value, float):
            if (
                "chance" in key
                or "rate" in key
                or "multiplier" in key
                or "bonus" in key
            ):
                return "decimal (e.g., 0.05)"
            return "decimal"
        return "text"

    def _coerce_setting_value(self, raw_value, original_type):
        if original_type is bool:
            if isinstance(raw_value, bool):
                return raw_value
            v = str(raw_value).strip().lower()
            if v in ("1", "true", "yes", "on"):
                return True
            if v in ("0", "false", "no", "off"):
                return False
            raise ValueError("must be On or Off")

        if original_type is int:
            return int(float(str(raw_value).strip()))

        if original_type is float:
            return float(str(raw_value).strip())

        return str(raw_value)

    def setup_planets_tab(self):
        """Enhanced planets tab with catalog, image management, and map preview."""
        for child in self.planets_frame.winfo_children():
            child.destroy()

        self.current_section = "planets"

        # Two-column layout: catalog on left, editor on right
        self.planets_frame.grid_columnconfigure(0, weight=0)
        self.planets_frame.grid_columnconfigure(1, weight=1)
        self.planets_frame.grid_rowconfigure(0, weight=1)

        # LEFT: Planet Catalog
        left_frame = ctk.CTkFrame(self.planets_frame, width=360)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        left_frame.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            left_frame,
            text="PLANET CATALOG",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 6))

        self.planet_summary_lbl = ctk.CTkLabel(
            left_frame, text="", font=ctk.CTkFont(size=12)
        )
        self.planet_summary_lbl.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 8))

        catalog_scroll_host, self.catalog_scroll = self._create_scrollable_area(
            left_frame, width=330
        )
        catalog_scroll_host.grid(row=2, column=0, sticky="nsew", padx=10, pady=(0, 10))

        ctk.CTkButton(
            left_frame,
            text="Refresh Catalog",
            command=self.refresh_planet_catalog,
            fg_color="#3498db",
        ).grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))

        ctk.CTkButton(
            left_frame,
            text="Activate All READY",
            command=self.activate_all_ready_planets,
            fg_color="#2ecc71",
            hover_color="#27ae60",
        ).grid(row=4, column=0, sticky="ew", padx=12, pady=(0, 12))

        # RIGHT: Planet Editor
        right_host, right_frame = self._create_scrollable_area(self.planets_frame)
        right_host.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)

        ctk.CTkLabel(
            right_frame,
            text="Planet Activation & Management",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 4))

        ctk.CTkLabel(
            right_frame,
            text="Only planets with BOTH background and thumbnail images can be activated.",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=12, pady=(0, 12))

        self.selected_planet_info = ctk.CTkLabel(
            right_frame, text="Select a planet from the catalog."
        )
        self.selected_planet_info.pack(anchor="w", padx=12, pady=(0, 10))

        # Planet editor form
        form = ctk.CTkFrame(right_frame)
        form.pack(fill="x", padx=10, pady=8)

        self.planet_editor = {}
        self.planet_editor["name"] = self._row_entry(form, "Planet Name")
        self.planet_editor["pop"] = self._row_entry(form, "Population")
        self.planet_editor["desc"] = self._row_entry(form, "Description")
        self.planet_editor["vendor"] = self._row_entry(form, "Vendor")
        self.planet_editor["trade"] = self._row_entry(form, "Trade Center")
        self.planet_editor["defenders"] = self._row_entry(form, "Defenders")
        self.planet_editor["shields"] = self._row_entry(form, "Shields")
        self.planet_editor["bank"] = self._row_switch(
            form, "Bank / Repairs", value=False
        )
        self.planet_editor["items"] = self._row_entry(form, "Items (Name,Price;...)")

        # Action buttons
        btn_frame = ctk.CTkFrame(right_frame, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(6, 14))

        ctk.CTkButton(
            btn_frame,
            text="Activate / Add Planet",
            fg_color="#2ecc71",
            hover_color="#27ae60",
            command=self.activate_planet,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_frame,
            text="Save Changes",
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=self.save_planet_changes,
        ).pack(side="left", padx=(0, 6))

        ctk.CTkButton(
            btn_frame,
            text="Deactivate",
            fg_color="#e67e22",
            hover_color="#d35400",
            command=self.deactivate_planet,
        ).pack(side="left")

        # Image linking section
        link_frame = ctk.CTkFrame(right_frame)
        link_frame.pack(fill="x", padx=10, pady=(8, 14))

        ctk.CTkLabel(
            link_frame,
            text="Create New Planet by Linking Existing Images",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            link_frame,
            text="Pick source PNG files from server/assets/planets/backgrounds and /thumbnails.",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=12, pady=(0, 8))

        self.link_new_name = self._row_entry(link_frame, "New Planet Name")
        self.link_bg_path = self._row_file_picker(
            link_frame,
            "Source Background Image (.png)",
            lambda: self._choose_planet_image("background"),
        )
        self.link_thumb_path = self._row_file_picker(
            link_frame,
            "Source Thumbnail Image (.png)",
            lambda: self._choose_planet_image("thumbnail"),
        )

        ctk.CTkButton(
            link_frame,
            text="Link Images + Add Planet",
            fg_color="#9b59b6",
            hover_color="#8e44ad",
            command=self.link_and_add_planet,
        ).pack(anchor="w", padx=12, pady=(6, 12))

        # Map preview section
        map_frame = ctk.CTkFrame(right_frame)
        map_frame.pack(fill="x", padx=10, pady=(8, 14))

        ctk.CTkLabel(
            map_frame,
            text="Travel Map Preview",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            map_frame,
            text="Preview travel coordinates (deterministic by planet name).",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=12, pady=(0, 8))

        ctk.CTkButton(
            map_frame,
            text="Rebuild Map Preview",
            fg_color="#16a085",
            hover_color="#138d75",
            command=self.rebuild_map_preview,
        ).pack(anchor="w", padx=12, pady=(0, 8))

        self.map_preview_box = ctk.CTkTextbox(map_frame, width=680, height=180)
        self.map_preview_box.pack(fill="x", padx=12, pady=(0, 12))
        self.map_preview_box.insert(
            "1.0", "Press 'Rebuild Map Preview' to show active coordinates.\n"
        )

        # Initialize catalog
        self.selected_planet_name = None
        self.refresh_planet_catalog()

    def setup_items_tab(self):
        self.current_section = "items"
        self.setup_crud_tab(
            self.items_frame,
            "Global Commodities",
            self.item_scroll_event,
            self.add_item_event,
            self.delete_item_event,
            [
                ("name", "Item Name:"),
                ("price", "Base Price:"),
                ("active", "Active:"),
                ("default_pct", "Default Planet %:"),
            ],
        )

        ctk.CTkButton(
            self.items_frame,
            text="Disperse Selected Item To Viable Planets",
            fg_color="#8e44ad",
            hover_color="#6c3483",
            command=self.disperse_selected_item_event,
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=20, pady=(0, 12))

    def setup_ships_tab(self):
        self.setup_crud_tab(
            self.ships_frame,
            "Shipyard Templates",
            self.ship_scroll_event,
            self.add_ship_event,
            self.delete_ship_event,
            [
                ("model", "Model Name:"),
                ("cost", "Purchase Cost:"),
                ("s_cargo", "Starting Cargo:"),
                ("s_shields", "Starting Shields:"),
                ("s_defenders", "Starting Combatants:"),
                ("m_cargo", "Max Cargo Capacity:"),
                ("m_shields", "Max Shield Capacity:"),
                ("m_defenders", "Max Combatant Capacity:"),
                ("special", "Special Systems:"),
                ("integrity", "Structural Integrity:"),
            ],
        )

    def setup_players_tab(self):
        for child in self.players_frame.winfo_children():
            child.destroy()

        self.players_frame.grid_columnconfigure(0, weight=1, minsize=320)
        self.players_frame.grid_columnconfigure(1, weight=2)
        self.players_frame.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self.players_frame, width=320)
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        ctk.CTkLabel(
            left, text="PLAYER ACCOUNTS", font=ctk.CTkFont(size=16, weight="bold")
        ).pack(pady=10)

        self.players_summary_lbl = ctk.CTkLabel(
            left,
            text="",
            text_color=("gray45", "gray70"),
            font=ctk.CTkFont(size=11),
        )
        self.players_summary_lbl.pack(anchor="w", padx=10, pady=(0, 6))

        p_host, self.players_scroll = self._create_scrollable_area(left, width=300)
        p_host.pack(fill="both", expand=True, padx=5, pady=5)

        ctk.CTkButton(
            left,
            text="Refresh Accounts",
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=self.refresh_players_list,
        ).pack(padx=10, pady=10)

        right_host, right = self._create_scrollable_area(self.players_frame)
        right_host.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)

        ctk.CTkLabel(
            right,
            text="Commander Details",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).pack(anchor="w", padx=20, pady=(12, 6))

        self.players_selected_info = ctk.CTkLabel(
            right,
            text="Select an account from the left list.",
            text_color=("gray45", "gray70"),
        )
        self.players_selected_info.pack(anchor="w", padx=20, pady=(0, 8))

        self.commander_selected_info = ctk.CTkLabel(
            right,
            text="Select a commander to edit save data.",
            text_color=("gray45", "gray70"),
        )
        self.commander_selected_info.pack(anchor="w", padx=20, pady=(0, 8))

        self.player_entries = {}
        for key, label in [
            ("name", "Commander Name:"),
            ("credits", "Credits:"),
            ("bank_credits", "Bank Credits:"),
            ("location", "Current Location (Planet Name):"),
            ("ship_model", "Ship Model:"),
            ("owned_planets", "Owned Planets (comma-separated):"),
        ]:
            ctk.CTkLabel(right, text=label).pack(padx=20, pady=(8, 0), anchor="w")
            entry = ctk.CTkEntry(right, width=480)
            entry.pack(padx=20, pady=(2, 4), anchor="w")
            self.player_entries[key] = entry

        self.player_entries["name"].configure(state="disabled")

        ctk.CTkLabel(right, text="Account Disabled:").pack(
            padx=20, pady=(8, 0), anchor="w"
        )
        row_disabled = ctk.CTkFrame(right, fg_color="transparent")
        row_disabled.pack(padx=20, pady=(2, 4), anchor="w")
        self.player_disabled_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(row_disabled, text="", variable=self.player_disabled_var).pack(
            side="left"
        )
        ctk.CTkLabel(
            row_disabled,
            text="ON / OFF",
            text_color=("gray45", "gray70"),
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(right, text="Blacklisted:").pack(padx=20, pady=(8, 0), anchor="w")
        row_blacklisted = ctk.CTkFrame(right, fg_color="transparent")
        row_blacklisted.pack(padx=20, pady=(2, 4), anchor="w")
        self.player_blacklisted_var = ctk.BooleanVar(value=False)
        ctk.CTkSwitch(
            row_blacklisted, text="", variable=self.player_blacklisted_var
        ).pack(side="left")
        ctk.CTkLabel(
            row_blacklisted,
            text="ON / OFF",
            text_color=("gray45", "gray70"),
            font=ctk.CTkFont(size=11),
        ).pack(side="left", padx=(8, 0))

        ctk.CTkLabel(right, text="Reset Password (new password):").pack(
            padx=20, pady=(8, 0), anchor="w"
        )
        self.player_new_password = ctk.CTkEntry(right, width=480, show="*")
        self.player_new_password.pack(padx=20, pady=(2, 8), anchor="w")

        self.commander_btn_row = ctk.CTkFrame(right, fg_color="transparent")
        self.commander_btn_row.pack(fill="x", padx=20, pady=(10, 6))

        self.player_save_button = ctk.CTkButton(
            self.commander_btn_row,
            text="Save",
            fg_color="#2ecc71",
            hover_color="#27ae60",
            width=150,
            command=self.save_player_changes,
        )
        self.player_save_button.pack(side="left", padx=(0, 8))

        self.player_delete_button = ctk.CTkButton(
            self.commander_btn_row,
            text="Delete",
            fg_color="#e67e22",
            hover_color="#d35400",
            width=150,
            command=self.delete_selected_commander,
        )
        self.player_delete_button.pack(side="left")

        self.account_btn_row = ctk.CTkFrame(right, fg_color="transparent")
        self.account_btn_row.pack(fill="x", padx=20, pady=(2, 12))

        self.account_reset_button = ctk.CTkButton(
            self.account_btn_row,
            text="Reset Password",
            fg_color="#8e44ad",
            hover_color="#6c3483",
            width=150,
            command=self.reset_player_password,
        )
        self.account_reset_button.pack(side="left", padx=(0, 8))

        self.account_delete_button = ctk.CTkButton(
            self.account_btn_row,
            text="Delete Account",
            fg_color="#e74c3c",
            hover_color="#c0392b",
            width=150,
            command=self.delete_selected_player,
        )
        self.account_delete_button.pack(side="left")

        self.selected_account_name = None
        self.selected_account_auth_path = None
        self.selected_commander_record = None
        self.selected_player_path = None
        self.commander_button_by_path = {}
        self.players_records = []
        self.refresh_players_list()
        self._set_player_action_mode("account")

    def _set_player_action_mode(self, mode):
        is_commander = str(mode or "").strip().lower() == "commander"
        try:
            self.player_save_button.configure(
                state=("normal" if is_commander else "disabled")
            )
            self.player_delete_button.configure(
                state=("normal" if is_commander else "disabled")
            )
        except Exception:
            pass

        try:
            self.account_reset_button.configure(
                state=("disabled" if is_commander else "normal")
            )
            self.account_delete_button.configure(
                state=("disabled" if is_commander else "normal")
            )
        except Exception:
            pass

    def _parse_owned_planets_text(self, text):
        parts = [p.strip() for p in str(text or "").split(",")]
        return {p for p in parts if p}

    def _build_planet_id_maps(self):
        id_by_name = {}
        name_by_id = {}
        try:
            blocks = [
                b.strip()
                for b in self._read_catalog_text(self.planets_path).split("\n\n")
                if b.strip()
            ]
            next_id = 1
            for block in blocks:
                p_name = ""
                p_id = None
                for raw in block.split("\n"):
                    line = str(raw or "").strip()
                    if not line or ":" not in line:
                        continue
                    key, value = line.split(":", 1)
                    key = key.strip().lower()
                    value = value.strip()
                    if key == "name":
                        p_name = value
                    elif key == "planet id" and value.isdigit():
                        p_id = int(value)
                if not p_name:
                    continue
                if p_id is None:
                    p_id = next_id
                p_id = int(p_id)
                next_id = max(next_id + 1, p_id + 1)
                id_by_name[p_name.strip().lower()] = p_id
                name_by_id[p_id] = p_name.strip()
        except Exception:
            return {}, {}
        return id_by_name, name_by_id

    def _resolve_planet_id(self, value, id_by_name):
        try:
            direct = int(value)
            if direct > 0:
                return direct
        except Exception:
            pass
        key = str(value or "").strip().lower()
        if not key:
            return None
        return id_by_name.get(key)

    def _read_json_file(self, path):
        if getattr(self, "store", None) is None:
            return None
        try:
            if getattr(self, "store", None) is not None:
                target = str(path or "").strip()
                if target.startswith("db://"):
                    _, _, remainder = target.partition("db://")
                    account_name, _, character_name = remainder.partition("/")
                    payload = self.store.get_character_payload(account_name, character_name)
                    if isinstance(payload, dict):
                        return payload
                    return None
                if target.startswith("dbauth://"):
                    account_name = str(target.partition("dbauth://")[2] or "").strip()
                    payload = self.store.get_account_payload(account_name)
                    if isinstance(payload, dict):
                        return payload
                    return None

                rel_path = os.path.relpath(os.path.abspath(target), os.path.abspath(self.saves_dir))
                rel_parts = rel_path.split(os.sep)
                low_file = str(rel_parts[-1] if rel_parts else "").lower()
                shared_map = {
                    "universe_planets.json": "universe_planets",
                    "galactic_news.json": "galactic_news",
                    "winner_board.json": "winner_board",
                    "analytics_metrics.json": "analytics_metrics",
                }
                if len(rel_parts) == 1 and low_file in shared_map:
                    payload = self.store.get_kv("shared", shared_map[low_file], default=None)
                    if isinstance(payload, dict):
                        return payload
                    return None
                if len(rel_parts) == 2 and low_file == "account.json":
                    payload = self.store.get_account_payload(rel_parts[0])
                    if isinstance(payload, dict):
                        return payload
                    return None
                if len(rel_parts) == 2 and low_file.endswith(".json"):
                    account_name = rel_parts[0]
                    character_name = os.path.splitext(rel_parts[1])[0]
                    payload = self.store.get_character_payload(account_name, character_name)
                    if isinstance(payload, dict):
                        return payload
                    return None
        except Exception:
            pass

        return None

    def _write_json_file(self, path, payload):
        if getattr(self, "store", None) is None:
            return
        try:
            if getattr(self, "store", None) is not None:
                target = str(path or "").strip()
                body = dict(payload or {})
                if target.startswith("db://"):
                    _, _, remainder = target.partition("db://")
                    account_name, _, character_name = remainder.partition("/")
                    display_name = str((body.get("player") or {}).get("name") or character_name)
                    self.store.upsert_character_payload(account_name, character_name, body, display_name)
                    return
                if target.startswith("dbauth://"):
                    account_name = str(target.partition("dbauth://")[2] or "").strip()
                    self.store.upsert_account_payload(account_name, body)
                    return

                rel_path = os.path.relpath(os.path.abspath(target), os.path.abspath(self.saves_dir))
                rel_parts = rel_path.split(os.sep)
                low_file = str(rel_parts[-1] if rel_parts else "").lower()
                shared_map = {
                    "universe_planets.json": "universe_planets",
                    "galactic_news.json": "galactic_news",
                    "winner_board.json": "winner_board",
                    "analytics_metrics.json": "analytics_metrics",
                }
                if len(rel_parts) == 1 and low_file in shared_map:
                    self.store.set_kv("shared", shared_map[low_file], body)
                    return
                if len(rel_parts) == 2 and low_file == "account.json":
                    self.store.upsert_account_payload(rel_parts[0], body)
                    return
                if len(rel_parts) == 2 and low_file.endswith(".json"):
                    account_name = rel_parts[0]
                    character_name = os.path.splitext(rel_parts[1])[0]
                    display_name = str((body.get("player") or {}).get("name") or character_name)
                    self.store.upsert_character_payload(account_name, character_name, body, display_name)
                    return
        except Exception:
            pass

        return

    def _is_reserved_save_file(self, file_name):
        low = str(file_name or "").strip().lower()
        return low in ("universe_planets.json", "galactic_news.json", "account.json")

    def _owner_matches(self, left, right):
        return str(left or "").strip().lower() == str(right or "").strip().lower()

    def _normalize_commander_ref(self, path):
        target = str(path or "").strip()
        if not target:
            return ""
        if target.startswith("db://"):
            return target.lower()
        return os.path.abspath(target)

    def _collect_player_account_records(self):
        accounts = {}

        def ensure_account(account_name):
            safe = str(account_name or "").strip()
            if not safe:
                return None
            key = safe.lower()
            if key not in accounts:
                accounts[key] = {
                    "account_name": safe,
                    "account_dir": None,
                    "auth_path": None,
                    "auth_data": {},
                    "commanders": [],
                }
            return accounts[key]

        if getattr(self, "store", None) is not None:
            for account_row in self.store.iter_accounts():
                account_name = str(account_row.get("account_name") or "").strip()
                if not account_name:
                    continue
                acc = ensure_account(account_name)
                if not acc:
                    continue
                acc["auth_path"] = f"dbauth://{account_name}"
                payload = account_row.get("payload") if isinstance(account_row, dict) else None
                if isinstance(payload, dict):
                    acc["auth_data"] = payload

            for row in self.store.iter_all_characters():
                account_name = str(row.get("account_name") or "").strip()
                character_name = str(row.get("character_name") or "").strip()
                data = row.get("payload") if isinstance(row, dict) else None
                if not account_name or not character_name or not isinstance(data, dict):
                    continue
                acc = ensure_account(account_name)
                if not acc:
                    continue
                acc["auth_path"] = f"dbauth://{account_name}"
                if not isinstance(acc.get("auth_data"), dict) or not acc.get("auth_data"):
                    auth_data = self.store.get_account_payload(account_name)
                    if isinstance(auth_data, dict):
                        acc["auth_data"] = auth_data
                player_name = str(data.get("player", {}).get("name") or character_name).strip()
                acc["commanders"].append(
                    {
                        "character_name": character_name,
                        "display_name": player_name,
                        "path": f"db://{account_name}/{character_name}",
                        "data": data,
                    }
                )

            records = []
            for acc in accounts.values():
                acc["commanders"].sort(
                    key=lambda c: (
                        str(c.get("character_name", "")).lower(),
                        str(c.get("display_name", "")).lower(),
                    )
                )
                records.append(acc)
            records.sort(key=lambda a: str(a.get("account_name", "")).lower())
            return records

        return []

    def _load_player_save_files(self):
        records = []
        for account in self._collect_player_account_records():
            for commander in account.get("commanders", []):
                path = commander.get("path", "")
                records.append(
                    {
                        "file_name": os.path.basename(path),
                        "path": path,
                        "player_name": commander.get("display_name")
                        or commander.get("character_name")
                        or "",
                        "data": commander.get("data", {}),
                    }
                )
        return records

    def refresh_players_list(self):
        previous_commander_path = self.selected_player_path
        self.players_records = self._collect_player_account_records()
        for w in self.players_scroll.winfo_children():
            w.destroy()
        self.commander_button_by_path = {}

        account_count = len(self.players_records)
        commander_count = sum(
            len(a.get("commanders", [])) for a in self.players_records
        )
        disabled_count = 0
        blacklisted_count = 0
        for account in self.players_records:
            auth_data = dict(account.get("auth_data", {}) or {})
            if bool(auth_data.get("account_disabled", False)):
                disabled_count += 1
            elif bool(auth_data.get("blacklisted", False)):
                blacklisted_count += 1

        active_count = max(0, account_count - disabled_count - blacklisted_count)

        self.players_summary_lbl.configure(
            text=(
                f"Accounts: {account_count}  Commanders: {commander_count}  "
                f"Active: {active_count}  Disabled: {disabled_count}  Blacklisted: {blacklisted_count}"
            )
        )

        for account in self.players_records:
            auth_data = dict(account.get("auth_data", {}) or {})
            name = str(account.get("account_name", ""))
            commander_total = len(account.get("commanders", []))
            if bool(auth_data.get("account_disabled", False)):
                suffix = " [DISABLED]"
                text_color = "#d35454"
            elif bool(auth_data.get("blacklisted", False)):
                suffix = " [BLACKLISTED]"
                text_color = "#cc8f20"
            else:
                suffix = ""
                text_color = "#e8e8e8"

            account_selected = self._owner_matches(name, self.selected_account_name)
            ctk.CTkButton(
                self.players_scroll,
                text=f"{name} ({commander_total}){suffix}",
                fg_color=("#2d2d2d" if account_selected else "transparent"),
                hover_color="#2d2d2d",
                text_color=text_color,
                anchor="w",
                command=lambda a=account: self.select_player_record(a),
            ).pack(fill="x", pady=2)

            for commander in list(account.get("commanders", []) or []):
                display_name = str(
                    commander.get("display_name")
                    or commander.get("character_name")
                    or ""
                )
                char_name = str(commander.get("character_name") or "")
                cmd_btn = ctk.CTkButton(
                    self.players_scroll,
                    text=f"     {display_name} [{char_name}]",
                    fg_color="transparent",
                    hover_color="#2d2d2d",
                    text_color="#e8e8e8",
                    anchor="w",
                    command=lambda c=commander: self.select_commander_record(c),
                )
                cmd_btn.pack(fill="x", pady=1)
                cmd_path = commander.get("path")
                if cmd_path:
                    self.commander_button_by_path[
                        self._normalize_commander_ref(cmd_path)
                    ] = cmd_btn

        self._refresh_commander_selection_highlight()

        if self.selected_account_name:
            selected = next(
                (
                    a
                    for a in self.players_records
                    if self._owner_matches(
                        a.get("account_name", ""), self.selected_account_name
                    )
                ),
                None,
            )
            if selected:
                self.select_player_record(selected)
                if previous_commander_path:
                    retained = next(
                        (
                            c
                            for c in list(selected.get("commanders", []) or [])
                            if self._normalize_commander_ref(c.get("path", ""))
                            == self._normalize_commander_ref(previous_commander_path)
                        ),
                        None,
                    )
                    if retained:
                        self.select_commander_record(retained)
            else:
                self.selected_account_name = None
                self.selected_account_auth_path = None
                self.selected_commander_record = None
                self.selected_player_path = None
                self.players_selected_info.configure(
                    text="Select an account from the left list."
                )
                self.commander_selected_info.configure(
                    text="Select a commander to edit save data."
                )
                self._begin_dirty_suspension()
                try:
                    for key in self.player_entries:
                        widget = self.player_entries[key]
                        widget.configure(state="normal")
                        widget.delete(0, "end")
                        if key == "name":
                            widget.configure(state="disabled")
                    self.player_disabled_var.set(False)
                    self.player_blacklisted_var.set(False)
                    self.player_new_password.delete(0, "end")
                finally:
                    self._end_dirty_suspension()

    def _render_selected_account_commanders(self, account_record):
        return

    def _refresh_commander_selection_highlight(self):
        selected_path = ""
        if isinstance(self.selected_commander_record, dict):
            selected_path = str(
                self.selected_commander_record.get("path") or ""
            ).strip()
        selected_ref = self._normalize_commander_ref(selected_path)

        for path_key, btn in dict(
            getattr(self, "commander_button_by_path", {}) or {}
        ).items():
            is_selected = bool(selected_ref) and (
                self._normalize_commander_ref(path_key) == selected_ref
            )
            try:
                if is_selected:
                    btn.configure(
                        fg_color="#1f6aa5",
                        hover_color="#144870",
                        text_color="#ffffff",
                    )
                else:
                    btn.configure(
                        fg_color="transparent",
                        hover_color="#2d2d2d",
                        text_color="#e8e8e8",
                    )
            except Exception:
                continue

    def select_player_record(self, record):
        self.selected_account_name = str(record.get("account_name", "")).strip() or None
        self.selected_account_auth_path = record.get("auth_path")
        self.selected_commander_record = None
        self.selected_player_path = None

        auth_data = dict(record.get("auth_data", {}) or {})
        self.players_selected_info.configure(
            text=(
                f"Account: {self.selected_account_name or 'Unknown'}"
                f" | Source: {'SQLite' if self.selected_account_auth_path else 'No auth record'}"
            )
        )
        self.commander_selected_info.configure(
            text="Select a commander to edit save data."
        )
        self._refresh_commander_selection_highlight()
        self._set_player_action_mode("account")

        self._begin_dirty_suspension()
        try:
            for key, widget in self.player_entries.items():
                widget.configure(state="normal")
                widget.delete(0, "end")
                if key == "name":
                    widget.configure(state="disabled")

            self.player_disabled_var.set(bool(auth_data.get("account_disabled", False)))
            self.player_blacklisted_var.set(bool(auth_data.get("blacklisted", False)))
            self.player_new_password.delete(0, "end")
        finally:
            self._end_dirty_suspension()

    def select_commander_record(self, commander_record):
        self.selected_commander_record = commander_record
        self.selected_player_path = commander_record.get("path")
        self._refresh_commander_selection_highlight()
        self._set_player_action_mode("commander")
        data = dict(commander_record.get("data", {}) or {})
        player = dict(data.get("player", {}) or {})
        ship = dict(player.get("spaceship", {}) or {})
        id_by_name, name_by_id = self._build_planet_id_maps()

        universe_states = {}
        universe_payload = self._read_json_file(os.path.join(self.saves_dir, "universe_planets.json"))
        if isinstance(universe_payload, dict):
            universe_states = dict(universe_payload.get("planet_states", {}) or {})

        owner_key = str(player.get("name", "") or "").strip().lower()
        owned_ids = []
        for pid_key, state in universe_states.items():
            if not isinstance(state, dict):
                continue
            if not self._owner_matches(state.get("owner"), owner_key):
                continue
            try:
                owned_ids.append(int(pid_key))
            except Exception:
                continue

        path_text = os.path.basename(self.selected_player_path or "")
        self.commander_selected_info.configure(
            text=f"Editing commander: {player.get('name', commander_record.get('character_name', ''))} ({path_text})"
        )

        self._begin_dirty_suspension()
        try:
            self.player_entries["name"].configure(state="normal")
            self.player_entries["name"].delete(0, "end")
            self.player_entries["name"].insert(0, str(player.get("name", "")))
            self.player_entries["name"].configure(state="disabled")

            self.player_entries["credits"].delete(0, "end")
            self.player_entries["credits"].insert(0, str(player.get("credits", 0)))

            self.player_entries["bank_credits"].delete(0, "end")
            self.player_entries["bank_credits"].insert(
                0, str(player.get("bank_balance", 0))
            )

            self.player_entries["location"].delete(0, "end")
            current_pid = self._resolve_planet_id(data.get("current_planet_id"), id_by_name)
            if current_pid is None:
                current_pid = self._resolve_planet_id(data.get("current_planet_name"), id_by_name)
            self.player_entries["location"].insert(0, str(name_by_id.get(current_pid, "")))

            self.player_entries["ship_model"].delete(0, "end")
            self.player_entries["ship_model"].insert(0, str(ship.get("model", "")))

            owned_list = sorted(
                [str(name_by_id.get(pid, pid)) for pid in owned_ids],
                key=lambda v: str(v).lower(),
            )
            self.player_entries["owned_planets"].delete(0, "end")
            self.player_entries["owned_planets"].insert(0, ", ".join(owned_list))
        finally:
            self._end_dirty_suspension()

    def _replace_other_owner(self, target_planet, new_owner_name, current_save_path):
        id_by_name, _name_by_id = self._build_planet_id_maps()
        target_id = self._resolve_planet_id(target_planet, id_by_name)
        if target_id is None:
            return True

        universe_path = os.path.join(self.saves_dir, "universe_planets.json")
        u_data = self._read_json_file(universe_path)
        if not isinstance(u_data, dict):
            return True
        states = u_data.get("planet_states", {})
        if not isinstance(states, dict):
            return True
        current_state = states.get(str(target_id), {})
        if not isinstance(current_state, dict):
            return True
        owner = current_state.get("owner")
        if not owner or self._owner_matches(owner, new_owner_name):
            return True

        confirm = messagebox.askyesno(
            "Replace Owner?",
            f"Planet '{target_planet}' is currently owned by '{owner}'.\n"
            f"Replace with '{new_owner_name}'?",
        )
        if not confirm:
            return False

        current_state["owner"] = None
        self._write_json_file(universe_path, u_data)

        return True

    def _clear_planet_owner_references(self, owner_name, owned_planets=None):
        owner_text = str(owner_name or "").strip()
        if not owner_text:
            return

        owned_set = None
        if owned_planets is not None:
            owned_set = {str(p).strip() for p in owned_planets if str(p).strip()}

        id_by_name, _name_by_id = self._build_planet_id_maps()
        if owned_set is not None:
            owned_set = {
                str(pid)
                for raw in owned_set
                for pid in [self._resolve_planet_id(raw, id_by_name)]
                if pid is not None
            }

        for account in self._collect_player_account_records():
            for commander in list(account.get("commanders", []) or []):
                path = commander.get("path", "")
                data = self._read_json_file(path)
                if not isinstance(data, dict):
                    continue

                changed = False
                player = data.get("player", {})
                if isinstance(player, dict):
                    if player.pop("owned_planets", None) is not None:
                        changed = True
                if data.pop("planet_states", None) is not None:
                    changed = True

                if changed:
                    self._write_json_file(path, data)

        universe_path = os.path.join(self.saves_dir, "universe_planets.json")
        u_data = self._read_json_file(universe_path)
        if isinstance(u_data, dict):
            states = u_data.get("planet_states", {})
            if isinstance(states, dict):
                changed = False
                for planet_key, state in states.items():
                    if not isinstance(state, dict):
                        continue
                    if not self._owner_matches(state.get("owner"), owner_text):
                        continue
                    if (
                        owned_set is not None
                        and str(planet_key).strip() not in owned_set
                    ):
                        continue
                    state["owner"] = None
                    changed = True
                if changed:
                    self._write_json_file(universe_path, u_data)

    def _clear_account_owner_references(self, account_name):
        account_key = str(account_name or "").strip().lower()
        if not account_key:
            return
        for account in self._collect_player_account_records():
            if not self._owner_matches(account.get("account_name", ""), account_key):
                continue
            for commander in list(account.get("commanders", []) or []):
                data = dict(commander.get("data") or {})
                player = (
                    data.get("player") if isinstance(data.get("player"), dict) else {}
                )
                owner_name = str(
                    player.get("name") or commander.get("display_name") or ""
                ).strip()
                if owner_name:
                    self._clear_planet_owner_references(owner_name)

    def _sync_universe_planet_owners(self, owner_name, owned_set):
        id_by_name, _name_by_id = self._build_planet_id_maps()
        owned_ids = {
            str(pid)
            for raw in set(owned_set or set())
            for pid in [self._resolve_planet_id(raw, id_by_name)]
            if pid is not None
        }
        universe_path = os.path.join(self.saves_dir, "universe_planets.json")
        try:
            data = self._read_json_file(universe_path)
            if not isinstance(data, dict):
                return
            states = data.get("planet_states", {})
            if not isinstance(states, dict):
                return
            for planet_key, state in states.items():
                if not isinstance(state, dict):
                    continue
                current_owner = state.get("owner")
                if str(planet_key) in owned_ids:
                    state["owner"] = owner_name
                elif self._owner_matches(current_owner, owner_name):
                    state["owner"] = None
            self._write_json_file(universe_path, data)
        except Exception:
            return

    def save_player_changes(self):
        if not self.selected_player_path:
            messagebox.showinfo("No Commander", "Select a commander first.")
            return

        try:
            data = self._read_json_file(self.selected_player_path)
            if not isinstance(data, dict):
                raise ValueError("Commander profile is unavailable")
        except Exception as ex:
            messagebox.showerror("Load Failed", f"Could not open save file: {ex}")
            return

        player = data.setdefault("player", {})
        ship = player.setdefault("spaceship", {})

        player_name = str(player.get("name", "")).strip()
        location = self.player_entries["location"].get().strip()
        ship_model = self.player_entries["ship_model"].get().strip()
        owned_set = self._parse_owned_planets_text(
            self.player_entries["owned_planets"].get().strip()
        )
        now_blocked = bool(self.player_disabled_var.get()) or bool(
            self.player_blacklisted_var.get()
        )

        try:
            credits = int(float(self.player_entries["credits"].get().strip() or "0"))
            bank_credits = int(
                float(self.player_entries["bank_credits"].get().strip() or "0")
            )
        except Exception:
            messagebox.showerror(
                "Invalid Credits", "Credits and bank credits must be numeric."
            )
            return

        # Handle ownership conflicts planet-by-planet.
        approved_owned = set()
        for planet_name in sorted(owned_set):
            if self._replace_other_owner(
                planet_name, player_name, self.selected_player_path
            ):
                approved_owned.add(planet_name)

        if now_blocked:
            approved_owned = set()

        # Update this player's owned planets and planet state ownership.
        player["credits"] = max(0, credits)
        player["bank_balance"] = max(0, bank_credits)
        id_by_name, _name_by_id = self._build_planet_id_maps()
        if location:
            loc_id = self._resolve_planet_id(location, id_by_name)
            if loc_id is not None:
                data["current_planet_id"] = int(loc_id)
            data.pop("current_planet_name", None)
        if ship_model:
            ship["model"] = ship_model

        # Commander files should not persist authoritative ownership or shared planet state.
        player.pop("owned_planets", None)
        data.pop("planet_states", None)

        try:
            self._write_json_file(self.selected_player_path, data)
        except Exception as ex:
            messagebox.showerror("Save Failed", f"Could not write save file: {ex}")
            return

        auth_path = self.selected_account_auth_path
        if auth_path:
            auth_data = self._read_json_file(auth_path)
            if isinstance(auth_data, dict):
                auth_data["account_disabled"] = bool(self.player_disabled_var.get())
                auth_data["blacklisted"] = bool(self.player_blacklisted_var.get())
                self._write_json_file(auth_path, auth_data)

        self._sync_universe_planet_owners(player_name, approved_owned)
        if now_blocked:
            self._clear_planet_owner_references(player_name)
            self._clear_account_owner_references(self.selected_account_name)
        self.refresh_players_list()
        self._set_section_dirty("players", False)
        messagebox.showinfo("Saved", f"Updated commander '{player_name}'.")

    def reset_player_password(self):
        if not self.selected_account_auth_path:
            messagebox.showinfo(
                "No Account",
                "Select an account before resetting password.",
            )
            return
        if bcrypt is None:
            messagebox.showerror(
                "bcrypt Missing",
                "bcrypt is not installed in this environment. Install server requirements first.",
            )
            return

        new_password = self.player_new_password.get().strip()
        if len(new_password) < 3:
            messagebox.showerror(
                "Invalid Password", "Enter a new password (at least 3 characters)."
            )
            return

        try:
            data = self._read_json_file(self.selected_account_auth_path)
            if not isinstance(data, dict):
                raise ValueError("Account profile is unavailable")
            password_hash = bcrypt.hashpw(
                new_password.encode("utf-8"), bcrypt.gensalt()
            ).decode("utf-8")
            data["password_hash"] = password_hash
            data["account_disabled"] = bool(self.player_disabled_var.get())
            data["blacklisted"] = bool(self.player_blacklisted_var.get())
            self._write_json_file(self.selected_account_auth_path, data)
            self.player_new_password.delete(0, "end")
            self._set_section_dirty("players", False)
            messagebox.showinfo("Password Reset", "Password updated successfully.")
        except Exception as ex:
            messagebox.showerror("Password Reset Failed", str(ex))

    def delete_selected_commander(self):
        commander = self.selected_commander_record or {}
        path = commander.get("path") if isinstance(commander, dict) else None
        if not path:
            messagebox.showinfo("No Commander", "Select a commander first.")
            return

        success, commander_name, _ = self._delete_commander_record(
            commander_record=commander,
            prompt=True,
        )
        if not success:
            return

        self.selected_commander_record = None
        self.selected_player_path = None
        self.commander_selected_info.configure(
            text="Select a commander to edit save data."
        )
        self._set_player_action_mode("account")
        self.refresh_players_list()
        self._set_section_dirty("players", False)
        messagebox.showinfo("Deleted", f"Deleted commander '{commander_name}'.")

    def _delete_commander_record(self, commander_record, prompt=True):
        commander = commander_record or {}
        path = commander.get("path") if isinstance(commander, dict) else None
        if not path:
            return False, "", "missing"

        try:
            data = self._read_json_file(path) or {}
            commander_name = str(
                data.get("player", {}).get("name")
                or commander.get("display_name")
                or commander.get("character_name")
                or os.path.basename(path)
            )
            char_name = str(
                data.get("character_name")
                or commander.get("character_name")
                or os.path.splitext(os.path.basename(path))[0]
            )
            owned_set = {
                str(k).strip()
                for k, v in dict(
                    data.get("player", {}).get("owned_planets", {})
                ).items()
                if str(k).strip() and bool(v)
            }
            if not owned_set:
                u_data = self._read_json_file(
                    os.path.join(self.saves_dir, "universe_planets.json")
                )
                u_states = dict((u_data or {}).get("planet_states", {}) or {})
                for p_key, p_state in u_states.items():
                    if not isinstance(p_state, dict):
                        continue
                    if self._owner_matches(p_state.get("owner"), commander_name):
                        owned_set.add(str(p_key).strip())
        except Exception:
            commander_name = os.path.basename(path)
            char_name = os.path.splitext(os.path.basename(path))[0]
            owned_set = set()

        if prompt:
            if not messagebox.askyesno(
                "Delete Commander",
                f"Delete commander '{commander_name}' permanently?\nThis cannot be undone.",
            ):
                return False, commander_name, "cancelled"

        self._clear_planet_owner_references(commander_name, owned_set)

        try:
            if str(path).startswith("db://") and getattr(self, "store", None) is not None:
                _, _, remainder = str(path).partition("db://")
                account_name, _, character_name = remainder.partition("/")
                self.store.delete_character(account_name, character_name)
            else:
                raise ValueError("Unsupported non-database commander path")
        except Exception as ex:
            if prompt:
                messagebox.showerror("Delete Failed", str(ex))
            return False, commander_name, str(ex)

        if self.selected_account_auth_path:
            auth_data = self._read_json_file(self.selected_account_auth_path)
            if isinstance(auth_data, dict):
                chars = []
                for entry in list(auth_data.get("characters", []) or []):
                    c_name = str(entry.get("character_name") or "").strip()
                    if c_name.lower() == char_name.lower():
                        continue
                    chars.append(entry)
                auth_data["characters"] = chars
                auth_data["account_disabled"] = bool(self.player_disabled_var.get())
                auth_data["blacklisted"] = bool(self.player_blacklisted_var.get())
                self._write_json_file(self.selected_account_auth_path, auth_data)

            return True, commander_name, "ok"

    def delete_selected_player(self):
        if not self.selected_account_name:
            messagebox.showinfo("No Account", "Select an account first.")
            return

        account_name = str(self.selected_account_name)

        if not messagebox.askyesno(
            "Delete Account",
            f"Delete account '{account_name}' and all commanders permanently?\nThis cannot be undone.",
        ):
            return

        account_record = next(
            (
                a
                for a in self._collect_player_account_records()
                if self._owner_matches(a.get("account_name", ""), account_name)
            ),
            None,
        )
        if not account_record:
            messagebox.showerror("Delete Failed", "Account record no longer exists.")
            self.refresh_players_list()
            return

        account_auth_path = account_record.get("auth_path")
        self.selected_account_auth_path = account_auth_path

        for commander in list(account_record.get("commanders", []) or []):
            self._delete_commander_record(commander, prompt=False)

        try:
            auth_path = account_record.get("auth_path")
            if (
                auth_path
                and str(auth_path).startswith("dbauth://")
                and getattr(self, "store", None) is not None
            ):
                account_ref = str(auth_path).partition("dbauth://")[2].strip()
                self.store.delete_account(account_ref)
            else:
                raise ValueError("Unsupported non-database account path")
        except Exception as ex:
            messagebox.showerror("Delete Failed", str(ex))
            return

        self.selected_account_name = None
        self.selected_account_auth_path = None
        self.selected_commander_record = None
        self.selected_player_path = None
        self.players_selected_info.configure(
            text="Select an account from the left list."
        )
        self.commander_selected_info.configure(
            text="Select a commander to edit save data."
        )
        self._set_player_action_mode("account")
        self.refresh_players_list()
        self._set_section_dirty("players", False)
        messagebox.showinfo("Deleted", f"Deleted account '{account_name}'.")

    def setup_crud_tab(
        self,
        frame,
        title,
        scroll_cmd,
        add_cmd,
        del_cmd,
        fields,
        has_desc=False,
        has_items=False,
    ):
        for child in frame.winfo_children():
            child.destroy()

        frame.grid_columnconfigure(0, weight=1, minsize=300)
        frame.grid_columnconfigure(1, weight=2)
        frame.grid_rowconfigure(0, weight=1)
        l_cont = ctk.CTkFrame(frame, width=300)
        l_cont.grid(row=0, column=0, sticky="nsew", padx=(10, 5), pady=10)
        ctk.CTkLabel(l_cont, text=title, font=ctk.CTkFont(size=16, weight="bold")).pack(
            pady=10
        )
        scroll_host, scroll = self._create_scrollable_area(l_cont, width=280)
        scroll_host.pack(fill="both", expand=True, padx=5, pady=5)
        # Store for refreshes
        if title == "Planetary Archive":
            self.p_scroll = scroll
            self.p_entries = {}
            self.p_desc = None
            self.p_items = None
            if not hasattr(self, "planet_filter_active_only"):
                self.planet_filter_active_only = ctk.BooleanVar(value=False)
        elif title == "Global Commodities":
            self.i_scroll = scroll
            self.i_entries = {}
            if not hasattr(self, "item_filter_active_only"):
                self.item_filter_active_only = ctk.BooleanVar(value=False)
        elif title == "Shipyard Templates":
            self.s_scroll = scroll
            self.s_entries = {}

        ctk.CTkButton(
            l_cont, text="+ Add New", command=add_cmd, fg_color="#3498db"
        ).pack(pady=10)

        if title == "Planetary Archive":
            row = ctk.CTkFrame(l_cont, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=(2, 8))
            ctk.CTkButton(
                row,
                text="Activate",
                width=120,
                fg_color="#2ecc71",
                hover_color="#27ae60",
                command=self.activate_selected_planet,
            ).pack(side="left", padx=(0, 6), pady=2)
            ctk.CTkButton(
                row,
                text="Deactivate",
                width=120,
                fg_color="#e67e22",
                hover_color="#d35400",
                command=self.deactivate_selected_planet,
            ).pack(side="left", pady=2)

            filt_row = ctk.CTkFrame(l_cont, fg_color="transparent")
            filt_row.pack(fill="x", padx=8, pady=(0, 8))
            ctk.CTkSwitch(
                filt_row,
                text="Show Active Only",
                variable=self.planet_filter_active_only,
                command=lambda: self.refresh_list("Planetary Archive"),
            ).pack(side="left", pady=2)
        elif title == "Global Commodities":
            row = ctk.CTkFrame(l_cont, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=(2, 8))
            ctk.CTkButton(
                row,
                text="Activate",
                width=120,
                fg_color="#2ecc71",
                hover_color="#27ae60",
                command=self.activate_selected_item,
            ).pack(side="left", padx=(0, 6), pady=2)
            ctk.CTkButton(
                row,
                text="Deactivate",
                width=120,
                fg_color="#e67e22",
                hover_color="#d35400",
                command=self.deactivate_selected_item,
            ).pack(side="left", pady=2)

            filt_row = ctk.CTkFrame(l_cont, fg_color="transparent")
            filt_row.pack(fill="x", padx=8, pady=(0, 8))
            ctk.CTkSwitch(
                filt_row,
                text="Show Active Only",
                variable=self.item_filter_active_only,
                command=lambda: self.refresh_list("Global Commodities"),
            ).pack(side="left", pady=2)

        r_cont_host, r_cont = self._create_scrollable_area(frame)
        r_cont_host.grid(row=0, column=1, sticky="nsew", padx=(5, 10), pady=10)
        entries = (
            self.p_entries
            if title == "Planetary Archive"
            else (self.i_entries if title == "Global Commodities" else self.s_entries)
        )

        for field, lbl in fields:
            ctk.CTkLabel(r_cont, text=lbl).pack(padx=20, pady=(10, 0), anchor="w")
            if field == "active":
                var = ctk.BooleanVar(value=True)
                row = ctk.CTkFrame(r_cont, fg_color="transparent")
                row.pack(padx=20, pady=5, anchor="w")
                ctk.CTkSwitch(row, text="", variable=var).pack(side="left")
                ctk.CTkLabel(
                    row,
                    text="ON / OFF",
                    text_color=("gray45", "gray70"),
                    font=ctk.CTkFont(size=11),
                ).pack(side="left", padx=(8, 0))
                entries[field] = {"kind": "bool", "var": var}
            else:
                entries[field] = ctk.CTkEntry(r_cont, width=400)
                entries[field].pack(padx=20, pady=5, anchor="w")

        if has_desc:
            ctk.CTkLabel(r_cont, text="Description:").pack(
                padx=20, pady=(10, 0), anchor="w"
            )
            self.p_desc = ctk.CTkTextbox(r_cont, width=400, height=100)
            self.p_desc.pack(padx=20, pady=5, anchor="w")
        if has_items:
            ctk.CTkLabel(r_cont, text="Market Content (Name,Price;...):").pack(
                padx=20, pady=(10, 0), anchor="w"
            )
            self.p_items = ctk.CTkEntry(r_cont, width=400)
            self.p_items.pack(padx=20, pady=5, anchor="w")

        ctk.CTkButton(
            r_cont, text="Remove Selected", fg_color="#e74c3c", command=del_cmd
        ).pack(padx=20, pady=20, anchor="w")
        self.refresh_list(title)

    # EVENT HANDLERS
    def select_frame_by_name(self, name):
        section_to_tab = {
            "settings": 0,
            "planets": 1,
            "items": 2,
            "ships": 3,
            "spaceships": 3,
            "players": 4,
        }
        idx = section_to_tab.get(name, 0)
        if hasattr(self, "main_tabs"):
            self.main_tabs.select(idx)
        self._update_section_status(name)

    def _on_tab_changed(self, _event=None):
        if not hasattr(self, "main_tabs"):
            return
        current = self.main_tabs.tab(self.main_tabs.select(), "text").strip().lower()
        section = "settings"
        if current == "planets":
            section = "planets"
        elif current == "items":
            section = "items"
        elif current == "spaceships":
            section = "ships"
        elif current == "players":
            section = "players"
        self.current_section = section
        self._update_section_status(section)

    def _is_active_text(self, value):
        return str(value).strip().lower() in ("1", "true", "yes", "on")

    def _update_section_status(self, section_name=None):
        section = section_name or getattr(self, "current_section", "settings")
        if section == "planets":
            total = len(getattr(self, "planets", []))
            active = sum(
                1
                for p in getattr(self, "planets", [])
                if self._is_active_text(p.get("active", "On"))
            )
            self.section_status_lbl.configure(
                text=f"Planets: {active} active / {total} total"
            )
            return
        if section == "items":
            total = len(getattr(self, "items", []))
            active = sum(
                1
                for i in getattr(self, "items", [])
                if self._is_active_text(i.get("active", "On"))
            )
            self.section_status_lbl.configure(
                text=f"Items: {active} active / {total} total"
            )
            return
        if section == "ships":
            total = len(getattr(self, "ships", []))
            self.section_status_lbl.configure(text=f"Spaceships: {total} total")
            return
        if section == "players":
            total = len(getattr(self, "players_records", []))
            self.section_status_lbl.configure(text=f"Players: {total} total")
            return
        self.section_status_lbl.configure(
            text=f"Settings keys: {len(getattr(self, 'settings_widgets', {}))}"
        )

    def refresh_list(self, title):
        if title == "Planetary Archive":
            scroll, data, cmd = self.p_scroll, self.planets, self.planet_scroll_event
            self.cur_p = -1
        elif title == "Global Commodities":
            scroll, data, cmd = self.i_scroll, self.items, self.item_scroll_event
            self.cur_i = -1
        else:
            scroll, data, cmd = self.s_scroll, self.ships, self.ship_scroll_event
            self.cur_s = -1

        for w in scroll.winfo_children():
            w.destroy()
        source_rows = list(enumerate(data))
        if title == "Planetary Archive" and hasattr(self, "planet_filter_active_only"):
            if bool(self.planet_filter_active_only.get()):
                source_rows = [
                    (i, d)
                    for i, d in source_rows
                    if self._is_active_text(d.get("active", "On"))
                ]
        elif title == "Global Commodities" and hasattr(self, "item_filter_active_only"):
            if bool(self.item_filter_active_only.get()):
                source_rows = [
                    (i, d)
                    for i, d in source_rows
                    if self._is_active_text(d.get("active", "On"))
                ]

        for i, d in source_rows:
            name = d["name"] if "name" in d else d["model"]
            is_active = True
            if title in ("Planetary Archive", "Global Commodities"):
                is_active = self._is_active_text(d.get("active", "On"))
            display_name = name if is_active else f"{name} [INACTIVE]"
            ctk.CTkButton(
                scroll,
                text=display_name,
                fg_color="transparent",
                text_color=("#E8E8E8" if is_active else "#A16A6A"),
                anchor="w",
                command=lambda idx=i: cmd(idx),
            ).pack(fill="x", pady=2)
        if title == "Planetary Archive":
            self._update_section_status("planets")
        elif title == "Global Commodities":
            self._update_section_status("items")

    def planet_scroll_event(self, idx):
        if hasattr(self, "cur_p") and self.cur_p != -1:
            self.save_state("planets")
        self.cur_p = idx
        p = self.planets[idx]
        self._begin_dirty_suspension()
        try:
            for f, e in self.p_entries.items():
                self._set_entry_widget_value(e, p.get(f, ""))
            self.p_desc.delete("1.0", "end")
            self.p_desc.insert("1.0", p["desc"])
            self.p_items.delete(0, "end")
            self.p_items.insert(0, p["items"])
        finally:
            self._end_dirty_suspension()

    def item_scroll_event(self, idx):
        if hasattr(self, "cur_i") and self.cur_i != -1:
            self.save_state("items")
        self.cur_i = idx
        i = self.items[idx]
        self._begin_dirty_suspension()
        try:
            for f, e in self.i_entries.items():
                self._set_entry_widget_value(e, i.get(f, ""))
        finally:
            self._end_dirty_suspension()

    def ship_scroll_event(self, idx):
        if hasattr(self, "cur_s") and self.cur_s != -1:
            self.save_state("ships")
        self.cur_s = idx
        s = self.ships[idx]
        self._begin_dirty_suspension()
        try:
            for f, e in self.s_entries.items():
                self._set_entry_widget_value(e, s.get(f, ""))
        finally:
            self._end_dirty_suspension()

    def _normalize_bool_text(self, value):
        return (
            "On" if str(value).strip().lower() in ("1", "true", "yes", "on") else "Off"
        )

    def _set_entry_widget_value(self, widget, value):
        if isinstance(widget, dict) and widget.get("kind") == "bool":
            widget["var"].set(self._normalize_bool_text(value) == "On")
            return

        widget.delete(0, "end")
        widget.insert(0, str(value))

    def _get_entry_widget_value(self, widget):
        if isinstance(widget, dict) and widget.get("kind") == "bool":
            return "On" if bool(widget["var"].get()) else "Off"
        return widget.get()

    def save_state(self, mode):
        if mode == "planets" and self.cur_p != -1:
            p = self.planets[self.cur_p]
            p.update(
                {f: self._get_entry_widget_value(e) for f, e in self.p_entries.items()}
            )
            p["desc"] = self.p_desc.get("1.0", "end-1c").replace("\n", " ").strip()
            p["items"] = self.p_items.get()
        elif mode == "items" and self.cur_i != -1:
            self.items[self.cur_i].update(
                {f: self._get_entry_widget_value(e) for f, e in self.i_entries.items()}
            )
        elif mode == "ships" and self.cur_s != -1:
            self.ships[self.cur_s].update(
                {f: self._get_entry_widget_value(e) for f, e in self.s_entries.items()}
            )

    def add_planet_event(self):
        self.planets.append(
            {
                "name": "New World",
                "active": "On",
                "pop": "0",
                "desc": "Empty",
                "vendor": "None",
                "trade": "None",
                "defenders": "0",
                "shields": "0",
                "bank": "Off",
                "items": "",
            }
        )
        self.refresh_list("Planetary Archive")
        self._set_section_dirty("planets")

    def add_item_event(self):
        self.items.append(
            {"name": "New Item", "price": "100", "active": "On", "default_pct": "100"}
        )
        self.refresh_list("Global Commodities")
        self._set_section_dirty("items")

    def add_ship_event(self):
        self.ships.append(
            {
                "model": "New Ship",
                "cost": "1000",
                "s_cargo": "10",
                "s_shields": "10",
                "s_defenders": "10",
                "m_cargo": "100",
                "m_shields": "100",
                "m_defenders": "100",
                "special": "None",
                "integrity": "100",
            }
        )
        self.refresh_list("Shipyard Templates")
        self._set_section_dirty("ships")

    def delete_planet_event(self):
        if self.cur_p != -1:
            self.planets.pop(self.cur_p)
            self.cur_p = -1
            self.refresh_list("Planetary Archive")
            self._set_section_dirty("planets")

    def delete_item_event(self):
        if self.cur_i != -1:
            self.items.pop(self.cur_i)
            self.cur_i = -1
            self.refresh_list("Global Commodities")
            self._set_section_dirty("items")

    def activate_selected_planet(self):
        if getattr(self, "cur_p", -1) == -1:
            messagebox.showinfo("Select Planet", "Select a planet to activate.")
            return
        self.save_state("planets")
        self.planets[self.cur_p]["active"] = "True"
        self.planet_scroll_event(self.cur_p)
        self.refresh_list("Planetary Archive")
        self._set_section_dirty("planets")

    def deactivate_selected_planet(self):
        if getattr(self, "cur_p", -1) == -1:
            messagebox.showinfo("Select Planet", "Select a planet to deactivate.")
            return
        self.save_state("planets")
        self.planets[self.cur_p]["active"] = "False"
        self.planet_scroll_event(self.cur_p)
        self.refresh_list("Planetary Archive")
        self._set_section_dirty("planets")

    def activate_selected_item(self):
        if getattr(self, "cur_i", -1) == -1:
            messagebox.showinfo("Select Item", "Select an item to activate.")
            return
        self.save_state("items")
        self.items[self.cur_i]["active"] = "True"
        self.item_scroll_event(self.cur_i)
        self.refresh_list("Global Commodities")
        self._set_section_dirty("items")

    def deactivate_selected_item(self):
        if getattr(self, "cur_i", -1) == -1:
            messagebox.showinfo("Select Item", "Select an item to deactivate.")
            return
        self.save_state("items")
        self.items[self.cur_i]["active"] = "False"
        self.item_scroll_event(self.cur_i)
        self.refresh_list("Global Commodities")
        self._set_section_dirty("items")

    def delete_ship_event(self):
        if self.cur_s != -1:
            self.ships.pop(self.cur_s)
            self.cur_s = -1
            self.refresh_list("Shipyard Templates")
            self._set_section_dirty("ships")

    def _parse_planet_items(self, items_str):
        parsed = {}
        raw = str(items_str or "").strip()
        if not raw:
            return parsed
        for pair in raw.split(";"):
            piece = pair.strip()
            if not piece or "," not in piece:
                continue
            name, value = piece.split(",", 1)
            item_name = name.strip()
            item_price = value.strip()
            if not item_name:
                continue
            try:
                parsed[item_name] = str(int(float(item_price)))
            except Exception:
                continue
        return parsed

    def _format_planet_items(self, items_map):
        if not items_map:
            return ""
        return ";".join(
            [f"{name},{price}" for name, price in sorted(items_map.items())]
        )

    def disperse_selected_item_event(self):
        if not self.items:
            messagebox.showinfo("No Items", "No items available to disperse.")
            return

        if getattr(self, "cur_i", -1) == -1:
            messagebox.showinfo(
                "Select Item", "Select an item from the left list before dispersing."
            )
            return

        self.save_state("items")

        item = self.items[self.cur_i]
        item_name = str(item.get("name", "")).strip()
        if not item_name:
            messagebox.showerror("Invalid Item", "Item name cannot be empty.")
            return

        try:
            base_price = max(1, int(float(str(item.get("price", "100")).strip())))
        except Exception:
            messagebox.showerror("Invalid Price", "Item base price must be numeric.")
            return

        active_flag = str(item.get("active", "True")).strip().lower() in (
            "1",
            "true",
            "yes",
            "on",
        )
        if not active_flag:
            messagebox.showinfo(
                "Item Inactive",
                "Activate the item before dispersing it to planets.",
            )
            return

        try:
            default_pct = int(float(str(item.get("default_pct", "100")).strip()))
        except Exception:
            default_pct = 100
        default_pct = max(55, min(220, default_pct))

        viable = []
        for p in self.planets:
            if str(p.get("active", "True")).strip().lower() not in (
                "1",
                "true",
                "yes",
                "on",
            ):
                continue
            trade = str(p.get("trade", "")).strip().lower()
            if not trade or trade in ("none", "false", "0"):
                continue
            viable.append(p)

        if not viable:
            messagebox.showinfo(
                "No Viable Planets",
                "No active planets with a trade center were found.",
            )
            return

        spread_count = max(3, int(round(len(viable) * 0.45)))
        spread_count = min(len(viable), spread_count)
        selected = random.sample(viable, spread_count)

        updated = 0
        for p in selected:
            item_map = self._parse_planet_items(p.get("items", ""))
            drift = random.randint(-24, 28)
            pct = max(55, min(240, default_pct + drift))
            price = max(1, int(round(base_price * (pct / 100.0))))
            item_map[item_name] = str(price)
            p["items"] = self._format_planet_items(item_map)
            updated += 1

        if getattr(self, "cur_p", -1) != -1:
            p = self.planets[self.cur_p]
            for f, e in self.p_entries.items():
                self._set_entry_widget_value(e, p.get(f, ""))
            if self.p_desc is not None:
                self.p_desc.delete("1.0", "end")
                self.p_desc.insert("1.0", p.get("desc", ""))
            if self.p_items is not None:
                self.p_items.delete(0, "end")
                self.p_items.insert(0, p.get("items", ""))

            self._set_section_dirty("planets")

        messagebox.showinfo(
            "Dispersal Complete",
            f"Distributed '{item_name}' to {updated} active trade planets using current market pricing profile.",
        )

    def save_all(self):
        try:
            settings = self.config.setdefault("settings", {})
            updated_settings = {}
            parse_errors = []

            for existing_key in list(settings.keys()):
                if self._is_client_only_setting(existing_key):
                    settings.pop(existing_key, None)

            if getattr(self, "store", None) is not None:
                for existing_key in list(self.store.get_all_settings().keys()):
                    if self._is_client_only_setting(existing_key):
                        self.store.delete_kv("settings", existing_key)

            self._flush_editor_buffers()
            planet_sync_err = self._sync_selected_planet_editor_to_memory()
            if planet_sync_err:
                parse_errors.append(planet_sync_err)

            for key, widget_info in self.settings_widgets.items():
                original_type = widget_info["original_type"]
                try:
                    if widget_info["kind"] == "bool":
                        raw = widget_info["var"].get()
                    else:
                        raw = widget_info["entry"].get()
                    updated_settings[key] = self._coerce_setting_value(
                        raw, original_type
                    )
                except Exception as ex:
                    parse_errors.append(f"{key}: {ex}")

            if parse_errors:
                raise ValueError(
                    "Invalid setting values:\n" + "\n".join(parse_errors[:10])
                )

            settings.update(updated_settings)
            self._persist_settings_payload(self.config)

            self._save_editor_files()
            self.original_config = json.loads(json.dumps(self.config))
            self._clear_dirty_sections()
            messagebox.showinfo(
                "Success",
                "Saved settings and editor data files (planets/items/ships).",
            )
        except Exception as e:
            messagebox.showerror("Error", f"Save failed: {e}")

    # PLANET EDITOR METHODS

    def _collect_bg_stems(self):
        """Get all background image stems."""
        if not os.path.exists(self.bg_dir):
            return set()
        return {
            os.path.splitext(name)[0]
            for name in os.listdir(self.bg_dir)
            if name.lower().endswith(".png")
        }

    def _collect_thumb_stems(self):
        """Get all thumbnail image stems."""
        if not os.path.exists(self.thumb_dir):
            return set()
        out = set()
        for name in os.listdir(self.thumb_dir):
            if not name.lower().endswith(".png"):
                continue
            stem = os.path.splitext(name)[0]
            if stem.startswith("sm_"):
                stem = stem[3:]
            out.add(stem)
        return out

    def _planet_status(self, name, has_data, has_bg, has_thumb):
        """Determine planet status for catalog."""
        if has_data:
            return "ACTIVE"
        if name.startswith("UNUSED_"):
            return "UNUSED"
        if not has_bg or not has_thumb:
            return "UNUSED"
        return "READY"

    def _load_base_items_for_planet(self):
        """Load base items for planet default generation."""
        out = {}
        if not os.path.exists(self.items_path):
            return out
        for item in self.items:
            name = item.get("name", "").strip()
            price = item.get("price", "100")
            if name:
                try:
                    out[name] = int(price)
                except ValueError:
                    out[name] = 100
        return out

    def _generate_default_items_string(self):
        """Generate default items string for new planets."""
        base_items = self._load_base_items_for_planet()
        preferred = [
            "Fuel Cells",
            "Cargo Pod",
            "Nanobot Repair Kits",
            "Energy Shields",
            "Fighter Squadron",
            "Warp Drives",
            "Quantum Data Chips",
            "Purified Water Extractor",
        ]
        pairs = []
        for item in preferred:
            if item in base_items:
                pairs.append(f"{item},{base_items[item]}")
        if len(pairs) < 6:
            for name, price in base_items.items():
                pair = f"{name},{price}"
                if pair not in pairs:
                    pairs.append(pair)
                if len(pairs) >= 8:
                    break
        return ";".join(pairs[:8])

    def refresh_planet_catalog(self):
        """Refresh the planet catalog with status indicators."""
        # Load active planets from planets.txt
        active_planets = {}
        blocks = [
            b.strip()
            for b in re.split(r"\r?\n\r?\n", self._read_catalog_text(self.planets_path))
            if b.strip()
        ]
        for block in blocks:
            lines = [ln.strip() for ln in block.split("\n") if ln.strip()]
            if len(lines) < 9:
                continue
            vals = {}
            for ln in lines:
                if ":" not in ln:
                    continue
                k, v = ln.split(":", 1)
                vals[k.strip()] = v.strip()
            name = vals.get("Name")
            if name:
                active_planets[name] = vals

        # Get image availability
        bg_names = self._collect_bg_stems()
        thumb_names = self._collect_thumb_stems()
        active_names = set(active_planets.keys())

        # Build catalog
        all_names = []
        for name in sorted(active_names | bg_names | thumb_names):
            if name.startswith("UNUSED_"):
                used_name = name[len("UNUSED_") :]
                if (
                    used_name in active_names
                    or used_name in bg_names
                    or used_name in thumb_names
                ):
                    continue
            all_names.append(name)
        catalog = []
        for name in all_names:
            has_data = name in active_names
            has_bg = name in bg_names
            has_thumb = name in thumb_names
            status = self._planet_status(name, has_data, has_bg, has_thumb)
            catalog.append(
                {
                    "name": name,
                    "status": status,
                    "has_data": has_data,
                    "has_bg": has_bg,
                    "has_thumb": has_thumb,
                }
            )

        # Sort by status priority
        order = {"ACTIVE": 0, "READY": 1, "UNUSED": 2}
        catalog.sort(key=lambda c: (order.get(c["status"], 9), c["name"]))

        # Update summary
        active_count = sum(1 for c in catalog if c["status"] == "ACTIVE")
        ready_count = sum(1 for c in catalog if c["status"] == "READY")
        unused_count = sum(1 for c in catalog if c["status"] == "UNUSED")
        self.planet_summary_lbl.configure(
            text=f"Active: {active_count}   Ready: {ready_count}   Unused: {unused_count}"
        )

        # Clear and rebuild catalog list
        for w in self.catalog_scroll.winfo_children():
            w.destroy()

        for entry in catalog:
            name = entry["name"]
            status = entry["status"]
            color = (
                "#2ecc71"
                if status == "ACTIVE"
                else ("#f1c40f" if status == "READY" else "#7f8c8d")
            )
            text = f"[{status}] {name}"
            ctk.CTkButton(
                self.catalog_scroll,
                text=text,
                fg_color=color,
                hover_color=color,
                text_color="#101010",
                anchor="w",
                command=lambda n=name, e=entry: self.select_planet_from_catalog(n, e),
            ).pack(fill="x", padx=4, pady=2)

        self.planet_catalog = catalog
        self.active_planets_data = active_planets

    def select_planet_from_catalog(self, name, entry):
        """Select a planet from the catalog."""
        self.selected_planet_name = name

        # Update selection info
        self.selected_planet_info.configure(
            text=(
                f"Selected: {name} | Status: {entry['status']} | "
                f"Data: {'Y' if entry['has_data'] else 'N'} | "
                f"BG: {'Y' if entry['has_bg'] else 'N'} | "
                f"Thumb: {'Y' if entry['has_thumb'] else 'N'}"
            )
        )

        # Load data into form
        data = self.active_planets_data.get(name, {})
        self._begin_dirty_suspension()
        try:
            self._set_entry(self.planet_editor["name"], name)
            self._set_entry(
                self.planet_editor["pop"], data.get("Population", "1000000")
            )
            self._set_entry(
                self.planet_editor["desc"],
                data.get("Description", f"{name} is now open for trade and expansion."),
            )
            self._set_entry(
                self.planet_editor["vendor"],
                data.get("Vendor", "Independent Market Authority"),
            )
            self._set_entry(
                self.planet_editor["trade"],
                data.get("Trade Center", "Central Exchange"),
            )
            self._set_entry(
                self.planet_editor["defenders"], data.get("Defenders", "1000")
            )
            self._set_entry(self.planet_editor["shields"], data.get("Shields", "3000"))
            self._set_entry(self.planet_editor["bank"], data.get("Bank", "Off"))
            self._set_entry(
                self.planet_editor["items"],
                data.get("Items", self._generate_default_items_string()),
            )
        finally:
            self._end_dirty_suspension()

    def _set_entry(self, entry_widget, value):
        """Set entry widget value."""
        if isinstance(entry_widget, dict) and entry_widget.get("kind") == "bool":
            v = str(value).strip().lower()
            entry_widget["var"].set(v in ("1", "true", "yes", "on"))
            return
        entry_widget.delete(0, "end")
        entry_widget.insert(0, str(value))

    def _build_planet_payload(self):
        """Build planet data from form."""
        name = self.planet_editor["name"].get().strip()
        bank_widget = self.planet_editor["bank"]
        bank_value = "Off"
        if isinstance(bank_widget, dict) and bank_widget.get("kind") == "bool":
            bank_value = "On" if bool(bank_widget["var"].get()) else "Off"
        else:
            bank_value = self.planet_editor["bank"].get().strip() or "Off"
        return {
            "Name": name,
            "Population": self.planet_editor["pop"].get().strip() or "1000000",
            "Description": self.planet_editor["desc"].get().strip()
            or f"{name} is open for trade.",
            "Vendor": self.planet_editor["vendor"].get().strip()
            or "Independent Market Authority",
            "Trade Center": self.planet_editor["trade"].get().strip()
            or "Central Exchange",
            "Defenders": self.planet_editor["defenders"].get().strip() or "1000",
            "Shields": self.planet_editor["shields"].get().strip() or "3000",
            "Bank": bank_value,
            "Items": self.planet_editor["items"].get().strip()
            or self._generate_default_items_string(),
        }

    def _validate_planet_payload(self, payload):
        """Validate planet data."""
        if not payload.get("Name"):
            return False, "Planet name is required."

        try:
            int(payload["Population"].replace(",", ""))
            int(payload["Defenders"].replace(",", ""))
            int(payload["Shields"].replace(",", ""))
        except ValueError:
            return False, "Population/Defenders/Shields must be numeric."

        # Validate items format
        base_items = self._load_base_items_for_planet()
        try:
            if payload.get("Items"):
                for pair in payload["Items"].split(";"):
                    if not pair.strip():
                        continue
                    if "," not in pair:
                        raise ValueError(f"Invalid item pair: {pair}")
                    item_name, price = pair.split(",", 1)
                    item_name = item_name.strip()
                    if not item_name or item_name not in base_items:
                        raise ValueError(f"Unknown item: {item_name}")
                    int(price.strip())
        except Exception as ex:
            return False, str(ex)

        return True, ""

    def activate_planet(self):
        """Activate/add a planet to planets.txt."""
        payload = self._build_planet_payload()
        name = payload["Name"]

        if not name:
            messagebox.showerror("Error", "Planet name is required.")
            return

        if name in self.active_planets_data:
            messagebox.showinfo("Info", f"{name} is already active.")
            return

        # Check for images
        bg_path = os.path.join(self.bg_dir, f"{name}.png")
        thumb_path = os.path.join(self.thumb_dir, f"sm_{name}.png")
        if not (os.path.exists(bg_path) and os.path.exists(thumb_path)):
            messagebox.showerror(
                "Missing Images",
                "Planet requires BOTH background and thumbnail images before activation.",
            )
            return

        # Validate
        ok, err = self._validate_planet_payload(payload)
        if not ok:
            messagebox.showerror("Invalid Planet Data", err)
            return

        # Append to planets.txt
        block = (
            f"Name: {payload['Name']}\n"
            f"Population: {payload['Population']}\n"
            f"Description: {payload['Description']}\n"
            f"Vendor: {payload['Vendor']}\n"
            f"Trade Center: {payload['Trade Center']}\n"
            f"Defenders: {payload['Defenders']}\n"
            f"Shields: {payload['Shields']}\n"
            f"Bank: {payload['Bank']}\n"
            f"Items: {payload['Items']}"
        )

        existing = self._read_catalog_text(self.planets_path).strip()

        out = f"{existing}\n\n{block}" if existing else block
        self._write_catalog_text(self.planets_path, out + "\n")

        messagebox.showinfo("Planet Activated", f"{name} is now active and playable!")
        self.load_planets()  # Reload
        self.refresh_planet_catalog()
        self._set_section_dirty("planets", False)
        self.select_planet_from_catalog(
            name,
            {"status": "ACTIVE", "has_data": True, "has_bg": True, "has_thumb": True},
        )

    def _build_default_planet_payload_for_name(self, name):
        clean_name = str(name or "").strip()
        return {
            "Name": clean_name,
            "Population": "1000000",
            "Description": f"{clean_name} is now open for trade and expansion.",
            "Vendor": "Independent Market Authority",
            "Trade Center": "Central Exchange",
            "Defenders": "1000",
            "Shields": "3000",
            "Bank": "Off",
            "Items": self._generate_default_items_string(),
        }

    def activate_all_ready_planets(self):
        if not hasattr(self, "planet_catalog") or not self.planet_catalog:
            self.refresh_planet_catalog()

        ready_entries = [c for c in self.planet_catalog if c.get("status") == "READY"]
        if not ready_entries:
            messagebox.showinfo(
                "No READY Planets", "There are no READY planets to activate."
            )
            return

        if not messagebox.askyesno(
            "Activate All READY",
            f"Activate all READY planets now?\nCount: {len(ready_entries)}",
        ):
            return

        existing_blocks = []
        active_names = set()
        raw_planets = self._read_catalog_text(self.planets_path)
        existing_blocks = [b.strip() for b in raw_planets.split("\n\n") if b.strip()]
        for block in existing_blocks:
            for line in [ln.strip() for ln in block.split("\n") if ln.strip()]:
                if line.startswith("Name:"):
                    active_names.add(line.split(":", 1)[1].strip())
                    break

        created = 0
        for entry in ready_entries:
            name = str(entry.get("name", "")).strip()
            if not name or name in active_names:
                continue
            payload = self._build_default_planet_payload_for_name(name)
            ok, err = self._validate_planet_payload(payload)
            if not ok:
                print(f"[CONFIG] Skipping '{name}' during bulk activation: {err}")
                continue
            block = (
                f"Name: {payload['Name']}\n"
                f"Population: {payload['Population']}\n"
                f"Description: {payload['Description']}\n"
                f"Vendor: {payload['Vendor']}\n"
                f"Trade Center: {payload['Trade Center']}\n"
                f"Defenders: {payload['Defenders']}\n"
                f"Shields: {payload['Shields']}\n"
                f"Bank: {payload['Bank']}\n"
                f"Items: {payload['Items']}"
            )
            existing_blocks.append(block)
            active_names.add(name)
            created += 1

        if created == 0:
            messagebox.showinfo("No Changes", "No READY planets were activated.")
            return

        self._write_catalog_text(self.planets_path, "\n\n".join(existing_blocks) + "\n")

        self.load_planets()
        self.refresh_planet_catalog()
        self._set_section_dirty("planets", False)
        messagebox.showinfo(
            "Bulk Activation Complete", f"Activated {created} READY planet(s)."
        )

    def save_planet_changes(self):
        """Save changes to an existing planet."""
        payload = self._build_planet_payload()
        ok, err, synced = self._persist_planet_payload(payload, require_active=True)
        if not ok:
            if err.startswith("This planet is not active"):
                messagebox.showerror("Planet Not Active", err)
            elif err == "No planets file found.":
                messagebox.showerror("Save Failed", err)
            else:
                messagebox.showerror("Invalid Planet Data", err)
            return

        messagebox.showinfo(
            "Planet Saved", f"Saved {payload['Name']}. Synced {synced} save file(s)."
        )
        self._set_section_dirty("planets", False)

    def deactivate_planet(self):
        """Remove a planet from planets.txt."""
        if not self.selected_planet_name:
            messagebox.showinfo("No Selection", "Select a planet first.")
            return

        name = self.selected_planet_name

        if name not in self.active_planets_data:
            messagebox.showinfo("Not Active", f"{name} is not currently active.")
            return

        if not messagebox.askyesno(
            "Confirm", f"Deactivate {name}? It will be removed from planets.txt."
        ):
            return

        # Read and filter
        raw_blocks = [
            b.strip()
            for b in self._read_catalog_text(self.planets_path).split("\n\n")
            if b.strip()
        ]

        blocks = []
        for block in raw_blocks:
            vals = {}
            for ln in [ln.strip() for ln in block.split("\n") if ln.strip()]:
                if ":" not in ln:
                    continue
                k, v = ln.split(":", 1)
                vals[k.strip()] = v.strip()

            # Skip the one we're deactivating
            if vals.get("Name") != name and vals.get("Name"):
                blocks.append(vals)

        # Write back
        ordered_keys = [
            "Name",
            "Population",
            "Description",
            "Vendor",
            "Trade Center",
            "Defenders",
            "Shields",
            "Bank",
            "Items",
        ]

        rendered = []
        for vals in blocks:
            lines = []
            for key in ordered_keys:
                lines.append(f"{key}: {vals.get(key, '')}")
            rendered.append("\n".join(lines).strip())

        self._write_catalog_text(
            self.planets_path, "\n\n".join([r for r in rendered if r]) + "\n"
        )

        messagebox.showinfo("Planet Deactivated", f"{name} has been deactivated.")
        self.load_planets()
        self.refresh_planet_catalog()
        self._set_section_dirty("planets", False)

    def link_and_add_planet(self):
        """Link existing images to create a new planet."""
        new_name = self.link_new_name.get().strip()
        src_bg = self.link_bg_path.get().strip()
        src_thumb = self.link_thumb_path.get().strip()

        if not new_name:
            messagebox.showerror("Error", "New Planet Name is required.")
            return

        if new_name.startswith("UNUSED_"):
            messagebox.showerror("Error", "Planet name cannot start with UNUSED_.")
            return

        if not src_bg or not src_thumb:
            messagebox.showerror(
                "Missing Images",
                "Select both a source background and source thumbnail image.",
            )
            return

        src_bg = os.path.abspath(src_bg)
        src_thumb = os.path.abspath(src_thumb)

        if not self._is_path_within(src_bg, self.bg_dir):
            messagebox.showerror(
                "Invalid Background",
                "Background source must be under server/assets/planets/backgrounds.",
            )
            return

        if not self._is_path_within(src_thumb, self.thumb_dir):
            messagebox.showerror(
                "Invalid Thumbnail",
                "Thumbnail source must be under server/assets/planets/thumbnails.",
            )
            return

        # Check source images exist
        if not (os.path.exists(src_bg) and os.path.exists(src_thumb)):
            messagebox.showerror(
                "Missing Source", "Selected source image file(s) not found."
            )
            return

        # Copy images
        dst_bg = os.path.join(self.bg_dir, f"{new_name}.png")
        dst_thumb = os.path.join(self.thumb_dir, f"sm_{new_name}.png")

        if not os.path.exists(dst_bg):
            shutil.copyfile(src_bg, dst_bg)
        if not os.path.exists(dst_thumb):
            shutil.copyfile(src_thumb, dst_thumb)

        # Set up form with new planet
        self._set_entry(self.planet_editor["name"], new_name)
        self._set_entry(self.planet_editor["pop"], "1000000")
        self._set_entry(
            self.planet_editor["desc"], f"{new_name} is a newly charted world."
        )
        self._set_entry(self.planet_editor["vendor"], "Independent Market Authority")
        self._set_entry(self.planet_editor["trade"], "Central Exchange")
        self._set_entry(self.planet_editor["defenders"], "1000")
        self._set_entry(self.planet_editor["shields"], "3000")
        self._set_entry(self.planet_editor["bank"], "Off")
        self._set_entry(
            self.planet_editor["items"], self._generate_default_items_string()
        )

        self.refresh_planet_catalog()
        self._set_section_dirty("planets")
        messagebox.showinfo(
            "Images Linked",
            f"Images linked. Now click 'Activate / Add Planet' to add {new_name}.",
        )

    def rebuild_map_preview(self):
        """Rebuild the travel map coordinate preview."""
        try:
            from planets import get_planet_map_coordinates
        except ImportError:
            self.map_preview_box.delete("1.0", "end")
            self.map_preview_box.insert("1.0", "ERROR: planets.py module not found.\n")
            return

        active_names = sorted(self.active_planets_data.keys())

        # Include pending planet from form
        pending_name = self.planet_editor["name"].get().strip()
        pending_note = ""
        if pending_name and pending_name not in active_names:
            active_names.append(pending_name)
            active_names.sort()
            pending_note = f"\nPENDING: {pending_name} (not yet activated)"

        if not active_names:
            self.map_preview_box.delete("1.0", "end")
            self.map_preview_box.insert("1.0", "No planets for map preview.\n")
            return

        lines = [
            "TRAVEL MAP COORDINATE PREVIEW",
            "Deterministic coordinates (x, y) by planet name:",
            "",
        ]

        coord_to_names = {}
        for name in active_names:
            x, y = get_planet_map_coordinates(name)
            coord_to_names.setdefault((x, y), []).append(name)
            lines.append(f"- {name}: ({x}, {y})")

        # Check for collisions
        collisions = [
            (coord, names) for coord, names in coord_to_names.items() if len(names) > 1
        ]
        if collisions:
            lines.append("")
            lines.append("WARNING: Coordinate collisions detected:")
            for (x, y), names in collisions:
                lines.append(f"  ({x}, {y}) -> {', '.join(sorted(names))}")
        else:
            lines.append("")
            lines.append("No collisions detected.")

        if pending_note:
            lines.append(pending_note)

        self.map_preview_box.delete("1.0", "end")
        self.map_preview_box.insert("1.0", "\n".join(lines))

    def _sync_planet_state_to_saves(self, planet_name, payload):
        """Sync planet defenders/shields to all save files."""
        if not os.path.isdir(self.saves_dir):
            return 0
        if getattr(self, "store", None) is None:
            return 0

        # Build name -> id mapping from planets.txt order (or explicit Planet ID if present).
        planet_id_by_name = {}
        try:
            blocks = [
                b.strip()
                for b in self._read_catalog_text(self.planets_path).split("\n\n")
                if b.strip()
            ]
            if blocks:
                next_id = 1
                for block in blocks:
                    name_val = ""
                    explicit_id = None
                    for raw_line in block.split("\n"):
                        line = str(raw_line or "").strip()
                        if not line or ":" not in line:
                            continue
                        key, value = line.split(":", 1)
                        key = key.strip().lower()
                        value = value.strip()
                        if key == "name":
                            name_val = value
                        elif key == "planet id" and value.isdigit():
                            explicit_id = int(value)
                    if not name_val:
                        continue
                    pid = int(explicit_id if explicit_id is not None else next_id)
                    planet_id_by_name[name_val.strip().lower()] = pid
                    next_id = max(next_id + 1, pid + 1)
        except Exception:
            planet_id_by_name = {}

        candidate_id = planet_id_by_name.get(str(planet_name or "").strip().lower())

        defenders = int(payload["Defenders"].replace(",", ""))
        shields = int(payload["Shields"].replace(",", ""))

        try:
            universe_payload = self.store.get_kv("shared", "universe_planets", default=None)
            if not isinstance(universe_payload, dict):
                return 0
            planet_states = universe_payload.get("planet_states")
            if not isinstance(planet_states, dict):
                return 0

            state_key = str(planet_name)
            if candidate_id is not None and str(candidate_id) in planet_states:
                state_key = str(candidate_id)
            if state_key not in planet_states:
                return 0

            state = dict(planet_states.get(state_key) or {})
            state["defenders"] = max(0, defenders)
            state["shields"] = max(0, shields)
            state["max_shields"] = max(1, shields)
            planet_states[state_key] = state
            universe_payload["planet_states"] = planet_states
            self.store.set_kv("shared", "universe_planets", universe_payload)
            return 1
        except Exception:
            return 0

    def on_closing(self):
        c = self._has_unsaved_changes()
        if c and not messagebox.askyesno("Unsaved", "Exit without saving?"):
            return
        self.quit()
        self.destroy()


if __name__ == "__main__":
    app = ConfigApp()
    app.mainloop()
