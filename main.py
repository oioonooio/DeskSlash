"""Desktop Slash entry point.

    python main.py                 # transparent desktop overlay (default)
    python main.py --window        # normal 1280x720 window
    python main.py --overlay --monitor 1
    python main.py --self-test     # verify a packaged/copied build

The overlay hands the mouse back to the desktop while paused and always
restores the original window styles, capture and cursor clipping on exit.
"""

from __future__ import annotations

import argparse
import os
import sys
import traceback

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
# SDL must not minimize the borderless overlay on focus loss: the game
# manages its own topmost band so it can come back without losing its surface.
os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="DesktopSlash",
        description="Desktop Slash - slice desktop icons in a transparent overlay.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--window",
        action="store_true",
        help="run in a normal 1280x720 window instead of the overlay",
    )
    group.add_argument(
        "--overlay",
        action="store_true",
        help="force the transparent desktop overlay (default)",
    )
    parser.add_argument(
        "--monitor",
        type=int,
        default=None,
        metavar="N",
        help="monitor index for the overlay, 0 = primary",
    )
    parser.add_argument(
        "--self-test",
        action="store_true",
        help="run the packaged-build self-test, write a report and exit",
    )
    parser.add_argument(
        "--desktop-watchdog",
        nargs=2,
        type=int,
        metavar=("PID", "HWND"),
        help=argparse.SUPPRESS,
    )
    return parser


def _init_language() -> None:
    """Load the saved language before pygame or any window exists."""
    try:
        from core.profile import ProfileStore
        from localization import set_language

        set_language(ProfileStore().load().language)
    except Exception:
        pass


def _write_crash_log() -> str:
    try:
        from core.diagnostics import log_exception
        from core.profile import default_profile_path

        log_exception("LOOP", "uncaught exception")
        path = default_profile_path().parent / "crash.log"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(traceback.format_exc(), encoding="utf-8")
        return str(path)
    except Exception:
        return ""


def _show_crash_message(log_path: str) -> None:
    from localization import t

    message = (
        t("error.crash_with_log", log=log_path) if log_path else t("error.crash")
    )
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Desktop Slash", 0x10)
    except Exception:
        pass


def _show_single_instance_message() -> None:
    from localization import t

    message = t("error.already_running")
    try:
        if sys.stderr is not None:
            sys.stderr.write(message + "\n")
    except Exception:
        pass
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Desktop Slash", 0x40)
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    _init_language()

    if args.desktop_watchdog:
        from desktop.desktop_background import run_watchdog

        pid, hwnd = args.desktop_watchdog
        return run_watchdog(pid, hwnd)

    if args.self_test:
        os.environ["SDL_VIDEODRIVER"] = "dummy"
        os.environ["SDL_AUDIODRIVER"] = "dummy"
        try:
            from core.self_test import run_self_test
        except ModuleNotFoundError as exc:
            if exc.name == "pygame":
                from localization import t

                sys.stderr.write(t("error.needs_pygame") + "\n")
                return 1
            raise
        return run_self_test(args.monitor)

    try:
        from core.diagnostics import log, session_banner, log_exception

        session_banner("desktop-slash")
        log("SESSION", f"argv={argv if argv is not None else sys.argv[1:]}")
    except Exception:
        pass

    try:
        from core.game import Game
        from core.instance_lock import SingleInstanceLock
        from desktop.desktop_background import (
            DesktopBackgroundManager,
            recover_stale_session,
        )
        from window.window_manager import WindowManager
    except ModuleNotFoundError as exc:
        if exc.name == "pygame":
            from localization import t

            sys.stderr.write(t("error.needs_pygame") + "\n")
            return 1
        raise

    lock = SingleInstanceLock()
    try:
        acquired = lock.acquire()
    except OSError as exc:
        from localization import t

        sys.stderr.write(t("error.lock", error=exc) + "\n")
        return 1
    if not acquired:
        _show_single_instance_message()
        return 2

    try:
        recover_stale_session()

        overlay = None
        if args.window:
            overlay = False
        elif args.overlay:
            overlay = True

        game = None
        try:
            game = Game(overlay=overlay, monitor=args.monitor)
            log("SESSION", "game created")
            game.run()
            log("SESSION", "game finished cleanly")
            return 0
        except KeyboardInterrupt:
            log("SESSION", "interrupted by user")
            return 0
        except Exception:
            log_exception("LOOP", "game raised")
            log_path = _write_crash_log()
            WindowManager.emergency_restore()
            DesktopBackgroundManager.emergency_restore()
            if sys.stderr is not None:
                traceback.print_exc()
            _show_crash_message(log_path)
            return 1
        finally:
            WindowManager.emergency_restore()
            DesktopBackgroundManager.emergency_restore()
    finally:
        lock.release()


if __name__ == "__main__":
    raise SystemExit(main())
