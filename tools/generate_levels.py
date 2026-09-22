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


def grow_backward(grid, head, direction, rows, cols, rng, max_len, straight_bias=0.62):
    """从箭头位置往回长出一条路径，返回 tail -> head 顺序的格子元组。

    第一步必须沿 -direction，保证「最后一段和箭头方向一致」。
    之后可以在「继续直行」和「转向」里随机挑，直行概率高一点，
    这样出来的形状以长条 + 少量拐弯为主，接近参照画面里的箭头。

    有一条硬禁区：**不许长到箭头正前方那条射线上去**。箭头是从箭头往回长的，
    绕一圈之后完全可能把尾巴甩到箭头前面，那就成了「箭头指着自己的箭身」——
    画面上像打了个死结，规则上也永远飞不出去（见 pieces.faces_own_body）。
    """
    cells = [head]
    used = {head}
    cursor = head
    back = OPPOSITE[direction]
    forbidden = set(ray_cells(head, direction, rows, cols))

    while len(cells) < max_len:
        if len(cells) == 1:
            options = [back]
        else:
            options = [back] + [DIRECTIONS[name] for name in PERPENDICULAR[direction]]
        choices = []
        for delta in options:
            row, col = cursor[0] + delta[0], cursor[1] + delta[1]
            if not (0 <= row < rows and 0 <= col < cols):
                continue
            if grid[row][col] != -1 or (row, col) in used or (row, col) in forbidden:
                continue
            # 优先钻进「空格邻居少」的角落，能把零碎的空隙吃掉
            weight = straight_bias if delta == back else (1.0 - straight_bias) / 2.0
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


def place_one(grid, rows, cols, rng, max_len, head_sample=36, path_tries=5,
              ray_bias=3.0):
    """在当前盘面上找一支最能填满棋盘的箭放下；找不到返回 None。

    返回 (cells, direction)，cells 是 tail -> head 顺序。

    ray_bias 的作用：放置时射线一定是通的，但**偏爱「朝盘内、射线更长」的方向**。
    朝盘外摆的箭（射线长 0）放在边上永远可点，会让开局可点数虚高、关卡变简单；
    把箭尽量朝里摆，后来者更容易挡住它，开局可点数就压下来了。
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

    for _, head, dirs in options[:head_sample]:
        for _ in range(path_tries):
            direction = rng.choice(dirs)
            cells = grow_backward(grid, head, direction, rows, cols, rng, max_len)
            # 打分：占的格子越多越好；奖励「把憋的位置吃掉了」；再偏向朝盘内
            tight = sum(3 - empty_neighbours(grid, r, c, rows, cols) for r, c in cells)
            score = (len(cells) * 10 + tight
                     + ray_bias * ray_length(head, direction, rows, cols)
                     + rng.random())
            if best is None or score > best[0]:
                best = (score, cells, direction)
    if best is None:
        return None
    return best[1], best[2]


def generate(rows, cols, seed=0, max_len=8, max_pieces=None, ray_bias=3.0):
    """生成一个布局，返回「放置顺序」下的箭列表（倒序即为一条通关顺序）。"""
    rng = random.Random(seed)
    grid = [[-1] * cols for _ in range(rows)]
    placed = []

    while max_pieces is None or len(placed) < max_pieces:
        found = place_one(grid, rows, cols, rng, max_len, ray_bias=ray_bias)
        if found is None:
            break
        cells, direction = found
        index = len(placed)
        for row, col in cells:
            grid[row][col] = index
        placed.append(Piece(cells=cells, direction=direction, uid=index))

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
