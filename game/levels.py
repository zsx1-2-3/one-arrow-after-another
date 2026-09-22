# -*- coding: utf-8 -*-
"""关卡数据。

写法
----
每支箭写成一行字符串，四个部分用空格分开::

    "行,列 方向 路径"

行、列从 0 开始编号，方向是 ``^ v < >``（上 / 下 / 左 / 右），
路径是一串 ``方向字母 + 格数``，字母 ``U D L R`` 对应上 / 下 / 左 / 右::

    "4,6 > D3R2"     从第 4 行第 6 列出发，箭头朝右，
                     箭头先向下 3 格、再向右 2 格，共 6 格

**箭头在路径的末端**——也就是最后经过的那一格。路径必须逐格相邻、不能和自己交叉，
而且最后一段必须和箭头方向一致（不然画出来的箭头会歪在拐角上）。
这几条都由 pieces.validate_layout 把关，写错了导入时就会报错。

设计原则
--------
「难」来自**要扫多少条射线**：棋盘越大、箭头越多，越难一眼找出能点的那支。
所以九个关卡的尺寸与箭头数是一级一级加上去的：

    第 1 关  11×8   20 支   开局 5 支能点
    第 2 关  13×9   23 支   开局 6 支
    第 3 关  14×10  22 支   开局 5 支
    ...
    第 9 关  26×18  46 支   开局 5 支

可点数不设硬目标：能通关就行（选关器只把它当排序末位的软偏好，
第 2 关因为难度阶梯的缘故有个下限，见 tools/pick_levels.py 的 FREE_FLOOR）。
朝向均衡会把箭头往四个方向摊、天然多开几个口，这是「画面不再一边倒」
的代价，由更紧的生命值（3/4 颗）补回来。

每支箭的长度由生成器围绕「平均单支长度」大散开地抽出来：一盘里
既有两三格的短箭、也有十几格的长蛇（第 9 关 1~18 格），
长短差距本身就是观感的一部分，不再是清一色的等长箭。
后期关卡还掺了**带拐弯的蛇形箭**（C 形回折、S 形蜿蜒），
形状本身也是难度和观感的一部分。

尺寸一律取**竖着的**（行数 > 列数）：这个游戏按手机竖屏比例做
（窗口 680×880，棋盘视口约 660×690），竖长方形的棋盘才能把视口填满，
不至于上下各空出一条。生成器也是按这个比例出题的。

真正决定手感的是**开局可点数**：可点数越多越容易。它由 tools/pick_levels.py
从生成器的候选里挑出来（同一尺寸下挑「朝向最均衡 + 铺满率高 + 长短差距大」
的那一版，九关的最大单朝向占比压在 26%~44%，早年一度是 70% 一边倒）。

九个编号关卡全部由 tools/generate_levels.py **逆向构造**生成：
把「消除顺序」倒过来当「放置顺序」，放置时要求新箭的射线上没有已放好的箭，
于是「放置顺序的倒序」天然就是一条合法通关顺序，布局必然可解。
生成完还要过两道保险——tools/verify_levels.py 与 tests/test_game.py
都会真的把这个布局解一遍。

教学关不算一关
--------------
教学关单独放在 TUTORIAL 里，**不在 LEVELS 里**：不计分、不占编号、不需要解锁，
主菜单上有单独入口，随时可以回去复习。编号因此从第 1 关「初次拉弓」干净地开始。

生命值为什么是 3 颗 / 4 颗
------------------------
生命值上限按**关卡序号**给（见 HP_BY_LEVEL）：第 1~4 关 3 颗心，
第 5~9 关 4 颗心。前期棋盘小、要扫的射线少，3 颗心足够容错；
后期棋盘大、步步都要算，多给一颗心。容错随难度小幅上调，
但不像早年按星级给 4~7 颗那样宽松——心少了，每一次点错都更疼。
教学关不走这张表：它单独给 6 颗心，是个随便点的沙盒，
不该让人在教程里被判失败。

得分规则见 game/scoring.py：本关得分 = 星级 × 250 × 剩余生命值 ÷ 生命值上限，
一颗心都没丢再额外加 20%。星级只管得分和总览展示，不再决定心数。
"""

import re
from dataclasses import dataclass, field

from . import pieces
from .pieces import Piece

# 生命值上限 = 按关卡序号给：第 1~4 关 3 颗，第 5~9 关 4 颗。
# 星级只用于得分与总览展示，不再决定心数（早年按星级给 4~7 颗太宽松）。
# 每关的心数同时写在 Level.hp 字段里（选关器生成数据时带上），
# HP_BY_LEVEL 是这张表的唯一出处，测试会核对两者一致。
HP_BY_LEVEL = (3, 3, 3, 3, 4, 4, 4, 4, 4)
TUTORIAL_HP = 6

# ---- 难度分与星级的换算 ----
# 难度分只回答一个问题：**这一关要玩家扫多少地方**。
# 三个来源，权重都是在九个关卡上试出来的：
#   * 箭头支数——每支都要看一眼它的箭头朝哪；
#   * 棋盘格数——空格也要扫过去（0.12 是「每 8 格相当于一支箭头」的量级）；
#   * 开局可点数——能直接点的越多越省事，所以是负贡献。
#
# 刻意**不含生命值**：生命值是由难度分推出来的，要是再算进难度分，
# 就成了「难度高 → 给的心多 → 难度算下来变低」的循环，星级会跟着乱跳。
PIECE_WEIGHT = 1.6
CELL_WEIGHT = 0.12
FREE_WEIGHT = 3.0

# 星级阈值：把九个关卡的实际难度分切成 1~5 星。
# 目标不是「均匀分档」，而是**让星数一路不回头**、且五档都有关卡落进去
# （见 tests 里的用例）。当前九关的难度分是
# 27.6 / 32.8 / 37.0 / 52.3 / 55.7 / 77.8 / 85.4 / 103.7 / 114.8，
# 按这套阈值映射成 1/1/2/2/3/4/4/5/5 星。
STAR_THRESHOLDS = ((35.0, 1), (55.0, 2), (75.0, 3), (100.0, 4))


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
    hp 是本关生命值上限（编号关卡必填，取值见 HP_BY_LEVEL；教学关不用它，
    走 TUTORIAL_HP）。默认 3 只是为了让测试里随手构造的小关卡也能玩，
    正式关卡数据都会显式写出来。
    """

    name: str
    hint: str
    rows: int
    cols: int
    specs: tuple
    tutorial: bool = False
    steps: tuple = ()
    hp: int = 3
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
        """本关箭头（箭）的支数。旧名字沿用，文档与测试都在用。"""
        return len(self.pieces)

    @property
    def free_count(self):
        """开局就能直接飞出去的支数（越少越难找）。"""
        from .board import count_free_pieces
        return count_free_pieces(self.rows, self.cols, self.pieces)

    @property
    def density(self):
        """铺满率 = 被箭头占掉的格子 ÷ 全部格子。

        这一版棋盘是密密麻麻铺满的（参照画面就是这样），所以这个数普遍在
        0.93 以上；它衡量的是「画面有多满」，不再用来当难度。
        """
        used = sum(piece.length for piece in self.pieces)
        return used / float(self.rows * self.cols)

    @property
    def max_hp(self):
        """本关生命值上限。教学关单独一档，编号关卡用自己的 hp 字段。"""
        return TUTORIAL_HP if self.tutorial else self.hp

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
        """把难度分映射成 1~5 颗星（关卡总览里显示，也参与得分）。"""
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
#  四支箭头，把「前方空 → 能飞 / 前方有箭头 → 飞不出去」走一遍，
#  最后一支是弯的——正式关里有 C/S 形大弯箭，教学关先让玩家见过一支：
#      A 2,0 > R2   横躺的三格，箭头朝右，正前方被 B 挡着
#      B 2,3 v D2   竖着的三格，箭头朝下，前方一路空到盘外
#      C 0,4 v D    竖着的两格，箭头朝下，也是通的
#      D 0,0 < RDL  带两个同向拐弯的 C 形四格，箭头朝左，前方就是盘外
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
        "0,0 < RDL",
    ),
    steps=(
        TutorialStep("先点中间那支横躺的箭头。它箭头正前方还压着别的箭头，"
                     "飞不出去，会丢掉一颗心——这就是「被挡住」。", 2, 0, "blocked"),
        TutorialStep("再看那支竖着的：它箭头朝下，前方一路空到棋盘外，"
                     "点它就会整条飞出去。", 4, 3, "fly"),
        TutorialStep("挡路的走开了。再点刚才那支横躺的，这次它前方是空的，"
                     "也能飞出去了。", 2, 0, "fly"),
        TutorialStep("箭头不一定是直的。这种弯箭头也一样：只看「箭头尖」朝哪，"
                     "前方空着，整条就能飞出去。", 1, 1, "fly"),
        TutorialStep("最后点掉右上角那一支，本关就通了。"
                     "记住：谁的箭头前方是空的，谁就能飞。", 1, 4, "fly"),
    ),
)


LEVELS = (
    # 第 1 关：11×8，20 支，开局可点 5，铺满率 0.97，箭长 1~8，最大单朝向 30%，蛇形 C×0 S×2（seed=53）
    Level(
        name="初次拉弓",
        hint="点朝外的那几支，先开出一条路",
        rows=11,
        cols=8,
        hp=3,
        specs=(
        "10,7 ^ ",
        "0,0 v ",
        "1,0 v RDLD",
        "10,6 < ULDL3",
        "0,1 > RDR2",
        "9,7 < U2LDL",
        "2,2 > DR2",
        "7,5 ^ ",
        "6,7 ^ L2U2",
        "3,1 v DLD3",
        "4,4 < D4L",
        "0,3 > R2",
        "4,2 v RDLDLD2",
        "6,3 < DLD2LDL",
        "5,7 ^ LURU",
        "2,3 > R2",
        "3,5 ^ RURU2",
        "1,5 ^ RU",
        "8,0 < ",
        "9,0 < ",
        ),
    ),
    # 第 2 关：13×9，23 支，开局可点 6，铺满率 0.94，箭长 1~9，最大单朝向 30%，蛇形 C×0 S×2（seed=186）
    Level(
        name="交叉路口",
        hint="开局能点的很少，先找朝外的",
        rows=13,
        cols=9,
        hp=3,
        specs=(
        "0,0 v ",
        "12,1 ^ R7U",
        "1,0 > ",
        "10,8 < ",
        "0,1 > DRUR",
        "2,0 v RDLD3",
        "11,0 ^ R7U",
        "7,8 < ",
        "8,8 < DL2DL",
        "10,0 ^ R4U",
        "9,5 ^ UR2U2RU",
        "2,2 > D2R",
        "3,3 > U2RURDR",
        "8,4 < ULD2L",
        "4,1 > DR3UR",
        "7,6 ^ LU2R2URU",
        "6,4 < L2D2L",
        "12,0 v ",
        "3,4 > UR3",
        "2,8 ^ ULU",
        "6,1 < DL",
        "9,1 < L",
        "0,8 ^ ",
        ),
    ),

    # 第 3 关：14×10，22 支，开局可点 5，铺满率 0.96，箭长 1~11，最大单朝向 32%，蛇形 C×0 S×6（seed=17）
    Level(
        name="连锁反应",
        hint="消掉一支，往往就有新的一支能走了",
        rows=14,
        cols=10,
        hp=3,
        specs=(
        "0,9 v ",
        "13,0 ^ RU2LU",
        "13,2 ^ ",
        "8,9 < U7LUL",
        "2,8 v LDRD2",
        "1,7 < LUL2",
        "10,1 ^ RUL2U",
        "11,2 > DRDR3",
        "11,3 > ",
        "0,2 v RDR2DRD2RD",
        "5,6 v LDR3D2",
        "3,5 < DLU2L",
        "10,3 > URD3R",
        "13,9 < U4L2U2L",
        "9,5 ^ RUL5ULU",
        "7,5 < LU2L2",
        "7,3 ^ LULU2",
        "10,5 v R3D3",
        "4,2 ^ RUL3U2",
        "11,5 v RDRD",
        "2,2 ^ LU2",
        "12,0 < ",
        ),
    ),
    # 第 4 关：16×11，27 支，开局可点 4，铺满率 0.91，箭长 1~12，最大单朝向 44%，蛇形 C×2 S×4（seed=23）
    Level(
        name="四面楚歌",
        hint="上下左右都要扫一遍",
        rows=16,
        cols=11,
        hp=3,
        specs=(
        "15,10 ^ L10U",
        "14,10 ^ ",
        "10,10 < U10L",
        "14,1 ^ RU2L2U4",
        "11,1 > ",
        "14,9 ^ L6U",
        "10,1 > URD2RDRDR",
        "1,9 < ",
        "2,9 < ",
        "12,9 > RUL2D2R",
        "13,7 ^ LULULULU",
        "10,9 < U7L2",
        "10,8 < U5L3",
        "7,6 < LD3R2U4L",
        "8,1 ^ R3U",
        "7,3 ^ L3U",
        "2,8 < U2L2",
        "6,5 ^ L4ULU",
        "13,10 > ",
        "2,7 < ",
        "4,8 < L2U3L",
        "5,4 ^ L2ULU",
        "4,5 ^ L2ULULU",
        "0,5 < L3",
        "3,0 ^ U3",
        "13,1 < L",
        "0,1 ^ ",
        ),
    ),
    # 第 5 关：18×12，28 支，开局可点 5，铺满率 0.97，箭长 1~13，最大单朝向 43%，蛇形 C×3 S×9（seed=73）
    Level(
        name="错位走廊",
        hint="箭头更长，先看清它朝哪边",
        rows=18,
        cols=12,
        hp=4,
        specs=(
        "17,11 ^ LU2RU",
        "0,11 v L11D",
        "2,0 v RDLD6",
        "2,11 > ULD2R",
        "1,1 v RD2",
        "9,11 < D4LDLD3L2",
        "13,9 < ULD4L2DL",
        "12,10 < UL",
        "4,1 > ",
        "1,9 v L6D",
        "5,1 > ",
        "4,11 < D4LD2L",
        "2,9 v L5DLD2",
        "7,10 < LD2LD2LD4L",
        "3,9 v L4DLD2L3D",
        "14,0 < URD2L",
        "16,11 > ",
        "4,10 < D2L2D2LD2L",
        "4,9 v L3DLD2L3D",
        "8,3 v ",
        "14,6 < U3LUL",
        "5,9 v L2DLD2L2DLD2",
        "16,5 < U4L2",
        "8,1 v DRD5",
        "13,4 < D4L3",
        "13,3 < D3L2",
        "11,0 < DRU2L",
        "16,0 v D",
        ),
    ),
    # 第 6 关：20×14，37 支，开局可点 5，铺满率 0.92，箭长 1~13，最大单朝向 38%，蛇形 C×4 S×7（seed=1395）
    Level(
        name="纵横交错",
        hint="别只盯着中间，边角往往藏着出口",
        rows=20,
        cols=14,
        hp=4,
        specs=(
        "0,13 v LDRD2",
        "19,0 ^ ",
        "0,11 v ",
        "18,0 > URD2R2",
        "19,4 ^ ",
        "18,2 ^ RULUL2U",
        "1,0 < DRU2L",
        "4,0 < DRU2L",
        "19,5 ^ RUL2U",
        "14,0 > U8R",
        "0,6 v R4DRDRD2RD",
        "0,3 v R2DR4DRDRD",
        "16,3 > UR2DR2D3R",
        "2,6 v R2DRDRDR2DRD",
        "15,2 > LUR3",
        "12,2 > RUL2D2R3",
        "7,1 > D3R2",
        "9,2 ^ R2UL2U",
        "6,11 v LDR2DRD2",
        "5,9 v ",
        "14,5 > URD2R",
        "6,2 ^ ",
        "8,11 v LDR2D",
        "10,4 > D2R2",
        "5,2 ^ RULU3",
        "1,3 v RDRDR2DRD2RD",
        "6,3 > DR2D4R",
        "3,3 v RDR2DRD2RDRD",
        "0,2 ^ ",
        "10,6 > URD2RDR",
        "9,8 v DR2D",
        "12,7 > DR2",
        "11,13 v LD2",
        "14,7 > RD4RDR2",
        "10,11 v D4RD",
        "17,9 > URD2R2DR",
        "14,9 > DR2D2RUR",
        ),
    ),
    # 第 7 关：22×15，38 支，开局可点 5，铺满率 0.93，箭长 1~15，最大单朝向 39%，蛇形 C×4 S×11（seed=236）
    Level(
        name="长蛇阵",
        hint="一支挨着一支，顺序想好再点",
        rows=22,
        cols=15,
        hp=4,
        specs=(
        "0,14 v LDRD3",
        "21,0 ^ ",
        "0,0 v R12D",
        "1,1 v R10DR2D",
        "9,0 > D11RDR",
        "19,1 > URD2RDR",
        "4,11 < LDR2U2L",
        "4,13 v DRD2",
        "8,14 < ",
        "5,0 > D3RD9R",
        "2,10 v LD2",
        "2,8 v ",
        "16,2 > ",
        "6,5 < D2RU6L5",
        "2,7 v DRDLD",
        "7,1 > URD3R4",
        "5,5 < U2L3",
        "19,6 > DRU2L2D3R2",
        "5,1 < R2UL3",
        "15,2 > U5R",
        "5,8 v RDR4D2",
        "19,3 > U8RUR",
        "6,7 v RDR4D",
        "12,4 > D5R3",
        "7,7 v DR4DR3D5",
        "11,5 > D5R3D5R",
        "9,7 v R3DR3D",
        "3,1 < L",
        "1,0 < ",
        "10,6 > D5R",
        "2,0 < ",
        "11,12 v LDR2D",
        "15,8 > ",
        "10,7 v R2DRD2R2D2",
        "11,7 > RDRD8RDR",
        "14,10 v RD2R2DLDRD",
        "19,10 > URD2R2",
        "14,13 v DRD6",
        ),
    ),
    # 第 8 关：23×17，43 支，开局可点 4，铺满率 0.92，箭长 1~16，最大单朝向 37%，蛇形 C×2 S×8（seed=30）
    Level(
        name="十面埋伏",
        hint="开局只有几支能动，慢慢找",
        rows=23,
        cols=17,
        hp=4,
        specs=(
        "21,15 ^ U2LD3R2U2",
        "22,0 ^ RU2LU2",
        "22,2 ^ R11U3",
        "21,12 ^ LURU",
        "14,0 > U14R",
        "3,1 > DRU2LURUR2",
        "7,1 > DRU2LUR",
        "21,2 ^ R8U",
        "17,16 < ",
        "19,16 ^ ULU2RU3",
        "15,15 < ",
        "11,1 > DRU2LUR",
        "17,14 < ",
        "13,1 > R2U12R",
        "16,14 < ",
        "18,14 ^ L2URU",
        "14,15 < UL2DRDL",
        "11,15 ^ ULD2R2U",
        "20,9 ^ ",
        "20,2 ^ R6UR3U",
        "13,4 > U11RU2R",
        "0,7 > DRUR5",
        "1,6 > DRDRURUR",
        "16,12 < ",
        "3,5 > DR4URURUR",
        "15,12 < ",
        "17,11 < U2L5DL",
        "17,10 < ",
        "14,2 > R2DRU10R",
        "10,16 ^ U",
        "18,10 < L3DLU2L",
        "14,6 > U8RUR",
        "14,7 > U7RUR",
        "14,8 ^ R4U2RU3R2URU",
        "13,8 > U5RURUR3",
        "19,5 < ULU2L",
        "13,11 ^ LU2R2U3R2U2",
        "19,4 < LU2LDLUL",
        "5,9 > RURDRU3R",
        "7,15 ^ URU2",
        "15,3 < LDLUL",
        "5,13 ^ R2U2RU2",
        "4,14 ^ LURURU2",
        ),
    ),
    # 第 9 关：26×18，46 支，开局可点 5，铺满率 0.92，箭长 1~18，最大单朝向 37%，蛇形 C×2 S×5（seed=39）
    Level(
        name="万箭归一",
        hint="全场只剩几个出口，每一步都要算",
        rows=26,
        cols=18,
        hp=4,
        specs=(
        "25,17 ^ L2U2R2U3",
        "24,13 ^ U5LD6R2U",
        "25,0 ^ R11U2",
        "24,10 ^ L10U",
        "23,14 ^ UR2U2L2U",
        "23,1 ^ R9URU",
        "16,0 > U16R",
        "17,17 < ",
        "18,17 < DL2UL2",
        "14,1 > U13RUR2",
        "20,11 < ULD2LDL3",
        "15,1 > ",
        "2,2 > DRU2R2UR6",
        "16,1 > ",
        "18,16 < UL",
        "4,2 > D2RU2RU2R",
        "16,17 < ULUL2D3L",
        "18,12 ^ ",
        "7,2 > ",
        "17,12 < ULD2L",
        "17,10 < ULD4LDL",
        "13,2 > U5RURU2RU2RU2R",
        "14,17 ^ U6",
        "16,13 ^ U2",
        "15,12 ^ ",
        "15,11 ^ LUR2UR4U",
        "19,8 < ULDLD2LDL",
        "6,5 > DRU3RU2RUR3",
        "3,8 > DRU2R2",
        "9,3 > DRU2R3U3R",
        "15,9 < ULD3L",
        "13,11 ^ LUR5URU",
        "13,9 ^ LURUR5URURU",
        "18,6 < ULD3LDLDL2UL",
        "6,8 > ",
        "5,9 > DRU3R",
        "16,7 < U3LDL3D2LDL",
        "16,6 < UL2D3L2",
        "0,15 ^ LDR2U",
        "13,3 > U2R2U2R3U2R2",
        "19,4 < LDL2U2L",
        "10,13 ^ L2UR3URUR2U2",
        "4,11 > ",
        "12,5 ^ R2ULUR4ULUR4U",
        "7,11 > U2RU3R2D2RUR",
        "7,12 ^ UR4U2RU",
        ),
    ),
)

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

TOTAL_LEVELS = len(LEVELS)

def get_level(index):
    """按下标取关卡，越界时抛 IndexError。"""
    return LEVELS[index]
