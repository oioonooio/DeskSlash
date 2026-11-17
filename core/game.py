from __future__ import annotations

import os
import threading
import time
from enum import Enum

import pygame

import game_config as config
from core.diagnostics import log, log_exception
from core.focus import FocusManager
from core.frame_stats import FrameStats
from core.phases import GamePhase
from core.profile import ProfileStore
from core.state_manager import StateManager
from desktop.desktop_background import (
    DesktopBackgroundError,
    DesktopBackgroundManager,
)
from desktop.desktop_interface import DesktopInterface, DesktopReadError
from desktop.wallpaper import build_desktop_backdrop
from desktop.win32_desktop import enable_dpi_awareness
from effects.effect_manager import EffectManager
from effects.particles import PixelParticles
from effects.screen_fx import ScreenFX
from gameplay.combo_tracker import ComboTracker
from gameplay.fallback_icons import build_fallback_icons
from gameplay.icon_manager import IconManager
from gameplay.slash_detector import SlashDetector
from localization import current_language, set_language as apply_language
from physics.physics_world import PhysicsWorld
from audio.sfx import SoundBank
from ui.background import Background
from ui.fonts import clear_font_cache
from ui.hud import HUD
from ui.text import clear_text_cache
from window.win32_overlay import IS_WINDOWS, release_system_input
from window.window_manager import WindowManager

_FOCUS_LOST = getattr(pygame, "WINDOWFOCUSLOST", None)
_FOCUS_GAINED = getattr(pygame, "WINDOWFOCUSGAINED", None)


class ShutdownPhase(Enum):
    RUNNING = "running"
    SHUTTING_DOWN = "shutting_down"
    RESTORING_DESKTOP = "restoring_desktop"
    DESTROYING_WINDOWS = "destroying_windows"
    RELEASING_RESOURCES = "releasing_resources"
    STOPPED = "stopped"


class Game:
    """Owns the window, the shared systems and the fixed-timestep loop."""

    def __init__(
        self,
        profile_store: ProfileStore | None = None,
        *,
        overlay: bool | None = None,
        monitor: int | None = None,
        desktop: DesktopInterface | None = None,
        hide_desktop: bool | None = None,
    ) -> None:
        enable_dpi_awareness()
        os.environ.setdefault("SDL_VIDEO_MINIMIZE_ON_FOCUS_LOSS", "0")
        pygame.init()
        # Cached font surfaces die with SDL; a second Game in the same process
        # (tests, editor restarts) must not reuse them by id(font).
        clear_font_cache()
        clear_text_cache()
        self.window = WindowManager(overlay=overlay, monitor=monitor)
        self.screen = self.window.create()
        self.is_overlay = self.window.is_overlay
        self.scene = pygame.Surface(self.screen.get_size()).convert()
        if self.is_overlay:
            self.scene.fill(config.WINDOW_TRANSPARENT_COLOR_KEY)
        self.wallpaper_backdrop = None
        self.wallpaper_error = ""
        self.wallpaper_backdrop = self._build_wallpaper_backdrop()
        self.clock = pygame.time.Clock()
        self.frame_stats = FrameStats()
        self.running = True

        self.profile_store = profile_store or ProfileStore()
        self.profile = self.profile_store.load()
        # Fonts and state labels are built below, so apply the saved language
        # before the UI objects exist.
        apply_language(self.profile.language)

        self.desktop = desktop or DesktopInterface()
        self.desktop_background = DesktopBackgroundManager()
        self.desktop_hidden = False
        self.desktop_hide_error = ""
        self.physics = PhysicsWorld()
        self.effects = EffectManager()
        self.particles = PixelParticles()
        self.screen_fx = ScreenFX(
            self.screen.get_size(),
            scanlines=not self.is_overlay,
        )
        self.screen_fx.overlay_mode = self.is_overlay
        self.screen_fx.shake_enabled = self.profile.shake_enabled
        self.screen_fx.scanlines_enabled = (
            self.profile.scanlines_enabled and not self.is_overlay
        )
        self.sfx = SoundBank()
        self.sfx.set_volume(self.profile.volume)
        self.combo = ComboTracker()
        self.icon_manager = IconManager(
            self.physics,
            self.screen.get_size(),
            dpi=self.window.dpi,
        )
        self.slashes = SlashDetector()
        self.background = Background(
            self.screen.get_size(),
            enabled=not self.is_overlay,
        )
        self.hud = HUD()

        self.score = 0
        self.lives = config.STARTING_LIVES
        self.slice_count = 0
        self.best_combo = 0
        self.new_high_score = False
        self.round_result = ""
        self.icon_source_count = 0
        self.icon_source_label = "fallback"
        self.icon_read_errors = 0
        self.icon_error = ""
        self.desktop_read_count = 0
        self.icon_source_size = self._requested_source_size()
        self._load_icon_sources()

        self.states = StateManager(self)
        self.states.change(GamePhase.MENU)
        self.focus = FocusManager(
            on_focus_lost=self._on_focus_lost,
            on_background=self._on_background,
            on_foreground=self._on_foreground,
            foreground_probe=self.window.foreground_is_self,
            activation_probe=self.window.native_activation,
            paused_probe=lambda: self.states.phase is GamePhase.PAUSED,
        )
        self._accumulator = 0.0
        self._last_input_time = pygame.time.get_ticks() / 1000.0
        self._paused_at = 0.0
        self._resume_key_armed = False
        self._pause_key_echo_until = 0.0

        self._shutdown = False
        self._shutdown_done = threading.Event()
        self._shutdown_deadline = 0.0
        self.shutdown_phase = ShutdownPhase.RUNNING
        self.shutdown_reason = ""
        self.shutdown_errors: list[str] = []
        self._emergency_event = threading.Event()
        self._emergency_thread: threading.Thread | None = None

        self.window.acquire_input()
        self._hide_desktop_if_needed(hide_desktop)
        if IS_WINDOWS:
            self._start_emergency_watcher()

    def run(self) -> None:
        log("LOOP", "main loop start")
        self._last_heartbeat = 0.0
        try:
            while self.running:
                if self._emergency_event.is_set():
                    self.request_shutdown("emergency_hotkey")
                    break
                # The loop never blocks on focus: in the background it still
                # pumps SDL/Win32 messages and exit events, just slower.
                frame_time = self.clock.tick(self.focus.render_fps) / 1000.0
                self.frame_stats.record(frame_time)
                self._handle_events()
                if not self.running:
                    break

                if self.focus.simulates:
                    self.advance(frame_time)
                self._render()
                pygame.display.flip()
                self._log_heartbeat()
        except BaseException:
            log_exception("LOOP", "main loop raised")
            self.request_shutdown("loop_exception")
            raise
        finally:
            log("LOOP", "main loop stop")
            self.shutdown()

    def _log_heartbeat(self) -> None:
        now = time.monotonic()
        if now - self._last_heartbeat < config.LOG_HEARTBEAT_SECONDS:
            return
        self._last_heartbeat = now
        fps = getattr(self.frame_stats, "average_fps", 0.0)
        log(
            "LOOP",
            f"alive fps={fps:.1f} phase={self.states.phase} "
            f"focus={self.focus.state.value} input={self.window.input_mode}",
        )

    # ------------------------------------------------------------------
    # Unified shutdown
    # ------------------------------------------------------------------
    def request_shutdown(self, reason: str = "quit") -> None:
        """The only exit entry point. Safe to call from any exit route."""
        if self._shutdown or self.shutdown_phase is ShutdownPhase.STOPPED:
            return
        if reason and not self.shutdown_reason:
            self.shutdown_reason = reason
        log("SHUTDOWN", f"requested reason={reason}")
        if self.shutdown_phase is ShutdownPhase.RUNNING:
            self.shutdown_phase = ShutdownPhase.SHUTTING_DOWN
        self.focus.begin_shutdown()
        self.running = False
        try:
            self.window.release_input()
        except Exception:
            pass

    def shutdown(self) -> None:
        """Clean up in priority order; one failure must not skip the rest."""
        if self._shutdown:
            return
        self._shutdown = True
        self.running = False
        self.shutdown_phase = ShutdownPhase.SHUTTING_DOWN
        self.focus.begin_shutdown()
        log("SHUTDOWN", "begin")
        self._shutdown_deadline = time.monotonic() + config.SHUTDOWN_BUDGET_SECONDS
        try:
            # Attribute lookup happens inside the step too: a partially
            # initialised or replaced manager must not abort the pipeline.
            self._run_step("release input", lambda: self.window.release_input())

            self.shutdown_phase = ShutdownPhase.RESTORING_DESKTOP
            log("SHUTDOWN", "restore desktop")
            restored = self._run_step(
                "restore desktop icons",
                lambda: self.desktop_background.restore_icons(),
            )
            if restored is False:
                self.shutdown_errors.append(
                    "desktop icons still hidden; watchdog and marker retained"
                )
            if restored is not False:
                self.desktop_hidden = False

            self.shutdown_phase = ShutdownPhase.DESTROYING_WINDOWS
            log("SHUTDOWN", "destroy windows")
            self._run_step("close window", lambda: self.window.close())

            self.shutdown_phase = ShutdownPhase.RELEASING_RESOURCES
            log("SHUTDOWN", "release resources")
            self._run_step("stop audio", lambda: self.sfx.stop_all())
            self._run_step("release system input", release_system_input)
            self._run_step("clear font cache", clear_font_cache)
            self._run_step("clear text cache", clear_text_cache)
            self._run_step("quit pygame", pygame.quit)
        finally:
            for error in self.shutdown_errors:
                log("SHUTDOWN", f"error: {error}")
            log(
                "SHUTDOWN",
                f"complete reason={self.shutdown_reason or 'unknown'} "
                f"errors={len(self.shutdown_errors)}",
            )
            self.shutdown_phase = ShutdownPhase.STOPPED
            self._shutdown_done.set()

    def _run_step(self, name: str, step) -> object:
        if time.monotonic() > self._shutdown_deadline:
            self.shutdown_errors.append(f"{name}: skipped (shutdown budget exhausted)")
            return None
        try:
            return step()
        except Exception as exc:
            self.shutdown_errors.append(f"{name}: {exc!r}")
            return None

    def _start_emergency_watcher(self) -> None:
        """Ctrl+Shift+Q is read on a daemon thread, independent of messages."""
        if self._emergency_thread is not None:
            return
        thread = threading.Thread(
            target=self._emergency_watch,
            name="desktop-slash-emergency",
            daemon=True,
        )
        self._emergency_thread = thread
        thread.start()

    def _emergency_watch(self) -> None:
        was_down = False
        while not self._shutdown_done.is_set():
            down = self.window.poll_emergency_exit()
            if down and not was_down:
                self.shutdown_reason = self.shutdown_reason or "emergency_hotkey"
                self._emergency_event.set()
                self.running = False
                if self._shutdown_done.wait(config.EMERGENCY_HOTKEY_GRACE):
                    return
                # The main loop is wedged. Restore the desktop with ctypes
                # only, then terminate: nothing is force-killed beforehand.
                try:
                    DesktopBackgroundManager.emergency_restore()
                except Exception:
                    pass
                try:
                    release_system_input()
                except Exception:
                    pass
                os._exit(0)
            was_down = down
            if self._shutdown_done.wait(config.EMERGENCY_HOTKEY_POLL):
                return

    def _hide_desktop_if_needed(self, requested: bool | None) -> None:
        """Hide the real icon list only for the validated overlay session."""
        enabled = config.DESKTOP_HIDE_ICONS if requested is None else requested
        if not enabled or not self.is_overlay:
            return
        try:
            backup = self.desktop_background.hide_icons()
        except DesktopBackgroundError as exc:
            self.desktop_hide_error = str(exc)
            return
        self.desktop_hidden = bool(backup.applied)

    # ------------------------------------------------------------------
    # Focus transitions (called once per transition by FocusManager)
    # ------------------------------------------------------------------
    def _on_focus_lost(self) -> None:
        """Activation left the game: stop the stroke and pause immediately."""
        if self.states.phase is GamePhase.PLAYING:
            self.pause_round(silent=True)
        self._resume_key_armed = False
        self.slashes.reset()
        self._accumulator = 0.0
        try:
            self.window.release_input()
        except Exception:
            log_exception("INPUT", "release input on focus loss failed")

    def _on_background(self) -> None:
        if self.states.phase is GamePhase.PLAYING:
            self.pause_round(silent=True)
        self._accumulator = 0.0
        try:
            self.window.enter_background()
        except Exception:
            log_exception("WINDOW", "entering background failed")
        self._drop_queued_pointer_events()

    def _on_foreground(self) -> bool:
        take_input = self.states.phase is not GamePhase.PAUSED
        try:
            restored = self.window.enter_foreground(take_input=take_input)
        except Exception:
            log_exception("WINDOW", "foreground restore failed")
            restored = False
        self._accumulator = 0.0
        # A resume key held while another app was in front must not resume the
        # round the moment the game comes back; require a fresh press.
        self._resume_key_armed = False
        if not restored:
            return False
        self.slashes.reset()
        self._last_input_time = pygame.time.get_ticks() / 1000.0
        self._drop_queued_pointer_events()
        return True

    @staticmethod
    def _drop_queued_pointer_events() -> None:
        """A click made in the other app must not slice on return."""
        for kind in (
            pygame.MOUSEBUTTONDOWN,
            pygame.MOUSEBUTTONUP,
            pygame.MOUSEMOTION,
        ):
            try:
                pygame.event.clear(kind)
            except pygame.error:
                return

    # ------------------------------------------------------------------
    # Round flow used by the states
    # ------------------------------------------------------------------
    def start_round(self) -> None:
        self.score = 0
        self.lives = config.STARTING_LIVES
        self.slice_count = 0
        self.best_combo = 0
        self.new_high_score = False
        self.round_result = ""
        self.combo.reset()
        self.icon_manager.begin_round()
        self.slashes.reset()
        self.physics.clear()
        self.effects.clear()
        self.particles.clear()
        self.screen_fx.clear()
        self.sfx.stop_all()
        self.window.acquire_input()
        self.states.change(GamePhase.COUNTDOWN)

    def begin_play(self) -> None:
        self.icon_manager.begin_round()
        self.slashes.reset()
        self.window.acquire_input()
        self.states.change(GamePhase.PLAYING)

    def finish_round(self, reason: str) -> None:
        if self.states.phase == GamePhase.GAME_OVER:
            return
        self.round_result = reason
        self.best_combo = max(self.best_combo, self.combo.best)
        if self.score > self.profile.high_score:
            self.profile.high_score = self.score
            self.new_high_score = True
            self.save_profile()
        self.icon_manager.clear()
        self.slashes.reset()
        self.window.acquire_input()
        self.states.change(GamePhase.GAME_OVER)

    def pause_round(self, *, silent: bool = False) -> None:
        if self.states.phase != GamePhase.PLAYING:
            return
        self.states.change(GamePhase.PAUSED)
        if config.PAUSE_INPUT_RELEASE:
            self.window.release_input()
        self.slashes.reset()
        if not silent:
            self.sfx.play("click", 0.6)
        self._paused_at = pygame.time.get_ticks() / 1000.0
        self._resume_key_armed = False

    def resume_round(self) -> None:
        if self.states.phase != GamePhase.PAUSED:
            return
        self.window.acquire_input()
        self.states.change(GamePhase.PLAYING, resume=True)
        self.slashes.reset()
        self._last_input_time = pygame.time.get_ticks() / 1000.0
        pygame.event.clear(pygame.MOUSEMOTION)
        self.sfx.play("click", 0.8)

    def go_to_menu(self) -> None:
        self.icon_manager.clear()
        self.slashes.reset()
        self.physics.clear()
        self.effects.clear()
        self.particles.clear()
        self.screen_fx.clear()
        self.combo.reset()
        self.sfx.stop_all()
        self.window.acquire_input()
        self.states.change(GamePhase.MENU)

    def quit(self) -> None:
        self.request_shutdown("quit")

    # ------------------------------------------------------------------
    # Saved profile
    # ------------------------------------------------------------------
    @property
    def high_score(self) -> int:
        return self.profile.high_score

    def save_profile(self) -> bool:
        return self.profile_store.save(self.profile)

    def set_language(self, code: str) -> bool:
        applied = apply_language(code)
        self.profile.language = current_language()
        self.save_profile()
        clear_text_cache()
        self.hud.refresh_language()
        self.states.refresh_language()
        return applied

    def adjust_volume(self, delta: float) -> None:
        self.profile.volume = round(
            max(0.0, min(1.0, self.profile.volume + delta)),
            2,
        )
        self.sfx.set_volume(self.profile.volume)
        self.save_profile()

    def toggle_shake(self) -> None:
        self.profile.shake_enabled = not self.profile.shake_enabled
        self.screen_fx.shake_enabled = self.profile.shake_enabled
        if not self.screen_fx.shake_enabled:
            self.screen_fx.cancel_shake()
        self.save_profile()

    def toggle_scanlines(self) -> None:
        self.profile.scanlines_enabled = not self.profile.scanlines_enabled
        self.screen_fx.scanlines_enabled = (
            self.profile.scanlines_enabled and not self.is_overlay
        )
        self.save_profile()

    # ------------------------------------------------------------------
    # Fixed-timestep advance
    # ------------------------------------------------------------------
    def advance(self, frame_time: float) -> int:
        """Feed one rendered frame to the accumulator and return the steps run."""
        max_steps = max(1, int(config.MAX_FRAME_TIME / config.FIXED_DT))
        self._accumulator += min(max(0.0, frame_time), config.MAX_FRAME_TIME)

        steps = 0
        while self._accumulator >= config.FIXED_DT and steps < max_steps:
            self._update(config.FIXED_DT)
            self._accumulator -= config.FIXED_DT
            steps += 1
        if steps >= max_steps:
            self._accumulator = 0.0
        return steps

    # ------------------------------------------------------------------
    # Loop internals
    # ------------------------------------------------------------------
    def _handle_events(self) -> None:
        if self._emergency_event.is_set():
            self.request_shutdown("emergency_hotkey")
            return
        if self.window.close_requested():
            self.window.clear_close_request()
            self.request_shutdown("wm_close")
            return

        events = pygame.event.get()
        if events:
            now = pygame.time.get_ticks() / 1000.0
            span = now - self._last_input_time
            if span <= 0.0 or span > config.MAX_FRAME_TIME:
                span = config.FIXED_DT
            self._last_input_time = now

            count = len(events)
            for index, event in enumerate(events):
                event.input_time = now - span * (count - 1 - index) / count
                if event.type == pygame.QUIT:
                    self.request_shutdown("window_close")
                    return
                if _FOCUS_LOST is not None and event.type == _FOCUS_LOST:
                    log("FOCUS", "pygame WINDOWFOCUSLOST")
                    self.focus.notify(False)
                    self.focus.update()
                    continue
                if _FOCUS_GAINED is not None and event.type == _FOCUS_GAINED:
                    log("FOCUS", "pygame WINDOWFOCUSGAINED")
                    self.focus.notify(True)
                    self.focus.update()
                    continue
                if not self.focus.accepts_input:
                    continue
                if (
                    event.type == pygame.KEYDOWN
                    and event.key in (pygame.K_ESCAPE, pygame.K_p)
                    and now < self._pause_key_echo_until
                ):
                    log("INPUT", "ignored duplicate pause-key delivery")
                    self._pause_key_echo_until = 0.0
                    continue
                self.states.handle_event(event)

        # Backstop for SDL focus events that never arrive; cheap (0.2 s poll).
        self.focus.update()
        if self.states.phase == GamePhase.PAUSED and self.focus.accepts_input:
            self._poll_resume_key()

    def _poll_resume_key(self) -> None:
        """Global Esc poll: never resumes the game over another application."""
        if not self.window.foreground_is_self():
            return
        down = self.window.poll_escape()
        if not down:
            self._resume_key_armed = True
            return
        now = pygame.time.get_ticks() / 1000.0
        elapsed = now - self._paused_at
        if self._resume_key_armed and elapsed >= config.PAUSE_RESUME_GUARD:
            log("INPUT", f"global Esc resumed the round elapsed={elapsed:.2f}s")
            # SDL may still hand the same press to the queue a frame later;
            # swallow that echo so the round is not paused again at once.
            self._pause_key_echo_until = now + config.PAUSE_KEY_ECHO_GUARD
            self.resume_round()

    def _update(self, dt: float) -> None:
        self.states.update(dt)
        if self.states.phase == GamePhase.PAUSED:
            return
        self.physics.update(dt)
        self.states.post_update(dt)
        self.effects.update(dt)
        self.particles.update(dt)
        self.background.update(dt)
        self.screen_fx.update(dt)

    def _render(self) -> None:
        if self.wallpaper_backdrop is not None:
            self.scene.blit(self.wallpaper_backdrop, (0, 0))
        elif self.is_overlay:
            self.scene.fill(config.WINDOW_TRANSPARENT_COLOR_KEY)
        self.states.render(self.scene)
        self.screen_fx.present(self.scene, self.screen)

    # ------------------------------------------------------------------
    # Desktop icons
    # ------------------------------------------------------------------
    def _build_wallpaper_backdrop(self) -> pygame.Surface | None:
        if not self.is_overlay or not config.OVERLAY_WALLPAPER_BACKDROP:
            return None
        window_rect = self.window.window_rect
        monitor_rect = self.window.monitor_rect
        if not window_rect or not monitor_rect:
            return None
        device = self.window.monitor_info.device if self.window.monitor_info else ""
        try:
            return build_desktop_backdrop(window_rect, monitor_rect, device)
        except Exception as exc:
            self.wallpaper_error = str(exc)
            return None

    def _requested_source_size(self) -> int:
        """Shell bitmap size that keeps the largest on-screen icon crisp."""
        largest = self.icon_manager.icon_max_size
        if largest <= config.ICON_SOURCE_SIZE:
            return config.ICON_SOURCE_SIZE
        return min(512, round(largest * 1.5))

    def _load_icon_sources(self) -> None:
        """Read the desktop exactly once per session, never per frame."""
        surfaces: list[pygame.Surface] = []
        self.desktop_read_count += 1
        try:
            result = self.desktop.read_desktop_icons(self.icon_source_size)
        except DesktopReadError as exc:
            self.icon_error = str(exc)
        else:
            self.icon_read_errors = len(result.errors)
            surfaces = [
                icon.image
                for icon in result.icons
                if icon.image.get_width() >= 2 and icon.image.get_height() >= 2
            ]
            if surfaces:
                self.icon_source_label = "desktop"

        if not surfaces:
            if not self.icon_error:
                self.icon_error = "The desktop returned no usable icons."
            surfaces = build_fallback_icons()
            self.icon_source_label = "fallback"

        self.icon_source_count = len(surfaces)
        self.icon_manager.set_sources(surfaces)
