from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

import game_config as config
from core.states.base import GameState
from localization import t
from ui.button import PixelButton
from ui.fonts import get_font
from ui.text import draw_pixel_text

if TYPE_CHECKING:
    from core.game import Game


class GameOverState(GameState):
    """Round summary with stats, best score and three exit actions."""

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self._elapsed = 0.0
        self._focused = 0
        self._fonts_ready = False
        self._buttons: list[PixelButton] = []
        self.refresh_language()
        self._buttons = self._build_buttons()

    def refresh_language(self) -> None:
        if not pygame.font.get_init():
            return
        self._label_font = get_font(config.FONT_SIZE_EYEBROW, bold=True)
        self._title_font = get_font(config.FONT_SIZE_GAME_OVER_TITLE, bold=True)
        self._score_font = get_font(config.FONT_SIZE_GAME_OVER_SCORE, bold=True)
        self._stat_label_font = get_font(config.FONT_SIZE_STAT_LABEL, bold=True)
        self._stat_value_font = get_font(config.FONT_SIZE_STAT_VALUE, bold=True)
        self._badge_font = get_font(config.FONT_SIZE_HUD_COMBO, bold=True)
        self._footer_font = get_font(config.FONT_SIZE_FOOTER)
        for button in self._buttons:
            button.refresh_language()
        self._fonts_ready = True

    def _build_buttons(self) -> list[PixelButton]:
        width, height = self.game.screen.get_size()
        button_w = 300
        button_h = config.UI_BUTTON_HEIGHT
        gap = 22
        total = 3 * button_w + 2 * gap
        x = width // 2 - total // 2
        y = int(height * 0.74)
        specs = (
            ("again", "gameover.play_again", "start"),
            ("menu", "gameover.main_menu", "menu"),
            ("exit", "gameover.exit", "exit"),
        )
        return [
            PixelButton(
                key,
                "",
                pygame.Rect(x + index * (button_w + gap), y, button_w, button_h),
                action,
                label_key=label_key,
            )
            for index, (key, label_key, action) in enumerate(specs)
        ]

    def on_enter(self, **kwargs: object) -> None:
        self._elapsed = 0.0
        self._focused = 0

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_LEFT, pygame.K_a, pygame.K_UP, pygame.K_w):
                self._focused = (self._focused - 1) % len(self._buttons)
                self.game.sfx.play("click", 0.5)
            elif event.key in (pygame.K_RIGHT, pygame.K_d, pygame.K_DOWN, pygame.K_s):
                self._focused = (self._focused + 1) % len(self._buttons)
                self.game.sfx.play("click", 0.5)
            elif event.key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
                self._activate(self._buttons[self._focused].action)
            elif event.key == pygame.K_r:
                self._activate("start")
            elif event.key == pygame.K_ESCAPE:
                self._activate("menu")
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
        elif action == "menu":
            self.game.sfx.play("click", 0.9)
            self.game.go_to_menu()
        elif action == "exit":
            self.game.request_shutdown("gameover_exit")

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def render(self, surface: pygame.Surface) -> None:
        if not self._fonts_ready:
            self.refresh_language()
        self.game.background.draw(surface)
        width, height = surface.get_size()
        cx = width // 2

        reason = self.game.round_result or "round_over"
        title_key = f"gameover.title.{reason}"
        title = t(title_key)
        if title == title_key:
            title = t("gameover.title.round_over")
        draw_pixel_text(
            surface,
            t("gameover.complete"),
            self._label_font,
            config.COLOR_NEON_CYAN,
            (cx, height * 0.10),
            shadow=2,
        )
        title_color = (
            config.COLOR_NEON_RED
            if reason == "out_of_lives"
            else config.COLOR_NEON_CYAN
        )
        title_rect = draw_pixel_text(
            surface,
            title,
            self._title_font,
            title_color,
            (cx, height * 0.20),
            shadow=5,
            outline=2,
            outline_color=config.COLOR_SHADOW,
        )
        half = int(title_rect.width * 0.36)
        pygame.draw.line(
            surface,
            config.COLOR_NEON_MAGENTA,
            (cx - half, title_rect.bottom + 8),
            (cx + half, title_rect.bottom + 8),
            3,
        )

        draw_pixel_text(
            surface,
            t("gameover.final_score"),
            self._label_font,
            config.COLOR_TEXT_DIM,
            (cx, height * 0.335),
            shadow=1,
        )
        draw_pixel_text(
            surface,
            f"{self.game.score:06d}",
            self._score_font,
            config.COLOR_NEON_YELLOW,
            (cx, height * 0.41),
            shadow=4,
        )

        best_combo = max(self.game.best_combo, self.game.combo.best)
        stats = (
            (t("gameover.sliced"), f"{self.game.slice_count}"),
            (t("gameover.max_combo"), f"x{best_combo}"),
            (t("gameover.high_score"), f"{self.game.profile.high_score:06d}"),
        )
        for index, (label, value) in enumerate(stats):
            x = int(width * (0.3 + 0.2 * index))
            draw_pixel_text(
                surface,
                label,
                self._stat_label_font,
                config.COLOR_ACCENT_DIM,
                (x, height * 0.535),
                shadow=1,
            )
            value_color = (
                config.COLOR_NEON_YELLOW
                if index == 2
                else config.COLOR_TEXT
            )
            draw_pixel_text(
                surface,
                value,
                self._stat_value_font,
                value_color,
                (x, height * 0.59),
                shadow=2,
            )

        if self.game.new_high_score:
            pulse = 0.5 + 0.5 * math.sin(self._elapsed * 6.0)
            draw_pixel_text(
                surface,
                t("gameover.new_high_score"),
                self._badge_font,
                config.COLOR_NEON_MAGENTA,
                (cx, height * 0.665),
                alpha=int(170 + 85 * pulse),
                shadow=2,
            )

        accents = (
            config.COLOR_NEON_CYAN,
            config.COLOR_NEON_PURPLE,
            config.COLOR_NEON_MAGENTA,
        )
        for index, button in enumerate(self._buttons):
            button.draw(
                surface,
                focused=index == self._focused,
                accent=accents[index],
            )

        draw_pixel_text(
            surface,
            t("gameover.footer"),
            self._footer_font,
            config.COLOR_TEXT_DIM,
            (cx, height - 26),
            shadow=1,
        )
