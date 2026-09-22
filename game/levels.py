# -*- coding: utf-8 -*-
"""关卡数据。

写法
----
每支箭写成一行字符串，四个部分用空格分开::

    "行,列 方向 路径"

行、列从 0 开始编号，方向是 ``^ v < >``（上 / 下 / 左 / 右），
路径是一串 ``方向字母 + 格数``，字母 ``U D L R`` 对应上 / 下 / 左 / 右::

    "4,6 > D3R2"     从第 4 行第 6 列出发，箭头朝右，
                     管道先向下 3 格、再向右 2 格，共 6 格

**箭头在路径的末端**——也就是最后经过的那一格。路径必须逐格相邻、不能和自己交叉，
而且最后一段必须和箭头方向一致（不然画出来的箭头会歪在拐角上）。
这几条都由 pieces.validate_layout 把关，写错了导入时就会报错。

设计原则
--------
「难」来自**要扫多少条射线**：棋盘越大、管道越多，越难一眼找出能点的那支。
所以九个关卡的尺寸与管道数是一级一级加上去的：

    第 1 关  11×8   21 支   开局 7 支能点
    第 2 关  13×9   23 支   开局 6 支
    第 3 关  14×10  22 支   开局 5 支
    ...
    第 9 关  26×18  46 支   开局 3 支

尺寸一律取**竖着的**（行数 > 列数）：这个游戏按手机竖屏比例做
（窗口 600×960，棋盘视口约 572×728），竖长方形的棋盘才能把视口填满，
不至于上下各空出一条。生成器也是按这个比例出题的。

真正决定手感的是**开局可点数**：可点数越多越容易。它不是随手定的数，
而是每一步的难度台阶，由 tools/pick_levels.py 从生成器的候选里挑出来
（同一尺寸下挑「铺满率最高 + 可点数最接近目标」的那一版）。

第 5~9 关由 tools/generate_levels.py **逆向构造**生成：
把「消除顺序」倒过来当「放置顺序」，放置时要求新箭的射线上没有已放好的箭，
于是「放置顺序的倒序」天然就是一条合法通关顺序，布局必然可解。
生成完还要过两道保险——tools/verify_levels.py 与 tests/test_game.py
都会真的把这个布局解一遍。

教学关不算一关
--------------
教学关单独放在 TUTORIAL 里，**不在 LEVELS 里**：不计分、不占编号、不需要解锁，
主菜单上有单独入口，随时可以回去复习。编号因此从第 1 关「初次拉弓」干净地开始。

生命值为什么逐关变多
--------------------
管道越到后面越多，要逐条扫视的射线也越多，越容易点错，
所以生命值上限不是固定值，而是**按难度星级给**（见 HP_BY_STARS）：
第 1 关 4 颗心，最后一关 7 颗心。容错和难度一起往上走，
玩家不会在最后一关因为一次手滑就被打回原点。
教学关不走这张表：它单独给 6 颗心，是个随便点的沙盒，
不该让人在教程里被判失败。

得分规则见 game/scoring.py：本关得分 = 星级 × 250 × 剩余生命值 ÷ 生命值上限，
一颗心都没丢再额外加 20%。每关满分因此正好是「星级 × 300」。
"""

import re
from dataclasses import dataclass, field

from . import pieces
from .pieces import Piece

# 生命值上限 = 按难度星级给。星级越高（越难），容错越高。
# 只有 LEVELS 里的编号关卡走这张表；教学关单独给 TUTORIAL_HP。
HP_BY_STARS = {1: 4, 2: 5, 3: 6, 4: 6, 5: 7}
TUTORIAL_HP = 6

# ---- 难度分与星级的换算 ----
# 难度分只回答一个问题：**这一关要玩家扫多少地方**。
# 三个来源，权重都是在九个关卡上试出来的：
#   * 管道支数——每支都要看一眼它的箭头朝哪；
#   * 棋盘格数——空格也要扫过去（0.12 是「每 8 格相当于一支管道」的量级）；
#   * 开局可点数——能直接点的越多越省事，所以是负贡献。
#
# 刻意**不含生命值**：生命值是由难度分推出来的，要是再算进难度分，
# 就成了「难度高 → 给的心多 → 难度算下来变低」的循环，星级会跟着乱跳。
PIECE_WEIGHT = 1.6
CELL_WEIGHT = 0.12
FREE_WEIGHT = 3.0

# 星级阈值：把九个关卡的实际难度分切成 1~5 星。
# 目标不是「均匀分档」，而是**让星数一路不回头**（见 tests 里的用例）。
STAR_THRESHOLDS = ((35.0, 1), (45.0, 2), (70.0, 3), (100.0, 4))


@dataclass
class TutorialStep:
    """教学关的一步引导。

    target 指定「希望玩家点哪一格」（点这支箭身上的任意一格都算），
    expect 指定期望的结果："fly"（应该飞出去）/ "blocked"（应该被挡住）。
    """

    text: str
    row: int
    col: int
    expect: str


@dataclass
class Level:
    """一个关卡。

    specs 是 pieces.parse_piece 能读的字符串，见模块开头的写法说明。
    max_hp 由星级推导（HP_BY_STARS），不单独写——两处各写一个数迟早会对不上。
    """

    name: str
    hint: str
    rows: int
    cols: int
    specs: tuple
    tutorial: bool = False
    steps: tuple = ()
    pieces: tuple = field(default=(), init=False)      # 解析出来的 Piece（带颜色）
    _difficulty: float = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if self.rows <= 0 or self.cols <= 0:
            raise ValueError("关卡「%s」的尺寸不合法" % self.name)
        parsed = []
        for index, spec in enumerate(self.specs):
            cells, direction = pieces.parse_piece(spec)
            parsed.append(Piece(cells=cells, direction=direction, uid=index))
        pieces.validate_layout(self.rows, self.cols, parsed)
        colors = pieces.assign_colors(parsed, self.rows, self.cols)
        parsed = [Piece(cells=p.cells, direction=p.direction, color=color, uid=p.uid)
                  for p, color in zip(parsed, colors)]
        self.pieces = tuple(parsed)

        if self.tutorial and not self.steps:
            raise ValueError("教学关「%s」必须提供引导步骤" % self.name)

    # ------------------------------------------------------------ 基本指标
    @property
    def arrow_count(self):
        """本关管道（箭）的支数。旧名字沿用，文档与测试都在用。"""
        return len(self.pieces)

    @property
    def free_count(self):
        """开局就能直接飞出去的支数（越少越难找）。"""
        from .board import count_free_pieces
        return count_free_pieces(self.rows, self.cols, self.pieces)

    @property
    def density(self):
        """铺满率 = 被管道占掉的格子 ÷ 全部格子。

        这一版棋盘是密密麻麻铺满的（参照画面就是这样），所以这个数普遍在
        0.93 以上；它衡量的是「画面有多满」，不再用来当难度。
        """
        used = sum(piece.length for piece in self.pieces)
        return used / float(self.rows * self.cols)

    @property
    def max_hp(self):
        """本关生命值上限。教学关单独一档，编号关卡按星级给。"""
        return TUTORIAL_HP if self.tutorial else HP_BY_STARS[self.stars]

    @property
    def difficulty_score(self):
        """难度分（越大越难），含义见模块开头的说明。"""
        if self._difficulty is None:
            self._difficulty = (self.arrow_count * PIECE_WEIGHT
                                + self.rows * self.cols * CELL_WEIGHT
                                - self.free_count * FREE_WEIGHT)
        return self._difficulty

    @property
    def stars(self):
        """把难度分映射成 1~5 颗星（关卡总览里显示），也决定本关给几颗心。"""
        if self.tutorial:
            return 1
        score = self.difficulty_score
        for threshold, stars in STAR_THRESHOLDS:
            if score < threshold:
                return stars
        return 5

    def solution(self):
        """返回一个可行的通关顺序（每项是一支箭）；无解返回 None。"""
        from .board import solve_level
        return solve_level(self.rows, self.cols, self.pieces)


# ============================================================ 教学关（独立一档）
#  刻意**不放进 LEVELS**：它不计分、不占关卡编号、不需要解锁，
#  主菜单上有单独入口（也随时可以回去复习）。
#  三支管道，把「前方空 → 能飞 / 前方有管道 → 飞不出去」走一遍：
#      A 2,0 > R2   横躺的三格，箭头朝右，正前方被 B 挡着
#      B 2,3 v D2   竖着的三格，箭头朝下，前方一路空到盘外
#      C 0,4 v D    竖着的两格，箭头朝下，也是通的
TUTORIAL = Level(
    name="教学关",
    hint="跟着黄色高亮环点，很快就能上手",
    rows=5,
    cols=5,
    tutorial=True,
    specs=(
        "2,0 > R2",
        "2,3 v D2",
        "0,4 v D",
    ),
    steps=(
        TutorialStep("先点最长的那支横躺的管道。它箭头正前方还压着别的管道，"
                     "飞不出去，会丢掉一颗心——这就是「被挡住」。", 2, 0, "blocked"),
        TutorialStep("再看那支竖着的：它箭头朝下，前方一路空到棋盘外，"
                     "点它就会整条飞出去。", 4, 3, "fly"),
        TutorialStep("挡路的走开了。再点刚才那支横躺的，这次它前方是空的，"
                     "也能飞出去了。", 2, 0, "fly"),
        TutorialStep("最后点掉右上角那一支，本关就通了。"
                     "记住：谁的箭头前方是空的，谁就能飞。", 1, 4, "fly"),
    ),
)


LEVELS = (
    # ======================================================== 第 1 关
    #  初次拉弓  11×8  箭 21 支  开局可点 7  seed=14
    #  点朝外的那几支，先开出一条路
    Level(
        name='初次拉弓',
        hint='点朝外的那几支，先开出一条路',
        rows=11,
        cols=8,
        specs=(
            '10,3 ^ L3U',
            '10,4 ^ R3U',
            '9,2 ^ LULU',
            '9,5 ^ RURU',
            '9,3 ^ RURU',
            '3,7 < U3L',
            '8,2 ^ RURU',
            '4,6 < U3L',
            '7,2 ^ UL2U',
            '3,0 > DRDR',
            '5,5 < U3L',
            '6,3 ^ U2LU',
            '5,4 ^ U2LU',
            '0,5 < LDL2',
            '3,1 ^ ULU2',
            '6,5 > RUR',
            '1,1 ^ U',
            '4,7 > ',
            '6,7 > ',
            '0,2 ^ ',
            '0,3 ^ ',
        ),
    ),
    # ======================================================== 第 2 关
    #  交叉路口  13×9  箭 23 支  开局可点 6  seed=25
    #  开局能点的很少，先找朝外的
    Level(
        name='交叉路口',
        hint='开局能点的很少，先找朝外的',
        rows=13,
        cols=9,
        specs=(
            '12,4 ^ L4U',
            '12,5 ^ R3U2',
            '11,3 ^ R4U',
            '11,2 ^ LULU2',
            '10,4 ^ L2ULU',
            '10,5 ^ RUR2U',
            '4,0 > U4R',
            '9,4 ^ RUR2U',
            '5,0 > D2RUR',
            '1,1 > D4R',
            '9,3 ^ ULURU',
            '4,2 > U4R',
            '8,4 ^ UR2U2',
            '7,8 ^ ULURU',
            '5,3 > U4R',
            '6,4 > U4R',
            '6,5 ^ U2R2U',
            '3,6 ^ UR2U2',
            '1,5 ^ R2U',
            '3,8 > ',
            '0,6 ^ ',
            '0,5 ^ ',
            '0,4 ^ ',
        ),
    ),
    # ======================================================== 第 3 关
    #  连锁反应  14×10  箭 22 支  开局可点 5  seed=50
    #  消掉一支，往往就有新的一支能走了
    Level(
        name='连锁反应',
        hint='消掉一支，往往就有新的一支能走了',
        rows=14,
        cols=10,
        specs=(
            '0,5 v L5D',
            '13,4 ^ R5U',
            '12,5 ^ R3URU',
            '1,4 v L3DLD',
            '11,6 ^ RURURU',
            '2,3 v LDLDLD',
            '11,5 ^ URURU2',
            '11,4 ^ U2RURU',
            '6,9 < U2LD2L',
            '4,3 v LDLDLD',
            '3,3 v RD2LD2',
            '6,6 v L2D2LD',
            '6,2 v DLDLD2',
            '8,2 v DLDR2D',
            '5,6 ^ RU2R2U',
            '4,5 > U3RUR',
            '12,4 < LDLU2L',
            '4,6 > U2RUR2',
            '11,0 v DRD',
            '8,8 > UR',
            '0,8 > R',
            '13,0 < ',
        ),
    ),
    # ======================================================== 第 4 关
    #  四面楚歌  16×11  箭 27 支  开局可点 5  seed=47
    #  上下左右都要扫一遍
    Level(
        name='四面楚歌',
        hint='上下左右都要扫一遍',
        rows=16,
        cols=11,
        specs=(
            '0,5 v L5D',
            '15,7 ^ R3U3',
            '15,5 ^ RUR3U',
            '1,4 v L3DLD',
            '13,7 ^ RURURU',
            '2,2 v DLDLD2',
            '0,6 v DLDL2D',
            '3,4 v DL2DLD',
            '5,3 v DLDL2D',
            '2,6 v DLD2LD',
            '12,0 > U3RUR',
            '11,7 ^ RURURU',
            '5,6 v DLDL2D',
            '9,7 ^ RURURU',
            '9,5 ^ LUR3U',
            '7,8 ^ URURU2',
            '9,2 v RDL2D2',
            '10,6 < D3LDL',
            '4,6 > RU4R',
            '10,4 v RDL3D',
            '6,7 ^ URURU2',
            '12,4 v LDL3D',
            '15,4 < LUL2DL',
            '3,8 > U2RUR',
            '15,2 v ',
            '2,10 > ',
            '1,10 > ',
        ),
    ),
    # ======================================================== 第 5 关
    #  错位走廊  18×12  箭 28 支  开局可点 4  seed=19
    #  管道更长，先看清它朝哪边
    Level(
        name='错位走廊',
        hint='管道更长，先看清它朝哪边',
        rows=18,
        cols=12,
        specs=(
            '0,6 v L6D',
            '17,7 ^ R4U3',
            '17,5 ^ RUR4U',
            '1,5 v L4DLD',
            '15,7 ^ R2URURU',
            '14,8 ^ URURURU',
            '2,4 v L2DLDLD',
            '3,3 v DLDLDLD',
            '11,8 ^ RURURU2',
            '0,7 v DLDLDLD',
            '5,3 v DLDLDLD',
            '2,7 v DLDLDLD',
            '11,7 ^ URURURU',
            '7,3 v DLDLDLD',
            '4,7 v DLDLDLD',
            '8,7 ^ RURUR2U',
            '9,7 ^ LU2RURU',
            '8,5 v DL2D2',
            '14,7 < LDLDLDL',
            '12,8 < LDL2DL2',
            '11,6 < UL2D3L',
            '10,2 v DLDLD2',
            '5,10 ^ LUR2ULU',
            '12,3 v LDLD2LD',
            '4,8 > U4R3',
            '15,4 < LDLDL2',
            '3,9 > U2R2',
            '2,11 > ',
        ),
    ),
    # ======================================================== 第 6 关
    #  纵横交错  20×14  箭 37 支  开局可点 4  seed=6
    #  别只盯着中间，边角往往藏着出口
    Level(
        name='纵横交错',
        hint='别只盯着中间，边角往往藏着出口',
        rows=20,
        cols=14,
        specs=(
            '19,6 ^ L6U',
            '19,9 ^ R4U3',
            '19,7 ^ RUR4U',
            '18,5 ^ L4ULU',
            '17,9 ^ R2URURU',
            '17,4 ^ L2ULULU',
            '16,3 ^ ULULULU',
            '18,7 ^ LULULU',
            '6,0 > U6R',
            '16,10 ^ URURURU',
            '14,10 ^ URURURU',
            '17,8 ^ LUR2U2',
            '5,1 > U4RUR',
            '16,6 ^ UR2U',
            '12,10 ^ URURURU',
            '15,5 ^ UR2UR2U',
            '4,2 > U2RURUR',
            '8,0 > URURUR2',
            '9,0 > RURURUR',
            '13,5 ^ RUR2URU',
            '14,4 ^ U2RU2RU',
            '10,10 ^ URURURU',
            '3,3 > RURURUR',
            '11,7 ^ URURU3',
            '4,4 > RD2RU2R',
            '10,4 ^ U2R4U',
            '7,4 ^ R3U2RU',
            '3,5 > RURURUR',
            '8,10 ^ URURURU',
            '3,7 > RURURUR',
            '6,10 ^ URURURU',
            '5,9 > URU2RUR',
            '10,3 < D3LU2L',
            '8,3 < DLDL2',
            '0,12 > R',
            '1,13 > ',
            '11,0 < ',
        ),
    ),
    # ======================================================== 第 7 关
    #  长蛇阵  22×15  箭 38 支  开局可点 3  seed=136
    #  一支挨着一支，顺序想好再点
    Level(
        name='长蛇阵',
        hint='一支挨着一支，顺序想好再点',
        rows=22,
        cols=15,
        specs=(
            '0,6 v L6D2',
            '0,8 v R6D2',
            '0,7 v DL6D',
            '1,9 v R4D2RD',
            '2,4 v L2DL2D3',
            '2,6 v LDL2DL2D',
            '1,8 v DR4D',
            '3,9 v R2DR2DRD',
            '15,14 < D6L2',
            '4,4 v DL2DLDLD',
            '2,7 v DLDLD',
            '17,13 < D3L2DL2',
            '14,14 < LD2LD3L',
            '7,14 < D6L',
            '6,4 v LDLDLDLD',
            '8,4 v LDLDLDLD',
            '3,8 v DLDLDLD2',
            '4,10 v LDLDLDLD',
            '9,13 < D3LD3L',
            '8,7 v DL3D2RD',
            '5,12 v L2DLDLD2',
            '8,10 v DLDL2DLD',
            '17,11 < DLD2L2DL',
            '14,11 < LD3LD2L',
            '8,13 < LD3LD2L',
            '8,11 < D2LD2LDL',
            '10,3 v DLDLDLD2',
            '11,9 v LDLDL2D',
            '16,8 < D2LD2LDL',
            '16,9 < U2L2D3L',
            '12,3 v RDL2DLD',
            '14,4 v LDLDL2D',
            '15,6 v L2DLDL2D',
            '18,6 < DLDLDLUL',
            '16,6 < LD2LDL3',
            '18,0 v D2RD',
            '21,0 < ',
            '21,2 v ',
        ),
    ),
    # ======================================================== 第 8 关
    #  十面埋伏  23×17  箭 43 支  开局可点 3  seed=19
    #  开局只有两三支能动，慢慢找
    Level(
        name='十面埋伏',
        hint='开局只有两三支能动，慢慢找',
        rows=23,
        cols=17,
        specs=(
            '22,9 ^ R7U',
            '0,7 v L7D',
            '1,4 v L3DLD3',
            '1,6 v LDL3DLD',
            '21,11 ^ R4URU2',
            '20,13 ^ RURU2RU2',
            '3,3 v DLDLDLD2',
            '18,13 ^ U2R2U2RU',
            '22,8 ^ UR2UR2U2',
            '22,7 ^ U2R2UR2U',
            '19,7 ^ RURUR3U',
            '3,4 v D2LDLDLD',
            '0,9 v LDLDLDLD',
            '6,4 v DLDLDL2D',
            '8,4 v DLDL2DLD',
            '16,8 ^ R3UR3U',
            '2,8 v DLDLDLD2',
            '14,12 ^ RUR2URU2',
            '14,11 ^ URUR2URU',
            '2,9 v D2LDLDLD',
            '18,6 ^ RU3R3U',
            '12,2 > UR2URU2R',
            '11,11 ^ R2URUR2U',
            '10,12 ^ URUR2URU',
            '14,8 ^ RURU3RU',
            '12,4 v LDL3D3',
            '7,8 v LD2LD2LD',
            '12,6 v DL2DL3D',
            '15,4 v L2DLDLD2',
            '8,12 ^ UR2URURU',
            '11,9 v DLDLDL2D',
            '11,7 ^ RURURURU',
            '5,9 > RU5R2',
            '7,10 > URU5R',
            '16,6 v L3DLDLD',
            '6,12 > U4RU2R',
            '19,6 < D3L3UL',
            '17,6 < LD4LUL',
            '17,4 v DLDLDL2D',
            '6,13 ^ URURURU2',
            '4,13 > URU2RUR',
            '21,1 < DL',
            '22,2 v ',
        ),
    ),
    # ======================================================== 第 9 关
    #  万箭归一  26×18  箭 46 支  开局可点 3  seed=42
    #  全场只剩几个出口，每一步都要算
    Level(
        name='万箭归一',
        hint='全场只剩几个出口，每一步都要算',
        rows=26,
        cols=18,
        specs=(
            '25,10 ^ R7U2',
            '25,7 ^ L7U2',
            '24,12 ^ R4U2RU2',
            '24,6 ^ L5U2LU',
            '25,8 ^ ULUL5U',
            '25,9 ^ UR2UR4U',
            '22,12 ^ R2UR2U2RU',
            '22,6 ^ L3UL2ULU',
            '23,10 ^ URUR2UR2U',
            '21,4 ^ UL2ULULU2',
            '20,12 ^ UR2UR2URU',
            '23,9 ^ LURURURU',
            '7,0 > U7R2',
            '8,0 > RU7R',
            '18,12 ^ RUR2URURU',
            '7,2 > U5RU2R',
            '22,7 ^ UL2U',
            '16,12 ^ R2URURURU',
            '6,3 > U3RU2RUR',
            '21,8 ^ ',
            '20,6 ^ R3URURU2',
            '15,0 > U6R',
            '19,4 ^ R4URURU',
            '15,13 ^ URURURURU',
            '5,4 > URU2RURUR',
            '18,7 ^ URURUR3U',
            '8,2 > RURUR2DR2',
            '16,1 > U6RUR',
            '13,2 > U2RURU2R2',
            '14,2 > RU2RURU2R',
            '13,4 > RURU2RU2R',
            '13,13 ^ URURURURU',
            '16,7 ^ URUR3URU',
            '14,6 ^ URU2RU2RU',
            '13,9 ^ RURURUL2U',
            '5,6 > U2RURURUR',
            '11,13 ^ URURURURU',
            '4,7 > RURURURUR',
            '5,7 > DR2U2RUR',
            '9,13 ^ URURURURU',
            '9,11 ^ RU2RURURU',
            '8,10 ^ RU2RURURU',
            '7,9 > RU2RURU2R',
            '1,12 > RURD2RDR2',
            '1,15 > URD2R',
            '1,17 ^ U',
        ),
    ),
)

TOTAL_LEVELS = len(LEVELS)


def get_level(index):
    """按下标取关卡，越界时抛 IndexError。"""
    return LEVELS[index]


def report_for(level, index, tutorial=False):
    """校验单个关卡并整理成报告条目（index 用显示用的关号）。

    教学关和编号关卡共用这一份，只是 index 传 0、tutorial 传 True。
    """
    from .scoring import max_score

    order = level.solution()
    return {
        "index": index,
        "name": level.name,
        "size": "%d×%d" % (level.rows, level.cols),
        "arrows": level.arrow_count,
        "density": level.density,
        "free": level.free_count,
        "solvable": order is not None,
        "order": order or [],
        "max_hp": level.max_hp,
        "stars": level.stars,
        "max_score": max_score(level),
        "difficulty": level.difficulty_score,
        "tutorial": tutorial,
    }


def validate_levels():
    """检查全部编号关卡：布局是否合法、是否可解。

    返回 [{'index', 'name', 'size', 'arrows', 'density', 'free', 'solvable', 'order',
            'max_hp', 'stars', 'max_score', 'difficulty', 'tutorial'}]。
    """
    return [report_for(level, index) for index, level in enumerate(LEVELS, start=1)]


def validate_tutorial():
    """单独校验教学关（它不在 LEVELS 里，所以不进 validate_levels 的循环）。"""
    return report_for(TUTORIAL, 0, tutorial=True)
