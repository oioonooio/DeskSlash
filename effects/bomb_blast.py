from __future__ import annotations

import math

import pygame

import game_config as config


class BombBlast:
    """Orange-red pixel shockwave with hard arcade edges."""

    def __init__(self, position: tuple[float, float] | pygame.Vector2) -> None:
        self._origin = pygame.Vector2(position)
        self._age = 0.0
        self._lifetime = config.BOMB_BLAST_LIFETIME
        radius = int(config.BOMB_BLAST_RADIUS_MAX) + 32
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
        if inverse <= 0.0:
            return
        self._layer.fill((0, 0, 0, 0))
        center = self._center
        snap = max(1, config.PIXEL_SNAP)
        radius = (
            config.BOMB_BLAST_RADIUS_MIN
            + (config.BOMB_BLAST_RADIUS_MAX - config.BOMB_BLAST_RADIUS_MIN)
            * (1.0 - inverse**3)
        )
        alpha = int(255 * inverse**1.2)

        # White-hot core for the first few frames.
        if progress < 0.4:
            core = max(4, int(radius * 0.35)) // snap * snap
            pygame.draw.rect(
                self._layer,
                (*config.BOMB_CORE_COLOR, alpha),
                (center[0] - core // 2, center[1] - core // 2, core, core),
            )

        rings = (
            (1.0, config.COLOR_NEON_ORANGE, 0.9),
            (0.72, config.COLOR_NEON_RED, 0.7),
            (0.46, config.COLOR_NEON_YELLOW, 0.6),
        )
        for scale, color, strength in rings:
            ring_radius = max(4.0, radius * scale)
            points = _jagged_diamond(center, ring_radius, progress * 10.0 + scale * 7.0)
            width = max(2, int(8 * inverse * strength)) // snap * snap
            # Faint fill turns the outlines into a solid pixel fireball.
            pygame.draw.polygon(
                self._layer,
                (*color, int(alpha * strength * 0.18)),
                points,
            )
            pygame.draw.polygon(
                self._layer,
                (*color, int(alpha * strength)),
                points,
                max(2, width),
            )

        # Pixel shrapnel bars flying out on the axes.
        arm = int(radius * 1.15) // snap * snap
        thickness = max(2, int(9 * inverse)) // snap * snap
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            pygame.draw.line(
                self._layer,
                (*config.COLOR_NEON_ORANGE, int(alpha * 0.75)),
                (center[0] + dx * arm * 0.25, center[1] + dy * arm * 0.25),
                (center[0] + dx * arm, center[1] + dy * arm),
                thickness,
            )

        surface.blit(
            self._layer,
            (round(self._origin.x - center[0]), round(self._origin.y - center[1])),
            special_flags=pygame.BLEND_RGBA_ADD,
        )


def _jagged_diamond(
    center: tuple[int, int],
    radius: float,
    phase: float,
) -> list[tuple[int, int]]:
    points: list[tuple[int, int]] = []
    for index in range(8):
        angle = math.tau * index / 8.0 + math.pi / 4.0
        wobble = 1.0 + 0.16 * math.sin(phase + index * 2.3)
        points.append(
            (
                round(center[0] + math.cos(angle) * radius * wobble),
                round(center[1] + math.sin(angle) * radius * wobble),
            )
        )
    return points
