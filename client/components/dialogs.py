"""
Dialog UI components for Starship Terminal.
Provides InputDialog (text entry) and MessageBox (notification overlay).
"""

import arcade
from constants import SCREEN_WIDTH, SCREEN_HEIGHT
from utils.drawing import _draw_centered_rectangle_filled, _draw_centered_rectangle_outline


class InputDialog:
    """Simple input dialog for text entry with optional password masking."""

    def __init__(self, prompt, default="", max_length=50, password=False):
        self.prompt = prompt
        self.text = default
        self.max_length = max_length
        self.password = password
        self.active = True

    def update(self, delta_time):
        """Update cursor blink (placeholder for future animation)."""
        pass

    def draw(self):
        """Draw the input dialog overlay."""
        _draw_centered_rectangle_filled(
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            (0, 0, 0, 180),
        )

        box_width = 600
        box_height = 200
        _draw_centered_rectangle_filled(
            SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2, box_width, box_height, (30, 30, 40)
        )
        _draw_centered_rectangle_outline(
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2,
            box_width,
            box_height,
            (0, 255, 100),
            2,
        )

        arcade.draw_text(
            self.prompt,
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2 + 50,
            (200, 200, 200),
            16,
            anchor_x="center",
            font_name="Courier New",
        )

        display_text = "●" * len(self.text) if self.password else self.text

        arcade.draw_text(
            display_text,
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2,
            (0, 255, 100),
            18,
            anchor_x="center",
            font_name="Courier New",
            bold=True,
        )

        arcade.draw_text(
            "[ENTER] Confirm  |  [ESC] Cancel",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2 - 60,
            (100, 100, 100),
            12,
            anchor_x="center",
            font_name="Courier New",
        )

    def on_key_press(self, key, modifiers):
        """Handle key input. Returns the text on confirm, None on cancel, 'continue' otherwise."""
        if key == arcade.key.ESCAPE:
            self.active = False
            return None
        elif key == arcade.key.ENTER:
            self.active = False
            return self.text
        elif key == arcade.key.BACKSPACE:
            self.text = self.text[:-1]
        return "continue"

    def on_text(self, text):
        """Handle printable character input."""
        if len(self.text) < self.max_length and text.isprintable():
            self.text += text


class MessageBox:
    """Simple message box overlay for notifications and errors."""

    def __init__(self, title, message, type="info"):
        self.title = title
        self.message = message
        self.type = type  # "info", "error", "success"
        self.active = True

    def draw(self):
        """Draw the message box overlay."""
        _draw_centered_rectangle_filled(
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2,
            SCREEN_WIDTH,
            SCREEN_HEIGHT,
            (0, 0, 0, 180),
        )

        box_width = 600
        box_height = 250
        _draw_centered_rectangle_filled(
            SCREEN_WIDTH // 2, SCREEN_HEIGHT // 2, box_width, box_height, (30, 30, 40)
        )

        if self.type == "error":
            border_color = (255, 50, 50)
        elif self.type == "success":
            border_color = (50, 255, 100)
        else:
            border_color = (100, 200, 255)

        _draw_centered_rectangle_outline(
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2,
            box_width,
            box_height,
            border_color,
            2,
        )

        arcade.draw_text(
            self.title,
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2 + 70,
            border_color,
            20,
            anchor_x="center",
            font_name="Courier New",
            bold=True,
        )

        # Word-wrap the message
        lines = []
        words = self.message.split()
        current_line = ""
        max_width = 50

        for word in words:
            if len(current_line) + len(word) + 1 <= max_width:
                current_line += word + " "
            else:
                lines.append(current_line.strip())
                current_line = word + " "
        if current_line:
            lines.append(current_line.strip())

        y_offset = (len(lines) - 1) * 10
        for i, line in enumerate(lines):
            arcade.draw_text(
                line,
                SCREEN_WIDTH // 2,
                SCREEN_HEIGHT // 2 + y_offset - i * 20,
                (200, 200, 200),
                14,
                anchor_x="center",
                font_name="Courier New",
            )

        arcade.draw_text(
            "[ENTER] or [ESC] to continue",
            SCREEN_WIDTH // 2,
            SCREEN_HEIGHT // 2 - 80,
            (100, 100, 100),
            12,
            anchor_x="center",
            font_name="Courier New",
        )

    def on_key_press(self, key, modifiers):
        """Handle key input. Returns True to dismiss."""
        if key in (arcade.key.ESCAPE, arcade.key.ENTER):
            self.active = False
            return True
        return False
