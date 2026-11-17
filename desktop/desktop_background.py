"""Temporarily hide the real desktop icon list while the overlay is active.

The only change made to the desktop is the window show state of the
``SysListView32`` control that lives under ``SHELLDLL_DefView`` inside
``Progman`` or a ``WorkerW`` host. No file is touched, no item is moved, and no
registry value or Explorer process is modified.

Safety contract:
  * the icon control must be validated (class hierarchy + explorer.exe owner)
    before anything is hidden;
  * the original visibility/style is saved to a JSON marker first;
  * hiding and restoring are done with ``ShowWindow`` only;
  * restore is idempotent and also runs from ``atexit`` and a watchdog child
    process if the game dies without cleaning up.
"""

from __future__ import annotations

import atexit
import ctypes
import json
import os
import subprocess
import sys
import time
from ctypes import wintypes
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

import game_config as config
from core.profile import default_profile_path

IS_WINDOWS = sys.platform == "win32"

SW_HIDE = 0
SW_SHOWNA = 8
GWL_STYLE = -16
GWL_EXSTYLE = -20
PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
SYNCHRONIZE = 0x00100000
WAIT_OBJECT_0 = 0
WAIT_TIMEOUT = 258
INFINITE = 0xFFFFFFFF
CREATE_NO_WINDOW = 0x08000000

if IS_WINDOWS:
    _user32 = ctypes.windll.user32
    _kernel32 = ctypes.windll.kernel32

    _user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    _user32.FindWindowW.restype = wintypes.HWND
    _user32.FindWindowExW.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
    ]
    _user32.FindWindowExW.restype = wintypes.HWND
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    _user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    _user32.EnumWindows.restype = wintypes.BOOL
    _user32.GetParent.argtypes = [wintypes.HWND]
    _user32.GetParent.restype = wintypes.HWND
    _user32.GetClassNameW.argtypes = [
        wintypes.HWND,
        wintypes.LPWSTR,
        ctypes.c_int,
    ]
    _user32.GetClassNameW.restype = ctypes.c_int
    _user32.IsWindow.argtypes = [wintypes.HWND]
    _user32.IsWindow.restype = wintypes.BOOL
    _user32.IsWindowVisible.argtypes = [wintypes.HWND]
    _user32.IsWindowVisible.restype = wintypes.BOOL
    _user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.ShowWindow.restype = wintypes.BOOL
    _user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    _user32.GetWindowLongW.restype = wintypes.LONG
    _user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _user32.GetWindowThreadProcessId.restype = wintypes.DWORD

    _kernel32.OpenProcess.argtypes = [
        wintypes.DWORD,
        wintypes.BOOL,
        wintypes.DWORD,
    ]
    _kernel32.OpenProcess.restype = wintypes.HANDLE
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.QueryFullProcessImageNameW.argtypes = [
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
        ctypes.POINTER(wintypes.DWORD),
    ]
    _kernel32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    _kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    _kernel32.WaitForSingleObject.restype = wintypes.DWORD
    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = wintypes.DWORD


class DesktopBackgroundError(RuntimeError):
    """Raised when the desktop icon control cannot be validated or changed."""


@dataclass
class DesktopWindowInfo:
    listview_hwnd: int
    defview_hwnd: int
    host_hwnd: int
    host_class: str
    owner_pid: int
    owner_name: str
    style: int
    exstyle: int
    was_visible: bool


@dataclass
class DesktopStateBackup:
    """Everything needed to undo the single ShowWindow call."""

    listview_hwnd: int = 0
    defview_hwnd: int = 0
    host_hwnd: int = 0
    host_class: str = ""
    owner_pid: int = 0
    owner_name: str = ""
    style: int = 0
    exstyle: int = 0
    was_visible: bool = True
    hidden: bool = False
    applied: bool = False
    pid: int = 0
    created_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "DesktopStateBackup":
        names = cls.__dataclass_fields__.keys()
        return cls(**{name: data[name] for name in names if name in data})


def default_marker_path() -> Path:
    return default_profile_path().parent / "desktop_backup.json"


def default_log_path() -> Path:
    return default_profile_path().parent / config.DESKTOP_RESTORE_LOG


def _last_error() -> int:
    return int(_kernel32.GetLastError())


def _class_name(hwnd: int) -> str:
    if not hwnd:
        return ""
    buffer = ctypes.create_unicode_buffer(256)
    if _user32.GetClassNameW(hwnd, buffer, 256) <= 0:
        return ""
    return buffer.value


def _process_name(pid: int) -> str:
    handle = _kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
    if not handle:
        raise DesktopBackgroundError(
            "Could not query the process that owns the desktop icon list "
            f"(WinError {_last_error()})."
        )
    try:
        buffer = ctypes.create_unicode_buffer(1024)
        size = wintypes.DWORD(1024)
        if not _kernel32.QueryFullProcessImageNameW(
            handle, 0, buffer, ctypes.byref(size)
        ):
            raise DesktopBackgroundError(
                "Could not resolve the desktop icon list owner process "
                f"(WinError {_last_error()})."
            )
        return os.path.basename(buffer.value)
    finally:
        _kernel32.CloseHandle(handle)


def _find_def_view() -> int:
    progman = _user32.FindWindowW("Progman", None)
    if progman:
        view = _user32.FindWindowExW(progman, 0, "SHELLDLL_DefView", None)
        if view:
            return int(view)

    found: list[int] = []

    @WNDENUMPROC
    def _callback(hwnd, _lparam):
        view = _user32.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
        if view:
            found.append(int(view))
            return False
        return True

    _user32.EnumWindows(_callback, 0)
    return found[0] if found else 0


def find_desktop_window() -> DesktopWindowInfo:
    """Locate and validate the desktop icon list.

    Raises ``DesktopBackgroundError`` with an explicit reason instead of
    guessing when the hierarchy does not look like the real desktop.
    """
    if not IS_WINDOWS:
        raise DesktopBackgroundError(
            "Hiding desktop icons requires Windows; nothing was changed."
        )

    view = _find_def_view()
    if not view or not _user32.IsWindow(view):
        raise DesktopBackgroundError(
            "The desktop SHELLDLL_DefView window was not found. "
            "Start the game from a normal Explorer desktop."
        )
    if _class_name(view) != "SHELLDLL_DefView":
        raise DesktopBackgroundError(
            "The desktop view window has an unexpected class; refusing to hide."
        )

    listview = _user32.FindWindowExW(view, 0, "SysListView32", None)
    if not listview:
        raise DesktopBackgroundError(
            "The desktop SysListView32 icon control was not found; refusing to hide."
        )
    listview = int(listview)
    if _class_name(listview) != "SysListView32":
        raise DesktopBackgroundError(
            "The desktop icon control has an unexpected class; refusing to hide."
        )

    host = int(_user32.GetParent(view) or 0)
    host_class = _class_name(host)
    if host_class not in ("Progman", "WorkerW"):
        raise DesktopBackgroundError(
            "The desktop view is not hosted by Progman or WorkerW "
            f"(found {host_class or 'unknown'}); refusing to hide."
        )

    pid = wintypes.DWORD(0)
    _user32.GetWindowThreadProcessId(listview, ctypes.byref(pid))
    if not pid.value:
        raise DesktopBackgroundError(
            "Could not resolve the desktop icon list process; refusing to hide."
        )
    owner = _process_name(pid.value)
    if owner.lower() != "explorer.exe":
        raise DesktopBackgroundError(
            f"The desktop icon list is owned by {owner!r}, not explorer.exe; "
            "refusing to hide."
        )

    return DesktopWindowInfo(
        listview_hwnd=listview,
        defview_hwnd=view,
        host_hwnd=host,
        host_class=host_class,
        owner_pid=int(pid.value),
        owner_name=owner,
        style=int(_user32.GetWindowLongW(listview, GWL_STYLE)),
        exstyle=int(_user32.GetWindowLongW(listview, GWL_EXSTYLE)),
        was_visible=bool(_user32.IsWindowVisible(listview)),
    )


def _log(path: Path, message: str) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().isoformat(timespec="seconds")
        with path.open("a", encoding="utf-8") as stream:
            stream.write(f"{stamp} pid={os.getpid()} {message}\n")
    except OSError:
        pass


def _process_alive(pid: int) -> bool:
    if pid <= 0 or not IS_WINDOWS:
        return False
    handle = _kernel32.OpenProcess(SYNCHRONIZE, False, pid)
    if not handle:
        return False
    try:
        return _kernel32.WaitForSingleObject(handle, 0) == WAIT_TIMEOUT
    finally:
        _kernel32.CloseHandle(handle)


_ACTIVE_MANAGER: "DesktopBackgroundManager | None" = None


class DesktopBackgroundManager:
    """Owns the temporary hide/restore of the real desktop icon list."""

    def __init__(
        self,
        marker_path: Path | None = None,
        log_path: Path | None = None,
    ) -> None:
        self.marker_path = Path(marker_path) if marker_path else default_marker_path()
        self.log_path = Path(log_path) if log_path else default_log_path()
        self.backup: DesktopStateBackup | None = None
        self.error = ""
        self._watchdog: subprocess.Popen | None = None
        self._atexit_registered = False

    # ------------------------------------------------------------------
    # Validation / display
    # ------------------------------------------------------------------
    def probe(self) -> DesktopWindowInfo:
        info = find_desktop_window()
        if not info.was_visible:
            _log(self.log_path, "desktop icon list is already hidden; will not change it")
        return info

    def hide_icons(self) -> DesktopStateBackup:
        """Hide the validated icon list, saving state first. Idempotent."""
        if self.backup is not None:
            return self.backup
        info = self.probe()
        backup = DesktopStateBackup(
            listview_hwnd=info.listview_hwnd,
            defview_hwnd=info.defview_hwnd,
            host_hwnd=info.host_hwnd,
            host_class=info.host_class,
            owner_pid=info.owner_pid,
            owner_name=info.owner_name,
            style=info.style,
            exstyle=info.exstyle,
            was_visible=info.was_visible,
            pid=os.getpid(),
            created_at=time.time(),
        )
        self._write_marker(backup)

        if not info.was_visible:
            self.backup = backup
            self._register_atexit()
            _log(
                self.log_path,
                f"icons already hidden before launch hwnd={info.listview_hwnd}; "
                "left untouched",
            )
            return backup

        _user32.ShowWindow(info.listview_hwnd, SW_HIDE)
        if _user32.IsWindowVisible(info.listview_hwnd):
            _user32.ShowWindow(info.listview_hwnd, SW_SHOWNA)
            self._delete_marker()
            raise DesktopBackgroundError(
                "Windows still reports the desktop icon list as visible after "
                "ShowWindow(SW_HIDE); nothing was hidden."
            )

        backup.hidden = True
        backup.applied = True
        self.backup = backup
        self._write_marker(backup)
        self._register_atexit()
        self._start_watchdog(backup)
        _log(
            self.log_path,
            f"hid desktop icons hwnd={info.listview_hwnd} host={info.host_class} "
            f"owner={info.owner_name}",
        )
        return backup

    def restore_icons(self) -> bool:
        """Show the icon list again. Safe to call repeatedly."""
        backup = self.backup
        if backup is None:
            return True
        if backup.applied and backup.hidden:
            hwnd = backup.listview_hwnd
            if not _user32.IsWindow(hwnd):
                _log(
                    self.log_path,
                    "desktop icon list no longer exists (Explorer restarted?)",
                )
            elif not _user32.IsWindowVisible(hwnd):
                _user32.ShowWindow(hwnd, SW_SHOWNA)
                if not _user32.IsWindowVisible(hwnd):
                    _log(
                        self.log_path,
                        f"could not restore desktop icons hwnd={hwnd}; "
                        "watchdog will retry",
                    )
                    return False
        self._finish_restore()
        _log(self.log_path, "desktop icons restored")
        return True

    def _finish_restore(self) -> None:
        self.backup = None
        self._delete_marker()
        self._stop_watchdog()

    def _write_marker(self, backup: DesktopStateBackup) -> None:
        try:
            self.marker_path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.marker_path.with_suffix(self.marker_path.suffix + ".tmp")
            temp.write_text(
                json.dumps(backup.to_dict(), indent=2),
                encoding="utf-8",
            )
            os.replace(temp, self.marker_path)
        except OSError as exc:
            raise DesktopBackgroundError(
                "Could not write the desktop state backup file "
                f"({exc}); desktop icons were not hidden."
            ) from exc

    def _delete_marker(self) -> None:
        try:
            self.marker_path.unlink(missing_ok=True)
        except OSError:
            pass

    # ------------------------------------------------------------------
    # Crash recovery
    # ------------------------------------------------------------------
    def _register_atexit(self) -> None:
        global _ACTIVE_MANAGER
        _ACTIVE_MANAGER = self
        if self._atexit_registered:
            return
        self._atexit_registered = True
        atexit.register(DesktopBackgroundManager.emergency_restore)

    def _start_watchdog(self, backup: DesktopStateBackup) -> None:
        if not config.DESKTOP_HIDE_WATCHDOG or self._watchdog is not None:
            return
        try:
            from core import resources

            command = [sys.executable]
            if not resources.is_frozen():
                command.append(str(resources.package_root() / "main.py"))
            command += [
                "--desktop-watchdog",
                str(os.getpid()),
                str(backup.listview_hwnd),
            ]
            self._watchdog = subprocess.Popen(
                command,
                creationflags=CREATE_NO_WINDOW,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                close_fds=True,
            )
            _log(
                self.log_path,
                f"watchdog started pid={self._watchdog.pid} "
                f"parent={os.getpid()} hwnd={backup.listview_hwnd}",
            )
        except Exception as exc:
            _log(self.log_path, f"watchdog could not be started: {exc}")

    def _stop_watchdog(self) -> None:
        process = self._watchdog
        self._watchdog = None
        if process is None or process.poll() is not None:
            return
        try:
            process.terminate()
        except Exception:
            pass

    @classmethod
    def emergency_restore(cls) -> None:
        manager = _ACTIVE_MANAGER
        if manager is None:
            return
        try:
            manager.restore_icons()
        except Exception as exc:
            _log(manager.log_path, f"emergency restore failed: {exc}")


def recover_stale_session(
    marker_path: Path | None = None,
    log_path: Path | None = None,
) -> bool:
    """Restore the desktop after a previous process left a marker behind."""
    marker = Path(marker_path) if marker_path else default_marker_path()
    log = Path(log_path) if log_path else default_log_path()
    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return False
    except (OSError, ValueError) as exc:
        _log(log, f"unreadable desktop backup marker removed: {exc}")
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        return False

    try:
        backup = DesktopStateBackup.from_dict(data)
    except Exception:
        backup = None
    if backup is None or backup.pid == os.getpid():
        return False
    if _process_alive(backup.pid):
        _log(log, f"marker belongs to live process pid={backup.pid}; not touching it")
        return False

    restored = True
    if (
        IS_WINDOWS
        and backup.applied
        and backup.listview_hwnd
        and _user32.IsWindow(backup.listview_hwnd)
        and not _user32.IsWindowVisible(backup.listview_hwnd)
    ):
        _user32.ShowWindow(backup.listview_hwnd, SW_SHOWNA)
        restored = bool(_user32.IsWindowVisible(backup.listview_hwnd))
        _log(
            log,
            f"stale desktop session pid={backup.pid} "
            f"hwnd={backup.listview_hwnd} restore={'ok' if restored else 'failed'}",
        )
    if restored:
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
    return restored


def run_watchdog(parent_pid: int, hwnd: int) -> int:
    """Wait for the game process to exit, then restore the desktop if needed."""
    if not IS_WINDOWS:
        return 0
    marker = default_marker_path()
    log = default_log_path()
    _log(log, f"watchdog attached parent={parent_pid} hwnd={hwnd}")

    handle = _kernel32.OpenProcess(SYNCHRONIZE, False, parent_pid)
    if handle:
        try:
            _kernel32.WaitForSingleObject(handle, INFINITE)
        finally:
            _kernel32.CloseHandle(handle)
    else:
        _log(log, f"watchdog could not open parent pid={parent_pid}")

    try:
        data = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        _log(log, "watchdog found no backup marker; nothing to do")
        return 0
    try:
        backup = DesktopStateBackup.from_dict(data)
    except Exception:
        _log(log, "watchdog could not parse the backup marker")
        return 1
    if backup.pid != parent_pid:
        _log(
            log,
            f"watchdog marker pid={backup.pid} does not match parent={parent_pid}",
        )
        return 0

    target = backup.listview_hwnd or hwnd
    if not target or not _user32.IsWindow(target):
        _log(log, f"watchdog target hwnd={target} no longer exists")
        try:
            marker.unlink(missing_ok=True)
        except OSError:
            pass
        return 0
    if backup.applied and not _user32.IsWindowVisible(target):
        _user32.ShowWindow(target, SW_SHOWNA)
        if _user32.IsWindowVisible(target):
            _log(log, f"watchdog restored desktop icons hwnd={target}")
        else:
            _log(log, f"watchdog restore failed hwnd={target}")
            return 1
    else:
        _log(log, "watchdog: desktop icons were already visible")
    try:
        marker.unlink(missing_ok=True)
    except OSError:
        pass
    return 0
