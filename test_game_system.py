"""Stage 4 checks and snapshots for Desktop Slash.

Run with the project virtual environment:

    python test_game_system.py                # checks + snapshots
    python test_game_system.py --no-snapshots

All checks run headless with SDL's dummy drivers. A throwaway profile file is
used for every check and snapshot, so the real save in %APPDATA% is never
touched. Snapshots go to ``test_output/stage4_*.png``.
"""

from __future__ import annotations

import json
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
from core.profile import Profile, ProfileStore
from desktop.desktop_interface import DesktopInterface
from gameplay.combo_tracker import combo_multiplier
from gameplay.difficulty import difficulty_at
from gameplay.fallback_icons import build_fallback_icons
from localization import current_language, set_language, t
from ui.fonts import get_font
from ui.text import draw_pixel_text

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_output")
FIXED_DT = config.FIXED_DT
_PROFILE_DIR = Path(tempfile.mkdtemp(prefix="desktop_slash_stage4_"))
_GAME_SEQUENCE = 0


def _new_game(name: str = "") -> Game:
    """Game wired to a throwaway profile so tests never touch the real save."""
    global _GAME_SEQUENCE
    _GAME_SEQUENCE += 1
    file_name = f"{name}_{_GAME_SEQUENCE}.json" if name else f"game_{_GAME_SEQUENCE}.json"
    return Game(ProfileStore(_PROFILE_DIR / file_name))


def _click(target: object, position: tuple[int, int]) -> None:
    target.handle_event(
        pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=position)
    )


def _press(target: object, key: int) -> None:
    target.handle_event(pygame.event.Event(pygame.KEYDOWN, key=key))


def _clear_scene(game: Game) -> None:
    game.icon_manager.clear()
    game.physics.clear()
    game.slashes.reset()
    game.effects.clear()
    game.particles.clear()
    game.screen_fx.clear()
    game.combo.reset()


def _prepare_playing(game: Game, surfaces: list[pygame.Surface]) -> None:
    game.icon_manager.set_sources(surfaces)
    game.start_round()
    game.begin_play()
    _clear_scene(game)


def _spawn_targets(
    game: Game,
    surfaces: list[pygame.Surface],
    positions: list[tuple[float, float]],
) -> None:
    game.icon_manager.set_sources(surfaces)
    for position in positions:
        icon = game.icon_manager._spawn_icon()
        icon.body.position.update(position[0], position[1])
        icon.body.velocity.update(0.0, 0.0)
        icon.body.gravity_scale = 0.0
        icon.entered = True
    game.icon_manager.set_sources([])


def _slash_through(
    game: Game,
    start: tuple[float, float],
    end: tuple[float, float],
    now: float = 0.0,
    segments: int = 6,
) -> None:
    game.slashes.begin(start, now)
    duration = 0.05
    for index in range(1, segments + 1):
        ratio = index / segments
        point = (
            start[0] + (end[0] - start[0]) * ratio,
            start[1] + (end[1] - start[1]) * ratio,
        )
        game.slashes.move(point, now + duration * ratio)
    game.slashes.end(end, now + duration)


def _fallback_surfaces() -> list[pygame.Surface]:
    return build_fallback_icons(10)


# ---------------------------------------------------------------------------
# Profile storage
# ---------------------------------------------------------------------------
def test_profile_roundtrip() -> None:
    directory = Path(tempfile.mkdtemp(prefix="profile_ok_", dir=_PROFILE_DIR))
    path = directory / "save.json"
    store = ProfileStore(path)

    fresh = store.load()
    assert fresh == Profile(), fresh
    assert not path.exists(), "loading must not create a file"

    saved = Profile(
        high_score=1234,
        volume=0.65,
        shake_enabled=False,
        scanlines_enabled=False,
        language="en_US",
    )
    assert store.save(saved), store.last_error
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["version"] == config.PROFILE_VERSION
    assert payload["high_score"] == 1234
    assert payload["settings"] == {
        "volume": 0.65,
        "shake": False,
        "scanlines": False,
        "language": "en_US",
    }
    assert store.load() == saved
    assert [item.name for item in directory.iterdir()] == ["save.json"], (
        "atomic save left a temp file"
    )


def test_profile_survives_bad_data() -> None:
    directory = Path(tempfile.mkdtemp(prefix="profile_bad_", dir=_PROFILE_DIR))
    path = directory / "save.json"
    store = ProfileStore(path)

    path.write_text("{not json", encoding="utf-8")
    assert store.load() == Profile()
    assert store.last_error, "a corrupt file should be reported"

    path.write_text(
        json.dumps(
            {
                "version": 99,
                "high_score": -40,
                "settings": {"volume": 4.5, "shake": "no", "scanlines": False},
            }
        ),
        encoding="utf-8",
    )
    loaded = store.load()
    assert loaded.high_score == 0
    assert loaded.volume == 1.0
    assert loaded.shake_enabled is True
    assert loaded.scanlines_enabled is False

    assert store.save(loaded)
    assert store.load() == loaded
    assert store.last_error == ""

    default_path = ProfileStore().path
    assert default_path.name == config.PROFILE_FILE_NAME
    assert config.PROFILE_DIR_NAME in str(default_path)


# ---------------------------------------------------------------------------
# Difficulty and scoring
# ---------------------------------------------------------------------------
def test_difficulty_curve() -> None:
    start = difficulty_at(0.0)
    end = difficulty_at(config.ROUND_SECONDS)
    over = difficulty_at(config.ROUND_SECONDS * 2)

    assert start.wave_bonus == 0
    assert start.speed_multiplier == 1.0
    assert start.spawn_interval == config.ICON_SPAWN_INTERVAL
    assert start.bomb_chance == config.BOMB_SPAWN_CHANCE

    assert end.wave_bonus == config.DIFFICULTY_WAVE_BONUS_MAX
    assert abs(end.speed_multiplier - config.DIFFICULTY_SPEED_MAX_MULT) < 1e-6
    assert abs(end.spawn_interval - config.DIFFICULTY_SPAWN_INTERVAL_MIN) < 1e-6
    assert abs(end.bomb_chance - config.DIFFICULTY_BOMB_CHANCE_MAX) < 1e-6
    assert over == end, "the curve must clamp at the end of the round"

    samples = [difficulty_at(config.ROUND_SECONDS * ratio) for ratio in (0, 0.25, 0.5, 0.75, 1.0)]
    for earlier, later in zip(samples, samples[1:]):
        assert later.wave_bonus >= earlier.wave_bonus
        assert later.speed_multiplier >= earlier.speed_multiplier
        assert later.spawn_interval <= earlier.spawn_interval
        assert later.bomb_chance >= earlier.bomb_chance


def test_waves_follow_difficulty() -> None:
    game = _new_game("waves")
    try:
        surfaces = _fallback_surfaces()
        manager = game.icon_manager
        manager.set_sources(surfaces)
        manager._rng = random.Random(5)

        manager.clear()
        manager._elapsed = 0.0
        manager._spawn_wave(difficulty_at(0.0))
        early_count = len(manager.icons)
        assert config.ICON_WAVE_MIN <= early_count <= config.ICON_WAVE_MAX, early_count

        manager.clear()
        manager._elapsed = config.ROUND_SECONDS
        manager._spawn_wave(difficulty_at(config.ROUND_SECONDS))
        late_count = len(manager.icons)
        assert late_count > early_count, (early_count, late_count)
        assert late_count <= config.ICON_MAX_ACTIVE, late_count
        assert late_count >= config.ICON_WAVE_MIN + config.DIFFICULTY_WAVE_BONUS_MAX

        manager.clear()
        manager._elapsed = 0.0
        manager._spawn_timer = 0.0
        manager.update(0.0)
        early_timer = manager._spawn_timer
        manager.clear()
        manager._elapsed = config.ROUND_SECONDS * 0.9
        manager._spawn_timer = 0.0
        manager.update(0.0)
        late_timer = manager._spawn_timer
        assert late_timer < early_timer - 0.3, (early_timer, late_timer)
    finally:
        game.window.close()


def test_combo_multiplier_scoring() -> None:
    game = _new_game("multiplier")
    try:
        surfaces = _fallback_surfaces()
        _prepare_playing(game, surfaces)
        xs = [260.0, 460.0, 660.0, 860.0]
        _spawn_targets(game, surfaces, [(x, 360.0) for x in xs])
        _slash_through(game, (120.0, 360.0), (1000.0, 360.0))
        game.advance(FIXED_DT)

        expected = sum(
            config.SCORE_PER_ICON * combo_multiplier(index) for index in range(1, 5)
        )
        assert expected == 50
        assert game.score == expected, game.score
        assert game.combo.count == 4
        assert game.slice_count == 4
        assert game.best_combo == 4
        assert combo_multiplier(4) == 2
        assert combo_multiplier(7) == 3
    finally:
        game.window.close()


# ---------------------------------------------------------------------------
# Menu and settings
# ---------------------------------------------------------------------------
def test_menu_navigation() -> None:
    game = _new_game("menu")
    try:
        assert game.states.phase == GamePhase.MENU
        menu = game.states._current
        labels = [button.label for button in menu._buttons]
        assert labels == [t("menu.start"), t("menu.settings"), t("menu.exit")], labels
        assert menu._buttons[0].action == "start"
        assert menu._buttons[1].action == "settings"
        assert menu._buttons[2].action == "exit"

        _click(menu, menu._buttons[0].rect.center)
        assert game.states.phase == GamePhase.COUNTDOWN

        game.go_to_menu()
        _click(menu, menu._buttons[1].rect.center)
        assert menu._overlay.is_open
        _click(menu, menu._overlay._rows[-1].center)
        assert not menu._overlay.is_open

        game.running = True
        _click(menu, menu._buttons[2].rect.center)
        assert not game.running
    finally:
        game.window.close()


def test_settings_overlay() -> None:
    game = _new_game("settings")
    try:
        menu = game.states._current
        _click(menu, menu._buttons[1].rect.center)
        overlay = menu._overlay
        assert overlay.is_open
        start_volume = game.profile.volume
        start_shake = game.profile.shake_enabled
        start_scanlines = game.profile.scanlines_enabled

        _click(menu, overlay._plus.center)
        expected = round(min(1.0, start_volume + config.VOLUME_STEP), 2)
        assert abs(game.profile.volume - expected) < 1e-6, game.profile.volume
        assert abs(game.sfx.volume - expected) < 1e-6

        _click(menu, overlay._minus.center)
        assert abs(game.profile.volume - start_volume) < 1e-6

        _click(menu, overlay._rows[1].center)
        assert game.profile.shake_enabled is not start_shake
        assert game.screen_fx.shake_enabled == game.profile.shake_enabled

        _click(menu, overlay._rows[2].center)
        assert game.profile.scanlines_enabled is not start_scanlines
        assert game.screen_fx.scanlines_enabled == game.profile.scanlines_enabled

        saved = game.profile_store.load()
        assert saved.volume == game.profile.volume
        assert saved.shake_enabled == game.profile.shake_enabled
        assert saved.scanlines_enabled == game.profile.scanlines_enabled
        assert saved.language == game.profile.language

        language_before = game.profile.language
        _click(menu, overlay._rows[3].center)
        assert game.profile.language != language_before
        assert current_language() == game.profile.language
        assert game.profile_store.load().language == game.profile.language
        assert menu._buttons[0].label == t("menu.start")
        _click(menu, overlay._rows[3].center)
        assert game.profile.language == language_before
        set_language(language_before)

        _click(menu, overlay._rows[-1].center)
        assert not overlay.is_open

        menu._focused = 0
        _press(menu, pygame.K_DOWN)
        assert menu._focused == 1
        _press(menu, pygame.K_UP)
        assert menu._focused == 0
        _press(menu, pygame.K_ESCAPE)
        assert not game.running
    finally:
        game.window.close()


def test_settings_persist_across_games() -> None:
    path = _PROFILE_DIR / "persist.json"
    store = ProfileStore(path)
    first = Game(store)
    try:
        menu = first.states._current
        _click(menu, menu._buttons[1].rect.center)
        _click(menu, menu._overlay._plus.center)
        _click(menu, menu._overlay._rows[1].center)
        _click(menu, menu._overlay._rows[2].center)
        expected = first.profile
    finally:
        first.window.close()

    second = Game(ProfileStore(path))
    try:
        assert second.profile == expected
        assert second.screen_fx.shake_enabled == expected.shake_enabled
        assert second.screen_fx.scanlines_enabled == expected.scanlines_enabled
        assert abs(second.sfx.volume - expected.volume) < 1e-6
        menu = second.states._current
        assert menu._buttons[0].rect.width == config.UI_BUTTON_WIDTH
    finally:
        second.window.close()


# ---------------------------------------------------------------------------
# Countdown, high score and reset
# ---------------------------------------------------------------------------
def test_countdown_and_sounds() -> None:
    game = _new_game("countdown")
    try:
        game.start_round()
        countdown = game.states._current
        assert game.states.phase == GamePhase.COUNTDOWN

        samples = (
            (3.7, "3"),
            (2.7, "2"),
            (1.7, "1"),
            (0.5, t("countdown.go_label")),
        )
        for time_left, label in samples:
            countdown._time_left = time_left
            stage = countdown._stage()
            assert stage[3] == label, (time_left, stage)

        recorded: list[str] = []
        original_play = game.sfx.play

        def record(name: str, volume: float = 1.0) -> bool:
            recorded.append(name)
            return True

        game.sfx.play = record  # type: ignore[method-assign]
        try:
            countdown._sound_index = -1
            for time_left, _label in samples:
                countdown._time_left = time_left
                countdown._sync_sound()
        finally:
            game.sfx.play = original_play  # type: ignore[method-assign]
        assert recorded == ["count", "count", "count", "go"], recorded

        countdown._time_left = 0.05
        countdown.update(0.1)
        assert game.states.phase == GamePhase.PLAYING
        assert game.profile.high_score >= 0
    finally:
        game.window.close()


def test_high_score_and_game_over() -> None:
    game = _new_game("highscore")
    try:
        game.profile.high_score = 900
        game.save_profile()
        game.start_round()
        game.begin_play()
        game.score = 1280
        game.slice_count = 24
        game.best_combo = 11
        game.lives = 0
        game.finish_round("out_of_lives")

        assert game.states.phase == GamePhase.GAME_OVER
        assert game.new_high_score
        assert game.profile.high_score == 1280
        assert game.profile_store.load().high_score == 1280

        game_over = game.states._current
        labels = [button.label for button in game_over._buttons]
        assert labels == [
            t("gameover.play_again"),
            t("gameover.main_menu"),
            t("gameover.exit"),
        ], labels
        assert [button.action for button in game_over._buttons] == [
            "start",
            "menu",
            "exit",
        ]

        _click(game_over, game_over._buttons[0].rect.center)
        assert game.states.phase == GamePhase.COUNTDOWN
        assert game.score == 0
        assert game.lives == config.STARTING_LIVES
        assert game.slice_count == 0
        assert game.best_combo == 0
        assert not game.new_high_score
        assert game.combo.count == 0
        assert not game.icon_manager.icons

        game.begin_play()
        game.score = 40
        game.slice_count = 2
        game.best_combo = 2
        game.finish_round("time_up")
        assert not game.new_high_score
        assert game.profile.high_score == 1280, "a lower score overwrote the best"

        _click(game.states._current, game.states._current._buttons[1].rect.center)
        assert game.states.phase == GamePhase.MENU
    finally:
        game.window.close()


def test_restart_clears_everything() -> None:
    game = _new_game("restart")
    try:
        surfaces = _fallback_surfaces()
        _prepare_playing(game, surfaces)
        xs = [260.0, 460.0, 660.0, 860.0]
        _spawn_targets(game, surfaces, [(x, 360.0) for x in xs])
        _slash_through(game, (120.0, 360.0), (1000.0, 360.0))
        game.advance(FIXED_DT)
        assert game.score > 0
        assert len(game.effects) > 0
        assert game.particles.active_count > 0

        game.start_round()
        assert game.states.phase == GamePhase.COUNTDOWN
        assert game.score == 0
        assert game.lives == config.STARTING_LIVES
        assert game.slice_count == 0
        assert game.best_combo == 0
        assert game.new_high_score is False
        assert game.combo.count == 0
        assert not game.icon_manager.icons
        assert len(game.effects) == 0
        assert game.particles.active_count == 0
        assert not game.screen_fx.is_shaking
        assert not game.screen_fx.is_flashing
    finally:
        game.window.close()


def test_every_screen_renders() -> None:
    game = _new_game("render")
    try:
        game._render()
        game.start_round()
        game._render()
        countdown = game.states._current
        countdown._time_left = 0.6
        game._render()
        game.begin_play()
        game._render()
        game.finish_round("time_up")
        game._render()
        assert game.screen.get_size() == tuple(config.WINDOW_SIZE)
    finally:
        game.window.close()


# ---------------------------------------------------------------------------
# Snapshots
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


def _snap(game: Game, name: str) -> None:
    game._render()
    pygame.image.save(game.screen, os.path.join(OUTPUT_DIR, name))


def _spawn_demo_targets(
    game: Game,
    positions: list[tuple[float, float]],
) -> None:
    for position in positions:
        icon = game.icon_manager._spawn_icon()
        icon.body.position.update(position[0], position[1])
        icon.body.velocity.update(0.0, 0.0)
        icon.body.gravity_scale = 0.0
        icon.entered = True


def _build_contact_sheet(entries: list[tuple[str, str]]) -> None:
    font = get_font(18, bold=True)
    columns = 3
    rows = (len(entries) + columns - 1) // columns
    cell = (426, 248)
    sheet = pygame.Surface((columns * cell[0], rows * cell[1]))

    for index, (filename, label) in enumerate(entries):
        image = pygame.image.load(os.path.join(OUTPUT_DIR, filename)).convert()
        image = pygame.transform.smoothscale(image, cell)
        x = (index % columns) * cell[0]
        y = (index // columns) * cell[1]
        sheet.blit(image, (x, y))
        pygame.draw.rect(sheet, config.COLOR_PANEL_BORDER, (x, y, *cell), 1)
        bar = pygame.Surface((cell[0], 22), pygame.SRCALPHA)
        bar.fill((0, 0, 0, 190))
        sheet.blit(bar, (x, y + cell[1] - 22))
        draw_pixel_text(
            sheet,
            label,
            font,
            config.COLOR_NEON_CYAN,
            (x + 8, y + cell[1] - 11),
            "midleft",
            shadow=1,
        )

    pygame.image.save(sheet, os.path.join(OUTPUT_DIR, "stage4_system_sheet.png"))


def save_snapshots() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    before = _desktop_state()
    store = ProfileStore(_PROFILE_DIR / "snapshot.json")
    store.save(Profile(high_score=900, volume=0.6))

    game = Game(store)
    try:
        sources = list(game.icon_manager._sources)
        print(
            f"  snapshots use {game.icon_source_count} "
            f"{game.icon_source_label} icon(s)"
        )

        game.go_to_menu()
        _snap(game, "stage4_menu.png")

        menu = game.states._current
        _click(menu, menu._buttons[1].rect.center)
        _snap(game, "stage4_settings.png")
        menu._overlay.close()

        game.start_round()
        _snap(game, "stage4_countdown_3.png")

        game.states._current._time_left = 0.55
        _snap(game, "stage4_countdown_go.png")

        game.begin_play()
        game.icon_manager.set_sources(sources)
        xs = [250.0, 380.0, 510.0, 640.0, 770.0, 900.0, 1030.0]
        _spawn_demo_targets(game, [(x, 360.0) for x in xs])
        game.icon_manager.set_sources([])
        _slash_through(game, (150.0, 360.0), (1130.0, 360.0))
        for _ in range(10):
            game.advance(FIXED_DT)
        _snap(game, "stage4_playing.png")

        game.score = 1280
        game.slice_count = 24
        game.best_combo = 11
        game.lives = 0
        game.finish_round("out_of_lives")
        for _ in range(10):
            game.advance(FIXED_DT)
        _snap(game, "stage4_game_over.png")

        _build_contact_sheet(
            [
                ("stage4_menu.png", "START SCREEN"),
                ("stage4_settings.png", "SETTINGS"),
                ("stage4_countdown_3.png", "COUNTDOWN 3"),
                ("stage4_countdown_go.png", "COUNTDOWN GO!"),
                ("stage4_playing.png", "HUD · COMBO · BEST"),
                ("stage4_game_over.png", "SUMMARY · NEW HIGH"),
            ]
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
def run(name: str, function: object) -> bool:
    try:
        function()
    except Exception:
        print(f"[FAIL] {name}")
        traceback.print_exc()
        return False
    print(f"[PASS] {name}")
    return True


def main() -> int:
    print("Desktop Slash - stage 4 game system checks")
    checks = [
        ("profile JSON round trip", test_profile_roundtrip),
        ("profile survives bad data", test_profile_survives_bad_data),
        ("single difficulty curve", test_difficulty_curve),
        ("waves and spacing ramp up", test_waves_follow_difficulty),
        ("combo multiplier scoring", test_combo_multiplier_scoring),
        ("menu buttons and navigation", test_menu_navigation),
        ("settings overlay controls", test_settings_overlay),
        ("settings persist across games", test_settings_persist_across_games),
        ("3-2-1-GO countdown and sounds", test_countdown_and_sounds),
        ("high score and game over actions", test_high_score_and_game_over),
        ("restart resets all state", test_restart_clears_everything),
        ("every screen renders", test_every_screen_renders),
    ]
    passed = 0
    for name, function in checks:
        passed += run(name, function)
    print(f"\n{passed}/{len(checks)} checks passed")

    if "--no-snapshots" not in sys.argv:
        print("\nWriting stage 4 snapshots")
        try:
            save_snapshots()
        except Exception:
            traceback.print_exc()
            return 1
        print("  wrote test_output/stage4_*.png")

    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
