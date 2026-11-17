from __future__ import annotations

import pygame

import game_config as config


def build_fallback_icons(
    count: int | None = None,
    size: int | None = None,
) -> list[pygame.Surface]:
    """Procedural icons used when the real desktop cannot be read.

    The game must stay playable on a locked-down machine, so this mirrors the
    shape of a desktop shortcut with a coloured tile and a letter.
    """
    if not pygame.font.get_init():
        pygame.font.init()

    count = config.FALLBACK_ICON_COUNT if count is None else max(0, count)
    size = config.FALLBACK_ICON_SIZE if size is None else max(8, size)
    font = pygame.font.Font(None, max(10, int(size * 0.62)))

    icons: list[pygame.Surface] = []
    for index in range(count):
        color = config.FALLBACK_ICON_COLORS[index % len(config.FALLBACK_ICON_COLORS)]
        border = tuple(min(255, channel + 46) for channel in color)

        surface = pygame.Surface((size, size), pygame.SRCALPHA)
        rect = pygame.Rect(2, 2, size - 4, size - 4)
        pygame.draw.rect(surface, color, rect, border_radius=max(4, size // 6))
        pygame.draw.rect(
            surface,
            border,
            rect,
            width=max(1, size // 24),
            border_radius=max(4, size // 6),
        )

        shine = pygame.Rect(
            rect.left + 4,
            rect.top + 4,
            max(1, rect.width - 8),
            max(1, rect.height // 5),
        )
        pygame.draw.rect(
            surface,
            (*border, 90),
            shine,
            border_radius=max(2, size // 12),
        )

        label = chr(ord("A") + index) if index < 26 else "?"
        glyph = font.render(label, True, (255, 255, 255))
        glyph.set_alpha(232)
        surface.blit(glyph, glyph.get_rect(center=rect.center))

        icons.append(surface)

    return icons
