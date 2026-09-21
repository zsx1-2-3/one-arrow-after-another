# -*- coding: utf-8 -*-
"""全局配置：窗口、布局、配色、字体与动画参数。

把所有"魔数"集中放在这里，调整界面风格时不需要改动逻辑代码。
"""

# ------------------------------------------------------------------ 窗口
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 720
WINDOW_TITLE = "一箭又一箭"
FPS = 60

# ------------------------------------------------------------------ 布局
HUD_HEIGHT = 100          # 顶部信息栏高度
FOOTER_HEIGHT = 52        # 底部提示栏高度
BOARD_MARGIN_X = 40       # 棋盘区域左右留白
BOARD_MARGIN_Y = 16       # 棋盘区域上下留白
BOARD_MAX_SIDE = 520      # 棋盘网格的最大边长
CELL_MAX_SIDE = 88        # 单元格边长上限（小棋盘不要把格子撑得太大）
CELL_GAP = 8              # 单元格之间的间距
CELL_RADIUS = 12          # 单元格圆角半径
ARROW_RATIO = 0.62        # 箭头图形边长 / 单元格边长

# ------------------------------------------------------------------ 配色
COLOR_BG_TOP = (24, 30, 52)
COLOR_BG_BOTTOM = (13, 17, 30)
COLOR_HUD = (27, 34, 58)
COLOR_HUD_LINE = (46, 56, 88)
COLOR_PANEL = (31, 39, 66)
COLOR_PANEL_EDGE = (62, 76, 116)
COLOR_CELL = (34, 42, 68)
COLOR_CELL_EDGE = (48, 59, 92)
COLOR_CELL_USED = (44, 55, 88)
COLOR_CELL_HOVER = (58, 74, 116)
COLOR_TEXT = (236, 241, 250)
COLOR_TEXT_DIM = (150, 162, 192)
COLOR_TEXT_FAINT = (98, 110, 142)
COLOR_ACCENT = (88, 166, 255)
COLOR_SUCCESS = (76, 212, 136)
COLOR_DANGER = (240, 98, 98)
COLOR_WARN = (246, 178, 72)
COLOR_MASK = (8, 11, 20)

# ---- 关卡卡片（关卡总览界面）----
COLOR_CARD = (32, 40, 66)              # 可挑战
COLOR_CARD_EDGE = (62, 76, 116)
COLOR_CARD_HOVER = (46, 58, 94)
COLOR_CARD_DONE = (28, 58, 48)         # 已通关
COLOR_CARD_DONE_EDGE = (76, 178, 130)
COLOR_CARD_LOCKED = (24, 28, 42)       # 未解锁
COLOR_CARD_LOCKED_EDGE = (42, 48, 66)
COLOR_LOCK = (96, 106, 134)
COLOR_STAR = (246, 190, 78)            # 难度星星
COLOR_STAR_EMPTY = (58, 66, 92)

# ---- 生命值（点错一次扣 1 点）----
COLOR_HP = (240, 98, 98)               # 还有的生命值（实心心形）
COLOR_HP_LOW = (246, 178, 72)          # 只剩最后 1 点时换成提醒色
COLOR_HP_LOST = (118, 78, 90)          # 已经失去的生命值（空心心形）

# ---- 教学关引导 ----
COLOR_TUTORIAL = (246, 190, 78)        # 目标箭头的高亮环
COLOR_TUTORIAL_BAR = (46, 40, 26)
COLOR_TUTORIAL_BAR_EDGE = (108, 88, 44)

# 四个方向对应的箭头颜色（色盲友好度一般，但辨识度高）
DIR_COLORS = {
    "up": (92, 204, 230),
    "down": (248, 174, 88),
    "left": (180, 132, 236),
    "right": (110, 212, 142),
}

# ------------------------------------------------------------------ 动画
FLY_DURATION = 0.45       # 箭头飞出动画时长（秒）
FLY_MARGIN_RATIO = 0.9    # 飞出距离额外多走 0.9 个单元格
IMPACT_DURATION = 0.36    # 撞击提示动画时长
IMPACT_PUSH_RATIO = 0.18  # 撞击时前冲幅度（相对单元格边长）
RESULT_DELAY = 0.70       # 通关 / 失败后延迟多久弹出结果面板

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
