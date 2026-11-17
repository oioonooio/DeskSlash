"""Read-only access to the Windows desktop icon list.

Only enumeration and read operations are used here: window discovery,
``LVM_GETITEMCOUNT``/``LVM_GETITEMPOSITION``/``LVM_GETITEMTEXTW`` and
``SHGetFileInfoW``.  Nothing in this module moves, renames or deletes any
desktop item or file.
"""

from __future__ import annotations

import ctypes
import os
import sys
import uuid
from ctypes import wintypes
from dataclasses import dataclass

from .errors import DesktopReadError, IconReadError

IS_WINDOWS = sys.platform == "win32"

# ListView messages (commctrl.h)
LVM_FIRST = 0x1000
LVM_GETITEMCOUNT = LVM_FIRST + 4
LVM_GETITEMPOSITION = LVM_FIRST + 16
LVM_GETITEMTEXTW = LVM_FIRST + 115
LVIF_TEXT = 0x0001

SMTO_ABORTIFHUNG = 0x0002
PROCESS_VM_OPERATION = 0x0008
PROCESS_VM_READ = 0x0010
PROCESS_VM_WRITE = 0x0020
MEM_COMMIT = 0x1000
MEM_RESERVE = 0x2000
MEM_RELEASE = 0x8000
PAGE_READWRITE = 0x04

SHGFI_ICON = 0x000000100
SHGFI_LARGEICON = 0x000000000
SHGFI_PIDL = 0x000000008
DIB_RGB_COLORS = 0
CSIDL_DESKTOPDIRECTORY = 0x0010
CSIDL_COMMON_DESKTOPDIRECTORY = 0x0019

# IShellItemImageFactory asks the shell for the jumbo (256 px or larger)
# artwork instead of the 32-48 px HICON returned by SHGFI_LARGEICON.
IID_ISHELLITEMIMAGEFACTORY = "{BCC18B79-BA16-442F-80C4-8A59C30C463B}"
SIIGBF_BIGGERSIZEOK = 0x01
SIIGBF_ICONONLY = 0x04
DEFAULT_ICON_SOURCE_SIZE = 256
MAX_ICON_SOURCE_SIZE = 512


class _GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class _SIZE(ctypes.Structure):
    _fields_ = [("cx", wintypes.LONG), ("cy", wintypes.LONG)]

REMOTE_BUFFER_SIZE = 4096
LVITEM_OFFSET = 0
TEXT_OFFSET = 1024
POINT_OFFSET = 3072


class LVITEMW(ctypes.Structure):
    _fields_ = [
        ("mask", wintypes.UINT),
        ("iItem", ctypes.c_int),
        ("iSubItem", ctypes.c_int),
        ("state", wintypes.UINT),
        ("stateMask", wintypes.UINT),
        ("pszText", ctypes.c_void_p),
        ("cchTextMax", ctypes.c_int),
        ("iImage", ctypes.c_int),
        ("lParam", wintypes.LPARAM),
        ("iIndent", ctypes.c_int),
        ("iGroupId", ctypes.c_int),
        ("cColumns", wintypes.UINT),
        ("puColumns", ctypes.c_void_p),
        ("piColFmt", ctypes.c_void_p),
        ("iGroup", ctypes.c_int),
    ]


class ICONINFO(ctypes.Structure):
    _fields_ = [
        ("fIcon", wintypes.BOOL),
        ("xHotspot", wintypes.DWORD),
        ("yHotspot", wintypes.DWORD),
        ("hbmMask", wintypes.HBITMAP),
        ("hbmColor", wintypes.HBITMAP),
    ]


class BITMAP(ctypes.Structure):
    _fields_ = [
        ("bmType", wintypes.LONG),
        ("bmWidth", wintypes.LONG),
        ("bmHeight", wintypes.LONG),
        ("bmWidthBytes", wintypes.LONG),
        ("bmPlanes", wintypes.WORD),
        ("bmBitsPixel", wintypes.WORD),
        ("bmBits", wintypes.LPVOID),
    ]


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


class SHFILEINFOW(ctypes.Structure):
    _fields_ = [
        ("hIcon", wintypes.HICON),
        ("iIcon", ctypes.c_int),
        ("dwAttributes", wintypes.DWORD),
        ("szDisplayName", wintypes.WCHAR * 260),
        ("szTypeName", wintypes.WCHAR * 80),
    ]


if IS_WINDOWS:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)

    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.FindWindowExW.argtypes = [
        wintypes.HWND,
        wintypes.HWND,
        wintypes.LPCWSTR,
        wintypes.LPCWSTR,
    ]
    user32.FindWindowExW.restype = wintypes.HWND
    WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows.argtypes = [WNDENUMPROC, wintypes.LPARAM]
    user32.EnumWindows.restype = wintypes.BOOL
    user32.SendMessageTimeoutW.argtypes = [
        wintypes.HWND,
        wintypes.UINT,
        wintypes.WPARAM,
        wintypes.LPARAM,
        wintypes.UINT,
        wintypes.UINT,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    user32.SendMessageTimeoutW.restype = ctypes.c_ssize_t
    user32.GetWindowThreadProcessId.argtypes = [
        wintypes.HWND,
        ctypes.POINTER(wintypes.DWORD),
    ]
    user32.GetWindowThreadProcessId.restype = wintypes.DWORD
    user32.ClientToScreen.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.POINT)]
    user32.ClientToScreen.restype = wintypes.BOOL
    user32.GetSystemMetrics.argtypes = [ctypes.c_int]
    user32.GetSystemMetrics.restype = ctypes.c_int
    user32.GetDC.argtypes = [wintypes.HWND]
    user32.GetDC.restype = wintypes.HDC
    user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    user32.ReleaseDC.restype = ctypes.c_int
    user32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
    user32.GetIconInfo.restype = wintypes.BOOL
    user32.DestroyIcon.argtypes = [wintypes.HICON]
    user32.DestroyIcon.restype = wintypes.BOOL

    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL
    kernel32.VirtualAllocEx.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        ctypes.c_size_t,
        wintypes.DWORD,
        wintypes.DWORD,
    ]
    kernel32.VirtualAllocEx.restype = wintypes.LPVOID
    kernel32.VirtualFreeEx.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        ctypes.c_size_t,
        wintypes.DWORD,
    ]
    kernel32.VirtualFreeEx.restype = wintypes.BOOL
    kernel32.ReadProcessMemory.argtypes = [
        wintypes.HANDLE,
        wintypes.LPCVOID,
        wintypes.LPVOID,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel32.ReadProcessMemory.restype = wintypes.BOOL
    kernel32.WriteProcessMemory.argtypes = [
        wintypes.HANDLE,
        wintypes.LPVOID,
        wintypes.LPCVOID,
        ctypes.c_size_t,
        ctypes.POINTER(ctypes.c_size_t),
    ]
    kernel32.WriteProcessMemory.restype = wintypes.BOOL

    gdi32.GetObjectW.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID]
    gdi32.GetObjectW.restype = ctypes.c_int
    gdi32.GetDIBits.argtypes = [
        wintypes.HDC,
        wintypes.HBITMAP,
        wintypes.UINT,
        wintypes.UINT,
        wintypes.LPVOID,
        ctypes.POINTER(BITMAPINFO),
        wintypes.UINT,
    ]
    gdi32.GetDIBits.restype = ctypes.c_int
    gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
    gdi32.DeleteObject.restype = wintypes.BOOL

    shell32.SHParseDisplayName.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
        wintypes.DWORD,
        ctypes.POINTER(wintypes.DWORD),
    ]
    shell32.SHParseDisplayName.restype = ctypes.c_long
    shell32.SHGetFileInfoW.argtypes = [
        wintypes.LPCWSTR,
        wintypes.DWORD,
        ctypes.POINTER(SHFILEINFOW),
        wintypes.UINT,
        wintypes.UINT,
    ]
    shell32.SHGetFileInfoW.restype = ctypes.c_size_t
    shell32.SHGetFolderPathW.argtypes = [
        wintypes.HWND,
        ctypes.c_int,
        wintypes.HANDLE,
        wintypes.DWORD,
        wintypes.LPWSTR,
    ]
    shell32.SHGetFolderPathW.restype = ctypes.c_long
    shell32.SHCreateItemFromParsingName.argtypes = [
        wintypes.LPCWSTR,
        ctypes.c_void_p,
        ctypes.POINTER(_GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell32.SHCreateItemFromParsingName.restype = ctypes.c_long

    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, wintypes.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None


def is_supported() -> bool:
    return IS_WINDOWS


def enable_dpi_awareness() -> str:
    """Make the process DPI aware so screen coordinates are physical pixels.

    Must be called before any window (including the Pygame window) is created.
    """
    if not IS_WINDOWS:
        return "not-windows"

    try:
        setter = user32.SetProcessDpiAwarenessContext
        setter.argtypes = [ctypes.c_void_p]
        setter.restype = wintypes.BOOL
        # DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 == (HANDLE)-4
        if setter(ctypes.c_void_p(-4)):
            return "per-monitor-v2"
    except (AttributeError, OSError):
        pass

    try:
        shcore = ctypes.WinDLL("shcore")
        shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
        shcore.SetProcessDpiAwareness.restype = ctypes.c_long
        if shcore.SetProcessDpiAwareness(2) == 0:  # PROCESS_PER_MONITOR_DPI_AWARE
            return "per-monitor"
    except (AttributeError, OSError):
        pass

    try:
        if user32.SetProcessDPIAware():
            return "system"
    except (AttributeError, OSError):
        pass
    return "unchanged"


def _require_windows() -> None:
    if not IS_WINDOWS:
        raise DesktopReadError("Desktop icon reading is only available on Windows.")


def _find_def_view() -> int:
    progman = user32.FindWindowW("Progman", None)
    if progman:
        view = user32.FindWindowExW(progman, 0, "SHELLDLL_DefView", None)
        if view:
            return int(view)

    # When the desktop is hosted by WorkerW (e.g. Wallpaper Engine, or after
    # the shell re-parents the view), search every top-level window.
    found: list[int] = []

    @WNDENUMPROC
    def _callback(hwnd, _lparam):
        view = user32.FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
        if view:
            found.append(int(view))
            return False
        return True

    user32.EnumWindows(_callback, 0)
    return found[0] if found else 0


def find_desktop_listview() -> int:
    """Return the HWND of the desktop ``SysListView32`` (0 when absent)."""
    _require_windows()
    view = _find_def_view()
    if not view:
        return 0
    listview = user32.FindWindowExW(view, 0, "SysListView32", None)
    return int(listview) if listview else 0


class _RemoteBuffer:
    """A small block of memory allocated inside the explorer process."""

    def __init__(self, process: int, size: int) -> None:
        self.process = process
        self.address = kernel32.VirtualAllocEx(
            process, None, size, MEM_COMMIT | MEM_RESERVE, PAGE_READWRITE
        )
        if not self.address:
            raise DesktopReadError(
                f"VirtualAllocEx failed (WinError {ctypes.get_last_error()})."
            )
        self.size = size

    def read(self, size: int, offset: int = 0) -> bytes:
        if offset + size > self.size:
            raise DesktopReadError("Remote read outside the allocated buffer.")
        buffer = ctypes.create_string_buffer(size)
        read = ctypes.c_size_t(0)
        ok = kernel32.ReadProcessMemory(
            self.process,
            ctypes.c_void_p(self.address + offset),
            buffer,
            size,
            ctypes.byref(read),
        )
        if not ok:
            raise DesktopReadError(
                f"ReadProcessMemory failed (WinError {ctypes.get_last_error()})."
            )
        return buffer.raw[: read.value]

    def write_struct(self, struct: ctypes.Structure, offset: int = 0) -> None:
        written = ctypes.c_size_t(0)
        ok = kernel32.WriteProcessMemory(
            self.process,
            ctypes.c_void_p(self.address + offset),
            ctypes.byref(struct),
            ctypes.sizeof(struct),
            ctypes.byref(written),
        )
        if not ok:
            raise DesktopReadError(
                f"WriteProcessMemory failed (WinError {ctypes.get_last_error()})."
            )

    def close(self) -> None:
        if self.address:
            kernel32.VirtualFreeEx(self.process, self.address, 0, MEM_RELEASE)
            self.address = 0


@dataclass
class RawIcon:
    index: int
    name: str
    screen_position: tuple[int, int]
    image: "object"  # PIL.Image.Image
    image_source: str
    shell_path: str | None


@dataclass
class RawReadResult:
    icons: list[RawIcon]
    errors: list[IconReadError]
    total_items: int
    listview_hwnd: int


def _desktop_folder_paths() -> list[str]:
    paths: list[str] = []
    for csidl in (CSIDL_DESKTOPDIRECTORY, CSIDL_COMMON_DESKTOPDIRECTORY):
        buffer = ctypes.create_unicode_buffer(260)
        if shell32.SHGetFolderPathW(None, csidl, None, 0, buffer) == 0:
            path = buffer.value
            if path and os.path.isdir(path):
                paths.append(path)
    return paths


def _dib_bits(hdc: int, bitmap: int, width: int, height: int) -> bytes:
    header = BITMAPINFO()
    header.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    header.bmiHeader.biWidth = width
    header.bmiHeader.biHeight = -height  # top-down
    header.bmiHeader.biPlanes = 1
    header.bmiHeader.biBitCount = 32
    header.bmiHeader.biCompression = 0
    buffer = ctypes.create_string_buffer(width * height * 4)
    lines = gdi32.GetDIBits(
        hdc,
        bitmap,
        0,
        height,
        buffer,
        ctypes.byref(header),
        DIB_RGB_COLORS,
    )
    if not lines:
        raise DesktopReadError(
            f"GetDIBits returned 0 lines (WinError {ctypes.get_last_error()})."
        )
    return buffer.raw


def hicont_to_pil(hicon: int):
    """Convert an HICON into a 32-bit RGBA PIL image, preserving alpha."""
    from PIL import Image

    info = ICONINFO()
    if not user32.GetIconInfo(hicon, ctypes.byref(info)):
        raise DesktopReadError(
            f"GetIconInfo failed (WinError {ctypes.get_last_error()})."
        )

    hdc = user32.GetDC(None)
    try:
        width = height = 0
        bitmap = BITMAP()
        if info.hbmColor:
            gdi32.GetObjectW(
                info.hbmColor, ctypes.sizeof(BITMAP), ctypes.byref(bitmap)
            )
            width, height = int(bitmap.bmWidth), int(bitmap.bmHeight)

        if info.hbmColor and width > 0 and height > 0:
            color = _dib_bits(hdc, info.hbmColor, width, height)
            image = Image.frombuffer(
                "RGBA", (width, height), color, "raw", "BGRA", 0, 1
            ).copy()
            if image.getchannel("A").getextrema()[1] == 0 and info.hbmMask:
                image.putalpha(_mask_alpha(hdc, info.hbmMask, width, height))
            return image

        # Monochrome icon: there is only a mask. White means transparent.
        if info.hbmMask:
            gdi32.GetObjectW(
                info.hbmMask, ctypes.sizeof(BITMAP), ctypes.byref(bitmap)
            )
            width, height = int(bitmap.bmWidth), int(bitmap.bmHeight)
            if width > 0 and height > 0:
                alpha = _mask_alpha(hdc, info.hbmMask, width, height)
                image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
                image.putalpha(alpha)
                return image

        raise DesktopReadError("Icon has no usable color or mask bitmap.")
    finally:
        if info.hbmColor:
            gdi32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            gdi32.DeleteObject(info.hbmMask)
        user32.ReleaseDC(None, hdc)


def _mask_alpha(hdc: int, bitmap: int, width: int, height: int):
    from PIL import Image

    bits = _dib_bits(hdc, bitmap, width, height)
    alpha = bytes(
        0 if bits[i] > 127 else 255 for i in range(0, len(bits), 4)
    )
    return Image.frombytes("L", (width, height), alpha)


def _bitmap_to_pil(hbitmap: int):
    """Convert a 32-bit BGRA HBITMAP into a straight-alpha RGBA image."""
    from PIL import Image

    bitmap = BITMAP()
    if not gdi32.GetObjectW(hbitmap, ctypes.sizeof(BITMAP), ctypes.byref(bitmap)):
        raise DesktopReadError(
            f"GetObjectW failed on the shell bitmap (WinError {ctypes.get_last_error()})."
        )
    width, height = int(bitmap.bmWidth), int(bitmap.bmHeight)
    if width <= 0 or height <= 0:
        raise DesktopReadError("The shell bitmap has no usable size.")

    hdc = user32.GetDC(None)
    try:
        bits = _dib_bits(hdc, hbitmap, width, height)
    finally:
        user32.ReleaseDC(None, hdc)
    image = Image.frombuffer("RGBA", (width, height), bits, "raw", "BGRA", 0, 1).copy()
    return _straight_alpha(image)


def _straight_alpha(image):
    """Undo premultiplied alpha when the shell returns it.

    IShellItemImageFactory documents premultiplied BGRA, but current Windows
    builds already hand back straight alpha. Sampling decides which one it is
    so half-transparent edges are neither darkened nor blown out.
    """
    from PIL import Image, ImageChops

    raw = image.tobytes()
    semi = 0
    over = 0
    step = 4 * 17
    for offset in range(0, len(raw), step):
        alpha = raw[offset + 3]
        if 0 < alpha < 255:
            semi += 1
            if max(raw[offset], raw[offset + 1], raw[offset + 2]) > alpha + 2:
                over += 1
    if not semi or over * 10 >= semi:
        return image

    red, green, blue, alpha = image.split()
    inverse = alpha.point(
        lambda value: 0 if value == 0 else min(255, (255 * 255) // value)
    )
    return Image.merge(
        "RGBA",
        (
            ImageChops.multiply(red, inverse),
            ImageChops.multiply(green, inverse),
            ImageChops.multiply(blue, inverse),
            alpha,
        ),
    )


def _shell_item_image(parsing_name: str, size: int):
    """Ask the shell for a large icon bitmap, or return ``None``."""
    from PIL import Image

    size = max(16, min(MAX_ICON_SOURCE_SIZE, int(size)))
    com_initialised = False
    hr = ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
    if hr in (0, 1):
        com_initialised = True
    elif (hr & 0xFFFFFFFF) not in (0x80010106,):  # RPC_E_CHANGED_MODE
        return None

    factory = ctypes.c_void_p()
    vtable = None
    try:
        iid = _GUID.from_buffer_copy(
            uuid.UUID(IID_ISHELLITEMIMAGEFACTORY).bytes_le
        )
        create_hr = shell32.SHCreateItemFromParsingName(
            parsing_name, None, ctypes.byref(iid), ctypes.byref(factory)
        )
        if create_hr != 0 or not factory.value:
            return None

        vtable = ctypes.cast(
            factory, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))
        )[0]
        get_image = ctypes.WINFUNCTYPE(
            ctypes.c_long,
            ctypes.c_void_p,
            _SIZE,
            ctypes.c_int,
            ctypes.POINTER(wintypes.HBITMAP),
        )(vtable[3])
        handle = wintypes.HBITMAP()
        image_hr = get_image(
            factory,
            _SIZE(size, size),
            SIIGBF_ICONONLY | SIIGBF_BIGGERSIZEOK,
            ctypes.byref(handle),
        )
        if image_hr != 0 or not handle.value:
            return None
        try:
            image = _bitmap_to_pil(handle.value)
        finally:
            gdi32.DeleteObject(handle)
        if image.size != (size, size):
            image.thumbnail((size, size), Image.LANCZOS)
        return image
    except Exception:
        return None
    finally:
        if factory.value and vtable is not None:
            try:
                release = ctypes.WINFUNCTYPE(
                    wintypes.ULONG, ctypes.c_void_p
                )(vtable[2])
                release(factory)
            except Exception:
                pass
        if com_initialised:
            ole32.CoUninitialize()


def _parse_display_name(parsing_name: str) -> int:
    pidl = ctypes.c_void_p()
    attributes = wintypes.DWORD(0)
    hr = shell32.SHParseDisplayName(
        parsing_name, None, ctypes.byref(pidl), 0, ctypes.byref(attributes)
    )
    if hr != 0 or not pidl.value:
        return 0
    return int(pidl.value)
def _shell_icon_from_pidl(pidl: int) -> int:
    info = SHFILEINFOW()
    result = shell32.SHGetFileInfoW(
        ctypes.cast(ctypes.c_void_p(pidl), wintypes.LPCWSTR),
        0,
        ctypes.byref(info),
        ctypes.sizeof(info),
        SHGFI_ICON | SHGFI_LARGEICON | SHGFI_PIDL,
    )
    if not result or not info.hIcon:
        raise DesktopReadError(
            f"SHGetFileInfoW(PIDL) failed (WinError {ctypes.get_last_error()})."
        )
    return int(info.hIcon)


def _shell_icon_from_path(path: str) -> int:
    info = SHFILEINFOW()
    result = shell32.SHGetFileInfoW(
        path,
        0,
        ctypes.byref(info),
        ctypes.sizeof(info),
        SHGFI_ICON | SHGFI_LARGEICON,
    )
    if not result or not info.hIcon:
        raise DesktopReadError(
            f"SHGetFileInfoW(path) failed (WinError {ctypes.get_last_error()})."
        )
    return int(info.hIcon)


def extract_shell_icon(parsing_name: str, size: int | None = None):
    """Return ``(PIL.Image, source)`` for a shell parsing name.

    ``parsing_name`` is either a filesystem path or a virtual ``::{CLSID}``
    name obtained from the shell namespace. The jumbo shell bitmap is tried
    first; the HICON paths remain as a fallback for locked-down shells.
    """
    _require_windows()
    source = "pidl" if parsing_name.startswith("::") else "path"
    requested = DEFAULT_ICON_SOURCE_SIZE if size is None else int(size)
    large = _shell_item_image(parsing_name, requested)
    if large is not None:
        return large, source

    pidl = _parse_display_name(parsing_name)
    if pidl:
        image = None
        hicon = 0
        try:
            hicon = _shell_icon_from_pidl(pidl)
            image = hicont_to_pil(hicon)
        except DesktopReadError:
            image = None
        finally:
            if hicon:
                user32.DestroyIcon(hicon)
            ole32.CoTaskMemFree(ctypes.c_void_p(pidl))
        if image is not None:
            return image, source
        # A virtual item has no filesystem path to fall back to.
        if parsing_name.startswith("::"):
            raise DesktopReadError(
                f"Could not load the virtual item icon for {parsing_name}."
            )

    hicon = _shell_icon_from_path(parsing_name)
    try:
        return hicont_to_pil(hicon), source
    finally:
        user32.DestroyIcon(hicon)


class Win32DesktopReader:
    """Enumerates the desktop listview without modifying the desktop.

    Use as a context manager: the remote buffer and process handle are
    released on exit.
    """

    def __init__(self) -> None:
        _require_windows()
        self._com_module = None
        self._com_initialized = False
        self._initialize_com()

        self.listview_hwnd = find_desktop_listview()
        if not self.listview_hwnd:
            self._release_com()
            raise DesktopReadError(
                "Desktop SysListView32 not found. Is explorer.exe running?"
            )

        pid = wintypes.DWORD(0)
        user32.GetWindowThreadProcessId(self.listview_hwnd, ctypes.byref(pid))
        if not pid.value:
            self._release_com()
            raise DesktopReadError("Could not resolve the desktop shell process id.")

        access = PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE
        self.process = kernel32.OpenProcess(access, False, pid.value)
        if not self.process:
            self._release_com()
            raise DesktopReadError(
                "OpenProcess on the desktop shell failed "
                f"(WinError {ctypes.get_last_error()})."
            )
        try:
            self.remote = _RemoteBuffer(self.process, REMOTE_BUFFER_SIZE)
        except Exception:
            kernel32.CloseHandle(self.process)
            self.process = None
            self._release_com()
            raise

    def _initialize_com(self) -> None:
        # SHGetFileInfoW needs COM on the calling thread; keeping it alive for
        # the reader's lifetime also keeps shell namespace enumeration working.
        try:
            import pythoncom

            pythoncom.CoInitialize()
            self._com_module = pythoncom
            self._com_initialized = True
            return
        except Exception:
            pass
        hr = ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
        if hr == 0:
            self._com_initialized = True

    def _release_com(self) -> None:
        if not self._com_initialized:
            return
        self._com_initialized = False
        if self._com_module is not None:
            try:
                self._com_module.CoUninitialize()
            except Exception:
                pass
            self._com_module = None
        else:
            ole32.CoUninitialize()

    def close(self) -> None:
        if getattr(self, "remote", None) is not None:
            self.remote.close()
            self.remote = None
        if getattr(self, "process", None):
            kernel32.CloseHandle(self.process)
            self.process = None
        self._release_com()

    def __enter__(self) -> "Win32DesktopReader":
        return self

    def __exit__(self, *_exc) -> None:
        self.close()

    # ------------------------------------------------------------------
    # ListView access
    # ------------------------------------------------------------------
    def _send(self, message: int, wparam: int = 0, lparam: int = 0) -> int:
        result = ctypes.c_size_t(0)
        ok = user32.SendMessageTimeoutW(
            self.listview_hwnd,
            message,
            wparam,
            lparam,
            SMTO_ABORTIFHUNG,
            2000,
            ctypes.byref(result),
        )
        if not ok:
            raise DesktopReadError(
                f"SendMessageTimeoutW(0x{message:04X}) failed "
                f"(WinError {ctypes.get_last_error()})."
            )
        return int(result.value)

    def item_count(self) -> int:
        return self._send(LVM_GETITEMCOUNT)

    def item_name(self, index: int) -> str:
        item = LVITEMW()
        item.mask = LVIF_TEXT
        item.iItem = index
        item.iSubItem = 0
        item.pszText = self.remote.address + TEXT_OFFSET
        item.cchTextMax = 260
        self.remote.write_struct(item, LVITEM_OFFSET)
        text_ptr = self.remote.address + LVITEM_OFFSET
        self._send(LVM_GETITEMTEXTW, index, text_ptr)
        raw = self.remote.read(260 * 2, TEXT_OFFSET)
        return raw.decode("utf-16-le", "replace").split("\x00", 1)[0]

    def item_screen_position(self, index: int) -> tuple[int, int]:
        point_ptr = self.remote.address + POINT_OFFSET
        self._send(LVM_GETITEMPOSITION, index, point_ptr)
        raw = self.remote.read(ctypes.sizeof(wintypes.POINT), POINT_OFFSET)
        point = wintypes.POINT.from_buffer_copy(raw)
        if not user32.ClientToScreen(self.listview_hwnd, ctypes.byref(point)):
            raise DesktopReadError(
                f"ClientToScreen failed (WinError {ctypes.get_last_error()})."
            )
        return int(point.x), int(point.y)

    # ------------------------------------------------------------------
    # Shell namespace
    # ------------------------------------------------------------------
    def shell_paths(self) -> dict[str, str]:
        """Map desktop display name -> shell parsing name (path or CLSID)."""
        paths: dict[str, str] = {}
        try:
            import win32com.client
        except ImportError:
            win32com = None

        if win32com is not None:
            try:
                shell = win32com.client.Dispatch("Shell.Application")
                folder = shell.NameSpace(0)
                if folder is not None:
                    for entry in folder.Items():
                        try:
                            name = str(entry.Name)
                            path = str(entry.Path or "")
                        except Exception:
                            continue
                        if name and name not in paths:
                            paths[name] = path
            except Exception:
                paths = {}

        # Filesystem fallback for plain desktop files when COM is unavailable.
        for folder_path in _desktop_folder_paths():
            try:
                entries = os.listdir(folder_path)
            except OSError:
                continue
            for filename in entries:
                if filename in paths:
                    continue
                stem = os.path.splitext(filename)[0]
                key = stem if filename.lower().endswith(".lnk") else filename
                if key and key not in paths:
                    paths[key] = os.path.join(folder_path, filename)
        return paths

    def read_icons(self, icon_size: int | None = None) -> RawReadResult:
        total = self.item_count()
        paths = self.shell_paths()
        icons: list[RawIcon] = []
        errors: list[IconReadError] = []

        for index in range(total):
            try:
                name = self.item_name(index)
            except Exception as exc:
                errors.append(IconReadError(index, "", "name", str(exc)))
                continue
            if not name:
                errors.append(
                    IconReadError(index, "", "name", "empty display name")
                )
                continue

            try:
                position = self.item_screen_position(index)
            except Exception as exc:
                errors.append(IconReadError(index, name, "position", str(exc)))
                continue

            parsing_name = paths.get(name, "")
            if not parsing_name:
                errors.append(
                    IconReadError(
                        index,
                        name,
                        "shell-path",
                        "no shell namespace entry matched this name",
                    )
                )
                continue

            try:
                image, source = extract_shell_icon(parsing_name, icon_size)
            except Exception as exc:
                errors.append(IconReadError(index, name, "image", str(exc)))
                continue

            icons.append(
                RawIcon(
                    index=index,
                    name=name,
                    screen_position=position,
                    image=image,
                    image_source=source,
                    shell_path=parsing_name,
                )
            )

        return RawReadResult(
            icons=icons,
            errors=errors,
            total_items=total,
            listview_hwnd=self.listview_hwnd,
        )
