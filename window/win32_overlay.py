"""Win32 helpers for the transparent desktop overlay.

The overlay has two mutually exclusive mouse modes:

* active  -- the game owns the mouse. A layered colour-key window lets the
             mouse fall through its transparent pixels (documented Windows
             behaviour), so a second invisible window -- the input shield --
             sits above the overlay with a constant alpha of 1/255. It is
             visually irrelevant (0.4% tint) but every pixel is hit-testable,
             and presses are posted to the SDL window so Pygame sees them.
* released -- ``WM_NCHITTEST`` returns ``HTTRANSPARENT``, ``WS_EX_TRANSPARENT``
             is set and the input shield is hidden, so the desktop receives
             the mouse again.

Never combine ``WS_EX_TRANSPARENT`` with an input capture: the mode switch is
what prevents the two from fighting. No mouse capture or cursor clipping is
held outside a release call, so a crash cannot leave the desktop grabbed.
"""

from __future__ import annotations

import ctypes
import sys
from dataclasses import dataclass
from ctypes import wintypes

from core.diagnostics import log, log_once

IS_WINDOWS = sys.platform == "win32"

WM_DESTROY = 0x0002
WM_ACTIVATE = 0x0006
WM_SETFOCUS = 0x0007
WM_KILLFOCUS = 0x0008
WM_CLOSE = 0x0010
WM_QUERYENDSESSION = 0x0011
WM_ENDSESSION = 0x0016
WM_ACTIVATEAPP = 0x001C
WM_NCHITTEST = 0x0084
WM_MOUSEACTIVATE = 0x0021
WM_SETCURSOR = 0x0020
WM_ERASEBKGND = 0x0014
WM_MOUSEMOVE = 0x0200
WM_LBUTTONDOWN = 0x0201
WM_LBUTTONUP = 0x0202
WM_DISPLAYCHANGE = 0x007E
WM_DPICHANGED = 0x02E0

WA_INACTIVE = 0

HTTRANSPARENT = -1
HTCLIENT = 1
MA_NOACTIVATE = 3
MK_LBUTTON = 0x0001
IDC_ARROW = 32512

GWL_EXSTYLE = -20
GWLP_WNDPROC = -4

WS_EX_NOACTIVATE = 0x08000000
WS_POPUP = 0x80000000
CS_HREDRAW = 0x0002
CS_VREDRAW = 0x0001

WS_EX_TRANSPARENT = 0x00000020
WS_EX_TOPMOST = 0x00000008
WS_EX_TOOLWINDOW = 0x00000080
WS_EX_LAYERED = 0x00080000
WS_EX_APPWINDOW = 0x00040000

LWA_COLORKEY = 0x00000001
LWA_ALPHA = 0x00000002
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_FRAMECHANGED = 0x0020
SWP_SHOWWINDOW = 0x0040
SWP_NOOWNERZORDER = 0x0200

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
HWND_BOTTOM = 1
SW_HIDE = 0
SW_SHOW = 5

VK_ESCAPE = 0x1B
VK_CONTROL = 0x11
VK_SHIFT = 0x10
VK_Q = 0x51
MONITORINFOF_PRIMARY = 1
MDT_EFFECTIVE_DPI = 0


@dataclass(frozen=True)
class MonitorInfo:
    index: int
    handle: int
    rect: tuple[int, int, int, int]
    work_rect: tuple[int, int, int, int]
    dpi: int
    primary: bool
    device: str

    @property
    def size(self) -> tuple[int, int]:
        return self.rect[2], self.rect[3]

    @property
    def work_size(self) -> tuple[int, int]:
        return self.work_rect[2], self.work_rect[3]

    def describe(self) -> str:
        x, y, w, h = self.rect
        wx, wy, ww, wh = self.work_rect
        return (
            f"monitor {self.index} {w}x{h} at ({x},{y}) "
            f"work={ww}x{wh} at ({wx},{wy}) dpi={self.dpi}"
            f"{' primary' if self.primary else ''}"
        )


class _MONITORINFOEXW(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
        ("szDevice", wintypes.WCHAR * 32),
    ]


if IS_WINDOWS:
    user32 = ctypes.WinDLL("user32", use_last_error=True)

    user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.SetWindowLongPtrW.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_ssize_t,
    ]
    user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
    user32.CallWindowProcW.argtypes = [
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.CallWindowProcW.restype = ctypes.c_ssize_t
    user32.SetLayeredWindowAttributes.argtypes = [
        wintypes.HWND,
        wintypes.COLORREF,
        ctypes.c_ubyte,
        wintypes.DWORD,
    ]
    user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
    user32.SetWindowPos.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_uint,
    ]
    user32.SetWindowPos.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
    user32.GetWindowRect.restype = wintypes.BOOL
    user32.IsWindow.argtypes = [wintypes.HWND]
    user32.IsWindow.restype = wintypes.BOOL
    user32.SendMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.SendMessageW.restype = ctypes.c_ssize_t
    user32.SetCapture.argtypes = [wintypes.HWND]
    user32.SetCapture.restype = wintypes.HWND
    user32.GetCapture.argtypes = []
    user32.GetCapture.restype = wintypes.HWND
    user32.ClipCursor.argtypes = [ctypes.POINTER(wintypes.RECT)]
    user32.ClipCursor.restype = wintypes.BOOL
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    user32.SetForegroundWindow.restype = wintypes.BOOL
    user32.SetFocus.argtypes = [wintypes.HWND]
    user32.SetFocus.restype = wintypes.HWND
    user32.WindowFromPoint.argtypes = [wintypes.POINT]
    user32.WindowFromPoint.restype = wintypes.HWND
    user32.EnumDisplayMonitors.argtypes = [
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        ctypes.c_void_p,
        wintypes.LPARAM,
    ]
    user32.EnumDisplayMonitors.restype = wintypes.BOOL
    user32.GetMonitorInfoW.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_MONITORINFOEXW),
    ]
    user32.GetMonitorInfoW.restype = wintypes.BOOL
    user32.PostMessageW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.PostMessageW.restype = wintypes.BOOL
    user32.RegisterClassW.argtypes = [ctypes.c_void_p]
    user32.RegisterClassW.restype = wintypes.ATOM
    user32.CreateWindowExW.argtypes = [
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
    user32.CreateWindowExW.restype = wintypes.HWND
    user32.DefWindowProcW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    ]
    user32.DefWindowProcW.restype = ctypes.c_ssize_t
    user32.DestroyWindow.argtypes = [wintypes.HWND]
    user32.DestroyWindow.restype = wintypes.BOOL
    user32.LoadCursorW.argtypes = [wintypes.HINSTANCE, ctypes.c_void_p]
    user32.LoadCursorW.restype = wintypes.HANDLE
    user32.SetCursor.argtypes = [wintypes.HANDLE]
    user32.SetCursor.restype = wintypes.HANDLE

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetModuleHandleW.argtypes = [wintypes.LPCWSTR]
    kernel32.GetModuleHandleW.restype = wintypes.HMODULE
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    gdi32.CreateSolidBrush.argtypes = [wintypes.COLORREF]
    gdi32.CreateSolidBrush.restype = wintypes.HBRUSH

    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        shcore.GetDpiForMonitor.argtypes = [
            wintypes.HANDLE,
            ctypes.c_int,
            ctypes.POINTER(wintypes.UINT),
            ctypes.POINTER(wintypes.UINT),
        ]
        shcore.GetDpiForMonitor.restype = ctypes.c_long
    except (AttributeError, OSError):
        shcore = None

    try:
        user32.GetDpiForWindow.argtypes = [wintypes.HWND]
        user32.GetDpiForWindow.restype = wintypes.UINT
    except AttributeError:
        pass

    user32.GetForegroundWindow.argtypes = []
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetActiveWindow.argtypes = []
    user32.GetActiveWindow.restype = wintypes.HWND
    user32.IsIconic.argtypes = [wintypes.HWND]
    user32.IsIconic.restype = wintypes.BOOL
    user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]
    user32.GetAncestor.restype = wintypes.HWND


def is_supported() -> bool:
    return IS_WINDOWS


def list_monitors() -> list[MonitorInfo]:
    """Enumerate monitors as physical-pixel rectangles, primary first."""
    if not IS_WINDOWS:
        return []

    found: list[MonitorInfo] = []
    callback_type = ctypes.WINFUNCTYPE(
        wintypes.BOOL,
        wintypes.HANDLE,
        wintypes.HDC,
        ctypes.POINTER(wintypes.RECT),
        wintypes.LPARAM,
    )

    @callback_type
    def _callback(hmonitor, _hdc, _rect, _lparam):
        info = _MONITORINFOEXW()
        info.cbSize = ctypes.sizeof(_MONITORINFOEXW)
        if not user32.GetMonitorInfoW(hmonitor, ctypes.byref(info)):
            return True
        dpi = 96
        if shcore is not None:
            dx = wintypes.UINT()
            dy = wintypes.UINT()
            if shcore.GetDpiForMonitor(
                hmonitor, MDT_EFFECTIVE_DPI, ctypes.byref(dx), ctypes.byref(dy)
            ) == 0:
                dpi = int(dx.value or 96)
        monitor = info.rcMonitor
        work = info.rcWork
        found.append(
            MonitorInfo(
                index=0,
                handle=int(hmonitor),
                rect=(
                    int(monitor.left),
                    int(monitor.top),
                    int(monitor.right - monitor.left),
                    int(monitor.bottom - monitor.top),
                ),
                work_rect=(
                    int(work.left),
                    int(work.top),
                    int(work.right - work.left),
                    int(work.bottom - work.top),
                ),
                dpi=dpi,
                primary=bool(info.dwFlags & MONITORINFOF_PRIMARY),
                device=str(info.szDevice),
            )
        )
        return True

    user32.EnumDisplayMonitors(None, None, _callback, 0)
    found.sort(key=lambda item: (not item.primary, item.rect[0], item.rect[1]))
    return [
        MonitorInfo(
            index=index,
            handle=item.handle,
            rect=item.rect,
            work_rect=item.work_rect,
            dpi=item.dpi,
            primary=item.primary,
            device=item.device,
        )
        for index, item in enumerate(found)
    ]


def get_monitor(index: int = 0) -> MonitorInfo | None:
    monitors = list_monitors()
    if not monitors:
        return None
    if 0 <= index < len(monitors):
        return monitors[index]
    return monitors[0]


def dpi_for_window(hwnd: int) -> int:
    if not IS_WINDOWS or not hwnd:
        return 96
    try:
        return int(user32.GetDpiForWindow(hwnd) or 96)
    except AttributeError:
        return 96


def window_from_point(x: int, y: int) -> int:
    if not IS_WINDOWS:
        return 0
    return int(user32.WindowFromPoint(wintypes.POINT(x, y)) or 0)


def foreground_window() -> int:
    if not IS_WINDOWS:
        return 0
    return int(user32.GetForegroundWindow() or 0)


def window_is_foreground(hwnd: int) -> bool:
    """True when *hwnd* (or its root) is the active foreground window."""
    if not IS_WINDOWS or not hwnd:
        return True
    foreground = int(user32.GetForegroundWindow() or 0)
    if not foreground:
        return False
    return int(user32.GetAncestor(foreground, 2) or foreground) == int(
        user32.GetAncestor(hwnd, 2) or hwnd
    )


def window_is_minimized(hwnd: int) -> bool:
    if not IS_WINDOWS or not hwnd:
        return False
    try:
        return bool(user32.IsIconic(hwnd))
    except Exception:
        return False


def set_window_topmost(hwnd: int, enabled: bool) -> bool:
    """Move a window in or out of the topmost band without activating it.

    Leaving the band is not enough on its own: ``HWND_NOTOPMOST`` drops a
    window at the *top* of the normal band, which would still cover the app
    the user just switched to. ``HWND_BOTTOM`` then parks the overlay behind
    every other window, so it can never occlude a foreground application.
    """
    if not IS_WINDOWS or not hwnd:
        return False
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER
    try:
        if enabled:
            return bool(user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, flags))
        ok = bool(user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, flags))
        if ok:
            ok = bool(user32.SetWindowPos(hwnd, HWND_BOTTOM, 0, 0, 0, 0, flags))
        return ok
    except Exception:
        return False


def release_system_input() -> None:
    """Release any capture/clip left behind by an abnormal shutdown."""
    if not IS_WINDOWS:
        return
    try:
        user32.SetCapture(None)
        user32.ClipCursor(None)
    except Exception:
        pass


def emergency_exit_down() -> bool:
    """True while Ctrl+Shift+Q is held.

    ``GetAsyncKeyState`` is used instead of ``RegisterHotKey`` so no global
    hotkey is ever left registered in the OS. It works in both overlay and
    normal-window mode.
    """
    if not IS_WINDOWS:
        return False
    try:
        keys = (VK_CONTROL, VK_SHIFT, VK_Q)
        return all(user32.GetAsyncKeyState(key) & 0x8000 for key in keys)
    except Exception:
        return False


if IS_WINDOWS:
    _WNDPROC = ctypes.WINFUNCTYPE(
        ctypes.c_ssize_t,
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
    )

    class _WNDCLASSW(ctypes.Structure):
        _fields_ = [
            ("style", wintypes.UINT),
            ("lpfnWndProc", _WNDPROC),
            ("cbClsExtra", ctypes.c_int),
            ("cbWndExtra", ctypes.c_int),
            ("hInstance", wintypes.HINSTANCE),
            ("hIcon", wintypes.HICON),
            ("hCursor", wintypes.HANDLE),
            ("hbrBackground", wintypes.HBRUSH),
            ("lpszMenuName", wintypes.LPCWSTR),
            ("lpszClassName", wintypes.LPCWSTR),
        ]


_SHIELD_CLASS_NAME = "DesktopSlashInputShield"
_shield_class_registered = False
_shield_proc_ref = None
_shield_by_hwnd: dict[int, "InputShield"] = {}


def _register_shield_class() -> None:
    global _shield_class_registered, _shield_proc_ref
    if _shield_class_registered:
        return
    _shield_proc_ref = _WNDPROC(_shield_dispatch)
    wc = _WNDCLASSW()
    wc.style = CS_HREDRAW | CS_VREDRAW
    wc.lpfnWndProc = _shield_proc_ref
    wc.hInstance = kernel32.GetModuleHandleW(None)
    wc.hCursor = user32.LoadCursorW(None, ctypes.c_void_p(IDC_ARROW))
    wc.hbrBackground = gdi32.CreateSolidBrush(0)
    wc.lpszClassName = _SHIELD_CLASS_NAME
    if not user32.RegisterClassW(ctypes.byref(wc)):
        error = ctypes.get_last_error()
        if error != 1410:  # ERROR_CLASS_ALREADY_EXISTS
            raise OSError(f"RegisterClassW failed (WinError {error}).")
    _shield_class_registered = True


def _shield_dispatch(hwnd, message, wparam, lparam):
    shield = _shield_by_hwnd.get(int(hwnd or 0))
    if shield is not None:
        return shield.handle_message(hwnd, message, wparam, lparam)
    return user32.DefWindowProcW(hwnd, message, wparam, lparam)


class InputShield:
    """Invisible, fully clickable window that sits above the overlay.

    A layered colour-key window lets the mouse fall through its transparent
    pixels, so a swipe that starts on empty space would reach the desktop.
    This window uses a constant alpha of 1/255: it darkens the scene by 0.4%
    and every pixel stays hit-testable. Mouse messages are posted to the SDL
    window, so Pygame receives ordinary events; SDL's own capture then routes
    the rest of a drag. Hiding it hands the desktop back its mouse.
    """

    def __init__(self, target_hwnd: int, rect: tuple[int, int, int, int]) -> None:
        if not IS_WINDOWS:
            raise RuntimeError("The input shield is only available on Windows.")
        _register_shield_class()
        self.target_hwnd = int(target_hwnd)
        self.rect = tuple(rect)
        x, y, width, height = self.rect
        self.hwnd = int(
            user32.CreateWindowExW(
                WS_EX_LAYERED
                | WS_EX_TOOLWINDOW
                | WS_EX_TOPMOST
                | WS_EX_NOACTIVATE,
                _SHIELD_CLASS_NAME,
                "Desktop Slash input",
                WS_POPUP,
                x,
                y,
                width,
                height,
                None,
                None,
                kernel32.GetModuleHandleW(None),
                None,
            )
            or 0
        )
        if not self.hwnd:
            raise OSError(
                f"CreateWindowExW failed (WinError {ctypes.get_last_error()})."
            )
        _shield_by_hwnd[self.hwnd] = self
        self._visible = False
        self._offset = (0, 0)
        if not user32.SetLayeredWindowAttributes(
            self.hwnd, 0, 1, LWA_ALPHA
        ):
            error = ctypes.get_last_error()
            self.destroy()
            raise OSError(
                f"SetLayeredWindowAttributes failed (WinError {error})."
            )

    @property
    def visible(self) -> bool:
        return self._visible

    def show(self) -> None:
        if not self.hwnd:
            return
        target = wintypes.RECT()
        if user32.GetWindowRect(self.target_hwnd, ctypes.byref(target)):
            self.rect = (
                int(target.left),
                int(target.top),
                int(target.right - target.left),
                int(target.bottom - target.top),
            )
        x, y, width, height = self.rect
        user32.ShowWindow(self.hwnd, 8)  # SW_SHOWNOACTIVATE
        user32.SetWindowPos(
            self.hwnd,
            HWND_TOPMOST,
            x,
            y,
            width,
            height,
            SWP_NOACTIVATE | SWP_SHOWWINDOW,
        )
        shield_rect = wintypes.RECT()
        if user32.GetWindowRect(self.hwnd, ctypes.byref(shield_rect)):
            self._offset = (
                int(shield_rect.left) - x,
                int(shield_rect.top) - y,
            )
        if not self._visible:
            log("WINDOW", f"input shield shown hwnd=0x{self.hwnd:X}")
        self._visible = True

    def hide(self) -> None:
        if not self.hwnd:
            return
        user32.ShowWindow(self.hwnd, SW_HIDE)
        if self._visible:
            log("WINDOW", f"input shield hidden hwnd=0x{self.hwnd:X}")
        self._visible = False

    def destroy(self) -> None:
        hwnd = self.hwnd
        if not hwnd:
            return
        self.hwnd = 0
        self._visible = False
        _shield_by_hwnd.pop(hwnd, None)
        try:
            user32.DestroyWindow(hwnd)
        except Exception:
            pass

    def handle_message(self, hwnd, message, wparam, lparam):
        if message == WM_NCHITTEST:
            # Even if the shield is still visible for a frame around a focus
            # transition, a background game must not swallow the click: let
            # the hit-test fall through to the window below.
            if not window_is_foreground(self.target_hwnd):
                return HTTRANSPARENT
            return HTCLIENT
        if message == WM_MOUSEACTIVATE:
            return MA_NOACTIVATE
        if message == WM_ERASEBKGND:
            return 1
        if message == WM_SETCURSOR:
            user32.SetCursor(
                user32.LoadCursorW(None, ctypes.c_void_p(IDC_ARROW))
            )
            return 1
        if message == WM_MOUSEMOVE:
            held = bool(int(user32.GetAsyncKeyState(0x01)) & 0x8000)
            self._forward(WM_MOUSEMOVE, lparam, MK_LBUTTON if held else 0)
            return 0
        if message == WM_LBUTTONDOWN:
            self._forward(WM_MOUSEMOVE, lparam, 0)
            self._forward(WM_LBUTTONDOWN, lparam, MK_LBUTTON)
            return 0
        if message == WM_LBUTTONUP:
            self._forward(WM_MOUSEMOVE, lparam, 0)
            self._forward(WM_LBUTTONUP, lparam, 0)
            return 0
        return user32.DefWindowProcW(hwnd, message, wparam, lparam)

    def _forward(self, message: int, lparam, wparam: int) -> None:
        if not self.target_hwnd or not user32.IsWindow(self.target_hwnd):
            return
        if not window_is_foreground(self.target_hwnd):
            # Never deliver game input while another app owns the foreground;
            # the shield can still be visible for a few milliseconds around a
            # focus transition.
            return
        x = ctypes.c_short(int(lparam) & 0xFFFF).value + self._offset[0]
        y = ctypes.c_short((int(lparam) >> 16) & 0xFFFF).value + self._offset[1]
        packed = ((y & 0xFFFF) << 16) | (x & 0xFFFF)
        user32.PostMessageW(self.target_hwnd, message, wparam, packed)


class Win32Overlay:
    """Styles, hit-testing and input mode for one layered Pygame window."""

    def __init__(
        self,
        hwnd: int,
        color_key: tuple[int, int, int],
        *,
        topmost: bool = True,
        toolwindow: bool = True,
    ) -> None:
        if not IS_WINDOWS:
            raise RuntimeError("The desktop overlay is only available on Windows.")
        self.hwnd = int(hwnd)
        self.color_key = color_key
        self.topmost = topmost
        self.toolwindow = toolwindow
        self.input_mode = "active"
        self._active = True
        self._closed = False
        self._original_exstyle = 0
        self._original_wndproc = 0
        self._wndproc = None
        self._shield: InputShield | None = None
        self._native_seq = 0
        self._native_active = True
        self._close_requested = False
        self._last_activation = None
        self._topmost_active = bool(topmost)

    # ------------------------------------------------------------------
    # Attach / detach
    # ------------------------------------------------------------------
    def attach(self) -> None:
        self._original_exstyle = int(
            user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE)
        )
        style = self._original_exstyle
        style |= WS_EX_LAYERED
        if self.toolwindow:
            style |= WS_EX_TOOLWINDOW
            style &= ~WS_EX_APPWINDOW
        else:
            style &= ~WS_EX_TOOLWINDOW
            style |= WS_EX_APPWINDOW
        if self.topmost:
            style |= WS_EX_TOPMOST
        style &= ~WS_EX_TRANSPARENT
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, style)

        rect = self.window_rect()
        if rect:
            x, y, w, h = rect
            user32.SetWindowPos(
                self.hwnd,
                HWND_TOPMOST if self.topmost else 0,
                x,
                y,
                w,
                h,
                SWP_NOACTIVATE | SWP_FRAMECHANGED | SWP_SHOWWINDOW,
            )
        self._topmost_active = bool(self.topmost)

        red, green, blue = self.color_key
        color_ref = red | (green << 8) | (blue << 16)
        if not user32.SetLayeredWindowAttributes(
            self.hwnd, color_ref, 0, LWA_COLORKEY
        ):
            raise RuntimeError(
                "SetLayeredWindowAttributes failed "
                f"(WinError {ctypes.get_last_error()})."
            )

        wndproc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            wintypes.HWND,
            wintypes.UINT,
            wintypes.WPARAM,
            wintypes.LPARAM,
        )
        self._wndproc = wndproc_type(self._window_proc)
        new_proc = ctypes.cast(self._wndproc, ctypes.c_void_p).value
        self._original_wndproc = int(
            user32.SetWindowLongPtrW(self.hwnd, GWLP_WNDPROC, new_proc)
        )
        if not self._original_wndproc:
            raise RuntimeError(
                "Could not subclass the overlay window procedure "
                f"(WinError {ctypes.get_last_error()})."
            )

        # The colour-key window alone would send empty-area clicks to the
        # desktop, so the shield owns the mouse while the game is active.
        rect = self.window_rect() or (0, 0, 1, 1)
        self._shield = InputShield(self.hwnd, rect)
        self._active = True
        self.input_mode = "active"
        self._shield.show()
        log(
            "WINDOW",
            f"overlay attached hwnd=0x{self.hwnd:X} topmost={self.topmost} "
            f"toolwindow={self.toolwindow} exstyle=0x{self.exstyle():08X}",
        )

    def detach(self) -> None:
        """Undo every style and restore the original window procedure."""
        if self._closed or not IS_WINDOWS:
            return
        self._closed = True
        if self._shield is not None:
            try:
                self._shield.destroy()
            finally:
                self._shield = None
        self.set_input(released=True)
        if self._original_wndproc:
            try:
                user32.SetWindowLongPtrW(
                    self.hwnd, GWLP_WNDPROC, self._original_wndproc
                )
            except Exception:
                pass
            self._original_wndproc = 0
        self._wndproc = None
        try:
            user32.SetWindowLongPtrW(
                self.hwnd, GWL_EXSTYLE, self._original_exstyle
            )
            user32.SetWindowPos(
                self.hwnd,
                HWND_NOTOPMOST if self.topmost else 0,
                0,
                0,
                0,
                0,
                SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
            )
            user32.ShowWindow(self.hwnd, SW_HIDE)
        except Exception:
            pass
        release_system_input()
        log("WINDOW", f"overlay detached hwnd=0x{self.hwnd:X}")

    # ------------------------------------------------------------------
    # Input modes
    # ------------------------------------------------------------------
    @property
    def input_active(self) -> bool:
        return self._active

    def set_input(self, released: bool) -> None:
        """Switch between full overlay input and click-through desktop input."""
        if self._closed:
            return
        active = not released
        style = int(user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE))
        if active:
            style &= ~WS_EX_TRANSPARENT
        else:
            style |= WS_EX_TRANSPARENT
        user32.SetWindowLongPtrW(self.hwnd, GWL_EXSTYLE, style)
        self._active = active
        self.input_mode = "active" if active else "released"

        if self._shield is not None:
            if active:
                self._shield.show()
            else:
                self._shield.hide()

        if released:
            # Hand any tentative capture back before becoming click-through.
            user32.SetCapture(None)
            user32.ClipCursor(None)

    def acquire(self, *, activate: bool = False) -> None:
        """Take the mouse back and make sure the overlay is on top.

        ``activate`` is reserved for the single startup activation; focus
        recovery must never force the game in front of another application.
        """
        if self._closed:
            return
        if activate:
            try:
                user32.SetForegroundWindow(self.hwnd)
                user32.SetFocus(self.hwnd)
            except Exception:
                pass
        self.set_topmost(True)
        self.set_input(released=False)

    def release(self) -> None:
        self.set_input(released=True)

    def set_topmost(self, enabled: bool) -> None:
        """Move between the topmost and normal bands without activating."""
        if self._closed:
            return
        want = bool(enabled) and self.topmost
        if want == self._topmost_active:
            return
        if set_window_topmost(self.hwnd, want):
            self._topmost_active = want
            log("WINDOW", f"topmost {'restored' if want else 'dropped'}")
        else:
            log("WINDOW", f"topmost change failed wanted={want}")

    def restore_visible(self) -> None:
        """Un-minimise without activation (SW_SHOWNOACTIVATE)."""
        if self._closed:
            return
        user32.ShowWindow(self.hwnd, 4)
        log("WINDOW", f"overlay restored without activation hwnd=0x{self.hwnd:X}")

    def _window_proc(self, hwnd, message, wparam, lparam):
        if message == WM_NCHITTEST:
            # Layered colour-key pixels are already click-through at the OS
            # level, so real presses belong to the input shield. This answer
            # still describes the overlay itself for diagnostics.
            return HTCLIENT if self._active else HTTRANSPARENT
        if message == WM_ACTIVATEAPP:
            active = bool(wparam)
            self._native_active = active
            self._native_seq += 1
            log_once(
                "FOCUS",
                "native_activateapp",
                f"WM_ACTIVATEAPP active={active} hwnd=0x{self.hwnd:X}",
            )
        elif message == WM_ACTIVATE:
            active = (int(wparam) & 0xFFFF) != WA_INACTIVE
            self._native_active = active
            self._native_seq += 1
            log_once(
                "FOCUS",
                "native_activate",
                f"WM_ACTIVATE active={active} minimized={bool(int(wparam) >> 16)}",
            )
        elif message in (WM_SETFOCUS, WM_KILLFOCUS):
            active = message == WM_SETFOCUS
            self._native_active = active
            self._native_seq += 1
            log_once(
                "FOCUS",
                "native_focus",
                f"{'WM_SETFOCUS' if active else 'WM_KILLFOCUS'}",
            )
        elif message == WM_CLOSE:
            self._close_requested = True
            log("WINDOW", "WM_CLOSE received")
        elif message == WM_DESTROY:
            log("WINDOW", "WM_DESTROY received")
        elif message == WM_DISPLAYCHANGE:
            log("WINDOW", f"WM_DISPLAYCHANGE {int(lparam) & 0xFFFF}x{int(lparam) >> 16}")
        elif message == WM_DPICHANGED:
            log("WINDOW", f"WM_DPICHANGED dpi={int(wparam) & 0xFFFF}")
        return user32.CallWindowProcW(
            self._original_wndproc, hwnd, message, wparam, lparam
        )

    # ------------------------------------------------------------------
    # Introspection used by tests and diagnostics
    # ------------------------------------------------------------------
    def window_rect(self) -> tuple[int, int, int, int] | None:
        rect = wintypes.RECT()
        if not user32.GetWindowRect(self.hwnd, ctypes.byref(rect)):
            return None
        return (
            int(rect.left),
            int(rect.top),
            int(rect.right - rect.left),
            int(rect.bottom - rect.top),
        )

    def exstyle(self) -> int:
        return int(user32.GetWindowLongPtrW(self.hwnd, GWL_EXSTYLE))

    @property
    def shield_hwnd(self) -> int:
        return self._shield.hwnd if self._shield is not None else 0

    def hit_test(self, screen_x: int, screen_y: int) -> int:
        value = (int(screen_y) & 0xFFFF) << 16 | (int(screen_x) & 0xFFFF)
        return int(user32.SendMessageW(self.hwnd, WM_NCHITTEST, 0, value))

    def is_alive(self) -> bool:
        return bool(user32.IsWindow(self.hwnd))

    def poll_native_activation(self) -> tuple[int, bool]:
        """Last activation flag seen by the window procedure.

        The sequence number lets a caller notice changes without doing any
        work inside the Win32 callback itself.
        """
        return self._native_seq, self._native_active

    @property
    def close_requested(self) -> bool:
        return self._close_requested

    def clear_close_request(self) -> None:
        self._close_requested = False

    def dpi(self) -> int:
        return dpi_for_window(self.hwnd)

    def escape_down(self) -> bool:
        return bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)

    @staticmethod
    def capture_window() -> int:
        return int(user32.GetCapture() or 0)
