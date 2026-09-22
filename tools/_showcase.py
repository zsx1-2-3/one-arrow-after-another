# -*- coding: utf-8 -*-
"""演示素材（截图 / 演示动图）共用的「取景」逻辑。

两个脚本都要回答同一类问题：「棋盘上现在哪一支管道最能说明这件事？」
答案不能写死坐标——关卡数据一改，写死的坐标会静默指向别的管道，
截出来的图还是"能看"的，只是已经不能说明它要说明的那件事了。
所以这里一律**按状态找目标**。

另一条来自关卡数据的约束得先说清楚：九个关卡是**逆向构造**出来的
（见 game/levels.py），铺满率 92% 以上，开局盘面上几乎没有空格。于是——

  * 任何朝盘内的射线都在一两格内被对方挡住，被挡路径（红）只有一格；
  * 能直接飞的只剩「贴着边、箭头朝盘外」的那几支，它们的射线长度为 0，
    "这条路是空的"（绿）根本画不出来。

所以想拍到像样的红/绿路径，得**先按解法点掉几步**给盘面腾出空档，
再按状态找回该悬停哪一支。`plan_*` 系列就是干这个的：
在另建的一局棋盘上试几步，算出「点掉前 k 支之后盘面是什么样」，
返回该点几步，调用方照着点就行。
"""

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.board import Board  # noqa: E402
from game.progress import Progress  # noqa: E402


def find_blocked(board):
    """找当前盘面上「被挡路径最长」的管道——悬停它，红色最长。"""
    found = [p for p in board.pieces
             if board.piece_at(*p.head) is p and board.find_blocker(p) is not None]
    if not found:
        raise RuntimeError("没有找到被挡住的管道")
    return max(found, key=lambda p: (len(board.path_to_blocker(p)[0]), -p.head[0]))


def find_free(board):
    """找当前盘面上「射线最长且通畅」的管道——悬停它，绿色最长。

    只挑射线长度 > 0 的：贴着边、箭头朝盘外的那类虽然也能飞，
    但射线是空的，画出来只有一个小箭头，说明不了"这条路一路空到盘外"。
    """
    free = [p for p in board.available_arrows() if len(board.path_cells(p)) > 0]
    if not free:
        raise RuntimeError("没有找到射线通畅的管道")
    return max(free, key=lambda p: (len(board.path_cells(p)), -p.head[0]))


# ---------------------------------------------------------------- 局面扫描
def _metrics(board):
    """当前盘面的两个取景指标：最长被挡路径（红）、最长通畅射线（绿）。"""
    red = 0
    for piece in board.pieces:
        if board.piece_at(*piece.head) is not piece:
            continue                                   # 已经飞走了
        path, blocker = board.path_to_blocker(piece)
        if blocker is not None and len(path) > red:
            red = len(path)
    green = 0
    for piece in board.available_arrows():
        green = max(green, len(board.path_cells(piece)))
    return red, green


def _scan(level, max_steps):
    """扫一遍「点掉前 k 支之后的盘面」，yield (k, 红路径长度, 绿路径长度)。

    在**另建的一局棋盘**上走，不会动调用方手里那局。
    """
    probe = Board(level)
    solution = probe.solution() or []
    for step in range(max_steps + 1):
        red, green = _metrics(probe)
        yield step, red, green
        if step < len(solution):
            probe.click(*solution[step].head)


def plan_balance(level, max_steps=6, red_cap=4, green_cap=5):
    """找一个「红绿两条路径都拿得出手」的局面，返回该点掉几支（k）。

    这一版的关卡盘面是铺满的，开局红路径只有一格、绿路径长度为 0；
    点掉几支才画得出长度，但点太多又会把棋盘点空、看不出"密集"这件事，
    所以两头都要兼顾。打分就是取两者各自封顶后的和：

        score = min(最长被挡路径, red_cap) + min(最长通畅射线, green_cap)

    取分最高的一步；同分取步数少的（少点几下，GIF 更短）。
    封顶是为了不让某一头把另一头压死：一条 12 格的绿路径很好看，
    但配一条 1 格的红路径，两张对照图就没法说明差别只在"通不通"。
    """
    best_step, best_score = 0, -1
    for step, red, green in _scan(level, max_steps):
        score = min(red, red_cap) + min(green, green_cap)
        if score > best_score:
            best_step, best_score = step, score
    return best_step


def plan_long_green(level, max_steps=6, floor=3):
    """找一个「绿路径尽量长」的局面，返回该点掉几支（k）。

    拍「辅助线」这类图要用它：辅助线画的是每支管道的前方，盘面空档越多，
    这些线才拉得越长、越看得出是在讲「去路」；用 plan_balance 挑出来的
    局面为了照顾红路径会偏保守，辅助线就还是一堆小短线。
    floor 是及格线：达到就先收，避免为了多一格多点上好几步。
    """
    best_step, best_green = 0, -1
    for step, _red, green in _scan(level, max_steps):
        if green > best_green:
            best_step, best_green = step, green
        if green >= floor:
            return step
    return best_step


def same_piece(board, piece):
    """在当前棋盘上按 uid 找回同一支管道（Piece 的 uid 在关卡内唯一）。"""
    for candidate in board.pieces:
        if candidate.uid == piece.uid:
            return candidate
    raise RuntimeError("棋盘上找不到 uid=%s 的管道" % piece.uid)


# ---------------------------------------------------------------- 存档
def fresh_progress(tag, precleared=()):
    """建一份**临时目录里的存档**，避免录素材时把玩家真实进度读进来 / 写坏。

    precleared 里的关卡会被标记成已通关——`start_level` 走的是和真实玩家
    同一套解锁判定，不预先解锁的话脚本会直接被拒绝开局。
    """
    save_path = os.path.join(tempfile.gettempdir(), "_arrow_%s_progress.json" % tag)
    if os.path.exists(save_path):
        os.remove(save_path)
    progress = Progress(path=save_path, autoload=False)
    for index in precleared:
        progress.mark_cleared(index)
    return progress, save_path


def discard_progress(save_path):
    """录完把临时存档删掉。"""
    if os.path.exists(save_path):
        os.remove(save_path)
