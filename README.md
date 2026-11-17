# Desktop Slash

Windows 桌面图标切割游戏（Desktop Ninja 风格）。

当前版本为 **阶段 6（放大图标、超高抛射与真正的桌面背景模式）+ 2026-11-17 迭代修复（中英切换、统一退出、壁纸零噪点、焦点/切换应用）**：启动后保留 Windows 壁纸，临时隐藏真实桌面图标，大量放大的图标从屏幕底部高高飞起，整块桌面就是切割场地；暂停只释放鼠标、不恢复图标；正常退出、异常退出与看门狗兜底都会恢复图标和桌面操作。仍然只有**一个游戏模式**。

> 阶段 1–5 对桌面**只读取**。阶段 6 为“桌面背景模式”增加了唯一一项桌面写操作：临时隐藏 `SysListView32` 桌面图标控件的**窗口显示状态**（`ShowWindow(SW_HIDE / SW_SHOWNA)`），并在退出时恢复。不移动、不删除、不改名、不改变排列/间距、不写注册表、不重启 Explorer、不修改任何桌面文件。

## 本次迭代修复（2026-11-17）

在阶段 6 的基础上只做三处底层修复，没有新增模式、没有更换技术栈：

- **完整中英切换**：新增 `localization/` 模块（`LanguageManager` + `zh_CN.json` / `en_US.json`，各 71 个键，键集合完全一致），所有界面文本统一走 `t("menu.start")` 取词。默认简体中文，设置面板新增 `语言 / Language` 行，随时切换后菜单、倒计时、HUD、暂停、设置、结算、首启引导、退出确认、错误提示、统计全部立即重绘，无需重启；选择写入 `save.json` 的 `language` 字段。非法/缺失/损坏值一律回退 `zh_CN`。中文使用微软雅黑/等线等系统字体并逐字符校验字形，英文下双语标签也能正常显示中文（不再出现 `□□`）。
- **统一退出流程**：所有退出来源（菜单 EXIT、结算 EXIT、暂停 Q、窗口关闭、系统关闭、未捕获异常、`Ctrl + Shift + Q` 紧急退出）都只调用 `Game.request_shutdown()`，按 `SHUTTING_DOWN → RESTORING_DESKTOP → DESTROYING_WINDOWS → RELEASING_RESOURCES → STOPPED` 顺序执行，退出请求幂等。每一步独立 `try/except`，单步失败只记录错误并继续；`SHUTDOWN_BUDGET_SECONDS = 5.0` 总预算防止卡死；**桌面恢复永远先于窗口销毁**，所以不会再出现“窗口没了、图标还藏着”的偶发卡死。`Ctrl + Shift + Q` 由守护线程用 `GetAsyncKeyState` 轮询，即使主循环卡住也能在 3 秒宽限后先恢复桌面再 `os._exit(0)`。
- **壁纸零噪点**：背景改为直接使用 Windows 自己合成的壁纸位图（`%APPDATA%\Microsoft\Windows\Themes\TranscodedWallpaper`）按显示器矩形裁切（`precomposed`），不再对壁纸做“再缩放”或任何滤镜；读取顺序为 `IDesktopWallpaper` 逐显示器 → 全局壁纸 → `SPI_GETDESKWALLPAPER` → 注册表 → 合成位图 → 纯色。新增 `test_wallpaper_fidelity.py` 做像素比对：本机 `mean=0.0000 / max=0`（逐字节一致），并输出 `game_backdrop_new.png` / `native_wallpaper_new.png` / 差值图用于复核。

对应的验证：`test_i18n.py`（8 项）、`test_shutdown.py`（11 项）、`test_wallpaper_fidelity.py`（样式 + 实时比对）全部通过，既有 10 个测试文件回归通过。

## 焦点/切换应用修复（2026-11-17）

修复“Alt+Tab 切到浏览器后游戏像卡死、画面停在最后一帧、鼠标被抢、只能用任务管理器结束”的问题。根因不是暂停逻辑，而是窗口层：

- 覆盖层一直停留在 `WS_EX_TOPMOST` 层，切走后仍盖在别的应用上，只显示最后一帧；
- 焦点状态只依赖 pygame 事件，SDL 事件缺失时没有任何兜底；
- 启动之外的 `SetForegroundWindow` 路径可能把游戏拉回前台；
- 后台仍按 60 FPS 渲染并持续转发鼠标消息。

修复后：

- **统一焦点状态机** `core/focus.py`：`FOREGROUND / FOCUS_LOST / PAUSED / BACKGROUND / RESTORING / SHUTTING_DOWN`，pygame 事件 + `WM_ACTIVATE/WM_SETFOCUS` 原生序号 + 0.2 秒轮询三路输入，带 0.2 秒失焦去抖和 0.05 秒恢复去抖，不会反复迁移或重复恢复。
- **切走**：立即暂停正在进行的回合、清空刀光/拖拽、`SetCapture(None)` + `ClipCursor(None)`、隐藏输入盾并把覆盖层移出 topmost（`HWND_NOTOPMOST` 后再 `HWND_BOTTOM`，避免停在普通层顶部遮挡其他窗口）、后台降到 15 FPS。整个过程中不调用任何强制抢前台 API。
- **切回**：只恢复 topmost、输入盾和鼠标；游戏保持暂停，等玩家按 `Esc`；不重建场景、不重新读取桌面图标、不重置分数/生命/进度；暂停前的鼠标按下和队列中的移动事件都会被丢弃，不会一回来就出现“卡住的刀”。
- **按键回声去重**：全局 `Esc` 轮询收到一次恢复按键后，0.3 秒内忽略 SDL 迟到的同一按键 `KEYDOWN`，一次按键不会“恢复后立刻又暂停”。
- **输入法（IME）修复**：pygame 默认开启 SDL 文本输入，在中文输入法下字母键会以 `VK_PROCESSKEY (0xE5)` 到达，暂停菜单的 `M`/`Q` 因此失效。显示创建后调用 `pygame.key.stop_text_input()` 断开 IME 上下文，所有按键恢复为正常虚拟键码。
- **退出**：全部入口（Alt+F4/WM_CLOSE、暂停 Q、菜单退出、失焦/暂停/恢复中退出、Ctrl+Shift+Q）都走 `request_shutdown()`；关闭序列先恢复桌面再销毁窗口，即使主循环卡住，紧急热键线程也会在 3 秒宽限后先恢复桌面。
- **诊断日志**：`%APPDATA%\DesktopSlash\desktop_slash.log`，分类 `[FOCUS] [WINDOW] [INPUT] [GAME] [LOOP] [SHUTDOWN]`，只在状态迁移和按键/每 5 秒心跳时写入，不做逐帧日志；超过 2 MB 自动轮换。设置 `DESKTOP_SLASH_DEBUG=1` 可同时输出到 stderr。

验证：`test_focus.py`（29 项，无头焦点状态机/窗口恢复/退出）、`test_focus_live.py`（真实桌面，阶段 1–7：切走、使用其他应用后返回、11 秒后台帧率、暂停后往返、连续 20 次 Alt+Tab、失焦时 Ctrl+Shift+Q 退出、可选的 30 分钟压力循环），以及既有测试全部回归。

已知边界：置顶层被其他同样置顶的应用（如某些全屏游戏、部分安全软件弹窗）覆盖时，Windows 的 z-order 规则优先，游戏不会强行抢回；多显示器下覆盖层只覆盖启动时选中的那块显示器；紧急退出依赖 `GetAsyncKeyState` 轮询，若系统级键盘钩子吞掉了 `Ctrl+Shift+Q`，仍可用任务管理器结束（此时看门狗会在父进程消失后恢复桌面图标）。

## 阶段 6 已实现

- **图标全面放大**：普通图标改用 80 / 96 / 112 / 128 px 四档逻辑尺寸（权重 22% / 50% / 24% / 4%），每档再叠加 ±5% 随机抖动；同屏尺寸有变化，大目标更醒目。1080p / 96 DPI 下实际屏幕尺寸约 76–134 px，2560 × 1600 / 144 DPI 覆盖层下约 139–222 px
- **分辨率与 DPI 自适应**：`ui_scale = clamp(DPI/96, 0.75–3.0) × clamp(sqrt(min(W/1920, H/1080)), 1.00–1.40)`，保证任何分辨率下都不会把图标缩到 80 px 以下；水平速度按屏幕宽度缩放，宽屏不会变成近乎垂直的抛射
- **高清图标来源**：通过 `IShellItemImageFactory::GetImage` 向 Windows Shell 请求 **256 px** 图标，而不是把 48 px 系统大图标硬放大；图标按等比缩放，保留原始透明通道，炸弹也是原生 256 px 程序绘制
- **图标表现力**：图标独立呼吸缩放（幅度 2.8%、周期 1.9 秒、相位错开）、轮廓柔光（基于 alpha 掩码的四分之一分辨率模糊）、右下像素阴影；切割时的白色星芒与左右碎片沿用阶段 3 特效
- **按高度反解抛射**：图标从屏幕底部下方生成，按目标顶点比例反解初速度 `v0 = sqrt(2·g·rise / compensation)`；顶点目标 55%–75% 屏高，15% 概率出现 76%–82% 的近顶抛射。`compensation` 随屏幕高度线性修正（0.80 − (H−1080)×0.00006，夹在 0.72–0.86），抵消线性阻尼在高屏上多消耗的高度
- **自然弧线**：每图标独立重力系数、出生深度（0–6% 屏高）、方向与水平速度（30–190 × 屏宽系数，24% 概率向外侧飞），没有瞬移或方向突变；固定 1/120 秒步长下每步位移不超过初速度 × 步长
- **底部三段式生成**：把底部切成左/中/右三条出生带，每波轮换打乱，单个图标仍落在自己的带内；同波图标的最小水平间距按较大图标半径的 2.3 倍检查，保证可切割
- **真正的桌面背景**：启动时校验并隐藏真实桌面图标控件，覆盖层自行绘制**只读**壁纸（壁纸路径、纯色、平铺/填充样式来自系统设置，多显示器按各自壁纸裁剪），再叠加 12% 暗化，让桌面看起来“只有壁纸，没有图标”
- **安全隐藏与恢复**：`DesktopBackgroundManager` 只在确认 `Progman/WorkerW → SHELLDLL_DefView → SysListView32` 且属主为 `explorer.exe` 后才操作；先把原始可见性/样式写入标记文件，正常退出、初始化失败、运行异常、`atexit` 全部走幂等恢复
- **看门狗与单实例**：子进程看门狗等待父进程退出，若标记仍在且图标控件仍是隐藏状态就执行恢复；命名互斥锁阻止同时运行两个实例；崩溃恢复日志写入 `%APPDATA%\DesktopSlash\desktop_restore.log`
- **暂停语义**：`Esc / P` 暂停只把鼠标交还桌面，**图标保持隐藏**；继续后重新接管。菜单/结算/暂停失焦同样只释放鼠标，不会让真实图标中途闪现
- **新增测试**：`test_visual_upgrade.py`（9 项尺寸/高清/顶点/出生带/呼吸/光晕）、`test_desktop_background.py`（6 项无头 + 1 项真实覆盖层生命周期，含崩溃看门狗、旧标记恢复、单实例）、以及既有阶段 5 测试全部回归通过

## 阶段 5 已实现

- **透明无边框覆盖层**：默认创建一个覆盖所选显示器工作区的 `NOFRAME` 窗口，通过 `WS_EX_LAYERED + SetLayeredWindowAttributes(LWA_COLORKEY)` 把键色 `(1, 0, 2)` 设为完全透明；每帧先用键色清空场景再绘制，因此桌面上只留下游戏对象、刀光、粒子和 UI
- **鼠标输入与穿透互斥**：Windows 会让键色透明像素的鼠标事件直接落到桌面（即使 `WM_NCHITTEST` 返回 `HTCLIENT`），因此游戏接管时额外创建一个几乎不可见的输入盾窗（常驻 alpha = 1/255，视觉影响 0.4%，但每个像素都可命中），由它把鼠标移动、按下、松开消息按客户区坐标转发给 SDL 窗口（若 SDL 建立了鼠标捕获，则后续移动由捕获直接送达，盾窗不会重复转发）；暂停/退出时隐藏盾窗、设置 `WS_EX_TRANSPARENT` 并返回 `HTTRANSPARENT`，桌面完整恢复操作。两种模式互斥，绝不与鼠标捕获同时使用
- **暂停**：`Esc / P` 暂停，冻结倒计时、物理、特效和粒子，同时释放鼠标（`SetCapture(None)`、`ClipCursor(None)`）；暂停面板显示剩余时间与 `MOUSE RELEASED · DESKTOP INPUT ACTIVE`；`Esc / P` 继续、`M` 返回菜单、`Q` 退出。继续时会丢弃暂停前的鼠标移动，按住超过 0.35 秒的 Esc 不会自动继续
- **全局继续键**：暂停后用 `GetAsyncKeyState(VK_ESCAPE)` 轮询，即使用户点过桌面、窗口失去焦点也能直接按 Esc 继续
- **焦点丢失自动暂停**：游戏中窗口失去焦点会立即进入暂停并释放鼠标，避免在桌面上误切；菜单/倒计时/结算界面失焦时也会隐藏输入盾窗，重新聚焦后自动接管（暂停界面保持释放，等玩家按 Esc 继续）。窗口保留任务栏与 Alt+Tab 入口，随时能切回
- **多显示器与 DPI**：`EnumDisplayMonitors` + `GetMonitorInfoW` 枚举物理像素矩形，默认覆盖主显示器工作区（保留任务栏），可用 `--monitor N` 选择其他显示器；进程启用 Per-Monitor V2 DPI 感知，窗口尺寸与鼠标坐标均为物理像素
- **退出与崩溃恢复**：正常退出会还原扩展样式与原始 `WNDPROC`、隐藏窗口、释放捕获与光标裁剪；`atexit` + `WindowManager.emergency_restore()` 在异常退出时做同样的尽力恢复；崩溃日志写入 `%APPDATA%\DesktopSlash\crash.log`
- **性能**：文字渲染缓存（上限 512）、HUD 面板缓存、背景尘埃精灵缓存、图标缩放/阴影缓存（旋转代替每帧 `rotozoom`）、碰撞 AABB 预筛选、物理与图标列表原地压缩、每帧清空键色场景；桌面图标整个会话只读取一次。阶段 6 实测 2560 × 1528 覆盖层约 `update 0.10 ms + render/flip 13.6 ms`（CPU 估算约 73 FPS，取决于后台负载），5 分钟特效/粒子压力测试工作集增长 0.1 MB
- **覆盖层渲染适配**：覆盖层模式自动禁用背景合成波与 CRT 扫描线，半透明面板按近黑色混合（键色窗口的限制）；普通窗口模式保留完整背景与扫描线。阶段 6 起覆盖层先绘制只读壁纸背景，再绘制游戏内容
- **打包**：`assets/icon.png` / `assets/icon.ico`、`DesktopSlash.spec`、`version_info.txt`、`build_exe.bat`；打包为单文件窗口化 `dist\DesktopSlash.exe`，内置 `--self-test` 验证资源、字体、pywin32、桌面读取、覆盖层渲染路径与暂停输入交接
- **新增测试**：`test_overlay_window.py`（23 项真实 Win32 样式/输入盾/透明度/退出恢复）、`test_stage5_flow.py`（32 项完整流程）、`test_performance.py`（15 项性能与长时间内存）

## 阶段 4 已实现

- **开始界面**：`DESKTOP / SLASH` 像素标题、最高分、`START` / `SETTINGS` / `EXIT` 三个像素按钮；支持鼠标悬停点击和 `↑/↓ + Enter` 键盘选择，`Esc` 退出
- **设置面板**：模态遮罩 + 像素面板；音量 `−10% / +10%`、屏幕震动 `ON/OFF`、CRT 扫描线 `ON/OFF`、`语言 / Language`（简体中文 / English）、`BACK`；改动立即写入 JSON 并存效到当前画面，切换语言后所有界面立即换词，无需重启
- **倒计时**：`3 → 2 → 1 → GO!`，每个数字进入时从 1.34 倍缩小回 1.0 的弹出动画；每一步播放一次程序合成短音，`GO!` 使用上行双音；Space/Enter 可跳过
- **HUD**：当前分数、剩余时间与时间条、3 颗生命心、当前连击 + 连击倍率、历史最高分（`BEST`）；跨过旧最高分时 `BEST` 实时跟随本局分数
- **连击倍率**：连击 1–3 为 `x1`、4–6 为 `x2`、7–9 为 `x3`、10–12 为 `x4`、13+ 为 `x5`（上限 5）。每个普通图标基础 10 分 × 当前倍率，飘字显示实际得分
- **难度递增**：一条统一曲线随回合进度同时提高波次数量、飞行速度、生成频率和炸弹概率；无模式配置系统
- **结算页**：最终分数、本局切割数量、最大连击、最高分、`NEW HIGH SCORE` 提示，以及 `PLAY AGAIN` / `MAIN MENU` / `EXIT GAME` 三个按钮；重开时分数、生命、统计、图标、刀光、特效、粒子、震屏全部重置
- **JSON 存档**：默认 `%APPDATA%\DesktopSlash\save.json`，保存最高分与设置；临时文件 + `os.replace` 原子写入；文件缺失/损坏/字段越界时回退默认值
- **新增自动化测试 `test_game_system.py`**：12 项检查，6 张阶段 4 截图 + 1 张总览图

## 阶段 3 已实现

- **Retro Pixel Arcade 美术**：深色合成波背景（渐变、透视网格、星点、漂浮像素尘埃）、霓虹青/紫/橙/黄 HUD、非抗锯齿像素文字、CRT 扫描线
- **多层刀光**：紫色外辉光 + 青色中层 + 近白核心；轨迹从尾端向刀尖渐亮；松手后 0.24 秒淡出；高速采样点会喷出像素火花
- **图标切割**：旋转/缩放后的图标沿中线切成左右两半，两半反向飞出并带自旋、重力、淡出；每刀额外生成 8–20 个取自图标自身颜色的像素碎片；命中点有短暂的白色像素星芒
- **得分动画**：得分数字从命中点弹出、上浮、放大并淡出；阶段 4 起显示 `10 × 连击倍率` 的实际得分，连击越高字号/放大倍数/颜色越强
- **池化粒子系统**：固定 900 个粒子槽位，支持颜色、速度、方向、重力、生命周期、尺寸、透明度与像素吸附；粒子用尽时丢弃多余粒子而不是分配新对象
- **炸弹**：开局 6 秒后开始出现，每波最多 1 个，初始概率 18%（随难度曲线升至 48%）；切中后橙红像素火球、屏幕震动、短暂橙色闪光、52 个爆炸粒子和程序合成爆炸声；扣 1 条生命并中断连击，漏掉炸弹不扣命
- **连击**：1.7 秒内连续切割累计连击；`COMBO x2`、`COMBO x3`、`COMBO x5`、`GREAT COMBO x8/x13/...`；里程碑有专属大字播报、环形粒子、闪光，高连击追加屏震
- **生命周期管理**：`EffectManager` 最多 96 个活动特效，超限直接丢弃；粒子为固定容量对象池；刀光轨迹最多 32 点；环境尘埃固定 64 个；所有绘制均为程序生成，不依赖图片素材
- **特效与判定解耦**：特效只在渲染阶段绘制；屏震只移动最终画面，不改变鼠标坐标或碰撞几何；特效数量被填满时切割、计分和扣命仍按原逻辑运行
- **程序合成音效**：`slice` / `combo` / `bomb` / `miss` 由方波、正弦和噪声生成；没有可用音频设备时自动静音，不影响游戏
- **新增自动化测试 `test_effects.py`**：12 项检查、10 张特效截图、1 张总览图，可选实时演示模式

## 阶段 2 已实现

- `GameIcon` 独立对象：图像、位置、水平/垂直速度、重力、旋转角度/角速度、缩放、是否已切割、是否已漏掉
- 图标从窗口下方生成，向上抛出，带随机水平速度、重力、旋转和缩放；飞出屏幕后判定漏掉
- 波次生成：每波 3–5 个，间隔约 1.5 秒（含小幅抖动），同屏最多 12 个
- 每次生成都从已读取的桌面图标中随机选图并复制 Surface，创建全新的 `GameIcon` 和 `PhysicsBody`，不复用游戏对象
- 独立 `SlashDetector`：记录鼠标按下、移动、松开轨迹；只有达到速度阈值的线段才参与切割；线段与图标圆形碰撞区求交；一次划动可切割多个图标；每个图标只能计分一次；松开后刀光逐渐消失
- 切割反馈：图标立即消失；生成简单的左右两半碎片（带重力、旋转、淡出）；生成少量粒子；在切割位置显示 `+10`
- 规则：90 秒倒计时；3 条生命；普通图标 10 分；漏掉普通图标扣 1 条生命；生命归零显示 `OUT OF LIVES`，时间结束显示 `TIME'S UP`
- HUD 增加生命心形；菜单显示已载入的图标数量与来源（真实桌面 / 回退图标）；结算页显示结束原因
- 固定 120 Hz 逻辑更新，鼠标速度按真实事件时间估算；`post_update` 在物理更新之后处理漏判、切割、计分与回合结束，避免帧率影响物理
- 桌面读取失败或没有可用图标时自动使用程序生成的彩色回退图标，游戏仍可运行并在菜单中标注
- 独立自动化测试 `test_gameplay.py`，并在真实桌面环境下直接验证运行后图标名称和坐标未改变

## 阶段 1 已实现

- 通过 `Progman → SHELLDLL_DefView → SysListView32`（含 `WorkerW` 回退）定位桌面图标列表控件
- 跨进程读取桌面图标数量、显示名称、客户区坐标，并通过 `ClientToScreen` 转为屏幕物理像素坐标
- 通过 `Shell.Application` 命名空间把显示名称解析为文件路径或虚拟项 `::{CLSID}` 路径
- 通过 `SHParseDisplayName` + `SHGetFileInfoW` 提取真实 HICON，再转为 32 位 RGBA 图像
- 把 RGBA 图像转为带透明通道的 Pygame `Surface`
- 进程级 Per-Monitor V2 DPI 感知，坐标与图标尺寸均为物理像素
- 单个图标失败时跳过并记录错误，不影响其余图标
- 独立测试程序 `test_desktop_icons.py`：控制台明细、桌面布局视图、缩略图网格、透明 PNG、UTF-8 报告、截图

## 阶段 0 已实现

- 1280 × 720 普通 Pygame 窗口
- `MENU → COUNTDOWN → PLAYING → GAME_OVER` 状态机
- 3 秒倒计时、顶部 HUD
- 固定 120 Hz 逻辑更新 + 60 FPS 渲染，避免物理帧率耦合
- 桌面接口、物理、特效、UI、窗口相互独立
- 透明无边框窗口的配置项与 Windows 分层窗口实现（默认关闭，留待桌面覆盖层阶段启用）

> 阶段 0 当时的遗留项（暂停、透明覆盖层、高清图标、exe 打包）已在阶段 4–6 全部实现。

## 环境要求

- Windows 10 / 11 x64
- Python 3.12（项目目标版本；代码兼容 3.11+，本次验证使用 Python 3.11.2）
- pygame 2.6.x（本次验证版本）

| 依赖 | 用途 | 必需 |
| --- | --- | --- |
| pygame | 窗口、输入、渲染、字体、图像变换、混音 | 是 |
| pywin32 | `Shell.Application` 枚举桌面命名空间（虚拟项路径） | 是 |
| Pillow | HICON → RGBA 图像转换、透明通道处理 | 是 |
| PyInstaller | 打包 exe | 否 |
| ctypes | Python 标准库，Windows API 调用 | 是（代码已使用） |

## 安装

在 **cmd** 中执行：

```bat
cd /d E:\Desktop\fruit\DesktopSlash
py -3.12 -m venv .venv
.venv\Scripts\activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

如果机器上没有 3.12，可把 `py -3.12` 换成实际安装的版本（需 ≥ 3.11）。

只运行游戏最少需要 pygame；要读取真实桌面图标还需要 pywin32 和 Pillow：

```bat
python -m pip install pygame pywin32 Pillow
```

> PowerShell 的激活命令为 `.venv\Scripts\Activate.ps1`；Git Bash 为 `source .venv/Scripts/activate`。

## 启动游戏

```bat
python main.py
```

默认是**桌面背景模式**：开启 DPI 感知 → 创建透明覆盖层 → 只读枚举一次桌面图标 → 校验桌面图标控件并隐藏 → 绘制只读壁纸背景 → 显示菜单。读取通常需要 0.4–0.6 秒，期间不会显示游戏菜单；菜单出现时真实图标已经不在屏幕上。若读取失败或桌面没有可用图标，会自动使用程序生成的回退图标，菜单底部会显示 `FALLBACK ICONS · DESKTOP MODE`；若隐藏失败（控件无法确认、权限不足、非 Explorer 桌面），游戏仍可运行，但菜单会显示红色 `DESKTOP NOT HIDDEN` 原因，并且**绝不**去猜控件或隐藏其他窗口。

默认覆盖主显示器工作区，并隐藏该桌面上的真实图标。常用参数：

```bat
python main.py --window            :: 普通 1280x720 窗口（不隐藏图标，开发/对比用）
python main.py --overlay           :: 强制透明覆盖层 + 桌面背景模式（默认）
python main.py --monitor 1         :: 覆盖第 2 台显示器（其壁纸与图标状态独立处理）
python main.py --self-test         :: 运行打包自检并写出报告
```

也可以直接运行打包好的 `dist\DesktopSlash.exe`（参数相同）。覆盖层没有标题栏，退出方式：菜单 `EXIT / 退出游戏`、游戏中暂停后按 `Q`、关闭窗口，或任意时刻按 `Ctrl + Shift + Q` 紧急安全退出（先恢复桌面再结束进程）。退出码 0 表示正常关闭。

> 阶段 6 只隐藏图标控件的显示状态，不隐藏壁纸、不隐藏任务栏，也不改变桌面图标的排列。查看恢复状态：`%APPDATA%\DesktopSlash\desktop_backup.json`（会话期间存在，恢复后删除）和 `desktop_restore.log`。

## 完整运行流程

1. 启动 `python main.py`（或 `dist\DesktopSlash.exe`）。程序开启 DPI 感知、选择显示器、读取一次桌面图标（256 px）、校验并临时隐藏真实图标、绘制壁纸背景，并载入 `%APPDATA%\DesktopSlash\save.json`。
2. 屏幕上只剩 Windows 壁纸和开始界面：标题、历史最高分和 `开始游戏 / 设置 / 退出游戏`（默认中文；可在设置中切换英文）。真实桌面图标暂时不可见，壁纸、任务栏和桌面本身仍在。
3. 可选：打开 `SETTINGS / 设置` 调整音量、屏幕震动、扫描线或语言（简体中文 / English）；每次改动立即保存，切换语言后所有界面马上换词。点击面板外或按 `Esc` 返回菜单。
4. 选择 `START`：进入 `3 → 2 → 1 → GO!` 倒计时，每一步有音效和缩放弹出动画；`Space / Enter` 可跳过。
5. 进入游戏：大量放大后的图标从屏幕底部左/中/右三条出生带高高飞起，顶点通常达到屏幕高度的 55%–75%，少数接近 80%。按住鼠标左键快速划动切割；普通图标得分、炸弹扣命，连击提高得分倍率。整个显示器都是场地，在壁纸空白处也能起刀。
6. 随时按 `Esc / P` 暂停：画面冻结，鼠标立即交还桌面（可以点任务栏、开开始菜单）。**真实图标仍然保持隐藏**。再按 `Esc / P` 继续；按 `M` 回主菜单，按 `Q` 退出。
7. 时间到或生命归零进入结算页：查看最终分数、切割数量、最大连击和最高分；若是新纪录会显示 `NEW HIGH SCORE`。
8. 在结算页选择 `PLAY AGAIN` 重开（所有数据与对象重置）、`MAIN MENU` 返回标题，或 `EXIT GAME` 退出。
9. 退出后覆盖层与输入盾窗销毁、鼠标捕获和样式复原、**真实桌面图标与排列恢复**；最高分、设置和语言已经写入 JSON。若进程被强杀或断电，下次启动的 `recover_stale_session()` 与看门狗会补做恢复。

## 操作与规则

| 状态 | 操作 | 结果 |
| --- | --- | --- |
| MENU | `↑/↓` 或 `W/S` | 切换 `START / SETTINGS / EXIT` |
| MENU | `Enter` / `Space` | 执行当前焦点按钮（默认 `START`） |
| MENU | 鼠标移动 / 左键点击 | 悬停选择 / 点击执行 |
| MENU | `Esc` | 退出游戏 |
| SETTINGS | `↑/↓` 选择行，`Enter/Space` 执行 | 音量行按 Enter 增加 10%；震动/扫描线行切换；`BACK` 关闭 |
| SETTINGS | `←/→` | 音量行减少 / 增加 10% |
| SETTINGS | 鼠标点击 `− / +` | 降低 / 提高音量 |
| SETTINGS | 点击 `SCREEN SHAKE` / `SCANLINES` 行 | 立即切换开关并保存 |
| SETTINGS | `←/→` 或点击 `语言 / Language` 行 | 立即切换 `简体中文 / English` 并保存 |
| SETTINGS | `Esc` 或点击面板外 | 关闭设置 |
| 任意状态 | `Ctrl + Shift + Q` | 紧急安全退出：停止主循环 → 恢复桌面图标与鼠标 → 销毁窗口 → 退出 |
| COUNTDOWN | 等待 | `3 → 2 → 1 → GO!` 共 3.8 秒后进入 PLAYING |
| COUNTDOWN | `Space` / `Enter` | 跳过倒计时 |
| COUNTDOWN | `Esc` | 返回菜单 |
| PLAYING | 按住鼠标左键并快速划动 | 切割经过的图标 |
| PLAYING | `Esc` / `P` | 暂停并释放鼠标；窗口失去焦点也会自动暂停 |
| PAUSED | `Esc` / `P` | 继续本局（剩余时间与场面保持不变） |
| PAUSED | `M` | 返回主菜单（本局作废） |
| PAUSED | `Q` | 退出游戏 |
| GAME_OVER | `←/→` 或 `↑/↓` | 切换三个按钮 |
| GAME_OVER | `Enter` / `Space` / 鼠标左键 | 执行当前按钮（默认 `PLAY AGAIN`） |
| GAME_OVER | `R` | 立即再玩一次 |
| GAME_OVER | `Esc` | 返回主菜单 |

规则：

| 项目 | 值 |
| --- | --- |
| 游戏模式 | 仅一个模式；无模式选择、无模式配置文件 |
| 回合时长 | 90 秒 |
| 初始生命 | 3 |
| 普通图标基础分 | +10 |
| 连击倍率 | 连击 1–3 `x1`、4–6 `x2`、7–9 `x3`、10–12 `x4`、13+ `x5`（上限 5） |
| 实际得分 | `10 × 当前连击倍率`；飘字显示实际得分 |
| 漏掉普通图标 | −1 生命，并中断连击 |
| 切中炸弹 | −1 生命、中断连击、不加分 |
| 漏掉炸弹 | 不扣生命，也不加分 |
| 炸弹出现 | 开局 6 秒后开始；每波最多 1 个；概率随难度从 18% 升到 48% |
| 结束条件 | 生命归零（`OUT OF LIVES`）或时间结束（`TIME'S UP`） |
| 生成节奏 | 开局每波 3–5 个、约 1.5 秒一波；随时间升到每波 6–8 个、最快约 0.72 秒一波 |
| 难度曲线 | 0 → 90 秒：波次 +0→+3、速度 ×1→×1.38、生成间隔 1.5→0.72 秒、炸弹概率 18%→48% |
| 图标逻辑尺寸 | 80 / 96 / 112 / 128 px（22% / 50% / 24% / 4%），±5% 随机抖动；按 DPI 与分辨率放大，1080p / 96 DPI 下约 76–134 px |
| 图标图像来源 | Windows Shell 256 px 位图（`IShellItemImageFactory`），等比缩放并保留 alpha |
| 抛射顶点 | 55%–75% 屏高；15% 概率 76%–82%；按 `v0 = sqrt(2·g·rise/compensation)` 反解，不用固定竖直速度 |
| 出生位置 | 屏幕底部下方（深度 0–6% 屏高），左/中/右三条出生带轮换，最小水平间距按较大图标半径的 2.3 倍检查 |
| 水平运动 | 30–190 像素/秒 × 屏宽系数，24% 概率朝屏幕外侧飞；每图标独立重力与自旋 |
| 同屏上限 | 12 个目标 |
| 切割门槛 | 鼠标轨迹速度 ≥ 420 像素/秒；慢速拖动只显示刀光，不切割 |
| 连击窗口 | 1.7 秒内连续切割；超时、漏掉普通图标或切中炸弹都会中断 |
| 连击播报 | x2 / x3 / x5，8 连起每 5 连一次 `GREAT COMBO`（8、13、18…） |
| 音效 | `slice` / `combo` / `bomb` / `miss` / `click` / `count` / `go`，启动时程序合成；无音频设备时自动静音 |
| 最高分 | 写入 JSON；只有本局分数严格超过旧纪录时才更新 |
| 重复计分 | 不允许；切割后图标立即移除，每个图标在一次划动中只产生一次命中 |

> 初始只有 3 条生命，连续漏掉 3 个普通图标就会结束回合。所有节奏、倍率、难度和 UI 参数都在 `game_config.py` 中统一配置。

## 存档与设置

存档文件：

```text
%APPDATA%\DesktopSlash\save.json
```

如果没有 `APPDATA` 环境变量，则退回到 `~/.desktop_slash/DesktopSlash/save.json`。文件内容示例：

```json
{
  "version": 1,
  "high_score": 1280,
  "language": "zh_CN",
  "settings": {
    "volume": 0.6,
    "shake": true,
    "scanlines": true
  }
}
```

- `language` 为 `zh_CN`（默认）或 `en_US`；缺失、类型错误或未知代码时回退 `zh_CN`。
- 最高分在回合结束时比较并保存，设置项和语言在改动时立即保存。
- 写入使用同目录临时文件 + `os.replace`，避免中途退出留下半个 JSON。
- 文件不存在时使用默认值（最高分 0、音量 0.32、震动和扫描线开启、语言 `zh_CN`），不会自动创建空文件。
- JSON 解析失败、根节点不是对象、字段类型/范围异常时回退默认值；超范围音量会被夹到 `0.0–1.0`，负分夹到 `0`。
- 启动时读入存档并立即应用到音频音量、屏震开关和扫描线开关。
- 自动化测试使用临时目录中的存档，不会改动真实 `%APPDATA%` 文件。

## 本次迭代验证（2026-11-17）

```bat
python test_i18n.py            :: 中英词表、默认/回退、字形、即时切换、各界面布局
python test_shutdown.py        :: 退出顺序、幂等、错误隔离、预算、全部退出入口、紧急热键
python test_wallpaper_fidelity.py :: 七种壁纸样式 + 预合成裁切 + 原生桌面像素比对
python main.py --self-test     :: 含中文无豆腐块与词表加载检查
dist\DesktopSlash.exe --self-test :: 打包版同样检查
```

本机结果：

- `test_i18n.py` 8/8：中英词表各 71 键且集合一致；默认 `zh_CN`，非法代码回退；术语表逐条命中；`hud.best` 格式化与坏模板回退；存档写入/读取/损坏回退；CJK 字形逐字非空；切换语言后菜单/设置/暂停/结算画面立即变化；两种语言的按钮与设置行不溢出。
- `test_shutdown.py` 11/11：重复请求只执行一次；恢复桌面早于窗口销毁；单步异常与缺失方法不中断后续步骤；5 秒预算生效；菜单/结算/暂停/窗口关闭/QUIT/紧急事件全部走同一管线；守护线程按宽限期退出。
- `test_wallpaper_fidelity.py` 全部 PASS：Fill/Fit/Stretch/Tile/Center/Span/1:1 与预合成裁切均正确；本机壁纸源为 `transcoded`（`precomposed=True`，样式 4），与 Windows 合成位图逐像素比对 `mean=0.0000 max=0`。
- `dist\DesktopSlash.exe --self-test`：`Chinese glyphs render (no tofu)`、`language catalogues loaded -> zh_CN,en_US`，总计 `PASS: 0 failure(s)`。
- 既有回归：`test_gameplay` 9/9、`test_effects` 12/12、`test_game_system` 12/12、`test_stage5_flow` 32/32、`test_visual_upgrade` 9/9、`test_desktop_background` 6/6、`test_overlay_window` 23/23、`test_performance` 15/15（13.00 ms/帧，5 分钟内存增量 +0.2 MB），桌面图标 112 个坐标未变。

## 阶段 6 自动化测试与手动验证

所有测试都使用项目虚拟环境的 Python：

```bat
python test_visual_upgrade.py                  :: 图标尺寸、高清来源、抛射顶点、出生带、呼吸/光晕
python test_desktop_background.py              :: 桌面控件校验、隐藏/恢复循环、看门狗、单实例
python test_desktop_background.py --live-overlay  :: 真实覆盖层：桌面模式 + 游戏 + 暂停/继续 + 退出恢复
```

### 1. 视觉与物理 `test_visual_upgrade.py`

在 dummy 驱动下生成 400 个图标并对比多个屏幕/DPI 组合，检查：

- 四档逻辑尺寸与权重正确，抖动不越界，实际屏幕尺寸落在目标区间
- 所有图标的宽高比与透明通道保持不变，没有把 48 px 位图硬拉到 128 px
- 1280×720 / 96 DPI、1920×1080 / 96、1920×1080 / 144、2560×1600 / 144、3840×2160 / 192 DPI 的 `ui_scale` 与标称一致
- 真实 Shell 图标读取：112/112 个图标均为 256 px，且屏幕尺寸全部 ≥128 px
- 五种屏幕组合各采样 200 次抛射：顶点最低 ≥0.55、最高 ≈0.80、中位数约 0.67，顶点分布有足够离散度
- 每波覆盖左/中/右三条出生带，同波最小间距 ≥ 1.15 倍较大图标尺寸，单个图标不越出自己的出生带
- 呼吸缩放围绕基准值以 1.9 秒周期振荡；光晕覆盖层尺寸大于图标且包含非零 alpha
- 输出 `test_output/stage6_icon_sizes.png` 与 `test_output/stage6_flight_arcs.png`

本机结果（2026-11-17，Python 3.11.2 / pygame 2.6.1）：

```
live shell icons: 112 read, 112 at >=128 px, max 256 px
apex 1280x720 @ 96 dpi:  0.558-0.799, median 0.677
apex 1920x1080 @ 96 dpi: 0.557-0.796, median 0.675
apex 1920x1080 @ 144 dpi:0.555-0.794, median 0.673
apex 2560x1600 @ 144 dpi:0.558-0.795, median 0.675
apex 3840x2160 @ 192 dpi:0.563-0.801, median 0.680
9/9 checks passed
```

### 2. 桌面背景与恢复 `test_desktop_background.py`

默认在无头模式下真实执行隐藏/恢复（会短暂隐藏桌面图标几秒），检查：

- 只接受 `Progman/WorkerW → SHELLDLL_DefView → SysListView32` 且属主为 `explorer.exe` 的控件；校验失败时抛出 `DesktopBackgroundError`，不执行任何隐藏
- 连续 3 次“隐藏 → 恢复”：标记文件写入/删除正确，隐藏期间只清除 `WS_VISIBLE` 位、扩展样式不变，恢复后样式完全一致
- 恢复是幂等的；112 个图标的名称与屏幕坐标在 3 轮后完全不变；看门狗进程被正确释放
- 伪造“上次异常退出”的旧标记（PID 已失效）时，`recover_stale_session()` 能恢复并清理标记
- 真实子进程隐藏图标后 `os._exit(7)` 模拟崩溃：父进程在 20 秒内观察到看门狗把图标恢复，并清理标记
- 初始化失败（模拟隐藏阶段抛错）时 `game.desktop_hidden=False`，菜单能拿到明确错误原因
- 命名互斥锁拒绝第二个实例，释放后可重新获取
- `--live-overlay` 额外验证：真实覆盖层启动后图标隐藏、菜单显示、40 帧游戏、暂停释放/继续接管、关闭后 112 个图标恢复，并输出 `test_output/stage6_live_menu_formal.png`

本机结果：

```
cycle 1/2/3: hidden hwnd=0x1018A marker=yes positions=unchanged
112 icon(s) unchanged after 3 hide/restore cycles
crashed child returned 7, watchdog restored the icons
6/6 checks passed

overlay dpi=144 ui_scale=1.732 icons=139-222 input=active
play frames 40, active icons=3, pause released and resume reacquired the mouse
shutdown restored 112 icon(s)
7/7 checks passed
```

### 3. 打包版实机冒烟（本机已执行）

构建 `dist\DesktopSlash.exe` 后启动它，等图标隐藏和菜单出现，再向窗口发送 `WM_CLOSE` 触发正常退出流程。本机结果：

```
before: icons=112 marker=False
launched: icons_hidden=True marker=True overlay=0x620B2C
exit_code=0 icons_visible=1 marker=False icons=112
hidden=True closed=True restored=True count_same=True positions_same=True
PASS
```

即：EXE 启动后会隐藏 112 个真实图标并写标记；关闭后进程退出码 0、图标重新可见、标记删除、112 个图标坐标与启动前完全一致。

### 4. 如何测试图标恢复

1. **正常退出**：菜单 `EXIT`；或游戏中 `Esc/P` 暂停后按 `Q`。图标应立刻回到原位置，`desktop_backup.json` 消失。
2. **强制结束**：另开一个终端执行 `taskkill /F /IM DesktopSlash.exe`。看门狗子进程会在父进程消失后恢复图标；确认日志 `%APPDATA%\DesktopSlash\desktop_restore.log` 含 `watchdog restored desktop icons`。
3. **延迟恢复**：若强制结束后图标仍未出现，重新启动一次 `python main.py`。启动前的 `recover_stale_session()` 会读取旧标记并恢复，然后正常进入游戏（单实例锁只阻止同时运行，不影响恢复）。
4. **手动兜底**（仅在上述都失败时）：

   ```bat
   python -c "from desktop.desktop_background import recover_stale_session; print(recover_stale_session())"
   ```

   该命令只读取标记、校验控件并调用 `ShowWindow(SW_SHOWNA)`，不会触碰文件或布局。
5. **核对布局**：运行 `python test_desktop_background.py`，最后一行会报告 112 个图标在 3 轮隐藏/恢复后的名称与坐标是否完全一致。正常退出后也可以肉眼确认图标位置、名称、排列未变。

### 5. 手动验证清单

1. 启动 `python main.py`：壁纸仍在，真实图标消失，出现开始界面；任务栏出现 `Desktop Slash` 按钮
2. 按 `START`：图标明显比桌面原图标大，从底部高高飞起，顶点达到屏幕上中部；同屏图标大小有差异
3. 在整个屏幕任意空白处划动都能切到图标；刀光、碎片、粒子、炸弹和连击正常
4. `Esc/P` 暂停：鼠标可以正常操作任务栏/开始菜单，但真实桌面图标**不会**出现；继续后重新接管
5. `Alt+Tab` 切走再切回：只暂停/释放鼠标，图标保持隐藏
6. `--monitor 1` 在第二台显示器：覆盖该屏，另一屏桌面图标保持原状
7. 正常退出：图标恢复原位、桌面点击/拖动正常、没有残留透明层；再启动一次仍只运行一个实例
8. 用任务管理器强制结束进程：等待几秒看图标是否被看门狗恢复；必要时重新启动一次
9. 检查桌面图标名称、位置与运行前一致，桌面文件夹没有被修改

## 阶段 5 回归测试与手动验证

以下为阶段 5 的测试说明，阶段 6 已全部回归通过。所有测试都使用项目虚拟环境的 Python：

```bat
python test_overlay_window.py          :: 真实 Win32 覆盖层窗口
python test_stage5_flow.py             :: 覆盖层渲染 + 暂停 + 10 步完整流程
python test_performance.py             :: 帧耗时、缓存上限、长时间内存
python main.py --self-test             :: 源码自检
dist\DesktopSlash.exe --self-test      :: 打包自检
```

### 1. 覆盖层独立测试 `test_overlay_window.py`

会真实创建覆盖所选显示器的分层窗口几秒钟，检查：

- 窗口覆盖显示器工作区、无标题栏/边框
- `WS_EX_LAYERED`、`WS_EX_TOPMOST`、`WS_EX_APPWINDOW`（任务栏/Alt+Tab 入口）生效
- 游戏模式：`WM_NCHITTEST → HTCLIENT`，没有 `WS_EX_TRANSPARENT`
- 输入盾窗存在、可见，且在透明像素上 `WindowFromPoint` 返回盾窗而不是桌面
- 键色区域显示测试程序放置的橙色参照窗口（截图差异 < 2%），证明背景真的透明；绘制的洋红测试卡片能被截取到
- 主动模式能收到真实鼠标按下/松开（点击盾窗 → 转发到 SDL → Pygame 事件）
- 释放模式：`WM_NCHITTEST → HTTRANSPARENT`、`WS_EX_TRANSPARENT` 生效、盾窗隐藏、`WindowFromPoint` 不再返回覆盖层/盾窗、没有鼠标捕获
- 重新接管后样式、盾窗与命中测试恢复
- 关闭后覆盖层与盾窗都销毁、桌面不被遮挡、捕获为 0
- 读取前后桌面图标名称与坐标完全一致

```bat
python test_overlay_window.py                    :: 自动检查 + 真实鼠标点击探针
python test_overlay_window.py --no-input-probe   :: 不移动鼠标
python test_overlay_window.py --interactive      :: 实时测试卡片：Space 切换接管/穿透，Esc 退出
```

> 如果 Windows 处于锁屏、UAC 提权提示或远程会话断开状态，屏幕截图与真实鼠标探针会被标记为 `[SKIP]`（样式、命中测试和生命周期检查仍会执行）。解锁桌面后重新运行即可完成全部检查。

### 2. 完整流程 `test_stage5_flow.py`

在 dummy 驱动下用真实桌面图标运行：开始界面 → START → 倒计时 → 切割 4 个图标（连击 + 倍率）→ 切中炸弹 → 时间结束 → 结算与最高分 → 重开 → 暂停/冻结/全局 Esc 继续/焦点丢失暂停 → 退出。同时检查：

- 覆盖层菜单角落是精确键色、右边缘整列透明（没有扫描线）
- 每帧绘制前会用键色清空场景
- 游戏中空桌面保持透明、对象像素可见
- 菜单失焦释放鼠标、重新聚焦接管；暂停中重新聚焦仍保持 `released`
- 暂停时倒计时与物理完全冻结，鼠标模式为 `released`
- 暂停瞬间按住 Esc 不会立刻继续；0.35 秒后全局轮询可继续
- 整个会话桌面图标只读取 1 次，前后名称/坐标一致

### 3. 性能与内存 `test_performance.py`

在显示器物理工作区尺寸（本机 2560 × 1528）下构造 12 个旋转图标、满刀光、数百粒子和特效，统计 150 帧的平均耗时；然后把粒子/特效池填满到上限，检查文字缓存、HUD 面板缓存、图标缩放缓存；最后做 1 分钟预热 + 5 分钟特效/粒子压力测试，比较工作集并确认所有对象能自行清空。

本机结果（Python 3.11.2 / pygame 2.6.1 / 2560 × 1528）：

```
startup: 858 ms
frame cost: update 0.10 ms + render/flip 13.57 ms = 13.67 ms (~73 FPS CPU-bound)
working set: 196.5 MB -> 196.6 MB (delta +0.1 MB)
15/15 checks passed
```

### 4. 打包自检 `--self-test`

`main.py --self-test` 与 `dist\DesktopSlash.exe --self-test` 会在 dummy 驱动下检查：`assets/icon.png|ico`、窗口图标、pywin32 COM 导入、显示器枚举、桌面图标控件校验（Progman/WorkerW + explorer.exe）、桌面图标读取（只读 1 次，报告 `icon source request=256px ui_scale=1.00 on-screen=80-128px`）、字体、7 个合成音效、覆盖层键色渲染、菜单绘制、PLAYING 推进、暂停释放/继续接管、桌面未改变、崩溃恢复。结果写入 `desktop_slash_self_test.txt`（打包版在 EXE 同目录），EXE 退出码 0 表示通过。

### 5. 手动验证清单

真实桌面手感与视觉需要在解锁的桌面上人工确认：

1. 启动 `python main.py`：桌面背景完全可见，只有 UI 和游戏对象，没有窗口底色；任务栏出现 `Desktop Slash` 按钮
2. 在空白桌面处按下鼠标划动也能切到图标（不是只有图标像素能接收鼠标）
3. `Esc / P` 暂停后可直接点击桌面图标、打开开始菜单；再按 `Esc / P` 回到游戏
4. `Alt+Tab` 切到浏览器：游戏暂停并释放鼠标；点击任务栏的 `Desktop Slash` 切回（菜单/结算界面也会直接释放鼠标，切回后自动接管）
5. 用 `--monitor 1` 在第二台显示器上运行；任务栏保持可点击
6. 退出游戏后所有窗口（含输入盾窗）消失，桌面点击/拖动正常，没有残留的置顶透明层
7. 检查桌面图标位置与运行前一致

## 阶段 4 自动化测试

### 运行

```bat
python test_game_system.py
```

默认使用 SDL `dummy` 视频/音频驱动，不弹窗、不发声。脚本会：

1. 在临时目录中验证 JSON 存档的默认值、写入、读取、原子性和损坏回退；
2. 验证单一难度曲线在 0 → 90 秒内单调递增并正确钳制；
3. 验证波次数量、生成间隔和连击倍率实际生效；
4. 用真实 `Game` 状态机点击菜单、设置面板和结算按钮，检查状态切换；
5. 检查最高分只在破纪录时更新，重开清空分数/生命/统计/图标/特效；
6. 渲染每个界面，并生成阶段 4 截图与总览图。

| 参数 | 作用 |
| --- | --- |
| `--no-snapshots` | 只跑 12 项检查，不生成截图，也不做真实桌面前后对比 |

### 检查项

| 检查 | 内容 |
| --- | --- |
| profile JSON round trip | 缺失文件返回默认值且不创建文件；保存后字段、版本、设置完整；无临时文件残留 |
| profile survives bad data | 非法 JSON 回退默认值并记录错误；负分/超范围音量被修正；损坏文件可被覆盖 |
| single difficulty curve | 0 秒与 90 秒的全部难度值；超过回合时长后保持钳制；中间采样单调 |
| waves and spacing ramp up | 早期每波 3–5 个、晚期 6–8 个；晚期生成间隔明显缩短；不超过 12 个上限 |
| combo multiplier scoring | 一刀 4 个 = `10+10+10+20 = 50`；连击 4/7 分别对应 `x2/x3` |
| menu buttons and navigation | 三个按钮文案与动作；点击 START 进入倒计时；设置打开/关闭；EXIT 设置 `running=False` |
| settings overlay controls | `−/+` 调整音量并写入存档；震动/扫描线立即生效；键盘导航；Esc 退出游戏 |
| settings persist across games | 关闭后用同一存档新建 `Game`，音量/开关/音频音量全部恢复 |
| 3-2-1-GO countdown and sounds | 四个阶段标签正确；每一步只播放一次 `count`，GO 播放 `go`；倒计时结束进入 PLAYING |
| high score and game over actions | 破纪录写入存档；三个按钮动作；PLAY AGAIN 重置全部统计；低分不覆盖最高分 |
| restart resets all state | 切割产生特效后重开：分数、生命、统计、连击、图标、特效、粒子、震屏/闪光全部归零 |
| every screen renders | MENU / COUNTDOWN / GO / PLAYING / GAME_OVER 全部离屏渲染无异常 |

### 本机测试结果（2026-11-17）

| 项目 | 结果 |
| --- | --- |
| 阶段 4 自动化检查 | **12 / 12 通过** |
| 阶段 3 回归检查 | **12 / 12 通过**（连击倍率断言已更新） |
| 阶段 2 回归检查 | **9 / 9 通过** |
| 真实桌面图标载入 | **112 个**（`desktop` 来源） |
| 阶段 4 截图 | 6 张 + 1 张总览图 |
| 桌面只读检查 | 运行前后 **112 个图标的名称与坐标完全一致** |
| 真实存档 | 自动化测试只写临时目录，未改动 `%APPDATA%` |

截图位于 `test_output/`：

- `stage4_menu.png` — 开始界面（标题、最高分、三个按钮）
- `stage4_settings.png` — 设置面板（音量 / 震动 / 扫描线 / BACK）
- `stage4_countdown_3.png` — 倒计时数字 3
- `stage4_countdown_go.png` — `GO!`
- `stage4_playing.png` — HUD：分数、时间、生命、`COMBO 7 X3`、`BEST`
- `stage4_game_over.png` — 结算统计 + `NEW HIGH SCORE` + 三个按钮
- `stage4_system_sheet.png` — 3×2 总览图

### 手动验证清单

1. 运行 `python main.py`。菜单显示标题、最高分和 `START / SETTINGS / EXIT`；底部显示 `PHASE 5 · N DESKTOP ICONS · OVERLAY MODE`（用 `--window` 启动则是 `WINDOW MODE`；读取失败则为 `PHASE 5 · N FALLBACK ICONS · ...`）。
2. 用 `↑/↓ + Enter` 和鼠标分别选择按钮；设置 `SETTINGS` 打开面板后，菜单被遮罩压暗。
3. 在设置中连续按 `+` 提高音量：点击音效立即变响；关闭 `SCREEN SHAKE` 后切中炸弹只闪光不震动；关闭 `SCANLINES` 后扫描线消失。按 `BACK` 或 `Esc` 关闭。
4. 退出游戏再启动：最高分、音量、震动和扫描线状态保持（存档 `%APPDATA%\DesktopSlash\save.json`）。
5. 选择 `START`：依次出现 `3`、`2`、`1`、`GO!`，数字带缩放弹出，每步有短音，GO 有上行音；按 `Space` 可跳过。
6. 游戏中检查 HUD：分数、时间条、3 颗心、当前连击和倍率、右上角 `BEST` 都随状态变化。
7. 连续切 4 / 7 / 10 个图标：HUD 出现 `X2` / `X3` / `X4`，飘字显示 `+20` / `+30` / `+40`。
8. 观察后期：每波图标更多、飞行更快、波次更密、炸弹更频繁；同屏始终不超过 12 个。
9. 漏掉 3 个普通图标或切中足够多炸弹 → `OUT OF LIVES`；等待 90 秒 → `TIME'S UP`。结算页显示最终分数、切割数量、最大连击、最高分；破纪录时出现 `NEW HIGH SCORE`。
10. 在结算页依次测试 `PLAY AGAIN`（分数/生命/统计/图标/特效全部重置）、`MAIN MENU`、`EXIT GAME`。
11. 存档容错：退出游戏，把 `save.json` 改成非法内容，再启动。游戏应正常进入菜单并使用默认值；再刷新纪录或改设置后会写回合法 JSON。
12. 退出后检查桌面：图标位置、名称和文件均未改变。
13. 快速回归：`python test_game_system.py --no-snapshots`、`python test_effects.py --no-snapshots`、`python test_gameplay.py --no-snapshots` 应分别为 12/12、12/12、9/9。

> 想快速检查结算流程，可临时把 `game_config.py` 的 `ROUND_SECONDS` 改成 `8.0`，测试完改回 `90.0`。该参数没有模式配置，直接改的就是全局回合时长。

## 阶段 3 自动化测试与特效演示

### 运行

```bat
python test_effects.py
```

默认使用 SDL `dummy` 视频/音频驱动，不弹窗、不发声，可在桌面环境下直接运行。脚本会：

1. 检查粒子池容量/复用、特效管理器上限、屏震/闪光生命周期、连击计时与里程碑；
2. 用真实 `Game` 状态机验证切割反馈包、连击 x5 / GREAT COMBO x8、炸弹扣命与后续切割；
3. 把特效管理器填满，确认切割、计分和扣命完全不受特效数量影响；
4. 验证所有特效与粒子会在生命周期结束后归零；
5. 生成 10 张阶段 3 截图和 1 张 3×3 总览图；
6. 若真实桌面可读，截图使用真实桌面图标，并在运行前后比较图标名称与屏幕坐标。

可选参数：

| 参数 | 作用 |
| --- | --- |
| `--no-snapshots` | 只跑 12 项逻辑检查，不生成截图，也不做真实桌面前后对比 |
| `--live` | 打开真实窗口，自动循环展示 6 种特效 |
| `--live-seconds N` | 配合 `--live`，N 秒后自动退出（用于冒烟测试） |

### 检查项

| 检查 | 内容 |
| --- | --- |
| particle pool cap and reuse | 900 上限；持续喷射不会扩容；过期粒子归还槽位并被复用 |
| particle lifetime cleanup | 粒子在生命周期结束后全部释放，不泄漏池槽 |
| effect manager cap | 上限 96；超限拒绝并记录 `skipped`，不会无限创建 |
| screen shake/flash lifecycle | 震动幅度上限 18 px；弱震动不会截断强震动；震/闪到时归零 |
| combo tracker and milestones | 连击窗口、超时归零、x2/x3/x5/GREAT 文案与颜色、炸弹/漏判中断 |
| slash trail stays bounded | 轨迹最多 32 点；火花采样最多 16 个；松手/超时后清空 |
| config and audio interface | 关键参数范围；音效接口在无音频设备时安全降级 |
| slice feedback package | 得分 +10、图标移除、左右碎片、白闪、`+10` 飘字、≥8 个像素碎片 |
| effects never change scoring | 特效管线被填满时仍能切割、计分、保持生命不变 |
| combo x5 and great combo | 一刀 5 个 = 70 分（1×10×3 + 2×10×2）、连击 5、只出现一个 x5 播报；一刀 8 个 = 150 分（1×30 + 2×30 + 3×20）、`GREAT COMBO x8` + 屏震 |
| bomb explosion and life loss | 生命 −1、0 分、连击清零、火球/粒子/震屏/闪屏齐全；爆炸后普通图标仍可切割 |
| effects clean themselves up | 600 个固定步后特效、粒子、震屏、闪光全部归零，连击自然过期 |

### 本机测试结果（2026-11-17）

环境：Windows 10 22H2（10.0.22000）、Python 3.11.2、pygame 2.6.1、pywin32、Pillow。

| 项目 | 结果 |
| --- | --- |
| 阶段 3 自动化检查 | **12 / 12 通过** |
| 阶段 2 回归检查 | **9 / 9 通过**（`python test_gameplay.py --no-snapshots`） |
| 真实桌面图标载入 | **112 个**（`desktop` 来源） |
| 特效截图 | 10 张 + 1 张总览图 |
| 桌面只读检查 | 运行前后 **112 个图标的名称与坐标完全一致** |
| `--live` 冒烟 | 21 秒无头循环完整跑完 6 个演示场景，无异常 |

截图位于 `test_output/`：

- `stage3_menu.png` — 街机菜单
- `stage3_countdown.png` — 倒计时
- `stage3_playing.png` — 正常游戏中
- `stage3_slash.png` — 多层霓虹刀光 + 像素火花
- `stage3_slice.png` — 左右碎片 + 白色星芒 + `+10`
- `stage3_particles.png` — 8–20 个像素碎片扩散
- `stage3_combo.png` — `COMBO x5` 播报 + 环形粒子
- `stage3_great_combo.png` — `GREAT COMBO x8` + 高连击屏震
- `stage3_bomb.png` — 橙红像素火球 + 闪屏
- `stage3_game_over.png` — 结算页
- `stage3_effects_sheet.png` — 3×3 特效总览

### 实时特效演示

```bat
python test_effects.py --live
```

窗口打开后会直接进入游戏画面，每 2.9 秒自动切换一个演示：

| 顺序 | 演示 |
| --- | --- |
| 1 | 刀光轨迹（沿正弦路径移动的鼠标划动） |
| 2 | 单个图标切割 |
| 3 | 一刀 5 个 → `COMBO x5` |
| 4 | 一刀 8 个 → `GREAT COMBO x8` |
| 5 | 切中炸弹 → 火球 + 屏震 + 闪光 |
| 6 | 大量彩色像素粒子 + 环形爆发 |

操作：

| 按键 | 作用 |
| --- | --- |
| `Space` | 立即切换下一个特效 |
| `R` | 重开当前演示 |
| `Esc` | 退出演示 |

### 如何调强度、颜色和持续时间

所有特效参数都在 `game_config.py`，改完重新运行即可，无需改代码：

| 效果 | 强度 / 尺寸 | 颜色 | 持续时间 | 其他 |
| --- | --- | --- | --- | --- |
| 刀光 | `SLASH_TRAIL_OUTER_WIDTH=14`、`GLOW_WIDTH=8`、`CORE_WIDTH=3` | `SLASH_TRAIL_OUTER_COLOR` 紫、`GLOW_COLOR` 青、`CORE_COLOR` 近白 | `SLASH_TRAIL_LIFETIME=0.42`、`SLASH_TRAIL_RELEASE_FADE=0.24` | `SLASH_TRAIL_MAX_POINTS=32`；`SLASH_TRAIL_SPARK_*` 控制火花 |
| 图标碎片 | `FRAGMENT_SPLIT_SPEED=235`、`LIFT_SPEED=130`、`SPIN_MAX=300` | 直接使用图标原图左右两半 | `FRAGMENT_LIFETIME=1.05` | `FRAGMENT_GRAVITY=1900`、`FRAGMENT_FADE_START=.55` |
| 像素碎片 | `SLICE_PIXEL_MIN/MAX=8/20`、`SIZE=(3,8)`、`SPEED=(110,430)` | `SLICE_PIXEL_COLORS`（白/青/黄/橙/紫） | `SLICE_PIXEL_LIFETIME=(0.45,0.95)` | `SLICE_PIXEL_GRAVITY=1500` |
| 白色星芒 | `SLICE_FLASH_RADIUS_MIN/MAX=20/62` | `SLICE_FLASH_COLOR`、`SLICE_FLASH_RING_COLOR` | `SLICE_FLASH_LIFETIME=0.16` | 加色混合 |
| `+10` 飘字 | `SCORE_POPUP_START_SCALE=.72`、`END_SCALE=1.38`、`RISE=88` | 默认 `SCORE_POPUP_COLOR` 黄；按连击切换青/黄/橙/品红 | `SCORE_POPUP_LIFETIME=0.92` | 连击越高字号与放大倍数越大 |
| 粒子池 | `PARTICLE_POOL_MAX=900`、`PIXEL_SNAP=2` | `PARTICLE_COLOR`、各效果的 `*_COLORS` | 每个粒子独立寿命 | `PARTICLE_ADDITIVE=True`；满池丢弃多余粒子 |
| 炸弹 | 粒子 `BOMB_PARTICLE_COUNT=52`、`SIZE=(2,8)`、`SPEED=(180,700)`；火球半径 26→190；震动 16 px | `BOMB_PARTICLE_COLORS`、`BOMB_FLASH_COLOR=(255,120,40)`、`BOMB_CORE_COLOR` | 火球 `BOMB_BLAST_LIFETIME=0.48`、闪光 `0.15`、震动 `0.36` | 闪光强度 `BOMB_FLASH_ALPHA=60`；出现时间/概率 `BOMB_START_TIME` / `BOMB_SPAWN_CHANCE` |
| 连击播报 | 字号 `FONT_SIZE_COMBO=76`、副字号 34 | `COMBO_X2/X3/X5/GREAT_COLOR` | `COMBO_CALLOUT_LIFETIME=1.05` | 窗口 `COMBO_WINDOW=1.7`；高连击闪屏 `COMBO_FLASH_*`、屏震 `COMBO_SHAKE_*` |
| 全屏效果 | 震动上限 `SCREEN_SHAKE_MAX=18` | `SCANLINE_ALPHA=24`、`SCANLINE_SPACING=3` | 每次震动/闪光独立计时 | `EFFECT_MAX_ACTIVE=96`、`FLASH_ADDITIVE=True` |
| 音效 | `AUDIO_VOLUME=0.32` | 波形由方波/正弦/噪声合成 | 每段 0.10–0.46 秒 | `AUDIO_ENABLED=False` 可整体关闭 |

常用调法：

- 觉得刀光太粗：降低 `SLASH_TRAIL_*_WIDTH`，或把 `SLASH_TRAIL_OUTER_COLOR` 调暗。
- 觉得切割不够炸：提高 `SLICE_PIXEL_MAX`、`SLICE_PIXEL_SPEED`、`SLICE_FLASH_RADIUS_MAX`。
- 觉得炸弹闪屏刺眼：降低 `BOMB_FLASH_ALPHA` 或 `BOMB_FLASH_DURATION`；想要更亮可加回色混合颜色通道。
- 觉得连击太吵/太亮：降低 `COMBO_FLASH_ALPHA`、`COMBO_SHAKE_STRENGTH`，或调高 `COMBO_GREAT_THRESHOLD`。
- 粒子太多导致低端机掉帧：降低 `PARTICLE_POOL_MAX`，并把 `SLICE_PIXEL_MAX` 控制在 12–16。

## 阶段 2 自动化测试

测试使用 SDL 的 `dummy` 视频驱动，**不会弹出窗口**，可以直接在桌面环境下运行。它会：

1. 用固定种子和程序生成图标测试波次、物理与切割逻辑；
2. 用真实的 `Game` 状态机测试计分、生命、时间结束和重新开始；
3. 生成阶段 2 各画面截图；
4. 如果真实桌面可读，使用真实桌面图标生成截图，并在运行前后比较桌面图标的名称与屏幕坐标，确认没有被修改。

可选参数：

| 参数 | 作用 |
| --- | --- |
| `--no-snapshots` | 只跑逻辑检查，不生成截图，也不做真实桌面前后对比 |

### 检查项

| 检查 | 内容 |
| --- | --- |
| segment/circle collision | 线段最近点、线段与圆相交/不相交 |
| wave size, interval, cap | 每波 3–5 个、间隔约 1.5 秒、最多 12 个、对象不复用、运动参数不同 |
| miss only after entering | 图标先进入屏幕，飞出后才判定漏掉 |
| slash speed, multi-hit, dedupe | 慢速不切割、快速一次切多个、同一图标不重复计分、点击不切割 |
| fixed-timestep advance | 60 FPS 与 30 FPS 渲染节奏下都执行相同数量的 1/120 秒逻辑步 |
| slice scoring and effects | 切割 +10、图标移除、碎片/粒子/飘字存在、重复划动不再得分 |
| miss costs a life | 漏掉一个图标生命 −1，回合继续 |
| zero lives ends the round | 生命归零进入 `GAME_OVER`，原因为 `OUT OF LIVES` |
| time up and restart | 时间结束原因为 `TIME'S UP`；重新开始后分数/生命/图标正确重置 |

### 输出

- 控制台：每项 `[PASS]` / `[FAIL]`，最后汇总 `9/9 checks passed`
- `test_output/stage2_menu.png`
- `test_output/stage2_countdown.png`
- `test_output/stage2_playing.png`
- `test_output/stage2_slice.png`（含刀光、碎片、粒子、`+10`）
- `test_output/stage2_game_over.png`
- 真实桌面可读时额外打印 `desktop unchanged: N item(s)`

### 本机测试结果（2026-11-17）

环境：Windows 10 22H2（10.0.22000）、Python 3.11.2、pygame 2.6.1、pywin32、Pillow。

| 项目 | 结果 |
| --- | --- |
| 自动化检查 | **9 / 9 通过** |
| 真实桌面图标载入 | **112 个**（`desktop` 来源） |
| 快照 | 5 张 Stage 2 截图全部生成 |
| 桌面只读检查 | 运行前后 **112 个图标的名称与坐标完全一致** |
| 实际窗口冒烟测试 | 112 个真实图标载入；合成鼠标划动成功切割并加 10 分；真实 Pygame 窗口正常渲染和退出 |

截图位于 `test_output/`，可直接打开检查视觉效果：

- `stage2_menu.png`
- `stage2_countdown.png`
- `stage2_playing.png`
- `stage2_slice.png`
- `stage2_game_over.png`

### 手动验证清单

1. 运行 `python main.py`，选择 `START` 进入倒计时和游戏；菜单底部显示 `PHASE 5 · N DESKTOP ICONS · OVERLAY MODE`（`--window` 启动为 `WINDOW MODE`；读取失败则为 `PHASE 5 · N FALLBACK ICONS · ...`）。
2. 按 `Space` 跳过倒计时进入游戏；3–5 个真实桌面图标应从窗口下方飞入并旋转，背景为深色透视网格。
3. 按住鼠标左键快速划过图标：出现紫色外辉光 + 青色中层 + 近白核心的刀光，命中点有白色星芒、8–20 个像素碎片、左右两半图标和得分飘字，分数增加 `10 × 倍率`；松开后刀光约 0.24 秒淡出。
4. 慢慢拖动鼠标划过图标：只有刀光，不切割、不加分。
5. 快速连续切 2 / 3 / 5 个图标：依次出现 `COMBO x2`、`COMBO x3`、`COMBO x5` 大字播报和环形粒子；8 连出现 `GREAT COMBO x8` 并伴随屏震。
6. 等到开局 6 秒后，出现带橙红菱形警示框的炸弹。切中炸弹：屏幕震动、短暂橙色闪光、橙红像素火球、`-1 LIFE`，连击清零；漏掉炸弹不扣命。
7. 放任普通图标飞出屏幕：右上角生命心形逐个变暗；连续漏掉 3 个进入 `OUT OF LIVES`。
8. 等待 90 秒：进入 `TIME'S UP`。
9. 在结算页选择 `PLAY AGAIN`：分数回到 `000000`、生命恢复 3 颗、旧图标和特效清空。
10. 退出游戏后检查桌面：图标位置、名称和文件均未改变。
11. 可选：运行 `python test_effects.py --live`，用 `Space` 逐一查看 6 种特效演示；`Esc` 退出。

## 阶段 1 测试程序

### 运行

```bat
python test_desktop_icons.py
```

可选参数：

| 参数 | 作用 |
| --- | --- |
| `--snapshot` | 不进入交互循环，渲染两个视图并保存 PNG 后退出 |
| `--auto-quit 3` | 打开交互窗口，3 秒后自动关闭 |
| `--out D:\some\dir` | 指定报告/图标/截图输出目录（默认 `test_output/`） |

窗口内操作：

| 按键 | 作用 |
| --- | --- |
| `Tab` | 在“桌面布局视图”和“缩略图视图”之间切换 |
| `S` | 保存当前两个视图的截图 |
| `R` | 重新读取桌面图标（只读） |
| `←` / `→` | 缩略图视图翻页 |
| `Esc` | 退出 |

### 输出

- 控制台：DPI 模式、屏幕物理尺寸、ListView 句柄、图标总数、成功/跳过数量、每个图标的名称、屏幕坐标、图像尺寸、alpha 范围、图像来源
- `test_output/icons/`：每个图标的 RGBA PNG（默认 256 × 256，文件名带序号），可单独检查透明通道
- `test_output/test_desktop_icons_report.txt`：UTF-8 完整报告与失败明细
- `test_output/test_desktop_layout.png`：按真实屏幕坐标等比缩放的布局视图
- `test_output/test_desktop_thumbnails.png`：带名称和坐标的缩略图网格，棋盘格表示透明像素

`test_output/` 是测试产物，可以随时删除，重新运行会再生成。

### 本机测试结果（2026-11-17）

环境：Windows 10 22H2（10.0.22000）、Python 3.11.2、pygame 2.6.1、pywin32、Pillow。

| 项目 | 结果 |
| --- | --- |
| DPI 感知 | `per-monitor-v2` |
| 屏幕物理尺寸 | 2560 × 1600 |
| 桌面 ListView | 找到，项目总数 112 |
| 成功读取 | **112 / 112** |
| 跳过/失败 | **0** |
| 读取耗时 | 0.39 – 0.59 秒（多次运行） |
| 图标图像 | 全部 256 × 256 RGBA（阶段 6 默认请求 256 px），透明通道范围 `(0, 255)` |
| 含透明/半透明像素 | 111 / 112（其余 1 个为不透明图标） |
| 名称解析 | 112 个名称全部匹配到 Shell 命名空间路径（含虚拟项） |

坐标示例：`auralis_tkinter → (366, 1178)`、`MiroFish-main → (21, 2)`，桌面左上角虚拟项位于 `(0, 0)` 附近。连续两次读取的名称与坐标完全一致。

## 读取原理

### 1. 定位桌面列表控件

1. `FindWindowW("Progman")`
2. `FindWindowExW(progman, "SHELLDLL_DefView")`
3. `FindWindowExW(defView, "SysListView32")`

如果 `Progman` 下找不到 `SHELLDLL_DefView`（例如 Wallpaper Engine 或外壳重排后），用 `EnumWindows` 遍历顶层窗口查找 `SHELLDLL_DefView`，再取其中的 `SysListView32`。

### 2. 跨进程读取名称、坐标

桌面列表控件属于 `explorer.exe`，因此使用：

- `OpenProcess(PROCESS_VM_OPERATION | PROCESS_VM_READ | PROCESS_VM_WRITE)`
- `VirtualAllocEx` + `WriteProcessMemory` 在 explorer 中准备 `LVITEMW` 和文本缓冲区
- `SendMessageTimeoutW(..., SMTO_ABORTIFHUNG, 2000ms)`
  - `LVM_GETITEMCOUNT (0x1004)`
  - `LVM_GETITEMPOSITION (0x1010)`
  - `LVM_GETITEMTEXTW (0x1073)`
- `ReadProcessMemory` 取回 UTF-16 名称与 `POINT`
- `ClientToScreen(listView, POINT)` 把客户区坐标转换为屏幕坐标

`LVITEMW` 在 x64 下大小为 88 字节，已按真实结构定义，不使用猜测偏移。

### 3. 名称 → Shell 路径

图标图像不通过跨进程 ImageList 获取（见“已知限制”）。改为：

- `Shell.Application` → `NameSpace(0)` → `Items()`，用显示名称匹配 `Name`，取 `Path`
- 普通文件返回 `C:\...` 路径
- 虚拟项返回 `::{CLSID}` 解析名，例如：
  - 此电脑 `::{20D04FE0-3AEA-1069-A2D8-08002B30309D}`
  - 回收站 `::{645FF040-5081-101B-9F08-00AA002F954E}`

如果 COM 枚举不可用，会退化为在用户/公共桌面目录中按文件名匹配，但虚拟项将无法解析。

### 4. 提取真实图标并转为 Pygame Surface

主路径（阶段 6 起）：

1. `SHParseDisplayName(path)` 得到 PIDL
2. `SHCreateItemFromParsingName` 取得 Shell 项，`BindToHandler` 到 `IShellItemImageFactory`
3. `GetImage(SIZE(256, 256), SIIGBF_ICONONLY | SIIGBF_BIGGERSIZEOK)` 返回 32bpp 位图
4. 按 `GetImage` 的直通 alpha 约定转换 BGRA → RGBA；若 alpha 全为 0，则按掩码/不透明处理
5. `DeleteObject` / `CoTaskMemFree` 释放位图与 Shell 接口
6. `pygame.image.frombuffer(rgba_bytes, size, "RGBA").copy()` 生成带 `SRCALPHA` 的 Surface

回退路径（Shell 不提供大图时）：

1. `SHGetFileInfoW(..., SHGFI_ICON | SHGFI_LARGEICON | SHGFI_PIDL)` 得到系统大图标 HICON
2. `GetIconInfo` + `GetObjectW(BITMAP)` 取尺寸与位图句柄
3. `GetDIBits` 以 32bpp、top-down 方式读取颜色位图，再转 RGBA
4. 若 alpha 全为 0（旧式图标），读取 `hbmMask`，白色视为透明，生成 alpha 通道

实测该路径对普通文件、快捷方式、文件夹和回收站等虚拟项均有效；本机 112/112 个图标都走 256 px 主路径。

### 5. DPI 处理

游戏和测试程序在创建任何窗口之前调用：

- `SetProcessDpiAwarenessContext(PER_MONITOR_AWARE_V2)`（首选）
- `SetProcessDpiAwareness(PROCESS_PER_MONITOR_DPI_AWARE)`
- `SetProcessDPIAware()`（回退）

本机 150% 缩放下，DPI 感知进程得到物理分辨率 2560 × 1600 与 256 × 256 Shell 位图；未开启 DPI 感知时系统会把坐标虚拟化，Shell 也可能只返回更小的位图。

### 6. 错误处理

- 找不到桌面 ListView 或无法打开 explorer 进程：`DesktopReadError`；游戏捕获后使用回退图标，阶段 1 测试程序打印原因并退出
- 单个图标名称、坐标、路径或图像读取失败：记录 `IconReadError(index, name, stage, message)`，跳过该图标继续
- 测试报告与窗口顶部均显示成功/失败数量

## 只读与安全

阶段 1–5 的桌面访问只使用读取类 API：

- `LVM_GETITEMCOUNT` / `LVM_GETITEMPOSITION` / `LVM_GETITEMTEXTW`，没有 `LVM_SETITEMPOSITION`、重命名或删除消息
- `ReadProcessMemory`，没有对桌面布局的写入
- `Shell.Application` 仅枚举名称与路径
- `IShellItemImageFactory::GetImage` 仅请求图标位图，不修改文件
- 游戏对图标 Surface 只做 `copy()`、`smoothscale()`、`rotate()` 等内存内图像操作
- 测试程序只在项目 `test_output/` 下写报告、PNG 和截图
- 持久化写入只有游戏存档 `save.json`（最高分与设置）和阶段 6 的 `desktop_backup.json`（隐藏状态标记）；自动化测试全部写到系统临时目录

阶段 6 的桌面背景模式增加了**唯一一项**桌面写操作，并且严格受限：

- 只对已校验的 `SysListView32` 图标控件调用 `ShowWindow(SW_HIDE)` / `ShowWindow(SW_SHOWNA)`，改变的是窗口显示状态
- 不使用 `LVM_SETITEMPOSITION`、不写注册表、不重启/结束 Explorer、不移动/删除/重命名任何桌面项、不清空桌面文件夹
- 隐藏前必须匹配 `Progman` 或 `WorkerW` 宿主 + `SHELLDLL_DefView` 父链 + `explorer.exe` 属主；任何一步不匹配就放弃隐藏并报告原因
- 原始样式/扩展样式/可见性/属主写入 `%APPDATA%\DesktopSlash\desktop_backup.json`；恢复时只恢复这个控件并删除标记
- 恢复路径覆盖正常退出、用户退出、初始化失败、运行异常、`Ctrl+C`、`atexit`、看门狗和下次启动的旧标记清理；恢复是幂等的
- 覆盖层只改变**游戏自己窗口**的样式与 `WNDPROC`，不触碰 explorer 或其他进程的窗口；鼠标接管与点击穿透互斥，不长期持有 `SetCapture` 或 `ClipCursor`

不会移动桌面图标、不会删除或修改桌面文件、不会通过修改桌面布局来模拟游戏。

`test_gameplay.py`、`test_effects.py`、`test_game_system.py`、`test_overlay_window.py`、`test_stage5_flow.py` 与 `test_desktop_background.py` 都会在测试前后读取桌面并比较名称与屏幕坐标；本机结果为 112 项完全一致（`test_desktop_background.py` 还做了 3 轮隐藏/恢复后的坐标比较）。

## 已知限制与替代方案

1. **碰撞区是圆形近似**：图标使用「图像对角线半径 × 缩放 × 0.88」的圆形碰撞区；旋转后的尖角可能略超出。对 80–128 px 的图标足够稳定，若需要像素级精确切割可改用遮罩/多边形检测。
2. **图标可能重叠**：同屏最多 12 个，随机轨迹可能让图标在视觉上重叠；一次划动切割多个是预期行为。
3. **难度曲线**：90 秒内波次 3–5 → 6–8、速度 ×1 → ×1.38、间隔 1.5 → 0.72 秒、炸弹概率 18% → 48%，同屏上限始终 12 个。3 条生命下连续漏掉 3 个普通图标仍会结束回合；若觉得过难，可降低 `DIFFICULTY_*`、降低 `ICON_APEX_MAX` 或提高 `STARTING_LIVES`。难度速度倍率会同时缩短滞空时间，但顶点比例保持不变。
4. **速度判定依赖鼠标事件**：`SlashDetector` 用事件时间估算像素/秒；不同鼠标回报率或系统负载下，同一手势的估算会有差异。阈值 `SLASH_MIN_SPEED` 可调。
5. **桌面读取失败时使用回退图标**：这是有意的降级，不是真实桌面图标；菜单会明确标注 `FALLBACK ICONS`。
6. **图标分辨率**：阶段 6 已改用 `IShellItemImageFactory::GetImage` 请求 256 px 位图，本机 112/112 个图标均返回 256 px；若某个 Shell 项只提供小图，游戏会等比放大，不伪造细节。`SHGetFileInfoW` 的 48 px 路径仍作为单项失败时的兼容回退，但不再是主路径。
7. **跨进程 ImageList 不可用**：已实测 `LVM_GETIMAGELIST` 得到的 `HIMAGELIST` 属于 explorer 进程，本进程调用 `ImageList_GetIcon` 全部返回 `NULL`。因此图像改为按 Shell 命名空间逐项提取。
8. **虚拟项依赖 COM**：此电脑、回收站、控制面板等没有文件路径，必须通过 `Shell.Application` + `::{CLSID}` 解析。若 pywin32/COM 不可用，这些项会被跳过并记录错误。
9. **重名项**：名称到路径的映射按显示名称建立，遇到同名项时复用第一个匹配路径；名称和坐标仍逐项读取。
10. **权限**：读取需要能打开 explorer 进程。若游戏与 explorer 完整性级别差异过大，`OpenProcess` 会失败；普通用户桌面环境无需管理员权限。
11. **多显示器/第三方桌面工具**：当前只读取找到的第一个桌面 `SysListView32`。若系统版本或桌面美化工具创建多个列表控件，只覆盖主控件。
12. **测试覆盖**：`test_gameplay.py`、`test_effects.py`、`test_game_system.py`、`test_stage5_flow.py`、`test_performance.py` 与 `test_visual_upgrade.py` 使用 dummy 视频驱动验证逻辑、物理和离屏渲染；`test_overlay_window.py`、`test_desktop_background.py --live-overlay` 会创建真实窗口验证样式、命中测试、隐藏/恢复与生命周期。真实鼠标手感、实际音量、壁纸合成观感仍建议按“手动验证清单”确认。锁屏/安全桌面状态下真实截图与鼠标探针会被跳过。
13. **特效有硬上限**：粒子上限 900、特效对象上限 96、刀光 32 点。极密集操作下多余火花/特效会被丢弃而不是继续分配内存；这是性能保护，不是逻辑错误。
14. **屏震只影响画面**：`ScreenFX` 在 `present` 阶段偏移最终画面，鼠标坐标、命中判定和 HUD 布局都不随震动移动。
15. **闪光可能压低暗部对比**：全屏闪光为加色混合，强度过高会让深色背景整体泛橙。默认 `BOMB_FLASH_ALPHA=60` 已调低；若仍觉得刺眼可继续降低或缩短 `BOMB_FLASH_DURATION`。
16. **音效为程序合成**：没有加载外部音频素材，音色偏 8-bit；没有可用混音设备时 `SoundBank` 自动禁用，游戏其余部分不受影响。
17. **存档是纯本地 JSON**：位置为 `%APPDATA%\DesktopSlash\save.json`；删除它会清空最高分与设置。文件损坏会回退默认值，写入失败只记录 `last_error`，不会阻塞游戏，但该次改动无法跨启动保存。
18. **只有一个模式**：没有模式选择或难度选项；暂停已是完整功能（`Esc / P`），暂停会释放鼠标但保留本局进度。
19. **键色透明不是逐像素 alpha**：`LWA_COLORKEY` 只把精确等于键色的像素变透明，渐变/半透明像素会与近黑键色混合再显示，因此覆盖层关闭了合成波背景、CRT 扫描线和大幅半透明遮罩。阶段 6 为“桌面背景模式”改为在覆盖层内自行绘制壁纸，并叠加 12% 暗化；若需要真正的半透明桌面效果，需要改用 `WS_EX_NOREDIRECTIONBITMAP` + DirectComposition 或 `UpdateLayeredWindow` 的逐像素 alpha 方案，复杂度和 Win32 依赖明显更高。
20. **锁屏与安全桌面**：Windows 不允许普通应用显示在锁屏、UAC 或安全桌面上。覆盖层在这些状态下不可见、也收不到真实鼠标；解锁后自动恢复。`test_overlay_window.py` 检测到锁屏会跳过真实截图/输入探针。
21. **系统悬浮窗可能压在上面**：输入法候选窗、音量 OSD、部分录屏/悬浮工具使用更高 z-order；覆盖层和输入盾窗在它们之下是正常的，落在这些窗口上的点击会归它们处理。
22. **多显示器覆盖单个屏幕**：一次只覆盖 `--monitor` 指定的显示器工作区（默认主屏、保留任务栏）。壁纸按该显示器的壁纸与样式裁剪；另一台显示器的图标不会被隐藏。显示器热插拔或 Windows 缩放比例变化后建议重启游戏，让窗口尺寸和 DPI 重新计算。
23. **切换输入模式需要消息处理**：接管时显示输入盾窗，穿透时隐藏盾窗并恢复 `WS_EX_TRANSPARENT`。极少数全局鼠标钩子程序（远程控制、宏工具）可能缓存窗口信息，切换后移动一次鼠标即可刷新命中结果。
24. **设置立即生效但无确认弹窗**：音量、震动、扫描线和语言点击后马上应用并写入存档；如果不希望保留，需要手动改回。
25. **壁纸是只读快照**：桌面背景由启动时读取的壁纸路径/纯色、`WallpaperStyle`/`TileWallpaper` 和显示器矩形绘制。运行期间更换壁纸或切换主题不会实时更新，需要重启游戏；Windows 的“幻灯片放映”只在启动那一刻取当前图片。
26. **壁纸布局**：优先使用 `IDesktopWallpaper` 的逐显示器路径与样式；当系统只能提供 `TranscodedWallpaper`（整屏合成位图）时，按虚拟桌面矩形 1:1 裁切，因此该路径与原生显示逐像素一致。只有拿到的是未缩放的原始图片时才按 Fill/Fit/Stretch/Tile/Center/Span 近似实现；非主屏或极端比例下可能与 Explorer 有细微差异。暗化 12% 是刻意的视觉取舍，可用 `OVERLAY_WALLPAPER_DIM=0.0` 关闭。
27. **游戏运行期间会盖住其他窗口**：桌面背景模式是一个置顶的、绘制壁纸的窗口，所以玩游戏时浏览器/资源管理器等普通窗口会被壁纸画面遮住；暂停只会把鼠标交还桌面，不会让它们重新显示。需要看其他窗口时按 `Alt+Tab` 或退出游戏（覆盖层保留任务栏/Alt+Tab 入口）。
28. **非 Explorer 桌面不支持隐藏**：只识别标准 `Progman/WorkerW → SHELLDLL_DefView → SysListView32` 且属主为 explorer 的布局。第三方桌面替换工具、Explorer 重启后的异常布局、或权限不足时会拒绝隐藏并在菜单显示原因，游戏仍可用但真实图标会留在画面上。
29. **强杀/断电的恢复窗口**：正常退出、异常退出和看门狗能覆盖绝大多数情况；但如果整个系统断电或看门狗也被同时杀死，图标会保持隐藏，直到下次启动游戏执行 `recover_stale_session()`，或手动运行上文的一条恢复命令。标记文件只记录一个 `ShowWindow` 状态，恢复不会移动或重排图标。
30. **语言字体依赖系统字体**：中文优先使用微软雅黑、等线、黑体等系统字体，项目不内置字体文件；极少数精简 Windows 镜像若缺少全部中文字体，会由 pygame 回退字体渲染，可能缺少个别字形。`--self-test` 会逐字检查并报告缺失字符。
31. **紧急退出不是强杀**：`Ctrl + Shift + Q` 先请求安全退出并优先恢复桌面；只有主流程在 3 秒宽限内没有响应时，才在桌面恢复后调用 `os._exit(0)`。断电、系统崩溃或系统级强杀仍无法 100% 保证恢复，下次启动会自动补做。

## 项目结构

```
DesktopSlash/
├── main.py                     # 入口：CLI、单实例锁、旧标记恢复、看门狗参数、--self-test
├── game_config.py              # 所有可调参数、难度曲线、倍率、特效、配色、字体、覆盖层与性能参数
├── DesktopSlash.spec           # PyInstaller 单文件窗口化打包配置
├── version_info.txt            # EXE 版本信息
├── build_exe.bat               # 清理 → 构建 → 运行打包自检
├── assets/
│   ├── icon.png                # 256x256 窗口/自检图标
│   └── icon.ico                # EXE 多尺寸图标
├── test_visual_upgrade.py      # 阶段 6 图标尺寸/高清来源/抛射顶点/出生带/呼吸/光晕
├── test_desktop_background.py  # 阶段 6 控件校验、隐藏/恢复、旧标记、看门狗、单实例、--live-overlay
├── test_i18n.py                # 中英词表一致性、默认语言/回退、字形、即时切换、布局适配
├── test_shutdown.py            # 统一退出：顺序、幂等、错误隔离、预算、各入口、紧急热键
├── test_wallpaper_fidelity.py  # 壁纸样式 + 原生桌面像素比对（差值图）
├── test_overlay_window.py      # 阶段 5 真实分层窗口样式/命中/透明度/恢复检查（含 --interactive）
├── test_stage5_flow.py         # 阶段 5 覆盖层渲染 + 暂停 + 10 步完整流程
├── test_performance.py         # 阶段 5 帧耗时、缓存上限、长时间内存
├── test_game_system.py         # 阶段 4 存档/菜单/设置/倒计时/结算/重置检查与截图
├── test_effects.py             # 阶段 3 特效检查、截图、总览图、--live 演示
├── test_gameplay.py            # 阶段 2 自动化测试与截图（回归）
├── test_desktop_icons.py       # 阶段 1 独立只读测试程序
├── requirements.txt
├── README.md
├── localization/
│   ├── __init__.py             # 对外导出 t / set_language / current_language / available_languages
│   ├── language_manager.py     # LanguageManager：词表加载、点分键查找、格式化、回退
│   └── translations/
│       ├── zh_CN.json          # 简体中文（默认，71 键）
│       └── en_US.json          # 英文（71 键，与中文键集合一致）
├── core/
│   ├── game.py                 # 窗口、共享系统、固定步长主循环、暂停/继续、桌面隐藏与壁纸背景、统一退出状态机
│   ├── instance_lock.py        # 命名互斥锁：拒绝第二个同时运行的实例
│   ├── phases.py               # GamePhase 枚举（MENU/COUNTDOWN/PLAYING/PAUSED/GAME_OVER）
│   ├── profile.py              # Profile / ProfileStore：JSON 原子读写与容错
│   ├── resources.py            # 源码/打包资源路径（_MEIPASS）
│   ├── frame_stats.py          # 帧耗时滑动窗口（平均/峰值 FPS）
│   ├── self_test.py            # 打包自检（资源、pywin32、桌面控件、图标尺寸、语言/字形、暂停、渲染）
│   ├── state_manager.py        # 状态注册与事件/更新/物理后处理/渲染分发
│   └── states/
│       ├── base.py             # 状态基类（update / post_update / render）
│       ├── menu.py             # MENU：标题、最高分、START/SETTINGS/EXIT 按钮、隐藏失败提示
│       ├── countdown.py        # COUNTDOWN：3-2-1-GO!、缩放动画与逐步音效
│       ├── playing.py          # PLAYING：切割、连击倍率、炸弹、特效调度、HUD
│       ├── paused.py           # PAUSED：冻结的战场、释放鼠标、恢复/菜单/退出
│       └── game_over.py        # GAME_OVER：分数/切割数/最大连击/最高分 + 三个按钮
├── desktop/
│   ├── errors.py               # DesktopReadError / IconReadError
│   ├── win32_desktop.py        # Win32 桌面列表读取、256px Shell 图标提取、DPI
│   ├── desktop_interface.py    # 对外接口：DesktopIcon / DesktopReadResult
│   ├── desktop_background.py   # 图标控件校验、隐藏/恢复、标记文件、看门狗、旧会话恢复
│   └── wallpaper.py            # 只读壁纸路径/纯色/样式（COM → SPI → 注册表 → TranscodedWallpaper）、预合成裁切
├── gameplay/
│   ├── game_icon.py            # GameIcon：物理体、呼吸缩放、柔光/阴影缓存、旋转
│   ├── icon_manager.py         # 波次/出生带生成、顶点反解速度、DPI 缩放、难度应用、漏判
│   ├── difficulty.py           # 单一难度曲线：波次/速度/间隔/炸弹概率
│   ├── bomb.py                 # 程序化炸弹图标（无图片素材）
│   ├── combo_tracker.py        # 连击窗口、里程碑文案/颜色、得分倍率
│   ├── slash_detector.py       # 鼠标轨迹、速度过滤、AABB 预筛选、线段碰撞、多层刀光
│   └── fallback_icons.py       # 桌面读取失败时的程序化图标
├── physics/
│   ├── body.py                 # 物理刚体（位置/速度/重力/阻尼）
│   └── physics_world.py        # 物理世界与原地批量更新
├── effects/
│   ├── effect_manager.py       # 有上限的特效管线
│   ├── particles.py            # 固定容量像素粒子池（爆发/刀光火花/碎片/环形/炸弹）
│   ├── screen_fx.py            # 全屏震动、闪光、CRT 扫描线、覆盖层键色清屏
│   ├── slice_flash.py          # 切割白色星芒
│   ├── icon_fragments.py       # 左右碎片 + 重力/旋转/淡出
│   ├── floating_text.py        # +10 / -1 LIFE 像素飘字
│   ├── combo_callout.py        # COMBO / GREAT COMBO 大字播报
│   └── bomb_blast.py           # 橙红像素火球
├── audio/
│   └── sfx.py                  # 程序合成音效（slice/combo/bomb/miss/click/count/go）
├── ui/
│   ├── fonts.py                # 字体加载与缓存
│   ├── text.py                 # 像素文本 + 有上限的文字渲染缓存
│   ├── background.py           # 合成波背景（覆盖层模式禁用）+ 尘埃精灵缓存
│   ├── button.py               # PixelButton 与模态像素面板
│   ├── settings.py             # 设置遮罩面板：音量 / 震动 / 扫描线 / 语言 / BACK
│   └── hud.py                  # 分数 / 计时 / 生命 / 连击倍率 / 最高分（面板缓存）
└── window/
    ├── win32_overlay.py        # 显示器枚举、DPI、分层样式、WNDPROC 子类化、输入模式、捕获恢复
    └── window_manager.py       # 窗口/覆盖层创建、重建、关闭、atexit 紧急恢复
```

测试运行后还会生成 `test_output/`（截图、报告、图标 PNG），可安全删除。

各包均包含 `__init__.py`。

## 架构与主循环

渲染帧：

```
pygame 事件（带帧内插值时间） → StateManager → 当前 GameState
```

固定逻辑步（`Game.advance(frame_time)`）：

```
State.update(dt)          # 计时、生成/旋转、刀光衰减、连击计时、火花采样
PhysicsWorld.update(dt)   # 所有 GameIcon 的 PhysicsBody 积分
State.post_update(dt)     # 物理之后：漏判、线段命中、计分、扣命、炸弹、回合结束
EffectManager.update(dt)  # 碎片、白闪、飘字、连击播报、火球
PixelParticles.update(dt) # 固定池粒子推进与过期回收
Background.update(dt)     # 环境尘埃漂移
ScreenFX.update(dt)       # 震动/闪光计时
```

渲染（`Game._render`）：

```
Wallpaper backdrop blit               # 覆盖层：只读壁纸 + 12% 暗化
States.render(scene)                  # 背景、图标、刀光、粒子、特效、HUD
ScreenFX.present(scene, screen)       # 震动偏移 + 扫描线 + 闪光
```

特效只在 `present` 阶段作用于最终画面，鼠标坐标与碰撞几何始终基于未抖动的场景坐标。

- 渲染帧率：`game_config.FPS = 60`
- 逻辑步长：`game_config.FIXED_DT = 1/120` 秒
- 帧时间超过 `MAX_FRAME_TIME` 时被截断，并限制单帧最大模拟步数，避免卡顿后的“死亡螺旋”
- 物理与碰撞判定始终按固定步长推进；渲染帧率变化不会改变每秒钟的逻辑步数
- 鼠标事件在一个渲染帧内被分配到该帧的时间区间，`SlashDetector` 用 `距离 / 时间` 估算速度；慢速拖动不会生成可切割线段
- 状态切换全部通过 `Game.start_round()`、`begin_play()`、`finish_round()`、`go_to_menu()` 完成，状态类不直接操作其他状态

主要对象关系：

```
Game
├─ SingleInstanceLock ── 命名互斥锁（main.py）
├─ DesktopBackgroundManager ── 校验控件 → 写标记 → 隐藏/恢复图标 + 看门狗
├─ Wallpaper backdrop ── 只读壁纸路径/样式 → 当前显示器尺寸的 Surface
├─ ProfileStore ── 读取/原子写入 save.json（最高分 + 设置）
├─ DesktopInterface ── 只读读取 256px 图标 → Surface 列表
├─ IconManager ── 逻辑尺寸×DPI → 出生带 → 顶点反解速度 → GameIcon + PhysicsBody（含炸弹）
├─ PhysicsWorld ── 固定步长积分
├─ SlashDetector ── 鼠标轨迹 → SlashSegment → SlashHit + 火花采样
├─ ComboTracker ── 连击计数/窗口/最佳连击/得分倍率
├─ EffectManager ── IconFragments / SliceFlash / FloatingText / ComboCallout / BombBlast
├─ PixelParticles ── 固定 900 槽粒子池
├─ ScreenFX ── 震动 / 闪光 / 扫描线（受设置开关控制）
├─ SoundBank ── 程序合成音效（受设置音量控制，可静音）
├─ HUD / Background
└─ StateManager
   ├─ MenuState ── 三个按钮 + SettingsOverlay
   ├─ CountdownState ── 3-2-1-GO! 时间轴与音效
   ├─ PlayingState ── 组织生成、判定、倍率计分、连击、炸弹、生命与回合结束
   └─ GameOverState ── 统计、最高分与新纪录、三个按钮
```

- `GameIcon` 本身只负责图像、旋转/缩放和状态标记，运动由 `PhysicsBody` 完成
- `IconManager` 只负责“生成什么、什么时候生成、什么时候算漏掉”，不参与计分；它每波向 `difficulty_at(elapsed)` 询问波次/速度/间隔/炸弹概率
- `Difficulty` 是纯函数快照，不持有状态、不读写存档，也不包含任何模式分支
- `ProfileStore` 是唯一持久化入口；`Game` 读取后把音量交给 `SoundBank`、把开关交给 `ScreenFX`，设置面板只调用 `Game` 的方法
- `SlashDetector` 与生成、计分完全解耦，只输出命中的图标和命中点；火花采样仅用于粒子表现
- `PlayingState` 负责把命中转成得分（`10 × 倍率`）/爆炸、把漏判转成扣命，并触发回合结束
- `Game.start_round()` 统一重置分数、生命、统计、连击、图标、物理体、刀光、特效、粒子和屏幕效果，供菜单与结算页复用
- 所有特效对象只实现 `update(dt)` / `draw(surface)` / `finished`，由 `EffectManager` 统一回收；它们不持有 `GameIcon` 或物理体，不会参与命中判定

桌面读取与游戏逻辑的边界：

```
Game / test_desktop_icons.py ──> DesktopInterface.read_desktop_icons()
                                    └─ Win32DesktopReader（仅读取）
                                          ├─ 列表控件：名称、坐标
                                          └─ Shell 命名空间：路径、HICON → PIL → Surface
```

`DesktopInterface` 不持有桌面布局的写权限；阶段 3 只消费返回的 `DesktopIcon.image`，复制后用于游戏。

## 配置

所有游戏参数集中在 `game_config.py`：

| 参数组 | 说明 |
| --- | --- |
| `WINDOW_SIZE` / `WINDOW_TITLE` | 窗口尺寸与标题 |
| `FPS` / `FIXED_DT` / `MAX_FRAME_TIME` | 渲染帧率、逻辑步长、单帧截断 |
| `ROUND_SECONDS` | 回合时长（90 秒） |
| `COUNTDOWN_STEP_SECONDS` / `COUNTDOWN_GO_SECONDS` / `COUNTDOWN_SECONDS` | 3、2、1 各 1 秒 + `GO!` 0.8 秒，共 3.8 秒 |
| `STARTING_LIVES` / `SCORE_PER_ICON` | 初始生命与单图标基础分 |
| `COMBO_MULTIPLIER_STEP` / `COMBO_MULTIPLIER_MAX` | 每 3 连提升一级倍率，最高 5 倍 |
| `PHYSICS_GRAVITY` / `PHYSICS_LINEAR_DRAG` / `PHYSICS_MAX_SPEED` | 全局重力、阻尼、最大速度 |
| `ICON_WAVE_MIN` / `ICON_WAVE_MAX` / `ICON_SPAWN_INTERVAL` / `ICON_SPAWN_JITTER` | 起始波次数量与间隔（难度曲线在此基础上递增） |
| `DIFFICULTY_*` | 曲线幂次、波次加成上限、速度上限、生成间隔下限、炸弹概率上限 |
| `ICON_MAX_ACTIVE` / `ICON_SPAWN_MARGIN` / `ICON_SPAWN_BELOW` / `ICON_MISS_MARGIN` | 同屏上限、生成位置、漏判边界 |
| `ICON_SIZE_SMALL/NORMAL/LARGE/SPECIAL` / `ICON_SIZE_CLASSES` / `ICON_SIZE_WEIGHTS` / `ICON_SIZE_JITTER` | 80/96/112/128 逻辑尺寸、抽取权重与 ±5% 抖动 |
| `ICON_SIZE_REFERENCE` / `ICON_SIZE_RESOLUTION_MIN/MAX` / `ICON_SOURCE_SIZE` | 尺寸缩放基准分辨率、分辨率系数范围、Shell 位图请求尺寸（256） |
| `ICON_APEX_MIN/MAX` / `ICON_APEX_RARE_MIN/MAX` / `ICON_APEX_RARE_CHANCE` | 常规与罕见的顶点屏高比例 |
| `ICON_LAUNCH_DRAG_COMPENSATION` / `ICON_DRAG_COMP_HEIGHT_SLOPE` / `ICON_DRAG_COMP_MIN/MAX` | 阻尼补偿基准、随屏幕高度的斜率与夹取范围 |
| `ICON_SPAWN_ZONES` / `ICON_SPAWN_MIN_SEPARATION` | 底部出生带数量、同波最小间距（较大图标尺寸的倍数） |
| `ICON_VX_MIN` / `ICON_VX_MAX` / `ICON_VX_OUTWARD_CHANCE` | 水平速度范围与向外侧飞的概率 |
| `ICON_GRAVITY_SCALE_MIN` / `ICON_GRAVITY_SCALE_MAX` | 每个图标的重量差异 |
| `ICON_BREATHE_AMPLITUDE` / `ICON_BREATHE_PERIOD` / `ICON_SCALE_QUANTUM` | 呼吸缩放幅度/周期与缓存量化步长 |
| `ICON_GLOW_ENABLED` / `ICON_GLOW_COLOR` / `ICON_GLOW_ALPHA` / `ICON_GLOW_PADDING` | 图标轮廓柔光开关、颜色、不透明度与留白 |
| `ICON_SPIN_MIN` / `ICON_SPIN_MAX` / `ICON_HITBOX_SCALE` | 旋转速度与碰撞区缩放 |
| `SLASH_MIN_SPEED` / `SLASH_MIN_SEGMENT_DISTANCE` / `SLASH_HIT_PADDING` | 切割速度门槛与线段采样 |
| `SLASH_TRAIL_LIFETIME` / `SLASH_TRAIL_RELEASE_FADE` / `SLASH_TRAIL_MAX_POINTS` | 刀光长度与松开后淡出 |
| `SLASH_TRAIL_OUTER/GLOW/CORE_COLOR` / `*_WIDTH` | 三层刀光颜色与宽度 |
| `SLASH_TRAIL_SPARK_*` | 刀光像素火花数量、颜色、速度、寿命、尺寸、重力 |
| `FRAGMENT_*` / `SLICE_PIXEL_*` / `SLICE_FLASH_*` / `SCORE_POPUP_*` | 左右碎片、8–20 像素碎片、白色星芒、`+10` 飘字 |
| `PARTICLE_POOL_MAX` / `PIXEL_SNAP` / `PARTICLE_ADDITIVE` / `PARTICLE_*` | 粒子池容量、像素吸附、加色混合与默认粒子参数 |
| `BOMB_*` | 炸弹出现时间/概率/尺寸、扣命、粒子、火球半径/寿命、闪光、屏震、核心色 |
| `COMBO_*` | 连击窗口、高连击阈值、GREAT 阈值/步长、倍数分级、文案、播报时长、额外粒子、闪光、屏震、颜色 |
| `EFFECT_MAX_ACTIVE` / `SCREEN_SHAKE_MAX` / `SCANLINE_*` / `FLASH_ADDITIVE` | 特效上限、震动上限、扫描线、闪光混合模式 |
| `AUDIO_ENABLED` / `AUDIO_VOLUME` / `AUDIO_SAMPLE_RATE` / `DEFAULT_VOLUME` / `VOLUME_STEP` | 程序合成音效开关、默认音量、采样率、存档默认音量与每次调整步长 |
| `PROFILE_DIR_NAME` / `PROFILE_FILE_NAME` / `PROFILE_VERSION` | 存档目录名、文件名与版本号 |
| `BACKGROUND_*` / `AMBIENT_PIXEL_*` | 透视网格、星点、环境尘埃 |
| `FALLBACK_ICON_*` | 回退图标数量、尺寸、颜色 |
| `COLOR_*` / `FONT_*` / `UI_*` | 街机配色、字体、HUD/按钮/设置面板布局、生命心形 |
| `WINDOW_OVERLAY` / `WINDOW_OVERLAY_MONITOR` / `WINDOW_OVERLAY_USE_WORK_AREA` | 是否使用透明覆盖层、默认显示器索引、是否保留任务栏工作区 |
| `WINDOW_TRANSPARENT_COLOR_KEY` / `WINDOW_TOPMOST` / `WINDOW_TOOLWINDOW` | 键色（默认 `(1, 0, 2)`）、置顶、是否隐藏任务栏入口（默认 `False`，保留入口以便切回游戏） |
| `PAUSE_INPUT_RELEASE` / `PAUSE_RESUME_GUARD` / `PAUSE_KEYS` | 暂停时释放鼠标、恢复键防抖时间、暂停键 |
| `WINDOW_OVERLAY_SCANLINES` | 覆盖层扫描线（默认关闭） |
| `TEXT_CACHE_MAX` / `ICON_TRANSFORM_CACHE` / `PERF_SAMPLE_FRAMES` | 文字缓存上限、图标缩放缓存、帧统计窗口 |
| `DESKTOP_HIDE_ICONS` / `DESKTOP_HIDE_WATCHDOG` / `DESKTOP_RESTORE_LOG` | 桌面背景模式开关、看门狗开关、恢复日志文件名 |
| `OVERLAY_WALLPAPER_BACKDROP` / `OVERLAY_WALLPAPER_DIM` | 是否在覆盖层绘制只读壁纸、暗化比例（0–1） |

### 透明覆盖层机制

1. `pygame.display.set_mode(..., pygame.NOFRAME)` 创建无边框窗口，尺寸取所选显示器 `rcWork`（物理像素）。
2. `SetWindowLongPtrW(GWL_EXSTYLE)` 加上 `WS_EX_LAYERED | WS_EX_TOPMOST | WS_EX_APPWINDOW`，去掉 `WS_EX_TRANSPARENT`。保留任务栏/Alt+Tab 入口，切到别的窗口后还能点回来（`WINDOW_TOOLWINDOW=True` 可改为完全隐藏入口的桌面挂件模式）。
3. `SetLayeredWindowAttributes(hwnd, keyref, 0, LWA_COLORKEY)` 把键色设为全透明；每帧先 `scene.fill(key)`，桌面就从键色像素处透出。
4. `SetWindowLongPtrW(GWLP_WNDPROC)` 子类化窗口过程，拦截 `WM_NCHITTEST`：接管返回 `HTCLIENT`，释放返回 `HTTRANSPARENT`。
5. **输入盾窗**：这是本阶段解决“透明 + 穿透 + 输入冲突”的关键。实测 Windows 11 会把键色像素的鼠标事件直接交给下层窗口，`HTCLIENT` 并不能让空白处起刀。因此另建一个 `WS_EX_LAYERED | WS_EX_TOOLWINDOW | WS_EX_TOPMOST | WS_EX_NOACTIVATE` 的 `WS_POPUP` 窗口，盖住同一工作区，`SetLayeredWindowAttributes(hwnd, 0, 1, LWA_ALPHA)`；它只让画面变暗 0.4%，但每个像素都可命中：
   - 盾窗把 `WM_MOUSEMOVE / WM_LBUTTONDOWN / WM_LBUTTONUP` 以客户区坐标 `PostMessageW` 给 SDL 窗口，Pygame 收到普通鼠标事件；按下前先补发一次同坐标移动，保证 `event.pos` 正确；
   - 若 SDL 建立鼠标捕获，后续移动直接进入 SDL，盾窗收不到消息，因此不会重复；没有捕获时仍由盾窗逐条转发，两种路径都可用；
   - 释放模式直接 `ShowWindow(SW_HIDE)` 隐藏盾窗，桌面立刻恢复点击。
6. 暂停/退出时 `SetCapture(None)` + `ClipCursor(None)`，销毁盾窗并还原样式与原始 `WNDPROC`；`atexit` 与崩溃处理再兜底一次。

`SetWindowLongPtrW` 的失败、显示器缺失或 SDL 驱动不支持时，`WindowManager` 会自动回退到普通窗口，并在菜单中显示 `WINDOW MODE`。

### 桌面背景模式（阶段 6）

覆盖层是整个显示器的置顶窗口，单纯“透明”只会让用户看见桌面真实图标，无法实现“壁纸保留、图标消失”的效果。阶段 6 的处理分成两部分：

1. **临时隐藏真实图标**（`DesktopBackgroundManager`）：
   - 从 `Progman` 以及所有顶层 `WorkerW` 上查找 `SHELLDLL_DefView`，再找其下的 `SysListView32`；
   - 用 `GetWindowThreadProcessId` + `QueryFullProcessImageNameW` 确认属主是 `explorer.exe`；
   - 读取 `GWL_STYLE` / `GWL_EXSTYLE` / 可见性，写入 `%APPDATA%\DesktopSlash\desktop_backup.json`；
   - `ShowWindow(listview, SW_HIDE)`；
   - 恢复时按标记调用 `ShowWindow(SW_SHOWNA)`，确认样式与标记一致后删除标记；重复调用无副作用。
2. **自行绘制壁纸**（`desktop/wallpaper.py`）：
   - 读取顺序：`IDesktopWallpaper`（逐显示器路径 + 样式）→ 全局 `GetWallpaper(NULL)` → `SystemParametersInfoW(SPI_GETDESKWALLPAPER)` → 注册表 `HKCU\Control Panel\Desktop` → `%APPDATA%\Microsoft\Windows\Themes\TranscodedWallpaper`（Windows 自己合成好的整屏位图）→ `GetSysColor(COLOR_DESKTOP)` 纯色；
   - **无噪点**：源为 `TranscodedWallpaper` 时按虚拟桌面坐标把原始像素直接裁切到当前显示器（`precomposed=True`），不缩放、不重采样、不加滤镜、不做颜色调整；壁纸与显示器同尺寸时同样 1:1 使用；
   - 常规路径按 `WallpaperStyle`（Fill / Fit / Stretch / Tile / Center / Span）与 `TileWallpaper` 裁剪或平铺，仅在需要缩放时使用 Pillow LANCZOS，并且先转不透明 RGB，避免 alpha 边缘和压缩伪影；
   - 仅在壁纸之上叠加 `OVERLAY_WALLPAPER_DIM` 暗化（这是游戏可读性需要，可在 `game_config.py` 调为 0）；
   - 壁纸数据只在启动时读取一次，运行期间不再访问系统设置。

因此游戏开始时用户看到的是“自己的壁纸 + 游戏菜单”，真实图标隐藏；暂停只释放鼠标，图标仍隐藏；退出时覆盖层先销毁、再恢复图标，桌面回到启动前状态。若隐藏失败，游戏会在菜单底部用红字显示具体原因，并继续以普通透明覆盖层运行。

## 打包 EXE

项目已包含 `DesktopSlash.spec`、`version_info.txt`、`assets/icon.ico` 和一键脚本 `build_exe.bat`。

### 一键构建

```bat
cd /d E:\Desktop\fruit\DesktopSlash
.venv\Scripts\activate
python -m pip install -r requirements.txt
build_exe.bat
```

脚本会清理 `build/` 与 `dist/`，用 `DesktopSlash.spec` 构建单文件窗口化 EXE，然后自动运行打包自检。成功输出：

```
dist\DesktopSlash.exe
dist\desktop_slash_self_test.txt
```

也可以手动执行：

```bat
python -m PyInstaller --noconfirm --clean DesktopSlash.spec
dist\DesktopSlash.exe --self-test
```

### 打包内容

| 资源 | 处理方式 | 自检 |
| --- | --- | --- |
| 窗口/EXE 图标 | `assets/icon.png` + `assets/icon.ico`，spec 的 `datas` 与 `EXE(icon=...)` | 检查存在、PNG 为 256×256 |
| 语言词表 | `localization/translations/zh_CN.json` + `en_US.json`（spec 的 `datas`） | 两套词表加载、键集合一致、中文逐字无豆腐块 |
| 字体 | pygame 内置字体 + 系统中文回退（雅黑/等线等），无需外部文件 | 渲染标题与中文文本 |
| 音效 | 程序合成，无音频素材 | 检查 7 个 cue 或音频设备缺失提示 |
| 桌面读取 | `ctypes` + `PIL` + `pythoncom` / `win32com.client`（`hiddenimports`） | COM 导入、112 个真实图标、256px 请求、80–128px 屏幕尺寸 |
| 桌面控件 | `DesktopBackgroundManager`（ctypes） | 校验 Progman/WorkerW + explorer.exe；报告 hwnd/host/owner |
| 图标隐藏/恢复 | `ShowWindow` + 标记文件 + `atexit` + 看门狗 | 自检调用恢复；打包实机冒烟验证 112 个图标坐标不变 |
| 停止/崩溃恢复 | `atexit` + `emergency_restore` + 独立看门狗子进程 | 自检与 `test_desktop_background.py` 崩溃子进程测试 |

EXE 约 23 MB，启动时 PyInstaller 会解压到临时目录（首次启动略慢）。`--window`、`--overlay`、`--monitor N` 参数对 EXE 同样有效。看门狗会以同一个 EXE 加隐藏参数 `--desktop-watchdog PID HWND` 启动，因此打包版也能在父进程被强杀后恢复图标。EXE 不需要管理员权限。

## 后续可选改进

1. 逐像素 alpha 覆盖层（DirectComposition / `UpdateLayeredWindow`），让桌面背景真正实时可见而不是绘制壁纸快照
2. 壁纸幻灯片/主题切换的运行时热更新（当前只在启动时读取）
3. 对局统计（命中率、炸弹数、每分钟得分）与本地排行榜
4. 更多炸弹类型、连击奖励分与更细的难度曲线
5. 把图标隐藏状态做成可配置（仅隐藏图标 / 保留图标 / 模糊壁纸），仍保持单模式玩法
6. 代码签名与安装包（Inno Setup / MSIX）
