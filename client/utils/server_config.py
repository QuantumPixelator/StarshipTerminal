"""
Server configuration utilities for Starship Terminal.
Handles server URL management, port configuration, and servers.json I/O.
"""

import os
import json
from urllib.parse import urlparse

SERVERS_CONFIG = "servers.json"
DEFAULT_SERVER_PORT = 8765


def _get_configured_server_port():
    """Read the server port from the local game_config.json if present."""
    game_config_path = os.path.normpath(
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "server", "game_config.json")
    )
    try:
        with open(game_config_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
        settings = payload.get("settings", {}) if isinstance(payload, dict) else {}
        candidate = settings.get("server_port", DEFAULT_SERVER_PORT)
        return _coerce_server_port(candidate, fallback=DEFAULT_SERVER_PORT)
    except Exception:
        return DEFAULT_SERVER_PORT


def _coerce_server_port(raw_value, fallback=DEFAULT_SERVER_PORT):
    """Coerce any value to a valid TCP port number."""
    try:
        parsed = int(str(raw_value).strip())
    except Exception:
        return int(fallback)
    if 1 <= parsed <= 65535:
        return parsed
    return int(fallback)


def _extract_host_port_from_url(raw_url):
    """Parse a URL or host:port string and return (host, port)."""
    text = str(raw_url or "").strip()
    if not text:
        return ("localhost", DEFAULT_SERVER_PORT)

    candidate = text if "://" in text else f"ws://{text}"
    try:
        parsed = urlparse(candidate)
        host = (parsed.hostname or "localhost").strip()
        port = parsed.port if parsed.port else DEFAULT_SERVER_PORT
        return (host or "localhost", _coerce_server_port(port))
    except Exception:
        fallback_host = text.split(":")[0].strip() or "localhost"
        return (fallback_host, DEFAULT_SERVER_PORT)


def _build_server_url(host, port):
    """Build a ws:// URL from host and port."""
    clean_host = str(host or "localhost").strip() or "localhost"
    clean_port = _coerce_server_port(port)
    return f"ws://{clean_host}:{clean_port}"


def _normalize_server_entry(entry):
    """Normalize a server entry dict to a canonical form."""
    if not isinstance(entry, dict):
        entry = {}

    name = str(entry.get("name") or "Unnamed Server").strip() or "Unnamed Server"
    host = str(entry.get("host") or "").strip()
    raw_url = str(entry.get("url") or "").strip()
    parsed_host, parsed_port = _extract_host_port_from_url(raw_url)
    if not host:
        host = parsed_host

    port = _coerce_server_port(entry.get("port"), fallback=parsed_port)
    normalized = {
        "name": name,
        "host": host,
        "port": int(port),
        "url": _build_server_url(host, port),
    }
    account = str(entry.get("account") or "").strip()
    if account:
        normalized["account"] = account
    return normalized


def load_servers():
    """Load saved server list from servers.json config file."""
    configured_port = _get_configured_server_port()

    if os.path.exists(SERVERS_CONFIG):
        try:
            with open(SERVERS_CONFIG, "r") as f:
                payload = json.load(f)
            servers = payload.get("servers", []) if isinstance(payload, dict) else []
            normalized_servers = [_normalize_server_entry(s) for s in servers]
            for entry in normalized_servers:
                host_lc = str(entry.get("host", "")).strip().lower()
                if host_lc in {"localhost", "127.0.0.1", "0.0.0.0"} and int(
                    entry.get("port", DEFAULT_SERVER_PORT)
                ) == DEFAULT_SERVER_PORT:
                    entry["port"] = int(configured_port)
                    entry["url"] = _build_server_url(entry.get("host", "localhost"), configured_port)
            normalized_payload = {"servers": normalized_servers}
            if payload != normalized_payload:
                with open(SERVERS_CONFIG, "w") as f:
                    json.dump(normalized_payload, f, indent=2)
            return {"servers": normalized_servers}
        except Exception:
            pass

    # Default local server
    return {
        "servers": [
            {
                "name": "Local Server",
                "host": "localhost",
                "port": int(configured_port),
                "url": _build_server_url("localhost", configured_port),
            }
        ]
    }


def save_servers(servers_data):
    """Persist the server list to servers.json."""
    try:
        servers = servers_data.get("servers", []) if isinstance(servers_data, dict) else []
        normalized = {"servers": [_normalize_server_entry(s) for s in servers]}
        with open(SERVERS_CONFIG, "w") as f:
            json.dump(normalized, f, indent=2)
        return True
    except Exception as e:
        print(f"Error saving servers: {e}")
        return False


def get_server_username(server_url):
    """Return the saved account name for the given server URL, or '' if none."""
    if not server_url:
        return ""
    data = load_servers()
    for entry in data.get("servers", []):
        if entry.get("url") == server_url:
            return entry.get("account", "")
    return ""


def save_server_username(server_url, username):
    """Persist username against server_url in servers.json (no password stored)."""
    if not server_url or not username:
        return
    data = load_servers()
    servers = data.get("servers", [])
    for entry in servers:
        if entry.get("url") == server_url:
            entry["account"] = username
            break
    else:
        host, port = _extract_host_port_from_url(server_url)
        servers.append(
            {
                "name": server_url,
                "host": host,
                "port": port,
                "url": _build_server_url(host, port),
                "account": username,
            }
        )
    data["servers"] = servers
    save_servers(data)
