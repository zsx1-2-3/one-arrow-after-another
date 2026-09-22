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

    第 1 关  11×8   21 支   开局 7 支能点
    第 2 关  13×9   23 支   开局 6 支
    第 3 关  14×10  22 支   开局 5 支
    ...
    第 9 关  26×18  44 支   开局 2 支

每支箭的长度由生成器围绕「平均单支长度」大散开地抽出来：一盘里
既有两三格的短箭、也有十几格的长蛇（第 9 关 1~18 格），
长短差距本身就是观感的一部分，不再是清一色的等长箭。

尺寸一律取**竖着的**（行数 > 列数）：这个游戏按手机竖屏比例做
（窗口 600×960，棋盘视口约 572×728），竖长方形的棋盘才能把视口填满，
不至于上下各空出一条。生成器也是按这个比例出题的。

真正决定手感的是**开局可点数**：可点数越多越容易。它不是随手定的数，
而是每一步的难度台阶，由 tools/pick_levels.py 从生成器的候选里挑出来
（同一尺寸下挑「铺满率最高 + 可点数最接近目标」的那一版）。

九个编号关卡全部由 tools/generate_levels.py **逆向构造**生成：
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
箭头越到后面越多，要逐条扫视的射线也越多，越容易点错，
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
    # 第 1 关：11×8，21 支，开局可点 7，铺满率 0.92，箭长 1~8（seed=18）
    Level(
        name="初次拉弓",
        hint="点朝外的那几支，先开出一条路",
        rows=11,
        cols=8,
        specs=(
        "0,7 v LD2RD",
        "0,5 v L5D",
        "1,5 v L4DLD",
        "2,2 v ",
        "2,5 v LD",
        "4,7 < D2L2",
        "2,3 v D",
        "4,0 v RD",
        "10,0 > U2R",
        "10,7 < U3L",
        "3,1 v RDR2D2",
        "5,0 v DR2D",
        "5,2 v RD2",
        "7,5 v LD2",
        "8,3 v LDLD",
        "8,5 v RD2",
        "7,1 < L",
        "9,5 v D",
        "9,3 v D",
        "10,4 v ",
        "1,7 > ",
        ),
    ),
    # 第 2 关：13×9，23 支，开局可点 6，铺满率 0.97，箭长 1~9（seed=17）
    Level(
        name="交叉路口",
        hint="开局能点的很少，先找朝外的",
        rows=13,
        cols=9,
        specs=(
        "0,0 v ",
        "12,8 ^ LURU",
        "12,6 ^ ",
        "0,6 v L5DLD",
        "3,0 > DRU2RUR",
        "1,4 v RD3",
        "12,4 ^ RURURURU",
        "2,4 v LD2",
        "3,2 v D2L2D",
        "3,4 v D2LD",
        "6,2 v LDLD2",
        "7,2 v RD3",
        "8,2 v LD2LD",
        "9,2 < D3L2",
        "1,6 > D3R2",
        "12,3 > URU4R",
        "3,7 ^ RU",
        "6,4 > R",
        "2,7 ^ URU",
        "5,5 > RDR",
        "10,5 > U2R2UR",
        "5,7 > R",
        "6,8 > ",
        ),
    ),
    # 第 3 关：14×10，22 支，开局可点 5，铺满率 0.94，箭长 1~11（seed=13）
    Level(
        name="连锁反应",
        hint="消掉一支，往往就有新的一支能走了",
        rows=14,
        cols=10,
        specs=(
        "0,0 > DR2UR2",
        "0,7 v L2DL2DL3D",
        "13,9 ^ LU2RU2",
        "4,0 v RDLD3",
        "3,1 v R2DLD2LD",
        "0,9 v LDL2DL2D",
        "3,5 v R2DLD4",
        "4,4 v RD2",
        "6,9 < D2LD2LD3L",
        "5,4 v ",
        "2,9 < D3L2D4L",
        "5,3 v DRDRD",
        "12,6 < U2L",
        "11,5 < D2L",
        "7,2 v RD2",
        "9,5 < LD3LDL",
        "8,1 v RDL2D",
        "11,3 < ULD2LDL",
        "10,1 < DL",
        "0,1 ^ ",
        "12,9 > ",
        "1,9 > ",
        ),
    ),
    # 第 4 关：16×11，27 支，开局可点 5，铺满率 0.94，箭长 1~12（seed=19）
    Level(
        name="四面楚歌",
        hint="上下左右都要扫一遍",
        rows=16,
        cols=11,
        specs=(
        "15,10 ^ LU2RU",
        "15,0 ^ ",
        "15,8 ^ L7ULU2",
        "14,3 ^ R5U2RURU",
        "14,2 ^ UR5U",
        "0,0 > DRUR2",
        "12,6 ^ ",
        "11,0 > U9R",
        "3,1 > DR2",
        "13,1 > U8R",
        "9,10 ^ L2U4",
        "11,8 ^ LU3",
        "12,5 ^ ",
        "12,2 ^ R2UR2U",
        "11,2 ^ RUR2URU2RU2",
        "10,2 ^ UR2URU2RU",
        "8,9 ^ RU3LUL4U",
        "8,3 ^ LU2RURU",
        "3,2 > U2R3",
        "3,3 > UR3U2R",
        "3,6 > R2",
        "4,10 ^ U2",
        "3,9 ^ UL2URU",
        "1,9 ^ RU",
        "0,9 ^ ",
        "14,10 > ",
        "0,5 ^ ",
        ),
    ),
    # 第 5 关：18×12，28 支，开局可点 4，铺满率 0.93，箭长 1~13（seed=14）
    Level(
        name="错位走廊",
        hint="箭头更长，先看清它朝哪边",
        rows=18,
        cols=12,
        specs=(
        "17,0 ^ R11U",
        "16,10 ^ L10U",
        "14,0 > URDRDR2",
        "15,5 ^ R6U",
        "13,11 ^ L2URU4RU",
        "14,9 ^ L6ULUL2U",
        "6,11 < U6L2",
        "13,8 ^ ",
        "7,10 < U6L",
        "13,7 ^ ",
        "13,6 ^ ",
        "0,8 < DL2UL",
        "11,9 < U9L2",
        "11,1 ^ RUL2U2",
        "13,4 ^ RUL2U",
        "11,4 ^ ",
        "10,3 ^ RU",
        "12,8 < U8L",
        "9,3 ^ L2U2LU2",
        "12,7 ^ LULU3LU",
        "8,3 ^ LU2LU",
        "3,8 < L2",
        "2,6 < LULUL2",
        "11,7 < U6LULUL2",
        "2,4 < LUL2UL",
        "9,6 < U3LULUL2U2L",
        "3,1 < DL",
        "0,7 ^ ",
        ),
    ),
    # 第 6 关：20×14，33 支，开局可点 4，铺满率 0.95，箭长 1~13（seed=3）
    Level(
        name="纵横交错",
        hint="别只盯着中间，边角往往藏着出口",
        rows=20,
        cols=14,
        specs=(
        "19,13 ^ LU2RU2",
        "19,0 ^ R11U",
        "18,10 ^ L10U2",
        "17,2 ^ R9URU",
        "17,1 ^ U2LU5",
        "16,10 ^ L8U2LU",
        "15,11 ^ L8U",
        "11,13 < U11L",
        "14,5 ^ ",
        "1,12 < DLU2L",
        "14,4 ^ UL2ULU2",
        "1,10 < DLU2L3",
        "13,5 ^ ",
        "12,3 > URDR",
        "11,2 ^ U",
        "13,13 < ULU9L",
        "4,11 < D2LU3L",
        "14,6 > URDR2",
        "12,8 ^ L2ULUL2UL3U",
        "14,13 < LULU6L",
        "4,9 < DL4",
        "4,8 < U3L3UL2",
        "6,9 < DLUL2",
        "14,11 < LU6L3UL",
        "11,9 ^ L2ULUL2UL3U",
        "2,7 < D2LUL",
        "8,6 ^ LUL3ULU",
        "6,5 ^ L2ULU",
        "7,0 ^ U3RURU",
        "4,5 < LULU2LULD2L",
        "1,0 ^ U",
        "18,13 > ",
        "3,0 < ",
        ),
    ),
    # 第 7 关：22×15，38 支，开局可点 3，铺满率 0.96，箭长 1~15（seed=20）
    Level(
        name="长蛇阵",
        hint="一支挨着一支，顺序想好再点",
        rows=22,
        cols=15,
        specs=(
        "0,1 v R13D",
        "0,0 v D4",
        "1,13 v L12D2",
        "2,14 v ",
        "2,2 v R11DRD",
        "3,10 v L8DLDLD2",
        "3,11 v ",
        "3,12 v DRDRD",
        "4,11 v LDR2DRDRD",
        "4,3 v R6D",
        "5,8 v ",
        "5,2 v ",
        "9,14 < D12L",
        "5,7 v L4DL2D2LD",
        "6,9 v L5DL2D2LDLD",
        "9,13 < D11LDL",
        "7,5 v RDL3D",
        "10,12 < D9LDLDL",
        "6,11 v LDL3D",
        "10,2 v RDL2DLD2",
        "7,12 v LDL3DLD",
        "9,4 v R2D2RD2",
        "8,13 v LDL3DLD3",
        "10,4 v RD2RD",
        "10,11 v LDLD3L3D",
        "11,4 v DL2D2RD",
        "11,11 < D3LDL3DL",
        "13,1 v D",
        "15,11 < DL3DL",
        "18,11 < UL2DLD3L3UL",
        "20,7 < U2L2",
        "13,3 v R2D2LD3LD2",
        "15,0 v R2DRDLD2",
        "16,1 v LDRD",
        "21,4 < L",
        "18,0 v DRDRD",
        "21,1 < L",
        "20,0 < ",
        ),
    ),
    # ======================================================== 第 8 关
    # 第 8 关：23×17，43 支，开局可点 3，铺满率 0.94，箭长 1~16（seed=184）
    Level(
        name='十面埋伏',
        hint='开局只有两三支能动，慢慢找',
        rows=23,
        cols=17,
        specs=(
        "0,0 > DRUR4",
        "0,6 v R10D3",
        "1,13 v L11DL2D",
        "2,12 v L9DL2DLD",
        "1,14 v RD3RD4",
        "2,13 v RD3RD2",
        "3,4 v R9D",
        "4,12 v ",
        "4,2 v ",
        "4,11 v LDR3DRD2RDRD",
        "11,16 < D11L",
        "4,9 v ",
        "4,8 v L5DL2DLD",
        "8,0 v RD2LD3",
        "7,1 v RD2",
        "5,9 v L5DLD",
        "6,5 v R7DRD",
        "7,11 v ",
        "7,4 v RD3L3DLD2",
        "7,10 v ",
        "7,9 v L3D4L3DLD",
        "8,12 v L5D2",
        "10,15 < D11LDL2",
        "9,14 < D11LDL",
        "22,11 < UL2DL5",
        "19,13 < UL2",
        "20,12 < UL",
        "9,13 < D8L2",
        "20,11 < L3",
        "9,12 < D7L",
        "21,8 < L4ULD2L",
        "19,10 < U4LDL",
        "17,9 < D2L2DL2UL",
        "15,11 < UL3",
        "9,11 < D4L4DL",
        "15,8 < L",
        "9,9 v LD2LDL3DLDL3D",
        "18,8 < ULULDL",
        "13,6 v LDLDL3DLD3",
        "15,6 v LDL3D3LDLD",
        "20,2 < DLDL",
        "9,0 < ",
        "22,10 v ",
        ),
    ),

    # 第 9 关：26×18，44 支，开局可点 2，铺满率 0.94，箭长 1~18（seed=27）
    Level(
        name="万箭归一",
        hint="全场只剩几个出口，每一步都要算",
        rows=26,
        cols=18,
        specs=(
        "25,17 < ULDL",
        "25,0 ^ ",
        "25,14 ^ L13ULU2",
        "24,15 ^ ",
        "23,17 ^ LU2RU4",
        "24,14 ^ LU2R2U2RU2",
        "24,12 ^ ",
        "24,11 ^ L9ULU2LU",
        "23,3 ^ R9U",
        "22,11 ^ L9U2LULU",
        "21,14 ^ LURURU",
        "21,12 ^ L9U",
        "18,1 ^ RUL2U5",
        "19,2 ^ RU3L2U3",
        "20,12 ^ L8U4",
        "0,0 > DRUR4",
        "2,0 > DR2U2R2",
        "17,16 ^ LUR2U3",
        "11,0 > U7R3U2R",
        "19,5 ^ R8URU",
        "1,5 > DRU2R",
        "18,5 ^ R7URURUR2U",
        "12,1 > U7R",
        "6,2 > DRU2RU2R",
        "4,5 > DRU2RU2RUR2",
        "15,2 > U7R",
        "17,7 ^ R4URURUR2URURU2",
        "9,3 > DRU4R",
        "17,5 ^ RUR4URU2",
        "14,12 ^ UR2URURU",
        "15,3 > U4R2U4R",
        "6,6 > RU2RU2RUR2UR4",
        "15,4 > U3R2U4RUR",
        "16,5 > U3R2U4RUR3",
        "15,7 ^ R2URU2R3URURUR2U",
        "6,8 > URU2RUR",
        "11,12 ^ LUR2URUR2URU2",
        "7,9 > URU2RURU2R",
        "7,10 > RU2RURU2RUR2",
        "6,12 > DRU2RU2R",
        "7,14 > URU2R",
        "4,17 ^ ULURU",
        "0,16 > R",
        "22,17 > ",
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
