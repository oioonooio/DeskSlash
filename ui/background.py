from __future__ import annotations

import math
import random
from dataclasses import dataclass

import pygame

import game_config as config


@dataclass
class _Mote:
    x: float
    y: float
    speed: float
    size: int
    color: tuple[int, int, int]
    alpha: int
    phase: float


class Background:
    """Pre-rendered synthwave grid plus drifting pixel dust.

    In overlay mode the game must reveal the real desktop, so the background is
    disabled and neither the large gradient surface nor its mote layer is
    allocated at all.
    """

    def __init__(self, size: tuple[int, int], enabled: bool = True) -> None:
        self._size = size
        self.enabled = enabled
        self._surface = self._build(size) if enabled else None
        self._motes = self._build_motes(size) if enabled else []
        self._mote_sprites = self._build_mote_sprites() if enabled else {}
        self._elapsed = 0.0

    def update(self, dt: float) -> None:
        if not self.enabled:
            return
        self._elapsed += dt
        width, height = self._size
        for mote in self._motes:
            mote.y -= mote.speed * dt
            mote.x += math.sin(self._elapsed * 0.7 + mote.phase) * 3.0 * dt
            if mote.y < -4.0:
                mote.y = height + 4.0
            if mote.x < -4.0:
                mote.x = width + 4.0
            elif mote.x > width + 4.0:
                mote.x = -4.0

    def draw(self, surface: pygame.Surface) -> None:
        if not self.enabled or self._surface is None:
            return
        surface.blit(self._surface, (0, 0))
        # Small cached sprites avoid clearing and blitting a full-screen layer
        # for only 64 drifting pixels.
        for mote in self._motes:
            sprite = self._mote_sprites[(mote.color, mote.alpha, mote.size)]
            surface.blit(sprite, (round(mote.x), round(mote.y)))

    # ------------------------------------------------------------------
    # Static art
    # ------------------------------------------------------------------
    @staticmethod
    def _build(size: tuple[int, int]) -> pygame.Surface:
        width, height = size
        surface = pygame.Surface(size).convert()
        top = pygame.Color(*config.COLOR_BACKGROUND_TOP)
        bottom = pygame.Color(*config.COLOR_BACKGROUND_BOTTOM)

        for y in range(height):
            t = y / max(1, height - 1)
            color = (
                round(top.r + (bottom.r - top.r) * t),
                round(top.g + (bottom.g - top.g) * t),
                round(top.b + (bottom.b - top.b) * t),
            )
            pygame.draw.line(surface, color, (0, y), (width, y))

        horizon_y = int(height * config.BACKGROUND_FLOOR_RATIO)
        glow = pygame.Surface(size, pygame.SRCALPHA)
        for offset in range(0, 22, 2):
            alpha = max(4, 52 - offset * 2)
            pygame.draw.line(
                glow,
                (*config.COLOR_BACKGROUND_HORIZON, alpha),
                (0, horizon_y - offset),
                (width, horizon_y - offset),
                2,
            )
            pygame.draw.line(
                glow,
                (*config.COLOR_NEON_MAGENTA, alpha // 2),
                (0, horizon_y + offset),
                (width, horizon_y + offset),
                2,
            )
        surface.blit(glow, (0, 0))

        grid = pygame.Surface(size, pygame.SRCALPHA)
        center_x = width // 2
        lines = max(2, config.BACKGROUND_PERSPECTIVE_LINES)
        for index in range(-lines, lines + 1):
            bottom_x = center_x + index * width / lines
            pygame.draw.line(
                grid,
                (*config.COLOR_GRID[:3], 30),
                (center_x, horizon_y),
                (bottom_x, height),
                1,
            )
        floor_height = max(1, height - horizon_y)
        for index in range(1, config.BACKGROUND_HORIZONTAL_LINES + 1):
            t = index / config.BACKGROUND_HORIZONTAL_LINES
            y = horizon_y + int(floor_height * t**1.9)
            alpha = int(12 + 40 * t)
            pygame.draw.line(
                grid,
                (*config.COLOR_NEON_PURPLE, alpha),
                (0, y),
                (width, y),
                1,
            )
        surface.blit(grid, (0, 0))

        rng = random.Random(20261117)
        stars = pygame.Surface(size, pygame.SRCALPHA)
        for _ in range(config.BACKGROUND_STAR_COUNT):
            x = rng.randrange(width)
            y = rng.randrange(max(1, horizon_y + 10))
            color = rng.choice(config.BACKGROUND_STAR_COLORS)
            alpha = rng.randint(18, 95)
            block = rng.choice((1, 1, 2))
            pygame.draw.rect(stars, (*color, alpha), (x, y, block, block))
        surface.blit(stars, (0, 0))
        return surface

    def _build_mote_sprites(self) -> dict[tuple[tuple[int, int, int], int, int], pygame.Surface]:
        sprites: dict[tuple[tuple[int, int, int], int, int], pygame.Surface] = {}
        for mote in self._motes:
            key = (mote.color, mote.alpha, mote.size)
            if key in sprites:
                continue
            sprite = pygame.Surface((mote.size, mote.size), pygame.SRCALPHA)
            sprite.fill((*mote.color, mote.alpha))
            sprites[key] = sprite
        return sprites

    @staticmethod
    def _build_motes(size: tuple[int, int]) -> list[_Mote]:
        width, height = size
        rng = random.Random(77123)
        motes: list[_Mote] = []
        for _ in range(config.AMBIENT_PIXEL_COUNT):
            motes.append(
                _Mote(
                    x=float(rng.randrange(width)),
                    y=float(rng.randrange(height)),
                    speed=rng.uniform(*config.AMBIENT_PIXEL_SPEED),
                    size=rng.randint(*config.AMBIENT_PIXEL_SIZE),
                    color=rng.choice(config.BACKGROUND_STAR_COLORS),
                    alpha=rng.randint(*config.AMBIENT_PIXEL_ALPHA),
                    phase=rng.uniform(0.0, math.tau),
                )
            )
        return motes
