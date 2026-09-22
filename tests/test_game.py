# -*- coding: utf-8 -*-
"""自动化测试：覆盖作业要求中的 T01~T06 六个测试用例，外加边界检查、
关卡平衡、配色、进度解锁、竖屏布局与交互、教学关引导。

运行方式（在项目根目录下执行）：
    python tests/test_game.py
    python -m unittest discover -s tests -v

说明：T04~T06 与布局/交互用例需要创建窗口，这里把 SDL 视频驱动切成 dummy，
做到无头运行，所以在没有显示器的机器上也能跑。

T01~T06 的对应关系：
    T01  箭头前方无阻挡          -> 点击后整支箭头飞出被消除
    T02  箭头前方有别的箭头       -> 飞不出去，并扣 1 点生命值
    T03  箭头朝棋盘外（含边角）   -> 算作无阻挡，可以飞出，且不越界
    T04  点击空格                -> 什么都不发生（不扣生命值、不消除）
    T05  生命值耗尽              -> 本关失败、不得分
    T06  清空全部箭头            -> 通关、按剩余生命值计分、解锁下一关

关于「箭头」这个词：这一版的一支「箭」是一条占好几格的折线箭头，末端是箭头。
所以测试里凡是点格子，点它身上的**任意一格**都应该选中整支箭头——
这是这一版最容易被写错的地方，专门有几个用例钉住它。
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

import pygame  # noqa: E402

from game import anim, bgfx, config, levels, pieces, scoring, ui  # noqa: E402
from game.app import (DEMO_BLOCKED_CAPTION, DEMO_BLOCKED_SPECS,  # noqa: E402
                      DEMO_CLEAR_CAPTION, DEMO_CLEAR_SPECS, DEMO_COLORS,
                      DEMO_ROWS, DEMO_COLS, OVERLAY_ALL_CLEAR, OVERLAY_FAIL,
                      OVERLAY_SETTINGS, OVERLAY_TUTORIAL_DONE, OVERLAY_WIN,
                      PANEL_HEIGHT, SCENE_LEVELS, SCENE_MENU, SCENE_PLAY, Game,
                      demo_pieces)
from game.board import (CLICK_BLOCKED, CLICK_EMPTY, CLICK_FLY,  # noqa: E402
                        CLICK_IGNORED, STATE_CLEARED, STATE_FAILED,
                        STATE_PLAYING, Board, count_free_pieces, solve_level)
from game.levels import (HP_BY_STARS, LEVELS, TOTAL_LEVELS, TUTORIAL,  # noqa: E402
                         Level, TutorialStep, validate_levels)
from game.pieces import DIR_CHARS, DIRECTIONS, PIECE_PALETTE, Piece  # noqa: E402
from game.progress import Progress  # noqa: E402

FRAME = 1.0 / 60.0

# 跑完一整关 + 等结果面板弹出来，需要跨过 config.RESULT_DELAY 这道坎。
_RESULT_FRAMES = int(config.RESULT_DELAY / FRAME) + 20


# ---------------------------------------------------------------- 测试用小工具
def make_level(specs, rows, cols, name="测试关卡", hint="", **extra):
    """按关卡数据构造一个 Level（构造时就会跑一遍 validate_layout）。"""
    return Level(name=name, hint=hint, rows=rows, cols=cols,
                 specs=tuple(specs), **extra)


def piece_at_head(level, row, col):
    """取「头在 (row, col)」的那支箭。"""
    for piece in level.pieces:
        if piece.head == (row, col):
            return piece
    raise KeyError("没有头在 (%d, %d) 的箭头" % (row, col))


def level_index(name):
    """按关卡名查下标。

    关号会随着「插一关 / 删一关」整体前移或后移，写死的数字会静默指错关卡
    （测试还照常通过，只是测的已经不是原来那一关了），所以一律按名字查。
    """
    for index, level in enumerate(LEVELS):
        if level.name == name:
            return index
    raise KeyError("没有叫「%s」的关卡" % name)


def neighbour_pairs(level):
    """返回所有「两支箭头有一格上下左右相邻」的组合（用于配色检查）。"""
    owner = {}
    for index, piece in enumerate(level.pieces):
        for cell in piece.cells:
            owner[cell] = index
    pairs = set()
    for (row, col), index in owner.items():
        for d_row, d_col in DIRECTIONS.values():
            other = owner.get((row + d_row, col + d_col))
            if other is not None and other != index:
                pairs.add((min(index, other), max(index, other)))
    return pairs


# ---------------------------------------------------------------- T01~T03 规则
# 三支箭头，摆成一个「挡住 -> 让路 -> 都能飞」的小局面：
#     A "2,0 > R2"  横躺三格，箭头朝右，正前方 (2,3) 是 B 的身子   -> 被挡
#     B "2,3 v D2"  竖着三格，箭头朝下，前方一路空到盘外           -> 能飞
#     C "0,4 v D"   竖着两格，箭头朝下，也是通的                   -> 能飞
BASIC_SPECS = ("2,0 > R2", "2,3 v D2", "0,4 v D")
BASIC_ROWS, BASIC_COLS = 5, 5

# 四条边上的箭头都朝向棋盘外，用来验证边界判断（T03）
EDGE_SPECS = ("0,0 ^", "0,3 v", "1,4 >", "3,4 <")
EDGE_ROWS, EDGE_COLS = 4, 5


class BoardRuleTestCase(unittest.TestCase):
    """棋盘规则（纯逻辑，不需要 pygame）。"""

    # ------------------------------------------------------------ 写法解析
    def test_parse_single_cell_piece(self):
        """不带路径段的写法 = 只占一格。"""
        cells, direction = pieces.parse_piece("3,4 ^")
        self.assertEqual(cells, ((3, 4),))
        self.assertEqual(direction, "up")

    def test_parse_multi_segment_path(self):
        """路径按「方向字母 + 格数」累加，从尾到头有序。"""
        cells, direction = pieces.parse_piece("4,6 > D2R2")
        # 起点 (4,6)，先向下 2 格到 (6,6)，再向右 2 格到 (6,8)
        self.assertEqual(cells, ((4, 6), (5, 6), (6, 6), (6, 7), (6, 8)))
        self.assertEqual(direction, "right")

    def test_parse_default_segment_count_is_one(self):
        """字母后面不写数字就是走一格。"""
        cells, _ = pieces.parse_piece("0,0 > DRD")
        self.assertEqual(cells, ((0, 0), (1, 0), (1, 1), (2, 1)))

    def test_parse_downward_piece_is_not_broken_by_upper(self):
        """朝下的 'v' 不能被 upper() 变成 'V' 而解析失败。

        这是一个真实发生过的 bug：整串 upper() 之后 'v' 变成 'V'，
        方向表里认的是小写 'v'，于是所有朝下的箭头都没法解析。
        """
        for char in ("v",):
            cells, direction = pieces.parse_piece("1,1 %s D" % char)
            self.assertEqual(direction, "down")
            self.assertEqual(cells, ((1, 1), (2, 1)))

    def test_parse_accepts_lowercase_path_and_extra_spaces(self):
        """关卡数据是手写与脚本混着的，大小写与多余空格都要能吃下。"""
        cells, direction = pieces.parse_piece("  2,2   v   d2  ")
        self.assertEqual(direction, "down")
        self.assertEqual(cells, ((2, 2), (3, 2), (4, 2)))

    def test_parse_rejects_bad_specs(self):
        for bad in ("", "abc", "1,2", "1,2 X", "-1,0 ^", "1,2 > ZZ"):
            with self.assertRaises(ValueError, msg="应当拒绝 %r" % bad):
                pieces.parse_piece(bad)

    def test_format_piece_round_trip(self):
        """format_piece 是 parse_piece 的逆运算，生成器靠它打印布局。

        注意它是**会把连续同向的步子合并**的：D,R,D,R 不会被合成 "D2R2"
        （中间隔着拐弯），只有像 D,D 这种才写成 "D2"。
        """
        cells = ((0, 0), (1, 0), (1, 1), (2, 1), (2, 2))
        text = pieces.format_piece(cells, "right")
        self.assertEqual(text, "0,0 > DRDR")
        again, direction = pieces.parse_piece(text)
        self.assertEqual(again, cells)
        self.assertEqual(direction, "right")

    def test_format_piece_merges_repeated_steps(self):
        cells = ((0, 0), (1, 0), (2, 0), (2, 1), (2, 2))
        self.assertEqual(pieces.format_piece(cells, "right"), "0,0 > D2R2")

    def test_format_piece_rejects_diagonal_step(self):
        with self.assertRaises(ValueError):
            pieces.format_piece(((0, 0), (1, 1)), "right")

    def test_piece_head_tail_and_length(self):
        piece = Piece(cells=((0, 0), (0, 1), (0, 2)), direction="right")
        self.assertEqual(piece.head, (0, 2))
        self.assertEqual(piece.tail, (0, 0))
        self.assertEqual(piece.length, 3)
        self.assertEqual(piece.delta, (0, 1))

    def test_piece_ray_stops_at_board_edge(self):
        """射线从箭头出发、直到棋盘边界，且**不含箭头自己**。"""
        piece = Piece(cells=((0, 0), (0, 1)), direction="right")
        self.assertEqual(piece.ray(1, 5), [(0, 2), (0, 3), (0, 4)])
        self.assertEqual(piece.ray(1, 2), [])
        down = Piece(cells=((0, 0),), direction="down")
        self.assertEqual(down.ray(3, 1), [(1, 0), (2, 0)])

    # ------------------------------------------------------------ 布局校验
    def test_validate_layout_accepts_good_level(self):
        parsed = [Piece(cells=pieces.parse_piece(s)[0], direction=pieces.parse_piece(s)[1])
                  for s in BASIC_SPECS]
        self.assertTrue(pieces.validate_layout(BASIC_ROWS, BASIC_COLS, parsed))

    def test_validate_layout_rejects_empty_level(self):
        with self.assertRaises(ValueError):
            pieces.validate_layout(3, 3, [])

    def test_validate_layout_rejects_out_of_board(self):
        bad = [Piece(cells=((0, 0), (0, 1), (0, 2)), direction="right")]
        with self.assertRaises(ValueError):
            pieces.validate_layout(1, 2, bad)

    def test_validate_layout_rejects_overlap(self):
        bad = [Piece(cells=((0, 0),), direction="right"),
               Piece(cells=((0, 0),), direction="left")]
        with self.assertRaises(ValueError):
            pieces.validate_layout(2, 2, bad)

    def test_validate_layout_rejects_broken_path(self):
        """路径必须逐格相邻，不能跳格。"""
        bad = [Piece(cells=((0, 0), (0, 2)), direction="right")]
        with self.assertRaises(ValueError):
            pieces.validate_layout(2, 4, bad)

    def test_validate_layout_rejects_self_crossing(self):
        bad = [Piece(cells=((0, 0), (1, 0), (1, 1), (0, 1), (0, 0)), direction="left")]
        with self.assertRaises(ValueError):
            pieces.validate_layout(3, 3, bad)

    def test_validate_layout_rejects_head_direction_mismatch(self):
        """最后一段必须和箭头方向一致，否则画出来的箭头会歪在拐角上。"""
        bad = [Piece(cells=((0, 0), (1, 0)), direction="right")]
        with self.assertRaises(ValueError):
            pieces.validate_layout(3, 3, bad)

    def test_validate_layout_rejects_piece_facing_own_body(self):
        """箭头正对着自己的箭头 -> 永远飞不出去，必须在关卡校验里拦掉。

        形状是一条绕回来的箭头：从 (0,0) 一路向右、向下、再向左绕回 (1,1)，
        箭头朝上，正前方 (0,1) 就是自己身上的一格。
        这一支的**末段方向与箭头是一致的**，所以触发的一定是
        「箭头正对自己」这条规则，而不是「末段不一致」那条。
        """
        spiral = ((0, 0), (0, 1), (0, 2), (0, 3), (1, 3), (2, 3), (2, 2), (2, 1), (1, 1))
        bad = [Piece(cells=spiral, direction="up")]
        self.assertEqual(bad[0].head, (1, 1))
        self.assertIn((0, 1), bad[0].ray(4, 4))            # 射线确实穿过自己
        self.assertTrue(pieces.faces_own_body(bad[0], 4, 4))
        with self.assertRaises(ValueError):
            pieces.validate_layout(4, 4, bad)

    def test_faces_own_body_false_for_clean_shape(self):
        ok = Piece(cells=((2, 0), (2, 1), (2, 2)), direction="right")
        self.assertFalse(pieces.faces_own_body(ok, 5, 5))

    def test_build_grid_marks_owner_index(self):
        parsed = [Piece(cells=pieces.parse_piece(s)[0], direction=pieces.parse_piece(s)[1])
                  for s in BASIC_SPECS]
        grid = pieces.build_grid(BASIC_ROWS, BASIC_COLS, parsed)
        self.assertEqual(grid[2][0], 0)
        self.assertEqual(grid[2][2], 0)
        self.assertEqual(grid[2][3], 1)
        self.assertIsNone(grid[4][0])

    # ------------------------------------------------------------ 配色
    def test_assign_colors_gives_every_piece_a_palette_color(self):
        level = make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS)
        for piece in level.pieces:
            self.assertIn(piece.color, PIECE_PALETTE)

    def test_adjacent_pieces_never_share_a_color(self):
        """相邻箭头同色会「糊成一片」，看不出是几支——所有关卡都要守住这条。"""
        for level in list(LEVELS) + [TUTORIAL]:
            for left, right in neighbour_pairs(level):
                self.assertNotEqual(level.pieces[left].color, level.pieces[right].color,
                                    "「%s」里第 %d 支和第 %d 支同色" % (level.name, left, right))

    def test_assign_colors_is_deterministic(self):
        """同样的布局必须得到同样的配色，否则每次打开画面都不一样。"""
        first = make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS).pieces
        second = make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS).pieces
        self.assertEqual([p.color for p in first], [p.color for p in second])

    # ------------------------------------------------------------ T01 无阻挡
    def test_t01_free_piece_flies_out_and_disappears(self):
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        target = board.piece_at(2, 3)                  # 竖着那支，箭头朝下
        result = board.click(2, 3)
        self.assertEqual(result.kind, CLICK_FLY)
        self.assertIs(result.piece, target)
        self.assertIsNone(result.blocker)
        self.assertIsNone(board.piece_at(2, 3))
        self.assertEqual(board.remaining, 2)
        self.assertEqual(board.hp, board.max_hp)       # 点对不扣生命值
        self.assertEqual(len(board.history), 1)

    def test_clicking_any_cell_of_a_pipe_selects_the_whole_pipe(self):
        """点箭头的哪一格都算选中它——玩家看到的是整条箭头。"""
        for row, col in ((2, 3), (3, 3), (4, 3)):
            board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
            result = board.click(row, col)
            self.assertEqual(result.kind, CLICK_FLY, "点 (%d,%d) 应当消除整条箭头" % (row, col))
            self.assertEqual(board.remaining, 2)
            # 整条箭头三格都要被清空，不能只清点中的那一格
            for r, c in ((2, 3), (3, 3), (4, 3)):
                self.assertIsNone(board.piece_at(r, c))

    # ------------------------------------------------------------ T02 被挡
    def test_t02_blocked_piece_loses_one_heart(self):
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        target = board.piece_at(2, 0)                  # 横躺那支，正前方有箭头
        result = board.click(2, 0)
        self.assertEqual(result.kind, CLICK_BLOCKED)
        self.assertIs(result.piece, target)
        self.assertIsNotNone(result.blocker)
        # 挡住它的是竖着那支（身子压在 (2,3)，箭头在 (4,3)）；
        # 这里比对的是**整支箭头**，不是被碰上的那一格。
        self.assertEqual(result.blocker.cells, ((2, 3), (3, 3), (4, 3)))
        self.assertIn(result.blocker, board.pieces)
        self.assertEqual(board.hp, board.max_hp - 1)
        self.assertEqual(board.hearts_lost, 1)
        self.assertEqual(board.remaining, 3)           # 没被消除
        self.assertIsNotNone(board.piece_at(2, 0))

    def test_t02_blocker_is_the_nearest_piece_on_the_ray(self):
        """射线上可能有好几支箭头，挡住它的应当是**最先遇到**的那一支。

        而且挡路的往往是那支箭头的**身子**，它的箭头可能在别的地方——
        下面 (1,1) 那支的头就落在 (2,1)，不在射线上。
        （界面早先直接 `path.index(blocker.head)` 画悬停路径，遇到这种就会崩。）
        """
        level = make_level(("1,0 >", "1,1 v D", "1,3 v"), 3, 4)
        board = Board(level)
        result = board.click(1, 0)
        self.assertEqual(result.kind, CLICK_BLOCKED)
        self.assertEqual(result.blocker.head, (2, 1))
        self.assertNotIn(result.blocker.head, result.path,
                         "这一例的意义就在于「挡路的格子不是它的箭头」")
        self.assertEqual(result.path, [(1, 1), (1, 2), (1, 3)])

    def test_path_to_blocker_stops_at_the_nearest_piece(self):
        """悬停路径要截断在挡路那一格，再往后跟「为什么飞不出去」无关。"""
        level = make_level(("1,0 >", "1,1 v D", "1,3 v"), 3, 4)
        board = Board(level)
        piece = board.piece_at(1, 0)
        path, blocker = board.path_to_blocker(piece)
        self.assertEqual(path, [(1, 1)])
        self.assertEqual(blocker.head, (2, 1))

    def test_path_to_blocker_returns_the_whole_ray_when_clear(self):
        level = make_level(("1,0 >", "1,1 v D"), 3, 4)
        board = Board(level)
        board.click(1, 1)                              # 先让路走开
        path, blocker = board.path_to_blocker(board.piece_at(1, 0))
        self.assertEqual(path, [(1, 1), (1, 2), (1, 3)])
        self.assertIsNone(blocker)

    def test_t02_blocking_piece_moves_away_then_it_can_fly(self):
        """把挡路的点掉之后，原本被挡的那支就能飞了（连锁的最小例子）。"""
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        self.assertEqual(board.click(2, 0).kind, CLICK_BLOCKED)   # 起初被 B 挡着
        self.assertIsNotNone(board.piece_at(2, 0))                # 被挡不会消失
        self.assertEqual(board.click(2, 3).kind, CLICK_FLY)       # 点掉挡路的 B
        result = board.click(2, 0)                                # 这回轮到 A 了
        self.assertEqual(result.kind, CLICK_FLY)
        self.assertIsNone(board.piece_at(2, 0))
        self.assertEqual(board.remaining, 1)

    def test_find_blocker_ignores_the_pieces_own_body(self):
        """箭头绕回来贴着自己的箭头前方时，不算「被自己挡住」。

        取一支真实关卡里形状恰好如此的箭头来验证：它的射线会经过自己的某一格，
        但 find_blocker 只认**别的**箭头。
        """
        hits = 0
        for level in LEVELS:
            board = Board(level)
            for piece in board.pieces:
                own = set(piece.cells)
                if own & set(piece.ray(board.rows, board.cols)):
                    continue                           # 关卡校验不允许这种形状
                blocker = board.find_blocker(piece)
                if blocker is not None:
                    self.assertIsNot(blocker, piece)
                    hits += 1
            board.reset()
        self.assertGreater(hits, 0, "至少要有一个被挡的例子，否则这条断言没测到东西")

    def test_click_result_carries_the_ray_path(self):
        """点击结果要带上「箭头前方直到边界」的格子，界面靠它画路径提示。"""
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        result = board.click(2, 0)
        self.assertEqual(result.path, [(2, 3), (2, 4)])

    # ------------------------------------------------------------ T03 边界
    def test_t03_pieces_at_edges_face_outward_and_can_fly(self):
        board = Board(make_level(EDGE_SPECS, EDGE_ROWS, EDGE_COLS))
        self.assertEqual(board.remaining, 4)
        for piece in list(board.pieces):
            self.assertTrue(board.can_fly(piece),
                            "朝棋盘外的箭头应当能飞：%r" % (piece.cells,))
        for row, col in ((0, 0), (0, 3), (1, 4), (3, 4)):
            self.assertEqual(board.click(row, col).kind, CLICK_FLY)
        self.assertEqual(board.remaining, 0)
        self.assertEqual(board.state, STATE_CLEARED)

    def test_edge_ray_does_not_run_off_the_board(self):
        """边上的射线只到边界为止，不能越界算出负坐标或越界的格子。"""
        for direction, head, rows, cols in (
                ("up", (0, 2), 3, 4),
                ("down", (2, 2), 3, 4),
                ("left", (1, 0), 3, 4),
                ("right", (1, 3), 3, 4)):
            piece = Piece(cells=(head,), direction=direction)
            self.assertEqual(piece.ray(rows, cols), [])

    def test_ray_covers_corner_pieces_correctly(self):
        piece = Piece(cells=((0, 0),), direction="right")
        self.assertEqual(piece.ray(3, 3), [(0, 1), (0, 2)])

    # ------------------------------------------------------------ T04 空格
    def test_clicking_empty_cell_does_nothing(self):
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        before = (board.remaining, board.hp, board.state)
        result = board.click(4, 0)                     # 空格
        self.assertEqual(result.kind, CLICK_EMPTY)
        self.assertIsNone(result.piece)
        self.assertEqual((board.remaining, board.hp, board.state), before)

    def test_click_outside_board_is_ignored(self):
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        for row, col in ((-1, 0), (0, -1), (BASIC_ROWS, 0), (0, BASIC_COLS)):
            self.assertEqual(board.click(row, col).kind, CLICK_IGNORED)
        self.assertEqual(board.hp, board.max_hp)

    # ------------------------------------------------------------ T05 失败
    def test_running_out_of_hearts_fails_the_level(self):
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        for _ in range(board.max_hp - 1):
            self.assertEqual(board.click(2, 0).kind, CLICK_BLOCKED)
            self.assertEqual(board.state, STATE_PLAYING)
        self.assertEqual(board.click(2, 0).kind, CLICK_BLOCKED)
        self.assertEqual(board.state, STATE_FAILED)
        self.assertEqual(board.hp, 0)

    def test_clicks_after_failure_are_ignored(self):
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        for _ in range(board.max_hp):
            board.click(2, 0)
        self.assertEqual(board.state, STATE_FAILED)
        self.assertEqual(board.click(2, 3).kind, CLICK_IGNORED)
        self.assertEqual(board.remaining, 3)

    # ------------------------------------------------------------ T06 通关
    def test_clearing_every_piece_clears_the_level(self):
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        order = board.solution()
        self.assertIsNotNone(order)
        self.assertEqual(len(order), 3)
        for piece in order:
            self.assertEqual(board.click(*piece.head).kind, CLICK_FLY)
        self.assertEqual(board.remaining, 0)
        self.assertEqual(board.state, STATE_CLEARED)

    def test_clicks_after_clearing_are_ignored(self):
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        for piece in board.solution():
            board.click(*piece.head)
        self.assertEqual(board.click(0, 0).kind, CLICK_IGNORED)

    def test_reset_restores_initial_state(self):
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        board.click(2, 3)
        board.click(2, 0)
        board.reset()
        self.assertEqual(board.remaining, 3)
        self.assertEqual(board.hp, board.max_hp)
        self.assertEqual(board.state, STATE_PLAYING)
        self.assertEqual(board.history, [])
        self.assertIsNotNone(board.piece_at(2, 3))

    def test_hp_left_and_hearts_lost_are_consistent(self):
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        self.assertEqual(board.hp_left + board.hearts_lost, board.max_hp)
        board.click(2, 0)
        self.assertEqual(board.hp_left + board.hearts_lost, board.max_hp)

    def test_score_drops_as_hearts_are_lost(self):
        """棋盘上的 score 是「此刻通关能拿多少」，丢心就往下掉。"""
        board = Board(make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS))
        full = board.score
        board.click(2, 0)
        self.assertLess(board.score, full)


# ---------------------------------------------------------------- 求解器
class SolverTestCase(unittest.TestCase):
    """贪心求解器：判断关卡有没有解，并给出一条通关顺序。"""

    def test_solve_simple_level(self):
        level = make_level(BASIC_SPECS, BASIC_ROWS, BASIC_COLS)
        order = solve_level(level.rows, level.cols, level.pieces)
        self.assertIsNotNone(order)
        self.assertEqual(len(order), 3)
        self.assertEqual({p.head for p in order},
                         {(2, 2), (4, 3), (1, 4)})

    def test_two_pieces_facing_each_other_are_unsolvable(self):
        """互相指着的两支谁也飞不出去——求解器必须报「无解」而不是死循环。"""
        stuck = (Piece(cells=((0, 0),), direction="right", uid=0),
                 Piece(cells=((0, 1),), direction="left", uid=1))
        self.assertIsNone(solve_level(1, 4, stuck))

    def test_solver_order_actually_clears_the_board(self):
        """求解器给出的顺序拿去真的点一遍，必须能清空。"""
        for level in list(LEVELS) + [TUTORIAL]:
            board = Board(level)
            order = solve_level(board.rows, board.cols, board.pieces)
            self.assertIsNotNone(order, "「%s」应当有解" % level.name)
            for piece in order:
                result = board.click(*piece.head)
                self.assertEqual(result.kind, CLICK_FLY,
                                 "「%s」按参考顺序点 (%d,%d) 却没飞出去"
                                 % (level.name, piece.head[0], piece.head[1]))
            self.assertEqual(board.state, STATE_CLEARED)

    def test_solver_is_monotonic(self):
        """消除一支箭头只会让别的射线更空，所以「能飞」不会因为等待而失效。

        这条性质是贪心求解正确性的根基，用它做一次随机自检：
        开局能飞的箭头，在消掉任意其它箭头之后依然能飞。
        """
        rng = random.Random(20260922)
        for level in LEVELS[:5]:
            board = Board(level)
            free = board.available_arrows()
            self.assertTrue(free)
            victim = rng.choice(free)
            for other in board.solution():
                if other is victim or board.piece_at(*victim.head) is None:
                    continue
                board.click(*other.head)
                if board.piece_at(*victim.head) is None:
                    break
                self.assertTrue(board.can_fly(victim),
                                "「%s」里等了一会儿就不让飞了" % level.name)

    def test_solver_rejects_a_layout_with_no_free_piece(self):
        """一个连开局都点不动的循环，应当被判定为无解。"""
        cycle = (Piece(cells=((0, 0),), direction="right", uid=0),
                 Piece(cells=((0, 2),), direction="left", uid=1))
        # 0 号头在 (0,0) 朝右 -> 射线 (0,1) (0,2)，被 1 号占着
        # 1 号头在 (0,2) 朝左 -> 射线 (0,1) (0,0)，被 0 号占着
        self.assertIsNone(solve_level(1, 3, cycle))

    def test_count_free_pieces_matches_board_query(self):
        for level in list(LEVELS) + [TUTORIAL]:
            board = Board(level)
            self.assertEqual(count_free_pieces(board.rows, board.cols, board.pieces),
                             len(board.available_arrows()),
                             "「%s」的可点数两处算得不一样" % level.name)

    def test_count_free_pieces_is_monotonic_after_removing_a_piece(self):
        """每消掉一支，可点数只可能变多或不变（不会变少）。"""
        for level in LEVELS[:5]:
            board = Board(level)
            previous = len(board.available_arrows())
            for piece in board.solution():
                board.click(*piece.head)
                now = len(board.available_arrows())
                self.assertGreaterEqual(now, previous - 1)
                previous = now


# ---------------------------------------------------------------- 关卡数据
class LevelBalanceTestCase(unittest.TestCase):
    """关卡数据本身的质量：数量、尺寸、难度是否逐关递增、是否都可解。"""

    def test_level_count_and_names(self):
        self.assertEqual(TOTAL_LEVELS, 9)
        names = [level.name for level in LEVELS]
        self.assertEqual(len(set(names)), TOTAL_LEVELS, "关卡名不能重复")
        for level in LEVELS:
            self.assertTrue(level.hint.strip(), "「%s」没有提示语" % level.name)

    def test_every_level_is_solvable(self):
        for level in LEVELS:
            self.assertIsNotNone(level.solution(), "「%s」无解" % level.name)

    def test_solution_covers_every_piece_exactly_once(self):
        for level in LEVELS:
            order = level.solution()
            self.assertEqual(len(order), level.arrow_count)
            self.assertEqual(len({id(p) for p in order}), level.arrow_count)

    def test_boards_are_portrait(self):
        """九关都取竖长方形（行数 > 列数）。

        窗口 600×960 是手机竖屏比例，竖棋盘才能把视口填满；
        横过来的话上下会各空出一条，画面看着像没铺开。
        """
        for level in LEVELS:
            self.assertGreater(level.rows, level.cols,
                               "「%s」不是竖长方形：%d×%d" % (level.name, level.rows, level.cols))

    def test_board_size_grows_with_level_number(self):
        sizes = [(level.rows, level.cols) for level in LEVELS]
        for earlier, later in zip(sizes, sizes[1:]):
            self.assertLess(earlier[0] * earlier[1], later[0] * later[1],
                            "棋盘面积应当逐关变大：%r -> %r" % (earlier, later))
            self.assertLessEqual(earlier[0], later[0])
            self.assertLessEqual(earlier[1], later[1])

    def test_piece_count_grows_with_level_number(self):
        """箭头数整体上一路变多。

        允许相邻两关偶尔差一支（棋盘形状不同，铺满同一块面积需要的箭头数
        本来就会有出入——第 3 关棋盘更大、却比第 2 关少一支），
        真正决定难度的是「开局可点数」和棋盘面积，那两条另有用例把关。
        """
        counts = [level.arrow_count for level in LEVELS]
        for earlier, later in zip(counts, counts[1:]):
            self.assertGreaterEqual(later, earlier - 2,
                                    "箭头数掉得太多：%r" % (counts,))
        self.assertLess(counts[0], counts[-1])
        self.assertGreaterEqual(counts[-1], counts[0] * 2 - 4)

    def test_boards_are_densely_filled(self):
        """这一版棋盘是密密麻麻铺满的（参照画面就是这样）。"""
        for level in LEVELS:
            self.assertGreater(level.density, 0.90,
                               "「%s」铺满率只有 %.2f，看着太空" % (level.name, level.density))

    def test_free_pieces_never_increase(self):
        """开局可点数逐关不增：这是玩家真正感觉得到的难度。"""
        frees = [level.free_count for level in LEVELS]
        for earlier, later in zip(frees, frees[1:]):
            self.assertGreaterEqual(earlier, later, "开局可点数不该反弹：%r" % (frees,))
        self.assertGreaterEqual(frees[0], 5, "第 1 关开局应当很好找")
        self.assertLessEqual(frees[-1], 3, "最后一关开局应当很难找")

    def test_difficulty_and_stars_never_go_backwards(self):
        stars = [level.stars for level in LEVELS]
        for earlier, later in zip(stars, stars[1:]):
            self.assertLessEqual(earlier, later, "星级不该往回退：%r" % (stars,))
        self.assertEqual(stars[0], 1)
        self.assertEqual(stars[-1], 5)
        difficulties = [level.difficulty_score for level in LEVELS]
        for earlier, later in zip(difficulties, difficulties[1:]):
            self.assertLess(earlier, later, "难度分应当逐关递增：%r" % (difficulties,))

    def test_hp_follows_the_star_table(self):
        for level in LEVELS:
            self.assertEqual(level.max_hp, HP_BY_STARS[level.stars])
        self.assertEqual(min(level.max_hp for level in LEVELS), 4)
        self.assertEqual(max(level.max_hp for level in LEVELS), 7)

    def test_max_score_is_stars_times_300(self):
        for level in LEVELS:
            self.assertEqual(scoring.max_score(level), level.stars * 300)

    def test_total_max_score_is_stable(self):
        self.assertEqual(scoring.total_max_score(LEVELS), 8400)

    def test_level_rejects_invalid_specs_at_construction(self):
        """关卡数据写错时要在 import 阶段就炸，而不是等到玩家点进去。"""
        with self.assertRaises(ValueError):
            make_level(("2,0 > R9",), 3, 3)                     # 跑出棋盘
        with self.assertRaises(ValueError):
            make_level(("1,1 ^", "1,1 v"), 3, 3)                # 重叠
        with self.assertRaises(ValueError):
            make_level(("0,0 > D",), 3, 3)                      # 末段方向与箭头不符

    def test_level_rejects_zero_size(self):
        with self.assertRaises(ValueError):
            make_level(("0,0 ^",), 0, 0)

    # ------------------------------------------------------------ 教学关
    def test_tutorial_is_separate_from_numbered_levels(self):
        """教学关不占编号、不在 LEVELS 里，主菜单上有单独入口。"""
        self.assertTrue(TUTORIAL.tutorial)
        self.assertNotIn(TUTORIAL, LEVELS)
        self.assertEqual(TUTORIAL.max_hp, levels.TUTORIAL_HP)

    def test_tutorial_has_guided_steps(self):
        self.assertGreaterEqual(len(TUTORIAL.steps), 3)
        for step in TUTORIAL.steps:
            self.assertIsInstance(step, TutorialStep)
            self.assertIn(step.expect, ("fly", "blocked"),
                          "教学步骤的期望结果只能是 fly / blocked")
            self.assertTrue(step.text.strip(), "教学步骤要有说明文字")

    def test_tutorial_steps_both_explain_ways(self):
        """教学关必须把「能飞」和「被挡」两种情形各讲一遍。"""
        expects = {step.expect for step in TUTORIAL.steps}
        self.assertEqual(expects, {"fly", "blocked"})

    def test_tutorial_is_solvable_and_small(self):
        self.assertIsNotNone(TUTORIAL.solution())
        self.assertLessEqual(TUTORIAL.arrow_count, 4, "教学关不该摆太多箭头")
        self.assertLessEqual(TUTORIAL.rows * TUTORIAL.cols, 36)

    def test_report_shape(self):
        report = validate_levels()
        self.assertEqual(len(report), TOTAL_LEVELS)
        keys = {"index", "name", "size", "arrows", "density", "free", "solvable",
                "order", "max_hp", "stars", "max_score", "difficulty", "tutorial"}
        for item in report:
            self.assertTrue(keys.issubset(item.keys()))
            self.assertTrue(item["solvable"])
            self.assertFalse(item["tutorial"])


# ---------------------------------------------------------------- 计分
class ScoringTestCase(unittest.TestCase):
    """得分规则：基础分按星级给，再按剩余生命值折算，零失误有奖励。"""

    def test_base_score_is_stars_times_250(self):
        for level in LEVELS:
            self.assertEqual(scoring.base_score(level), level.stars * 250)

    def test_perfect_bonus_is_20_percent_of_base(self):
        for level in LEVELS:
            self.assertEqual(scoring.perfect_bonus(level),
                             int(scoring.base_score(level) * 0.2))

    def test_full_hp_gives_max_score(self):
        for level in LEVELS:
            self.assertEqual(scoring.level_score(level, level.max_hp),
                             scoring.max_score(level))

    def test_zero_hp_gives_zero_score(self):
        for level in LEVELS:
            self.assertEqual(scoring.level_score(level, 0), 0)

    def test_score_never_exceeds_max_and_never_negative(self):
        for level in LEVELS:
            for hp in range(-2, level.max_hp + 3):
                score = scoring.level_score(level, hp)
                self.assertGreaterEqual(score, 0)
                self.assertLessEqual(score, scoring.max_score(level))

    def test_score_is_monotonic_in_remaining_hp(self):
        for level in LEVELS:
            scores = [scoring.level_score(level, hp) for hp in range(level.max_hp + 1)]
            for earlier, later in zip(scores, scores[1:]):
                self.assertLessEqual(earlier, later)

    def test_losing_one_heart_costs_more_than_nothing(self):
        """丢一颗心必须真的掉分，否则「别点错」这件事就没有反馈。"""
        for level in LEVELS:
            self.assertGreater(scoring.level_score(level, level.max_hp - 1),
                               0)
            self.assertLess(scoring.level_score(level, level.max_hp - 1),
                            scoring.max_score(level))

    def test_lost_hearts_helper(self):
        level = LEVELS[0]
        self.assertEqual(scoring.lost_hearts(level, level.max_hp), 0)
        self.assertEqual(scoring.lost_hearts(level, level.max_hp - 2), 2)
        self.assertEqual(scoring.lost_hearts(level, 0), level.max_hp)
        # 越界传参也要夹在合法范围里
        self.assertEqual(scoring.lost_hearts(level, level.max_hp + 5), 0)
        self.assertEqual(scoring.lost_hearts(level, -3), level.max_hp)

    def test_total_max_score_sums_levels(self):
        self.assertEqual(scoring.total_max_score(LEVELS),
                         sum(scoring.max_score(level) for level in LEVELS))


# ---------------------------------------------------------------- 进度
class ProgressTestCase(unittest.TestCase):
    """闯关进度：解锁链、最高分、存档读写。"""

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="oa_test_")
        self.path = os.path.join(self.dir, "progress.json")

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def test_fresh_progress_only_has_level_one_unlocked(self):
        progress = Progress(path=self.path)
        self.assertTrue(progress.is_unlocked(0, TOTAL_LEVELS))
        self.assertFalse(progress.is_unlocked(1, TOTAL_LEVELS))
        self.assertEqual(progress.cleared_count(TOTAL_LEVELS), 0)
        self.assertEqual(progress.next_index(TOTAL_LEVELS), 0)
        self.assertFalse(progress.all_cleared(TOTAL_LEVELS))

    def test_clearing_a_level_unlocks_the_next_one(self):
        progress = Progress(path=self.path)
        progress.mark_cleared(0)
        self.assertTrue(progress.is_cleared(0))
        self.assertTrue(progress.is_unlocked(1, TOTAL_LEVELS))
        self.assertFalse(progress.is_unlocked(2, TOTAL_LEVELS))
        self.assertEqual(progress.next_index(TOTAL_LEVELS), 1)

    def test_scores_keep_the_best_result(self):
        """重玩只留最高分，不会越玩越低。"""
        progress = Progress(path=self.path)
        first = progress.record_score(1, 600)
        self.assertEqual(first, 600, "第一次刷分，全部计入")
        self.assertEqual(progress.best_score(1), 600)
        gain = progress.record_score(1, 300)
        self.assertEqual(gain, 0, "打得更差不该扣分")
        self.assertEqual(progress.best_score(1), 600)
        gain = progress.record_score(1, 900)
        self.assertEqual(gain, 300, "打破纪录时增益应当是差值")
        self.assertEqual(progress.best_score(1), 900)

    def test_total_score_sums_best_scores(self):
        progress = Progress(path=self.path)
        for index, score in ((0, 300), (1, 600), (2, 900)):
            progress.record_score(index, score)
        self.assertEqual(progress.total_score(TOTAL_LEVELS), 1800)

    def test_mark_all_cleared_opens_everything(self):
        progress = Progress(path=self.path)
        progress.mark_all_cleared(TOTAL_LEVELS)
        self.assertEqual(progress.cleared_count(TOTAL_LEVELS), TOTAL_LEVELS)
        self.assertTrue(progress.all_cleared(TOTAL_LEVELS))
        for index in range(TOTAL_LEVELS):
            self.assertTrue(progress.is_unlocked(index, TOTAL_LEVELS))

    def test_save_and_load_round_trip(self):
        progress = Progress(path=self.path)
        progress.mark_cleared(0)
        progress.record_score(0, 300)
        progress.mark_cleared(1)
        progress.record_score(1, 500)
        self.assertTrue(os.path.exists(self.path), "存档文件应当真的写出来了")

        again = Progress(path=self.path)
        self.assertTrue(again.is_cleared(0))
        self.assertTrue(again.is_cleared(1))
        self.assertEqual(again.best_score(0), 300)
        self.assertEqual(again.best_score(1), 500)
        self.assertEqual(again.total_score(TOTAL_LEVELS), 800)

    def test_saved_file_is_valid_json_with_version(self):
        progress = Progress(path=self.path)
        progress.mark_cleared(0)
        progress.save()
        with open(self.path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertIn("version", data)
        self.assertIn("cleared", data)
        self.assertIn("scores", data)

    def test_corrupt_save_file_falls_back_to_fresh_progress(self):
        """存档坏了不能让游戏打不开——退回全新进度就好。"""
        with open(self.path, "w", encoding="utf-8") as handle:
            handle.write("{ 这不是 JSON")
        progress = Progress(path=self.path)
        self.assertEqual(progress.cleared_count(TOTAL_LEVELS), 0)

    def test_save_file_with_wrong_shapes_is_sanitised(self):
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump({"version": 2, "cleared": [1, "x", 99, -1], "scores": {"1": "abc"}},
                      handle)
        progress = Progress(path=self.path)
        self.assertTrue(progress.is_cleared(1))
        for index in range(TOTAL_LEVELS):
            self.assertIsInstance(progress.best_score(index), int)
            self.assertGreaterEqual(progress.best_score(index), 0)

    def test_reset_clears_everything(self):
        progress = Progress(path=self.path)
        progress.mark_cleared(0)
        progress.record_score(0, 300)
        progress.reset()
        self.assertEqual(progress.cleared_count(TOTAL_LEVELS), 0)
        self.assertEqual(progress.best_score(0), 0)
        self.assertFalse(progress.is_unlocked(1, TOTAL_LEVELS))

    def test_best_score_of_unknown_level_is_zero(self):
        progress = Progress(path=self.path)
        self.assertEqual(progress.best_score(4), 0)
        self.assertFalse(progress.is_cleared(4))

    def test_clearing_is_idempotent(self):
        progress = Progress(path=self.path)
        progress.mark_cleared(0)
        progress.mark_cleared(0)
        self.assertEqual(progress.cleared_count(TOTAL_LEVELS), 1)


# ---------------------------------------------------------------- 绘制原语
class RenderPrimitiveTestCase(unittest.TestCase):
    """界面绘制的基础件：箭头贴图、字体折行、滑杆、像素心、动画。"""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        ui.clear_caches()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_piece_surface_is_cached(self):
        """同一支箭头重复取贴图必须命中缓存，否则每帧都在重新渲染。"""
        cells, direction = pieces.parse_piece("0,0 > R2")
        color = PIECE_PALETTE[0]
        first = ui.piece_surface(cells, direction, color, 40)
        second = ui.piece_surface(cells, direction, color, 40)
        self.assertIs(first, second)

    def test_piece_surface_differs_by_cell_size(self):
        cells, direction = pieces.parse_piece("0,0 > R2")
        color = PIECE_PALETTE[0]
        small = ui.piece_surface(cells, direction, color, 24)[0]
        large = ui.piece_surface(cells, direction, color, 48)[0]
        self.assertGreater(large.get_width(), small.get_width())
        self.assertGreater(large.get_height(), small.get_height())

    def test_piece_surface_geometry_places_each_cell_correctly(self):
        """贴图 + 偏移必须能把每一格摆回它该在的位置。

        约定是：把贴图贴到「棋盘左上角 + 偏移」，管线起点那一格的**中心**
        就正好落在 棋盘左上角 + (min_col + 0.5) * 格距。留白左右对称，
        所以从「贴图宽度 - 箭头实际跨度」就能反推出留白是多少。
        """
        cells, direction = pieces.parse_piece("2,1 v D2")     # (2,1) (3,1) (4,1)
        cell = 32
        image, (dx, dy) = ui.build_piece_surface(cells, direction, PIECE_PALETTE[2], cell)
        span_w = 1 * cell
        span_h = 3 * cell
        pad_x = (image.get_width() - span_w) / 2.0
        pad_y = (image.get_height() - span_h) / 2.0
        self.assertGreater(pad_x, 0, "贴图要留白，不然描边和箭头尖会被裁掉")
        self.assertAlmostEqual(dx, 1 * cell - pad_x, delta=1.5)
        self.assertAlmostEqual(dy, 2 * cell - pad_y, delta=1.5)

    def test_piece_surface_big_enough_for_the_whole_pipe(self):
        for level in LEVELS[:4]:
            for piece in level.pieces:
                image, _ = ui.build_piece_surface(piece.cells, piece.direction,
                                                  piece.color, 24)
                rows = [row for row, _ in piece.cells]
                cols = [col for _, col in piece.cells]
                self.assertGreaterEqual(image.get_width(), (max(cols) - min(cols) + 1) * 24)
                self.assertGreaterEqual(image.get_height(), (max(rows) - min(rows) + 1) * 24)

    def test_piece_color_falls_back_to_palette(self):
        bare = Piece(cells=((0, 0),), direction="up", uid=3)
        self.assertEqual(ui.piece_color(bare), PIECE_PALETTE[3 % len(PIECE_PALETTE)])
        painted = Piece(cells=((0, 0),), direction="up", color=(1, 2, 3))
        self.assertEqual(ui.piece_color(painted), (1, 2, 3))

    def test_draw_piece_accepts_alpha_and_offset(self):
        piece = Piece(cells=((0, 0), (0, 1)), direction="right", color=PIECE_PALETTE[4])
        for alpha, offset in ((255, (0, 0)), (128, (10, -6)), (0, (999, 999))):
            ui.draw_piece(self.screen, (10, 10), piece, 40, alpha=alpha, offset=offset)

    def test_clear_caches_drops_piece_surfaces(self):
        cells, direction = pieces.parse_piece("0,0 > R")
        color = PIECE_PALETTE[5]
        first = ui.piece_surface(cells, direction, color, 30)
        ui.clear_caches()
        second = ui.piece_surface(cells, direction, color, 30)
        self.assertIsNot(first, second)

    def test_wrap_text_respects_max_width(self):
        text = "一支箭头是一条占好几格的折线，末端那个箭头就是它的朝向，点它身上任意一格都算选中。"
        lines = ui.wrap_text(text, size=16, max_width=200)
        self.assertGreater(len(lines), 1)
        for line in lines:
            self.assertLessEqual(ui.text_width(line, 16), 200)

    def test_wrap_text_never_starts_a_line_with_punctuation(self):
        """逐字折行很容易把句号甩到下一行，中文排版上很难看。"""
        text = "前方有箭头挡着，飞不出去。这时会丢掉一颗心；所以要看清楚再点。"
        for line in ui.wrap_text(text, size=15, max_width=110):
            self.assertNotIn(line[0], "。，、；：！？）】》」』")

    def test_wrap_text_handles_short_and_empty_input(self):
        self.assertEqual(ui.wrap_text("", size=15, max_width=100), [])
        self.assertEqual(ui.wrap_text("短", size=15, max_width=100), ["短"])

    def test_text_width_and_draw_text_agree(self):
        rect = ui.draw_text(self.screen, "一箭又一箭", (0, 0), size=20)
        self.assertAlmostEqual(rect.width, ui.text_width("一箭又一箭", 20), delta=2)

    def test_draw_paragraph_returns_consumed_height(self):
        rect = pygame.Rect(0, 0, 160, 200)
        height = ui.draw_paragraph(self.screen, "点一下箭头，让它飞出棋盘。" * 3, rect, size=14)
        self.assertGreater(height, 0)
        self.assertLessEqual(height, rect.height)

    def test_slider_helpers_round_trip(self):
        rect = pygame.Rect(100, 800, 300, 30)
        for ratio in (0.0, 0.25, 0.5, 0.75, 1.0):
            x = ui.slider_knob_x(rect, ratio)
            self.assertAlmostEqual(ui.slider_ratio_from_x(rect, x), ratio, delta=0.02)

    def test_slider_ratio_is_clamped(self):
        rect = pygame.Rect(100, 800, 300, 30)
        self.assertEqual(ui.slider_ratio_from_x(rect, -9999), 0.0)
        self.assertEqual(ui.slider_ratio_from_x(rect, 9999), 1.0)

    def test_slider_track_leaves_room_for_the_knob(self):
        rect = pygame.Rect(100, 800, 300, 30)
        track = ui.slider_track_rect(rect)
        self.assertGreater(track.width, 0)
        self.assertGreater(track.x, rect.x)
        self.assertLess(track.right, rect.right)

    def test_draw_slider_does_not_raise(self):
        ui.draw_slider(self.screen, pygame.Rect(100, 800, 300, 30), 0.4)

    def test_icons_do_not_raise(self):
        icons = (ui.draw_icon_back, ui.draw_icon_grid, ui.draw_icon_bulb,
                 ui.draw_icon_guide, ui.draw_icon_clock, ui.draw_icon_gear,
                 ui.draw_icon_moon, ui.draw_icon_sun, ui.draw_icon_minus,
                 ui.draw_icon_plus, ui.draw_icon_replay)
        for icon in icons:
            icon(self.screen, (50, 50), 24, config.COLOR_TEXT)

    def test_stars_and_lock_do_not_raise(self):
        ui.draw_stars(self.screen, (100, 100), 3)
        ui.draw_stars(self.screen, (100, 100), 5)
        ui.draw_lock(self.screen, (100, 100), 20)
        ui.draw_check(self.screen, (100, 100), 20)

    def test_draw_hearts_handles_every_count(self):
        for current in range(0, 8):
            ui.draw_hearts(self.screen, (20, 20), current, 7, size=18, gap=6)

    def test_draw_dashed_line_does_not_raise(self):
        ui.draw_dashed_line(self.screen, config.COLOR_TEXT_DIM, (0, 0), (200, 120))
        ui.draw_dashed_line(self.screen, config.COLOR_TEXT_DIM, (200, 120), (0, 0), dash=2, gap=2)

    def test_mix_color_endpoints(self):
        self.assertEqual(ui.mix_color((0, 0, 0), (255, 255, 255), 0.0), (0, 0, 0))
        self.assertEqual(ui.mix_color((0, 0, 0), (255, 255, 255), 1.0), (255, 255, 255))

    def test_lighten_and_darken_move_toward_the_right_end(self):
        self.assertGreater(sum(ui.lighten((100, 100, 100), 0.5)), 300)
        self.assertLess(sum(ui.darken((100, 100, 100), 0.5)), 300)

    def test_vertical_gradient_size(self):
        surface = ui.make_vertical_gradient((40, 60), (255, 0, 0), (0, 0, 255))
        self.assertEqual(surface.get_size(), (40, 60))

    def test_round_rect_alpha_does_not_raise(self):
        ui.draw_round_rect_alpha(self.screen, pygame.Rect(10, 10, 60, 40), (0, 0, 0), 120)
        ui.draw_round_rect_alpha(self.screen, pygame.Rect(10, 10, 60, 40), (0, 0, 0), 120,
                                 width=2)

    def test_piece_surface_cache_stays_bounded(self):
        """缓存上限是硬要求：缩放滑杆一路拖过去会生成上百个格距。"""
        for cell in range(6, 130):
            cells, direction = pieces.parse_piece("0,0 > R2")
            ui.piece_surface(cells, direction, PIECE_PALETTE[cell % 12], cell)
        self.assertLessEqual(len(ui._piece_cache), ui.PIECE_CACHE_LIMIT)


# ---------------------------------------------------------------- 动画
class AnimationTestCase(unittest.TestCase):
    """飞出 / 撞击 / 飘字 / 飘心四种动画的生命周期。

    注意 offset / alpha / flash / lift 都是 **property**（只读属性），
    写法是 `effect.offset` 而不是 `effect.offset()`——它们是每帧现算的派生量，
    写成属性是为了让调用处一眼看出「取个值」而不是「做件事」。
    """

    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        ui.clear_caches()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def drain(self, effect, limit=600):
        """反复 update 直到动画自己报告结束，返回用掉的帧数。"""
        frames = 0
        while not effect.update(FRAME):
            frames += 1
            self.assertLess(frames, limit, "动画没有自行结束，可能有死循环")
        return frames

    def test_fly_out_finishes_and_keeps_moving_away(self):
        piece = Piece(cells=((2, 2), (2, 3)), direction="right", color=PIECE_PALETTE[0])
        effect = anim.FlyOut(piece, (0, 0), 40, 400)
        start = effect.joints()[-1]
        effect.update(FRAME)
        moved = effect.joints()[-1]
        self.assertGreater(moved[0], start[0])         # 箭头朝右钻出去
        self.assertEqual(moved[1], start[1])           # 这条路没有上下分量
        frames = self.drain(effect)
        self.assertGreater(frames, 5)
        self.assertAlmostEqual(effect.advance, 400)    # 滑满全程

    def test_fly_out_respects_direction(self):
        for direction, sign, axis in (("right", 1, 0), ("left", -1, 0),
                                      ("down", 1, 1), ("up", -1, 1)):
            piece = Piece(cells=((1, 1),), direction=direction, color=PIECE_PALETTE[1])
            effect = anim.FlyOut(piece, (0, 0), 40, 300)
            effect.update(FRAME)
            head = effect.joints()[-1]
            rest = (1 + 0.5) * 40                       # 单格中心的初始坐标
            self.assertGreater(sign * (head[axis] - rest), 0,
                               "%s 方向飞反了：%r" % (direction, head))

    def test_fly_out_tail_follows_the_bend(self):
        """L 形箭头：尾巴没过弯时沿第一段滑，过弯后沿箭头方向直线出视口。

        弯折是「流」过去的：每个折点沿路径走的弧长都相同，所以任何时刻
        尾巴的位置都应该正好落在原始路径上弧长 = advance 的那个点。
        """
        piece = Piece(cells=((2, 2), (2, 3), (3, 3)), direction="right",
                      color=PIECE_PALETTE[4])
        cell = 40
        # 走了半格：还在第一段（向右）上，没有上下分量
        tail = ui.path_joints(piece, cell, 20)[0]
        self.assertAlmostEqual(tail[0], (2 + 0.5) * cell + 20)
        self.assertAlmostEqual(tail[1], (2 + 0.5) * cell)
        # 一格半：尾巴已经流过拐弯，转到竖直段上了
        tail = ui.path_joints(piece, cell, 60)[0]
        self.assertAlmostEqual(tail[0], (3 + 0.5) * cell)
        self.assertAlmostEqual(tail[1], (2 + 0.5) * cell + 20)
        # 两格：尾巴正好到箭头原来的位置
        tail = ui.path_joints(piece, cell, 2 * cell)[0]
        self.assertAlmostEqual(tail[0], (3 + 0.5) * cell)
        self.assertAlmostEqual(tail[1], (3 + 0.5) * cell)
        # 再往前就是沿箭头方向的直线延长
        tail = ui.path_joints(piece, cell, 2 * cell + 25)[0]
        self.assertAlmostEqual(tail[0], (3 + 0.5) * cell + 25)
        self.assertAlmostEqual(tail[1], (3 + 0.5) * cell)

    def test_impact_fades_out_and_ends(self):
        piece = Piece(cells=((1, 1), (1, 2)), direction="up", color=PIECE_PALETTE[2])
        effect = anim.Impact(piece, (0, 0), 40, pygame.Rect(0, 0, 40, 40))
        self.assertGreater(effect.flash, 0)
        frames = self.drain(effect)
        self.assertGreater(frames, 5)

    def test_impact_offset_moves_along_its_direction(self):
        piece = Piece(cells=((1, 1),), direction="right", color=PIECE_PALETTE[2])
        effect = anim.Impact(piece, (0, 0), 40, pygame.Rect(0, 0, 40, 40))
        effect.update(FRAME)
        self.assertGreater(effect.offset[0], 0)

    def test_impact_tint_moves_toward_red(self):
        """被撞的箭头要真的泛红——这是「点错了」最直接的反馈。"""
        piece = Piece(cells=((1, 1),), direction="up", color=(0, 0, 255))
        effect = anim.Impact(piece, (0, 0), 40, pygame.Rect(0, 0, 40, 40))
        image, offset = effect.tinted(effect.TINT_LEVELS)
        self.assertEqual(image.get_size(),
                         ui.piece_surface(piece.cells, piece.direction,
                                          (0, 0, 255), 40)[0].get_size())
        # 染色是「本色 × 偏红的乘数」，蓝色分量必须被压下去
        self.assertLess(image.get_at((image.get_width() // 2,
                                      image.get_height() // 2))[2], 255)
        self.assertIsInstance(offset, tuple)

    def test_impact_tint_is_cached_per_level(self):
        piece = Piece(cells=((1, 1),), direction="up", color=PIECE_PALETTE[2])
        effect = anim.Impact(piece, (0, 0), 40, pygame.Rect(0, 0, 40, 40))
        self.assertIs(effect.tinted(2), effect.tinted(2))

    def test_floating_text_rises_and_ends(self):
        effect = anim.FloatingText("+300", (100, 100), size=20, duration=0.5)
        frames = self.drain(effect)
        self.assertGreater(frames, 5)
        self.assertLess(frames, 600)

    def test_floating_heart_rises_and_ends(self):
        effect = anim.FloatingHeart((100, 100), duration=0.5)
        effect.update(FRAME)
        self.assertLess(effect.lift, 0, "心应当先向上弹起（屏幕 y 变小）")
        self.assertEqual(effect.alpha, 255)
        for _ in range(20):
            effect.update(FRAME)
        self.assertLess(effect.alpha, 255)
        self.drain(effect)

    def test_floating_heart_splits_into_two_halves(self):
        """「心碎」动画把整颗心切成左右两半，两半拼起来必须还是整颗心。"""
        effect = anim.FloatingHeart((100, 100), size=40)
        full = ui.heart_surface(40, config.COLOR_HP)
        self.assertEqual(effect.left.get_width() + effect.right.get_width(),
                         full.get_width())
        self.assertEqual(effect.left.get_height(), full.get_height())
        self.assertEqual(effect.right.get_height(), full.get_height())

    def test_animations_draw_without_raising(self):
        piece = Piece(cells=((1, 1), (1, 2)), direction="right", color=PIECE_PALETTE[3])
        effects = [
            anim.FlyOut(piece, (10, 10), 40, 400),
            anim.Impact(piece, (10, 10), 40, pygame.Rect(10, 10, 40, 40)),
            anim.FloatingText("测试", (50, 50)),
            anim.FloatingHeart((50, 50)),
        ]
        for effect in effects:
            # 整段动画每一帧都画一遍：撞击那支的染色贴图只在闪得厉害时才会用到，
            # 只画第一帧或者只画最后一帧都可能漏掉那条分支（真的漏过一次）。
            while not effect.update(FRAME):
                effect.draw(self.screen)
            effect.draw(self.screen)


# ---------------------------------------------------------------- 背景
class BackgroundTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        ui.clear_caches()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def test_every_scene_draws(self):
        bg = bgfx.Background((config.WINDOW_WIDTH, config.WINDOW_HEIGHT), SCENE_MENU)
        for scene in (SCENE_MENU, SCENE_LEVELS, SCENE_PLAY):
            bg.set_scene(scene)
            for _ in range(3):
                bg.update(FRAME)
            bg.draw(self.screen)

    def test_background_follows_theme(self):
        for theme in config.THEME_ORDER:
            config.apply_theme(theme)
            ui.clear_caches()
            bg = bgfx.Background((config.WINDOW_WIDTH, config.WINDOW_HEIGHT), SCENE_MENU)
            bg.draw(self.screen)
        config.apply_theme("night")
        ui.clear_caches()


# ---------------------------------------------------------------- 界面流程
class GameFlowTestCase(unittest.TestCase):
    """整机流程：菜单 / 关卡总览 / 关卡内交互 / 提示 / 缩放平移 / 结算面板。"""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        ui.clear_caches()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        config.apply_theme("night")
        ui.clear_caches()
        self.dir = tempfile.mkdtemp(prefix="oa_flow_")
        self.progress = Progress(path=os.path.join(self.dir, "progress.json"))
        self.game = Game(self.screen, self.progress)

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def enter_level(self, index):
        """进入第 index 关。

        解锁链本身有专门的用例（test_locked_level_cannot_be_started_...、
        test_fresh_progress_only_has_level_one_unlocked），其余用例关心的是
        「这一关长什么样」，所以先把全部关卡解锁，免得被「第 N 关还没开」挡住。
        """
        self.progress.mark_all_cleared(TOTAL_LEVELS)
        self.assertTrue(self.game.start_level(index), "第 %d 关应当可以进入" % (index + 1))
        return self.game

    # ------------------------------------------------------------ 基础
    def test_starts_in_menu(self):
        self.assertEqual(self.game.scene, SCENE_MENU)
        self.assertIsNone(self.game.board)

    def test_every_scene_draws_without_raising(self):
        self.game.enter_menu()
        self.game.draw()
        self.game.enter_levels()
        self.game.draw()
        self.game.start_tutorial()
        self.game.draw()
        self.enter_level(0)
        self.game.draw()
        for index in range(TOTAL_LEVELS):
            self.enter_level(index)
            self.game.draw()

    def test_enter_levels_and_back(self):
        self.game.enter_levels()
        self.assertEqual(self.game.scene, SCENE_LEVELS)
        self.game.enter_menu()
        self.assertEqual(self.game.scene, SCENE_MENU)

    def test_start_level_rejects_out_of_range(self):
        self.assertFalse(self.game.start_level(-1))
        self.assertFalse(self.game.start_level(TOTAL_LEVELS))

    def test_locked_level_cannot_be_started_and_shows_a_toast(self):
        self.assertFalse(self.game.start_level(3))
        self.assertIsNone(self.game.board)
        self.assertGreater(self.game.toast_timer, 0)

    def test_starting_a_level_sets_up_the_board(self):
        self.assertTrue(self.game.start_level(0))
        self.assertEqual(self.game.scene, SCENE_PLAY)
        self.assertIsNotNone(self.game.board)
        self.assertEqual(self.game.board.total, LEVELS[0].arrow_count)
        self.assertEqual(self.game.board.remaining, LEVELS[0].arrow_count)
        self.assertFalse(self.game.in_tutorial)
        self.assertIsNone(self.game.overlay)

    # ------------------------------------------------------------ 关卡内交互
    def test_clicking_a_free_pipe_starts_a_fly_animation(self):
        self.game.start_level(0)
        piece = self.game.board.available_arrows()[0]
        before = self.game.board.remaining
        result = self.game.click_cell(*piece.head)
        self.assertEqual(result.kind, CLICK_FLY)
        self.assertEqual(self.game.board.remaining, before - 1)
        self.assertTrue(self.game.animations)

    def test_clicking_a_blocked_pipe_shows_a_floating_heart(self):
        self.game.start_level(0)
        blocked = [p for p in self.game.board.pieces if not self.game.board.can_fly(p)]
        self.assertTrue(blocked, "第 1 关开局应当有被挡住的箭头")
        before = self.game.board.hp
        result = self.game.click_cell(*blocked[0].head)
        self.assertEqual(result.kind, CLICK_BLOCKED)
        self.assertEqual(self.game.board.hp, before - 1)
        self.assertTrue(self.game.floats)

    def test_clicking_empty_cell_does_nothing_in_game(self):
        self.game.start_level(0)
        empty = None
        for row in range(self.game.board.rows):
            for col in range(self.game.board.cols):
                if self.game.board.piece_at(row, col) is None:
                    empty = (row, col)
                    break
            if empty:
                break
        if empty is None:
            self.skipTest("本关没有空格")
        result = self.game.click_cell(*empty)
        self.assertEqual(result.kind, CLICK_EMPTY)
        self.assertFalse(self.game.animations)

    def test_click_cell_returns_none_while_an_overlay_is_open(self):
        self.game.start_level(0)
        self.game.open_settings()
        self.assertIsNone(self.game.click_cell(0, 0))

    def test_clicking_outside_the_board_does_nothing(self):
        self.game.start_level(0)
        self.game.handle_click((1, 1))              # 左上角是顶栏按钮区
        self.assertEqual(self.game.board.remaining, LEVELS[0].arrow_count)

    def test_t04_clear_level_then_go_to_next_level(self):
        """T04：清空本关全部箭头 -> 弹「通关」面板并记分 -> 点「下一关」进入下一关。"""
        self.game.start_level(0)
        for piece in self.game.board.solution():
            self.game.click_cell(*piece.head)
        self.assertEqual(self.game.board.state, STATE_CLEARED)
        for _ in range(_RESULT_FRAMES):
            self.game.update(FRAME)
        self.assertEqual(self.game.overlay, OVERLAY_WIN)
        self.assertEqual(self.game.last_score, scoring.max_score(LEVELS[0]))
        self.assertTrue(self.game.score_perfect)
        self.assertEqual(self.progress.best_score(0), self.game.last_score)
        self.assertTrue(self.progress.is_cleared(0))
        self.assertTrue(self.game.is_unlocked(1))

        # 「进入下一关」：通关面板上的主按钮就是它
        self.game.next_level()
        self.assertEqual(self.game.level_index, 1)
        self.assertEqual(self.game.board.remaining, LEVELS[1].arrow_count)

    def test_t05_fail_then_restart(self):
        """T05：把生命值点光 -> 弹「失败」面板且不得分 -> 「重新开始本关」能接着玩。"""
        self.game.start_level(0)
        blocked = [p for p in self.game.board.pieces if not self.game.board.can_fly(p)]
        target = blocked[0]
        for _ in range(self.game.board.max_hp):
            self.game.click_cell(*target.head)
        self.assertEqual(self.game.board.state, STATE_FAILED)
        for _ in range(_RESULT_FRAMES):
            self.game.update(FRAME)
        self.assertEqual(self.game.overlay, OVERLAY_FAIL)
        self.assertEqual(self.game.last_score, 0)
        self.assertEqual(self.progress.best_score(0), 0)

        # 失败面板的主按钮是「重新开始本关」，点了就回到干净的开局状态
        self.game.restart_level()
        self.assertEqual(self.game.board.state, STATE_PLAYING)
        self.assertEqual(self.game.board.hp, self.game.board.max_hp)
        self.assertEqual(self.game.board.remaining, LEVELS[0].arrow_count)
        self.assertIsNone(self.game.overlay)

    def test_final_level_clear_shows_all_clear(self):
        self.progress.mark_all_cleared(TOTAL_LEVELS)
        self.game.start_level(TOTAL_LEVELS - 1)
        for piece in self.game.board.solution():
            self.game.click_cell(*piece.head)
        for _ in range(_RESULT_FRAMES):
            self.game.update(FRAME)
        self.assertEqual(self.game.overlay, OVERLAY_ALL_CLEAR)
        self.assertTrue(self.progress.all_cleared(TOTAL_LEVELS))

    def test_next_level_advances_after_winning(self):
        self.game.start_level(0)
        for piece in self.game.board.solution():
            self.game.click_cell(*piece.head)
        for _ in range(_RESULT_FRAMES):
            self.game.update(FRAME)
        self.game.next_level()
        self.assertEqual(self.game.level_index, 1)
        self.assertEqual(self.game.board.remaining, LEVELS[1].arrow_count)

    def test_t06_restart_mid_game(self):
        """T06：进行中点掉一支、再故意点错一次，重新开始后布局与生命值都要恢复。"""
        self.game.start_level(0)
        piece = self.game.board.available_arrows()[0]
        self.game.click_cell(*piece.head)
        blocked = [p for p in self.game.board.pieces
                   if not self.game.board.can_fly(p)][0]
        self.game.click_cell(*blocked.head)
        for _ in range(10):
            self.game.update(FRAME)
        self.assertLess(self.game.board.remaining, LEVELS[0].arrow_count)
        self.assertLess(self.game.board.hp, self.game.board.max_hp)
        self.game.restart_level()
        self.assertEqual(self.game.board.remaining, LEVELS[0].arrow_count)
        self.assertEqual(self.game.board.hp, self.game.board.max_hp)
        self.assertIsNone(self.game.overlay)
        self.assertEqual(self.game.elapsed, 0.0)
        self.assertEqual(self.game.animations, [])

        # 不只是「数量回来了」——每一支箭头都回到了它自己原来的格子上
        for pipe in LEVELS[0].pieces:
            self.assertIs(self.game.board.piece_at(*pipe.head), pipe)

    def test_timer_only_runs_while_playing(self):
        """分出胜负之后时钟要停下来，否则玩家盯着结算面板那几秒用时还在涨。"""
        self.game.start_level(0)
        for _ in range(30):
            self.game.update(FRAME)
        self.assertGreater(self.game.elapsed, 0)
        for piece in self.game.board.solution():
            self.game.click_cell(*piece.head)
        for _ in range(_RESULT_FRAMES):
            self.game.update(FRAME)
        frozen = self.game.elapsed
        for _ in range(30):
            self.game.update(FRAME)
        self.assertAlmostEqual(self.game.elapsed, frozen, delta=1e-9)

    # ------------------------------------------------------------ 提示 / 辅助线
    def test_hint_picks_a_piece_that_can_actually_fly(self):
        self.game.start_level(0)
        piece = self.game.best_hint()
        self.assertIsNotNone(piece)
        self.assertTrue(self.game.board.can_fly(piece))

    def test_hint_prefers_unlocking_the_most_pieces(self):
        """提示要挑「点掉之后能连带解锁最多」的那一支，而不是随便一支。"""
        self.game.start_level(0)
        best = self.game.best_hint()
        grid = self.game.board.grid
        index_of = {id(p): i for i, p in enumerate(self.game.board.pieces)}
        def gain_for(piece):
            index = index_of[id(piece)]
            for row, col in piece.cells:
                grid[row][col] = None
            try:
                return len(self.game.board.available_arrows())
            finally:
                for row, col in piece.cells:
                    grid[row][col] = index
        gains = {gain_for(p) for p in self.game.board.available_arrows()}
        self.assertEqual(gain_for(best), max(gains))

    def test_hint_does_not_corrupt_the_board(self):
        """回归测试：提示的试算必须把 grid 原样还原。

        早先的写法用「候选列表里的第几个」当真实下标写回 grid，
        结果调用一次提示就把棋盘写坏，之后所有点击都判成「被挡住」。
        """
        self.game.start_level(0)
        before = len(self.game.board.available_arrows())
        for _ in range(6):
            self.game.best_hint()
        self.assertEqual(len(self.game.board.available_arrows()), before,
                         "调用提示之后可点数变了，说明 grid 被写坏了")
        for piece in self.game.board.solution():
            self.assertEqual(self.game.click_cell(*piece.head).kind, CLICK_FLY)
        self.assertEqual(self.game.board.state, STATE_CLEARED)

    def test_use_hint_sets_and_expires_the_highlight(self):
        self.game.start_level(0)
        self.game.use_hint()
        self.assertIsNotNone(self.game.hint_piece)
        self.assertGreater(self.game.hint_timer, 0)
        for _ in range(int(config.HINT_DURATION / FRAME) + 10):
            self.game.update(FRAME)
        self.assertIsNone(self.game.hint_piece)
        self.assertEqual(self.game.hint_timer, 0.0)

    def test_clicking_the_hinted_piece_clears_the_highlight(self):
        self.game.start_level(0)
        self.game.use_hint()
        piece = self.game.hint_piece
        self.game.click_cell(*piece.head)
        self.assertIsNone(self.game.hint_piece)

    def test_use_hint_outside_a_level_only_toasts(self):
        self.game.enter_menu()
        self.game.use_hint()
        self.assertIsNone(self.game.hint_piece)

    def test_guides_toggle_updates_the_button_state(self):
        self.game.start_level(0)
        self.assertFalse(self.game.show_guides)
        self.game.toggle_guides()
        self.assertTrue(self.game.show_guides)
        self.game.draw()
        self.game.toggle_guides()
        self.assertFalse(self.game.show_guides)
        self.game.draw()

    def test_guides_draw_for_every_level(self):
        for index in range(TOTAL_LEVELS):
            self.enter_level(index)
            self.game.toggle_guides()
            self.game.draw()
            self.game.toggle_guides()

    def test_guide_segment_is_parallel_to_the_arrow(self):
        """辅助线必须和箭头同向、且在射线不为空时有长度。

        这是补一个真出现过的 bug：辅助线的终点原先取的是「挡路那支的**箭头**
        所在格」，而挡路的通常是对方的身子和箭头在棋盘另一头，
        于是辅助线会斜穿整个棋盘去连一个方向完全无关的格子。
        端点几何抽成 guide_segment 之后，就能这样直接把它盯住。
        """
        for index in range(TOTAL_LEVELS):
            self.enter_level(index)
            for piece in self.game.board.pieces:
                segment = self.game.guide_segment(piece)
                self.assertIsNotNone(segment)
                (x1, y1), (x2, y2) = segment
                dx, dy = ui.DIR_VECTORS[piece.direction]
                # 与箭头方向叉积为 0 -> 共线
                self.assertAlmostEqual((x2 - x1) * dy - (y2 - y1) * dx, 0.0, places=6)
                # 共线之后，点积就是线段的有效长度
                length = (x2 - x1) * dx + (y2 - y1) * dy
                if self.game.board.path_cells(piece):
                    # 射线非空（前方至少有一格）时必须真的画出长度来，
                    # 否则辅助线在密铺的盘面上等于没画
                    self.assertGreater(length, 0.0, (index, piece.head))
                else:
                    # 贴着边、朝盘外的那类，线长本来就是 0；
                    # 端点一个是浮点格心、一个是取整过的矩形边，留 1 像素余量
                    self.assertLessEqual(abs(length), 1.0, (index, piece.head))

    def test_guide_segment_ends_inside_the_blocking_cell(self):
        """被挡住时，辅助线的终点要落在**射线上被占的那一格**里。"""
        for index in range(TOTAL_LEVELS):
            self.enter_level(index)
            for piece in self.game.board.pieces:
                path, blocker = self.game.board.path_to_blocker(piece)
                if blocker is None:
                    continue
                end = self.game.guide_segment(piece)[1]
                rect = self.game.cell_rect(*path[-1])
                self.assertTrue(rect.left <= end[0] <= rect.right,
                                (index, piece.head, end))
                self.assertTrue(rect.top <= end[1] <= rect.bottom,
                                (index, piece.head, end))

    def test_guide_segment_disappears_with_the_piece(self):
        """已经飞走的箭头不再有辅助线。"""
        self.enter_level(0)
        piece = self.game.board.available_arrows()[0]
        self.game.click_cell(*piece.head)
        self.assertIsNone(self.game.guide_segment(piece))

    # ------------------------------------------------------------ 缩放 / 平移
    def test_zoom_range_is_respected(self):
        self.game.start_level(0)
        self.game.set_zoom_ratio(0.0)
        self.assertAlmostEqual(self.game.zoom, config.ZOOM_MIN)
        self.game.set_zoom_ratio(1.0)
        self.assertAlmostEqual(self.game.zoom, config.ZOOM_MAX)
        self.game.set_zoom_ratio(-5.0)
        self.assertAlmostEqual(self.game.zoom, config.ZOOM_MIN)
        self.game.set_zoom_ratio(5.0)
        self.assertAlmostEqual(self.game.zoom, config.ZOOM_MAX)

    def test_zoom_is_rounded_to_two_decimals(self):
        """zoom 量化到两位小数：滑杆连着拖不会留下几百个无意义的中间值。"""
        self.enter_level(0)
        for step in range(101):
            self.game.set_zoom_ratio(step / 100.0)
            self.assertEqual(self.game.zoom, round(self.game.zoom, 2))

    def test_zoom_sweep_keeps_the_piece_cache_bounded(self):
        """一路拖过整条滑杆也不能把贴图缓存撑爆。

        真正参与缓存键的是**整数格距** self.cell（piece_surface 里再取一次整），
        所以缓存键的个数被格距的整数范围卡住；PIECE_CACHE_LIMIT 再兜一道底。
        """
        self.enter_level(0)
        self.assertIsInstance(self.game.cell, int)
        for step in range(101):
            self.game.set_zoom_ratio(step / 100.0)
            self.game.draw()
        self.assertLessEqual(len(ui._piece_cache), ui.PIECE_CACHE_LIMIT)

    def test_zoom_by_moves_by_one_step(self):
        self.game.start_level(0)
        self.game.set_zoom_ratio(0.5)
        start = self.game.zoom
        self.game.zoom_by(config.ZOOM_STEP)
        self.assertGreater(self.game.zoom, start)
        self.game.zoom_by(-config.ZOOM_STEP)
        self.assertAlmostEqual(self.game.zoom, start, delta=0.011)

    def test_zoom_ratio_reports_current_position(self):
        self.game.start_level(0)
        self.game.set_zoom_ratio(0.5)
        self.assertAlmostEqual(self.game.zoom_ratio, 0.5, delta=0.02)

    def test_cell_size_scales_with_zoom(self):
        self.game.start_level(0)
        self.game.set_zoom_ratio(0.0)
        small = self.game.cell
        self.game.set_zoom_ratio(1.0)
        self.assertGreater(self.game.cell, small)
        self.assertAlmostEqual(self.game.cell / float(small),
                               config.ZOOM_MAX / config.ZOOM_MIN, delta=0.2)

    def test_base_cell_is_within_limits(self):
        for index in range(TOTAL_LEVELS):
            self.enter_level(index)
            self.assertGreaterEqual(self.game.base_cell, config.CELL_MIN_SIDE)
            self.assertLessEqual(self.game.base_cell, config.CELL_MAX_SIDE)

    def test_board_fits_the_viewport_at_default_zoom(self):
        view = self.game.viewport_rect
        for index in range(TOTAL_LEVELS):
            self.enter_level(index)
            rect = self.game.board_rect
            self.assertLessEqual(rect.width, view.width + 1, "第 %d 关棋盘太宽" % (index + 1))
            self.assertLessEqual(rect.height, view.height + 1, "第 %d 关棋盘太高" % (index + 1))

    def test_board_fills_the_viewport_vertically(self):
        """竖屏棋盘应当把视口高度基本占满，否则上下会各空出一条。"""
        for index in range(TOTAL_LEVELS):
            self.enter_level(index)
            ratio = self.game.board_rect.height / float(self.game.viewport_rect.height)
            self.assertGreater(ratio, 0.90, "第 %d 关棋盘只占了视口高度的 %.0f%%"
                               % (index + 1, ratio * 100))

    def test_board_never_leaves_the_viewport(self):
        view = self.game.viewport_rect
        for index in (0, TOTAL_LEVELS - 1):
            self.enter_level(index)
            self.game.set_zoom_ratio(1.0)               # 放到最大，必然需要平移
            for delta in ((400, 400), (-900, -900), (100000, -100000)):
                self.game.pan = [delta[0], delta[1]]
                self.game.layout_board()
                rect = self.game.board_rect
                if rect.width > view.width:
                    self.assertLessEqual(rect.left, view.left)
                    self.assertGreaterEqual(rect.right, view.right)
                else:
                    self.assertEqual(rect.centerx, view.centerx)
                if rect.height > view.height:
                    self.assertLessEqual(rect.top, view.top)
                    self.assertGreaterEqual(rect.bottom, view.bottom)
                else:
                    self.assertEqual(rect.centery, view.centery)

    def test_small_board_is_centred(self):
        self.game.start_level(0)
        self.game.set_zoom_ratio(0.0)
        self.assertEqual(self.game.board_rect.centerx, self.game.viewport_rect.centerx)

    def test_pan_is_clamped_back_into_range(self):
        """拖到边界之后 pan 要记回实际偏移，否则往回拖有一段是空转。"""
        self.enter_level(TOTAL_LEVELS - 1)
        self.game.set_zoom_ratio(1.0)
        self.game.pan = [99999, 0]
        self.game.layout_board()
        first = list(self.game.pan)
        self.game.layout_board()
        self.assertEqual(first, self.game.pan)

    def test_cell_rect_and_center_agree(self):
        self.enter_level(0)
        rect = self.game.cell_rect(3, 4)
        center = self.game.cell_center(3, 4)
        self.assertAlmostEqual(center[0], rect.centerx, delta=1)
        self.assertAlmostEqual(center[1], rect.centery, delta=1)

    def test_cell_at_pos_round_trip(self):
        for index in (0, TOTAL_LEVELS - 1):
            self.enter_level(index)
            for row, col in ((0, 0), (1, 1), (self.game.board.rows - 1, self.game.board.cols - 1)):
                pos = self.game.cell_center(row, col)
                self.assertEqual(self.game.cell_at_pos(pos), (row, col))

    def test_cell_at_pos_outside_the_board_is_none(self):
        self.game.start_level(0)
        self.assertIsNone(self.game.cell_at_pos((1, 1)))
        self.assertIsNone(self.game.cell_at_pos((config.WINDOW_WIDTH - 2, config.WINDOW_HEIGHT - 2)))

    # ------------------------------------------------------------ 拖拽
    def test_drag_on_board_does_not_count_as_a_click(self):
        """拖动查看棋盘时松手不能顺手点掉一支箭头。"""
        self.enter_level(TOTAL_LEVELS - 1)
        self.game.set_zoom_ratio(1.0)
        row, col = self.game.board.available_arrows()[0].head
        pos = self.game.cell_center(row, col)
        before = self.game.board.remaining
        self.game.on_press(pos)
        self.game.on_motion((pos[0] + 40, pos[1] + 40), (1, 0, 0))
        self.game.on_motion((pos[0] + 80, pos[1] + 80), (1, 0, 0))
        self.game.on_release((pos[0] + 80, pos[1] + 80))
        self.assertEqual(self.game.board.remaining, before)

    def test_short_press_is_treated_as_a_click(self):
        self.enter_level(TOTAL_LEVELS - 1)
        piece = self.game.board.available_arrows()[0]
        pos = self.game.cell_center(*piece.head)
        before = self.game.board.remaining
        self.game.on_press(pos)
        self.game.on_release(pos)
        self.assertEqual(self.game.board.remaining, before - 1)

    def test_tiny_mouse_jitter_still_counts_as_a_click(self):
        """手抖了几像素不该被当成拖动——阈值是 DRAG_THRESHOLD。"""
        self.enter_level(0)
        piece = self.game.board.available_arrows()[0]
        pos = self.game.cell_center(*piece.head)
        before = self.game.board.remaining
        self.game.on_press(pos)
        self.game.on_motion((pos[0] + 2, pos[1] + 2), (1, 0, 0))
        self.game.on_release((pos[0] + 2, pos[1] + 2))
        self.assertEqual(self.game.board.remaining, before - 1)

    def test_pressing_a_button_is_not_a_board_drag(self):
        self.game.start_level(0)
        pos = self.game.buttons[0].rect.center
        self.assertIsNone(self.game.pick_drag_target(pos))

    def test_pressing_the_viewport_targets_the_board(self):
        self.game.start_level(0)
        self.assertEqual(self.game.pick_drag_target(self.game.viewport_rect.center), "board")

    def test_slider_drag_sets_the_zoom(self):
        """按住滑杆拖动：滑杆中点对应 120%，两端是最小 / 最大。

        滑杆比例是线性的 0~1 映射到 ZOOM_MIN~ZOOM_MAX，
        所以中点不是「100%」而是 1.2——100% 落在三分之一处。
        """
        self.enter_level(0)
        rect = self.game.zoom_slider_rect
        center = (rect.centerx, rect.centery)
        self.assertEqual(self.game.pick_drag_target(center), "slider")
        self.game.on_press(center)
        self.assertAlmostEqual(self.game.zoom,
                               (config.ZOOM_MIN + config.ZOOM_MAX) / 2.0, delta=0.02)

        track = ui.slider_track_rect(rect)
        self.game.on_motion((track.left - 200, rect.centery), (1, 0, 0))
        self.assertAlmostEqual(self.game.zoom, config.ZOOM_MIN, delta=0.02)
        self.game.on_motion((track.right + 200, rect.centery), (1, 0, 0))
        self.assertAlmostEqual(self.game.zoom, config.ZOOM_MAX, delta=0.02)
        self.game.on_release((track.right, rect.centery))

    def test_default_zoom_sits_at_one_third_of_the_slider(self):
        """默认缩放是 100%，它对应的滑杆位置应当就是三分之一处。"""
        self.enter_level(0)
        expected = ((config.ZOOM_DEFAULT - config.ZOOM_MIN)
                    / (config.ZOOM_MAX - config.ZOOM_MIN))
        self.assertAlmostEqual(self.game.zoom_ratio, expected, delta=0.01)
        x = ui.slider_knob_x(self.game.zoom_slider_rect, expected)
        self.assertAlmostEqual(ui.slider_ratio_from_x(self.game.zoom_slider_rect, x),
                               expected, delta=0.02)

    def test_slider_is_not_draggable_outside_a_level(self):
        self.game.enter_menu()
        rect = self.game.zoom_slider_rect
        self.assertIsNone(self.game.pick_drag_target(rect.center))

    # ------------------------------------------------------------ 设置 / 主题
    def test_settings_overlay_opens_and_closes(self):
        self.game.start_level(0)
        self.game.open_settings()
        self.assertEqual(self.game.overlay, OVERLAY_SETTINGS)
        self.game.draw()
        self.game.close_overlay()
        self.assertIsNone(self.game.overlay)

    def test_theme_toggle_switches_and_returns(self):
        original = config.THEME
        self.game.start_level(0)
        self.game.toggle_theme()
        self.assertNotEqual(config.THEME, original)
        self.game.draw()
        self.game.toggle_theme()
        self.assertEqual(config.THEME, original)
        self.game.draw()

    def test_theme_toggle_works_in_every_scene(self):
        for enter in (self.game.enter_menu, self.game.enter_levels, lambda: self.game.start_level(0)):
            enter()
            self.game.toggle_theme()
            self.game.draw()
            self.game.toggle_theme()
            self.game.draw()

    def test_panel_geometry_holds_content(self):
        """结算面板要在 64 像素高的窗口里放得下，还要在窗口内。"""
        self.game.start_level(0)
        panel = self.game.panel_rect
        self.assertEqual(panel.width, 460)
        self.assertEqual(panel.height, PANEL_HEIGHT)
        self.assertGreater(panel.top, 0)
        self.assertLess(panel.bottom, config.WINDOW_HEIGHT)
        # 五颗设置按钮加底部两行说明，都要落在面板里
        self.game.open_settings()
        for button in self.game.make_settings_buttons():
            self.assertGreaterEqual(button.rect.top, panel.top)
            self.assertLessEqual(button.rect.bottom, panel.bottom)

    def test_overlay_buttons_stay_inside_the_panel(self):
        self.game.start_level(0)
        for piece in self.game.board.solution():
            self.game.click_cell(*piece.head)
        for _ in range(_RESULT_FRAMES):
            self.game.update(FRAME)
        self.assertIsNotNone(self.game.overlay)
        block = self.game.panel_rect
        for button in self.game.buttons:
            self.assertGreaterEqual(button.rect.left, block.left)
            self.assertLessEqual(button.rect.right, block.right)
            self.assertGreaterEqual(button.rect.top, block.top)
            self.assertLessEqual(button.rect.bottom, block.bottom)

    def test_play_buttons_stay_inside_the_window(self):
        self.game.start_level(0)
        for button in self.game.make_play_buttons():
            self.assertGreaterEqual(button.rect.left, 0)
            self.assertLessEqual(button.rect.right, config.WINDOW_WIDTH)
            self.assertGreaterEqual(button.rect.top, 0)
            self.assertLessEqual(button.rect.bottom, config.WINDOW_HEIGHT)

    def test_menu_buttons_stay_inside_the_window(self):
        self.game.enter_menu()
        for button in self.game.make_menu_buttons():
            self.assertGreaterEqual(button.rect.left, 0)
            self.assertLessEqual(button.rect.right, config.WINDOW_WIDTH)
            self.assertLessEqual(button.rect.bottom, config.WINDOW_HEIGHT)

    def test_level_cards_stay_inside_the_window(self):
        self.game.enter_levels()
        rects = self.game.card_rects
        self.assertEqual(len(rects), TOTAL_LEVELS)
        for rect in rects:
            self.assertGreaterEqual(rect.left, 0)
            self.assertLessEqual(rect.right, config.WINDOW_WIDTH)
            self.assertGreaterEqual(rect.top, 0)
            self.assertLessEqual(rect.bottom, config.WINDOW_HEIGHT)

    def test_level_cards_do_not_overlap(self):
        self.game.enter_levels()
        rects = self.game.card_rects
        for index, first in enumerate(rects):
            for second in rects[index + 1:]:
                self.assertFalse(first.colliderect(second),
                                 "关卡卡片重叠：%r / %r" % (first, second))

    def test_clicking_a_locked_card_does_not_enter(self):
        self.game.enter_levels()
        self.game.click_card(4)
        self.assertEqual(self.game.scene, SCENE_LEVELS)
        self.assertIsNone(self.game.board)
        self.assertGreater(self.game.toast_timer, 0)

    def test_clicking_an_unlocked_card_enters_the_level(self):
        self.game.enter_levels()
        self.game.click_card(0)
        self.assertEqual(self.game.scene, SCENE_PLAY)
        self.assertEqual(self.game.level_index, 0)

    def test_reset_progress_needs_two_clicks(self):
        """清空进度是不可逆的，第一次点只提醒、第二次才真的清。"""
        self.progress.mark_all_cleared(TOTAL_LEVELS)
        self.game.enter_levels()
        self.game.toggle_reset_progress()
        self.assertEqual(self.progress.cleared_count(TOTAL_LEVELS), TOTAL_LEVELS)
        self.game.toggle_reset_progress()
        self.assertEqual(self.progress.cleared_count(TOTAL_LEVELS), 0)

    def test_toast_expires(self):
        self.game.enter_menu()
        self.game.show_toast("测试提示")
        self.assertGreater(self.game.toast_timer, 0)
        for _ in range(int(2 * 60) + 10):
            self.game.update(FRAME)
        self.assertEqual(self.game.toast_timer, 0.0)

    # ------------------------------------------------------------ 键盘
    def test_escape_returns_to_the_menu(self):
        self.game.start_level(0)
        self.game.handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode=""))
        self.assertEqual(self.game.scene, SCENE_MENU)

    def test_escape_closes_the_settings_panel_first(self):
        self.game.start_level(0)
        self.game.open_settings()
        self.game.handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, unicode=""))
        self.assertIsNone(self.game.overlay)
        self.assertEqual(self.game.scene, SCENE_PLAY)

    def test_r_restarts_the_level(self):
        self.game.start_level(0)
        piece = self.game.board.available_arrows()[0]
        self.game.click_cell(*piece.head)
        self.game.handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_r, unicode="r"))
        self.assertEqual(self.game.board.remaining, LEVELS[0].arrow_count)

    def test_h_and_g_shortcuts(self):
        self.game.start_level(0)
        self.game.handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_h, unicode="h"))
        self.assertIsNotNone(self.game.hint_piece)
        self.game.handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g, unicode="g"))
        self.assertTrue(self.game.show_guides)

    def test_plus_and_minus_zoom_shortcuts(self):
        self.game.start_level(0)
        self.game.set_zoom_ratio(0.5)
        start = self.game.zoom
        self.game.handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_EQUALS, unicode="+"))
        self.assertGreater(self.game.zoom, start)
        self.game.handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_MINUS, unicode="-"))
        self.assertAlmostEqual(self.game.zoom, start, delta=0.011)

    def test_space_starts_the_game_from_the_menu(self):
        self.game.enter_menu()
        self.game.handle_key(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_SPACE, unicode=" "))
        self.assertEqual(self.game.scene, SCENE_PLAY)

    # ------------------------------------------------------------ 教学关
    def test_tutorial_runs_through_all_steps(self):
        """教学关的每一步期望值都必须和实际结果对上——教程骗人会直接误导玩家。"""
        self.game.start_tutorial()
        self.assertTrue(self.game.in_tutorial)
        seen = []
        for index, step in enumerate(TUTORIAL.steps):
            piece = self.game.board.piece_at(step.row, step.col)
            self.assertIsNotNone(piece, "第 %d 步的引导格子已经是空的了" % (index + 1))
            result = self.game.click_cell(step.row, step.col)
            self.assertEqual(result.kind, step.expect,
                             "教学第 %d 步：期望 %s，实际 %s"
                             % (index + 1, step.expect, result.kind))
            seen.append(result.kind)
            self.assertEqual(self.game.tutorial_index, index + 1)
        self.assertEqual(set(seen), {"fly", "blocked"})
        self.assertTrue(self.game.tutorial_done)

    def test_tutorial_does_not_score_or_unlock(self):
        self.game.start_tutorial()
        for piece in self.game.board.solution():
            self.game.click_cell(*piece.head)
        for _ in range(_RESULT_FRAMES):
            self.game.update(FRAME)
        self.assertEqual(self.game.overlay, OVERLAY_TUTORIAL_DONE)
        self.assertEqual(self.game.last_score, 0)
        self.assertEqual(self.progress.cleared_count(TOTAL_LEVELS), 0)
        self.assertFalse(self.progress.is_unlocked(1, TOTAL_LEVELS))

    def test_tutorial_can_be_replayed(self):
        self.game.start_tutorial()
        for piece in self.game.board.solution():
            self.game.click_cell(*piece.head)
        for _ in range(_RESULT_FRAMES):
            self.game.update(FRAME)
        self.game.start_tutorial()
        self.assertEqual(self.game.board.remaining, TUTORIAL.arrow_count)
        self.assertEqual(self.game.tutorial_index, 0)
        self.assertFalse(self.game.tutorial_done)

    def test_tutorial_shows_a_hint_ring_on_the_current_target(self):
        self.game.start_tutorial()
        step = TUTORIAL.steps[0]
        self.assertEqual(self.game.tutorial_target().head,
                         self.game.board.piece_at(step.row, step.col).head)
        self.game.draw()

    def test_tutorial_bar_is_inside_the_window(self):
        self.game.start_tutorial()
        rect = self.game.tutorial_bar_rect
        self.assertGreaterEqual(rect.left, 0)
        self.assertLessEqual(rect.right, config.WINDOW_WIDTH)
        self.assertLessEqual(rect.bottom, config.WINDOW_HEIGHT)
        self.assertGreaterEqual(rect.top, 0)
        self.game.draw()

    def test_tutorial_bar_does_not_overlap_the_toolbar(self):
        self.game.start_tutorial()
        self.assertFalse(self.game.tutorial_bar_rect.colliderect(self.game.toolbar_rect),
                         "讲解条压在工具栏上了")

    def test_tutorial_viewport_leaves_room_for_the_bar(self):
        """讲解条要占掉一块地方，棋盘视口得相应让出来，否则会叠在一起。"""
        self.game.start_tutorial()
        with_bar = self.game.viewport_rect
        self.game.enter_menu()
        self.game.start_level(0)
        without_bar = self.game.viewport_rect
        self.assertLess(with_bar.height, without_bar.height)

    def test_tutorial_skips_steps_that_no_longer_apply(self):
        """玩家完全可以乱点；不管怎么点，引导都不能指着一支已经飞走的箭头。"""
        self.game.start_tutorial()
        for piece in list(self.game.board.pieces):
            self.game.click_cell(*piece.head)
            if self.game.board.state != STATE_PLAYING:
                break
        if not self.game.tutorial_done:
            piece = self.game.tutorial_target()
            self.assertIsNotNone(piece)
            self.assertTrue(self.game.board.can_fly(piece))
        self.game.draw()

    # ------------------------------------------------------------ 示例小图
    def test_menu_demo_specs_match_their_captions(self):
        """主菜单那两张小图的画面必须和说明文字一致。

        被挡那张：正好一支被挡，而且是「橙色」那支（说明文字点了名）；
        通畅那张：唯一一支能飞。
        早先写成了两支互指，两张图里两支都被挡住，文字和画面对不上。
        """
        blocked_level = make_level(DEMO_BLOCKED_SPECS, DEMO_ROWS, DEMO_COLS, name="示例被挡")
        board = Board(blocked_level)
        # 颜色要按 demo_pieces 取（主菜单画的就是它），不能按 Level 取——
        # Level 会自己跑一遍 assign_colors，那套配色跟说明文字里点名的颜色无关。
        palettes = [p.color for p in demo_pieces(DEMO_BLOCKED_SPECS)]
        states = [(palettes[i], board.can_fly(p))
                  for i, p in enumerate(board.pieces)]
        self.assertEqual([can for _, can in states].count(False), 1)
        self.assertEqual([can for _, can in states].count(True), 1)
        orange = [color for color, can in states if not can][0]
        self.assertEqual(orange, DEMO_COLORS[1],
                         "说明文字里写的是「橙色那支被挡」，画出来的却换色了")
        self.assertIn("橙色", DEMO_BLOCKED_CAPTION)

        clear_board = Board(make_level(DEMO_CLEAR_SPECS, DEMO_ROWS, DEMO_COLS, name="示例通畅"))
        self.assertEqual(len(clear_board.pieces), 1)
        self.assertTrue(clear_board.can_fly(clear_board.pieces[0]))
        self.assertEqual(demo_pieces(DEMO_CLEAR_SPECS)[0].color, DEMO_COLORS[0])

    def test_demo_specs_parse_and_are_deterministic(self):
        first = demo_pieces(DEMO_BLOCKED_SPECS)
        second = demo_pieces(DEMO_BLOCKED_SPECS)
        self.assertIs(first, second)                    # 走缓存
        for index, piece in enumerate(first):
            self.assertEqual(piece.color, DEMO_COLORS[index % len(DEMO_COLORS)])

    def test_demo_colors_are_distinct(self):
        self.assertEqual(len(set(DEMO_COLORS)), len(DEMO_COLORS))

    # ------------------------------------------------------------ 事件循环
    def test_event_handling_smoke(self):
        """走一遍真实事件分发：移动 / 按下 / 松开 / 按键，都不能抛异常。"""
        self.game.start_level(0)
        events = [
            pygame.event.Event(pygame.MOUSEMOTION, pos=(300, 400), rel=(0, 0), buttons=(0, 0, 0)),
            pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=(300, 400), button=1),
            pygame.event.Event(pygame.MOUSEBUTTONUP, pos=(300, 400), button=1),
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_g, unicode="g"),
            pygame.event.Event(pygame.KEYUP, key=pygame.K_g, unicode="g"),
        ]
        for event in events:
            self.game.handle_event(event)
        self.game.draw()

    def test_quit_sets_the_running_flag(self):
        self.assertTrue(self.game.running)
        self.game.quit()
        self.assertFalse(self.game.running)


# ---------------------------------------------------------------- 视觉一致性
class VisualVarietyTestCase(unittest.TestCase):
    """画面本身的检查：颜色够不够分散、每个界面都画得出来。"""

    @classmethod
    def setUpClass(cls):
        pygame.init()
        cls.screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        ui.clear_caches()

    @classmethod
    def tearDownClass(cls):
        pygame.quit()

    def setUp(self):
        self.dir = tempfile.mkdtemp(prefix="oa_vis_")
        self.game = Game(self.screen, Progress(path=os.path.join(self.dir, "p.json")))

    def tearDown(self):
        shutil.rmtree(self.dir, ignore_errors=True)

    def enter_level(self, index):
        """进入第 index 关（先把全部关卡解锁，见 GameFlowTestCase 里的说明）。"""
        self.game.progress.mark_all_cleared(TOTAL_LEVELS)
        self.assertTrue(self.game.start_level(index))
        return self.game

    def test_levels_use_a_variety_of_colors(self):
        """一支一色但整体太单调也不行——每关用到的颜色种类要够多。"""
        for level in LEVELS:
            used = {piece.color for piece in level.pieces}
            self.assertGreaterEqual(len(used), 4,
                                    "「%s」只用了 %d 种颜色" % (level.name, len(used)))

    def test_colors_come_from_the_palette(self):
        for level in LEVELS:
            for piece in level.pieces:
                self.assertIn(piece.color, PIECE_PALETTE)

    def test_no_two_adjacent_pieces_share_a_color_in_any_level(self):
        for index in range(TOTAL_LEVELS):
            self.enter_level(index)
            level = LEVELS[index]
            for left, right in neighbour_pairs(level):
                self.assertNotEqual(level.pieces[left].color, level.pieces[right].color,
                                    "第 %d 关里有相邻同色" % (index + 1))

    def test_every_level_draws_and_saves(self):
        """每个关卡都完整画一遍——渲染报错在这一步就该暴露。"""
        for index in range(TOTAL_LEVELS):
            self.enter_level(index)
            self.game.draw()
            self.game.set_zoom_ratio(1.0)
            self.game.draw()
            self.game.set_zoom_ratio(0.0)
            self.game.draw()
            self.game.set_zoom_ratio(config.ZOOM_DEFAULT)

    def test_every_level_draws_with_guides_and_hover(self):
        """辅助线 + 悬停高亮一起上的时候最容易漏画或画错层，逐关过一遍。"""
        for index in range(TOTAL_LEVELS):
            self.enter_level(index)
            self.game.toggle_guides()
            for row, col in ((0, 0), (1, 1), (2, 2)):
                self.game.mouse_pos = self.game.cell_center(row, col)
                self.game.update_hover()
                self.game.draw()

    def test_every_level_draws_with_animations_running(self):
        """动画播到一半时也要能画——撞击那支的染色贴图只在闪得厉害时才用到。"""
        for index in range(TOTAL_LEVELS):
            self.enter_level(index)
            piece = self.game.board.available_arrows()[0]
            blocked = [p for p in self.game.board.pieces if not self.game.board.can_fly(p)]
            self.game.click_cell(*piece.head)
            if blocked:
                self.game.click_cell(*blocked[0].head)
            while self.game.animations:
                self.game.update(FRAME)
                self.game.draw()

    def test_hover_highlight_works_on_any_cell_of_a_pipe(self):
        self.enter_level(0)
        piece = self.game.board.available_arrows()[0]
        for cell in piece.cells:
            self.game.mouse_pos = self.game.cell_center(*cell)
            self.game.update_hover()
            hovered = self.game.hovered_piece()
            self.assertIsNotNone(hovered)
            self.assertEqual(hovered.head, piece.head)
        self.game.draw()

    def test_hover_on_empty_cell_highlights_nothing(self):
        self.enter_level(0)
        for row in range(self.game.board.rows):
            for col in range(self.game.board.cols):
                if self.game.board.piece_at(row, col) is None:
                    self.game.mouse_pos = self.game.cell_center(row, col)
                    self.game.update_hover()
                    self.assertIsNone(self.game.hovered_piece())
                    return
        self.skipTest("第 1 关没有空格")

    def test_render_does_not_mutate_the_board(self):
        """画一遍不能改棋盘状态——渲染和逻辑必须完全分开。"""
        self.enter_level(3)
        snapshot = (self.game.board.remaining, self.game.board.hp, self.game.board.state)
        self.game.mouse_pos = self.game.cell_center(0, 0)
        self.game.update_hover()
        self.game.draw()
        self.game.update(FRAME)
        self.game.draw()
        self.assertEqual((self.game.board.remaining, self.game.board.hp,
                          self.game.board.state), snapshot)


def main():
    """直接 python tests/test_game.py 时的入口：跑全部用例并打印统计。"""
    loader = unittest.TestLoader()
    suite = loader.loadTestsFromModule(sys.modules[__name__])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    print()
    print("用例总数：%d" % result.testsRun)
    print("失败：%d    错误：%d    跳过：%d"
          % (len(result.failures), len(result.errors), len(result.skipped)))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
