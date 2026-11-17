from __future__ import annotations

import pygame

import game_config as config


def build_bomb_surface(size: int | None = None) -> pygame.Surface:
    """Procedural pixel bomb drawn natively at ``size`` (no upscaled art)."""
    size = max(32, int(size or config.BOMB_SOURCE_SIZE))
    surface = pygame.Surface((size, size), pygame.SRCALPHA)

    def px(value: float) -> int:
        return round(value * size)

    center = (px(0.47), px(0.57))
    radius = max(4, px(0.33))
    rim = max(1, px(0.035))

    pygame.draw.circle(surface, (18, 16, 26), center, radius)
    pygame.draw.circle(surface, config.COLOR_NEON_ORANGE, center, radius, rim)
    pygame.draw.circle(
        surface, (255, 90, 60), center, max(1, radius - px(0.07)), max(1, px(0.012))
    )

    # Chunky highlight and rim pixels.
    pygame.draw.rect(
        surface, (255, 170, 90), (px(0.28), px(0.38), px(0.13), px(0.09))
    )
    pygame.draw.rect(
        surface, (255, 220, 140), (px(0.31), px(0.41), px(0.06), px(0.045))
    )
    pygame.draw.rect(
        surface, (90, 60, 80), (px(0.60), px(0.72), px(0.11), px(0.06))
    )
    pygame.draw.rect(
        surface, (60, 40, 60), (px(0.34), px(0.75), px(0.16), px(0.06))
    )

    # Fuse.
    fuse = [
        (px(0.72), px(0.32)),
        (px(0.79), px(0.24)),
        (px(0.83), px(0.15)),
        (px(0.90), px(0.10)),
    ]
    pygame.draw.lines(surface, (206, 150, 90), False, fuse, max(1, px(0.055)))
    pygame.draw.lines(surface, (255, 214, 150), False, fuse, max(1, px(0.016)))

    # Spark cluster, deliberately asymmetric.
    spark = max(1, px(0.04))
    for x, y, color in (
        (0.88, 0.05, config.COLOR_NEON_YELLOW),
        (0.94, 0.11, config.COLOR_NEON_ORANGE),
        (0.82, 0.03, config.COLOR_WHITE_HOT),
        (0.92, 0.19, config.COLOR_NEON_RED),
        (0.97, 0.05, config.COLOR_NEON_YELLOW),
    ):
        pygame.draw.rect(surface, color, (px(x), px(y), spark, spark))

    # Warning bar.
    pygame.draw.rect(
        surface, config.COLOR_NEON_RED, (px(0.33), px(0.50), px(0.20), px(0.07))
    )
    pygame.draw.rect(
        surface, config.COLOR_NEON_YELLOW, (px(0.36), px(0.60), px(0.13), px(0.07))
    )

    return surface
