"""Stage 5 standalone test for the transparent desktop overlay.

Run with a real Windows desktop (not a remote/headless session):

    python test_overlay_window.py                 # automated checks
    python test_overlay_window.py --interactive   # visual test card
    python test_overlay_window.py --no-input-probe --no-screen-probe

The automated run creates the real layered window for a few seconds. It
verifies window styles, hit-testing in both mouse modes, the invisible input
shield, colour-key transparency against an orange reference window, rendered
content, real mouse input, desktop layout preservation and full cleanup. The
interactive mode paints a test card over the live desktop so you can confirm
transparency by eye; SPACE toggles mouse mode, ESC exits.

Safety: the overlay only reads the desktop icon list. No icon is moved,
renamed or deleted, and the test never keeps a mouse capture after it exits.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import sys
import time
from ctypes import wintypes

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

import game_config as config
from desktop.desktop_interface import DesktopInterface, enable_dpi_awareness
from window.win32_overlay import (
    HTCLIENT,
    HTTRANSPARENT,
    IS_WINDOWS,
    WS_EX_LAYERED,
    WS_EX_TOOLWINDOW,
    WS_EX_TOPMOST,
    WS_EX_TRANSPARENT,
    get_monitor,
    list_monitors,
)
from window.window_manager import WindowManager, overlay_available, system_summary

GWL_STYLE = -16
WS_CAPTION = 0x00C00000
WS_THICKFRAME = 0x00040000
WS_EX_APPWINDOW = 0x00040000
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

if IS_WINDOWS:
    _user32 = ctypes.WinDLL("user32", use_last_error=True)
    _user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    _user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
    _user32.GetCursorPos.restype = wintypes.BOOL
    _user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
    _user32.SetCursorPos.restype = wintypes.BOOL
    _user32.mouse_event.argtypes = [
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        wintypes.DWORD,
        ctypes.c_void_p,
    ]
    _user32.mouse_event.restype = None
    _user32.GetForegroundWindow.restype = wintypes.HWND
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.DefWindowProcW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    _user32.DefWindowProcW.restype = ctypes.c_ssize_t
    _user32.RegisterClassW.argtypes = [ctypes.c_void_p]
    _user32.RegisterClassW.restype = wintypes.ATOM
    _user32.CreateWindowExW.argtypes = [
        wintypes.DWORD,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        wintypes.HWND,
        wintypes.HMENU,
        wintypes.HINSTANCE,
        ctypes.c_void_p,
    ]
    _user32.CreateWindowExW.restype = wintypes.HWND
    _user32.DestroyWindow.argtypes = [wintypes.HWND]
    _user32.DestroyWindow.restype = wintypes.BOOL
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    _kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    _kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    _gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    _gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    _gdi32.CreateSolidBrush.restype = wintypes.HBRUSH

_PASSED = 0
_FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> bool:
    global _PASSED, _FAILED
    if condition:
        _PASSED += 1
        print(f"[PASS] {name}")
    else:
        _FAILED += 1
        print(f"[FAIL] {name}" + (f" -> {detail}" if detail else ""))
    return condition


def skip(name: str, reason: str) -> None:
    print(f"[SKIP] {name} -> {reason}")


def _style(hwnd: int) -> int:
    return int(_user32.GetWindowLongPtrW(hwnd, GWL_STYLE))


def _cursor_position() -> tuple[int, int]:
    point = wintypes.POINT()
    _user32.GetCursorPos(ctypes.byref(point))
    return int(point.x), int(point.y)


def _set_cursor(position: tuple[int, int]) -> None:
    _user32.SetCursorPos(int(position[0]), int(position[1]))


def _pump(seconds: float, discard: bool = False) -> list[pygame.event.Event]:
    events: list[pygame.event.Event] = []
    end = time.time() + seconds
    while time.time() < end:
        pygame.event.pump()
        batch = pygame.event.get()
        if not discard:
            events.extend(batch)
        time.sleep(0.01)
    return events


def _desktop_signature(desktop: DesktopInterface) -> list[tuple[str, int, int]]:
    result = desktop.read_desktop_icons()
    return [(icon.name, icon.screen_position[0], icon.screen_position[1]) for icon in result.icons]


def _grab(bbox: tuple[int, int, int, int]):
    from PIL import ImageGrab

    return ImageGrab.grab(bbox=bbox, all_screens=True).convert("RGB")


def _diff_ratio(before, after) -> float:
    from PIL import ImageChops

    diff = ImageChops.difference(before, after).convert("L")
    histogram = diff.histogram()
    changed = sum(histogram[9:])
    pixels = max(1, before.width * before.height)
    return changed / pixels


def _probe_click(
    position: tuple[int, int],
) -> tuple[bool, bool, tuple[int, int] | None, tuple[int, int]]:
    _set_cursor(position)
    _pump(0.12, discard=True)
    actual = _cursor_position()
    _user32.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, None)
    time.sleep(0.04)
    _user32.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, None)
    events = _pump(0.35)
    down_pos = next(
        (
            event.pos
            for event in events
            if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1
        ),
        None,
    )
    down = down_pos is not None
    up = any(
        event.type == pygame.MOUSEBUTTONUP and event.button == 1 for event in events
    )
    return down, up, down_pos, actual


def _print_monitors() -> None:
    monitors = list_monitors()
    print(f"Monitors: {len(monitors)}")
    for monitor in monitors:
        print(f"  {monitor.describe()}")


class _Backdrop:
    """Solid orange reference window behind the overlay.

    Comparing screenshots against this window proves the colour key is really
    transparent: the pixels must stay orange, not turn into the key colour.
    """

    _class_ready = False
    _proc_ref = None
    _brush = None

    @classmethod
    def _ensure_class(cls) -> None:
        if cls._class_ready:
            return
        proc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        cls._proc_ref = proc_type(
            lambda hwnd, message, wparam, lparam: _user32.DefWindowProcW(
                hwnd, message, wparam, lparam
            )
        )

        class _WNDCLASSW(ctypes.Structure):
            _fields_ = [
                ("style", wintypes.UINT),
                ("lpfnWndProc", proc_type),
                ("cbClsExtra", ctypes.c_int),
                ("cbWndExtra", ctypes.c_int),
                ("hInstance", wintypes.HINSTANCE),
                ("hIcon", wintypes.HICON),
                ("hCursor", wintypes.HANDLE),
                ("hbrBackground", wintypes.HBRUSH),
                ("lpszMenuName", wintypes.LPCWSTR),
                ("lpszClassName", wintypes.LPCWSTR),
            ]

        cls._brush = _gdi32.CreateSolidBrush(255 | (140 << 8))
        wc = _WNDCLASSW()
        wc.style = 0x0002 | 0x0001
        wc.lpfnWndProc = cls._proc_ref
        wc.hInstance = _kernel32.GetModuleHandleW(None)
        wc.hbrBackground = cls._brush
        wc.lpszClassName = "DesktopSlashTestBackdrop"
        if not _user32.RegisterClassW(ctypes.byref(wc)):
            error = ctypes.get_last_error()
            if error != 1410:  # ERROR_CLASS_ALREADY_EXISTS
                raise OSError(f"RegisterClassW failed (WinError {error}).")
        cls._class_ready = True

    def __init__(self, rect: tuple[int, int, int, int]) -> None:
        self._ensure_class()
        x, y, width, height = rect
        self.hwnd = int(
            _user32.CreateWindowExW(
                0,
                "DesktopSlashTestBackdrop",
                "",
                0x80000000,  # WS_POPUP
                x,
                y,
                width,
                height,
                None,
                None,
                _kernel32.GetModuleHandleW(None),
                None,
            )
            or 0
        )
        if not self.hwnd:
            raise OSError(
                f"CreateWindowExW failed (WinError {ctypes.get_last_error()})."
            )
        _user32.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE

    def destroy(self) -> None:
        if self.hwnd:
            _user32.DestroyWindow(self.hwnd)
            self.hwnd = 0


def run_checks(args: argparse.Namespace) -> int:
    if not IS_WINDOWS:
        print("[SKIP] The overlay needs Windows.")
        return 0
    if not overlay_available():
        print("[SKIP] Overlay unavailable: a dummy/offscreen SDL video driver is set.")
        return 0

    enable_dpi_awareness()
    _print_monitors()
    monitor = get_monitor(args.monitor)
    if monitor is None:
        print("[FAIL] No monitor was reported.")
        return 1

    desktop = DesktopInterface()
    try:
        desktop_before = _desktop_signature(desktop)
    except Exception as exc:  # pragma: no cover - environment specific
        desktop_before = []
        print(f"  desktop signature unavailable: {exc}")
    cursor_before = _cursor_position()

    work_x, work_y, work_w, work_h = monitor.work_rect
    probe_bbox = (work_x + 30, work_y + 30, work_x + 230, work_y + 190)
    backdrop = None
    baseline = None
    if args.screen_probe:
        try:
            backdrop = _Backdrop(
                (
                    probe_bbox[0],
                    probe_bbox[1],
                    probe_bbox[2] - probe_bbox[0],
                    probe_bbox[3] - probe_bbox[1],
                )
            )
            time.sleep(0.25)
            baseline = _grab(probe_bbox)
        except Exception as exc:
            print(f"  screen probe disabled: {exc}")
            if backdrop is not None:
                backdrop.destroy()
                backdrop = None

    pygame.init()
    manager = WindowManager(overlay=True, monitor=args.monitor)
    try:
        screen = manager.create()
    except Exception as exc:
        print(f"[FAIL] Overlay creation raised: {exc}")
        if backdrop is not None:
            backdrop.destroy()
        pygame.quit()
        return 1

    if not check("overlay mode is used", manager.is_overlay, manager.overlay_error):
        manager.close()
        if backdrop is not None:
            backdrop.destroy()
        pygame.quit()
        return 1

    hwnd = manager.overlay.hwnd
    print(f"  {system_summary(manager)}")
    print(f"  hwnd=0x{hwnd:X} window_rect={manager.window_rect}")
    print(f"  monitor work_rect={monitor.work_rect} dpi={manager.dpi}")

    check("overlay window is visible", bool(_user32.IsWindowVisible(hwnd)))

    foreground = int(_user32.GetForegroundWindow() or 0)
    interactive = foreground == hwnd
    if not interactive:
        print(
            "\nNOTE: another window holds the foreground (a locked desktop or a"
            "\n      secure prompt). Style, hit-test and lifecycle checks still"
            "\n      run; screen and real-mouse probes are skipped. Unlock the"
            "\n      desktop and re-run for the full test.\n"
        )

    check(
        "window covers the monitor work area",
        manager.window_rect is not None
        and tuple(manager.window_rect[:2]) == (work_x, work_y)
        and tuple(manager.window_rect[2:]) == (work_w, work_h),
        f"{manager.window_rect} != {(work_x, work_y, work_w, work_h)}",
    )

    style = _style(hwnd)
    check(
        "borderless window (no caption / thick frame)",
        style & (WS_CAPTION | WS_THICKFRAME) == 0,
        f"style=0x{style:08X}",
    )

    exstyle = manager.exstyle()
    check("layered style WS_EX_LAYERED", bool(exstyle & WS_EX_LAYERED), f"0x{exstyle:08X}")
    check(
        "topmost style with a taskbar entry",
        bool(exstyle & WS_EX_TOPMOST) and not exstyle & WS_EX_TOOLWINDOW,
        f"0x{exstyle:08X}",
    )
    check(
        "input starts active (no WS_EX_TRANSPARENT)",
        not exstyle & WS_EX_TRANSPARENT,
        f"0x{exstyle:08X}",
    )

    center = (work_x + work_w // 2, work_y + work_h // 2)
    hit = manager.hit_test(*center)
    check("active hit-test returns HTCLIENT", hit == HTCLIENT, f"got {hit}")

    shield = manager.overlay.shield_hwnd
    print(f"  input shield hwnd=0x{shield:X}")
    check(
        "input shield exists",
        shield != 0 and bool(_user32.IsWindow(shield)),
    )
    check(
        "input shield is visible while active",
        shield != 0 and bool(_user32.IsWindowVisible(shield)),
    )
    if interactive:
        check(
            "input shield owns an empty (colour-keyed) pixel",
            manager.window_at(*center) == shield,
            f"WindowFromPoint={manager.window_at(*center)}",
        )
        probe_center = (
            (probe_bbox[0] + probe_bbox[2]) // 2,
            (probe_bbox[1] + probe_bbox[3]) // 2,
        )
        if backdrop is not None:
            check(
                "input shield sits above the colour-keyed area",
                manager.window_at(*probe_center) == shield,
                f"WindowFromPoint={manager.window_at(*probe_center)}",
            )
    else:
        print("[SKIP] input shield z-order probe (another window is foreground)")

    pygame.display.flip()
    time.sleep(0.2)

    if baseline is not None and interactive:
        try:
            after = _grab(probe_bbox)
            ratio = _diff_ratio(baseline, after)
            check(
                "colour key keeps the background visible through the overlay",
                ratio < 0.02,
                f"{ratio:.1%} of probe pixels changed",
            )
        except Exception as exc:
            skip(
                "colour key keeps the background visible through the overlay",
                str(exc),
            )

        card = pygame.Rect(0, 0, 280, 200)
        card.center = center
        screen.fill(config.WINDOW_TRANSPARENT_COLOR_KEY)
        pygame.draw.rect(screen, (255, 0, 255), card)
        pygame.display.flip()
        time.sleep(0.2)
        try:
            shot = _grab((card.left, card.top, card.right, card.bottom))
            pixel = shot.getpixel((card.width // 2, card.height // 2))
            check(
                "overlay content is visible above the desktop",
                all(abs(channel - target) < 24 for channel, target in zip(pixel, (255, 0, 255))),
                f"centre pixel={pixel}",
            )
        except Exception as exc:
            skip("overlay content is visible above the desktop", str(exc))
        finally:
            screen.fill(config.WINDOW_TRANSPARENT_COLOR_KEY)
            pygame.display.flip()
    elif baseline is not None:
        skip(
            "colour key keeps the background visible through the overlay",
            "desktop not foreground",
        )
        skip(
            "overlay content is visible above the desktop",
            "desktop not foreground",
        )

    if args.input_probe and interactive:
        down, up, down_pos, click_at = _probe_click(center)
        check("active mode receives mouse press", down)
        check("active mode receives mouse release", up)
        if down_pos is not None:
            expected = (click_at[0] - work_x, click_at[1] - work_y)
            drift = max(
                abs(down_pos[0] - expected[0]), abs(down_pos[1] - expected[1])
            )
            check(
                "click position is forwarded intact",
                drift <= 8,
                f"event={down_pos} expected={expected}",
            )
        _set_cursor(cursor_before)
    elif args.input_probe:
        skip("active mode receives mouse press", "desktop not foreground")
        skip("active mode receives mouse release", "desktop not foreground")

    manager.release_input()
    time.sleep(0.1)
    exstyle = manager.exstyle()
    check(
        "released mode sets WS_EX_TRANSPARENT",
        bool(exstyle & WS_EX_TRANSPARENT),
        f"0x{exstyle:08X}",
    )
    hit = manager.hit_test(*center)
    check("released hit-test returns HTTRANSPARENT", hit == HTTRANSPARENT, f"got {hit}")
    check(
        "input shield is hidden while released",
        shield != 0 and not _user32.IsWindowVisible(shield),
    )
    target = manager.window_at(*center)
    check(
        "desktop can be reached through the released overlay",
        target not in (hwnd, shield),
        f"WindowFromPoint={target} overlay={hwnd} shield={shield}",
    )
    check("no mouse capture is held", manager.capture_window() == 0)

    manager.acquire_input()
    time.sleep(0.1)
    check(
        "acquire clears click-through",
        not manager.exstyle() & WS_EX_TRANSPARENT,
        f"0x{manager.exstyle():08X}",
    )
    check("hit-test returns to HTCLIENT", manager.hit_test(*center) == HTCLIENT)
    check(
        "input shield is visible again after acquire",
        shield != 0 and bool(_user32.IsWindowVisible(shield)),
    )
    if interactive:
        check(
            "input shield is back on top after acquire",
            manager.window_at(*center) == shield,
            f"WindowFromPoint={manager.window_at(*center)}",
        )
    else:
        skip("input shield is back on top after acquire", "desktop not foreground")

    manager.close()
    check("window is destroyed after close", not _user32.IsWindow(hwnd))
    check("input shield is destroyed after close", not _user32.IsWindow(shield))
    check("display teardown left no capture", manager.capture_window() == 0)
    covered = manager.window_at(*center)
    check(
        "desktop is not covered after close",
        covered not in (hwnd, shield),
        f"WindowFromPoint={covered}",
    )
    WindowManager.emergency_restore()

    if desktop_before:
        try:
            desktop_after = _desktop_signature(desktop)
            check(
                "desktop icons unchanged (name + position)",
                desktop_after == desktop_before,
                f"{len(desktop_before)} -> {len(desktop_after)}",
            )
        except Exception as exc:
            skip("desktop icons unchanged (name + position)", str(exc))

    if backdrop is not None:
        backdrop.destroy()
    _set_cursor(cursor_before)
    pygame.quit()
    return 0


# ----------------------------------------------------------------------
# Interactive test card
# ----------------------------------------------------------------------
def run_interactive(args: argparse.Namespace) -> int:
    if not IS_WINDOWS or not overlay_available():
        print("[SKIP] The interactive overlay needs a real Windows desktop.")
        return 0

    enable_dpi_awareness()
    _print_monitors()
    pygame.init()
    manager = WindowManager(overlay=True, monitor=args.monitor)
    screen = manager.create()
    if not manager.is_overlay:
        print(f"[FAIL] Overlay creation failed: {manager.overlay_error}")
        pygame.quit()
        return 1

    from ui.fonts import get_font
    from ui.text import draw_pixel_text

    title_font = get_font(config.FONT_SIZE_TITLE, bold=True)
    body_font = get_font(config.FONT_SIZE_PROMPT, bold=True)
    small_font = get_font(config.FONT_SIZE_FOOTER)
    clock = pygame.time.Clock()
    marks: list[tuple[tuple[int, int], float]] = []
    width, height = screen.get_size()
    started = time.time()
    cursor_was = _cursor_position()
    running = True

    while running:
        dt = clock.tick(60) / 1000.0
        now = time.time()
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_SPACE:
                    if manager.input_mode == "active":
                        manager.release_input()
                    else:
                        manager.acquire_input()
            elif event.type == pygame.MOUSEBUTTONDOWN:
                marks.append((event.pos, now))
        marks = [item for item in marks if now - item[1] < 2.5]

        screen.fill(config.WINDOW_TRANSPARENT_COLOR_KEY)
        pygame.draw.rect(screen, config.COLOR_NEON_CYAN, (16, 16, width - 32, height - 32), 3)
        pygame.draw.line(
            screen,
            config.COLOR_NEON_MAGENTA,
            (width // 2, 0),
            (width // 2, height),
            1,
        )
        pygame.draw.line(
            screen,
            config.COLOR_NEON_MAGENTA,
            (0, height // 2),
            (width, height // 2),
            1,
        )
        phase = (now - started) % 4.0
        px = width // 2 + int((width * 0.32) * min(1.0, phase / 2.0) - width * 0.16)
        pygame.draw.circle(screen, config.COLOR_NEON_YELLOW, (px, height // 2), 24)
        pygame.draw.circle(screen, config.COLOR_WHITE_HOT, (px, height // 2), 10)
        for position, born in marks:
            age = now - born
            if age < 2.5:
                pygame.draw.circle(
                    screen,
                    config.COLOR_NEON_PURPLE,
                    position,
                    int(30 * (1.0 - age / 2.5)) + 2,
                    3,
                )

        draw_pixel_text(
            screen,
            "OVERLAY TEST CARD",
            title_font,
            config.COLOR_NEON_YELLOW,
            (width // 2, height * 0.16),
            shadow=4,
            outline=2,
            outline_color=config.COLOR_SHADOW,
        )
        mode = manager.input_mode.upper()
        mode_color = (
            config.COLOR_NEON_CYAN if mode == "ACTIVE" else config.COLOR_NEON_RED
        )
        draw_pixel_text(
            screen,
            f"MOUSE MODE: {mode}",
            body_font,
            mode_color,
            (width // 2, height * 0.24),
            shadow=2,
        )
        draw_pixel_text(
            screen,
            "HOLD LEFT MOUSE AND SWIPE · CLICKS LEAVE RINGS",
            small_font,
            config.COLOR_TEXT,
            (width // 2, height * 0.30),
            shadow=1,
        )
        draw_pixel_text(
            screen,
            "SPACE  TOGGLE ACTIVE / CLICK-THROUGH      ESC  EXIT",
            small_font,
            config.COLOR_TEXT_DIM,
            (width // 2, height - 48),
            shadow=1,
        )

        pygame.display.flip()

    manager.close()
    _set_cursor(cursor_was)
    pygame.quit()
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Desktop Slash overlay test")
    parser.add_argument("--monitor", type=int, default=config.WINDOW_OVERLAY_MONITOR)
    parser.add_argument("--interactive", action="store_true")
    parser.add_argument("--no-input-probe", action="store_true")
    parser.add_argument("--no-screen-probe", action="store_true")
    args = parser.parse_args()
    args.input_probe = not args.no_input_probe
    args.screen_probe = not args.no_screen_probe

    print("Desktop Slash - stage 5 overlay window checks")
    if args.interactive:
        return run_interactive(args)
    code = run_checks(args)
    if code == 0 and _PASSED + _FAILED:
        print(f"\n{_PASSED}/{_PASSED + _FAILED} checks passed")
    if _FAILED:
        return 1
    return code


if __name__ == "__main__":
    raise SystemExit(main())
