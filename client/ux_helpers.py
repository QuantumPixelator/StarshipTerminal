"""
client/ux_helpers.py — UX improvements for new game mechanics.

Provides:
- Tooltips and help text for modules
- Gamepad support helpers
- Keybinding customization
- Status indicators for special weapons
"""

# Module Tooltips
MODULE_TOOLTIPS = {
    "scanner": {
        "name": "Scanner Module",
        "description": "Improves targeting and detection capabilities",
        "bonuses": [
            "+10% scanning bonus",
            "+20% combat power multiplier",
            "Enhanced interceptor strength",
        ],
        "best_for": "Interceptor ships and tactical combat",
    },
    "jammer": {
        "name": "Jammer Module",
        "description": "Reduces detection and improves evasion",
        "bonuses": [
            "+12% jammer bonus",
            "+12% scan evasion",
            "Enhanced siege ship strength",
            "Benefits runners with additional stealth",
        ],
        "best_for": "Avoiding detection and evasion-based gameplay",
    },
    "cargo_optimizer": {
        "name": "Cargo Optimizer Module",
        "description": "Optimizes cargo space and fuel efficiency",
        "bonuses": [
            "+12% effective cargo capacity",
            "-3.5% fuel burn rate",
            "Enhanced hauler strength",
        ],
        "best_for": "Trading and economic gameplay",
    },
}

# Special Weapon Tooltips
SPECIAL_WEAPON_TOOLTIPS = {
    "EMP Burst": {
        "name": "EMP Burst",
        "description": "Electromagnetic pulse depletes enemy shields",
        "effects": ["Damages shields", "Reduces combat power"],
        "cooldown": "36 hours",
        "best_against": "Shielded targets",
    },
    "Plasma Strike": {
        "name": "Plasma Strike",
        "description": "Powerful energy weapon with area effect",
        "effects": ["Damages shields and integrity", "Population reduction"],
        "cooldown": "36 hours",
        "best_against": "Planetary targets",
    },
    "Ion Cannon": {
        "name": "Ion Cannon",
        "description": "Ionized particle beam",
        "effects": ["Structural damage", "System disruption"],
        "cooldown": "36 hours",
        "best_against": "Large targets",
    },
    "Laser Beam": {
        "name": "Laser Beam",
        "description": "Concentrated laser energy",
        "effects": ["Precision damage", "Defender elimination"],
        "cooldown": "36 hours",
        "best_against": "Fighter defense",
    },
}

# Keybinding Defaults
DEFAULT_KEYBINDINGS = {
    # Navigation
    "forward": "W",
    "backward": "S",
    "strafe_left": "A",
    "strafe_right": "D",
    
    # Combat
    "fire_weapon": "SPACE",
    "fire_special_weapon": "SHIFT+SPACE",
    "target_next": "E",
    "target_previous": "Q",
    
    # Systems
    "transfer_fighters": "LEFT",
    "transfer_shields": "UP",
    "repair": "R",
    "open_inventory": "I",
    
    # UI
    "help": "F1",
    "menu": "ESC",
}

# Gamepad Button Mappings
GAMEPAD_BUTTONS = {
    "A": "Confirm",
    "B": "Cancel",
    "X": "Special Action",
    "Y": "Info/Help",
    "LB": "Cycle Left",
    "RB": "Cycle Right",
    "LT": "Previous Target",
    "RT": "Next Target",
    "Back": "Menu",
    "Start": "Pause",
}

# Status Indicators for Special Weapons
SPECIAL_WEAPON_STATUS = {
    "ready": {
        "color": (0, 255, 0),  # Green
        "text": "READY",
        "symbol": "⚡",
    },
    "cooldown": {
        "color": (255, 165, 0),  # Orange
        "text": "COOLDOWN",
        "symbol": "⏱",
    },
    "unavailable": {
        "color": (128, 128, 128),  # Gray
        "text": "N/A",
        "symbol": "○",
    },
    "no_target": {
        "color": (255, 0, 0),  # Red
        "text": "NO TARGET",
        "symbol": "✗",
    },
}

# Module Installation Help
MODULE_INSTALLATION_HELP = """
=== Module Installation Guide ===

Modules upgrade your ship with special abilities.

BEFORE INSTALLING:
1. Check available module slots on your ship
2. Verify the module isn't already installed
3. Ensure you have enough credits (if required)

HOW TO INSTALL:
1. Access the ship upgrade menu
2. Select "Install Module"
3. Choose from available modules
4. Confirm the installation

MODULE EFFECTS:
- Scanner: Better targeting (+10% scanning)
- Jammer: Better evasion (+12% scan evasion)  
- Cargo Optimizer: More cargo (+12% capacity)

TIPS:
- Modules work best with compatible ship roles
- Multiple modules stack their bonuses
- Remove modules by replacing them with different ones
"""

# Special Weapon Usage Help
SPECIAL_WEAPON_HELP = """
=== Special Weapon Guide ===

Special weapons are powerful limited-use abilities.

BEFORE USING:
1. Equip a special weapon on your ship
2. Engage in combat with a target
3. Wait for cooldown to expire if recently used

HOW TO FIRE:
1. Enter combat
2. Target an enemy
3. Press SHIFT+SPACE (or configured key)
4. Wait 36 hours for cooldown to recharge

WEAPON TYPES:
- EMP Burst: Disables shields
- Plasma Strike: Area damage
- Ion Cannon: Structural damage
- Laser Beam: Precision strike

STRATEGIC TIPS:
- Use against tough opponents
- Perfect for planet conquest
- Conserve uses for critical battles
- Different weapons have different effects
"""

# Gamepad Tutorial
GAMEPAD_TUTORIAL = """
=== Gamepad Controls ===

NAVIGATION:
- Left Stick: Move around
- Right Stick: Look around (if applicable)

COMBAT:
- RT: Fire weapon
- LT: Fire special weapon
- LB/RB: Cycle targets
- A: Confirm selection
- B: Return to previous screen

MENUS:
- D-Pad: Navigate options
- A: Confirm
- B: Cancel
- Y: Get help
- Start: Pause game
"""


def get_module_tooltip(module_name: str) -> dict:
    """Get tooltip information for a module."""
    return MODULE_TOOLTIPS.get(module_name.lower(), {})


def get_weapon_tooltip(weapon_name: str) -> dict:
    """Get tooltip information for a special weapon."""
    return SPECIAL_WEAPON_TOOLTIPS.get(weapon_name, {})


def get_weapon_status_display(status: str) -> dict:
    """Get display information for weapon status."""
    return SPECIAL_WEAPON_STATUS.get(status, SPECIAL_WEAPON_STATUS["unavailable"])


def format_module_info(module_name: str) -> str:
    """Format module information for display."""
    tooltip = get_module_tooltip(module_name)
    if not tooltip:
        return f"Unknown module: {module_name}"
    
    lines = [
        f"=== {tooltip['name']} ===",
        tooltip['description'],
        "",
        "Bonuses:",
    ]
    
    for bonus in tooltip.get('bonuses', []):
        lines.append(f"  • {bonus}")
    
    lines.append("")
    lines.append(f"Best for: {tooltip['best_for']}")
    
    return "\n".join(lines)


def format_weapon_info(weapon_name: str) -> str:
    """Format special weapon information for display."""
    tooltip = get_weapon_tooltip(weapon_name)
    if not tooltip:
        return f"Unknown weapon: {weapon_name}"
    
    lines = [
        f"=== {tooltip['name']} ===",
        tooltip['description'],
        "",
        "Effects:",
    ]
    
    for effect in tooltip.get('effects', []):
        lines.append(f"  • {effect}")
    
    lines.append("")
    lines.append(f"Cooldown: {tooltip['cooldown']}")
    lines.append(f"Best against: {tooltip['best_against']}")
    
    return "\n".join(lines)


def get_keybinding(action: str) -> str:
    """Get the keybinding for an action."""
    return DEFAULT_KEYBINDINGS.get(action, "Not bound")


def customize_keybinding(action: str, key: str) -> bool:
    """Customize a keybinding for an action."""
    if action not in DEFAULT_KEYBINDINGS:
        return False
    
    DEFAULT_KEYBINDINGS[action] = key
    return True


def get_all_keybindings() -> dict:
    """Get all current keybindings."""
    return DEFAULT_KEYBINDINGS.copy()
