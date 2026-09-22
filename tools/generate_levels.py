# -*- coding: utf-8 -*-
"""关卡生成器：批量产出「密集铺满 + 必然可解」的箭头箭布局。

核心思路是**逆向构造**：把「消除顺序」倒过来当「放置顺序」。

* 放置第 i 支箭时，要求它箭头前方的射线上**没有已经放好的箭**；
* 于是「放置顺序的倒序」天然是一条合法的通关顺序 —— 布局必然可解，
  连事后筛选都不需要（当然事后还是要跑一遍求解器复核）。

判据为什么成立：某支箭被消掉时，盘上还在的箭就是「在它之后才被消掉的」，
也就是逆向构造时「比它先放好的」。所以只要放置时避开这些箭，顺序就成立。

另一条硬约束：**每支箭最后一段必须沿箭头方向**，否则画出来箭头会歪在拐角上
（见 pieces.validate_layout）。

形状（2026-09-22 第三版）：除了直条和 L 形，还支持两类**蛇形箭**——

* ``C`` 形：两个以上**同号**拐弯（像字母 C / U，箭头回折半圈）；
* ``S`` 形：三个以上**交替**拐弯（像字母 S / 5，蛇形蜿蜒）。

由 generate 的 curve_prob / s_share 控制掺入比例：每支箭开工前先抽形状，
抽中 C/S 的箭在 grow_backward 里按「下一个拐弯该同号还是反号」加权，
place_one 再按形状达成度加分——没弯够数就罚，弯对了就奖。
这两类箭占格多、射线关系绕，是后期关卡难度的主力来源。
"""

import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from game.board import count_free_pieces, solve_level          # noqa: E402
from game.pieces import (CHAR_DIRS, DIRECTIONS, Piece,         # noqa: E402
                         format_piece, ray_cells, validate_layout)

# 方向取反 / 取垂直，用于「从箭头往回长」
OPPOSITE = {name: (-d_row, -d_col) for name, (d_row, d_col) in DIRECTIONS.items()}
PERPENDICULAR = {
    "up": ["left", "right"], "down": ["left", "right"],
    "left": ["up", "down"], "right": ["up", "down"],
}


def ray_clear(grid, head, direction, rows, cols):
    """从 head 沿 direction 看出去，射线上是否一格都没有。"""
    d_row, d_col = DIRECTIONS[direction]
    row, col = head[0] + d_row, head[1] + d_col
    while 0 <= row < rows and 0 <= col < cols:
        if grid[row][col] != -1:
            return False
        row += d_row
        col += d_col
    return True


def empty_neighbours(grid, row, col, rows, cols):
    """四邻里还有几个空格（越少说明这个位置越「憋」，应当优先填掉）。"""
    count = 0
    for d_row, d_col in DIRECTIONS.values():
        r, c = row + d_row, col + d_col
        if 0 <= r < rows and 0 <= c < cols and grid[r][c] == -1:
            count += 1
    return count


def _turn_signs(cells):
    """路径每个拐弯的旋转符号（网格坐标系下的叉积，±1）。

    直行不记；连续拐弯按出现顺序排列。C 形 = 全同号，S 形 = 全交替，
    见 shape_kind。
    """
    signs = []
    heading = None
    for prev, cur in zip(cells, cells[1:]):
        delta = (cur[0] - prev[0], cur[1] - prev[1])
        if heading is not None and delta != heading:
            cross = heading[0] * delta[1] - heading[1] * delta[0]
            signs.append(1 if cross > 0 else -1)
        heading = delta
    return signs


def shape_kind(cells):
    """返回路径形状：'C'（≥2 个同号拐弯）、'S'（≥3 个交替拐弯）或 None。"""
    signs = _turn_signs(cells)
    if len(signs) >= 2 and all(sign == signs[0] for sign in signs):
        return "C"
    if len(signs) >= 3 and all(cur == -prev for prev, cur in zip(signs, signs[1:])):
        return "S"
    return None


# C/S 形的打分：弯够数 +40 一档（多弯一个 +8），只有一两弯给安慰分。
# 数值要压过「长度偏差 × 12」一两格的代价——不然生成器宁可放弃形状
# 也要贴目标长度，curve_prob 就名存实亡了。
SHAPE_BONUS = 40.0
SHAPE_EXTRA_BEND = 8.0
SHAPE_NEAR_MISS = 8.0


def shape_bonus(cells, curve):
    """一支候选路径对目标形状（'C'/'S'）的达成加分。"""
    signs = _turn_signs(cells)
    kind = shape_kind(cells)
    if kind == curve:
        return SHAPE_BONUS + SHAPE_EXTRA_BEND * (len(signs) - (2 if curve == "C" else 3))
    if kind is not None:
        # 要 C 来了个 S（或反之）也算半个蛇形，安慰分给足弯数
        return SHAPE_NEAR_MISS + 0.5 * SHAPE_EXTRA_BEND * len(signs)
    if signs:
        return SHAPE_NEAR_MISS * 0.5
    return 0.0


def grow_backward(grid, head, direction, rows, cols, rng, max_len, straight_bias=0.62,
                  curve=None, curve_boost=6.0):
    """从箭头位置往回长出一条路径，返回 tail -> head 顺序的格子元组。

    第一步必须沿 -direction，保证「最后一段和箭头方向一致」。
    之后可以在「继续直行」和「转向」里随机挑，直行概率高一点，
    这样出来的形状以长条 + 少量拐弯为主，接近参照画面里的箭头。

    curve 给定（'C'/'S'）时按蛇形加权：每个拐弯有旋转符号（见 _turn_signs），
    C 形要求下一个弯**和上一个同号**（一直往同一边卷），S 形要求**交替**
    （往回弯，蛇形蜿蜒）。匹配预期符号的转向乘 curve_boost、不匹配除以
    curve_boost；同时调用方应把 straight_bias 压低——直行太多的话
    弯根本没机会出现，形状加权就是空转。

    还有一处只为 C 形开的口子：普通路径每步只许走「箭轴反向」或「垂直」，
    而「垂直→箭轴反向」这一拐的符号必然和「箭轴→垂直」相反（叉积算得出），
    转弯永远正负交替——C 形在这种步进模型里**结构性不可能**。所以蛇形箭
    额外允许沿 +direction 走：从垂线拐回箭轴时就能拐出同号弯，C 形才弯得出来。
    沿 +direction 逼近箭头正前方的射线仍被 forbidden 拦着，不会指向自己。

    有一条硬禁区：**不许长到箭头正前方那条射线上去**。箭头是从箭头往回长的，
    绕一圈之后完全可能把尾巴甩到箭头前面，那就成了「箭头指着自己的箭身」——
    画面上像打了个死结，规则上也永远飞不出去（见 pieces.faces_own_body）。
    """
    cells = [head]
    used = {head}
    cursor = head
    back = OPPOSITE[direction]
    forward = DIRECTIONS[direction]
    forbidden = set(ray_cells(head, direction, rows, cols))
    heading = back                      # 上一步的行进方向（第一步沿 back）
    last_sign = None                    # 最近一个拐弯的符号，喂给 C/S 加权

    while len(cells) < max_len:
        if len(cells) == 1:
            options = [back]
        elif curve is not None:
            options = [back] + [DIRECTIONS[name]
                                for name in PERPENDICULAR[direction]] + [forward]
        else:
            options = [back] + [DIRECTIONS[name] for name in PERPENDICULAR[direction]]
        choices = []
        for delta in options:
            row, col = cursor[0] + delta[0], cursor[1] + delta[1]
            if not (0 <= row < rows and 0 <= col < cols):
                continue
            if grid[row][col] != -1 or (row, col) in used or (row, col) in forbidden:
                continue
            # 优先钻进「空格邻居少」的角落，能把零碎的空隙吃掉。
            # 直行按 delta == back 判是刻意的：拐弯后拐回箭轴也吃直行的高权重，
            # 整体形状才以「长条 + 少量拐弯」为主（改成按 heading 判会让
            # 所有箭都变弯弯绕绕，大盘铺满率直接塌掉——实测过，别改）。
            weight = straight_bias if delta == back else (1.0 - straight_bias) / 2.0
            if delta != back and curve is not None and last_sign is not None:
                cross = heading[0] * delta[1] - heading[1] * delta[0]
                sign = 1 if cross > 0 else -1
                want = last_sign if curve == "C" else -last_sign
                weight *= curve_boost if sign == want else 1.0 / curve_boost
            weight *= 1.0 + 0.5 * (3 - empty_neighbours(grid, row, col, rows, cols))
            choices.append((weight, (row, col)))
        if not choices:
            break
        total = sum(weight for weight, _ in choices)
        pick = rng.random() * total
        for weight, cell in choices:
            pick -= weight
            if pick <= 0:
                cursor = cell
                break
        else:
            cursor = choices[-1][1]
        delta = (cursor[0] - cells[-1][0], cursor[1] - cells[-1][1])
        if delta != heading:
            cross = heading[0] * delta[1] - heading[1] * delta[0]
            last_sign = 1 if cross > 0 else -1
            heading = delta
        cells.append(cursor)
        used.add(cursor)

    cells.reverse()                     # tail -> head
    return tuple(cells)


def ray_length(head, direction, rows, cols):
    """从 head 沿 direction 到棋盘边界还有几格（射线长度）。"""
    d_row, d_col = DIRECTIONS[direction]
    row, col = head[0] + d_row, head[1] + d_col
    length = 0
    while 0 <= row < rows and 0 <= col < cols:
        length += 1
        row += d_row
        col += d_col
    return length


def sample_target(rng, mean_len, max_len):
    """给下一支箭采一个「目标长度」。

    长短差距是观感的一部分：满盘等长的箭看着像尺子铺出来的。
    所以每支箭开工前先抽一个目标——以 mean_len 为中心、标准差
    0.45×mean 的大方差正态，截到 [2, max_len]。抽出来自然有的
    短到两三格、有的长到快顶上限，而不是全都长成一个模样。

    下限卡 2 不是随手的：1 格箭在半满的盘上最容易把周围的射线
    截成一段段死角，后面没有位置能再放下新的箭，铺满率塌掉
    （实测 min=1 时大盘平均只有 0.79，min=2 能回到 0.85+）。
    sigma 0.45 也是实测出来的平衡点：再大铺满率掉、再小长短差出不来。
    """
    sigma = mean_len * 0.45
    target = int(round(rng.gauss(mean_len, sigma)))
    return max(2, min(max_len, target))


# 朝向均衡：同一支方向放得越多，再放一支同向的罚分越重。
# 罚的是「相对当前最少方向的差值」而不是绝对支数——这样不管盘面多满，
# 永远有一个零罚分的方向，罚分差不会被整体抬高稀释。
# 没有这条时「ray_bias 偏爱长射线」会让箭头集体朝棋盘长边指——实测
# 第 4 关一度 70% 朝上、第 7 关 74% 朝下，四个方向挤成两个；
# 参照画面里上下左右是均匀混着指的，观感差距很大。
DIR_BALANCE_LINEAR = 12.0
DIR_BALANCE_QUAD = 1.5


def place_one(grid, rows, cols, rng, max_len, head_sample=36, path_tries=5,
              ray_bias=3.0, target=None, dir_counts=None, curve=None):
    """在当前盘面上找一支最能填满棋盘的箭放下；找不到返回 None。

    返回 (cells, direction)，cells 是 tail -> head 顺序。

    target 不是 None 时，打分从「越长越好」改成「离目标长度越近越好」——
    这是长短差距的来源；target 为 None 时保持旧打法（尽量长）。

    ray_bias 的作用：放置时射线一定是通的，但**偏爱「朝盘内、射线更长」的方向**。
    朝盘外摆的箭（射线长 0）放在边上永远可点，会让开局可点数虚高、关卡变简单；
    把箭尽量朝里摆，后来者更容易挡住它，开局可点数就压下来了。

    dir_counts 记录各方向已放几支（generate 负责维护），驱动朝向均衡罚分——
    见 DIR_BALANCE_LINEAR / DIR_BALANCE_QUAD 的说明。

    curve 给定（'C'/'S'）时按蛇形箭养：直行概率压到 0.45 给拐弯让路，
    路径多试两次（形状没那么容易弯出来），打分叠加 shape_bonus——
    弯够了数 +40，压得住「离目标长度差一两格 × 12」的长度罚分，
    否则生成器宁可放弃形状也要贴长度，curve_prob 就名存实亡了。
    """
    empty = [(r, c) for r in range(rows) for c in range(cols) if grid[r][c] == -1]
    if not empty:
        return None

    # 先算出每个空格「朝哪几个方向的射线是通的」，没有可放方向就不用管了
    options = []
    for row, col in empty:
        dirs = [name for name in DIRECTIONS
                if ray_clear(grid, (row, col), name, rows, cols)]
        if dirs:
            options.append((empty_neighbours(grid, row, col, rows, cols), (row, col), dirs))
    if not options:
        return None

    rng.shuffle(options)
    options.sort(key=lambda item: item[0])      # 越憋的位置越先填
    best = None
    if curve is not None:
        path_tries += 2

    for _, head, dirs in options[:head_sample]:
        for _ in range(path_tries):
            direction = rng.choice(dirs)
            cells = grow_backward(grid, head, direction, rows, cols, rng, max_len,
                                  straight_bias=0.45 if curve else 0.62,
                                  curve=curve)
            # 打分：贴住目标长度；奖励「把憋的位置吃掉了」；再偏向朝盘内；
            # 最后按朝向均衡罚分——同方向比最少方向多出几支就罚几份。
            # 偏差一格罚 12 分，压得过 ray_bias 的方向分——长度贴目标
            # 是硬要求，方向偏好只是软性倾向；朝向均衡罚分则专门对付
            # 「满盘箭头都朝一头」的规律感。
            if target is None:
                base = len(cells) * 10
            else:
                base = -abs(len(cells) - target) * 12
            tight = sum(3 - empty_neighbours(grid, r, c, rows, cols) for r, c in cells)
            if dir_counts:
                dev = dir_counts.get(direction, 0) - min(dir_counts.values())
                balance_penalty = (DIR_BALANCE_LINEAR * dev
                                   + DIR_BALANCE_QUAD * dev * dev)
            else:
                balance_penalty = 0.0
            score = (base + tight
                     + ray_bias * ray_length(head, direction, rows, cols)
                     + rng.random()
                     - balance_penalty)
            if curve is not None:
                score += shape_bonus(cells, curve)
            if best is None or score > best[0]:
                best = (score, cells, direction)
    if best is None:
        return None
    return best[1], best[2]


def generate(rows, cols, seed=0, max_len=8, max_pieces=None, ray_bias=3.0,
             mean_len=None, curve_prob=0.0, s_share=0.5):
    """生成一个布局，返回「放置顺序」下的箭列表（倒序即为一条通关顺序）。

    mean_len 给定时每支箭按 sample_target 抽目标长度（长短差距大）；
    不给时退回旧行为：每支都尽量长（等长盘）。

    curve_prob 是每支箭抽中蛇形（C/S 形）的概率，s_share 是抽中时归为
    S 形的比例（其余为 C 形）。蛇形箭占格多、目标长度有下限
    （C 至少 6 格、S 至少 9 格，不然弯不出形状），抽中后把目标长度
    抬到下限再交给 place_one。
    """
    rng = random.Random(seed)
    grid = [[-1] * cols for _ in range(rows)]
    placed = []
    dir_counts = {}                     # 各方向已放几支，喂给朝向均衡罚分

    while max_pieces is None or len(placed) < max_pieces:
        target = sample_target(rng, mean_len, max_len) if mean_len else None
        curve = None
        if rng.random() < curve_prob:
            curve = "S" if rng.random() < s_share else "C"
            floor = 9 if curve == "S" else 6
            if target is not None:
                target = max(target, min(floor, max_len))
        found = place_one(grid, rows, cols, rng, max_len, ray_bias=ray_bias,
                          target=target, dir_counts=dir_counts, curve=curve)
        if found is None:
            break
        cells, direction = found
        index = len(placed)
        for row, col in cells:
            grid[row][col] = index
        placed.append(Piece(cells=cells, direction=direction, uid=index))
        dir_counts[direction] = dir_counts.get(direction, 0) + 1

    return placed


def to_ascii(rows, cols, pieces):
    """把布局画成 ASCII：. 空格 / o 箭头身子 / ^v<> 箭头那一格。"""
    grid = [["."] * cols for _ in range(rows)]
    for piece in pieces:
        for row, col in piece.cells:
            grid[row][col] = "o"
    for piece in pieces:
        row, col = piece.head
        grid[row][col] = CHAR_DIRS[piece.direction]
    return ["".join(line) for line in grid]


def fill_ratio(rows, cols, pieces):
    """铺满率：被箭头占掉的格子占棋盘的比例。"""
    used = sum(piece.length for piece in pieces)
    return used / float(rows * cols)


def report(rows, cols, pieces, index=None):
    """打印一份可读的关卡报告。"""
    head = "第 %d 关" % index if index is not None else "候选布局"
    order = solve_level(rows, cols, pieces)
    print("%s  %d×%d  箭头 %d 支  占格 %d/%d（%.0f%%）  开局可点 %d  可解：%s"
          % (head, rows, cols, len(pieces),
             sum(p.length for p in pieces), rows * cols,
             fill_ratio(rows, cols, pieces) * 100,
             count_free_pieces(rows, cols, pieces), "是" if order else "否"))
    for row, line in enumerate(to_ascii(rows, cols, pieces)):
        print("   %2d | %s" % (row, line))
    return order


def best_of(rows, cols, seeds, max_len=8, keep=1, max_pieces=None):
    """跑多个种子，留下铺得最满的那几版。"""
    results = []
    for seed in seeds:
        pieces = generate(rows, cols, seed=seed, max_len=max_len,
                          max_pieces=max_pieces)
        if not pieces:
            continue
        if validate_layout_quiet(rows, cols, pieces) is not None:
            continue                          # 布局自检没过（不该发生）
        if solve_level(rows, cols, pieces) is None:
            continue                          # 理论上有解，复核一道更放心
        results.append((fill_ratio(rows, cols, pieces), seed, pieces))
    results.sort(key=lambda item: -item[0])
    return results[:keep]


def validate_layout_quiet(rows, cols, pieces):
    """布局自检；不合法时返回错误信息而不是抛异常（生成器要批量试）。"""
    try:
        validate_layout(rows, cols, pieces)
    except ValueError as error:
        return str(error)
    return None


def dump(pieces, indent="        "):
    """把布局打印成 levels.py 里可以直接粘贴的写法。"""
    return "\n".join(indent + '"%s",' % format_piece(p.cells, p.direction)
                     for p in pieces)


if __name__ == "__main__":
    # 默认按手机的竖屏比例出一题（列 < 行）；也可以从命令行给行列。
    rows, cols = (int(sys.argv[1]), int(sys.argv[2])) if len(sys.argv) > 2 else (13, 9)
    for ratio, seed, pieces in best_of(rows, cols, range(12), keep=3):
        report(rows, cols, pieces)
        print("  seed=%d  铺满率 %.3f" % (seed, ratio))
