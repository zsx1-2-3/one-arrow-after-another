# -*- coding: utf-8 -*-
"""自动化测试：覆盖作业要求中的 T01~T06 六个测试用例，外加若干边界检查。

运行方式（在项目根目录下执行）：
    python tests/test_game.py
    python -m unittest discover -s tests -v

说明：T04~T06 需要创建窗口，这里把 SDL 视频驱动切成 dummy，做到无头运行，
所以在没有显示器的服务器上也能跑。
"""

import os
import sys
import unittest

# 必须在 import pygame 之前设置，才能无头运行
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from game import config  # noqa: E402
from game.app import (OVERLAY_FAIL, OVERLAY_WIN, SCENE_MENU, SCENE_PLAY,  # noqa: E402
                      Game)
from game.board import (CLICK_BLOCKED, CLICK_EMPTY, CLICK_FLY,  # noqa: E402
                        CLICK_IGNORED, STATE_CLEARED, STATE_FAILED,
                        STATE_PLAYING, Board, solve_level)
from game.levels import LEVELS, Level  # noqa: E402

FRAME = 1.0 / 60.0


def make_level(layout, max_mistakes=3, name="测试关卡"):
    return Level(name=name, hint="", max_mistakes=max_mistakes, layout=tuple(layout))


# T01 / T02 / T03 使用的测试关卡
#   (1,1) 的「>」被 (1,2) 的「v」挡住；(1,2) 的「v」下方全空，可以飞出
#   一共 3 支箭头：(1,1) 右、(1,2) 下、(3,1) 上
BASIC_LAYOUT = ("....", ".>v.", "....", ".^..")

# 四条边上的箭头都朝向棋盘外，用来验证边界判断
EDGE_LAYOUT = (".^..", "...>", "<...", "..v.")

# 四个角落的箭头朝棋盘内部，用来验证角落不会越界
CORNER_LAYOUT = ("v...", "....", "....", "...^")


class BoardRuleTestCase(unittest.TestCase):
    """棋盘规则（纯逻辑，不需要 pygame）。"""

    def setUp(self):
        self.board = Board(make_level(BASIC_LAYOUT))

    # ---------------------------------------------------------- T01
    def test_t01_click_free_arrow_flies_out(self):
        """T01 点击前方无阻挡的箭头 -> 箭头飞出棋盘并消失。"""
        self.assertEqual(self.board.total, 3)
        result = self.board.click(1, 2)                 # 朝下的箭头，下方无阻挡
        self.assertEqual(result.kind, CLICK_FLY)
        self.assertIsNotNone(result.arrow)
        self.assertEqual(self.board.remaining, 2)
        self.assertIsNone(self.board.arrow_at(1, 2))    # 已经从棋盘上消失
        self.assertEqual(self.board.mistakes, 0)        # 不消耗失误

    # ---------------------------------------------------------- T02
    def test_t02_click_blocked_arrow_costs_a_mistake(self):
        """T02 点击前方有阻挡的箭头 -> 箭头不消失，失误次数减 1。"""
        result = self.board.click(1, 1)                 # 朝右，被 (1,2) 的箭头挡住
        self.assertEqual(result.kind, CLICK_BLOCKED)
        self.assertEqual(result.blocker.row, 1)
        self.assertEqual(result.blocker.col, 2)
        self.assertIsNotNone(self.board.arrow_at(1, 1))  # 箭头还在
        self.assertEqual(self.board.remaining, 3)        # 剩余箭头数不变
        self.assertEqual(self.board.mistakes, 1)
        self.assertEqual(self.board.mistakes_left, 2)

    # ---------------------------------------------------------- T03
    def test_t03_arrows_on_the_edge_fly_out_safely(self):
        """T03 点击边缘且朝向棋盘外的箭头 -> 正常消失，不发生越界错误。"""
        for layout in (EDGE_LAYOUT, CORNER_LAYOUT):
            board = Board(make_level(layout))
            for arrow in list(board.arrows):
                result = board.click(arrow.row, arrow.col)
                self.assertEqual(result.kind, CLICK_FLY,
                                 "(%d,%d) 朝向棋盘外的箭头应该能飞出" % (arrow.row, arrow.col))
                # 路径检查不允许算出棋盘外的坐标
                for row, col in result.path:
                    self.assertTrue(board.in_bounds(row, col))
            self.assertEqual(board.remaining, 0)
            self.assertEqual(board.state, STATE_CLEARED)

    def test_corner_arrow_path_never_leaves_the_board(self):
        """路径检测返回的坐标必须全部落在棋盘内。"""
        board = Board(make_level(EDGE_LAYOUT))
        for arrow in board.arrows:
            for row, col in board.path_cells(arrow.row, arrow.col):
                self.assertTrue(0 <= row < board.rows)
                self.assertTrue(0 <= col < board.cols)

    def test_click_empty_cell_is_harmless(self):
        """点到空格子不算失误，也不改变棋盘。"""
        result = self.board.click(0, 0)
        self.assertEqual(result.kind, CLICK_EMPTY)
        self.assertEqual(self.board.mistakes, 0)
        self.assertEqual(self.board.remaining, 3)

    def test_click_outside_board_is_ignored(self):
        """点到棋盘外不会抛异常。"""
        self.assertEqual(self.board.click(-1, 0).kind, CLICK_IGNORED)
        self.assertEqual(self.board.click(0, 99).kind, CLICK_IGNORED)

    def test_click_after_level_finished_is_ignored(self):
        """本关结束后再点棋盘不再改变任何状态。"""
        board = Board(make_level(EDGE_LAYOUT))
        for arrow in list(board.arrows):
            board.click(arrow.row, arrow.col)
        self.assertEqual(board.state, STATE_CLEARED)
        self.assertEqual(board.click(1, 1).kind, CLICK_IGNORED)
        self.assertEqual(board.remaining, 0)

    def test_fail_when_mistakes_used_up(self):
        """失误用尽后棋盘进入失败状态。"""
        board = Board(make_level(BASIC_LAYOUT, max_mistakes=2))
        board.click(1, 1)
        self.assertEqual(board.state, STATE_PLAYING)
        board.click(1, 1)
        self.assertEqual(board.state, STATE_FAILED)
        self.assertEqual(board.mistakes_left, 0)

    def test_victory_condition(self):
        """清空全部箭头后棋盘进入通关状态。"""
        board = Board(make_level(BASIC_LAYOUT))
        order = board.solution()
        self.assertIsNotNone(order)
        for row, col in order:
            self.assertEqual(board.click(row, col).kind, CLICK_FLY)
        self.assertEqual(board.remaining, 0)
        self.assertEqual(board.state, STATE_CLEARED)

    def test_reset_restores_the_level(self):
        """reset() 把箭头布局和失误次数都恢复原样。"""
        board = Board(make_level(BASIC_LAYOUT))
        board.click(1, 2)
        board.click(1, 1)
        board.reset()
        self.assertEqual(board.remaining, board.total)
        self.assertEqual(board.mistakes, 0)
        self.assertEqual(board.state, STATE_PLAYING)
        for arrow in board.arrows:
            self.assertIs(board.arrow_at(arrow.row, arrow.col), arrow)


class SolverTestCase(unittest.TestCase):
    """关卡求解器与关卡数据校验。"""

    def test_all_levels_are_solvable(self):
        """作业要求：每个关卡都必须存在合理的通关顺序。"""
        for level in LEVELS:
            order = solve_level(level.rows, level.cols, level.arrows)
            self.assertIsNotNone(order, "关卡「%s」无解" % level.name)
            self.assertEqual(len(order), level.arrow_count)

    def test_every_level_can_be_played_to_the_end(self):
        """按求解器给出的顺序实际点击，每个关卡都能通关。"""
        for level in LEVELS:
            board = Board(level)
            for row, col in board.solution():
                self.assertEqual(board.click(row, col).kind, CLICK_FLY,
                                 "关卡「%s」在 (%d,%d) 处卡住了" % (level.name, row, col))
            self.assertEqual(board.state, STATE_CLEARED)
            self.assertEqual(board.remaining, 0)

    def test_deadlock_is_detected(self):
        """互相阻挡的死锁布局必须被判定为无解。"""
        layout = ("....", ".><.", "....", "....")
        level = make_level(layout)
        self.assertIsNone(solve_level(level.rows, level.cols, level.arrows))
        board = Board(level)
        self.assertEqual(board.available_arrows(), [])

    def test_level_layout_validation(self):
        """布局不合法时应当直接报错，避免出现隐蔽的坏关卡。"""
        with self.assertRaises(ValueError):
            make_level(("....", ".>.", "...."))      # 每行长度不一致
        with self.assertRaises(ValueError):
            make_level(("....", ".x..", "...."))     # 非法字符
        with self.assertRaises(ValueError):
            make_level(("....", "...."))             # 一个箭头都没有

    def test_level_sizes_are_within_screen(self):
        """关卡尺寸不能超过窗口能容纳的范围。"""
        for level in LEVELS:
            self.assertLessEqual(level.rows, 12)
            self.assertLessEqual(level.cols, 12)


class GameFlowTestCase(unittest.TestCase):
    """完整流程（含渲染，用 dummy 视频驱动无头运行）。"""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.game = Game(self.screen)

    def advance(self, seconds=1.5):
        """推进若干个渲染帧（用于等待结果面板弹出）。"""
        for _ in range(int(seconds / FRAME) + 1):
            self.game.update(FRAME)

    def blocked_arrow(self, board):
        """找一个当下确实还在棋盘上、且被挡住的箭头。"""
        for arrow in board.arrows:
            if board.arrow_at(arrow.row, arrow.col) is not arrow:
                continue                                # 已经飞出去了，跳过
            if not board.can_fly(arrow.row, arrow.col):
                return arrow
        self.fail("本关没有找到被挡住的箭头，测试用例需要调整")

    def test_start_screen_and_start_button(self):
        """开始界面存在，点「开始游戏」能进入第 1 关。"""
        self.assertEqual(self.game.scene, SCENE_MENU)
        self.assertEqual(self.game.board, None)
        start_button = self.game.buttons[0]
        self.assertEqual(start_button.label, "开始游戏")
        self.game.handle_click(start_button.rect.center)
        self.assertEqual(self.game.scene, SCENE_PLAY)
        self.assertEqual(self.game.level_index, 0)
        self.assertEqual(self.game.board.remaining, LEVELS[0].arrow_count)

    def test_render_every_scene_without_error(self):
        """各个画面都能正常渲染（顺便覆盖绘制代码）。"""
        self.game.draw()                                # 开始界面
        self.game.start_level(0)
        self.game.draw()                                # 游戏界面
        for row, col in self.game.board.solution():
            self.game.click_cell(row, col)
        self.advance()
        self.game.draw()                                # 通关界面
        self.assertEqual(self.game.overlay, OVERLAY_WIN)

    # ---------------------------------------------------------- T04
    def test_t04_clear_level_then_go_to_next_level(self):
        """T04 消除本关全部箭头 -> 显示通关并进入下一关。"""
        game = self.game
        game.start_level(0)
        for row, col in game.board.solution():
            self.assertEqual(game.click_cell(row, col).kind, CLICK_FLY)
        self.assertEqual(game.board.state, STATE_CLEARED)
        self.assertEqual(game.board.remaining, 0)

        self.advance()
        self.assertEqual(game.overlay, OVERLAY_WIN)      # 弹出通关面板

        next_button = game.buttons[0]
        self.assertEqual(next_button.label, "下一关")
        game.handle_click(next_button.rect.center)       # 点「下一关」

        self.assertEqual(game.level_index, 1)
        self.assertEqual(game.scene, SCENE_PLAY)
        self.assertIsNone(game.overlay)
        self.assertEqual(game.board.remaining, LEVELS[1].arrow_count)

    def test_t04_clearing_the_last_level_shows_all_clear(self):
        """打完最后一关显示「全部通关」。"""
        game = self.game
        game.start_level(len(LEVELS) - 1)
        for row, col in game.board.solution():
            game.click_cell(row, col)
        self.advance()
        self.assertEqual(game.overlay, "allclear")

    # ---------------------------------------------------------- T05
    def test_t05_fail_then_restart(self):
        """T05 失误次数耗尽 -> 显示失败并允许重新开始。"""
        game = self.game
        game.start_level(0)
        board = game.board
        target = self.blocked_arrow(board)

        for _ in range(board.max_mistakes):
            game.click_cell(target.row, target.col)
        self.assertEqual(board.state, STATE_FAILED)
        self.assertEqual(board.mistakes_left, 0)

        self.advance()
        self.assertEqual(game.overlay, OVERLAY_FAIL)     # 弹出失败面板

        restart_button = game.buttons[0]
        self.assertEqual(restart_button.label, "重新开始本关")
        game.handle_click(restart_button.rect.center)

        self.assertIsNone(game.overlay)
        self.assertEqual(board.state, STATE_PLAYING)
        self.assertEqual(board.remaining, board.total)
        self.assertEqual(board.mistakes, 0)

    # ---------------------------------------------------------- T06
    def test_t06_restart_mid_game(self):
        """T06 游戏进行中重新开始 -> 箭头布局和失误次数都恢复。"""
        game = self.game
        game.start_level(0)
        board = game.board
        total = board.total

        free = board.available_arrows()[0]
        game.click_cell(free.row, free.col)              # 先消掉一个箭头
        blocked = self.blocked_arrow(board)
        game.click_cell(blocked.row, blocked.col)        # 再制造一次失误
        self.assertLess(board.remaining, total)
        self.assertEqual(board.mistakes, 1)

        restart_button = [b for b in game.buttons if b.label == "重新开始"][0]
        game.handle_click(restart_button.rect.center)

        self.assertEqual(board.remaining, total)
        self.assertEqual(board.mistakes, 0)
        self.assertEqual(board.state, STATE_PLAYING)
        for arrow in board.arrows:                       # 每个箭头都回到原位
            self.assertIs(board.arrow_at(arrow.row, arrow.col), arrow)

    def test_keyboard_shortcuts(self):
        """R 重开本关、Esc 返回主菜单。"""
        game = self.game
        game.start_level(0)
        free = game.board.available_arrows()[0]
        game.click_cell(free.row, free.col)
        self.assertEqual(game.board.remaining, game.board.total - 1)

        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r))
        self.assertEqual(game.board.remaining, game.board.total)

        game.handle_event(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertEqual(game.scene, SCENE_MENU)

    def test_mouse_click_routes_to_the_board(self):
        """鼠标点击棋盘坐标能正确换算到对应的格子。"""
        game = self.game
        game.start_level(0)
        free = game.board.available_arrows()[0]
        target = game.cell_rect(free.row, free.col).center
        game.handle_click(target)
        self.assertIsNone(game.board.arrow_at(free.row, free.col))


def main():
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
