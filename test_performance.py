"""Stage 5 performance and long-run memory checks.

    python test_performance.py

Runs headless (SDL dummy) at the real overlay resolution reported by the
primary monitor, so update/render costs reflect the transparent window size.
The long-run test churns effects and particles for several simulated minutes
and asserts the working set stays flat.
"""

from __future__ import annotations

import ctypes
import gc
import os
import random
import tempfile
import time
import traceback
from ctypes import wintypes
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

import game_config as config
import ui.text as text_module
from core.game import Game
from core.phases import GamePhase
from core.profile import ProfileStore
from desktop.desktop_interface import enable_dpi_awareness
from effects.floating_text import FloatingText
from effects.icon_fragments import IconFragments
from ui.fonts import get_font
from window.win32_overlay import get_monitor

_PROFILE_DIR = Path(tempfile.mkdtemp(prefix="desktop_slash_perf_"))
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


class _ProcessMemoryCounters(ctypes.Structure):
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


def working_set_mb() -> float:
    kernels = ctypes.WinDLL("kernel32", use_last_error=True)
    psapi = ctypes.WinDLL("psapi", use_last_error=True)
    counters = _ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    psapi.GetProcessMemoryInfo.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(_ProcessMemoryCounters),
        wintypes.DWORD,
    ]
    psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
    process = kernels.GetCurrentProcess()
    if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
        return 0.0
    return counters.WorkingSetSize / (1024 * 1024)


def _spawn_icon(game: Game, x: float, y: float):
    icon = game.icon_manager._spawn_icon()
    icon.body.position.update(x, y)
    icon.body.velocity.update(0.0, 0.0)
    return icon


def _busy_scene(game: Game) -> None:
    width, height = game.screen.get_size()
    for index in range(12):
        icon = _spawn_icon(
            game,
            width * (0.08 + 0.082 * index),
            height * (0.3 + 0.22 * (index % 3)),
        )
        icon.angle = (index * 37.0) % 360.0

    game.particles.burst(
        (width * 0.5, height * 0.5),
        count=180,
        colors=config.SLICE_PIXEL_COLORS,
        speed=config.SLICE_PIXEL_SPEED,
        lifetime=config.SLICE_PIXEL_LIFETIME,
        size=config.SLICE_PIXEL_SIZE,
        gravity=config.SLICE_PIXEL_GRAVITY,
    )
    y = int(height * 0.5)
    now = 500.0
    game.slashes.begin((width * 0.25, y), now)
    for index in range(18):
        now += 0.02
        game.slashes.move((width * (0.25 + 0.03 * index), y + (index % 4) * 6), now)

    for index in range(6):
        point = pygame.Vector2(width * (0.3 + 0.08 * index), y)
        game.effects.add(
            FloatingText(f"+{10 * (index + 1)}", point, color=config.COLOR_NEON_YELLOW)
        )


def main() -> int:
    global _PASSED, _FAILED
    print("Desktop Slash - stage 5 performance & memory checks")
    enable_dpi_awareness()

    monitor = get_monitor(0)
    if monitor is None:
        size = config.WINDOW_SIZE
        label = f"{size[0]}x{size[1]}"
    else:
        size = monitor.work_size
        label = f"{size[0]}x{size[1]} (monitor work area)"

    original_size = config.WINDOW_SIZE
    config.WINDOW_SIZE = size
    pygame.init()
    started = time.perf_counter()
    try:
        game = Game(ProfileStore(_PROFILE_DIR / "perf.json"))
    finally:
        config.WINDOW_SIZE = original_size
    startup_ms = (time.perf_counter() - started) * 1000.0
    print(f"  overlay target: {label}, dpi={game.window.dpi}")
    print(f"  startup (window + desktop read + assets): {startup_ms:.0f} ms")
    print(f"  desktop read count at startup: {game.desktop_read_count}")

    try:
        check("startup under 3 seconds", startup_ms < 3000.0, f"{startup_ms:.0f} ms")
        check("desktop icons read once", game.desktop_read_count == 1)
        check(
            "render surface matches the overlay target",
            game.screen.get_size() == size,
            f"{game.screen.get_size()} vs {size}",
        )

        game.is_overlay = True
        game.background.enabled = False
        game.screen_fx.overlay_mode = True
        game.screen_fx.scanlines_enabled = False
        game.start_round()
        game.begin_play()
        game.lives = 9999
        playing = game.states.get(GamePhase.PLAYING)
        playing._time_left = 999.0
        game.icon_manager.clear()
        _busy_scene(game)

        for _ in range(20):
            game._render()
            pygame.display.flip()

        frames = 150
        started = time.perf_counter()
        for _ in range(frames):
            game._render()
            pygame.display.flip()
        render_ms = (time.perf_counter() - started) * 1000.0 / frames

        steps = 240
        started = time.perf_counter()
        for index in range(steps):
            if index % 30 == 0 and game.icon_manager.active_count < 8:
                _spawn_icon(game, game.screen.get_width() * 0.5, 200)
            game.advance(1.0 / 60.0)
        update_ms = (time.perf_counter() - started) * 1000.0 / steps

        frame_ms = render_ms + update_ms
        print(
            f"  frame cost: update {update_ms:.2f} ms + render/flip "
            f"{render_ms:.2f} ms = {frame_ms:.2f} ms "
            f"(~{1000.0 / max(0.001, frame_ms):.0f} FPS CPU-bound)"
        )
        check(
            "update fits the 16.7 ms frame budget",
            update_ms < 8.0,
            f"{update_ms:.2f} ms",
        )
        check(
            "render fits the 16.7 ms frame budget",
            render_ms < 14.0,
            f"{render_ms:.2f} ms",
        )
        check(
            "combined estimate reaches 60 FPS",
            frame_ms <= 16.7,
            f"{frame_ms:.2f} ms",
        )

        # --- bounded pools and caches ---------------------------------
        for _ in range(3000):
            game.particles.burst(
                (100, 100),
                count=8,
                colors=config.SLICE_PIXEL_COLORS,
                speed=config.SLICE_PIXEL_SPEED,
                lifetime=config.SLICE_PIXEL_LIFETIME,
                size=config.SLICE_PIXEL_SIZE,
                gravity=config.SLICE_PIXEL_GRAVITY,
            )
        check(
            "particle pool is capped",
            game.particles.active_count <= game.particles.capacity,
            f"{game.particles.active_count}/{game.particles.capacity}",
        )
        for _ in range(300):
            game.effects.add(FloatingText("+10", (50, 50), color=config.COLOR_WHITE_HOT))
        check(
            "effect list is capped",
            len(game.effects) <= game.effects.max_active,
            f"{len(game.effects)}/{game.effects.max_active}",
        )

        text_module.clear_text_cache()
        font = get_font(config.FONT_SIZE_HUD_VALUE, bold=True)
        canvas = pygame.Surface((320, 80))
        for index in range(config.TEXT_CACHE_MAX * 2):
            text_module.draw_pixel_text(
                canvas,
                f"{index:06d}",
                font,
                config.COLOR_TEXT,
                (160, 40),
            )
        check(
            "text render cache is bounded",
            len(text_module._TEXT_CACHE) <= config.TEXT_CACHE_MAX,
            f"{len(text_module._TEXT_CACHE)}/{config.TEXT_CACHE_MAX}",
        )

        hud_surface = pygame.Surface((640, 120))
        game.hud.draw(hud_surface, 1230, 45.0, 90.0, 2, 4, 2, 9999)
        panel = game.hud._panel
        game.hud.draw(hud_surface, 4560, 44.0, 90.0, 2, 4, 2, 9999)
        check(
            "HUD panel surface is reused",
            game.hud._panel is panel and panel is not None,
        )

        icon = game.icon_manager._spawn_icon()
        icon.angle = 0.0
        first = icon.current_surface()
        second = icon.current_surface()
        check(
            "icon scale surface is cached",
            first is second and icon._scaled_cache is not None,
        )

        # --- long-run memory ------------------------------------------
        width, height = game.screen.get_size()
        sources = game.icon_manager._sources
        rng = random.Random(7)
        dt = 1.0 / 60.0

        def churn(seconds: float) -> None:
            steps = int(seconds * 60)
            for index in range(steps):
                if index % 20 == 0:
                    game.particles.burst(
                        (rng.uniform(0, width), rng.uniform(0, height)),
                        count=18,
                        colors=config.SLICE_PIXEL_COLORS,
                        speed=config.SLICE_PIXEL_SPEED,
                        lifetime=config.SLICE_PIXEL_LIFETIME,
                        size=config.SLICE_PIXEL_SIZE,
                        gravity=config.SLICE_PIXEL_GRAVITY,
                    )
                if index % 45 == 0:
                    image = sources[index % len(sources)].copy()
                    game.effects.add(
                        IconFragments(
                            image,
                            (
                                rng.uniform(0, width),
                                rng.uniform(0, height),
                            ),
                            (0.0, 0.0),
                            rng=rng,
                        )
                    )
                    game.effects.add(
                        FloatingText(
                            "+10",
                            (rng.uniform(0, width), rng.uniform(0, height)),
                            color=config.COLOR_NEON_YELLOW,
                        )
                    )
                game.effects.update(dt)
                game.particles.update(dt)

        churn(60.0)
        gc.collect()
        baseline_mb = working_set_mb()
        churn(300.0)
        gc.collect()
        after_mb = working_set_mb()
        growth = after_mb - baseline_mb
        print(
            f"  working set after 1 min warm-up: {baseline_mb:.1f} MB; "
            f"after +5 min churn: {after_mb:.1f} MB (delta {growth:+.1f} MB)"
        )
        check(
            "long-run memory stays flat (< 24 MB growth)",
            growth < 24.0,
            f"{growth:+.1f} MB",
        )

        for _ in range(360):
            game.effects.update(dt)
            game.particles.update(dt)
        check(
            "effects drain after churn stops",
            len(game.effects) == 0,
            f"{len(game.effects)} left",
        )
        check(
            "particles drain after churn stops",
            game.particles.active_count == 0,
            f"{game.particles.active_count} left",
        )
        check(
            "no desktop re-reads during the benchmark",
            game.desktop_read_count == 1,
            f"{game.desktop_read_count} reads",
        )

        game._render()
        gc.collect()
        final_mb = working_set_mb()
        print(f"  final working set: {final_mb:.1f} MB")
    except Exception:
        traceback.print_exc()
        check("performance run completed without exceptions", False)
    finally:
        game.shutdown()

    print(f"\n{_PASSED}/{_PASSED + _FAILED} checks passed")
    return 0 if _FAILED == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
