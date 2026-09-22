# -*- coding: utf-8 -*-
"""自动化测试：覆盖作业要求中的 T01~T06 六个测试用例，外加边界检查、进度解锁、
关卡总览交互与教学关引导。

运行方式（在项目根目录下执行）：
    python tests/test_game.py
    python -m unittest discover -s tests -v

说明：T04~T06 需要创建窗口，这里把 SDL 视频驱动切成 dummy，做到无头运行，
所以在没有显示器的服务器上也能跑。
"""

import json
import os
import random
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
TOOLS = os.path.join(ROOT, "tools")
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import pygame  # noqa: E402

import deshuffle_levels  # noqa: E402
from game import anim, bgfx, config, scoring, ui  # noqa: E402
from game.app import (HUD_HEART_GAP, HUD_HEART_SIZE, HUD_HEARTS_X,  # noqa: E402
                      HUD_SCORE_LABEL_X, HUD_SCORE_VALUE_X,
                      OVERLAY_ALL_CLEAR, OVERLAY_FAIL, OVERLAY_TUTORIAL_DONE,
                      OVERLAY_WIN, SCENE_LEVELS, SCENE_MENU, SCENE_PLAY, Game)
from game.board import (CLICK_BLOCKED, CLICK_EMPTY, CLICK_FLY,  # noqa: E402
                        CLICK_IGNORED, STATE_CLEARED, STATE_FAILED,
                        STATE_PLAYING, Board, count_free_arrows, solve_level)
from game.levels import (HP_BY_STARS, LEVELS, TOTAL_LEVELS, TUTORIAL,  # noqa: E402
                         Level)
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


def level_index(name):
    """按关卡名查下标。

    关号会随着「插一关 / 删一关」整体前移或后移，写死的数字会静默指错关卡
    （测试还照常通过，只是测的已经不是原来那一关了），所以一律按名字查。
    """
    for index, level in enumerate(LEVELS):
        if level.name == name:
            return index
    raise KeyError("没有叫「%s」的关卡" % name)


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
        """标准关正好 9 关，且难度整条曲线是递增的。

        关数写成硬断言是故意的：这是需求本身（9 个标准关 + 1 个独立的教学关），
        以后再加关就得同时改这条用例，等于逼着人再确认一次「还符合需求吗」。
        """
        self.assertEqual(TOTAL_LEVELS, 9, "标准关应当是 9 关，另加 1 个独立的教学关")
        scores = [level.difficulty_score for level in LEVELS]
        self.assertEqual(scores, sorted(scores), "难度分应当从左到右递增")

    def test_levels_one_to_four_get_harder_step_by_step(self):
        """第 1~4 关是入门段，难度必须一关比一关高，而且步子要看得出来。

        教学关独立出去以后，这四关就是玩家真正开始的地方：
        棋盘只许变大、箭头只许变多、开局能直接飞出的箭头只许变少，
        难度分则必须严格上升。这条用例把「递增」从口头约定变成硬约束。
        """
        first_four = LEVELS[:4]
        self.assertEqual(len(first_four), 4)
        for index in range(len(first_four) - 1):
            before, after = first_four[index], first_four[index + 1]
            number = index + 2
            self.assertLess(before.difficulty_score, after.difficulty_score,
                            "第 %d 关（%.2f）并不比第 %d 关（%.2f）难"
                            % (number, after.difficulty_score, number - 1,
                               before.difficulty_score))
            self.assertLessEqual(before.rows, after.rows,
                                 "第 %d 关的棋盘不该比前一关矮" % number)
            self.assertLessEqual(before.cols, after.cols,
                                 "第 %d 关的棋盘不该比前一关窄" % number)
            self.assertLessEqual(before.arrow_count, after.arrow_count,
                                 "第 %d 关的箭头不该比前一关少" % number)
            self.assertLessEqual(before.stars, after.stars,
                                 "第 %d 关的星级不该比前一关低" % number)

        # 第 2 关的招牌是「全场只有一支能飞」，这个数字要真的成立
        self.assertEqual(LEVELS[1].free_count, 1)
        self.assertGreaterEqual(LEVELS[0].free_count, 2)
        self.assertNotEqual(LEVELS[0].layout, TUTORIAL.layout,
                            "第 1 关不该和教学关长得一样")

    def test_difficulty_steps_stay_smooth_across_nine_levels(self):
        """九个关卡的难度是一级一级加的，任意相邻两关都不能顶出一个大台阶。

        把关卡表从 8 关补到 9 关时，最讲究的就是「新关插在哪儿」——
        插错地方会在曲线上顶出一处陡坡（原来第 5→6 关一跳 22.3 分，
        后一关的箭头数是前一关的 1.67 倍，中间缺了一档）。
        这条用例把两件事钉死：一次只许加 1~10 支箭头；相邻难度差 ≤ 20 分。
        """
        arrows = [level.arrow_count for level in LEVELS]
        for index, (before, after) in enumerate(zip(arrows, arrows[1:]), start=2):
            self.assertGreaterEqual(after, before, "第 %d 关箭头数反而变少了" % index)
            self.assertLessEqual(after - before, 10,
                                 "第 %d 关一次加了 %d 支箭头，台阶太陡"
                                 % (index, after - before))

        scores = [level.difficulty_score for level in LEVELS]
        gaps = [after - before for before, after in zip(scores, scores[1:])]
        self.assertLess(max(gaps), 20.0, "相邻两关的难度差别超过 20 分")
        self.assertGreater(max(gaps), 12.0,
                           "最后一跳应当拉到 12 分以上，否则收尾不够有力")

        # 台阶是「越往后越大」：前半程平均步子明显小于后半程
        half = len(gaps) // 2
        early = sum(gaps[:half]) / half
        late = sum(gaps[half:]) / (len(gaps) - half)
        self.assertGreater(late, early, "难度台阶应当越往后越大")

    def test_tutorial_is_not_a_numbered_level(self):
        """教学关独立于关卡表：不占第 1 关的位置，也不参与编号。"""
        self.assertTrue(TUTORIAL.tutorial)
        self.assertGreater(len(TUTORIAL.steps), 0, "教学关必须带引导步骤")
        self.assertFalse(any(level.tutorial for level in LEVELS),
                         "编号关卡里不该再混进教学关")
        self.assertFalse(any(level.steps for level in LEVELS),
                         "编号关卡不该带教学引导步骤")
        for level in LEVELS:
            self.assertNotEqual(level.name, TUTORIAL.name)

    def test_tutorial_is_solvable_and_playable(self):
        """教学关自己也要可解、能一路点到通关。"""
        board = Board(TUTORIAL)
        for row, col in board.solution():
            self.assertEqual(board.click(row, col).kind, CLICK_FLY,
                             "教学关在 (%d,%d) 处卡住了" % (row, col))
        self.assertEqual(board.state, STATE_CLEARED)

    def test_tutorial_is_a_forgiving_sandbox(self):
        """教学关是给人放胆点的沙盒，生命值要比同星级的关卡宽裕。"""
        self.assertGreater(TUTORIAL.max_hp, HP_BY_STARS[TUTORIAL.stars],
                           "教学关的生命值该比按星级给的更宽松，"
                           "否则新手会在教程里就被判失败")

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

        max_side = max(max(rows, cols) for rows, cols in sizes)
        self.assertLessEqual(max_side, 9, "棋盘尺寸不该超过 9×9")

        # 找到第一次达到最大尺寸的那一关，之后就不许再变大了
        frozen_at = next(index for index, size in enumerate(sizes)
                         if max(size) == max_side)
        for index, size in enumerate(sizes[frozen_at:], start=frozen_at + 1):
            self.assertEqual(size, sizes[frozen_at],
                             "第 %d 关的棋盘不该比前关更大" % index)

        # 封顶之后的箭头数量必须严格递增（难度只能从密度来）
        arrows = [level.arrow_count for level in LEVELS]
        for index in range(frozen_at, len(arrows) - 1):
            self.assertLess(arrows[index], arrows[index + 1],
                            "第 %d 关起箭头数应当继续增加" % (index + 1))

        # 最后一关的密度要明显高于棋盘封顶前的那一关。
        # 参照关卡写成 frozen_at - 1（而不是硬编码的关号）：
        # 教学关独立出去之后所有下标都前移了一位，写死下标会被这种改动坑到。
        self.assertGreater(LEVELS[-1].density, LEVELS[frozen_at - 1].density + 0.10)

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


class LevelBalanceTestCase(unittest.TestCase):
    """生命值按难度给：关卡越难，容错越高。

    早期版本每关的容错是固定值，后来变成 5/4/4/4/3/4/3/2/2——越到后面越少，
    第九关要塞 50 支箭头却只剩 2 颗心，一次手滑就得从头再来。
    现在生命值由难度星级推出来（levels.HP_BY_STARS），整体只增不减。
    """

    def test_hp_is_granted_by_difficulty(self):
        """每关的生命值必须正好是「星级 → 生命值」表里对应的值。"""
        for index, level in enumerate(LEVELS, start=1):
            self.assertEqual(
                level.max_hp, HP_BY_STARS[level.stars],
                "第 %d 关「%s」是 %d 星，应当给 %d 颗心，实际 %d 颗"
                % (index, level.name, level.stars, HP_BY_STARS[level.stars], level.max_hp))

    def test_tolerance_grows_from_first_level_to_last(self):
        """生命值上限整体不下降，最后一关要明显比第 1 关宽容。"""
        hp = [level.max_hp for level in LEVELS]
        self.assertEqual(hp, sorted(hp), "生命值不该越到后面越少，实际是 %s" % hp)
        self.assertGreater(hp[-1], hp[0], "最后一关的容错应当高于第 1 关")
        for index, level in enumerate(LEVELS, start=1):
            self.assertGreaterEqual(level.max_hp, 3,
                                    "第 %d 关只给 %d 颗心，太苛刻了"
                                    % (index, level.max_hp))

    def test_one_mistake_hurts_less_on_harder_levels(self):
        """点错一次的代价逐关变小——这就是「容错越来越高」的量化说法。

        比较的是「丢一颗心损失掉本关满分的百分之几」，
        而不是绝对分数：后面关卡底分更高，绝对分差本来就更大。
        """
        penalties = []
        for level in LEVELS:
            full = float(scoring.max_score(level))
            after = scoring.level_score(level, level.max_hp - 1)
            penalties.append(1.0 - after / full)

        for index in range(len(penalties) - 1):
            self.assertLessEqual(
                penalties[index + 1], penalties[index] + 1e-9,
                "第 %d 关丢一颗心要损失 %.1f%%，比第 %d 关的 %.1f%% 还重"
                % (index + 2, penalties[index + 1] * 100,
                   index + 1, penalties[index] * 100))
        self.assertLess(penalties[-1], penalties[0])

    def test_star_ramp_starts_at_one_and_ends_at_five(self):
        """星级从第 1 关的 1 星升到最后一关的 5 星（教学关不在这条链上）。"""
        stars = [level.stars for level in LEVELS]
        self.assertEqual(stars[0], 1)
        self.assertEqual(stars[-1], 5)
        self.assertEqual(stars[:4], [1, 2, 3, 3], "前四关的星级阶梯变了")


class ScoringTestCase(unittest.TestCase):
    """得分规则：剩下的心越多分越高，一颗心都没丢另有奖励。"""

    def test_full_score_follows_the_difficulty_stars(self):
        """满分 = 星级 × 300（基础分 250 + 20% 完美奖励）。"""
        for index, level in enumerate(LEVELS, start=1):
            self.assertEqual(scoring.base_score(level), level.stars * 250)
            self.assertEqual(scoring.max_score(level), level.stars * 300,
                             "第 %d 关满分不对" % index)
            self.assertEqual(scoring.level_score(level, level.max_hp),
                             scoring.max_score(level), "满心通关应当拿满分")

    def test_every_mistake_costs_points(self):
        """同一关里，失去的心越多得分越低，且是严格下降。"""
        for index, level in enumerate(LEVELS, start=1):
            scores = [scoring.level_score(level, hp)
                      for hp in range(level.max_hp, -1, -1)]
            for before, after in zip(scores, scores[1:]):
                self.assertGreater(before, after,
                                   "第 %d 关 %d→%d 颗心时得分没有下降：%s"
                                   % (index, scores[0], scores[-1], scores))

    def test_perfect_bonus_only_when_nothing_is_lost(self):
        """零失误奖励只在满心通关时给，而且正好是基础分的 20%。"""
        for level in LEVELS:
            bonus = scoring.perfect_bonus(level)
            self.assertEqual(bonus, scoring.base_score(level) * 20 // 100)
            self.assertEqual(scoring.level_score(level, level.max_hp),
                             scoring.base_score(level) + bonus)
            # 丢一颗心就没有奖励了：剩下的分正好是按比例折算的基础分
            self.assertEqual(scoring.level_score(level, level.max_hp - 1),
                             scoring.base_score(level) * (level.max_hp - 1)
                             // level.max_hp)

    def test_failing_the_level_is_worth_nothing(self):
        """生命值耗尽时本关 0 分（越界的参数也不会算出一个负数）。"""
        for level in LEVELS:
            self.assertEqual(scoring.level_score(level, 0), 0)
            self.assertEqual(scoring.level_score(level, -2), 0)
            self.assertEqual(scoring.lost_hearts(level, -2), level.max_hp)

    def test_board_exposes_a_live_score(self):
        """棋盘自己就知道当前能拿多少分，HUD 直接用这个数（点错立刻掉）。"""
        level = make_level(BASIC_LAYOUT, max_hp=4)
        board = Board(level)
        self.assertEqual(board.hearts_lost, 0)
        self.assertEqual(board.score, scoring.level_score(level, 4))

        board.click(1, 1)                    # (1,1) 的「>」被 (1,2) 的「v」挡住
        self.assertEqual(board.hearts_lost, 1)
        self.assertEqual(board.hp, 3)
        self.assertEqual(board.score, scoring.level_score(level, 3))
        self.assertLess(board.score, scoring.level_score(level, 4))

    def test_total_full_score_is_the_sum_of_all_levels(self):
        self.assertEqual(scoring.total_max_score(LEVELS),
                         sum(scoring.max_score(level) for level in LEVELS))
        self.assertGreater(scoring.total_max_score(LEVELS), 1000)


class ColorSpreadTestCase(unittest.TestCase):
    """配色打散的回归：相邻的箭头不要大面积朝同一个方向。

    同向的两支箭头挨在一起，在屏幕上就是两块同色贴在一起；一整排同向
    就是一条色带，看着既单调又显得简单（早期第 8 关相邻同向对占 59%、
    最大同色块 6 格）。现在关卡定稿前会过一遍 tools/deshuffle_levels.py。
    """

    MAX_SAME_RATIO = 0.28      # 相邻同向对占比上限（方向随机撒的时代期望值是 0.25）
    MAX_BLOCK = 4              # 同方向连通块的最大格子数上限

    def test_adjacent_arrows_are_mostly_different_directions(self):
        """每关「相邻且同向」的箭头对不能太多。"""
        for index, level in enumerate(LEVELS, start=1):
            ratio, _ = same_color_cluster(level)
            self.assertLessEqual(
                ratio, self.MAX_SAME_RATIO,
                "第 %d 关「%s」相邻同向对占 %.0f%%，屏幕上会连成同色的片"
                % (index, level.name, ratio * 100))

    def test_same_color_blocks_stay_small(self):
        """同方向的箭头不该连成一大块。"""
        for index, level in enumerate(LEVELS, start=1):
            _, biggest = same_color_cluster(level)
            self.assertLessEqual(
                biggest, self.MAX_BLOCK,
                "第 %d 关「%s」有 %d 支同向箭头连成一块" % (index, level.name, biggest))

    def test_arrow_colors_are_still_decided_only_by_direction(self):
        """打散配色只动关卡布局，不动调色板：一个方向仍然只有一种颜色。"""
        self.assertEqual(len(config.DIR_COLORS), 4)
        for level in LEVELS:
            for row, line in enumerate(level.layout):
                for col, char in enumerate(line):
                    direction = _char_direction(char)
                    if direction is None:
                        continue
                    self.assertEqual(ui.arrow_color(direction),
                                     config.DIR_COLORS[direction])

    def test_deshuffle_keeps_the_level_solvable_and_no_easier(self):
        """打散工具只换方向：换完仍然可解，开局可点数不会变多。

        这是这个工具唯一的存在理由——为了好看把题目改坏（变成死局、或者
        顺手把开局可点数抬上去）是不允许的，所以拿最扎堆的一关实测一遍。
        """
        level = max(LEVELS, key=lambda item: same_color_cluster(item)[0])
        arrows = [(row, col, direction) for row, col, direction in level.arrows]
        before_same, _ = deshuffle_levels.pair_stats(level.rows, level.cols, arrows)
        before_free = level.free_count

        rng = random.Random(20260921)
        result, (same, _, free0, _) = deshuffle_levels.deshuffle(
            level.rows, level.cols, arrows, rng, attempts=400, max_free0=before_free)

        self.assertIsNotNone(
            solve_level(level.rows, level.cols, result), "打散之后关卡无解了")
        self.assertEqual(free0, count_free_arrows(level.rows, level.cols, result))
        self.assertLessEqual(same, before_same, "打散不该让同向相邻对变多")
        self.assertLessEqual(free0, before_free, "打散不该让开局变容易")
        self.assertEqual(
            sorted((row, col) for row, col, _ in result),
            sorted((row, col) for row, col, _ in arrows),
            "打散只换方向，位置一支都不能动")


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
        """清空进度后回到只解锁第 1 关的状态，最高分也一并清掉，且已经落盘。"""
        self.progress.mark_all_cleared(TOTAL_LEVELS)
        self.progress.record_score(0, 600)
        self.progress.reset()
        self.assertEqual(self.progress.cleared, set())
        self.assertEqual(self.progress.scores, {})
        reloaded = Progress(path=self.path)
        self.assertEqual(reloaded.cleared, set())
        self.assertEqual(reloaded.scores, {})

    # ---------------------------------------------------------- 最高分
    def test_scores_are_recorded_and_only_the_best_one_wins(self):
        """每关只留最高分：重玩手感差不会把纪录冲掉。"""
        self.assertEqual(self.progress.best_score(0), 0)
        self.assertEqual(self.progress.record_score(0, 375), 375)   # 首次记分，增量 375
        self.assertEqual(self.progress.best_score(0), 375)
        self.assertEqual(self.progress.record_score(0, 200), 0)     # 打得更差：不覆盖
        self.assertEqual(self.progress.best_score(0), 375)
        self.assertEqual(self.progress.record_score(0, 600), 225)   # 刷新纪录，增量 225
        self.assertEqual(self.progress.best_score(0), 600)
        self.assertEqual(self.progress.record_score(0, 600), 0)     # 打平也不算刷新
        self.assertEqual(Progress(path=self.path).best_score(0), 600)

    def test_total_score_is_the_sum_of_each_levels_best(self):
        """总分 = 各关最高分之和；不存在关卡里的分数不计入。"""
        self.progress.record_score(0, 300)
        self.progress.record_score(1, 375)
        self.progress.record_score(TOTAL_LEVELS + 5, 999)     # 手改存档留下的垃圾关号
        self.assertEqual(self.progress.total_score(TOTAL_LEVELS), 675)

    def test_old_save_without_scores_still_loads(self):
        """老存档（version 1，没有 scores 字段）不能因为升级格式丢进度。"""
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"version": 1, "cleared": [0, 1]}, handle)
        loaded = Progress(path=self.path)
        self.assertEqual(loaded.cleared, {0, 1})
        self.assertEqual(loaded.scores, {})
        self.assertEqual(loaded.total_score(TOTAL_LEVELS), 0)

    def test_broken_scores_in_the_save_file_are_ignored(self):
        """存档里的分数被人手改坏了（非数字、负数）时，只丢掉坏的那几条。"""
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"version": 2, "cleared": [0],
                       "scores": {"0": "abc", "-1": 500, "2": 300, "x": 100}},
                      handle)
        loaded = Progress(path=self.path)
        self.assertEqual(loaded.cleared, {0})
        self.assertEqual(loaded.scores, {2: 300})


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
        """主菜单必须有玩法说明，以及教学关 / 关卡总览 / 退出三个入口。"""
        labels = [button.label for button in self.game.buttons]
        self.assertIn("教学关", labels)
        self.assertIn("关卡总览", labels)
        self.assertIn("退出游戏", labels)
        self.assertEqual(len(self.game.buttons), 4)

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

    def test_blocked_click_pops_a_broken_heart_not_hanzi(self):
        """点错时飘出来的是一颗「碎掉的像素心」，不是「失去一心」四个汉字。

        生命值本来就用心的形状表示，所以扣血的提示也用同一套图形；
        文字提示只留给「这里没有箭头」这种和生命值无关的消息。
        """
        self.game.start_level(0)
        arrow = self.blocked_arrow(self.game.board)
        self.assertTrue(self.game.click_cell(arrow.row, arrow.col))

        hearts = [item for item in self.game.floats
                  if isinstance(item, anim.FloatingHeart)]
        self.assertEqual(len(hearts), 1, "点错一次应该正好飘出一颗心")
        heart = hearts[0]
        self.assertEqual(heart.color, config.COLOR_HP)
        self.assertGreater(heart.size, 0)

        for text in [item.text for item in self.game.floats
                     if isinstance(item, anim.FloatingText)]:
            self.assertNotIn("一心", text, "扣血提示不该再用汉字描述")

        # 心会自己飘完消失，不会一直挂在画面上
        for _ in range(int(heart.duration / FRAME) + 4):
            self.game.update(FRAME)
        self.assertFalse([item for item in self.game.floats
                          if isinstance(item, anim.FloatingHeart)],
                         "心碎动画播完要自动移除")

    def test_broken_heart_animation_renders_and_fades_out(self):
        """心碎动画：两半分开、心往上飘、末端淡出，每一帧都画得出来。"""
        heart = anim.FloatingHeart((480, 360), size=40, duration=1.2, rise=50)
        self.assertEqual(heart.left.get_width() + heart.right.get_width(), 40,
                         "左右两半拼起来应该是完整的一颗心")

        for _ in range(18):                      # 前 0.3 秒：应该还看得很清楚
            heart.update(FRAME)
            heart.draw(self.screen)
        self.assertEqual(heart.alpha, 255, "前 30% 的时间不该已经开始淡出")
        self.assertLess(heart.lift, 0.0, "心应该已经离开原位往上飘了")

        for _ in range(18):                      # 0.3 ~ 0.6 秒：开始淡出
            heart.update(FRAME)
            heart.draw(self.screen)
        self.assertLess(heart.alpha, 255, "后半段应该开始淡出")

        while not heart.update(FRAME):           # 一直播到结束
            heart.draw(self.screen)
        self.assertEqual(heart.progress, 1.0)
        self.assertEqual(heart.alpha, 0, "播完之后要完全淡出，不能留一颗挂在画面上")

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

    # ---------------------------------------------------------- 得分结算
    # 用「错位走廊」做样本：6 颗心、满分 1200，中间量足够看出差别。
    # 按名字查下标，关卡表插一关也不会指到别的关卡上去。
    SAMPLE = level_index("错位走廊")

    def test_clearing_without_mistakes_pays_the_full_score(self):
        """零失误通关：拿满分、记进存档，结算面板写出完美奖励。"""
        self.unlock_all()
        self.clear_level(self.SAMPLE)
        self.advance()

        game = self.game
        level = LEVELS[self.SAMPLE]
        self.assertEqual(game.overlay, OVERLAY_WIN)
        self.assertTrue(game.score_perfect)
        self.assertEqual(game.score_max, scoring.max_score(level))
        self.assertEqual(game.last_score, scoring.max_score(level))
        self.assertEqual(game.score_gain, game.last_score)     # 首次通关就是全部增量
        self.assertEqual(self.progress.best_score(self.SAMPLE), game.last_score)
        self.assertIn("完美奖励", game.score_note()[0])
        game.draw()                                            # 结算面板画得出来

    def test_every_mistake_lowers_the_score(self):
        """丢一颗心，HUD 上的得分立刻按比例下降，最终结算也跟着少。"""
        self.unlock_all()
        game = self.game
        level = LEVELS[self.SAMPLE]
        self.assertTrue(game.start_level(self.SAMPLE))
        full = scoring.max_score(level)
        self.assertEqual(game.board.score, full)               # 开局是满分

        target = self.blocked_arrow(game.board)
        game.click_cell(target.row, target.col)                # 故意点错一次
        expected = scoring.level_score(level, level.max_hp - 1)
        self.assertEqual(game.board.score, expected)
        game.draw()

        for row, col in game.board.solution():                 # 再老老实实通关
            game.click_cell(row, col)
        self.advance()
        self.assertEqual(game.last_score, expected)
        self.assertLess(game.last_score, full)
        self.assertFalse(game.score_perfect)
        self.assertIn("得分 =", game.score_note()[0])

    def test_a_worse_replay_keeps_the_old_record(self):
        """重玩打得差不会把最高分冲掉（存档只记最好的一次）。"""
        self.unlock_all()
        self.clear_level(self.SAMPLE)
        self.advance()
        best = self.progress.best_score(self.SAMPLE)
        self.assertEqual(best, scoring.max_score(LEVELS[self.SAMPLE]))

        game = self.game
        self.assertTrue(game.start_level(self.SAMPLE))
        target = self.blocked_arrow(game.board)
        game.click_cell(target.row, target.col)
        for row, col in game.board.solution():
            game.click_cell(row, col)
        self.advance()
        self.assertEqual(game.score_gain, 0)
        self.assertLess(game.last_score, best)
        self.assertEqual(self.progress.best_score(self.SAMPLE), best)

    def test_failing_a_level_scores_zero(self):
        """生命值耗尽：本关 0 分，也不写进存档。"""
        self.unlock_all()
        game = self.game
        self.assertTrue(game.start_level(self.SAMPLE))
        target = self.blocked_arrow(game.board)
        for _ in range(game.board.max_hp):
            game.click_cell(target.row, target.col)
        self.advance()
        self.assertEqual(game.overlay, OVERLAY_FAIL)
        self.assertEqual(game.last_score, 0)
        self.assertEqual(game.score_gain, 0)
        self.assertEqual(self.progress.best_score(self.SAMPLE), 0)
        self.assertIn("0 分", game.score_note()[0])
        game.draw()

    def test_hud_has_room_for_the_widest_level(self):
        """HUD 三组数字排得下：心最多的一关（7 颗）也不会顶到右边或压到得分。

        生命值上限是按难度给的、最后一关有 7 颗心，最宽的一排心加上
        「7 / 7」正好顶到得分那一栏就会糊成一片，所以这里用真实字宽量一遍。
        （三个按钮在上一行，不和这行数字抢位置，所以只需守住窗口右边界。）
        """
        widest = max(level.max_hp for level in LEVELS)
        hearts_right = (HUD_HEARTS_X + widest * HUD_HEART_SIZE
                        + (widest - 1) * HUD_HEART_GAP + 10
                        + ui.text_width("%d / %d" % (widest, widest), size=15))
        self.assertLess(hearts_right, HUD_SCORE_LABEL_X, "生命值压到得分那一栏了")

        score_right = (HUD_SCORE_VALUE_X + ui.text_width("9999", size=26, bold=True) + 8
                       + ui.text_width("/ 9999", size=14))
        self.assertLess(score_right, config.WINDOW_WIDTH - 24, "得分顶到窗口右边了")

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

        用第 2 关（交叉路口）来测：它同时存在「能飞」和「被挡住」的箭头，
        消掉那支能飞的之后仍有箭头被挡着，扣得到生命值。
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
    def test_tutorial_has_its_own_entry_on_the_menu(self):
        """教学关是菜单上的独立入口：不用解锁，点了就能进。"""
        game = self.game
        self.assertFalse(game.is_unlocked(1))            # 全新存档，第 2 关还锁着
        button = [b for b in game.buttons if b.label == "教学关"][0]
        game.handle_click(button.rect.center)

        self.assertEqual(game.scene, SCENE_PLAY)
        self.assertTrue(game.in_tutorial)
        self.assertIs(game.level, TUTORIAL)
        self.assertIsNot(game.level, LEVELS[0])
        self.assertEqual(game.board.remaining, TUTORIAL.arrow_count)
        game.draw()                                      # 教学关界面画得出来

    def test_finishing_the_tutorial_scores_nothing(self):
        """教学关走完：不进存档、不解锁、不算分，只引导去第 1 关。"""
        game = self.game
        self.assertTrue(game.start_tutorial())
        for row, col in game.board.solution():
            game.click_cell(row, col)
        self.advance()

        self.assertEqual(game.overlay, OVERLAY_TUTORIAL_DONE)
        self.assertEqual(game.last_score, 0)
        self.assertEqual(self.progress.cleared, set(), "教学关不该写进通关记录")
        self.assertEqual(self.progress.total_score(TOTAL_LEVELS), 0)
        self.assertFalse(game.is_unlocked(1), "教学关不该顺手解锁第 2 关")
        self.assertIn("不计分", game.score_note()[0])
        game.draw()

        # 结算面板只给「开始第 1 关 / 再看一遍 / 关卡总览 / 返回主菜单」
        labels = [button.label for button in game.buttons]
        self.assertEqual(labels[0], "开始第 1 关")
        self.assertNotIn("下一关", labels)
        game.handle_click(game.buttons[0].rect.center)
        self.assertFalse(game.in_tutorial)
        self.assertEqual(game.level_index, 0)
        self.assertEqual(game.scene, SCENE_PLAY)

    def test_tutorial_can_be_failed_and_retried_without_penalty(self):
        """教学关点光生命值也只是重来一遍：不记分、不锁关。"""
        game = self.game
        game.start_tutorial()
        target = self.blocked_arrow(game.board)
        for _ in range(game.board.max_hp):
            game.click_cell(target.row, target.col)
        self.advance()

        self.assertEqual(game.overlay, OVERLAY_FAIL)
        self.assertEqual(game.last_score, 0)
        self.assertEqual(self.progress.cleared, set())
        self.assertIn("教学关", game.score_note()[0])
        game.draw()

        restart = [b for b in game.buttons if b.label == "重新开始本关"][0]
        game.handle_click(restart.rect.center)
        self.assertEqual(game.board.state, STATE_PLAYING)
        self.assertEqual(game.board.hp, game.board.max_hp)
        self.assertTrue(game.in_tutorial)

    def test_tutorial_steps_advance_one_by_one(self):
        """照着引导点，步骤会一步步推进，最后引导结束。"""
        game = self.game
        game.start_tutorial()
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
        game.start_tutorial()
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
        game.start_tutorial()
        self.assertIsNotNone(game.current_step)
        game.draw()
        for row, col in game.board.solution():
            game.click_cell(row, col)
        self.advance(0.2)
        self.assertIsNone(game.current_step)
        game.draw()

    # ---------------------------------------------------------- 全关卡回归
    def test_all_levels_can_be_cleared_in_order(self):
        """按顺序把 9 关全部打通，验证解锁链路与关卡数据整体可用。"""
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

    def test_every_arrow_takes_its_direction_color(self):
        """箭头颜色只由方向决定：同一方向的箭头颜色完全一致。

        这是「不要有的亮有的暗」的直接体现——一个方向就是唯一一个颜色，
        不再按格子坐标取深浅变体。
        """
        for level in LEVELS:
            for row in range(level.rows):
                for col in range(level.cols):
                    direction = _char_direction(level.layout[row][col])
                    if direction is None:
                        continue
                    self.assertEqual(ui.arrow_color(direction),
                                     config.DIR_COLORS[direction])

    def test_direction_colors_have_matched_brightness(self):
        """四个方向的颜色感知亮度要拉平，整屏看起来才像「一套」。

        感知亮度 = 0.299R + 0.587G + 0.114B。
        早先每个方向配了 4 档明暗变体，同方向内亮度跨度到 70 以上，
        看着忽明忽暗；现在四个颜色的亮度差必须收在 5 以内。
        """
        luminances = []
        for direction, color in config.DIR_COLORS.items():
            self.assertTrue(all(0 <= value <= 255 for value in color), direction)
            luminances.append(0.299 * color[0] + 0.587 * color[1] + 0.114 * color[2])
        spread = max(luminances) - min(luminances)
        self.assertLess(spread, 5.0,
                        "四个方向的箭头颜色亮度差了 %.1f，看起来会有的亮有的暗"
                        % spread)

    def test_direction_colors_are_distinct_and_all_used(self):
        """四个方向颜色互不相同，且确实都在关卡里用到。"""
        colors = list(config.DIR_COLORS.values())
        self.assertEqual(len(set(colors)), len(colors), "有两个方向撞色了")

        used = set()
        for level in LEVELS:
            for row in range(level.rows):
                for col in range(level.cols):
                    direction = _char_direction(level.layout[row][col])
                    if direction is not None:
                        used.add(direction)
        self.assertEqual(used, set(config.DIR_COLORS), "有关卡里几乎不出现的方向")

    def test_level_colors_are_only_direction_colors(self):
        """一关里出现的颜色只可能来自那 4 个方向色，不会有第 5 种。"""
        for level in LEVELS:
            colors = set()
            for row in range(level.rows):
                for col in range(level.cols):
                    direction = _char_direction(level.layout[row][col])
                    if direction is not None:
                        colors.add(ui.arrow_color(direction))
            self.assertLessEqual(len(colors), len(config.DIR_COLORS))
            self.assertTrue(colors.issubset(set(config.DIR_COLORS.values())),
                            "%s 出现了配色表以外的箭头颜色" % level.name)

    def test_wrap_text_keeps_punctuation_off_line_start(self):
        """折行后不允许有行以收尾标点开头（中文排版的基本要求）。"""
        # 引导文案现在只存在于独立的教学关里（LEVELS 里已经不带 steps）
        texts = [step.text for step in TUTORIAL.steps]
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

    # ---------------------------------------------------------- 生命值图标
    def test_heart_icon_is_a_pixel_art_grid(self):
        """生命值图标是「像素心」：规整网格、左右对称、顶部中间留凹口。"""
        art = config.HEART_PIXEL_ART
        self.assertGreaterEqual(len(art), 4, "像素心太小了，看不出心的形状")
        width = len(art[0])
        for row in art:
            self.assertEqual(len(row), width, "像素心每一行必须一样长")
            self.assertTrue(set(row) <= {"#", "."}, "像素心只允许 # 和 . 两种格子")
            self.assertEqual(row, row[::-1], "像素心必须左右对称")
        self.assertEqual(art[0][width // 2 - 1: width // 2 + 1], "..",
                         "心形顶部中间要留出凹口，否则看着像个三角形")
        self.assertIn("#", art[-1], "心形底部要有尖")

    def test_heart_surface_matches_the_grid(self):
        """渲染出来的心和网格一一对应：格子在就是实心，不在就是透明。"""
        size = 40
        image = ui.heart_surface(size, config.COLOR_HP)
        self.assertEqual(image.get_width(), size)
        self.assertEqual(image.get_height(), int(round(size * ui.HEART_ASPECT)))

        def opaque(col, row):
            x = int((col + 0.5) * image.get_width() / float(ui.HEART_COLS))
            y = int((row + 0.5) * image.get_height() / float(ui.HEART_ROWS))
            return image.get_at((x, y)).a > 0

        for row in range(ui.HEART_ROWS):
            for col in range(ui.HEART_COLS):
                self.assertEqual(opaque(col, row),
                                 config.HEART_PIXEL_ART[row][col] == "#",
                                 "第 %d 行第 %d 格和图案对不上" % (row, col))

    def test_lost_heart_is_an_empty_outline(self):
        """已经失去的那颗心只剩外沿：内部镂空，和实心的一眼能区分。"""
        image = ui.heart_surface(40, config.COLOR_HP_LOST, filled=False)
        solid = ui.heart_surface(40, config.COLOR_HP, filled=True)

        def opaque(target, col, row):
            x = int((col + 0.5) * target.get_width() / float(ui.HEART_COLS))
            y = int((row + 0.5) * target.get_height() / float(ui.HEART_ROWS))
            return target.get_at((x, y)).a > 0

        hollowed = 0
        for row in range(ui.HEART_ROWS):
            for col in range(ui.HEART_COLS):
                if config.HEART_PIXEL_ART[row][col] != "#":
                    continue
                self.assertTrue(opaque(solid, col, row), "实心心不该有缺口")
                if not opaque(image, col, row):
                    hollowed += 1
        self.assertGreater(hollowed, 0, "已经失去的心应该只剩轮廓，内部是空的")

    def test_hud_hearts_are_pixel_hearts(self):
        """HUD 那一排生命值画的也是像素心：还有的用亮色、失去的用暗色。"""
        surface = pygame.display.get_surface()
        surface.fill((0, 0, 0))
        size, gap = 20, 8
        height = int(size * ui.HEART_ASPECT)
        width = ui.draw_hearts(surface, (40, 40), 2, 3, size=size, gap=gap)
        self.assertEqual(width, 3 * size + 2 * gap, "返回的整排宽度不对")

        def pixels_of(index):
            rect = pygame.Rect(40 + index * (size + gap), 40 - height // 2, size, height)
            return [surface.get_at((x, y))[:3]
                    for x in range(rect.left, rect.right)
                    for y in range(rect.top, rect.bottom)]

        self.assertIn(config.COLOR_HP, pixels_of(0), "还剩的那颗应该是亮色的心")
        self.assertIn(config.COLOR_HP_LOST, pixels_of(2), "失去的那颗应该是暗色的心")
        self.assertNotIn(config.COLOR_HP, pixels_of(2), "失去的那颗不该还是亮的")


def _char_direction(char):
    """关卡布局里的字符 -> 方向名；空格或未知字符返回 None。"""
    return {">": "right", "<": "left", "^": "up", "v": "down"}.get(char)


def same_color_cluster(level):
    """统计一关里「相邻且同向」的箭头对占比，以及同方向连通块的最大格子数。

    相邻指上下左右；同向的两支箭头挨在一起，屏幕上就是两块同色贴在一起。
    返回 (占比, 最大块)。占比在方向完全随机时约 0.25，方向交错排可以接近 0。
    """
    grid = {}
    for row, line in enumerate(level.layout):
        for col, char in enumerate(line):
            direction = _char_direction(char)
            if direction is not None:
                grid[(row, col)] = direction

    pair = same = 0
    for (row, col), direction in grid.items():
        for d_row, d_col in ((1, 0), (0, 1)):
            other = grid.get((row + d_row, col + d_col))
            if other is None:
                continue
            pair += 1
            if other == direction:
                same += 1

    seen = set()
    biggest = 0
    for start in grid:
        if start in seen:
            continue
        direction = grid[start]
        stack = [start]
        seen.add(start)
        size = 0
        while stack:
            row, col = stack.pop()
            size += 1
            for d_row, d_col in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                nxt = (row + d_row, col + d_col)
                if nxt not in seen and grid.get(nxt) == direction:
                    seen.add(nxt)
                    stack.append(nxt)
        biggest = max(biggest, size)

    return (same / float(pair) if pair else 0.0), biggest


def main():
    suite = unittest.TestLoader().loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
