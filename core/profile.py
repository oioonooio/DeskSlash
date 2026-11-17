from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

import game_config as config


@dataclass
class Profile:
    """Player data persisted between sessions."""

    high_score: int = 0
    volume: float = config.DEFAULT_VOLUME
    shake_enabled: bool = True
    scanlines_enabled: bool = True
    language: str = config.DEFAULT_LANGUAGE


def default_profile_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        base = Path(appdata)
    else:
        base = Path.home() / ".desktop_slash"
    return base / config.PROFILE_DIR_NAME / config.PROFILE_FILE_NAME


class ProfileStore:
    """Reads and writes the profile as JSON, surviving missing or corrupt files."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path is not None else default_profile_path()
        self.last_error = ""

    def load(self) -> Profile:
        self.last_error = ""
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return Profile()
        except OSError as exc:
            self.last_error = f"read failed: {exc}"
            return Profile()

        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError) as exc:
            self.last_error = f"parse failed: {exc}"
            return Profile()
        if not isinstance(data, dict):
            self.last_error = "save file is not an object"
            return Profile()

        settings = data.get("settings")
        if not isinstance(settings, dict):
            settings = {}
        return Profile(
            high_score=_coerce_int(data.get("high_score"), 0, 0, 10**9),
            volume=_coerce_float(
                settings.get("volume"),
                config.DEFAULT_VOLUME,
                0.0,
                1.0,
            ),
            shake_enabled=_coerce_bool(settings.get("shake"), True),
            scanlines_enabled=_coerce_bool(settings.get("scanlines"), True),
            language=_coerce_language(
                settings.get("language"),
                config.DEFAULT_LANGUAGE,
            ),
        )

    def save(self, profile: Profile) -> bool:
        payload = {
            "version": config.PROFILE_VERSION,
            "high_score": max(0, int(profile.high_score)),
            "settings": {
                "volume": round(max(0.0, min(1.0, float(profile.volume))), 3),
                "shake": bool(profile.shake_enabled),
                "scanlines": bool(profile.scanlines_enabled),
                "language": _coerce_language(
                    profile.language,
                    config.DEFAULT_LANGUAGE,
                ),
            },
        }
        temp_path: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            handle, temp_name = tempfile.mkstemp(
                prefix=".save-",
                suffix=".tmp",
                dir=str(self.path.parent),
            )
            temp_path = Path(temp_name)
            with os.fdopen(handle, "w", encoding="utf-8") as stream:
                json.dump(payload, stream, indent=2)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_path, self.path)
            self.last_error = ""
            return True
        except (OSError, ValueError) as exc:
            self.last_error = f"write failed: {exc}"
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except OSError:
                    pass
            return False


def _coerce_int(value: object, default: int, low: int, high: int) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    try:
        return max(low, min(high, int(value)))
    except (OverflowError, ValueError):
        return default


def _coerce_float(value: object, default: float, low: float, high: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return default
    try:
        return max(low, min(high, float(value)))
    except (OverflowError, ValueError):
        return default


def _coerce_bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    return default


def _coerce_language(value: object, default: str) -> str:
    if isinstance(value, str) and value in config.LANGUAGE_CHOICES:
        return value
    return default
