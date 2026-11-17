from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

from core.diagnostics import log
from core.phases import GamePhase
from core.states import (
    CountdownState,
    GameOverState,
    GameState,
    MenuState,
    PausedState,
    PlayingState,
)

if TYPE_CHECKING:
    from core.game import Game


class StateManager:
    """Owns one instance of every phase and forwards the active one."""

    def __init__(self, game: "Game") -> None:
        self._states: dict[GamePhase, GameState] = {
            GamePhase.MENU: MenuState(game),
            GamePhase.COUNTDOWN: CountdownState(game),
            GamePhase.PLAYING: PlayingState(game),
            GamePhase.PAUSED: PausedState(game),
            GamePhase.GAME_OVER: GameOverState(game),
        }
        self._phase: GamePhase | None = None
        self._current: GameState | None = None

    @property
    def phase(self) -> GamePhase | None:
        return self._phase

    def get(self, phase: GamePhase) -> GameState:
        return self._states[phase]

    def refresh_language(self) -> None:
        for state in self._states.values():
            refresh = getattr(state, "refresh_language", None)
            if refresh is not None:
                refresh()

    def change(self, phase: GamePhase, **kwargs: object) -> None:
        previous = self._phase
        if self._current is not None:
            self._current.on_exit()
        self._current = self._states[phase]
        self._phase = phase
        self._current.on_enter(**kwargs)
        log("GAME", f"phase {previous} -> {phase}")

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._current is not None:
            self._current.handle_event(event)

    def update(self, dt: float) -> None:
        if self._current is not None:
            self._current.update(dt)

    def post_update(self, dt: float) -> None:
        if self._current is not None:
            self._current.post_update(dt)

    def render(self, surface: pygame.Surface) -> None:
        if self._current is not None:
            self._current.render(surface)
