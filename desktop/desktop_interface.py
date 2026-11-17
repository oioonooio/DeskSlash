from __future__ import annotations

import ctypes
from dataclasses import dataclass, field

import pygame

from .errors import DesktopReadError, IconReadError
from .win32_desktop import (
    Win32DesktopReader,
    enable_dpi_awareness,
    is_supported as _win32_supported,
)

__all__ = [
    "DesktopIcon",
    "DesktopReadResult",
    "DesktopInterface",
    "DesktopReadError",
    "IconReadError",
    "enable_dpi_awareness",
]


@dataclass
class DesktopIcon:
    """One desktop item, already converted to a Pygame surface."""

    index: int
    name: str
    screen_position: tuple[int, int]
    image: pygame.Surface
    image_source: str
    alpha_range: tuple[int, int]
    shell_path: str | None

    @property
    def image_size(self) -> tuple[int, int]:
        return self.image.get_size()


@dataclass
class DesktopReadResult:
    icons: list[DesktopIcon] = field(default_factory=list)
    errors: list[IconReadError] = field(default_factory=list)
    total_items: int = 0
    listview_hwnd: int = 0
    screen_size: tuple[int, int] = (0, 0)


def _to_surface(image) -> tuple[pygame.Surface, tuple[int, int]]:
    rgba = image.convert("RGBA")
    alpha = rgba.getchannel("A").getextrema()
    surface = pygame.image.frombuffer(rgba.tobytes(), rgba.size, "RGBA").copy()
    return surface, (int(alpha[0]), int(alpha[1]))


class DesktopInterface:
    """Read-only bridge to the Windows desktop icon list.

    Every method here only reads. Desktop positions, names, files and
    shortcuts are never modified.
    """

    @property
    def is_supported(self) -> bool:
        return _win32_supported()

    def screen_size(self) -> tuple[int, int]:
        if not self.is_supported:
            return (0, 0)
        user32 = ctypes.windll.user32
        return (
            int(user32.GetSystemMetrics(0)),
            int(user32.GetSystemMetrics(1)),
        )

    def read_desktop_icons(self, icon_size: int | None = None) -> DesktopReadResult:
        """Enumerate desktop icons and read name, screen position and image.

        ``icon_size`` asks the Windows Shell for that pixel size (256 by
        default) so the game can display large, crisp icons. Individual
        failures are recorded in ``result.errors`` and the icon is skipped.
        A failure to locate or open the desktop listview raises
        ``DesktopReadError``.
        """
        if not self.is_supported:
            raise DesktopReadError("Desktop icon reading requires Windows.")

        with Win32DesktopReader() as reader:
            raw = reader.read_icons(icon_size)
            listview_hwnd = reader.listview_hwnd

        icons: list[DesktopIcon] = []
        for item in raw.icons:
            surface, alpha = _to_surface(item.image)
            icons.append(
                DesktopIcon(
                    index=item.index,
                    name=item.name,
                    screen_position=item.screen_position,
                    image=surface,
                    image_source=item.image_source,
                    alpha_range=alpha,
                    shell_path=item.shell_path,
                )
            )

        return DesktopReadResult(
            icons=icons,
            errors=raw.errors,
            total_items=raw.total_items,
            listview_hwnd=listview_hwnd,
            screen_size=self.screen_size(),
        )

    def list_desktop_icons(self) -> list[DesktopIcon]:
        return self.read_desktop_icons().icons
