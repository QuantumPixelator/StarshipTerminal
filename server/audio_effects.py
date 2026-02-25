"""
Sound Effects and Audio Configuration for Starship Terminal.

Defines all sound effects used throughout the game with paths, 
volume levels, and usage context.
"""

# UI Sound Effects
UI_SOUNDS = {
    "menu_select": {
        "path": "assets/audio/ui/menu_select.wav",
        "category": "ui",
        "volume": 0.8,
        "description": "Menu item selected",
    },
    "menu_hover": {
        "path": "assets/audio/ui/menu_hover.wav",
        "category": "ui",
        "volume": 0.6,
        "description": "Mouse over menu item",
    },
    "confirm": {
        "path": "assets/audio/ui/confirm.wav",
        "category": "ui",
        "volume": 0.9,
        "description": "Action confirmed",
    },
    "cancel": {
        "path": "assets/audio/ui/cancel.wav",
        "category": "ui",
        "volume": 0.7,
        "description": "Action cancelled",
    },
    "error": {
        "path": "assets/audio/ui/error.wav",
        "category": "ui",
        "volume": 0.8,
        "description": "Error/warning sound",
    },
    "success": {
        "path": "assets/audio/ui/success.wav",
        "category": "ui",
        "volume": 0.85,
        "description": "Success/completion sound",
    },
}

# Trading and Market Sound Effects
TRADING_SOUNDS = {
    "purchase": {
        "path": "assets/audio/trading/purchase.wav",
        "category": "ui",
        "volume": 0.8,
        "description": "Item purchased",
    },
    "sale": {
        "path": "assets/audio/trading/sale.wav",
        "category": "ui",
        "volume": 0.8,
        "description": "Item sold",
    },
    "credits_transfer": {
        "path": "assets/audio/trading/credits_transfer.wav",
        "category": "ui",
        "volume": 0.7,
        "description": "Credits transferred between accounts",
    },
    "contract_accept": {
        "path": "assets/audio/trading/contract_accept.wav",
        "category": "ui",
        "volume": 0.9,
        "description": "Trade contract accepted",
    },
    "contract_complete": {
        "path": "assets/audio/trading/contract_complete.wav",
        "category": "ui",
        "volume": 0.95,
        "description": "Trade contract completed",
    },
}

# Combat Sound Effects
COMBAT_SOUNDS = {
    "combat_start": {
        "path": "assets/audio/combat/combat_start.wav",
        "category": "combat",
        "volume": 0.95,
        "description": "Combat begins",
    },
    "combat_fire": {
        "path": "assets/audio/combat/combat_fire.wav",
        "category": "combat",
        "volume": 0.8,
        "description": "Weapon fired",
    },
    "combat_hit": {
        "path": "assets/audio/combat/combat_hit.wav",
        "category": "combat",
        "volume": 0.85,
        "description": "Successful hit on target",
    },
    "combat_miss": {
        "path": "assets/audio/combat/combat_miss.wav",
        "category": "combat",
        "volume": 0.6,
        "description": "Attack missed target",
    },
    "shield_hit": {
        "path": "assets/audio/combat/shield_hit.wav",
        "category": "combat",
        "volume": 0.7,
        "description": "Shields absorb damage",
    },
    "hull_damage": {
        "path": "assets/audio/combat/hull_damage.wav",
        "category": "combat",
        "volume": 0.85,
        "description": "Hull takes damage",
    },
    "critical_hit": {
        "path": "assets/audio/combat/critical_hit.wav",
        "category": "combat",
        "volume": 0.95,
        "description": "Critical hit scored",
    },
    "special_weapon_ready": {
        "path": "assets/audio/combat/special_weapon_ready.wav",
        "category": "combat",
        "volume": 0.8,
        "description": "Special weapon is ready to use",
    },
    "special_weapon_fire": {
        "path": "assets/audio/combat/special_weapon_fire.wav",
        "category": "combat",
        "volume": 1.0,
        "description": "Special weapon fired",
    },
    "special_weapon_cooldown": {
        "path": "assets/audio/combat/special_weapon_cooldown.wav",
        "category": "combat",
        "volume": 0.7,
        "description": "Special weapon on cooldown",
    },
    "combat_victory": {
        "path": "assets/audio/combat/combat_victory.wav",
        "category": "combat",
        "volume": 1.0,
        "description": "Combat won",
    },
    "combat_defeat": {
        "path": "assets/audio/combat/combat_defeat.wav",
        "category": "combat",
        "volume": 0.9,
        "description": "Combat lost",
    },
    "combat_retreat": {
        "path": "assets/audio/combat/combat_retreat.wav",
        "category": "combat",
        "volume": 0.75,
        "description": "Retreated from combat",
    },
}

# Ship and Systems Sound Effects
SHIP_SOUNDS = {
    "engine_startup": {
        "path": "assets/audio/ship/engine_startup.wav",
        "category": "ship",
        "volume": 0.7,
        "description": "Ship engines starting",
    },
    "engine_running": {
        "path": "assets/audio/ship/engine_running.wav",
        "category": "ship",
        "volume": 0.5,
        "description": "Ship engines running (looping)",
    },
    "jump_charge": {
        "path": "assets/audio/ship/jump_charge.wav",
        "category": "ship",
        "volume": 0.8,
        "description": "Warp engine charging",
    },
    "jump_execute": {
        "path": "assets/audio/ship/jump_execute.wav",
        "category": "ship",
        "volume": 0.9,
        "description": "Warp jump executed",
    },
    "module_install": {
        "path": "assets/audio/ship/module_install.wav",
        "category": "ui",
        "volume": 0.8,
        "description": "Module successfully installed",
    },
    "module_remove": {
        "path": "assets/audio/ship/module_remove.wav",
        "category": "ui",
        "volume": 0.7,
        "description": "Module removed from ship",
    },
    "upgrade_install": {
        "path": "assets/audio/ship/upgrade_install.wav",
        "category": "ui",
        "volume": 0.85,
        "description": "Upgrade successfully installed",
    },
    "shield_active": {
        "path": "assets/audio/ship/shield_active.wav",
        "category": "ship",
        "volume": 0.6,
        "description": "Shields activated",
    },
    "shield_low": {
        "path": "assets/audio/ship/shield_low.wav",
        "category": "ship",
        "volume": 0.8,
        "description": "Shields are low (warning)",
    },
    "hull_breach": {
        "path": "assets/audio/ship/hull_breach.wav",
        "category": "ship",
        "volume": 0.9,
        "description": "Hull breach warning",
    },
}

# Planet and Location Sound Effects
PLANET_SOUNDS = {
    "planet_docking": {
        "path": "assets/audio/planet/planet_docking.wav",
        "category": "planet",
        "volume": 0.75,
        "description": "Docking at planet",
    },
    "planet_departure": {
        "path": "assets/audio/planet/planet_departure.wav",
        "category": "planet",
        "volume": 0.7,
        "description": "Departing from planet",
    },
    "planet_scan": {
        "path": "assets/audio/planet/planet_scan.wav",
        "category": "ui",
        "volume": 0.7,
        "description": "Planet scanned",
    },
    "orbit_alert": {
        "path": "assets/audio/planet/orbit_alert.wav",
        "category": "planet",
        "volume": 0.85,
        "description": "Alert in planetary orbit",
    },
}

# Notification and Alert Sound Effects
ALERT_SOUNDS = {
    "notification": {
        "path": "assets/audio/alerts/notification.wav",
        "category": "ui",
        "volume": 0.7,
        "description": "General notification",
    },
    "mail_received": {
        "path": "assets/audio/alerts/mail_received.wav",
        "category": "ui",
        "volume": 0.8,
        "description": "New mail received",
    },
    "target_acquired": {
        "path": "assets/audio/alerts/target_acquired.wav",
        "category": "combat",
        "volume": 0.85,
        "description": "Target acquired",
    },
    "enemy_detected": {
        "path": "assets/audio/alerts/enemy_detected.wav",
        "category": "combat",
        "volume": 0.9,
        "description": "Enemy detected nearby",
    },
    "alarm": {
        "path": "assets/audio/alerts/alarm.wav",
        "category": "alert",
        "volume": 0.95,
        "description": "System alarm",
    },
}

# Special Weapon Sound Effects
SPECIAL_WEAPON_SOUNDS = {
    "special_weapon_default": {
        "path": "assets/audio/special_weapons/special_weapon_default.wav",
        "category": "combat",
        "volume": 1.0,
        "description": "Generic special weapon sound",
    },
    "special_weapon_ion_blast": {
        "path": "assets/audio/special_weapons/ion_blast.wav",
        "category": "combat",
        "volume": 1.0,
        "description": "Ion blast special weapon",
    },
    "special_weapon_emp_surge": {
        "path": "assets/audio/special_weapons/emp_surge.wav",
        "category": "combat",
        "volume": 0.95,
        "description": "EMP surge special weapon",
    },
    "special_weapon_focus_fire": {
        "path": "assets/audio/special_weapons/focus_fire.wav",
        "category": "combat",
        "volume": 1.0,
        "description": "Focus fire special weapon",
    },
}

# Music and Ambient Sound Effects
MUSIC_SOUNDS = {
    "music_mainmenu": {
        "path": "assets/audio/music/mainmenu.wav",
        "category": "music",
        "volume": 0.5,
        "description": "Main menu music",
        "looping": True,
    },
    "music_exploration": {
        "path": "assets/audio/music/exploration.wav",
        "category": "music",
        "volume": 0.45,
        "description": "Space exploration ambient",
        "looping": True,
    },
    "music_combat": {
        "path": "assets/audio/music/combat.wav",
        "category": "combat",
        "volume": 0.55,
        "description": "Combat music",
        "looping": True,
    },
    "music_planet": {
        "path": "assets/audio/music/planet.wav",
        "category": "music",
        "volume": 0.4,
        "description": "Planet surface music",
        "looping": True,
    },
}

# Combine all sounds
ALL_SOUNDS = {}
ALL_SOUNDS.update(UI_SOUNDS)
ALL_SOUNDS.update(TRADING_SOUNDS)
ALL_SOUNDS.update(COMBAT_SOUNDS)
ALL_SOUNDS.update(SHIP_SOUNDS)
ALL_SOUNDS.update(PLANET_SOUNDS)
ALL_SOUNDS.update(ALERT_SOUNDS)
ALL_SOUNDS.update(SPECIAL_WEAPON_SOUNDS)
ALL_SOUNDS.update(MUSIC_SOUNDS)


def get_sound_path(sound_name):
    """Get the file path for a sound effect."""
    if sound_name in ALL_SOUNDS:
        return ALL_SOUNDS[sound_name]["path"]
    return None


def get_sound_volume(sound_name):
    """Get the default volume for a sound effect."""
    if sound_name in ALL_SOUNDS:
        return ALL_SOUNDS[sound_name]["volume"]
    return 0.7


def get_sounds_by_category(category):
    """Get all sounds in a category."""
    return {
        name: info
        for name, info in ALL_SOUNDS.items()
        if info.get("category") == category
    }


def get_sound_description(sound_name):
    """Get the description of a sound effect."""
    if sound_name in ALL_SOUNDS:
        return ALL_SOUNDS[sound_name]["description"]
    return "Unknown sound effect"
