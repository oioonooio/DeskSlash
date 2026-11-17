"""Flat-key translation catalogue with a safe fallback to Simplified Chinese.

The manager deliberately has no pygame import so ``main.py`` can use it before
a display (or pygame itself) exists, for example to localise a startup error.
"""

from __future__ import annotations

import json
from pathlib import Path

import game_config as config


def _default_translations_dir() -> Path:
    here = Path(__file__).resolve().parent / "translations"
    if here.is_dir():
        return here
    try:
        from core.resources import resource_path

        bundled = resource_path("localization", "translations")
        if bundled.is_dir():
            return bundled
    except Exception:
        pass
    return here


def _flatten(value: object, prefix: str, out: dict[str, str]) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            _flatten(child, f"{prefix}.{key}" if prefix else str(key), out)
    elif isinstance(value, str):
        out[prefix] = value


class LanguageManager:
    """Loads one JSON catalogue per supported language and resolves keys."""

    def __init__(
        self,
        translations_dir: Path | None = None,
        default: str | None = None,
    ) -> None:
        self.directory = (
            Path(translations_dir) if translations_dir else _default_translations_dir()
        )
        self._catalogues: dict[str, dict[str, str]] = {}
        self._language = config.DEFAULT_LANGUAGE
        self._load()
        self.set_language(default or config.DEFAULT_LANGUAGE)

    # ------------------------------------------------------------------
    # Loading
    # ------------------------------------------------------------------
    def _load(self) -> None:
        for code in config.LANGUAGE_CHOICES:
            path = self.directory / f"{code}.json"
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                self._catalogues[code] = {}
                continue
            flat: dict[str, str] = {}
            _flatten(raw, "", flat)
            self._catalogues[code] = flat

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @property
    def language(self) -> str:
        return self._language

    def available(self) -> tuple[str, ...]:
        usable = tuple(
            code for code in config.LANGUAGE_CHOICES if self._catalogues.get(code)
        )
        return usable or (config.DEFAULT_LANGUAGE,)

    def set_language(self, code: str) -> bool:
        """Switch language; unknown or unloaded codes fall back safely."""
        requested = code if isinstance(code, str) else ""
        if requested in self._catalogues and self._catalogues[requested]:
            self._language = requested
            return True
        if self._catalogues.get(config.DEFAULT_LANGUAGE):
            self._language = config.DEFAULT_LANGUAGE
        else:
            usable = self.available()
            self._language = usable[0]
        return False

    # ------------------------------------------------------------------
    # Lookup
    # ------------------------------------------------------------------
    def t(self, key: str, **values: object) -> str:
        text = self._catalogues.get(self._language, {}).get(key)
        if text is None:
            text = self._catalogues.get(config.DEFAULT_LANGUAGE, {}).get(key)
        if text is None:
            return key
        if values:
            try:
                return text.format(**values)
            except (KeyError, IndexError, ValueError):
                return text
        return text


_MANAGER: LanguageManager | None = None


def get_language_manager() -> LanguageManager:
    global _MANAGER
    if _MANAGER is None:
        _MANAGER = LanguageManager()
    return _MANAGER


def current_language() -> str:
    return get_language_manager().language


def set_language(code: str) -> bool:
    return get_language_manager().set_language(code)


def available_languages() -> tuple[str, ...]:
    return get_language_manager().available()


def t(key: str, **values: object) -> str:
    return get_language_manager().t(key, **values)
