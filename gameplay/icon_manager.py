from __future__ import annotations

import math
import random

import pygame

import game_config as config
from gameplay.bomb import build_bomb_surface
from gameplay.difficulty import Difficulty, difficulty_at
from gameplay.game_icon import GameIcon
from physics.body import PhysicsBody
from physics.physics_world import PhysicsWorld


class IconManager:
    """Spawns desktop icons in waves and owns their flight lifecycle.

    Every spawned icon gets a logical display size (80/96/112/128) that is
    converted to physical pixels through the monitor DPI and a gentle screen
    size factor. Launch speed is solved from a target apex fraction instead of
    a fixed vertical velocity, so the flight height stays consistent across
    resolutions while the difficulty ramp still shortens the air time.
    """

    def __init__(
        self,
        physics: PhysicsWorld,
        screen_size: tuple[int, int],
        rng: random.Random | None = None,
        dpi: int = 96,
    ) -> None:
        self._physics = physics
        self._screen_size = screen_size
        self._rng = rng or random.Random()
        self._dpi = max(48, int(dpi))

        reference_width, reference_height = config.ICON_SIZE_REFERENCE
        width, height = screen_size
        dpi_scale = max(0.75, min(3.0, self._dpi / 96.0))
        resolution_scale = math.sqrt(
            min(width / reference_width, height / reference_height)
        )
        resolution_scale = max(
            config.ICON_SIZE_RESOLUTION_MIN,
            min(config.ICON_SIZE_RESOLUTION_MAX, resolution_scale),
        )
        self.ui_scale = max(0.72, min(3.2, dpi_scale * resolution_scale))
        # Horizontal speeds follow the monitor width so wide desktops do not
        # produce nearly vertical flights.
        self._horizontal_scale = max(0.8, min(2.0, width / reference_width))

        self._sources: list[pygame.Surface] = []
        self._icons: list[GameIcon] = []
        self._spawn_timer = 0.0
        self._elapsed = 0.0
        self._bomb_image = build_bomb_surface() if config.BOMB_ENABLED else None

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------
    def set_sources(self, sources: list[pygame.Surface]) -> None:
        self._sources = list(sources)

    def begin_round(self) -> None:
        self.clear()
        self._spawn_timer = 0.0
        self._elapsed = 0.0

    def clear(self) -> None:
        for icon in self._icons:
            icon.stop()
        self._icons.clear()

    @property
    def icons(self) -> list[GameIcon]:
        # Hot path: called every physics step. Returning the live list avoids
        # allocating a tuple 120 times per second.
        return self._icons

    @property
    def active_count(self) -> int:
        return len(self._icons)

    @property
    def icon_min_size(self) -> int:
        return round(config.ICON_SIZE_CLASSES[0] * self.ui_scale)

    @property
    def icon_max_size(self) -> int:
        return round(config.ICON_SIZE_CLASSES[-1] * self.ui_scale)

    # ------------------------------------------------------------------
    # Round update
    # ------------------------------------------------------------------
    def update(self, dt: float) -> None:
        for icon in self._icons:
            if icon.alive:
                icon.update(dt)

        if not self._sources:
            return

        self._elapsed += dt
        self._spawn_timer -= dt
        if self._spawn_timer <= 0.0:
            difficulty = difficulty_at(self._elapsed)
            self._spawn_wave(difficulty)
            jitter = self._rng.uniform(
                -config.ICON_SPAWN_JITTER, config.ICON_SPAWN_JITTER
            )
            # The ramp shortens the wait between waves as the round advances.
            self._spawn_timer = max(0.6, difficulty.spawn_interval + jitter)

    def _spawn_wave(self, difficulty: Difficulty | None = None) -> None:
        if difficulty is None:
            difficulty = difficulty_at(self._elapsed)
        capacity = config.ICON_MAX_ACTIVE - len(self._icons)
        if capacity <= 0:
            return
        count = self._rng.randint(
            config.ICON_WAVE_MIN + difficulty.wave_bonus,
            config.ICON_WAVE_MAX + difficulty.wave_bonus,
        )
        count = min(count, capacity)

        bomb_slot = -1
        if (
            self._bomb_image is not None
            and self._elapsed >= config.BOMB_START_TIME
            and self._rng.random() < difficulty.bomb_chance
        ):
            bomb_slot = self._rng.randrange(count)

        # Cycle through shuffled bottom lanes so a wave spreads out instead of
        # stacking every target in the centre.
        zones = max(1, int(config.ICON_SPAWN_ZONES))
        lanes = list(range(zones))
        self._rng.shuffle(lanes)
        reserved: list[float] = []

        for index in range(count):
            icon = self._spawn_icon(
                force_bomb=index == bomb_slot,
                speed_multiplier=difficulty.speed_multiplier,
                lane=lanes[index % zones],
                avoid=reserved,
            )
            reserved.append(icon.position.x)

    def spawn_bomb(self) -> GameIcon:
        """Explicit bomb spawn used by the effects test and demo."""
        return self._spawn_icon(
            force_bomb=True,
            speed_multiplier=difficulty_at(self._elapsed).speed_multiplier,
        )

    def _spawn_icon(
        self,
        force_bomb: bool = False,
        speed_multiplier: float = 1.0,
        *,
        lane: int | None = None,
        avoid: list[float] | None = None,
    ) -> GameIcon:
        is_bomb = force_bomb and self._bomb_image is not None
        if is_bomb:
            source = self._bomb_image
            logical = self._rng.uniform(config.BOMB_SIZE_MIN, config.BOMB_SIZE_MAX)
            target = self._round_size(
                logical * self._rng.uniform(config.BOMB_SCALE_MIN, config.BOMB_SCALE_MAX)
            )
        else:
            source = self._rng.choice(self._sources)
            logical = self._rng.choices(
                config.ICON_SIZE_CLASSES,
                weights=config.ICON_SIZE_WEIGHTS,
                k=1,
            )[0]
            jitter = 1.0 + self._rng.uniform(
                -config.ICON_SIZE_JITTER, config.ICON_SIZE_JITTER
            )
            target = self._round_size(logical * jitter)
        # Each icon owns its surface; the source list is immutable and never
        # affected by slicing or scaling.
        image = source.copy()
        source_size = max(1, max(image.get_width(), image.get_height()))
        scale = max(0.05, target / source_size)

        width, height = self._screen_size
        radius = 0.5 * source_size * scale

        x = self._pick_x(radius, lane, avoid)
        # Some targets launch from deeper below the screen so a wave never
        # pops into view in a perfectly straight row.
        extra_depth = self._rng.uniform(0.0, max(1.0, height * 0.06))
        y = height + config.ICON_SPAWN_BELOW + radius + extra_depth

        apex = self._pick_apex()
        apex_y = height * (1.0 - apex)
        rise = max(1.0, y - apex_y)

        gravity_scale = self._rng.uniform(
            config.ICON_GRAVITY_SCALE_MIN, config.ICON_GRAVITY_SCALE_MAX
        )
        gravity = config.PHYSICS_GRAVITY[1] * gravity_scale
        # rise = v0^2 / (2g); linear drag costs more on a taller screen, so the
        # compensation is solved from the screen height.
        compensation = config.ICON_LAUNCH_DRAG_COMPENSATION - (
            height - config.ICON_SIZE_REFERENCE[1]
        ) * config.ICON_DRAG_COMP_HEIGHT_SLOPE
        compensation = max(
            config.ICON_DRAG_COMP_MIN,
            min(config.ICON_DRAG_COMP_MAX, compensation),
        )
        launch_speed = math.sqrt(2.0 * gravity * rise / compensation)

        direction = -1.0 if x >= width * 0.5 else 1.0
        if self._rng.random() < config.ICON_VX_OUTWARD_CHANCE:
            direction = -direction
        horizontal = (
            self._rng.uniform(config.ICON_VX_MIN, config.ICON_VX_MAX)
            * self._horizontal_scale
        )
        velocity = pygame.Vector2(direction * horizontal, -launch_speed)
        velocity *= speed_multiplier

        body = PhysicsBody(position=pygame.Vector2(x, y), velocity=velocity)
        # Scaling gravity with the squared speed keeps the same flight arc
        # while shortening how long the icon spends on screen.
        body.gravity_scale = gravity_scale * speed_multiplier * speed_multiplier
        self._physics.add(body)

        spin_magnitude = self._rng.uniform(config.ICON_SPIN_MIN, config.ICON_SPIN_MAX)
        icon = GameIcon(
            body=body,
            image=image,
            angle=self._rng.uniform(0.0, 360.0),
            spin=spin_magnitude if self._rng.random() < 0.5 else -spin_magnitude,
            scale=scale,
            base_scale=scale,
            name="BOMB" if is_bomb else "",
            is_bomb=is_bomb,
        )
        self._icons.append(icon)
        return icon

    def _round_size(self, logical: float) -> int:
        return max(24, round(logical * self.ui_scale))

    def _pick_apex(self) -> float:
        if self._rng.random() < config.ICON_APEX_RARE_CHANCE:
            return self._rng.uniform(
                config.ICON_APEX_RARE_MIN, config.ICON_APEX_RARE_MAX
            )
        return self._rng.uniform(config.ICON_APEX_MIN, config.ICON_APEX_MAX)

    def _pick_x(
        self,
        radius: float,
        lane: int | None,
        avoid: list[float] | None,
    ) -> float:
        width = self._screen_size[0]
        margin = max(config.ICON_SPAWN_MARGIN, radius * 0.45)
        zones = max(1, int(config.ICON_SPAWN_ZONES))
        if lane is None:
            lane = self._rng.randrange(zones)
        lane = lane % zones
        zone_width = width / zones
        left = max(margin, lane * zone_width + radius * 0.25)
        right = min(width - margin, (lane + 1) * zone_width - radius * 0.25)
        if right < left:
            left, right = margin, max(margin, width - margin)

        separation = config.ICON_SPAWN_MIN_SEPARATION * 2.0 * max(radius, 24.0)
        best = None
        best_gap = -1.0
        for _ in range(10):
            candidate = self._rng.uniform(left, right)
            if not avoid:
                return candidate
            gap = min(abs(candidate - other) for other in avoid)
            if gap >= separation:
                return candidate
            if gap > best_gap:
                best_gap = gap
                best = candidate
        return best if best is not None else self._rng.uniform(left, right)

    def after_physics(self) -> list[GameIcon]:
        """Drop escaped icons after the physics step and report them."""
        missed: list[GameIcon] = []
        height = self._screen_size[1]
        kept = 0
        for icon in self._icons:
            if not icon.body.alive or icon.sliced or icon.missed:
                continue
            if not icon.entered:
                if icon.position.y - icon.hit_radius < height:
                    icon.entered = True
                self._icons[kept] = icon
                kept += 1
                continue
            if icon.position.y - icon.hit_radius > height + config.ICON_MISS_MARGIN:
                icon.missed = True
                icon.stop()
                missed.append(icon)
                continue
            self._icons[kept] = icon
            kept += 1
        if kept < len(self._icons):
            del self._icons[kept:]
        return missed

    def remove(self, icon: GameIcon) -> None:
        icon.stop()
        try:
            self._icons.remove(icon)
        except ValueError:
            pass

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def draw(self, surface: pygame.Surface) -> None:
        for icon in self._icons:
            if icon.alive:
                icon.draw(surface)
