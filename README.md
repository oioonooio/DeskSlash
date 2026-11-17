<div align="center">

# Desktop Slash

**把 Windows 桌面变成一场街机切割游戏。**

你的桌面图标会飞起来，用鼠标划过去把它们切开。

![platform](https://img.shields.io/badge/platform-Windows%2010%20%7C%2011-0078D6?logo=windows&logoColor=white)
![python](https://img.shields.io/badge/python-3.11%2B-3776AB?logo=python&logoColor=white)
![pygame](https://img.shields.io/badge/pygame-2.6-4B8BBE)

[![下载 DesktopSlash.exe](https://img.shields.io/badge/%E4%B8%8B%E8%BD%BD-DesktopSlash.exe-2ea043?style=for-the-badge&logo=windows&logoColor=white)](https://github.com/oioonooio/DeskSlash/releases/latest/download/DesktopSlash.exe)
[![最新版本](https://img.shields.io/github/v/release/oioonooio/DeskSlash?style=for-the-badge&color=0078D6&label=%E6%9C%80%E6%96%B0%E7%89%88%E6%9C%AC)](https://github.com/oioonooio/DeskSlash/releases/latest)

**不用装 Python，不用配环境：下载单个 EXE，双击就能玩。**

<img src="docs/images/main-menu.png" alt="Desktop Slash 主菜单" width="100%">

<sub><a href="#演示视频">演示视频</a> · <a href="#下载-exe">下载 EXE</a> · <a href="#从源码运行">从源码运行</a> · <a href="#玩法">玩法</a> · <a href="#常见问题">常见问题</a></sub>

</div>

## 简介

Desktop Slash 不是窗口里的游戏。启动后，它会在桌面上铺一层透明覆盖层，读取你**真实的桌面图标**，临时隐藏图标本体，同时保留你的壁纸和任务栏。成批图标从屏幕底部飞起，按住左键快速划动即可把它们切成两半。

退出时会自动恢复桌面图标——不管是正常退出、异常崩溃，还是看门狗兜底。游戏不会移动、删除或重命名任何桌面文件。

## 演示视频

[![Desktop Slash 25 秒演示](docs/video/cover-16x9.png)](docs/video/deskslash-promo-16x9.mp4)

<sub>25 秒实机演示：真实桌面、开局倒计时、划切连击与结算。点击封面播放；竖屏版见 [9:16](docs/video/deskslash-promo-9x16.mp4)。</sub>

## 特性

- **真实图标** — 通过 Windows Shell 读取 256 px 图标，而不是内置素材包
- **桌面即场地** — 透明无边框覆盖层，壁纸与任务栏保持原样
- **街机玩法** — 90 秒一局、3 条命、连击倍率、炸弹
- **手感反馈** — 刀光轨迹、碎片、粒子、飘分、震屏、扫描线
- **中英双语** — 设置里即时切换，无需重启
- **安全退出** — 统一退出流程 + 看门狗，崩溃后也能恢复图标
- **不抢焦点** — 切到其他应用自动暂停并释放鼠标，不会把你强行拉回游戏

## 游戏画面

<table>
  <tr>
    <td width="50%"><img src="docs/images/gameplay.png" alt="切割图标"></td>
    <td width="50%"><img src="docs/images/slash-effect.png" alt="刀光轨迹"></td>
  </tr>
  <tr>
    <td align="center"><sub>划动切割，图标分裂并飘出得分</sub></td>
    <td align="center"><sub>刀光轨迹与拖尾</sub></td>
  </tr>
  <tr>
    <td width="50%"><img src="docs/images/combo.png" alt="连击"></td>
    <td width="50%"><img src="docs/images/desktop-mode.png" alt="桌面模式"></td>
  </tr>
  <tr>
    <td align="center"><sub>连击倍率与碎片特效</sub></td>
    <td align="center"><sub>真实桌面：壁纸、任务栏与飞起的图标</sub></td>
  </tr>
</table>

## 快速开始

### 下载 EXE

推荐方式：不用配置任何环境。

| 项目 | 说明 |
| --- | --- |
| 下载 | [DesktopSlash.exe](https://github.com/oioonooio/DeskSlash/releases/latest/download/DesktopSlash.exe)（约 23 MB，最新版 [1.0.0](https://github.com/oioonooio/DeskSlash/releases/latest)） |
| 运行 | 双击 EXE，主菜单选「开始游戏」，3-2-1 倒计时后进入桌面 |
| 需要 | 无。不需要 Python、pip 或任何第三方库 |
| 卸载 | 删除 EXE 即可；如需清空存档，再删除 `%APPDATA%\DesktopSlash\` |

首次运行时 Windows SmartScreen 可能提示「Windows 已保护你的电脑」，点 **更多信息 → 仍要运行** 即可。EXE 未做代码签名，部分杀毒软件可能对 PyInstaller 单文件误报，添加信任即可。

系统要求：Windows 10 / 11 x64。存档、设置与日志都写在 `%APPDATA%\DesktopSlash\`，不会写入程序目录。

## 从源码运行

适合开发、调试或二次修改，需要 Python 3.11+：

| 项目 | 要求 |
| --- | --- |
| 系统 | Windows 10 / 11，x64 |
| Python | 3.11 或更高（开发与验证使用 3.11.2） |
| 依赖 | pygame 2.6.x、Pillow 10+、pywin32 |

```bash
git clone https://github.com/oioonooio/DeskSlash.git
cd DeskSlash

py -3.11 -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

python main.py --overlay
```

启动后桌面图标会被临时隐藏，壁纸保持不变；退出时恢复。

可用参数：

| 参数 | 作用 |
| --- | --- |
| `--overlay` | 桌面覆盖层模式（推荐） |
| `--window` | 普通窗口模式，便于调试 |
| `--monitor N` | 指定显示器 |
| `--self-test` | 运行内置自检后退出 |

## 操作

| 操作 | 按键 |
| --- | --- |
| 移动刀锋 | 鼠标移动 |
| 切割 | 按住鼠标左键快速划动（≥ 420 px/s） |
| 暂停 / 继续 | `Esc` 或 `P` |
| 菜单选择 / 确认 | `↑` `↓` / `Enter` |
| 暂停时返回主菜单 | `M` |
| 暂停时退出 | `Q` |
| 紧急退出（任意状态） | `Ctrl + Shift + Q` |

暂停只释放鼠标，不恢复桌面图标；切出游戏再切回来也不会自动继续。

## 玩法

- 每局 **90 秒**，初始 **3 条命**。
- 切中图标得 **10 分 × 连击倍率**，连击间隔 1.7 秒内继续切中即可累积，倍率最高 ×5。
- 漏掉图标或切到炸弹扣 1 条命，连击清零。
- 炸弹在开局 6 秒后出现，随时间越来越密集。
- 时间耗尽或生命归零时结算，最高分自动保存。

## 技术实现

- **透明覆盖层**：`WS_EX_LAYERED + LWA_COLORKEY`，键色 `(1, 0, 2)` 全透明，桌面只留下游戏对象
- **鼠标接管**：一个近乎不可见的输入盾窗转发鼠标消息；暂停时切换为 `WS_EX_TRANSPARENT`，桌面可正常操作
- **图标读取**：`IShellItemImageFactory` 获取 256 px 图标，等比缩放并保留透明通道
- **桌面隐藏**：校验 `SysListView32` 属主为 `explorer.exe` 后 `ShowWindow(SW_HIDE)`；恢复前写标记文件，正常退出、异常、`atexit` 与看门狗均可恢复
- **焦点管理**：`FocusManager` 综合 SDL 焦点事件、`WM_ACTIVATE` 与 0.2 秒 `GetForegroundWindow` 轮询；后台降到 15 FPS，从不调用 `SetForegroundWindow` 抢焦点
- **统一退出**：`SHUTTING_DOWN → RESTORING_DESKTOP → DESTROYING_WINDOWS → RELEASING_RESOURCES → STOPPED`，5 秒预算，单步失败不中断

## 项目结构

```
DesktopSlash/
├─ main.py                 # 入口与命令行参数
├─ game_config.py          # 全部可调参数
├─ core/                   # 主循环、状态机、焦点、存档、退出
├─ desktop/                # 桌面图标读取、壁纸、隐藏与恢复
├─ gameplay/               # 图标生成、切割检测、炸弹、连击
├─ physics/                # 抛射与阻尼
├─ effects/                # 刀光、碎片、粒子、飘分
├─ ui/                     # 菜单、HUD、设置、字体
├─ window/                 # 覆盖层、输入盾窗、窗口管理
├─ localization/           # 中英文翻译
├─ audio/                  # 代码合成音效
├─ assets/                 # 图标资源
├─ docs/images/            # README 截图
├─ docs/video/             # 演示视频与封面
├─ test_*.py               # 自动化与实机测试
└─ DesktopSlash.spec       # PyInstaller 打包配置
```

## 测试

```bash
python test_focus.py             # 焦点状态机（无头）
python test_gameplay.py          # 切割与得分
python test_effects.py           # 特效
python test_i18n.py              # 中英切换
python test_shutdown.py          # 退出流程
python test_desktop_background.py
```

需要真实桌面的测试会接管鼠标和前台窗口，请在空闲时运行：

```bash
python test_focus_live.py --cycles 4
python test_focus_live.py --cycles 20 --no-screens
```

## 打包

```bat
build_exe.bat
```

生成 `dist\DesktopSlash.exe`（单文件、无控制台），并自动运行 `--self-test` 自检。

## 数据与日志

| 内容 | 路径 |
| --- | --- |
| 存档与设置 | `%APPDATA%\DesktopSlash\save.json` |
| 运行日志 | `%APPDATA%\DesktopSlash\desktop_slash.log` |
| 桌面恢复记录 | `%APPDATA%\DesktopSlash\desktop_restore.log` |

所有用户数据都在仓库之外，不会被提交。

## 已知限制

- 仅支持 Windows 10 / 11 x64。
- 部分 UWP / 商店应用不提供 Shell 图标，会使用内置回退图标。
- 游戏运行期间桌面图标不可见；请勿用任务管理器强杀进程，正常退出或紧急退出会恢复桌面。

## 常见问题

**EXE 需要先安装 Python 吗？**

不需要。EXE 已经把 Python 解释器和依赖一起打包，系统只需要 Windows 10 / 11 x64。

**双击后提示「Windows 已保护你的电脑」或被杀毒软件拦截？**

EXE 没有代码签名，SmartScreen 会拦截：点「更多信息 → 仍要运行」。PyInstaller 单文件偶尔会被误报，添加信任即可。

**退出后桌面图标没回来？**

正常退出、`Esc` 菜单退出和 `Ctrl + Shift + Q` 紧急退出都会恢复图标；程序崩溃时由看门狗子进程兜底。请避免从任务管理器强杀进程。

**会读取或上传我的桌面内容吗？**

游戏只在本地读取桌面图标图像来生成游戏对象，不联网、不上传任何文件；存档与日志都保存在 `%APPDATA%\DesktopSlash\`。

## 许可证

仓库暂未添加开源许可证，默认保留所有权利。如需转载或二次分发，请先联系作者。
