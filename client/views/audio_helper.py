"""
Audio system helper module for PlanetView.

Handles all audio and sound effects including:
- Audio asset loading and caching
- Sound effect playback with volume control
- Audio configuration management
"""

import os
import arcade
from constants import *


class AudioManager:
    """Manages audio and sound effects for a game view."""

    def __init__(self, view):
        """Initialize audio manager.
        
        Args:
            view: The parent PlanetView instance
        """
        self.view = view
        self.enabled = bool(view.network.config.get("audio_enabled", True))
        self.sfx_channel_volume = {
            "ui": max(
                0.0, min(1.0, float(view.network.config.get("audio_ui_volume", 0.70)))
            ),
            "combat": max(
                0.0,
                min(1.0, float(view.network.config.get("audio_combat_volume", 0.80))),
            ),
            "ambient": max(
                0.0,
                min(1.0, float(view.network.config.get("audio_ambient_volume", 0.45))),
            ),
        }
        self.sfx_assets = {}
        self._load_assets()

    def _load_assets(self):
        """Load all audio assets."""
        # Define audio assets and their locations
        audio_assets = {
            "ui": ["menu_select", "menu_hover", "confirm", "cancel"],
            "combat": ["combat_fire", "combat_hit", "combat_special", "combat_victory", "combat_defeat"],
            "ambient": ["travel_hum", "shields_low", "alert"],
        }
        
        for category, sounds in audio_assets.items():
            for sound_name in sounds:
                self._try_load_sound(category, sound_name)

    def _try_load_sound(self, category, sound_name):
        """Try to load a sound file from assets.
        
        Args:
            category: Audio category (ui, combat, ambient)
            sound_name: Name of the sound file
        """
        # Try multiple file extensions
        audio_path = f"assets/audio/{category}/{sound_name}"
        
        for ext in [".wav", ".mp3", ".ogg"]:
            file_path = audio_path + ext
            if os.path.exists(file_path):
                try:
                    sound = arcade.load_sound(file_path)
                    key = f"{category}:{sound_name}"
                    self.sfx_assets[key] = sound
                    return True
                except Exception as e:
                    print(f"Warning: Failed to load {file_path}: {e}")
                    return False
        
        # Asset not found - this is not an error for now
        return False

    def play(self, category, sound_name, volume_override=None):
        """Play a sound effect.
        
        Args:
            category: Audio category (ui, combat, ambient)
            sound_name: Name of the sound to play
            volume_override: Optional volume override (0.0-1.0)
        """
        if not self.enabled:
            return
        
        key = f"{category}:{sound_name}"
        sound = self.sfx_assets.get(key)
        
        if not sound:
            # Sound not loaded - try to load it now
            self._try_load_sound(category, sound_name)
            sound = self.sfx_assets.get(key)
        
        if not sound:
            return
        
        # Calculate volume
        category_volume = self.sfx_channel_volume.get(category, 0.7)
        final_volume = volume_override if volume_override is not None else category_volume
        final_volume = max(0.0, min(1.0, final_volume))
        
        # Play the sound
        try:
            arcade.play_sound(sound, volume=final_volume)
        except Exception as e:
            print(f"Warning: Failed to play sound {key}: {e}")

    def set_volume(self, category, volume):
        """Set volume for a category.
        
        Args:
            category: Audio category (ui, combat, ambient)
            volume: Volume level (0.0-1.0)
        """
        self.sfx_channel_volume[category] = max(0.0, min(1.0, float(volume)))
        
        # Update config
        config_key = f"audio_{category}_volume"
        self.view.network.config[config_key] = self.sfx_channel_volume[category]

    def get_volume(self, category):
        """Get current volume for a category.
        
        Args:
            category: Audio category (ui, combat, ambient)
            
        Returns:
            Current volume (0.0-1.0)
        """
        return self.sfx_channel_volume.get(category, 0.7)

    def set_enabled(self, enabled):
        """Enable or disable audio.
        
        Args:
            enabled: Whether audio is enabled
        """
        self.enabled = bool(enabled)
        self.view.network.config["audio_enabled"] = self.enabled

    def is_enabled(self):
        """Check if audio is enabled."""
        return self.enabled

    def play_ui_feedback(self, action):
        """Play standard UI feedback sound.
        
        Args:
            action: Type of action (select, hover, confirm, cancel)
        """
        if action == "select":
            self.play("ui", "menu_select")
        elif action == "hover":
            self.play("ui", "menu_hover")
        elif action == "confirm":
            self.play("ui", "confirm")
        elif action == "cancel":
            self.play("ui", "cancel")

    def play_combat_feedback(self, event):
        """Play combat sound effects based on event.
        
        Args:
            event: Type of combat event (fire, hit, special, victory, defeat)
        """
        if event == "fire":
            self.play("combat", "combat_fire")
        elif event == "hit":
            self.play("combat", "combat_hit")
        elif event == "special":
            self.play("combat", "combat_special")
        elif event == "victory":
            self.play("combat", "combat_victory")
        elif event == "defeat":
            self.play("combat", "combat_defeat")

    def stop_all(self):
        """Stop all currently playing sounds."""
        # Note: Arcade library doesn't have a built-in stop-all method
        # Sounds will stop when they finish playing or when replaced
        pass

    def preload_category(self, category):
        """Preload all sounds in a category.
        
        Args:
            category: Audio category to preload
        """
        assets_by_category = {
            "ui": ["menu_select", "menu_hover", "confirm", "cancel"],
            "combat": ["combat_fire", "combat_hit", "combat_special", "combat_victory", "combat_defeat"],
            "ambient": ["travel_hum", "shields_low", "alert"],
        }
        
        sounds = assets_by_category.get(category, [])
        for sound_name in sounds:
            if f"{category}:{sound_name}" not in self.sfx_assets:
                self._try_load_sound(category, sound_name)

    def get_loaded_sounds(self):
        """Get list of currently loaded sounds.
        
        Returns:
            List of loaded sound keys
        """
        return list(self.sfx_assets.keys())

    def unload_unused(self):
        """Unload audio assets that are rarely used.
        
        This can help manage memory usage.
        """
        # Keep recent sounds, unload old ones
        # For now, keep all loaded sounds in memory
        pass
