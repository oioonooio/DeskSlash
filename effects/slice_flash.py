from __future__ import annotations

import pygame

import game_config as config


class SliceFlash:
    """The brief white pixel star that pops where the blade lands."""

    def __init__(
        self,
        position: tuple[float, float] | pygame.Vector2,
        color: tuple[int, int, int] = config.SLICE_FLASH_COLOR,
    ) -> None:
        self._origin = pygame.Vector2(position)
        self._color = color
        self._age = 0.0
        self._lifetime = config.SLICE_FLASH_LIFETIME
        radius = int(config.SLICE_FLASH_RADIUS_MAX) + 24
        self._layer = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
        self._center = (radius, radius)
        self.finished = False

    def update(self, dt: float) -> None:
        self._age += dt
        if self._age >= self._lifetime:
            self.finished = True

    def draw(self, surface: pygame.Surface) -> None:
        if self.finished:
            return
        progress = min(1.0, self._age / self._lifetime)
        inverse = 1.0 - progress
        radius = config.SLICE_FLASH_RADIUS_MIN + (
            config.SLICE_FLASH_RADIUS_MAX - config.SLICE_FLASH_RADIUS_MIN
        ) * (1.0 - inverse**2)
        alpha = int(255 * inverse**1.4)
        if alpha <= 0:
            return

        self._layer.fill((0, 0, 0, 0))
        center = self._center
        color = self._color
        ring = config.SLICE_FLASH_RING_COLOR
        snap = max(1, config.PIXEL_SNAP)

        core = max(2, int(radius * 0.18)) // snap * snap
        pygame.draw.rect(
            self._layer,
            (*color, alpha),
            (center[0] - core // 2, center[1] - core // 2, core, core),
        )

        length = int(radius)
        thickness = max(2, int(6 * inverse))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            pygame.draw.line(
                self._layer,
                (*color, int(alpha * 0.85)),
                (center[0], center[1]),
                (center[0] + dx * length, center[1] + dy * length),
                thickness,
            )
        diagonal = int(radius * 0.55)
        for dx, dy in ((1, 1), (-1, 1), (1, -1), (-1, -1)):
            pygame.draw.line(
                self._layer,
                (*ring, int(alpha * 0.5)),
                (center[0], center[1]),
                (center[0] + dx * diagonal, center[1] + dy * diagonal),
                max(1, thickness - 1),
            )

        size = int(radius * 0.9) // snap * snap
        half = size // 2
        points = [
            (center[0], center[1] - half),
            (center[0] + half, center[1]),
            (center[0], center[1] + half),
            (center[0] - half, center[1]),
        ]
        pygame.draw.polygon(self._layer, (*ring, int(alpha * 0.55)), points, 2)
        pygame.draw.rect(
            self._layer,
            (*color, int(alpha * 0.3)),
            (center[0] - half // 2, center[1] - half // 2, half, half),
        )

        surface.blit(
            self._layer,
            (round(self._origin.x - center[0]), round(self._origin.y - center[1])),
            special_flags=pygame.BLEND_RGBA_ADD,
        )
