from __future__ import annotations

import math
from typing import TYPE_CHECKING

import pygame

import game_config as config
from core.states.base import GameState
from localization import t
from ui.fonts import get_font
from ui.text import draw_pixel_text, has_cjk

if TYPE_CHECKING:
    from core.game import Game


class CountdownState(GameState):
    """3-2-1-GO! lead-in with a pop animation and one blip per step."""

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self._time_left = config.COUNTDOWN_SECONDS
        self._sound_index = -1
        self._fonts_ready = False
        self.refresh_language()

    def refresh_language(self) -> None:
        if not pygame.font.get_init():
            return
        self._label_font = get_font(config.FONT_SIZE_EYEBROW, bold=True)
        self._number_font = get_font(config.FONT_SIZE_COUNTDOWN, bold=True)
        self._footer_font = get_font(config.FONT_SIZE_FOOTER)
        self._fonts_ready = True

    def on_enter(self, **kwargs: object) -> None:
        self._time_left = config.COUNTDOWN_SECONDS
        self._sound_index = -1
        self._sync_sound()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type != pygame.KEYDOWN:
            return
        if event.key in (pygame.K_SPACE, pygame.K_RETURN):
            self.game.begin_play()
        elif event.key == pygame.K_ESCAPE:
            self.game.go_to_menu()

    def update(self, dt: float) -> None:
        self._time_left -= dt
        self._sync_sound()
        if self._time_left <= 0.0:
            self.game.begin_play()

    def _stage(self) -> tuple[int, float, float, str, bool]:
        """Return ``(index, local_time, stage_length, label, is_go)``."""
        elapsed = max(0.0, config.COUNTDOWN_SECONDS - self._time_left)
        step = config.COUNTDOWN_STEP_SECONDS
        if elapsed < step * 3:
            index = int(elapsed // step)
            local = elapsed - index * step
            return index, local, step, str(3 - index), False
        local = elapsed - step * 3
        return 3, local, config.COUNTDOWN_GO_SECONDS, t("countdown.go_label"), True

    def _sync_sound(self) -> None:
        index, _local, _duration, _label, is_go = self._stage()
        if index == self._sound_index:
            return
        self._sound_index = index
        self.game.sfx.play("go" if is_go else "count")

    def render(self, surface: pygame.Surface) -> None:
        if not self._fonts_ready:
            self.refresh_language()
        self.game.background.draw(surface)
        width, height = surface.get_size()
        cx = width // 2
        cy = int(height * 0.52)
        radius = 170
        index, local, duration, label, is_go = self._stage()

        draw_pixel_text(
            surface,
            t("countdown.go") if is_go else t("countdown.get_ready"),
            self._label_font,
            config.COLOR_NEON_YELLOW if is_go else config.COLOR_NEON_CYAN,
            (cx, height * 0.2),
            shadow=2,
        )

        pygame.draw.circle(surface, (48, 22, 66), (cx, cy), radius + 8, 10)
        pygame.draw.circle(surface, config.COLOR_NEON_PURPLE, (cx, cy), radius, 2)
        for tick in range(24):
            angle = math.tau * tick / 24.0
            inner = radius - 12
            outer = radius - 4
            color = (
                config.COLOR_NEON_YELLOW
                if is_go and tick % 2 == 0
                else config.COLOR_NEON_CYAN
                if tick % 3 == 0
                else config.COLOR_ACCENT_DIM
            )
            pygame.draw.line(
                surface,
                color,
                (cx + math.cos(angle) * inner, cy + math.sin(angle) * inner),
                (cx + math.cos(angle) * outer, cy + math.sin(angle) * outer),
                2,
            )

        fraction = max(0.0, min(1.0, self._time_left / config.COUNTDOWN_SECONDS))
        if fraction > 0.0:
            arc_rect = pygame.Rect(cx - radius, cy - radius, radius * 2, radius * 2)
            start = math.pi / 2
            arc_color = (
                config.COLOR_NEON_YELLOW if is_go else config.COLOR_NEON_MAGENTA
            )
            pygame.draw.arc(
                surface,
                arc_color,
                arc_rect,
                start,
                start + math.tau * fraction,
                8,
            )
            pygame.draw.arc(
                surface,
                config.COLOR_NEON_CYAN,
                arc_rect,
                start,
                start + math.tau * fraction,
                3,
            )

        pop = 1.0 - min(1.0, max(0.0, local) / max(0.001, duration * 0.6))
        scale = 1.0 + config.COUNTDOWN_POP_SCALE * pop * pop
        number_color = (
            config.COLOR_NEON_YELLOW if is_go else config.COLOR_WHITE_HOT
        )
        smooth = has_cjk(label)
        image = self._number_font.render(label, smooth, number_color)
        shadow = self._number_font.render(label, smooth, config.COLOR_NEON_MAGENTA)
        size = (
            max(1, round(image.get_width() * scale)),
            max(1, round(image.get_height() * scale)),
        )
        image = pygame.transform.scale(image, size)
        shadow = pygame.transform.scale(shadow, size)
        rect = image.get_rect(center=(cx, cy + 4))
        surface.blit(shadow, rect.move(6, 6))
        surface.blit(image, rect)

        draw_pixel_text(
            surface,
            t("countdown.skip"),
            self._footer_font,
            config.COLOR_TEXT_DIM,
            (cx, height - 36),
            shadow=1,
        )
