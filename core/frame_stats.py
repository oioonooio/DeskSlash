from __future__ import annotations

from collections import deque

import game_config as config


class FrameStats:
    """Small rolling frame-time window used by diagnostics and tests."""

    def __init__(self, window: int | None = None) -> None:
        self._samples: deque[float] = deque(
            maxlen=window or config.PERF_SAMPLE_FRAMES
        )
        self.frames = 0
        self.peak_ms = 0.0

    def record(self, seconds: float) -> None:
        value = max(0.0, float(seconds))
        self._samples.append(value)
        self.frames += 1
        self.peak_ms = max(self.peak_ms, value * 1000.0)

    @property
    def average_ms(self) -> float:
        if not self._samples:
            return 0.0
        return sum(self._samples) / len(self._samples) * 1000.0

    @property
    def average_fps(self) -> float:
        if not self._samples:
            return 0.0
        total = sum(self._samples)
        if total <= 0.0:
            return 0.0
        return len(self._samples) / total

    def reset(self) -> None:
        self._samples.clear()
        self.frames = 0
        self.peak_ms = 0.0
