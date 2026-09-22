# -*- coding: utf-8 -*-
"""关卡校验脚本：检查所有关卡是否合法、是否可解，并给出参考通关顺序。

用法：
    python tools/verify_levels.py             # 打印可读报告
    python tools/verify_levels.py --markdown  # 输出 Markdown 表格（写博客/报告用）

退出码：0 = 全部关卡都能通关；1 = 存在无解或非法关卡。

它是**第二道保险**：生成器保证「逆向构造出来的布局必然可解」，import 关卡时
pieces.validate_layout 又把形状问题挡了一道，但这两道都在理论上，
所以这里再老老实实跑一遍求解器 —— 布局对不对，点一遍最清楚。

棋盘画成 ASCII：``.`` 是空格，``o`` 是管道身子，``^ v < >`` 是箭头那一格。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.levels import (LEVELS, TUTORIAL, validate_levels,  # noqa: E402
                         validate_tutorial)
from game.pieces import CHAR_DIRS  # noqa: E402

DIR_NAME = {"up": "上", "down": "下", "left": "左", "right": "右"}


def ascii_map(level):
    """把关卡画成 ASCII 图：. 空格 / o 管道身子 / ^v<> 箭头。

    箭头那一格优先于身子，所以头尾重合时看到的是箭头 —— 这正是玩家看到的。
    """
    rows = [["."] * level.cols for _ in range(level.rows)]
    for piece in level.pieces:
        for row, col in piece.cells:
            rows[row][col] = "o"
    for piece in level.pieces:
        row, col = piece.head
        rows[row][col] = CHAR_DIRS[piece.direction]
    return ["".join(line) for line in rows]


def describe(level, order):
    """把通关顺序翻译成「(第几行,第几列)朝某方向」的可读文本。

    order 里是一支支 Piece（不是坐标）：管道占好几格，只说坐标说明不了是谁，
    所以报的是**箭头那一格 + 箭头方向**。
    """
    parts = []
    for piece in order:
        row, col = piece.head
        parts.append("(%d,%d)%s" % (row, col, DIR_NAME[piece.direction]))
    return " -> ".join(parts)


def print_level(level, item, index_label):
    """把一关的棋盘与结论打印出来（教学关和编号关卡共用）。"""
    print("%s   棋盘 %s   管道 %2d 支   密度 %.2f   开局可点 %d 支"
          % (index_label, item["size"], item["arrows"], item["density"], item["free"]))
    print("         难度 %s   生命值 %d 颗   本关满分 %s"
          % ("★" * item["stars"], item["max_hp"],
             "不计分" if item["tutorial"] else "%d 分" % item["max_score"]))
    print("-" * 78)
    for row, line in enumerate(ascii_map(level)):
        print("   %2d | %s" % (row, line))
    print("-" * 78)
    if item["solvable"]:
        print("   [OK] 可解，共 %d 步" % len(item["order"]))
        print("   参考顺序：" + describe(level, item["order"]))
    else:
        print("   [FAIL] 无解！存在互相阻挡的死循环，请调整布局。")


def markdown_table(items):
    """按 Markdown 表格打印汇总。"""
    print("| 关卡 | 名称 | 棋盘 | 管道数 | 铺满率 | 开局可点 | 难度 | 生命值 | 本关满分 | 是否可解 |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for item in items:
        label = "教学关（独立入口）" if item["tutorial"] else "第%d关" % item["index"]
        score = "不计分" if item["tutorial"] else "%d" % item["max_score"]
        print(
            "| %s | %s | %s | %d | %.2f | %d | %s | %d 颗 | %s | %s |"
            % (
                label,
                item["name"],
                item["size"],
                item["arrows"],
                item["density"],
                item["free"],
                "★" * item["stars"],
                item["max_hp"],
                score,
                "是" if item["solvable"] else "**否**",
            )
        )


def main():
    parser = argparse.ArgumentParser(description="《一箭又一箭》关卡可解性校验")
    parser.add_argument("--markdown", action="store_true", help="以 Markdown 表格输出")
    args = parser.parse_args()

    tutorial = validate_tutorial()
    report = validate_levels()

    if args.markdown:
        markdown_table([tutorial] + report)
    else:
        print("=" * 78)
        print("《一箭又一箭》关卡校验报告")
        print("=" * 78)

        # 教学关单独排在最前面：它不占关卡编号，也不参与计分
        print()
        print("教学关（主菜单独立入口：不计分、不占关卡编号、不用解锁）")
        print_level(TUTORIAL, tutorial, "          ")
        if tutorial["solvable"]:
            print("   引导步骤：%d 步（点哪里、为什么，都在关卡里的高亮环上）"
                  % len(TUTORIAL.steps))

        for level, item in zip(LEVELS, report):
            print()
            print_level(level, item, "第 %2d 关  %s" % (item["index"], level.name))

    all_items = [tutorial] + report
    bad = [item for item in all_items if not item["solvable"]]
    print()
    if bad:
        print("校验结果：%d 个关卡存在问题 %s" % (len(bad), [b["name"] for b in bad]))
        return 1
    print("校验结果：教学关 + 全部 %d 个编号关卡均可正常通关。" % len(report))
    if not args.markdown:
        # 封顶关号从关卡数据里现算，不写死——插关删关的时候这种数字最容易过期，
        # 而且过期了也不会报错，只会静静地印一句错的说明（之前就写过「第 7 关」）。
        sizes = [max(level.rows, level.cols) for level in LEVELS]
        max_side = max(sizes)
        frozen = sizes.index(max_side) + 1
        long_side = [level.rows for level in LEVELS]      # 竖屏棋盘取行数当长边
        print("难度参考：棋盘尺寸逐关放大，第 %d 关到 %d×%d 就封顶，"
              % (frozen, long_side[frozen - 1], LEVELS[frozen - 1].cols))
        print("          之后同样的格子里塞进更多管道，靠铺满率继续加难；")
        print("          开局可点的管道越少，越要在开局仔细扫射线。")
        print("生命值参考：按难度星级给，第 1 关 4 颗心、最后一关 7 颗心。")
        print("            关卡越难容错越高，一次手滑不至于被打回原点。")
        print("            教学关不参与计分，单独给 %d 颗心，是个随便点的沙盒。"
              % tutorial["max_hp"])
        # 注意百分号要写成 %%：这一行同时在做 % 格式化，
        # 直接写「+20%」会被当成格式符，脚本会在最后一行抛 ValueError。
        print("得分参考：本关得分 = 星级×250 × 剩余生命值 ÷ 生命值上限，")
        print("          一颗心都没丢再 +20%%；第 1~%d 关满分合计 %d 分。"
              % (len(report), sum(item["max_score"] for item in report)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
