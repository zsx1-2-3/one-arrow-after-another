# -*- coding: utf-8 -*-
"""选关：从生成器的候选里，按「尺寸 + 目标开局可点数」挑出九个正式关卡，
并把 levels.py 里可以直接粘贴的布局数据打印出来。

挑选准则（三条，缺一不可）
--------------------------
1. 必须通过 pieces.validate_layout 与求解器复核；
2. 铺满率尽量高——画面要够「满」，接近参照画面那种密密麻麻的感觉；
3. 开局可点数**尽量贴近该关的目标值**，且不得超过：这是唯一真正影响手感的
   指标（可点数越少，越要在开局仔细扫射线）。

第二步和第三步会打架：铺得最满的那一版往往开局也好点。所以排序的主键是
「可点数是否正好等于目标」，其次才是铺满率。

用法
----
    python tools/pick_levels.py                # 布局源码打到 stdout，剪进 levels.py
    python tools/pick_levels.py --seeds 40     # 多试几个种子（更慢，但更容易挑到）

挑选报告（铺满率 / 可点数 / 用的哪个种子）走 stderr，不混进可粘贴的源码里。

注意：这是**当初挑关卡那套准则的固化**，不是一份「按下就能还原出同一批数据」
的脚本——搜索是按种子走的，重跑挑到的可能是另一个同样合格的候选。
所以挑完务必再跑一遍 tools/verify_levels.py 复核。
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from game.board import count_free_pieces, solve_level            # noqa: E402
import generate_levels as G                                       # noqa: E402

# (行, 列, 箭头数, 关卡名, 提示语, 目标开局可点数, 单支最长格数)
# 尺寸一律取竖着的（行 > 列）：游戏按手机竖屏比例做，竖长方形的棋盘才填得满视口。
#
# max_len 给到「平均单支长度（格数×0.93÷箭头数）」的两倍上下：生成器会给
# 每支箭抽一个围绕平均值大散开的目标长度，上限太紧会把长的那截压平、
# 长短差距出不来。上限也不给太大——超过平均的三倍后，长箭很难在
# 半满的盘上找到整条通路，白烧时间。目标长度本身由 generate_levels.py 抽。
PICKS = [
    (11, 8, 21, "初次拉弓", "点朝外的那几支，先开出一条路", 7, 8),
    (13, 9, 23, "交叉路口", "开局能点的很少，先找朝外的", 6, 9),
    (14, 10, 22, "连锁反应", "消掉一支，往往就有新的一支能走了", 5, 11),
    (16, 11, 27, "四面楚歌", "上下左右都要扫一遍", 5, 12),
    (18, 12, 28, "错位走廊", "箭头更长，先看清它朝哪边", 4, 13),
    (20, 14, 37, "纵横交错", "别只盯着中间，边角往往藏着出口", 4, 13),
    (22, 15, 38, "长蛇阵", "一支挨着一支，顺序想好再点", 3, 15),
    (23, 17, 43, "十面埋伏", "开局只有两三支能动，慢慢找", 3, 16),
    (26, 18, 46, "万箭归一", "全场只剩几个出口，每一步都要算", 3, 18),
]


def evaluate(rows, cols, count, pieces):
    """校验一个候选；不合格返回 None，合格返回它的开局可点数。

    硬性淘汰线有四条：支数比目标少四支以上（画面明显填不满）、
    铺满率低于 0.91（tests 里「密密麻麻」那条用例卡 0.90，留点余量）、
    布局不合法、无解。「可点数」不在这里卡——那要跟目标值比，
    交给 pick 排序，因为「比目标还好点」和「差一点没到目标」两种情况
    的处理不一样。
    """
    if len(pieces) < count - 4:            # 支数差太多，画面会显得空
        return None
    if G.fill_ratio(rows, cols, pieces) < 0.91:
        return None
    if G.validate_layout_quiet(rows, cols, pieces) is not None:
        return None
    if solve_level(rows, cols, pieces) is None:
        return None
    return count_free_pieces(rows, cols, pieces)


def length_spread(pieces):
    """箭长的标准差——长短差距的量化。等长盘是 0，差距越大越好。"""
    lens = [len(p.cells) for p in pieces]
    mean = sum(lens) / float(len(lens))
    return (sum((n - mean) ** 2 for n in lens) / len(lens)) ** 0.5


def pick(spec, seeds, index=0, slack=1):
    """在若干种子上跑生成器，返回最好的那一个候选。

    排序的主键是「**这一版够不够难**」：首先看可点数有没有超出目标太多
    （超了就是太简单，只能当兜底），然后看有没有正好命中目标；
    再往后是**箭长的标准差**——满盘等长的箭看着像尺子铺出来的，
    长短差距本身就是观感的一部分，所以它排在铺满率前面。

    slack 是兜底余量：大盘面上出口天然更多，偶尔找不到刚好达标的，
    允许退让 slack 个。真退让了会在报告里标出来，不会悄悄放水。
    """
    rows, cols, count, _name, _hint, target, max_len = spec
    mean_len = rows * cols / float(count)     # 平均单支长度（铺满率的倒推基准）
    best = None
    for seed in seeds:
        pieces = G.generate(rows, cols, seed=seed, max_len=max_len,
                            max_pieces=count, mean_len=mean_len)
        if not pieces:
            continue
        free = evaluate(rows, cols, count, pieces)
        if free is None:
            continue
        # 第一列：达标（没超出目标 + slack）。不达标的只在实在挑不出时兜底用。
        # 之后依次比：有没有正好命中目标 -> 离目标差多少 -> 长短差距 -> 铺满率。
        # 「离目标差多少」排在观感指标前面是有意的：目标可点数是**手感**指标，
        # 铺满率和长度差只是画面观感，冲突时先保手感。
        score = (free <= target + slack, free == target, -abs(free - target),
                 length_spread(pieces), G.fill_ratio(rows, cols, pieces),
                 len(pieces))
        if best is None or score > best[0]:
            best = (score, seed, pieces, free)
    if best is None:
        raise SystemExit("第 %d 关（%s）在 %d 个种子里没挑到合法且可解的候选，"
                         "把 --seeds 调大再试" % (index, spec[3], len(seeds)))
    return best


def emit(index, spec, best):
    """把挑中的布局打印成 levels.py 里能直接粘贴的 Level(...) 源码。"""
    rows, cols, _count, name, hint, _target, _max_len = spec
    score, seed, pieces, free = best
    lens = sorted(len(p.cells) for p in pieces)
    print("    # 第 %d 关：%d×%d，%d 支，开局可点 %d，铺满率 %.2f，"
          "箭长 %d~%d（seed=%d）"
          % (index, rows, cols, len(pieces), free, score[4],
             lens[0], lens[-1], seed))
    print("    Level(")
    print('        name="%s",' % name)
    print('        hint="%s",' % hint)
    print("        rows=%d," % rows)
    print("        cols=%d," % cols)
    print("        specs=(")
    print(G.dump(pieces))
    print("        ),")
    print("    ),")


def main():
    parser = argparse.ArgumentParser(description="《一箭又一箭》选关")
    parser.add_argument("--seeds", type=int, default=16,
                        help="每个关卡试多少个种子（默认 16，越大越慢也越容易挑到）")
    parser.add_argument("--slack", type=int, default=1,
                        help="开局可点数允许比目标多几个（兜底余量，默认 1）")
    args = parser.parse_args()

    seeds = range(args.seeds)
    picked = []
    for index, spec in enumerate(PICKS, start=1):
        best = pick(spec, seeds, index, slack=args.slack)
        picked.append((index, spec, best))
        score, seed, pieces, free = best
        target = spec[5]
        mark = "" if score[0] else "  [没达标，已取最难的候选]"
        print("第 %d 关 %-5s %2d×%-2d  %2d 支  铺满率 %.3f  长短差 σ=%.2f  "
              "开局可点 %d（目标 %d）  seed=%d%s"
              % (index, spec[3], spec[0], spec[1], len(pieces),
                 score[4], score[3], free, target, seed, mark),
              file=sys.stderr)

    print("LEVELS = (", file=sys.stdout)
    for index, spec, best in picked:
        emit(index, spec, best)
    print(")", file=sys.stdout)
    print("", file=sys.stderr)
    print("把上面这段贴进 game/levels.py 的 LEVELS，然后跑 tools/verify_levels.py 复核。",
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
