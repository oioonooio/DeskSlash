"""Chinese/English switching checks for Desktop Slash.

    python test_i18n.py

Verifies the two catalogues, the default and fallback behaviour, the profile
persistence, immediate in-game switching, CJK glyph coverage (no tofu) and
that labels still fit their buttons in both languages. Everything runs
headless with a throwaway profile.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
import traceback
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")

import pygame

import game_config as config
from core.game import Game
from core.phases import GamePhase
from core.profile import Profile, ProfileStore
from localization import (
    available_languages,
    current_language,
    get_language_manager,
    set_language,
    t,
)
from ui.fonts import get_font

_PROFILE_DIR = Path(tempfile.mkdtemp(prefix="desktop_slash_i18n_"))
_SEQUENCE = 0
FAILURES: list[str] = []

ZH = {
    "menu.start": "\u5f00\u59cb\u6e38\u620f",
    "menu.settings": "\u8bbe\u7f6e",
    "menu.exit": "\u9000\u51fa\u6e38\u620f",
    "paused.resume": "ESC / P   \u7ee7\u7eed\u6e38\u620f",
    "gameover.play_again": "\u91cd\u65b0\u5f00\u59cb",
    "gameover.title.round_over": "\u6e38\u620f\u7ed3\u675f",
    "gameover.exit": "\u9000\u51fa\u684c\u9762",
    "hud.score": "\u5f97\u5206",
    "hud.best": "\u6700\u9ad8\u5206 {score:06d}",
    "hud.combo": "\u8fde\u51fb {combo}",
    "hud.lives": "\u751f\u547d",
    "paused.title": "\u6682\u505c",
}

EN = {
    "menu.start": "START",
    "menu.settings": "SETTINGS",
    "menu.exit": "EXIT",
    "paused.resume": "ESC / P   RESUME",
    "gameover.play_again": "PLAY AGAIN",
    "gameover.title.round_over": "ROUND OVER",
    "gameover.exit": "EXIT GAME",
    "hud.score": "SCORE",
    "hud.best": "BEST {score:06d}",
    "hud.combo": "COMBO {combo}",
    "hud.lives": "LIVES",
    "paused.title": "PAUSED",
}

CJK_SAMPLE = (
    "\u5f00\u59cb\u6e38\u620f\u8bbe\u7f6e\u7ee7\u7eed\u91cd\u65b0\u9000\u51fa"
    "\u5f97\u5206\u6700\u9ad8\u8fde\u51fb\u751f\u547d\u6682\u505c\u5173\u95ed"
)


def _new_store(name: str = "") -> ProfileStore:
    global _SEQUENCE
    _SEQUENCE += 1
    file_name = f"{name}_{_SEQUENCE}.json" if name else f"game_{_SEQUENCE}.json"
    return ProfileStore(_PROFILE_DIR / file_name)


def _new_game(store: ProfileStore) -> Game:
    return Game(store, overlay=False, hide_desktop=False)


def _text_width(font: pygame.font.Font, text: str) -> int:
    return font.size(text)[0]


def test_catalogues() -> None:
    manager = get_language_manager()
    catalogues = manager._catalogues
    assert set(catalogues) >= {"zh_CN", "en_US"}, catalogues.keys()
    keys_zh = set(catalogues["zh_CN"])
    keys_en = set(catalogues["en_US"])
    assert keys_zh == keys_en, (
        f"missing in en: {sorted(keys_zh - keys_en)}; "
        f"extra in en: {sorted(keys_en - keys_zh)}"
    )
    assert len(keys_zh) >= 60, len(keys_zh)
    for code, catalogue in catalogues.items():
        empty = sorted(key for key, value in catalogue.items() if not value.strip())
        assert not empty, f"{code} has empty values: {empty}"
    assert available_languages() == ("zh_CN", "en_US"), available_languages()


def test_default_and_fallback() -> None:
    assert config.DEFAULT_LANGUAGE == "zh_CN"
    set_language("zh_CN")
    assert current_language() == "zh_CN"
    assert set_language("fr_FR") is False
    assert current_language() == "zh_CN", "an unknown code must fall back to zh_CN"
    assert set_language(None) is False  # type: ignore[arg-type]
    assert current_language() == "zh_CN"
    assert t("no.such.key") == "no.such.key"


def test_glossary() -> None:
    set_language("zh_CN")
    for key, expected in ZH.items():
        assert t(key) == expected, f"{key}: {t(key)!r} != {expected!r}"
    set_language("en_US")
    for key, expected in EN.items():
        assert t(key) == expected, f"{key}: {t(key)!r} != {expected!r}"


def test_formatting() -> None:
    set_language("zh_CN")
    assert t("hud.best", score=42) == ZH["hud.best"].format(score=42)
    assert t("hud.combo", combo=7) == ZH["hud.combo"].format(combo=7)
    assert t("playing.life_penalty", count=2) == "-2 \u751f\u547d"
    assert t("hud.best", wrong=1) == ZH["hud.best"]
    set_language("en_US")
    assert t("hud.best", score=42) == "BEST 000042"


def test_profile_language() -> None:
    store = _new_store("profile")
    fresh = store.load()
    assert fresh.language == "zh_CN", fresh.language

    assert store.save(Profile(high_score=7, language="en_US"))
    assert store.load().language == "en_US"

    corrupt = {
        "version": config.PROFILE_VERSION,
        "high_score": 3,
        "settings": {"language": 5},
    }
    store.path.write_text(json.dumps(corrupt), encoding="utf-8")
    assert store.load().language == "zh_CN", "a non-string language must fall back"

    corrupt["settings"] = {"language": "fr_FR"}
    store.path.write_text(json.dumps(corrupt), encoding="utf-8")
    assert store.load().language == "zh_CN", "an unknown language must fall back"

    store.path.write_text("{not json", encoding="utf-8")
    assert store.load().language == "zh_CN", "a broken file must fall back"

    store.path.write_text(json.dumps({"version": 1, "high_score": 1}), encoding="utf-8")
    assert store.load().language == "zh_CN", "a missing field must fall back"


def test_font_glyphs() -> None:
    pygame.init()
    set_language("zh_CN")
    cjk_font = get_font(32, cjk=True)
    for char in CJK_SAMPLE:
        metrics = cjk_font.metrics(char)
        assert metrics and metrics[0] is not None, (
            f"no glyph for {char!r} (U+{ord(char):04X}); the Chinese font is missing"
        )
    cjk_width = cjk_font.size("\u5f00\u59cb\u6e38\u620f")[0]
    assert cjk_width > 40, f"Chinese text rendered only {cjk_width}px wide"

    set_language("en_US")
    latin = get_font(32)
    assert latin.metrics("START SETTINGS EXIT")[0] is not None
    assert latin.size("START SETTINGS")[0] > 100


def test_switch_in_game() -> None:
    store = _new_store("switch")
    store.save(Profile(language="en_US"))
    game = _new_game(store)
    try:
        assert current_language() == "en_US"
        menu = game.states._current
        assert [button.label for button in menu._buttons] == [
            EN["menu.start"],
            EN["menu.settings"],
            EN["menu.exit"],
        ], [button.label for button in menu._buttons]

        menu.handle_event(
            pygame.event.Event(
                pygame.MOUSEBUTTONDOWN, button=1, pos=menu._buttons[1].rect.center
            )
        )
        overlay = menu._overlay
        assert overlay.is_open
        language_row = overlay._rows[overlay.ROW_LANGUAGE]
        overlay.handle_event(
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=1, pos=language_row.center)
        )
        assert game.profile.language == "zh_CN", game.profile.language
        assert current_language() == "zh_CN"
        assert [button.label for button in menu._buttons] == [
            ZH["menu.start"],
            ZH["menu.settings"],
            ZH["menu.exit"],
        ], "the menu did not update immediately"
        assert store.load().language == "zh_CN", "the switch was not saved"
        overlay.draw(game.screen, game)
        pygame.display.flip()

        game.start_round()
        game.begin_play()
        game.pause_round()
        game._render()
        paused_pixels = pygame.image.tobytes(game.screen, "RGB")

        game.set_language("en_US")
        assert [button.label for button in menu._buttons] == [
            EN["menu.start"],
            EN["menu.settings"],
            EN["menu.exit"],
        ]
        assert game.states.phase == GamePhase.PAUSED
        game._render()
        assert pygame.image.tobytes(game.screen, "RGB") != paused_pixels, (
            "the pause screen did not repaint after switching language"
        )
    finally:
        game.shutdown()

    reloaded = _new_game(store)
    try:
        assert current_language() == "en_US"
        assert reloaded.states._current._buttons[0].label == EN["menu.start"]
    finally:
        reloaded.shutdown()
        set_language("zh_CN")


def _render_every_screen(game: Game) -> dict[str, bytes]:
    shots: dict[str, bytes] = {}
    menu = game.states._current
    game._render()
    shots["menu"] = pygame.image.tobytes(game.screen, "RGB")

    menu.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=menu._buttons[1].rect.center
        )
    )
    game._render()
    shots["settings"] = pygame.image.tobytes(game.screen, "RGB")
    menu.handle_event(
        pygame.event.Event(
            pygame.MOUSEBUTTONDOWN, button=1, pos=menu._overlay._rows[-1].center
        )
    )

    game.start_round()
    game._render()
    shots["countdown"] = pygame.image.tobytes(game.screen, "RGB")
    game.begin_play()
    game._render()
    shots["playing"] = pygame.image.tobytes(game.screen, "RGB")

    game.pause_round()
    game._render()
    shots["paused"] = pygame.image.tobytes(game.screen, "RGB")

    game.finish_round("time_up")
    game._render()
    shots["game_over"] = pygame.image.tobytes(game.screen, "RGB")
    return shots


def test_every_screen_and_layout() -> None:
    store = _new_store("screens")
    game = _new_game(store)
    try:
        shots: dict[str, dict[str, bytes]] = {}
        for language in ("zh_CN", "en_US"):
            game.set_language(language)
            assert current_language() == language
            shots[language] = _render_every_screen(game)

            menu = game.states._current
            for button in menu._buttons:
                width = _text_width(button._font, button.label)
                assert button.rect.width >= width + 56, (
                    f"{language} menu {button.label!r} needs {width}px of "
                    f"{button.rect.width}px"
                )

            game.finish_round("time_up")
            over = game.states._current
            for button in over._buttons:
                width = _text_width(button._font, button.label)
                assert button.rect.width >= width + 24, (
                    f"{language} game over {button.label!r} needs {width}px of "
                    f"{button.rect.width}px"
                )
            game.go_to_menu()

            menu = game.states._current
            menu.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN, button=1, pos=menu._buttons[1].rect.center
                )
            )
            overlay = menu._overlay
            row = overlay._rows[overlay.ROW_LANGUAGE]
            label = t("settings.language")
            name = config.LANGUAGE_LABELS[game.profile.language]
            label_font = overlay._label_cjk_font
            assert label_font.metrics("\u8bed\u8a00")[0] is not None, (
                f"{language} language row label has no Chinese glyphs"
            )
            label_width = _text_width(label_font, label)
            value_width = _text_width(overlay._value_cjk_font, f"<  {name}  >")
            assert label_width + value_width + 60 <= row.width, (
                f"{language} language row overflows: {label_width}+{value_width} "
                f"in {row.width}px"
            )
            for index, label_key in (
                (overlay.ROW_VOLUME, "settings.volume"),
                (overlay.ROW_SHAKE, "settings.shake"),
                (overlay.ROW_SCANLINES, "settings.scanlines"),
            ):
                text = t(label_key)
                label_width = _text_width(overlay._label_font, text)
                assert row.x + 20 + label_width <= row.right - 132 - 8, (
                    f"{language} settings label {text!r} overlaps its value"
                )
            for value_key in ("settings.on", "settings.off"):
                assert _text_width(overlay._value_font, t(value_key)) < 120
            menu.handle_event(
                pygame.event.Event(
                    pygame.MOUSEBUTTONDOWN, button=1, pos=overlay._rows[-1].center
                )
            )

        for screen, zh_pixels in shots["zh_CN"].items():
            digest_zh = hashlib.sha1(zh_pixels).hexdigest()
            digest_en = hashlib.sha1(shots["en_US"][screen]).hexdigest()
            assert digest_zh != digest_en, (
                f"{screen} looks identical in both languages"
            )
    finally:
        game.shutdown()
        set_language("zh_CN")


def main() -> int:
    tests = (
        ("both catalogues share every key", test_catalogues),
        ("Chinese is the safe default", test_default_and_fallback),
        ("required game vocabulary", test_glossary),
        ("translation formatting", test_formatting),
        ("profile language persistence", test_profile_language),
        ("Chinese glyphs exist (no tofu)", test_font_glyphs),
        ("switching applies immediately and is saved", test_switch_in_game),
        ("every screen changes and labels fit", test_every_screen_and_layout),
    )
    print("Desktop Slash - language switching checks")
    for label, function in tests:
        try:
            function()
        except Exception as exc:  # noqa: BLE001 - report every check
            FAILURES.append(label)
            print(f"[FAIL] {label}: {exc}")
            traceback.print_exc()
        else:
            print(f"[PASS] {label}")

    print(f"\n{'PASS' if not FAILURES else 'FAIL'}: {len(FAILURES)} failure(s)")
    return 0 if not FAILURES else 1


if __name__ == "__main__":
    raise SystemExit(main())
