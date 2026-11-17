from __future__ import annotations

import atexit
import os
import sys

import pygame

import game_config as config
from core.diagnostics import log
from core.resources import asset_path
from window.win32_overlay import (
    IS_WINDOWS,
    MonitorInfo,
    Win32Overlay,
    emergency_exit_down,
    get_monitor,
    list_monitors,
    release_system_input,
    window_from_point,
    window_is_foreground,
    window_is_minimized,
)

_ACTIVE_MANAGER: "WindowManager | None" = None


def _disable_ime_text_input() -> None:
    """Keep the IME from turning letter keys into VK_PROCESSKEY.

    The game has no text fields. With a Chinese/Japanese IME active, SDL still
    receives letters as VK_PROCESSKEY (0xE5), so shortcuts like Q/M never fire.
    Stopping text input detaches the IME context for the window.
    """
    try:
        pygame.key.stop_text_input()
    except (AttributeError, pygame.error):
        pass


def overlay_available() -> bool:
    """True when a real Windows desktop can host the layered overlay."""
    if not IS_WINDOWS:
        return False
    driver = os.environ.get("SDL_VIDEODRIVER", "").strip().lower()
    return driver not in {"dummy", "offscreen"}


class WindowManager:
    """Owns the Pygame window and its Win32 overlay input mode.

    Modes:
      * window   -- ordinary 1280x720 window (tests, --window, fallback)
      * overlay  -- borderless colour-keyed window covering one monitor

    Only the overlay has an OS-level released mode. A normal window still
    reports ``input_mode`` so gameplay/tests can use the same pause contract.
    """

    def __init__(
        self,
        overlay: bool | None = None,
        monitor: int | None = None,
        size: tuple[int, int] | None = None,
        position: tuple[int, int] | None = None,
    ) -> None:
        self.screen: pygame.Surface | None = None
        self.is_overlay = False
        self.input_mode = "active"
        self.overlay: Win32Overlay | None = None
        self.hwnd = 0
        self.monitor_info: MonitorInfo | None = None
        self.monitor_rect: tuple[int, int, int, int] | None = None
        self.window_rect: tuple[int, int, int, int] | None = None
        self.dpi = 96
        self.overlay_error = ""
        self.monitors: list[MonitorInfo] = []
        self._requested_overlay = config.WINDOW_OVERLAY if overlay is None else overlay
        self._requested_monitor = (
            config.WINDOW_OVERLAY_MONITOR if monitor is None else monitor
        )
        self._size_override = size
        self._position_override = position
        self._closed = False
        self._atexit_registered = False

    # ------------------------------------------------------------------
    # Creation
    # ------------------------------------------------------------------
    def create(self) -> pygame.Surface:
        self.monitors = list_monitors()
        if self._requested_overlay and overlay_available():
            try:
                screen = self._create_overlay()
            except Exception as exc:
                self.overlay_error = str(exc)
                log("WINDOW", f"overlay creation failed: {exc!r}; using a window")
                self._teardown_display()
                screen = self._create_window()
        else:
            if self._requested_overlay and not overlay_available():
                self.overlay_error = "Overlay unavailable with this SDL driver."
            screen = self._create_window()

        self.screen = screen
        self._apply_window_icon()
        self._register_atexit()
        log(
            "WINDOW",
            f"created mode={'overlay' if self.is_overlay else 'window'} "
            f"size={screen.get_size()} hwnd=0x{self.hwnd:X} dpi={self.dpi}",
        )
        return screen

    def _create_overlay(self) -> pygame.Surface:
        info = get_monitor(int(self._requested_monitor))
        if info is None:
            raise RuntimeError("No Windows monitor was reported.")
        self.monitor_info = info
        x, y, width, height = (
            info.work_rect if config.WINDOW_OVERLAY_USE_WORK_AREA else info.rect
        )
        size = self._size_override or (width, height)
        if self._position_override is not None:
            position = self._position_override
        elif self._size_override is None:
            position = (x, y)
        else:
            position = (
                x + max(0, (width - size[0]) // 2),
                y + max(0, (height - size[1]) // 2),
            )

        old_position = os.environ.get("SDL_VIDEO_WINDOW_POS")
        os.environ["SDL_VIDEO_WINDOW_POS"] = f"{position[0]},{position[1]}"
        try:
            screen = pygame.display.set_mode(
                size,
                pygame.NOFRAME,
                vsync=config.WINDOW_VSYNC,
            )
        finally:
            if old_position is None:
                os.environ.pop("SDL_VIDEO_WINDOW_POS", None)
            else:
                os.environ["SDL_VIDEO_WINDOW_POS"] = old_position

        pygame.display.set_caption(config.WINDOW_TITLE)
        screen.fill(config.WINDOW_TRANSPARENT_COLOR_KEY)
        _disable_ime_text_input()

        info_dict = pygame.display.get_wm_info()
        hwnd = int(info_dict.get("window") or 0)
        if not hwnd:
            raise RuntimeError("SDL did not expose a native window handle.")

        overlay = Win32Overlay(
            hwnd,
            config.WINDOW_TRANSPARENT_COLOR_KEY,
            topmost=config.WINDOW_TOPMOST,
            toolwindow=config.WINDOW_TOOLWINDOW,
        )
        self.overlay = overlay
        self.hwnd = hwnd
        try:
            overlay.attach()
            # The launcher is allowed one activation: the user just started
            # the game. Every later focus change is left to Windows.
            overlay.acquire(activate=True)
        except Exception:
            overlay.detach()
            self.overlay = None
            raise

        self.is_overlay = True
        self.input_mode = "active"
        self.window_rect = overlay.window_rect() or (*position, *size)
        self.monitor_rect = info.rect
        self.dpi = overlay.dpi() or info.dpi
        pygame.display.flip()
        return screen

    def _create_window(self) -> pygame.Surface:
        screen = pygame.display.set_mode(
            self._size_override or config.WINDOW_SIZE,
            0,
            vsync=config.WINDOW_VSYNC,
        )
        pygame.display.set_caption(config.WINDOW_TITLE)
        self.is_overlay = False
        self.input_mode = "active"
        _disable_ime_text_input()
        try:
            self.hwnd = int(pygame.display.get_wm_info().get("window") or 0)
        except (pygame.error, AttributeError, TypeError, ValueError):
            self.hwnd = 0
        return screen

    def _teardown_display(self) -> None:
        if self.overlay is not None:
            try:
                self.overlay.detach()
            finally:
                self.overlay = None
        try:
            pygame.display.quit()
            pygame.display.init()
        except pygame.error:
            pass

    def _apply_window_icon(self) -> None:
        icon_path = asset_path("icon.png")
        if not icon_path.exists():
            return
        try:
            pygame.display.set_icon(pygame.image.load(str(icon_path)))
        except (pygame.error, OSError):
            pass

    # ------------------------------------------------------------------
    # Input modes
    # ------------------------------------------------------------------
    def acquire_input(self) -> None:
        """Take the mouse back; the game must already own the foreground.

        No ``SetForegroundWindow`` here: activation is the user's decision.
        The only forced activation is the single one at window creation.
        """
        if self._closed:
            return
        if self.input_mode != "active":
            log("INPUT", "mouse input enabled")
        self.input_mode = "active"
        if self.overlay is not None:
            self.overlay.acquire()

    def release_input(self) -> None:
        if self._closed:
            return
        if self.input_mode != "released":
            log("INPUT", "mouse input released")
        self.input_mode = "released"
        if self.overlay is not None:
            self.overlay.release()

    def foreground_is_self(self) -> bool:
        """True when this window (or a child of it) owns the foreground."""
        if not IS_WINDOWS or not self.hwnd:
            return True
        return window_is_foreground(self.hwnd)

    def is_minimized(self) -> bool:
        if not IS_WINDOWS or not self.hwnd:
            return False
        return window_is_minimized(self.hwnd)

    def native_activation(self) -> tuple[int, bool]:
        """(sequence, active) from WM_ACTIVATE/WM_ACTIVATEAPP/WM_SETFOCUS."""
        if self.overlay is not None:
            return self.overlay.poll_native_activation()
        return 0, True

    def close_requested(self) -> bool:
        return self.overlay.close_requested if self.overlay is not None else False

    def clear_close_request(self) -> None:
        if self.overlay is not None:
            self.overlay.clear_close_request()

    # ------------------------------------------------------------------
    # Foreground / background
    # ------------------------------------------------------------------
    def enter_background(self) -> None:
        """Hand the desktop back: release the mouse and leave the topmost band.

        Dropping ``WS_EX_TOPMOST`` is what stops the colour-keyed overlay from
        covering the browser the user just switched to. The overlay stays
        visible underneath so the hidden desktop icons keep their painted
        backdrop, and it keeps rendering at the low background frame rate.
        """
        if self._closed:
            return
        self.release_input()
        if self.overlay is not None:
            self.overlay.set_topmost(False)
        log(
            "WINDOW",
            f"background hwnd=0x{self.hwnd:X} input={self.input_mode} "
            f"exstyle=0x{self.exstyle():08X}",
        )

    def enter_foreground(self, take_input: bool = True) -> bool:
        """Restore z-order (and maybe the mouse) after a real focus gain.

        Returns False when another window still owns the foreground, in which
        case nothing is raised and the next focus poll retries.
        """
        if self._closed:
            return False
        if not self.foreground_is_self():
            log("FOCUS", "restore skipped: foreground belongs to another window")
            return False
        if self.overlay is not None:
            if self.is_minimized():
                self.overlay.restore_visible()
            self.overlay.set_topmost(True)
        if take_input:
            self.acquire_input()
        else:
            self.release_input()
        log(
            "WINDOW",
            f"foreground hwnd=0x{self.hwnd:X} input={self.input_mode} "
            f"exstyle=0x{self.exstyle():08X}",
        )
        return True

    def poll_escape(self) -> bool:
        """Global resume key; works even after the desktop got focus."""
        if self.overlay is not None:
            return self.overlay.escape_down()
        return False

    def poll_emergency_exit(self) -> bool:
        """Ctrl+Shift+Q, readable without window messages or focus."""
        return emergency_exit_down()

    # ------------------------------------------------------------------
    # Diagnostics
    # ------------------------------------------------------------------
    def exstyle(self) -> int:
        return self.overlay.exstyle() if self.overlay is not None else 0

    def hit_test(self, screen_x: int, screen_y: int) -> int | None:
        if self.overlay is None:
            return None
        return self.overlay.hit_test(screen_x, screen_y)

    @staticmethod
    def window_at(screen_x: int, screen_y: int) -> int:
        return window_from_point(screen_x, screen_y)

    @staticmethod
    def capture_window() -> int:
        return Win32Overlay.capture_window() if IS_WINDOWS else 0

    def monitor_summary(self) -> str:
        if not self.monitors:
            return "no monitors"
        return ", ".join(item.describe() for item in self.monitors)

    # ------------------------------------------------------------------
    # Shutdown
    # ------------------------------------------------------------------
    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        log("WINDOW", f"closing hwnd=0x{self.hwnd:X}")
        if self.overlay is not None:
            try:
                self.overlay.detach()
            finally:
                self.overlay = None
        release_system_input()
        if self.screen is not None:
            try:
                pygame.display.quit()
            except pygame.error:
                pass
            self.screen = None
        self.is_overlay = False

    @classmethod
    def emergency_restore(cls) -> None:
        """Best-effort recovery used by atexit and the crash handler."""
        global _ACTIVE_MANAGER
        manager = _ACTIVE_MANAGER
        if manager is not None and not manager._closed:
            try:
                manager.close()
            except Exception:
                pass
        release_system_input()
        _ACTIVE_MANAGER = None

    def _register_atexit(self) -> None:
        if self._atexit_registered:
            return
        self._atexit_registered = True
        global _ACTIVE_MANAGER
        _ACTIVE_MANAGER = self
        atexit.register(WindowManager.emergency_restore)


def system_summary(manager: WindowManager | None = None) -> str:
    driver = pygame.display.get_driver() if pygame.display.get_init() else "none"
    if manager is None:
        return f"driver={driver} monitors={len(list_monitors())} platform={sys.platform}"
    return (
        f"driver={driver} mode={'overlay' if manager.is_overlay else 'window'} "
        f"monitors={len(manager.monitors)} dpi={manager.dpi} platform={sys.platform}"
    )
