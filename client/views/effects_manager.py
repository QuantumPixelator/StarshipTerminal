"""
Integrated Audio-Visual Effects Manager.

Coordinates audio effects with visual feedback for cohesive,
immersive player experience during combat, trading, and ship operations.
"""

from typing import Dict, Optional, Tuple
from dataclasses import dataclass
import time


@dataclass
class EffectEvent:
    """Represents a game event that triggers audio-visual feedback."""
    event_type: str
    location: Tuple[int, int]
    intensity: float = 1.0
    duration: float = 0.3
    timestamp: float = None
    
    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


class IntegratedEffectsManager:
    """
    Manages coordinated audio-visual effects for game events.
    
    Ensures audio and visual feedback occur simultaneously and
    maintains consistent effect configurations across the game.
    """
    
    # Combat effect mappings: (audio, visual, duration)
    COMBAT_EFFECTS_MAP = {
        "player_fires": {
            "audio": "combat_fire",
            "visual": "laser_to_target",
            "duration": 0.18,
            "intensity": 1.0,
        },
        "enemy_fires": {
            "audio": "combat_fire",
            "visual": "laser_to_player",
            "duration": 0.18,
            "intensity": 0.85,
        },
        "shield_hit_target": {
            "audio": "shield_hit",
            "visual": "shield_target",
            "duration": 0.32,
            "intensity": 1.0,
        },
        "shield_hit_player": {
            "audio": "shield_hit",
            "visual": "shield_player",
            "duration": 0.32,
            "intensity": 1.2,
        },
        "hull_damage_target": {
            "audio": "hull_damage",
            "visual": "hull_target",
            "duration": 0.36,
            "intensity": 1.0,
        },
        "hull_damage_player": {
            "audio": "hull_damage",
            "visual": "hull_player",
            "duration": 0.36,
            "intensity": 1.3,
        },
        "critical_hit": {
            "audio": "critical_hit",
            "visual": "critical_hit",
            "duration": 0.5,
            "intensity": 1.5,
        },
        "special_weapon_ready": {
            "audio": "special_weapon_ready",
            "visual": "module_active",
            "duration": 0.2,
            "intensity": 0.8,
        },
        "special_weapon_fire": {
            "audio": "special_weapon_fire",
            "visual": "special_weapon",
            "duration": 0.55,
            "intensity": 1.4,
        },
        "combat_start": {
            "audio": "combat_start",
            "visual": "combat_start",
            "duration": 0.3,
            "intensity": 1.0,
        },
        "combat_victory": {
            "audio": "combat_victory",
            "visual": "module_active",
            "duration": 1.0,
            "intensity": 1.2,
        },
        "combat_defeat": {
            "audio": "combat_defeat",
            "visual": "hull_damaged",
            "duration": 0.8,
            "intensity": 1.1,
        },
    }
    
    # Trading effect mappings
    TRADING_EFFECTS_MAP = {
        "purchase": {
            "audio": "purchase",
            "visual": "module_active",
            "duration": 0.4,
            "intensity": 0.9,
        },
        "sale": {
            "audio": "sale",
            "visual": "module_active",
            "duration": 0.4,
            "intensity": 0.9,
        },
        "contract_accept": {
            "audio": "contract_accept",
            "visual": "module_active",
            "duration": 0.3,
            "intensity": 0.8,
        },
        "contract_complete": {
            "audio": "contract_complete",
            "visual": "special_weapon",
            "duration": 0.55,
            "intensity": 1.1,
        },
        "credits_transfer": {
            "audio": "credits_transfer",
            "visual": "scan_pulse",
            "duration": 0.4,
            "intensity": 0.7,
        },
    }
    
    # Ship operation effect mappings
    SHIP_EFFECTS_MAP = {
        "module_install": {
            "audio": "module_install",
            "visual": "module_active",
            "duration": 0.35,
            "intensity": 1.0,
        },
        "module_remove": {
            "audio": "module_remove",
            "visual": "module_cooldown",
            "duration": 0.25,
            "intensity": 0.8,
        },
        "upgrade_install": {
            "audio": "upgrade_install",
            "visual": "scan_pulse",
            "duration": 0.4,
            "intensity": 1.0,
        },
        "engine_startup": {
            "audio": "engine_startup",
            "visual": "pulse_wave",
            "duration": 0.5,
            "intensity": 0.9,
        },
        "engine_running": {
            "audio": "engine_running",
            "visual": "efficiency_pulse",
            "duration": 0.2,
            "intensity": 0.5,
        },
        "jump_charge": {
            "audio": "jump_charge",
            "visual": "interference_waves",
            "duration": 1.0,
            "intensity": 1.1,
        },
        "jump_execute": {
            "audio": "jump_execute",
            "visual": "pulse_wave",
            "duration": 0.6,
            "intensity": 1.2,
        },
        "shield_activated": {
            "audio": "shield_active",
            "visual": "shield_impact",
            "duration": 0.32,
            "intensity": 0.8,
        },
        "shield_low": {
            "audio": "shield_low",
            "visual": "shields_low",
            "duration": 0.5,
            "intensity": 1.1,
        },
        "hull_breach": {
            "audio": "hull_breach",
            "visual": "hull_damaged",
            "duration": 0.8,
            "intensity": 1.3,
        },
    }
    
    # Planet operation effect mappings
    PLANET_EFFECTS_MAP = {
        "planet_docking": {
            "audio": "planet_docking",
            "visual": "scan_pulse",
            "duration": 0.4,
            "intensity": 0.9,
        },
        "planet_departure": {
            "audio": "planet_departure",
            "visual": "pulse_wave",
            "duration": 0.3,
            "intensity": 0.8,
        },
        "planet_scan": {
            "audio": "planet_scan",
            "visual": "scan_pulse",
            "duration": 0.35,
            "intensity": 0.7,
        },
        "orbit_alert": {
            "audio": "orbit_alert",
            "visual": "module_cooldown",
            "duration": 0.4,
            "intensity": 1.0,
        },
    }
    
    # Alert effect mappings
    ALERT_EFFECTS_MAP = {
        "target_acquired": {
            "audio": "target_acquired",
            "visual": "module_active",
            "duration": 0.3,
            "intensity": 1.0,
        },
        "enemy_detected": {
            "audio": "enemy_detected",
            "visual": "shields_low",
            "duration": 0.4,
            "intensity": 1.2,
        },
        "alarm": {
            "audio": "alarm",
            "visual": "rapid_flash",
            "duration": 0.2,
            "intensity": 1.4,
        },
        "notification": {
            "audio": "notification",
            "visual": "module_active",
            "duration": 0.2,
            "intensity": 0.7,
        },
        "mail_received": {
            "audio": "mail_received",
            "visual": "scan_pulse",
            "duration": 0.3,
            "intensity": 0.8,
        },
    }
    
    # UI effect mappings
    UI_EFFECTS_MAP = {
        "menu_select": {
            "audio": "menu_select",
            "visual": "module_active",
            "duration": 0.15,
            "intensity": 0.6,
        },
        "menu_hover": {
            "audio": "menu_hover",
            "visual": "scan_pulse",
            "duration": 0.1,
            "intensity": 0.4,
        },
        "confirm": {
            "audio": "confirm",
            "visual": "module_active",
            "duration": 0.25,
            "intensity": 0.8,
        },
        "cancel": {
            "audio": "cancel",
            "visual": "module_cooldown",
            "duration": 0.15,
            "intensity": 0.6,
        },
        "error": {
            "audio": "error",
            "visual": "shields_low",
            "duration": 0.3,
            "intensity": 1.0,
        },
        "success": {
            "audio": "success",
            "visual": "module_active",
            "duration": 0.35,
            "intensity": 0.95,
        },
    }
    
    def __init__(self):
        """Initialize the effects manager."""
        self.active_effects: Dict[str, EffectEvent] = {}
        self.effect_queue = []
        self.last_effect_time = {}
        
    def trigger_combat_effect(self, effect_name: str, location: Tuple[int, int], 
                             intensity: float = 1.0) -> bool:
        """Trigger a combat audio-visual effect."""
        if effect_name in self.COMBAT_EFFECTS_MAP:
            effect_config = self.COMBAT_EFFECTS_MAP[effect_name]
            return self._play_effect(effect_name, effect_config, location, intensity)
        return False
    
    def trigger_trading_effect(self, effect_name: str, location: Tuple[int, int],
                              intensity: float = 1.0) -> bool:
        """Trigger a trading audio-visual effect."""
        if effect_name in self.TRADING_EFFECTS_MAP:
            effect_config = self.TRADING_EFFECTS_MAP[effect_name]
            return self._play_effect(effect_name, effect_config, location, intensity)
        return False
    
    def trigger_ship_effect(self, effect_name: str, location: Tuple[int, int],
                           intensity: float = 1.0) -> bool:
        """Trigger a ship operation audio-visual effect."""
        if effect_name in self.SHIP_EFFECTS_MAP:
            effect_config = self.SHIP_EFFECTS_MAP[effect_name]
            return self._play_effect(effect_name, effect_config, location, intensity)
        return False
    
    def trigger_planet_effect(self, effect_name: str, location: Tuple[int, int],
                             intensity: float = 1.0) -> bool:
        """Trigger a planet operation audio-visual effect."""
        if effect_name in self.PLANET_EFFECTS_MAP:
            effect_config = self.PLANET_EFFECTS_MAP[effect_name]
            return self._play_effect(effect_name, effect_config, location, intensity)
        return False
    
    def trigger_alert_effect(self, effect_name: str, location: Tuple[int, int],
                            intensity: float = 1.0) -> bool:
        """Trigger an alert audio-visual effect."""
        if effect_name in self.ALERT_EFFECTS_MAP:
            effect_config = self.ALERT_EFFECTS_MAP[effect_name]
            return self._play_effect(effect_name, effect_config, location, intensity)
        return False
    
    def trigger_ui_effect(self, effect_name: str, location: Tuple[int, int],
                        intensity: float = 1.0) -> bool:
        """Trigger a UI audio-visual effect."""
        if effect_name in self.UI_EFFECTS_MAP:
            effect_config = self.UI_EFFECTS_MAP[effect_name]
            return self._play_effect(effect_name, effect_config, location, intensity)
        return False
    
    def _play_effect(self, effect_name: str, config: Dict, location: Tuple[int, int],
                    intensity: float) -> bool:
        """Internal method to play an effect."""
        # Prevent effect spam with cooldown check
        current_time = time.time()
        if effect_name in self.last_effect_time:
            time_since_last = current_time - self.last_effect_time[effect_name]
            if time_since_last < 0.05:  # Minimum 50ms between same effects
                return False
        
        # Create effect event
        effect = EffectEvent(
            event_type=effect_name,
            location=location,
            intensity=round(float(intensity) * float(config.get("intensity", 1.0)), 4),
            duration=config.get("duration", 0.3),
        )
        
        # Store in active effects
        self.active_effects[effect_name] = effect
        self.last_effect_time[effect_name] = current_time
        self.effect_queue.append((effect_name, config))
        
        return True
    
    def get_effect_config(self, effect_name: str) -> Optional[Dict]:
        """Retrieve configuration for a specific effect."""
        # Check all effect maps
        for effect_map in [
            self.COMBAT_EFFECTS_MAP,
            self.TRADING_EFFECTS_MAP,
            self.SHIP_EFFECTS_MAP,
            self.PLANET_EFFECTS_MAP,
            self.ALERT_EFFECTS_MAP,
            self.UI_EFFECTS_MAP,
        ]:
            if effect_name in effect_map:
                return effect_map[effect_name]
        return None
    
    def get_all_effects_by_category(self, category: str) -> Dict[str, Dict]:
        """Get all effects in a category."""
        category_map = {
            "combat": self.COMBAT_EFFECTS_MAP,
            "trading": self.TRADING_EFFECTS_MAP,
            "ship": self.SHIP_EFFECTS_MAP,
            "planet": self.PLANET_EFFECTS_MAP,
            "alert": self.ALERT_EFFECTS_MAP,
            "ui": self.UI_EFFECTS_MAP,
        }
        return category_map.get(category, {})
    
    def update(self, delta_time: float):
        """Update active effects, removing expired ones."""
        current_time = time.time()
        expired = []
        
        for effect_name, effect in self.active_effects.items():
            elapsed = current_time - effect.timestamp
            if effect.duration > 0 and elapsed > effect.duration:
                expired.append(effect_name)
        
        for effect_name in expired:
            del self.active_effects[effect_name]
    
    def clear_all_effects(self):
        """Clear all active effects."""
        self.active_effects.clear()
        self.effect_queue.clear()
        self.last_effect_time.clear()
    
    def get_active_effects(self) -> Dict[str, EffectEvent]:
        """Get dictionary of currently active effects."""
        return self.active_effects.copy()
    
    def is_effect_active(self, effect_name: str) -> bool:
        """Check if a specific effect is currently active."""
        return effect_name in self.active_effects


# Global instance for use throughout the game
effects_manager = IntegratedEffectsManager()


def play_combat_effect(effect_name: str, location: Tuple[int, int] = (0, 0), 
                       intensity: float = 1.0) -> bool:
    """Global function to play combat effects."""
    return effects_manager.trigger_combat_effect(effect_name, location, intensity)


def play_trading_effect(effect_name: str, location: Tuple[int, int] = (0, 0),
                       intensity: float = 1.0) -> bool:
    """Global function to play trading effects."""
    return effects_manager.trigger_trading_effect(effect_name, location, intensity)


def play_ship_effect(effect_name: str, location: Tuple[int, int] = (0, 0),
                    intensity: float = 1.0) -> bool:
    """Global function to play ship effects."""
    return effects_manager.trigger_ship_effect(effect_name, location, intensity)


def play_planet_effect(effect_name: str, location: Tuple[int, int] = (0, 0),
                      intensity: float = 1.0) -> bool:
    """Global function to play planet effects."""
    return effects_manager.trigger_planet_effect(effect_name, location, intensity)


def play_alert_effect(effect_name: str, location: Tuple[int, int] = (0, 0),
                     intensity: float = 1.0) -> bool:
    """Global function to play alert effects."""
    return effects_manager.trigger_alert_effect(effect_name, location, intensity)


def play_ui_effect(effect_name: str, location: Tuple[int, int] = (0, 0),
                  intensity: float = 1.0) -> bool:
    """Global function to play UI effects."""
    return effects_manager.trigger_ui_effect(effect_name, location, intensity)
