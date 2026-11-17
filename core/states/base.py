"""Shared contract for every game state."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

if TYPE_CHECKING:
    from core.game import Game


class GameState:
    """A screen with its own input, update and render behaviour."""

    def __init__(self, game: "Game") -> None:
        self.game = game

    def on_enter(self, **kwargs: object) -> None:
        pass

    def on_exit(self) -> None:
        pass

    def handle_event(self, event: pygame.event.Event) -> None:
        pass

    def update(self, dt: float) -> None:
        pass

    def post_update(self, dt: float) -> None:
        """Runs after the physics step, in the same fixed timestep."""
        pass

    def render(self, surface: pygame.Surface) -> None:
        pass
