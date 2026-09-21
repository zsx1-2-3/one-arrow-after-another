# -*- coding: utf-8 -*-
"""游戏主体：场景状态机、事件分发、渲染与主循环。

场景（self.scene）：
    SCENE_MENU  开始界面：标题、关卡选择、退出
    SCENE_PLAY  游戏界面：顶部信息栏 + 棋盘 + 底部提示

通关 / 失败以「结果面板」的形式叠加在游戏界面上（self.overlay），
面板关闭前不接受棋盘点击，避免误操作。
"""

import pygame

from . import anim, config, ui
from .board import (CLICK_BLOCKED, CLICK_EMPTY, CLICK_FLY, STATE_CLEARED,
                    STATE_FAILED, STATE_PLAYING, Board)
from .levels import LEVELS

SCENE_MENU = "menu"
SCENE_PLAY = "play"

OVERLAY_WIN = "win"
OVERLAY_FAIL = "fail"
OVERLAY_ALL_CLEAR = "allclear"


class Game:
    """整个游戏的状态与渲染。"""

    def __init__(self, screen):
        self.screen = screen
        self.width, self.height = screen.get_size()
        self.running = True

        self.scene = SCENE_MENU
        self.level_index = 0
        self.board = None

        self.cell_size = 60
        self.board_rect = pygame.Rect(0, 0, 0, 0)
        self.animations = []
        self.floats = []
        self.buttons = []
        self.overlay = None
        self.overlay_timer = 0.0
        self.mouse_pos = (-1, -1)
        self.hover_cell = None

        self.background = ui.make_vertical_gradient(
            (self.width, self.height), config.COLOR_BG_TOP, config.COLOR_BG_BOTTOM
        )
        self.enter_menu()

    # ================================================================ 场景
    @property
    def level(self):
        return LEVELS[self.level_index]

    def enter_menu(self):
        """回到开始界面。"""
        self.scene = SCENE_MENU
        self.board = None
        self.overlay = None
        self.overlay_timer = 0.0
        self.hover_cell = None
        self.animations.clear()
        self.floats.clear()
        self.buttons = self.make_menu_buttons()

    def start_level(self, index):
        """开始第 index 关（从 0 开始计数）。"""
        self.level_index = max(0, min(index, len(LEVELS) - 1))
        self.board = Board(self.level)
        self.scene = SCENE_PLAY
        self.overlay = None
        self.overlay_timer = 0.0
        self.hover_cell = None
        self.animations.clear()
        self.floats.clear()
        self.layout_board()
        self.buttons = self.make_play_buttons()

    def next_level(self):
        self.start_level(self.level_index + 1)

    def restart_level(self):
        """把当前关卡恢复到初始状态（重新开始按钮 / R 键）。"""
        if self.board is None:
            return
        self.board.reset()
        self.overlay = None
        self.overlay_timer = 0.0
        self.hover_cell = None
        self.animations.clear()
        self.floats.clear()
        self.buttons = self.make_play_buttons()
        self.floats.append(anim.FloatingText(
            "已重新开始", (self.board_rect.centerx, self.board_rect.centery),
            config.COLOR_ACCENT, size=26, duration=1.0, rise=24))

    # ================================================================ 布局
    def layout_board(self):
        """根据关卡尺寸计算单元格边长与棋盘矩形（居中显示）。"""
        rows, cols = self.board.rows, self.board.cols
        gap = config.CELL_GAP
        area = pygame.Rect(
            config.BOARD_MARGIN_X,
            config.HUD_HEIGHT + config.BOARD_MARGIN_Y,
            self.width - config.BOARD_MARGIN_X * 2,
            self.height - config.HUD_HEIGHT - config.FOOTER_HEIGHT - config.BOARD_MARGIN_Y * 2,
        )
        size = min(
            (area.width - gap * (cols - 1)) / cols,
            (area.height - gap * (rows - 1)) / rows,
            config.BOARD_MAX_SIDE / max(rows, cols),
        )
        self.cell_size = int(size)
        grid_w = self.cell_size * cols + gap * (cols - 1)
        grid_h = self.cell_size * rows + gap * (rows - 1)
        self.board_rect = pygame.Rect(0, 0, grid_w, grid_h)
        self.board_rect.center = area.center

    def cell_rect(self, row, col):
        step = self.cell_size + config.CELL_GAP
        x = self.board_rect.x + col * step
        y = self.board_rect.y + row * step
        return pygame.Rect(int(x), int(y), self.cell_size, self.cell_size)

    def cell_at_pos(self, pos):
        """把屏幕坐标换算成棋盘坐标，落在空隙或界外返回 None。"""
        if self.board is None or not self.board_rect.collidepoint(pos):
            return None
        step = self.cell_size + config.CELL_GAP
        col = int((pos[0] - self.board_rect.x) // step)
        row = int((pos[1] - self.board_rect.y) // step)
        if not (0 <= row < self.board.rows and 0 <= col < self.board.cols):
            return None
        if not self.cell_rect(row, col).collidepoint(pos):
            return None          # 点在了单元格之间的缝隙上
        return row, col

    @property
    def panel_rect(self):
        panel = pygame.Rect(0, 0, 560, 340)
        panel.center = (self.width // 2, self.height // 2)
        return panel

    # ================================================================ 按钮
    def make_menu_buttons(self):
        center_x = self.width // 2
        buttons = [
            ui.Button((center_x - 150, 322, 300, 62), "开始游戏",
                      lambda: self.start_level(0), "primary", size=26)
        ]

        width, height, gap = 150, 94, 18
        total = len(LEVELS) * width + (len(LEVELS) - 1) * gap
        left = center_x - total // 2
        for index, level in enumerate(LEVELS):
            buttons.append(ui.Button(
                (left + index * (width + gap), 430, width, height),
                "第 %d 关" % (index + 1),
                (lambda i=index: self.start_level(i)),   # 默认参数避免闭包陷阱
                "level", size=20, sub=level.name))

        buttons.append(ui.Button((center_x - 80, 566, 160, 44), "退出游戏",
                                 self.quit, "ghost", size=18))
        return buttons

    def make_play_buttons(self):
        return [
            ui.Button((626, 30, 124, 42), "返回主菜单", self.enter_menu, "ghost", size=16),
            ui.Button((764, 30, 156, 42), "重新开始", self.restart_level, "primary", size=18),
        ]

    def make_overlay_buttons(self):
        panel = self.panel_rect
        buttons = []

        def add_secondary(items):
            width, height, gap = 136, 40, 12
            total = len(items) * width + (len(items) - 1) * gap
            left = panel.centerx - total // 2
            for index, (label, action) in enumerate(items):
                buttons.append(ui.Button(
                    (left + index * (width + gap), panel.y + 282, width, height),
                    label, action, "ghost", size=16))

        if self.overlay == OVERLAY_WIN:
            buttons.append(ui.Button((panel.centerx - 140, panel.y + 216, 280, 54),
                                     "下一关", self.next_level, "success", size=22))
            add_secondary([("重玩本关", self.restart_level), ("返回主菜单", self.enter_menu)])
        elif self.overlay == OVERLAY_FAIL:
            buttons.append(ui.Button((panel.centerx - 140, panel.y + 216, 280, 54),
                                     "重新开始本关", self.restart_level, "primary", size=22))
            add_secondary([("返回主菜单", self.enter_menu)])
        else:
            buttons.append(ui.Button((panel.centerx - 140, panel.y + 216, 280, 54),
                                     "再玩一遍", lambda: self.start_level(0), "success", size=22))
            add_secondary([("返回主菜单", self.enter_menu)])

        for button in buttons:
            button.hovered = button.hit(self.mouse_pos)
        return buttons

    def quit(self):
        self.running = False

    # ================================================================ 交互
    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.running = False
        elif event.type == pygame.MOUSEMOTION:
            self.mouse_pos = event.pos
            self.update_hover()
            for button in self.buttons:
                button.hovered = button.hit(event.pos)
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.handle_click(event.pos)
        elif event.type == pygame.KEYDOWN:
            self.handle_key(event)

    def update_hover(self):
        self.hover_cell = None
        if self.scene == SCENE_PLAY and self.overlay is None:
            self.hover_cell = self.cell_at_pos(self.mouse_pos)

    def handle_click(self, pos):
        for button in self.buttons:
            if button.hit(pos):
                if button.on_click:
                    button.on_click()
                return
        if self.scene == SCENE_PLAY and self.overlay is None:
            cell = self.cell_at_pos(pos)
            if cell is not None:
                self.click_cell(cell[0], cell[1])

    def handle_key(self, event):
        if event.key == pygame.K_ESCAPE:
            if self.scene == SCENE_PLAY or self.overlay is not None:
                self.enter_menu()
            else:
                self.running = False
        elif event.key == pygame.K_r and self.scene == SCENE_PLAY and self.overlay is None:
            self.restart_level()
        elif event.key == pygame.K_SPACE and self.scene == SCENE_MENU:
            self.start_level(0)

    def click_cell(self, row, col):
        """点击棋盘上的一个格子，返回 ClickResult（供测试脚本直接调用）。"""
        if self.board is None or self.overlay is not None:
            return None
        result = self.board.click(row, col)
        if result is None:
            return None

        rect = self.cell_rect(row, col)
        if result.kind == CLICK_FLY:
            self.animations.append(anim.FlyOut(result.arrow, rect,
                                               self.fly_travel(rect, result.arrow.direction)))
        elif result.kind == CLICK_BLOCKED:
            self.animations.append(anim.Impact(result.arrow, rect))
            self.floats.append(anim.FloatingText(
                "被挡住了 -1 失误", (rect.centerx, rect.top - 2),
                config.COLOR_DANGER, size=20, duration=1.0, rise=44))
        elif result.kind == CLICK_EMPTY:
            self.floats.append(anim.FloatingText(
                "这里没有箭头", (rect.centerx, rect.centery - 18),
                config.COLOR_TEXT_FAINT, size=17, duration=0.7, rise=22))
        return result

    def fly_travel(self, cell_rect, direction):
        """箭头要飞多远才能完全离开棋盘区域。"""
        margin = cell_rect.width * config.FLY_MARGIN_RATIO
        if direction == "right":
            return self.board_rect.right - cell_rect.centerx + margin
        if direction == "left":
            return cell_rect.centerx - self.board_rect.left + margin
        if direction == "down":
            return self.board_rect.bottom - cell_rect.centery + margin
        return cell_rect.centery - self.board_rect.top + margin

    # ================================================================ 更新
    def update(self, dt):
        for effect in list(self.animations):
            if effect.update(dt):
                self.animations.remove(effect)
        for item in list(self.floats):
            if item.update(dt):
                self.floats.remove(item)

        if self.scene == SCENE_PLAY and self.board is not None and self.overlay is None:
            if self.board.state in (STATE_CLEARED, STATE_FAILED):
                # 等飞行动画播完再弹结果面板
                self.overlay_timer += dt
                if self.overlay_timer >= config.RESULT_DELAY:
                    self.show_result()
        return None

    def show_result(self):
        if self.board.state == STATE_CLEARED:
            if self.level_index >= len(LEVELS) - 1:
                self.overlay = OVERLAY_ALL_CLEAR
            else:
                self.overlay = OVERLAY_WIN
        else:
            self.overlay = OVERLAY_FAIL
        self.buttons = self.make_overlay_buttons()

    # ================================================================ 渲染
    def draw(self):
        self.screen.blit(self.background, (0, 0))
        if self.scene == SCENE_MENU:
            self.draw_menu()
        else:
            self.draw_play()
            if self.overlay is not None:
                self.draw_overlay()
        for button in self.buttons:
            button.draw(self.screen)

    # ---------------------------------------------------------------- 开始界面
    def draw_menu(self):
        center_x = self.width // 2
        ui.draw_text(self.screen, "一箭又一箭", (center_x, 116),
                     size=72, bold=True, anchor="center")
        ui.draw_text(self.screen, "点击箭头，让它飞出棋盘", (center_x, 180),
                     size=22, color=config.COLOR_TEXT_DIM, anchor="center")

        demo = ["up", "right", "down", "left"]
        start_x = center_x - (len(demo) - 1) * 40
        for index, direction in enumerate(demo):
            ui.draw_arrow(self.screen, (start_x + index * 80, 252), 46, direction)

        ui.draw_text(self.screen, "选一个关卡开始，或者直接点「开始游戏」", (center_x, 396),
                     size=16, color=config.COLOR_TEXT_FAINT, anchor="center")

        rules = [
            "玩法：点击箭头 —— 前进方向上没有其它箭头时，它会飞出棋盘并被消除",
            "被挡住时箭头不会消失，并且消耗一次失误机会；失误用尽本关失败",
            "清空本关全部箭头即可进入下一关",
        ]
        for index, line in enumerate(rules):
            ui.draw_text(self.screen, line, (center_x, 636 + index * 24),
                         size=15, color=config.COLOR_TEXT_FAINT, anchor="center")

    # ---------------------------------------------------------------- 游戏界面
    def draw_play(self):
        self.draw_hud()
        self.draw_board()
        for effect in self.animations:
            effect.draw(self.screen)
        for item in self.floats:
            item.draw(self.screen)
        self.draw_footer()

    def draw_hud(self):
        hud = pygame.Rect(0, 0, self.width, config.HUD_HEIGHT)
        ui.draw_round_rect(self.screen, hud, config.COLOR_HUD, radius=0)
        pygame.draw.line(self.screen, config.COLOR_HUD_LINE,
                         (0, config.HUD_HEIGHT - 1), (self.width, config.HUD_HEIGHT - 1))

        ui.draw_text(self.screen, "第 %d / %d 关" % (self.level_index + 1, len(LEVELS)),
                     (40, 22), size=24, bold=True)
        ui.draw_text(self.screen, self.level.name, (40, 58), size=17,
                     color=config.COLOR_TEXT_DIM)

        # 剩余箭头
        ui.draw_text(self.screen, "剩余箭头", (300, 26), size=15, color=config.COLOR_TEXT_DIM)
        ui.draw_text(self.screen, str(self.board.remaining), (300, 46),
                     size=32, color=config.COLOR_ACCENT, bold=True)

        # 剩余失误：实心圆 = 还能错几次，空心红圈 = 已经用掉的
        ui.draw_text(self.screen, "剩余失误", (420, 26), size=15, color=config.COLOR_TEXT_DIM)
        left = self.board.mistakes_left
        for index in range(self.board.max_mistakes):
            center = (432 + index * 30, 66)
            if index < left:
                color = config.COLOR_SUCCESS if left > 1 else config.COLOR_WARN
                pygame.draw.circle(self.screen, color, center, 9)
            else:
                pygame.draw.circle(self.screen, config.COLOR_DANGER, center, 9, 3)
        ui.draw_text(self.screen, "%d / %d" % (left, self.board.max_mistakes),
                     (432 + self.board.max_mistakes * 30 + 8, 57), size=18,
                     color=config.COLOR_TEXT_DIM)

    def draw_board(self):
        rows, cols = self.board.rows, self.board.cols

        # 悬停时高亮该箭头的前进路径：绿色=畅通，红色=被挡
        path_cells = set()
        blocker_cell = None
        path_color = config.COLOR_SUCCESS
        if (self.hover_cell is not None and self.board.state == STATE_PLAYING
                and self.board.arrow_at(*self.hover_cell) is not None):
            path = self.board.path_cells(*self.hover_cell)
            blocker = self.board.find_blocker(*self.hover_cell)
            if blocker is not None:
                path_color = config.COLOR_DANGER
                blocker_cell = (blocker.row, blocker.col)
                # 只高亮到挡路的那个箭头为止，挡路之后的路段没有意义
                path = path[:path.index(blocker_cell) + 1]
            path_cells = set(path)

        for row in range(rows):
            for col in range(cols):
                rect = self.cell_rect(row, col)
                arrow = self.board.arrow_at(row, col)
                base = config.COLOR_CELL_USED if arrow is not None else config.COLOR_CELL

                ui.draw_round_rect(self.screen, rect, base, radius=config.CELL_RADIUS)
                if (row, col) in path_cells:
                    ui.draw_round_rect_alpha(self.screen, rect, path_color, 48,
                                             radius=config.CELL_RADIUS)
                edge = config.COLOR_CELL_EDGE
                if (row, col) == blocker_cell:
                    edge = config.COLOR_DANGER
                elif arrow is not None and self.hover_cell == (row, col):
                    edge = config.COLOR_ACCENT
                pygame.draw.rect(self.screen, edge, rect, 2, border_radius=config.CELL_RADIUS)

                if arrow is not None:
                    ui.draw_arrow(self.screen, rect.center,
                                  rect.width * config.ARROW_RATIO, arrow.direction)

        # 棋盘外框
        pygame.draw.rect(self.screen, config.COLOR_CELL_EDGE,
                         self.board_rect.inflate(16, 16), 2, border_radius=16)

    def draw_footer(self):
        ui.draw_text(self.screen, "提示：" + self.level.hint,
                     (self.width // 2, self.height - 28), size=16,
                     color=config.COLOR_TEXT_FAINT, anchor="center")
        ui.draw_text(self.screen, "R 重开本关    Esc 返回主菜单",
                     (self.width - 32, self.height - 28), size=14,
                     color=config.COLOR_TEXT_FAINT, anchor="midright")

    # ---------------------------------------------------------------- 结果面板
    def draw_overlay(self):
        mask = pygame.Surface((self.width, self.height), pygame.SRCALPHA)
        mask.fill(tuple(config.COLOR_MASK) + (210,))
        self.screen.blit(mask, (0, 0))

        panel = self.panel_rect
        ui.draw_round_rect(self.screen, panel, config.COLOR_PANEL, radius=18)
        ui.draw_round_rect(self.screen, panel, config.COLOR_PANEL_EDGE, radius=18, width=2)

        if self.overlay == OVERLAY_WIN:
            title, color = "通关！", config.COLOR_SUCCESS
            desc = "第 %d 关「%s」的箭头全部飞出了棋盘" % (self.level_index + 1, self.level.name)
        elif self.overlay == OVERLAY_FAIL:
            title, color = "本关失败", config.COLOR_DANGER
            desc = "失误次数已经用完，再试一次吧"
        else:
            title, color = "全部通关！", config.COLOR_SUCCESS
            desc = "四个关卡的箭头都被你清理干净了"

        ui.draw_text(self.screen, title, (panel.centerx, panel.y + 58),
                     size=44, color=color, bold=True, anchor="center")
        ui.draw_text(self.screen, desc, (panel.centerx, panel.y + 106),
                     size=17, color=config.COLOR_TEXT_DIM, anchor="center")

        stats = [
            ("本关箭头", str(self.board.total)),
            ("点错次数", str(self.board.mistakes)),
            ("剩余失误", "%d / %d" % (self.board.mistakes_left, self.board.max_mistakes)),
        ]
        box_w, box_h, gap = 150, 64, 12
        total = len(stats) * box_w + (len(stats) - 1) * gap
        left = panel.centerx - total // 2
        for index, (label, value) in enumerate(stats):
            box = pygame.Rect(left + index * (box_w + gap), panel.y + 136, box_w, box_h)
            ui.draw_round_rect(self.screen, box, (40, 49, 76), radius=12)
            ui.draw_text(self.screen, label, (box.centerx, box.y + 16),
                         size=14, color=config.COLOR_TEXT_DIM, anchor="center")
            ui.draw_text(self.screen, value, (box.centerx, box.y + 44),
                         size=22, bold=True, anchor="center")
