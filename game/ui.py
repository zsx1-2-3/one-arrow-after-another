# -*- coding: utf-8 -*-
"""界面绘制工具：字体、文字、按钮、箭头图形。

所有函数都只依赖 Surface 与普通数值，因此 app.py 与截图脚本可以复用同一套绘制代码。
"""

import math
import os

import pygame

from . import config

_font_cache = {}
_arrow_cache = {}


# ------------------------------------------------------------------ 字体
def font_file(bold=False):
    """返回第一个存在的中文字体文件路径；都没找到返回 None。"""
    for path in (config.FONT_BOLD_PATHS if bold else config.FONT_PATHS):
        if os.path.exists(path):
            return path
    return None


def has_cjk_font():
    """是否成功找到中文字体（找不到时中文会显示成方块）。"""
    return font_file(False) is not None


def get_font(size, bold=False):
    """按字号缓存字体对象，避免每帧重复加载。"""
    key = (int(size), bool(bold))
    cached = _font_cache.get(key)
    if cached is not None:
        return cached

    path = font_file(bold)
    if path:
        font = pygame.font.Font(path, int(size))
    else:
        # 兜底：pygame 自带字体（不支持中文，仅保证程序不崩溃）
        font = pygame.font.Font(None, int(size))
        font.set_bold(bold)

    _font_cache[key] = font
    return font


# ------------------------------------------------------------------ 文字
def draw_text(surface, text, pos, size=22, color=config.COLOR_TEXT, bold=False, anchor="topleft"):
    """绘制一行文字，anchor 用法同 pygame.Rect（topleft / center / midleft ...）。"""
    image = get_font(size, bold).render(str(text), True, color)
    rect = image.get_rect(**{anchor: pos})
    surface.blit(image, rect)
    return rect


def text_width(text, size=22, bold=False):
    return get_font(size, bold).size(str(text))[0]


# 不允许出现在行首的标点（中文排版的基本规则）。
# 逐字折行时很容易把句号、右括号甩到下一行，读起来像多了一行残缺的字。
_NO_LINE_START = "。，、；：！？）】》」』”’%…·"


def wrap_text(text, size=22, max_width=400, bold=False):
    """把一段文字按像素宽度折行，返回行列表。

    中文没有空格，所以逐字符累加——宽度超了就换行。
    遇到换行符强制断行。

    折完再做一遍「标点不下行」修正：若某行以收尾标点开头，
    就把上一行的最后一个字一起挪下来。这样句号不会孤零零占一行。
    """
    font = get_font(size, bold)
    lines = []
    for paragraph in str(text).split("\n"):
        if not paragraph:
            lines.append("")
            continue
        current = ""
        for char in paragraph:
            candidate = current + char
            if current and font.size(candidate)[0] > max_width:
                lines.append(current)
                current = char
            else:
                current = candidate
        lines.append(current)

    # 标点不下行：把行首的收尾标点连同上一行的末字一起挪到下一行
    for index in range(1, len(lines)):
        line = lines[index]
        while line and line[0] in _NO_LINE_START and lines[index - 1]:
            line = lines[index - 1][-1] + line
            lines[index - 1] = lines[index - 1][:-1]
        lines[index] = line
    return lines


def draw_paragraph(surface, text, rect, size=18, color=config.COLOR_TEXT,
                   line_gap=6, bold=False, align="left"):
    """在 rect 内绘制一段自动折行的文字，返回实际占用的高度。

    align 取 left / center。
    """
    lines = wrap_text(text, size=size, max_width=rect.width, bold=bold)
    line_height = get_font(size, bold).get_linesize() + line_gap
    y = rect.y
    for line in lines:
        if align == "center":
            draw_text(surface, line, (rect.centerx, y), size=size, color=color,
                      bold=bold, anchor="midtop")
        else:
            draw_text(surface, line, (rect.x, y), size=size, color=color,
                      bold=bold, anchor="topleft")
        y += line_height
    return y - rect.y


# ------------------------------------------------------------------ 图标
def star_points(center, radius, inner_ratio=0.45):
    """画一个五角星需要的顶点序列。"""
    points = []
    for index in range(10):
        angle = -math.pi / 2 + index * math.pi / 5
        length = radius if index % 2 == 0 else radius * inner_ratio
        points.append((center[0] + math.cos(angle) * length,
                       center[1] + math.sin(angle) * length))
    return points


def draw_star(surface, center, radius, color, filled=True):
    """画一颗五角星；filled=False 时只画描边（表示未点亮的星）。"""
    points = star_points(center, radius)
    if filled:
        pygame.draw.polygon(surface, color, points)
    else:
        pygame.draw.polygon(surface, color, points, 2)


def draw_stars(surface, right_center, count, total=5, radius=7, gap=4, color=None):
    """从右往左排一行星星，count 颗点亮，其余为空心。返回整行宽度。"""
    color = color or config.COLOR_STAR
    step = radius * 2 + gap
    width = total * radius * 2 + (total - 1) * gap
    x = right_center[0] - width + radius
    for index in range(total):
        filled = index < count
        draw_star(surface, (x + index * step, right_center[1]), radius,
                  color if filled else config.COLOR_STAR_EMPTY, filled=filled)
    return width


def draw_lock(surface, center, size, color=None):
    """画一把挂锁（未解锁标记）。"""
    color = color or config.COLOR_LOCK
    body_w = size
    body_h = size * 0.78
    body = pygame.Rect(0, 0, body_w, body_h)
    body.center = (center[0], center[1] + size * 0.18)
    pygame.draw.rect(surface, color, body, border_radius=max(2, int(size * 0.16)))

    # 锁梁：一个上半圆
    shackle_w = size * 0.62
    shackle = pygame.Rect(0, 0, shackle_w, size * 0.66)
    shackle.midbottom = (center[0], body.top + 1)
    pygame.draw.arc(surface, color, shackle, 0, math.pi, max(2, int(size * 0.15)))

    # 锁孔
    hole = max(2, int(size * 0.13))
    pygame.draw.circle(surface, config.COLOR_CARD_LOCKED,
                       (int(center[0]), int(body.centery - hole * 0.4)), hole)


def draw_check(surface, center, size, color=None):
    """画一个对勾（已通关标记）。"""
    color = color or config.COLOR_SUCCESS
    points = [
        (center[0] - size * 0.42, center[1] + size * 0.02),
        (center[0] - size * 0.10, center[1] + size * 0.34),
        (center[0] + size * 0.44, center[1] - size * 0.34),
    ]
    pygame.draw.lines(surface, color, False, points, max(2, int(size * 0.20)))


# ------------------------------------------------------------------ 生命值（像素心）
# 生命值图标是一颗「像素心」：不写汉字、也不是圆滑的矢量心形，
# 和整套界面的像素箭头是同一种质感（图形定义见 config.HEART_PIXEL_ART）。
_heart_cache = {}
HEART_COLS = len(config.HEART_PIXEL_ART[0])
HEART_ROWS = len(config.HEART_PIXEL_ART)
HEART_ASPECT = HEART_ROWS / float(HEART_COLS)


def _heart_is_edge(col, row):
    """这个格子是否处在图案外沿（上下左右有一个不是实心格）。"""
    art = config.HEART_PIXEL_ART
    for d_col, d_row in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        c, r = col + d_col, row + d_row
        if not (0 <= c < HEART_COLS and 0 <= r < HEART_ROWS):
            return True
        if art[r][c] != "#":
            return True
    return False


def heart_surface(width, color, filled=True):
    """预渲染一颗像素心，按「宽度 + 颜色 + 是否实心」缓存。

    filled=False 是已经失去的那一颗：只保留外沿像素、内部镂空，
    和对面的实心心一对比就知道还剩几点生命值。
    """
    key = (int(width), tuple(color), bool(filled))
    cached = _heart_cache.get(key)
    if cached is not None:
        return cached

    width = max(HEART_COLS, int(width))
    height = max(HEART_ROWS, int(round(width * HEART_ASPECT)))
    surface = pygame.Surface((width, height), pygame.SRCALPHA)
    art = config.HEART_PIXEL_ART

    # 先把网格边界圆整成整数像素再画矩形：每格都落在整数像素上，
    # 相邻格之间不会因为浮点误差留下 1px 细缝。
    xs = [int(round(col * width / float(HEART_COLS))) for col in range(HEART_COLS + 1)]
    ys = [int(round(row * height / float(HEART_ROWS))) for row in range(HEART_ROWS + 1)]
    for row in range(HEART_ROWS):
        for col in range(HEART_COLS):
            if art[row][col] != "#":
                continue
            if not filled and not _heart_is_edge(col, row):
                continue
            rect = pygame.Rect(xs[col], ys[row],
                               max(1, xs[col + 1] - xs[col]),
                               max(1, ys[row + 1] - ys[row]))
            pygame.draw.rect(surface, tuple(color), rect)

    _heart_cache[key] = surface
    return surface


def draw_heart(surface, center, width, color, filled=True, alpha=255):
    """在 center 处画一颗像素心（width 为心形宽度）。"""
    image = heart_surface(width, color, filled)
    if alpha < 255:
        image = image.copy()
        image.set_alpha(int(alpha))
    surface.blit(image, image.get_rect(center=(int(center[0]), int(center[1]))))


def draw_hearts(surface, left_center, current, total, size=20, gap=8):
    """从左往右排一排心：前 current 颗实心，其余只剩轮廓。返回整排宽度。

    生命值按「还剩几点」显示，所以从左往右依次点亮，
    剩下的空位就是已经失去的生命值——玩家一眼能看出还能错几次。
    """
    step = size + gap
    width = total * size + (total - 1) * gap
    low = current <= 1
    for index in range(total):
        center = (left_center[0] + size / 2.0 + index * step, left_center[1])
        if index < current:
            draw_heart(surface, center, size,
                       config.COLOR_HP_LOW if low else config.COLOR_HP, filled=True)
        else:
            draw_heart(surface, center, size, config.COLOR_HP_LOST, filled=False)
    return width


# ------------------------------------------------------------------ 基础图形
def draw_round_rect(surface, rect, color, radius=12, width=0):
    pygame.draw.rect(surface, color, rect, width, border_radius=radius)


def draw_round_rect_alpha(surface, rect, color, alpha, radius=12, width=0):
    """带透明度的圆角矩形（用于路径高亮、遮罩等）。"""
    layer = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(layer, tuple(color) + (int(alpha),), layer.get_rect(), width, border_radius=radius)
    surface.blit(layer, rect.topleft)


def make_vertical_gradient(size, top_color, bottom_color):
    """生成竖直渐变背景（只在启动时生成一次）。"""
    width, height = size
    surface = pygame.Surface(size)
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = tuple(int(a + (b - a) * ratio) for a, b in zip(top_color, bottom_color))
        pygame.draw.line(surface, color, (0, y), (width, y))
    return surface


# ------------------------------------------------------------------ 箭头
def _arrow_shape(surface, center, side, color):
    """在 surface 上画一个「朝右」的箭头图形。"""
    cx, cy = center
    half = side / 2.0
    joint = cx + half * 0.08                      # 箭杆与箭头的交界 x 坐标
    shaft_left = cx - half
    shaft_height = side * 0.24

    pygame.draw.rect(
        surface,
        color,
        pygame.Rect(int(shaft_left), int(cy - shaft_height / 2),
                    int(joint - shaft_left), int(shaft_height)),
        border_radius=max(1, int(side * 0.11)),
    )
    pygame.draw.polygon(
        surface,
        color,
        [
            (int(cx + half), int(cy)),
            (int(joint), int(cy - side * 0.30)),
            (int(joint), int(cy + side * 0.30)),
        ],
    )


def _build_arrow(side, color, direction):
    """生成某种颜色/方向的箭头贴图。

    做法：先用白色画一个「朝右」的箭头当遮罩，旋转到目标方向，
    再乘上一层竖直渐变（上亮下暗），得到有光泽的立体箭头。
    渐变在**旋转之后**再乘，这样四个方向的受光方向一致（都从上方来），
    不会出现「朝上的箭头变成左边亮」这种别扭的光照。
    """
    pad = max(3, int(side * 0.14))
    size = int(side) + pad * 2

    # 1) 白色箭头遮罩
    shape = pygame.Surface((size, size), pygame.SRCALPHA)
    center = (size / 2.0, size / 2.0)
    _arrow_shape(shape, center, side, (255, 255, 255))

    # 2) 旋转到目标方向（90 的整数倍，贴图尺寸不变）
    angle = {"right": 0, "up": 90, "left": 180, "down": -90}[direction]
    if angle:
        shape = pygame.transform.rotate(shape, angle)

    # 3) 乘上竖直渐变：顶部提亮、底部压暗
    top = mix_color(color, (255, 255, 255), config.ARROW_HIGHLIGHT)
    bottom = mix_color(color, (0, 0, 0), config.ARROW_SHADE)
    gradient = pygame.Surface((size, size), pygame.SRCALPHA)
    for y in range(size):
        ratio = y / max(1, size - 1)
        gradient.fill(tuple(int(a + (b - a) * ratio) for a, b in zip(top, bottom)) + (255,),
                      pygame.Rect(0, y, size, 1))

    arrow = shape.copy()
    arrow.blit(gradient, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)

    # 4) 深色投影垫在下面，让箭头从格子上"浮"起来
    shadow = shape.copy()
    shadow.fill(tuple(max(0, int(value * 0.42)) for value in color) + (255,),
                special_flags=pygame.BLEND_RGBA_MULT)

    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    surface.blit(shadow, (2, 3))
    surface.blit(arrow, (0, 0))
    return surface


def arrow_color(direction):
    """取某个方向对应的箭头颜色。

    一个方向就是唯一一个颜色：同方向的箭头在画面上完全一致，
    不会出现有的深有的浅。四个方向的颜色亮度是拉平的（见 config.DIR_COLORS）。
    """
    return config.DIR_COLORS[direction]


def arrow_surface(side, color, direction):
    key = (int(side), tuple(color), direction)
    cached = _arrow_cache.get(key)
    if cached is None:
        cached = _build_arrow(key[0], tuple(color), direction)
        _arrow_cache[key] = cached
    return cached


def draw_arrow(surface, center, side, direction, color=None, alpha=255):
    """在 center（屏幕坐标）处画一个箭头，color 传 None 时按方向自动取色。"""
    if color is None:
        color = arrow_color(direction)
    image = arrow_surface(side, color, direction)
    if alpha < 255:
        image = image.copy()
        image.set_alpha(int(alpha))
    surface.blit(image, image.get_rect(center=(int(center[0]), int(center[1]))))


def mix_color(color_a, color_b, ratio):
    """按比例混合两种颜色，ratio=0 取 color_a，ratio=1 取 color_b。"""
    ratio = max(0.0, min(1.0, ratio))
    return tuple(int(a + (b - a) * ratio) for a, b in zip(color_a, color_b))


def lighten(color, ratio):
    """往白色方向提亮。"""
    return mix_color(color, (255, 255, 255), ratio)


def darken(color, ratio):
    """往黑色方向压暗。"""
    return mix_color(color, (0, 0, 0), ratio)


# ------------------------------------------------------------------ 光晕
_glow_cache = {}


def clear_caches():
    """清空字体 / 箭头 / 像素心 / 光晕贴图的缓存。

    什么时候需要它：pygame.quit() 之后又重新 init 的场景（比如测试里一个用例组
    退出 pygame、下一个用例组还要画图）。缓存里的 Font 与 Surface 在 quit 时
    已经被释放，再拿去渲染不会抛异常，而是直接段错误——排查起来很费劲，
    所以重新初始化之后先把缓存清干净。
    """
    _font_cache.clear()
    _arrow_cache.clear()
    _heart_cache.clear()
    _glow_cache.clear()


def glow_surface(radius, color, falloff=2.0, brightness=1.0):
    """预渲染一张径向渐变的光晕贴图（中心最亮、边缘全黑）。

    贴图用 BLEND_RGB_ADD 叠加，所以亮度直接烘进 RGB 里——
    好处是动画每帧只需要一次 blit，不用再复制/调 alpha，也就不会有每帧的内存分配。
    亮度按档位量化后缓存，避免呼吸动画把缓存撑爆。
    """
    key = (int(radius), tuple(color), round(falloff, 2), round(brightness, 2))
    cached = _glow_cache.get(key)
    if cached is not None:
        return cached

    radius = max(1, int(radius))
    size = radius * 2
    surface = pygame.Surface((size, size), pygame.SRCALPHA)
    steps = max(12, radius)
    for step in range(steps, 0, -1):
        ratio = step / float(steps)                  # 1 -> 0（外 -> 内）
        factor = max(0.0, 1.0 - ratio) ** falloff * brightness
        if factor <= 0.004:
            continue
        color_now = tuple(min(255, int(value * factor)) for value in color)
        pygame.draw.circle(surface, color_now + (255,), (radius, radius), int(radius * ratio))

    _glow_cache[key] = surface
    return surface


def draw_glow(surface, center, radius, color, intensity=1.0, falloff=2.0, levels=6):
    """在 center 处叠加一团光晕（加法混合）。

    intensity 0~1 控制明暗，内部量化成 levels 档再取缓存贴图，
    因此呼吸 / 淡入淡出这类动画不会产生额外开销。
    """
    intensity = max(0.0, min(1.0, intensity))
    if intensity <= 0.0:
        return
    level = max(1, int(round(intensity * levels)))
    image = glow_surface(radius, color, falloff, level / float(levels))
    surface.blit(image, image.get_rect(center=(int(center[0]), int(center[1]))),
                 special_flags=pygame.BLEND_RGB_ADD)


# ------------------------------------------------------------------ 按钮
BUTTON_STYLES = {
    "primary": {"bg": (70, 130, 226), "bg_hover": (98, 160, 250), "edge": (126, 184, 255), "text": (255, 255, 255)},
    "ghost": {"bg": (34, 42, 68), "bg_hover": (50, 62, 96), "edge": (62, 76, 116), "text": (206, 218, 240)},
    "success": {"bg": (50, 158, 106), "bg_hover": (68, 186, 124), "edge": (110, 224, 156), "text": (255, 255, 255)},
    "danger": {"bg": (172, 68, 68), "bg_hover": (200, 88, 88), "edge": (240, 126, 126), "text": (255, 255, 255)},
    "level": {"bg": (32, 40, 64), "bg_hover": (48, 60, 96), "edge": (60, 74, 112), "text": (232, 238, 250)},
}


class Button:
    """矩形按钮：由上层（app.py）决定点击后做什么。"""

    def __init__(self, rect, label, on_click=None, style="primary", size=22, sub=""):
        self.rect = pygame.Rect(rect)
        self.label = label
        self.sub = sub
        self.on_click = on_click
        self.style = style
        self.size = size
        self.enabled = True
        self.hovered = False

    def hit(self, pos):
        return self.enabled and self.rect.collidepoint(pos)

    def draw(self, surface):
        style = BUTTON_STYLES[self.style]
        hovered = self.hovered and self.enabled
        background = style["bg_hover"] if hovered else style["bg"]
        edge = style["edge"] if self.enabled else (68, 74, 96)
        text_color = style["text"] if self.enabled else (118, 126, 148)

        draw_round_rect(surface, self.rect, background, radius=12)
        draw_round_rect(surface, self.rect, edge, radius=12, width=2)
        if hovered:
            draw_round_rect_alpha(surface, self.rect, (255, 255, 255), 20, radius=12)

        if self.sub:
            draw_text(surface, self.label, (self.rect.centerx, self.rect.centery - 13),
                      size=self.size, color=text_color, bold=True, anchor="center")
            draw_text(surface, self.sub, (self.rect.centerx, self.rect.centery + 16),
                      size=15, color=config.COLOR_TEXT_DIM, anchor="center")
        else:
            draw_text(surface, self.label, self.rect.center,
                      size=self.size, color=text_color, bold=True, anchor="center")
