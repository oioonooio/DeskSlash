from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import pygame

import game_config as config

if TYPE_CHECKING:
    from gameplay.game_icon import GameIcon


@dataclass(frozen=True)
class SlashSegment:
    start: pygame.Vector2
    end: pygame.Vector2


@dataclass(frozen=True)
class SlashHit:
    icon: "GameIcon"
    point: pygame.Vector2


@dataclass
class _TrailPoint:
    position: pygame.Vector2
    age: float = 0.0


class SlashDetector:
    """Turns mouse strokes into fast segments and icon hits.

    The detector is independent from spawning and scoring: it records the
    pointer path, keeps the segments that were fast enough and exposes hits
    once, so an icon can never score twice for one stroke.
    """

    def __init__(self) -> None:
        self._pressed = False
        self._last_point = pygame.Vector2()
        self._last_time = 0.0
        self._segments: list[SlashSegment] = []
        self._trail: list[_TrailPoint] = []
        self._spark_points: list[tuple[pygame.Vector2, float]] = []
        self._release_age = 0.0
        self._overlay: pygame.Surface | None = None

    @property
    def is_slashing(self) -> bool:
        return self._pressed

    @property
    def trail_length(self) -> int:
        return len(self._trail)

    def reset(self) -> None:
        self._pressed = False
        self._segments.clear()
        self._trail.clear()
        self._spark_points.clear()
        self._release_age = 0.0

    def begin(self, position: tuple[float, float] | pygame.Vector2, now: float) -> None:
        self._pressed = True
        self._release_age = 0.0
        self._last_point = pygame.Vector2(position)
        self._last_time = now
        self._segments.clear()
        self._trail.clear()
        self._trail.append(_TrailPoint(self._last_point.copy()))

    def move(self, position: tuple[float, float] | pygame.Vector2, now: float) -> None:
        if not self._pressed:
            return
        point = pygame.Vector2(position)
        distance = point.distance_to(self._last_point)
        if distance < config.SLASH_MIN_SEGMENT_DISTANCE:
            return

        elapsed = max(1e-4, now - self._last_time)
        speed = distance / elapsed
        if speed >= config.SLASH_MIN_SPEED:
            self._segments.append(
                SlashSegment(self._last_point.copy(), point.copy())
            )
            direction = math.degrees(
                math.atan2(point.y - self._last_point.y, point.x - self._last_point.x)
            )
            self._spark_points.append((point.copy(), direction))
            if len(self._spark_points) > 16:
                del self._spark_points[: len(self._spark_points) - 16]

        self._last_point = point
        self._last_time = now
        self._trail.append(_TrailPoint(point.copy()))
        if len(self._trail) > config.SLASH_TRAIL_MAX_POINTS:
            del self._trail[: len(self._trail) - config.SLASH_TRAIL_MAX_POINTS]

    def end(self, position: tuple[float, float] | pygame.Vector2, now: float) -> None:
        if not self._pressed:
            return
        self.move(position, now)
        self._pressed = False
        self._release_age = 0.0

    def update(self, dt: float) -> None:
        lifetime = config.SLASH_TRAIL_LIFETIME
        kept = 0
        for point in self._trail:
            point.age += dt
            if point.age < lifetime:
                self._trail[kept] = point
                kept += 1
        if kept < len(self._trail):
            del self._trail[kept:]
        if not self._pressed:
            self._release_age += dt
            if self._release_age >= config.SLASH_TRAIL_RELEASE_FADE:
                self._trail.clear()

    def consume_hits(self, icons: tuple["GameIcon", ...] | list["GameIcon"]) -> list[SlashHit]:
        """Return at most one hit per icon and discard the pending segments."""
        if not self._segments:
            return []

        hits: list[SlashHit] = []
        hit_ids: set[int] = set()
        for segment in self._segments:
            sx, sy = segment.start.x, segment.start.y
            ex, ey = segment.end.x, segment.end.y
            min_x, max_x = (sx, ex) if sx <= ex else (ex, sx)
            min_y, max_y = (sy, ey) if sy <= ey else (ey, sy)
            for icon in icons:
                if id(icon) in hit_ids or not icon.alive:
                    continue
                limit = icon.hit_radius + config.SLASH_HIT_PADDING
                px, py = icon.position.x, icon.position.y
                # Cheap AABB rejection before the closest-point calculation.
                if (
                    px < min_x - limit
                    or px > max_x + limit
                    or py < min_y - limit
                    or py > max_y + limit
                ):
                    continue
                point = _closest_point(px, py, sx, sy, ex, ey)
                dx = px - point[0]
                dy = py - point[1]
                if dx * dx + dy * dy <= limit * limit:
                    hit_ids.add(id(icon))
                    hits.append(SlashHit(icon, pygame.Vector2(point)))

        self._segments.clear()
        return hits

    def consume_spark_points(self) -> list[tuple[pygame.Vector2, float]]:
        """Trail positions added by fast samples, for the particle emitter."""
        if not self._spark_points:
            return []
        points = self._spark_points
        self._spark_points = []
        return points

    @staticmethod
    def segment_intersects_circle(
        start: pygame.Vector2,
        end: pygame.Vector2,
        center: pygame.Vector2,
        radius: float,
    ) -> bool:
        point = closest_point_on_segment(center, start, end)
        return point.distance_squared_to(center) <= radius * radius

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        if len(self._trail) < 2:
            return
        if self._overlay is None or self._overlay.get_size() != surface.get_size():
            self._overlay = pygame.Surface(surface.get_size(), pygame.SRCALPHA)
        self._overlay.fill((0, 0, 0, 0))

        release_alpha = 1.0
        if not self._pressed:
            release_alpha = max(
                0.0, 1.0 - self._release_age / config.SLASH_TRAIL_RELEASE_FADE
            )
        if release_alpha <= 0.0:
            return

        outer = config.SLASH_TRAIL_OUTER_COLOR
        glow = config.SLASH_TRAIL_GLOW_COLOR
        core = config.SLASH_TRAIL_CORE_COLOR
        snap = max(1, config.PIXEL_SNAP)

        span = max(1, len(self._trail) - 1)
        for index, (previous, current) in enumerate(zip(self._trail, self._trail[1:])):
            life = max(0.0, 1.0 - current.age / config.SLASH_TRAIL_LIFETIME)
            # Older samples sit at the tail, so they fade out along the stroke.
            tail = 0.16 + 0.84 * ((index + 1) / span)
            alpha = life * release_alpha * tail
            if alpha <= 0.0:
                continue
            start = (round(previous.position.x), round(previous.position.y))
            end = (round(current.position.x), round(current.position.y))
            width = max(1, round((1.0 + 3.0 * life) / snap) * snap)

            outer_width = max(3, round(config.SLASH_TRAIL_OUTER_WIDTH * life) // snap * snap)
            pygame.draw.line(
                self._overlay,
                (*outer, int(46 * alpha)),
                start,
                end,
                outer_width + 6,
            )
            glow_width = max(2, round(config.SLASH_TRAIL_GLOW_WIDTH * life) // snap * snap)
            pygame.draw.line(
                self._overlay,
                (*glow, int(96 * alpha)),
                start,
                end,
                glow_width,
            )
            pygame.draw.line(
                self._overlay,
                (*core, int(245 * alpha)),
                start,
                end,
                max(2, width),
            )

            # Hard pixel caps make the stroke read as blocks, not anti-aliased.
            cap = max(2, glow_width // 2) // snap * snap
            x = int(round(current.position.x / snap)) * snap
            y = int(round(current.position.y / snap)) * snap
            pygame.draw.rect(
                self._overlay,
                (*glow, int(150 * alpha)),
                (x - cap, y - cap, cap * 2, cap * 2),
            )

        newest = self._trail[-1]
        life = max(0.0, 1.0 - newest.age / config.SLASH_TRAIL_LIFETIME) * release_alpha
        x = round(newest.position.x)
        y = round(newest.position.y)
        size = max(2, round(6 * life) // snap * snap)
        pygame.draw.rect(
            self._overlay,
            (*core, int(230 * life)),
            (x - size // 2, y - size // 2, size, size),
        )
        pygame.draw.line(
            self._overlay,
            (*core, int(220 * life)),
            (x - size * 2, y),
            (x + size * 2, y),
            2,
        )
        pygame.draw.line(
            self._overlay,
            (*core, int(220 * life)),
            (x, y - size * 2),
            (x, y + size * 2),
            2,
        )

        if config.SLASH_TRAIL_ADDITIVE:
            surface.blit(self._overlay, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        else:
            surface.blit(self._overlay, (0, 0))


def _closest_point(
    px: float,
    py: float,
    sx: float,
    sy: float,
    ex: float,
    ey: float,
) -> tuple[float, float]:
    dx = ex - sx
    dy = ey - sy
    length_squared = dx * dx + dy * dy
    if length_squared <= 1e-9:
        return sx, sy
    t = ((px - sx) * dx + (py - sy) * dy) / length_squared
    t = max(0.0, min(1.0, t))
    return sx + dx * t, sy + dy * t


def closest_point_on_segment(
    point: pygame.Vector2,
    start: pygame.Vector2,
    end: pygame.Vector2,
) -> pygame.Vector2:
    direction = end - start
    length_squared = direction.length_squared()
    if length_squared <= 1e-9:
        return start.copy()
    t = (point - start).dot(direction) / length_squared
    t = max(0.0, min(1.0, t))
    return start + direction * t
