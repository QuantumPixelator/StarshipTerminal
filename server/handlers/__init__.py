"""
server/handlers/__init__.py

Exports a single ``build_dispatch(server)`` factory that merges every
domain-handler registry into one flat dict:

    { "action_name": handler_func, ... }

Each handler function has the signature:

    handler(server, session, gm, params) -> dict

where *server* is the ``GameServer`` instance (for access to helpers like
``_serialize_player``, ``_safe_name``, etc.).
"""

from .auth_session import register as _auth_session
from .player_info import register as _player_info
from .economy import register as _economy
from .ship_ops import register as _ship_ops
from .navigation import register as _navigation
from .combat import register as _combat
from .banking import register as _banking
from .factions import register as _factions
from .messaging import register as _messaging
from .misc import register as _misc
from .analytics import register as _analytics


def build_dispatch():
    """Return the merged action → handler mapping."""
    merged = {}
    for reg in (
        _auth_session,
        _player_info,
        _economy,
        _ship_ops,
        _navigation,
        _combat,
        _banking,
        _factions,
        _messaging,
        _misc,
        _analytics,
    ):
        merged.update(reg())
    return merged


__all__ = ["build_dispatch"]
