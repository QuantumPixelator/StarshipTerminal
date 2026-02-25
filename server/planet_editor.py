import os
import json
import shutil
import tkinter as tk
from tkinter import messagebox

from config import ctk
from planets import get_planet_map_coordinates


class PlanetEditorApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Starship Terminal - Planet Editor")
        self.geometry("1280x820")

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.planets_path = os.path.join("assets", "texts", "planets.txt")
        self.items_path = os.path.join("assets", "texts", "items.txt")
        self.saves_dir = "saves"
        self.bg_dir = os.path.join("assets", "planets", "backgrounds")
        self.thumb_dir = os.path.join("assets", "planets", "thumbnails")

        self.base_items = self._load_base_items()
        self.active_planets = self._load_active_planets()
        self.catalog = []
        self.selected_name = None

        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_ui()
        self._refresh_catalog()

    def _using_fallback(self):
        return bool(getattr(ctk, "_is_fallback", False))

    def _create_scrollable_area(self, parent, width=None):
        if not self._using_fallback():
            scroll = (
                ctk.CTkScrollableFrame(parent, width=width)
                if width
                else ctk.CTkScrollableFrame(parent)
            )
            return scroll, scroll

        container = ctk.CTkFrame(parent)
        canvas = tk.Canvas(container, highlightthickness=0, borderwidth=0)
        scrollbar = tk.Scrollbar(container, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scrollbar.set)

        inner = ctk.CTkFrame(canvas)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def _sync_scroll(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window_id, width=canvas.winfo_width())

        inner.bind("<Configure>", _sync_scroll)
        canvas.bind("<Configure>", _sync_scroll)

        def _wheel(event):
            delta = event.delta
            if delta == 0:
                return
            canvas.yview_scroll(int(-1 * (delta / 120)), "units")

        canvas.bind_all("<MouseWheel>", _wheel)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return container, inner

    def _build_ui(self):
        self.left = ctk.CTkFrame(self, width=360)
        self.left.grid(row=0, column=0, sticky="nsew", padx=(12, 6), pady=12)
        self.left.grid_rowconfigure(2, weight=1)

        ctk.CTkLabel(
            self.left,
            text="PLANET CATALOG",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 6))

        self.summary_lbl = ctk.CTkLabel(self.left, text="", font=ctk.CTkFont(size=12))
        self.summary_lbl.grid(row=1, column=0, sticky="w", padx=14, pady=(0, 8))

        self.list_scroll_host, self.list_scroll = self._create_scrollable_area(
            self.left, width=330
        )
        self.list_scroll_host.grid(
            row=2, column=0, sticky="nsew", padx=10, pady=(0, 10)
        )

        ctk.CTkButton(
            self.left,
            text="Refresh Catalog",
            command=self._refresh_catalog,
            fg_color="#3498db",
        ).grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))

        self.right_host, self.right = self._create_scrollable_area(self)
        self.right_host.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)

        ctk.CTkLabel(
            self.right,
            text="Planet Activation & Linking",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 4))

        ctk.CTkLabel(
            self.right,
            text="Only planets with BOTH background and thumbnail images can be activated.",
            font=ctk.CTkFont(size=12),
        ).pack(anchor="w", padx=12, pady=(0, 12))

        self.selected_info = ctk.CTkLabel(
            self.right, text="Select a planet from the catalog."
        )
        self.selected_info.pack(anchor="w", padx=12, pady=(0, 10))

        self.form = ctk.CTkFrame(self.right)
        self.form.pack(fill="x", padx=10, pady=8)

        self.f_name = self._row_entry(self.form, "Planet Name")
        self.f_population = self._row_entry(self.form, "Population")
        self.f_description = self._row_entry(self.form, "Description")
        self.f_vendor = self._row_entry(self.form, "Vendor")
        self.f_trade = self._row_entry(self.form, "Trade Center")
        self.f_defenders = self._row_entry(self.form, "Defenders")
        self.f_shields = self._row_entry(self.form, "Shields")
        self.f_bank = self._row_entry(self.form, "Bank (True/False)")
        self.f_items = self._row_entry(self.form, "Items (Name,Price;...)")

        self.activate_btn = ctk.CTkButton(
            self.right,
            text="Activate / Add Planet",
            fg_color="#2ecc71",
            hover_color="#27ae60",
            command=self._activate_selected,
        )
        self.activate_btn.pack(anchor="w", padx=12, pady=(6, 14))

        self.save_btn = ctk.CTkButton(
            self.right,
            text="Save Planet Changes",
            fg_color="#1f6aa5",
            hover_color="#144870",
            command=self._save_selected,
        )
        self.save_btn.pack(anchor="w", padx=12, pady=(0, 14))

        self.link_frame = ctk.CTkFrame(self.right)
        self.link_frame.pack(fill="x", padx=10, pady=(8, 14))

        ctk.CTkLabel(
            self.link_frame,
            text="Create New Planet by Linking Existing Images",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            self.link_frame,
            text="Example: New Name = Cryostar, Source Image Stem = UNUSED_Cryostar",
            font=ctk.CTkFont(size=11),
        ).pack(anchor="w", padx=12, pady=(0, 8))

        self.new_name = self._row_entry(self.link_frame, "New Planet Name")
        self.src_stem = self._row_entry(self.link_frame, "Source Image Stem")

        ctk.CTkButton(
            self.link_frame,
            text="Link Images + Add Planet",
            fg_color="#9b59b6",
            hover_color="#8e44ad",
            command=self._link_and_add,
        ).pack(anchor="w", padx=12, pady=(6, 12))

        self.map_frame = ctk.CTkFrame(self.right)
        self.map_frame.pack(fill="x", padx=10, pady=(8, 14))

        ctk.CTkLabel(
            self.map_frame,
            text="Travel Map Preview / Rebuild",
            font=ctk.CTkFont(size=16, weight="bold"),
        ).pack(anchor="w", padx=12, pady=(12, 6))

        ctk.CTkLabel(
            self.map_frame,
            text=(
                "Preview deterministic travel coordinates before activation/removal. "
                "Positions are recalculated by name and stay stable across saves."
            ),
            font=ctk.CTkFont(size=11),
            wraplength=900,
            justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 8))

        btn_row = ctk.CTkFrame(self.map_frame, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="Rebuild Planet Map Preview",
            fg_color="#16a085",
            hover_color="#138d75",
            command=self._rebuild_map_preview,
        ).pack(side="left", padx=(0, 10))

        ctk.CTkButton(
            btn_row,
            text="Copy Selected Coord",
            fg_color="#34495e",
            hover_color="#2c3e50",
            command=self._copy_selected_coord,
        ).pack(side="left")

        self.map_preview_box = ctk.CTkTextbox(self.map_frame, width=980, height=220)
        self.map_preview_box.pack(fill="x", padx=12, pady=(0, 12))
        self.map_preview_box.insert(
            "1.0",
            "Press 'Rebuild Planet Map Preview' to list active and pending coordinates.\n",
        )

        self.bind("<Control-s>", lambda _event: self._save_selected())

    def _row_entry(self, parent, label):
        row = ctk.CTkFrame(parent, fg_color="transparent")
        row.pack(fill="x", padx=12, pady=4)
        row.grid_columnconfigure(0, weight=0)
        row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(row, text=label, width=220, anchor="w").grid(
            row=0, column=0, sticky="w", padx=(0, 10)
        )

        entry = ctk.CTkEntry(row, width=520)
        entry.grid(row=0, column=1, sticky="ew")
        return entry

    def _load_base_items(self):
        out = {}
        if not os.path.exists(self.items_path):
            return out
        with open(self.items_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or "," not in line:
                    continue
                name, price = line.split(",", 1)
                name = name.strip()
                price = price.strip()
                if not name:
                    continue
                try:
                    out[name] = int(price)
                except ValueError:
                    continue
        return out

    def _load_active_planets(self):
        planets = {}
        if not os.path.exists(self.planets_path):
            return planets

        with open(self.planets_path, "r", encoding="utf-8") as f:
            blocks = [b.strip() for b in f.read().split("\n\n") if b.strip()]

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
                planets[name] = vals
        return planets

    def _collect_bg_stems(self):
        if not os.path.exists(self.bg_dir):
            return set()
        return {
            os.path.splitext(name)[0]
            for name in os.listdir(self.bg_dir)
            if name.lower().endswith(".png")
        }

    def _collect_thumb_stems(self):
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

    def _status_of(self, name, has_data, has_bg, has_thumb):
        if name.startswith("UNUSED_"):
            return "UNUSED"
        if not has_bg or not has_thumb:
            return "UNUSED"
        if has_data:
            return "ACTIVE"
        return "READY"

    def _refresh_catalog(self):
        self.active_planets = self._load_active_planets()
        active_names = set(self.active_planets.keys())
        bg_names = self._collect_bg_stems()
        thumb_names = self._collect_thumb_stems()

        names = sorted(active_names | bg_names | thumb_names)
        self.catalog = []
        for name in names:
            has_data = name in active_names
            has_bg = name in bg_names
            has_thumb = name in thumb_names
            status = self._status_of(name, has_data, has_bg, has_thumb)
            self.catalog.append(
                {
                    "name": name,
                    "status": status,
                    "has_data": has_data,
                    "has_bg": has_bg,
                    "has_thumb": has_thumb,
                }
            )

        for w in self.list_scroll.winfo_children():
            w.destroy()

        order = {"ACTIVE": 0, "READY": 1, "UNUSED": 2}
        self.catalog.sort(key=lambda c: (order.get(c["status"], 9), c["name"]))

        active_count = sum(1 for c in self.catalog if c["status"] == "ACTIVE")
        ready_count = sum(1 for c in self.catalog if c["status"] == "READY")
        unused_count = sum(1 for c in self.catalog if c["status"] == "UNUSED")
        self.summary_lbl.configure(
            text=f"Active: {active_count}   Ready: {ready_count}   Unused: {unused_count}"
        )

        for entry in self.catalog:
            name = entry["name"]
            status = entry["status"]
            color = (
                "#2ecc71"
                if status == "ACTIVE"
                else ("#f1c40f" if status == "READY" else "#7f8c8d")
            )
            text = f"[{status}] {name}"
            ctk.CTkButton(
                self.list_scroll,
                text=text,
                fg_color=color,
                hover_color=color,
                anchor="w",
                command=lambda n=name: self._select_planet(n),
            ).pack(fill="x", padx=4, pady=2)

    def _generate_default_items_string(self):
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
            if item in self.base_items:
                pairs.append(f"{item},{self.base_items[item]}")
        if len(pairs) < 6:
            for name, price in self.base_items.items():
                pair = f"{name},{price}"
                if pair not in pairs:
                    pairs.append(pair)
                if len(pairs) >= 8:
                    break
        return ";".join(pairs[:8])

    def _select_planet(self, name):
        self.selected_name = name
        entry = next((c for c in self.catalog if c["name"] == name), None)
        if not entry:
            return

        self.selected_info.configure(
            text=(
                f"Selected: {name} | Status: {entry['status']} | "
                f"Data: {'Y' if entry['has_data'] else 'N'} | "
                f"BG: {'Y' if entry['has_bg'] else 'N'} | "
                f"Thumb: {'Y' if entry['has_thumb'] else 'N'}"
            )
        )

        data = self.active_planets.get(name, {})
        self._set_entry(self.f_name, name)
        self._set_entry(self.f_population, data.get("Population", "1000000"))
        self._set_entry(
            self.f_description,
            data.get("Description", f"{name} is now open for trade and expansion."),
        )
        self._set_entry(
            self.f_vendor, data.get("Vendor", "Independent Market Authority")
        )
        self._set_entry(self.f_trade, data.get("Trade Center", "Central Exchange"))
        self._set_entry(self.f_defenders, data.get("Defenders", "1000"))
        self._set_entry(self.f_shields, data.get("Shields", "3000"))
        self._set_entry(self.f_bank, data.get("Bank", "False"))
        self._set_entry(
            self.f_items, data.get("Items", self._generate_default_items_string())
        )

    def _set_entry(self, entry, value):
        entry.delete(0, "end")
        entry.insert(0, str(value))

    def _build_map_preview_text(self):
        active_names = sorted(self.active_planets.keys())

        pending_name = self.f_name.get().strip()
        pending_note = ""
        if pending_name and pending_name not in active_names:
            active_names.append(pending_name)
            active_names.sort()
            pending_note = (
                f"\nPENDING: {pending_name} (previewed but not yet activated)."
            )

        if not active_names:
            return "No planets found for mapping preview."

        lines = [
            "REBUILT TRAVEL MAP PREVIEW",
            "Name-based deterministic coordinates (x,y):",
            "",
        ]

        coord_to_names = {}
        for name in active_names:
            x, y = get_planet_map_coordinates(name)
            coord_to_names.setdefault((x, y), []).append(name)
            lines.append(f"- {name}: ({x}, {y})")

        collisions = [
            (coord, names) for coord, names in coord_to_names.items() if len(names) > 1
        ]
        if collisions:
            lines.append("")
            lines.append("WARN: Coordinate collisions detected:")
            for (x, y), names in collisions:
                lines.append(f"  ({x}, {y}) -> {', '.join(sorted(names))}")
        else:
            lines.append("")
            lines.append("No coordinate collisions detected.")

        if pending_note:
            lines.append(pending_note)

        return "\n".join(lines)

    def _rebuild_map_preview(self):
        self.active_planets = self._load_active_planets()
        preview_text = self._build_map_preview_text()
        self.map_preview_box.delete("1.0", "end")
        self.map_preview_box.insert("1.0", preview_text)

    def _copy_selected_coord(self):
        name = self.f_name.get().strip() or self.selected_name
        if not name:
            messagebox.showinfo("No Planet", "Select or type a planet name first.")
            return
        x, y = get_planet_map_coordinates(name)
        coord_text = f"{name}: ({x}, {y})"
        self.clipboard_clear()
        self.clipboard_append(coord_text)
        messagebox.showinfo("Copied", f"Copied coordinate: {coord_text}")

    def _append_planet_block(self, payload):
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

        existing = ""
        if os.path.exists(self.planets_path):
            with open(self.planets_path, "r", encoding="utf-8") as f:
                existing = f.read().strip()

        out = f"{existing}\n\n{block}" if existing else block
        with open(self.planets_path, "w", encoding="utf-8") as f:
            f.write(out + "\n")

    def _read_planet_blocks(self):
        if not os.path.exists(self.planets_path):
            return []

        with open(self.planets_path, "r", encoding="utf-8") as f:
            raw_blocks = [b.strip() for b in f.read().split("\n\n") if b.strip()]

        blocks = []
        for block in raw_blocks:
            vals = {}
            for ln in [ln.strip() for ln in block.split("\n") if ln.strip()]:
                if ":" not in ln:
                    continue
                k, v = ln.split(":", 1)
                vals[k.strip()] = v.strip()
            if vals.get("Name"):
                blocks.append(vals)
        return blocks

    def _write_planet_blocks(self, blocks):
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
            for key in vals.keys():
                if key in ordered_keys:
                    continue
                lines.append(f"{key}: {vals.get(key, '')}")
            rendered.append("\n".join(lines).strip())

        with open(self.planets_path, "w", encoding="utf-8") as f:
            f.write("\n\n".join([r for r in rendered if r]) + "\n")

    def _build_payload_from_form(self):
        name = self.f_name.get().strip()
        payload = {
            "Name": name,
            "Population": self.f_population.get().strip() or "1000000",
            "Description": self.f_description.get().strip()
            or f"{name} is open for trade.",
            "Vendor": self.f_vendor.get().strip() or "Independent Market Authority",
            "Trade Center": self.f_trade.get().strip() or "Central Exchange",
            "Defenders": self.f_defenders.get().strip() or "1000",
            "Shields": self.f_shields.get().strip() or "3000",
            "Bank": self.f_bank.get().strip() or "False",
            "Items": self.f_items.get().strip() or self._generate_default_items_string(),
        }
        return payload

    def _validate_payload(self, payload):
        if not payload.get("Name"):
            return False, "Planet name is required."

        try:
            int(payload["Population"].replace(",", ""))
            int(payload["Defenders"].replace(",", ""))
            int(payload["Shields"].replace(",", ""))
        except ValueError:
            return False, "Population/Defenders/Shields must be numeric."

        try:
            if payload.get("Items"):
                for pair in payload["Items"].split(";"):
                    if not pair.strip():
                        continue
                    if "," not in pair:
                        raise ValueError(f"Invalid item pair: {pair}")
                    item_name, price = pair.split(",", 1)
                    item_name = item_name.strip()
                    if not item_name or item_name not in self.base_items:
                        raise ValueError(f"Unknown item: {item_name}")
                    int(price.strip())
        except Exception as ex:
            return False, str(ex)

        return True, ""

    def _sync_planet_state_to_saves(self, planet_name, payload):
        if not os.path.isdir(self.saves_dir):
            return 0

        defenders = int(payload["Defenders"].replace(",", ""))
        shields = int(payload["Shields"].replace(",", ""))
        synced_count = 0

        for file_name in os.listdir(self.saves_dir):
            if not file_name.lower().endswith(".json"):
                continue
            save_path = os.path.join(self.saves_dir, file_name)
            try:
                with open(save_path, "r", encoding="utf-8") as fh:
                    save_data = json.load(fh)
            except Exception:
                continue

            planet_states = save_data.get("planet_states")
            if not isinstance(planet_states, dict):
                continue
            if planet_name not in planet_states:
                continue

            state = planet_states.get(planet_name, {})
            state["defenders"] = max(0, defenders)
            state["shields"] = max(0, shields)
            state["max_shields"] = max(1, shields)
            planet_states[planet_name] = state

            try:
                with open(save_path, "w", encoding="utf-8") as fh:
                    json.dump(save_data, fh, indent=4)
                synced_count += 1
            except Exception:
                continue

        return synced_count

    def _save_selected(self):
        payload = self._build_payload_from_form()
        ok, err = self._validate_payload(payload)
        if not ok:
            messagebox.showerror("Invalid Planet Data", err)
            return

        blocks = self._read_planet_blocks()
        if not blocks:
            messagebox.showerror("Save Failed", "No planets file data found to update.")
            return

        updated = False
        for block in blocks:
            if str(block.get("Name", "")).strip() == payload["Name"]:
                block.update(payload)
                updated = True
                break

        if not updated:
            messagebox.showerror(
                "Planet Not Active",
                "This planet is not active in planets.txt yet. Use 'Activate / Add Planet' first.",
            )
            return

        self._write_planet_blocks(blocks)
        synced = self._sync_planet_state_to_saves(payload["Name"], payload)
        self._refresh_catalog()
        self._select_planet(payload["Name"])
        self._rebuild_map_preview()
        messagebox.showinfo(
            "Planet Saved",
            f"Saved updates for {payload['Name']} to planets.txt. Synced {synced} save file(s).",
        )

    def _activate_selected(self):
        payload = self._build_payload_from_form()
        name = payload["Name"]

        if not name:
            messagebox.showerror("Error", "Planet name is required.")
            return
        if name in self.active_planets:
            messagebox.showinfo("Info", f"{name} is already active.")
            return

        bg_path = os.path.join(self.bg_dir, f"{name}.png")
        thumb_path = os.path.join(self.thumb_dir, f"sm_{name}.png")
        if not (os.path.exists(bg_path) and os.path.exists(thumb_path)):
            messagebox.showerror(
                "Missing Images",
                "Planet requires BOTH background and thumbnail images before activation.",
            )
            return

        ok, err = self._validate_payload(payload)
        if not ok:
            messagebox.showerror("Invalid Planet Data", err)
            return

        self._append_planet_block(payload)
        messagebox.showinfo(
            "Planet Activated",
            f"{name} is now active and fully playable (market, combat, contracts, reputation systems).",
        )
        self._refresh_catalog()
        self._select_planet(name)
        self._rebuild_map_preview()

    def _link_and_add(self):
        new_name = self.new_name.get().strip()
        src = self.src_stem.get().strip()

        if not new_name or not src:
            messagebox.showerror(
                "Error", "Both New Planet Name and Source Image Stem are required."
            )
            return

        if new_name.startswith("UNUSED_"):
            messagebox.showerror("Error", "New planet name cannot start with UNUSED_.")
            return

        src_bg = os.path.join(self.bg_dir, f"{src}.png")
        src_thumb = os.path.join(self.thumb_dir, f"sm_{src}.png")
        if not (os.path.exists(src_bg) and os.path.exists(src_thumb)):
            messagebox.showerror(
                "Missing Source Images",
                f"Could not find source images for stem '{src}'.",
            )
            return

        dst_bg = os.path.join(self.bg_dir, f"{new_name}.png")
        dst_thumb = os.path.join(self.thumb_dir, f"sm_{new_name}.png")

        if not os.path.exists(dst_bg):
            shutil.copyfile(src_bg, dst_bg)
        if not os.path.exists(dst_thumb):
            shutil.copyfile(src_thumb, dst_thumb)

        self._set_entry(self.f_name, new_name)
        self._set_entry(self.f_population, "1000000")
        self._set_entry(
            self.f_description,
            f"{new_name} is a newly charted world with expanding trade lanes.",
        )
        self._set_entry(self.f_vendor, "Independent Market Authority")
        self._set_entry(self.f_trade, "Central Exchange")
        self._set_entry(self.f_defenders, "1000")
        self._set_entry(self.f_shields, "3000")
        self._set_entry(self.f_bank, "False")
        self._set_entry(self.f_items, self._generate_default_items_string())

        self._activate_selected()


if __name__ == "__main__":
    app = PlanetEditorApp()
    app.mainloop()
