from __future__ import annotations

import math
from dataclasses import dataclass, field

import pygame

import game_config as config
from physics.body import PhysicsBody


@dataclass
class GameIcon:
    """A flying desktop icon backed by a fixed-timestep physics body."""

    body: PhysicsBody
    image: pygame.Surface
    angle: float = 0.0
    spin: float = 0.0
    scale: float = 1.0
    base_scale: float | None = None
    name: str = ""
    sliced: bool = False
    missed: bool = False
    entered: bool = False
    is_bomb: bool = False
    _scaled_cache: tuple[float, pygame.Surface] | None = field(
        default=None, init=False, repr=False
    )
    _shadow_cache: tuple[float, pygame.Surface] | None = field(
        default=None, init=False, repr=False
    )
    _glow_cache: tuple[float, pygame.Surface | None] | None = field(
        default=None, init=False, repr=False
    )
    _age: float = field(default=0.0, init=False, repr=False)
    _breathe_phase: float = field(default=0.0, init=False, repr=False)

    def __post_init__(self) -> None:
        if self.base_scale is None:
            self.base_scale = self.scale
        # Offset the breathing cycle per icon so a wave never pulses in sync.
        self._breathe_phase = (
            self.body.position.x * 0.021 + self.body.position.y * 0.013
        ) % math.tau

    @property
    def position(self) -> pygame.Vector2:
        return self.body.position

    @property
    def velocity(self) -> pygame.Vector2:
        return self.body.velocity

    @property
    def velocity_x(self) -> float:
        return self.body.velocity.x

    @property
    def velocity_y(self) -> float:
        return self.body.velocity.y

    @property
    def gravity(self) -> float:
        return config.PHYSICS_GRAVITY[1] * self.body.gravity_scale

    @property
    def hit_radius(self) -> float:
        width, height = self.image.get_size()
        return 0.5 * math.hypot(width, height) * self.scale * config.ICON_HITBOX_SCALE

    @property
    def alive(self) -> bool:
        return self.body.alive and not self.sliced and not self.missed

    def update(self, dt: float) -> None:
        self.angle = (self.angle + self.spin * dt) % 360.0
        if config.ICON_BREATHE_AMPLITUDE <= 0.0:
            return
        self._age += dt
        wave = math.sin(
            self._age * (math.tau / config.ICON_BREATHE_PERIOD) + self._breathe_phase
        )
        target = self.base_scale * (1.0 + config.ICON_BREATHE_AMPLITUDE * wave)
        quantum = config.ICON_SCALE_QUANTUM
        self.scale = round(target / quantum) * quantum

    def stop(self) -> None:
        self.body.alive = False

    def _scaled_image(self) -> pygame.Surface:
        """Scale once per icon instead of rotozooming scale every frame."""
        if self._scaled_cache is not None and self._scaled_cache[0] == self.scale:
            return self._scaled_cache[1]
        width = max(1, round(self.image.get_width() * self.scale))
        height = max(1, round(self.image.get_height() * self.scale))
        scaled = pygame.transform.smoothscale(self.image, (width, height))
        self._scaled_cache = (self.scale, scaled)
        self._shadow_cache = None
        return scaled

    def _shadow_image(self) -> pygame.Surface:
        if self._shadow_cache is not None and self._shadow_cache[0] == self.scale:
            return self._shadow_cache[1]
        shadow = self._scaled_image().copy()
        shadow.fill((0, 0, 0, 90), special_flags=pygame.BLEND_RGBA_MULT)
        self._shadow_cache = (self.scale, shadow)
        return shadow

    def _glow_image(self) -> pygame.Surface | None:
        """Soft halo derived from the icon alpha, rebuilt per scale step.

        The silhouette is rendered at quarter resolution and upscaled, which
        blurs it for far less cost than a per-pixel convolution.
        """
        if not config.ICON_GLOW_ENABLED:
            return None
        if self._glow_cache is not None and self._glow_cache[0] == self.scale:
            return self._glow_cache[1]
        scaled = self._scaled_image()
        width, height = scaled.get_size()
        mask = pygame.mask.from_surface(scaled, 32)
        if mask.count() == 0:
            self._glow_cache = (self.scale, None)
            return None
        pad = max(4, round(max(width, height) * config.ICON_GLOW_PADDING))
        tinted = mask.to_surface(
            setcolor=(*config.ICON_GLOW_COLOR, config.ICON_GLOW_ALPHA),
            unsetcolor=(0, 0, 0, 0),
        )
        small = pygame.transform.smoothscale(
            tinted, (max(1, width // 4), max(1, height // 4))
        )
        glow = pygame.transform.smoothscale(
            small, (width + pad * 2, height + pad * 2)
        )
        self._glow_cache = (self.scale, glow)
        return glow

    def current_surface(self) -> pygame.Surface:
        """The icon as currently rotated and scaled on screen."""
        scaled = self._scaled_image()
        if abs(self.angle % 360.0) < 0.01:
            return scaled
        return pygame.transform.rotate(scaled, self.angle)

    def draw(self, surface: pygame.Surface) -> None:
        image = self.current_surface()
        rect = image.get_rect(center=(round(self.position.x), round(self.position.y)))

        glow = self._glow_image()
        if glow is not None:
            surface.blit(glow, glow.get_rect(center=rect.center))

        if self.is_bomb:
            pulse = 0.5 + 0.5 * math.sin(math.radians(self.angle) * 3.0)
            size = rect.width * 0.62 + 6.0 + 4.0 * pulse
            color = config.COLOR_NEON_ORANGE if pulse > 0.5 else config.COLOR_NEON_RED
            points = [
                (rect.centerx, rect.centery - size),
                (rect.centerx + size, rect.centery),
                (rect.centerx, rect.centery + size),
                (rect.centerx - size, rect.centery),
            ]
            pygame.draw.polygon(surface, color, points, 2)

        shadow = self._shadow_image()
        if abs(self.angle % 360.0) >= 0.01:
            shadow = pygame.transform.rotate(shadow, self.angle)
        surface.blit(shadow, rect.move(3, 5))
        surface.blit(image, rect)
