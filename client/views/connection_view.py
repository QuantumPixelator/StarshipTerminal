"""
ConnectionView — server selection screen for Starship Terminal.
Allows players to add/edit/delete servers and connect or play offline.
"""

import arcade
from constants import SCREEN_WIDTH, SCREEN_HEIGHT
from components.dialogs import InputDialog
from utils.server_config import (
    load_servers,
    save_servers,
    _extract_host_port_from_url,
    _coerce_server_port,
    _build_server_url,
)


class ConnectionView(arcade.View):
    """Enhanced connection screen with server list management."""

    def __init__(self):
        super().__init__()
        self.servers_data = load_servers()
        self.selected_index = 0
        self.status = "Select a server or play offline"
        self.connecting = False
        self.input_dialog = None
        self.edit_mode = None  # "add_name", "add_host", "add_port", "edit_name", "edit_host", "edit_port"

    def on_show(self):
        arcade.set_background_color((10, 10, 15))

    def on_update(self, delta_time):
        if self.input_dialog and self.input_dialog.active:
            self.input_dialog.update(delta_time)

    def on_draw(self):
        self.clear()

        if self.input_dialog and self.input_dialog.active:
            self._draw_main_screen(dimmed=True)
            self.input_dialog.draw()
            return

        self._draw_main_screen(dimmed=False)

    def _draw_main_screen(self, dimmed=False):
        alpha = 80 if dimmed else 255

        arcade.draw_text(
            "STARSHIP TERMINAL",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 150,
            (0, 255, 100, alpha),
            54,
            anchor_x="center",
            font_name="Courier New",
            bold=True,
        )

        arcade.draw_text(
            "SERVER SELECTION",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT - 210,
            (100, 200, 255, alpha),
            20,
            anchor_x="center",
            font_name="Courier New",
        )

        y_pos = SCREEN_HEIGHT - 320
        servers = self.servers_data.get("servers", [])

        for i, server in enumerate(servers):
            selected = i == self.selected_index
            color = (0, 255, 100, alpha) if selected else (150, 150, 150, alpha)
            prefix = "► " if selected else "  "

            arcade.draw_text(
                f"{prefix}{server['name']}",
                SCREEN_WIDTH // 2 - 250,
                y_pos - i * 40,
                color,
                16,
                font_name="Courier New",
                bold=selected,
            )

            if selected:
                arcade.draw_text(
                    server["url"],
                    SCREEN_WIDTH // 2 + 100,
                    y_pos - i * 40,
                    (100, 150, 200, alpha),
                    14,
                    font_name="Courier New",
                )

        # Offline option at the end of the list
        offline_selected = self.selected_index == len(servers)
        offline_color = (255, 255, 100, alpha) if offline_selected else (150, 150, 150, alpha)
        offline_prefix = "► " if offline_selected else "  "
        arcade.draw_text(
            f"{offline_prefix}PLAY OFFLINE (Local Mode)",
            SCREEN_WIDTH // 2 - 250,
            y_pos - len(servers) * 40,
            offline_color,
            16,
            font_name="Courier New",
            bold=offline_selected,
        )

        if self.status:
            status_color = (255, 255, 100, alpha) if self.connecting else (180, 220, 200, alpha)
            arcade.draw_text(
                self.status,
                SCREEN_WIDTH // 2,
                200,
                status_color,
                14,
                anchor_x="center",
                font_name="Courier New",
            )

        if not self.connecting:
            instructions = [
                "[↑/↓] Select  |  [ENTER] Connect  |  [A] Add Server",
                "[D] Delete Server  |  [E] Edit Server  |  [Q] Quit",
            ]
            for i, inst in enumerate(instructions):
                arcade.draw_text(
                    inst,
                    SCREEN_WIDTH // 2,
                    100 - i * 25,
                    (100, 100, 100, alpha),
                    12,
                    anchor_x="center",
                    font_name="Courier New",
                )

    def on_key_press(self, key, modifiers):
        if self.input_dialog and self.input_dialog.active:
            result = self.input_dialog.on_key_press(key, modifiers)
            if result != "continue":
                self._handle_dialog_result(result)
            return

        if key == arcade.key.DOWN:
            max_index = len(self.servers_data.get("servers", []))
            self.selected_index = (self.selected_index + 1) % (max_index + 1)

        elif key == arcade.key.UP:
            max_index = len(self.servers_data.get("servers", []))
            self.selected_index = (self.selected_index - 1) % (max_index + 1)

        elif key == arcade.key.ENTER and not self.connecting:
            self._handle_connect()

        elif key == arcade.key.A:
            self._start_add_server()

        elif key == arcade.key.E:
            self._start_edit_server()

        elif key == arcade.key.D:
            self._start_delete_server()

        elif key == arcade.key.Q:
            arcade.exit()

    def on_text(self, text):
        if self.input_dialog and self.input_dialog.active:
            self.input_dialog.on_text(text)

    def _start_add_server(self):
        self.edit_mode = "add_name"
        self.input_dialog = InputDialog("Enter server name:", "My Server")

    def _start_edit_server(self):
        servers = self.servers_data.get("servers", [])
        if self.selected_index < len(servers):
            server = servers[self.selected_index]
            self.edit_mode = "edit_name"
            self.input_dialog = InputDialog("Edit server name:", server["name"])

    def _start_delete_server(self):
        servers = self.servers_data.get("servers", [])
        if self.selected_index < len(servers):
            servers.pop(self.selected_index)
            save_servers(self.servers_data)
            self.selected_index = min(self.selected_index, len(servers))
            self.status = "Server deleted"

    def _handle_dialog_result(self, result):
        if result is None:
            self.input_dialog = None
            self.edit_mode = None
            self.connecting = False
            return

        if self.edit_mode == "add_name":
            self.temp_name = result
            self.edit_mode = "add_host"
            self.input_dialog = InputDialog("Enter server host/IP:", "localhost")

        elif self.edit_mode == "add_host":
            host, inferred_port = _extract_host_port_from_url(result)
            self.temp_host = host
            self.temp_port = inferred_port
            self.edit_mode = "add_port"
            self.input_dialog = InputDialog(
                "Enter server port (1-65535):",
                str(self.temp_port),
                max_length=5,
            )

        elif self.edit_mode == "add_port":
            port_text = str(result or "").strip()
            if (not port_text.isdigit()) or len(port_text) > 5:
                self.status = "Port must be numbers only (max 5 digits)"
                self.input_dialog = InputDialog(
                    "Enter server port (1-65535):", str(self.temp_port), max_length=5
                )
                return
            port = _coerce_server_port(port_text, fallback=-1)
            if not (1 <= int(port) <= 65535):
                self.status = "Port must be between 1 and 65535"
                self.input_dialog = InputDialog(
                    "Enter server port (1-65535):", str(self.temp_port), max_length=5
                )
                return
            servers = self.servers_data.get("servers", [])
            servers.append(
                {
                    "name": self.temp_name,
                    "host": self.temp_host,
                    "port": int(port),
                    "url": _build_server_url(self.temp_host, port),
                }
            )
            save_servers(self.servers_data)
            self.status = "Server added!"
            self.input_dialog = None
            self.edit_mode = None

        elif self.edit_mode == "edit_name":
            self.temp_name = result
            servers = self.servers_data.get("servers", [])
            server = servers[self.selected_index]
            default_host = str(server.get("host") or _extract_host_port_from_url(server.get("url"))[0])
            self.edit_mode = "edit_host"
            self.input_dialog = InputDialog(
                "Edit server host/IP:", default_host, max_length=100
            )

        elif self.edit_mode == "edit_host":
            servers = self.servers_data.get("servers", [])
            current = servers[self.selected_index]
            host, inferred_port = _extract_host_port_from_url(result)
            self.temp_host = host
            self.temp_port = _coerce_server_port(
                current.get("port"), fallback=inferred_port
            )
            self.edit_mode = "edit_port"
            self.input_dialog = InputDialog(
                "Edit server port (1-65535):", str(self.temp_port), max_length=5
            )

        elif self.edit_mode == "edit_port":
            port_text = str(result or "").strip()
            if (not port_text.isdigit()) or len(port_text) > 5:
                self.status = "Port must be numbers only (max 5 digits)"
                self.input_dialog = InputDialog(
                    "Edit server port (1-65535):", str(self.temp_port), max_length=5
                )
                return
            port = _coerce_server_port(port_text, fallback=-1)
            if not (1 <= int(port) <= 65535):
                self.status = "Port must be between 1 and 65535"
                self.input_dialog = InputDialog(
                    "Edit server port (1-65535):", str(self.temp_port), max_length=5
                )
                return
            servers = self.servers_data.get("servers", [])
            existing_account = servers[self.selected_index].get("account")
            updated = {
                "name": self.temp_name,
                "host": self.temp_host,
                "port": int(port),
                "url": _build_server_url(self.temp_host, port),
            }
            if existing_account:
                updated["account"] = existing_account
            servers[self.selected_index] = updated
            save_servers(self.servers_data)
            self.status = "Server updated!"
            self.input_dialog = None
            self.edit_mode = None

    def _handle_connect(self):
        """Handle connection to selected server or offline mode."""
        servers = self.servers_data.get("servers", [])

        if self.selected_index == len(servers):
            from views.auth_view import AuthenticationView  # lazy
            auth_view = AuthenticationView(offline=True)
            self.window.show_view(auth_view)
            return

        server_url = servers[self.selected_index]["url"]
        from views.auth_view import AuthenticationView  # lazy
        auth_view = AuthenticationView(server_url=server_url, offline=False)
        self.window.show_view(auth_view)
