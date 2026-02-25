"""
Audio Playback Integration System.

Bridges the effects manager with the audio system to play coordinated
sound effects during gameplay. Handles asset loading, volume control,
and playback scheduling.
"""

import sys
import os
from typing import Dict, Optional, Tuple
from enum import Enum
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'server'))

from audio_effects import ALL_SOUNDS, get_sound_path, get_sound_volume
from .audio_helper import AudioManager


class AudioChannel(Enum):
    """Audio playback channels for different sound categories."""
    COMBAT = "combat"
    TRADING = "trading"
    SHIP = "ship"
    PLANET = "planet"
    ALERT = "alert"
    UI = "ui"
    MUSIC = "music"
    AMBIENT = "ambient"


# Setup logging
logger = logging.getLogger("audio_integration")


class AudioPlaybackIntegration:
    """
    Integrates effects manager with arcade audio system.
    
    Manages sound playback for all effect events, handling:
    - Asset loading and caching
    - Volume control per channel
    - Effect-to-sound mapping
    - Spam prevention
    """
    
    # Category to channel mapping
    CATEGORY_TO_CHANNEL = {
        "combat": AudioChannel.COMBAT,
        "trading": AudioChannel.TRADING,
        "ship": AudioChannel.SHIP,
        "planet": AudioChannel.PLANET,
        "alert": AudioChannel.ALERT,
        "ui": AudioChannel.UI,
        "music": AudioChannel.MUSIC,
    }
    
    # Default volume per channel
    DEFAULT_VOLUMES = {
        AudioChannel.COMBAT: 0.8,      # Weapons, hits, explosions
        AudioChannel.TRADING: 0.7,     # Transaction sounds
        AudioChannel.SHIP: 0.6,        # Engine, modules
        AudioChannel.PLANET: 0.65,     # Docking, scanning
        AudioChannel.ALERT: 0.85,      # Important warnings
        AudioChannel.UI: 0.5,          # Menu interactions
        AudioChannel.MUSIC: 0.6,       # Background music
        AudioChannel.AMBIENT: 0.3,     # Ambient loops
    }
    
    def __init__(self, audio_manager: Optional[AudioManager] = None):
        """
        Initialize audio playback integration.
        
        Args:
            audio_manager: AudioManager instance (from audio_helper.py)
        """
        self.audio_manager = audio_manager
        self.sound_cache: Dict[str, object] = {}  # Cached arcade.Sound objects
        self.channel_volumes = self.DEFAULT_VOLUMES.copy()
        self.enabled = True
        self.last_played = {}  # Track recently played sounds
        
        logger.info("AudioPlaybackIntegration initialized")
    
    def play_effect_sound(self, effect_name: str, intensity: float = 1.0) -> bool:
        """
        Play sound for an effect.
        
        Args:
            effect_name: Name of the effect sound to play
            intensity: Volume multiplier (0.0-1.5)
            
        Returns:
            True if sound played, False if not found or disabled
        """
        if not self.enabled:
            return False
        
        # Look up sound configuration
        if effect_name not in ALL_SOUNDS:
            logger.warning(f"Sound not found: {effect_name}")
            return False
        
        sound_config = ALL_SOUNDS[effect_name]
        channel = self.CATEGORY_TO_CHANNEL.get(sound_config.get("category"))
        
        if not channel:
            logger.warning(f"Unknown channel for sound: {effect_name}")
            return False
        
        # Calculate final volume
        base_volume = sound_config.get("volume", 1.0)
        channel_volume = self.channel_volumes[channel]
        final_volume = base_volume * channel_volume * intensity
        final_volume = max(0.0, min(1.0, final_volume))  # Clamp to 0-1
        
        # Get sound path and load/play
        sound_path = sound_config.get("path")
        if not sound_path:
            logger.warning(f"No path for sound: {effect_name}")
            return False
        
        try:
            if self.audio_manager:
                # Use AudioManager if available
                success = self._play_via_manager(
                    effect_name, sound_path, final_volume, 
                    sound_config.get("looping", False)
                )
            else:
                # Fallback: would use arcade directly
                success = self._play_via_arcade(
                    effect_name, sound_path, final_volume,
                    sound_config.get("looping", False)
                )
            
            if success:
                self.last_played[effect_name] = True
                logger.debug(f"Played sound: {effect_name} (vol: {final_volume:.2f})")
            
            return success
            
        except Exception as e:
            logger.error(f"Failed to play sound {effect_name}: {e}")
            return False
    
    def _play_via_manager(self, sound_name: str, path: str, 
                         volume: float, looping: bool) -> bool:
        """Play sound using AudioManager."""
        if not self.audio_manager:
            return False
        
        try:
            # AudioManager.play() interface
            self.audio_manager.play(sound_name, volume=volume)
            return True
        except Exception as e:
            logger.error(f"AudioManager play failed: {e}")
            return False
    
    def _play_via_arcade(self, sound_name: str, path: str,
                        volume: float, looping: bool) -> bool:
        """Play sound using arcade directly."""
        try:
            import arcade
            
            # Try to load from cache
            if sound_name not in self.sound_cache:
                try:
                    sound = arcade.load_sound(path)
                    self.sound_cache[sound_name] = sound
                except Exception as e:
                    logger.error(f"Failed to load sound {sound_name} from {path}: {e}")
                    return False
            
            sound = self.sound_cache[sound_name]
            
            # Play the sound
            player = arcade.play_sound(sound, volume=volume, looping=looping)
            return player is not None
            
        except Exception as e:
            logger.error(f"Arcade playback failed: {e}")
            return False
    
    def set_channel_volume(self, channel: AudioChannel, volume: float) -> None:
        """
        Set volume for a specific channel.
        
        Args:
            channel: AudioChannel to adjust
            volume: Volume level (0.0-1.0)
        """
        volume = max(0.0, min(1.0, volume))
        self.channel_volumes[channel] = volume
        logger.info(f"Set {channel.value} volume to {volume:.2f}")
    
    def set_all_volumes(self, volume: float) -> None:
        """Set volume for all channels."""
        volume = max(0.0, min(1.0, volume))
        for channel in AudioChannel:
            self.channel_volumes[channel] = volume
        logger.info(f"Set all channels volume to {volume:.2f}")
    
    def get_channel_volume(self, channel: AudioChannel) -> float:
        """Get current volume for a channel."""
        return self.channel_volumes.get(channel, 1.0)
    
    def disable(self) -> None:
        """Disable all audio playback."""
        self.enabled = False
        logger.info("Audio playback disabled")
    
    def enable(self) -> None:
        """Enable audio playback."""
        self.enabled = True
        logger.info("Audio playback enabled")
    
    def is_enabled(self) -> bool:
        """Check if audio is enabled."""
        return self.enabled
    
    def clear_sound_cache(self) -> None:
        """Clear cached sounds to free memory."""
        self.sound_cache.clear()
        logger.info("Sound cache cleared")
    
    def get_sound_info(self, sound_name: str) -> Optional[Dict]:
        """Get information about a sound."""
        if sound_name in ALL_SOUNDS:
            return ALL_SOUNDS[sound_name].copy()
        return None
    
    def get_channel_sounds(self, channel: AudioChannel) -> Dict[str, Dict]:
        """Get all sounds in a channel."""
        result = {}
        for sound_name, sound_config in ALL_SOUNDS.items():
            if sound_config.get("category") == channel.value:
                result[sound_name] = sound_config
        return result


# Global instance
audio_integration = AudioPlaybackIntegration()


def initialize_audio_integration(audio_manager: Optional[AudioManager] = None) -> None:
    """Initialize the global audio integration instance."""
    global audio_integration
    audio_integration = AudioPlaybackIntegration(audio_manager)


def play_effect_sound(effect_name: str, intensity: float = 1.0) -> bool:
    """Play sound for an effect effect."""
    return audio_integration.play_effect_sound(effect_name, intensity)


def set_channel_volume(channel: AudioChannel, volume: float) -> None:
    """Set volume for a channel."""
    audio_integration.set_channel_volume(channel, volume)


def set_all_volumes(volume: float) -> None:
    """Set volume for all channels."""
    audio_integration.set_all_volumes(volume)


def enable_audio() -> None:
    """Enable audio playback."""
    audio_integration.enable()


def disable_audio() -> None:
    """Disable audio playback."""
    audio_integration.disable()
