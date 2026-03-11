"""
server/multiplayer_features.py — Extended multiplayer features for Starship Terminal.

Provides:
- Module trading between players
- Special weapon leaderboards
- Player achievements system
- Trading contracts and auctions
"""

import time
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class AchievementType(Enum):
    """Types of player achievements."""
    COMBAT_WINS = "combat_wins"
    MODULES_COLLECTED = "modules_collected"
    SPECIAL_WEAPONS = "special_weapons"
    WEALTH = "wealth"
    EXPLORATION = "exploration"
    TRADING = "trading"


@dataclass
class Achievement:
    """Player achievement record."""
    id: str
    player_name: str
    achievement_type: AchievementType
    title: str
    description: str
    unlocked_at: float = field(default_factory=time.time)
    progress: int = 0
    max_progress: int = 100

    def is_completed(self) -> bool:
        """Check if achievement is completed."""
        return self.progress >= self.max_progress

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "player_name": self.player_name,
            "type": self.achievement_type.value,
            "title": self.title,
            "description": self.description,
            "unlocked_at": self.unlocked_at,
            "progress": self.progress,
            "max_progress": self.max_progress,
            "completed": self.is_completed(),
        }


@dataclass
class TradeOffer:
    """Module trade offer between players."""
    id: str
    seller_name: str
    buyer_name: Optional[str]
    module_name: str
    asking_price: int
    created_at: float = field(default_factory=time.time)
    expires_at: float = 0

    def is_expired(self) -> bool:
        """Check if trade offer has expired."""
        if self.expires_at == 0:
            return False
        return time.time() > self.expires_at

    def is_available(self) -> bool:
        """Check if trade offer is still available."""
        return self.buyer_name is None and not self.is_expired()

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "id": self.id,
            "seller": self.seller_name,
            "buyer": self.buyer_name,
            "module": self.module_name,
            "price": self.asking_price,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "available": self.is_available(),
        }


@dataclass
class Leaderboard:
    """Player leaderboard entry."""
    rank: int
    player_name: str
    category: str
    score: int
    timestamp: float = field(default_factory=time.time)
    details: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "rank": self.rank,
            "player": self.player_name,
            "category": self.category,
            "score": self.score,
            "timestamp": self.timestamp,
            "details": self.details,
        }


class LeaderboardManager:
    """Manages player leaderboards for various categories."""

    CATEGORIES = [
        "combat_wins",
        "special_weapons_fired",
        "modules_collected",
        "wealth",
        "planets_owned",
        "contracts_completed",
    ]

    def __init__(self, max_entries: int = 100):
        self.max_entries = max_entries
        self.leaderboards = {cat: [] for cat in self.CATEGORIES}

    def update_score(
        self, category: str, player_name: str, score: int, details: Dict = None
    ):
        """Update a player's score in a category."""
        if category not in self.leaderboards:
            return False

        # Remove existing entry if present
        self.leaderboards[category] = [
            entry for entry in self.leaderboards[category]
            if entry.player_name != player_name
        ]

        # Add new entry
        entry = Leaderboard(
            rank=len(self.leaderboards[category]) + 1,
            player_name=player_name,
            category=category,
            score=score,
            details=details or {},
        )
        self.leaderboards[category].append(entry)

        # Sort and trim
        self.leaderboards[category].sort(key=lambda x: x.score, reverse=True)
        self.leaderboards[category] = self.leaderboards[category][:self.max_entries]

        # Update ranks
        for i, entry in enumerate(self.leaderboards[category]):
            entry.rank = i + 1

        return True

    def get_leaderboard(self, category: str) -> List[Leaderboard]:
        """Get a complete leaderboard."""
        return self.leaderboards.get(category, [])

    def get_player_rank(self, category: str, player_name: str) -> Optional[int]:
        """Get a player's rank in a category."""
        for entry in self.leaderboards.get(category, []):
            if entry.player_name == player_name:
                return entry.rank
        return None


class ModuleTradeManager:
    """Manages module trading between players."""

    def __init__(self):
        self.trades = {}  # trade_id -> TradeOffer
        self.next_id = 0

    def create_trade_offer(
        self, seller_name: str, module_name: str, price: int, expires_in_hours: int = 24
    ) -> Tuple[bool, str, Optional[str]]:
        """Create a new module trade offer."""
        from security import ModuleValidator

        # Validate module
        valid, msg = ModuleValidator.validate_module(module_name)
        if not valid:
            return False, msg, None

        # Validate price
        if price < 0:
            return False, "Price cannot be negative", None

        # Create trade
        trade_id = f"trade_{self.next_id}"
        self.next_id += 1

        expires_at = time.time() + (expires_in_hours * 3600)

        trade = TradeOffer(
            id=trade_id,
            seller_name=seller_name,
            buyer_name=None,
            module_name=module_name,
            asking_price=price,
            expires_at=expires_at,
        )

        self.trades[trade_id] = trade
        return True, "Trade offer created", trade_id

    def accept_trade(self, trade_id: str, buyer_name: str) -> Tuple[bool, str]:
        """Accept a module trade offer."""
        if trade_id not in self.trades:
            return False, "Trade not found"

        trade = self.trades[trade_id]

        if not trade.is_available():
            return False, "Trade is no longer available"

        if trade.seller_name == buyer_name:
            return False, "Cannot buy from yourself"

        trade.buyer_name = buyer_name
        return True, f"Trade accepted: {trade.module_name} for {trade.asking_price} credits"

    def get_available_trades(self, module_filter: Optional[str] = None) -> List[TradeOffer]:
        """Get list of available trade offers."""
        trades = [t for t in self.trades.values() if t.is_available()]

        if module_filter:
            trades = [t for t in trades if t.module_name.lower() == module_filter.lower()]

        return trades

    def get_player_trades(self, player_name: str) -> Tuple[List[TradeOffer], List[TradeOffer]]:
        """Get a player's buying and selling offers."""
        selling = [t for t in self.trades.values() if t.seller_name == player_name]
        buying = [t for t in self.trades.values() if t.buyer_name == player_name]

        return selling, buying


class PlayerAchievementManager:
    """Manages player achievements."""

    def __init__(self):
        self.achievements = {}  # player_name -> [Achievement]
        self.next_id = 0

    def unlock_achievement(
        self, player_name: str, achievement_type: AchievementType, title: str, description: str
    ) -> bool:
        """Unlock a new achievement for a player."""
        if player_name not in self.achievements:
            self.achievements[player_name] = []

        achievement_id = f"ach_{self.next_id}"
        self.next_id += 1

        achievement = Achievement(
            id=achievement_id,
            player_name=player_name,
            achievement_type=achievement_type,
            title=title,
            description=description,
        )

        self.achievements[player_name].append(achievement)
        return True

    def update_progress(
        self, player_name: str, achievement_type: AchievementType, progress: int
    ) -> bool:
        """Update achievement progress."""
        if player_name not in self.achievements:
            return False

        for achievement in self.achievements.get(player_name, []):
            if achievement.achievement_type == achievement_type:
                achievement.progress = progress
                return True

        return False

    def get_player_achievements(self, player_name: str) -> List[Achievement]:
        """Get all achievements for a player."""
        return self.achievements.get(player_name, [])

    def get_completed_achievements(self, player_name: str) -> List[Achievement]:
        """Get completed achievements for a player."""
        return [
            a for a in self.achievements.get(player_name, [])
            if a.is_completed()
        ]


# Global instances for multiplayer features
leaderboard_manager = LeaderboardManager()
module_trade_manager = ModuleTradeManager()
achievement_manager = PlayerAchievementManager()


# Predefined leaderboards
def initialize_leaderboards():
    """Initialize predefined leaderboard categories."""
    return leaderboard_manager


def get_player_stats_summary(player_name: str) -> Dict:
    """Get a summary of player statistics and achievements."""
    achievements = achievement_manager.get_player_achievements(player_name)
    completed = achievement_manager.get_completed_achievements(player_name)

    stats = {
        "player": player_name,
        "total_achievements": len(achievements),
        "completed_achievements": len(completed),
        "leaderboard_positions": {},
    }

    for category in LeaderboardManager.CATEGORIES:
        rank = leaderboard_manager.get_player_rank(category, player_name)
        if rank is not None:
            stats["leaderboard_positions"][category] = rank

    return stats
