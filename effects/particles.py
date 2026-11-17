from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

import game_config as config


@dataclass
class _Particle:
    active: bool = False
    x: float = 0.0
    y: float = 0.0
    vx: float = 0.0
    vy: float = 0.0
    gravity: float = 0.0
    age: float = 0.0
    lifetime: float = 0.0
    size: int = 2
    color: tuple[int, int, int] = (255, 255, 255)
    fade_power: float = 1.3
    shrink: bool = True


class PixelParticles:
    """A fixed-capacity pixel spark pool shared by every effect.

    Particles are reused in place: spawning never allocates and the pool never
    grows past ``config.PARTICLE_POOL_MAX``. When the pool is exhausted extra
    sparks are silently dropped, which keeps a busy slash from stalling a frame.
    """

    def __init__(
        self,
        capacity: int | None = None,
        rng: random.Random | None = None,
    ) -> None:
        self._capacity = max(1, capacity or config.PARTICLE_POOL_MAX)
        self._pool = [_Particle() for _ in range(self._capacity)]
        self._free = list(range(self._capacity))
        self._active = 0
        self._rng = rng or random.Random()
        self._overlay: pygame.Surface | None = None

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @property
    def capacity(self) -> int:
        return self._capacity

    @property
    def active_count(self) -> int:
        return self._active

    def clear(self) -> None:
        for particle in self._pool:
            particle.active = False
        self._free = list(range(self._capacity))
        self._active = 0

    # ------------------------------------------------------------------
    # Spawning
    # ------------------------------------------------------------------
    def burst(
        self,
        position: tuple[float, float] | pygame.Vector2,
        count: int = 18,
        colors: tuple[tuple[int, int, int], ...] | list[tuple[int, int, int]] | None = None,
        speed: tuple[float, float] = (config.PARTICLE_SPEED_MIN, config.PARTICLE_SPEED_MAX),
        lifetime: tuple[float, float] = (0.25, config.PARTICLE_LIFETIME),
        size: tuple[int, int] = (1, 4),
        gravity: float = config.PARTICLE_GRAVITY,
        spread: float = 360.0,
        direction: float | None = None,
    ) -> int:
        """Spray pixels in random directions around ``position``."""
        colors = colors or (
            config.COLOR_SLASH_CORE,
            config.COLOR_SLASH_GLOW,
            config.COLOR_PARTICLE,
        )
        origin = pygame.Vector2(position)
        base_angle = 0.0 if direction is None else direction
        for _ in range(max(0, count)):
            angle = base_angle + self._rng.uniform(-spread * 0.5, spread * 0.5)
            velocity = pygame.Vector2(1.0, 0.0).rotate(angle) * self._rng.uniform(
                speed[0], speed[1]
            )
            self._spawn(
                origin.x + velocity.x * 0.01,
                origin.y + velocity.y * 0.01,
                velocity.x,
                velocity.y,
                gravity,
                self._rng.uniform(lifetime[0], lifetime[1]),
                self._rng.randint(size[0], size[1]),
                self._rng.choice(colors),
            )
        return self._active

    def trail_sparks(
        self,
        position: tuple[float, float] | pygame.Vector2,
        direction: float | None = None,
    ) -> None:
        """A couple of small sparks clinging to a fast slash sample."""
        self.burst(
            position,
            count=config.SLASH_TRAIL_SPARK_COUNT,
            colors=config.SLASH_TRAIL_SPARK_COLORS,
            speed=config.SLASH_TRAIL_SPARK_SPEED,
            lifetime=config.SLASH_TRAIL_SPARK_LIFETIME,
            size=config.SLASH_TRAIL_SPARK_SIZE,
            gravity=config.SLASH_TRAIL_SPARK_GRAVITY,
            spread=120.0,
            direction=None if direction is None else direction + 180.0,
        )

    def slice_shards(
        self,
        position: tuple[float, float] | pygame.Vector2,
        image: pygame.Surface | None = None,
        count: int | None = None,
    ) -> int:
        """8-20 chunky pixels in the icon's own colours."""
        if count is None:
            count = self._rng.randint(config.SLICE_PIXEL_MIN, config.SLICE_PIXEL_MAX)
        colors = _sample_icon_colors(image, self._rng) if image is not None else None
        self.burst(
            position,
            count=count,
            colors=colors or config.SLICE_PIXEL_COLORS,
            speed=config.SLICE_PIXEL_SPEED,
            lifetime=config.SLICE_PIXEL_LIFETIME,
            size=config.SLICE_PIXEL_SIZE,
            gravity=config.SLICE_PIXEL_GRAVITY,
        )
        return self._active

    def ring(
        self,
        position: tuple[float, float] | pygame.Vector2,
        count: int = 18,
        radius: float = 22.0,
        speed: tuple[float, float] = (150.0, 260.0),
        colors: tuple[tuple[int, int, int], ...] = (
            config.COLOR_NEON_YELLOW,
            config.COLOR_NEON_CYAN,
        ),
        lifetime: tuple[float, float] = (0.22, 0.45),
        size: tuple[int, int] = (2, 4),
        gravity: float = 160.0,
    ) -> None:
        """Even radial ring used for combo milestones."""
        origin = pygame.Vector2(position)
        for index in range(max(0, count)):
            angle = 360.0 * index / count + self._rng.uniform(-4.0, 4.0)
            direction = pygame.Vector2(1.0, 0.0).rotate(angle)
            velocity = direction * self._rng.uniform(speed[0], speed[1])
            self._spawn(
                origin.x + direction.x * radius,
                origin.y + direction.y * radius,
                velocity.x,
                velocity.y,
                gravity,
                self._rng.uniform(lifetime[0], lifetime[1]),
                self._rng.randint(size[0], size[1]),
                self._rng.choice(colors),
            )

    def bomb_burst(
        self,
        position: tuple[float, float] | pygame.Vector2,
        count: int | None = None,
    ) -> int:
        count = config.BOMB_PARTICLE_COUNT if count is None else count
        self.burst(
            position,
            count=count,
            colors=config.BOMB_PARTICLE_COLORS,
            speed=config.BOMB_PARTICLE_SPEED,
            lifetime=config.BOMB_PARTICLE_LIFETIME,
            size=config.BOMB_PARTICLE_SIZE,
            gravity=config.BOMB_PARTICLE_GRAVITY,
        )
        self.ring(
            position,
            count=18,
            radius=12.0,
            speed=(320.0, 520.0),
            colors=(config.COLOR_WHITE_HOT, config.COLOR_NEON_YELLOW),
            lifetime=(0.12, 0.28),
            size=(2, 4),
            gravity=80.0,
        )
        return self._active

    # ------------------------------------------------------------------
    # Simulation
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        for index, particle in enumerate(self._pool):
            if not particle.active:
                continue
            particle.age += dt
            if particle.age >= particle.lifetime:
                particle.active = False
                self._free.append(index)
                self._active -= 1
                continue

            particle.vy += particle.gravity * dt
            particle.x += particle.vx * dt
            particle.y += particle.vy * dt

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        if self._active <= 0:
            return
        if self._overlay is None or self._overlay.get_size() != surface.get_size():
            self._overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        self._overlay.fill((0, 0, 0, 0))

        snap = max(1, config.PIXEL_SNAP)
        for particle in self._pool:
            if not particle.active:
                continue
            remaining = max(0.0, 1.0 - particle.age / particle.lifetime)
            alpha = int(255 * remaining**particle.fade_power)
            if alpha <= 0:
                continue
            size = particle.size
            if particle.shrink:
                size = max(1, int(round(size * (0.55 + 0.45 * remaining))))
            x = int(round(particle.x / snap)) * snap
            y = int(round(particle.y / snap)) * snap

            if size >= 4:
                glow = (
                    particle.color[0],
                    particle.color[1],
                    particle.color[2],
                    alpha // 4,
                )
                pygame.draw.rect(
                    self._overlay,
                    glow,
                    (x - size, y - size, size * 3, size * 3),
                )
            pygame.draw.rect(
                self._overlay,
                (*particle.color, alpha),
                (x - size // 2, y - size // 2, size, size),
            )

        if config.PARTICLE_ADDITIVE:
            surface.blit(self._overlay, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        else:
            surface.blit(self._overlay, (0, 0))

    # ------------------------------------------------------------------
    # Pool internals
    # ------------------------------------------------------------------
    def _spawn(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        gravity: float,
        lifetime: float,
        size: int,
        color: tuple[int, int, int],
    ) -> None:
        if not self._free:
            return
        index = self._free.pop()
        particle = self._pool[index]
        particle.active = True
        particle.x = x
        particle.y = y
        particle.vx = vx
        particle.vy = vy
        particle.gravity = gravity
        particle.age = 0.0
        particle.lifetime = max(0.02, lifetime)
        particle.size = max(1, size)
        particle.color = color
        particle.fade_power = self._rng.uniform(1.0, 1.7)
        particle.shrink = True
        self._active += 1


def _sample_icon_colors(
    image: pygame.Surface,
    rng: random.Random,
    limit: int = 24,
) -> list[tuple[int, int, int]]:
    width, height = image.get_size()
    colors: list[tuple[int, int, int]] = []
    samples = max(4, min(limit, width * height))
    for index in range(samples):
        angle = math.tau * index / samples
        radius = 0.5 * min(width, height) * (0.25 + 0.7 * ((index * 7) % samples) / samples)
        x = int(width * 0.5 + math.cos(angle) * radius)
        y = int(height * 0.5 + math.sin(angle) * radius)
        x = max(0, min(width - 1, x))
        y = max(0, min(height - 1, y))
        color = image.get_at((x, y))
        if color.a > 40:
            colors.append((color.r, color.g, color.b))
    if not colors:
        return list(config.SLICE_PIXEL_COLORS)
    rng.shuffle(colors)
    return colors
