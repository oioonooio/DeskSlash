"""Stage 6 automated checks for the desktop background lifecycle.

Run from the project root:

    python test_desktop_background.py
    python test_desktop_background.py --live-overlay

The default run validates the real SysListView32 control, hides and restores it
three times with a temporary marker file, checks that icon positions never
change, tests stale-marker recovery, kills a child process that left the icons
hidden to prove the watchdog restores them, and verifies the single-instance
lock. ``--live-overlay`` additionally starts the real transparent overlay,
plays a few frames, pauses/resumes and shuts it down.

Safety: the only desktop change is ``ShowWindow`` on the validated icon list.
The script never writes to the desktop, never reorders icons, and every test
has a ``finally`` fallback that shows the list again. If the control cannot be
validated, the test stops before hiding anything.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

LIVE_OVERLAY = "--live-overlay" in sys.argv
if not LIVE_OVERLAY:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import game_config as config
from core.instance_lock import SingleInstanceLock
from desktop import desktop_background as bg
from desktop.desktop_interface import DesktopInterface
from desktop.win32_desktop import enable_dpi_awareness

OUTPUT_DIR = ROOT / "test_output"
WS_VISIBLE = 0x10000000


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _visible(hwnd: int) -> bool:
    return bool(bg._user32.IsWindowVisible(hwnd))


def _styles(hwnd: int) -> tuple[int, int]:
    return (
        int(bg._user32.GetWindowLongW(hwnd, bg.GWL_STYLE)),
        int(bg._user32.GetWindowLongW(hwnd, bg.GWL_EXSTYLE)),
    )


def _force_visible(hwnd: int) -> None:
    if not hwnd or not bg._user32.IsWindow(hwnd):
        return
    if not _visible(hwnd):
        bg._user32.ShowWindow(hwnd, bg.SW_SHOWNA)
    time.sleep(0.15)


def _desktop_signature() -> list[tuple[int, str, tuple[int, int]]] | None:
    try:
        result = DesktopInterface().read_desktop_icons()
    except Exception as exc:  # noqa: BLE001 - only used for comparison
        print(f"  desktop read unavailable: {exc}")
        return None
    return sorted(
        (icon.index, icon.name, icon.screen_position) for icon in result.icons
    )


def _require_visible(info: bg.DesktopWindowInfo) -> None:
    if not info.was_visible or not _visible(info.listview_hwnd):
        raise AssertionError(
            "the desktop icon list was already hidden before the test; "
            "restore it with Explorer and rerun"
        )


def _dead_pid() -> int:
    return 0x7FFFFFF0


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------
def test_control_validation() -> None:
    info = bg.find_desktop_window()
    assert info.listview_hwnd and info.defview_hwnd and info.host_hwnd
    assert info.host_class in ("Progman", "WorkerW"), info.host_class
    assert info.owner_name.lower() == "explorer.exe", info.owner_name
    _require_visible(info)
    print(
        f"  listview=0x{info.listview_hwnd:X} defview=0x{info.defview_hwnd:X} "
        f"host=0x{info.host_hwnd:X} {info.host_class} owner={info.owner_name} "
        f"style=0x{info.style:X} exstyle=0x{info.exstyle:X} visible={info.was_visible}"
    )


def test_hide_restore_cycles() -> None:
    info = bg.find_desktop_window()
    _require_visible(info)
    before = _desktop_signature()
    assert before is not None, "desktop icons could not be read before the test"
    style_before = _styles(info.listview_hwnd)

    work = Path(tempfile.mkdtemp(prefix="desktop_slash_stage6_"))
    marker = work / "desktop_backup.json"
    log = work / "desktop_restore.log"
    manager = bg.DesktopBackgroundManager(marker, log)
    try:
        for cycle in range(1, 4):
            backup = manager.hide_icons()
            assert backup.applied and backup.hidden, backup
            assert not _visible(info.listview_hwnd), "ShowWindow did not hide the list"
            assert marker.exists(), "the backup marker was not written before hiding"
            hidden_style = _styles(info.listview_hwnd)
            assert hidden_style[1] == style_before[1], "extended style changed"
            assert hidden_style[0] == style_before[0] & ~WS_VISIBLE, (
                "unexpected style bits changed: "
                f"0x{style_before[0]:X} -> 0x{hidden_style[0]:X}"
            )
            hidden_state = _desktop_signature()
            if hidden_state is not None:
                assert hidden_state == before, "icon positions changed while hidden"
            print(
                f"  cycle {cycle}: hidden hwnd=0x{info.listview_hwnd:X} "
                f"marker=yes positions={'unchanged' if hidden_state else 'unreadable'}"
            )

            assert manager.restore_icons(), "restore failed"
            assert _visible(info.listview_hwnd), "icons stayed hidden after restore"
            assert not marker.exists(), "marker was left behind after restore"
            assert _styles(info.listview_hwnd) == style_before, "style changed on restore"
            assert manager.restore_icons(), "restore must be idempotent"
            assert manager._watchdog is None, "watchdog was not released"
    finally:
        manager.restore_icons()
        _force_visible(info.listview_hwnd)

    after = _desktop_signature()
    assert after is not None and after == before, "desktop icons changed during the test"
    assert not marker.exists()
    text = log.read_text(encoding="utf-8") if log.exists() else ""
    assert "hid desktop icons" in text, "hide was not logged"
    assert "desktop icons restored" in text, "restore was not logged"
    print(f"  {len(before)} icon(s) unchanged after 3 hide/restore cycles")


def test_stale_marker_recovery() -> None:
    info = bg.find_desktop_window()
    _require_visible(info)
    before = _desktop_signature()
    assert before is not None
    work = Path(tempfile.mkdtemp(prefix="desktop_slash_stale_"))
    marker = work / "desktop_backup.json"
    log = work / "desktop_restore.log"
    payload = {
        "listview_hwnd": info.listview_hwnd,
        "defview_hwnd": info.defview_hwnd,
        "host_hwnd": info.host_hwnd,
        "host_class": info.host_class,
        "owner_pid": info.owner_pid,
        "owner_name": info.owner_name,
        "style": info.style,
        "exstyle": info.exstyle,
        "was_visible": True,
        "hidden": True,
        "applied": True,
        "pid": _dead_pid(),
        "created_at": time.time(),
    }
    marker.write_text(json.dumps(payload), encoding="utf-8")
    try:
        bg._user32.ShowWindow(info.listview_hwnd, bg.SW_HIDE)
        time.sleep(0.15)
        assert not _visible(info.listview_hwnd)
        assert bg.recover_stale_session(marker, log), "stale session was not recovered"
        assert _visible(info.listview_hwnd), "icons were not restored"
        assert not marker.exists(), "stale marker was not removed"
        text = log.read_text(encoding="utf-8") if log.exists() else ""
        assert "stale desktop session" in text, text
    finally:
        marker.unlink(missing_ok=True)
        _force_visible(info.listview_hwnd)
    after = _desktop_signature()
    assert after is not None and after == before
    print("  stale marker restored the icons and was deleted")


def test_watchdog_crash_recovery() -> None:
    default_marker = bg.default_marker_path()
    default_log = bg.default_log_path()
    if default_marker.exists():
        bg.recover_stale_session()
    if default_marker.exists():
        print("  watchdog crash test skipped: another instance owns the marker")
        return

    info = bg.find_desktop_window()
    _require_visible(info)
    before = _desktop_signature()
    assert before is not None

    fd, script_name = tempfile.mkstemp(
        prefix="desktop_slash_crash_", suffix=".py"
    )
    os.close(fd)
    script = Path(script_name)
    script.write_text(
        "import os, sys\n"
        f"sys.path.insert(0, {str(ROOT)!r})\n"
        "from desktop.desktop_background import DesktopBackgroundManager\n"
        "manager = DesktopBackgroundManager()\n"
        "info = manager.probe()\n"
        "print(info.listview_hwnd, flush=True)\n"
        "manager.hide_icons()\n"
        "sys.stdout.flush()\n"
        "os._exit(7)\n",
        encoding="utf-8",
    )
    try:
        result = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=40,
        )
        assert result.returncode == 7, (
            result.returncode,
            result.stdout,
            result.stderr,
        )
        deadline = time.time() + 20.0
        while time.time() < deadline:
            if _visible(info.listview_hwnd) and not default_marker.exists():
                break
            time.sleep(0.2)
        assert _visible(info.listview_hwnd), "watchdog did not restore the icons"
        assert not default_marker.exists(), "watchdog left the marker behind"
        text = default_log.read_text(encoding="utf-8") if default_log.exists() else ""
        assert "watchdog restored desktop icons" in text, text[-800:]
    finally:
        try:
            data = json.loads(default_marker.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = None
        if data and int(data.get("listview_hwnd", 0)) == info.listview_hwnd:
            if not bg._process_alive(int(data.get("pid", 0))):
                _force_visible(info.listview_hwnd)
                default_marker.unlink(missing_ok=True)
        _force_visible(info.listview_hwnd)
        script.unlink(missing_ok=True)

    after = _desktop_signature()
    assert after is not None and after == before
    print("  crashed child returned 7, watchdog restored the icons")


def test_hide_failure_is_reported() -> None:
    import pygame

    from core.game import Game
    from core.profile import ProfileStore

    work = Path(tempfile.mkdtemp(prefix="desktop_slash_failure_"))
    game = Game(
        ProfileStore(work / "save.json"),
        overlay=False,
        hide_desktop=False,
    )
    try:
        game.is_overlay = True

        class BrokenManager:
            def hide_icons(self):
                raise bg.DesktopBackgroundError("no validated desktop control")

        game.desktop_background = BrokenManager()
        game.desktop_hidden = False
        game.desktop_hide_error = ""
        game._hide_desktop_if_needed(True)
        assert game.desktop_hidden is False
        assert "no validated desktop control" in game.desktop_hide_error
    finally:
        game.shutdown()
        pygame.quit()
    print("  validation failure leaves the icons visible and is reported")


def test_single_instance_lock() -> None:
    name = f"Local\\DesktopSlash.Test.{os.getpid()}.{int(time.time() * 1000)}"
    first = SingleInstanceLock(name)
    second = SingleInstanceLock(name)
    try:
        assert first.acquire(), "first acquire failed"
        assert not second.acquire(), "a second instance acquired the lock"
        second.release()
        first.release()
        assert second.acquire(), "lock was not reusable after release"
        second.release()
    finally:
        first.release()
        second.release()

    name2 = f"{name}.context"
    with SingleInstanceLock(name2) as lock:
        assert lock._acquired
    with SingleInstanceLock(name2) as lock:
        assert lock._acquired
    print("  named mutex rejects a second instance and is reusable")


def test_live_overlay_lifecycle() -> None:
    import pygame

    from core.game import Game
    from core.phases import GamePhase
    from core.profile import ProfileStore

    default_marker = bg.default_marker_path()
    if default_marker.exists():
        bg.recover_stale_session()
    if default_marker.exists():
        raise AssertionError("another instance owns the desktop marker")

    info = bg.find_desktop_window()
    _require_visible(info)
    before = _desktop_signature()
    assert before is not None
    work = Path(tempfile.mkdtemp(prefix="desktop_slash_live_"))
    game = None
    try:
        game = Game(ProfileStore(work / "save.json"), overlay=True, monitor=0)
        assert game.is_overlay, "the overlay window was not created"
        assert game.desktop_hidden, game.desktop_hide_error
        assert not _visible(info.listview_hwnd), "icons are visible during menu"
        print(
            f"  overlay dpi={game.window.dpi} ui_scale={game.icon_manager.ui_scale:.3f} "
            f"icons={game.icon_manager.icon_min_size}-{game.icon_manager.icon_max_size} "
            f"input={game.window.input_mode}"
        )
        game._render()
        pygame.display.flip()
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        pygame.image.save(game.screen, str(OUTPUT_DIR / "stage6_live_menu_formal.png"))

        game.start_round()
        game.begin_play()
        game.lives = 99
        game.states.get(GamePhase.PLAYING)._time_left = 60.0
        for _ in range(40):
            pygame.event.pump()
            game.advance(1 / 60)
            game._render()
            pygame.display.flip()
            time.sleep(1 / 120)
        assert not _visible(info.listview_hwnd), "icons came back while playing"

        game.pause_round()
        assert game.window.input_mode == "released", game.window.input_mode
        assert not _visible(info.listview_hwnd), "icons appear while paused"
        game.resume_round()
        assert game.window.input_mode == "active", game.window.input_mode
        assert not _visible(info.listview_hwnd)
        print(
            f"  play frames 40, active icons={game.icon_manager.active_count}, "
            "pause released and resume reacquired the mouse"
        )
    finally:
        if game is not None:
            game.shutdown()
        _force_visible(info.listview_hwnd)

    time.sleep(0.3)
    assert _visible(info.listview_hwnd), "icons stayed hidden after shutdown"
    assert not default_marker.exists(), "marker survived shutdown"
    after = _desktop_signature()
    assert after is not None and after == before, "desktop icons changed"
    print(f"  shutdown restored {len(before)} icon(s)")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    enable_dpi_awareness()

    checks = [
        ("desktop icon control validation", test_control_validation),
        ("hide/restore cycles and positions", test_hide_restore_cycles),
        ("stale marker recovery", test_stale_marker_recovery),
        ("watchdog crash recovery", test_watchdog_crash_recovery),
        ("init failure is reported safely", test_hide_failure_is_reported),
        ("single-instance named mutex", test_single_instance_lock),
    ]
    if LIVE_OVERLAY:
        checks.append(("live overlay lifecycle", test_live_overlay_lifecycle))

    print("Desktop Slash - stage 6 desktop background checks")
    if config.DESKTOP_HIDE_ICONS:
        print("  config: DESKTOP_HIDE_ICONS=True")
    failures = 0
    info = None
    try:
        info = bg.find_desktop_window()
    except bg.DesktopBackgroundError as exc:
        print(f"  validation probe failed before testing: {exc}")

    for label, function in checks:
        try:
            function()
            print(f"[PASS] {label}")
        except Exception as exc:  # noqa: BLE001 - the runner reports every failure
            failures += 1
            print(f"[FAIL] {label}: {exc}")
            traceback.print_exc()

    if info is not None:
        _force_visible(info.listview_hwnd)

    total = len(checks)
    print(f"\n{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
