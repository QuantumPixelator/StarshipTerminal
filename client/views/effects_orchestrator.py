"""
Unified Effects Orchestrator for Audio-Visual Integration.

Coordinates audio playback and visual particle effects for cohesive,
immersive gameplay feedback. Main integration point for effects system.
"""

from typing import Tuple, Optional, Dict
import logging

from .effects_manager import IntegratedEffectsManager, play_combat_effect
from .audio_playback_integration import (
    AudioPlaybackIntegration,
    AudioChannel,
    audio_integration,
    play_effect_sound,
)
from .particle_system import particle_system, create_particle_effect


logger = logging.getLogger("effects_orchestrator")


class EffectsOrchestrator:
    """
    Orchestrates all audio-visual effects in the game.
    
    Coordinates between:
    - Effects manager (configuration and timing)
    - Audio system (sound playback)
    - Particle system (visual effects)
    - Game systems (combat, trading, ship, etc.)
    """
    
    def __init__(self, audio_manager=None):
        """Initialize the orchestrator."""
        self.effects_manager = IntegratedEffectsManager()
        self.audio_integration = AudioPlaybackIntegration(audio_manager)
        self.particle_system = particle_system
        self.enabled = True
        
        logger.info("EffectsOrchestrator initialized")
    
    def trigger_effect(self, effect_type: str, effect_name: str,
                      location: Tuple[int, int] = (0, 0),
                      intensity: float = 1.0) -> bool:
        """
        Trigger a coordinated audio-visual effect.
        
        Args:
            effect_type: Category ('combat', 'trading', 'ship', etc.)
            effect_name: Name of specific effect
            location: Screen coordinates for effect
            intensity: Effect strength (0.0-1.5)
            
        Returns:
            True if effect triggered, False otherwise
        """
        if not self.enabled:
            return False
        
        # Trigger via manager based on type
        trigger_map = {
            'combat': self.effects_manager.trigger_combat_effect,
            'trading': self.effects_manager.trigger_trading_effect,
            'ship': self.effects_manager.trigger_ship_effect,
            'planet': self.effects_manager.trigger_planet_effect,
            'alert': self.effects_manager.trigger_alert_effect,
            'ui': self.effects_manager.trigger_ui_effect,
        }
        
        trigger_func = trigger_map.get(effect_type)
        if not trigger_func:
            logger.warning(f"Unknown effect type: {effect_type}")
            return False
        
        # Get effect configuration
        if not trigger_func(effect_name, location, intensity):
            return False
        
        config = self.effects_manager.get_effect_config(effect_name)
        if not config:
            return False
        
        # Play audio
        audio_name = config.get("audio")
        if audio_name:
            self.audio_integration.play_effect_sound(audio_name, intensity)
        
        # Create visual effect
        visual_name = config.get("visual")
        if visual_name:
            self.particle_system.create_effect(visual_name, location[0], location[1], intensity)
        
        logger.debug(f"Triggered {effect_type} effect: {effect_name}")
        return True
    
    # Combat effects shortcuts
    def trigger_combat_effect(self, effect_name: str,
                            location: Tuple[int, int] = (0, 0),
                            intensity: float = 1.0) -> bool:
        """Trigger a combat effect."""
        return self.trigger_effect('combat', effect_name, location, intensity)
    
    def trigger_player_fires(self, location: Tuple[int, int], intensity: float = 1.0) -> bool:
        """Player shoots weapon."""
        return self.trigger_combat_effect('player_fires', location, intensity)
    
    def trigger_enemy_fires(self, location: Tuple[int, int], intensity: float = 1.0) -> bool:
        """Enemy shoots weapon."""
        return self.trigger_combat_effect('enemy_fires', location, intensity)
    
    def trigger_shield_hit(self, location: Tuple[int, int], is_player: bool = True,
                          intensity: float = 1.0) -> bool:
        """Shield takes a hit."""
        effect = 'shield_hit_player' if is_player else 'shield_hit_target'
        return self.trigger_combat_effect(effect, location, intensity)
    
    def trigger_hull_damage(self, location: Tuple[int, int], is_player: bool = True,
                           intensity: float = 1.0) -> bool:
        """Hull takes damage."""
        effect = 'hull_damage_player' if is_player else 'hull_damage_target'
        return self.trigger_combat_effect(effect, location, intensity)
    
    def trigger_critical_hit(self, location: Tuple[int, int], intensity: float = 1.5) -> bool:
        """Critical hit explosion."""
        return self.trigger_combat_effect('critical_hit', location, intensity)
    
    def trigger_special_weapon(self, location: Tuple[int, int], intensity: float = 1.4) -> bool:
        """Special weapon fired."""
        return self.trigger_combat_effect('special_weapon_fire', location, intensity)
    
    def trigger_combat_victory(self, location: Tuple[int, int]) -> bool:
        """Combat victory."""
        return self.trigger_combat_effect('combat_victory', location, 1.2)
    
    def trigger_combat_defeat(self, location: Tuple[int, int]) -> bool:
        """Combat defeat."""
        return self.trigger_combat_effect('combat_defeat', location, 1.1)
    
    # Trading effects shortcuts
    def trigger_trading_effect(self, effect_name: str,
                             location: Tuple[int, int] = (0, 0),
                             intensity: float = 1.0) -> bool:
        """Trigger a trading effect."""
        return self.trigger_effect('trading', effect_name, location, intensity)
    
    def trigger_purchase(self, location: Tuple[int, int]) -> bool:
        """Item purchased."""
        return self.trigger_trading_effect('purchase', location, 0.9)
    
    def trigger_sale(self, location: Tuple[int, int]) -> bool:
        """Item sold."""
        return self.trigger_trading_effect('sale', location, 0.9)
    
    def trigger_contract_complete(self, location: Tuple[int, int]) -> bool:
        """Contract completed."""
        return self.trigger_trading_effect('contract_complete', location, 1.1)
    
    # Ship effects shortcuts
    def trigger_ship_effect(self, effect_name: str,
                           location: Tuple[int, int] = (0, 0),
                           intensity: float = 1.0) -> bool:
        """Trigger a ship effect."""
        return self.trigger_effect('ship', effect_name, location, intensity)
    
    def trigger_module_install(self, location: Tuple[int, int]) -> bool:
        """Module installed."""
        return self.trigger_ship_effect('module_install', location, 1.0)
    
    def trigger_upgrade_install(self, location: Tuple[int, int]) -> bool:
        """Upgrade installed."""
        return self.trigger_ship_effect('upgrade_install', location, 1.0)
    
    def trigger_jump(self, location: Tuple[int, int]) -> bool:
        """Jump executed."""
        return self.trigger_ship_effect('jump_execute', location, 1.2)
    
    def trigger_shield_low(self, location: Tuple[int, int]) -> bool:
        """Shields critically low."""
        return self.trigger_ship_effect('shield_low', location, 1.1)
    
    # Planet effects shortcuts
    def trigger_planet_effect(self, effect_name: str,
                            location: Tuple[int, int] = (0, 0),
                            intensity: float = 1.0) -> bool:
        """Trigger a planet effect."""
        return self.trigger_effect('planet', effect_name, location, intensity)
    
    def trigger_planet_docking(self, location: Tuple[int, int]) -> bool:
        """Planet docking."""
        return self.trigger_planet_effect('planet_docking', location, 0.9)
    
    def trigger_planet_scan(self, location: Tuple[int, int]) -> bool:
        """Planet scanned."""
        return self.trigger_planet_effect('planet_scan', location, 0.7)
    
    # Alert effects shortcuts
    def trigger_alert_effect(self, effect_name: str,
                            location: Tuple[int, int] = (0, 0),
                            intensity: float = 1.0) -> bool:
        """Trigger an alert effect."""
        return self.trigger_effect('alert', effect_name, location, intensity)
    
    def trigger_target_acquired(self, location: Tuple[int, int]) -> bool:
        """Target acquired."""
        return self.trigger_alert_effect('target_acquired', location, 1.0)
    
    def trigger_enemy_detected(self, location: Tuple[int, int]) -> bool:
        """Enemy detected."""
        return self.trigger_alert_effect('enemy_detected', location, 1.2)
    
    def trigger_alarm(self, location: Tuple[int, int]) -> bool:
        """Alarm alert."""
        return self.trigger_alert_effect('alarm', location, 1.4)
    
    # UI effects shortcuts
    def trigger_ui_effect(self, effect_name: str,
                         location: Tuple[int, int] = (0, 0),
                         intensity: float = 1.0) -> bool:
        """Trigger a UI effect."""
        return self.trigger_effect('ui', effect_name, location, intensity)
    
    def trigger_ui_confirm(self, location: Tuple[int, int]) -> bool:
        """UI confirmation."""
        return self.trigger_ui_effect('confirm', location, 0.8)
    
    def trigger_ui_error(self, location: Tuple[int, int]) -> bool:
        """UI error."""
        return self.trigger_ui_effect('error', location, 1.0)
    
    # State management
    def update(self, delta_time: float) -> None:
        """Update all effect systems."""
        self.effects_manager.update(delta_time)
        self.particle_system.update(delta_time)
    
    def draw(self) -> None:
        """Draw all visual effects."""
        self.particle_system.draw()
    
    def enable(self) -> None:
        """Enable effects."""
        self.enabled = True
        self.audio_integration.enable()
        logger.info("Effects enabled")
    
    def disable(self) -> None:
        """Disable effects."""
        self.enabled = False
        self.audio_integration.disable()
        logger.info("Effects disabled")
    
    def set_effect_volume(self, channel: AudioChannel, volume: float) -> None:
        """Set volume for an effect channel."""
        self.audio_integration.set_channel_volume(channel, volume)
    
    def get_stats(self) -> Dict[str, int]:
        """Get current effect system statistics."""
        return {
            'active_effects': len(self.effects_manager.get_active_effects()),
            'particle_emitters': self.particle_system.get_emitter_count(),
            'total_particles': self.particle_system.get_particle_count(),
        }


# Global orchestrator instance
orchestrator = EffectsOrchestrator()


def initialize_orchestrator(audio_manager=None) -> EffectsOrchestrator:
    """Initialize the global orchestrator."""
    global orchestrator
    orchestrator = EffectsOrchestrator(audio_manager)
    return orchestrator


def get_orchestrator() -> EffectsOrchestrator:
    """Get the global orchestrator."""
    return orchestrator


# Convenience functions
def trigger_effect(effect_type: str, effect_name: str,
                  location: Tuple[int, int] = (0, 0),
                  intensity: float = 1.0) -> bool:
    """Trigger an effect through the global orchestrator."""
    return orchestrator.trigger_effect(effect_type, effect_name, location, intensity)


def update_effects(delta_time: float) -> None:
    """Update all effects."""
    orchestrator.update(delta_time)


def draw_effects() -> None:
    """Draw all visual effects."""
    orchestrator.draw()


def get_effect_stats() -> Dict[str, int]:
    """Get effect system statistics."""
    return orchestrator.get_stats()
