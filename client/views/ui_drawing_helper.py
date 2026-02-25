"""
UI drawing and display helper module for PlanetView.

Handles all UI rendering and layout including:
- Button drawing and interaction
- Text formatting and wrapping
- Market display and layout
- Message classification and styling
- UI component positioning
"""

import textwrap
from constants import *


class UIDrawingHelper:
    """Handles UI rendering and display logic for PlanetView."""

    def __init__(self, view):
        """Initialize UI drawing helper.
        
        Args:
            view: The parent PlanetView instance
        """
        self.view = view
        self.cached_button_states = {}

    def draw_button(self, x, y, w, h, text, color, enabled=True):
        """Draw an interactive button.
        
        Args:
            x, y: Button position (bottom-left)
            w, h: Button width and height
            text: Button label
            color: Button background color
            enabled: Whether button is clickable
        """
        import arcade
        
        # Check hover state
        hover = enabled and (
            x <= self.view.mouse_x <= x + w and
            y <= self.view.mouse_y <= y + h
        )

        # Draw background with alpha based on state
        alpha = 255 if hover else (180 if enabled else 60)
        bg_color = (*color, alpha)
        
        arcade.draw_lbwh_rectangle_filled(x, y, w, h, bg_color)
        arcade.draw_lbwh_rectangle_outline(
            x, y, w, h,
            COLOR_PRIMARY if enabled else COLOR_TEXT_DIM,
            2
        )

        # Draw text
        text_color = (
            COLOR_BG if hover else
            (COLOR_PRIMARY if enabled else COLOR_TEXT_DIM)
        )
        
        arcade.Text(
            text,
            x + w / 2,
            y + h / 2,
            text_color,
            11,
            anchor_x="center",
            anchor_y="center",
            font_name=self.view.font_ui_bold,
        ).draw()

    def draw_stat_bar(self, x, y, current, maximum, width=200, height=20, color=COLOR_PRIMARY):
        """Draw a stat bar (health, shields, etc).
        
        Args:
            x, y: Bar position
            current: Current value
            maximum: Maximum value
            width: Bar width
            height: Bar height
            color: Bar color
        """
        import arcade
        
        if maximum <= 0:
            fill_ratio = 0
        else:
            fill_ratio = min(1.0, current / maximum)

        # Background
        arcade.draw_lbwh_rectangle_filled(x, y, width, height, (40, 40, 40))

        # Fill
        arcade.draw_lbwh_rectangle_filled(
            x, y, width * fill_ratio, height, color
        )

        # Border
        arcade.draw_lbwh_rectangle_outline(x, y, width, height, COLOR_PRIMARY, 1)

    def clamp_text(self, text, max_chars):
        """Truncate text to maximum characters with ellipsis.
        
        Args:
            text: Text to clamp
            max_chars: Maximum length
            
        Returns:
            Clamped text
        """
        value = str(text or "").replace("\n", " ").strip()
        if max_chars <= 3:
            return value[:max_chars]
        return value if len(value) <= max_chars else (value[:max_chars - 3] + "...")

    def wrap_text(self, text, max_chars=72, max_lines=2):
        """Wrap text to multiple lines.
        
        Args:
            text: Text to wrap
            max_chars: Maximum characters per line
            max_lines: Maximum number of lines
            
        Returns:
            Wrapped text with newlines
        """
        value = str(text or "").replace("\n", " ").strip()
        if not value:
            return ""

        lines = textwrap.wrap(value, width=max(12, int(max_chars)))
        if len(lines) <= max_lines:
            return "\n".join(lines)

        kept = lines[:max_lines]
        last = kept[-1]
        if len(last) > 3:
            kept[-1] = last[:-3].rstrip() + "..."
        else:
            kept[-1] = "..."
        return "\n".join(kept)

    def format_duration(self, total_seconds):
        """Format seconds as human-readable duration.
        
        Args:
            total_seconds: Duration in seconds
            
        Returns:
            Formatted string like "2H 30M"
        """
        total_seconds = max(0, int(total_seconds))
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        return f"{hours}H {minutes:02d}M"

    def format_number(self, value, use_k=False):
        """Format a number with optional K suffix.
        
        Args:
            value: Number to format
            use_k: If True, use K for thousands (e.g., 1.2K)
            
        Returns:
            Formatted number string
        """
        try:
            val = int(value)
        except (ValueError, TypeError):
            return str(value)

        if use_k and val >= 1000:
            return f"{val / 1000:.1f}K"
        return f"{val:,}"

    def classify_message_type(self, message, default_type="info"):
        """Classify a message as error, warning, success, or info.
        
        Args:
            message: Message text
            default_type: Type if classification fails
            
        Returns:
            Message type: "error", "warning", "success", or "info"
        """
        msg = str(message or "").upper()
        if not msg:
            return default_type

        error_markers = [
            "ERROR", "FAILED", "INSUFFICIENT", "DENIED",
            "INVALID", "BLOCKED", "NOT ENOUGH", "NO ", "UNABLE"
        ]
        warning_markers = [
            "WARNING", "ALERT", "LOCKED", "SANCTION",
            "HOSTILE", "RISK", "DETECTED"
        ]
        success_markers = [
            "SUCCESS", "SOLD", "PURCHASED", "COMPLETE",
            "INSTALLED", "TRANSFERRED", "PAID", "UNLOCKED",
            "ACCEPTED", "CLAIMED", "STORED"
        ]

        if any(marker in msg for marker in error_markers):
            return "error"
        if any(marker in msg for marker in warning_markers):
            return "warning"
        if any(marker in msg for marker in success_markers):
            return "success"
        return default_type

    def get_message_color(self, message_type):
        """Get color for a message type.
        
        Args:
            message_type: Type from classify_message_type
            
        Returns:
            RGB color tuple
        """
        color_map = {
            "error": COLOR_ACCENT,
            "warning": (255, 180, 0),
            "success": COLOR_PRIMARY,
            "info": COLOR_SECONDARY,
        }
        return color_map.get(message_type, COLOR_TEXT)

    def get_market_layout(self, item_count, max_visible=11):
        """Calculate market list layout.
        
        Args:
            item_count: Number of items in market
            max_visible: Maximum visible rows
            
        Returns:
            Dictionary with layout parameters
        """
        row_height = 40
        list_start_y = SCREEN_HEIGHT - 250
        market_list_height = list_start_y - 102

        max_visible_rows = market_list_height // row_height
        max_visible_rows = max(1, max_visible_rows - 1)

        if item_count <= max_visible_rows:
            return {
                "row_height": row_height,
                "start_y": list_start_y,
                "max_visible": max_visible_rows,
                "scroll_offset": 0,
                "item_count": item_count,
            }

        scroll_offset = min(
            self.view.market_scroll if hasattr(self.view, "market_scroll") else 0,
            max(0, item_count - max_visible_rows)
        )
        return {
            "row_height": row_height,
            "start_y": list_start_y,
            "max_visible": max_visible_rows,
            "scroll_offset": scroll_offset,
            "item_count": item_count,
        }

    def is_point_in_rect(self, px, py, rect_x, rect_y, rect_w, rect_h):
        """Check if point is inside rectangle.
        
        Args:
            px, py: Point coordinates
            rect_x, rect_y: Rectangle position
            rect_w, rect_h: Rectangle dimensions
            
        Returns:
            True if point is inside
        """
        return (rect_x <= px <= rect_x + rect_w and
                rect_y <= py <= rect_y + rect_h)

    def get_centered_rect(self, width, height):
        """Get coordinates for centered rectangle.
        
        Args:
            width: Rectangle width
            height: Rectangle height
            
        Returns:
            Tuple of (x, y)
        """
        x = (SCREEN_WIDTH - width) // 2
        y = (SCREEN_HEIGHT - height) // 2
        return x, y

    def draw_panel(self, x, y, width, height, title="", border_color=COLOR_PRIMARY):
        """Draw a UI panel with border and optional title.
        
        Args:
            x, y: Panel position
            width, height: Panel dimensions
            title: Optional title text
            border_color: Border color
        """
        import arcade
        
        # Background
        arcade.draw_lbwh_rectangle_filled(x, y, width, height, (30, 30, 40, 200))

        # Border
        arcade.draw_lbwh_rectangle_outline(x, y, width, height, border_color, 2)

        # Title if provided
        if title:
            title_y = y + height - 25
            arcade.Text(
                title.upper(),
                x + 15,
                title_y,
                border_color,
                14,
                font_name=self.view.font_ui_bold,
            ).draw()

            # Separator line
            arcade.draw_line(x, title_y - 10, x + width, title_y - 10, border_color, 1)

    def highlight_row(self, x, y, width, height, highlight_color=COLOR_PRIMARY, alpha=100):
        """Draw a highlighted row.
        
        Args:
            x, y: Row position
            width, height: Row dimensions
            highlight_color: Highlight color
            alpha: Transparency
        """
        import arcade
        
        arcade.draw_lbwh_rectangle_filled(
            x, y, width, height,
            (*highlight_color, alpha)
        )
