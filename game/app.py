# -*- coding: utf-8 -*-
"""游戏主体：场景状态机、事件分发、渲染与主循环。

场景（self.scene）：
    SCENE_MENU    开始界面：标题、玩法说明、进度、开始 / 教学关 / 关卡总览 / 退出
    SCENE_LEVELS  关卡总览：全部关卡一览，未解锁的显示锁，点击会提示先通关哪一关
    SCENE_PLAY    游戏界面：顶部信息栏 + 棋盘 + 底部工具栏（教学关额外有逐步引导）

通关 / 失败 / 设置以「浮层」的形式叠加在游戏界面上（self.overlay），
浮层关闭前不接受棋盘点击，避免误操作。

窗口是**竖向**的（600×960），和参照画面一致。棋盘区域夹在顶栏与底栏之间，
底栏那根滑杆可以放大棋盘，放大之后按住棋盘就能拖动查看——
参照画面里的棋盘是比屏幕大的，靠缩放 + 拖动来看全貌。
"""

import math

import pygame

from . import anim, bgfx, config, pieces, scoring, ui
from .board import (CLICK_BLOCKED, CLICK_EMPTY, CLICK_FLY, CLICK_IGNORED,
                    STATE_CLEARED, STATE_FAILED, STATE_PLAYING, Board)
from .levels import TOTAL_LEVELS, LEVELS, TUTORIAL
from .progress import Progress

# 场景常量定义在 config 里（背景模块也要用，避免循环依赖），这里只是转发一下
SCENE_MENU = config.SCENE_MENU
SCENE_LEVELS = config.SCENE_LEVELS
SCENE_PLAY = config.SCENE_PLAY

OVERLAY_WIN = "win"
OVERLAY_FAIL = "fail"
OVERLAY_ALL_CLEAR = "allclear"
OVERLAY_TUTORIAL_DONE = "tutorial"      # 教学关走完（不计分，所以单独一档结果面板）
OVERLAY_SETTINGS = "settings"           # 顶栏齿轮打开的设置面板

TOAST_DURATION = 2.0        # 提示气泡停留时间（秒）
HP_FLASH_DURATION = 0.9     # 刚失去一颗心时，HUD 上那颗心的闪烁时长（秒）

# ---------------------------------------------------------------- 顶部信息栏
# 两行：
#
#   y=30 ┌ [齿轮][月亮]        第 4 关 四面楚歌        [▦ 关卡总览] ┐
#   y=80 │        ⏱ 00:35   ❤❤❤❤❤ 5 / 5   剩余 12   得分 900/900 │
#
# 第二行**先算整行总宽、再整体居中**，不写死 x 坐标。心数随关卡变化（3~4 颗）、
# 得分位数也会变，固定坐标每动一点内容就得重新人工核算会不会撞在一起。
HUD_TITLE_Y = 30            # 标题那一行的垂直中心
HUD_ROW_Y = 80              # 信息那一行的垂直中心
HUD_INFO_GAP = 22           # 四组信息之间的间距
HUD_TITLE_SIZE = 24         # 标题字号
HUD_HEART_SIZE = 17
HUD_HEART_GAP = 5
HUD_CLOCK_SIZE = 15         # 计时器那个小钟表的直径

# 顶部圆钮 / 右上胶囊按钮的尺寸（圆钮的 rect 传正方形）
HUD_BUTTON_SIZE = 42
HUD_BUTTON_MARGIN = 14      # 距窗口左右边的距离
HUD_BUTTON_GAP = 10         # 齿轮与月亮之间的间距
HUD_PILL_WIDTH = 116        # 右上「关卡总览」胶囊的宽度

# ---------------------------------------------------------------- 底部工具栏
# 左「提示」、右「辅助线」，中间一根缩放滑杆（两端各一个 − / +）。
TOOL_BUTTON_SIZE = 52
TOOL_BUTTON_MARGIN = 32
TOOL_BUTTON_TOP = 10        # 距工具栏上沿
TOOL_STEP_SIZE = 34         # 滑杆两端 − / + 圆钮的直径
TOOL_SLIDER_WIDTH = 400
TOOL_LABEL_Y = 77           # 「提示 / 辅助线 / 缩放 xx%」那行小字距工具栏上沿

# ---------------------------------------------------------------- 关卡总览
# 9 个标准关排成 3 列正好是 3 × 3 的方阵。教学关不在这张表里（主菜单有独立入口），
# 所以不会把方阵顶成 3 + 3 + 3 + 1。
CARD_COLUMNS = 3
CARD_WIDTH = 176
CARD_HEIGHT = 172
CARD_GAP_X = 18
CARD_GAP_Y = 24
CARDS_TOP = 150

# 教学关底部的讲解条。它不是浮在棋盘之上的：棋盘区域要先把这块地方让出来
# （见 layout_board），否则 5×5 的教学关棋盘会一直顶到讲解条的边线上。
TUTORIAL_BAR_HEIGHT = 58
TUTORIAL_BAR_MARGIN = 10

# 结果面板 / 设置面板
PANEL_WIDTH = 460
# 面板高度按「内容最长的那个面板」定：结算面板排到 panel.y + 408（第二排按钮下沿），
# 上下各留 32 像素左右的留白，也就是 408 + 32 = 440。
# 加高会看到底部一大片空，压矮则会顶穿面板下边线。
PANEL_HEIGHT = 440

# 玩法说明里的两个迷你棋盘（5 列 2 行）：
#   上面那个演示「前方有箭头 → 飞不出去」，下面那个演示「前方空 → 飞出去」
#
# 两处演示都刻意只让**一支**箭处在「被讨论」的位置，另一支（如果有）箭头朝棋盘外，
# 保证「挡」的那张图里被挡住的只有橙色那支、「通」的那张图里只有绿色那支。
# 早先的写法是两支箭面对面互指，结果两张图里两支都被挡住，
# 示例和说明文字对不上——改这两个常量时务必让每张图只有一个主角。
DEMO_ROWS, DEMO_COLS = 2, 5
#  绿色：竖着两格、箭头朝下（朝棋盘外）→ 自己飞得出去
#  橙色：横着两格、箭头朝左，前方 (1,1) 正是绿色那支的身子 → 飞不出去
DEMO_BLOCKED_SPECS = ("0,1 v D", "1,3 < L")
#  绿色：横着占满一行、箭头朝右（朝棋盘外）→ 一路畅通
DEMO_CLEAR_SPECS = ("1,0 > R4",)
DEMO_BLOCKED_CAPTION = "橙色这支箭头前方压着绿色箭头 → 飞不出去"
DEMO_CLEAR_CAPTION = "这支箭头前方一路是空的 → 整条飞出棋盘并消失"
# 说明文字里点名了颜色，所以这两支的颜色**写死**在这里，
# 不能用 PIECE_PALETTE[index*3] 那种按序号取色的写法——
# 哪天调色板顺序一变，文字就会和画面对不上。改说明文字时记得一起改这两个。
DEMO_COLORS = (pieces.PIECE_PALETTE[0], pieces.PIECE_PALETTE[3])
_demo_cache = {}


def demo_pieces(specs):
    """把玩法说明里的迷你棋盘解析成 Piece（颜色按 DEMO_COLORS 固定），结果缓存住。"""
    cached = _demo_cache.get(specs)
    if cached is None:
        built = []
        for index, spec in enumerate(specs):
            cells, direction = pieces.parse_piece(spec)
            built.append(pieces.Piece(cells=cells, direction=direction,
                                      color=DEMO_COLORS[index % len(DEMO_COLORS)],
                                      uid=index))
        cached = tuple(built)
        _demo_cache[specs] = cached
    return cached


class Game:
    """整个游戏的状态与渲染。"""

    def __init__(self, screen, progress=None):
        self.screen = screen
        self.width, self.height = screen.get_size()
        self.running = True

        # 进度：不传就自动从存档文件读取（测试与截图脚本会传入临时存档）
        self.progress = progress if progress is not None else Progress()

        self.scene = SCENE_MENU
        self.level_index = 0
        self.in_tutorial = False        # 当前玩的是不是教学关（它不占关卡编号、不计分）
        self.board = None

        self.base_cell = 20.0           # 恰好铺满视口时的格距
        self.cell = 20                  # 实际格距 = base_cell × zoom
        self.zoom = config.ZOOM_DEFAULT
        self.pan = [0, 0]               # 放大之后的平移量（像素）
        self.board_rect = pygame.Rect(0, 0, 0, 0)
        self.animations = []
        self.floats = []
        self.buttons = []
        self.card_rects = []
        self.hover_card = None
        self.overlay = None
        self.overlay_timer = 0.0
        self.mouse_pos = (-1, -1)
        self.hover_cell = None

        # 计时 / 提示 / 辅助线：参照画面底栏与顶栏上那几个控件的状态
        self.elapsed = 0.0              # 本关已用时（秒），开局与重开都归零
        self.hint_piece = None          # 「提示」高亮出来的那一支（存 cells 而不是格子）
        self.hint_timer = 0.0           # 高亮还能持续多久
        self.show_guides = False        # 辅助线开关（跨关保留，属于玩家偏好）

        # 鼠标拖动（放大棋盘后用来平移，滑杆也靠它）
        self.pressed = False
        self.dragged = False
        self.press_pos = (0, 0)
        self.drag_target = None

        # 按下拖动时用到的基准，重置成「没在拖」的初始状态
        self.pan_at_press = [0, 0]
        self.drag_target = None

        # 教学关引导
        self.tutorial_index = 0
        self.tutorial_done = False

        # 得分：本关打完后的结算结果（结算面板要显示，所以存在 Game 上）
        self.last_score = 0        # 本关最终得分（失败为 0）
        self.score_max = 0         # 本关满分，作为「得了多少」的分母
        self.score_gain = 0        # 比历史最高分多拿了多少（0 = 没刷新纪录）
        self.score_perfect = False # 是否一颗心都没丢

        # 提示气泡 / 二次确认
        self.toast_text = ""
        self.toast_color = config.COLOR_TEXT
        self.toast_timer = 0.0
        self.reset_armed = False

        self.time = 0.0

        # 动态背景：漂移光晕 + 四角暗角（星点与流星默认关着，见 config）
        self.bg = bgfx.Background((self.width, self.height), SCENE_MENU)
        self.enter_menu()

    # ================================================================ 场景
    @property
    def level(self):
        """当前关卡：教学关单独一份数据，不占 LEVELS 的编号。"""
        return TUTORIAL if self.in_tutorial else LEVELS[self.level_index]

    @property
    def tutorial_steps(self):
        return self.level.steps if self.level.tutorial else ()

    @property
    def current_step(self):
        """当前的教学引导步骤；没有则返回 None。"""
        if not self.level.tutorial or self.tutorial_done:
            return None
        if 0 <= self.tutorial_index < len(self.level.steps):
            return self.level.steps[self.tutorial_index]
        return None

    def reset_common(self):
        """切换场景时的公共清理。"""
        self.overlay = None
        self.overlay_timer = 0.0
        self.hover_cell = None
        self.hover_card = None
        self.hint_piece = None
        self.hint_timer = 0.0
        self.reset_armed = False
        self.hp_lost_flash = 0.0
        self.pressed = False
        self.dragged = False
        self.last_score = 0
        self.score_max = 0
        self.score_gain = 0
        self.score_perfect = False
        self.animations.clear()
        self.floats.clear()
        # 提示气泡属于上一屏的上下文，换场景时一起清掉，
        # 免得「先通关第 N 关吧」这种提示跟着玩家进了关卡
        self.toast_text = ""
        self.toast_timer = 0.0
        # 背景跟着换浓淡：游戏界面要收敛，别和棋盘抢注意力
        self.bg.set_scene(self.scene)

    def enter_menu(self):
        """回到开始界面。"""
        self.scene = SCENE_MENU
        self.board = None
        self.reset_common()
        self.buttons = self.make_menu_buttons()

    def enter_levels(self):
        """进入关卡总览。"""
        self.scene = SCENE_LEVELS
        self.board = None
        self.reset_common()
        self.card_rects = self.make_card_rects()
        self.buttons = self.make_levels_buttons()

    # ------------------------------------------------------------ 进度查询
    def is_unlocked(self, index):
        return self.progress.is_unlocked(index, TOTAL_LEVELS)

    def is_cleared(self, index):
        return self.progress.is_cleared(index)

    def next_level_index(self):
        return self.progress.next_index(TOTAL_LEVELS)

    def show_toast(self, text, color=None):
        """弹出一条短暂的提示（屏幕中央或底部，自动淡出）。"""
        self.toast_text = text
        self.toast_color = color or config.COLOR_TEXT
        self.toast_timer = TOAST_DURATION

    # ------------------------------------------------------------ 关卡
    def enter_play(self, level, index=0, tutorial=False):
        """进入游戏界面，关卡数据由调用方给出。

        教学关和编号关卡走的是同一套界面与状态机，区别只在数据来源与
        「要不要记分 / 记进度」，所以开局这件事抽成一处，免得两边逻辑漂移。
        """
        self.in_tutorial = tutorial
        self.level_index = index
        self.board = Board(level)
        self.scene = SCENE_PLAY
        self.reset_common()
        self.elapsed = 0.0
        self.zoom = config.ZOOM_DEFAULT
        self.pan = [0, 0]
        self.tutorial_index = 0
        self.tutorial_done = not level.tutorial
        self.layout_board()
        self.buttons = self.make_play_buttons()
        self.sync_tutorial()

    def start_level(self, index):
        """开始第 index 关（从 0 开始计数）。未解锁则拒绝并提示。"""
        if not 0 <= index < TOTAL_LEVELS:
            return False
        if not self.is_unlocked(index):
            self.show_toast("先通关第 %d 关「%s」才能解锁本关"
                            % (index, LEVELS[index - 1].name), config.COLOR_WARN)
            return False

        self.enter_play(LEVELS[index], index)
        return True

    def start_tutorial(self):
        """开始教学关：不占关卡编号、不用解锁、也不计分。

        它随时可以从主菜单再进一次——想复习、或者想给同学演示都很方便。
        """
        self.enter_play(TUTORIAL, 0, tutorial=True)
        return True

    def next_level(self):
        if self.level_index + 1 < TOTAL_LEVELS:
            self.start_level(self.level_index + 1)
        else:
            self.enter_levels()

    def restart_level(self):
        """把当前关卡恢复到初始状态（设置面板的「重玩本关」/ R 键）。

        计时与提示都要一起归零：本关用时是「从眼前这个布局开始算」的，
        不归零的话重开之后计时器还挂着上一把的时间，看着像出了 bug。
        """
        if self.board is None:
            return
        self.board.reset()
        self.overlay = None
        self.overlay_timer = 0.0
        self.hover_cell = None
        self.hint_piece = None
        self.hint_timer = 0.0
        self.elapsed = 0.0
        self.pan = [0, 0]
        self.zoom = config.ZOOM_DEFAULT
        self.animations.clear()
        self.floats.clear()
        self.tutorial_index = 0
        self.tutorial_done = not self.level.tutorial
        self.layout_board()
        self.buttons = self.make_play_buttons()
        self.sync_tutorial()
        self.floats.append(anim.FloatingText(
            "已重新开始", (self.viewport_rect.centerx, self.viewport_rect.centery),
            config.COLOR_ACCENT, size=26, duration=1.0, rise=24))

    # ================================================================ 教学引导
    def sync_tutorial(self):
        """让引导步骤与棋盘的实际状态对齐。

        玩家完全可能不按提示点（甚至提前把后面的箭头消掉），
        所以每一步在展示前都要检查一次：目标还在吗？这一步还成立吗？
        不成立就直接跳过，避免出现「让你点一个已经飞走的箭头」这种尴尬。
        """
        if not self.level.tutorial or self.board is None:
            return
        steps = self.level.steps
        while self.tutorial_index < len(steps):
            step = steps[self.tutorial_index]
            piece = self.board.piece_at(step.row, step.col)
            if piece is None:
                self.tutorial_index += 1        # 目标已经飞走了
                continue
            if step.expect == "blocked" and self.board.can_fly(piece):
                self.tutorial_index += 1        # 已经没有阻挡了，这一步失去意义
                continue
            break
        self.tutorial_done = self.tutorial_index >= len(steps)

    def tutorial_target(self):
        """当前这一步指的是哪一支（没有就返回 None）。"""
        step = self.current_step
        if step is None or self.board is None:
            return None
        return self.board.piece_at(step.row, step.col)

    def advance_tutorial(self, result, clicked, step_piece):
        """某一步被正确完成后，推进到下一步。

        clicked 是玩家真正点到的那支，step_piece 是这一步希望点的那支——
        两者必须是同一支；玩家点了别的箭头不算完成这一步。
        """
        if not self.level.tutorial or self.tutorial_done:
            return
        step = self.current_step
        if step is None or step_piece is None or clicked is None:
            return
        if clicked != step_piece:
            return
        if result.kind != step.expect:
            return
        self.tutorial_index += 1
        self.sync_tutorial()

    # ================================================================ 布局
    @property
    def viewport_rect(self):
        """棋盘视口：顶栏下沿与工具栏上沿之间那一块。"""
        return pygame.Rect(
            config.BOARD_MARGIN_X,
            config.HUD_HEIGHT + config.BOARD_MARGIN_Y,
            self.width - config.BOARD_MARGIN_X * 2,
            self.height - config.HUD_HEIGHT - config.TOOLBAR_HEIGHT
            - config.BOARD_MARGIN_Y * 2 - (TUTORIAL_BAR_HEIGHT + TUTORIAL_BAR_MARGIN
                                           if self.in_tutorial else 0),
        )

    @property
    def toolbar_rect(self):
        return pygame.Rect(0, self.height - config.TOOLBAR_HEIGHT,
                           self.width, config.TOOLBAR_HEIGHT)

    @property
    def zoom_slider_rect(self):
        toolbar = self.toolbar_rect
        return pygame.Rect((self.width - TOOL_SLIDER_WIDTH) // 2,
                           toolbar.y + TOOL_BUTTON_TOP,
                           TOOL_SLIDER_WIDTH, TOOL_BUTTON_SIZE)

    @property
    def zoom_ratio(self):
        """当前缩放对应的滑杆位置（0~1）。"""
        span = config.ZOOM_MAX - config.ZOOM_MIN
        return (self.zoom - config.ZOOM_MIN) / span

    def set_zoom_ratio(self, ratio):
        """按滑杆位置设置缩放，并把平移量按新尺寸重新夹一遍。"""
        ratio = max(0.0, min(1.0, ratio))
        zoom = config.ZOOM_MIN + ratio * (config.ZOOM_MAX - config.ZOOM_MIN)
        # 量化到两位小数：滑杆上连着拖不会产生上百个不同的格距（贴图缓存会炸）
        self.zoom = round(zoom, 2)
        self.layout_board()

    def zoom_by(self, step):
        """点滑杆两端的 − / + 时用。"""
        self.set_zoom_ratio(self.zoom_ratio + step / (config.ZOOM_MAX - config.ZOOM_MIN))

    def layout_board(self):
        """根据关卡尺寸与缩放算出格距与棋盘矩形。

        棋盘区域 = 顶栏下沿到工具栏上沿之间那一块，上下再各留一点余量。
        所有尺寸常量都在 config 里（HUD_HEIGHT / TOOLBAR_HEIGHT / BOARD_MARGIN_Y），
        改任何一条这里的排版都会自己跟着重算，
        不会出现"信息栏加高了两像素、棋盘就压到工具栏上"这种事。

        缩放只放大**格距**，棋盘视口不变；放大之后按住棋盘拖动查看，
        平移量会夹在「棋盘边缘不离开视口」的范围里——
        否则玩家一路拖下去，棋盘就整个划出屏幕、只剩一片点阵了。
        """
        view = self.viewport_rect
        rows, cols = self.board.rows, self.board.cols
        base = min(view.width / float(cols), view.height / float(rows),
                   config.CELL_MAX_SIDE)
        self.base_cell = max(float(config.CELL_MIN_SIDE), base)
        # 取整要**向下**取，不能四舍五入：base_cell 的含义是「刚好塞得下」，
        # 16 行时 729/16 = 45.5625，进上去变成 46，16 × 46 = 736 > 729，
        # 于是 100% 缩放时棋盘竟然还溢出了视口、还能拖动。
        # 向下取则恒有 cell × 行数 ≤ 视口高（列方向同理）。
        self.cell = max(4, int(self.base_cell * self.zoom))

        width, height = self.cell * cols, self.cell * rows
        rect = pygame.Rect(0, 0, width, height)
        center_x = view.centerx - width // 2
        center_y = view.centery - height // 2
        if width <= view.width:
            x = center_x                                   # 放得下就居中，拖动无效
        else:
            x = max(view.right - width, min(view.left, center_x + self.pan[0]))
        if height <= view.height:
            y = center_y
        else:
            y = max(view.bottom - height, min(view.top, center_y + self.pan[1]))
        rect.topleft = (x, y)
        self.board_rect = rect

        # 夹完之后把实际偏移记回 pan：否则拖到边界之后 pan 会继续累加，
        # 往回拖的那一段就成了"空转"，手感很怪。
        self.pan = [x - center_x, y - center_y]

    def cell_rect(self, row, col):
        return pygame.Rect(self.board_rect.x + col * self.cell,
                           self.board_rect.y + row * self.cell,
                           self.cell, self.cell)

    def cell_center(self, row, col):
        return (self.board_rect.x + int((col + 0.5) * self.cell),
                self.board_rect.y + int((row + 0.5) * self.cell))

    def cell_at_pos(self, pos):
        """把屏幕坐标换算成棋盘坐标；落在视口外或界外返回 None。"""
        if self.board is None or not self.viewport_rect.collidepoint(pos):
            return None
        if not self.board_rect.collidepoint(pos):
            return None
        col = int((pos[0] - self.board_rect.x) // self.cell)
        row = int((pos[1] - self.board_rect.y) // self.cell)
        if not (0 <= row < self.board.rows and 0 <= col < self.board.cols):
            return None
        return row, col

    def make_card_rects(self):
        """关卡总览里每张卡片的矩形（不满的那一行居中）。"""
        total_width = CARD_COLUMNS * CARD_WIDTH + (CARD_COLUMNS - 1) * CARD_GAP_X
        left = (self.width - total_width) // 2
        rects = []
        for index in range(TOTAL_LEVELS):
            row, col = divmod(index, CARD_COLUMNS)
            in_row = min(CARD_COLUMNS, TOTAL_LEVELS - row * CARD_COLUMNS)
            offset = 0
            if in_row < CARD_COLUMNS:               # 这一行没排满，居中显示
                row_width = in_row * CARD_WIDTH + (in_row - 1) * CARD_GAP_X
                offset = (total_width - row_width) // 2
            rects.append(pygame.Rect(
                left + offset + col * (CARD_WIDTH + CARD_GAP_X),
                CARDS_TOP + row * (CARD_HEIGHT + CARD_GAP_Y),
                CARD_WIDTH, CARD_HEIGHT,
            ))
        return rects

    @property
    def tutorial_bar_rect(self):
        """教学关底部讲解条的矩形。

        单独抽出来是因为有两个地方要用它：画讲解条、以及布局棋盘时
        把这块地方让出来（见 viewport_rect）。
        """
        return pygame.Rect(30,
                           self.height - config.TOOLBAR_HEIGHT
                           - TUTORIAL_BAR_MARGIN - TUTORIAL_BAR_HEIGHT,
                           self.width - 60, TUTORIAL_BAR_HEIGHT)

    @property
    def panel_rect(self):
        panel = pygame.Rect(0, 0, PANEL_WIDTH, PANEL_HEIGHT)
        panel.center = (self.width // 2, self.height // 2)
        return panel

    # ================================================================ 按钮
    @property
    def primary_label(self):
        """主按钮文字随进度变化：没玩过叫「开始游戏」，玩到一半叫「继续第 N 关」。"""
        if self.progress.cleared_count(TOTAL_LEVELS) >= TOTAL_LEVELS:
            return "重新挑战第 1 关"
        index = self.next_level_index()
        if index == 0:
            return "开始游戏"
        return "继续第 %d 关" % (index + 1)

    def primary_action(self):
        """主按钮做什么：优先进入没通关的那一关。"""
        self.start_level(self.next_level_index())

    def make_menu_buttons(self):
        # 主按钮独占一行；下面三个并排：教学关 / 关卡总览 / 退出游戏。
        # 教学关占一个正式入口（而不是塞进关卡列表当第 1 关），
        # 所以不计分、不占编号，想复习随时能再进。
        center_x = self.width // 2
        row_y, row_w, row_gap = 756, 180, 16
        left = center_x - (row_w * 3 + row_gap * 2) // 2
        buttons = [
            ui.Button((center_x - 160, 682, 320, 58), self.primary_label,
                      self.primary_action, "primary", size=24),
            ui.Button((left, row_y, row_w, 46), "教学关",
                      self.start_tutorial, "ghost", size=17),
            ui.Button((left + row_w + row_gap, row_y, row_w, 46), "关卡总览",
                      self.enter_levels, "ghost", size=17),
            ui.Button((left + (row_w + row_gap) * 2, row_y, row_w, 46), "退出游戏",
                      self.quit, "ghost", size=17),
        ]
        return buttons

    def make_levels_buttons(self):
        top_right = self.width - 18 - 150
        buttons = [
            ui.Button((top_right, 40, 150, 42), "返回主菜单",
                      self.enter_menu, "ghost", size=16),
            ui.Button((top_right, 90, 150, 42),
                      "确认清空？" if self.reset_armed else "清空进度",
                      self.toggle_reset_progress, "ghost", size=16),
            ui.Button((self.width // 2 - 170, 776, 340, 54),
                      "继续挑战（第 %d 关）" % (self.next_level_index() + 1),
                      self.primary_action, "primary", size=20),
        ]
        for button in buttons:
            button.hovered = button.hit(self.mouse_pos)
        return buttons

    def toggle_reset_progress(self):
        """清空进度需要点两次，避免手滑把存档清了。"""
        if not self.reset_armed:
            self.reset_armed = True
            self.show_toast("再点一次「确认清空」才会删除全部闯关进度", config.COLOR_WARN)
        else:
            self.reset_armed = False          # 先复位，按钮文字才会变回「清空进度」
            self.progress.reset()
            self.show_toast("进度已清空，现在只能从第 1 关开始", config.COLOR_SUCCESS)
        self.buttons = self.make_levels_buttons()

    def make_play_buttons(self):
        """游戏界面的按钮：顶栏三个 + 底部工具栏四个，合成一个列表返回。

        分成「顶栏 / 工具栏」只是写布局时好读——事件分发仍然只认这一份
        self.buttons，不必为两组按钮各写一遍点击判断。
        """
        margin = HUD_BUTTON_MARGIN
        size = HUD_BUTTON_SIZE
        y = HUD_BUTTON_TOP = 9
        buttons = [
            ui.IconButton((margin, y, size, size), icon="gear",
                          on_click=self.open_settings),
            ui.IconButton((margin + size + HUD_BUTTON_GAP, y, size, size),
                          icon="moon" if config.THEME == "night" else "sun",
                          on_click=self.toggle_theme),
            ui.IconButton((self.width - margin - HUD_PILL_WIDTH, y,
                           HUD_PILL_WIDTH, size),
                          icon="grid", label="关卡总览",
                          on_click=self.enter_levels, shape="pill", size=15),
        ]

        toolbar = self.toolbar_rect
        top = toolbar.y + TOOL_BUTTON_TOP
        hint = ui.IconButton((TOOL_BUTTON_MARGIN, top, TOOL_BUTTON_SIZE, TOOL_BUTTON_SIZE),
                             icon="bulb", on_click=self.use_hint,
                             label_below="提示")
        guide = ui.IconButton((self.width - TOOL_BUTTON_MARGIN - TOOL_BUTTON_SIZE, top,
                               TOOL_BUTTON_SIZE, TOOL_BUTTON_SIZE),
                              icon="guide", on_click=self.toggle_guides,
                              toggle=True, label_below="辅助线")
        guide.on = self.show_guides          # 开关的当前状态要跟着画面走

        slider = self.zoom_slider_rect
        minus = ui.IconButton((slider.x, slider.y + (slider.height - TOOL_STEP_SIZE) // 2,
                               TOOL_STEP_SIZE, TOOL_STEP_SIZE),
                              icon="minus", on_click=lambda: self.zoom_by(-config.ZOOM_STEP))
        plus = ui.IconButton((slider.right - TOOL_STEP_SIZE,
                              slider.y + (slider.height - TOOL_STEP_SIZE) // 2,
                              TOOL_STEP_SIZE, TOOL_STEP_SIZE),
                             icon="plus", on_click=lambda: self.zoom_by(config.ZOOM_STEP))
        buttons += [hint, guide, minus, plus]
        return buttons

    # ------------------------------------------------------------ 提示 / 辅助线
    def best_hint(self):
        """在「当前能飞出的箭头」里挑一支最值得点的，返回那支箭；没有则 None。

        挑选标准是「消掉它之后能连带解锁多少支其它的」，取最多的那支。
        为什么不随便挑一支能飞的：能飞的里面，有的点掉只是少一支，
        有的点掉会让后面一大串跟着解锁——后者才是对玩家真正有用的提示。

        实现上直接借用棋盘自己的判定：临时把它从格子上摘掉、数一遍
        还剩几支能飞、再放回去。候选最多几十个、每个候选扫一遍棋盘，
        点一下按钮跑一次完全够快（毫秒级）。

        注意**还原时必须写回它在棋盘里的真实下标**（先查好 index_of），
        不能拿"候选列表里的第几个"顶替：那样试算一次就把 grid 写坏了，
        之后所有点击都会判错——这个 bug 真的发生过，测试里专门钉了一条。
        """
        if self.board is None:
            return None
        free = self.board.available_arrows()
        if not free:
            return None

        grid = self.board.grid
        index_of = {id(piece): index for index, piece in enumerate(self.board.pieces)}
        best, best_gain = None, -1
        for piece in free:
            index = index_of[id(piece)]
            for row, col in piece.cells:                 # 假装把它消掉
                grid[row][col] = None
            try:
                gain = len(self.board.available_arrows())
            finally:                                     # 无论如何都要还原
                for row, col in piece.cells:
                    grid[row][col] = index
            if gain > best_gain:
                best, best_gain = piece, gain
        return best

    def use_hint(self):
        """「提示」按钮：高亮一支当前能飞出的箭头，几秒后自己消失。"""
        if self.scene != SCENE_PLAY or self.board is None or self.overlay is not None:
            return
        piece = self.best_hint()
        if piece is None:
            self.show_toast("当前没有能飞出去的箭头，先重新开始吧", config.COLOR_WARN)
            return
        self.hint_piece = piece
        self.hint_timer = config.HINT_DURATION

    def toggle_guides(self):
        """「辅助线」开关：给每支箭头画出它箭头前方的射线。

        两个状态用的是**同一个颜色**，它只帮玩家把方向关系看清楚，
        不替玩家判断能不能点——真要按能否飞出上色，等于把答案画在脸上。
        """
        self.show_guides = not self.show_guides
        self.buttons = self.make_play_buttons()      # 重建才能把开关状态同步到圆钮
        if self.show_guides:
            self.show_toast("辅助线已打开：每支箭头前方的虚线就是它的去路",
                            config.COLOR_TEXT_DIM)
        else:
            self.show_toast("辅助线已关闭", config.COLOR_TEXT_DIM)

    # ------------------------------------------------------------ 设置 / 主题
    def open_settings(self):
        """顶栏齿轮：打开设置浮层（暂停看棋盘，不接受点击）。"""
        if self.scene != SCENE_PLAY:
            return
        self.overlay = OVERLAY_SETTINGS
        self.buttons = self.make_settings_buttons()

    def close_overlay(self):
        self.overlay = None
        self.buttons = self.make_play_buttons()

    def toggle_theme(self):
        """昼夜开关：换一套配色，并把贴图缓存清掉（颜色烘在贴图里）。"""
        config.next_theme()
        ui.clear_caches()
        self.bg = bgfx.Background((self.width, self.height), self.scene)
        self.buttons = self.make_play_buttons() if self.scene == SCENE_PLAY \
            else (self.make_menu_buttons() if self.scene == SCENE_MENU
                  else self.make_levels_buttons())
        self.show_toast("已切换到%s" % ("日间" if config.THEME == "day" else "夜间"),
                        config.COLOR_TEXT_DIM)

    def make_settings_buttons(self):
        """设置面板：五颗按钮竖排。"""
        panel = self.panel_rect
        width, height, gap = 300, 46, 10
        left = panel.centerx - width // 2
        top = panel.y + 94            # 让开上面「设置 / 当前主题」两行（见 draw_settings）
        step = height + gap
        buttons = [
            ui.Button((left, top, width, height), "继续游戏",
                      self.close_overlay, "primary", size=19),
            ui.Button((left, top + step, width, height), "重玩本关",
                      self.restart_level, "ghost", size=17),
            ui.Button((left, top + step * 2, width, height),
                      "切换到日间" if config.THEME == "night" else "切换到夜间",
                      self.toggle_theme, "ghost", size=17),
            ui.Button((left, top + step * 3, width, height), "关卡总览",
                      self.enter_levels, "ghost", size=17),
            ui.Button((left, top + step * 4, width, height), "返回主菜单",
                      self.enter_menu, "ghost", size=17),
        ]
        for button in buttons:
            button.hovered = button.hit(self.mouse_pos)
        return buttons

    def make_overlay_buttons(self):
        panel = self.panel_rect
        buttons = []

        def add_secondary(items, y):
            width, height, gap = 130, 40, 10
            total = len(items) * width + (len(items) - 1) * gap
            left = panel.centerx - total // 2
            for index, (label, action) in enumerate(items):
                buttons.append(ui.Button(
                    (left + index * (width + gap), y, width, height),
                    label, action, "ghost", size=15))

        if self.overlay == OVERLAY_TUTORIAL_DONE:
            buttons.append(ui.Button((panel.centerx - 150, panel.y + 306, 300, 50),
                                     "开始第 1 关", lambda: self.start_level(0),
                                     "success", size=21))
            add_secondary([("再看一遍", self.start_tutorial),
                           ("关卡总览", self.enter_levels),
                           ("返回主菜单", self.enter_menu)], panel.y + 368)
        elif self.overlay == OVERLAY_WIN:
            buttons.append(ui.Button((panel.centerx - 150, panel.y + 306, 300, 50),
                                     "下一关", self.next_level, "success", size=21))
            add_secondary([("重玩本关", self.restart_level),
                           ("关卡总览", self.enter_levels),
                           ("返回主菜单", self.enter_menu)], panel.y + 368)
        elif self.overlay == OVERLAY_FAIL:
            buttons.append(ui.Button((panel.centerx - 150, panel.y + 306, 300, 50),
                                     "重新开始本关", self.restart_level, "primary", size=21))
            add_secondary([("关卡总览", self.enter_levels),
                           ("返回主菜单", self.enter_menu)], panel.y + 368)
        else:
            buttons.append(ui.Button((panel.centerx - 150, panel.y + 306, 300, 50),
                                     "查看关卡总览", self.enter_levels, "success", size=21))
            add_secondary([("重玩第 1 关", lambda: self.start_level(0)),
                           ("返回主菜单", self.enter_menu)], panel.y + 368)

        for button in buttons:
            button.hovered = button.hit(self.mouse_pos)
        return buttons

    def quit(self):
        self.running = False

    # ================================================================ 交互
    def handle_event(self, event):
        """把 pygame 事件转成三种动作：按下、移动、松开。

        点击不在这里直接生效——要等松开时才知道玩家是「点了一下」还是
        「按住拖了两下」。放大棋盘之后靠拖动看边角，混在一起会误触。
        """
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
            self.on_motion(event.pos, event.buttons)
            for button in self.buttons:
                button.hovered = button.hit(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.on_press(event.pos)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.on_release(event.pos)
        elif event.type == pygame.KEYDOWN:
            self.handle_key(event)

    def pick_drag_target(self, pos):
        """按下这一点，接下来拖动的是谁？

        * 按在按钮上 -> None（交给按钮的点击逻辑，别把滑杆也一起拖走）；
        * 按在滑杆上 -> "slider"；
        * 按在棋盘视口里 -> "board"（放大之后拖动看边角）。
        """
        for button in self.buttons:
            if button.hit(pos):
                return None
        if self.scene == SCENE_PLAY:
            if self.overlay is not None:
                return None
            if self.zoom_slider_rect.collidepoint(pos):
                return "slider"
            if self.viewport_rect.collidepoint(pos):
                return "board"
        return None

    def on_press(self, pos):
        self.pressed = True
        self.dragged = False
        self.press_pos = pos
        self.drag_target = self.pick_drag_target(pos)
        if self.drag_target == "slider":
            self.set_zoom_ratio(ui.slider_ratio_from_x(self.zoom_slider_rect, pos[0]))

    def on_motion(self, pos, buttons=(0, 0, 0)):
        if not self.pressed:
            return
        moved = math.hypot(pos[0] - self.press_pos[0], pos[1] - self.press_pos[1])
        if moved > config.DRAG_THRESHOLD:
            self.dragged = True
        if self.drag_target == "slider":
            self.set_zoom_ratio(ui.slider_ratio_from_x(self.zoom_slider_rect, pos[0]))
        elif self.drag_target == "board" and self.dragged:
            step_x = pos[0] - self.mouse_pos[0] if self.mouse_pos != (-1, -1) else 0
            step_y = pos[1] - self.mouse_pos[1] if self.mouse_pos != (-1, -1) else 0
            self.pan = [self.pan[0] + step_x, self.pan[1] + step_y]
            self.layout_board()

    def on_release(self, pos):
        was_pressed, dragged = self.pressed, self.dragged
        self.pressed = False
        self.drag_target = None
        if was_pressed and not dragged:
            self.handle_click(pos)

    def update_hover(self):
        self.hover_cell = None
        self.hover_card = None
        if self.scene == SCENE_PLAY and self.overlay is None:
            self.hover_cell = self.cell_at_pos(self.mouse_pos)
        elif self.scene == SCENE_LEVELS:
            for index, rect in enumerate(self.card_rects):
                if rect.collidepoint(self.mouse_pos):
                    self.hover_card = index
                    break

    def handle_click(self, pos):
        for button in self.buttons:
            if button.hit(pos):
                if button.on_click:
                    button.on_click()
                return

        if self.reset_armed:                    # 点了别处就取消「确认清空」
            self.reset_armed = False
            self.buttons = self.make_levels_buttons()

        if self.scene == SCENE_LEVELS:
            for index, rect in enumerate(self.card_rects):
                if rect.collidepoint(pos):
                    self.click_card(index)
                    return
        if self.scene == SCENE_PLAY and self.overlay is None:
            cell = self.cell_at_pos(pos)
            if cell is not None:
                self.click_cell(cell[0], cell[1])

    def click_card(self, index):
        """点击关卡总览里的一张卡片。已解锁就开局，未解锁就给提示。"""
        if self.is_unlocked(index):
            self.start_level(index)
        else:
            self.show_toast("第 %d 关还没解锁——先通关第 %d 关「%s」吧"
                            % (index + 1, index, LEVELS[index - 1].name),
                            config.COLOR_WARN)

    def handle_key(self, event):
        if event.key == pygame.K_ESCAPE:
            if self.overlay is not None:
                self.close_overlay()
            elif self.scene == SCENE_MENU:
                self.running = False
            else:
                self.enter_menu()
        elif event.key == pygame.K_r and self.scene == SCENE_PLAY and self.overlay is None:
            self.restart_level()
        elif event.key == pygame.K_h and self.scene == SCENE_PLAY and self.overlay is None:
            self.use_hint()
        elif event.key == pygame.K_g and self.scene == SCENE_PLAY and self.overlay is None:
            self.toggle_guides()
        elif event.key in (pygame.K_PLUS, pygame.K_EQUALS, pygame.K_KP_PLUS) \
                and self.scene == SCENE_PLAY and self.overlay is None:
            self.zoom_by(config.ZOOM_STEP)
        elif event.key in (pygame.K_MINUS, pygame.K_KP_MINUS) \
                and self.scene == SCENE_PLAY and self.overlay is None:
            self.zoom_by(-config.ZOOM_STEP)
        elif event.key == pygame.K_SPACE and self.overlay is None:
            if self.scene in (SCENE_MENU, SCENE_LEVELS):
                self.primary_action()

    def click_cell(self, row, col):
        """点击棋盘上的一个格子，返回 ClickResult（供测试脚本直接调用）。"""
        if self.board is None or self.overlay is not None:
            return None

        # 引导这一步指的是哪一支，要在点击**之前**问清楚：
        # 点对了它就会飞走，点完再查那一格已经是空的了。
        step_piece = self.tutorial_target()
        clicked = self.board.piece_at(row, col)

        result = self.board.click(row, col)
        if result is None:
            return None
        if result.kind == CLICK_IGNORED:
            return result

        rect = self.cell_rect(row, col)
        if result.kind == CLICK_FLY:
            self.animations.append(anim.FlyOut(
                result.piece, self.board_rect.topleft, self.cell,
                self.fly_travel(result.piece)))
            if self.hint_piece is not None and self.hint_piece == result.piece:
                self.hint_piece = None               # 已经点掉了，环也该收起来
        elif result.kind == CLICK_BLOCKED:
            head_row, head_col = result.piece.head
            self.animations.append(anim.Impact(
                result.piece, self.board_rect.topleft, self.cell,
                self.cell_rect(head_row, head_col)))
            # 扣生命值的提示是一颗「碎掉的像素心」，不是「失去一心」四个字：
            # 生命值本身就用心的形状表示，心碎的画面一看就懂，
            # 也不至于和「这里没有箭头」那句文字提示混成同一类消息。
            # 心形是 10 格宽的像素图，宽度取 10 的整数倍，每格才是整数像素
            self.floats.append(anim.FloatingHeart(
                (rect.centerx, rect.centery - rect.height * 0.08),
                color=config.COLOR_HP,
                size=max(20, int(round(max(20, self.cell) * 0.78 / 10.0)) * 10),
                duration=1.15, rise=max(24.0, self.cell * 0.95)))
            self.hp_lost_flash = 1.0        # 让刚失去的那颗心闪一下
        elif result.kind == CLICK_EMPTY:
            self.floats.append(anim.FloatingText(
                "这里没有箭头", (rect.centerx, rect.centery - 18),
                config.COLOR_TEXT_FAINT, size=17, duration=0.7, rise=22))

        self.advance_tutorial(result, clicked, step_piece)
        return result

    def fly_travel(self, piece):
        """沿自身路径要滑多远（像素），整条箭头才能完全离开棋盘视口。

        滑出时身体每一点沿路径前进相同的弧长；某点滑过箭头之后，
        就沿着箭头方向直线走出视口。所以总弧长 =
        尾巴到箭头的弧长 + 箭头中心到视口出口的距离 + 余量。
        """
        body = (len(piece.cells) - 1) * self.cell
        head_row, head_col = piece.head
        dx, dy = ui.DIR_VECTORS[piece.direction]
        head_x = self.board_rect.x + (head_col + 0.5) * self.cell
        head_y = self.board_rect.y + (head_row + 0.5) * self.cell
        view = self.viewport_rect
        margin = self.cell * config.FLY_MARGIN_RATIO
        if dx > 0:
            extra = view.right - head_x
        elif dx < 0:
            extra = head_x - view.left
        elif dy > 0:
            extra = view.bottom - head_y
        else:
            extra = head_y - view.top
        return body + max(self.cell, extra + margin)

    # ================================================================ 更新
    def update(self, dt):
        self.time += dt
        self.bg.update(dt)
        for effect in list(self.animations):
            if effect.update(dt):
                self.animations.remove(effect)
        for item in list(self.floats):
            if item.update(dt):
                self.floats.remove(item)

        if self.toast_timer > 0:
            self.toast_timer = max(0.0, self.toast_timer - dt)

        if self.hp_lost_flash > 0.0:
            self.hp_lost_flash = max(0.0, self.hp_lost_flash - dt / HP_FLASH_DURATION)

        if self.hint_timer > 0.0:
            self.hint_timer = max(0.0, self.hint_timer - dt)
            if self.hint_timer == 0.0:
                self.hint_piece = None           # 高亮结束，连那一支一起忘掉

        if self.scene == SCENE_PLAY and self.board is not None and self.overlay is None:
            # 计时只在「真的在玩」的时候往前走：本关已经分出胜负、
            # 或者正弹着结果面板时，时钟都不该再跳——
            # 否则玩家盯着结算面板那几秒，用时还在涨，看着像没停下来。
            if self.board.state == STATE_PLAYING:
                self.elapsed += dt
            elif self.board.state in (STATE_CLEARED, STATE_FAILED):
                # 等飞行动画播完再弹结果面板
                self.overlay_timer += dt
                if self.overlay_timer >= config.RESULT_DELAY:
                    self.show_result()
        return None

    def show_result(self):
        level = self.level
        if self.in_tutorial:
            # 教学关不进存档、不算分：走完这一步就引导去第 1 关；
            # 万一真把 6 颗心点光了也只是重来一遍，同样不给分。
            self.score_max = 0
            self.last_score = 0
            self.score_gain = 0
            self.score_perfect = self.board.hearts_lost == 0
            self.overlay = (OVERLAY_TUTORIAL_DONE if self.board.state == STATE_CLEARED
                            else OVERLAY_FAIL)
            self.buttons = self.make_overlay_buttons()
            return

        self.score_max = scoring.max_score(level)
        if self.board.state == STATE_CLEARED:
            # 得分只看「丢了几颗心」：一颗都没丢拿满分 + 完美奖励，
            # 每丢一颗按比例扣。重玩只留最高分，所以这里先跟存档里的纪录比一比。
            self.last_score = scoring.level_score(level, self.board.hp_left)
            self.score_perfect = self.board.hearts_lost == 0
            self.score_gain = self.progress.record_score(self.level_index, self.last_score)
            self.progress.mark_cleared(self.level_index)      # 记进度 + 解锁下一关
            if self.level_index >= TOTAL_LEVELS - 1:
                self.overlay = OVERLAY_ALL_CLEAR
            else:
                self.overlay = OVERLAY_WIN
        else:
            self.last_score = 0                               # 失败不给分
            self.score_perfect = False
            self.score_gain = 0
            self.overlay = OVERLAY_FAIL
        self.buttons = self.make_overlay_buttons()

    # ================================================================ 渲染
    def draw(self):
        self.bg.draw(self.screen)
        if self.scene == SCENE_MENU:
            self.draw_menu()
        elif self.scene == SCENE_LEVELS:
            self.draw_levels()
        else:
            self.draw_play()
            if self.overlay is not None:
                self.draw_overlay()
        for button in self.buttons:
            button.draw(self.screen)
        self.draw_toast()

    # ---------------------------------------------------------------- 开始界面
    def draw_menu(self):
        center_x = self.width // 2
        ui.draw_text(self.screen, "一箭又一箭", (center_x, 116),
                     size=52, bold=True, anchor="center")
        ui.draw_text(self.screen, "点一下箭头，让它飞出棋盘", (center_x, 168),
                     size=18, color=config.COLOR_TEXT_DIM, anchor="center")

        # 进度一行（顺带报一下总分：目标感主要来自分数的增长）
        cleared = self.progress.cleared_count(TOTAL_LEVELS)
        total = self.progress.total_score(TOTAL_LEVELS)
        full = scoring.total_max_score(LEVELS)
        if cleared >= TOTAL_LEVELS:
            progress_text = "已通关全部 %d 关 · 总分 %d / %d，随时可以重玩刷分" % (
                TOTAL_LEVELS, total, full)
        elif cleared == 0:
            progress_text = ("还没开始 · 共 %d 关，满分 %d 分 · 第一次玩建议先走一遍「教学关」"
                             % (TOTAL_LEVELS, full))
        else:
            index = self.next_level_index()
            progress_text = "已通关 %d / %d 关 · 总分 %d / %d · 下一关是第 %d 关「%s」" % (
                cleared, TOTAL_LEVELS, total, full, index + 1, LEVELS[index].name)
        ui.draw_text(self.screen, progress_text, (center_x, 204),
                     size=14, color=config.COLOR_TEXT_FAINT, anchor="center")

        self.draw_rules_card()

        ui.draw_text(self.screen, "空格 开始 / 继续　Esc 退出　进入关卡后：R 重开、H 提示、G 辅助线、加减号缩放",
                     (center_x, 838), size=13, color=config.COLOR_TEXT_FAINT, anchor="center")

    def draw_rules_card(self):
        """主界面的玩法说明卡片：文字规则 + 两组迷你棋盘示例。

        卡片里所有纵向位置都写成 ``card.y + 偏移``，偏移量按「标题 26 + 五行规则 125
        + 分隔线 + 小标题 + 两行示例 + 脚注」的顺序一路排下来，彼此留出空隙。
        不要改成裸数字绝对坐标——改卡片高度时下面整串都会跟着错位。
        """
        card = pygame.Rect((self.width - 500) // 2, 228, 500, 436)
        ui.draw_round_rect(self.screen, card, config.COLOR_PANEL, radius=18)
        ui.draw_round_rect(self.screen, card, config.COLOR_PANEL_EDGE, radius=18, width=2)

        ui.draw_text(self.screen, "玩法说明", (card.x + 24, card.y + 16),
                     size=20, bold=True, color=config.COLOR_PANEL_TEXT)

        rules = (
            "① 一支「箭」是一条占好几格的箭头，末端那个箭头就是它的朝向。",
            "② 点它身上任意一格：箭头前方是空的，整条箭头就飞出去。",
            "③ 前方还有别的箭头挡着，就飞不出去，并且失去",
            "④ 清空本关所有箭头即可通关；剩下的生命值越多，本关得分越高。",
            "⑤ 生命值耗尽本关失败；通关才解锁下一关，得分与进度都会自动保存。",
        )
        y = card.y + 52
        for index, line in enumerate(rules):
            rect = ui.draw_text(self.screen, line, (card.x + 24, y),
                                size=14, color=config.COLOR_PANEL_TEXT_DIM)
            if index == 2:
                # 行尾直接画一颗像素心，而不是写「一心」两个字——
                # 生命值就是用这个图形表示的，文字说明也照同一个写法走
                ui.draw_heart(self.screen, (rect.right + 12, rect.centery),
                              config.HEART_INLINE_SIZE, config.COLOR_HP)
            y += 25

        divider = card.y + 190
        pygame.draw.line(self.screen, config.COLOR_PANEL_EDGE,
                         (card.x + 24, divider), (card.right - 24, divider), 1)

        demo_x = card.x + 24
        ui.draw_paragraph(self.screen, "两个微型棋盘，看清「挡」和「通」的区别：",
                          pygame.Rect(demo_x, divider + 16, 460, 22),
                          size=13, color=config.COLOR_PANEL_TEXT_DIM)

        # 上：被挡。下：通畅。两张小图上下对照，比一整段文字好读。
        self.draw_demo_row(demo_x, card.y + 246, DEMO_BLOCKED_SPECS,
                           DEMO_BLOCKED_CAPTION, config.COLOR_DANGER, heart_icon=True)
        self.draw_demo_row(demo_x, card.y + 326, DEMO_CLEAR_SPECS,
                           DEMO_CLEAR_CAPTION, config.COLOR_SUCCESS)

        ui.draw_text(self.screen, "把鼠标放在箭头上，还能看到它前方的路径：绿色=畅通，红色=被挡。",
                     (card.x + 24, card.y + 402), size=13,
                     color=config.COLOR_PANEL_TEXT_DIM)

    def draw_demo_row(self, x, y, specs, caption, color, heart_icon=False, cell=26):
        """画一行迷你棋盘（用于玩法说明里的示例）。

        示例图靠左，说明文字靠右；``heart_icon`` 为真时在说明文字末尾接一颗像素心
        （「还会失去 ❤」），心的位置由文字实际右边缘算出来，所以改文案不会画歪。
        """
        for piece in demo_pieces(specs):
            ui.draw_piece(self.screen, (x, y), piece, cell)
        board_w = DEMO_COLS * cell
        text_x = x + board_w + 16
        text_w = self.width - text_x - 40
        # 自己先折一次行：draw_paragraph 只返回占用高度，不返回末行的右边缘，
        # 而「失去 ❤」那颗心要贴着最后一个字画，所以得按同样的换行规则算一遍。
        lines = ui.wrap_text(caption, size=13, max_width=text_w)
        line_h = ui.get_font(13).get_linesize() + 3
        row_px = cell * DEMO_ROWS
        top = y + max(0, (row_px - len(lines) * line_h) // 2)
        ui.draw_paragraph(self.screen, caption, pygame.Rect(text_x, top, text_w, 40),
                          size=13, color=color, line_gap=3)
        if heart_icon:
            right = text_x + ui.text_width(lines[-1], size=13)
            baseline = top + (len(lines) - 1) * line_h + ui.get_font(13).get_linesize() // 2
            ui.draw_heart(self.screen, (right + 11, baseline),
                          config.HEART_INLINE_SIZE, config.COLOR_HP)
        return top + len(lines) * line_h

    # ---------------------------------------------------------------- 关卡总览
    def draw_levels(self):
        ui.draw_text(self.screen, "关卡总览", (30, 44), size=32, bold=True)

        cleared = self.progress.cleared_count(TOTAL_LEVELS)
        unlocked = self.progress.highest_unlocked(TOTAL_LEVELS)
        ui.draw_text(self.screen, "已通关 %d / %d 关" % (cleared, TOTAL_LEVELS),
                     (30, 86), size=14, color=config.COLOR_TEXT_FAINT)
        ui.draw_text(self.screen, "已解锁到第 %d 关" % (unlocked + 1),
                     (30, 108), size=14, color=config.COLOR_TEXT_FAINT)

        for index, rect in enumerate(self.card_rects):
            self.draw_level_card(rect, index)

        # 三行卡片的下沿在 150 + 3×172 + 2×24 = 714，下面这块留给总结与按钮
        ui.draw_text(self.screen,
                     "总分 %d / %d　·　进度自动保存" % (
                         self.progress.total_score(TOTAL_LEVELS),
                         scoring.total_max_score(LEVELS)),
                     (self.width // 2, 748), size=14,
                     color=config.COLOR_TEXT_DIM, anchor="center")
        ui.draw_text(self.screen, "点击卡片开始挑战；带锁的关卡需要先通关它前面的一关。",
                     (self.width // 2, 856), size=13,
                     color=config.COLOR_TEXT_FAINT, anchor="center")
        ui.draw_text(self.screen, "Esc 返回主菜单　　空格 继续挑战",
                     (self.width // 2, 882), size=12,
                     color=config.COLOR_TEXT_FAINT, anchor="center")

    def draw_level_card(self, rect, index):
        level = LEVELS[index]
        unlocked = self.is_unlocked(index)
        cleared = self.is_cleared(index)
        hovered = self.hover_card == index

        if not unlocked:
            background, edge, title_color = (config.COLOR_CARD_LOCKED,
                                             config.COLOR_CARD_LOCKED_EDGE,
                                             config.COLOR_TEXT_FAINT)
        elif cleared:
            background, edge = config.COLOR_CARD_DONE, config.COLOR_CARD_DONE_EDGE
            title_color = config.COLOR_TEXT
        else:
            background, edge = config.COLOR_CARD, config.COLOR_CARD_EDGE
            title_color = config.COLOR_TEXT
        if hovered and unlocked:
            background = config.COLOR_CARD_HOVER
            edge = config.COLOR_ACCENT

        ui.draw_round_rect(self.screen, rect, background, radius=14)
        ui.draw_round_rect(self.screen, rect, edge, radius=14, width=2)

        # 左上角序号
        ui.draw_text(self.screen, "%02d" % (index + 1), (rect.x + 14, rect.y + 12),
                     size=22, bold=True,
                     color=config.COLOR_TEXT_DIM if unlocked else config.COLOR_TEXT_FAINT)

        # 名称
        ui.draw_text(self.screen, level.name, (rect.x + 14, rect.y + 46),
                     size=18, bold=True, color=title_color)

        # 规格：顺手把本关给几颗心写出来，玩家开局前就知道这一关能错几次
        ui.draw_text(self.screen, "%d×%d · %d 支箭头 · %d 颗心" % (
            level.rows, level.cols, level.arrow_count, level.max_hp),
            (rect.x + 14, rect.y + 78), size=12,
            color=config.COLOR_TEXT_FAINT)

        # 状态（已通关的关卡把最高分一起报出来：这是重玩的理由）
        best = self.progress.best_score(index)
        if not unlocked:
            status, status_color = "未解锁", config.COLOR_TEXT_FAINT
        elif cleared and best > 0:
            status, status_color = "已通关 · 最高 %d 分" % best, config.COLOR_SUCCESS
        elif cleared:
            # 老存档（只有通关记录、还没有分数）或截图脚本造的进度会走到这里，
            # 不写「最高 0 分」这种让人以为存档坏了的说法
            status, status_color = "已通关", config.COLOR_SUCCESS
        else:
            status, status_color = "可挑战 · 满分 %d" % scoring.max_score(level), \
                config.COLOR_ACCENT
        ui.draw_text(self.screen, status, (rect.x + 14, rect.y + 108), size=13,
                     color=status_color)

        # 右上角：锁 / 星星 / 对勾
        if not unlocked:
            ui.draw_lock(self.screen, (rect.right - 26, rect.y + 26), 18)
        else:
            ui.draw_stars(self.screen, (rect.right - 14, rect.y + 22),
                          level.stars, total=5, radius=6, gap=3)
            if cleared:
                ui.draw_check(self.screen, (rect.right - 24, rect.bottom - 22), 18)

    # ---------------------------------------------------------------- 游戏界面
    def draw_play(self):
        self.draw_board()
        # 飞出动画要一起被视口裁住，否则整条箭头会飞过顶栏、在信息栏上滑过去
        previous_clip = self.screen.get_clip()
        self.screen.set_clip(self.viewport_rect)
        for effect in self.animations:
            effect.draw(self.screen)
        self.screen.set_clip(previous_clip)
        for item in self.floats:
            item.draw(self.screen)
        self.draw_tutorial_bar()
        self.draw_toolbar()
        self.draw_hud()

    # ---------------------------------------------------------------- 顶部信息栏
    def time_text(self):
        """本关已用时的文本，格式 MM:SS；超过一小时进位成 H:MM:SS。"""
        total = max(0, int(self.elapsed))
        if total >= 3600:
            return "%d:%02d:%02d" % (total // 3600, (total % 3600) // 60, total % 60)
        return "%02d:%02d" % (total // 60, total % 60)

    def draw_hud(self):
        """顶部信息栏：上面一行标题，下面一行四组信息（整体居中）。"""
        hud = pygame.Rect(0, 0, self.width, config.HUD_HEIGHT)
        pygame.draw.rect(self.screen, config.COLOR_HUD, hud)
        pygame.draw.line(self.screen, config.COLOR_HUD_LINE,
                         (0, config.HUD_HEIGHT - 1), (self.width, config.HUD_HEIGHT - 1))
        self.draw_hud_title()
        self.draw_hud_info()

    def draw_hud_title(self):
        """标题行：编号关卡写「第 N 关 + 关卡名」，教学关写「教学关」。"""
        if self.in_tutorial:
            # 教学关的 Level.name 本身就是「教学关」，不必再拼一遍
            title, title_color = "教学关", config.COLOR_TUTORIAL
            name = "跟着高亮环走一遍就会玩了"
        else:
            title, title_color = "第 %d 关" % (self.level_index + 1), config.COLOR_TEXT
            name = self.level.name

        title_w = ui.text_width(title, HUD_TITLE_SIZE, True)
        name_w = ui.text_width(name, 16)
        gap = 12
        x = self.width // 2 - (title_w + gap + name_w) // 2
        ui.draw_text(self.screen, title, (x, HUD_TITLE_Y), size=HUD_TITLE_SIZE,
                     color=title_color, bold=True, anchor="midleft")
        ui.draw_text(self.screen, name, (x + title_w + gap, HUD_TITLE_Y + 1),
                     size=16, color=config.COLOR_TEXT_DIM, anchor="midleft")

    def draw_hud_info(self):
        """信息行：计时 / 生命值 / 剩余箭头 / 本关得分，四项横排、整体居中。

        为什么不写死 x 坐标：这一行里心数随关卡变化（3~4 颗）、得分位数也会变，
        固定坐标每动一点内容就要重新人工核算会不会压在一起。
        """
        board = self.board
        hp = board.hp_left
        heart_size, heart_gap = HUD_HEART_SIZE, HUD_HEART_GAP
        hearts_w = board.max_hp * heart_size + (board.max_hp - 1) * heart_gap
        hp_text = "%d / %d" % (hp, board.max_hp)
        hp_w = hearts_w + 8 + ui.text_width(hp_text, 14)
        clock_w = HUD_CLOCK_SIZE + 6 + ui.text_width(self.time_text(), 16, True)
        arrow_w = ui.text_width("剩余", 14) + 6 + ui.text_width(str(board.remaining), 20, True)

        if self.in_tutorial:
            score_w = ui.text_width("不计分", 14)
        else:
            score_w = (ui.text_width("得分", 14) + 6
                       + ui.text_width(str(board.score), 20, True) + 5
                       + ui.text_width("/ %d" % scoring.max_score(self.level), 13))

        total = clock_w + hp_w + arrow_w + score_w + HUD_INFO_GAP * 3
        x = self.width // 2 - total // 2

        # 1) 计时：一个钟表图标 + MM:SS
        ui.draw_icon_clock(self.screen, (x + HUD_CLOCK_SIZE / 2.0, HUD_ROW_Y),
                           HUD_CLOCK_SIZE, config.COLOR_TEXT_DIM)
        ui.draw_text(self.screen, self.time_text(), (x + HUD_CLOCK_SIZE + 6, HUD_ROW_Y),
                     size=16, color=config.COLOR_TEXT, bold=True, anchor="midleft")
        x += clock_w + HUD_INFO_GAP

        # 2) 生命值：实心像素心 = 还能错几次，只剩轮廓的 = 已经失去的那几颗。
        #    刚失去的那颗套一圈短暂的红色脉冲——点错时一眼看出是哪颗心没了。
        if self.hp_lost_flash > 0.0 and hp < board.max_hp:
            center = (x + heart_size / 2.0 + hp * (heart_size + heart_gap), HUD_ROW_Y)
            ui.draw_glow(self.screen, center, heart_size + 4, (176, 56, 56),
                         self.hp_lost_flash, falloff=1.7)
        ui.draw_hearts(self.screen, (x, HUD_ROW_Y), hp, board.max_hp,
                       size=heart_size, gap=heart_gap)
        ui.draw_text(self.screen, hp_text, (x + hearts_w + 8, HUD_ROW_Y), size=14,
                     color=config.COLOR_TEXT_DIM, anchor="midleft")
        x += hp_w + HUD_INFO_GAP

        # 3) 剩余箭头
        ui.draw_text(self.screen, "剩余", (x, HUD_ROW_Y), size=14,
                     color=config.COLOR_TEXT_DIM, anchor="midleft")
        ui.draw_text(self.screen, str(board.remaining),
                     (x + ui.text_width("剩余", 14) + 6, HUD_ROW_Y),
                     size=20, color=config.COLOR_ACCENT, bold=True, anchor="midleft")
        x += arrow_w + HUD_INFO_GAP

        # 4) 本关得分：点错会立刻往下掉，所以刚丢心时把数字染红提示一下。
        #    教学关不参与计分，这一栏换成说明文字，免得玩家以为没得分是出错了。
        if self.in_tutorial:
            ui.draw_text(self.screen, "不计分", (x, HUD_ROW_Y), size=14,
                         color=config.COLOR_TEXT_FAINT, anchor="midleft")
        else:
            ui.draw_text(self.screen, "得分", (x, HUD_ROW_Y), size=14,
                         color=config.COLOR_TEXT_DIM, anchor="midleft")
            score_color = (config.COLOR_DANGER if self.hp_lost_flash > 0.0
                           else config.COLOR_SCORE)
            rect = ui.draw_text(self.screen, str(board.score),
                                (x + ui.text_width("得分", 14) + 6, HUD_ROW_Y),
                                size=20, color=score_color, bold=True, anchor="midleft")
            ui.draw_text(self.screen, "/ %d" % scoring.max_score(self.level),
                         (rect.right + 5, HUD_ROW_Y + 3), size=13,
                         color=config.COLOR_TEXT_FAINT, anchor="midleft")

    # ---------------------------------------------------------------- 棋盘
    def hovered_piece(self):
        if self.hover_cell is None or self.board is None:
            return None
        return self.board.piece_at(*self.hover_cell)

    def draw_board(self):
        """画棋盘。

        这一版**不画底格**（对齐参考画面）：棋盘就是深色底上一片极淡的点阵，
        箭头是画面上最亮的东西。

        为什么去掉底格：这个游戏的难度来自「在一堆箭头里找出能点的那支」，
        而几十个空格子的方框会让视线一直被拽住，那是"乱"不是"难"。
        把底格换成点阵之后，棋盘范围照样看得出来，箭头却跳出来了。
        """
        board = self.board
        view = self.viewport_rect
        dot_color = ui.mix_color(config.COLOR_BG_TOP, config.COLOR_DOT,
                                 config.COLOR_DOT_ALPHA / 255.0)
        dot_radius = max(1, int(round(self.cell * 0.075)))

        # 悬停：整条射线染色，绿色=畅通、红色=被挡
        hovered = self.hovered_piece()
        path_cells, path_centers, blocker_piece = [], [], None
        path_color = config.COLOR_PATH_OK
        if hovered is not None and board.state == STATE_PLAYING:
            # 被挡时路径只画到挡路那一格为止——那之后的格子跟「为什么飞不出去」
            # 没关系。截断由 board.path_to_blocker 负责，界面这里不要自己
            # 拿 blocker.head 去 index()：挡路的通常是那支箭头的**身子**，
            # 它的箭头可能在很远的另一头，那样写会直接抛 ValueError。
            path, blocker_piece = board.path_to_blocker(hovered)
            if blocker_piece is not None:
                path_color = config.COLOR_PATH_BLOCK
            path_cells = path
            path_centers = [self.cell_center(*hovered.head)]
            path_centers += [self.cell_center(*cell) for cell in path]

        step = self.current_step
        pulse = self.tutorial_pulse()
        hover_pulse = 0.5 + 0.5 * math.sin(self.time * 5.2)

        previous_clip = self.screen.get_clip()
        self.screen.set_clip(view)

        # 1) 点阵：只在空格子上画。有箭头的位置不需要点，
        #    否则会在箭头的圆角边上露出半颗点，看着像脏东西。
        for row in range(board.rows):
            for col in range(board.cols):
                if board.piece_at(row, col) is None:
                    rect = self.cell_rect(row, col)
                    pygame.draw.circle(self.screen, dot_color, rect.center, dot_radius)

        # 2) 悬停射线的底色。方块往里缩一圈：整格染色会变成一块块生硬的色斑，
        #    缩一圈之后就只是"沿路径点的几个记号"，方向感还在，画面却干净多了。
        inset = config.COLOR_PATH_INSET
        for row, col in path_cells:
            rect = self.cell_rect(row, col)
            ui.draw_round_rect_alpha(
                self.screen, rect.inflate(-inset * 2, -inset * 2), path_color,
                config.COLOR_PATH_ALPHA, radius=max(3, config.CELL_RADIUS - 4))

        # 3) 辅助线画在箭头**下面**：它是背景信息，不该压住箭头本身
        if self.show_guides:
            self.draw_guides()

        # 4) 箭头本身
        for piece in board.pieces:
            if board.piece_at(*piece.head) is not piece and board.piece_at(*piece.head) is None:
                continue                                  # 已经飞走了
            if board.grid[piece.head[0]][piece.head[1]] is None:
                continue
            ui.draw_piece(self.screen, self.board_rect.topleft, piece, self.cell)

        # 5) 悬停射线上的流光：一颗亮点从箭头出发跑到被挡处，循环播放
        if len(path_centers) > 1:
            self.draw_path_flow(path_centers, path_color)

        # 6) 各种"环"统一放在最后画：先画的会被后面几支箭头压掉边角，
        #    看上去像缺了一块。
        #    挡路的那一支**只圈住挡路的那一格**：整支圈起来会跟悬停环糊成
        #    一片红蓝交错的框，而玩家真正想知道的是「是哪一格挡着我」——
        #    红色高亮射线已经把方向指过去了，这一格就是答案。
        if path_cells and blocker_piece is not None:
            self.draw_cell_ring(self.cell_rect(*path_cells[-1]),
                                config.COLOR_DANGER, 1.0)
        if hovered is not None:
            color = ui.mix_color(config.COLOR_TEXT_FAINT, config.COLOR_HOVER_RING,
                                 0.55 + 0.45 * hover_pulse)
            self.draw_piece_ring(hovered, color, 1.0)
        if step is not None:
            self.draw_tutorial_ring(self.cell_rect(step.row, step.col), pulse)
        if self.hint_piece is not None:
            self.draw_hint_ring(self.hint_piece)

        self.screen.set_clip(previous_clip)

    # ---------------------------------------------------------------- 辅助线 / 提示环
    def guide_segment(self, piece):
        """算出一支箭头的辅助线两端点（屏幕坐标）；这支已经飞走则返回 None。

        起点是**箭头末端所在的那条格边**，不是格子中心：线从箭头的尖端接上去
        才连贯，也不会糊在箭头自己身上。

        终点分两种：前方有箭头就指到**挡路那一格的中心**，前方没有就一路画到棋盘边。

        为什么终点取"挡路那一格的中心"而不是它的入口格线：盘面是铺满的
        （铺满率 93% 以上），大多数箭头的去路只有一格，停在入口格线的话线长
        正好是 0——辅助线在密铺盘面上等于什么都没画。取中心既有半格可画
        （看得见），又仍然指着"挡我的就是这一格"。

        挡路的是**射线上被占的那一格**，不是挡路那支的箭头所在格：
        挡路的通常是对方的身子，箭头可能在棋盘另一头。早先这里直接写
        `blocker.head`，辅助线会斜穿整个棋盘去连一个方向完全无关的格子。
        所以这段几何单独抽成一个方法，好被测试盯住。
        """
        if self.board.grid[piece.head[0]][piece.head[1]] is None:
            return None
        dx, dy = ui.DIR_VECTORS[piece.direction]
        head = self.cell_center(*piece.head)
        start = (head[0] + dx * self.cell * 0.5, head[1] + dy * self.cell * 0.5)

        path, blocker = self.board.path_to_blocker(piece)
        if blocker is not None:
            return start, self.cell_center(*path[-1])
        return start, {
            "up": (start[0], self.board_rect.top),
            "down": (start[0], self.board_rect.bottom),
            "left": (self.board_rect.left, start[1]),
            "right": (self.board_rect.right, start[1]),
        }[piece.direction]

    def draw_guides(self):
        """辅助线：给每支箭头画一条朝它箭头方向延伸的虚线。

        两端怎么算见 `guide_segment`。两种终点**用同一个颜色**是刻意的：
        这条线的用途是帮玩家看清方向关系，不是替玩家判断。
        真要按"能不能飞"分别上绿/上红，等于把答案画在脸上，
        剩下的操作就只剩按图索骥了。
        """
        color = ui.mix_color(config.COLOR_BG_TOP, config.COLOR_GUIDE,
                             config.COLOR_GUIDE_ALPHA / 255.0)
        for piece in self.board.pieces:
            segment = self.guide_segment(piece)
            if segment is None:
                continue                                   # 已经飞走了
            ui.draw_dashed_line(self.screen, color, segment[0], segment[1],
                                dash=max(4, int(self.cell * 0.20)),
                                gap=max(3, int(self.cell * 0.16)),
                                width=max(1, int(self.cell * 0.09)))

    def draw_cell_ring(self, rect, color, alpha_ratio, width=None):
        """给单独一格套一圈描边（整支箭头的高亮就是逐格调用它拼出来的）。"""
        if width is None:
            width = max(2, int(self.cell * 0.11))
        grow = max(2, int(self.cell * 0.12))
        radius = max(3, config.CELL_RADIUS + grow)
        ui.draw_round_rect_alpha(self.screen, rect.inflate(grow * 2, grow * 2), color,
                                 int(255 * alpha_ratio), radius=radius, width=width)

    def draw_piece_ring(self, piece, color, alpha_ratio, width=None):
        """给一整支箭头套一圈描边（逐格画，所以弯折处也是贴着形状的）。"""
        for row, col in piece.cells:
            self.draw_cell_ring(self.cell_rect(row, col), color, alpha_ratio, width)

    def draw_hint_ring(self, piece):
        """「提示」高亮的那一支：一圈会呼吸的青绿环 + 一团加法光。

        用青绿而不是教学关的黄色：教学关的黄环意思是"就该点这里"，
        提示只是"可以考虑这一支"，两者会出现在同一套界面上，颜色得分得开。

        hint_timer 用完之后环自己就没了，不需要玩家手动关——
        高亮一直挂着会让人以为那一支有什么特殊状态。
        """
        fade = min(1.0, max(0.0, self.hint_timer) / 0.6)   # 最后 0.6 秒淡出
        if fade <= 0.0:
            return
        pulse = 0.5 + 0.5 * math.sin(self.time * 6.0)
        self.draw_piece_ring(piece, config.COLOR_HINT,
                             (110 + pulse * 120) / 255.0 * fade,
                             width=max(2, int(self.cell * 0.12)))
        for row, col in piece.cells:
            rect = self.cell_rect(row, col)
            ui.draw_glow(self.screen, rect.center, int(self.cell * 0.62),
                         (34, 126, 104), 0.40 * fade, falloff=2.0)

    def draw_path_flow(self, centers, color):
        """沿悬停路径跑动的流光，让「能不能飞」这条信息动起来。"""
        segments = []
        total = 0.0
        for start, end in zip(centers, centers[1:]):
            length = math.hypot(end[0] - start[0], end[1] - start[1])
            if length <= 0:
                continue
            segments.append((start, end, length))
            total += length
        if total <= 0:
            return

        travel = (self.time * 1.5) % 1.0 * total
        position = centers[-1]
        for start, end, length in segments:
            if travel <= length:
                ratio = travel / length
                position = (start[0] + (end[0] - start[0]) * ratio,
                            start[1] + (end[1] - start[1]) * ratio)
                break
            travel -= length
        ui.draw_glow(self.screen, position, max(12, int(self.cell * 0.7)), color,
                     0.75, falloff=1.7)

    def tutorial_pulse(self):
        """0~1 的呼吸系数，用于教学关高亮的闪烁节奏。"""
        return 0.5 + 0.5 * math.sin(self.time * 4.0)

    def draw_tutorial_ring(self, rect, pulse):
        """教学关的目标格子高亮环，用正弦做呼吸效果，吸引注意力。"""
        grow = max(3, int(self.cell * 0.16)) + int(pulse * 3)
        ring = rect.inflate(grow * 2, grow * 2)
        ui.draw_round_rect_alpha(self.screen, ring, config.COLOR_TUTORIAL,
                                 int(120 + pulse * 110),
                                 radius=config.CELL_RADIUS + grow,
                                 width=max(2, int(self.cell * 0.12)))

    def draw_tutorial_bar(self):
        """教学关底部的讲解条：这一步该点哪里、为什么。"""
        step = self.current_step
        if step is None:
            return
        bar = self.tutorial_bar_rect
        ui.draw_round_rect(self.screen, bar, config.COLOR_TUTORIAL_BAR, radius=14)
        ui.draw_round_rect(self.screen, bar, config.COLOR_TUTORIAL_BAR_EDGE,
                           radius=14, width=2)

        total = len(self.level.steps)
        ui.draw_text(self.screen, "教学 %d / %d" % (self.tutorial_index + 1, total),
                     (bar.right - 16, bar.centery), size=14,
                     color=config.COLOR_TUTORIAL, bold=True, anchor="midright")

        # 右侧要留出「教学 x / y」的位置，左边留一点内边距
        text_area = pygame.Rect(bar.x + 16, bar.y + 8, bar.width - 108, bar.height - 16)
        ui.draw_paragraph(self.screen, step.text, text_area, size=14,
                          color=config.COLOR_TEXT, line_gap=2)

    def draw_toolbar(self):
        """底部工具栏：底衬、分隔线、缩放滑杆。

        「提示 / 辅助线 / − / +」四个按钮都在 self.buttons 里，和其它按钮共用
        一份绘制代码——否则"工具栏上的按钮"和"别处的按钮"会各有一套悬停、
        开关逻辑，改一处忘一处，两边迟早长得不一样。
        """
        bar = self.toolbar_rect
        pygame.draw.rect(self.screen, config.COLOR_TOOLBAR, bar)
        pygame.draw.line(self.screen, config.COLOR_TOOLBAR_LINE,
                         (0, bar.y), (self.width, bar.y))

        slider = self.zoom_slider_rect
        ui.draw_slider(self.screen, slider, self.zoom_ratio)
        ui.draw_text(self.screen, "缩放 %d%%" % int(round(self.zoom * 100)),
                     (self.width // 2, bar.y + TOOL_LABEL_Y), size=13,
                     color=config.COLOR_TEXT_DIM, anchor="center")

    # ---------------------------------------------------------------- 浮层
    def draw_overlay(self):
        mask = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        mask.fill(tuple(config.COLOR_MASK) + (210,))
        self.screen.blit(mask, (0, 0))

        if self.overlay == OVERLAY_SETTINGS:
            self.draw_settings()
            return

        panel = self.panel_rect
        ui.draw_round_rect(self.screen, panel, config.COLOR_PANEL, radius=18)
        ui.draw_round_rect(self.screen, panel, config.COLOR_PANEL_EDGE, radius=18, width=2)

        if self.in_tutorial and self.overlay == OVERLAY_TUTORIAL_DONE:
            title, color = "教学结束！", config.COLOR_SUCCESS
            desc = "玩法就是这些：清空本关的箭头即可通关"
        elif self.in_tutorial:
            title, color = "再试一次", config.COLOR_WARN
            desc = "生命值用完了——教学关不计分也不占编号，重来一遍就好"
        elif self.overlay == OVERLAY_WIN:
            title, color = "通关！", config.COLOR_SUCCESS
            desc = "第 %d 关「%s」的箭头全部飞出了棋盘" % (self.level_index + 1, self.level.name)
        elif self.overlay == OVERLAY_FAIL:
            title, color = "本关失败", config.COLOR_DANGER
            desc = "生命值已经耗尽，本关不得分，再试一次吧"
        else:
            title, color = "全部通关！", config.COLOR_SUCCESS
            desc = "%d 个关卡的箭头都被你清理干净了" % TOTAL_LEVELS

        ui.draw_text(self.screen, title, (panel.centerx, panel.y + 52),
                     size=40, color=color, bold=True, anchor="center")
        ui.draw_text(self.screen, desc, (panel.centerx, panel.y + 98),
                     size=16, color=config.COLOR_PANEL_TEXT_DIM, anchor="center")

        if self.in_tutorial:
            # 教学关没有得分这一格——它不进任何纪录；用时还是值得给玩家看一眼的
            stats = [
                ("本关箭头", "%d 支" % self.board.total, False),
                ("失去生命值", "%d 颗" % self.board.hearts_lost, False),
                ("本关用时", self.time_text(), False),
                ("本关得分", "不计分", False),
            ]
        else:
            stats = [
                ("本关箭头", "%d 支" % self.board.total, False),
                ("失去生命值", "%d 颗" % self.board.hearts_lost, False),
                ("本关用时", self.time_text(), False),
                ("本关得分", "%d / %d" % (self.last_score, self.score_max), True),
            ]
        # 2 × 2 摆四格：竖屏面板不宽，一行四格每格只剩 100 出头，
        # 「本关得分」那格里的「1500 / 1500」会直接顶到边线上。
        box_w, box_h, gap = 200, 62, 12
        total = 2 * box_w + gap
        left = panel.centerx - total // 2
        for index, (label, value, highlight) in enumerate(stats):
            row, col = divmod(index, 2)
            box = pygame.Rect(left + col * (box_w + gap), panel.y + 114 + row * (box_h + 12),
                              box_w, box_h)
            ui.draw_round_rect(self.screen, box,
                               config.COLOR_STAT_BOX_SCORE if highlight else config.COLOR_STAT_BOX,
                               radius=12)
            ui.draw_text(self.screen, label, (box.centerx, box.y + 16),
                         size=13, color=config.COLOR_TEXT_DIM, anchor="center")
            ui.draw_text(self.screen, value, (box.centerx, box.y + 42), size=19,
                         bold=True, anchor="center",
                         color=config.COLOR_SCORE if highlight else config.COLOR_TEXT)

        # 底下那句「为什么是这个分数」：直接写出算式，玩家能自己核对。
        # 用 draw_paragraph 折行而不是 draw_text 一行画完——这句最长能到
        # 「零失误，额外 +250 分完美奖励　·　刷新纪录 +1500　·　总分 1500 / 8400」，
        # 一张 460 宽的面板放不下，硬画会顶穿左右两条边线。
        note, note_color = self.score_note()
        ui.draw_paragraph(self.screen, note,
                          pygame.Rect(panel.centerx - 210, panel.y + 258, 420, 44),
                          size=13, color=note_color, line_gap=4, align="center")

    def draw_settings(self):
        """设置面板：五颗按钮竖排 + 一句键盘说明。"""
        panel = self.panel_rect
        ui.draw_round_rect(self.screen, panel, config.COLOR_PANEL, radius=18)
        ui.draw_round_rect(self.screen, panel, config.COLOR_PANEL_EDGE, radius=18, width=2)

        # 标题与主题行都用 center 锚点，所以给的是「文字中心」的纵坐标：
        # 30 号字半高约 15、13 号字半高约 7，两者中心差 32 才不会叠在一起。
        # 面板顶部到第一颗按钮（panel.y + 94）之间就是这两行的空间。
        ui.draw_text(self.screen, "设置", (panel.centerx, panel.y + 40),
                     size=30, bold=True, color=config.COLOR_PANEL_TEXT, anchor="center")
        ui.draw_text(self.screen, "当前主题：%s" % ("夜间" if config.THEME == "night" else "日间"),
                     (panel.centerx, panel.y + 72), size=13,
                     color=config.COLOR_PANEL_TEXT_DIM, anchor="center")

        lines = [
            "R 重开本关　H 提示　G 辅助线",
            "加减号缩放棋盘；放大后按住棋盘可以拖动查看",
        ]
        y = panel.bottom - 62
        for line in lines:
            ui.draw_text(self.screen, line, (panel.centerx, y), size=13,
                         color=config.COLOR_PANEL_TEXT_DIM, anchor="center")
            y += 22

    def score_note(self):
        """结果面板底部的得分说明，返回 (文字, 颜色)。"""
        if self.in_tutorial:
            return ("教学关不计分、不占关卡编号：想再看一遍，随时从主菜单进来",
                    config.COLOR_PANEL_TEXT_DIM)
        if self.overlay == OVERLAY_FAIL:
            return ("生命值耗尽时本关得 0 分——先通关，再谈分数", config.COLOR_PANEL_TEXT_DIM)

        parts = []
        if self.score_perfect:
            # 把奖励的来源写清楚：基础分只按剩余生命值折算，奖励是额外给的
            parts.append("零失误，额外 +%d 分完美奖励" % scoring.perfect_bonus(self.level))
        else:
            parts.append("得分 = %d × %d ÷ %d" % (scoring.base_score(self.level),
                                                self.board.hp_left, self.board.max_hp))
        if self.score_gain > 0:
            parts.append("刷新纪录 +%d" % self.score_gain)
        parts.append("总分 %d/%d" % (self.progress.total_score(TOTAL_LEVELS),
                                    scoring.total_max_score(LEVELS)))
        # 用普通空格而不是全角空格做分隔：这句本来就贴着面板宽度上限，
        # 每个全角空格要多吃 13 像素，三个加起来就会把它挤到第二行去。
        return (" · ".join(parts),
                config.COLOR_SUCCESS if self.score_perfect else config.COLOR_PANEL_TEXT_DIM)

    # ---------------------------------------------------------------- 提示气泡
    def toast_position(self):
        """提示气泡的位置：尽量别压在玩家正在看的地方。

        - 关卡总览：靠底部，避开那一排关卡卡片；
        - 关卡里：贴着顶栏下沿。棋盘是满屏的，哪里都会盖住一点，
          但顶栏下面那条带子离玩家的视线中心最远，挡住的也通常是最上一排箭头；
        - 其余（主菜单 / 设置）：正中，本来就是静态界面。
        """
        if self.scene == SCENE_LEVELS:
            return (self.width // 2, self.height - 52)
        if self.scene == SCENE_PLAY:
            return (self.width // 2, config.HUD_HEIGHT + 34)
        return (self.width // 2, self.height // 2)

    def draw_toast(self):
        """提示气泡：深底浅字 + 一颗语义色小圆点。

        文字颜色**不用**调用方传进来的那个颜色——调用方传的是「这条提示是什么性质」
        （警告 / 成功 / 普通），那个颜色直接当文字色在日间主题下会是深灰压深底，
        基本看不见。所以统一用 COLOR_TOAST_TEXT，语义色改成左侧那颗小圆点，
        底色再深都读得清。
        """
        if self.toast_timer <= 0 or not self.toast_text:
            return
        alpha = min(1.0, self.toast_timer / 0.5)      # 最后 0.5 秒淡出
        image = ui.get_font(17, True).render(self.toast_text, True, config.COLOR_TOAST_TEXT)

        dot_r, gap, pad = 5, 12, 24
        pill = image.get_rect()
        pill.inflate_ip(pad * 2 + dot_r * 2 + gap, 26)
        pill.center = self.toast_position()
        # 气泡可能比窗口还宽（例如那句「先通关第 N 关」），夹回画面内
        pill.left = max(8, min(pill.left, self.width - pill.width - 8))

        radius = pill.height // 2
        layer = pygame.Surface(pill.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, tuple(config.COLOR_TOAST_BG) + (int(238 * alpha),),
                         layer.get_rect(), border_radius=radius)
        pygame.draw.rect(layer, tuple(config.COLOR_TOAST_EDGE) + (int(210 * alpha),),
                         layer.get_rect(), 2, border_radius=radius)
        pygame.draw.circle(layer, tuple(self.toast_color) + (int(240 * alpha),),
                           (pad + dot_r, pill.height // 2), dot_r)
        self.screen.blit(layer, pill.topleft)

        image.set_alpha(int(255 * alpha))
        self.screen.blit(image, image.get_rect(midleft=(pill.x + pad + dot_r * 2 + gap,
                                                        pill.centery)))
