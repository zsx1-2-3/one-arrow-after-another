# -*- coding: utf-8 -*-
"""棋子模型：一支「箭」是一条占多格的折线箭头，末端带一个箭头。

参照同类游戏的实际画面，箭头**不是「一格一支」**，而是一条蜿蜒的箭头：

    "4,6 > D3R2"

表示从第 4 行第 6 列出发，箭头朝右，路径先向下 3 格、再向右 2 格
（共 1 + 3 + 2 = 6 格，末端那一格就是箭头所在的位置）。

规则和单格箭头完全一样：从「头」（箭头末端）沿着箭头方向看出去，
射线上只要有一格被别的棋子占着，这支箭就飞不出去。

本模块只做数据与几何，不 import pygame，方便单独做单元测试。
"""

import re
from dataclasses import dataclass

# ---------------------------------------------------------------- 方向
# 方向 -> (行增量, 列增量)。行号向下增大，列号向右增大。
DIRECTIONS = {
    "up": (-1, 0),
    "down": (1, 0),
    "left": (0, -1),
    "right": (0, 1),
}

# 关卡数据里的方向字符
DIR_CHARS = {"^": "up", "v": "down", "<": "left", ">": "right"}
CHAR_DIRS = {direction: char for char, direction in DIR_CHARS.items()}

# 路径段字符：D3 = 向下 3 格
SEG_CHARS = {"U": "up", "D": "down", "L": "left", "R": "right"}
CHARS_FOR_SEG = {direction: char for char, direction in SEG_CHARS.items()}

# ---------------------------------------------------------------- 配色
# 从参照画面里采出来的糖果色。每支箭随机取一个，
# 但相邻的两支箭不允许同色（见 assign_colors），否则会「糊成一片」。
PIECE_PALETTE = (
    (143, 193,  61),   # 黄绿
    (245, 197,  66),   # 金黄
    (124, 181, 230),   # 天蓝
    (232, 162,  94),   # 橙
    (234, 129, 180),   # 粉
    (116, 213, 155),   # 薄荷
    ( 80, 164, 122),   # 青绿
    (224, 106, 120),   # 红
    (186, 104, 200),   # 紫
    (126, 134, 216),   # 蓝紫
    (196, 120,  60),   # 赭
    (232, 144, 144),   # 鲑
)

# ---------------------------------------------------------------- 写法解析
# "4,6 > D3R2"：行,列 方向 路径段
# 路径段可以省略（"5,0 <" 就是只占一格、箭头朝左的短箭），
# 也可以用小写（d3r2），方向和行列之间还能多打几个空格——
# 关卡数据是手写与脚本生成混着的，宽进严出比纠结格式更实用。
PIECE_SPEC = re.compile(r"^(\d+),(\d+)\s+([\^v<>])(?:\s+([UDLRudlr0-9]*))?$")
_SEGMENT = re.compile(r"([UDLR])(\d*)")


def parse_piece(spec):
    """把 "4,6 > D3R2" 解析成 (cells, direction)。

    cells 从「尾」到「头」有序，cells[-1] 是箭头所在的格子。

    一个坑：这里**不能**对整串调用 upper()。方向字符里的 'v'（向下）大写之后
    会变成 'V'，而方向字符表里认的是小写 'v'，于是所有朝下的箭都会解析失败。
    所以只把「路径段」那一段提出来大写，方向字符单独按小写去查表。
    """
    text = re.sub(r"\s+", " ", str(spec).strip())
    matched = PIECE_SPEC.match(text)
    if not matched:
        raise ValueError("棋子写法不合法：%r" % spec)
    row, col = int(matched.group(1)), int(matched.group(2))
    direction = DIR_CHARS[matched.group(3).lower()]
    cells = [(row, col)]
    for segment in _SEGMENT.finditer((matched.group(4) or "").upper()):
        d_row, d_col = DIRECTIONS[SEG_CHARS[segment.group(1)]]
        for _ in range(int(segment.group(2) or 1)):
            row, col = row + d_row, col + d_col
            cells.append((row, col))
    return tuple(cells), direction


def format_piece(cells, direction):
    """parse_piece 的逆运算，供关卡生成器打印布局用。"""
    if not cells:
        raise ValueError("棋子至少要占一格")
    segments = []
    for (r1, c1), (r2, c2) in zip(cells, cells[1:]):
        step = (r2 - r1, c2 - c1)
        for name, delta in DIRECTIONS.items():
            if delta == step:
                segments.append(CHARS_FOR_SEG[name])
                break
        else:
            raise ValueError("路径不是逐格相邻：%r -> %r" % ((r1, c1), (r2, c2)))

    # 把连续的同一方向合并成 D3 这种写法
    packed = []
    for char in segments:
        if packed and packed[-1][0] == char:
            packed[-1][1] += 1
        else:
            packed.append([char, 1])
    body = "".join(char + (str(count) if count > 1 else "") for char, count in packed)
    return "%d,%d %s %s" % (cells[0][0], cells[0][1], CHAR_DIRS[direction], body)


@dataclass(frozen=True)
class Piece:
    """棋盘上的一支箭：一条由若干相邻格子组成的折线 + 一个方向。"""

    cells: tuple
    direction: str
    color: tuple = None
    uid: int = 0

    @property
    def head(self):
        """箭头所在的那一格（箭头的末端）。"""
        return self.cells[-1]

    @property
    def tail(self):
        """箭头的起点（尾部）。"""
        return self.cells[0]

    @property
    def delta(self):
        return DIRECTIONS[self.direction]

    @property
    def length(self):
        return len(self.cells)

    def ray(self, rows, cols):
        """从箭头出发、沿箭头方向直到棋盘边界的格子（不含箭头自己）。"""
        d_row, d_col = self.delta
        row, col = self.head[0] + d_row, self.head[1] + d_col
        cells = []
        while 0 <= row < rows and 0 <= col < cols:
            cells.append((row, col))
            row += d_row
            col += d_col
        return cells


def ray_cells(head, direction, rows, cols):
    """任意「头 + 方向」的射线，给求解器复用。"""
    d_row, d_col = DIRECTIONS[direction]
    row, col = head[0] + d_row, head[1] + d_col
    cells = []
    while 0 <= row < rows and 0 <= col < cols:
        cells.append((row, col))
        row += d_row
        col += d_col
    return cells


def build_grid(rows, cols, pieces):
    """返回 rows × cols 的表，格子内容是该格所属棋子的下标（空格为 None）。"""
    grid = [[None] * cols for _ in range(rows)]
    for index, piece in enumerate(pieces):
        for row, col in piece.cells:
            grid[row][col] = index
    return grid


def faces_own_body(piece, rows, cols):
    """这支箭的射线是否穿过它自己的身体。

    为什么专门判这一条：箭头是从箭头往回长的，绕一圈之后完全可能把尾巴
    甩到箭头正前方去——那是「箭头指着自己的箭身」，画面上像个死结，
    规则上也永远飞不出去（射线被自己挡着）。生成器与关卡校验都拦掉这种形状。
    """
    return bool(set(piece.cells) & set(piece.ray(rows, cols)))


def validate_layout(rows, cols, pieces):
    """检查一份关卡布局是否合法；不合法就抛 ValueError。

    检查项：至少一支箭、都在盘内、不重叠、路径逐格相邻、不自交、
    **末端的一段必须和箭头方向一致**（否则画出来的箭头会歪在拐角上），
    以及**射线不能穿过自己的身体**（否则这支箭永远飞不出去）。
    """
    if not pieces:
        raise ValueError("关卡里没有任何箭头")
    used = {}
    for index, piece in enumerate(pieces):
        if not piece.cells:
            raise ValueError("第 %d 支箭没有占任何格子" % index)
        if piece.direction not in DIRECTIONS:
            raise ValueError("第 %d 支箭的方向不合法：%r" % (index, piece.direction))
        for row, col in piece.cells:
            if not (0 <= row < rows and 0 <= col < cols):
                raise ValueError("第 %d 支箭跑出棋盘了：(%d, %d)" % (index, row, col))
            if (row, col) in used:
                raise ValueError("第 %d 支箭和它前面的箭重叠在 (%d, %d)" % (index, row, col))
            used[(row, col)] = index
        for (r1, c1), (r2, c2) in zip(piece.cells, piece.cells[1:]):
            if abs(r2 - r1) + abs(c2 - c1) != 1:
                raise ValueError("第 %d 支箭的路径不是逐格相邻" % index)
        if len(set(piece.cells)) != len(piece.cells):
            raise ValueError("第 %d 支箭的路径自己交叉了" % index)
        if len(piece.cells) > 1:
            (r1, c1), (r2, c2) = piece.cells[-2], piece.cells[-1]
            if (r2 - r1, c2 - c1) != DIRECTIONS[piece.direction]:
                raise ValueError(
                    "第 %d 支箭最后一段和箭头方向不一致（画出来箭头会歪）" % index)
        if faces_own_body(piece, rows, cols):
            raise ValueError("第 %d 支箭的箭头正对着自己的箭头（会永远飞不出去）" % index)
    return True


def assign_colors(pieces, rows, cols):
    """给每支箭分配一个颜色，**保证相邻（上下左右）的两支箭不同色**。

    参照画面里同色的箭头挨在一起会连成一大片、看不出有几支；
    这里用贪心染色避开：挨个处理，挑一个邻居没用过的颜色。
    颜色只影响好看与否，不参与任何规则判断。
    """
    grid = build_grid(rows, cols, pieces)
    colors = [None] * len(pieces)
    for index in range(len(pieces)):
        neighbour_colors = set()
        for row, col in pieces[index].cells:
            for d_row, d_col in DIRECTIONS.values():
                r, c = row + d_row, col + d_col
                if 0 <= r < rows and 0 <= c < cols:
                    other = grid[r][c]
                    if other is not None and other != index and colors[other] is not None:
                        neighbour_colors.add(colors[other])
        for shift in range(len(PIECE_PALETTE)):
            candidate = PIECE_PALETTE[(index + shift) % len(PIECE_PALETTE)]
            if candidate not in neighbour_colors:
                colors[index] = candidate
                break
        else:                                     # 12 色还不够用（几乎不会发生）
            colors[index] = PIECE_PALETTE[index % len(PIECE_PALETTE)]
    return colors
