
# REFACTORED FOR NETWORK CLIENT - All game logic runs on server
# Views are split into individual modules for maintainability.

from .menu import (
    MainMenuView,
    LoadMissionView,
    GalacticNewsView,
    CommanderCreationView,
    ShipSelectionView,
)
from .gameplay import PlanetView
from .warp_view import WarpView
from .popup_view import TimedPopupView
from .travel_event_view import TravelEventView
from .travel_combat_view import TravelCombatView
from .travel_view import TravelView
from .auth_view import AuthenticationView, CharacterSelectView
from .connection_view import ConnectionView
from .analytics_view import AnalyticsView

__all__ = [
    "MainMenuView",
    "LoadMissionView",
    "GalacticNewsView",
    "CommanderCreationView",
    "ShipSelectionView",
    "PlanetView",
    "WarpView",
    "TimedPopupView",
    "TravelEventView",
    "TravelCombatView",
    "TravelView",
    "AuthenticationView",
    "CharacterSelectView",
    "ConnectionView",
    "AnalyticsView",
]
