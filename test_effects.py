"""Stage 3 checks and showcase for Desktop Slash.

Headless checks, effect snapshots and a live demo in one script:

    python test_effects.py               # checks + snapshots
    python test_effects.py --no-snapshots
    python test_effects.py --live        # real window, auto-cycling showcase

Snapshots are written to ``test_output/stage3_*.png``. If the real desktop can
be read, snapshots use those icons and the script verifies afterwards that no
desktop item was renamed or moved. The project never writes to the desktop.
"""

from __future__ import annotations

import math
import os
import random
import sys
import tempfile
import traceback
from pathlib import Path

LIVE = "--live" in sys.argv
if not LIVE:
    os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
    os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

import game_config as config
from audio.sfx import SoundBank
from core.game import Game
from core.phases import GamePhase
from core.profile import ProfileStore
from desktop.desktop_interface import (
    DesktopIcon,
    DesktopInterface,
    DesktopReadResult,
)
from desktop.win32_desktop import enable_dpi_awareness
from effects.bomb_blast import BombBlast
from effects.combo_callout import ComboCallout
from effects.effect_manager import EffectManager
from effects.floating_text import FloatingText
from effects.icon_fragments import IconFragments
from effects.particles import PixelParticles
from effects.screen_fx import ScreenFX
from effects.slice_flash import SliceFlash
from gameplay.combo_tracker import (
    ComboTracker,
    combo_color,
    combo_multiplier,
    combo_reward,
)
from gameplay.fallback_icons import build_fallback_icons
from gameplay.slash_detector import SlashDetector
from localization import t
from ui.fonts import get_font
from ui.text import draw_pixel_text

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_output")
FIXED_DT = config.FIXED_DT
_PROFILE_DIR = Path(tempfile.mkdtemp(prefix="desktop_slash_stage3_"))


def _new_game() -> Game:
    """Game wired to a throwaway profile so tests never touch the real save."""
    return Game(ProfileStore(_PROFILE_DIR / "save.json"))


class _StubEffect:
    """Never-ending effect used to prove the manager's cap behaves."""

    finished = False

    def update(self, dt: float) -> None:
        pass

    def draw(self, surface: pygame.Surface) -> None:
        pass


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
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


def _make_test_game(surfaces: list[pygame.Surface], seed: int = 11) -> Game:
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

    game.icon_manager = type(game.icon_manager)(
        game.physics, game.screen.get_size(), random.Random(seed)
    )
    game.icon_manager.set_sources(surfaces)
    return game


def _prepare(game: Game, sources: list[pygame.Surface]) -> None:
    """Fresh PLAYING scene with every transient effect cleared."""
    game.icon_manager.set_sources(sources)
    game.start_round()
    game.begin_play()
    _clear_scene(game)
    game.icon_manager.set_sources([])


def _clear_scene(game: Game) -> None:
    game.icon_manager.clear()
    game.physics.clear()
    game.slashes.reset()
    game.effects.clear()
    game.particles.clear()
    game.screen_fx.clear()
    game.combo.reset()


def _reset_demo(game: Game) -> None:
    """Clean scene plus a fresh scoreboard, for isolated snapshot demos."""
    if game.states.phase != GamePhase.PLAYING:
        game.begin_play()
    _clear_scene(game)
    game.score = 0
    game.lives = config.STARTING_LIVES


def _spawn_targets(
    game: Game,
    sources: list[pygame.Surface],
    positions: list[tuple[float, float]],
    bomb: bool = False,
) -> list[object]:
    """Place stationary targets exactly where the test wants them."""
    game.icon_manager.set_sources(sources)
    icons = []
    for position in positions:
        icon = game.icon_manager.spawn_bomb() if bomb else game.icon_manager._spawn_icon()
        icon.body.position.update(position[0], position[1])
        icon.body.velocity.update(0.0, 0.0)
        icon.body.gravity_scale = 0.0
        icon.entered = True
        icons.append(icon)
    game.icon_manager.set_sources([])
    return icons


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


def _effects_of(game: Game, effect_type: type) -> list[object]:
    return [effect for effect in game.effects._effects if isinstance(effect, effect_type)]


# ---------------------------------------------------------------------------
# Component checks
# ---------------------------------------------------------------------------
def test_particle_pool() -> None:
    pool = PixelParticles(capacity=24, rng=random.Random(1))
    added = pool.burst((100.0, 100.0), count=100, lifetime=(0.3, 0.5))

    assert pool.capacity == 24
    assert len(pool._pool) == 24
    assert added == 24
    assert pool.active_count == 24, pool.active_count

    identities = {id(particle) for particle in pool._pool}
    pool.update(0.6)
    assert pool.active_count == 0

    pool.burst((0.0, 0.0), count=10, lifetime=(0.3, 0.3))
    assert {id(particle) for particle in pool._pool} == identities, (
        "the pool allocated new particles instead of reusing slots"
    )

    # Sustained emission must stay at capacity and never grow the pool.
    for _ in range(200):
        pool.burst((320.0, 180.0), count=40)
        pool.update(FIXED_DT)
        assert pool.active_count <= pool.capacity

    pool.clear()
    assert pool.active_count == 0
    assert len(pool._pool) == pool.capacity


def test_particle_lifecycle() -> None:
    pool = PixelParticles(capacity=32, rng=random.Random(2))
    pool.burst((50.0, 50.0), count=12, lifetime=(0.2, 0.2), speed=(10.0, 20.0))
    assert pool.active_count == 12

    pool.update(0.1)
    assert pool.active_count == 12

    pool.update(0.1)
    assert pool.active_count == 0, "particles outlived their lifetime"
    assert len(pool._free) == pool.capacity, "expired particles leaked pool slots"


def test_effect_manager_cap() -> None:
    manager = EffectManager(max_active=4)
    accepted = sum(manager.add(_StubEffect()) for _ in range(10))

    assert manager.max_active == 4
    assert accepted == 4
    assert len(manager) == 4
    assert manager.skipped == 6, manager.skipped

    manager.add(_StubEffect())
    assert len(manager) == 4, "the manager grew past its cap"

    manager.clear()
    assert len(manager) == 0


def test_screen_fx_lifecycle() -> None:
    fx = ScreenFX((320, 180))

    fx.shake(999.0, 0.2)
    assert fx.is_shaking
    assert fx.shake_strength == config.SCREEN_SHAKE_MAX

    fx.update(0.05)
    assert fx.offset.length() > 0.0, "shake produced no displacement"

    fx.shake(1.0, 0.05)
    fx.update(0.1)
    assert fx.is_shaking, "a weak shake cut a strong one short"

    fx.update(0.2)
    assert not fx.is_shaking
    assert fx.offset.length() == 0.0

    fx.flash((255, 0, 0), 0.1, 100)
    assert fx.is_flashing
    fx.update(0.11)
    assert not fx.is_flashing

    fx.shake(4.0, 0.1)
    fx.clear()
    assert not fx.is_shaking and not fx.is_flashing


def test_combo_tracker() -> None:
    tracker = ComboTracker(window=1.0)
    assert tracker.register() == 1
    assert tracker.register() == 2
    assert tracker.register() == 3
    assert tracker.register() == 4
    assert tracker.register() == 5
    assert tracker.best == 5
    assert tracker.high

    assert combo_reward(2)[0] == t("combo.x2")
    assert combo_reward(3)[0] == t("combo.x3")
    assert combo_reward(5)[0] == t("combo.x5")
    assert combo_reward(4) is None
    assert combo_reward(8) == (t("combo.great"), "x8", config.COMBO_GREAT_COLOR)
    assert combo_reward(13)[0] == t("combo.great")
    assert combo_reward(9) is None
    assert combo_color(2) == config.COMBO_X2_COLOR
    assert combo_color(5) == config.COMBO_X5_COLOR
    assert combo_color(8) == config.COMBO_GREAT_COLOR
    assert combo_multiplier(1) == 1
    assert combo_multiplier(3) == 1
    assert combo_multiplier(4) == 2
    assert combo_multiplier(7) == 3
    assert combo_multiplier(10) == 4
    assert combo_multiplier(13) == config.COMBO_MULTIPLIER_MAX

    tracker.update(0.6)
    assert tracker.count == 5
    tracker.update(0.5)
    assert tracker.count == 0, "combo did not expire"

    tracker.register()
    tracker.break_combo()
    assert tracker.count == 0
    assert tracker.timer == 0.0


def test_slash_trail_is_bounded() -> None:
    detector = SlashDetector()
    detector.begin((0.0, 360.0), 0.0)
    for index in range(1, 320):
        detector.move(
            (index * 3.0, 360.0 + math.sin(index * 0.2) * 40.0), index * 0.004
        )

    assert detector.trail_length <= config.SLASH_TRAIL_MAX_POINTS
    sparks = detector.consume_spark_points()
    assert 0 < len(sparks) <= 16, len(sparks)

    detector.update(10.0)
    assert detector.trail_length == 0
    detector.end((960.0, 360.0), 12.0)
    detector.update(1.0)
    assert detector.trail_length == 0


def test_score_and_lives_are_config_driven() -> None:
    assert config.SLICE_PIXEL_MIN >= 8
    assert config.SLICE_PIXEL_MAX <= 20
    assert config.BOMB_LIFE_PENALTY == 1
    assert config.PARTICLE_POOL_MAX > 0
    assert config.EFFECT_MAX_ACTIVE > 0
    assert config.SLASH_TRAIL_LIFETIME > 0.0

    bank = SoundBank()
    assert isinstance(bank.enabled, bool)
    assert bank.play("slice") in (True, False)
    assert bank.play("missing") is False
    bank.stop_all()


# ---------------------------------------------------------------------------
# Integration checks
# ---------------------------------------------------------------------------
def test_slice_feedback(game: Game, surfaces: list[pygame.Surface]) -> None:
    _prepare(game, surfaces)
    target = _spawn_targets(game, surfaces, [(640.0, 340.0)])[0]

    _slash_through(game, (470.0, 340.0), (810.0, 340.0))
    game.advance(FIXED_DT)

    assert game.score == config.SCORE_PER_ICON, game.score
    assert target.sliced
    assert not target.alive
    assert len(_effects_of(game, IconFragments)) == 1, "missing icon halves"
    assert len(_effects_of(game, SliceFlash)) == 1, "missing white slice flash"
    popups = _effects_of(game, FloatingText)
    assert len(popups) == 1, "missing +10 popup"
    assert popups[0]._main.get_width() > 0
    assert game.particles.active_count >= config.SLICE_PIXEL_MIN, (
        game.particles.active_count
    )


def test_effects_never_change_scoring(game: Game, surfaces: list[pygame.Surface]) -> None:
    _prepare(game, surfaces)
    target = _spawn_targets(game, surfaces, [(640.0, 340.0)])[0]

    for _ in range(config.EFFECT_MAX_ACTIVE + 5):
        game.effects.add(_StubEffect())
    assert len(game.effects) == config.EFFECT_MAX_ACTIVE

    _slash_through(game, (470.0, 340.0), (810.0, 340.0))
    game.advance(FIXED_DT)

    assert game.score == config.SCORE_PER_ICON, "effects changed the score"
    assert target.sliced, "effects blocked hit detection"
    assert game.lives == config.STARTING_LIVES
    assert game.effects.skipped >= 3, "the capped manager did not report skips"


def test_combo_milestones(game: Game, surfaces: list[pygame.Surface]) -> None:
    _prepare(game, surfaces)
    xs = [160.0 + index * 180.0 for index in range(5)]
    _spawn_targets(game, surfaces, [(x, 360.0) for x in xs])
    _slash_through(game, (80.0, 360.0), (1120.0, 360.0))
    game.advance(FIXED_DT)

    callouts = _effects_of(game, ComboCallout)
    expected = sum(
        config.SCORE_PER_ICON * combo_multiplier(index) for index in range(1, 6)
    )
    assert game.score == expected, game.score
    assert game.score == 70, "combo multiplier changed the five-icon total"
    assert game.combo.count == 5
    assert game.combo.best == 5
    assert len(callouts) == 1, f"expected one callout, got {len(callouts)}"
    assert callouts[0]._text == t("combo.x5")
    assert game.screen_fx.is_flashing

    _prepare(game, surfaces)
    xs = [110.0 + index * 151.0 for index in range(8)]
    _spawn_targets(game, surfaces, [(x, 360.0) for x in xs])
    _slash_through(game, (40.0, 360.0), (1200.0, 360.0))
    game.advance(FIXED_DT)

    callouts = _effects_of(game, ComboCallout)
    expected = sum(
        config.SCORE_PER_ICON * combo_multiplier(index) for index in range(1, 9)
    )
    assert game.score == expected, game.score
    assert game.score == 150, "combo multiplier changed the eight-icon total"
    assert game.combo.count == 8
    assert len(callouts) == 1, f"expected one great callout, got {len(callouts)}"
    assert callouts[0]._text == t("combo.great")
    assert callouts[0]._subtext == "x8"
    assert game.screen_fx.is_shaking, "high combo did not shake the screen"


def test_bomb_explosion(game: Game, surfaces: list[pygame.Surface]) -> None:
    _prepare(game, surfaces)
    game.combo.register()
    game.combo.register()
    assert game.combo.count == 2

    bomb = _spawn_targets(game, surfaces, [(640.0, 340.0)], bomb=True)[0]
    _slash_through(game, (470.0, 340.0), (810.0, 340.0))
    game.advance(FIXED_DT)

    assert game.lives == config.STARTING_LIVES - config.BOMB_LIFE_PENALTY, game.lives
    assert game.score == 0, "a bomb must not award points"
    assert game.combo.count == 0, "a bomb must break the combo"
    assert not bomb.alive
    assert len(_effects_of(game, BombBlast)) == 1, "missing bomb blast"
    assert game.screen_fx.is_shaking
    assert game.screen_fx.is_flashing
    assert game.particles.active_count >= config.BOMB_PARTICLE_COUNT, (
        game.particles.active_count
    )

    normal = _spawn_targets(game, surfaces, [(400.0, 260.0)])[0]
    _slash_through(game, (300.0, 260.0), (500.0, 260.0), now=1.0)
    game.advance(FIXED_DT)
    assert normal.sliced and game.score == config.SCORE_PER_ICON


def test_effects_clean_themselves_up(game: Game, surfaces: list[pygame.Surface]) -> None:
    _prepare(game, surfaces)
    xs = [160.0 + index * 180.0 for index in range(5)]
    _spawn_targets(game, surfaces, [(x, 360.0) for x in xs])
    _slash_through(game, (80.0, 360.0), (1120.0, 360.0))
    game.advance(FIXED_DT)

    assert len(game.effects) > 0
    assert game.particles.active_count > 0

    for _ in range(600):
        game.advance(FIXED_DT)
        assert len(game.effects) <= config.EFFECT_MAX_ACTIVE
        assert game.particles.active_count <= config.PARTICLE_POOL_MAX

    assert len(game.effects) == 0, "effects were not released"
    assert game.particles.active_count == 0, "particles were not released"
    assert not game.screen_fx.is_shaking
    assert not game.screen_fx.is_flashing
    assert game.combo.count == 0, "combo did not expire"


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


def _snapshot_stroke(game: Game) -> None:
    game.slashes.begin((120.0, 520.0), 0.0)
    for index in range(1, 15):
        game.slashes.move(
            (120.0 + index * 78.0, 520.0 - math.sin(index * 0.36) * 110.0),
            index * 0.012,
        )
    game.advance(FIXED_DT)
    _snap(game, "stage3_slash.png")
    game.slashes.end((1212.0, 520.0), 0.30)


def _build_contact_sheet(entries: list[tuple[str, str]]) -> None:
    cell = (426, 240)
    sheet = pygame.Surface((cell[0] * 3, cell[1] * 3))
    sheet.fill((0, 0, 0))
    font = get_font(15, bold=True)

    for index, (filename, label) in enumerate(entries):
        image = pygame.image.load(os.path.join(OUTPUT_DIR, filename)).convert()
        image = pygame.transform.smoothscale(image, cell)
        x = (index % 3) * cell[0]
        y = (index // 3) * cell[1]
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

    pygame.image.save(sheet, os.path.join(OUTPUT_DIR, "stage3_effects_sheet.png"))


def save_snapshots() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    before = _desktop_state()

    game = _new_game()
    try:
        sources = list(game.icon_manager._sources)
        print(
            f"  snapshots use {game.icon_source_count} "
            f"{game.icon_source_label} icon(s)"
        )

        game.go_to_menu()
        _snap(game, "stage3_menu.png")

        game.start_round()
        _snap(game, "stage3_countdown.png")

        game.begin_play()
        for _ in range(35):
            game.advance(1 / 60)
        _snap(game, "stage3_playing.png")

        _reset_demo(game)
        _snapshot_stroke(game)

        _reset_demo(game)
        _spawn_targets(game, sources, [(640.0, 350.0)])
        _slash_through(game, (470.0, 350.0), (810.0, 350.0))
        for _ in range(6):
            game.advance(FIXED_DT)
        _snap(game, "stage3_slice.png")
        for _ in range(16):
            game.advance(FIXED_DT)
        _snap(game, "stage3_particles.png")

        _reset_demo(game)
        xs = [240.0, 440.0, 640.0, 840.0, 1040.0]
        _spawn_targets(game, sources, [(x, 360.0) for x in xs])
        _slash_through(game, (120.0, 360.0), (1160.0, 360.0))
        for _ in range(10):
            game.advance(FIXED_DT)
        _snap(game, "stage3_combo.png")

        _reset_demo(game)
        xs = [110.0 + index * 151.0 for index in range(8)]
        _spawn_targets(game, sources, [(x, 360.0) for x in xs])
        _slash_through(game, (40.0, 360.0), (1200.0, 360.0))
        for _ in range(12):
            game.advance(FIXED_DT)
        _snap(game, "stage3_great_combo.png")

        _reset_demo(game)
        _spawn_targets(game, sources, [(640.0, 350.0)], bomb=True)
        _slash_through(game, (470.0, 350.0), (810.0, 350.0))
        for _ in range(8):
            game.advance(FIXED_DT)
        _snap(game, "stage3_bomb.png")

        _reset_demo(game)
        game.score = 140
        game.lives = 0
        game.finish_round("OUT OF LIVES")
        _snap(game, "stage3_game_over.png")

        _build_contact_sheet(
            [
                ("stage3_menu.png", "MENU"),
                ("stage3_playing.png", "PLAYING"),
                ("stage3_slash.png", "SLASH TRAIL"),
                ("stage3_slice.png", "ICON SLICE"),
                ("stage3_particles.png", "PIXEL SHARDS"),
                ("stage3_combo.png", "COMBO x5"),
                ("stage3_great_combo.png", "GREAT COMBO"),
                ("stage3_bomb.png", "BOMB BLAST"),
                ("stage3_game_over.png", "GAME OVER"),
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
# Live showcase
# ---------------------------------------------------------------------------
def _live_seconds() -> float:
    """Optional automatic stop, used to smoke-test the demo headlessly."""
    if "--live-seconds" not in sys.argv:
        return 0.0
    index = sys.argv.index("--live-seconds")
    try:
        return max(0.0, float(sys.argv[index + 1]))
    except (IndexError, ValueError):
        return 0.0


def run_live() -> int:
    enable_dpi_awareness()
    duration = _live_seconds()
    game = _new_game()
    sources = list(game.icon_manager._sources)

    game.start_round()
    game.begin_play()
    game.icon_manager.set_sources([])

    playing = game.states._states[GamePhase.PLAYING]
    clock = pygame.time.Clock()
    label_font = get_font(config.FONT_SIZE_HUD_VALUE, bold=True)
    hint_font = get_font(config.FONT_SIZE_FOOTER, bold=True)

    schedule: list[tuple[float, object]] = []
    state = {"now": 0.0, "index": 0, "label": "READY"}

    def at(delay: float, callback) -> None:
        schedule.append((state["now"] + delay, callback))

    def demo_trail() -> None:
        game.slashes.begin((120.0, 520.0), 0.0)
        for index in range(1, 15):
            at(
                0.04 + index * 0.02,
                lambda i=index: game.slashes.move(
                    (120.0 + i * 78.0, 520.0 - math.sin(i * 0.36) * 110.0),
                    0.04 + i * 0.02,
                ),
            )
        at(0.34, lambda: game.slashes.end((1212.0, 520.0), 0.36))

    def demo_slice() -> None:
        _spawn_targets(game, sources, [(640.0, 340.0)])
        at(0.25, lambda: _slash_through(game, (470.0, 340.0), (810.0, 340.0)))

    def demo_combo() -> None:
        xs = [240.0, 440.0, 640.0, 840.0, 1040.0]
        _spawn_targets(game, sources, [(x, 340.0) for x in xs])
        at(0.25, lambda: _slash_through(game, (120.0, 340.0), (1160.0, 340.0)))

    def demo_great() -> None:
        xs = [110.0 + index * 151.0 for index in range(8)]
        _spawn_targets(game, sources, [(x, 340.0) for x in xs])
        at(0.25, lambda: _slash_through(game, (40.0, 340.0), (1200.0, 340.0)))

    def demo_bomb() -> None:
        _spawn_targets(game, sources, [(640.0, 340.0)], bomb=True)
        at(0.3, lambda: _slash_through(game, (470.0, 340.0), (810.0, 340.0)))

    def demo_particles() -> None:
        colors = (
            config.COLOR_WHITE_HOT,
            config.COLOR_NEON_CYAN,
            config.COLOR_NEON_YELLOW,
            config.COLOR_NEON_ORANGE,
            config.COLOR_NEON_MAGENTA,
            config.COLOR_NEON_PURPLE,
        )
        game.particles.burst(
            (640.0, 360.0),
            count=240,
            colors=colors,
            speed=(120.0, 620.0),
            lifetime=(0.5, 1.3),
            size=(2, 6),
            gravity=460.0,
        )
        game.particles.ring(
            (640.0, 360.0),
            count=36,
            radius=20.0,
            speed=(220.0, 430.0),
            colors=colors,
            lifetime=(0.35, 0.7),
            size=(2, 5),
        )

    scenarios = [
        ("SLASH TRAIL", demo_trail),
        ("ICON SLICE", demo_slice),
        ("COMBO x5", demo_combo),
        ("GREAT COMBO x8", demo_great),
        ("BOMB BLAST", demo_bomb),
        ("PIXEL PARTICLE BURST", demo_particles),
    ]
    next_trigger = 0.0

    def trigger_next() -> None:
        scenario_name, action = scenarios[state["index"] % len(scenarios)]
        state["index"] += 1
        state["label"] = scenario_name
        schedule.clear()
        game.slashes.reset()
        _clear_scene(game)
        playing._time_left = config.ROUND_SECONDS
        action()

    while game.running and (duration <= 0.0 or state["now"] < duration):
        frame_time = min(clock.tick(config.FPS) / 1000.0, config.MAX_FRAME_TIME)
        state["now"] += frame_time

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                game.running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    game.running = False
                elif event.key == pygame.K_SPACE:
                    next_trigger = 0.0
                elif event.key == pygame.K_r:
                    game.start_round()
                    game.begin_play()
                    game.icon_manager.set_sources([])
                    schedule.clear()
                    next_trigger = 0.0

        due = [item for item in schedule if item[0] <= state["now"]]
        schedule[:] = [item for item in schedule if item[0] > state["now"]]
        for _, callback in due:
            callback()

        if state["now"] >= next_trigger:
            trigger_next()
            next_trigger = state["now"] + 2.9

        game.advance(frame_time)
        game._render()

        draw_pixel_text(
            game.screen,
            state["label"],
            label_font,
            config.COLOR_WHITE_HOT,
            (config.UI_MARGIN, config.UI_HUD_HEIGHT + 26),
            "topleft",
            outline=2,
            outline_color=config.COLOR_NEON_MAGENTA,
        )
        draw_pixel_text(
            game.screen,
            "LIVE FX DEMO   SPACE NEXT   R RESTART   ESC QUIT",
            hint_font,
            config.COLOR_NEON_CYAN,
            (game.screen.get_width() - config.UI_MARGIN, config.UI_HUD_HEIGHT + 34),
            "topright",
            shadow=1,
        )
        pygame.display.flip()

    game.window.close()
    pygame.quit()
    return 0


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def main() -> int:
    if LIVE:
        return run_live()

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

    print("Desktop Slash - stage 3 arcade FX checks")
    run("particle pool cap and reuse", test_particle_pool)
    run("particle lifetime cleanup", test_particle_lifecycle)
    run("effect manager cap", test_effect_manager_cap)
    run("screen shake/flash lifecycle", test_screen_fx_lifecycle)
    run("combo tracker and milestones", test_combo_tracker)
    run("slash trail stays bounded", test_slash_trail_is_bounded)
    run("config and audio interface", test_score_and_lives_are_config_driven)

    game = _make_test_game(surfaces)
    try:
        run("slice feedback package", lambda: test_slice_feedback(game, surfaces))
        run(
            "effects never change scoring",
            lambda: test_effects_never_change_scoring(game, surfaces),
        )
        run("combo x5 and great combo", lambda: test_combo_milestones(game, surfaces))
        run("bomb explosion and life loss", lambda: test_bomb_explosion(game, surfaces))
        run(
            "effects clean themselves up",
            lambda: test_effects_clean_themselves_up(game, surfaces),
        )
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
