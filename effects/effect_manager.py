from __future__ import annotations

from typing import Protocol

import pygame

import game_config as config


class Effect(Protocol):
    finished: bool

    def update(self, dt: float) -> None: ...

    def draw(self, surface: pygame.Surface) -> None: ...


class EffectManager:
    """Bounded pipeline for short-lived, self-cleaning effect objects."""

    def __init__(self, max_active: int | None = None) -> None:
        self._effects: list[Effect] = []
        self._max_active = max(1, max_active or config.EFFECT_MAX_ACTIVE)
        self.skipped = 0

    def add(self, effect: Effect) -> bool:
        if len(self._effects) >= self._max_active:
            self.skipped += 1
            return False
        self._effects.append(effect)
        return True

    def clear(self) -> None:
        self._effects.clear()

    def update(self, dt: float) -> None:
        for effect in self._effects:
            effect.update(dt)
        self._effects = [effect for effect in self._effects if not effect.finished]

    def draw(self, surface: pygame.Surface) -> None:
        for effect in self._effects:
            effect.draw(surface)

    @property
    def max_active(self) -> int:
        return self._max_active

    def __len__(self) -> int:
        return len(self._effects)
