# -*- coding: utf-8 -*-
"""关卡数据：用 ASCII 字符描述棋盘，直观且便于手工微调。

字符含义：
    '.' 或 ' '  空格子
    '^' 向上     'v' 向下     '<' 向左     '>' 向右

设计原则（避免做出无解关卡）：
    真正的死锁只有一种形态——同一行/列里两个箭头相互指责，
    例如同行中的「→ ... ←」；此外任何箭头都只被「自己正前方」的箭头挡住，
    所以只要保证每关至少有一个箭头能先飞出去，并让后续箭头依次解锁即可。
    最终是否可解由 tools/verify_levels.py 与 tests/test_game.py 自动校验。
"""

from dataclasses import dataclass

from .board import ARROW_CHARS

EMPTY_CHARS = {".", " ", "_", "-"}


@dataclass
class Level:
    """一个关卡。"""

    name: str
    hint: str
    max_mistakes: int
    layout: tuple

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

    @property
    def arrow_count(self):
        return len(self.arrows)


LEVELS = (
    # ---------------------------------------------------------- 第 1 关
    Level(
        name="初次拉弓",
        hint="箭头前面没有挡路的箭头，就能飞出去",
        max_mistakes=3,
        layout=(
            ".....",
            ".>.v.",
            ".....",
            ".^..v",
            "..>..",
        ),
    ),
    # ---------------------------------------------------------- 第 2 关
    Level(
        name="交叉路口",
        hint="全场只有一支箭能直接飞出去，先找到它",
        max_mistakes=3,
        layout=(
            ".....",
            ".>.v.",
            ".....",
            ".^..<",
            ".....",
        ),
    ),
    # ---------------------------------------------------------- 第 3 关
    Level(
        name="连锁反应",
        hint="一行里的箭头会排队依次飞出",
        max_mistakes=3,
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
    # ---------------------------------------------------------- 第 4 关
    Level(
        name="四面楚歌",
        hint="只有一次机会是直通的，想清楚再点",
        max_mistakes=2,
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
)


def get_level(index):
    """按下标取关卡，越界时抛 IndexError。"""
    return LEVELS[index]


def validate_levels():
    """检查全部关卡：布局是否合法、是否可解。

    返回 [{'index', 'name', 'size', 'arrows', 'free', 'solvable', 'order'}]。
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
            }
        )
    return report
