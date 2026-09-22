# -*- coding: utf-8 -*-
"""全局配置：窗口、布局、配色、字体与动画参数。

把所有"魔数"集中放在这里，调整界面风格时不需要改动逻辑代码。

============================ 配色风格说明 ============================
2026-09-22 第二版：按**实机录屏**重做，观感关键词是「竖向手机界面 + 箭头迷宫」。

  * 窗口是**竖向**的（600×960），和参照画面一致；
  * 底色是一块**偏蓝的深灰紫**（实测参照画面 #3B405A），
    顶栏与底栏各比底色亮一点点，靠一条 1px 亮线分隔；
  * 棋盘**不画格子**，只有每格一个很淡的圆点；
  * 棋子是一条**占多格的圆角粗箭头**，末端一个箭头（见 pieces.py）；
  * 每支箭的颜色随机取自一组糖果色，但**相邻两支不允许同色**
    （见 pieces.assign_colors）——同色箭头挨在一起会连成一片、数不清有几支；
  * 顶栏：设置齿轮 / 昼夜开关 / 「关卡N」+ 生命值 + 倒计时 / 右侧胶囊按钮；
  * 底栏：提示 / 缩放滑杆 / 辅助线。

两套主题（顶栏那个月亮开关切换）：
  * ``night``：上面描述的深色版，也是默认；
  * ``day``：浅色版，底色换成淡蓝白，其余结构不变。

常量名尽量**保持不变**：界面代码、截图脚本和测试都按名字引用，
换配色不该逼着所有地方一起改名。
"""

# ------------------------------------------------------------------ 窗口
# 680×880 而不是早年的 600×960：用户在电脑上窗口超出屏幕、看不到全貌，
# 于是「改宽一点、也改矮一点」——宽度给了顶栏底栏更从容的排布，
# 高度收掉 80px（主要来自棋盘视口），整窗在 1080p 屏幕上不再顶到任务栏。
# 逻辑分辨率之外，main.py 还有第二道保险：屏幕实在装不下时按 pygame.SCALED
# 整体等比缩小窗口，任何电脑都能看到完整界面。
WINDOW_WIDTH = 680
WINDOW_HEIGHT = 880
WINDOW_TITLE = "一箭又一箭"
FPS = 60

# ------------------------------------------------------------------ 场景
# 放在 config 里而不是 app 里：背景模块 bgfx 也要按场景切换浓淡，
# 若由 bgfx 反向 import app 会形成循环依赖。
SCENE_MENU = "menu"
SCENE_LEVELS = "levels"
SCENE_PLAY = "play"

# ------------------------------------------------------------------ 布局
# 自上而下三段：顶栏 / 棋盘 / 底栏。棋盘区域就是顶栏底边到顶栏底边之间那块，
# 见 app.layout_board。
# ------------------------------------------------------------------ 布局
# 自上而下三段：顶栏 / 棋盘 / 底栏。棋盘区域就是顶栏底边到工具栏顶边之间那块，
# 见 app.layout_board。
HUD_HEIGHT = 108          # 顶部信息栏高度（两行：按钮 + 标题 / 信息）
TOOLBAR_HEIGHT = 104      # 底部工具栏高度（圆钮 + 按钮下方那行小字）
FOOTER_HEIGHT = 104       # 兼容旧名字：底部工具栏就是页脚
BOARD_MARGIN_X = 14       # 棋盘视口左右留白
BOARD_MARGIN_Y = 10       # 棋盘视口上下留白
CELL_MAX_SIDE = 64        # 单元格边长上限（小棋盘不要把格子撑得太大）
CELL_MIN_SIDE = 6         # 单元格边长下限
CELL_GAP = 0              # 参照画面的格子是紧挨着的（箭头自带留白）
CELL_RADIUS = 10          # 单元格圆角半径（点阵格子用不到，仅高亮环用）

# ---- 缩放（底栏那根滑杆）----
# 参照画面的棋盘比窗口大，底部有根缩放滑杆。这里同样支持：
# 1.0 = 恰好铺满棋盘视口，放大之后可以按住棋盘拖动查看。
ZOOM_MIN = 0.6
ZOOM_MAX = 1.8
ZOOM_DEFAULT = 1.0
ZOOM_STEP = 0.1           # 点滑杆两端的 − / + 时每次变化多少
DRAG_THRESHOLD = 7        # 鼠标移动超过这么多像素就算「拖动」而不是「点击」

# ---- 棋子（箭头）造型 ----
# 三个比例都是相对**格距**而言，改这三个数就能调箭头的粗细与箭头的胖瘦。
PIECE_STROKE_RATIO = 0.40   # 箭头粗细 / 格距（0.46 偏粗，用户要求调细）
PIECE_HEAD_RATIO = 0.50     # 箭头三角的长度 / 格距
PIECE_HEAD_SPAN = 0.40      # 三角上下各张开多少（相对格距）
PIECE_OUTLINE_RATIO = 0.16  # 箭头外描边比箭身粗多少（相对箭身）
PIECE_OUTLINE_DARKEN = 0.22  # 描边的压暗比例——同色箭头挨在一起时靠它分开

# 箭身线宽的「大格距收细」：格距是相对量，前期小棋盘格距被 CELL_MAX_SIDE
# 顶到 64px，按 0.40 的固定比例算出来的箭身有 25px 粗，和参照画面那种
# 细箭头完全不是一个观感；后期大盘格距只有 28px 左右，0.40 正合适。
# 所以有效比例随格距按幂函数收细（见 ui.piece_stroke_px）：
PIECE_STROKE_REF_CELL = 30    # 格距超过这个数开始收细（小于则维持 RATIO）
PIECE_STROKE_SHRINK = 0.45    # 收细的幂次——越大，大格距收得越狠

# 拐弯的「绳子圆滑」：折线箭头在每个拐角处用一段二次贝塞尔曲线取代直角，
# 半径相对格距取值（实际圆滑半径还会被「不超过相邻两段各一半」夹住，
# 所以最短一格的折段也不会圆出格）。静态棋子与飞出动画走同一个比例，
# 整支箭看上去才是同一条「绳子」：静止时是弯的，飞出时弯折顺滑地流过去。
# 0 是旧行为（硬直角）；想更「面条」可以加到 0.45 左右。
PIECE_CORNER_RATIO = 0.38

# ------------------------------------------------------------------ 主题
NIGHT = {
    "BG_TOP": (59, 64, 90),
    "BG_BOTTOM": (52, 57, 82),
    "HUD": (65, 70, 98),
    "TOOLBAR": (67, 72, 98),
    "LINE": (92, 98, 130),
    "DIVIDER": (78, 84, 112),
    "PANEL": (242, 245, 250),
    "PANEL_HEAD": (143, 180, 232),
    "PANEL_EDGE": (206, 216, 232),
    "PANEL_TEXT": (58, 64, 90),
    "PANEL_TEXT_DIM": (120, 130, 152),
    "TEXT": (255, 255, 255),
    "TEXT_DIM": (176, 184, 206),
    "TEXT_FAINT": (132, 140, 166),
    "TEXT_OUTLINE": (36, 40, 60),
    "MASK": (24, 27, 44),
    "CARD": (72, 78, 108),
    "CARD_EDGE": (108, 116, 152),
    "CARD_HOVER": (90, 98, 134),
    "CARD_DONE": (48, 86, 78),
    "CARD_DONE_EDGE": (96, 200, 154),
    "CARD_LOCKED": (58, 62, 84),
    "CARD_LOCKED_EDGE": (80, 86, 110),
    "LOCK": (126, 134, 158),
    "DOT": (255, 255, 255),
    "DOT_ALPHA": 24,
    "TOOL_BTN": (86, 92, 124),
    "TOOL_BTN_HOVER": (108, 116, 152),
    "STAT_BOX": (86, 92, 120),
    "STAT_BOX_SCORE": (96, 84, 50),
    "SLIDER_TRACK": (150, 156, 176),
    "BADGE": (60, 62, 78),
    # 提示气泡固定走「深底浅字」：它可能弹在浅色面板上，也可能弹在深色棋盘上，
    # 只有深底浅字在两种背景上都读得清（浅底深字压在深色棋盘上就糊了）。
    "TOAST_BG": (26, 30, 48),
    "TOAST_EDGE": (108, 118, 152),
    "TOAST_TEXT": (238, 242, 252),
}

DAY = {
    "BG_TOP": (226, 236, 244),
    "BG_BOTTOM": (210, 224, 238),
    "HUD": (238, 245, 251),
    "TOOLBAR": (238, 245, 251),
    "LINE": (196, 210, 226),
    "DIVIDER": (206, 218, 232),
    "PANEL": (250, 252, 255),
    "PANEL_HEAD": (143, 180, 232),
    "PANEL_EDGE": (206, 216, 232),
    "PANEL_TEXT": (58, 64, 90),
    "PANEL_TEXT_DIM": (120, 130, 152),
    "TEXT": (58, 66, 92),
    "TEXT_DIM": (98, 108, 134),
    "TEXT_FAINT": (126, 136, 158),
    "TEXT_OUTLINE": (255, 255, 255),
    "MASK": (96, 110, 132),
    "CARD": (255, 255, 255),
    "CARD_EDGE": (168, 186, 208),
    "CARD_HOVER": (238, 246, 254),
    "CARD_DONE": (206, 240, 222),
    "CARD_DONE_EDGE": (72, 176, 132),
    "CARD_LOCKED": (216, 224, 234),
    "CARD_LOCKED_EDGE": (190, 200, 214),
    "LOCK": (150, 160, 178),
    "DOT": (90, 108, 132),
    "DOT_ALPHA": 26,
    "TOOL_BTN": (255, 255, 255),
    "TOOL_BTN_HOVER": (232, 242, 252),
    "STAT_BOX": (232, 240, 248),
    "STAT_BOX_SCORE": (250, 236, 200),
    "SLIDER_TRACK": (176, 190, 208),
    "BADGE": (255, 255, 255),
    # 日间主题的气泡也保持深底浅字（见 NIGHT 那边的说明），
    # 只比夜间稍微亮一点点，免得在白面板上显得像一块纯黑补丁。
    "TOAST_BG": (44, 50, 72),
    "TOAST_EDGE": (140, 152, 184),
    "TOAST_TEXT": (245, 248, 255),
}

THEME = "night"
THEME_ORDER = ("night", "day")


def apply_theme(name):
    """切换主题：把 THEME dict 里的颜色写到模块级常量上。

    写成「模块级常量」而不是到处 `config.color("BG")`，
    是为了让界面代码继续用 `config.COLOR_BG_TOP` 这种直白写法；
    代价是切主题时要用这个函数刷新一遍（并清掉贴图缓存）。
    """
    global THEME
    if name not in THEME_ORDER:
        raise ValueError("没有这个主题：%r" % name)
    THEME = name
    palette = NIGHT if name == "night" else DAY
    for key, value in palette.items():
        globals()["COLOR_" + key] = value
    # 两个别名：顶栏下沿 / 工具栏上沿的分隔线用的就是同一个「浅一档的线」颜色，
    # 但两处代码里的名字语义不同，各留一个名字比强行统一更好读。
    globals()["COLOR_HUD_LINE"] = palette["LINE"]
    globals()["COLOR_TOOLBAR_LINE"] = palette["LINE"]
    return name


def next_theme():
    """顶栏的月亮开关用：在 night / day 之间来回切。"""
    return apply_theme("day" if THEME == "night" else "night")


# 先落一套默认值（night），下面的常量名在 import 时就已经存在
apply_theme("night")

# ---- 固定配色（不随主题变化）----
COLOR_ACCENT = (74, 126, 216)          # 主按钮 / 强调数字
COLOR_ACCENT_DEEP = (58, 104, 190)     # 主按钮按下态
COLOR_SUCCESS = (76, 190, 150)         # 「下一关」这类前进按钮
COLOR_DANGER = (232, 86, 104)
COLOR_WARN = (246, 184, 92)
COLOR_TEAL = (46, 158, 143)            # 齿轮描边 / 底栏图标，来自参照画面
COLOR_GOLD = (245, 200, 66)            # 月亮、奖杯、金币
COLOR_GOLD_DEEP = (214, 158, 40)
COLOR_TOOL_ON = (108, 164, 255)        # 开关处于「开」的状态

# ---- 教学关 ----
COLOR_TUTORIAL = (246, 190, 78)        # 目标箭头的高亮环
COLOR_TUTORIAL_BAR = (86, 74, 44)
COLOR_TUTORIAL_BAR_EDGE = (140, 118, 60)

# ---- 点阵棋盘 ----
COLOR_CELL = (74, 77, 100)             # 兼容旧名字：棋盘上不再画格子
COLOR_CELL_EDGE = (112, 116, 146)
COLOR_CELL_USED = (74, 77, 100)
COLOR_CELL_HOVER = (255, 255, 255)
COLOR_CELL_HOVER_ALPHA = 22
COLOR_HOVER_RING = (108, 164, 255)

# ---- 射线高亮 ----
COLOR_PATH_OK = (110, 226, 152)        # 前方畅通
COLOR_PATH_BLOCK = (255, 108, 122)     # 前方被挡
COLOR_PATH_ALPHA = 46
COLOR_PATH_INSET = 6                   # 高亮块相对格子往里缩多少像素

# ---- 辅助线（底栏的开关）----
# 开启后把每支箭前方那条射线画出来：畅通的走到边界，被挡的停在挡路的那一支前面。
# **两个状态用同一个颜色**——它只是帮你把方向关系看清楚，不替玩家判断能不能点。
COLOR_GUIDE = (255, 255, 255)
COLOR_GUIDE_ALPHA = 54

# ---- 生命值（点错一次扣 1 点）----
COLOR_HP = (238, 78, 78)
COLOR_HP_LOW = (246, 176, 76)
COLOR_HP_LOST = (104, 110, 134)

# 生命值图标是一颗「像素心」：不是圆滑的矢量心形，而是一格一格的像素画，
# 和箭头那种硬边图形是同一种质感。'#' 为实心，'.' 为镂空。
HEART_PIXEL_ART = (
    "..##..##..",
    ".########.",
    "##########",
    "##########",
    ".########.",
    "..######..",
    "...####...",
    "....##....",
)
HEART_INLINE_SIZE = 18                 # 文字说明里夹带的那种小心的宽度

# ---- 得分 ----
COLOR_SCORE = (250, 208, 106)

# ---- 提示（高亮出来的那一支）----
COLOR_HINT = (120, 232, 190)

# ---- 关卡卡片 ----
COLOR_STAR = (250, 208, 106)
COLOR_STAR_EMPTY = (118, 124, 148)

# ---- 动态背景 ----
# 参照画面的底子非常干净，所以星点和流星都是关着的，
# 只留两团几乎看不出来的漂移光晕，让画面不至于是一块死板的纯色。
BG_STAR_COUNT = 0
BG_STAR_COUNT_PLAY = 0
BG_ORB_COUNT = 2
BG_ORB_SPEED = 0.045
BG_SHOOT_INTERVAL = (999.0, 1000.0)
BG_VIGNETTE_ALPHA = 40

# ------------------------------------------------------------------ 动画
FLY_DURATION = 0.38        # 一整支箭飞出动画时长（秒）——FlyOut 的兜底默认值
# 飞出时长随路径长度伸缩：固定时长时，长蛇形箭（C/S 形，弧长是短箭的几倍）
# 只能把速度翻几倍才能飞完，观感是「射出去的子弹」而不是「抽出去的绳子」。
# 所以按「每秒走多少格」换算时长，再夹在上下限之间：
#   duration = clamp(travel / (cell * FLY_SPEED_CPS), FLY_DURATION_MIN, FLY_DURATION_MAX)
# 26 格/秒实测短箭约 0.30s（和旧固定值手感一致）、最长蛇形箭约 0.7~0.8s，
# 长短箭的滑行速度接近恒定，绳子感才出得来。见 anim.fly_duration()。
FLY_SPEED_CPS = 26.0       # 飞出滑行速度（格/秒）
FLY_DURATION_MIN = 0.30    # 时长下限（短箭别太快）
FLY_DURATION_MAX = 0.80    # 时长上限（长箭别拖沓）
# 飞出缓动的幂次：advance = travel * t^FLY_EASE_POWER。
# 早年的 1.7 起步太黏——前 0.15 秒箭头几乎没动、然后突然窜出去，
# 手感是「卡一下再飞」；1.35 起步更快、末速也更收敛，看起来是
# 「被抓一把就顺顺地抽出去」。想要更猛的鞭子感可以调回 1.6~1.7。
FLY_EASE_POWER = 1.35
FLY_MARGIN_RATIO = 1.1     # 飞出距离额外多走这么多格
IMPACT_DURATION = 0.36     # 撞击提示动画时长
IMPACT_PUSH_RATIO = 0.18   # 撞击时前冲幅度（相对格距）
RESULT_DELAY = 0.70        # 通关 / 失败后延迟多久弹出结果面板
HINT_DURATION = 4.0        # 提示环持续多久后自动消失
CONFETTI_DURATION = 2.4    # 通关彩纸飘落时长

# ------------------------------------------------------------------ 字体
# 说明：pygame.font.match_font() / SysFont() 在部分 Windows 环境下会抛出
# TypeError（读取字体注册表时崩溃），因此这里直接给出常见中文字体文件路径，
# 按顺序尝试加载第一个存在的文件。
FONT_PATHS = [
    r"C:\Windows\Fonts\msyh.ttc",       # 微软雅黑
    r"C:\Windows\Fonts\simhei.ttf",     # 黑体
    r"C:\Windows\Fonts\Deng.ttf",       # 等线
    r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
    r"C:\Windows\Fonts\simsun.ttc",     # 宋体
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
FONT_BOLD_PATHS = [
    r"C:\Windows\Fonts\msyhbd.ttc",     # 微软雅黑 Bold
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\Dengb.ttf",
    r"C:\Windows\Fonts\NotoSansSC-VF.ttf",
]
