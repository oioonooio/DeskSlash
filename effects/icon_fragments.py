from __future__ import annotations

import random
from dataclasses import dataclass

import pygame

import game_config as config


@dataclass
class _Fragment:
    image: pygame.Surface
    position: pygame.Vector2
    velocity: pygame.Vector2
    angle: float
    spin: float
    age: float = 0.0


class IconFragments:
    """Two halves of the sliced icon flying apart and fading out."""

    def __init__(
        self,
        image: pygame.Surface,
        position: tuple[float, float] | pygame.Vector2,
        base_velocity: tuple[float, float] | pygame.Vector2,
        rng: random.Random | None = None,
    ) -> None:
        rng = rng or random.Random()
        origin = pygame.Vector2(position)
        drift = pygame.Vector2(base_velocity) * 0.25

        width, height = image.get_size()
        split = max(1, width // 2)
        left = image.subsurface((0, 0, split, height)).copy()
        right = image.subsurface((split, 0, width - split, height)).copy()

        lift = pygame.Vector2(0.0, -config.FRAGMENT_LIFT_SPEED)
        spin = rng.uniform(0.4, 1.0) * config.FRAGMENT_SPIN_MAX

        self._fragments = [
            _Fragment(
                image=left,
                position=origin + pygame.Vector2(-width * 0.25, 0.0),
                velocity=drift
                + lift
                + pygame.Vector2(-config.FRAGMENT_SPLIT_SPEED, 0.0),
                angle=0.0,
                spin=-spin,
            ),
            _Fragment(
                image=right,
                position=origin + pygame.Vector2(width * 0.25, 0.0),
                velocity=drift
                + lift
                + pygame.Vector2(config.FRAGMENT_SPLIT_SPEED, 0.0),
                angle=0.0,
                spin=spin,
            ),
        ]
        self.finished = False

    def update(self, dt: float) -> None:
        done = True
        for fragment in self._fragments:
            fragment.age += dt
            if fragment.age >= config.FRAGMENT_LIFETIME:
                continue
            done = False
            fragment.velocity.y += config.FRAGMENT_GRAVITY * dt
            fragment.position += fragment.velocity * dt
            fragment.angle = (fragment.angle + fragment.spin * dt) % 360.0
        self.finished = done

    def draw(self, surface: pygame.Surface) -> None:
        for fragment in self._fragments:
            if fragment.age >= config.FRAGMENT_LIFETIME:
                continue
            fade = _fade_alpha(fragment.age)
            if fade <= 0.0:
                continue
            image = pygame.transform.rotozoom(fragment.image, fragment.angle, 1.0)
            image.set_alpha(max(0, min(255, round(255 * fade))))
            rect = image.get_rect(
                center=(round(fragment.position.x), round(fragment.position.y))
            )
            surface.blit(image, rect)


def _fade_alpha(age: float) -> float:
    if age <= config.FRAGMENT_FADE_START:
        return 1.0
    fading = config.FRAGMENT_LIFETIME - config.FRAGMENT_FADE_START
    if fading <= 0.0:
        return 0.0
    return max(0.0, 1.0 - (age - config.FRAGMENT_FADE_START) / fading)
