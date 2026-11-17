"""Unified shutdown checks for Desktop Slash.

    python test_shutdown.py

Every exit route must end in the same idempotent pipeline, the desktop icon
list must be restored before the overlay window is destroyed, one failing
step must not skip the rest, and the whole pipeline must respect the timeout
budget. All checks run headless with a throwaway profile and a plain (non
overlay) window, so the real desktop and save file are never touched.
"""

from __future__ import annotations

import os
import sys
import tempfile
import threading
import time
import traceback
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

import game_config as config
from core.game import Game, ShutdownPhase
from core.phases import GamePhase
from core.profile import ProfileStore

_PROFILE_DIR = Path(tempfile.mkdtemp(prefix="desktop_slash_shutdown_"))
_SEQUENCE = 0
FAILURES: list[str] = []


def _new_game(name: str = "") -> Game:
    global _SEQUENCE
    _SEQUENCE += 1
    file_name = f"{name}_{_SEQUENCE}.json" if name else f"game_{_SEQUENCE}.json"
    return Game(
        ProfileStore(_PROFILE_DIR / file_name),
        overlay=False,
        hide_desktop=False,
    )


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -> {detail}" if detail else ""))
    if not ok:
        FAILURES.append(name)


def test_request_is_idempotent() -> None:
    game = _new_game("idempotent")
    try:
        game.request_shutdown("first")
        game.request_shutdown("second")
        assert game.shutdown_reason == "first", game.shutdown_reason
        assert game.running is False
        assert game.shutdown_phase is ShutdownPhase.SHUTTING_DOWN

        game.shutdown()
        assert game.shutdown_phase is ShutdownPhase.STOPPED
        game.shutdown()
        game.request_shutdown("after_stop")
        assert game.shutdown_phase is ShutdownPhase.STOPPED
        assert game.shutdown_reason == "first"
    finally:
        game.shutdown()


def test_pipeline_order() -> None:
    game = _new_game("order")
    try:
        calls: list[tuple[str, ShutdownPhase]] = []
        original_close = game.window.close
        original_stop = game.sfx.stop_all
        original_restore = game.desktop_background.restore_icons
        original_release = game.window.release_input

        def release_input() -> None:
            calls.append(("release_input", game.shutdown_phase))
            original_release()

        def restore_icons():
            calls.append(("restore_icons", game.shutdown_phase))
            return original_restore()

        def close() -> None:
            calls.append(("close", game.shutdown_phase))
            original_close()

        def stop_all() -> None:
            calls.append(("stop_all", game.shutdown_phase))
            original_stop()

        game.window.release_input = release_input  # type: ignore[method-assign]
        game.window.close = close  # type: ignore[method-assign]
        game.sfx.stop_all = stop_all  # type: ignore[method-assign]
        game.desktop_background.restore_icons = restore_icons  # type: ignore[method-assign]

        game.request_shutdown("order")
        game.shutdown()

        phases = [phase for _, phase in calls]
        assert calls[-1][0] == "stop_all", calls
        restore_index = phases.index(ShutdownPhase.RESTORING_DESKTOP)
        close_index = phases.index(ShutdownPhase.DESTROYING_WINDOWS)
        stop_index = phases.index(ShutdownPhase.RELEASING_RESOURCES)
        assert restore_index < close_index < stop_index, calls
        assert all(
            phases[index] is ShutdownPhase.SHUTTING_DOWN
            for index in range(phases.index(ShutdownPhase.RESTORING_DESKTOP))
        ), calls
    finally:
        game.shutdown()


def test_failure_does_not_skip_rest() -> None:
    game = _new_game("errors")
    try:
        closed: list[bool] = []
        original_close = game.window.close

        def broken_restore():
            raise RuntimeError("restore exploded")

        def close() -> None:
            closed.append(True)
            original_close()

        game.desktop_background.restore_icons = broken_restore  # type: ignore[method-assign]
        game.window.close = close  # type: ignore[method-assign]

        game.shutdown()

        assert closed == [True], "window close was skipped after an error"
        assert game.shutdown_phase is ShutdownPhase.STOPPED
        assert any(
            "restore desktop icons" in error for error in game.shutdown_errors
        ), game.shutdown_errors
    finally:
        game.shutdown()


def test_missing_method_does_not_abort() -> None:
    game = _new_game("missing_method")
    try:
        closed: list[bool] = []
        original_close = game.window.close

        class Incomplete:
            pass

        def close() -> None:
            closed.append(True)
            original_close()

        game.desktop_background = Incomplete()  # type: ignore[assignment]
        game.window.close = close  # type: ignore[method-assign]

        game.shutdown()

        assert closed == [True], "a missing restore_icons aborted the pipeline"
        assert game.shutdown_phase is ShutdownPhase.STOPPED
        assert any(
            "restore desktop icons" in error for error in game.shutdown_errors
        ), game.shutdown_errors
    finally:
        game.shutdown()


def test_budget_limits_hangs() -> None:
    game = _new_game("budget")
    previous = config.SHUTDOWN_BUDGET_SECONDS
    config.SHUTDOWN_BUDGET_SECONDS = 0.2
    try:
        closed: list[bool] = []
        original_close = game.window.close

        def slow_restore():
            time.sleep(0.45)
            return True

        def close() -> None:
            closed.append(True)
            original_close()

        game.desktop_background.restore_icons = slow_restore  # type: ignore[method-assign]
        game.window.close = close  # type: ignore[method-assign]

        started = time.monotonic()
        game.shutdown()
        elapsed = time.monotonic() - started
        assert elapsed < 1.0, f"shutdown took {elapsed:.2f}s"
        assert closed == [], "steps kept running after the budget expired"
        assert game.shutdown_phase is ShutdownPhase.STOPPED
        assert any("budget" in error for error in game.shutdown_errors), (
            game.shutdown_errors
        )
    finally:
        config.SHUTDOWN_BUDGET_SECONDS = previous
        pygame.quit()


def test_window_close_event() -> None:
    game = _new_game("quit_event")
    try:
        pygame.event.post(pygame.event.Event(pygame.QUIT))
        game._handle_events()
        assert game.running is False
        assert game.shutdown_reason == "window_close", game.shutdown_reason
    finally:
        game.shutdown()


def test_menu_exit_route() -> None:
    game = _new_game("menu_exit")
    try:
        menu = game.states._current
        exit_button = menu._buttons[-1]
        assert exit_button.action == "exit"
        menu.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, pos=exit_button.rect.center
            )
        )
        assert game.running is False
        assert game.shutdown_reason == "menu_exit", game.shutdown_reason
    finally:
        game.shutdown()


def test_game_over_exit_route() -> None:
    game = _new_game("gameover_exit")
    try:
        game.start_round()
        game.begin_play()
        game.finish_round("out_of_lives")
        over = game.states._current
        exit_button = over._buttons[-1]
        assert exit_button.action == "exit"
        over.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, pos=exit_button.rect.center
            )
        )
        assert game.running is False
        assert game.shutdown_reason == "gameover_exit", game.shutdown_reason
    finally:
        game.shutdown()


def test_pause_quit_route() -> None:
    game = _new_game("pause_quit")
    try:
        game.start_round()
        game.begin_play()
        game.pause_round()
        assert game.states.phase == GamePhase.PAUSED
        game._handle_events()
        game.states._current.handle_event(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_q)
        )
        assert game.running is False
        assert game.shutdown_reason == "pause_quit", game.shutdown_reason
    finally:
        game.shutdown()


def test_emergency_event_route() -> None:
    game = _new_game("emergency")
    try:
        game._emergency_event.set()
        game._handle_events()
        assert game.shutdown_reason == "emergency_hotkey", game.shutdown_reason
        assert game.running is False
    finally:
        game.shutdown()


def test_emergency_watcher_thread() -> None:
    game = _new_game("watcher")
    previous_grace = config.EMERGENCY_HOTKEY_GRACE
    config.EMERGENCY_HOTKEY_GRACE = 5.0
    observed = threading.Event()
    try:
        def hotkey() -> bool:
            observed.set()
            return True

        game.window.poll_emergency_exit = hotkey  # type: ignore[method-assign]
        thread = game._emergency_thread
        assert thread is not None and thread.daemon, "watcher must be a daemon"
        assert observed.wait(2.0), "watcher never polled the hotkey"
        assert game._emergency_event.wait(2.0), "watcher did not raise the event"

        game.request_shutdown("emergency_hotkey")
        game.shutdown()
        thread.join(timeout=3.0)
        assert not thread.is_alive(), "watcher thread survived shutdown"
    finally:
        config.EMERGENCY_HOTKEY_GRACE = previous_grace
        game.shutdown()


def main() -> int:
    tests = (
        ("request_shutdown is idempotent", test_request_is_idempotent),
        ("cleanup runs in priority order", test_pipeline_order),
        ("a failing step never skips the rest", test_failure_does_not_skip_rest),
        ("a missing method never aborts the rest", test_missing_method_does_not_abort),
        ("the shutdown budget stops hangs", test_budget_limits_hangs),
        ("window close event requests shutdown", test_window_close_event),
        ("menu exit uses the pipeline", test_menu_exit_route),
        ("game over exit uses the pipeline", test_game_over_exit_route),
        ("pause Q uses the pipeline", test_pause_quit_route),
        ("emergency event uses the pipeline", test_emergency_event_route),
        ("emergency watcher thread stops cleanly", test_emergency_watcher_thread),
    )
    print("Desktop Slash - unified shutdown checks")
    for label, function in tests:
        try:
            function()
        except Exception as exc:  # noqa: BLE001 - report every route
            FAILURES.append(label)
            print(f"[FAIL] {label}: {exc}")
            traceback.print_exc()
        else:
            print(f"[PASS] {label}")

    print(f"\n{'PASS' if not FAILURES else 'FAIL'}: {len(FAILURES)} failure(s)")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
