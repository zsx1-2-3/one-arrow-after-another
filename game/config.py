# -*- coding: utf-8 -*-
"""全局配置：窗口、布局、配色、字体与动画参数。

把所有"魔数"集中放在这里，调整界面风格时不需要改动逻辑代码。
"""

# ------------------------------------------------------------------ 窗口
WINDOW_WIDTH = 960
WINDOW_HEIGHT = 720
WINDOW_TITLE = "一箭又一箭"
FPS = 60

# ------------------------------------------------------------------ 场景
# 放在 config 里而不是 app 里：背景模块 bgfx 也要按场景切换浓淡，
# 若由 bgfx 反向 import app 会形成循环依赖。
SCENE_MENU = "menu"
SCENE_LEVELS = "levels"
SCENE_PLAY = "play"

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

# 每个方向再给 4 档明暗变体。生成器造出来的关卡里同向箭头经常连成一片
# （第 6 关有 67% 的相邻箭头同向、第 12 关整行都是「>」），一个方向只有一种颜色时，
# 这些箭头会糊成一大块色块，看不出是一支支独立的箭头，关卡观感就很平。
# 变体按 (行×3 + 列×5) % 4 取——3 和 5 都与 4 互质，因此**上下左右相邻的箭头
# 一定落在不同变体上**，色块被打散；而色相不变，方向依旧一眼可辨。
# 变体与方向无关，不会泄露「哪支能点」的解法信息。
DIR_VARIANTS = 4
DIR_PALETTES = {
    "up": (
        (74, 178, 214), (100, 216, 240), (136, 232, 250), (62, 154, 196),
    ),
    "down": (
        (232, 152, 70), (250, 186, 104), (255, 208, 142), (206, 128, 58),
    ),
    "left": (
        (158, 112, 218), (192, 146, 244), (212, 176, 252), (136, 94, 196),
    ),
    "right": (
        (88, 190, 122), (122, 224, 154), (158, 238, 182), (70, 164, 104),
    ),
}
ARROW_HIGHLIGHT = 0.34    # 箭头贴图顶部提亮比例（做出上亮下暗的光泽感）
ARROW_SHADE = 0.26        # 箭头贴图底部压暗比例

# ---- 棋盘面板 / 悬停流光 ----
COLOR_BOARD_PANEL = (26, 33, 55)        # 棋盘底衬面板
COLOR_BOARD_PANEL_EDGE = (52, 64, 98)
COLOR_HOVER_RING = (96, 170, 255)       # 悬停格子的呼吸环
COLOR_PATH_OK = (86, 214, 138)          # 前方畅通的路径
COLOR_PATH_BLOCK = (238, 96, 96)        # 前方被挡的路径

# ---- 动态背景 ----
BG_STAR_COUNT = 78                      # 菜单场景的星星数量
BG_STAR_COUNT_PLAY = 46                 # 游戏场景少放一些，别抢棋盘注意力
BG_ORB_COUNT = 3                        # 缓慢漂移的光晕数量
BG_ORB_SPEED = 0.055                    # 光晕漂移速度（周期比例/秒，很慢）
BG_SHOOT_INTERVAL = (5.0, 11.0)         # 流星出现的间隔区间（秒）
BG_VIGNETTE_ALPHA = 96                  # 四周压暗程度

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
