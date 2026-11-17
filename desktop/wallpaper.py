"""Render the current Windows wallpaper as the overlay backdrop.

A topmost colour-keyed window reveals whatever window happens to be behind
it, not necessarily the wallpaper. To make the game really sit on the desktop
picture, the overlay paints the wallpaper itself (read-only from the file the
shell reports) and draws the game on top.

Only reads are performed: the shell wallpaper API (``IDesktopWallpaper``),
``SystemParametersInfoW``, two wallpaper preferences and the image file. The
wallpaper, desktop settings and icon layout are never modified.

Fidelity notes:
  * decoding and scaling happen in Pillow on opaque RGB data, so no alpha,
    premultiplied-alpha or pygame smoothscale filtering artefacts can appear;
  * an exact 1:1 wallpaper is never resampled;
  * resizing uses LANCZOS, close to the GDI+/DWM resampler, and avoids the
    visible grain of bilinear filtering.
"""

from __future__ import annotations

import ctypes
import os
import sys
from ctypes import wintypes
from dataclasses import dataclass

import pygame

import game_config as config

IS_WINDOWS = sys.platform == "win32"

SPI_GETDESKWALLPAPER = 0x0073
COLOR_DESKTOP = 1
SM_XVIRTUALSCREEN = 76
SM_YVIRTUALSCREEN = 77
SM_CXVIRTUALSCREEN = 78
SM_CYVIRTUALSCREEN = 79

CLSCTX_ALL = 0x17
COINIT_APARTMENTTHREADED = 0x2
RPC_E_CHANGED_MODE = 0x80010106
S_FALSE = 1

WALLPAPER_CENTER = 0
WALLPAPER_TILE = 1
WALLPAPER_STRETCH = 2
WALLPAPER_FIT = 3
WALLPAPER_FILL = 4
WALLPAPER_SPAN = 5

if IS_WINDOWS:
    _user32 = ctypes.windll.user32
    _user32.SystemParametersInfoW.argtypes = [
        wintypes.UINT,
        wintypes.UINT,
        ctypes.c_void_p,
        wintypes.UINT,
    ]
    _user32.SystemParametersInfoW.restype = wintypes.BOOL
    _user32.GetSysColor.argtypes = [ctypes.c_int]
    _user32.GetSysColor.restype = wintypes.DWORD
    _user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    _user32.GetSystemMetrics.restype = ctypes.c_int

    _ole32 = ctypes.windll.ole32
    _ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    _ole32.CoInitializeEx.restype = ctypes.c_long
    _ole32.CoUninitialize.argtypes = []
    _ole32.CoUninitialize.restype = None
    _ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(ctypes.c_byte),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(ctypes.c_byte),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    _ole32.CoCreateInstance.restype = ctypes.c_long
    _ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    _ole32.CoTaskMemFree.restype = None


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


_CLSID_DESKTOP_WALLPAPER = _GUID(
    0xC2CF3110,
    0x460E,
    0x4FC1,
    (ctypes.c_ubyte * 8)(0xB9, 0xD0, 0x8A, 0x1C, 0x0C, 0x9C, 0xC4, 0xBD),
)
_IID_IDESKTOP_WALLPAPER = _GUID(
    0xB92B56A9,
    0x8B55,
    0x4E14,
    (ctypes.c_ubyte * 8)(0x9A, 0x89, 0x01, 0x99, 0xBB, 0xB6, 0xF9, 0x3B),
)


def wallpaper_path() -> str:
    if not IS_WINDOWS:
        return ""
    buffer = ctypes.create_unicode_buffer(2048)
    if not _user32.SystemParametersInfoW(
        SPI_GETDESKWALLPAPER, len(buffer), buffer, 0
    ):
        return ""
    return buffer.value


def desktop_color() -> tuple[int, int, int]:
    if not IS_WINDOWS:
        return (8, 10, 20)
    value = int(_user32.GetSysColor(COLOR_DESKTOP))
    return (value & 0xFF, (value >> 8) & 0xFF, (value >> 16) & 0xFF)


def _registry_preferences() -> tuple[int, bool]:
    """Return ``(style, tile)`` for the legacy single-wallpaper setting."""
    if not IS_WINDOWS:
        return WALLPAPER_FILL, False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Control Panel\Desktop"
        ) as key:
            try:
                style = str(winreg.QueryValueEx(key, "WallpaperStyle")[0])
            except OSError:
                style = "10"
            try:
                tile = str(winreg.QueryValueEx(key, "TileWallpaper")[0])
            except OSError:
                tile = "0"
        styles = {
            "0": WALLPAPER_CENTER,
            "2": WALLPAPER_STRETCH,
            "6": WALLPAPER_FIT,
            "10": WALLPAPER_FILL,
            "22": WALLPAPER_SPAN,
        }
        return styles.get(style, WALLPAPER_FILL), tile == "1"
    except OSError:
        return WALLPAPER_FILL, False


def _read_wide(pointer: ctypes.c_void_p) -> str:
    if not pointer or not pointer.value:
        return ""
    try:
        return ctypes.wstring_at(pointer.value)
    finally:
        _ole32.CoTaskMemFree(pointer)


class DesktopWallpaperSession:
    """Minimal read-only ``IDesktopWallpaper`` wrapper (per-monitor aware)."""

    def __init__(self) -> None:
        self._ptr: ctypes.c_void_p | None = None
        self._co_initialized = False
        self._vtbl = None

    def __enter__(self) -> "DesktopWallpaperSession | None":
        result = _ole32.CoInitializeEx(None, COINIT_APARTMENTTHREADED)
        if result in (0, S_FALSE):
            self._co_initialized = True
        elif (result & 0xFFFFFFFF) != RPC_E_CHANGED_MODE:
            return None
        ptr = ctypes.c_void_p()
        hresult = _ole32.CoCreateInstance(
            ctypes.cast(
                ctypes.byref(_CLSID_DESKTOP_WALLPAPER),
                ctypes.POINTER(ctypes.c_byte),
            ),
            None,
            CLSCTX_ALL,
            ctypes.cast(
                ctypes.byref(_IID_IDESKTOP_WALLPAPER),
                ctypes.POINTER(ctypes.c_byte),
            ),
            ctypes.byref(ptr),
        )
        if hresult < 0 or not ptr.value:
            self._quit()
            return None
        self._ptr = ptr
        self._vtbl = ctypes.cast(
            ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        ).contents
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._ptr is not None:
            release = ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.c_void_p)(
                self._vtbl[2]
            )
            release(self._ptr)
            self._ptr = None
            self._vtbl = None
        self._quit()

    def _quit(self) -> None:
        if self._co_initialized:
            _ole32.CoUninitialize()
            self._co_initialized = False

    def _method(self, index: int, *argtypes: object):
        prototype = ctypes.WINFUNCTYPE(
            ctypes.c_long, ctypes.c_void_p, *argtypes
        )
        return prototype(self._vtbl[index])

    def monitor_count(self) -> int:
        count = wintypes.UINT()
        hresult = self._method(3, ctypes.POINTER(wintypes.UINT))(
            self._ptr, ctypes.byref(count)
        )
        return int(count.value) if hresult >= 0 else 0

    def monitor_device(self, index: int) -> str:
        pointer = ctypes.c_void_p()
        hresult = self._method(
            4, wintypes.UINT, ctypes.POINTER(ctypes.c_void_p)
        )(self._ptr, index, ctypes.byref(pointer))
        if hresult < 0:
            return ""
        return _read_wide(pointer)

    def wallpaper(self, monitor_id: str | None) -> str:
        # IDesktopWallpaper vtable: 7 = GetWallpaper (6 is SetWallpaper).
        pointer = ctypes.c_void_p()
        hresult = self._method(
            7, wintypes.LPCWSTR, ctypes.POINTER(ctypes.c_void_p)
        )(self._ptr, monitor_id, ctypes.byref(pointer))
        if hresult < 0:
            return ""
        return _read_wide(pointer)

    def position(self) -> int | None:
        # 10 = GetPosition (8 is GetBackgroundColor, 9 is SetBackgroundColor).
        value = ctypes.c_int()
        hresult = self._method(10, ctypes.POINTER(ctypes.c_int))(
            self._ptr, ctypes.byref(value)
        )
        if hresult < 0:
            return None
        return int(value.value)

    def background_color(self) -> tuple[int, int, int] | None:
        value = wintypes.DWORD()
        hresult = self._method(8, ctypes.POINTER(wintypes.DWORD))(
            self._ptr, ctypes.byref(value)
        )
        if hresult < 0:
            return None
        color = int(value.value)
        return (color & 0xFF, (color >> 8) & 0xFF, (color >> 16) & 0xFF)


@dataclass(frozen=True)
class WallpaperSetting:
    path: str
    style: int
    background: tuple[int, int, int]
    source: str = "shell"
    # Windows' own composed bitmap already has every monitor stitched in, so
    # the styles must not be applied to it again.
    precomposed: bool = False


def transcoded_wallpaper_path() -> str:
    """Windows' composed wallpaper bitmap (``Themes\\TranscodedWallpaper``).

    Modern personalisation can leave ``SPI_GETDESKWALLPAPER`` and
    ``IDesktopWallpaper`` empty (for example while the workstation is locked,
    or when per-monitor wallpapers are in use). The shell always keeps this
    file for the bitmap it is actually painting, so it is a read-only
    fallback, never a source of a different picture.
    """
    base = os.environ.get("APPDATA", "")
    if not base:
        return ""
    path = os.path.join(
        base, "Microsoft", "Windows", "Themes", "TranscodedWallpaper"
    )
    return path if os.path.isfile(path) else ""


def resolve_wallpaper(monitor_device: str = "") -> WallpaperSetting:
    """Return the best available wallpaper source for one monitor.

    Resolution order: shell per-monitor wallpaper, shell global wallpaper,
    ``SPI_GETDESKWALLPAPER``, then the shell's composed bitmap. Styling comes
    from the shell's ``GetPosition`` or the registry preferences.
    """
    fallback_path = wallpaper_path()
    style, tile = _registry_preferences()
    if tile:
        style = WALLPAPER_TILE
    fallback = WallpaperSetting(fallback_path, style, desktop_color())

    def composed() -> WallpaperSetting | None:
        path = transcoded_wallpaper_path()
        if not path:
            return None
        return WallpaperSetting(
            path, WALLPAPER_FILL, desktop_color(), "transcoded", True
        )

    if not IS_WINDOWS:
        return fallback

    try:
        with DesktopWallpaperSession() as session:
            if session is None:
                return composed() or fallback
            native_style = session.position()
            background = session.background_color() or fallback.background
            selected = ""
            if monitor_device:
                count = session.monitor_count()
                for index in range(count):
                    device = session.monitor_device(index)
                    if device.lower() == monitor_device.lower():
                        selected = session.wallpaper(device)
                        break
            if not selected:
                selected = session.wallpaper(None)
            if native_style is None:
                native_style = style
            if selected:
                return WallpaperSetting(
                    selected, int(native_style), background
                )
            return composed() or WallpaperSetting(
                fallback_path, int(native_style), background
            )
    except Exception:
        return composed() or fallback


def _open_image(path: str):
    """Decode to opaque RGB, honouring EXIF orientation; never keep alpha."""
    try:
        from PIL import Image, ImageOps
    except Exception:
        return None
    try:
        with Image.open(path) as raw:
            raw.seek(0)
            image = ImageOps.exif_transpose(raw)
            if image.mode != "RGB":
                image = image.convert("RGB")
            else:
                image = image.copy()
        return image
    except Exception:
        return None


def _resize(image, size: tuple[int, int]):
    from PIL import Image

    width, height = max(1, size[0]), max(1, size[1])
    if image.size == (width, height):
        return image
    return image.resize((width, height), Image.LANCZOS)


def _render_monitor(
    image,
    monitor_rect: tuple[int, int, int, int],
    style: int,
    background: tuple[int, int, int],
    virtual_rect: tuple[int, int, int, int],
):
    """Render one monitor at native pixels, matching the Windows style."""
    from PIL import Image

    mon_x, mon_y, mon_w, mon_h = monitor_rect
    canvas = Image.new("RGB", (mon_w, mon_h), background)

    if style == WALLPAPER_TILE:
        tile = image
        vx, vy, _vw, _vh = virtual_rect
        tile_w, tile_h = tile.size
        phase_x = (mon_x - vx) % max(1, tile_w)
        phase_y = (mon_y - vy) % max(1, tile_h)
        for y in range(-phase_y, mon_h, max(1, tile_h)):
            for x in range(-phase_x, mon_w, max(1, tile_w)):
                canvas.paste(tile, (x, y))
        return canvas

    if style == WALLPAPER_CENTER:
        canvas.paste(
            image,
            ((mon_w - image.width) // 2, (mon_h - image.height) // 2),
        )
        return canvas

    if style == WALLPAPER_STRETCH:
        canvas.paste(_resize(image, (mon_w, mon_h)), (0, 0))
        return canvas

    if style == WALLPAPER_FIT:
        ratio = min(mon_w / image.width, mon_h / image.height)
        size = (
            max(1, round(image.width * ratio)),
            max(1, round(image.height * ratio)),
        )
        scaled = _resize(image, size)
        canvas.paste(
            scaled,
            ((mon_w - scaled.width) // 2, (mon_h - scaled.height) // 2),
        )
        return canvas

    if style == WALLPAPER_SPAN:
        vx, vy, vw, vh = virtual_rect
        ratio = max(vw / image.width, vh / image.height)
        scaled = _resize(
            image,
            (
                max(1, round(image.width * ratio)),
                max(1, round(image.height * ratio)),
            ),
        )
        left = (scaled.width - vw) // 2
        top = (scaled.height - vh) // 2
        crop = scaled.crop(
            (
                left + (mon_x - vx),
                top + (mon_y - vy),
                left + (mon_x - vx) + mon_w,
                top + (mon_y - vy) + mon_h,
            )
        )
        canvas.paste(crop, (0, 0))
        return canvas

    # WALLPAPER_FILL (and unknown values): cover, centred crop.
    ratio = max(mon_w / image.width, mon_h / image.height)
    scaled = _resize(
        image,
        (
            max(1, round(image.width * ratio)),
            max(1, round(image.height * ratio)),
        ),
    )
    left = (scaled.width - mon_w) // 2
    top = (scaled.height - mon_h) // 2
    canvas.paste(
        scaled.crop((left, top, left + mon_w, top + mon_h)), (0, 0)
    )
    return canvas


def _virtual_rect() -> tuple[int, int, int, int]:
    if not IS_WINDOWS:
        return (0, 0, 0, 0)
    return (
        int(_user32.GetSystemMetrics(SM_XVIRTUALSCREEN)),
        int(_user32.GetSystemMetrics(SM_YVIRTUALSCREEN)),
        max(1, int(_user32.GetSystemMetrics(SM_CXVIRTUALSCREEN))),
        max(1, int(_user32.GetSystemMetrics(SM_CYVIRTUALSCREEN))),
    )


def _render_precomposed(
    image,
    monitor_rect: tuple[int, int, int, int],
    virtual_rect: tuple[int, int, int, int],
    background: tuple[int, int, int],
):
    """Crop one monitor out of a bitmap Windows already composed.

    ``TranscodedWallpaper`` is stored in physical pixels at the size of the
    virtual desktop, so no wallpaper style may be applied to it. If it does
    not cover the virtual desktop (older builds store only the primary
    monitor), it is scaled as-is instead of being cropped.
    """
    from PIL import Image

    mon_x, mon_y, mon_w, mon_h = monitor_rect
    vx, vy, vw, vh = virtual_rect
    canvas = Image.new("RGB", (mon_w, mon_h), background)
    if image.size == (vw, vh):
        left, top = mon_x - vx, mon_y - vy
        canvas.paste(
            image.crop((left, top, left + mon_w, top + mon_h)), (0, 0)
        )
    elif image.size == (mon_w, mon_h):
        canvas.paste(image, (0, 0))
    else:
        canvas.paste(_resize(image, (mon_w, mon_h)), (0, 0))
    return canvas


def _render_to_surface(image, monitor_rect, setting: WallpaperSetting):
    if setting.precomposed:
        rendered = _render_precomposed(
            image, monitor_rect, _virtual_rect(), setting.background
        )
    else:
        rendered = _render_monitor(
            image,
            monitor_rect,
            setting.style,
            setting.background,
            _virtual_rect(),
        )
    surface = pygame.image.frombytes(
        rendered.tobytes(), rendered.size, "RGB"
    )
    try:
        return surface.convert()
    except pygame.error:
        return surface


def build_desktop_backdrop(
    window_rect: tuple[int, int, int, int],
    monitor_rect: tuple[int, int, int, int],
    monitor_device: str = "",
) -> pygame.Surface:
    """Return a surface matching ``window_rect`` with the wallpaper painted.

    ``monitor_device`` is the Win32 device name (``\\\\.\\DISPLAY1``) so the
    shell can report a per-monitor wallpaper instead of the legacy global one.
    """
    window_x, window_y, window_w, window_h = window_rect
    monitor_x, monitor_y, monitor_w, monitor_h = monitor_rect
    setting = resolve_wallpaper(monitor_device)
    image = (
        _open_image(setting.path)
        if setting.path and os.path.isfile(setting.path)
        else None
    )
    if image is None:
        surface = pygame.Surface((window_w, window_h))
        surface.fill(setting.background)
        return surface

    surface = _render_to_surface(
        image,
        (monitor_x, monitor_y, monitor_w, monitor_h),
        setting,
    )
    if (window_x, window_y) != (monitor_x, monitor_y):
        offset = (monitor_x - window_x, monitor_y - window_y)
        cropped = pygame.Surface((window_w, window_h))
        cropped.fill(setting.background)
        cropped.blit(surface, offset)
        surface = cropped

    if config.OVERLAY_WALLPAPER_DIM > 0.0:
        veil = pygame.Surface((window_w, window_h), pygame.SRCALPHA)
        alpha = max(0, min(255, round(255 * config.OVERLAY_WALLPAPER_DIM)))
        veil.fill((0, 0, 0, alpha))
        surface.blit(veil, (0, 0))
    try:
        return surface.convert()
    except pygame.error:
        return surface
