# -*- coding: utf-8 -*-
"""棋盘核心逻辑（不依赖 pygame，可单独做单元测试）。

规则（对照参照画面的实际玩法）：
  * 棋盘是 rows × cols 的网格，每一格上可能落着某支箭的一段管道；
  * 一支「箭」是一条占若干格的折线，末端是一个箭头，方向为上/下/左/右之一；
  * 点击一支箭（点它身上任意一格都算）：
      - 从箭头出发、沿箭头方向到棋盘边界的射线上没有别的箭 -> 整支箭飞出棋盘被消除；
      - 射线上有别的箭挡着 -> 飞不出去，扣 1 点生命值；
  * 全部箭消除 -> 通关；生命值耗尽 -> 失败。
  * 通关时按「剩余生命值 ÷ 生命值上限」折算本关得分（规则见 game/scoring.py）。

为什么贪心求解是正确的：消除一支箭只会让其它箭的射线「变得更空」，
所以某支箭此刻能飞出，之后任何时刻它依然能飞出（单调性）。
详见 solve_level 的注释。
"""

from dataclasses import dataclass, field

from .pieces import DIRECTIONS, Piece, build_grid
from .scoring import level_score

# 棋盘状态
STATE_PLAYING = "playing"
STATE_CLEARED = "cleared"
STATE_FAILED = "failed"

# 点击结果类型
CLICK_FLY = "fly"          # 射线无阻挡，整支箭飞出
CLICK_BLOCKED = "blocked"  # 射线有阻挡，飞不出去（扣 1 点生命值）
CLICK_EMPTY = "empty"      # 点到了空格子
CLICK_IGNORED = "ignored"  # 本关已结束 / 点到棋盘外


@dataclass
class ClickResult:
    """一次点击的结果，交给界面层决定播放什么动画。"""

    kind: str
    piece: Piece = None                              # 被点击的箭
    blocker: Piece = None                            # 挡住它的箭（若被阻挡）
    path: list = field(default_factory=list)         # 箭头前方直到边界的格子


class Board:
    """一局游戏的棋盘状态。"""

    def __init__(self, level):
        # level 只需提供 rows / cols / pieces / max_hp 四个属性
        self.level = level
        self.rows = level.rows
        self.cols = level.cols
        self.max_hp = level.max_hp
        self.reset()

    # ------------------------------------------------------------ 初始化
    def reset(self):
        """把棋盘恢复到关卡初始状态（「重新开始」按钮调用）。"""
        self.pieces = list(self.level.pieces)
        self.grid = build_grid(self.rows, self.cols, self.pieces)
        self.total = len(self.pieces)   # 本关箭的总数
        self.remaining = self.total     # 剩余箭数
        self.hp = self.max_hp           # 剩余生命值（点错一次扣 1 点）
        self.state = STATE_PLAYING
        self.history = []               # 已经飞出的箭，便于复盘/测试

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
    def arrow_count(self):
        """本关箭的总数（沿用旧名字，关卡数据与文档里都在用）。"""
        return self.total

    @property
    def score(self):
        """本关当前能拿到的分数，随失去生命值实时下降（规则见 game/scoring.py）。

        放在棋盘上是有意的：得分只跟「丢了几颗心」有关，
        不需要另外维护一个计数器，也就不会出现两处数字对不上。
        """
        return level_score(self.level, self.hp)

    def in_bounds(self, row, col):
        return 0 <= row < self.rows and 0 <= col < self.cols

    def piece_at(self, row, col):
        """返回该格子所属的箭，越界或空格返回 None。"""
        if not self.in_bounds(row, col):
            return None
        index = self.grid[row][col]
        return None if index is None else self.pieces[index]

    def path_cells(self, piece):
        """该箭箭头前方、直到棋盘边界的全部格子坐标（不含箭头自己）。"""
        return piece.ray(self.rows, self.cols)

    def find_blocker(self, piece):
        """返回射线上第一支挡路的箭；通畅返回 None。

        只认**别的**箭：一支箭的身体本来就可能从自己箭头旁边绕过，
        把自己算成阻挡的话它会永远飞不出去（生成器与关卡校验都会拦掉
        更极端的「箭头正对自己」形状，但这里仍然要按「别的箭」来判断）。
        """
        own = self.grid[piece.head[0]][piece.head[1]]
        for row, col in self.path_cells(piece):
            index = self.grid[row][col]
            if index is not None and index != own:
                return self.pieces[index]
        return None

    def path_to_blocker(self, piece):
        """返回 (射线上到挡路那支为止的格子, 挡路的箭)，通畅时是 (整条射线, None)。

        界面画悬停路径时用的是它：红色只该画到被挡住的那一格，
        再往后的格子跟「为什么飞不出去」没有关系。

        单独抽出一个方法，是因为「挡路的格子」并不等于「挡路那支的箭头」——
        一支管道是好几格，压在射线上的一般是它的**身子**，箭头可能在很远的另一头。
        早先在界面里直接写 `path.index(blocker.head)`，只要挡路那支的箭头
        不在射线上就会抛 ValueError（悬停到这类管道上就崩），
        所以这个判断必须放在棋盘层、用格子归属来算。
        """
        path = self.path_cells(piece)
        own = self.grid[piece.head[0]][piece.head[1]]
        for index, (row, col) in enumerate(path):
            other = self.grid[row][col]
            if other is not None and other != own:
                return path[:index + 1], self.pieces[other]
        return path, None

    def can_fly(self, piece):
        """判断这支箭当前能否飞出棋盘。"""
        return self.grid[piece.head[0]][piece.head[1]] is not None and \
            self.find_blocker(piece) is None

    def available_arrows(self):
        """当前可以直接飞出的箭（用于难度统计与「提示」）。"""
        return [p for p in self.pieces if self.grid[p.head[0]][p.head[1]] is not None
                and self.can_fly(p)]

    # ------------------------------------------------------------ 交互
    def click(self, row, col):
        """点击一个格子，返回 ClickResult。

        这是整个游戏唯一修改棋盘状态的入口，界面层只负责根据返回值播放动画。
        点中一支箭的**任意一格**都算选中它——玩家看到的是整条管道。
        """
        if self.state != STATE_PLAYING:
            return ClickResult(CLICK_IGNORED)
        if not self.in_bounds(row, col):
            return ClickResult(CLICK_IGNORED)

        piece = self.piece_at(row, col)
        if piece is None:
            return ClickResult(CLICK_EMPTY)

        path = self.path_cells(piece)
        blocker = self.find_blocker(piece)

        # 情况一：射线无阻挡 -> 整支箭飞出棋盘
        if blocker is None:
            for r, c in piece.cells:
                self.grid[r][c] = None
            self.remaining -= 1
            self.history.append(piece)
            if self.remaining == 0:
                self.state = STATE_CLEARED
            return ClickResult(CLICK_FLY, piece, None, path)

        # 情况二：射线有阻挡 -> 扣 1 点生命值
        self.hp -= 1
        if self.hp <= 0:
            self.state = STATE_FAILED
        return ClickResult(CLICK_BLOCKED, piece, blocker, path)

    def solution(self):
        """返回一个可行的通关点击顺序（每项是一支箭）；若本关无解返回 None。"""
        return solve_level(self.rows, self.cols, self.pieces)


# ---------------------------------------------------------------- 关卡求解
def solve_level(rows, cols, pieces):
    """贪心求解关卡，返回可通关的点击顺序（箭的列表）；无解返回 None。

    为什么贪心是正确的：消除一支箭只会让其它箭的射线「变得更空」，
    所以一支箭此刻可以飞出，那么之后任何时刻它依然可以飞出（单调性）。
    因此反复扫描、每次消掉当前所有可消的箭，只要最后能全消掉，
    就一定存在通关顺序；反之若扫到无法继续却还有剩箭，则本关无解。
    """
    grid = [[None] * cols for _ in range(rows)]
    for index, piece in enumerate(pieces):
        for row, col in piece.cells:
            grid[row][col] = index

    order = []
    changed = True
    while changed:
        changed = False
        for index, piece in enumerate(pieces):
            head = piece.head
            if grid[head[0]][head[1]] != index:
                continue                       # 已经飞走了，或者被覆盖了（不该发生）
            d_row, d_col = DIRECTIONS[piece.direction]
            row, col = head[0] + d_row, head[1] + d_col
            blocked = False
            while 0 <= row < rows and 0 <= col < cols:
                if grid[row][col] is not None and grid[row][col] != index:
                    blocked = True             # 挡路的必须是别的箭，不是自己
                    break
                row += d_row
                col += d_col
            if not blocked:
                for r, c in piece.cells:
                    grid[r][c] = None
                order.append(piece)
                changed = True

    left = sum(1 for line in grid for cell in line if cell is not None)
    return order if left == 0 else None


def count_free_pieces(rows, cols, pieces):
    """统计开局时可以直接飞出的箭数（越少通常越难）。

    和 solve_level 一样，**挡路的只认别的箭**：管道绕回来贴着自己箭头前方
    是可能发生的（虽然 validate_layout 会拦掉「射线穿过自己身体」的极端形状）。
    两处判断必须同源，否则会出现「统计说这支能飞、求解器说它飞不出去」
    这种谁都不算错的矛盾结果。
    """
    grid = [[None] * cols for _ in range(rows)]
    for index, piece in enumerate(pieces):
        for row, col in piece.cells:
            grid[row][col] = index

    free = 0
    for index, piece in enumerate(pieces):
        head = piece.head
        d_row, d_col = DIRECTIONS[piece.direction]
        row, col = head[0] + d_row, head[1] + d_col
        blocked = False
        while 0 <= row < rows and 0 <= col < cols:
            if grid[row][col] is not None and grid[row][col] != index:
                blocked = True
                break
            row += d_row
            col += d_col
        if not blocked:
            free += 1
    return free
