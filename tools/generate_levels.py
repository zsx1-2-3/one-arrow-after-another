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
    density 箭头数 ÷ 格子数（同一尺寸下密度越高，需要扫视的箭头越多）

**为什么难度不能只靠放大棋盘**：棋盘放大到 10×10 之后，能点的箭头也跟着变多，
反而是靠「密度」——同样的棋盘里塞进更多箭头——才继续变难。但要注意一个陷阱：

    贴着棋盘边缘、朝向棋盘外的箭头，射线长度是 0，永远能飞出去。

如果不管它，密度一高，剩下的合法放置位置几乎只剩这类箭头，布局会退化成
「一大半箭头开局就能点」的松局面（实测 9×9 放 54 支时开局可点 18 支，比稀疏时还简单）。
所以放置时**除最后一步外一律避开射线为空的候选**，并用
`seen × w_block + raylen × w_ray` 打分：既看「能挡住多少已放置的箭头」，
也看「自己射线有多长」——射线越长，将来能被后续放置的箭头挡住的空间就越大。
这样一来 9×9 放 50 支（密度 0.62）仍能把开局可点数压在 5 支左右。

用法：
    python tools/generate_levels.py                     # 打印预设难度的候选
    python tools/generate_levels.py -r 8 -c 8 -n 30 -k 5 --seed 2026
    python tools/generate_levels.py --ascii -r 7 -c 7 -n 18 -k 1

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
def place_reverse(rows, cols, count, rng, bias=0.9, w_block=1.0, w_ray=3.0,
                  forbid_empty_ray=True):
    """逆向放置 count 支箭头，返回 {'placement': [(r, c, dir), ...]}。

    placement[0] 是最后被消掉的箭头，placement[-1] 是开局第一个应该被点掉的箭头。
    返回 None 表示在给定尺寸下放不下这么多箭头。

    bias：有多大概率走「挑最优候选」的路子；剩下的小概率纯随机，保证布局多样。
    w_block / w_ray：候选打分权重（挡住别人的价值 / 自己射线长度的价值）。
    forbid_empty_ray：是否避开射线为空的候选（见文件开头的说明），
        这类箭头贴着边朝外、永远能飞，是「高密度反而变简单」的元凶。

    实现要点：维护一张 seen 表——seen[r][c] 记录「有多少支已放置的箭头正前方会经过
    这个格子」，放置箭头时沿它的射线加一。这样判断某格会不会挡住别人就是 O(1)，
    不需要每次重新扫描全盘。
    """
    placed = {}                                   # (row, col) -> direction
    seen = [[0] * cols for _ in range(rows)]      # 被多少支箭头的射线覆盖
    placement = []
    directions = list(DIRECTIONS)

    for step in range(count):
        samples = []

        def collect(row, col, direction):
            """若合法就收集起来（含射线长度）。"""
            if (row, col) in placed:
                return
            d_row, d_col = DIRECTIONS[direction]
            r, c = row + d_row, col + d_col
            raylen = 0
            while 0 <= r < rows and 0 <= c < cols:
                if (r, c) in placed:              # 正前方有已放置的箭头 -> 不合法
                    return
                raylen += 1
                r += d_row
                c += d_col
            samples.append((row, col, direction, raylen))

        for _ in range(80):                       # 随机采样
            collect(rng.randrange(rows), rng.randrange(cols), rng.choice(directions))

        if not samples:                           # 兜底：全量扫描
            for row in range(rows):
                for col in range(cols):
                    for direction in directions:
                        collect(row, col, direction)
        if not samples:
            return None

        # 射线为空的候选除最后一步外一律避开（见文件开头「为什么难度不能只靠放大棋盘」）
        if forbid_empty_ray and step < count - 1:
            non_empty = [item for item in samples if item[3] > 0]
            if non_empty:
                samples = non_empty

        if rng.random() < bias:
            # 优先选「挡住别人多 + 自己射线长」的位置；并列时在前几名里随机，保证布局多样
            samples.sort(key=lambda item: seen[item[0]][item[1]] * w_block
                         + item[3] * w_ray, reverse=True)
            pool = samples[:4]
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
      * 密度越高越难（+30.0 / 单位密度）—— 同一块棋盘里塞得越满，
        需要逐条扫视的射线越多，容错空间越小；
      * 开局能直接飞出的箭头越多越**简单**（-3.0 / 支，权重最大）；
      * 全程平均可选数越大越顺推、越简单（-1.5）；
      * 峰值可选数越大说明中途会出现「全都能点」的宽松时刻（-0.3）。
    """
    density = len(placement) / float(rows * cols)
    return (len(placement) * 1.0
            + density * 30.0
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
    print("候选 %d   棋盘 %d×%d   箭头 %d 支   密度 %.2f   开局可点 %d   平均可选 %.2f   峰值 %d   铺开 %.0f%%/%.0f%%"
          % (index, rows, cols, len(placement), len(placement) / float(rows * cols),
             stats["free0"], stats["avg"], stats["peak"],
             row_spread * 100, col_spread * 100))
    for line in to_ascii(rows, cols, placement):
        print("    " + " ".join(line))
    print("    建议通关顺序：" + describe_placement(list(reversed(placement))))
    if verbose:
        print("    全程可选数变化：" + str(stats["counts"]))


def generate(rows, cols, count, keep, seed, attempts=900, bias=0.9,
             w_block=1.0, w_ray=3.0, forbid_empty_ray=True):
    """多次随机尝试，返回按难度分（越高越难）排序的前 keep 个候选。"""
    rng = random.Random(seed)
    results = []
    seen = set()

    for _ in range(attempts):
        data = place_reverse(rows, cols, count, rng, bias=bias,
                             w_block=w_block, w_ray=w_ray,
                             forbid_empty_ray=forbid_empty_ray)
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
    # (行, 列, 箭头数) —— 棋盘尺寸很快封顶（最多 9×9），难度主要靠**密度**往上走
    # 括号里是密度 = 箭头数 ÷ 格子数
    (5, 5, 6),        # 0.24
    (6, 6, 9),        # 0.25
    (6, 7, 12),       # 0.29
    (7, 7, 15),       # 0.31
    (7, 7, 18),       # 0.37
    (8, 8, 24),       # 0.38
    (8, 8, 30),       # 0.47
    (9, 9, 35),       # 0.43
    (9, 9, 40),       # 0.49
    (9, 9, 45),       # 0.56
    (9, 9, 50),       # 0.62
]


def main():
    parser = argparse.ArgumentParser(description="《一箭又一箭》关卡布局生成器")
    parser.add_argument("-r", "--rows", type=int, default=None)
    parser.add_argument("-c", "--cols", type=int, default=None)
    parser.add_argument("-n", "--count", type=int, default=None, help="箭头数量")
    parser.add_argument("-k", "--keep", type=int, default=3, help="输出前几个候选")
    parser.add_argument("--seed", type=int, default=20260921)
    parser.add_argument("--attempts", type=int, default=900, help="每个难度档位的随机尝试次数")
    parser.add_argument("--bias", type=float, default=0.9,
                        help="走「挑最优候选」的概率，0=纯随机，1=总是挑最优")
    parser.add_argument("--w-block", type=float, default=1.0,
                        help="候选打分里「挡住别人」的权重")
    parser.add_argument("--w-ray", type=float, default=3.0,
                        help="候选打分里「自己射线长度」的权重")
    parser.add_argument("--allow-empty-ray", action="store_true",
                        help="允许放置射线为空的箭头（默认禁止，见文件开头说明）")
    parser.add_argument("--ascii", action="store_true", help="只输出 ASCII 布局，便于复制")
    args = parser.parse_args()

    if args.rows and args.cols and args.count:
        specs = [(args.rows, args.cols, args.count)]
    else:
        specs = PRESETS

    for spec_index, (rows, cols, count) in enumerate(specs, start=1):
        seed = args.seed + spec_index * 977
        results = generate(rows, cols, count, args.keep, seed,
                           attempts=args.attempts, bias=args.bias,
                           w_block=args.w_block, w_ray=args.w_ray,
                           forbid_empty_ray=not args.allow_empty_ray)
        print("=" * 78)
        print("难度档位 %d：%d×%d，目标 %d 支箭头（密度 %.2f，%d 个候选）"
              % (spec_index, rows, cols, count, count / float(rows * cols), len(results)))
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
