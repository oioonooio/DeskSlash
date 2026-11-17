"""Focus state machine and Game integration checks (headless).

    python test_focus.py

Part 1 drives ``FocusManager`` with a fake clock so every debounce edge is
deterministic. Part 2 injects SDL focus events into a real ``Game`` on the
dummy driver and checks the gameplay contracts: pause on loss, no forced
foreground, no reload, no auto-resume.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

import game_config as config
from core.focus import FocusManager, FocusState
from core.game import Game
from core.phases import GamePhase
from core.profile import ProfileStore

_PROFILE_DIR = Path(tempfile.mkdtemp(prefix="desktop_slash_focus_"))
_PASSED = 0
_FAILED = 0
_GAME_SEQUENCE = 0


def check(name: str, condition: bool, detail: str = "") -> bool:
    global _PASSED, _FAILED
    if condition:
        _PASSED += 1
        print(f"[PASS] {name}")
    else:
        _FAILED += 1
        print(f"[FAIL] {name}" + (f" -> {detail}" if detail else ""))
    return condition


class _Rig:
    """FocusManager wired to a fake clock and togglable probes."""

    def __init__(self, *, paused: bool = False) -> None:
        self.now = 100.0
        self.focused = True
        self.paused = paused
        self.seq = 0
        self.native_active = True
        self.calls: list[str] = []

        self.manager = FocusManager(
            on_focus_lost=lambda: self.calls.append("focus_lost"),
            on_background=lambda: self.calls.append("background"),
            on_foreground=lambda: self.calls.append("foreground"),
            foreground_probe=lambda: self.focused,
            activation_probe=lambda: (self.seq, self.native_active),
            paused_probe=lambda: self.paused,
            clock=lambda: self.now,
        )
        self.manager.update()

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _unit_checks() -> None:
    rig = _Rig()
    check("starts in FOREGROUND", rig.manager.state is FocusState.FOREGROUND)

    rig.focused = False
    rig.manager.notify(False)
    rig.manager.update()
    check(
        "focus loss enters FOCUS_LOST and releases once",
        rig.manager.state is FocusState.FOCUS_LOST
        and rig.calls == ["focus_lost"],
        f"{rig.manager.state} {rig.calls}",
    )

    rig.advance(0.1)
    rig.manager.update()
    check(
        "the loss is debounced (still FOCUS_LOST after 0.1 s)",
        rig.manager.state is FocusState.FOCUS_LOST and rig.calls == ["focus_lost"],
        f"{rig.manager.state} {rig.calls}",
    )

    rig.advance(config.FOCUS_LOST_DELAY)
    rig.manager.update()
    check(
        "background starts after the debounce",
        rig.manager.state is FocusState.BACKGROUND
        and rig.calls == ["focus_lost", "background"],
        f"{rig.manager.state} {rig.calls}",
    )

    for _ in range(8):
        rig.advance(0.05)
        rig.manager.update()
    check(
        "no duplicate callbacks while idle in the background",
        rig.calls == ["focus_lost", "background"],
        str(rig.calls),
    )
    check(
        "background renders at the low frame rate and freezes time",
        rig.manager.render_fps == config.BACKGROUND_FPS
        and not rig.manager.simulates
        and not rig.manager.accepts_input,
        f"fps={rig.manager.render_fps}",
    )

    rig.focused = True
    rig.manager.notify(True)
    rig.manager.update()
    check(
        "focus gain enters RESTORING and restores once",
        rig.manager.state is FocusState.RESTORING
        and rig.calls == ["focus_lost", "background", "foreground"],
        f"{rig.manager.state} {rig.calls}",
    )
    rig.advance(config.FOCUS_GAIN_DELAY + 0.01)
    rig.manager.update()
    check(
        "restoring settles in FOREGROUND without another callback",
        rig.manager.state is FocusState.FOREGROUND
        and rig.calls == ["focus_lost", "background", "foreground"],
        f"{rig.manager.state} {rig.calls}",
    )

    # --- quick return inside the debounce window ------------------------
    quick = _Rig()
    quick.focused = False
    quick.manager.notify(False)
    quick.manager.update()
    quick.advance(0.05)
    quick.focused = True
    quick.manager.notify(True)
    quick.manager.update()
    check(
        "a quick focus return never reaches the background",
        quick.manager.state is FocusState.FOREGROUND
        and quick.calls == ["focus_lost", "foreground"],
        f"{quick.manager.state} {quick.calls}",
    )

    # --- paused round keeps its label through a focus cycle -------------
    paused = _Rig(paused=True)
    check("paused probe labels the focused state", paused.manager.state is FocusState.PAUSED)
    paused.focused = False
    paused.manager.notify(False)
    paused.manager.update()
    paused.advance(config.FOCUS_LOST_DELAY + 0.01)
    paused.manager.update()
    paused.focused = True
    paused.manager.notify(True)
    paused.manager.update()
    paused.advance(config.FOCUS_GAIN_DELAY + 0.01)
    paused.manager.update()
    check(
        "a paused round comes back as PAUSED",
        paused.manager.state is FocusState.PAUSED,
        str(paused.manager.state),
    )

    # --- a raising callback must not wedge the machine ------------------
    boom_calls: list[str] = []
    boom_clock = [0.0]

    def _boom() -> None:
        boom_calls.append("boom")
        raise RuntimeError("handler failure")

    boom = FocusManager(
        on_background=_boom,
        foreground_probe=lambda: False,
        clock=lambda: boom_clock[0],
    )
    boom.update()
    boom.notify(False)
    boom.update()
    boom_clock[0] = 1.0
    boom.update()
    check(
        "a failing handler does not block the transition",
        boom.state is FocusState.BACKGROUND and boom_calls == ["boom"],
        f"{boom.state} {boom_calls}",
    )

    boom.begin_shutdown()
    boom.notify(True)
    boom.update()
    check(
        "shutdown is terminal for focus transitions",
        boom.state is FocusState.SHUTTING_DOWN,
        str(boom.state),
    )


def _new_game() -> Game:
    global _GAME_SEQUENCE
    _GAME_SEQUENCE += 1
    return Game(ProfileStore(_PROFILE_DIR / f"focus_{_GAME_SEQUENCE}.json"))


def _event(kind: int, **kwargs: object) -> pygame.event.Event:
    return pygame.event.Event(kind, **kwargs)


def _game_checks() -> None:
    game = _new_game()
    focus_lost = getattr(pygame, "WINDOWFOCUSLOST", None)
    focus_gained = getattr(pygame, "WINDOWFOCUSGAINED", None)
    if focus_lost is None or focus_gained is None:
        check("pygame exposes focus events", False, "WINDOWFOCUS* missing")
        game.shutdown()
        return
    try:
        check("game starts focused", game.focus.state is FocusState.FOREGROUND)
        game.start_round()
        game.begin_play()
        playing = game.states.get(GamePhase.PLAYING)
        playing._time_left = 42.0
        icon = game.icon_manager._spawn_icon()
        icon.body.position.update(game.screen.get_width() * 0.5, 300)
        icon.body.velocity.update(0.0, 0.0)
        score = game.score
        lives = game.lives

        # A stroke in progress must be dropped when activation leaves.
        game.slashes.begin((100.0, 100.0), 10.0)
        pygame.event.clear()
        pygame.event.post(_event(focus_lost))
        game._handle_events()

        check(
            "focus loss pauses a running round and releases the mouse",
            game.states.phase is GamePhase.PAUSED
            and game.window.input_mode == "released",
            f"{game.states.phase} {game.window.input_mode}",
        )
        check(
            "focus loss cancels the current stroke",
            not game.slashes.is_slashing and game.slashes.trail_length == 0,
            f"slashing={game.slashes.is_slashing}",
        )
        check(
            "focus loss keeps score, lives and the round clock",
            game.score == score
            and game.lives == lives
            and playing.time_left == 42.0,
            f"score={game.score} lives={game.lives} time={playing.time_left}",
        )
        check(
            "focus loss does not reload the desktop",
            game.desktop_read_count == 1,
            f"{game.desktop_read_count} reads",
        )

        old_delay = config.FOCUS_LOST_DELAY
        config.FOCUS_LOST_DELAY = 0.0
        try:
            game.focus.update()
        finally:
            config.FOCUS_LOST_DELAY = old_delay
        check(
            "the debounce settles into the background",
            game.focus.state is FocusState.BACKGROUND and game.focus.is_background,
            str(game.focus.state),
        )
        check(
            "background keeps the scene frozen",
            not game.focus.simulates
            and game.focus.render_fps == config.BACKGROUND_FPS,
            f"fps={game.focus.render_fps}",
        )

        # Return: the game must stay paused and keep the mouse released.
        pygame.event.clear()
        pygame.event.post(_event(focus_gained))
        game._handle_events()
        check(
            "focus gain restores the window but not the round",
            game.focus.state is FocusState.RESTORING
            and game.states.phase is GamePhase.PAUSED
            and game.window.input_mode == "released",
            f"{game.focus.state} {game.states.phase} {game.window.input_mode}",
        )
        old_gain = config.FOCUS_GAIN_DELAY
        config.FOCUS_GAIN_DELAY = 0.0
        try:
            game.focus.update()
        finally:
            config.FOCUS_GAIN_DELAY = old_gain
        check(
            "restoring settles back into PAUSED",
            game.focus.state is FocusState.PAUSED,
            str(game.focus.state),
        )

        # The global Esc poll must never resume over another application.
        original_probe = game.window.foreground_is_self
        original_poll = game.window.poll_escape
        game.window.foreground_is_self = lambda: False  # type: ignore[method-assign]
        game.window.poll_escape = lambda: True  # type: ignore[method-assign]
        game._resume_key_armed = True
        game._paused_at = 0.0
        game._poll_resume_key()
        check(
            "global Esc does not resume while another app is foreground",
            game.states.phase is GamePhase.PAUSED,
            str(game.states.phase),
        )
        game.window.foreground_is_self = original_probe  # type: ignore[method-assign]
        game.window.poll_escape = original_poll  # type: ignore[method-assign]

        game.states.handle_event(_event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        check(
            "Esc still resumes the paused round",
            game.states.phase is GamePhase.PLAYING
            and game.window.input_mode == "active",
            f"{game.states.phase} {game.window.input_mode}",
        )
        check(
            "resume does not reload or reset the round",
            game.desktop_read_count == 1
            and game.score == score
            and playing.time_left == 42.0,
            f"reads={game.desktop_read_count} score={game.score}",
        )

        # --- menu focus cycle ------------------------------------------
        game.go_to_menu()
        pygame.event.clear()
        pygame.event.post(_event(focus_lost))
        game._handle_events()
        check(
            "menu focus loss releases the mouse without pausing",
            game.states.phase is GamePhase.MENU
            and game.window.input_mode == "released",
            f"{game.states.phase} {game.window.input_mode}",
        )
        pygame.event.clear()
        pygame.event.post(_event(focus_gained))
        game._handle_events()
        check(
            "menu focus gain takes the mouse again",
            game.window.input_mode == "active",
            game.window.input_mode,
        )

        # --- WM_CLOSE while unfocused -----------------------------------
        game.focus.begin_shutdown()
        game.focus.notify(False)
        game.focus.update()
        check(
            "no focus work after shutdown begins",
            game.focus.state is FocusState.SHUTTING_DOWN,
            str(game.focus.state),
        )
        original_close = game.window.close_requested
        game.window.close_requested = lambda: True  # type: ignore[method-assign]
        game.window.clear_close_request = lambda: None  # type: ignore[method-assign]
        game._handle_events()
        game.window.close_requested = original_close  # type: ignore[method-assign]
        check(
            "WM_CLOSE is handled even while unfocused",
            not game.running and game.shutdown_phase.value == "shutting_down",
            f"running={game.running} phase={game.shutdown_phase}",
        )
    finally:
        game.shutdown()


def main() -> int:
    print("Desktop Slash - focus state checks")
    _unit_checks()
    _game_checks()
    print(f"\n{_PASSED}/{_PASSED + _FAILED} checks passed")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
