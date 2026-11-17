from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

import game_config as config
from core.diagnostics import log
from core.phases import GamePhase
from core.states.base import GameState
from localization import t
from ui.button import draw_pixel_panel
from ui.fonts import get_font
from ui.text import draw_pixel_text

if TYPE_CHECKING:
    from core.game import Game


class PausedState(GameState):
    """Frozen round with the mouse handed back to the desktop."""

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self._elapsed = 0.0
        width, height = game.screen.get_size()
        self._panel = pygame.Rect(0, 0, min(620, width - 80), 320)
        self._panel.center = (width // 2, int(height * 0.5))
        self._scrim = pygame.Surface((width, height), pygame.SRCALPHA)
        self._scrim.fill((3, 4, 10, 158))
        self._fonts_ready = False
        self.refresh_language()

    def refresh_language(self) -> None:
        if not pygame.font.get_init():
            return
        self._title_font = get_font(config.FONT_SIZE_GAME_OVER_TITLE, bold=True)
        self._label_font = get_font(config.FONT_SIZE_EYEBROW, bold=True)
        self._body_font = get_font(config.FONT_SIZE_PROMPT, bold=True)
        self._small_font = get_font(config.FONT_SIZE_FOOTER)
        self._time_font = get_font(config.FONT_SIZE_HUD_VALUE, bold=True)
        self._fonts_ready = True

    def on_enter(self, **kwargs: object) -> None:
        self._elapsed = 0.0

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        log("INPUT", f"paused key {pygame.key.name(event.key)}")
        if event.key in (pygame.K_ESCAPE, pygame.K_p):
            self.game.resume_round()
        elif event.key == pygame.K_m:
            self.game.go_to_menu()
        elif event.key == pygame.K_q:
            self.game.request_shutdown("pause_quit")

    def update(self, dt: float) -> None:
        self._elapsed += dt

    def render(self, surface: pygame.Surface) -> None:
        if not self._fonts_ready:
            self.refresh_language()
        playing = self.game.states.get(GamePhase.PLAYING)
        playing.render(surface)

        if not self.game.is_overlay:
            surface.blit(self._scrim, (0, 0))

        draw_pixel_panel(surface, self._panel, config.COLOR_NEON_YELLOW)
        cx = self._panel.centerx
        top = self._panel.top

        pulse = 0.5 + 0.5 * math.sin(self._elapsed * 3.4)
        draw_pixel_text(
            surface,
            t("paused.title"),
            self._title_font,
            config.COLOR_NEON_YELLOW,
            (cx, top + 66),
            shadow=4,
            outline=2,
            outline_color=config.COLOR_SHADOW,
        )
        draw_pixel_text(
            surface,
            t("paused.frozen"),
            self._label_font,
            config.COLOR_NEON_CYAN,
            (cx, top + 122),
            shadow=1,
        )
        time_left = playing.time_left
        draw_pixel_text(
            surface,
            f"{int(time_left) // 60:02d}:{int(time_left) % 60:02d}",
            self._time_font,
            config.COLOR_TEXT,
            (cx, top + 168),
            shadow=2,
        )

        status = (
            t("paused.mouse_released")
            if self.game.window.input_mode == "released"
            else t("paused.input_active")
        )
        draw_pixel_text(
            surface,
            status,
            self._small_font,
            config.COLOR_ACCENT_DIM
            if self.game.window.input_mode == "released"
            else config.COLOR_NEON_CYAN,
            (cx, top + 206),
            alpha=int(190 + 55 * pulse),
            shadow=1,
        )

        draw_pixel_text(
            surface,
            t("paused.resume"),
            self._body_font,
            config.COLOR_WHITE_HOT,
            (cx, top + 250),
            shadow=2,
        )
        draw_pixel_text(
            surface,
            t("paused.menu_quit"),
            self._small_font,
            config.COLOR_TEXT_DIM,
            (cx, top + 290),
            shadow=1,
        )
