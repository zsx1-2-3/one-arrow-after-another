# -*- coding: utf-8 -*-
"""关卡数据：用 ASCII 字符描述棋盘，直观且便于手工微调。

字符含义：
    '.' 或 ' '  空格子
    '^' 向上     'v' 向下     '<' 向左     '>' 向右

设计原则
--------
真正的死锁只有一种形态——同一行/列里两个箭头相互指责（例如同行的
「→ ... ←」）；此外任何箭头都只被「自己正前方」的箭头挡住。
最终是否可解由 tools/verify_levels.py 与 tests/test_game.py 自动校验。

新增关卡是怎么来的
------------------
第 6 关之后的布局由 tools/generate_levels.py **逆向构造**生成：
把「消除顺序」倒过来当「放置顺序」，放置时要求"新箭头正前方没有已放置的箭头"，
这样「放置顺序的逆序」天然就是一条合法通关顺序，布局必然可解。
生成器还会优先把新箭头放在已有箭头的正前方，制造更多"必须按序解锁"的阻挡，
最后按难度指标（开局可飞行数、全程平均可选数）排序挑出最难的一批。
生成完再用 tools/verify_levels.py 复核一次，两道保险。
"""

from dataclasses import dataclass

from .board import ARROW_CHARS

EMPTY_CHARS = {".", " ", "_", "-"}


@dataclass
class TutorialStep:
    """教学关的一步引导。

    target 指定「希望玩家点哪一个格子」，expect 指定期望的结果：
    "fly"（应该飞出去）/ "blocked"（应该被挡住）。
    """

    text: str
    row: int
    col: int
    expect: str


@dataclass
class Level:
    """一个关卡。"""

    name: str
    hint: str
    max_mistakes: int
    layout: tuple
    tutorial: bool = False                  # 是否教学关（会显示逐步引导）
    steps: tuple = ()                       # 教学关的引导步骤

    def __post_init__(self):
        rows = len(self.layout)
        if rows == 0:
            raise ValueError("关卡布局不能为空")
        cols = len(self.layout[0])
        if any(len(line) != cols for line in self.layout):
            raise ValueError("关卡「%s」的每一行长度必须一致" % self.name)

        arrows = []
        for row, line in enumerate(self.layout):
            for col, char in enumerate(line):
                if char in EMPTY_CHARS:
                    continue
                if char not in ARROW_CHARS:
                    raise ValueError(
                        "关卡「%s」第 %d 行出现非法字符 %r" % (self.name, row + 1, char)
                    )
                arrows.append((row, col, ARROW_CHARS[char]))
        if not arrows:
            raise ValueError("关卡「%s」没有任何箭头" % self.name)

        self.rows = rows
        self.cols = cols
        self.arrows = arrows

        if self.tutorial and not self.steps:
            raise ValueError("教学关「%s」必须提供引导步骤" % self.name)

    @property
    def arrow_count(self):
        return len(self.arrows)

    @property
    def free_count(self):
        """开局就能直接飞出去的箭头数量（越少越难找）。"""
        from .board import count_free_arrows
        return count_free_arrows(self.rows, self.cols, self.arrows)

    @property
    def difficulty_score(self):
        """难度分（越大越难）：箭头数、棋盘尺寸为正贡献，可点箭头与失误额度为负贡献。"""
        return (self.arrow_count * 1.6
                + self.rows * self.cols / 6.0
                - self.free_count * 2.0
                - self.max_mistakes * 1.5)

    @property
    def stars(self):
        """把难度分映射成 1~5 颗星，显示在关卡总览里。

        阈值是按当前 12 个关卡的实际难度分挑的，让星级均匀铺开：
        -3.4 / 0.2 → 1 星，2.6 / 13.0 → 2 星，20.9 / 21.2 → 3 星，
        25.4 / 27.9 → 4 星，37.7 以上 → 5 星。
        """
        score = self.difficulty_score
        for threshold, stars in ((1.0, 1), (14.0, 2), (22.0, 3), (30.0, 4)):
            if score < threshold:
                return stars
        return 5


LEVELS = (
    # ======================================================== 第 0 关：教学
    Level(
        name="教学关",
        hint="跟着黄色提示点，很快就能上手",
        max_mistakes=5,
        tutorial=True,
        layout=(
            ".....",
            ".>.v.",
            ".....",
            "..^..",
        ),
        steps=(
            TutorialStep("先点这支朝右的箭头。它前方还有一支箭头挡路，飞不出去，"
                         "会扣掉 1 次失误——这就是「被挡住」的样子。", 1, 1, "blocked"),
            TutorialStep("再看这支朝下的箭头：它前方一路空到棋盘外，"
                         "点它就会一路飞出棋盘并消失。", 1, 3, "fly"),
            TutorialStep("挡路的箭头飞走了。再点刚才那支朝右的箭头，"
                         "这次它前方没有阻挡，也能飞出去了。", 1, 1, "fly"),
            TutorialStep("最后点这支朝上的箭头，本关就通关了。"
                         "记住：谁的箭头前方是空的，谁就能飞。", 3, 2, "fly"),
        ),
    ),
    # ======================================================== 第 1 关
    Level(
        name="初次拉弓",
        hint="箭头前方没有挡路的箭头，就能飞出去",
        max_mistakes=4,
        layout=(
            ".....",
            ".>.v.",
            ".....",
            ".^..v",
            "..>..",
        ),
    ),
    # ======================================================== 第 2 关
    Level(
        name="交叉路口",
        hint="全场只有一支箭能直接飞出去，先找到它",
        max_mistakes=4,
        layout=(
            ".....",
            ".>.v.",
            ".....",
            ".^..<",
            ".....",
        ),
    ),
    # ======================================================== 第 3 关
    Level(
        name="连锁反应",
        hint="一行里的箭头会排队依次飞出",
        max_mistakes=4,
        layout=(
            "......",
            ".>>>>v",
            "......",
            "......",
            ".^<<<.",
            "....v.",
            "......",
        ),
    ),
    # ======================================================== 第 4 关
    Level(
        name="四面楚歌",
        hint="开局只有一支箭头能直接飞出，先找到它",
        max_mistakes=3,
        layout=(
            "....v..",
            ".>>>>v.",
            ".......",
            "..^v...",
            ".......",
            ".^<<<..",
            ".......",
        ),
    ),
    # ======================================================== 第 5 关
    #  由 tools/generate_levels.py 生成（档位 5），开局可点 3 支
    Level(
        name="错位走廊",
        hint="顺着能飞的那一支点下去，会一路连锁",
        max_mistakes=3,
        layout=(
            "....v.<^",
            "v...<..^",
            "........",
            "v.......",
            ">..v>..^",
            "........",
            ">..v...v",
        ),
    ),
    # ======================================================== 第 6 关
    Level(
        name="层叠封锁",
        hint="别急着点，先看谁的前方是空的",
        max_mistakes=3,
        layout=(
            "....>...",
            "...>^...",
            ".....v..",
            "^.v<....",
            "...^....",
            "....^.v.",
            "<.<^.v<.",
            "...v.<..",
        ),
    ),
    # ======================================================== 第 7 关
    Level(
        name="长蛇阵",
        hint="棋盘变大之后，横竖两个方向都要扫一遍",
        max_mistakes=3,
        layout=(
            ".v...v.<.",
            "....v..^.",
            ".........",
            ".....v.>v",
            ".....>..v",
            ".....v...",
            "^<...v..<",
            ".v.v.v..<",
        ),
    ),
    # ======================================================== 第 8 关
    Level(
        name="九宫迷阵",
        hint="只有四支箭头能直接飞出去，找到它们",
        max_mistakes=2,
        layout=(
            "...<v....",
            ">.....v..",
            "...^v.<..",
            "...^.....",
            "...>.v.v.",
            "....v>>..",
            ".....v...",
            "...^.>.v.",
            "^<...<.v.",
        ),
    ),
    # ======================================================== 第 9 关
    Level(
        name="十面埋伏",
        hint="开局可点的箭头变多了，但别急着点错",
        max_mistakes=2,
        layout=(
            "...^......",
            "<....>....",
            "..........",
            "^..<.^.v..",
            "...^v.v<..",
            ".^...^v<..",
            "<.........",
            "......v...",
            "^^.^<<>v..",
        ),
    ),
    # ======================================================== 第 10 关
    Level(
        name="铁壁合围",
        hint="大棋盘上找空档，耐心一点",
        max_mistakes=2,
        layout=(
            "<.<<<.....",
            "....>>>...",
            "^..<<....<",
            ".........>",
            "....^.....",
            ".v.......>",
            "....^.>>>.",
            ".>.^^.>.>^",
            ".......^..",
            ".<........",
        ),
    ),
    # ======================================================== 第 11 关
    Level(
        name="万箭归一",
        hint="全场只有七支能先飞，想清楚再落手",
        max_mistakes=2,
        layout=(
            ".......>.^",
            "....v..^..",
            "..<.<.....",
            ".>.>.^v.v.",
            "....>v.^.v",
            "<>....>..v",
            "<....<....",
            "....v...>.",
            ".^..<.....",
            "^<^.<....>",
        ),
    ),
)

TOTAL_LEVELS = len(LEVELS)


def get_level(index):
    """按下标取关卡，越界时抛 IndexError。"""
    return LEVELS[index]


def tutorial_level_index():
    """教学关的下标；没有教学关时返回 None。"""
    for index, level in enumerate(LEVELS):
        if level.tutorial:
            return index
    return None


def validate_levels():
    """检查全部关卡：布局是否合法、是否可解。

    返回 [{'index', 'name', 'size', 'arrows', 'free', 'solvable', 'order',
            'max_mistakes', 'stars', 'tutorial'}]。
    """
    from .board import count_free_arrows, solve_level

    report = []
    for index, level in enumerate(LEVELS):
        order = solve_level(level.rows, level.cols, level.arrows)
        report.append(
            {
                "index": index + 1,
                "name": level.name,
                "size": "%d×%d" % (level.rows, level.cols),
                "arrows": level.arrow_count,
                "free": count_free_arrows(level.rows, level.cols, level.arrows),
                "solvable": order is not None,
                "order": order or [],
                "max_mistakes": level.max_mistakes,
                "stars": level.stars,
                "tutorial": level.tutorial,
            }
        )
    return report
