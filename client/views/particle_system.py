"""
Particle System for Visual Effects.

Implements particle emitters and rendering for visual effect
feedback during gameplay. Supports burst and continuous emission.
"""

from typing import List, Tuple, Optional
from dataclasses import dataclass, field
import math
import random
import logging


logger = logging.getLogger("particle_system")


@dataclass
class Particle:
    """Represents a single particle in the system."""
    x: float
    y: float
    vx: float  # Velocity X
    vy: float  # Velocity Y
    lifetime: float  # Remaining lifetime in seconds
    max_lifetime: float  # Original lifetime
    color: Tuple[int, int, int]
    size: float
    rotation: float = 0.0
    angular_velocity: float = 0.0
    
    def update(self, delta_time: float) -> bool:
        """
        Update particle position and lifetime.
        
        Returns:
            True if particle still alive, False if expired
        """
        self.x += self.vx * delta_time
        self.y += self.vy * delta_time
        self.lifetime -= delta_time
        self.rotation += self.angular_velocity * delta_time
        
        return self.lifetime > 0
    
    def get_alpha(self) -> float:
        """Get current alpha (opacity) for fade out."""
        return max(0.0, self.lifetime / self.max_lifetime)


@dataclass
class ParticleEmitter:
    """Emits particles for visual effects."""
    x: float
    y: float
    velocity_min: float = 100.0
    velocity_max: float = 300.0
    angle_min: float = 0.0
    angle_max: float = 360.0
    particle_lifetime: float = 1.0
    emission_rate: float = 50.0  # Particles per second
    color: Tuple[int, int, int] = (255, 255, 255)
    particle_size: float = 2.0
    particles: List[Particle] = field(default_factory=list)
    time_since_emission: float = 0.0
    burst_count: Optional[int] = None  # None = continuous, int = burst
    total_emitted: int = 0
    
    def update(self, delta_time: float) -> None:
        """Update emitter and emit new particles."""
        # Update existing particles
        dead_particles = []
        for i, particle in enumerate(self.particles):
            if not particle.update(delta_time):
                dead_particles.append(i)
        
        # Remove dead particles (in reverse to maintain indices)
        for i in reversed(dead_particles):
            self.particles.pop(i)
        
        # Emit new particles
        if self.burst_count is None:
            # Continuous emission
            self.time_since_emission += delta_time
            particles_to_emit = int(self.time_since_emission * self.emission_rate)
            
            if particles_to_emit > 0:
                self.emit_particles(particles_to_emit)
                self.time_since_emission -= particles_to_emit / self.emission_rate
        elif self.total_emitted < self.burst_count:
            # Burst emission
            remaining = self.burst_count - self.total_emitted
            self.emit_particles(min(remaining, int(delta_time * self.emission_rate * 10)))
    
    def emit_particles(self, count: int) -> None:
        """Emit specified number of particles."""
        for _ in range(count):
            velocity = random.uniform(self.velocity_min, self.velocity_max)
            angle = random.uniform(self.angle_min, self.angle_max)
            angle_rad = math.radians(angle)
            
            vx = velocity * math.cos(angle_rad)
            vy = velocity * math.sin(angle_rad)
            
            particle = Particle(
                x=self.x,
                y=self.y,
                vx=vx,
                vy=vy,
                lifetime=self.particle_lifetime,
                max_lifetime=self.particle_lifetime,
                color=self.color,
                size=self.particle_size,
            )
            
            self.particles.append(particle)
            self.total_emitted += 1
    
    def get_particle_count(self) -> int:
        """Get current number of particles."""
        return len(self.particles)
    
    def is_active(self) -> bool:
        """Check if emitter is still active."""
        if self.burst_count is None:
            return True
        return self.total_emitted < self.burst_count


class ParticleSystem:
    """
    Manages multiple particle emitters for visual effects.
    
    Handles creation, updating, and rendering of particle effects
    throughout the game.
    """
    
    def __init__(self, max_particles: int = 10000):
        """
        Initialize particle system.
        
        Args:
            max_particles: Maximum particles allowed at once
        """
        self.emitters: List[ParticleEmitter] = []
        self.max_particles = max_particles
        self.total_particles = 0
        
        logger.info(f"ParticleSystem initialized with max {max_particles} particles")
    
    def create_effect(self, effect_name: str, x: float, y: float,
                     intensity: float = 1.0) -> bool:
        """
        Create a particle effect by name.
        
        Args:
            effect_name: Name of effect to create
            x, y: Screen coordinates
            intensity: Effect strength multiplier
            
        Returns:
            True if effect created, False if not found
        """
        if self.total_particles >= self.max_particles:
            return False

        emitter = self._get_emitter_for_effect(effect_name, x, y, intensity)
        if emitter:
            self.emitters.append(emitter)
            return True
        return False
    
    def _get_emitter_for_effect(self, effect_name: str, x: float, y: float,
                               intensity: float) -> Optional[ParticleEmitter]:
        """Create emitter configuration for an effect."""
        
        # Explosion effects
        if "explosion" in effect_name:
            if "large" in effect_name:
                return ParticleEmitter(
                    x=x, y=y,
                    velocity_min=200.0 * intensity,
                    velocity_max=500.0 * intensity,
                    angle_min=0, angle_max=360,
                    particle_lifetime=1.2,
                    color=(255, 150, 0),
                    particle_size=4.0 * intensity,
                    burst_count=int(80 * intensity),
                )
            else:  # small explosion
                return ParticleEmitter(
                    x=x, y=y,
                    velocity_min=150.0 * intensity,
                    velocity_max=350.0 * intensity,
                    angle_min=0, angle_max=360,
                    particle_lifetime=0.8,
                    color=(255, 100, 0),
                    particle_size=2.0 * intensity,
                    burst_count=int(40 * intensity),
                )
        
        # Shield impact
        elif "shield" in effect_name:
            return ParticleEmitter(
                x=x, y=y,
                velocity_min=100.0 * intensity,
                velocity_max=250.0 * intensity,
                angle_min=0, angle_max=360,
                particle_lifetime=0.6,
                color=(0, 150, 255),
                particle_size=1.5 * intensity,
                burst_count=int(30 * intensity),
            )
        
        # Laser beam effect
        elif "laser" in effect_name:
            return ParticleEmitter(
                x=x, y=y,
                velocity_min=50.0 * intensity,
                velocity_max=150.0 * intensity,
                angle_min=0, angle_max=360,
                particle_lifetime=0.3,
                color=(0, 255, 150),
                particle_size=1.0 * intensity,
                burst_count=int(15 * intensity),
            )
        
        # Pulse wave effect
        elif "pulse" in effect_name:
            return ParticleEmitter(
                x=x, y=y,
                velocity_min=200.0 * intensity,
                velocity_max=400.0 * intensity,
                angle_min=0, angle_max=360,
                particle_lifetime=0.7,
                color=(255, 200, 0),
                particle_size=2.0 * intensity,
                burst_count=int(50 * intensity),
            )
        
        # Module effects
        elif "module" in effect_name or "scan" in effect_name:
            return ParticleEmitter(
                x=x, y=y,
                velocity_min=80.0 * intensity,
                velocity_max=200.0 * intensity,
                angle_min=0, angle_max=360,
                particle_lifetime=0.5,
                color=(64, 220, 255),
                particle_size=1.2 * intensity,
                burst_count=int(25 * intensity),
            )
        
        # Ion effect
        elif "ion" in effect_name:
            return ParticleEmitter(
                x=x, y=y,
                velocity_min=250.0 * intensity,
                velocity_max=500.0 * intensity,
                angle_min=0, angle_max=360,
                particle_lifetime=0.8,
                color=(100, 150, 255),
                particle_size=2.5 * intensity,
                burst_count=int(60 * intensity),
            )
        
        # Default effect
        else:
            return ParticleEmitter(
                x=x, y=y,
                velocity_min=100.0 * intensity,
                velocity_max=300.0 * intensity,
                angle_min=0, angle_max=360,
                particle_lifetime=0.6,
                color=(200, 200, 200),
                particle_size=1.5 * intensity,
                burst_count=int(30 * intensity),
            )
    
    def update(self, delta_time: float) -> None:
        """Update all emitters and particles."""
        delta_time = max(0.0, float(delta_time))
        # Update active emitters
        dead_emitters = []
        for i, emitter in enumerate(self.emitters):
            emitter.update(delta_time)
            if not emitter.is_active() and emitter.get_particle_count() <= 0:
                dead_emitters.append(i)
        
        # Remove dead emitters
        for i in reversed(dead_emitters):
            self.emitters.pop(i)
        
        # Calculate total particles
        self.total_particles = sum(len(e.particles) for e in self.emitters)
    
    def draw(self) -> None:
        """Draw all particles (arcade-based)."""
        try:
            import arcade
            
            for emitter in self.emitters:
                for particle in emitter.particles:
                    # Calculate alpha for fade out
                    alpha = int(255 * particle.get_alpha())
                    
                    # Draw particle as circle
                    arcade.draw_circle_filled(
                        particle.x,
                        particle.y,
                        particle.size,
                        (*particle.color[:3], alpha) if len(particle.color) == 3 else particle.color
                    )
        except Exception as e:
            logger.error(f"Failed to draw particles: {e}")
    
    def get_emitter_count(self) -> int:
        """Get number of active emitters."""
        return len(self.emitters)
    
    def get_particle_count(self) -> int:
        """Get total number of particles."""
        return self.total_particles
    
    def clear(self) -> None:
        """Clear all emitters and particles."""
        self.emitters.clear()
        self.total_particles = 0
        logger.info("Particle system cleared")


# Global instance
particle_system = ParticleSystem()


def create_particle_effect(effect_name: str, x: float, y: float,
                          intensity: float = 1.0) -> bool:
    """Create a particle effect."""
    return particle_system.create_effect(effect_name, x, y, intensity)


def update_particle_system(delta_time: float) -> None:
    """Update particle system."""
    particle_system.update(delta_time)


def draw_particles() -> None:
    """Draw all particles."""
    particle_system.draw()


def get_particle_stats() -> Tuple[int, int]:
    """Get particle system statistics (emitters, particles)."""
    return (particle_system.get_emitter_count(), particle_system.get_particle_count())
