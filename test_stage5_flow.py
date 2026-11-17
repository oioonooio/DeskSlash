"""Stage 5 end-to-end flow: overlay rendering, pause, and the 10 test steps.

Headless run (SDL dummy driver), safe to run with the real desktop attached:

    python test_stage5_flow.py

The game still reads the real desktop icons once, exactly like a live session.
Mouse events are injected into the same state handlers the window loop uses.
"""

from __future__ import annotations

import os
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

import game_config as config
from core.game import Game
from core.phases import GamePhase
from core.profile import ProfileStore
from desktop.desktop_interface import DesktopInterface
from gameplay.combo_tracker import combo_multiplier
from window.win32_overlay import HTCLIENT, HTTRANSPARENT

_PROFILE_DIR = Path(tempfile.mkdtemp(prefix="desktop_slash_stage5_"))
_GAME_SEQUENCE = 0
_PASSED = 0
_FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> bool:
    global _PASSED, _FAILED
    if condition:
        _PASSED += 1
        print(f"[PASS] {name}")
    else:
        _FAILED += 1
        print(f"[FAIL] {name}" + (f" -> {detail}" if detail else ""))
    return condition


def _new_game() -> Game:
    global _GAME_SEQUENCE
    _GAME_SEQUENCE += 1
    return Game(ProfileStore(_PROFILE_DIR / f"flow_{_GAME_SEQUENCE}.json"))


def _event(kind: int, **kwargs: object) -> pygame.event.Event:
    return pygame.event.Event(kind, **kwargs)


def _key(code: int) -> pygame.event.Event:
    return _event(pygame.KEYDOWN, key=code)


def _spawn(game: Game, position: tuple[float, float], bomb: bool = False):
    icon = game.icon_manager.spawn_bomb() if bomb else game.icon_manager._spawn_icon()
    icon.body.position.update(position[0], position[1])
    icon.body.velocity.update(0.0, 0.0)
    return icon


def _swipe(game: Game, points: list[tuple[float, float]], start: float = 100.0) -> float:
    """Feed a fast left-button stroke to the active state."""
    now = start
    game.states.handle_event(
        _event(pygame.MOUSEBUTTONDOWN, button=1, pos=points[0], input_time=now)
    )
    for index in range(1, len(points)):
        now += 0.02
        game.states.handle_event(
            _event(
                pygame.MOUSEMOTION,
                pos=points[index],
                rel=(0, 0),
                buttons=(1, 0, 0),
                input_time=now,
            )
        )
    now += 0.02
    game.states.handle_event(
        _event(pygame.MOUSEBUTTONUP, button=1, pos=points[-1], input_time=now)
    )
    return now


def _step(game: Game, dt: float = config.FIXED_DT) -> None:
    game._update(dt)


def _enable_overlay_rendering(game: Game) -> None:
    """Use the overlay render path without a real layered window."""
    game.is_overlay = True
    game.background.enabled = False
    game.screen_fx.overlay_mode = True
    game.screen_fx.scanlines_enabled = False


def _desktop_signature(desktop: DesktopInterface) -> list[tuple[str, int, int]]:
    result = desktop.read_desktop_icons()
    return [(icon.name, *icon.screen_position) for icon in result.icons]


def main() -> int:
    desktop = DesktopInterface()
    before = _desktop_signature(desktop)
    game = _new_game()
    try:
        check("startup: menu phase", game.states.phase == GamePhase.MENU)
        check(
            "desktop icons read exactly once at startup",
            game.desktop_read_count == 1,
            f"read {game.desktop_read_count} time(s)",
        )
        check(
            "icon sources are available",
            game.icon_source_count > 0,
            f"{game.icon_source_count} sources ({game.icon_source_label})",
        )

        _enable_overlay_rendering(game)
        game._render()
        key = config.WINDOW_TRANSPARENT_COLOR_KEY
        corners = (
            game.scene.get_at((6, 6))[:3],
            game.scene.get_at((game.scene.get_width() - 6, 6))[:3],
            game.scene.get_at((6, game.scene.get_height() - 6))[:3],
            game.scene.get_at(
                (game.scene.get_width() - 6, game.scene.get_height() - 6)
            )[:3],
        )
        check(
            "overlay menu clears to the colour key",
            all(tuple(pixel) == key for pixel in corners),
            f"corners={corners}",
        )
        right_edge = [
            game.scene.get_at((game.scene.get_width() - 20, y))[:3]
            for y in range(300, 640)
        ]
        check(
            "overlay menu keeps the background fully transparent (no scanlines)",
            all(tuple(pixel) == key for pixel in right_edge),
            "an empty column is not the colour key",
        )
        game.scene.set_at((40, 400), (255, 0, 255))
        game._render()
        check(
            "each overlay frame is cleared before drawing",
            game.scene.get_at((40, 400))[:3] != (255, 0, 255),
        )

        # --- focus hand-off on the menu --------------------------------
        focus_lost = getattr(pygame, "WINDOWFOCUSLOST", None)
        focus_gained = getattr(pygame, "WINDOWFOCUSGAINED", None)
        if focus_lost is not None and focus_gained is not None:
            pygame.event.clear()
            pygame.event.post(_event(focus_lost))
            game._handle_events()
            check(
                "menu focus loss hands the mouse back to the desktop",
                game.window.input_mode == "released",
                f"input={game.window.input_mode}",
            )
            pygame.event.clear()
            pygame.event.post(_event(focus_gained))
            game._handle_events()
            check(
                "menu focus gain takes the mouse again",
                game.window.input_mode == "active",
                f"input={game.window.input_mode}",
            )
        else:
            check("menu focus loss hands the mouse back to the desktop", False, "event missing")
            check("menu focus gain takes the mouse again", False, "event missing")

        # --- step 3: start the round from the menu ---------------------
        game.states.handle_event(_key(pygame.K_SPACE))
        check(
            "menu START enters the countdown",
            game.states.phase == GamePhase.COUNTDOWN,
            str(game.states.phase),
        )
        check(
            "round state reset",
            game.score == 0 and game.lives == config.STARTING_LIVES,
            f"score={game.score} lives={game.lives}",
        )

        game.states.handle_event(_key(pygame.K_SPACE))
        playing = game.states.get(GamePhase.PLAYING)
        check(
            "countdown skip begins play",
            game.states.phase == GamePhase.PLAYING
            and abs(playing.time_left - config.ROUND_SECONDS) < 0.01,
            f"phase={game.states.phase} time={playing.time_left}",
        )

        # --- overlay render while playing ------------------------------
        _spawn(game, (game.screen.get_width() * 0.5, 240))
        game._render()
        occupied = sum(
            1
            for x in range(0, game.scene.get_width(), 16)
            for y in range(0, game.scene.get_height(), 16)
            if tuple(game.scene.get_at((x, y))[:3]) != key
        )
        check(
            "overlay playing frame draws objects over a transparent scene",
            occupied > 40,
            f"{occupied} sampled pixels differ from the key",
        )

        # --- step 4/5: slice a row of icons into a combo ---------------
        width, height = game.screen.get_size()
        y = int(height * 0.45)
        xs = [width * 0.30, width * 0.42, width * 0.54, width * 0.66]
        for x in xs:
            _spawn(game, (x, y))
        game.slashes.reset()
        _swipe(game, [(xs[0], y), (xs[-1], y)])
        _step(game)

        check(
            "a swipe slices several icons",
            game.slice_count == 4,
            f"slice_count={game.slice_count} score={game.score}",
        )
        check(
            "combo counter and multiplier react",
            game.combo.count == 4 and combo_multiplier(game.combo.count) == 2,
            f"combo={game.combo.count} mult={combo_multiplier(game.combo.count)}",
        )
        check(
            "score uses the combo multiplier",
            game.score == 50,
            f"score={game.score}",
        )
        check(
            "slice feedback objects were spawned",
            len(game.effects) >= 8 and game.particles.active_count > 0,
            f"effects={len(game.effects)} particles={game.particles.active_count}",
        )

        # --- step 6: hit a bomb ----------------------------------------
        bomb = _spawn(game, (width * 0.5, y), bomb=True)
        game.slashes.reset()
        _swipe(game, [(width * 0.34, y), (width * 0.66, y)], start=200.0)
        _step(game)
        check(
            "bomb slice removes a life and breaks the combo",
            game.lives == config.STARTING_LIVES - config.BOMB_LIFE_PENALTY
            and game.combo.count == 0
            and not bomb.alive,
            f"lives={game.lives} combo={game.combo.count}",
        )

        # --- step 7: run out of time ----------------------------------
        score_before = game.score
        playing._time_left = 0.02
        _step(game, 0.05)
        check(
            "time up ends the round",
            game.states.phase == GamePhase.GAME_OVER
            and game.round_result == "time_up",
            f"phase={game.states.phase} result={game.round_result!r}",
        )
        check(
            "profile high score updated",
            game.profile.high_score >= score_before,
            f"high={game.profile.high_score} score={score_before}",
        )
        game._render()

        # --- step 8: restart ------------------------------------------
        game.states.handle_event(_key(pygame.K_r))
        check(
            "play again restarts and resets stats",
            game.states.phase == GamePhase.COUNTDOWN
            and game.score == 0
            and game.lives == config.STARTING_LIVES
            and game.slice_count == 0
            and game.combo.count == 0,
            f"phase={game.states.phase} score={game.score} lives={game.lives}",
        )
        game.states.handle_event(_key(pygame.K_SPACE))
        game._render()

        # --- step 9: pause, freeze, global resume ---------------------
        _spawn(game, (width * 0.5, 300))
        _step(game)
        frozen_icon = game.icon_manager.icons[0] if game.icon_manager.icons else None
        assert frozen_icon is not None
        frozen_pos = tuple(frozen_icon.position)
        frozen_time = playing.time_left

        game.states.handle_event(_key(pygame.K_ESCAPE))
        check(
            "ESC pauses the round and releases the mouse",
            game.states.phase == GamePhase.PAUSED
            and game.window.input_mode == "released",
            f"phase={game.states.phase} input={game.window.input_mode}",
        )

        game.advance(1.0)
        still_pos = tuple(frozen_icon.position) if frozen_icon.alive else None
        check(
            "pause freezes time and physics",
            playing.time_left == frozen_time and still_pos == frozen_pos,
            f"time {frozen_time}->{playing.time_left} pos {frozen_pos}->{still_pos}",
        )
        game._render()

        if focus_gained is not None:
            pygame.event.clear()
            pygame.event.post(_event(focus_gained))
            game._handle_events()
            check(
                "focus gain during a pause keeps the mouse released",
                game.states.phase == GamePhase.PAUSED
                and game.window.input_mode == "released",
                f"phase={game.states.phase} input={game.window.input_mode}",
            )
        else:
            check("focus gain during a pause keeps the mouse released", False, "event missing")

        original_poll = game.window.poll_escape
        game._resume_key_armed = False
        game._paused_at = pygame.time.get_ticks() / 1000.0
        game.window.poll_escape = lambda: True  # type: ignore[method-assign]
        game._poll_resume_key()
        check(
            "held ESC right after pausing does not resume",
            game.states.phase == GamePhase.PAUSED,
            "resumed too early",
        )
        game.window.poll_escape = lambda: False  # type: ignore[method-assign]
        game._poll_resume_key()
        game._paused_at -= config.PAUSE_RESUME_GUARD + 0.2
        game.window.poll_escape = lambda: True  # type: ignore[method-assign]
        game._poll_resume_key()
        check(
            "global ESC poll resumes after the guard delay",
            game.states.phase == GamePhase.PLAYING
            and game.window.input_mode == "active"
            and abs(playing.time_left - frozen_time) < 1e-6,
            f"phase={game.states.phase} input={game.window.input_mode}",
        )
        game.window.poll_escape = original_poll  # type: ignore[method-assign]

        focus_lost = getattr(pygame, "WINDOWFOCUSLOST", None)
        if focus_lost is not None:
            pygame.event.clear()
            pygame.event.post(_event(focus_lost))
            game._handle_events()
            check(
                "losing focus during play pauses the round",
                game.states.phase == GamePhase.PAUSED
                and game.window.input_mode == "released",
                f"phase={game.states.phase}",
            )
        else:
            check("losing focus during play pauses the round", False, "event missing")

        game.states.handle_event(_key(pygame.K_ESCAPE))
        check(
            "ESC in pause resumes again",
            game.states.phase == GamePhase.PLAYING,
            str(game.states.phase),
        )
        game.states.handle_event(_key(pygame.K_ESCAPE))
        game.states.handle_event(_key(pygame.K_q))
        check(
            "Q in pause releases input and stops the loop",
            not game.running
            and game.window.input_mode == "released"
            and game.window.capture_window() == 0,
            f"running={game.running} input={game.window.input_mode}",
        )

        # --- step 10: desktop untouched -------------------------------
        after = _desktop_signature(desktop)
        check(
            "desktop icons unchanged (name + position)",
            after == before,
            f"{len(before)} -> {len(after)}",
        )
        check(
            "no extra desktop reads during the whole session",
            game.desktop_read_count == 1,
            f"read {game.desktop_read_count} time(s)",
        )

        # --- pause screen still renders -------------------------------
        game._render()
        check("pause screen renders", True)

        # --- overlay hit-test contract ---------------------------------
        check(
            "overlay hit-test constants are distinct",
            HTCLIENT != HTTRANSPARENT,
        )
    except Exception:
        traceback.print_exc()
        check("stage 5 flow completed without exceptions", False)
    finally:
        game.shutdown()

    print(f"\n{_PASSED}/{_PASSED + _FAILED} checks passed")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
