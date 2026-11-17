from __future__ import annotations

import os

import pygame

import game_config as config
from localization import current_language

_font_cache: dict[tuple[int, bool, str, bool], pygame.font.Font] = {}


def clear_font_cache() -> None:
    _font_cache.clear()


def _match(names: tuple[str, ...], bold: bool, files: tuple[str, ...]) -> str | None:
    for name in names:
        path = pygame.font.match_font(name, bold=bold)
        if path:
            return path
    for path in files:
        if os.path.isfile(path):
            return path
    return None


def get_font(
    size: int,
    bold: bool = False,
    *,
    cjk: bool | None = None,
) -> pygame.font.Font:
    """Return a cached font for the active language.

    ``cjk`` forces a Chinese-capable family for the few labels that show a
    Chinese language name even while the English catalogue is active.
    """
    language = current_language()
    want_cjk = (language == "zh_CN") if cjk is None else cjk
    key = (size, bold, language, want_cjk)
    cached = _font_cache.get(key)
    if cached is not None:
        return cached

    if want_cjk:
        path = _match(config.FONT_NAMES_ZH, bold, config.FONT_FILES_ZH)
    else:
        path = _match(config.FONT_NAMES, bold, ())

    font = pygame.font.Font(path, size) if path else pygame.font.Font(None, size)
    if path is None and bold:
        font.set_bold(True)

    _font_cache[key] = font
    return font
