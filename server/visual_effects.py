"""
Visual Effects and Animations for Starship Terminal.

Handles visual feedback including:
- Combat effect animations
- Module visual indicators
- Status effect displays
- Color themes and styling
"""

import arcade
import sys
import os

# Add parent directory to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'client'))
from constants import COLOR_PRIMARY, COLOR_SECONDARY, COLOR_ACCENT, COLOR_BG, COLOR_TEXT_DIM


# ========== Combat Visual Effects ==========
COMBAT_EFFECTS = {
    "laser_to_target": {
        "duration": 0.18,
        "animation": "laser_beam",
        "color": COLOR_PRIMARY,
        "sound": "combat_fire",
        "description": "Laser beam to target",
    },
    "laser_to_player": {
        "duration": 0.18,
        "animation": "laser_beam",
        "color": COLOR_ACCENT,
        "sound": "combat_fire",
        "description": "Laser beam to player",
    },
    "shield_target": {
        "duration": 0.32,
        "animation": "shield_impact",
        "color": COLOR_SECONDARY,
        "sound": "shield_hit",
        "description": "Shield impact on target",
    },
    "shield_player": {
        "duration": 0.32,
        "animation": "shield_impact",
        "color": COLOR_SECONDARY,
        "sound": "shield_hit",
        "description": "Shield impact on player",
    },
    "hull_target": {
        "duration": 0.36,
        "animation": "explosion_small",
        "color": (255, 100, 0),
        "sound": "hull_damage",
        "description": "Hull damage on target",
    },
    "hull_player": {
        "duration": 0.36,
        "animation": "explosion_small",
        "color": (255, 100, 0),
        "sound": "hull_damage",
        "description": "Hull damage on player",
    },
    "critical_hit": {
        "duration": 0.5,
        "animation": "explosion_large",
        "color": (255, 200, 0),
        "sound": "critical_hit",
        "description": "Critical hit explosion",
    },
    "special_weapon": {
        "duration": 0.55,
        "animation": "pulse_wave",
        "color": (255, 80, 40),
        "sound": "special_weapon_fire",
        "description": "Special weapon impact",
    },
}

# ========== Module Visual Indicators ==========
MODULE_INDICATORS = {
    "scanner": {
        "icon": "⊕",  # Circle with plus
        "color": COLOR_PRIMARY,
        "color_rgb": (64, 220, 255),
        "effect": "scan_pulse",
        "animation_speed": 2.0,
        "bonus_text": "+10% Scanning",
        "icon_description": "Scanning Module",
    },
    "jammer": {
        "icon": "◇",  # Diamond
        "color": COLOR_SECONDARY,
        "color_rgb": (255, 180, 0),
        "effect": "interference_waves",
        "animation_speed": 1.5,
        "bonus_text": "+12% Evasion",
        "icon_description": "Jammer Module",
    },
    "cargo_optimizer": {
        "icon": "□",  # Square
        "color": (100, 255, 100),
        "color_rgb": (100, 255, 100),
        "effect": "efficiency_pulse",
        "animation_speed": 1.0,
        "bonus_text": "+12% Capacity, -3.5% Fuel",
        "icon_description": "Cargo Optimizer",
    },
}

MODULE_THEMES = {
    "scanner": {
        "primary": (64, 220, 255),  # Cyan
        "secondary": (40, 140, 160),  # Dark cyan
        "highlight": (100, 255, 255),  # Light cyan
        "text": (255, 255, 255),
        "description": "Scanning system - Blue theme",
    },
    "jammer": {
        "primary": (255, 180, 0),  # Orange
        "secondary": (180, 120, 0),  # Dark orange
        "highlight": (255, 220, 80),  # Light orange
        "text": (255, 255, 255),
        "description": "Electronic warfare - Orange theme",
    },
    "cargo_optimizer": {
        "primary": (100, 255, 100),  # Green
        "secondary": (60, 180, 60),  # Dark green
        "highlight": (150, 255, 150),  # Light green
        "text": (255, 255, 255),
        "description": "Logistics system - Green theme",
    },
}

# ========== Weapon Effect Animations ==========
WEAPON_EFFECTS = {
    "laser": {
        "animation_type": "beam",
        "color": COLOR_PRIMARY,
        "width": 1.0,
        "particle_effect": "spark_burst",
        "duration": 0.2,
    },
    "missile": {
        "animation_type": "projectile",
        "color": (255, 100, 0),
        "width": 2.0,
        "particle_effect": "explosion",
        "duration": 0.3,
    },
    "ion_blast": {
        "animation_type": "pulse",
        "color": (100, 150, 255),
        "width": 3.0,
        "particle_effect": "ion_surge",
        "duration": 0.4,
    },
    "focus_fire": {
        "animation_type": "converging_beams",
        "color": COLOR_SECONDARY,
        "width": 2.0,
        "particle_effect": "energy_cascade",
        "duration": 0.5,
    },
}

# ========== Status Effect Displays ==========
STATUS_EFFECTS = {
    "shields_low": {
        "icon": "⚠",
        "color": (255, 180, 0),
        "animation": "flashing",
        "duration": 0.5,
        "intensity": "high",
    },
    "hull_damaged": {
        "icon": "✕",
        "color": COLOR_ACCENT,
        "animation": "pulse",
        "duration": 0.4,
        "intensity": "critical",
    },
    "system_critical": {
        "icon": "⬣",
        "color": (255, 0, 0),
        "animation": "rapid_flash",
        "duration": 0.2,
        "intensity": "critical",
    },
    "module_active": {
        "icon": "●",
        "color": COLOR_PRIMARY,
        "animation": "steady_glow",
        "duration": 0.0,  # Continuous
        "intensity": "normal",
    },
    "module_cooldown": {
        "icon": "◐",
        "color": (200, 100, 100),
        "animation": "rotating_arc",
        "duration": 1.0,
        "intensity": "low",
    },
    "special_weapon_ready": {
        "icon": "★",
        "color": COLOR_SECONDARY,
        "animation": "pulse_glow",
        "duration": 0.0,  # Continuous
        "intensity": "high",
    },
}

# ========== UI Theme Indicators ==========
SHIP_ROLE_COLORS = {
    "Hauler": {
        "primary": (100, 200, 100),  # Green for cargo
        "secondary": (60, 140, 60),
        "icon": "⬚",
        "bonus_module": "cargo_optimizer",
    },
    "Interceptor": {
        "primary": (64, 220, 255),  # Cyan for speed
        "secondary": (40, 140, 160),
        "icon": "▲",
        "bonus_module": "scanner",
    },
    "Siege": {
        "primary": (255, 100, 100),  # Red for firepower
        "secondary": (180, 60, 60),
        "icon": "■",
        "bonus_module": "jammer",
    },
    "Runner": {
        "primary": (255, 180, 0),  # Orange for balanced
        "secondary": (180, 120, 0),
        "icon": "◆",
        "bonus_module": "jammer",
    },
}

# ========== Animation Frames ==========
ANIMATIONS = {
    "laser_beam": {
        "frames": 3,
        "frame_rate": 10,
        "repeating": False,
        "description": "Laser beam animation",
    },
    "shield_impact": {
        "frames": 5,
        "frame_rate": 15,
        "repeating": False,
        "description": "Shield impact ripple",
    },
    "explosion_small": {
        "frames": 8,
        "frame_rate": 20,
        "repeating": False,
        "description": "Small explosion",
    },
    "explosion_large": {
        "frames": 12,
        "frame_rate": 20,
        "repeating": False,
        "description": "Large explosion",
    },
    "pulse_wave": {
        "frames": 4,
        "frame_rate": 8,
        "repeating": False,
        "description": "Expanding pulse wave",
    },
    "scan_pulse": {
        "frames": 6,
        "frame_rate": 12,
        "repeating": True,
        "description": "Scanning pulse effect",
    },
    "interference_waves": {
        "frames": 4,
        "frame_rate": 10,
        "repeating": True,
        "description": "Electronic interference waves",
    },
    "efficiency_pulse": {
        "frames": 3,
        "frame_rate": 8,
        "repeating": True,
        "description": "Efficiency pulse effect",
    },
}


# ========== Visual Feedback Functions ==========
def get_module_color(module_name):
    """Get the primary color for a module."""
    if module_name in MODULE_THEMES:
        return MODULE_THEMES[module_name]["primary"]
    return COLOR_PRIMARY


def get_module_icon(module_name):
    """Get the icon character for a module."""
    if module_name in MODULE_INDICATORS:
        return MODULE_INDICATORS[module_name]["icon"]
    return "?"


def get_status_effect_icon(status_name):
    """Get the icon for a status effect."""
    if status_name in STATUS_EFFECTS:
        return STATUS_EFFECTS[status_name]["icon"]
    return "●"


def get_ship_role_color(role_name):
    """Get the primary color for a ship role."""
    if role_name in SHIP_ROLE_COLORS:
        return SHIP_ROLE_COLORS[role_name]["primary"]
    return COLOR_PRIMARY


def get_weapon_color(weapon_type):
    """Get the color for a weapon type."""
    if weapon_type in WEAPON_EFFECTS:
        return WEAPON_EFFECTS[weapon_type]["color"]
    return COLOR_PRIMARY


def get_animation_speed(animation_name):
    """Get animation speed for a visual effect."""
    if animation_name in ANIMATIONS:
        return ANIMATIONS[animation_name]["frame_rate"]
    return 10


def get_combat_effect_duration(effect_name):
    """Get duration of a combat effect."""
    if effect_name in COMBAT_EFFECTS:
        return COMBAT_EFFECTS[effect_name]["duration"]
    return 0.3


# ========== Color Palette for Different Themes ==========
COLOR_THEME_DARK = {
    "background": (20, 20, 30),
    "text_primary": (255, 255, 255),
    "text_secondary": (200, 200, 200),
    "border": COLOR_PRIMARY,
    "highlight": COLOR_SECONDARY,
}

COLOR_THEME_LIGHT = {
    "background": (240, 240, 250),
    "text_primary": (20, 20, 30),
    "text_secondary": (80, 80, 100),
    "border": COLOR_ACCENT,
    "highlight": COLOR_PRIMARY,
}

COLOR_THEME_CYBER = {
    "background": (0, 0, 10),
    "text_primary": (0, 255, 150),
    "text_secondary": (0, 180, 120),
    "border": (0, 255, 150),
    "highlight": (255, 0, 150),
}
