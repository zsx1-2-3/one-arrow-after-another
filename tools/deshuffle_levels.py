# -*- coding: utf-8 -*-
"""配色打散：**保持每支箭头的位置不动**，只逐个试换方向，把同色扎堆磨平。

为什么要「只换方向、不动位置」
------------------------------
关卡的位置结构是一层层设计出来的——谁挡谁、先飞哪一支，都跟位置有关。
直接把整关重新生成一遍，配色是好了，但难度也跟着漂移（实测第 8 关开局可点
从 5 支涨到 9 支，比原来还简单）。只换方向就不一样：棋盘形状、箭头数量、
甚至「哪几支互相牵制」的骨架都在，改的只是每支箭头朝向哪个方向。

每次改动都要过三道闸
--------------------
    1) 扎堆指标必须**变小**（同向相邻对数减少，或同色块变小），否则不算数；
    2) 开局可点数不能超过原关卡（不能顺手把难度放松），也不能一支都点不动；
    3) 换完之后布局仍然**可解**（solve_level 验证——不能为了好看把题变成死局）。

方向的选择空间很小（每格 4 选 1），所以用「贪心 + 多次随机重启」：
一轮接受不了新改动就换个随机种子重来，最后取扎堆指标最好的一版。

用法：
    python tools/deshuffle_levels.py                    # 打印全部关卡的打散结果
    python tools/deshuffle_levels.py --index 4 5 6      # 只处理指定关卡（从 1 数起）
    python tools/deshuffle_levels.py --extra-free 1     # 允许开局可点比原来多 1 支
"""

import argparse
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.board import count_free_arrows, solve_level  # noqa: E402
from game.levels import LEVELS  # noqa: E402
from generate_levels import cluster_metrics, to_ascii  # noqa: E402

CHAR = {"up": "^", "down": "v", "left": "<", "right": ">"}
DIRECTIONS_LIST = ("up", "down", "left", "right")


def _placement(grid):
    return [(row, col, direction) for (row, col), direction in grid.items()]


def deshuffle(rows, cols, arrows, rng, attempts=800, max_free0=None):
    """返回 (新 arrows, 指标)。没找到更好的改法时原样返回。"""
    grid = {(row, col): direction for row, col, direction in arrows}
    cells = list(grid)
    same, biggest = pair_stats(rows, cols, _placement(grid))
    free0 = count_free_arrows(rows, cols, _placement(grid))
    accepted = 0

    for _ in range(attempts):
        row, col = rng.choice(cells)
        old = grid[(row, col)]
        others = [d for d in DIRECTIONS_LIST if d != old]
        rng.shuffle(others)

        for direction in others:
            grid[(row, col)] = direction
            placement = _placement(grid)
            new_same, new_block = pair_stats(rows, cols, placement)
            if new_same >= same:                    # 扎堆没变好，直接跳过
                continue
            new_free0 = count_free_arrows(rows, cols, placement)
            if new_free0 < 1:
                continue
            if max_free0 is not None and new_free0 > max_free0:
                continue
            if solve_level(rows, cols, placement) is None:
                continue
            same, biggest = new_same, new_block
            free0 = new_free0
            accepted += 1
            break
        else:
            grid[(row, col)] = old

    return [(row, col, grid[(row, col)]) for row, col in cells], (same, biggest, free0, accepted)


def pair_stats(rows, cols, placement):
    """相邻同向对数（分子）+ 同色连通块最大格子数。"""
    ratio, biggest = cluster_metrics(rows, cols, placement)
    grid = {(row, col): direction for row, col, direction in placement}
    pair = same = 0
    for (row, col), direction in grid.items():
        for d_row, d_col in ((1, 0), (0, 1)):
            other = grid.get((row + d_row, col + d_col))
            if other is None:
                continue
            pair += 1
            same += other == direction
    return same, biggest


def layout_of(rows, cols, arrows):
    grid = [["." for _ in range(cols)] for _ in range(rows)]
    for row, col, direction in arrows:
        grid[row][col] = CHAR[direction]
    return tuple("".join(line) for line in grid)


def main():
    parser = argparse.ArgumentParser(description="把同色扎堆的关卡打散（只换方向，不动位置）")
    parser.add_argument("--index", type=int, nargs="*", default=None,
                        help="只处理这些关卡（从 1 数起）")
    parser.add_argument("--extra-free", type=int, default=0,
                        help="允许开局可点比原来多几支（默认 0，即不放松难度）")
    parser.add_argument("--restarts", type=int, default=8, help="随机重启次数")
    parser.add_argument("--attempts", type=int, default=600, help="每次重启的尝试步数")
    parser.add_argument("--seed", type=int, default=20260921)
    args = parser.parse_args()

    wanted = set(args.index) if args.index else None

    for number, level in enumerate(LEVELS, start=1):
        if wanted and number not in wanted:
            continue
        base = [(row, col, direction) for row, col, direction in level.arrows]
        pair_base = cluster_metrics(level.rows, level.cols, base)
        free_base = count_free_arrows(level.rows, level.cols, base)

        best = None
        start = time.time()
        for restart in range(max(1, args.restarts)):
            rng = random.Random(args.seed + number * 131 + restart * 7717)
            candidate, stats = deshuffle(level.rows, level.cols, base, rng,
                                         attempts=args.attempts,
                                         max_free0=free_base + args.extra_free)
            if best is None or stats[:3] < best[1][:3]:
                best = (candidate, stats)
            if best[1][0] == 0:
                break
        spent = time.time() - start

        total_pairs = _pair_count(level.rows, level.cols, base)
        arrows, (same, biggest, free0, accepted) = best
        ratio = same / float(total_pairs) if total_pairs else 0.0
        print("=" * 78)
        print("第 %d 关  %s   %d×%d  %d 支   耗时 %.1fs   共接受 %d 次改动"
              % (number, level.name, level.rows, level.cols, level.arrow_count,
                 spent, accepted))
        print("  原：同向相邻 %.1f%%（%d/%d）  同色块 %d   开局可点 %d"
              % (pair_base[0] * 100, round(pair_base[0] * total_pairs), total_pairs,
                 pair_base[1], free_base))
        print("  新：同向相邻 %.1f%%（%d/%d）  同色块 %d   开局可点 %d"
              % (ratio * 100, same, total_pairs, biggest, free0))
        print("  新布局：")
        for line in layout_of(level.rows, level.cols, arrows):
            print('            "%s",' % line)
        print()


def _pair_count(rows, cols, arrows):
    grid = {(row, col): direction for row, col, direction in arrows}
    pair = 0
    for (row, col) in grid:
        for d_row, d_col in ((1, 0), (0, 1)):
            if (row + d_row, col + d_col) in grid:
                pair += 1
    return pair


if __name__ == "__main__":
    main()
