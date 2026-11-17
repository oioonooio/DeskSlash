from __future__ import annotations

import math

import pygame

import game_config as config


class ScreenFX:
    """Full-screen shake, flash and CRT scanlines.

    Presentation only: the effects are applied when the finished scene is
    blitted to the window, so mouse coordinates and collision geometry are
    never shifted by a shake.
    """

    def __init__(self, size: tuple[int, int], scanlines: bool = True) -> None:
        self._size = size
        self._scanlines = _build_scanlines(size) if scanlines else None
        self._flash_layer = pygame.Surface(size, pygame.SRCALPHA)
        self.overlay_mode = False
        self.shake_enabled = True
        self.scanlines_enabled = scanlines
        self._offset = pygame.Vector2()
        self._shake_time = 0.0
        self._shake_duration = 0.0
        self._shake_strength = 0.0
        self._shake_elapsed = 0.0
        self._flash_time = 0.0
        self._flash_duration = 0.0
        self._flash_alpha = 0.0
        self._flash_color = config.COLOR_WHITE_HOT

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @property
    def is_shaking(self) -> bool:
        return self._shake_time > 0.0

    @property
    def is_flashing(self) -> bool:
        return self._flash_time > 0.0

    @property
    def offset(self) -> pygame.Vector2:
        return self._offset.copy()

    @property
    def shake_strength(self) -> float:
        return self._shake_strength

    def clear(self) -> None:
        self._shake_time = 0.0
        self._shake_duration = 0.0
        self._shake_strength = 0.0
        self._shake_elapsed = 0.0
        self._flash_time = 0.0
        self._flash_duration = 0.0
        self._flash_alpha = 0.0
        self._offset.update(0.0, 0.0)

    def cancel_shake(self) -> None:
        self._shake_time = 0.0
        self._shake_duration = 0.0
        self._shake_strength = 0.0
        self._shake_elapsed = 0.0
        self._offset.update(0.0, 0.0)

    # ------------------------------------------------------------------
    # Triggers
    # ------------------------------------------------------------------
    def shake(self, strength: float, duration: float) -> None:
        if not self.shake_enabled:
            return
        strength = min(config.SCREEN_SHAKE_MAX, max(0.0, strength))
        duration = max(0.01, duration)
        if strength <= 0.0:
            return
        # A new, stronger shake wins; a weak one must not cut it short.
        remaining = max(duration, self._shake_time)
        self._shake_strength = min(
            config.SCREEN_SHAKE_MAX,
            max(strength, self._shake_strength),
        )
        self._shake_time = remaining
        self._shake_duration = remaining
        self._shake_elapsed = 0.0

    def flash(
        self,
        color: tuple[int, int, int],
        duration: float | None = None,
        alpha: int | None = None,
    ) -> None:
        self._flash_color = color
        self._flash_duration = max(
            0.01, duration if duration is not None else config.BOMB_FLASH_DURATION
        )
        self._flash_time = self._flash_duration
        self._flash_alpha = max(
            0.0,
            min(255.0, float(alpha if alpha is not None else config.BOMB_FLASH_ALPHA)),
        )

    # ------------------------------------------------------------------
    # Simulation / presentation
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        if self._shake_time > 0.0:
            self._shake_time = max(0.0, self._shake_time - dt)
            self._shake_elapsed += dt
            if self._shake_time <= 0.0:
                self._shake_strength = 0.0
                self._offset.update(0.0, 0.0)
            else:
                strength = self._shake_strength * (self._shake_time / max(0.01, self._shake_duration))
                self._offset.update(
                    math.sin(self._shake_elapsed * 71.0) * strength,
                    math.cos(self._shake_elapsed * 53.0) * strength * 0.75,
                )

        if self._flash_time > 0.0:
            self._flash_time = max(0.0, self._flash_time - dt)

    def present(self, scene: pygame.Surface, target: pygame.Surface) -> None:
        clear = (
            config.WINDOW_TRANSPARENT_COLOR_KEY
            if self.overlay_mode
            else config.COLOR_BACKGROUND_TOP
        )
        target.fill(clear)
        target.blit(scene, (round(self._offset.x), round(self._offset.y)))
        # Scanlines would tint the real desktop through the colour-keyed
        # overlay, so overlay mode ignores the profile toggle.
        if self.scanlines_enabled and self._scanlines is not None:
            target.blit(self._scanlines, (0, 0))

        if self._flash_time > 0.0 and self._flash_alpha > 0.0:
            ratio = self._flash_time / max(0.01, self._flash_duration)
            alpha = int(self._flash_alpha * ratio**1.5)
            if alpha <= 0:
                return
            color = self._flash_color
            if config.FLASH_ADDITIVE:
                scaled = (
                    color[0] * alpha // 255,
                    color[1] * alpha // 255,
                    color[2] * alpha // 255,
                    255,
                )
                self._flash_layer.fill(scaled)
                target.blit(self._flash_layer, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
            else:
                self._flash_layer.fill((*color, alpha))
                target.blit(self._flash_layer, (0, 0))


def _build_scanlines(size: tuple[int, int]) -> pygame.Surface:
    width, height = size
    surface = pygame.Surface(size, pygame.SRCALPHA)
    spacing = max(2, config.SCANLINE_SPACING)
    alpha = max(0, min(255, config.SCANLINE_ALPHA))
    for y in range(0, height, spacing):
        pygame.draw.line(surface, (0, 0, 0, alpha), (0, y), (width, y))
    return surface
