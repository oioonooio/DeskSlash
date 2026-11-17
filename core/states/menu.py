from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

import game_config as config
from core.states.base import GameState
from localization import t
from ui.button import PixelButton
from ui.fonts import get_font
from ui.settings import SettingsOverlay
from ui.text import draw_pixel_text

if TYPE_CHECKING:
    from core.game import Game


class MenuState(GameState):
    """Title screen with start, settings and exit actions."""

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self._elapsed = 0.0
        self._focused = 0
        self._eyebrow_font = get_font(config.FONT_SIZE_EYEBROW, bold=True)
        self._title_font = get_font(config.FONT_SIZE_TITLE, bold=True)
        self._subtitle_font = get_font(config.FONT_SIZE_SUBTITLE)
        self._score_label_font = get_font(config.FONT_SIZE_EYEBROW, bold=True)
        self._score_font = get_font(config.FONT_SIZE_HUD_VALUE, bold=True)
        self._footer_font = get_font(config.FONT_SIZE_FOOTER)
        self._overlay = SettingsOverlay(game.screen.get_size(), game)
        self._buttons = self._build_buttons()

    def _build_buttons(self) -> list[PixelButton]:
        width, height = self.game.screen.get_size()
        button_w = config.UI_BUTTON_WIDTH
        button_h = config.UI_BUTTON_HEIGHT
        gap = config.UI_BUTTON_GAP
        total = 3 * button_h + 2 * gap
        x = width // 2 - button_w // 2
        top = int(height * 0.60)
        if top + total > height - 74:
            top = height - 74 - total
        specs = (
            ("start", "menu.start", "start"),
            ("settings", "menu.settings", "settings"),
            ("exit", "menu.exit", "exit"),
        )
        return [
            PixelButton(
                key,
                "",
                pygame.Rect(x, top + index * (button_h + gap), button_w, button_h),
                action,
                label_key=label_key,
            )
            for index, (key, label_key, action) in enumerate(specs)
        ]

    def refresh_language(self) -> None:
        self._eyebrow_font = get_font(config.FONT_SIZE_EYEBROW, bold=True)
        self._title_font = get_font(config.FONT_SIZE_TITLE, bold=True)
        self._subtitle_font = get_font(config.FONT_SIZE_SUBTITLE)
        self._score_label_font = get_font(config.FONT_SIZE_EYEBROW, bold=True)
        self._score_font = get_font(config.FONT_SIZE_HUD_VALUE, bold=True)
        self._footer_font = get_font(config.FONT_SIZE_FOOTER)
        focused = self._focused
        self._buttons = self._build_buttons()
        self._focused = min(focused, len(self._buttons) - 1)
        self._overlay.refresh_language()

    def on_enter(self, **kwargs: object) -> None:
        self._elapsed = 0.0
        self._focused = 0
        self._overlay.close()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._overlay.is_open:
            self._overlay.handle_event(event)
            return

        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w):
                self._focused = (self._focused - 1) % len(self._buttons)
                self.game.sfx.play("click", 0.5)
            elif event.key in (pygame.K_DOWN, pygame.K_s):
                self._focused = (self._focused + 1) % len(self._buttons)
                self.game.sfx.play("click", 0.5)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                self._activate(self._buttons[self._focused].action)
            elif event.key == pygame.K_ESCAPE:
                self.game.request_shutdown("menu_escape")
        elif event.type == pygame.MOUSEMOTION:
            hovered = self._button_at(event.pos)
            if hovered is not None:
                self._focused = hovered
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            index = self._button_at(event.pos)
            if index is not None:
                self._focused = index
                self._activate(self._buttons[index].action)

    def update(self, dt: float) -> None:
        self._elapsed += dt

    def _button_at(self, position: tuple[int, int]) -> int | None:
        for index, button in enumerate(self._buttons):
            if button.hit(position):
                return index
        return None

    def _activate(self, action: str) -> None:
        if action == "start":
            self.game.sfx.play("click", 0.9)
            self.game.start_round()
        elif action == "settings":
            self.game.sfx.play("click", 0.9)
            self._overlay.open()
        elif action == "exit":
            self.game.request_shutdown("menu_exit")

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def render(self, surface: pygame.Surface) -> None:
        self.game.background.draw(surface)
        width, height = surface.get_size()
        cx = width // 2

        draw_pixel_text(
            surface,
            t("menu.eyebrow"),
            self._eyebrow_font,
            config.COLOR_NEON_CYAN,
            (cx, height * 0.12),
            shadow=2,
        )
        title_rect = draw_pixel_text(
            surface,
            t("menu.title"),
            self._title_font,
            config.COLOR_WHITE_HOT,
            (cx, height * 0.28),
            shadow=5,
            outline=2,
            outline_color=config.COLOR_NEON_MAGENTA,
        )
        half = int(title_rect.width * 0.38)
        pygame.draw.line(
            surface,
            config.COLOR_NEON_CYAN,
            (cx - half, title_rect.bottom + 12),
            (cx + half, title_rect.bottom + 12),
            3,
        )
        pygame.draw.line(
            surface,
            config.COLOR_NEON_MAGENTA,
            (cx - half // 2, title_rect.bottom + 18),
            (cx + half // 2, title_rect.bottom + 18),
            1,
        )
        draw_pixel_text(
            surface,
            t("menu.subtitle"),
            self._subtitle_font,
            config.COLOR_TEXT_DIM,
            (cx, height * 0.42),
            shadow=1,
        )

        draw_pixel_text(
            surface,
            t("menu.high_score"),
            self._score_label_font,
            config.COLOR_ACCENT_DIM,
            (cx, height * 0.475),
            shadow=1,
        )
        pulse = 0.5 + 0.5 * math.sin(self._elapsed * 2.4)
        draw_pixel_text(
            surface,
            f"{self.game.high_score:06d}",
            self._score_font,
            config.COLOR_NEON_YELLOW,
            (cx, height * 0.515),
            alpha=int(205 + 50 * pulse),
            shadow=2,
        )

        for index, button in enumerate(self._buttons):
            button.draw(surface, focused=index == self._focused)

        if self.game.desktop_hide_error:
            draw_pixel_text(
                surface,
                self._hide_warning(),
                self._footer_font,
                config.COLOR_DANGER,
                (cx, height - 64),
                shadow=1,
            )

        draw_pixel_text(
            surface,
            t("menu.footer"),
            self._footer_font,
            config.COLOR_TEXT_DIM,
            (cx, height - 40),
            shadow=1,
        )
        draw_pixel_text(
            surface,
            self._source_line(),
            self._footer_font,
            config.COLOR_ACCENT_DIM,
            (cx, height - 16),
            shadow=1,
        )

        self._overlay.draw(surface, self.game)

    def _source_line(self) -> str:
        count = self.game.icon_source_count
        if self.game.desktop_hidden:
            mode = t("menu.mode.desktop")
        elif self.game.is_overlay:
            mode = t("menu.mode.overlay")
        else:
            mode = t("menu.mode.window")
        label = t(
            "menu.source.desktop_icons"
            if self.game.icon_source_label == "desktop"
            else "menu.source.fallback_icons"
        )
        return t("menu.source", count=count, label=label, mode=mode)

    def _hide_warning(self) -> str:
        message = t("menu.hide_warning", error=self.game.desktop_hide_error)
        if len(message) > 92:
            message = message[:89] + "..."
        return message
