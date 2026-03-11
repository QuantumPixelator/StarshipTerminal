"""
Starship Terminal - Multiplayer Client
Main entry point for networked gameplay.

Classes and utilities that were previously defined here have been extracted
into dedicated modules:
  - utils/server_config.py  : server URL helpers, load_servers, save_servers, ...
  - utils/drawing.py        : _draw_centered_rectangle_filled/outline
  - components/dialogs.py   : InputDialog, MessageBox
  - views/connection_view.py: ConnectionView
  - views/auth_view.py      : AuthenticationView, CharacterSelectView
"""

import arcade
import os
import sys
import warnings
from constants import SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE

try:
    from arcade.exceptions import PerformanceWarning
    warnings.filterwarnings("ignore", category=PerformanceWarning)
except Exception:
    pass

# --- Set working directory so relative paths (assets/, servers.json) work ----
os.chdir(os.path.dirname(os.path.abspath(__file__)))

# --- Modular imports ----------------------------------------------------------
from utils.server_config import (  # noqa: E402
    load_servers,
    save_servers,
    get_server_username,
    save_server_username,
    _get_configured_server_port,
    _coerce_server_port,
    _extract_host_port_from_url,
    _build_server_url,
    _normalize_server_entry,
    DEFAULT_SERVER_PORT,
    SERVERS_CONFIG,
)
from utils.drawing import (  # noqa: E402
    _draw_centered_rectangle_filled,
    _draw_centered_rectangle_outline,
)
from components.dialogs import InputDialog, MessageBox  # noqa: E402
from views.connection_view import ConnectionView  # noqa: E402
from views.auth_view import AuthenticationView, CharacterSelectView  # noqa: E402


# =============================================================================
# Entry point
# =============================================================================

def main():
    """Main entry point."""
    # Load custom fonts
    font_dir = "assets/fonts"
    if os.path.exists(font_dir):
        for font_file in os.listdir(font_dir):
            if font_file.endswith(".ttf"):
                try:
                    arcade.load_font(os.path.join(font_dir, font_file))
                except Exception:
                    pass

    # Create window
    window = arcade.Window(SCREEN_WIDTH, SCREEN_HEIGHT, SCREEN_TITLE, resizable=False)

    # Always start centered to avoid restoring invalid/off-screen positions.
    try:
        window.center_window()
    except Exception:
        pass

    try:
        window.set_mouse_visible(True)
    except Exception:
        pass

    # Show connection screen
    connection_view = ConnectionView()
    window.show_view(connection_view)

    # Run game
    try:
        arcade.run()
    finally:
        try:
            window.set_mouse_visible(True)
        except Exception:
            pass

        # Close network connection on exit
        if hasattr(window, "network"):
            try:
                window.network.close()
            except Exception:
                pass


if __name__ == "__main__":
    print("\n" + "=" * 70)
    print(" " * 20 + "STARSHIP TERMINAL CLIENT")
    print("=" * 70)
    print()
    print("  Connect to a multiplayer server or play offline!")
    print("  Server configuration: servers.json (name + host + port)")
    print()
    print("-" * 70 + "\n")

    main()
