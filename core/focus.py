from __future__ import annotations

import time
from enum import Enum
from typing import Callable

import game_config as config
from core.diagnostics import log, log_exception


class FocusState(Enum):
    FOREGROUND = "foreground"
    FOCUS_LOST = "focus_lost"
    PAUSED = "paused"
    BACKGROUND = "background"
    RESTORING = "restoring"
    SHUTTING_DOWN = "shutting_down"


# States in which the window is the game's: gameplay may simulate and events
# are dispatched. PAUSED is foreground too; the game itself froze the round.
_FOCUSED = frozenset({FocusState.FOREGROUND, FocusState.PAUSED})


class FocusManager:
    """One debounced foreground/background state machine.

    Three signals feed it:

    * Pygame ``WINDOWFOCUSLOST``/``WINDOWFOCUSGAINED`` events, pushed in with
      :meth:`notify` as soon as the loop dequeues them;
    * the overlay's ``WM_ACTIVATE``/``WM_ACTIVATEAPP``/``WM_SETFOCUS`` hints,
      read through ``activation_probe`` without doing work in the Win32
      window procedure;
    * a ``GetForegroundWindow`` poll every ``FOCUS_POLL_SECONDS``.

    SDL can drop focus events (hidden, click-through or non-activating
    windows), so no single source is trusted on its own: the poll is the
    ground truth and the events only shorten the reaction time. Every
    transition runs on the main thread inside :meth:`update`, and callbacks
    fire exactly once per transition -- never per frame.
    """

    def __init__(
        self,
        *,
        on_focus_lost: Callable[[], None] | None = None,
        on_background: Callable[[], None] | None = None,
        on_foreground: Callable[[], None] | None = None,
        foreground_probe: Callable[[], bool] | None = None,
        activation_probe: Callable[[], tuple[int, bool]] | None = None,
        paused_probe: Callable[[], bool] | None = None,
        clock: Callable[[], float] | None = None,
    ) -> None:
        self._on_focus_lost = on_focus_lost or (lambda: None)
        self._on_background = on_background or (lambda: None)
        self._on_foreground = on_foreground or (lambda: None)
        self._foreground_probe = foreground_probe or (lambda: True)
        self._activation_probe = activation_probe or (lambda: (0, True))
        self._paused_probe = paused_probe or (lambda: False)
        self._clock = clock or time.monotonic

        self._state = FocusState.FOREGROUND
        self._since = self._clock()
        self._pygame_hint: bool | None = None
        self._native_seq = -1
        self._native_active = True
        self._last_poll = float("-inf")
        self._polled_foreground = True
        self.transitions = 0

    # ------------------------------------------------------------------
    # Read-only view
    # ------------------------------------------------------------------
    @property
    def state(self) -> FocusState:
        return self._state

    @property
    def is_background(self) -> bool:
        return self._state is FocusState.BACKGROUND

    @property
    def shutting_down(self) -> bool:
        return self._state is FocusState.SHUTTING_DOWN

    @property
    def accepts_input(self) -> bool:
        """True while key/mouse events may reach the active game state."""
        return self._state in _FOCUSED or self._state is FocusState.RESTORING

    @property
    def simulates(self) -> bool:
        """False in the background: time, physics and menus stay frozen."""
        return self._state not in (FocusState.BACKGROUND, FocusState.SHUTTING_DOWN)

    @property
    def render_fps(self) -> int:
        return (
            config.BACKGROUND_FPS
            if self._state is FocusState.BACKGROUND
            else config.FPS
        )

    # ------------------------------------------------------------------
    # Inputs
    # ------------------------------------------------------------------
    def notify(self, focused: bool) -> None:
        """Queue a Pygame focus hint; consumed by the next :meth:`update`."""
        self._pygame_hint = bool(focused)

    def update(self) -> None:
        """Advance the state machine once per frame (main thread only)."""
        if self._state is FocusState.SHUTTING_DOWN:
            return
        now = self._clock()
        focused, source = self._resolve(now)
        self._step(focused, source, now)

    def begin_shutdown(self) -> None:
        if self._state is FocusState.SHUTTING_DOWN:
            return
        self._state = FocusState.SHUTTING_DOWN
        self._pygame_hint = None

    # ------------------------------------------------------------------
    # Resolution
    # ------------------------------------------------------------------
    def _resolve(self, now: float) -> tuple[bool, str]:
        focused = self._polled_foreground
        source = "poll"

        try:
            seq, active = self._activation_probe()
        except Exception:
            log_exception("FOCUS", "activation probe failed")
            seq, active = self._native_seq, True

        if seq != self._native_seq:
            self._native_seq = seq
            self._native_active = bool(active)
            polled = self._poll(now)
            if self._native_active:
                focused = polled
            else:
                # Latch "lost" until the next scheduled poll re-reads the
                # real foreground; a stale "true" poll must not bounce the
                # state straight back while the activation is moving away.
                focused = False
                self._polled_foreground = False
            source = "native"
        elif now - self._last_poll >= config.FOCUS_POLL_SECONDS:
            focused = self._poll(now)
            source = "poll"

        hint = self._pygame_hint
        if hint is not None:
            self._pygame_hint = None
            if hint:
                focused = self._poll(now)
            else:
                focused = False
                self._polled_foreground = False
                self._last_poll = now
            source = "pygame"
        return focused, source

    def _poll(self, now: float) -> bool:
        self._last_poll = now
        try:
            self._polled_foreground = bool(self._foreground_probe())
        except Exception:
            log_exception("FOCUS", "foreground probe failed")
            self._polled_foreground = True
        return self._polled_foreground

    # ------------------------------------------------------------------
    # Transitions
    # ------------------------------------------------------------------
    def _step(self, focused: bool, source: str, now: float) -> None:
        state = self._state
        if state in _FOCUSED:
            if not focused:
                self._enter(FocusState.FOCUS_LOST, source, now)
                self._emit("focus_lost", self._on_focus_lost)
            else:
                target = self._focused_state()
                if target is not state:
                    self._state = target
            return

        if state is FocusState.FOCUS_LOST:
            if focused:
                self._enter(self._focused_state(), source, now)
                if self._emit("foreground", self._on_foreground) is False:
                    self._enter(FocusState.BACKGROUND, "restore_failed", now)
                    self._emit("background", self._on_background)
            elif now - self._since >= config.FOCUS_LOST_DELAY:
                self._enter(FocusState.BACKGROUND, "debounce", now)
                self._emit("background", self._on_background)
            return

        if state is FocusState.BACKGROUND:
            if focused:
                self._enter(FocusState.RESTORING, source, now)
                if self._emit("foreground", self._on_foreground) is False:
                    self._enter(FocusState.BACKGROUND, "restore_failed", now)
                    self._emit("background", self._on_background)
            return

        if state is FocusState.RESTORING:
            if not focused:
                self._enter(FocusState.BACKGROUND, source, now)
                self._emit("background", self._on_background)
            elif now - self._since >= config.FOCUS_GAIN_DELAY:
                self._enter(self._focused_state(), "settled", now)

    def _focused_state(self) -> FocusState:
        try:
            paused = bool(self._paused_probe())
        except Exception:
            paused = False
        return FocusState.PAUSED if paused else FocusState.FOREGROUND

    def _enter(self, state: FocusState, source: str, now: float) -> None:
        previous = self._state
        if previous is state:
            return
        self._state = state
        self._since = now
        self.transitions += 1
        log("FOCUS", f"state {previous.value} -> {state.value} source={source}")

    @staticmethod
    def _emit(name: str, callback: Callable[[], object]) -> object:
        # A failing callback must not wedge the state machine: the state has
        # already moved on, so the next poll can still recover.
        try:
            return callback()
        except Exception:
            log_exception("FOCUS", f"{name} handler failed")
            return None
