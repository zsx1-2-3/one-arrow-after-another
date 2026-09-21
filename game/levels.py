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

难度只在前 5 关靠**放大棋盘**，第 6 关起换成靠**提高密度**——
棋盘尺寸到第 8 关就封顶在 9×9，之后同样的格子里塞进更多箭头。
注意这件事有陷阱：贴着边、朝棋盘外的箭头射线长度是 0，永远能飞，
不管它的话密度一高开局可点数反而暴涨（比稀疏时还简单）。
生成器因此会避开这类候选，并用 `seen × 1 + raylen × 3` 打分，
让高密度布局仍能把开局可点数压在 3~5 支。详见 tools/generate_levels.py 开头。

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
    max_hp: int                             # 本关生命值上限（点错一次扣 1 点）
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
    def density(self):
        """箭头密度 = 箭头数 ÷ 格子数（同一尺寸下密度越高越难扫）。"""
        return self.arrow_count / float(self.rows * self.cols)

    @property
    def difficulty_score(self):
        """难度分（越大越难）：箭头数与密度为正贡献，可点箭头与生命值为负贡献。"""
        return (self.arrow_count * 1.6
                + self.density * 30.0
                - self.free_count * 2.0
                - self.max_hp * 1.5)

    @property
    def stars(self):
        """把难度分映射成 1~5 颗星，显示在关卡总览里。

        阈值是按当前 9 个关卡的实际难度分挑的，让星级均匀铺开
        （-2.2 / 2.0 → 1 星，3.2 / 13.1 → 2 星，20.0 / 27.8 → 3 星，
        51.6 / 67.8 → 4 星，85.5 → 5 星）。
        """
        score = self.difficulty_score
        for threshold, stars in ((3.0, 1), (16.0, 2), (30.0, 3), (70.0, 4)):
            if score < threshold:
                return stars
        return 5


LEVELS = (
    # ======================================================== 第 0 关：教学
    Level(
        name="教学关",
        hint="跟着黄色提示点，很快就能上手",
        max_hp=5,
        tutorial=True,
        layout=(
            ".....",
            ".>.v.",
            ".....",
            "..^..",
        ),
        steps=(
            TutorialStep("先点这支朝右的箭头。它前方还有一支箭头挡路，飞不出去，"
                         "会失去一心——这就是「被挡住」的样子。", 1, 1, "blocked"),
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
        max_hp=4,
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
        max_hp=4,
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
        max_hp=4,
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
        max_hp=3,
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
    #  第 5~8 关由 tools/generate_levels.py 生成（逆向构造，布局必然可解）。
    #  刻意**不靠放大棋盘**加难：尺寸到第 7 关就封顶在 9×9，
    #  之后只靠提高密度（同样的格子塞进更多箭头）继续变难。
    #  四关的箭头数 18 / 30 / 40 / 50，密度 0.37 / 0.47 / 0.49 / 0.62。
    Level(
        name="错位走廊",
        hint="顺着能飞的那一支点下去，会一路连锁",
        max_hp=4,
        layout=(
            ">..v...",
            ".>vv...",
            "v...<<<",
            ".>.v...",
            ">.vv...",
            ".>.....",
            ".^...^<",
        ),
    ),
    # ======================================================== 第 6 关
    Level(
        name="长蛇阵",
        hint="格子变挤了，横竖两个方向都要扫一遍",
        max_hp=3,
        layout=(
            ">vv.>...",
            ".v.....<",
            ">.v>.>>.",
            ">..^>^..",
            "..v<.<.<",
            ">>.>..^.",
            ">>...^^.",
            "....^.^<",
        ),
    ),
    # ======================================================== 第 7 关
    Level(
        name="十面埋伏",
        hint="空格没剩多少，别凭感觉乱点",
        max_hp=2,
        layout=(
            "v.vv...v.",
            ">>.v..vv.",
            ">..>.>v.^",
            ".v....v.<",
            ".v.<<v.v.",
            ">v..^vv..",
            "..>..>>v.",
            "....^>.v.",
            ">.v.^>>>.",
        ),
    ),
    # ======================================================== 第 8 关
    Level(
        name="万箭归一",
        hint="全场塞了 50 支箭头，只有几支能先飞",
        max_hp=2,
        layout=(
            ".v.vv.v.^",
            ">v^v.>>>^",
            ">v.>>>.^.",
            ">...v.>^.",
            ">..>>>.>^",
            ">>^>.^v^^",
            ">v..v>.>^",
            "..^....<^",
            "^.^....^<",
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

    返回 [{'index', 'name', 'size', 'arrows', 'density', 'free', 'solvable', 'order',
            'max_hp', 'stars', 'tutorial'}]。
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
                "density": level.density,
                "free": count_free_arrows(level.rows, level.cols, level.arrows),
                "solvable": order is not None,
                "order": order or [],
                "max_hp": level.max_hp,
                "stars": level.stars,
                "tutorial": level.tutorial,
            }
        )
    return report
