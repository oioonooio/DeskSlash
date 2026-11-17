"""Runtime language switching for every visible string in Desktop Slash."""

from __future__ import annotations

from localization.language_manager import (
    LanguageManager,
    available_languages,
    current_language,
    get_language_manager,
    set_language,
    t,
)

__all__ = [
    "LanguageManager",
    "available_languages",
    "current_language",
    "get_language_manager",
    "set_language",
    "t",
]
