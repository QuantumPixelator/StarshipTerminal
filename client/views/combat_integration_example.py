"""
Example: Combat System with Audio-Visual Effects Integration.

Complete working example showing how to integrate the effects
orchestrator with a combat system. Can be adapted for other game areas.
"""

import sys
import os
from typing import Optional, Tuple
import random
import logging

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'server'))

from views.effects_orchestrator import orchestrator


logger = logging.getLogger("combat_example")


class CombatantStats:
    """Simple stat container for combat example."""
    
    def __init__(self, name: str, max_hp: int = 100, max_shields: int = 50):
        """Initialize combatant stats."""
        self.name = name
        self.max_hp = max_hp
        self.max_shields = max_shields
        self.hull_hp = max_hp
        self.shields = max_shields
        self.alive = True
    
    def damage_shields(self, amount: float) -> float:
        """Damage shields, return overflow damage."""
        damage_absorbed = min(self.shields, amount)
        self.shields -= damage_absorbed
        return amount - damage_absorbed
    
    def damage_hull(self, amount: float) -> None:
        """Damage hull."""
        self.hull_hp -= amount
        if self.hull_hp <= 0:
            self.hull_hp = 0
            self.alive = False
    
    def is_alive(self) -> bool:
        """Check if combatant is still alive."""
        return self.alive and self.hull_hp > 0
    
    def get_health_percent(self) -> float:
        """Get health as percentage (0-1)."""
        return max(0, min(1.0, self.hull_hp / self.max_hp))
    
    def get_shield_percent(self) -> float:
        """Get shield as percentage (0-1)."""
        return max(0, min(1.0, self.shields / self.max_shields))


class CombatSystemExample:
    """
    Example combat system with audio-visual effects integration.
    
    Demonstrates:
    - Combat initialization
    - Attack resolution with effects
    - Damage application with feedback
    - Combat conclusion
    """
    
    def __init__(self):
        """Initialize combat system."""
        self.player = None
        self.enemy = None
        self.turn_count = 0
        self.in_combat = False
        self.combat_center = (400, 300)  # Screen center
        self.player_position = (200, 300)
        self.enemy_position = (600, 300)
        self.log = []
        
        logger.info("CombatSystemExample initialized")
    
    def start_combat(self, player_stats: CombatantStats, 
                    enemy_stats: CombatantStats) -> None:
        """
        Initialize combat with two combatants.
        
        Args:
            player_stats: Player's CombatantStats
            enemy_stats: Enemy's CombatantStats
        """
        self.player = player_stats
        self.enemy = enemy_stats
        self.turn_count = 0
        self.in_combat = True
        self.log = []
        
        # Trigger combat start effect
        orchestrator.trigger_effect('combat', 'combat_start',
                                   location=self.combat_center)
        
        self.log.append(f"Combat started: {self.player.name} vs {self.enemy.name}")
        logger.info(f"Combat started: {self.player.name} vs {self.enemy.name}")
    
    def execute_combat_round(self) -> bool:
        """
        Execute one complete combat round.
        
        Returns:
            True if combat continues, False if combat ended
        """
        if not self.in_combat or not self.player.is_alive() or not self.enemy.is_alive():
            return False
        
        self.turn_count += 1
        self.log.append(f"\n=== Round {self.turn_count} ===")
        
        # Player action
        player_success = self._resolve_player_attack()
        
        # Enemy counter-attack (if still alive)
        if self.enemy.is_alive():
            enemy_success = self._resolve_enemy_attack()
        
        # Check for combat end
        if not self.enemy.is_alive():
            self._end_combat(victory=True)
            return False
        
        if not self.player.is_alive():
            self._end_combat(victory=False)
            return False
        
        return True
    
    def _resolve_player_attack(self) -> bool:
        """
        Resolve player attack with audio-visual feedback.
        
        Returns:
            True if attack landed, False if missed
        """
        # Roll for hit
        base_accuracy = 0.75
        hit_roll = random.random()
        hits = hit_roll < base_accuracy
        
        self.log.append(f"{self.player.name} attacks...")
        
        if not hits:
            # Miss effect (no audio, just visual)
            self.log.append("  MISS!")
            return False
        
        # Determine attack strength
        base_damage = random.uniform(8, 15)
        critical_chance = 0.15
        is_critical = random.random() < critical_chance
        
        if is_critical:
            base_damage *= 1.5
        
        # Show attack effect
        orchestrator.trigger_player_fires(
            location=self.enemy_position,
            intensity=1.0
        )
        
        # Apply damage to enemy
        shield_overflow = self.enemy.damage_shields(base_damage * 0.7)
        
        if self.enemy.shields > 0:
            # Shields still up
            orchestrator.trigger_shield_hit(
                location=self.enemy_position,
                is_player=False,
                intensity=1.0
            )
            self.log.append(f"  Hit! {base_damage * 0.7:.0f} absorbed by shields. "
                          f"Shields: {self.enemy.shields:.0f}")
        else:
            # Shields down, hit hull
            self.enemy.damage_hull(shield_overflow)
            
            if is_critical:
                orchestrator.trigger_critical_hit(
                    location=self.enemy_position,
                    intensity=1.5
                )
                self.log.append(f"  CRITICAL HIT! {shield_overflow:.0f} hull damage! "
                              f"Hull: {self.enemy.hull_hp:.0f}/{self.enemy.max_hp}")
            else:
                orchestrator.trigger_hull_damage(
                    location=self.enemy_position,
                    is_player=False,
                    intensity=1.0
                )
                self.log.append(f"  Hit! {shield_overflow:.0f} hull damage. "
                              f"Hull: {self.enemy.hull_hp:.0f}/{self.enemy.max_hp}")
        
        return True
    
    def _resolve_enemy_attack(self) -> bool:
        """
        Resolve enemy counter-attack with audio-visual feedback.
        
        Returns:
            True if attack landed, False if missed
        """
        # Roll for hit
        base_accuracy = 0.70
        hit_roll = random.random()
        hits = hit_roll < base_accuracy
        
        self.log.append(f"{self.enemy.name} counter-attacks...")
        
        if not hits:
            self.log.append("  MISS!")
            return False
        
        # Determine attack strength
        base_damage = random.uniform(6, 12)
        
        # Show attack effect
        orchestrator.trigger_enemy_fires(
            location=self.player_position,
            intensity=0.85
        )
        
        # Apply damage to player
        shield_overflow = self.player.damage_shields(base_damage * 0.7)
        
        if self.player.shields > 0:
            # Shields still up
            orchestrator.trigger_shield_hit(
                location=self.player_position,
                is_player=True,
                intensity=1.2
            )
            self.log.append(f"  Hit! {base_damage * 0.7:.0f} absorbed by shields. "
                          f"Shields: {self.player.shields:.0f}")
        else:
            # Shields down, hit hull
            self.player.damage_hull(shield_overflow)
            
            # Check if hull critically low
            if self.player.hull_hp < self.player.max_hp * 0.25:
                orchestrator.trigger_shield_low(
                    location=self.player_position
                )
            else:
                orchestrator.trigger_hull_damage(
                    location=self.player_position,
                    is_player=True,
                    intensity=1.3
                )
            
            self.log.append(f"  Hit! {shield_overflow:.0f} hull damage! "
                          f"Hull: {self.player.hull_hp:.0f}/{self.player.max_hp}")
        
        return True
    
    def _end_combat(self, victory: bool) -> None:
        """
        End combat with appropriate feedback.
        
        Args:
            victory: True if player won, False if defeated
        """
        self.in_combat = False
        
        if victory:
            orchestrator.trigger_combat_victory(location=self.combat_center)
            self.log.append(f"\n*** VICTORY! {self.enemy.name} defeated! ***")
            logger.info(f"Combat victory in {self.turn_count} rounds")
        else:
            orchestrator.trigger_combat_defeat(location=self.combat_center)
            self.log.append(f"\n*** DEFEAT! {self.player.name} destroyed! ***")
            logger.info(f"Combat defeat in {self.turn_count} rounds")
    
    def get_combat_log(self) -> str:
        """Get formatted combat log."""
        return "\n".join(self.log)
    
    def get_stats(self) -> dict:
        """Get current combat stats."""
        return {
            'round': self.turn_count,
            'player_hull': self.player.hull_hp if self.player else 0,
            'player_shields': self.player.shields if self.player else 0,
            'enemy_hull': self.enemy.hull_hp if self.enemy else 0,
            'enemy_shields': self.enemy.shields if self.enemy else 0,
            'in_combat': self.in_combat,
        }


# Example usage
def demo_combat():
    """
    Demonstrate the combat system with effects.
    
    This would normally be called from game code when
    players encounter enemies.
    """
    
    # Initialize combat system
    combat = CombatSystemExample()
    
    # Create combatants
    player = CombatantStats("Player", max_hp=100, max_shields=50)
    enemy = CombatantStats("Enemy Fighter", max_hp=80, max_shields=40)
    
    # Start combat
    combat.start_combat(player, enemy)
    
    # Run combat rounds
    round_count = 0
    max_rounds = 20  # Safety limit
    
    while round_count < max_rounds:
        # Execute one round
        if not combat.execute_combat_round():
            break
        
        round_count += 1
        
        # In real game, this would be spread across multiple frames
        # For demo, we just continue
    
    # Print results
    print(combat.get_combat_log())
    print("\nFinal Stats:", combat.get_stats())
    
    return combat


if __name__ == "__main__":
    # Demo the system
    combat = demo_combat()
