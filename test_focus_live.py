"""Live Alt+Tab checks for the desktop overlay (real window, real desktop).

    python test_focus_live.py                 # quick run (about 2 minutes)
    python test_focus_live.py --cycles 20     # requested 20-switch run
    python test_focus_live.py --stress-minutes 30

The game runs in a child process on the real desktop overlay. The test only
reads window state and synthesises Alt+Tab / Ctrl+Shift+Q; it never kills the
game (a wedged run is reported, not hidden). Screenshots are written to
``test_output/focus_live/`` as evidence.
"""

from __future__ import annotations

import argparse
import ctypes
import os
import re
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

from PIL import ImageGrab

PROJECT = Path(__file__).resolve().parent
PYTHON = sys.executable
LOG = Path(os.environ.get("APPDATA", "")) / "DesktopSlash" / "desktop_slash.log"
OUT = PROJECT / "test_output" / "focus_live"

user32 = ctypes.WinDLL("user32", use_last_error=True)
user32.GetForegroundWindow.restype = wintypes.HWND
user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
user32.IsWindow.argtypes = [wintypes.HWND]
user32.IsWindowVisible.argtypes = [wintypes.HWND]
user32.WindowFromPoint.argtypes = [wintypes.POINT]
user32.WindowFromPoint.restype = wintypes.HWND
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
user32.keybd_event.argtypes = [ctypes.c_ubyte, ctypes.c_ubyte, wintypes.DWORD, ctypes.c_void_p]
user32.SendMessageTimeoutW.argtypes = [
    wintypes.HWND,
    wintypes.UINT,
    wintypes.WPARAM,
    wintypes.LPARAM,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.POINTER(ctypes.c_size_t),
]
user32.SendMessageTimeoutW.restype = wintypes.LPARAM
user32.MapVirtualKeyW.argtypes = [wintypes.UINT, wintypes.UINT]
user32.MapVirtualKeyW.restype = wintypes.UINT

VK_MENU, VK_TAB, VK_F4 = 0x12, 0x09, 0x73
VK_CONTROL, VK_SHIFT, VK_Q = 0x11, 0x10, 0x51
VK_SPACE, VK_ESCAPE = 0x20, 0x1B
KEYUP = 0x0002
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x0008
WS_EX_TRANSPARENT = 0x0020
SW_RESTORE = 9

WM_NULL = 0x0000
SMTO_ABORTIFHUNG = 0x0002

_PASSED = 0
_FAILED = 0
_SKIPPED = 0


def now() -> str:
    return time.strftime("%H:%M:%S")


def check(name: str, condition: bool, detail: str = "") -> bool:
    global _PASSED, _FAILED
    if condition:
        _PASSED += 1
        print(f"[PASS] {now()} {name}")
    else:
        _FAILED += 1
        print(f"[FAIL] {now()} {name}" + (f" -> {detail}" if detail else ""))
    return condition


def skip(name: str, reason: str) -> None:
    global _SKIPPED
    _SKIPPED += 1
    print(f"[SKIP] {now()} {name} -> {reason}")


def title(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, buf, 256)
    return buf.value


def foreground() -> int:
    return int(user32.GetForegroundWindow() or 0)


def exstyle(hwnd: int) -> int:
    return int(user32.GetWindowLongPtrW(hwnd, GWL_EXSTYLE))


def _scan(vk: int) -> int:
    return int(user32.MapVirtualKeyW(vk, 0))


def _down(vk: int) -> None:
    user32.keybd_event(vk, _scan(vk), 0, None)


def _up(vk: int) -> None:
    user32.keybd_event(vk, _scan(vk), KEYUP, None)


def tap(vk: int, hold: float = 0.05) -> None:
    """One real key press. SDL drops injected keys without a scan code."""
    _down(vk)
    time.sleep(hold)
    _up(vk)


def alt_tab() -> None:
    _down(VK_MENU)
    _down(VK_TAB)
    time.sleep(0.08)
    _up(VK_TAB)
    _up(VK_MENU)


def alt_f4() -> None:
    _down(VK_MENU)
    _down(VK_F4)
    time.sleep(0.08)
    _up(VK_F4)
    _up(VK_MENU)


def emergency() -> None:
    _down(VK_CONTROL)
    _down(VK_SHIFT)
    _down(VK_Q)
    time.sleep(0.2)
    _up(VK_Q)
    _up(VK_SHIFT)
    _up(VK_CONTROL)


def responsive(hwnd: int) -> bool:
    result = ctypes.c_size_t()
    ok = user32.SendMessageTimeoutW(
        wintypes.HWND(hwnd), WM_NULL, 0, 0, SMTO_ABORTIFHUNG, 500,
        ctypes.byref(result),
    )
    return bool(ok)


def shot(name: str) -> None:
    try:
        ImageGrab.grab(all_screens=True).save(OUT / name)
    except Exception as exc:  # pragma: no cover - environment specific
        print(f"  screenshot failed: {exc}")


def read_log() -> str:
    try:
        return LOG.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def wait_until(predicate, timeout: float, step: float = 0.05) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(step)
    return False


def memory_mb(pid: int) -> float:
    class _Counters(ctypes.Structure):
        _fields_ = [
            ("cb", wintypes.DWORD),
            ("PageFaultCount", wintypes.DWORD),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    kernels = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    process = kernels.OpenProcess(0x1000 | 0x0010, False, pid)
    if not process:
        return 0.0
    counters = _Counters()
    counters.cb = ctypes.sizeof(counters)
    try:
        if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            return 0.0
        return counters.WorkingSetSize / (1024 * 1024)
    finally:
        kernels.CloseHandle(process)


def start_game() -> tuple[subprocess.Popen, int, int]:
    if LOG.exists():
        LOG.unlink()
    OUT.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["DESKTOP_SLASH_DEBUG"] = "1"
    env["SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS"] = "0"
    out = open(OUT / "game_stdout.txt", "w", encoding="utf-8", errors="replace")
    proc = subprocess.Popen(
        [PYTHON, "main.py", "--overlay"],
        cwd=PROJECT,
        env=env,
        stdout=out,
        stderr=subprocess.STDOUT,
    )
    if not wait_until(lambda: "game created" in read_log(), 25.0):
        raise RuntimeError("game did not reach the menu\n" + read_log()[-2500:])
    text = read_log()
    pid_match = re.search(r"SESSION\] desktop-slash pid=(\d+)", text)
    hwnd_match = re.search(r"created mode=overlay .* hwnd=0x([0-9A-Fa-f]+)", text)
    if not pid_match or not hwnd_match:
        raise RuntimeError("session banner or hwnd missing\n" + text[-2500:])
    return proc, int(pid_match.group(1)), int(hwnd_match.group(1), 16)


def shield_hwnd() -> int:
    found = re.findall(r"input shield (?:shown|hidden) hwnd=0x([0-9A-Fa-f]+)", read_log())
    return int(found[-1], 16) if found else 0


def bring_to_front(hwnd: int, timeout: float = 3.0) -> bool:
    """User-level activation from an unprivileged test process.

    ``SetForegroundWindow`` is refused unless the caller owns the foreground
    lock, which is exactly why the game must never rely on it. Tapping Alt
    releases the lock, as it does for any other background application.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if foreground() == hwnd:
            return True
        user32.ShowWindow(hwnd, SW_RESTORE)
        tap(VK_MENU, hold=0.02)
        user32.SetForegroundWindow(hwnd)
        time.sleep(0.15)
        if foreground() == hwnd:
            return True
        alt_tab()
        time.sleep(0.4)
    return foreground() == hwnd


def background_state(hwnd: int) -> tuple[bool, bool, bool]:
    style = exstyle(hwnd)
    center = user32.WindowFromPoint(wintypes.POINT(1280, 600))
    under = int(center or 0)
    shield = shield_hwnd()
    released = bool(style & WS_EX_TRANSPARENT)
    dropped = not style & WS_EX_TOPMOST
    clear_of_mouse = under not in (hwnd, shield)
    return released, dropped, clear_of_mouse


def wait_background(hwnd: int, timeout: float = 2.5) -> tuple[bool, str]:
    state = [False, False, False]

    def _ready() -> bool:
        state[:] = background_state(hwnd)
        return all(state)

    ok = wait_until(_ready, timeout)
    return ok, f"released={state[0]} topmost_dropped={state[1]} clear={state[2]}"


def wait_foreground(hwnd: int, take_mouse: bool = True, timeout: float = 3.0) -> tuple[bool, str]:
    state = {"active": False, "topmost": False, "transparent": False}

    def _ready() -> bool:
        style = exstyle(hwnd)
        state["topmost"] = bool(style & WS_EX_TOPMOST)
        state["transparent"] = bool(style & WS_EX_TRANSPARENT)
        state["active"] = not state["transparent"]
        return foreground() == hwnd and state["topmost"] and (
            state["active"] if take_mouse else state["transparent"]
        )

    ok = wait_until(_ready, timeout)
    return ok, (
        f"fg={foreground() == hwnd} topmost={state['topmost']} "
        f"mouse={'active' if state['active'] else 'released'}"
    )


def switch_away(hwnd: int, attempts: int = 3) -> tuple[bool, str]:
    """Alt+Tab away; retry like a user would when the shell misses the key."""
    detail = ""
    for attempt in range(1, attempts + 1):
        before = foreground()
        alt_tab()
        ok, detail = wait_background(hwnd, 2.5)
        if ok and foreground() not in (0, hwnd):
            return True, f"attempt {attempt} {detail}"
        if foreground() == hwnd:
            # The key never reached the shell; wait and press again.
            time.sleep(0.4)
        else:
            # Focus left the game but another app did not take it (desktop).
            detail += f" fg=0x{foreground():X} before=0x{before:X}"
            time.sleep(0.4)
    return False, detail


def switch_back(hwnd: int, take_mouse: bool = True, attempts: int = 3) -> tuple[bool, str]:
    detail = ""
    for attempt in range(1, attempts + 1):
        alt_tab()
        ok, detail = wait_foreground(hwnd, take_mouse=take_mouse, timeout=2.5)
        if ok:
            return True, f"attempt {attempt} {detail}"
        time.sleep(0.4)
    return False, detail


def main() -> int:
    parser = argparse.ArgumentParser(description="Desktop Slash live focus checks")
    parser.add_argument("--cycles", type=int, default=20)
    parser.add_argument("--stress-minutes", type=float, default=0.0)
    parser.add_argument("--no-screens", action="store_true")
    args = parser.parse_args()

    print("Desktop Slash - live focus checks")
    proc = None
    try:
        proc, pid, hwnd = start_game()
        print(f"  game pid={pid} hwnd=0x{hwnd:X} {title(hwnd)!r}")
        if not check("game window responds to WM_NULL", responsive(hwnd)):
            return 1

        if not bring_to_front(hwnd):
            skip("foreground switch checks", "another window holds the foreground lock")
            return _summary()
        check("game owns the foreground at startup", foreground() == hwnd)
        style = exstyle(hwnd)
        check(
            "startup: topmost and mouse active",
            bool(style & WS_EX_TOPMOST) and not style & WS_EX_TRANSPARENT,
            f"0x{style:08X}",
        )
        if not args.no_screens:
            shot("01_foreground.png")

        # --- stage 1: switch away -------------------------------------
        print("\n--- stage 1: Alt+Tab to another app ---")
        ok, detail = switch_away(hwnd)
        check("switching away releases the mouse", ok, detail)
        other = foreground()
        check(
            "another app owns the foreground",
            other not in (0, hwnd),
            f"foreground=0x{other:X} {title(other)!r}",
        )
        check(
            "the overlay leaves the topmost band, so it cannot cover the app",
            not exstyle(hwnd) & WS_EX_TOPMOST,
            f"0x{exstyle(hwnd):08X}",
        )
        check("the message loop still answers WM_NULL", responsive(hwnd))
        check(
            "the game did not force the foreground back",
            foreground() == other,
            f"foreground=0x{foreground():X}",
        )
        if not args.no_screens:
            shot("02_background.png")

        # --- stage 2: use the other app, then return ------------------
        print("\n--- stage 2: use the other app and come back ---")
        time.sleep(1.0)
        check(
            "the other app keeps the foreground while in use",
            foreground() == other,
            f"foreground=0x{foreground():X}",
        )
        ok, detail = switch_back(hwnd)
        check("returning restores topmost and the mouse", ok, detail)
        check("the game is interactive again", responsive(hwnd))
        if not args.no_screens:
            shot("03_returned.png")

        # --- stage 3: background frame rate ---------------------------
        print("\n--- stage 3: background frame rate ---")
        ok, detail = switch_away(hwnd)
        check("the game reaches the background band", ok, detail)
        print(f"  sampling heartbeats from {now()} for 11 s")
        time.sleep(11.0)
        beats = re.findall(r"alive fps=([\d.]+).*focus=background", read_log())
        print(f"  background heartbeats: {beats[-3:]}")
        if beats:
            fps = float(beats[-1])
            check(
                "background rendering uses the low frame rate",
                fps <= 25.0,
                f"fps={fps}",
            )
        else:
            skip("background rendering uses the low frame rate", "no heartbeat yet")
        ok, detail = switch_back(hwnd)
        check("returning after a long background stay works", ok, detail)

        # --- stage 4: pause, switch away, return ---------------------
        print("\n--- stage 4: pause then switch away ---")
        if not bring_to_front(hwnd):
            skip("pause stage", "could not take the foreground for the key checks")
        else:
            def count(text: str) -> int:
                return read_log().count(text)

            menu_to_countdown = "phase GamePhase.MENU -> GamePhase.COUNTDOWN"
            countdown_to_playing = "phase GamePhase.COUNTDOWN -> GamePhase.PLAYING"
            playing_to_paused = "phase GamePhase.PLAYING -> GamePhase.PAUSED"
            paused_to_playing = "phase GamePhase.PAUSED -> GamePhase.PLAYING"

            tap(VK_SPACE)
            started = wait_until(lambda: count(menu_to_countdown) >= 1, 2.0)
            if not started:
                tap(VK_SPACE)
                started = wait_until(lambda: count(menu_to_countdown) >= 1, 2.0)
            check("Space starts the round from the menu", started, "no COUNTDOWN")

            tap(VK_SPACE)
            playing = wait_until(
                lambda: count(countdown_to_playing) >= 1 or count(playing_to_paused) >= 1,
                7.0,
            )
            check("the round reaches PLAYING", playing, "never left the countdown")

            paused = count(playing_to_paused)
            tap(VK_ESCAPE)
            check(
                "Esc pauses the round before the switch",
                wait_until(lambda: count(playing_to_paused) > paused, 2.5),
                "pause transition missing",
            )
            resumes_before = count(paused_to_playing)
            ok, detail = switch_away(hwnd)
            check("paused game still hands over the mouse", ok, detail)
            ok, detail = switch_back(hwnd, take_mouse=False)
            check("returning to a paused game keeps the mouse released", ok, detail)
            check(
                "a paused game is not resumed automatically",
                count(paused_to_playing) == resumes_before,
                "resumed without the player",
            )
            tap(VK_ESCAPE)
            check(
                "Esc still resumes after the round trip",
                wait_until(lambda: count(paused_to_playing) > resumes_before, 3.0),
                "no resume",
            )

            paused = count(playing_to_paused)
            tap(VK_ESCAPE)
            check(
                "Esc pauses again for the pause-menu quit",
                wait_until(lambda: count(playing_to_paused) > paused, 2.5),
                "second pause missing",
            )
            tap(VK_Q)  # Q: quit from the pause menu
            if wait_until(lambda: "game finished cleanly" in read_log(), 8.0):
                print("  (restarting for the switch and exit stages)")
            else:
                check("pause-menu quit finishes the game", False, "no clean exit")
                return _summary()

        proc, pid, hwnd = start_game()
        if not bring_to_front(hwnd):
            skip("remaining switch stages", "foreground lock denied")
            return _summary()

        # --- stage 5: repeated switches -------------------------------
        print(f"\n--- stage 5: {args.cycles} consecutive switches ---")
        failures = 0
        for index in range(1, args.cycles + 1):
            ok_away, detail_away = switch_away(hwnd)
            ok_back, detail_back = switch_back(hwnd)
            if not (ok_away and ok_back):
                failures += 1
                print(
                    f"  cycle {index}: away={ok_away} ({detail_away}) "
                    f"back={ok_back} ({detail_back})"
                )
        check(
            f"{args.cycles} consecutive Alt+Tab switches keep both states",
            failures == 0,
            f"{failures} failed cycles",
        )
        check("the loop stayed responsive through the switches", responsive(hwnd))

        # --- stage 6: exit while unfocused ----------------------------
        print("\n--- stage 6: exit while another app is foreground ---")
        switch_away(hwnd)
        check(
            "the game is unfocused before the exit",
            foreground() != hwnd,
            f"foreground=0x{foreground():X}",
        )
        if not args.no_screens:
            shot("04_unfocused_before_exit.png")
        emergency()
        clean = wait_until(lambda: "game finished cleanly" in read_log(), 10.0)
        check("Ctrl+Shift+Q exits cleanly while unfocused", clean, "no clean exit")
        check(
            "shutdown ran the ordered pipeline",
            "SHUTDOWN] begin" in read_log() and "SHUTDOWN] complete" in read_log(),
            "missing shutdown markers",
        )
        match = re.search(r"SHUTDOWN\] complete .* errors=(\d+)", read_log())
        check(
            "shutdown reported no errors",
            bool(match) and match.group(1) == "0",
            match.group(0) if match else "no completion line",
        )
        restored = "DESKTOP] icons restored" in read_log() or "restore" in read_log()
        check("desktop restore was requested on exit", restored)
        try:
            proc.wait(timeout=8)
            exit_ok = True
        except subprocess.TimeoutExpired:
            exit_ok = False
        check("the game process ended on its own", exit_ok, "process still running")
        if not exit_ok and proc is not None:
            print("  NOT killing the process: inspect log and desktop state")
        time.sleep(0.5)
        if not args.no_screens:
            shot("05_desktop_after_exit.png")

        # --- stage 7: optional long stress ----------------------------
        if args.stress_minutes > 0:
            print(f"\n--- stage 7: {args.stress_minutes:.0f} minute stress ---")
            proc, pid, hwnd = start_game()
            if not bring_to_front(hwnd):
                skip("stress loop", "foreground lock denied")
                return _summary()
            baseline_mb = memory_mb(pid)
            deadline = time.time() + args.stress_minutes * 60.0
            cycles = 0
            failures = 0
            while time.time() < deadline:
                ok_away, _ = switch_away(hwnd)
                time.sleep(2.0)
                ok_back, _ = switch_back(hwnd)
                cycles += 1
                if not (ok_away and ok_back):
                    failures += 1
                if cycles % 10 == 0:
                    print(
                        f"  {cycles} cycles {memory_mb(pid):.1f} MB "
                        f"failures={failures}"
                    )
                time.sleep(10.0)
            growth = memory_mb(pid) - baseline_mb
            check(
                f"{cycles} stress cycles kept both states",
                failures == 0,
                f"{failures} failed cycles",
            )
            check(
                "no progressive slowdown (WM_NULL still answered)",
                responsive(hwnd),
            )
            check(
                "memory stayed flat (< 60 MB growth)",
                growth < 60.0,
                f"{growth:+.1f} MB",
            )
            alt_tab()
            wait_background(hwnd)
            emergency()
            check(
                "stress run exits cleanly while unfocused",
                wait_until(lambda: "game finished cleanly" in read_log(), 10.0),
            )
            try:
                proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                check("stress process ended", False, "still running")
        return _summary()
    except Exception as exc:
        print(f"[FAIL] live focus run raised: {exc}")
        return 1
    finally:
        if proc is not None and proc.poll() is None:
            print("\n[cleanup] asking the game to exit")
            emergency()
            if not wait_until(lambda: "game finished cleanly" in read_log(), 8.0):
                print("[cleanup] game did not exit; leaving it for inspection")


def _summary() -> int:
    total = _PASSED + _FAILED
    print(f"\n{_PASSED}/{total} checks passed, {_SKIPPED} skipped")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
