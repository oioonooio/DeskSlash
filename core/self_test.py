"""Startup self-test used by ``main.py --self-test`` and the packaged EXE.

It verifies the things that only break after packaging: bundled assets,
pygame/SDL, pywin32 COM imports, desktop icon reading, the overlay helpers
and the render pipeline. It never creates the real overlay window, so it is
safe to run while the desktop is in use.
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
from pathlib import Path

import pygame

import game_config as config
from core import resources
from core.game import Game
from core.phases import GamePhase
from core.profile import ProfileStore
from desktop.desktop_interface import DesktopInterface
from desktop.desktop_background import DesktopBackgroundError, find_desktop_window
from localization import available_languages, current_language, t
from ui.fonts import get_font
from ui.text import draw_pixel_text
from window.win32_overlay import IS_WINDOWS, list_monitors


def run_self_test(monitor_index: int | None = None, report: Path | None = None) -> int:
    from desktop.win32_desktop import enable_dpi_awareness

    enable_dpi_awareness()
    lines: list[str] = []
    failures = 0

    def record(name: str, ok: bool, detail: str = "") -> None:
        nonlocal failures
        if not ok:
            failures += 1
        lines.append(f"[{'PASS' if ok else 'FAIL'}] {name}" + (f" -> {detail}" if detail else ""))

    def note(text: str) -> None:
        lines.append(f"  {text}")

    lines.append("Desktop Slash self-test")
    note(f"executable: {sys.executable}")
    note(f"frozen: {resources.is_frozen()} package_root={resources.package_root()}")
    note(f"platform: {sys.platform} python={sys.version.split()[0]}")
    note(f"pygame: {pygame.version.ver} SDL={'.'.join(map(str, pygame.get_sdl_version()))}")

    desktop = DesktopInterface()
    before: list[tuple[str, int, int]] = []
    try:
        before = [(icon.name, *icon.screen_position) for icon in desktop.read_desktop_icons().icons]
    except Exception as exc:
        note(f"desktop signature unavailable: {exc}")

    game = None
    try:
        icon_path = resources.asset_path("icon.png")
        record("bundled assets/icon.png exists", icon_path.exists(), str(icon_path))
        if icon_path.exists():
            image = pygame.image.load(str(icon_path))
            record(
                "window icon loads at 256x256",
                image.get_size() == (256, 256),
                str(image.get_size()),
            )
        ico_path = resources.asset_path("icon.ico")
        record("bundled assets/icon.ico exists", ico_path.exists(), str(ico_path))

        try:
            import pythoncom  # noqa: F401
            import win32com.client  # noqa: F401

            record("pywin32 COM modules import", True)
        except Exception as exc:
            record("pywin32 COM modules import", False, str(exc))

        if IS_WINDOWS:
            monitors = list_monitors()
            record("monitors enumerated", len(monitors) >= 1, f"{len(monitors)}")
            for monitor in monitors:
                note(monitor.describe())

            try:
                shell = find_desktop_window()
            except DesktopBackgroundError as exc:
                record("desktop icon control validated", False, str(exc))
            else:
                record(
                    "desktop icon control validated",
                    True,
                    f"hwnd={shell.listview_hwnd} host={shell.host_class} "
                    f"owner={shell.owner_name} visible={shell.was_visible}",
                )
                note(
                    f"desktop icon list style=0x{shell.style:08X} "
                    f"exstyle=0x{shell.exstyle:08X}"
                )

        record(
            "overlay helpers support Windows",
            IS_WINDOWS,
            f"platform={sys.platform}",
        )

        with tempfile.TemporaryDirectory(prefix="desktop_slash_selftest_") as tmp:
            game = Game(
                ProfileStore(Path(tmp) / "save.json"),
                overlay=False,
                monitor=monitor_index,
            )
            record(
                "game initialises",
                game.states.phase == GamePhase.MENU,
                str(game.states.phase),
            )
            record(
                "desktop icons read once",
                game.desktop_read_count == 1,
                f"{game.desktop_read_count} read(s)",
            )
            record(
                "icon sources loaded",
                game.icon_source_count > 0,
                f"{game.icon_source_count} ({game.icon_source_label})",
            )
            note(
                f"icon source request={game.icon_source_size}px "
                f"ui_scale={game.icon_manager.ui_scale:.2f} "
                f"on-screen={game.icon_manager.icon_min_size}-"
                f"{game.icon_manager.icon_max_size}px"
            )

            font = get_font(config.FONT_SIZE_TITLE, bold=True)
            text_surface = font.render("DESKTOP SLASH", False, config.COLOR_NEON_CYAN)
            record("bundled font renders", text_surface.get_width() > 0)

            cjk_font = get_font(config.FONT_SIZE_EYEBROW, bold=True, cjk=True)
            cjk_sample = t("menu.start") + t("hud.score") + t("hud.lives")
            missing = [
                char
                for char in cjk_sample
                if char.strip() and cjk_font.metrics(char)[0] is None
            ]
            record(
                "Chinese glyphs render (no tofu)",
                not missing and cjk_font.size(cjk_sample)[0] > 40,
                f"language={current_language()} missing={missing or 'none'}",
            )
            record(
                "language catalogues loaded",
                available_languages() == ("zh_CN", "en_US"),
                ",".join(available_languages()),
            )

            mixer = getattr(pygame, "mixer", None)
            audio_ready = bool(mixer and mixer.get_init() and game.sfx.enabled)
            if audio_ready:
                record("synthesised audio bank ready", True, f"{len(game.sfx._sounds)} cues")
            else:
                note("audio device unavailable; sounds are disabled (not a failure)")

            game.is_overlay = True
            game.background.enabled = False
            game.screen_fx.overlay_mode = True
            game.screen_fx.scanlines_enabled = False
            key = config.WINDOW_TRANSPARENT_COLOR_KEY
            game._render()
            corners = (
                game.scene.get_at((4, 4))[:3],
                game.scene.get_at((game.scene.get_width() - 4, 4))[:3],
                game.scene.get_at((4, game.scene.get_height() - 4))[:3],
                game.scene.get_at(
                    (game.scene.get_width() - 4, game.scene.get_height() - 4)
                )[:3],
            )
            record(
                "overlay render clears to the colour key",
                all(tuple(pixel) == key for pixel in corners),
                str(corners),
            )
            non_key = sum(
                1
                for x in range(0, game.scene.get_width(), 24)
                for y in range(0, game.scene.get_height(), 24)
                if tuple(game.scene.get_at((x, y))[:3]) != key
            )
            record("menu draws over the transparent scene", non_key > 30, f"{non_key} samples")

            game.start_round()
            game.begin_play()
            game.advance(config.FIXED_DT)
            game._render()
            record(
                "playing state advances and renders",
                game.states.phase == GamePhase.PLAYING,
                str(game.states.phase),
            )

            game.states.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
            record(
                "pause releases the mouse",
                game.states.phase == GamePhase.PAUSED
                and game.window.input_mode == "released",
                f"{game.states.phase} {game.window.input_mode}",
            )
            game.resume_round()
            record(
                "resume reclaims the mouse",
                game.window.input_mode == "active",
                game.window.input_mode,
            )
    except Exception:
        record("self-test completed without exceptions", False)
        note(traceback.format_exc())

    if before:
        try:
            after = [
                (icon.name, *icon.screen_position)
                for icon in desktop.read_desktop_icons().icons
            ]
            record("desktop icons unchanged", after == before, f"{len(before)} items")
        except Exception as exc:
            note(f"desktop re-check skipped: {exc}")

    if game is not None:
        try:
            game.shutdown()
        except Exception:
            note(traceback.format_exc())
    else:
        pygame.quit()

    try:
        from window.window_manager import WindowManager

        WindowManager.emergency_restore()
        record("crash recovery ran cleanly", True)
    except Exception as exc:
        record("crash recovery ran cleanly", False, str(exc))

    lines.append(f"\n{'PASS' if failures == 0 else 'FAIL'}: {failures} failure(s)")
    text = "\n".join(lines)

    report_path = report or default_report_path()
    try:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(text + "\n", encoding="utf-8")
        text += f"\nreport written: {report_path}"
    except OSError as exc:
        text += f"\ncould not write report: {exc}"

    if sys.stdout is not None:
        print(text)
    return 0 if failures == 0 else 1


def default_report_path() -> Path:
    if resources.is_frozen():
        base = Path(sys.executable).resolve().parent
    else:
        base = resources.package_root()
    return base / "desktop_slash_self_test.txt"
