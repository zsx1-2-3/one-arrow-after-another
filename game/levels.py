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

    第 1 关  11×8   21 支   开局 5 支能点
    第 2 关  13×9   23 支   开局 7 支
    第 3 关  14×10  22 支   开局 6 支
    ...
    第 9 关  26×18  46 支   开局 6 支

可点数的台阶没有早年（收到 2 支）那么陡：朝向均衡会把箭头往四个方向摊，
摊开之后朝外的箭变多、出口天然多几个——这是「画面不再一边倒」的代价，
由更紧的生命值（3/4 颗）补回来。

每支箭的长度由生成器围绕「平均单支长度」大散开地抽出来：一盘里
既有两三格的短箭、也有十几格的长蛇（第 9 关 1~18 格），
长短差距本身就是观感的一部分，不再是清一色的等长箭。

尺寸一律取**竖着的**（行数 > 列数）：这个游戏按手机竖屏比例做
（窗口 600×960，棋盘视口约 572×728），竖长方形的棋盘才能把视口填满，
不至于上下各空出一条。生成器也是按这个比例出题的。

真正决定手感的是**开局可点数**：可点数越多越容易。它不是随手定的数，
而是每一步的难度台阶，由 tools/pick_levels.py 从生成器的候选里挑出来
（同一尺寸下挑「可点数达标 + 朝向最均衡 + 铺满率高 + 长短差距大」的那一版，
九关的最大单朝向占比压在 26%~45%，早年一度是 70% 一边倒）。

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
# 29.2 / 29.8 / 34.0 / 52.3 / 55.7 / 83.8 / 88.4 / 97.7 / 111.8，
# 按这套阈值映射成 1/1/1/2/3/4/4/4/5 星。
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
#  三支箭头，把「前方空 → 能飞 / 前方有箭头 → 飞不出去」走一遍：
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
        TutorialStep("先点最长的那支横躺的箭头。它箭头正前方还压着别的箭头，"
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
    # 第 1 关：11×8，21 支，开局可点 5，铺满率 0.92，箭长 1~8，最大单朝向 29%（seed=28）
    Level(
        name="初次拉弓",
        hint="点朝外的那几支，先开出一条路",
        rows=11,
        cols=8,
        hp=3,
        specs=(
        "0,0 v R3D",
        "10,7 ^ LURU",
        "1,2 v L2D",
        "7,7 < UL2",
        "8,6 < UL",
        "3,0 > ",
        "10,2 ^ R3ULU2",
        "4,0 > ",
        "0,4 > DR",
        "5,7 ^ LU",
        "9,3 < U2L",
        "2,7 v L6D",
        "5,0 v RD2",
        "9,2 < UL",
        "6,2 > U3R",
        "1,6 ^ RU",
        "6,0 v D4",
        "3,4 > ",
        "9,1 v D",
        "6,3 > U2R2UR2",
        "0,5 ^ ",
        ),
    ),
    # 第 2 关：13×9，23 支，开局可点 7，铺满率 0.91，箭长 1~9，最大单朝向 26%（seed=69）
    Level(
        name="交叉路口",
        hint="开局能点的很少，先找朝外的",
        rows=13,
        cols=9,
        hp=3,
        specs=(
        "0,0 > DRUR",
        "0,3 v ",
        "12,8 ^ LURU2",
        "12,6 < UL2DL",
        "1,2 v ",
        "12,2 ^ URUR4U",
        "2,0 v RDLD2",
        "8,8 < ULDLDL",
        "0,4 > D2R2",
        "2,2 > DR2",
        "8,3 ^ R2URUR2U",
        "9,4 < L",
        "4,1 > DRUR2",
        "6,0 v RD",
        "7,2 ^ R2URUR2U",
        "8,2 < D2LD2L",
        "4,8 ^ U",
        "3,5 > DRURUR",
        "1,5 > UR2DR",
        "9,1 < UL",
        "12,5 v ",
        "7,0 < ",
        "0,8 ^ ",
        ),
    ),
    # 第 3 关：14×10，22 支，开局可点 6，铺满率 0.91，箭长 1~11，最大单朝向 32%（seed=151）
    Level(
        name="连锁反应",
        hint="消掉一支，往往就有新的一支能走了",
        rows=14,
        cols=10,
        hp=3,
        specs=(
        "13,0 ^ RULU2",
        "0,9 v ",
        "0,8 v ",
        "13,2 > UR2DR2",
        "10,9 < U9L",
        "13,7 ^ ",
        "3,0 > D6RD2R",
        "2,8 < ",
        "12,5 ^ ",
        "3,8 v LD2RD3",
        "2,7 < U2L2",
        "12,6 ^ RUL4ULU",
        "9,3 > RDR4D3R",
        "9,7 < U3LU5L",
        "8,1 ^ R3U2",
        "7,3 ^ L2URU",
        "7,6 < LU5LU2L",
        "13,3 v ",
        "5,4 < U2LU2LUL2",
        "6,3 < U2LU2L",
        "12,9 > ",
        "11,9 > ",
        ),
    ),
    # 第 4 关：16×11，27 支，开局可点 4，铺满率 0.93，箭长 1~12，最大单朝向 33%（seed=173）
    Level(
        name="四面楚歌",
        hint="上下左右都要扫一遍",
        rows=16,
        cols=11,
        hp=3,
        specs=(
        "0,10 < DLUL2",
        "0,6 v L6D3",
        "1,1 v ",
        "4,0 > ",
        "2,1 v RDLD",
        "15,10 < ",
        "1,2 v RD2",
        "9,0 > ",
        "6,10 < D8LDL",
        "8,0 > U3R2UR",
        "1,8 v L4D3",
        "13,9 < ",
        "12,0 > U2RU4R2UR",
        "2,5 v ",
        "7,9 < D5LD2LDL",
        "2,6 v RDL2D",
        "5,5 > ",
        "7,2 > DRURUR2U2R",
        "15,5 < UL2",
        "5,9 < DLD5LD2L",
        "2,8 > DR2",
        "5,8 v LD2L2DLDL2D",
        "8,7 < D2LD2LDL",
        "8,6 v DLDL2DL2D2",
        "15,4 < L2UL",
        "4,8 > R2",
        "2,9 > R",
        ),
    ),
    # 第 5 关：18×12，28 支，开局可点 5，铺满率 0.92，箭长 1~13，最大单朝向 32%（seed=28）
    Level(
        name="错位走廊",
        hint="箭头更长，先看清它朝哪边",
        rows=18,
        cols=12,
        hp=4,
        specs=(
        "0,11 < DL2UL4",
        "0,4 v L4D2",
        "1,1 v ",
        "17,0 > ",
        "1,3 v R5DR3D3",
        "13,11 < U7LU3L",
        "8,0 > D8RDR2",
        "7,10 v LDRD",
        "15,1 > ",
        "14,1 > URD3R",
        "2,3 v R4DRDRD2LD",
        "5,8 < LULUL",
        "9,9 < LULU2LULULUL",
        "0,10 ^ ",
        "15,3 > ",
        "1,2 < DLDL",
        "5,4 v ",
        "9,1 > D3R2D2RD3R",
        "12,10 < U2L3ULU2LUL",
        "11,9 v L2D2",
        "16,5 > URD2RU2R2",
        "10,6 < DLU3LUL2",
        "13,4 > URD2R2",
        "12,8 v RDRDRDLDL2D",
        "4,3 < D2L",
        "17,9 > R",
        "11,4 < U2LUL2U3L",
        "16,11 v D",
        ),
    ),
    # 第 6 关：20×14，37 支，开局可点 3，铺满率 0.93，箭长 1~13，最大单朝向 30%（seed=27）
    Level(
        name="纵横交错",
        hint="别只盯着中间，边角往往藏着出口",
        rows=20,
        cols=14,
        hp=4,
        specs=(
        "19,13 ^ ",
        "0,7 v ",
        "19,12 ^ L2UR3U",
        "0,6 v L6D2",
        "1,1 > DR3UR2",
        "16,13 < ",
        "3,0 v RDLD",
        "19,9 ^ ",
        "12,0 > U6RURU2R",
        "15,13 < ",
        "17,12 < ULDL2DLDL2",
        "15,12 ^ LUR2U4",
        "13,12 < UL2D4L",
        "0,8 > DRUR3",
        "1,7 v DL2DLDLD",
        "6,2 v RDL2D4",
        "8,2 > ",
        "9,2 > ",
        "15,8 ^ RU4R3U2RU",
        "8,3 v RDLDLD",
        "16,8 < DLDL",
        "5,4 v RD4",
        "11,8 < D3LD2LDLD2L",
        "4,5 > RUR2UR2UR2",
        "12,7 ^ U2R4U2RURU",
        "11,3 > RUR2U5RUR",
        "18,4 < UL2",
        "5,13 ^ ",
        "9,7 ^ R3U2RURU2RU",
        "13,7 < LDL2",
        "12,6 < ULD2L",
        "12,4 v L3DLD",
        "13,2 v RDL2D",
        "8,7 > U2RURU2R2UR",
        "15,2 v R2DL3D2R2D",
        "2,13 ^ U2",
        "15,0 v D4",
        ),
    ),
    # 第 7 关：22×15，38 支，开局可点 4，铺满率 0.92，箭长 1~15，最大单朝向 45%（seed=195）
    Level(
        name="长蛇阵",
        hint="一支挨着一支，顺序想好再点",
        rows=22,
        cols=15,
        hp=4,
        specs=(
        "0,0 v RDLD5",
        "21,14 ^ ",
        "21,2 ^ R11URU",
        "2,1 v RD3LD2LD",
        "20,5 ^ R7URURU3",
        "20,4 ^ ",
        "0,2 > DR3UR2",
        "18,12 ^ LUR2U2",
        "14,14 < ULDLD2L",
        "12,14 < ",
        "6,2 v RD4L3D",
        "21,0 ^ RUR2UR7U2",
        "20,0 > U8RUR2",
        "19,2 ^ LUR8U",
        "5,3 > U3R",
        "3,4 > ",
        "4,4 > DRU3RUR",
        "16,10 ^ LUR2U",
        "16,1 > U3RUR2U6R",
        "17,1 ^ R7U",
        "7,2 < D2L2",
        "3,6 > DRU2RU2R2",
        "7,5 > DRU3R",
        "13,3 > DRURU4R",
        "16,6 ^ RURUR2UR2URURU",
        "3,8 > DR2",
        "14,6 ^ RUR2UR2URURURU",
        "13,6 > U3RU4R2",
        "10,11 ^ ",
        "12,7 > URU4R",
        "11,10 ^ LU2R3URURU2",
        "3,9 > U2R2URDR",
        "3,10 > URD2RUR",
        "8,9 ^ R2URURU2RU",
        "2,12 > R",
        "2,14 ^ U2",
        "0,13 ^ ",
        "0,4 ^ ",
        ),
    ),

    # 第 8 关：23×17，43 支，开局可点 6，铺满率 0.92，箭长 1~16，最大单朝向 44%（seed=170）
    Level(
        name="十面埋伏",
        hint="开局只有几支能动，慢慢找",
        rows=23,
        cols=17,
        hp=4,
        specs=(
        "22,0 ^ R2U2L2U",
        "0,16 v ",
        "22,16 ^ L13U",
        "21,4 ^ RUL2UL2ULU3",
        "19,4 > UR2D3R",
        "21,16 ^ L8ULU2",
        "14,0 > URD4R6",
        "0,15 < DLDL2U2L",
        "20,16 ^ L7ULU",
        "1,16 < DLDL",
        "3,16 < DL3UL",
        "12,0 > U2RDRD5R2",
        "5,16 < ",
        "0,0 > D9R",
        "18,9 ^ ",
        "3,1 > D5RD2RD5R",
        "19,16 ^ L6U",
        "5,2 > D2RD2RD5RD2R",
        "17,8 ^ RUL2ULU",
        "6,3 > ",
        "18,16 ^ L5ULU",
        "4,2 > URD2RD3RD5R",
        "21,1 < L",
        "7,5 > ",
        "15,8 ^ ",
        "17,16 ^ L4ULUL2UL2U",
        "4,4 > URD3RD6R",
        "13,8 ^ RU2L2U4",
        "16,16 ^ L3ULUL2U",
        "2,4 > R2D3RURD6R",
        "14,13 > U4RDR2",
        "13,12 ^ LULU2",
        "11,11 > URUR2",
        "9,9 > UR3",
        "3,7 > UR2D5R2",
        "10,16 ^ LU2L2ULUL2U",
        "9,16 ^ U2L2ULULUL2U",
        "12,14 > ",
        "15,14 > U2RUR",
        "3,11 ^ ULU",
        "2,3 ^ ",
        "2,1 ^ RUR7U",
        "5,14 > RDR",
        ),
    ),
    # 第 9 关：26×18，46 支，开局可点 6，铺满率 0.92，箭长 1~18，最大单朝向 35%（seed=134）
    Level(
        name="万箭归一",
        hint="全场只剩几个出口，每一步都要算",
        rows=26,
        cols=18,
        hp=4,
        specs=(
        "25,0 ^ RULU2",
        "0,17 v ",
        "0,3 v R13DRD2",
        "25,15 ^ L13U2LU",
        "24,13 ^ L10U2LUL2U",
        "2,16 v ",
        "23,4 ^ RU2L2UL2ULU2",
        "4,17 < DLU2LU2L",
        "16,0 > ",
        "23,6 > U2RD2R2",
        "4,15 < DLU3LUL2",
        "20,4 ^ RUL3ULU",
        "1,7 v R3DR2DRD3R4D2",
        "15,0 > ",
        "13,17 < U4LU2L4U3LUL",
        "21,17 < U7LU4LU2L2",
        "11,15 v LD4R2D",
        "20,6 ^ RULUL3ULULU",
        "16,3 ^ RU2L4U4",
        "17,4 > R3DRD4R",
        "10,14 < UL2ULU3LULU2L",
        "16,5 ^ R3U2LUL6U",
        "21,9 > URD3R",
        "3,8 < DLU2LUL2",
        "10,13 < DLULULU3LUL",
        "17,16 v ",
        "16,15 v L2DRDR2D",
        "22,11 > ",
        "17,8 ^ RU4LUL6ULU",
        "12,13 v LD6RDR2DRD",
        "21,11 > URD3R",
        "7,9 < ",
        "17,11 ^ U5L2UL6ULU",
        "8,9 < ",
        "11,11 < LULULU3LUL",
        "20,13 > D2RD2R",
        "10,8 < LU3LULUL",
        "10,6 ^ L2ULULULULU",
        "20,14 v DRDR2D2LD",
        "9,5 ^ RUL2ULULU",
        "3,6 < DLU2L2ULUL2",
        "4,4 < ULDL",
        "25,17 > ",
        "3,2 < ULUL",
        "5,1 < U2L",
        "8,1 < DL",
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
