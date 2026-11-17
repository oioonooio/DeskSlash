"""Stage 2 automated checks for Desktop Slash.

Run with the project virtual environment:

    python test_gameplay.py

The script uses SDL's dummy video driver, so it does not open a window. It
exercises the wave spawner, the slash detector, scoring and lives, and writes
snapshots of every phase to ``test_output/stage2_*.png``.

If the real desktop can be read, the snapshots use those icons and the script
also verifies that desktop item names and positions are unchanged afterwards.
Nothing is ever written to the desktop.
"""

from __future__ import annotations

import os
import random
import sys
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
from desktop.desktop_interface import (
    DesktopIcon,
    DesktopInterface,
    DesktopReadResult,
)
from desktop.win32_desktop import enable_dpi_awareness
from gameplay.fallback_icons import build_fallback_icons
from gameplay.icon_manager import IconManager
from gameplay.slash_detector import SlashDetector, closest_point_on_segment
from physics.physics_world import PhysicsWorld

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_output")
FIXED_DT = config.FIXED_DT
_PROFILE_DIR = Path(tempfile.mkdtemp(prefix="desktop_slash_stage2_"))


def _new_game() -> Game:
    """Game wired to a throwaway profile so tests never touch the real save."""
    return Game(ProfileStore(_PROFILE_DIR / "save.json"))


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _icon_surface(color: tuple[int, int, int]) -> pygame.Surface:
    surface = pygame.Surface((48, 48), pygame.SRCALPHA)
    pygame.draw.rect(surface, color, surface.get_rect(), border_radius=8)
    return surface


def _fake_desktop_result(count: int = 12) -> DesktopReadResult:
    surfaces = build_fallback_icons(count)
    icons = [
        DesktopIcon(
            index=index,
            name=f"Fake {index}",
            screen_position=(index * 40, index * 30),
            image=surface,
            image_source="test",
            alpha_range=(0, 255),
            shell_path=None,
        )
        for index, surface in enumerate(surfaces)
    ]
    return DesktopReadResult(
        icons=icons,
        errors=[],
        total_items=count,
        listview_hwnd=0,
        screen_size=(1280, 720),
    )


def _make_test_game(surfaces: list[pygame.Surface], seed: int = 7) -> Game:
    original = DesktopInterface.read_desktop_icons

    def fake_read(
        self: DesktopInterface, icon_size: int | None = None
    ) -> DesktopReadResult:
        return _fake_desktop_result(len(surfaces))

    DesktopInterface.read_desktop_icons = fake_read
    try:
        game = _new_game()
    finally:
        DesktopInterface.read_desktop_icons = original

    game.icon_manager = IconManager(
        game.physics, game.screen.get_size(), random.Random(seed)
    )
    game.icon_manager.set_sources(surfaces)
    return game


def _spawn_one_and_keep(game: Game) -> object:
    """Advance one step, keep the first spawned icon and stop future waves."""
    game.advance(FIXED_DT)
    icons = list(game.icon_manager.icons)
    if not icons:
        raise AssertionError("the first wave did not spawn any icons")
    keep = icons[0]
    for extra in icons[1:]:
        game.icon_manager.remove(extra)
    game.icon_manager.set_sources([])
    return keep


def _advance_until(game: Game, predicate, max_steps: int = 600) -> bool:
    for _ in range(max_steps):
        game.advance(FIXED_DT)
        if predicate():
            return True
    return False


# ---------------------------------------------------------------------------
# Component checks
# ---------------------------------------------------------------------------
def test_segment_math() -> None:
    start = pygame.Vector2(-10, 0)
    end = pygame.Vector2(10, 0)

    closest = closest_point_on_segment(pygame.Vector2(0, 5), start, end)
    assert closest.distance_to(pygame.Vector2(0, 0)) < 1e-6
    assert SlashDetector.segment_intersects_circle(
        start, end, pygame.Vector2(0, 4), 5
    )
    assert not SlashDetector.segment_intersects_circle(
        start, end, pygame.Vector2(0, 6), 5
    )


def test_wave_rules() -> None:
    physics = PhysicsWorld()
    sources = build_fallback_icons(8)
    manager = IconManager(physics, (1280, 720), random.Random(3))
    manager.set_sources(sources)
    manager.begin_round()
    manager.update(0.0)

    first_wave = list(manager.icons)
    assert config.ICON_WAVE_MIN <= len(first_wave) <= config.ICON_WAVE_MAX, len(
        first_wave
    )
    assert len({id(icon) for icon in first_wave}) == len(first_wave)
    assert len({id(icon.body) for icon in first_wave}) == len(first_wave)
    assert all(icon.image is not sources[0] for icon in first_wave)
    motion = {
        (round(icon.velocity_x, 3), round(icon.velocity_y, 3), round(icon.gravity, 3))
        for icon in first_wave
    }
    assert len(motion) > 1, "icons should not all share the same motion"

    first_count = len(first_wave)
    manager.update(1.0)
    assert manager.active_count == first_count, "a wave spawned too early"
    manager.update(0.8)
    assert manager.active_count > first_count, "the next wave did not spawn"

    for _ in range(12):
        manager._spawn_wave()
    assert manager.active_count == config.ICON_MAX_ACTIVE, manager.active_count

    physics.clear()
    manager.clear()


def test_miss_requires_entering() -> None:
    physics = PhysicsWorld()
    manager = IconManager(physics, (1280, 720), random.Random(5))
    manager.set_sources(build_fallback_icons(6))
    manager.begin_round()
    manager.update(0.0)

    first_batch = {id(icon) for icon in manager.icons}
    missed_ids: set[int] = set()
    for _ in range(600):
        manager.update(FIXED_DT)
        physics.update(FIXED_DT)
        for icon in manager.after_physics():
            assert icon.entered, "an icon was missed before it entered the screen"
            assert icon.missed
            missed_ids.add(id(icon))

    assert first_batch <= missed_ids, "the first wave never completed its flight"
    physics.clear()
    manager.clear()


def test_slash_speed_and_multi_hit() -> None:
    detector = SlashDetector()
    icons = []
    for x in (500, 700):
        icon = type("FakeIcon", (), {})()
        icon.image = _icon_surface((90, 200, 255))
        icon.scale = 1.0
        icon.position = pygame.Vector2(x, 400)
        icon.sliced = False
        icon.missed = False
        icon.body = type("Body", (), {"alive": True})()
        icon.alive = True
        icon.hit_radius = 0.5 * (48**2 + 48**2) ** 0.5 * 1.0 * config.ICON_HITBOX_SCALE
        icons.append(icon)

    detector.begin((400, 400), 0.0)
    detector.move((500, 400), 0.5)
    assert detector.consume_hits(icons) == [], "a slow stroke must not slice"

    detector.begin((400, 400), 1.0)
    detector.move((800, 400), 1.05)
    hits = detector.consume_hits(icons)
    assert len(hits) == 2, f"expected two icons, got {len(hits)}"
    assert len({id(hit.icon) for hit in hits}) == 2
    assert detector.consume_hits(icons) == [], "segments must only score once"

    detector.begin((400, 400), 2.0)
    detector.end((400, 400), 2.0)
    assert detector.consume_hits(icons) == [], "a click without movement must not slice"


# ---------------------------------------------------------------------------
# Integration checks
# ---------------------------------------------------------------------------
def test_fixed_timestep(game: Game) -> None:
    calls: list[float] = []
    original = game._update
    game._update = lambda dt: calls.append(dt)
    try:
        game._accumulator = 0.0
        for _ in range(60):
            game.advance(FIXED_DT * 2)
        assert len(calls) == 120, len(calls)
        assert all(abs(dt - FIXED_DT) < 1e-12 for dt in calls)

        calls.clear()
        game._accumulator = 0.0
        for _ in range(30):
            game.advance(FIXED_DT * 4)
        assert len(calls) == 120, len(calls)
        assert all(abs(dt - FIXED_DT) < 1e-12 for dt in calls)
    finally:
        game._update = original
        game._accumulator = 0.0


def test_scoring_and_effects(game: Game, surfaces: list[pygame.Surface]) -> None:
    game.icon_manager.set_sources(surfaces)
    game.start_round()
    game.begin_play()
    if game.states.phase != GamePhase.PLAYING:
        raise AssertionError("begin_play did not enter PLAYING")

    target = _spawn_one_and_keep(game)
    point = target.position.copy()
    game.slashes.begin((point.x - 120, point.y), 0.0)
    game.slashes.move((point.x + 120, point.y), 0.02)
    game.slashes.end((point.x + 120, point.y), 0.03)
    game.advance(FIXED_DT)

    assert game.score == config.SCORE_PER_ICON, game.score
    assert target.sliced
    assert game.icon_manager.active_count == 0
    assert len(game.effects) >= 3, len(game.effects)

    score_before = game.score
    game.slashes.begin((point.x - 120, point.y), 1.0)
    game.slashes.move((point.x + 120, point.y), 1.02)
    game.advance(FIXED_DT)
    assert game.score == score_before, "the same icon scored twice"


def test_miss_costs_a_life(game: Game, surfaces: list[pygame.Surface]) -> None:
    game.icon_manager.set_sources(surfaces)
    game.start_round()
    game.begin_play()
    _spawn_one_and_keep(game)

    assert _advance_until(game, lambda: game.lives < config.STARTING_LIVES)
    assert game.lives == config.STARTING_LIVES - 1, game.lives
    assert game.states.phase == GamePhase.PLAYING


def test_zero_lives_ends_round(game: Game, surfaces: list[pygame.Surface]) -> None:
    game.icon_manager.set_sources(surfaces)
    game.start_round()
    game.begin_play()
    game.lives = 1
    _spawn_one_and_keep(game)

    assert _advance_until(game, lambda: game.states.phase == GamePhase.GAME_OVER)
    assert game.lives == 0
    assert game.round_result == "out_of_lives", game.round_result


def test_time_up_and_restart(game: Game, surfaces: list[pygame.Surface]) -> None:
    game.start_round()
    game.begin_play()
    playing = game.states._states[GamePhase.PLAYING]
    playing._time_left = FIXED_DT * 0.5
    game.advance(FIXED_DT)

    assert game.states.phase == GamePhase.GAME_OVER
    assert game.round_result == "time_up", game.round_result

    game.icon_manager.set_sources(surfaces)
    game.start_round()
    assert game.states.phase == GamePhase.COUNTDOWN
    assert game.score == 0
    assert game.lives == config.STARTING_LIVES
    assert game.round_result == ""
    assert game.icon_manager.active_count == 0

    game.begin_play()
    game.advance(FIXED_DT)
    assert game.states.phase == GamePhase.PLAYING
    assert config.ICON_WAVE_MIN <= game.icon_manager.active_count <= config.ICON_WAVE_MAX


# ---------------------------------------------------------------------------
# Snapshots and live desktop safety
# ---------------------------------------------------------------------------
def _desktop_state() -> list[tuple[int, str, tuple[int, int]]] | None:
    try:
        result = DesktopInterface().read_desktop_icons()
    except Exception as exc:  # noqa: BLE001 - the live check is optional
        print(f"  desktop check skipped: {exc}")
        return None
    return sorted(
        (icon.index, icon.name, icon.screen_position) for icon in result.icons
    )


def save_snapshots() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    before = _desktop_state()

    game = _new_game()
    try:
        print(
            f"  snapshots use {game.icon_source_count} "
            f"{game.icon_source_label} icon(s)"
        )

        game.go_to_menu()
        game._render()
        pygame.image.save(game.screen, os.path.join(OUTPUT_DIR, "stage2_menu.png"))

        game.start_round()
        game._render()
        pygame.image.save(
            game.screen, os.path.join(OUTPUT_DIR, "stage2_countdown.png")
        )

        game.begin_play()
        for _ in range(40):
            game.advance(1 / 60)
        game._render()
        pygame.image.save(
            game.screen, os.path.join(OUTPUT_DIR, "stage2_playing.png")
        )

        icons = list(game.icon_manager.icons)
        if icons:
            target = icons[0]
            point = target.position.copy()
            game.slashes.begin((point.x - 90, point.y - 18), 0.0)
            game.slashes.move((point.x + 90, point.y + 18), 0.02)
            game.slashes.end((point.x + 90, point.y + 18), 0.03)
            for _ in range(5):
                game.advance(1 / 60)
            game._render()
            pygame.image.save(
                game.screen, os.path.join(OUTPUT_DIR, "stage2_slice.png")
            )

        game.finish_round("out_of_lives")
        game._render()
        pygame.image.save(
            game.screen, os.path.join(OUTPUT_DIR, "stage2_game_over.png")
        )
    finally:
        game.window.close()

    after = _desktop_state()
    if before is not None and after is not None:
        if before != after:
            raise AssertionError("desktop item names or positions changed")
        print(f"  desktop unchanged: {len(before)} item(s)")


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def main() -> int:
    enable_dpi_awareness()
    pygame.init()
    surfaces = build_fallback_icons(12)

    failures = 0
    total = 0

    def run(label: str, function) -> None:
        nonlocal failures, total
        total += 1
        try:
            function()
            print(f"[PASS] {label}")
        except Exception as exc:  # noqa: BLE001 - the runner reports every failure
            failures += 1
            print(f"[FAIL] {label}: {exc}")
            traceback.print_exc()

    print("Desktop Slash - stage 2 gameplay checks")
    run("segment/circle collision", test_segment_math)
    run("wave size, interval, cap", test_wave_rules)
    run("miss only after entering", test_miss_requires_entering)
    run("slash speed, multi-hit, dedupe", test_slash_speed_and_multi_hit)

    game = _make_test_game(surfaces)
    try:
        run("fixed-timestep advance", lambda: test_fixed_timestep(game))
        run("slice scoring and effects", lambda: test_scoring_and_effects(game, surfaces))
        run("miss costs a life", lambda: test_miss_costs_a_life(game, surfaces))
        run("zero lives ends the round", lambda: test_zero_lives_ends_round(game, surfaces))
        run("time up and restart", lambda: test_time_up_and_restart(game, surfaces))
    finally:
        game.window.close()

    if "--no-snapshots" not in sys.argv:
        try:
            save_snapshots()
        except Exception as exc:  # noqa: BLE001
            failures += 1
            print(f"[FAIL] snapshots/live desktop check: {exc}")
            traceback.print_exc()

    pygame.quit()

    print(f"\n{total - failures}/{total} checks passed")
    if failures:
        print(f"{failures} check(s) failed")
        return 1
    if "--no-snapshots" not in sys.argv:
        print(f"Snapshots: {OUTPUT_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
