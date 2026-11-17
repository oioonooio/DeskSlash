from __future__ import annotations

import game_config as config
from localization import t


class ComboTracker:
    """Consecutive-slice counter with a forgiving timeout window."""

    def __init__(self, window: float = config.COMBO_WINDOW) -> None:
        self._window = max(0.1, window)
        self._count = 0
        self._best = 0
        self._timer = 0.0

    # ------------------------------------------------------------------
    # State
    # ------------------------------------------------------------------
    @property
    def count(self) -> int:
        return self._count

    @property
    def best(self) -> int:
        return self._best

    @property
    def timer(self) -> float:
        return self._timer

    @property
    def high(self) -> bool:
        return self._count >= config.COMBO_HIGH_THRESHOLD

    @property
    def fill(self) -> float:
        return max(0.0, min(1.0, self._timer / self._window))

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------
    def register(self) -> int:
        if self._timer > 0.0:
            self._count += 1
        else:
            self._count = 1
        self._timer = self._window
        self._best = max(self._best, self._count)
        return self._count

    def update(self, dt: float) -> None:
        if self._timer <= 0.0:
            return
        self._timer = max(0.0, self._timer - dt)
        if self._timer <= 0.0:
            self._count = 0

    def break_combo(self) -> None:
        self._count = 0
        self._timer = 0.0

    def reset(self) -> None:
        self._count = 0
        self._best = 0
        self._timer = 0.0


def combo_reward(count: int) -> tuple[str, str, tuple[int, int, int]] | None:
    """Return ``(callout, subtext, color)`` for a milestone, else ``None``."""
    if count == 2:
        return t("combo.x2"), "", config.COMBO_X2_COLOR
    if count == 3:
        return t("combo.x3"), "", config.COMBO_X3_COLOR
    if count == 5:
        return t("combo.x5"), "", config.COMBO_X5_COLOR
    if count >= config.COMBO_GREAT_THRESHOLD and (
        count - config.COMBO_GREAT_THRESHOLD
    ) % config.COMBO_GREAT_STEP == 0:
        return t("combo.great"), f"x{count}", config.COMBO_GREAT_COLOR
    return None


def combo_multiplier(count: int) -> int:
    """Score multiplier earned by the current combo streak."""
    streak = max(1, count)
    tier = 1 + (streak - 1) // config.COMBO_MULTIPLIER_STEP
    return min(config.COMBO_MULTIPLIER_MAX, tier)


def combo_color(count: int) -> tuple[int, int, int]:
    if count >= config.COMBO_GREAT_THRESHOLD:
        return config.COMBO_GREAT_COLOR
    if count >= config.COMBO_HIGH_THRESHOLD:
        return config.COMBO_X5_COLOR
    if count >= 3:
        return config.COMBO_X3_COLOR
    if count >= 2:
        return config.COMBO_X2_COLOR
    return config.SCORE_POPUP_COLOR
