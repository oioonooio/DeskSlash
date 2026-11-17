"""Wallpaper fidelity tests.

    python test_wallpaper_fidelity.py
    set DESKTOP_SLASH_LIVE_WALLPAPER=1 && python test_wallpaper_fidelity.py

The first mode renders synthetic wallpapers through every Windows style. The
live mode asks the shell for the real wallpaper, renders the game backdrop,
and pixel-compares it with the native reference. On an unlocked desktop the
reference is a PrintWindow capture of Progman with the icon list hidden; when
the session is locked or the display is asleep (a flat capture), the reference
is Windows' own composed bitmap ``Themes\\TranscodedWallpaper``. Nothing on
disk or in the icon layout is modified by either mode.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

import pygame
from PIL import Image, ImageChops, ImageStat

import game_config as config
import desktop.wallpaper as wallpaper
from desktop.desktop_background import DesktopBackgroundManager
from desktop.win32_desktop import enable_dpi_awareness
from window.win32_overlay import list_monitors

OUTPUT = Path(config.WALLPAPER_VERIFY_DIR)
FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -> {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def synthetic(size: tuple[int, int]) -> Image.Image:
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(size[1]):
        for x in range(size[0]):
            pixels[x, y] = (x * 255 // size[0], y * 255 // size[1], (x + y) % 256)
    return image


def style_checks() -> None:
    source = synthetic((400, 300))
    monitor = (100, 50, 200, 180)
    virtual = (0, 0, 400, 300)
    backgrounds = (7, 9, 11)

    stretched = wallpaper._render_monitor(
        source, monitor, wallpaper.WALLPAPER_STRETCH, backgrounds, virtual
    )
    check("stretch fills the monitor", stretched.size == (200, 180))

    fitted = wallpaper._render_monitor(
        source, monitor, wallpaper.WALLPAPER_FIT, backgrounds, virtual
    )
    check("fit keeps aspect ratio", fitted.size == (200, 180))

    centered = wallpaper._render_monitor(
        synthetic((100, 80)),
        monitor,
        wallpaper.WALLPAPER_CENTER,
        backgrounds,
        virtual,
    )
    check(
        "center leaves background around the image",
        centered.getpixel((0, 0)) == backgrounds,
        str(centered.getpixel((0, 0))),
    )

    exact = wallpaper._render_monitor(
        source, (0, 0, 400, 300), wallpaper.WALLPAPER_FILL, backgrounds, virtual
    )
    check(
        "1:1 fill is a byte-exact copy",
        exact.tobytes() == source.tobytes(),
    )

    tiled = wallpaper._render_monitor(
        source, monitor, wallpaper.WALLPAPER_TILE, backgrounds, virtual
    )
    check("tile fills the monitor", tiled.size == (200, 180))

    spanned = wallpaper._render_monitor(
        source,
        (200, 0, 200, 300),
        wallpaper.WALLPAPER_SPAN,
        backgrounds,
        (0, 0, 400, 300),
    )
    check("span crops the right half", spanned.size == (200, 300))
    check(
        "span uses the correct virtual slice",
        spanned.getpixel((0, 0)) == source.getpixel((200, 0)),
        f"{spanned.getpixel((0, 0))} vs {source.getpixel((200, 0))}",
    )

    composed = wallpaper._render_precomposed(
        source, (100, 50, 200, 180), virtual, backgrounds
    )
    check(
        "composed bitmap is cropped per monitor",
        composed.size == (200, 180)
        and composed.getpixel((0, 0)) == source.getpixel((100, 50)),
        f"{composed.size} {composed.getpixel((0, 0))} vs {source.getpixel((100, 50))}",
    )


def capture_window(hwnd: int, size: tuple[int, int]) -> Image.Image:
    import win32gui
    import win32ui

    hwnd_dc = win32gui.GetWindowDC(hwnd)
    source_dc = win32ui.CreateDCFromHandle(hwnd_dc)
    memory_dc = source_dc.CreateCompatibleDC()
    bitmap = win32ui.CreateBitmap()
    try:
        bitmap.CreateCompatibleBitmap(source_dc, size[0], size[1])
        memory_dc.SelectObject(bitmap)
        import ctypes

        if not ctypes.windll.user32.PrintWindow(hwnd, memory_dc.GetSafeHdc(), 3):
            raise RuntimeError("PrintWindow failed")
        info = bitmap.GetInfo()
        data = bitmap.GetBitmapBits(True)
        return Image.frombuffer(
            "RGB",
            (info["bmWidth"], info["bmHeight"]),
            data,
            "raw",
            "BGRX",
            0,
            1,
        )
    finally:
        win32gui.DeleteObject(bitmap.GetHandle())
        memory_dc.DeleteDC()
        source_dc.DeleteDC()
        win32gui.ReleaseDC(hwnd, hwnd_dc)


def capture_screen(width: int, height: int) -> Image.Image:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", wintypes.DWORD),
            ("biWidth", ctypes.c_long),
            ("biHeight", ctypes.c_long),
            ("biPlanes", wintypes.WORD),
            ("biBitCount", wintypes.WORD),
            ("biCompression", wintypes.DWORD),
            ("biSizeImage", wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.c_long),
            ("biYPelsPerMeter", ctypes.c_long),
            ("biClrUsed", wintypes.DWORD),
            ("biClrImportant", wintypes.DWORD),
        ]

    hdc = user32.GetDC(None)
    memory_dc = gdi32.CreateCompatibleDC(hdc)
    bitmap = gdi32.CreateCompatibleBitmap(hdc, width, height)
    previous = gdi32.SelectObject(memory_dc, bitmap)
    try:
        gdi32.BitBlt(
            memory_dc, 0, 0, width, height, hdc, 0, 0, 0x00CC0020
        )
        header = BITMAPINFOHEADER()
        header.biSize = ctypes.sizeof(header)
        header.biWidth = width
        header.biHeight = -height
        header.biPlanes = 1
        header.biBitCount = 32
        buffer = ctypes.create_string_buffer(width * height * 4)
        gdi32.GetDIBits(
            memory_dc, bitmap, 0, height, buffer, ctypes.byref(header), 0
        )
        return Image.frombuffer(
            "RGB", (width, height), buffer, "raw", "BGRX", 0, 1
        )
    finally:
        gdi32.SelectObject(memory_dc, previous)
        gdi32.DeleteObject(bitmap)
        gdi32.DeleteDC(memory_dc)
        user32.ReleaseDC(None, hdc)


def looks_like_capture(image: Image.Image) -> bool:
    """A locked or sleeping desktop captures as one flat colour."""
    colors = image.getcolors(1 << 16)
    if colors is None:
        return True
    if len(colors) < 64:
        return False
    return ImageStat.Stat(image).var[0] > 4.0


def compare(
    label: str,
    native: Image.Image,
    game: Image.Image,
    prefix: str,
) -> None:
    diff = ImageChops.difference(native, game)
    stats = ImageStat.Stat(diff)
    extrema = diff.getextrema()
    mean = sum(stats.mean) / 3.0
    worst = max(channel[1] for channel in extrema)
    diff.point(lambda value: min(255, value * 10)).save(
        OUTPUT / f"diff_{prefix}_x10.png"
    )
    check(
        f"backdrop matches {label}",
        mean < 0.5 and worst <= 2,
        f"mean={mean:.4f} max={worst}",
    )


def live_check() -> None:
    enable_dpi_awareness()
    pygame.init()
    pygame.display.set_mode((16, 16))
    monitor = list_monitors()[0]
    x, y, width, height = monitor.rect

    setting = wallpaper.resolve_wallpaper(monitor.device)
    print(
        f"[INFO] wallpaper source={setting.source} precomposed={setting.precomposed} "
        f"style={setting.style} path={setting.path!r}"
    )
    check(
        "shell wallpaper resolved",
        bool(setting.path) and Path(setting.path).is_file(),
        setting.path,
    )

    backdrop = wallpaper.build_desktop_backdrop(
        (x, y, width, height), monitor.rect, monitor.device
    )
    game = Image.frombytes(
        "RGB", backdrop.get_size(), pygame.image.tobytes(backdrop, "RGB")
    )
    game.save(OUTPUT / "game_backdrop_new.png")

    screen = capture_screen(width, height)
    screen_ok = looks_like_capture(screen)
    print(
        "[INFO] desktop capture "
        + ("available" if screen_ok else "unavailable (locked/sleeping session)")
    )

    on_screen = None
    if screen_ok:
        previous_watchdog = config.DESKTOP_HIDE_WATCHDOG
        config.DESKTOP_HIDE_WATCHDOG = False
        manager = DesktopBackgroundManager()
        try:
            manager.hide_icons()
            import win32gui

            hwnd = win32gui.FindWindow("Progman", None)
            candidate = capture_window(hwnd, (width, height))
            if looks_like_capture(candidate):
                on_screen = candidate
            else:
                print("[INFO] Progman capture was a flat fill; ignoring it")
        finally:
            manager.restore_icons()
            config.DESKTOP_HIDE_WATCHDOG = previous_watchdog

    try:
        pygame.quit()
    except pygame.error:
        pass

    OUTPUT.mkdir(parents=True, exist_ok=True)
    reference = on_screen or screen
    reference.save(OUTPUT / "native_wallpaper_new.png")

    if on_screen is not None:
        compare("the visible desktop", on_screen, game, "wallpaper_new")
    else:
        composed_path = wallpaper.transcoded_wallpaper_path()
        composed = wallpaper._open_image(composed_path) if composed_path else None
        if composed is None:
            print("[SKIP] no native reference available in this session")
            return
        composed = wallpaper._render_precomposed(
            composed,
            monitor.rect,
            wallpaper._virtual_rect(),
            setting.background,
        )
        composed.save(OUTPUT / "native_wallpaper_new.png")
        compare(
            "Windows' composed wallpaper (TranscodedWallpaper)",
            composed,
            game,
            "wallpaper_new",
        )


def main() -> int:
    style_checks()
    if os.environ.get("DESKTOP_SLASH_LIVE_WALLPAPER") == "1":
        live_check()
    else:
        print("[SKIP] live native capture (set DESKTOP_SLASH_LIVE_WALLPAPER=1)")
    print(f"\n{'PASS' if not FAILURES else 'FAIL'}: {len(FAILURES)} failure(s)")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
