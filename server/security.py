"""
server/security.py — Security utilities for preventing cheating and exploits.

Provides:
- Rate limiting for special weapon usage
- Input validation and sanitization
- Server-side verification of module installations
"""

import time
import hashlib
import logging
from collections import defaultdict
from typing import Dict, Tuple, Optional


class RateLimiter:
    """Simple rate limiter for preventing abuse of limited-use features."""

    def __init__(self, max_calls: int, time_window_seconds: int):
        """
        Initialize rate limiter.

        Args:
            max_calls: Maximum number of calls allowed in time window
            time_window_seconds: Time window in seconds
        """
        self.max_calls = max_calls
        self.time_window = time_window_seconds
        self.calls_by_player = defaultdict(list)

    def is_allowed(self, player_id: str) -> bool:
        """Check if a player is allowed to take an action."""
        now = time.time()
        
        # Clean old calls outside the time window
        cutoff_time = now - self.time_window
        if player_id in self.calls_by_player:
            self.calls_by_player[player_id] = [
                t for t in self.calls_by_player[player_id] if t > cutoff_time
            ]
        
        # Check if under limit
        if len(self.calls_by_player[player_id]) < self.max_calls:
            self.calls_by_player[player_id].append(now)
            return True
        
        return False

    def get_remaining_cooldown(self, player_id: str) -> float:
        """Get remaining cooldown time in seconds."""
        if not self.calls_by_player[player_id]:
            return 0.0
        
        oldest_call = self.calls_by_player[player_id][0]
        cutoff_time = time.time() - self.time_window
        
        if oldest_call < cutoff_time:
            return 0.0
        
        return oldest_call + self.time_window - time.time()


class InputValidator:
    """Validates and sanitizes user input."""

    # Allowed characters in names
    ALLOWED_NAME_CHARS = set(
        "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789 -'."
    )
    
    # Maximum field lengths
    MAX_NAME_LENGTH = 32
    MAX_MESSAGE_LENGTH = 500
    
    # Minimum field lengths
    MIN_NAME_LENGTH = 3
    MIN_PASSWORD_LENGTH = 8

    @staticmethod
    def validate_player_name(name: str) -> Tuple[bool, str]:
        """
        Validate player/character name.

        Returns:
            (is_valid, error_message)
        """
        if not name:
            return False, "Name cannot be empty"
        
        name = name.strip()
        
        if len(name) < InputValidator.MIN_NAME_LENGTH:
            return False, f"Name must be at least {InputValidator.MIN_NAME_LENGTH} characters"
        
        if len(name) > InputValidator.MAX_NAME_LENGTH:
            return False, f"Name cannot exceed {InputValidator.MAX_NAME_LENGTH} characters"
        
        # Check for invalid characters
        for char in name:
            if char not in InputValidator.ALLOWED_NAME_CHARS:
                return False, f"Invalid character '{char}' in name"
        
        return True, ""

    @staticmethod
    def validate_password(password: str) -> Tuple[bool, str]:
        """
        Validate password strength.

        Returns:
            (is_valid, error_message)
        """
        if len(password) < InputValidator.MIN_PASSWORD_LENGTH:
            return False, f"Password must be at least {InputValidator.MIN_PASSWORD_LENGTH} characters"
        
        has_upper = any(c.isupper() for c in password)
        has_lower = any(c.islower() for c in password)
        has_digit = any(c.isdigit() for c in password)
        
        if not (has_upper and has_lower and has_digit):
            return False, "Password must contain uppercase, lowercase, and digits"
        
        return True, ""

    @staticmethod
    def sanitize_message(message: str) -> str:
        """Sanitize message for safety."""
        if not message:
            return ""
        
        # Remove control characters
        sanitized = "".join(char for char in message if ord(char) >= 32)
        
        # Limit length
        return sanitized[: InputValidator.MAX_MESSAGE_LENGTH]

    @staticmethod
    def sanitize_name(name: str) -> str:
        """Sanitize name by removing invalid characters."""
        return "".join(
            char for char in name.strip()
            if char in InputValidator.ALLOWED_NAME_CHARS
        )


class ModuleValidator:
    """Validates module installations and prevents exploits."""

    # Valid modules
    VALID_MODULES = {"scanner", "jammer", "cargo_optimizer"}

    @staticmethod
    def validate_module(module_name: str) -> Tuple[bool, str]:
        """Validate that a module name is allowed."""
        if not module_name:
            return False, "Module name cannot be empty"
        
        module = module_name.strip().lower()
        
        if module not in ModuleValidator.VALID_MODULES:
            return False, f"Invalid module '{module_name}'. Valid modules: {', '.join(ModuleValidator.VALID_MODULES)}"
        
        return True, ""

    @staticmethod
    def validate_module_slot_availability(
        current_modules: list, max_slots: int
    ) -> Tuple[bool, str]:
        """Check if there's space for another module."""
        if len(current_modules) >= max_slots:
            return False, f"No available module slots (max: {max_slots})"
        
        return True, ""

    @staticmethod
    def validate_module_installation(
        module_name: str, current_modules: list, max_slots: int, duplicate_check=True
    ) -> Tuple[bool, str]:
        """Validate a complete module installation."""
        # Validate module name
        valid, msg = ModuleValidator.validate_module(module_name)
        if not valid:
            return False, msg
        
        # Normalize the module name
        module_name = module_name.strip().lower()
        
        # Check for duplicates
        if duplicate_check and module_name in current_modules:
            return False, f"Module '{module_name}' is already installed"
        
        # Check slots available
        valid, msg = ModuleValidator.validate_module_slot_availability(
            current_modules, max_slots
        )
        if not valid:
            return False, msg
        
        return True, ""


class SpecialWeaponValidator:
    """Validates special weapon usage and prevents exploits."""

    # Valid special weapons
    VALID_WEAPONS = {
        "EMP Burst",
        "Plasma Strike",
        "Ion Cannon",
        "Laser Beam",
    }

    @staticmethod
    def validate_weapon(weapon_name: Optional[str]) -> Tuple[bool, str]:
        """Validate that a weapon name is allowed or None."""
        if weapon_name is None:
            return True, ""
        
        if not weapon_name:
            return False, "Weapon name cannot be empty"
        
        if weapon_name not in SpecialWeaponValidator.VALID_WEAPONS:
            return False, f"Invalid weapon '{weapon_name}'"
        
        return True, ""

    @staticmethod
    def is_weapon_available(last_used_time: float, cooldown_hours: float) -> bool:
        """Check if a weapon is available based on cooldown."""
        now = time.time()
        elapsed_hours = (now - last_used_time) / 3600.0
        return elapsed_hours >= cooldown_hours

    @staticmethod
    def get_cooldown_remaining(last_used_time: float, cooldown_hours: float) -> float:
        """Get remaining cooldown in seconds."""
        now = time.time()
        elapsed_seconds = now - last_used_time
        cooldown_seconds = cooldown_hours * 3600
        
        return max(0.0, cooldown_seconds - elapsed_seconds)


# Initialize rate limiter for special weapons
# Max 1 special weapon use per cooldown period (36 hours default)
special_weapon_rate_limiter = RateLimiter(max_calls=1, time_window_seconds=36 * 3600)


def check_special_weapon_rate_limit(player_id: str) -> Tuple[bool, str]:
    """Check if player can fire a special weapon considering rate limits."""
    if not special_weapon_rate_limiter.is_allowed(player_id):
        remaining = special_weapon_rate_limiter.get_remaining_cooldown(player_id)
        hours = remaining / 3600
        return False, f"Special weapon on cooldown ({hours:.1f} hours remaining)"
    
    return True, ""


# Caching for validation results
class ValidationCache:
    """Cache validation results to improve performance."""

    def __init__(self, ttl_seconds: int = 600):
        """Initialize cache with TTL."""
        self.ttl = ttl_seconds
        self.cache = {}  # key -> (value, timestamp)

    def get(self, key: str):
        """Get cached value if still valid."""
        if key in self.cache:
            value, timestamp = self.cache[key]
            if time.time() - timestamp < self.ttl:
                return value
        
        return None

    def set(self, key: str, value):
        """Cache a value."""
        self.cache[key] = (value, time.time())

    def clear_expired(self):
        """Remove expired entries."""
        now = time.time()
        self.cache = {
            k: v for k, v in self.cache.items()
            if now - v[1] < self.ttl
        }
