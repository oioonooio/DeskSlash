"""Central tuning table for Desktop Slash.

Every value that shapes the game lives here so gameplay systems never have to
hard-code timings, sizes or colours. Units are pixels and seconds unless noted.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Window / desktop overlay
# ---------------------------------------------------------------------------
WINDOW_TITLE = "Desktop Slash"
WINDOW_SIZE = (1280, 720)
WINDOW_VSYNC = 0

# The game runs as a borderless transparent overlay on the selected monitor.
# Set WINDOW_OVERLAY = False (or pass --window) for the old 1280x720 window.
WINDOW_OVERLAY = True
WINDOW_OVERLAY_MONITOR = 0          # index from EnumDisplayMonitors, 0 = primary
WINDOW_OVERLAY_USE_WORK_AREA = True  # keep the taskbar usable
WINDOW_TRANSPARENT_COLOR_KEY = (1, 0, 2)
WINDOW_TOPMOST = True
# False keeps a taskbar/Alt+Tab entry, so the mouse can always come back to
# the game after alt-tabbing away. True hides it like a desktop gadget.
WINDOW_TOOLWINDOW = False

# Pause releases the mouse to the desktop. The resume key is polled globally
# so it still works after the desktop receives focus.
PAUSE_INPUT_RELEASE = True
PAUSE_RESUME_GUARD = 0.35
PAUSE_KEYS = ("escape", "p")
# After the global poll consumes a resume press, SDL can deliver the same
# physical key as a queued KEYDOWN a few milliseconds later. Ignore pause keys
# for this long so one press never toggles twice.
PAUSE_KEY_ECHO_GUARD = 0.3

# Full-screen flashes still apply in overlay mode; scanlines are disabled
# because they would tint the desktop behind the transparent window.
WINDOW_OVERLAY_SCANLINES = False

# Overlay sessions hide the real desktop icons (SHELLDLL_DefView's
# SysListView32) with ShowWindow, so the wallpaper shows through the colour
# key. Nothing on disk, no position and no registry value is touched.
DESKTOP_HIDE_ICONS = True
DESKTOP_HIDE_WATCHDOG = True
DESKTOP_RESTORE_LOG = "desktop_restore.log"

# Unified shutdown: every exit route goes through Game.request_shutdown().
# The budget is a soft deadline between cleanup steps; no step performs an
# unbounded wait. Ctrl+Shift+Q is polled from a daemon thread so it also works
# while the window message loop is busy.
SHUTDOWN_BUDGET_SECONDS = 5.0
EMERGENCY_HOTKEY_POLL = 0.05
EMERGENCY_HOTKEY_GRACE = 3.0

# The overlay paints the wallpaper itself so other application windows can
# never show through the colour-key hole. The backdrop is built once from the
# current wallpaper file (read-only) and the wallpaper style preferences.
# No dim, grain or tint is applied: the overlay must match the native desktop
# wallpaper pixel for pixel. OVERLAY_WALLPAPER_DIM is kept as an explicit
# escape hatch only; the default is 0.
OVERLAY_WALLPAPER_BACKDROP = True
OVERLAY_WALLPAPER_DIM = 0.0
WALLPAPER_VERIFY_DIR = "test_output"

# ---------------------------------------------------------------------------
# Timing
# ---------------------------------------------------------------------------
FPS = 60
FIXED_DT = 1.0 / 120.0
MAX_FRAME_TIME = 0.25
BACKGROUND_FPS = 15
LOG_HEARTBEAT_SECONDS = 5.0
FOCUS_POLL_SECONDS = 0.2
FOCUS_LOST_DELAY = 0.2
FOCUS_GAIN_DELAY = 0.05

# ---------------------------------------------------------------------------
# Round flow
# ---------------------------------------------------------------------------
COUNTDOWN_STEP_SECONDS = 1.0
COUNTDOWN_GO_SECONDS = 0.8
COUNTDOWN_SECONDS = COUNTDOWN_STEP_SECONDS * 3 + COUNTDOWN_GO_SECONDS
COUNTDOWN_GO_LABEL = "GO!"
COUNTDOWN_POP_SCALE = 0.34
COUNTDOWN_POP_TIME = 0.24
ROUND_SECONDS = 90.0
STARTING_LIVES = 3
SCORE_PER_ICON = 10

# ---------------------------------------------------------------------------
# Physics
# ---------------------------------------------------------------------------
PHYSICS_GRAVITY = (0.0, 2200.0)
PHYSICS_LINEAR_DRAG = 0.35
PHYSICS_MAX_SPEED = 6000.0

# ---------------------------------------------------------------------------
# Icon spawning
# ---------------------------------------------------------------------------
ICON_WAVE_MIN = 3
ICON_WAVE_MAX = 5
ICON_SPAWN_INTERVAL = 1.5
ICON_SPAWN_JITTER = 0.15
ICON_MAX_ACTIVE = 12
ICON_SPAWN_MARGIN = 70
ICON_SPAWN_BELOW = 120
ICON_MISS_MARGIN = 24
# The bottom edge is split into this many lanes; each wave tries to spread its
# icons across lanes and keeps a minimum gap so targets stay cuttable.
ICON_SPAWN_ZONES = 3
ICON_SPAWN_MIN_SEPARATION = 1.15  # multiples of the larger icon size

# ---------------------------------------------------------------------------
# Icon display size
# ---------------------------------------------------------------------------
# Logical sizes are multiplied by the monitor DPI scale (window.dpi / 96) and
# a gentle screen-size factor, then rendered as physical pixels. The source is
# requested from the Windows Shell at ICON_SOURCE_SIZE so 96 px icons stay
# crisp instead of being enlarged from 32 px art.
ICON_SIZE_SMALL = 80
ICON_SIZE_NORMAL = 96
ICON_SIZE_LARGE = 112
ICON_SIZE_SPECIAL = 128
ICON_SIZE_CLASSES = (
    ICON_SIZE_SMALL,
    ICON_SIZE_NORMAL,
    ICON_SIZE_LARGE,
    ICON_SIZE_SPECIAL,
)
# Small / normal / large / special share of spawned icons.
ICON_SIZE_WEIGHTS = (0.22, 0.50, 0.24, 0.04)
ICON_SIZE_JITTER = 0.05
ICON_SIZE_REFERENCE = (1920, 1080)
ICON_SIZE_RESOLUTION_MIN = 1.00
ICON_SIZE_RESOLUTION_MAX = 1.40
ICON_SOURCE_SIZE = 256

# A slow breathing scale keeps flight lively; values are quantised in
# GameIcon.update() so the scaled-surface cache is not rebuilt every frame.
ICON_BREATHE_AMPLITUDE = 0.028
ICON_BREATHE_PERIOD = 1.9
ICON_SCALE_QUANTUM = 0.006

# Soft halo drawn behind every icon. Derived from the icon alpha with a cheap
# downscale/upscale blur, cached per scale step.
ICON_GLOW_ENABLED = True
ICON_GLOW_COLOR = (120, 240, 255)
ICON_GLOW_ALPHA = 82
ICON_GLOW_PADDING = 0.10

# ---------------------------------------------------------------------------
# Icon motion
# ---------------------------------------------------------------------------
# Launch speed is solved from a target apex instead of a fixed vy:
#   rise = v0^2 / (2 * g)  ->  v0 = sqrt(2 * g * rise)
# ICON_APEX_* is the fraction of the screen height the icon centre reaches
# above the bottom edge. ICON_LAUNCH_DRAG_COMPENSATION compensates for the
# linear drag of the fixed-timestep integrator (measured at ~0.80).
ICON_APEX_MIN = 0.55
ICON_APEX_MAX = 0.75
ICON_APEX_RARE_MIN = 0.76
ICON_APEX_RARE_MAX = 0.82
ICON_APEX_RARE_CHANCE = 0.15
# Linear drag costs a larger share of a longer flight, so the compensation is
# solved per screen height instead of using one global constant:
#   compensation = 0.80 - (height - 1080) * 0.00006, clamped below.
# Calibrated at 720p, 1080p, 2560x1600 and 4K: measured apex 0.55-0.80.
ICON_LAUNCH_DRAG_COMPENSATION = 0.80
ICON_DRAG_COMP_HEIGHT_SLOPE = 0.00006
ICON_DRAG_COMP_MIN = 0.72
ICON_DRAG_COMP_MAX = 0.86
ICON_VX_MIN = 30.0
ICON_VX_MAX = 190.0
ICON_VX_OUTWARD_CHANCE = 0.24
ICON_GRAVITY_SCALE_MIN = 0.88
ICON_GRAVITY_SCALE_MAX = 1.16
ICON_SPIN_MIN = 60.0
ICON_SPIN_MAX = 190.0
ICON_HITBOX_SCALE = 0.88

# ---------------------------------------------------------------------------
# Difficulty ramp (one curve, no mode system)
# ---------------------------------------------------------------------------
DIFFICULTY_CURVE_POWER = 1.25
DIFFICULTY_WAVE_BONUS_MAX = 3
DIFFICULTY_SPEED_MAX_MULT = 1.38
DIFFICULTY_SPAWN_INTERVAL_MIN = 0.72
DIFFICULTY_SPAWN_INTERVAL_SCALE = 0.78
DIFFICULTY_BOMB_CHANCE_MAX = 0.48

# ---------------------------------------------------------------------------
# Slashing
# ---------------------------------------------------------------------------
SLASH_MIN_SPEED = 420.0
SLASH_MIN_SEGMENT_DISTANCE = 1.5
SLASH_HIT_PADDING = 2.0
SLASH_TRAIL_LIFETIME = 0.42
SLASH_TRAIL_RELEASE_FADE = 0.24
SLASH_TRAIL_MAX_POINTS = 32
SLASH_TRAIL_ADDITIVE = True

SLASH_TRAIL_OUTER_COLOR = (128, 46, 235)
SLASH_TRAIL_GLOW_COLOR = (0, 238, 255)
SLASH_TRAIL_CORE_COLOR = (255, 255, 240)
SLASH_TRAIL_OUTER_WIDTH = 14
SLASH_TRAIL_GLOW_WIDTH = 8
SLASH_TRAIL_CORE_WIDTH = 3

SLASH_TRAIL_SPARK_COUNT = 2
SLASH_TRAIL_SPARK_COLORS = (
    (255, 255, 240),
    (0, 238, 255),
    (255, 226, 92),
    (190, 90, 255),
)
SLASH_TRAIL_SPARK_SPEED = (25.0, 150.0)
SLASH_TRAIL_SPARK_LIFETIME = (0.16, 0.34)
SLASH_TRAIL_SPARK_SIZE = (1, 3)
SLASH_TRAIL_SPARK_GRAVITY = 120.0

# Kept for effects that still reference the original slash colours.
COLOR_SLASH_CORE = SLASH_TRAIL_CORE_COLOR
COLOR_SLASH_GLOW = SLASH_TRAIL_GLOW_COLOR

# ---------------------------------------------------------------------------
# Slice feedback
# ---------------------------------------------------------------------------
FRAGMENT_GRAVITY = 1900.0
FRAGMENT_LIFETIME = 1.05
FRAGMENT_FADE_START = 0.55
FRAGMENT_SPLIT_SPEED = 235.0
FRAGMENT_LIFT_SPEED = 130.0
FRAGMENT_SPIN_MAX = 300.0

SLICE_PIXEL_MIN = 8
SLICE_PIXEL_MAX = 20
SLICE_PIXEL_SIZE = (3, 8)
SLICE_PIXEL_SPEED = (110.0, 430.0)
SLICE_PIXEL_LIFETIME = (0.45, 0.95)
SLICE_PIXEL_GRAVITY = 1500.0
SLICE_PIXEL_COLORS = (
    (255, 255, 240),
    (0, 238, 255),
    (255, 226, 92),
    (255, 145, 40),
    (190, 90, 255),
)

SLICE_FLASH_LIFETIME = 0.16
SLICE_FLASH_RADIUS_MIN = 20.0
SLICE_FLASH_RADIUS_MAX = 62.0
SLICE_FLASH_COLOR = (255, 255, 245)
SLICE_FLASH_RING_COLOR = (255, 240, 150)

SCORE_POPUP_LIFETIME = 0.92
SCORE_POPUP_RISE = 88.0
SCORE_POPUP_START_SCALE = 0.72
SCORE_POPUP_END_SCALE = 1.38
SCORE_POPUP_COLOR = (255, 232, 92)

# ---------------------------------------------------------------------------
# Pixel particle system
# ---------------------------------------------------------------------------
PARTICLE_POOL_MAX = 900
PARTICLE_LIFETIME = 0.6
PARTICLE_RADIUS = 3
PARTICLE_SPEED_MIN = 90.0
PARTICLE_SPEED_MAX = 340.0
PARTICLE_GRAVITY = 900.0
PARTICLE_COLOR = (150, 245, 255)
COLOR_PARTICLE = PARTICLE_COLOR
PIXEL_SNAP = 2
PARTICLE_ADDITIVE = True

# ---------------------------------------------------------------------------
# Bombs
# ---------------------------------------------------------------------------
BOMB_ENABLED = True
BOMB_START_TIME = 6.0
BOMB_SPAWN_CHANCE = 0.18
BOMB_SIZE_MIN = 112      # logical size before DPI/resolution scaling
BOMB_SIZE_MAX = 128
BOMB_SOURCE_SIZE = 256   # procedural bomb source resolution
BOMB_SCALE_MIN = 0.98    # small per-icon variation
BOMB_SCALE_MAX = 1.06
BOMB_LIFE_PENALTY = 1

BOMB_PARTICLE_COUNT = 52
BOMB_PARTICLE_COLORS = (
    (255, 255, 240),
    (255, 226, 92),
    (255, 145, 40),
    (255, 58, 74),
    (190, 40, 60),
)
BOMB_PARTICLE_SIZE = (2, 8)
BOMB_PARTICLE_SPEED = (180.0, 700.0)
BOMB_PARTICLE_LIFETIME = (0.35, 0.95)
BOMB_PARTICLE_GRAVITY = 760.0

BOMB_BLAST_LIFETIME = 0.48
BOMB_BLAST_RADIUS_MIN = 26.0
BOMB_BLAST_RADIUS_MAX = 190.0
BOMB_FLASH_COLOR = (255, 120, 40)
BOMB_FLASH_DURATION = 0.15
BOMB_FLASH_ALPHA = 60
BOMB_SHAKE_STRENGTH = 16
BOMB_SHAKE_DURATION = 0.36
BOMB_CORE_COLOR = (255, 250, 220)

# ---------------------------------------------------------------------------
# Combo
# ---------------------------------------------------------------------------
COMBO_WINDOW = 1.7
COMBO_HIGH_THRESHOLD = 5
COMBO_GREAT_THRESHOLD = 8
COMBO_GREAT_STEP = 5
COMBO_MULTIPLIER_STEP = 3
COMBO_MULTIPLIER_MAX = 5
COMBO_CALLOUT_LIFETIME = 1.05
COMBO_CALLOUT_RISE = 14.0
COMBO_EXTRA_PARTICLES = 4
COMBO_EXTRA_PARTICLES_MAX = 28
COMBO_FLASH_DURATION = 0.14
COMBO_FLASH_ALPHA = 46
COMBO_SHAKE_STRENGTH = 4
COMBO_SHAKE_DURATION = 0.12
COMBO_X2_COLOR = (0, 238, 255)
COMBO_X3_COLOR = (255, 232, 92)
COMBO_X5_COLOR = (255, 145, 40)
COMBO_GREAT_COLOR = (255, 60, 200)
COMBO_HUD_COLOR = (255, 226, 92)

# ---------------------------------------------------------------------------
# Screen presentation / performance
# ---------------------------------------------------------------------------
EFFECT_MAX_ACTIVE = 96
SCREEN_SHAKE_MAX = 18.0
SCANLINE_ALPHA = 24
SCANLINE_SPACING = 3
FLASH_ADDITIVE = True

# Rendered text surfaces are cached so a 60 FPS HUD does not re-rasterise the
# same labels every frame. Dynamic strings (score/time) also benefit until the
# cache reaches this cap.
TEXT_CACHE_MAX = 512
ICON_TRANSFORM_CACHE = True
PERF_SAMPLE_FRAMES = 120

# ---------------------------------------------------------------------------
# Audio (procedural, no asset files required)
# ---------------------------------------------------------------------------
AUDIO_ENABLED = True
AUDIO_VOLUME = 0.32
AUDIO_SAMPLE_RATE = 44100

# ---------------------------------------------------------------------------
# Saved profile (JSON in %APPDATA%/DesktopSlash)
# ---------------------------------------------------------------------------
PROFILE_DIR_NAME = "DesktopSlash"
PROFILE_FILE_NAME = "save.json"
PROFILE_VERSION = 2
DEFAULT_VOLUME = AUDIO_VOLUME
VOLUME_STEP = 0.1

# ---------------------------------------------------------------------------
# Language
# ---------------------------------------------------------------------------
DEFAULT_LANGUAGE = "zh_CN"
LANGUAGE_CHOICES = ("zh_CN", "en_US")
LANGUAGE_LABELS = {
    "zh_CN": "简体中文",
    "en_US": "English",
}

# ---------------------------------------------------------------------------
# Fallback icons used when the desktop cannot be read
# ---------------------------------------------------------------------------
FALLBACK_ICON_COUNT = 10
FALLBACK_ICON_SIZE = 256
FALLBACK_ICON_COLORS = (
    (72, 132, 228),
    (228, 122, 72),
    (96, 190, 128),
    (176, 112, 224),
    (232, 190, 82),
    (90, 200, 214),
    (228, 104, 144),
    (120, 145, 230),
    (160, 200, 92),
    (218, 148, 102),
)

# ---------------------------------------------------------------------------
# Palette
# ---------------------------------------------------------------------------
COLOR_BACKGROUND_TOP = (4, 5, 13)
COLOR_BACKGROUND_BOTTOM = (24, 8, 38)
COLOR_BACKGROUND_HORIZON = (116, 34, 150)
COLOR_PANEL = (8, 10, 20)
COLOR_PANEL_BORDER = (54, 66, 104)
COLOR_TEXT = (238, 244, 255)
COLOR_TEXT_DIM = (128, 144, 178)
COLOR_ACCENT = (0, 238, 255)
COLOR_ACCENT_DIM = (36, 132, 158)
COLOR_DANGER = (255, 58, 74)
COLOR_GRID = (150, 64, 210, 26)

COLOR_NEON_CYAN = (0, 238, 255)
COLOR_NEON_PURPLE = (170, 86, 255)
COLOR_NEON_MAGENTA = (255, 60, 200)
COLOR_NEON_ORANGE = (255, 145, 40)
COLOR_NEON_YELLOW = (255, 232, 92)
COLOR_NEON_RED = (255, 58, 74)
COLOR_WHITE_HOT = (255, 255, 245)
COLOR_SHADOW = (2, 3, 8)

# ---------------------------------------------------------------------------
# Background art
# ---------------------------------------------------------------------------
BACKGROUND_GRID_SPACING = 64
BACKGROUND_FLOOR_RATIO = 0.58
BACKGROUND_PERSPECTIVE_LINES = 15
BACKGROUND_HORIZONTAL_LINES = 14
BACKGROUND_STAR_COUNT = 240
BACKGROUND_STAR_COLORS = (
    (0, 238, 255),
    (170, 86, 255),
    (255, 60, 200),
    (150, 185, 255),
)
AMBIENT_PIXEL_COUNT = 64
AMBIENT_PIXEL_SPEED = (6.0, 26.0)
AMBIENT_PIXEL_SIZE = (1, 2)
AMBIENT_PIXEL_ALPHA = (16, 58)

# ---------------------------------------------------------------------------
# Typography
# ---------------------------------------------------------------------------
FONT_NAMES = ("consolas", "lucidaconsole", "couriernew", "bahnschrift", "arial")
# CJK families are tried in order. Microsoft YaHei is the Windows 10 default,
# DengXian and SimHei are the usual fallbacks on trimmed installations.
FONT_NAMES_ZH = (
    "microsoft yahei",
    "microsoft yahei ui",
    "dengxian",
    "simhei",
    "simsun",
    "arial",
)
FONT_FILES_ZH = (
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\Deng.ttf",
    r"C:\Windows\Fonts\Dengb.ttf",
    r"C:\Windows\Fonts\simhei.ttf",
)
FONT_SIZE_TITLE = 128
FONT_SIZE_EYEBROW = 26
FONT_SIZE_SUBTITLE = 24
FONT_SIZE_PROMPT = 26
FONT_SIZE_FOOTER = 17
FONT_SIZE_COUNTDOWN = 168
FONT_SIZE_HUD_LABEL = 15
FONT_SIZE_HUD_VALUE = 38
FONT_SIZE_HUD_COMBO = 20
FONT_SIZE_SCORE_POPUP = 32
FONT_SIZE_COMBO = 76
FONT_SIZE_COMBO_SMALL = 34
FONT_SIZE_GAME_OVER_TITLE = 76
FONT_SIZE_GAME_OVER_SCORE = 96
FONT_SIZE_BUTTON = 26
FONT_SIZE_MENU_SCORE = 30
FONT_SIZE_STAT_LABEL = 16
FONT_SIZE_STAT_VALUE = 34
FONT_SIZE_SETTINGS_TITLE = 34

# ---------------------------------------------------------------------------
# UI layout
# ---------------------------------------------------------------------------
UI_MARGIN = 36
UI_HUD_HEIGHT = 112
UI_TIMER_BAR_WIDTH = 360
UI_TIMER_BAR_HEIGHT = 6
UI_TIMER_LOW_THRESHOLD = 5.0
UI_HEART_SIZE = 15
UI_HEART_GAP = 8
UI_HEART_TOP = 46

UI_BUTTON_WIDTH = 320
UI_BUTTON_HEIGHT = 54
UI_BUTTON_GAP = 18
UI_BUTTON_BORDER = 2
UI_SETTINGS_PANEL_WIDTH = 620
UI_SETTINGS_PANEL_HEIGHT = 484
UI_PANEL_PADDING = 32
