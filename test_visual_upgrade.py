"""Stage 6 automated checks: enlarged icons and higher launch arcs.

Run from the project root:

    python test_visual_upgrade.py

The script uses SDL's dummy driver and never opens a window. It verifies the
logical icon sizes, DPI/resolution scaling, aspect ratio, source resolution,
apex-based launch physics, spawn lanes and cuttable spacing, the breathing
scale animation and the glow pass. Two PNG sheets are written to
``test_output`` for visual inspection.

Nothing on the desktop is modified: the optional live source check only reads
the icons through the existing read-only stage 1 API.
"""

from __future__ import annotations

import math
import os
import random
import sys
import statistics
import traceback

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

import game_config as config
from desktop.desktop_interface import DesktopInterface
from desktop.win32_desktop import enable_dpi_awareness
from gameplay.game_icon import GameIcon
from gameplay.icon_manager import IconManager
from physics.body import PhysicsBody
from physics.physics_world import PhysicsWorld

OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_output")
DT = config.FIXED_DT


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _source(
    size: tuple[int, int] = (256, 256),
    color: tuple[int, int, int] = (80, 190, 240),
) -> pygame.Surface:
    width, height = size
    surface = pygame.Surface(size, pygame.SRCALPHA)
    surface.fill((0, 0, 0, 0))
    margin = max(2, min(width, height) // 12)
    pygame.draw.rect(
        surface,
        (*color, 255),
        pygame.Rect(margin, margin, width - margin * 2, height - margin * 2),
        border_radius=max(4, min(width, height) // 8),
    )
    pygame.draw.circle(
        surface,
        (255, 255, 255, 210),
        (width // 2, height // 3),
        max(3, min(width, height) // 7),
    )
    return surface


def _manager(
    screen: tuple[int, int] = (1920, 1080),
    dpi: int = 96,
    seed: int = 11,
    sources: list[pygame.Surface] | None = None,
) -> tuple[PhysicsWorld, IconManager]:
    physics = PhysicsWorld()
    manager = IconManager(physics, screen, random.Random(seed), dpi)
    manager.set_sources(sources or [_source()])
    return physics, manager


def _display_size(icon: GameIcon) -> float:
    width, height = icon.image.get_size()
    return max(width, height) * icon.scale


def _radius(icon: GameIcon) -> float:
    width, height = icon.image.get_size()
    return 0.5 * max(width, height) * icon.scale


def _flight(
    screen: tuple[int, int],
    dpi: int,
    seed: int,
) -> dict[str, float]:
    physics, manager = _manager(screen, dpi, seed)
    icon = manager._spawn_icon(speed_multiplier=1.0)
    start = icon.position.copy()
    initial_speed = icon.velocity.length()
    initial_vx = icon.velocity.x
    min_y = start.y
    max_step = 0.0
    previous = start.copy()
    saw_apex = False
    for _ in range(2400):
        physics.update(DT)
        current = icon.position.copy()
        min_y = min(min_y, current.y)
        if not saw_apex and icon.velocity_y >= 0.0:
            saw_apex = True
        max_step = max(max_step, current.distance_to(previous))
        if icon.velocity_x * initial_vx <= 0.0:
            raise AssertionError("horizontal direction snapped during the flight")
        previous = current
        if saw_apex and current.y > start.y:
            break
    if not saw_apex:
        raise AssertionError("the icon never reached its apex")
    return {
        "apex": 1.0 - min_y / screen[1],
        "min_y": min_y,
        "start_y": start.y,
        "initial_speed": initial_speed,
        "initial_vx": initial_vx,
        "max_step": max_step,
        "duration": 0.0,
    }


# ---------------------------------------------------------------------------
# Icon size and source checks
# ---------------------------------------------------------------------------
def test_logical_sizes() -> None:
    physics, manager = _manager()
    assert abs(manager.ui_scale - 1.0) < 1e-9, manager.ui_scale
    assert manager.icon_min_size == config.ICON_SIZE_SMALL
    assert manager.icon_max_size == config.ICON_SIZE_SPECIAL

    sizes: list[float] = []
    for _ in range(400):
        icon = manager._spawn_icon()
        sizes.append(_display_size(icon))
        manager.clear()
        physics.clear()

    smallest = config.ICON_SIZE_SMALL * (1.0 - config.ICON_SIZE_JITTER)
    largest = config.ICON_SIZE_SPECIAL * (1.0 + config.ICON_SIZE_JITTER)
    assert min(sizes) >= smallest - 1.0, min(sizes)
    assert max(sizes) <= largest + 1.0, max(sizes)

    classes = [0, 0, 0, 0]
    for size in sizes:
        if size < 88:
            classes[0] += 1
        elif size < 104:
            classes[1] += 1
        elif size < 120:
            classes[2] += 1
        else:
            classes[3] += 1
    assert all(count > 0 for count in classes), classes
    assert classes[1] > classes[0] and classes[1] > classes[2], classes
    assert 0.36 <= classes[1] / len(sizes) <= 0.64, classes
    assert 80 <= statistics.median(sizes) <= 112, statistics.median(sizes)


def test_aspect_and_alpha() -> None:
    source = _source((256, 160), (240, 140, 70))
    physics, manager = _manager(sources=[source])
    original = pygame.image.tostring(source, "RGBA")
    for _ in range(24):
        icon = manager._spawn_icon()
        scaled = icon._scaled_image()
        ratio = scaled.get_width() / scaled.get_height()
        assert abs(ratio - 256 / 160) < 0.02, ratio
        assert scaled.get_at((scaled.get_width() // 2, scaled.get_height() // 2)).a > 0
        assert scaled.get_at((0, 0)).a == 0
        manager.clear()
        physics.clear()
    assert pygame.image.tostring(source, "RGBA") == original, "source was mutated"


def test_dpi_and_resolution_scaling() -> None:
    cases = [
        ((1920, 1080), 96, 1.0),
        ((1920, 1080), 144, 1.5),
        ((1920, 1080), 192, 2.0),
        ((2560, 1600), 144, 1.5 * math.sqrt(2560 / 1920)),
        ((1366, 768), 96, max(1.0, math.sqrt(768 / 1080))),
    ]
    for screen, dpi, expected in cases:
        physics, manager = _manager(screen, dpi, seed=dpi + screen[0])
        assert abs(manager.ui_scale - expected) < 0.01, (screen, dpi, manager.ui_scale, expected)
        if expected >= 0.9:
            assert manager.icon_min_size >= 70, (screen, dpi, manager.icon_min_size)
        for _ in range(30):
            icon = manager._spawn_icon()
            size = _display_size(icon)
            low = manager.icon_min_size * (1.0 - config.ICON_SIZE_JITTER) - 1.0
            high = manager.icon_max_size * (1.0 + config.ICON_SIZE_JITTER) + 1.0
            assert low <= size <= high, (screen, dpi, size, low, high)
            manager.clear()
            physics.clear()


def test_live_source_resolution() -> None:
    try:
        result = DesktopInterface().read_desktop_icons(config.ICON_SOURCE_SIZE)
    except Exception as exc:  # noqa: BLE001 - the live check is optional
        print(f"  live icon source check skipped: {exc}")
        return
    if not result.icons:
        print("  live icon source check skipped: no desktop icons")
        return
    dimensions = [max(icon.image_size) for icon in result.icons]
    large = sum(1 for size in dimensions if size >= 128)
    print(
        f"  live shell icons: {len(dimensions)} read, "
        f"{large} at >=128 px, max {max(dimensions)} px"
    )
    assert large >= max(1, int(len(dimensions) * 0.75)), (
        f"only {large}/{len(dimensions)} icons were requested at high resolution"
    )


# ---------------------------------------------------------------------------
# Launch physics
# ---------------------------------------------------------------------------
def test_apex_height() -> None:
    for screen, dpi in (
        ((1280, 720), 96),
        ((1920, 1080), 96),
        ((1920, 1080), 144),
        ((2560, 1600), 144),
        ((3840, 2160), 192),
    ):
        results = [_flight(screen, dpi, seed) for seed in range(1, 71)]
        apexes = [item["apex"] for item in results]
        low, high = min(apexes), max(apexes)
        median = statistics.median(apexes)
        print(
            f"  apex {screen[0]}x{screen[1]} @ {dpi} dpi: "
            f"{low:.3f}-{high:.3f}, median {median:.3f}"
        )
        assert 0.53 <= low <= 0.60, low
        assert 0.75 <= high <= 0.84, high
        assert 0.62 <= median <= 0.74, median
        assert len({round(item, 3) for item in apexes}) >= 40
        assert statistics.pstdev(apexes) >= 0.035
        for item in results:
            assert item["start_y"] > screen[1], (screen, item["start_y"])
            limit = item["initial_speed"] * DT * 1.02 + 0.01
            assert item["max_step"] <= limit, (item["max_step"], limit)
            assert item["max_step"] <= config.PHYSICS_MAX_SPEED * DT + 0.01
        start_span = max(item["start_y"] for item in results) - min(
            item["start_y"] for item in results
        )
        assert start_span >= 20.0, start_span
        speeds = [item["initial_speed"] for item in results]
        assert max(speeds) - min(speeds) >= 150.0, (min(speeds), max(speeds))
        horizontal = [abs(item["initial_vx"]) for item in results]
        assert max(horizontal) - min(horizontal) >= 80.0, (min(horizontal), max(horizontal))


def test_spawn_lanes_and_spacing() -> None:
    physics, manager = _manager((2560, 1600), 144, seed=29)
    width, height = 2560, 1600
    physics.clear()
    manager.clear()

    for _ in range(40):
        manager._spawn_wave()
        icons = list(manager.icons)
        assert config.ICON_WAVE_MIN <= len(icons) <= config.ICON_WAVE_MAX, len(icons)
        xs = sorted(icon.position.x for icon in icons)
        gaps = [right - left for left, right in zip(xs, xs[1:])]
        radii = sorted(_radius(icon) for icon in icons)
        if gaps:
            assert min(gaps) >= 2.0 * radii[0] * 0.98 - 1.0, (min(gaps), radii[0])
        for third in range(3):
            if not any(
                third * width / 3 <= x < (third + 1) * width / 3 for x in xs
            ):
                raise AssertionError(f"wave skipped lane {third}: {xs}")
        manager.clear()
        physics.clear()

    for lane in range(3):
        for _ in range(12):
            icon = manager._spawn_icon(lane=lane)
            x = icon.position.x
            assert lane * width / 3 <= x <= (lane + 1) * width / 3, (lane, x)
            manager.clear()
            physics.clear()


# ---------------------------------------------------------------------------
# Presentation animation
# ---------------------------------------------------------------------------
def test_breathe_scale() -> None:
    icon = GameIcon(
        body=PhysicsBody(position=pygame.Vector2(100, 200)),
        image=_source((96, 96)),
        angle=12.0,
        spin=90.0,
        scale=1.0,
        base_scale=1.0,
    )
    scales: list[float] = []
    for _ in range(720):
        icon.update(DT)
        scales.append(icon.scale)
    amplitude = config.ICON_BREATHE_AMPLITUDE
    quantum = config.ICON_SCALE_QUANTUM
    assert max(scales) <= 1.0 + amplitude + quantum + 1e-9, max(scales)
    assert min(scales) >= 1.0 - amplitude - quantum - 1e-9, min(scales)
    assert max(scales) - min(scales) >= 2.0 * amplitude - 2.0 * quantum, (
        min(scales),
        max(scales),
    )
    assert len(set(scales)) >= 5, len(set(scales))
    for value in scales:
        assert abs(value - round(value / quantum) * quantum) < 1e-6, value

    other = GameIcon(
        body=PhysicsBody(position=pygame.Vector2(900, 600)),
        image=_source((96, 96)),
        scale=1.0,
        base_scale=1.0,
    )
    differs = False
    for _ in range(240):
        icon.update(DT)
        other.update(DT)
        differs = differs or icon.scale != other.scale
    assert differs, "icons breathe in lockstep"
    assert 0.0 <= icon.angle < 360.0


def test_glow_overlay() -> None:
    source = _source((96, 96), (90, 220, 255))
    original = pygame.image.tostring(source, "RGBA")
    icon = GameIcon(
        body=PhysicsBody(position=pygame.Vector2(200, 200)),
        image=source,
        scale=1.4,
        base_scale=1.4,
        angle=0.0,
    )
    scaled = icon._scaled_image()
    glow = icon._glow_image()
    assert glow is not None
    pad = max(4, round(max(scaled.get_size()) * config.ICON_GLOW_PADDING))
    assert glow.get_size() == (
        scaled.get_width() + pad * 2,
        scaled.get_height() + pad * 2,
    ), (glow.get_size(), scaled.get_size(), pad)
    assert glow.get_at(glow.get_rect().center).a > 0

    canvas = pygame.Surface((420, 420), pygame.SRCALPHA)
    canvas.fill((0, 0, 0, 0))
    icon.draw(canvas)
    alpha_rect = canvas.get_bounding_rect(min_alpha=1)
    assert alpha_rect.width > scaled.get_width(), (alpha_rect, scaled.get_size())
    assert alpha_rect.height > scaled.get_height(), (alpha_rect, scaled.get_size())
    assert pygame.image.tostring(source, "RGBA") == original, "drawing mutated the icon"

    disabled = config.ICON_GLOW_ENABLED
    config.ICON_GLOW_ENABLED = False
    try:
        icon._glow_cache = None
        assert icon._glow_image() is None
    finally:
        config.ICON_GLOW_ENABLED = disabled


# ---------------------------------------------------------------------------
# Visual sheets
# ---------------------------------------------------------------------------
def save_visual_sheets() -> None:
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    pygame.display.set_mode((1, 1), pygame.HIDDEN)

    sheet = pygame.Surface((1280, 720))
    sheet.fill((8, 10, 20))
    for y in range(720):
        tint = int(18 + 20 * y / 720)
        pygame.draw.line(sheet, (6, tint // 2, tint), (0, y), (1280, y))
    sources = [
        _source((256, 256), (80, 190, 240)),
        _source((256, 256), (240, 140, 70)),
        _source((256, 200), (110, 220, 140)),
        _source((200, 256), (210, 110, 220)),
    ]
    _, manager = _manager((1280, 720), 96, seed=4, sources=sources)
    xs = [220, 520, 820, 1090]
    for index, x in enumerate(xs):
        icon = manager._spawn_icon(lane=index % 3)
        icon.body.position = pygame.Vector2(x, 330)
        icon.angle = index * 17.0
        icon.scale = icon.base_scale
        icon.draw(sheet)
    font = pygame.font.Font(None, 30)
    labels = ["80-134 px logical", "rotated", "aspect kept", "DPI scaled"]
    for x, label in zip(xs, labels):
        text = font.render(label, True, (220, 235, 255))
        sheet.blit(text, (x - text.get_width() // 2, 520))
    pygame.image.save(sheet, os.path.join(OUTPUT_DIR, "stage6_icon_sizes.png"))

    arcs = pygame.Surface((1280, 720))
    arcs.fill((7, 9, 18))
    for fraction in (0.55, 0.75, 0.82):
        y = round(720 * (1.0 - fraction))
        pygame.draw.line(arcs, (44, 58, 84), (0, y), (1280, y), 1)
    colors = [
        (0, 238, 255),
        (255, 232, 92),
        (255, 145, 40),
        (190, 90, 255),
        (90, 220, 160),
    ]
    for index, seed in enumerate(range(1, 6)):
        physics, manager = _manager((1280, 720), 96, seed)
        icon = manager._spawn_icon(speed_multiplier=1.0)
        icon.body.position.x = 130 + index * 230
        start = icon.body.position.copy()
        points = [start.copy()]
        for _ in range(2400):
            physics.update(DT)
            points.append(icon.body.position.copy())
            if icon.body.velocity.y > 0 and icon.body.position.y > start.y:
                break
        pygame.draw.lines(arcs, colors[index], False, points, 2)
        apex_y = min(point.y for point in points)
        pygame.draw.circle(
            arcs, colors[index], (int(start.x), int(apex_y)), 4
        )
    pygame.image.save(arcs, os.path.join(OUTPUT_DIR, "stage6_flight_arcs.png"))


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------
def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    enable_dpi_awareness()
    pygame.init()

    checks = [
        ("logical icon sizes and weights", test_logical_sizes),
        ("aspect ratio and alpha preserved", test_aspect_and_alpha),
        ("DPI and resolution scaling", test_dpi_and_resolution_scaling),
        ("live high-resolution shell icons", test_live_source_resolution),
        ("launch apex 55-82% of screen height", test_apex_height),
        ("spawn lanes and cuttable spacing", test_spawn_lanes_and_spacing),
        ("breathing scale animation", test_breathe_scale),
        ("soft glow overlay", test_glow_overlay),
    ]
    failures = 0
    print("Desktop Slash - stage 6 icon and launch checks")
    for label, function in checks:
        try:
            function()
            print(f"[PASS] {label}")
        except Exception as exc:  # noqa: BLE001 - the runner reports every failure
            failures += 1
            print(f"[FAIL] {label}: {exc}")
            traceback.print_exc()

    try:
        save_visual_sheets()
        print(f"[PASS] visual sheets written to {OUTPUT_DIR}")
    except Exception as exc:  # noqa: BLE001
        failures += 1
        print(f"[FAIL] visual sheets: {exc}")
        traceback.print_exc()

    pygame.quit()
    total = len(checks) + 1
    print(f"\n{total - failures}/{total} checks passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
