# -*- coding: utf-8 -*-
"""游戏主体：场景状态机、事件分发、渲染与主循环。

场景（self.scene）：
    SCENE_MENU    开始界面：标题、玩法说明、进度、开始 / 关卡总览 / 退出
    SCENE_LEVELS  关卡总览：全部关卡一览，未解锁的显示锁，点击会提示先通关哪一关
    SCENE_PLAY    游戏界面：顶部信息栏 + 棋盘 + 底部提示（教学关额外有逐步引导）

通关 / 失败以「结果面板」的形式叠加在游戏界面上（self.overlay），
面板关闭前不接受棋盘点击，避免误操作。
"""

import math

import pygame

from . import anim, config, ui
from .board import (CLICK_BLOCKED, CLICK_EMPTY, CLICK_FLY, STATE_CLEARED,
                    STATE_FAILED, STATE_PLAYING, Board)
from .levels import TOTAL_LEVELS, LEVELS
from .progress import Progress

SCENE_MENU = "menu"
SCENE_LEVELS = "levels"
SCENE_PLAY = "play"

OVERLAY_WIN = "win"
OVERLAY_FAIL = "fail"
OVERLAY_ALL_CLEAR = "allclear"

# ---------------------------------------------------------------- 关卡总览布局
CARD_COLUMNS = 4
CARD_WIDTH = 196
CARD_HEIGHT = 104
CARD_GAP_X = 20
CARD_GAP_Y = 14
CARDS_TOP = 142

TOAST_DURATION = 2.0        # 提示气泡停留时间（秒）


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
        self.board = None

        self.cell_size = 60
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

        # 教学关引导
        self.tutorial_index = 0
        self.tutorial_done = False

        # 提示气泡 / 二次确认
        self.toast_text = ""
        self.toast_color = config.COLOR_TEXT
        self.toast_timer = 0.0
        self.reset_armed = False

        self.time = 0.0

        self.background = ui.make_vertical_gradient(
            (self.width, self.height), config.COLOR_BG_TOP, config.COLOR_BG_BOTTOM
        )
        self.enter_menu()

    # ================================================================ 场景
    @property
    def level(self):
        return LEVELS[self.level_index]

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
        self.reset_armed = False
        self.animations.clear()
        self.floats.clear()
        # 提示气泡属于上一屏的上下文，换场景时一起清掉，
        # 免得「先通关第 N 关吧」这种提示跟着玩家进了关卡
        self.toast_text = ""
        self.toast_timer = 0.0

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
        """弹出一条短暂的提示（屏幕中央，自动淡出）。"""
        self.toast_text = text
        self.toast_color = color or config.COLOR_TEXT
        self.toast_timer = TOAST_DURATION

    # ------------------------------------------------------------ 关卡
    def start_level(self, index):
        """开始第 index 关（从 0 开始计数）。未解锁则拒绝并提示。"""
        if not 0 <= index < TOTAL_LEVELS:
            return False
        if not self.is_unlocked(index):
            self.show_toast("先通关第 %d 关「%s」才能解锁本关"
                            % (index, LEVELS[index - 1].name), config.COLOR_WARN)
            return False

        self.level_index = index
        self.board = Board(self.level)
        self.scene = SCENE_PLAY
        self.reset_common()
        self.tutorial_index = 0
        self.tutorial_done = not self.level.tutorial
        self.layout_board()
        self.buttons = self.make_play_buttons()
        self.sync_tutorial()
        return True

    def next_level(self):
        if self.level_index + 1 < TOTAL_LEVELS:
            self.start_level(self.level_index + 1)
        else:
            self.enter_levels()

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
        self.tutorial_index = 0
        self.tutorial_done = not self.level.tutorial
        self.buttons = self.make_play_buttons()
        self.sync_tutorial()
        self.floats.append(anim.FloatingText(
            "已重新开始", (self.board_rect.centerx, self.board_rect.centery),
            config.COLOR_ACCENT, size=26, duration=1.0, rise=24))

    # ================================================================ 教学引导
    def sync_tutorial(self):
        """让引导步骤与棋盘的实际状态对齐。

        玩家完全可能不按提示点（甚至提前把后面的箭头消掉），
        所以每一步在展示前都要检查一次：目标格子还在吗？这一步还成立吗？
        不成立就直接跳过，避免出现「让你点一个已经飞走的箭头」这种尴尬。
        """
        if not self.level.tutorial or self.board is None:
            return
        steps = self.level.steps
        while self.tutorial_index < len(steps):
            step = steps[self.tutorial_index]
            if self.board.arrow_at(step.row, step.col) is None:
                self.tutorial_index += 1        # 目标已经飞走了
                continue
            if step.expect == "blocked" and self.board.can_fly(step.row, step.col):
                self.tutorial_index += 1        # 已经没有阻挡了，这一步失去意义
                continue
            break
        self.tutorial_done = self.tutorial_index >= len(steps)

    def advance_tutorial(self, result, row, col):
        """某一步被正确完成后，推进到下一步。"""
        if not self.level.tutorial or self.tutorial_done:
            return
        step = self.current_step
        if step is None:
            return
        if (row, col) == (step.row, step.col) and result.kind == step.expect:
            self.tutorial_index += 1
        self.sync_tutorial()

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
            config.CELL_MAX_SIDE,          # 小棋盘不要把格子撑得太大
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

    def make_card_rects(self):
        """关卡总览里每张卡片的矩形（按行列自动排布）。"""
        total_width = CARD_COLUMNS * CARD_WIDTH + (CARD_COLUMNS - 1) * CARD_GAP_X
        left = (self.width - total_width) // 2
        rects = []
        for index in range(TOTAL_LEVELS):
            row, col = divmod(index, CARD_COLUMNS)
            rects.append(pygame.Rect(
                left + col * (CARD_WIDTH + CARD_GAP_X),
                CARDS_TOP + row * (CARD_HEIGHT + CARD_GAP_Y),
                CARD_WIDTH, CARD_HEIGHT,
            ))
        return rects

    @property
    def panel_rect(self):
        panel = pygame.Rect(0, 0, 560, 340)
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
        center_x = self.width // 2
        buttons = [
            ui.Button((center_x - 160, 506, 320, 56), self.primary_label,
                      self.primary_action, "primary", size=24),
            ui.Button((center_x - 222, 578, 204, 46), "关卡总览",
                      self.enter_levels, "ghost", size=18),
            ui.Button((center_x + 18, 578, 204, 46), "退出游戏",
                      self.quit, "ghost", size=18),
        ]
        return buttons

    def make_levels_buttons(self):
        buttons = [
            ui.Button((self.width - 190, 40, 152, 42), "返回主菜单",
                      self.enter_menu, "ghost", size=16),
            ui.Button((self.width - 190, 92, 152, 42),
                      "确认清空？" if self.reset_armed else "清空进度",
                      self.toggle_reset_progress, "ghost", size=16),
            ui.Button((self.width // 2 - 170, 506, 340, 52),
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
        return [
            ui.Button((604, 30, 104, 42), "关卡总览", self.enter_levels, "ghost", size=13),
            ui.Button((716, 30, 104, 42), "返回主菜单", self.enter_menu, "ghost", size=13),
            ui.Button((828, 30, 104, 42), "重新开始", self.restart_level, "primary", size=15),
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
            add_secondary([("重玩本关", self.restart_level),
                           ("关卡总览", self.enter_levels),
                           ("返回主菜单", self.enter_menu)])
        elif self.overlay == OVERLAY_FAIL:
            buttons.append(ui.Button((panel.centerx - 140, panel.y + 216, 280, 54),
                                     "重新开始本关", self.restart_level, "primary", size=22))
            add_secondary([("关卡总览", self.enter_levels),
                           ("返回主菜单", self.enter_menu)])
        else:
            buttons.append(ui.Button((panel.centerx - 140, panel.y + 216, 280, 54),
                                     "查看关卡总览", self.enter_levels, "success", size=22))
            add_secondary([("重玩第 1 关", lambda: self.start_level(0)),
                           ("返回主菜单", self.enter_menu)])

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
            if self.scene == SCENE_MENU and self.overlay is None:
                self.running = False
            else:
                self.enter_menu()
        elif event.key == pygame.K_r and self.scene == SCENE_PLAY and self.overlay is None:
            self.restart_level()
        elif event.key == pygame.K_SPACE and self.overlay is None:
            if self.scene in (SCENE_MENU, SCENE_LEVELS):
                self.primary_action()

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

        self.advance_tutorial(result, row, col)
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
        self.time += dt
        for effect in list(self.animations):
            if effect.update(dt):
                self.animations.remove(effect)
        for item in list(self.floats):
            if item.update(dt):
                self.floats.remove(item)

        if self.toast_timer > 0:
            self.toast_timer = max(0.0, self.toast_timer - dt)

        if self.scene == SCENE_PLAY and self.board is not None and self.overlay is None:
            if self.board.state in (STATE_CLEARED, STATE_FAILED):
                # 等飞行动画播完再弹结果面板
                self.overlay_timer += dt
                if self.overlay_timer >= config.RESULT_DELAY:
                    self.show_result()
        return None

    def show_result(self):
        if self.board.state == STATE_CLEARED:
            self.progress.mark_cleared(self.level_index)      # 记进度 + 解锁下一关
            if self.level_index >= TOTAL_LEVELS - 1:
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
        ui.draw_text(self.screen, "一箭又一箭", (center_x, 72),
                     size=56, bold=True, anchor="center")
        ui.draw_text(self.screen, "点击箭头，让它飞出棋盘", (center_x, 118),
                     size=19, color=config.COLOR_TEXT_DIM, anchor="center")

        # 进度一行
        cleared = self.progress.cleared_count(TOTAL_LEVELS)
        if cleared >= TOTAL_LEVELS:
            progress_text = "已通关全部 %d 关，随时可以重玩" % TOTAL_LEVELS
        elif cleared == 0:
            progress_text = "还没开始 · 共 %d 关，第一次玩建议先走一遍教学关" % TOTAL_LEVELS
        else:
            progress_text = "已通关 %d / %d 关 · 下一关是第 %d 关「%s」" % (
                cleared, TOTAL_LEVELS, self.next_level_index() + 1,
                LEVELS[self.next_level_index()].name)
        ui.draw_text(self.screen, progress_text, (center_x, 150),
                     size=15, color=config.COLOR_TEXT_FAINT, anchor="center")

        self.draw_rules_card()

        ui.draw_text(self.screen, "按空格键可以直接开始（或继续）；Esc 退出游戏",
                     (center_x, 656), size=13, color=config.COLOR_TEXT_FAINT, anchor="center")

    def draw_rules_card(self):
        """主界面的玩法说明卡片：文字规则 + 两组迷你棋盘示例。"""
        card = pygame.Rect(120, 178, self.width - 240, 308)
        ui.draw_round_rect(self.screen, card, config.COLOR_PANEL, radius=18)
        ui.draw_round_rect(self.screen, card, config.COLOR_PANEL_EDGE, radius=18, width=2)

        ui.draw_text(self.screen, "玩法说明", (card.x + 22, card.y + 16),
                     size=20, bold=True)

        rules = [
            "① 点一下箭头，它就沿着自己的方向飞出棋盘并被消除。",
            "② 如果它前方还有别的箭头挡路，就飞不出去，并且扣掉 1 次失误。",
            "③ 清空本关所有箭头即可通关；失误次数用完本关失败，可以重新开始。",
            "④ 通关一关才会解锁下一关，进度会自动保存。",
        ]
        for index, line in enumerate(rules):
            ui.draw_text(self.screen, line, (card.x + 22, card.y + 48 + index * 25),
                         size=15, color=config.COLOR_TEXT_DIM)

        # 示例区：两种情形上下对照
        demo_y = card.y + 158
        divider = card.y + 150
        pygame.draw.line(self.screen, config.COLOR_PANEL_EDGE,
                         (card.x + 22, divider), (card.right - 22, divider), 1)

        self.draw_demo_row(card.x + 24, demo_y, (">", "v", ".", "."),
                           "「>」前方有箭头挡路 → 飞不出去，扣 1 次失误",
                           config.COLOR_DANGER)
        self.draw_demo_row(card.x + 24, demo_y + 56, (">", ".", ".", "."),
                           "「>」前方一路是空的 → 飞出棋盘并消失",
                           config.COLOR_SUCCESS)

        ui.draw_text(self.screen, "把鼠标放在箭头上，还能看到它前方的路径：绿色=畅通，红色=被挡。",
                     (card.x + 24, card.bottom - 28), size=13,
                     color=config.COLOR_TEXT_FAINT)

    def draw_demo_row(self, x, y, cells, caption, color):
        """画一行迷你棋盘（用于玩法说明里的示例）。"""
        side, gap = 30, 6
        for index, char in enumerate(cells):
            rect = pygame.Rect(x + index * (side + gap), y, side, side)
            ui.draw_round_rect(self.screen, rect, config.COLOR_CELL, radius=7)
            edge = color if (index == 0 or char != ".") else config.COLOR_CELL_EDGE
            pygame.draw.rect(self.screen, edge, rect, 2, border_radius=7)
            if char != ".":
                direction = {">": "right", "<": "left", "^": "up", "v": "down"}[char]
                ui.draw_arrow(self.screen, rect.center, side * config.ARROW_RATIO, direction)

        text_x = x + len(cells) * (side + gap) + 14
        ui.draw_text(self.screen, caption, (text_x, y + side // 2), size=15,
                     color=color, anchor="midleft")

    # ---------------------------------------------------------------- 关卡总览
    def draw_levels(self):
        ui.draw_text(self.screen, "关卡总览", (58, 44), size=34, bold=True)

        cleared = self.progress.cleared_count(TOTAL_LEVELS)
        unlocked = self.progress.highest_unlocked(TOTAL_LEVELS)
        ui.draw_text(self.screen,
                     "已通关 %d / %d 关　·　已解锁到第 %d 关　·　进度自动保存"
                     % (cleared, TOTAL_LEVELS, unlocked + 1),
                     (58, 92), size=15, color=config.COLOR_TEXT_FAINT)

        for index, rect in enumerate(self.card_rects):
            self.draw_level_card(rect, index)

        ui.draw_text(self.screen,
                     "点击卡片开始挑战；带锁的关卡需要先通关它前面的一关。",
                     (self.width // 2, 574), size=14,
                     color=config.COLOR_TEXT_FAINT, anchor="center")
        ui.draw_text(self.screen, "Esc 返回主菜单　　空格 继续挑战",
                     (self.width // 2, 620), size=13,
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
        ui.draw_text(self.screen, "%02d" % (index + 1), (rect.x + 14, rect.y + 10),
                     size=22, bold=True,
                     color=config.COLOR_TEXT_DIM if unlocked else config.COLOR_TEXT_FAINT)

        # 名称
        ui.draw_text(self.screen, level.name, (rect.x + 14, rect.y + 40),
                     size=18, bold=True, color=title_color)

        # 规格
        ui.draw_text(self.screen, "%d×%d · %d 支箭头" % (level.rows, level.cols,
                                                        level.arrow_count),
                     (rect.x + 14, rect.y + 64), size=12,
                     color=config.COLOR_TEXT_FAINT)

        # 状态
        if not unlocked:
            status, status_color = "未解锁", config.COLOR_TEXT_FAINT
        elif cleared:
            status, status_color = "已通关", config.COLOR_SUCCESS
        elif level.tutorial:
            status, status_color = "教学关 · 建议先玩", config.COLOR_TUTORIAL
        else:
            status, status_color = "可挑战", config.COLOR_ACCENT
        ui.draw_text(self.screen, status, (rect.x + 14, rect.y + 82), size=13,
                     color=status_color)

        # 右上角：锁 / 星星 / 对勾
        if not unlocked:
            ui.draw_lock(self.screen, (rect.right - 26, rect.y + 26), 18)
        else:
            ui.draw_stars(self.screen, (rect.right - 14, rect.y + 22),
                          level.stars, total=5, radius=6, gap=3)
            if cleared:
                ui.draw_check(self.screen, (rect.right - 24, rect.y + 82), 18)

    # ---------------------------------------------------------------- 游戏界面
    def draw_play(self):
        self.draw_hud()
        self.draw_board()
        for effect in self.animations:
            effect.draw(self.screen)
        for item in self.floats:
            item.draw(self.screen)
        self.draw_tutorial_bar()
        self.draw_footer()

    def draw_hud(self):
        hud = pygame.Rect(0, 0, self.width, config.HUD_HEIGHT)
        ui.draw_round_rect(self.screen, hud, config.COLOR_HUD, radius=0)
        pygame.draw.line(self.screen, config.COLOR_HUD_LINE,
                         (0, config.HUD_HEIGHT - 1), (self.width, config.HUD_HEIGHT - 1))

        ui.draw_text(self.screen, "第 %d / %d 关" % (self.level_index + 1, TOTAL_LEVELS),
                     (40, 22), size=24, bold=True)
        ui.draw_text(self.screen, self.level.name, (40, 58), size=17,
                     color=config.COLOR_TEXT_DIM)

        # 剩余箭头
        ui.draw_text(self.screen, "剩余箭头", (300, 26), size=15, color=config.COLOR_TEXT_DIM)
        ui.draw_text(self.screen, str(self.board.remaining), (300, 46),
                     size=32, color=config.COLOR_ACCENT, bold=True)

        # 剩余失误：实心圆 = 还能错几次，空心红圈 = 已经用掉的
        ui.draw_text(self.screen, "剩余失误", (420, 24), size=15, color=config.COLOR_TEXT_DIM)
        left = self.board.mistakes_left
        step = 28
        for index in range(self.board.max_mistakes):
            center = (420 + 8 + index * step, 66)
            if index < left:
                color = config.COLOR_SUCCESS if left > 1 else config.COLOR_WARN
                pygame.draw.circle(self.screen, color, center, 8)
            else:
                pygame.draw.circle(self.screen, config.COLOR_DANGER, center, 8, 3)
        counter_x = 420 + self.board.max_mistakes * step + 6
        ui.draw_text(self.screen, "%d / %d" % (left, self.board.max_mistakes),
                     (counter_x, 66), size=18, color=config.COLOR_TEXT_DIM,
                     anchor="midleft")

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

        step = self.current_step
        pulse = self.tutorial_pulse()

        for row in range(rows):
            for col in range(cols):
                rect = self.cell_rect(row, col)
                arrow = self.board.arrow_at(row, col)
                base = config.COLOR_CELL_USED if arrow is not None else config.COLOR_CELL

                ui.draw_round_rect(self.screen, rect, base, radius=config.CELL_RADIUS)
                if (row, col) in path_cells:
                    ui.draw_round_rect_alpha(self.screen, rect, path_color, 48,
                                             radius=config.CELL_RADIUS)
                # 教学关目标格子的底色：画在箭头下面，免得把箭头压暗
                if step is not None and (row, col) == (step.row, step.col):
                    ui.draw_round_rect_alpha(self.screen, rect, config.COLOR_TUTORIAL,
                                             int(28 + pulse * 40), radius=config.CELL_RADIUS)

                edge = config.COLOR_CELL_EDGE
                if step is not None and (row, col) == (step.row, step.col):
                    edge = config.COLOR_TUTORIAL
                elif (row, col) == blocker_cell:
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

        # 教学关：给当前该点的箭头套一圈会呼吸的高亮环（画在最上层）
        if step is not None:
            self.draw_tutorial_ring(self.cell_rect(step.row, step.col), pulse)

    def tutorial_pulse(self):
        """0~1 的呼吸系数，用于教学关高亮的闪烁节奏。"""
        return 0.5 + 0.5 * math.sin(self.time * 4.0)

    def draw_tutorial_ring(self, rect, pulse):
        """教学关的目标格子高亮环，用正弦做呼吸效果，吸引注意力。"""
        grow = int(4 + pulse * 6)
        ring = rect.inflate(grow * 2, grow * 2)
        alpha = int(120 + pulse * 110)
        ui.draw_round_rect_alpha(self.screen, ring, config.COLOR_TUTORIAL, alpha,
                                 radius=config.CELL_RADIUS + grow, width=3)

    def draw_tutorial_bar(self):
        """教学关底部的讲解条：这一步该点哪里、为什么。"""
        step = self.current_step
        if step is None:
            return
        bar = pygame.Rect(40, self.height - 112, self.width - 80, 56)
        ui.draw_round_rect(self.screen, bar, config.COLOR_TUTORIAL_BAR, radius=14)
        ui.draw_round_rect(self.screen, bar, config.COLOR_TUTORIAL_BAR_EDGE,
                           radius=14, width=2)

        total = len(self.level.steps)
        ui.draw_text(self.screen, "教学 %d / %d" % (self.tutorial_index + 1, total),
                     (bar.right - 18, bar.centery), size=15,
                     color=config.COLOR_TUTORIAL, bold=True, anchor="midright")

        text_area = pygame.Rect(bar.x + 18, bar.y + 10, bar.width - 150, bar.height - 20)
        ui.draw_paragraph(self.screen, step.text, text_area, size=15,
                          color=config.COLOR_TEXT, line_gap=2)

    def draw_footer(self):
        hint = self.level.hint
        if self.current_step is not None:
            hint = "跟着黄色高亮环点就行，点错了也不会失败"
        ui.draw_text(self.screen, "提示：" + hint,
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
            desc = "%d 个关卡的箭头都被你清理干净了" % TOTAL_LEVELS

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

    # ---------------------------------------------------------------- 提示气泡
    def toast_position(self):
        """提示气泡的位置：关卡总览里靠底部，避免挡住那一排关卡卡片。"""
        if self.scene == SCENE_LEVELS:
            return (self.width // 2, self.height - 52)
        return (self.width // 2, self.height // 2)

    def draw_toast(self):
        if self.toast_timer <= 0 or not self.toast_text:
            return
        alpha = min(1.0, self.toast_timer / 0.5)      # 最后 0.5 秒淡出
        image = ui.get_font(18, True).render(self.toast_text, True, self.toast_color)
        pill = image.get_rect()
        pill.inflate_ip(48, 26)
        pill.center = self.toast_position()

        layer = pygame.Surface(pill.size, pygame.SRCALPHA)
        pygame.draw.rect(layer, tuple(config.COLOR_MASK) + (int(235 * alpha),),
                         layer.get_rect(), border_radius=pill.height // 2)
        pygame.draw.rect(layer, tuple(config.COLOR_PANEL_EDGE) + (int(255 * alpha),),
                         layer.get_rect(), 2, border_radius=pill.height // 2)
        self.screen.blit(layer, pill.topleft)

        image.set_alpha(int(255 * alpha))
        self.screen.blit(image, image.get_rect(center=pill.center))
