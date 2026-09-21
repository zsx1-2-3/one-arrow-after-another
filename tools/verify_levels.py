# -*- coding: utf-8 -*-
"""关卡校验脚本：检查所有关卡是否合法、是否可解，并给出参考通关顺序。

用法：
    python tools/verify_levels.py             # 打印可读报告
    python tools/verify_levels.py --markdown  # 输出 Markdown 表格（写博客/报告用）

退出码：0 = 全部关卡都能通关；1 = 存在无解或非法关卡。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.board import DIRECTIONS  # noqa: E402
from game.levels import LEVELS, validate_levels  # noqa: E402

DIR_NAME = {"up": "上", "down": "下", "left": "左", "right": "右"}


def describe(level, order):
    """把坐标序列翻译成「第几行第几列 朝某方向」的可读文本。"""
    mapping = {(row, col): direction for row, col, direction in level.arrows}
    parts = []
    for row, col in order:
        parts.append("(%d,%d)%s" % (row, col, DIR_NAME[mapping[(row, col)]]))
    return " -> ".join(parts)


def main():
    parser = argparse.ArgumentParser(description="《一箭又一箭》关卡可解性校验")
    parser.add_argument("--markdown", action="store_true", help="以 Markdown 表格输出")
    args = parser.parse_args()

    report = validate_levels()

    if args.markdown:
        print("| 关卡 | 名称 | 棋盘 | 箭头数 | 密度 | 开局可点 | 难度 | 生命值 | 本关满分 | 是否可解 |")
        print("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for item in report:
            print(
                "| 第%d关 | %s | %s | %d | %.2f | %d | %s | %d 颗 | %d | %s |"
                % (
                    item["index"],
                    item["name"],
                    item["size"],
                    item["arrows"],
                    item["density"],
                    item["free"],
                    "★" * item["stars"],
                    item["max_hp"],
                    item["max_score"],
                    "是" if item["solvable"] else "**否**",
                )
            )
    else:
        print("=" * 78)
        print("《一箭又一箭》关卡校验报告")
        print("=" * 78)
        for level, item in zip(LEVELS, report):
            print()
            # 关卡名本身就叫「教学关」时不再重复标注，免得印成「教学关（教学关）」
            tag = "（教学关）" if item["tutorial"] and level.name != "教学关" else ""
            print("第 %2d 关  %s%s   棋盘 %s   箭头 %2d 支   密度 %.2f   开局可点 %d 支"
                  % (item["index"], level.name, tag, item["size"], item["arrows"],
                     item["density"], item["free"]))
            print("         难度 %s   生命值 %d 颗（容错随难度递增）   本关满分 %d 分"
                  % ("★" * item["stars"], item["max_hp"], item["max_score"]))
            print("-" * 78)
            for row, line in enumerate(level.layout):
                print("   %d | %s" % (row, " ".join(line)))
            print("-" * 78)
            if item["solvable"]:
                print("   [OK] 可解，共 %d 步" % len(item["order"]))
                print("   参考顺序：" + describe(level, item["order"]))
            else:
                print("   [FAIL] 无解！存在互相阻挡的死循环，请调整布局。")

    bad = [item for item in report if not item["solvable"]]
    print()
    if bad:
        print("校验结果：%d 个关卡存在问题 %s" % (len(bad), [b["name"] for b in bad]))
        return 1
    print("校验结果：全部 %d 个关卡均可正常通关。" % len(report))
    if not args.markdown:
        print("难度参考：棋盘尺寸到第 8 关就封顶在 9×9，之后靠密度继续加难——")
        print("          同样的格子里箭头越多，需要逐条扫视的射线就越多；")
        print("          开局可点的箭头越少，越要在开局仔细找出口。")
        print("生命值参考：按难度星级给，第 1 关 4 颗心、最后一关 7 颗心。")
        print("            关卡越难容错越高，一次手滑不至于被打回原点。")
        print("得分参考：本关得分 = 星级×250 × 剩余生命值 ÷ 生命值上限，")
        print("          一颗心都没丢再 +20%；所有关卡满分合计 %d 分。"
              % sum(item["max_score"] for item in report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
