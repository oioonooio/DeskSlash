"""Named-mutex single-instance guard for the real desktop overlay.

The lock is held for the whole game session. A second launch exits before it
can hide desktop icons, so two instances can never fight over the desktop
state. Tests that build several ``Game`` objects in one process never touch
this module.
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

IS_WINDOWS = sys.platform == "win32"
ERROR_ALREADY_EXISTS = 183

if IS_WINDOWS:
    _kernel32 = ctypes.windll.kernel32
    _kernel32.GetLastError.argtypes = []
    _kernel32.GetLastError.restype = wintypes.DWORD
    _kernel32.SetLastError.argtypes = [wintypes.DWORD]
    _kernel32.SetLastError.restype = None
    _kernel32.CreateMutexW.argtypes = [
        ctypes.c_void_p,
        wintypes.BOOL,
        wintypes.LPCWSTR,
    ]
    _kernel32.CreateMutexW.restype = wintypes.HANDLE
    _kernel32.ReleaseMutex.argtypes = [wintypes.HANDLE]
    _kernel32.ReleaseMutex.restype = wintypes.BOOL
    _kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    _kernel32.CloseHandle.restype = wintypes.BOOL


class SingleInstanceLock:
    """Windows named mutex that reports whether another instance is running."""

    def __init__(self, name: str = r"Local\DesktopSlash.SingleInstance") -> None:
        self.name = name
        self._handle: int | None = None
        self._acquired = False

    def acquire(self) -> bool:
        if self._acquired:
            return True
        if not IS_WINDOWS:
            self._acquired = True
            return True
        _kernel32.SetLastError(0)
        handle = _kernel32.CreateMutexW(None, True, self.name)
        if not handle:
            raise OSError(
                f"CreateMutexW failed (WinError {_kernel32.GetLastError()})"
            )
        if _kernel32.GetLastError() == ERROR_ALREADY_EXISTS:
            _kernel32.CloseHandle(handle)
            return False
        self._handle = int(handle)
        self._acquired = True
        return True

    def release(self) -> None:
        if self._handle is not None:
            try:
                _kernel32.ReleaseMutex(self._handle)
            finally:
                _kernel32.CloseHandle(self._handle)
                self._handle = None
        self._acquired = False

    def __enter__(self) -> "SingleInstanceLock":
        self.acquire()
        return self

    def __exit__(self, *_exc) -> None:
        self.release()
