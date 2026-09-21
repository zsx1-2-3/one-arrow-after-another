# -*- coding: utf-8 -*-
"""自动化测试：覆盖作业要求中的 T01~T06 六个测试用例，外加边界检查、进度解锁、
关卡总览交互与教学关引导。

运行方式（在项目根目录下执行）：
    python tests/test_game.py
    python -m unittest discover -s tests -v

说明：T04~T06 需要创建窗口，这里把 SDL 视频驱动切成 dummy，做到无头运行，
所以在没有显示器的服务器上也能跑。
"""

import os
import shutil
import sys
import tempfile
import unittest

# 必须在 import pygame 之前设置，才能无头运行
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from game import bgfx, config, ui  # noqa: E402
from game.app import (OVERLAY_ALL_CLEAR, OVERLAY_FAIL, OVERLAY_WIN,  # noqa: E402
                      SCENE_LEVELS, SCENE_MENU, SCENE_PLAY, Game)
from game.board import (CLICK_BLOCKED, CLICK_EMPTY, CLICK_FLY,  # noqa: E402
                        CLICK_IGNORED, STATE_CLEARED, STATE_FAILED,
                        STATE_PLAYING, Board, solve_level)
from game.levels import LEVELS, TOTAL_LEVELS, Level, tutorial_level_index  # noqa: E402
from game.progress import Progress  # noqa: E402

FRAME = 1.0 / 60.0


def make_level(layout, max_hp=3, name="测试关卡"):
    return Level(name=name, hint="", max_hp=max_hp, layout=tuple(layout))


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
        self.assertEqual(self.board.hp, self.board.max_hp)   # 不扣生命值

    # ---------------------------------------------------------- T02
    def test_t02_click_blocked_arrow_costs_hp(self):
        """T02 点击前方有阻挡的箭头 -> 箭头不消失，生命值减 1。"""
        result = self.board.click(1, 1)                 # 朝右，被 (1,2) 的箭头挡住
        self.assertEqual(result.kind, CLICK_BLOCKED)
        self.assertEqual(result.blocker.row, 1)
        self.assertEqual(result.blocker.col, 2)
        self.assertIsNotNone(self.board.arrow_at(1, 1))  # 箭头还在
        self.assertEqual(self.board.remaining, 3)        # 剩余箭头数不变
        self.assertEqual(self.board.hp, 2)               # 生命值 3 -> 2
        self.assertEqual(self.board.hp_left, 2)

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
        """点到空格子不扣生命值，也不改变棋盘。"""
        result = self.board.click(0, 0)
        self.assertEqual(result.kind, CLICK_EMPTY)
        self.assertEqual(self.board.hp, self.board.max_hp)
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

    def test_fail_when_hp_used_up(self):
        """生命值用尽后棋盘进入失败状态。"""
        board = Board(make_level(BASIC_LAYOUT, max_hp=2))
        board.click(1, 1)
        self.assertEqual(board.state, STATE_PLAYING)
        board.click(1, 1)
        self.assertEqual(board.state, STATE_FAILED)
        self.assertEqual(board.hp_left, 0)

    def test_hp_drops_one_per_blocked_click(self):
        """点错一次固定扣 1 点生命值；扣到 0 就失败，且不会再往下扣成负数。"""
        board = Board(make_level(BASIC_LAYOUT, max_hp=3))
        self.assertEqual(board.hp, 3)                    # 开局是满血

        for expected in (2, 1, 0):
            board.click(1, 1)                            # (1,1) 的「>」被 (1,2) 挡住
            self.assertEqual(board.hp, expected)

        self.assertEqual(board.state, STATE_FAILED)
        board.click(1, 1)                                # 本关已结束，再点不生效
        self.assertEqual(board.hp, 0)
        self.assertEqual(board.remaining, 3)             # 箭头一支都没少

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
        """reset() 把箭头布局和生命值都恢复原样。"""
        board = Board(make_level(BASIC_LAYOUT))
        board.click(1, 2)
        board.click(1, 1)
        board.reset()
        self.assertEqual(board.remaining, board.total)
        self.assertEqual(board.hp, board.max_hp)
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

    def test_level_count_and_difficulty_ramp(self):
        """关卡数量足够多，且难度整体是递增的。"""
        self.assertGreaterEqual(TOTAL_LEVELS, 10)
        scores = [level.difficulty_score for level in LEVELS]
        self.assertEqual(scores, sorted(scores), "难度分应当从左到右递增")

    def test_later_levels_gain_density_not_board_size(self):
        """后半段的难度不靠放大棋盘，而是靠提高密度。

        设计意图：棋盘尺寸尽早封顶，之后同样的格子里塞进更多箭头。
        这条用例把意图固定下来，避免以后又退回「一路把棋盘加大」。
        """
        sizes = [(level.rows, level.cols) for level in LEVELS]

        # 棋盘只许变大、不许变小（不能靠缩小棋盘来假装变难）
        for (rows_a, cols_a), (rows_b, cols_b) in zip(sizes, sizes[1:]):
            self.assertGreaterEqual(rows_b, rows_a)
            self.assertGreaterEqual(cols_b, cols_a)

        # 尺寸必须尽早封顶：从第 9 关起完全不再变化
        frozen = sizes[8]
        for index, size in enumerate(sizes[8:], start=9):
            self.assertEqual(size, frozen, "第 %d 关的棋盘不该再变大" % index)
        self.assertLessEqual(max(max(rows, cols) for rows, cols in sizes), 9,
                             "棋盘尺寸不该超过 9×9")

        # 封顶之后的箭头数量必须严格递增（难度只能从密度来）
        arrows = [level.arrow_count for level in LEVELS]
        for index in range(8, len(arrows) - 1):
            self.assertLess(arrows[index], arrows[index + 1],
                            "第 %d 关起箭头数应当继续增加" % (index + 1))

        # 最后一关的密度要明显高于刚开始加密的那一关
        self.assertGreater(LEVELS[-1].density, LEVELS[5].density + 0.15)

    def test_every_level_has_at_least_one_playable_arrow(self):
        """每个关卡开局都必须至少有一支能点的箭头，否则玩家一上手就是死局。"""
        for level in LEVELS:
            self.assertGreaterEqual(level.free_count, 1,
                                    "关卡「%s」开局无可点箭头" % level.name)

    def test_stars_within_range(self):
        """难度星级必须落在 1~5 之间，且不随难度提高而下降。"""
        stars = [level.stars for level in LEVELS]
        for index, value in enumerate(stars):
            self.assertTrue(1 <= value <= 5, "第 %d 关星级越界" % (index + 1))
        self.assertEqual(stars, sorted(stars), "星级应当不下降")

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

    def test_tutorial_level_must_have_steps(self):
        """教学关必须带引导步骤，否则界面上会没有任何提示。"""
        with self.assertRaises(ValueError):
            Level(name="坏教学关", hint="", max_hp=3,
                  layout=("....", ".>..", "...."), tutorial=True)

    def test_level_sizes_are_within_screen(self):
        """关卡尺寸不能超过窗口能容纳的范围。"""
        for level in LEVELS:
            self.assertLessEqual(level.rows, 12)
            self.assertLessEqual(level.cols, 12)


class ProgressTestCase(unittest.TestCase):
    """闯关进度与解锁规则（纯逻辑，不需要 pygame）。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="arrow_progress_")
        self.path = os.path.join(self.dir, "progress.json")
        self.progress = Progress(path=self.path, autoload=False)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_only_first_level_unlocked_at_start(self):
        """全新存档只解锁第 1 关。"""
        self.assertEqual(self.progress.highest_unlocked(TOTAL_LEVELS), 0)
        self.assertTrue(self.progress.is_unlocked(0, TOTAL_LEVELS))
        self.assertFalse(self.progress.is_unlocked(1, TOTAL_LEVELS))

    def test_clearing_unlocks_the_next_level(self):
        """通关一关之后才解锁下一关。"""
        self.progress.mark_cleared(0)
        self.assertEqual(self.progress.highest_unlocked(TOTAL_LEVELS), 1)
        self.assertTrue(self.progress.is_unlocked(1, TOTAL_LEVELS))
        self.assertFalse(self.progress.is_unlocked(2, TOTAL_LEVELS))

        self.progress.mark_cleared(1)
        self.assertTrue(self.progress.is_unlocked(2, TOTAL_LEVELS))

    def test_skipping_a_level_does_not_unlock_further(self):
        """跳着通关不算数：第 2 关没过，第 3 关依然锁着。"""
        self.progress.mark_cleared(0)
        self.progress.mark_cleared(2)                  # 正常玩法下点不到，这里直接构造
        self.assertEqual(self.progress.highest_unlocked(TOTAL_LEVELS), 1)
        self.assertFalse(self.progress.is_unlocked(2, TOTAL_LEVELS))

    def test_cleared_count_next_index_and_all_cleared(self):
        """统计与「下一关」的取值。"""
        self.assertEqual(self.progress.cleared_count(TOTAL_LEVELS), 0)
        self.assertEqual(self.progress.next_index(TOTAL_LEVELS), 0)

        self.progress.mark_cleared(0)
        self.assertEqual(self.progress.cleared_count(TOTAL_LEVELS), 1)
        self.assertEqual(self.progress.next_index(TOTAL_LEVELS), 1)

        self.progress.mark_all_cleared(TOTAL_LEVELS)
        self.assertTrue(self.progress.all_cleared(TOTAL_LEVELS))
        self.assertEqual(self.progress.next_index(TOTAL_LEVELS), 0)   # 全通关后回到第 1 关

    def test_mark_cleared_is_idempotent(self):
        """重复标记同一关不会出错，也不重复写盘。"""
        self.assertTrue(self.progress.mark_cleared(0))
        self.assertFalse(self.progress.mark_cleared(0))

    def test_save_and_reload(self):
        """存档写到磁盘后能被重新读回来。"""
        self.progress.mark_cleared(0)
        self.progress.mark_cleared(1)

        reloaded = Progress(path=self.path)
        self.assertEqual(reloaded.cleared, {0, 1})
        self.assertEqual(reloaded.highest_unlocked(TOTAL_LEVELS), 2)

    def test_missing_or_broken_save_file_is_tolerated(self):
        """存档不存在或内容损坏时，应当当成空进度而不是崩溃。"""
        missing = Progress(path=os.path.join(self.dir, "nope.json"))
        self.assertEqual(missing.cleared, set())

        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{ 这不是合法的 JSON")
        broken = Progress(path=self.path)
        self.assertEqual(broken.cleared, set())

    def test_reset_clears_everything(self):
        """清空进度后回到只解锁第 1 关的状态，并且已经落盘。"""
        self.progress.mark_all_cleared(TOTAL_LEVELS)
        self.progress.reset()
        self.assertEqual(self.progress.cleared, set())
        self.assertEqual(Progress(path=self.path).cleared, set())


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
        # 每个用例一份独立的临时存档，互不影响、也不会碰真实的 progress.json
        self.dir = tempfile.mkdtemp(prefix="arrow_game_")
        self.progress = Progress(path=os.path.join(self.dir, "progress.json"),
                                 autoload=False)
        self.game = Game(self.screen, progress=self.progress)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

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

    def clear_level(self, index):
        """用求解器给出的顺序把某一关打通。"""
        self.assertTrue(self.game.start_level(index), "第 %d 关进不去" % (index + 1))
        for row, col in self.game.board.solution():
            self.game.click_cell(row, col)

    def unlock_all(self):
        self.progress.mark_all_cleared(TOTAL_LEVELS)
        self.game.enter_menu()

    # ---------------------------------------------------------- 开始界面
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

    def test_menu_explains_the_rules(self):
        """主菜单必须有玩法说明与进入关卡总览的入口。"""
        labels = [button.label for button in self.game.buttons]
        self.assertIn("关卡总览", labels)
        self.assertIn("退出游戏", labels)
        self.assertEqual(len(self.game.buttons), 3)

    def test_primary_button_follows_progress(self):
        """主按钮文字会随进度变化：从「开始游戏」到「继续第 N 关」。"""
        self.assertEqual(self.game.buttons[0].label, "开始游戏")
        self.progress.mark_cleared(0)
        self.game.enter_menu()
        self.assertEqual(self.game.buttons[0].label, "继续第 2 关")
        self.progress.mark_all_cleared(TOTAL_LEVELS)
        self.game.enter_menu()
        self.assertEqual(self.game.buttons[0].label, "重新挑战第 1 关")

    def test_render_every_scene_without_error(self):
        """各个画面都能正常渲染（顺便覆盖绘制代码）。"""
        self.game.draw()                                # 开始界面
        self.game.enter_levels()
        self.game.draw()                                # 关卡总览
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
        self.assertTrue(self.progress.is_cleared(0))     # 顺便记下进度

        next_button = game.buttons[0]
        self.assertEqual(next_button.label, "下一关")
        game.handle_click(next_button.rect.center)       # 点「下一关」

        self.assertEqual(game.level_index, 1)
        self.assertEqual(game.scene, SCENE_PLAY)
        self.assertIsNone(game.overlay)
        self.assertEqual(game.board.remaining, LEVELS[1].arrow_count)

    def test_t04_clearing_the_last_level_shows_all_clear(self):
        """打完最后一关显示「全部通关」。"""
        self.unlock_all()
        self.clear_level(TOTAL_LEVELS - 1)
        self.advance()
        self.assertEqual(self.game.overlay, OVERLAY_ALL_CLEAR)

    # ---------------------------------------------------------- T05
    def test_t05_fail_then_restart(self):
        """T05 生命值耗尽 -> 显示失败并允许重新开始。"""
        game = self.game
        game.start_level(0)
        board = game.board
        target = self.blocked_arrow(board)

        for _ in range(board.max_hp):
            game.click_cell(target.row, target.col)
        self.assertEqual(board.state, STATE_FAILED)
        self.assertEqual(board.hp_left, 0)

        self.advance()
        self.assertEqual(game.overlay, OVERLAY_FAIL)     # 弹出失败面板

        restart_button = game.buttons[0]
        self.assertEqual(restart_button.label, "重新开始本关")
        game.handle_click(restart_button.rect.center)

        self.assertIsNone(game.overlay)
        self.assertEqual(board.state, STATE_PLAYING)
        self.assertEqual(board.remaining, board.total)
        self.assertEqual(board.hp, board.max_hp)

    # ---------------------------------------------------------- T06
    def test_t06_restart_mid_game(self):
        """T06 游戏进行中重新开始 -> 箭头布局和生命值都恢复。

        用第 2 关（初次拉弓）来测：它同时存在「能飞」和「被挡住」的箭头，
        在教学关里消掉一支之后会全部畅通，就扣不到生命值了。
        """
        game = self.game
        self.progress.mark_cleared(0)                    # 先解锁第 2 关
        self.assertTrue(game.start_level(1))
        board = game.board
        total = board.total

        free = board.available_arrows()[0]
        game.click_cell(free.row, free.col)              # 先消掉一个箭头
        blocked = self.blocked_arrow(board)
        game.click_cell(blocked.row, blocked.col)        # 再扣一次生命值
        self.assertLess(board.remaining, total)
        self.assertEqual(board.hp, board.max_hp - 1)     # 只扣掉 1 点

        restart_button = [b for b in game.buttons if b.label == "重新开始"][0]
        game.handle_click(restart_button.rect.center)

        self.assertEqual(board.remaining, total)
        self.assertEqual(board.hp, board.max_hp)
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

    # ---------------------------------------------------------- 关卡解锁
    def test_locked_level_cannot_be_started(self):
        """没通关前一关时，后面的关卡进不去，并且给出提示。"""
        self.assertFalse(self.game.start_level(3))
        self.assertEqual(self.game.scene, SCENE_MENU)
        self.assertEqual(self.game.level_index, 0)
        self.assertGreater(self.game.toast_timer, 0)      # 弹了提示
        self.assertIn("解锁", self.game.toast_text)

    def test_clearing_a_level_unlocks_the_next_one(self):
        """通关之后，下一关立刻变成可进入。"""
        self.assertFalse(self.game.is_unlocked(1))
        self.clear_level(0)
        self.advance()
        self.assertTrue(self.game.is_unlocked(1))
        self.assertTrue(self.game.start_level(1))
        self.assertEqual(self.game.level_index, 1)

    # ---------------------------------------------------------- 关卡总览
    def test_level_select_lists_all_levels(self):
        """关卡总览里每张卡片对应一个关卡。"""
        self.game.enter_levels()
        self.assertEqual(self.game.scene, SCENE_LEVELS)
        self.assertEqual(len(self.game.card_rects), TOTAL_LEVELS)
        self.game.draw()

    def test_clicking_a_locked_card_only_shows_a_hint(self):
        """点未解锁的卡片不会开局，只提示先通关哪一关。"""
        game = self.game
        game.enter_levels()
        game.handle_click(game.card_rects[TOTAL_LEVELS - 1].center)
        self.assertEqual(game.scene, SCENE_LEVELS)
        self.assertIsNone(game.board)
        self.assertGreater(game.toast_timer, 0)
        self.assertIn("解锁", game.toast_text)

    def test_clicking_an_unlocked_card_starts_that_level(self):
        """点已解锁的卡片直接开局。"""
        game = self.game
        game.enter_levels()
        game.handle_click(game.card_rects[0].center)
        self.assertEqual(game.scene, SCENE_PLAY)
        self.assertEqual(game.level_index, 0)

    def test_reset_progress_needs_two_clicks(self):
        """「清空进度」要点两次才真的清，避免手滑。"""
        self.progress.mark_all_cleared(TOTAL_LEVELS)
        game = self.game
        game.enter_levels()

        reset_button = game.buttons[1]
        game.handle_click(reset_button.rect.center)
        self.assertTrue(game.reset_armed)
        self.assertEqual(self.progress.cleared_count(TOTAL_LEVELS), TOTAL_LEVELS)

        game.handle_click(game.buttons[1].rect.center)
        self.assertFalse(game.reset_armed)
        self.assertEqual(self.progress.cleared_count(TOTAL_LEVELS), 0)
        self.assertFalse(game.is_unlocked(1))

    # ---------------------------------------------------------- 教学关
    def test_tutorial_is_the_first_level(self):
        """教学关排在第 1 关的位置，并且带引导步骤。"""
        self.assertEqual(tutorial_level_index(), 0)
        self.assertTrue(LEVELS[0].tutorial)
        self.assertGreater(len(LEVELS[0].steps), 0)

    def test_tutorial_steps_advance_one_by_one(self):
        """照着引导点，步骤会一步步推进，最后引导结束。"""
        game = self.game
        game.start_level(0)
        total_steps = len(game.level.steps)
        self.assertFalse(game.tutorial_done)

        for index in range(total_steps):
            step = game.current_step
            self.assertIsNotNone(step, "第 %d 步引导丢失" % (index + 1))
            result = game.click_cell(step.row, step.col)
            self.assertIsNotNone(result)
            self.assertEqual(result.kind, step.expect,
                             "第 %d 步的预期是 %s，实际是 %s"
                             % (index + 1, step.expect, result.kind))
            self.advance(0.12)

        self.assertTrue(game.tutorial_done)
        self.assertIsNone(game.current_step)
        self.assertEqual(game.board.state, STATE_CLEARED)

    def test_tutorial_resyncs_when_player_deviates(self):
        """玩家不按提示点时，引导会自动跳过已经失效的步骤，而不是卡住。"""
        game = self.game
        game.start_level(0)
        first = game.current_step
        self.assertEqual(first.expect, "blocked")

        # 故意先点「挡路的那一支」：目标 (1,1) 因此变得可以飞出，
        # 于是第 1 步（教碰撞）与第 2 步（教飞出）都失效，引导应直接跳到第 3 步。
        blocker = game.current_step
        game.click_cell(1, 3)                      # (1,3) 的「v」，就是挡路的那一支
        self.advance(0.12)

        step = game.current_step
        self.assertIsNotNone(step)
        self.assertEqual((step.row, step.col), (blocker.row, blocker.col))
        self.assertEqual(step.expect, "fly")
        self.assertEqual(game.tutorial_index, 2)

    def test_tutorial_ring_only_drawn_for_current_step(self):
        """引导高亮只在教学关且步骤未走完时出现（顺带覆盖绘制代码）。"""
        game = self.game
        game.start_level(0)
        self.assertIsNotNone(game.current_step)
        game.draw()
        for row, col in game.board.solution():
            game.click_cell(row, col)
        self.advance(0.2)
        self.assertIsNone(game.current_step)
        game.draw()

    # ---------------------------------------------------------- 全关卡回归
    def test_all_levels_can_be_cleared_in_order(self):
        """按顺序把 12 关全部打通，验证解锁链路与关卡数据整体可用。"""
        game = self.game
        for index in range(TOTAL_LEVELS):
            self.assertTrue(game.start_level(index),
                            "第 %d 关应当已解锁" % (index + 1))
            for row, col in game.board.solution():
                self.assertEqual(game.click_cell(row, col).kind, CLICK_FLY)
                self.advance(0.5)
            self.advance()
            self.assertTrue(self.progress.is_cleared(index),
                            "第 %d 关没有被记为通关" % (index + 1))
        self.assertEqual(game.overlay, OVERLAY_ALL_CLEAR)


class VisualVarietyTestCase(unittest.TestCase):
    """画面观感的回归：箭头配色要打散、文字折行要守中文排版规则、背景要真的在动。

    这些不属于玩法逻辑，但都是「看着很平 / 很糙」的真实问题，
    而且都能用数值断言钉住，所以一并纳入回归，避免以后又退回去。
    """

    @classmethod
    def setUpClass(cls):
        # 前面的用例组结束时调用过 pygame.quit()，缓存里的 Font / Surface 已经失效，
        # 不清掉的话这里再画图会直接段错误（不是抛异常，是进程崩掉）
        was_initialized = pygame.get_init()
        if not was_initialized:
            pygame.init()
        ui.clear_caches()
        if pygame.display.get_surface() is None:
            pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_arrow_variant_is_deterministic_and_in_range(self):
        """同一个格子每次都取到同一个变体，且落在合法档位内。"""
        for row in range(12):
            for col in range(12):
                variant = ui.arrow_variant(row, col)
                self.assertEqual((row * 3 + col * 5) % config.DIR_VARIANTS, variant)
                self.assertTrue(0 <= variant < config.DIR_VARIANTS)
                self.assertEqual(variant, ui.arrow_variant(row, col))

    def test_adjacent_arrows_never_share_a_color(self):
        """上下左右相邻的箭头一定不同色（同向也是这样）。

        这是「同色箭头连成一片」的直接解药：
        (行×3 + 列×5) % 4 里 3 和 5 都与 4 互质，所以四个方向的邻居必然错开。
        """
        for level in LEVELS:
            for row in range(level.rows):
                for col in range(level.cols):
                    direction = _char_direction(level.layout[row][col])
                    if direction is None:
                        continue
                    for d_row, d_col in ((0, 1), (1, 0)):
                        near_row, near_col = row + d_row, col + d_col
                        if not (near_row < level.rows and near_col < level.cols):
                            continue
                        near_direction = _char_direction(level.layout[near_row][near_col])
                        if near_direction != direction:
                            continue          # 不同方向的色相本来就不同
                        self.assertNotEqual(
                            ui.arrow_variant(row, col),
                            ui.arrow_variant(near_row, near_col),
                            "%s 第 (%d,%d) 与 (%d,%d) 两个同向箭头取了同一个变体"
                            % (level.name, row, col, near_row, near_col))

    def test_every_direction_has_its_own_palette(self):
        """四个方向都要有各自的配色，且同方向各档颜色互不相同。"""
        self.assertEqual(set(config.DIR_PALETTES), set(config.DIR_COLORS))
        for direction, palette in config.DIR_PALETTES.items():
            self.assertEqual(len(palette), config.DIR_VARIANTS, direction)
            self.assertEqual(len(set(palette)), len(palette),
                             "%s 的配色里有重复档位" % direction)
            for color in palette:
                self.assertTrue(all(0 <= value <= 255 for value in color))
        groups = [set(palette) for palette in config.DIR_PALETTES.values()]
        for index, group in enumerate(groups):
            for other in groups[index + 1:]:
                self.assertFalse(group & other, "两个方向的配色串了")

    def test_dense_levels_use_many_distinct_colors(self):
        """高密度关卡实际用到的颜色数要够多，不能一片同色。

        箭头少的关卡最多也就用得出「箭头数」种颜色，所以下限取两者的较小值；
        箭头数上到 20 支以后，要求至少铺开 12 种，避免又退回一色到底。
        """
        for level in LEVELS:
            colors = set()
            for row in range(level.rows):
                for col in range(level.cols):
                    direction = _char_direction(level.layout[row][col])
                    if direction is not None:
                        colors.add(ui.arrow_color(direction, ui.arrow_variant(row, col)))
            expected = min(8, level.arrow_count)
            if level.arrow_count >= 20:
                expected = max(expected, 12)
            self.assertGreaterEqual(
                len(colors), expected,
                "%s 只用了 %d 种箭头颜色（期望至少 %d 种），画面会糊成一块"
                % (level.name, len(colors), expected))

    def test_wrap_text_keeps_punctuation_off_line_start(self):
        """折行后不允许有行以收尾标点开头（中文排版的基本要求）。"""
        texts = [step.text for level in LEVELS for step in level.steps]
        texts += ["⑵ 如果它前方还有别的箭头挡路，就飞不出去，并且扣掉 1 点生命值。",
                  "⑷ 通关一关才会解锁下一关，进度会自动保存。"]
        for text in texts:
            for width in (240, 320, 480, 700):
                lines = ui.wrap_text(text, size=15, max_width=width)
                for line in lines:
                    if line:
                        self.assertNotIn(line[0], ui._NO_LINE_START,
                                         "「%s」在宽度 %d 下折出了以「%s」开头的行"
                                         % (text, width, line[0]))

    def test_background_actually_moves(self):
        """背景要真的在动：星点会上飘，时间推进后画面像素确实变了。"""
        surface = pygame.display.get_surface()
        background = bgfx.Background((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        before = [star["y"] for star in background.stars]

        for _ in range(120):
            background.update(FRAME)
        after = [star["y"] for star in background.stars]
        self.assertTrue(any(a < b for a, b in zip(after, before)),
                        "推进 2 秒后没有任何星点移动")

        background.draw(surface)
        first = pygame.image.tobytes(surface, "RGB")
        for _ in range(180):
            background.update(FRAME)
        background.draw(surface)
        second = pygame.image.tobytes(surface, "RGB")
        self.assertNotEqual(first, second, "过了 3 秒背景还是同一张画面")

    def test_background_shows_a_shooting_star_sooner_or_later(self):
        """流星按间隔出现，不会一直不出现。"""
        background = bgfx.Background((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        seen = False
        for _ in range(int(config.BG_SHOOT_INTERVAL[1] / FRAME) + 120):
            background.update(FRAME)
            if background.shooting is not None:
                seen = True
                break
        self.assertTrue(seen, "等了 %d 秒都没等到流星" % config.BG_SHOOT_INTERVAL[1])

    def test_every_scene_renders_with_background(self):
        """三个场景都要能带着动态背景正常画出来。"""
        surface = pygame.display.get_surface()
        background = bgfx.Background((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        for scene in (SCENE_MENU, SCENE_LEVELS, SCENE_PLAY):
            background.set_scene(scene)
            background.update(FRAME)
            background.draw(surface)


def _char_direction(char):
    """关卡布局里的字符 -> 方向名；空格或未知字符返回 None。"""
    return {">": "right", "<": "left", "^": "up", "v": "down"}.get(char)


def main():
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
