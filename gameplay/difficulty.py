from __future__ import annotations

from dataclasses import dataclass

import game_config as config


@dataclass(frozen=True)
class Difficulty:
    """Snapshot of the single difficulty curve at one point in the round."""

    wave_bonus: int
    speed_multiplier: float
    spawn_interval: float
    bomb_chance: float


def difficulty_at(
    elapsed: float,
    round_seconds: float = config.ROUND_SECONDS,
) -> Difficulty:
    """Return the ramp state for a round that has been running for ``elapsed``.

    One smooth curve drives every value, so late waves spawn more icons,
    faster, with a higher chance of bombs. No mode configuration involved.
    """
    span = max(0.001, round_seconds)
    progress = max(0.0, min(1.0, elapsed / span))
    curve = progress ** config.DIFFICULTY_CURVE_POWER

    wave_bonus = int(round(config.DIFFICULTY_WAVE_BONUS_MAX * curve))
    speed_multiplier = 1.0 + (config.DIFFICULTY_SPEED_MAX_MULT - 1.0) * curve
    spawn_interval = max(
        config.DIFFICULTY_SPAWN_INTERVAL_MIN,
        config.ICON_SPAWN_INTERVAL - config.DIFFICULTY_SPAWN_INTERVAL_SCALE * curve,
    )
    bomb_chance = min(
        config.DIFFICULTY_BOMB_CHANCE_MAX,
        config.BOMB_SPAWN_CHANCE
        + (config.DIFFICULTY_BOMB_CHANCE_MAX - config.BOMB_SPAWN_CHANCE) * curve,
    )
    return Difficulty(
        wave_bonus=wave_bonus,
        speed_multiplier=speed_multiplier,
        spawn_interval=spawn_interval,
        bomb_chance=bomb_chance,
    )
