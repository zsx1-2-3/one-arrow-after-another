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
        print("| 关卡 | 名称 | 棋盘 | 箭头数 | 开局可点 | 失误上限 | 是否可解 |")
        print("| --- | --- | --- | --- | --- | --- | --- |")
        for item in report:
            print(
                "| 第%d关 | %s | %s | %d | %d | %d | %s |"
                % (
                    item["index"],
                    item["name"],
                    item["size"],
                    item["arrows"],
                    item["free"],
                    item["max_mistakes"],
                    "是" if item["solvable"] else "**否**",
                )
            )
    else:
        print("=" * 68)
        print("《一箭又一箭》关卡校验报告")
        print("=" * 68)
        for level, item in zip(LEVELS, report):
            print()
            print("第 %d 关  %s   棋盘 %s   箭头 %d 支   开局可点 %d 支   失误上限 %d"
                  % (item["index"], level.name, item["size"], item["arrows"],
                     item["free"], item["max_mistakes"]))
            print("-" * 68)
            for row, line in enumerate(level.layout):
                pretty = " ".join(line)
                print("   %d | %s" % (row, pretty))
            print("-" * 68)
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
