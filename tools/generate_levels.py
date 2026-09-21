# -*- coding: utf-8 -*-
"""关卡生成器：用「逆向构造法」批量产出**保证可解**的布局，供人工挑选。

为什么要逆向构造
----------------
正向随机构造（随机撒箭头）很容易撒出无解布局。换个角度想：
把「消除顺序」倒过来就是「放置顺序」——

    设消除顺序为 a1, a2, ..., an。消除 a_k 时棋盘上只剩 a_1..a_{k-1}，
    所以 a_k 正前方不能有 a_1..a_{k-1}（它们那时还在）。

    反过来放置：先放 a_n，再放 a_{n-1}，……最后放 a_1。
    放置 a_k 时棋盘上只有 a_{k+1}..a_n，且要求「a_k 正前方不含已放置的箭头」。
    由于 a_1..a_{k-1} 此刻还没放，它们未来落在 a_k 前方是允许的——
    它们会在 a_k 之前被消掉。

于是——「放置顺序的逆序」天然就是一个合法通关顺序，布局必然可解。

难度指标
--------
    free0   开局可以直接飞出的箭头数（越少越难）
    avg     通关全程「当前可选择数」的平均值（越小说明选择越少、越像被锁死）
    peak    全程可选数的最大值（越大说明能一路顺推，越简单）

用法：
    python tools/generate_levels.py                     # 打印预设难度的候选
    python tools/generate_levels.py -r 8 -c 8 -n 17 -k 5 --seed 2026
    python tools/generate_levels.py --ascii -r 7 -c 7 -n 12 -k 1

参数说明：
    -r/-c  行数 / 列数        -n  箭头数量        -k  输出前 k 个候选
    --seed 随机种子（同一个种子结果可复现）
"""

import argparse
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.board import DIRECTIONS  # noqa: E402

CHAR = {"up": "^", "down": "v", "left": "<", "right": ">"}


# ------------------------------------------------------------------ 生成
def place_reverse(rows, cols, count, rng, density=0.85):
    """逆向放置 count 支箭头，返回 {'placement': [(r, c, dir), ...]}。

    placement[0] 是最后被消掉的箭头，placement[-1] 是开局第一个应该被点掉的箭头。
    返回 None 表示在给定尺寸下放不下这么多箭头。

    难度倾向（density）：放置新箭头时，优先选「落在已有箭头正前方」的位置，
    这样被挡住的老箭头需要等新箭头先飞走才能动，难度就上来了。
    density=0 退化为纯随机（布局很松、开局几乎全都能飞）。

    实现要点：维护一张 seen 表——seen[r][c] 记录「有多少支已放置的箭头正前方会经过
    这个格子」，放置箭头时沿它的射线加一。这样判断某格会不会挡住别人就是 O(1)，
    不需要每次重新扫描全盘。
    """
    placed = {}                                   # (row, col) -> direction
    seen = [[0] * cols for _ in range(rows)]      # 被多少支箭头的射线覆盖
    placement = []
    directions = list(DIRECTIONS)

    for _ in range(count):
        samples = []

        def collect(row, col, direction):
            """若合法就收集起来（含阻挡信息）。"""
            if (row, col) in placed:
                return
            d_row, d_col = DIRECTIONS[direction]
            r, c = row + d_row, col + d_col
            while 0 <= r < rows and 0 <= c < cols:
                if (r, c) in placed:              # 正前方有已放置的箭头 -> 不合法
                    return
                r += d_row
                c += d_col
            samples.append((row, col, direction, seen[row][col]))

        for _ in range(60):                       # 随机采样
            collect(rng.randrange(rows), rng.randrange(cols), rng.choice(directions))

        if not samples:                           # 兜底：全量扫描
            for row in range(rows):
                for col in range(cols):
                    for direction in directions:
                        collect(row, col, direction)
        if not samples:
            return None

        if rng.random() < density:
            # 优先选「挡住别人最多」的位置；并列时在前几名里随机，保证布局多样
            samples.sort(key=lambda item: item[3], reverse=True)
            pool = samples[:3]
        else:
            pool = samples
        row, col, direction, _ = rng.choice(pool)

        placed[(row, col)] = direction
        placement.append((row, col, direction))

        # 更新 seen 表：这支箭头的射线覆盖到的格子 +1
        d_row, d_col = DIRECTIONS[direction]
        r, c = row + d_row, col + d_col
        while 0 <= r < rows and 0 <= c < cols:
            seen[r][c] += 1
            r += d_row
            c += d_col

    return {"placement": placement}


def removal_order(placement):
    """放置顺序的逆序就是一条合法通关顺序。"""
    return [(row, col) for row, col, _ in reversed(placement)]


# ------------------------------------------------------------------ 指标
def measure(rows, cols, placement):
    """模拟通关过程，统计难度指标。"""
    grid = {(row, col): direction for row, col, direction in placement}
    order = removal_order(placement)
    counts = []

    for row, col in order:
        # 统计此刻有多少箭头能飞出
        available = 0
        for (r, c), direction in grid.items():
            d_row, d_col = DIRECTIONS[direction]
            rr, cc = r + d_row, c + d_col
            blocked = False
            while 0 <= rr < rows and 0 <= cc < cols:
                if (rr, cc) in grid:
                    blocked = True
                    break
                rr += d_row
                cc += d_col
            if not blocked:
                available += 1
        counts.append(available)
        del grid[(row, col)]

    if grid:                                   # 理论上不会发生
        return None

    return {
        "free0": counts[0] if counts else 0,
        "avg": round(sum(counts) / len(counts), 2) if counts else 0.0,
        "peak": max(counts) if counts else 0,
        "counts": counts,
    }


def difficulty(rows, cols, placement, stats):
    """难度分：**越高越难**，用于候选排序。

    权重解释：
      * 箭头越多越难（+1.0 / 支）；
      * 棋盘越大越难（铺得开才藏得住）；
      * 开局能直接飞出的箭头越多越**简单**（-3.0 / 支，权重最大）；
      * 全程平均可选数越大越顺推、越简单（-1.5）；
      * 峰值可选数越大说明中途会出现「全都能点」的宽松时刻（-0.3）。
    """
    return (len(placement) * 1.0
            + (rows * cols) / 12.0
            - stats["free0"] * 3.0
            - stats["avg"] * 1.5
            - stats["peak"] * 0.3)


def spread(rows, cols, placement):
    """布局的「散开程度」：被用到的行数与列数占总数的比例。

    太小的（比如箭头全挤在一两行里）虽然也可解，但玩起来没有观察价值。
    """
    used_rows = len({row for row, _, _ in placement})
    used_cols = len({col for _, col, _ in placement})
    return used_rows / rows, used_cols / cols


def to_ascii(rows, cols, placement):
    grid = [["." for _ in range(cols)] for _ in range(rows)]
    for row, col, direction in placement:
        grid[row][col] = CHAR[direction]
    return tuple("".join(line) for line in grid)


# ------------------------------------------------------------------ 输出
def describe_placement(placement):
    name = {"up": "上", "down": "下", "left": "左", "right": "右"}
    return " ".join("(%d,%d)%s" % (row, col, name[direction])
                    for row, col, direction in placement)


def show(rows, cols, placement, stats, index, verbose=False):
    row_spread, col_spread = spread(rows, cols, placement)
    print("候选 %d   棋盘 %d×%d   箭头 %d 支   开局可点 %d   平均可选 %.2f   峰值 %d   铺开 %.0f%%/%.0f%%"
          % (index, rows, cols, len(placement), stats["free0"], stats["avg"], stats["peak"],
             row_spread * 100, col_spread * 100))
    for line in to_ascii(rows, cols, placement):
        print("    " + " ".join(line))
    print("    建议通关顺序：" + describe_placement(list(reversed(placement))))
    if verbose:
        print("    全程可选数变化：" + str(stats["counts"]))


def generate(rows, cols, count, keep, seed, attempts=900, density=0.85):
    """多次随机尝试，返回按难度分（越高越难）排序的前 keep 个候选。"""
    rng = random.Random(seed)
    results = []
    seen = set()

    for _ in range(attempts):
        data = place_reverse(rows, cols, count, rng, density=density)
        if data is None:
            continue
        placement = data["placement"]
        ascii_layout = to_ascii(rows, cols, placement)
        if ascii_layout in seen:               # 去掉重复布局
            continue
        seen.add(ascii_layout)

        stats = measure(rows, cols, placement)
        if stats is None:
            continue
        # 开局至少留一支能点的箭头，否则玩家一上手就是死局
        if stats["free0"] < 1:
            continue
        # 布局要铺得开，避免箭头全挤在一两行里
        row_spread, col_spread = spread(rows, cols, placement)
        if row_spread < 0.6 or col_spread < 0.6:
            continue

        results.append((difficulty(rows, cols, placement, stats), placement, stats))

    results.sort(key=lambda item: item[0], reverse=True)   # 最难的排前面
    return results[:keep]


PRESETS = [
    # (行, 列, 箭头数)  —— 递进的难度阶梯
    (5, 5, 6),
    (6, 6, 8),
    (6, 7, 10),
    (7, 7, 12),
    (7, 8, 14),
    (8, 8, 17),
    (8, 9, 19),
    (9, 9, 22),
    (9, 10, 24),
    (10, 10, 27),
    (10, 10, 30),
]


def main():
    parser = argparse.ArgumentParser(description="《一箭又一箭》关卡布局生成器")
    parser.add_argument("-r", "--rows", type=int, default=None)
    parser.add_argument("-c", "--cols", type=int, default=None)
    parser.add_argument("-n", "--count", type=int, default=None, help="箭头数量")
    parser.add_argument("-k", "--keep", type=int, default=3, help="输出前几个候选")
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--attempts", type=int, default=900, help="每个难度档位的随机尝试次数")
    parser.add_argument("--density", type=float, default=0.85,
                        help="制造阻挡的倾向，0=纯随机，1=总是优先挡住别人")
    parser.add_argument("--ascii", action="store_true", help="只输出 ASCII 布局，便于复制")
    args = parser.parse_args()

    if args.rows and args.cols and args.count:
        specs = [(args.rows, args.cols, args.count)]
    else:
        specs = PRESETS

    for spec_index, (rows, cols, count) in enumerate(specs, start=1):
        seed = args.seed + spec_index * 977
        results = generate(rows, cols, count, args.keep, seed,
                           attempts=args.attempts, density=args.density)
        print("=" * 78)
        print("难度档位 %d：%d×%d，目标 %d 支箭头（%d 个候选）"
              % (spec_index, rows, cols, count, len(results)))
        print("=" * 78)
        if not results:
            print("  没能在该尺寸下放下这么多箭头，请调小 -n 或放大 -r/-c。")
            continue
        for index, (_, placement, stats) in enumerate(results, start=1):
            if args.ascii:
                for line in to_ascii(rows, cols, placement):
                    print('            "%s",' % line)
                print()
            else:
                show(rows, cols, placement, stats, index)
                print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
