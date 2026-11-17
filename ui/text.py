from __future__ import annotations

from typing import Sequence

import pygame

import game_config as config

Color = tuple[int, int, int]

# Font rendering is the most frequently repeated allocation in the HUD. Cache
# the rasterised surfaces; dynamic strings are evicted FIFO once the cap is hit.
_TEXT_CACHE: dict[tuple[int, str, tuple[int, int, int], int, bool], pygame.Surface] = {}


def clear_text_cache() -> None:
    _TEXT_CACHE.clear()


def has_cjk(text: str) -> bool:
    """True when the string contains glyphs that need smooth CJK rendering."""
    for char in text:
        code = ord(char)
        if (
            0x3400 <= code <= 0x4DBF
            or 0x4E00 <= code <= 0x9FFF
            or 0xF900 <= code <= 0xFAFF
            or 0xFF01 <= code <= 0xFF60
        ):
            return True
    return False


def _render(
    font: pygame.font.Font,
    text: str,
    color: Color,
    antialias: bool,
    alpha: int,
) -> pygame.Surface:
    key = (id(font), text, color, alpha, antialias)
    image = _TEXT_CACHE.get(key)
    if image is None:
        image = font.render(text, antialias, color)
        if alpha < 255:
            image.set_alpha(alpha)
        if len(_TEXT_CACHE) >= config.TEXT_CACHE_MAX:
            _TEXT_CACHE.pop(next(iter(_TEXT_CACHE)))
        _TEXT_CACHE[key] = image
    return image


def draw_text(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    color: Color,
    position: Sequence[float],
    anchor: str = "center",
    alpha: int = 255,
) -> pygame.Rect:
    """Draw antialiased text anchored to a rect attribute such as ``center``."""
    image = _render(font, text, color, True, alpha)
    rect = image.get_rect(**{anchor: (round(position[0]), round(position[1]))})
    surface.blit(image, rect)
    return rect


def draw_pixel_text(
    surface: pygame.Surface,
    text: str,
    font: pygame.font.Font,
    color: Color,
    position: Sequence[float],
    anchor: str = "center",
    alpha: int = 255,
    shadow: int = 2,
    outline: int = 0,
    outline_color: Color = config.COLOR_SHADOW,
) -> pygame.Rect:
    """Hard-edged arcade text with a block shadow and optional outline.

    Chinese glyphs are antialiased even in pixel mode: hard-edged CJK at small
    sizes loses strokes and becomes unreadable.
    """
    smooth = has_cjk(text)
    image = _render(font, text, color, smooth, alpha)
    rect = image.get_rect(**{anchor: (round(position[0]), round(position[1]))})

    if outline > 0:
        layer = _render(font, text, outline_color, smooth, alpha)
        for dx in (-outline, 0, outline):
            for dy in (-outline, 0, outline):
                if dx or dy:
                    surface.blit(layer, rect.move(dx, dy))

    if shadow > 0:
        layer = _render(font, text, config.COLOR_SHADOW, smooth, min(alpha, 190))
        surface.blit(layer, rect.move(shadow, shadow))

    surface.blit(image, rect)
    return rect
