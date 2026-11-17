from __future__ import annotations

from typing import TYPE_CHECKING

import pygame

import game_config as config
from core.diagnostics import log
from core.phases import GamePhase
from core.states.base import GameState
from effects.bomb_blast import BombBlast
from effects.combo_callout import ComboCallout
from effects.floating_text import FloatingText
from effects.icon_fragments import IconFragments
from effects.slice_flash import SliceFlash
from gameplay.combo_tracker import combo_color, combo_multiplier, combo_reward
from gameplay.game_icon import GameIcon
from localization import t
from ui.fonts import get_font
from ui.text import draw_pixel_text

if TYPE_CHECKING:
    from core.game import Game


class PlayingState(GameState):
    """Timed round: spawn icons, detect slices, score, combos and bombs."""

    def __init__(self, game: "Game") -> None:
        super().__init__(game)
        self._time_left = config.ROUND_SECONDS
        self._resume_mouse_lock = False
        self._fonts_ready = False
        self.refresh_language()

    def refresh_language(self) -> None:
        if not pygame.font.get_init():
            return
        self._watermark_font = get_font(config.FONT_SIZE_TITLE, bold=True)
        self._hint_font = get_font(config.FONT_SIZE_FOOTER)
        self._fonts_ready = True

    @property
    def time_left(self) -> float:
        return self._time_left

    def on_enter(self, resume: bool = False, **kwargs: object) -> None:
        if not resume:
            self._time_left = config.ROUND_SECONDS
        self._resume_mouse_lock = resume
        self.game.slashes.reset()

    def on_exit(self) -> None:
        self.game.slashes.reset()

    def handle_event(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_ESCAPE, pygame.K_p):
                log("INPUT", f"pause key {pygame.key.name(event.key)} in playing state")
                self.game.pause_round()
            return

        if self._resume_mouse_lock:
            if event.type in (
                pygame.MOUSEBUTTONDOWN,
                pygame.MOUSEBUTTONUP,
            ) and event.button == 1:
                self._resume_mouse_lock = False
            elif event.type == pygame.MOUSEMOTION:
                # A button held from before the pause must not start a slash.
                return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.game.slashes.begin(event.pos, self._event_time(event))
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.game.slashes.end(event.pos, self._event_time(event))
        elif event.type == pygame.MOUSEMOTION:
            if event.buttons[0]:
                if self.game.slashes.is_slashing:
                    self.game.slashes.move(event.pos, self._event_time(event))
                else:
                    self.game.slashes.begin(event.pos, self._event_time(event))
            elif self.game.slashes.is_slashing:
                self.game.slashes.end(event.pos, self._event_time(event))

    def update(self, dt: float) -> None:
        self._time_left -= dt
        self.game.combo.update(dt)
        self.game.slashes.update(dt)
        self.game.icon_manager.update(dt)

        for point, direction in self.game.slashes.consume_spark_points():
            self.game.particles.trail_sparks(point, direction)

        if self._time_left <= 0.0:
            self._time_left = 0.0
            self.game.finish_round("time_up")

    def post_update(self, dt: float) -> None:
        missed = self.game.icon_manager.after_physics()
        missed_regular = [icon for icon in missed if not icon.is_bomb]
        if missed_regular:
            self.game.combo.break_combo()
            self.game.lives = max(0, self.game.lives - len(missed_regular))
            self.game.screen_fx.flash(config.COLOR_NEON_RED, 0.12, 50)
            self.game.sfx.play("miss")
            if self.game.lives <= 0:
                self.game.finish_round("out_of_lives")
                return

        highest_combo = 0
        combo_point: pygame.Vector2 | None = None
        for hit in self.game.slashes.consume_hits(self.game.icon_manager.icons):
            icon = hit.icon
            if not icon.alive:
                continue
            image = icon.current_surface()
            icon.sliced = True
            self.game.icon_manager.remove(icon)

            if icon.is_bomb:
                self._explode_bomb(hit.point)
                if self.game.states.phase == GamePhase.GAME_OVER:
                    return
                continue

            combo = self.game.combo.register()
            multiplier = combo_multiplier(combo)
            points = config.SCORE_PER_ICON * multiplier
            self.game.score += points
            self.game.slice_count += 1
            self.game.best_combo = max(self.game.best_combo, combo)
            self._spawn_slice_feedback(icon, image, hit.point, combo, points)
            self.game.sfx.play("slice")
            if combo > highest_combo:
                highest_combo = combo
                combo_point = hit.point

        if highest_combo >= 2 and combo_point is not None:
            self._spawn_combo_feedback(highest_combo, combo_point)
            self.game.sfx.play("combo" if combo_reward(highest_combo) else "slice")

    # ------------------------------------------------------------------
    # Feedback
    # ------------------------------------------------------------------
    def _spawn_slice_feedback(
        self,
        icon: GameIcon,
        image: pygame.Surface,
        point: pygame.Vector2,
        combo: int,
        points: int,
    ) -> None:
        self.game.effects.add(IconFragments(image, point, icon.velocity))
        self.game.effects.add(SliceFlash(point))
        extra = min(
            config.COMBO_EXTRA_PARTICLES_MAX,
            max(0, combo - 2) * config.COMBO_EXTRA_PARTICLES,
        )
        self.game.particles.slice_shards(point, image)
        if extra:
            self.game.particles.burst(
                point,
                count=extra,
                colors=config.SLICE_PIXEL_COLORS,
                speed=config.SLICE_PIXEL_SPEED,
                lifetime=config.SLICE_PIXEL_LIFETIME,
                size=config.SLICE_PIXEL_SIZE,
                gravity=config.SLICE_PIXEL_GRAVITY,
            )
        self.game.effects.add(
            FloatingText(
                f"+{points}",
                point,
                color=combo_color(combo),
                combo=combo,
            )
        )

    def _spawn_combo_feedback(self, combo: int, point: pygame.Vector2) -> None:
        reward = combo_reward(combo)
        if reward is not None:
            text, subtext, color = reward
            width, height = self.game.screen.get_size()
            self.game.effects.add(
                ComboCallout(text, subtext, color, (width * 0.5, height * 0.32))
            )
            self.game.screen_fx.flash(color, config.COMBO_FLASH_DURATION, config.COMBO_FLASH_ALPHA)
            self.game.particles.ring(
                point,
                count=22,
                radius=18.0,
                speed=(160.0, 300.0),
                colors=(color, config.COLOR_WHITE_HOT),
                lifetime=(0.24, 0.5),
                size=(2, 4),
            )
            if combo >= config.COMBO_HIGH_THRESHOLD:
                self.game.screen_fx.shake(
                    config.COMBO_SHAKE_STRENGTH, config.COMBO_SHAKE_DURATION
                )
        elif combo >= config.COMBO_HIGH_THRESHOLD:
            # Every hit at high combo gets extra heat, not just milestones.
            self.game.screen_fx.flash(
                config.COMBO_X5_COLOR,
                config.COMBO_FLASH_DURATION,
                config.COMBO_FLASH_ALPHA // 2,
            )
            self.game.particles.ring(
                point,
                count=10,
                radius=12.0,
                speed=(100.0, 200.0),
                colors=(combo_color(combo), config.COLOR_NEON_YELLOW),
                lifetime=(0.16, 0.34),
                size=(2, 4),
                gravity=300.0,
            )

    def _explode_bomb(self, point: pygame.Vector2) -> None:
        self.game.combo.break_combo()
        self.game.effects.add(BombBlast(point))
        self.game.particles.bomb_burst(point)
        self.game.screen_fx.shake(
            config.BOMB_SHAKE_STRENGTH, config.BOMB_SHAKE_DURATION
        )
        self.game.screen_fx.flash(
            config.BOMB_FLASH_COLOR,
            config.BOMB_FLASH_DURATION,
            config.BOMB_FLASH_ALPHA,
        )
        self.game.sfx.play("bomb")
        if config.BOMB_LIFE_PENALTY > 0:
            self.game.effects.add(
                FloatingText(
                    t("playing.life_penalty", count=config.BOMB_LIFE_PENALTY),
                    point,
                    color=config.COLOR_NEON_RED,
                )
            )
        self.game.lives = max(0, self.game.lives - config.BOMB_LIFE_PENALTY)
        if self.game.lives <= 0:
            self.game.finish_round("out_of_lives")

    # ------------------------------------------------------------------
    # Render
    # ------------------------------------------------------------------
    def render(self, surface: pygame.Surface) -> None:
        if not self._fonts_ready:
            self.refresh_language()
        self.game.background.draw(surface)

        width, height = surface.get_size()
        if not self.game.is_overlay:
            draw_pixel_text(
                surface,
                t("playing.watermark"),
                self._watermark_font,
                config.COLOR_NEON_MAGENTA,
                (width // 2, height * 0.52),
                alpha=18,
                shadow=0,
            )

        self.game.icon_manager.draw(surface)
        self.game.slashes.draw(surface)
        self.game.particles.draw(surface)
        self.game.effects.draw(surface)
        self.game.hud.draw(
            surface,
            self.game.score,
            self._time_left,
            config.ROUND_SECONDS,
            self.game.lives,
            self.game.combo.count,
            combo_multiplier(self.game.combo.count),
            max(self.game.profile.high_score, self.game.score),
        )

        draw_pixel_text(
            surface,
            t("playing.hold"),
            self._hint_font,
            config.COLOR_ACCENT_DIM,
            (config.UI_MARGIN, height - 30),
            "midleft",
            shadow=1,
        )
        draw_pixel_text(
            surface,
            t("playing.pause"),
            self._hint_font,
            config.COLOR_TEXT_DIM,
            (width - config.UI_MARGIN, height - 30),
            "midright",
            shadow=1,
        )

    @staticmethod
    def _event_time(event: pygame.event.Event) -> float:
        value = getattr(event, "input_time", None)
        if value is None:
            return pygame.time.get_ticks() / 1000.0
        return float(value)
