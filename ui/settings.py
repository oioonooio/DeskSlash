from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

import game_config as config
from localization import t
from ui.button import draw_pixel_panel
from ui.fonts import get_font
from ui.text import draw_pixel_text

if TYPE_CHECKING:
    from core.game import Game


class SettingsOverlay:
    """Modal settings panel for volume, shake, scanlines and language."""

    ROW_VOLUME = 0
    ROW_SHAKE = 1
    ROW_SCANLINES = 2
    ROW_LANGUAGE = 3
    ROW_BACK = 4

    def __init__(self, size: tuple[int, int], game: "Game") -> None:
        width, height = size
        self._game = game
        self._open = False
        self._focused = 0
        panel_w = config.UI_SETTINGS_PANEL_WIDTH
        panel_h = config.UI_SETTINGS_PANEL_HEIGHT
        self._panel = pygame.Rect(0, 0, panel_w, panel_h)
        self._panel.center = (width // 2, height // 2)

        row_w = panel_w - 2 * config.UI_PANEL_PADDING
        row_h = 48
        gap = 12
        x = self._panel.centerx - row_w // 2
        y = self._panel.top + 118
        self._rows: list[pygame.Rect] = []
        for _ in range(5):
            self._rows.append(pygame.Rect(x, y, row_w, row_h))
            y += row_h + gap

        self._minus = pygame.Rect(0, 0, 34, 34)
        self._minus.center = (self._rows[0].right - 96, self._rows[0].centery)
        self._plus = pygame.Rect(0, 0, 34, 34)
        self._plus.center = (self._rows[0].right - 50, self._rows[0].centery)

        self._scrim = pygame.Surface(size, pygame.SRCALPHA)
        self._scrim.fill((3, 4, 10, 216))
        self._fonts_ready = False
        self.refresh_language()

    @property
    def is_open(self) -> bool:
        return self._open

    def open(self) -> None:
        self._open = True
        self._focused = 0

    def close(self) -> None:
        self._open = False

    def refresh_language(self) -> None:
        if not pygame.font.get_init():
            return
        self._title_font = get_font(config.FONT_SIZE_SETTINGS_TITLE, bold=True)
        self._label_font = get_font(config.FONT_SIZE_PROMPT, bold=True)
        # The language row is bilingual by design (语言 / LANGUAGE), so its
        # label always needs a Chinese-capable font, even in English mode.
        self._label_cjk_font = get_font(
            config.FONT_SIZE_PROMPT, bold=True, cjk=True
        )
        self._value_font = get_font(config.FONT_SIZE_HUD_COMBO, bold=True)
        self._value_cjk_font = get_font(
            config.FONT_SIZE_HUD_COMBO, bold=True, cjk=True
        )
        self._hint_font = get_font(config.FONT_SIZE_FOOTER)
        self._fonts_ready = True

    # ------------------------------------------------------------------
    # Input
    # ------------------------------------------------------------------
    def handle_event(self, event: pygame.event.Event) -> bool:
        if not self._open:
            return False

        if event.type == pygame.KEYDOWN:
            self._handle_key(event.key)
            return True
        if event.type == pygame.MOUSEMOTION:
            row = self._row_at(event.pos)
            if row is not None:
                self._focused = row
            return True
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self._handle_click(event.pos)
            return True
        return False

    def _handle_key(self, key: int) -> None:
        game = self._game
        rows = len(self._rows)
        if key == pygame.K_ESCAPE:
            game.sfx.play("click", 0.7)
            self.close()
        elif key in (pygame.K_UP, pygame.K_w):
            self._focused = (self._focused - 1) % rows
            game.sfx.play("click", 0.5)
        elif key in (pygame.K_DOWN, pygame.K_s):
            self._focused = (self._focused + 1) % rows
            game.sfx.play("click", 0.5)
        elif key in (pygame.K_LEFT, pygame.K_a):
            if self._focused == self.ROW_VOLUME:
                self._change_volume(-config.VOLUME_STEP)
            elif self._focused == self.ROW_LANGUAGE:
                self._cycle_language(-1)
        elif key in (pygame.K_RIGHT, pygame.K_d):
            if self._focused == self.ROW_VOLUME:
                self._change_volume(config.VOLUME_STEP)
            elif self._focused == self.ROW_LANGUAGE:
                self._cycle_language(1)
        elif key in (pygame.K_RETURN, pygame.K_SPACE, pygame.K_KP_ENTER):
            self._activate_row(self._focused)

    def _handle_click(self, position: tuple[int, int]) -> None:
        if not self._panel.collidepoint(position):
            self.close()
            return
        row = self._row_at(position)
        if row is None:
            return
        self._focused = row
        if row == self.ROW_VOLUME:
            if self._minus.collidepoint(position):
                self._change_volume(-config.VOLUME_STEP)
            elif self._plus.collidepoint(position):
                self._change_volume(config.VOLUME_STEP)
        elif row == self.ROW_LANGUAGE:
            self._cycle_language(1)
        else:
            self._activate_row(row)

    def _activate_row(self, row: int) -> None:
        game = self._game
        if row == self.ROW_VOLUME:
            self._change_volume(config.VOLUME_STEP)
        elif row == self.ROW_SHAKE:
            game.toggle_shake()
            game.sfx.play("click", 0.8)
        elif row == self.ROW_SCANLINES:
            game.toggle_scanlines()
            game.sfx.play("click", 0.8)
        elif row == self.ROW_LANGUAGE:
            self._cycle_language(1)
        else:
            game.sfx.play("click", 0.7)
            self.close()

    def _change_volume(self, delta: float) -> None:
        game = self._game
        game.adjust_volume(delta)
        game.sfx.play("click", 0.8)

    def _cycle_language(self, delta: int) -> None:
        game = self._game
        choices = list(config.LANGUAGE_CHOICES)
        current = game.profile.language
        if current not in choices:
            current = config.DEFAULT_LANGUAGE
        index = choices.index(current)
        new_language = choices[(index + delta) % len(choices)]
        game.sfx.play("click", 0.8)
        if new_language == current:
            return
        game.set_language(new_language)

    def _row_at(self, position: tuple[int, int]) -> int | None:
        for index, rect in enumerate(self._rows):
            if rect.collidepoint(position):
                return index
        return None

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface, game: "Game") -> None:
        if not self._open:
            return
        if not self._fonts_ready:
            self.refresh_language()
        if not game.is_overlay:
            surface.blit(self._scrim, (0, 0))
        draw_pixel_panel(surface, self._panel, config.COLOR_NEON_CYAN)
        draw_pixel_text(
            surface,
            t("settings.title"),
            self._title_font,
            config.COLOR_WHITE_HOT,
            (self._panel.centerx, self._panel.top + 50),
            shadow=3,
            outline=1,
            outline_color=config.COLOR_NEON_MAGENTA,
        )
        draw_pixel_text(
            surface,
            t("settings.subtitle"),
            self._hint_font,
            config.COLOR_TEXT_DIM,
            (self._panel.centerx, self._panel.top + 82),
            shadow=1,
        )

        profile = game.profile
        self._draw_row(surface, 0, t("settings.volume"), f"{int(round(profile.volume * 100))}%")
        self._draw_toggle_row(surface, 1, t("settings.shake"), profile.shake_enabled)
        self._draw_toggle_row(surface, 2, t("settings.scanlines"), profile.scanlines_enabled)
        self._draw_language_row(surface, 3, t("settings.language"))
        self._draw_row(surface, 4, t("settings.back"), "")

        draw_pixel_text(
            surface,
            t("settings.hint"),
            self._hint_font,
            config.COLOR_ACCENT_DIM,
            (self._panel.centerx, self._panel.bottom - 26),
            shadow=1,
        )

    def _draw_row(self, surface: pygame.Surface, index: int, label: str, value: str) -> None:
        row = self._rows[index]
        active = index == self._focused
        accent = config.COLOR_NEON_CYAN if index != self.ROW_BACK else config.COLOR_NEON_MAGENTA
        pygame.draw.rect(surface, (22, 30, 52) if active else (11, 15, 28), row)
        pygame.draw.rect(
            surface,
            accent if active else config.COLOR_PANEL_BORDER,
            row,
            1,
        )
        if active:
            pygame.draw.rect(surface, accent, (row.x, row.y, 5, row.height))

        if index == self.ROW_BACK:
            draw_pixel_text(
                surface,
                label,
                self._label_font,
                config.COLOR_WHITE_HOT if active else config.COLOR_TEXT,
                row.center,
                shadow=2,
            )
            return

        draw_pixel_text(
            surface,
            label,
            self._label_font,
            config.COLOR_WHITE_HOT if active else config.COLOR_TEXT,
            (row.x + 20, row.centery),
            "midleft",
            shadow=2,
        )
        draw_pixel_text(
            surface,
            value,
            self._value_font,
            accent if active else config.COLOR_TEXT_DIM,
            (row.right - 132, row.centery),
            "midright",
            shadow=1,
        )
        self._draw_adjust_box(surface, self._minus, "-", active)
        self._draw_adjust_box(surface, self._plus, "+", active)

    def _draw_language_row(self, surface: pygame.Surface, index: int, label: str) -> None:
        row = self._rows[index]
        active = index == self._focused
        pygame.draw.rect(surface, (22, 30, 52) if active else (11, 15, 28), row)
        pygame.draw.rect(
            surface,
            config.COLOR_NEON_CYAN if active else config.COLOR_PANEL_BORDER,
            row,
            1,
        )
        if active:
            pygame.draw.rect(surface, config.COLOR_NEON_CYAN, (row.x, row.y, 5, row.height))
        draw_pixel_text(
            surface,
            label,
            self._label_cjk_font,
            config.COLOR_WHITE_HOT if active else config.COLOR_TEXT,
            (row.x + 20, row.centery),
            "midleft",
            shadow=2,
        )
        language = self._game.profile.language
        name = config.LANGUAGE_LABELS.get(language, language)
        draw_pixel_text(
            surface,
            f"<  {name}  >",
            self._value_cjk_font,
            config.COLOR_NEON_YELLOW if active else config.COLOR_TEXT_DIM,
            (row.right - 24, row.centery),
            "midright",
            shadow=1,
        )

    def _draw_toggle_row(
        self,
        surface: pygame.Surface,
        index: int,
        label: str,
        enabled: bool,
    ) -> None:
        row = self._rows[index]
        active = index == self._focused
        value_color = config.COLOR_NEON_YELLOW if enabled else config.COLOR_DANGER
        pygame.draw.rect(surface, (22, 30, 52) if active else (11, 15, 28), row)
        pygame.draw.rect(
            surface,
            config.COLOR_NEON_CYAN if active else config.COLOR_PANEL_BORDER,
            row,
            1,
        )
        if active:
            pygame.draw.rect(surface, config.COLOR_NEON_CYAN, (row.x, row.y, 5, row.height))
        draw_pixel_text(
            surface,
            label,
            self._label_font,
            config.COLOR_WHITE_HOT if active else config.COLOR_TEXT,
            (row.x + 20, row.centery),
            "midleft",
            shadow=2,
        )
        draw_pixel_text(
            surface,
            t("settings.on") if enabled else t("settings.off"),
            self._value_font,
            value_color,
            (row.right - 24, row.centery),
            "midright",
            shadow=1,
        )

    def _draw_adjust_box(
        self,
        surface: pygame.Surface,
        rect: pygame.Rect,
        label: str,
        active: bool,
    ) -> None:
        pygame.draw.rect(surface, (30, 42, 72) if active else (18, 24, 42), rect)
        pygame.draw.rect(
            surface,
            config.COLOR_NEON_CYAN if active else config.COLOR_PANEL_BORDER,
            rect,
            1,
        )
        draw_pixel_text(
            surface,
            label,
            self._value_font,
            config.COLOR_WHITE_HOT if active else config.COLOR_TEXT_DIM,
            rect.center,
            shadow=0,
        )
