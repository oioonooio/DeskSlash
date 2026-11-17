"""The phases of a Desktop Slash session."""

from __future__ import annotations

from enum import Enum, auto


class GamePhase(Enum):
    MENU = auto()
    COUNTDOWN = auto()
    PLAYING = auto()
    PAUSED = auto()
    GAME_OVER = auto()
