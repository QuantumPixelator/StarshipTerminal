# Window constants
SCREEN_WIDTH = 1680
SCREEN_HEIGHT = 900
SCREEN_TITLE = "STARSHIP TERMINAL"

# Colors - Cyberpunk/Terminal theme
COLOR_PRIMARY = (0, 255, 150)  # Neon Green
COLOR_SECONDARY = (0, 150, 255)  # Cyber Blue
COLOR_ACCENT = (255, 0, 150)  # Neon Pink
COLOR_BG = (10, 10, 15)  # Deep Space Black
COLOR_TEXT_DIM = (150, 150, 150)

# Upgrade Core Prices (for value calculation)
UPGRADE_PRICE_CARGO = 75
UPGRADE_PRICE_SHIELD = 200
UPGRADE_PRICE_DEFENDER = 75


def get_font(font_type="ui"):
    if font_type == "title":
        return "Monofett"
    elif font_type == "ui_bold":
        return "Space Mono Bold"
    return "Space Mono"
