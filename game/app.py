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

from . import anim, bgfx, config, ui
from .board import (CLICK_BLOCKED, CLICK_EMPTY, CLICK_FLY, STATE_CLEARED,
                    STATE_FAILED, STATE_PLAYING, Board)
from .levels import TOTAL_LEVELS, LEVELS
from .progress import Progress

# 场景常量定义在 config 里（背景模块也要用，避免循环依赖），这里只是转发一下
SCENE_MENU = config.SCENE_MENU
SCENE_LEVELS = config.SCENE_LEVELS
SCENE_PLAY = config.SCENE_PLAY

OVERLAY_WIN = "win"
OVERLAY_FAIL = "fail"
OVERLAY_ALL_CLEAR = "allclear"

# ---------------------------------------------------------------- 关卡总览布局
# 9 关正好排成 3 × 3；用 4 列的话会变成 4 + 4 + 1，最后一行孤零零一张卡。
CARD_COLUMNS = 3
CARD_WIDTH = 264
CARD_HEIGHT = 104
CARD_GAP_X = 20
CARD_GAP_Y = 14
CARDS_TOP = 142

TOAST_DURATION = 2.0        # 提示气泡停留时间（秒）
HP_FLASH_DURATION = 0.9     # 刚失去一颗心时，HUD 上那颗心的闪烁时长（秒）


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
        self._light_layer = None        # 棋盘柔光的缓存贴图（面板尺寸变化时重建）

        # 教学关引导
        self.tutorial_index = 0
        self.tutorial_done = False

        # 提示气泡 / 二次确认
        self.toast_text = ""
        self.toast_color = config.COLOR_TEXT
        self.toast_timer = 0.0
        self.reset_armed = False

        self.time = 0.0

        # 动态背景：漂移光晕 + 星点 + 偶发流星，按场景切换浓淡（见 bgfx.py）
        self.bg = bgfx.Background((self.width, self.height), SCENE_MENU)
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
        self.hp_lost_flash = 0.0
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
            # 扣生命值的提示是一颗「碎掉的像素心」，不是「失去一心」四个字：
            # 生命值本身就用心的形状表示，心碎的画面一看就懂，
            # 也不至于和「这里没有箭头」那句文字提示混成同一类消息。
            # 心形是 10 格宽的像素图，宽度取 10 的整数倍，每格才是整数像素（见 ui.heart_surface）
            self.floats.append(anim.FloatingHeart(
                (rect.centerx, rect.centery - rect.height * 0.08),
                color=config.COLOR_HP,
                size=max(20, int(round(min(rect.width, rect.height) * 0.58 / 10.0)) * 10),
                duration=1.15, rise=rect.height * 0.95))
            self.hp_lost_flash = 1.0        # 让刚失去的那颗心闪一下
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
            ("① 点一下箭头，它就沿着自己的方向飞出棋盘并被消除。", False),
            ("② 如果它前方还有别的箭头挡路，就飞不出去，并且失去", True),
            ("③ 清空本关所有箭头即可通关；生命值耗尽本关失败，可以重新开始。", False),
            ("④ 通关一关才会解锁下一关，进度会自动保存。", False),
        ]
        for index, (line, heart_icon) in enumerate(rules):
            rect = ui.draw_text(self.screen, line, (card.x + 22, card.y + 48 + index * 25),
                                size=15, color=config.COLOR_TEXT_DIM)
            if heart_icon:
                # 行尾直接画一颗像素心，而不是写「一心」两个字——
                # 生命值就是用这个图形表示的，文字说明也照同一个写法走
                self.draw_heart_icon(rect.right + 12, rect.centery)

        # 示例区：两种情形上下对照
        demo_y = card.y + 158
        divider = card.y + 150
        pygame.draw.line(self.screen, config.COLOR_PANEL_EDGE,
                         (card.x + 22, divider), (card.right - 22, divider), 1)

        self.draw_demo_row(card.x + 24, demo_y, (">", "v", ".", "."),
                           "「>」前方有箭头挡路 → 飞不出去，并且失去",
                           config.COLOR_DANGER, heart_icon=True)
        self.draw_demo_row(card.x + 24, demo_y + 56, (">", ".", ".", "."),
                           "「>」前方一路是空的 → 飞出棋盘并消失",
                           config.COLOR_SUCCESS)

        ui.draw_text(self.screen, "把鼠标放在箭头上，还能看到它前方的路径：绿色=畅通，红色=被挡。",
                     (card.x + 24, card.bottom - 28), size=13,
                     color=config.COLOR_TEXT_FAINT)

    def draw_heart_icon(self, center_x, center_y, size=20):
        """画一颗用作「生命值」字样的像素心（与 HUD、扣血动画同一套图形）。"""
        ui.draw_heart(self.screen, (center_x, center_y), size, config.COLOR_HP)

    def draw_demo_row(self, x, y, cells, caption, color, heart_icon=False):
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
        rect = ui.draw_text(self.screen, caption, (text_x, y + side // 2), size=15,
                            color=color, anchor="midleft")
        if heart_icon:
            self.draw_heart_icon(rect.right + 12, rect.centery)

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

        # 剩余生命值：实心像素心 = 还能错几次，只剩轮廓的 = 已经失去的那几颗
        ui.draw_text(self.screen, "剩余生命值", (420, 24), size=15, color=config.COLOR_TEXT_DIM)
        hp = self.board.hp_left
        # 心形是 10 格宽的像素图，宽度取 20 时每格正好 2 像素，缩放后粗细均匀
        heart_size, heart_gap = 20, 8
        # 刚失去的那颗心套一圈短暂的红色脉冲——点错时一眼看出是哪颗心没了
        if self.hp_lost_flash > 0.0 and hp < self.board.max_hp:
            center = (420 + heart_size / 2.0 + hp * (heart_size + heart_gap), 66)
            ui.draw_glow(self.screen, center, 22, (176, 56, 56),
                         self.hp_lost_flash, falloff=1.7)
        width = ui.draw_hearts(self.screen, (420, 66), hp, self.board.max_hp,
                               size=heart_size, gap=heart_gap)
        ui.draw_text(self.screen, "%d / %d" % (hp, self.board.max_hp),
                     (420 + width + 10, 66), size=18, color=config.COLOR_TEXT_DIM,
                     anchor="midleft")

    def draw_board(self):
        rows, cols = self.board.rows, self.board.cols

        # 棋盘底衬：整块圆角面板 + 面板内缓慢游动的柔光。
        # 原来只有一圈外框，棋盘区域是一片死板的深色，关卡里看着很单调。
        panel = self.board_rect.inflate(28, 28)
        ui.draw_round_rect(self.screen, panel, config.COLOR_BOARD_PANEL, radius=20)
        self.draw_board_light(panel)

        # 悬停时高亮该箭头的前进路径：绿色=畅通，红色=被挡
        path_cells = set()
        path_centers = []
        blocker_cell = None
        path_color = config.COLOR_PATH_OK
        if (self.hover_cell is not None and self.board.state == STATE_PLAYING
                and self.board.arrow_at(*self.hover_cell) is not None):
            path = self.board.path_cells(*self.hover_cell)
            blocker = self.board.find_blocker(*self.hover_cell)
            if blocker is not None:
                path_color = config.COLOR_PATH_BLOCK
                blocker_cell = (blocker.row, blocker.col)
                # 只高亮到挡路的那个箭头为止，挡路之后的路段没有意义
                path = path[:path.index(blocker_cell) + 1]
            path_cells = set(path)
            # 流光要沿着整条路径跑，所以带上起点（箭头自己所在的格子）
            path_centers = [self.cell_rect(*self.hover_cell).center]
            path_centers += [self.cell_rect(r, c).center for r, c in path]
            if blocker_cell is not None:
                path_centers.append(self.cell_rect(*blocker_cell).center)

        step = self.current_step
        pulse = self.tutorial_pulse()
        hover_pulse = 0.5 + 0.5 * math.sin(self.time * 5.2)

        for row in range(rows):
            for col in range(cols):
                rect = self.cell_rect(row, col)
                arrow = self.board.arrow_at(row, col)
                base = config.COLOR_CELL_USED if arrow is not None else config.COLOR_CELL

                ui.draw_round_rect(self.screen, rect, base, radius=config.CELL_RADIUS)
                if (row, col) in path_cells:
                    ui.draw_round_rect_alpha(self.screen, rect, path_color, 48,
                                             radius=config.CELL_RADIUS)
                # 教学关目标格子：用加法柔光提亮，而不是叠一层黄色底。
                # 叠底色会把下面那支箭头染成一片发闷的橄榄色（试过，很难看），
                # 加法光只是"打亮"这一格，箭头的颜色还是它自己的。
                # 光晕裁到格子范围内，否则会溢到相邻格子上、
                # 而且行优先绘制会让相邻格把它盖掉一半，出现半明半暗的怪相。
                if step is not None and (row, col) == (step.row, step.col):
                    clip_backup = self.screen.get_clip()
                    self.screen.set_clip(rect)
                    ui.draw_glow(self.screen, rect.center, int(rect.width * 0.78),
                                 (168, 122, 34), 0.30 + 0.34 * pulse, falloff=2.0)
                    self.screen.set_clip(clip_backup)

                edge = config.COLOR_CELL_EDGE
                if step is not None and (row, col) == (step.row, step.col):
                    edge = config.COLOR_TUTORIAL
                elif (row, col) == blocker_cell:
                    edge = config.COLOR_DANGER
                elif arrow is not None and self.hover_cell == (row, col):
                    # 悬停格的边框跟着呼吸，鼠标停哪儿一眼就能看到
                    edge = ui.mix_color(config.COLOR_CELL_EDGE, config.COLOR_HOVER_RING,
                                        0.55 + 0.45 * hover_pulse)
                pygame.draw.rect(self.screen, edge, rect, 2, border_radius=config.CELL_RADIUS)

                if arrow is not None:
                    side = rect.width * config.ARROW_RATIO
                    if self.hover_cell == (row, col):
                        side *= 1.0 + 0.06 * hover_pulse     # 悬停时轻轻放大一点
                    ui.draw_arrow(self.screen, rect.center, side, arrow.direction)

        # 悬停路径上的流光：一颗亮点从箭头出发跑到被挡处，循环播放
        if len(path_centers) > 1:
            self.draw_path_flow(path_centers, path_color)

        # 棋盘外框
        pygame.draw.rect(self.screen, config.COLOR_BOARD_PANEL_EDGE,
                         panel, 2, border_radius=20)

        # 教学关：给当前该点的箭头套一圈会呼吸的高亮环（画在最上层）
        if step is not None:
            self.draw_tutorial_ring(self.cell_rect(step.row, step.col), pulse)

    # ---------------------------------------------------------------- 棋盘动效
    def board_light_layer(self, panel):
        """把「棋盘柔光」烘在一张比面板更大的画布上并缓存。

        画布做得比面板大一圈（四周各留 drift），这样光晕在面板内漂移时
        画布不会露边；真正绘制时用 set_clip 裁到面板范围，光不会溢出到棋盘外。
        """
        drift = self.board_light_drift(panel)
        size = (panel.width + drift * 2, panel.height + drift * 2)
        cached = self._light_layer
        if cached is not None and cached[0] == size:
            return cached[1]

        layer = pygame.Surface(size, pygame.SRCALPHA)
        ui.draw_glow(layer, (size[0] // 2, size[1] // 2),
                     int(min(panel.width, panel.height) * 0.52),
                     (36, 56, 104), 1.0, falloff=2.3)
        self._light_layer = (size, layer)
        return layer

    def board_light_drift(self, panel):
        """柔光在面板内可以漂移的最大距离。"""
        return int(min(panel.width, panel.height) * 0.13)

    def draw_board_light(self, panel):
        """棋盘面板里缓慢游动的一团柔光。

        纯粹的观感件：让"棋盘是活的"，又几乎不干扰判读——
        亮度压得很低，位置用两条不同周期的正弦合成，看不出规律。
        """
        layer = self.board_light_layer(panel)
        drift = self.board_light_drift(panel)
        t = self.time * 0.20
        offset_x = math.sin(t * 1.0) * drift
        offset_y = math.sin(t * 0.68 + 1.7) * drift
        position = (panel.x + drift - offset_x, panel.y + drift - offset_y)

        clip_backup = self.screen.get_clip()
        self.screen.set_clip(panel)
        self.screen.blit(layer, position, special_flags=pygame.BLEND_RGB_ADD)
        self.screen.set_clip(clip_backup)

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
        ui.draw_glow(self.screen, position, 24, color, 0.75, falloff=1.7)

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

        # 右侧要留出「教学 x / y」的位置，左边留一点内边距
        text_area = pygame.Rect(bar.x + 18, bar.y + 10, bar.width - 118, bar.height - 20)
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
            desc = "生命值已经耗尽，再试一次吧"
        else:
            title, color = "全部通关！", config.COLOR_SUCCESS
            desc = "%d 个关卡的箭头都被你清理干净了" % TOTAL_LEVELS

        ui.draw_text(self.screen, title, (panel.centerx, panel.y + 58),
                     size=44, color=color, bold=True, anchor="center")
        ui.draw_text(self.screen, desc, (panel.centerx, panel.y + 106),
                     size=17, color=config.COLOR_TEXT_DIM, anchor="center")

        stats = [
            ("本关箭头", str(self.board.total)),
            ("点错次数", str(self.board.max_hp - self.board.hp_left)),
            ("剩余生命值", "%d / %d" % (self.board.hp_left, self.board.max_hp)),
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
