from __future__ import annotations

import pygame

from physics.body import PhysicsBody


class PhysicsWorld:
    """Owns every simulated body; advanced once per fixed update step."""

    def __init__(self) -> None:
        self._bodies: list[PhysicsBody] = []

    @property
    def bodies(self) -> list[PhysicsBody]:
        return self._bodies

    def add(self, body: PhysicsBody) -> PhysicsBody:
        self._bodies.append(body)
        return body

    def clear(self) -> None:
        self._bodies.clear()

    def update(self, dt: float) -> None:
        for body in self._bodies:
            body.integrate(dt)
        kept = 0
        for body in self._bodies:
            if body.alive:
                self._bodies[kept] = body
                kept += 1
        if kept < len(self._bodies):
            del self._bodies[kept:]

    def __len__(self) -> int:
        return len(self._bodies)
