"""planet_view.py — re-export shim for PlanetView.

PlanetView is defined in gameplay.py (it's the large main game view).
This shim lets other modules do ``from views.planet_view import PlanetView``
instead of importing from the monolithic gameplay module directly.
"""

from .gameplay import PlanetView  # noqa: F401

__all__ = ["PlanetView"]
