from __future__ import annotations

import math

import pygame

import game_config as config
from ui.fonts import get_font


class ComboCallout:
    """Big pixel callout for combo milestones."""

    def __init__(
        self,
        text: str,
        subtext: str,
        color: tuple[int, int, int],
        position: tuple[float, float] | pygame.Vector2,
        lifetime: float = config.COMBO_CALLOUT_LIFETIME,
    ) -> None:
        self._text = text
        self._subtext = subtext
        self._color = color
        self._origin = pygame.Vector2(position)
        self._lifetime = max(0.01, lifetime)
        self._age = 0.0
        self._text_font = get_font(config.FONT_SIZE_COMBO, bold=True)
        self._sub_font = get_font(config.FONT_SIZE_COMBO_SMALL, bold=True)
        self.finished = False

    def update(self, dt: float) -> None:
        self._age += dt
        if self._age >= self._lifetime:
            self.finished = True

    def draw(self, surface: pygame.Surface) -> None:
        if self.finished:
            return
        progress = min(1.0, self._age / self._lifetime)
        pop = 1.0 - (1.0 - min(1.0, self._age / 0.2)) ** 3
        scale = 0.6 + 0.52 * pop + 0.16 * progress
        alpha = int(255 * (1.0 - max(0.0, (progress - 0.55) / 0.45)) ** 1.2)
        if alpha <= 0:
            return

        wobble = math.sin(progress * 38.0) * 2.2 * (1.0 - progress)
        center = (
            round(self._origin.x + wobble),
            round(self._origin.y - config.COMBO_CALLOUT_RISE * (1.0 - (1.0 - progress) ** 2)),
        )

        main = self._scaled(self._text_font, self._text, self._color, scale, alpha)
        outline = self._scaled(
            self._text_font, self._text, config.COLOR_SHADOW, scale, min(alpha, 220)
        )
        rect = main.get_rect(center=center)
        for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2), (-2, -2), (2, 2)):
            surface.blit(outline, rect.move(dx, dy))
        surface.blit(main, rect)

        if self._subtext:
            sub_alpha = int(alpha * 0.9)
            sub = self._scaled(
                self._sub_font, self._subtext, config.COLOR_WHITE_HOT, scale * 0.9, sub_alpha
            )
            surface.blit(sub, sub.get_rect(midtop=(center[0], rect.bottom + 4)))

    @staticmethod
    def _scaled(
        font: pygame.font.Font,
        text: str,
        color: tuple[int, int, int],
        scale: float,
        alpha: int,
    ) -> pygame.Surface:
        image = font.render(text, False, color)
        width = max(1, round(image.get_width() * scale))
        height = max(1, round(image.get_height() * scale))
        image = pygame.transform.scale(image, (width, height))
        image.set_alpha(alpha)
        return image
