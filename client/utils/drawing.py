"""
Shared drawing utility functions for Starship Terminal client UI.
Provides cross-Arcade-version compatible drawing helpers.
"""

import arcade


def _draw_centered_rectangle_filled(center_x, center_y, width, height, color):
    """Draw a centered filled rectangle compatible with all Arcade API versions."""
    if hasattr(arcade, "draw_rectangle_filled"):
        arcade.draw_rectangle_filled(center_x, center_y, width, height, color)
    else:
        arcade.draw_lbwh_rectangle_filled(
            center_x - width / 2,
            center_y - height / 2,
            width,
            height,
            color,
        )


def _draw_centered_rectangle_outline(
    center_x, center_y, width, height, color, border_width
):
    """Draw a centered rectangle outline compatible with all Arcade API versions."""
    if hasattr(arcade, "draw_rectangle_outline"):
        arcade.draw_rectangle_outline(
            center_x, center_y, width, height, color, border_width
        )
    else:
        arcade.draw_lbwh_rectangle_outline(
            center_x - width / 2,
            center_y - height / 2,
            width,
            height,
            color,
            border_width,
        )
