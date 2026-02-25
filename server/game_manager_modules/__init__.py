from .core import CoreMixin
from .persistence import PersistenceMixin
from .factions import FactionMixin
from .economy import EconomyMixin
from .crew_bank import CrewBankMixin
from .navigation import NavigationMixin
from .combat import CombatMixin
from .ship_ops import ShipOpsMixin
from .analytics import AnalyticsMixin


class GameManager(
    CoreMixin,
    PersistenceMixin,
    FactionMixin,
    EconomyMixin,
    CrewBankMixin,
    NavigationMixin,
    CombatMixin,
    ShipOpsMixin,
    AnalyticsMixin,
):
    pass
