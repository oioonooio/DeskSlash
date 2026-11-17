from __future__ import annotations

import pygame

import game_config as config
from ui.fonts import get_font


class FloatingText:
    """Arcade score popup: pops, grows, floats up and fades."""

    def __init__(
        self,
        text: str,
        position: tuple[float, float] | pygame.Vector2,
        color: tuple[int, int, int] = config.SCORE_POPUP_COLOR,
        lifetime: float = config.SCORE_POPUP_LIFETIME,
        rise: float = config.SCORE_POPUP_RISE,
        combo: int = 0,
    ) -> None:
        self._origin = pygame.Vector2(position)
        self._lifetime = max(0.01, lifetime)
        self._rise = rise
        self._age = 0.0
        size = config.FONT_SIZE_SCORE_POPUP + min(10, max(0, combo - 1) * 2)
        font = get_font(size, bold=True)
        self._main = font.render(text, False, color)
        self._shadow = font.render(text, False, config.COLOR_SHADOW)
        self._start_scale = config.SCORE_POPUP_START_SCALE
        self._end_scale = config.SCORE_POPUP_END_SCALE + min(0.25, max(0, combo - 1) * 0.03)
        self.finished = False

    def update(self, dt: float) -> None:
        self._age += dt
        if self._age >= self._lifetime:
            self.finished = True

    def draw(self, surface: pygame.Surface) -> None:
        if self.finished:
            return
        progress = min(1.0, self._age / self._lifetime)
        eased = 1.0 - (1.0 - progress) ** 2
        scale = self._start_scale + (self._end_scale - self._start_scale) * eased
        alpha = int(255 * (1.0 - max(0.0, (progress - 0.4) / 0.6)) ** 1.3)
        if alpha <= 0:
            return

        main = _scale(self._main, scale, alpha)
        shadow = _scale(self._shadow, scale, min(alpha, 200))
        center = (
            round(self._origin.x),
            round(self._origin.y - self._rise * eased),
        )
        rect = main.get_rect(center=center)
        surface.blit(shadow, rect.move(3, 3))
        surface.blit(main, rect)


def _scale(image: pygame.Surface, scale: float, alpha: int) -> pygame.Surface:
    width = max(1, round(image.get_width() * scale))
    height = max(1, round(image.get_height() * scale))
    scaled = pygame.transform.scale(image, (width, height))
    scaled.set_alpha(alpha)
    return scaled
