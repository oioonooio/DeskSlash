"""Standalone read-only test for Desktop Slash stage 1.

Run from the project root:

    python test_desktop_icons.py                # interactive Pygame window
    python test_desktop_icons.py --snapshot     # render PNGs and exit
    python test_desktop_icons.py --auto-quit 3  # interactive window for 3s

The program only reads the desktop: it never moves, renames or deletes any
desktop icon, file or shortcut.
"""

from __future__ import annotations

import argparse
import datetime as dt
import platform
import re
import sys
from pathlib import Path

import pygame

from desktop.desktop_interface import (
    DesktopIcon,
    DesktopInterface,
    DesktopReadResult,
    enable_dpi_awareness,
)
from desktop.errors import DesktopReadError

WINDOW_SIZE = (1600, 1000)
CAPTION = "Desktop Slash - Stage 1 Desktop Icon Read Test (read-only)"

BG = (16, 18, 26)
BG_GRID = (24, 27, 38)
PANEL = (30, 34, 46)
PANEL_LIGHT = (40, 45, 60)
CHECKER_A = (58, 63, 78)
CHECKER_B = (84, 90, 108)
TEXT = (230, 235, 245)
MUTED = (146, 156, 178)
ACCENT = (104, 226, 190)
WARN = (255, 186, 96)
ERROR = (255, 120, 120)

HEADER_H = 104
FOOTER_H = 38
CELL_W = 112
CELL_H = 88

FONT_FAMILIES = "microsoftyahei,msyh,simhei,segoeui,arial"


def _elide(text: str, font: pygame.font.Font, width: int) -> str:
    if font.size(text)[0] <= width:
        return text
    suffix = "..."
    while text and font.size(text + suffix)[0] > width:
        text = text[:-1]
    return text + suffix


def _safe_filename(name: str, limit: int = 48) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")
    return (cleaned or "unnamed")[:limit]


def _draw_checker(
    surface: pygame.Surface, rect: pygame.Rect, cell: int = 8
) -> None:
    surface.fill(CHECKER_A, rect)
    row = 0
    y = rect.top
    while y < rect.bottom:
        column = row % 2
        x = rect.left
        while x < rect.right:
            if column:
                pygame.draw.rect(
                    surface,
                    CHECKER_B,
                    (x, y, min(cell, rect.right - x), min(cell, rect.bottom - y)),
                )
            column ^= 1
            x += cell
        row += 1
        y += cell


class FontBook:
    def __init__(self) -> None:
        path = pygame.font.match_font(FONT_FAMILIES)
        self.path = path

        def make(size: int, bold: bool = False) -> pygame.font.Font:
            font = pygame.font.Font(path, size) if path else pygame.font.Font(None, size)
            font.set_bold(bold)
            return font

        self.title = make(26, True)
        self.body = make(16)
        self.small = make(13)
        self.tiny = make(11)
        self.icon_name = make(13)

    @property
    def description(self) -> str:
        return self.path or "pygame default font (CJK glyphs may be missing)"


class IconViewer:
    def __init__(
        self,
        screen: pygame.Surface,
        result: DesktopReadResult,
        dpi_mode: str,
        output_dir: Path,
    ) -> None:
        self.screen = screen
        self.result = result
        self.dpi_mode = dpi_mode
        self.output_dir = output_dir
        self.fonts = FontBook()
        self.view = "layout"
        self.page = 0
        self._layout_hits: list[tuple[pygame.Rect, DesktopIcon]] = []
        self._scale = 1.0

    # ------------------------------------------------------------------
    # Data
    # ------------------------------------------------------------------
    def set_result(self, result: DesktopReadResult) -> None:
        self.result = result
        self.page = 0

    def pages(self) -> int:
        area = self._content_rect()
        per_page = self._per_page(area)
        return max(1, (len(self.result.icons) + per_page - 1) // per_page)

    def _content_rect(self) -> pygame.Rect:
        return pygame.Rect(
            0,
            HEADER_H,
            self.screen.get_width(),
            self.screen.get_height() - HEADER_H - FOOTER_H,
        )

    @staticmethod
    def _per_page(area: pygame.Rect) -> int:
        cols = max(1, (area.width - 32) // CELL_W)
        rows = max(1, (area.height - 32) // CELL_H)
        return cols * rows

    # ------------------------------------------------------------------
    # Chrome
    # ------------------------------------------------------------------
    def _draw_header(self) -> None:
        screen = self.screen
        pygame.draw.rect(screen, PANEL, (0, 0, screen.get_width(), HEADER_H))
        pygame.draw.line(
            screen,
            ACCENT,
            (0, HEADER_H - 2),
            (screen.get_width(), HEADER_H - 2),
            2,
        )
        title = self.fonts.title.render(
            "Desktop Slash · 阶段 1 桌面图标读取测试", True, TEXT
        )
        screen.blit(title, (24, 14))

        total = self.result.total_items
        ok = len(self.result.icons)
        failed = len(self.result.errors)
        summary = (
            f"图标: {ok} / {total} 读取成功 · {failed} 跳过 · "
            f"ListView HWND 0x{self.result.listview_hwnd:X} · "
            f"屏幕 {self.result.screen_size[0]}x{self.result.screen_size[1]} · "
            f"DPI {self.dpi_mode}"
        )
        screen.blit(self.fonts.body.render(summary, True, TEXT), (24, 50))

        notice = (
            "只读测试：仅枚举和读取图标，不移动、不重命名、不修改或删除任何桌面项目或文件。"
        )
        screen.blit(self.fonts.small.render(notice, True, WARN), (24, 76))

    def _draw_footer(self) -> None:
        screen = self.screen
        top = screen.get_height() - FOOTER_H
        pygame.draw.rect(screen, PANEL, (0, top, screen.get_width(), FOOTER_H))
        hint = (
            "Tab 切换视图 · S 保存截图 · R 重新读取 · ←/→ 翻页 · ESC 退出"
        )
        screen.blit(
            self.fonts.small.render(hint, True, MUTED), (24, top + 10)
        )
        out = f"输出目录: {self.output_dir}"
        text = self.fonts.tiny.render(_elide(out, self.fonts.tiny, 620), True, MUTED)
        screen.blit(text, (screen.get_width() - text.get_width() - 24, top + 12))

    def _draw_tooltip(self, icon: DesktopIcon, mouse: tuple[int, int]) -> None:
        lines = [
            icon.name,
            f"screen=({icon.screen_position[0]}, {icon.screen_position[1]})  "
            f"image={icon.image_size[0]}x{icon.image_size[1]}  "
            f"alpha={icon.alpha_range[0]}..{icon.alpha_range[1]}",
            f"{icon.image_source}: {icon.shell_path or '-'}",
        ]
        rendered = [
            self.fonts.small.render(lines[0], True, TEXT),
            self.fonts.tiny.render(lines[1], True, MUTED),
            self.fonts.tiny.render(
                _elide(lines[2], self.fonts.tiny, 560), True, MUTED
            ),
        ]
        width = max(item.get_width() for item in rendered) + 20
        height = sum(item.get_height() for item in rendered) + 18
        x = min(mouse[0] + 16, self.screen.get_width() - width - 8)
        y = min(mouse[1] + 16, self.screen.get_height() - height - 8)
        box = pygame.Rect(x, y, width, height)
        pygame.draw.rect(self.screen, (48, 54, 70), box, border_radius=6)
        pygame.draw.rect(self.screen, ACCENT, box, 1, border_radius=6)
        cursor_y = y + 8
        for item in rendered:
            self.screen.blit(item, (x + 10, cursor_y))
            cursor_y += item.get_height() + 3

    # ------------------------------------------------------------------
    # Views
    # ------------------------------------------------------------------
    def _render_background(self, area: pygame.Rect) -> None:
        self.screen.fill(BG, area)
        step = 40
        for x in range(area.left, area.right, step):
            pygame.draw.line(self.screen, BG_GRID, (x, area.top), (x, area.bottom))
        for y in range(area.top, area.bottom, step):
            pygame.draw.line(self.screen, BG_GRID, (area.left, y), (area.right, y))

    def render_layout(self) -> None:
        area = self._content_rect()
        area.y += 30
        area.height -= 30
        self._render_background(area)
        icons = self.result.icons
        self._layout_hits = []

        if not icons:
            self._centered_message(area, "没有读取到可显示的桌面图标")
            return

        xs = [icon.screen_position[0] for icon in icons]
        ys = [icon.screen_position[1] for icon in icons]
        icon_w = max(icon.image_size[0] for icon in icons)
        icon_h = max(icon.image_size[1] for icon in icons)
        min_x, max_x = min(xs), max(xs) + icon_w
        min_y, max_y = min(ys), max(ys) + icon_h
        span_x = max(1, max_x - min_x)
        span_y = max(1, max_y - min_y)

        margin = 48
        scale = min(
            (area.width - margin * 2) / span_x,
            (area.height - margin * 2) / span_y,
            1.5,
        )
        self._scale = scale
        offset_x = area.left + (area.width - span_x * scale) / 2 - min_x * scale
        offset_y = area.top + (area.height - span_y * scale) / 2 - min_y * scale

        for icon in icons:
            x = int(offset_x + icon.screen_position[0] * scale)
            y = int(offset_y + icon.screen_position[1] * scale)
            size = max(12, int(round(icon.image_size[0] * scale)))
            scaled = pygame.transform.smoothscale(icon.image, (size, size))
            shadow = scaled.copy()
            shadow.fill((0, 0, 0, 80), special_flags=pygame.BLEND_RGBA_MULT)
            self.screen.blit(shadow, (x + 2, y + 3))
            self.screen.blit(scaled, (x, y))
            self._layout_hits.append((pygame.Rect(x, y, size, size), icon))

        label = (
            f"桌面布局视图 · 图标按真实屏幕坐标绘制 · 缩放 {scale:.2f}x"
        )
        self.screen.blit(
            self.fonts.small.render(label, True, MUTED), (area.left + 20, area.top + 14)
        )

        mouse = pygame.mouse.get_pos()
        for rect, icon in self._layout_hits:
            if rect.collidepoint(mouse):
                self._draw_tooltip(icon, mouse)
                break

    def render_grid(self) -> None:
        area = self._content_rect()
        self._render_background(area)
        icons = self.result.icons
        if not icons:
            self._centered_message(area, "没有读取到可显示的桌面图标")
            return

        per_page = self._per_page(area)
        pages = max(1, (len(icons) + per_page - 1) // per_page)
        self.page = max(0, min(self.page, pages - 1))
        start = self.page * per_page
        visible = icons[start : start + per_page]
        cols = max(1, (area.width - 32) // CELL_W)
        grid_x = area.left + 16
        grid_y = area.top + 40

        for number, icon in enumerate(visible):
            col = number % cols
            row = number // cols
            cell = pygame.Rect(
                grid_x + col * CELL_W,
                grid_y + row * CELL_H,
                CELL_W - 6,
                CELL_H - 6,
            )
            pygame.draw.rect(self.screen, PANEL, cell, border_radius=5)
            thumb_box = pygame.Rect(0, 0, 56, 56)
            thumb_box.center = (cell.centerx, cell.top + 30)
            _draw_checker(self.screen, thumb_box, 8)

            icon_rect = icon.image.get_rect(center=thumb_box.center)
            self.screen.blit(icon.image, icon_rect)

            name = _elide(icon.name, self.fonts.icon_name, cell.width - 8)
            name_surface = self.fonts.icon_name.render(name, True, TEXT)
            self.screen.blit(
                name_surface,
                (cell.centerx - name_surface.get_width() // 2, cell.top + 60),
            )
            coords = f"({icon.screen_position[0]}, {icon.screen_position[1]})"
            coords_surface = self.fonts.tiny.render(coords, True, MUTED)
            self.screen.blit(
                coords_surface,
                (cell.centerx - coords_surface.get_width() // 2, cell.top + 73),
            )

        label = (
            f"缩略图视图 · 第 {self.page + 1}/{pages} 页 · "
            f"棋盘格表示透明像素 · 共 {len(icons)} 个图标"
        )
        self.screen.blit(
            self.fonts.small.render(label, True, MUTED), (area.left + 20, area.top + 14)
        )

    def _centered_message(self, area: pygame.Rect, message: str) -> None:
        surface = self.fonts.body.render(message, True, MUTED)
        self.screen.blit(
            surface,
            (
                area.centerx - surface.get_width() // 2,
                area.centery - surface.get_height() // 2,
            ),
        )

    def render(self) -> None:
        self.screen.fill(BG)
        if self.view == "layout":
            self.render_layout()
        else:
            self.render_grid()
        self._draw_header()
        self._draw_footer()

    # ------------------------------------------------------------------
    # Output helpers
    # ------------------------------------------------------------------
    def save_screenshots(self, stem: str | None = None) -> list[Path]:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        saved: list[Path] = []
        if stem is not None:
            view = self.view
            self.view = "layout"
            self.render()
            path = self.output_dir / f"{stem}_layout.png"
            pygame.image.save(self.screen, str(path))
            saved.append(path)
            self.view = "grid"
            self.render()
            path = self.output_dir / f"{stem}_thumbnails.png"
            pygame.image.save(self.screen, str(path))
            saved.append(path)
            self.view = view
            self.render()
            return saved

        self.render()
        path = self.output_dir / f"test_desktop_{self.view}.png"
        pygame.image.save(self.screen, str(path))
        saved.append(path)
        return saved


def export_icons(result: DesktopReadResult, output_dir: Path) -> Path:
    icons_dir = output_dir / "icons"
    icons_dir.mkdir(parents=True, exist_ok=True)
    for old in icons_dir.glob("*.png"):
        old.unlink()
    for icon in result.icons:
        filename = f"{icon.index:03d}_{_safe_filename(icon.name)}.png"
        pygame.image.save(icon.image, str(icons_dir / filename))
    return icons_dir


def write_report(
    result: DesktopReadResult,
    dpi_mode: str,
    output_dir: Path,
    elapsed: float,
) -> Path:
    lines: list[str] = []
    lines.append("Desktop Slash - 阶段 1 桌面图标读取测试报告")
    lines.append("=" * 72)
    lines.append(f"时间: {dt.datetime.now():%Y-%m-%d %H:%M:%S}")
    lines.append(f"平台: {platform.platform()}")
    lines.append(f"Python: {platform.python_version()}   Pygame: {pygame.version.ver}")
    lines.append(f"DPI 感知: {dpi_mode}")
    lines.append(
        f"屏幕尺寸(物理像素): {result.screen_size[0]}x{result.screen_size[1]}"
    )
    lines.append(f"桌面 ListView HWND: 0x{result.listview_hwnd:X}")
    lines.append(f"ListView 项目总数: {result.total_items}")
    lines.append(f"成功读取图标: {len(result.icons)}")
    lines.append(f"跳过/失败: {len(result.errors)}")
    lines.append(f"读取耗时: {elapsed:.2f} 秒")

    translucent = sum(
        1 for icon in result.icons if icon.alpha_range[0] < 255
    )
    lines.append(f"包含透明/半透明像素的图标: {translucent}/{len(result.icons)}")
    lines.append("")
    lines.append("读取失败的项目:")
    if result.errors:
        for error in result.errors:
            lines.append(f"  - {error.format()}")
    else:
        lines.append("  (无)")
    lines.append("")
    lines.append("图标明细 (屏幕坐标为物理像素, 左上角):")
    for icon in result.icons:
        lines.append(
            f"[{icon.index:03d}] name={icon.name} | "
            f"screen=({icon.screen_position[0]}, {icon.screen_position[1]}) | "
            f"image={icon.image_size[0]}x{icon.image_size[1]} | "
            f"alpha={icon.alpha_range[0]}..{icon.alpha_range[1]} | "
            f"source={icon.image_source} | "
            f"shell={icon.shell_path or '-'}"
        )

    path = output_dir / "test_desktop_icons_report.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def print_summary(
    result: DesktopReadResult, dpi_mode: str, elapsed: float
) -> None:
    print("=" * 72)
    print("Desktop Slash · 阶段 1 桌面图标读取测试")
    print("=" * 72)
    print(f"DPI 感知: {dpi_mode}")
    print(
        f"屏幕尺寸(物理像素): {result.screen_size[0]}x{result.screen_size[1]}"
    )
    print(f"桌面 ListView 句柄: 0x{result.listview_hwnd:X}")
    print(f"ListView 项目总数: {result.total_items}")
    print(f"成功读取图标: {len(result.icons)}")
    print(f"跳过/失败: {len(result.errors)}")
    print(f"读取耗时: {elapsed:.2f} 秒")
    print()
    print("图标明细 (屏幕坐标 x, y | 图像尺寸 | alpha 范围 | 来源):")
    for icon in result.icons:
        print(
            f"[{icon.index:03d}] {icon.name} | "
            f"screen=({icon.screen_position[0]}, {icon.screen_position[1]}) | "
            f"image={icon.image_size[0]}x{icon.image_size[1]} | "
            f"alpha={icon.alpha_range[0]}..{icon.alpha_range[1]} | "
            f"{icon.image_source}"
        )
    if result.errors:
        print()
        print(f"读取失败并被跳过的图标 ({len(result.errors)}):")
        for error in result.errors:
            print(f"  - {error.format()}")
    print()


def main(argv: list[str] | None = None) -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

    parser = argparse.ArgumentParser(
        description="Read Windows desktop icons (read-only) and show them in Pygame."
    )
    parser.add_argument(
        "--snapshot",
        action="store_true",
        help="render the two views to PNG, then exit without interaction",
    )
    parser.add_argument(
        "--auto-quit",
        type=float,
        default=None,
        metavar="SECONDS",
        help="close the interactive window after N seconds",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(__file__).resolve().parent / "test_output",
        help="directory for reports, icon PNGs and screenshots",
    )
    args = parser.parse_args(argv)

    dpi_mode = enable_dpi_awareness()
    pygame.init()
    pygame.display.set_caption(CAPTION)
    flags = pygame.HIDDEN if args.snapshot else 0
    screen = pygame.display.set_mode(WINDOW_SIZE, flags)

    started = dt.datetime.now()
    try:
        result = DesktopInterface().read_desktop_icons()
    except DesktopReadError as exc:
        pygame.quit()
        print(f"读取桌面图标失败: {exc}")
        return 1
    elapsed = (dt.datetime.now() - started).total_seconds()

    print_summary(result, dpi_mode, elapsed)

    output_dir = args.out.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    icons_dir = export_icons(result, output_dir)
    report = write_report(result, dpi_mode, output_dir, elapsed)
    print(f"图标 PNG 已保存: {icons_dir}")
    print(f"UTF-8 报告已保存: {report}")
    print(f"字体: {FontBook().description}")

    if not result.icons:
        pygame.quit()
        print("没有读取到任何图标, 无法渲染测试视图。")
        return 1

    viewer = IconViewer(screen, result, dpi_mode, output_dir)

    if args.snapshot:
        saved = viewer.save_screenshots("test_desktop")
        viewer.render()
        pygame.display.flip()
        for path in saved:
            print(f"截图已保存: {path}")
        pygame.quit()
        print("快照模式完成。")
        return 0

    clock = pygame.time.Clock()
    running = True
    elapsed_loop = 0.0
    message = ""
    while running:
        dt_seconds = clock.tick(60) / 1000.0
        elapsed_loop += dt_seconds
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False
                elif event.key == pygame.K_TAB:
                    viewer.view = "grid" if viewer.view == "layout" else "layout"
                    message = ""
                elif event.key in (pygame.K_RIGHT, pygame.K_pagedown):
                    if viewer.view == "grid":
                        viewer.page = min(viewer.page + 1, viewer.pages() - 1)
                elif event.key in (pygame.K_LEFT, pygame.K_pageup):
                    if viewer.view == "grid":
                        viewer.page = max(viewer.page - 1, 0)
                elif event.key == pygame.K_s:
                    saved = viewer.save_screenshots("test_desktop")
                    message = f"已保存截图: {saved[-1]}"
                    print(message)
                elif event.key == pygame.K_r:
                    try:
                        fresh = DesktopInterface().read_desktop_icons()
                    except DesktopReadError as exc:
                        message = f"重新读取失败: {exc}"
                        print(message)
                    else:
                        viewer.set_result(fresh)
                        print_summary(fresh, dpi_mode, 0.0)
                        icons_dir = export_icons(fresh, output_dir)
                        write_report(fresh, dpi_mode, output_dir, 0.0)
                        message = f"已重新读取: {len(fresh.icons)} 个图标"
                        print(message)

        viewer.render()
        if message:
            surface = viewer.fonts.small.render(message, True, ACCENT)
            screen.blit(
                surface,
                (
                    screen.get_width() - surface.get_width() - 24,
                    HEADER_H + 18,
                ),
            )
        pygame.display.flip()

        if args.auto_quit is not None and elapsed_loop >= args.auto_quit:
            running = False

    pygame.quit()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
