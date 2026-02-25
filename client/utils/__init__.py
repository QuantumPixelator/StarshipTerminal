"""
Utility package for Starship Terminal client.
Contains server configuration helpers and drawing utilities.
"""
from .server_config import (
    load_servers,
    save_servers,
    get_server_username,
    save_server_username,
    _get_configured_server_port,
    _coerce_server_port,
    _extract_host_port_from_url,
    _build_server_url,
    _normalize_server_entry,
)
from .drawing import (
    _draw_centered_rectangle_filled,
    _draw_centered_rectangle_outline,
)

__all__ = [
    "load_servers",
    "save_servers",
    "get_server_username",
    "save_server_username",
    "_get_configured_server_port",
    "_coerce_server_port",
    "_extract_host_port_from_url",
    "_build_server_url",
    "_normalize_server_entry",
    "_draw_centered_rectangle_filled",
    "_draw_centered_rectangle_outline",
]
