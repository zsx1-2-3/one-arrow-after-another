# -*- coding: utf-8 -*-
"""内部工具：按「目标开局可点数」从生成器候选里挑布局，直接打印 Level(...) 源码。

用法：python tools/_pick_levels.py
把输出粘进 game/levels.py 的 LEVELS 即可（挑完请再跑一次 verify_levels.py 复核）。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.board import solve_level  # noqa: E402
from tools.generate_levels import generate, to_ascii  # noqa: E402

# (行, 列, 箭头数, 关卡名, 提示语, 生命值, 目标开局可点数)
PICKS = [
    (7, 7, 18, "错位走廊", "顺着能飞的那一支点下去，会一路连锁", 4, 3),
    (8, 8, 24, "层叠封锁", "别急着点，先看谁的前方是空的", 3, 3),
    (8, 8, 30, "长蛇阵", "格子变挤了，横竖两个方向都要扫一遍", 3, 3),
    (9, 9, 35, "九宫迷阵", "只有几支箭头能直接飞出去，找到它们", 3, 4),
    (9, 9, 40, "十面埋伏", "空格没剩多少，别凭感觉乱点", 2, 4),
    (9, 9, 45, "铁壁合围", "满盘都是箭头，慢慢找空档", 2, 4),
    (9, 9, 50, "万箭归一", "全场塞了 50 支箭头，只有几支能先飞", 2, 5),
]

ATTEMPTS = 260


def pick(rows, cols, count, target_free, seed):
    """挑一个开局可点数最接近目标、同时难度分最高的候选。"""
    results = generate(rows, cols, count, keep=40, seed=seed, attempts=ATTEMPTS)
    best = None
    for _, placement, stats in results:
        gap = abs(stats["free0"] - target_free)
        # 优先贴近目标开局可点数，其次看难度分（列表本身已按难度降序）
        key = (gap,)
        if best is None or key < best[0]:
            best = (key, placement, stats)
    return best


def main():
    for index, (rows, cols, count, name, hint, hp, target) in enumerate(PICKS, start=1):
        result = pick(rows, cols, count, target, seed=20260921 + index * 977)
        print("# " + "-" * 70)
        if result is None:
            print("# %s：%d×%d 放不下 %d 支箭头" % (name, rows, cols, count))
            continue
        _, placement, stats = result
        # 复核：必须可解，且布局合法
        order = solve_level(rows, cols, placement)
        assert order is not None, "%s 竟然无解" % name
        print("# %s   棋盘 %d×%d   箭头 %d   密度 %.2f   开局可点 %d   平均可选 %s"
              % (name, rows, cols, count, count / float(rows * cols),
                 stats["free0"], stats["avg"]))
        print("    Level(")
        print('        name="%s",' % name)
        print('        hint="%s",' % hint)
        print("        max_hp=%d," % hp)
        print("        layout=(")
        for line in to_ascii(rows, cols, placement):
            print('            "%s",' % line)
        print("        ),")
        print("    ),")
        print()
    return 0


if __name__ == "__main__":
    sys.exit(main())
