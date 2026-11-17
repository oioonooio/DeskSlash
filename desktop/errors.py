from __future__ import annotations

from dataclasses import dataclass


class DesktopReadError(RuntimeError):
    """Raised when the desktop icon source itself cannot be accessed."""


@dataclass(frozen=True)
class IconReadError:
    """A single desktop item that could not be read and was skipped."""

    index: int
    name: str
    stage: str
    message: str

    def format(self) -> str:
        label = self.name or "<unnamed>"
        return f"#{self.index} {label} [{self.stage}]: {self.message}"
