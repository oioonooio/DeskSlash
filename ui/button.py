from __future__ import annotations

import pygame

import game_config as config
from localization import t
from ui.fonts import get_font
from ui.text import draw_pixel_text


class PixelButton:
    """Rectangular arcade button with hover and keyboard-focus states."""

    def __init__(
        self,
        key: str,
        label: str,
        rect: pygame.Rect,
        action: str,
        value: str = "",
        label_key: str | None = None,
    ) -> None:
        self.key = key
        self._label = label
        self.label_key = label_key
        self.rect = pygame.Rect(rect)
        self.action = action
        self.value = value
        self._font = get_font(config.FONT_SIZE_BUTTON, bold=True)
        self._value_font = get_font(config.FONT_SIZE_HUD_COMBO, bold=True)

    @property
    def label(self) -> str:
        return t(self.label_key) if self.label_key else self._label

    def refresh_language(self) -> None:
        self._font = get_font(config.FONT_SIZE_BUTTON, bold=True)
        self._value_font = get_font(config.FONT_SIZE_HUD_COMBO, bold=True)

    def draw(
        self,
        surface: pygame.Surface,
        focused: bool = False,
        hovered: bool = False,
        accent: tuple[int, int, int] = config.COLOR_NEON_CYAN,
    ) -> None:
        active = focused or hovered
        rect = self.rect
        pygame.draw.rect(surface, config.COLOR_SHADOW, rect.move(4, 4))
        pygame.draw.rect(
            surface,
            (26, 34, 58) if active else (11, 15, 28),
            rect,
        )
        pygame.draw.rect(surface, (6, 9, 18), (rect.x + 4, rect.bottom - 9, rect.width - 8, 5))

        border = accent if active else config.COLOR_PANEL_BORDER
        pygame.draw.rect(surface, border, rect, config.UI_BUTTON_BORDER)
        pygame.draw.rect(
            surface,
            accent if active else config.COLOR_ACCENT_DIM,
            (rect.x, rect.y, 7, rect.height),
        )

        if active:
            self._draw_focus_marks(surface, rect, accent)

        text_color = config.COLOR_WHITE_HOT if active else config.COLOR_TEXT
        if self.value:
            draw_pixel_text(
                surface,
                self.label,
                self._font,
                text_color,
                (rect.x + 24, rect.centery),
                "midleft",
                shadow=2,
            )
            draw_pixel_text(
                surface,
                self.value,
                self._value_font,
                accent if active else config.COLOR_TEXT_DIM,
                (rect.right - 20, rect.centery),
                "midright",
                shadow=1,
            )
        else:
            draw_pixel_text(
                surface,
                self.label,
                self._font,
                text_color,
                rect.center,
                shadow=2,
            )

    @staticmethod
    def _draw_focus_marks(
        surface: pygame.Surface,
        rect: pygame.Rect,
        accent: tuple[int, int, int],
    ) -> None:
        # Rising pixel bars on the left edge act as a focus equalizer.
        for index in range(3):
            height = 4 + index * 3
            pygame.draw.rect(
                surface,
                accent,
                (rect.x + 17 + index * 5, rect.centery - height // 2, 4, height),
            )

    def hit(self, position: tuple[int, int]) -> bool:
        return self.rect.collidepoint(position)


def draw_pixel_panel(
    surface: pygame.Surface,
    rect: pygame.Rect,
    accent: tuple[int, int, int] = config.COLOR_NEON_CYAN,
    alpha: int = 238,
) -> None:
    """Dark modal panel with a neon frame and clipped pixel corners."""
    pygame.draw.rect(surface, config.COLOR_SHADOW, rect.move(6, 6))
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    layer.fill((*config.COLOR_PANEL, max(0, min(255, alpha))))
    pygame.draw.rect(layer, (*config.COLOR_PANEL_BORDER, 255), layer.get_rect(), 2)
    pygame.draw.rect(layer, (*accent, 255), (0, 0, layer.get_width(), 4))
    pygame.draw.rect(layer, (*config.COLOR_NEON_MAGENTA, 255), (0, 4, 8, 52))
    pygame.draw.rect(
        layer,
        (*config.COLOR_NEON_YELLOW, 255),
        (layer.get_width() - 8, layer.get_height() - 56, 8, 52),
    )
    inner = layer.get_rect().inflate(-14, -14)
    pygame.draw.rect(layer, (*config.COLOR_PANEL_BORDER, 120), inner, 1)
    surface.blit(layer, rect.topleft)
