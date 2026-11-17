"""Gameplay actors: desktop icons, spawning and slash recognition."""

from .game_icon import GameIcon
from .icon_manager import IconManager
from .slash_detector import SlashDetector, SlashHit

__all__ = ["GameIcon", "IconManager", "SlashDetector", "SlashHit"]
