"""Resource lookup that works both from source and from a PyInstaller bundle."""

from __future__ import annotations

import sys
from pathlib import Path


def package_root() -> Path:
    bundle = getattr(sys, "_MEIPASS", None)
    if bundle:
        return Path(bundle)
    return Path(__file__).resolve().parent.parent


def resource_path(*parts: str) -> Path:
    return package_root().joinpath(*parts)


def asset_path(name: str) -> Path:
    return resource_path("assets", name)


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))
