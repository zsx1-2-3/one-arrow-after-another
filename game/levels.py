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

配色为什么不让同色连片
----------------------
早期布局只关心「谁挡谁」，结果经常出现一整排同向箭头贴在一起：屏幕上是一片同色，
看着既单调又显简单（实测第 8 关相邻同向对占 59%、最大同色块 6 格）。
现在布局定稿前会再过一遍 tools/deshuffle_levels.py——**位置一格不动，只逐个试换方向**，
每换一次都要求「同向相邻对减少 + 开局可点数不增加 + 换完仍然可解」。
处理完 6 个关卡的同向相邻占比从 45%~67% 降到 11%~22%，开局可点数一支没变
（只有第 5 关的「只有一支能飞」松到两支，hint 已同步）。

注意**不要去改 config.DIR_COLORS**：要交错的是方向在棋盘上的分布，
不是一个方向内部的颜色——同方向的箭头永远保持同一个颜色，这是玩家判断走向的依据。

生命值为什么逐关变多
--------------------
关卡越到后面箭头越挤、要逐条扫视的射线越多，越容易点错，
所以生命值上限不是固定值，而是**按难度星级给**（见 HP_BY_STARS）：
第 1 关 4 颗心，最后一关 7 颗心。于是「容错」和「难度」一起往上走，
玩家不会在最后一关因为一次手滑就被打回原点。

得分规则见 game/scoring.py：本关得分 = 星级 × 250 × 剩余生命值 ÷ 生命值上限，
一颗心都没丢再额外加 20%。每关的满分因此正好是「星级 × 300」。

改关卡时请连 `max_hp` 一起核对：`max_hp` 必须等于 `HP_BY_STARS[星级]`，
而且整体不下降（tests/test_game.py 有专门的用例钉着这两条）。
"""

from dataclasses import dataclass

from .board import ARROW_CHARS

EMPTY_CHARS = {".", " ", "_", "-"}

# 生命值上限 = 按难度星级给。星级越高（越难），容错越高。
#
# 教学关（1 星）也给 4 颗：它的第一步就是故意引导玩家点一支被挡住的箭头，
# 那一颗心本来就在预算里，多留一颗免得新手在教程里就被判失败。
HP_BY_STARS = {1: 4, 2: 4, 3: 5, 4: 6, 5: 7}


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
    max_hp: int                             # 本关生命值上限（点错一次扣 1 点），按难度给
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
        self._difficulty = None                 # 难度分的缓存（星级、生命值都依赖它）

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
        """难度分（越大越难）：箭头数与密度为正贡献，可点箭头为负贡献。

        刻意**不含生命值**：生命值现在是由难度分推出来的（见 HP_BY_STARS），
        要是再把生命值算进难度分，就成了「难度高 → 给的心多 → 难度算下来变低」
        的循环，星级也会跟着乱跳。难度只管棋盘本身有多难扫。
        """
        if self._difficulty is None:
            self._difficulty = (self.arrow_count * 1.6
                                + self.density * 30.0
                                - self.free_count * 2.0)
        return self._difficulty

    @property
    def stars(self):
        """把难度分映射成 1~5 颗星（关卡总览里显示），也决定本关给几颗心。

        阈值是按当前 9 个关卡的实际难度分挑的，让星级均匀铺开
        （5.3 → 1 星，8.0 / 9.2 → 2 星，19.1 / 22.6 → 3 星，
        33.8 / 56.1 → 4 星，70.8 / 88.5 → 5 星）。
        """
        score = self.difficulty_score
        for threshold, stars in ((6.0, 1), (10.0, 2), (26.0, 3), (60.0, 4)):
            if score < threshold:
                return stars
        return 5


LEVELS = (
    # ======================================================== 第 0 关：教学
    Level(
        name="教学关",
        hint="跟着黄色提示点，很快就能上手",
        max_hp=4,
        tutorial=True,
        layout=(
            ".....",
            ".>.v.",
            ".....",
            "..^..",
        ),
        steps=(
            TutorialStep("先点这支朝右的箭头。它前方还有一支箭头挡路，飞不出去，"
                         "会丢掉一颗心——这就是「被挡住」的样子。", 1, 1, "blocked"),
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
        hint="先点掉能飞的那一支，它会替后面的箭头让开路",
        max_hp=5,
        layout=(
            "......",
            ".>>v>v",
            "......",
            "......",
            ".^<>^.",
            "....v.",
            "......",
        ),
    ),
    # ======================================================== 第 4 关
    Level(
        name="四面楚歌",
        hint="开局能直接飞出的箭头很少，先把它们找出来",
        max_hp=5,
        layout=(
            "....v..",
            ".>>v>v.",
            ".......",
            "..^v...",
            ".......",
            ".^<v<..",
            ".......",
        ),
    ),
    # ======================================================== 第 5 关
    #  第 5~8 关由 tools/generate_levels.py 生成（逆向构造，布局必然可解），
    #  再用 tools/deshuffle_levels.py 把同色扎堆磨平：保持位置不动、只逐个试换方向，
    #  要求「开局可点数不变 + 换完仍可解」，所以难度没被顺手改掉。
    #  刻意**不靠放大棋盘**加难：尺寸到第 7 关就封顶在 9×9，
    #  之后只靠提高密度（同样的格子塞进更多箭头）继续变难。
    #  四关的箭头数 18 / 30 / 40 / 50，密度 0.37 / 0.47 / 0.49 / 0.62。
    Level(
        name="错位走廊",
        hint="顺着能飞的那一支点下去，会一路连锁",
        max_hp=6,
        layout=(
            ">..v...",
            ".>v>...",
            "v...<<v",
            ".>.v...",
            ">.>v...",
            ".>.....",
            ".^...^<",
        ),
    ),
    # ======================================================== 第 6 关
    Level(
        name="长蛇阵",
        hint="格子变挤了，横竖两个方向都要扫一遍",
        max_hp=6,
        layout=(
            ">v>.>...",
            ".v.....<",
            ">.v>.>^.",
            "^..^>^..",
            "..v<.<.<",
            ">v.>..^.",
            "^>...>^.",
            "....^.^<",
        ),
    ),
    # ======================================================== 第 7 关
    Level(
        name="十面埋伏",
        hint="空格没剩多少，别凭感觉乱点",
        max_hp=7,
        layout=(
            "v.<>...v.",
            "v>.v..>v.",
            ">..>.>^.^",
            ".^....v.<",
            ".v.<<v.v.",
            ">v..^>v..",
            "..>..v>v.",
            "....^<.<.",
            ">.v.^>>v.",
        ),
    ),
    # ======================================================== 第 8 关
    Level(
        name="万箭归一",
        hint="全场塞了 50 支箭头，只有几支能先飞",
        max_hp=7,
        layout=(
            ".>.>v.>.>",
            ">v^v.>v>^",
            "^>.>v^.^.",
            ">...>.>^.",
            ">..>v>.>^",
            "^>^>.^v^^",
            ">v..v>.>^",
            "..^....<v",
            "^.<....^<",
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
            'max_hp', 'stars', 'max_score', 'tutorial'}]。
    """
    from .board import count_free_arrows, solve_level
    from .scoring import max_score

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
                "max_score": max_score(level),
                "tutorial": level.tutorial,
            }
        )
    return report
