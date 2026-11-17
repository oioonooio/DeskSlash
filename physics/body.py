from __future__ import annotations

from dataclasses import dataclass, field

import pygame

import game_config as config


@dataclass
class PhysicsBody:
    """A point-mass body integrated at the game's fixed timestep."""

    position: pygame.Vector2
    velocity: pygame.Vector2 = field(default_factory=pygame.Vector2)
    gravity_scale: float = 1.0
    alive: bool = True

    def apply_impulse(self, impulse: pygame.Vector2 | tuple[float, float]) -> None:
        self.velocity += pygame.Vector2(impulse)

    def integrate(self, dt: float) -> None:
        gravity = pygame.Vector2(config.PHYSICS_GRAVITY) * (self.gravity_scale * dt)
        self.velocity += gravity
        self.velocity *= max(0.0, 1.0 - config.PHYSICS_LINEAR_DRAG * dt)

        max_speed = config.PHYSICS_MAX_SPEED
        if self.velocity.length_squared() > max_speed * max_speed:
            self.velocity.scale_to_length(max_speed)

        self.position += self.velocity * dt
