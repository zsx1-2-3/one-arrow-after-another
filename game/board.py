# -*- coding: utf-8 -*-
"""棋盘核心逻辑（不依赖 pygame，可单独做单元测试）。

规则（见作业要求「二、作业描述」）：
  * 棋盘是 rows × cols 的网格，格子中可能有「上/下/左/右」四个方向之一的箭头；
  * 点击一个箭头后，沿着它指向的方向（同一行或同一列）一直检查到棋盘边界；
      - 路径上没有其它箭头  -> 该箭头飞出棋盘并被消除；
      - 路径上存在其它箭头  -> 不能消除，扣 1 点生命值；
  * 全部箭头消除 -> 通关；生命值耗尽 -> 失败。
  * 通关时按「剩余生命值 ÷ 生命值上限」折算本关得分（规则见 game/scoring.py）。
"""

from dataclasses import dataclass, field

from .scoring import level_score

# ---------------------------------------------------------------- 常量
# 方向 -> (行增量, 列增量)。行号向下增大，列号向右增大。
DIRECTIONS = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}

# 关卡布局中的字符 -> 方向
ARROW_CHARS = {"^": "up", "v": "down", "<": "left", ">": "right"}

# 棋盘状态
STATE_PLAYING = "playing"
STATE_CLEARED = "cleared"
STATE_FAILED = "failed"

# 点击结果类型
CLICK_FLY = "fly"          # 前方无阻挡，箭头飞出
CLICK_BLOCKED = "blocked"  # 前方有阻挡，不能飞出（扣 1 点生命值）
CLICK_EMPTY = "empty"      # 点到了空格子
CLICK_IGNORED = "ignored"  # 本关已结束 / 点到棋盘外


@dataclass
class Arrow:
    """棋盘上的一个箭头。"""

    row: int
    col: int
    direction: str
    uid: int = 0

    @property
    def delta(self):
        """返回 (行增量, 列增量)。"""
        return DIRECTIONS[self.direction]


@dataclass
class ClickResult:
    """一次点击的结果，交给界面层决定播放什么动画。"""

    kind: str
    arrow: Arrow = None                              # 被点击的箭头
    blocker: Arrow = None                            # 挡住它的箭头（若被阻挡）
    path: list = field(default_factory=list)         # 前进方向上的格子坐标列表


class Board:
    """一局游戏的棋盘状态。"""

    def __init__(self, level):
        # level 只需提供 rows / cols / arrows / max_hp 四个属性
        self.level = level
        self.rows = level.rows
        self.cols = level.cols
        self.max_hp = level.max_hp
        self.reset()

    # ------------------------------------------------------------ 初始化
    def reset(self):
        """把棋盘恢复到关卡初始状态（「重新开始」按钮调用）。"""
        self.grid = [[None] * self.cols for _ in range(self.rows)]
        self.arrows = []
        for index, (row, col, direction) in enumerate(self.level.arrows):
            arrow = Arrow(row, col, direction, index)
            self.grid[row][col] = arrow
            self.arrows.append(arrow)

        self.total = len(self.arrows)   # 本关箭头总数
        self.remaining = self.total     # 剩余箭头数
        self.hp = self.max_hp           # 剩余生命值（点错一次扣 1 点）
        self.state = STATE_PLAYING
        self.history = []               # 已经飞出的箭头，便于复盘/测试

    # ------------------------------------------------------------ 查询
    @property
    def hp_left(self):
        """剩余生命值。"""
        return self.hp

    @property
    def hearts_lost(self):
        """已经失去的生命值（点错了几次）；一颗心都没丢时是 0。"""
        return self.max_hp - self.hp

    @property
    def score(self):
        """本关当前能拿到的分数，随失去生命值实时下降（规则见 game/scoring.py）。

        放在棋盘上是有意的：得分只跟「丢了几颗心」有关，
        不需要另外维护一个计数器，也就不会出现两处数字对不上的情况。
        """
        return level_score(self.level, self.hp)

    def in_bounds(self, row, col):
        return 0 <= row < self.rows and 0 <= col < self.cols

    def arrow_at(self, row, col):
        """返回该格子上的箭头，越界或空格返回 None。"""
        if not self.in_bounds(row, col):
            return None
        return self.grid[row][col]

    def path_cells(self, row, col):
        """该箭头前进方向上、直到棋盘边界的全部格子坐标（不含自身）。"""
        arrow = self.grid[row][col]
        if arrow is None:
            return []
        d_row, d_col = arrow.delta
        cells = []
        r, c = row + d_row, col + d_col
        while self.in_bounds(r, c):
            cells.append((r, c))
            r += d_row
            c += d_col
        return cells

    def find_blocker(self, row, col):
        """返回前进方向上第一个挡路的箭头；路径通畅返回 None。"""
        for r, c in self.path_cells(row, col):
            if self.grid[r][c] is not None:
                return self.grid[r][c]
        return None

    def can_fly(self, row, col):
        """判断该格子上的箭头当前能否飞出棋盘。"""
        return self.grid[row][col] is not None and self.find_blocker(row, col) is None

    def available_arrows(self):
        """当前可以直接飞出的箭头列表（用于难度统计）。"""
        return [a for a in self.arrows if self.grid[a.row][a.col] is a and self.can_fly(a.row, a.col)]

    # ------------------------------------------------------------ 交互
    def click(self, row, col):
        """点击一个格子，返回 ClickResult。

        这是整个游戏唯一修改棋盘状态的入口，界面层只负责根据返回值播放动画。
        """
        if self.state != STATE_PLAYING:
            return ClickResult(CLICK_IGNORED)
        if not self.in_bounds(row, col):
            return ClickResult(CLICK_IGNORED)

        arrow = self.grid[row][col]
        if arrow is None:
            return ClickResult(CLICK_EMPTY)

        path = self.path_cells(row, col)
        blocker = self.find_blocker(row, col)

        # 情况一：前方无阻挡 -> 飞出棋盘
        if blocker is None:
            self.grid[row][col] = None
            self.remaining -= 1
            self.history.append(arrow)
            if self.remaining == 0:
                self.state = STATE_CLEARED
            return ClickResult(CLICK_FLY, arrow, None, path)

        # 情况二：前方有阻挡 -> 扣 1 点生命值
        self.hp -= 1
        if self.hp <= 0:
            self.state = STATE_FAILED
        return ClickResult(CLICK_BLOCKED, arrow, blocker, path)

    def solution(self):
        """返回一个可行的通关点击顺序；若本关无解返回 None。"""
        return solve_level(self.rows, self.cols, self.level.arrows)


# ---------------------------------------------------------------- 关卡求解
def solve_level(rows, cols, arrows):
    """贪心求解关卡，返回可通关的点击顺序 [(row, col), ...]；无解返回 None。

    为什么贪心是正确的：消除箭头只会让其它箭头的路径「变得更空」，
    所以一个箭头此刻可以飞出，那么之后任何时刻它依然可以飞出（单调性）。
    因此反复扫描、每次消掉当前所有可消的箭头，只要最后能全消掉，
    就一定存在通关顺序；反之若扫描到无法继续却还有剩余箭头，则本关无解。
    """
    grid = [[None] * cols for _ in range(rows)]
    for row, col, direction in arrows:
        grid[row][col] = direction

    order = []
    changed = True
    while changed:
        changed = False
        for row in range(rows):
            for col in range(cols):
                direction = grid[row][col]
                if direction is None:
                    continue
                d_row, d_col = DIRECTIONS[direction]
                r, c = row + d_row, col + d_col
                blocked = False
                while 0 <= r < rows and 0 <= c < cols:
                    if grid[r][c] is not None:
                        blocked = True
                        break
                    r += d_row
                    c += d_col
                if not blocked:
                    grid[row][col] = None
                    order.append((row, col))
                    changed = True

    left = sum(1 for line in grid for cell in line if cell is not None)
    return order if left == 0 else None


def count_free_arrows(rows, cols, arrows):
    """统计开局时可以直接飞出的箭头数量（越少通常越难）。"""
    grid = [[None] * cols for _ in range(rows)]
    for row, col, direction in arrows:
        grid[row][col] = direction

    free = 0
    for row, col, direction in arrows:
        d_row, d_col = DIRECTIONS[direction]
        r, c = row + d_row, col + d_col
        blocked = False
        while 0 <= r < rows and 0 <= c < cols:
            if grid[r][c] is not None:
                blocked = True
                break
            r += d_row
            c += d_col
        if not blocked:
            free += 1
    return free
