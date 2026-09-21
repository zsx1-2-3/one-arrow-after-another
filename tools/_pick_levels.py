# -*- coding: utf-8 -*-
"""内部小工具：从生成器的候选里按「档位 + 候选序号」挑出关卡布局，
输出成可以直接粘进 game/levels.py 的 Python 代码，顺便用求解器复核一遍。

这样做的目的：手抄 10×10 的布局极易出错，让程序输出就能保证布局与
生成器验证过的完全一致。

用法：python tools/_pick_levels.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.board import count_free_arrows, solve_level  # noqa: E402
from tools.generate_levels import PRESETS, generate, measure, to_ascii  # noqa: E402

SEED = 20260921
ATTEMPTS = 1500
DENSITY = 0.95

# 选中的关卡：(档位下标从 1 开始, 候选序号从 1 开始, 关卡名, 提示, 失误上限)
PICKS = [
    (5, 1, "错位走廊", "顺着能飞的那一支点下去，会一路连锁", 3),
    (6, 1, "层叠封锁", "别急着点，先看谁的前方是空的", 3),
    (7, 1, "长蛇阵", "棋盘变大之后，横竖两个方向都要扫一遍", 3),
    (8, 1, "九宫迷阵", "只有四支箭头能直接飞出去，找到它们", 2),
    (9, 1, "十面埋伏", "开局可点的箭头变多了，但别急着点错", 2),
    (10, 1, "铁壁合围", "大棋盘上找空档，耐心一点", 2),
    (11, 1, "万箭归一", "全场只有七支能先飞，想清楚再落手", 2),
]


def main():
    for spec_index, pick_index, name, hint, mistakes in PICKS:
        rows, cols, count = PRESETS[spec_index - 1]
        seed = SEED + spec_index * 977
        results = generate(rows, cols, count, max(pick_index, 2), seed,
                           attempts=ATTEMPTS, density=DENSITY)
        if len(results) < pick_index:
            print("# 档位 %d 只有 %d 个候选，取第 1 个" % (spec_index, len(results)))
        _, placement, stats = results[pick_index - 1]
        layout = to_ascii(rows, cols, placement)

        # 复核：求解器必须能通关，且指标一致
        # 从 ASCII 字符反解方向，避免自己再维护一份方向字典写错
        char_to_dir = {"^": "up", "v": "down", "<": "left", ">": "right"}
        arrows = []
        for row, line in enumerate(layout):
            for col, char in enumerate(line):
                if char != ".":
                    arrows.append((row, col, char_to_dir[char]))

        order = solve_level(rows, cols, arrows)
        free = count_free_arrows(rows, cols, arrows)
        stats2 = measure(rows, cols, placement)

        assert order is not None, "档位 %d 的候选无解！" % spec_index
        assert len(order) == count, "档位 %d 箭头数不对" % spec_index
        assert free == stats["free0"] == stats2["free0"], \
            "档位 %d 开局可点数不一致：%d / %d / %d" % (spec_index, free, stats["free0"], stats2["free0"])

        print("# ---------------- 档位 %d：%d×%d，%d 支箭头，开局可点 %d，"
              "平均可选 %.2f" % (spec_index, rows, cols, len(arrows), free, stats["avg"]))
        print("    Level(")
        print("        name=%r," % name)
        print("        hint=%r," % hint)
        print("        max_mistakes=%d," % mistakes)
        print("        layout=(")
        for line in layout:
            print('            "%s",' % line)
        print("        ),")
        print("    ),")
        print("#     参考通关顺序：" + " ".join("(%d,%d)" % cell for cell in order))
        print()


if __name__ == "__main__":
    main()
