from __future__ import annotations

import math

import pygame

import game_config as config
from localization import t
from ui.fonts import get_font
from ui.text import draw_pixel_text


def format_time(seconds: float) -> str:
    total = max(0, math.ceil(seconds))
    return f"{total // 60:02d}:{total % 60:02d}"


_HEART = (
    "0110110",
    "1111111",
    "1111111",
    "0111110",
    "0011100",
    "0001000",
)


class HUD:
    """Neon arcade top bar: score, timer, lives and the live combo."""

    def __init__(self) -> None:
        self._panel_width = 0
        self._panel: pygame.Surface | None = None
        self._fonts_ready = False
        self.refresh_language()

    def refresh_language(self) -> None:
        if not pygame.font.get_init():
            return
        self._label_font = get_font(config.FONT_SIZE_HUD_LABEL, bold=True)
        self._value_font = get_font(config.FONT_SIZE_HUD_VALUE, bold=True)
        self._combo_font = get_font(config.FONT_SIZE_HUD_COMBO, bold=True)
        self._fonts_ready = True

    def draw(
        self,
        surface: pygame.Surface,
        score: int,
        time_left: float,
        round_seconds: float,
        lives: int,
        combo: int = 0,
        multiplier: int = 1,
        high_score: int = 0,
    ) -> None:
        if not self._fonts_ready:
            self.refresh_language()
        width = surface.get_width()
        margin = config.UI_MARGIN

        if self._panel is None or self._panel_width != width:
            self._panel = pygame.Surface(
                (width, config.UI_HUD_HEIGHT), pygame.SRCALPHA
            )
            self._panel.fill((*config.COLOR_PANEL, 202))
            self._panel_width = width
        surface.blit(self._panel, (0, 0))

        pygame.draw.line(
            surface,
            config.COLOR_NEON_CYAN,
            (0, config.UI_HUD_HEIGHT),
            (width, config.UI_HUD_HEIGHT),
            1,
        )
        for x, color in (
            (0, config.COLOR_NEON_MAGENTA),
            (width - 46, config.COLOR_NEON_YELLOW),
        ):
            pygame.draw.rect(surface, color, (x, 0, 46, 3))

        draw_pixel_text(
            surface,
            t("hud.score"),
            self._label_font,
            config.COLOR_ACCENT_DIM,
            (margin, 20),
            "topleft",
            shadow=1,
        )
        draw_pixel_text(
            surface,
            f"{score:06d}",
            self._value_font,
            config.COLOR_NEON_YELLOW,
            (margin, 38),
            "topleft",
            shadow=2,
        )

        center_x = width // 2
        timer_color = (
            config.COLOR_NEON_RED
            if time_left <= config.UI_TIMER_LOW_THRESHOLD
            else config.COLOR_NEON_CYAN
        )
        draw_pixel_text(
            surface,
            t("hud.time"),
            self._label_font,
            config.COLOR_ACCENT_DIM,
            (center_x, 20),
            "midtop",
            shadow=1,
        )
        draw_pixel_text(
            surface,
            format_time(time_left),
            self._value_font,
            timer_color,
            (center_x, 38),
            "midtop",
            shadow=2,
        )

        bar = pygame.Rect(
            0,
            0,
            config.UI_TIMER_BAR_WIDTH,
            config.UI_TIMER_BAR_HEIGHT,
        )
        bar.midtop = (center_x, 92)
        pygame.draw.rect(surface, (22, 28, 44), bar)
        pygame.draw.rect(surface, config.COLOR_PANEL_BORDER, bar, 1)

        ratio = max(0.0, min(1.0, time_left / round_seconds)) if round_seconds else 0.0
        fill_width = int(bar.width * ratio)
        if fill_width > 0:
            fill = pygame.Rect(bar.x, bar.y, fill_width, bar.height)
            pygame.draw.rect(surface, timer_color, fill)
            pygame.draw.line(
                surface,
                config.COLOR_WHITE_HOT,
                (fill.x, fill.y),
                (fill.right - 1, fill.y),
                1,
            )

        right = width - margin
        draw_pixel_text(
            surface,
            t("hud.lives"),
            self._label_font,
            config.COLOR_ACCENT_DIM,
            (right, 20),
            "topright",
            shadow=1,
        )
        self._draw_hearts(surface, right, lives)
        draw_pixel_text(
            surface,
            t("hud.best", score=high_score),
            self._combo_font,
            config.COLOR_ACCENT_DIM,
            (right, 74),
            "topright",
            shadow=1,
        )

        if combo >= 2:
            color = config.COMBO_HUD_COLOR
            combo_rect = draw_pixel_text(
                surface,
                t("hud.combo", combo=combo),
                self._combo_font,
                color,
                (margin, 86),
                "topleft",
                shadow=1,
            )
            if multiplier > 1:
                draw_pixel_text(
                    surface,
                    t("hud.multiplier", multiplier=multiplier),
                    self._combo_font,
                    config.COLOR_NEON_MAGENTA
                    if multiplier >= config.COMBO_MULTIPLIER_MAX
                    else config.COLOR_NEON_YELLOW,
                    (combo_rect.right + 12, 86),
                    "topleft",
                    shadow=1,
                )

    def _draw_hearts(
        self,
        surface: pygame.Surface,
        right: int,
        lives: int,
    ) -> None:
        size = config.UI_HEART_SIZE
        gap = config.UI_HEART_GAP
        block = max(1, size // 7)
        heart_width = 7 * block
        total = config.STARTING_LIVES * heart_width + (
            config.STARTING_LIVES - 1
        ) * gap
        start_x = right - total
        top = config.UI_HEART_TOP

        for index in range(config.STARTING_LIVES):
            x = start_x + index * (heart_width + gap)
            filled = index < lives
            color = config.COLOR_NEON_RED if filled else (42, 30, 46)
            for row, pattern in enumerate(_HEART):
                for column, cell in enumerate(pattern):
                    if cell == "1":
                        pygame.draw.rect(
                            surface,
                            color,
                            (x + column * block, top + row * block, block, block),
                        )
