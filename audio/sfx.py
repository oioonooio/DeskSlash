from __future__ import annotations

import math
import random
from array import array

import pygame

import game_config as config


class SoundBank:
    """Tiny synthesised arcade sounds with a no-op fallback.

    No audio assets are required: the waveforms are generated from square,
    sine and noise sources when the mixer starts. If audio is unavailable the
    bank simply disables itself, so tests and headless runs keep working.
    """

    def __init__(self, enabled: bool = config.AUDIO_ENABLED) -> None:
        self.enabled = False
        self.volume = max(0.0, min(1.0, float(config.DEFAULT_VOLUME)))
        self._sounds: dict[str, pygame.mixer.Sound] = {}
        if not enabled:
            return
        try:
            if pygame.mixer.get_init() is None:
                pygame.mixer.init(
                    frequency=config.AUDIO_SAMPLE_RATE,
                    size=-16,
                    channels=2,
                    buffer=512,
                )
            pygame.mixer.set_num_channels(16)
            self._sounds = {
                "slice": _make_tone(880, 320, 0.10, 0.30, noise=0.30),
                "combo": _make_tone(520, 1320, 0.16, 0.34, noise=0.05),
                "bomb": _make_boom(0.46, 0.55),
                "miss": _make_tone(340, 90, 0.22, 0.28, noise=0.08),
                "click": _make_tone(720, 420, 0.05, 0.22, noise=0.0),
                "count": _make_tone(620, 640, 0.09, 0.28),
                "go": _make_tone(480, 1180, 0.24, 0.36),
            }
            self.enabled = bool(self._sounds)
        except (pygame.error, ValueError):
            self.enabled = False
            self._sounds = {}

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, float(volume)))

    def play(self, name: str, volume: float = 1.0) -> bool:
        if not self.enabled:
            return False
        sound = self._sounds.get(name)
        if sound is None:
            return False
        channel = sound.play()
        if channel is not None:
            channel.set_volume(self.volume * max(0.0, volume))
        return True

    def stop_all(self) -> None:
        if self.enabled:
            pygame.mixer.stop()


def _make_tone(
    start_hz: float,
    end_hz: float,
    duration: float,
    volume: float,
    noise: float = 0.0,
    seed: int = 7,
) -> pygame.mixer.Sound:
    rate, channels = _mixer_format()
    frames = max(1, int(rate * duration))
    rng = random.Random(seed)
    samples = array("h")
    phase = 0.0
    for index in range(frames):
        t = index / frames
        frequency = start_hz + (end_hz - start_hz) * t
        phase += math.tau * frequency / rate
        envelope = (1.0 - t) ** 1.6
        square = 1.0 if math.sin(phase) >= 0.0 else -1.0
        value = square * (1.0 - noise) + (rng.random() * 2.0 - 1.0) * noise
        sample = int(max(-1.0, min(1.0, value * envelope * volume)) * 32767)
        for _ in range(channels):
            samples.append(sample)
    return pygame.mixer.Sound(buffer=samples.tobytes())


def _make_boom(duration: float, volume: float) -> pygame.mixer.Sound:
    rate, channels = _mixer_format()
    frames = max(1, int(rate * duration))
    rng = random.Random(19)
    samples = array("h")
    phase = 0.0
    for index in range(frames):
        t = index / frames
        frequency = 110.0 * (1.0 - t) ** 2 + 28.0
        phase += math.tau * frequency / rate
        envelope = (1.0 - t) ** 1.2
        rumble = math.sin(phase) * 0.75
        noise = (rng.random() * 2.0 - 1.0) * 0.55
        value = (rumble + noise) * envelope * volume
        sample = int(max(-1.0, min(1.0, value)) * 32767)
        for _ in range(channels):
            samples.append(sample)
    return pygame.mixer.Sound(buffer=samples.tobytes())


def _mixer_format() -> tuple[int, int]:
    info = pygame.mixer.get_init()
    if not info:
        return config.AUDIO_SAMPLE_RATE, 2
    rate, _size, channels = info
    return rate, channels
