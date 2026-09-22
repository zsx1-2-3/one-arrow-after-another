# -*- coding: utf-8 -*-
"""动画效果：管道滑出、撞击抖动、飘字提示。

每个动画对象都提供统一的接口：
    update(dt) -> bool   返回 True 表示动画播完，可以从列表里移除
    draw(surface)        把自己画到屏幕上

注意这里的单位：从「一格里的一个箭头」变成了**一整支箭**（占多格的管道）。
滑出是沿管道自身的折线路径走的——箭头先钻出去，弯折顺着身体流到尾巴；
撞击则是整条管道朝箭头方向冲一下再弹回。
"""

import math

import pygame

from . import config, ui


class FlyOut:
    """整条管道沿**自己的路径**滑出棋盘——贪吃蛇转弯的连续版。

    想象把管道当成一条蛇：箭头先钻出去，拐弯顺着身体一路传到尾巴，
    全程连续插值，不是一格一格地跳。每个折点沿路径前进的弧长相同，
    滑过箭头之后就沿着箭头方向直线走出视口（视口裁剪由 draw_play 负责）。

    travel 是总滑行弧长（像素），由 app.fly_travel 按视口尺寸算好传进来。
    """

    def __init__(self, piece, board_origin, cell, travel, duration=config.FLY_DURATION):
        self.piece = piece
        self.board_origin = board_origin
        self.cell = cell
        self.travel = float(travel)
        self.duration = duration
        self.elapsed = 0.0
        self.progress = 0.0

    def update(self, dt):
        self.elapsed += dt
        self.progress = min(1.0, self.elapsed / self.duration)
        return self.progress >= 1.0

    @property
    def advance(self):
        # 用 1.7 次方做缓入，看起来像被"抽"出去一样越来越快
        return self.travel * (self.progress ** 1.7)

    def joints(self):
        """当前帧各折点的棋盘局部坐标（tail -> head），测试盯几何用。"""
        return ui.path_joints(self.piece, self.cell, self.advance)

    def draw(self, surface):
        ui.draw_piece_path(surface, self.board_origin, self.piece, self.cell,
                           self.advance)


class Impact:
    """撞击反馈：整支箭向前冲一下再弹回 + 抖动 + 箭头那格泛红 + 红圈扩散。"""

    # 变红的强度量化成几档：每档一张染色贴图，缓存住，动画里不再新建 Surface
    TINT_LEVELS = 4

    def __init__(self, piece, board_origin, cell, head_rect, duration=config.IMPACT_DURATION):
        self.piece = piece
        self.board_origin = board_origin
        self.cell = cell
        self.head_rect = pygame.Rect(head_rect)
        dx, dy = ui.DIR_VECTORS[piece.direction]
        self.vector = pygame.Vector2(dx, dy)
        self.perpendicular = pygame.Vector2(-dy, dx)
        self.duration = duration
        self.elapsed = 0.0
        self.progress = 0.0
        self._tints = {}

    def update(self, dt):
        self.elapsed += dt
        self.progress = min(1.0, self.elapsed / self.duration)
        return self.progress >= 1.0

    @property
    def flash(self):
        """0~1，红色警示强度，快速衰减。"""
        return max(0.0, 1.0 - self.progress * 1.3)

    @property
    def offset(self):
        t = self.progress
        # 前冲 18% 格宽后回弹
        push = math.sin(math.pi * min(t / 0.45, 1.0)) * self.cell * config.IMPACT_PUSH_RATIO
        # 垂直于前进方向的抖动，幅度随时间衰减
        wobble = math.sin(t * math.pi * 8.0) * self.cell * 0.05 * (1.0 - t)
        return self.vector * push + self.perpendicular * wobble

    def tinted(self, level):
        """染红到某一档的贴图与偏移；同一档只生成一次，整段动画反复用。

        偏移必须跟贴图一起缓存：贴图是**带留白**的（圆头、描边、箭头尖都要
        留出位置），不带着偏移一起用就会画偏一格。这里返回 (图, 偏移) 二元组，
        和 ui.piece_surface 的返回值形状保持一致，调用处好认。
        """
        cached = self._tints.get(level)
        if cached is None:
            color = ui.piece_color(self.piece)
            ratio = level / float(self.TINT_LEVELS)
            image, offset = ui.piece_surface(self.piece.cells, self.piece.direction,
                                             color, self.cell)
            tint = ui.mix_color((255, 255, 255), config.COLOR_DANGER, ratio)
            tinted = image.copy()
            tinted.fill(tuple(tint) + (255,), special_flags=pygame.BLEND_RGBA_MULT)
            cached = (tinted, offset)
            self._tints[level] = cached            # 存进去的就直接返回，
        return cached                              # 别在 return 里现拼一个新元组

    def draw(self, surface):
        flash = self.flash
        if flash > 0:
            # 箭头那一格染红：玩家点的就是这一支，反馈要落在它身上
            ui.draw_round_rect_alpha(surface, self.head_rect, config.COLOR_DANGER,
                                     int(96 * flash), radius=config.CELL_RADIUS)
            pygame.draw.rect(surface, config.COLOR_DANGER, self.head_rect, 3,
                             border_radius=config.CELL_RADIUS)
            # 向外扩散的红框
            grow = int(self.cell * 0.12 * self.progress)
            ring = self.head_rect.inflate(grow * 2, grow * 2)
            ui.draw_round_rect_alpha(surface, ring, config.COLOR_DANGER,
                                     int(130 * flash), radius=config.CELL_RADIUS, width=2)

        # 整支箭：闪得越厉害，染红越深
        level = int(round(flash * self.TINT_LEVELS))
        offset = self.offset
        if level <= 0:
            ui.draw_piece(surface, self.board_origin, self.piece, self.cell, offset=offset)
            return
        image, (dx, dy) = self.tinted(level)
        surface.blit(image, (int(self.board_origin[0] + dx + offset[0]),
                             int(self.board_origin[1] + dy + offset[1])))


class FloatingText:
    """向上飘动并淡出的提示文字（例如「这里没有管道」）。"""

    def __init__(self, text, position, color=config.COLOR_TEXT, size=22,
                 duration=0.9, rise=40):
        self.text = text
        self.position = position
        self.color = color
        self.size = size
        self.duration = duration
        self.rise = rise
        self.elapsed = 0.0
        self.progress = 0.0

    def update(self, dt):
        self.elapsed += dt
        self.progress = min(1.0, self.elapsed / self.duration)
        return self.progress >= 1.0

    def draw(self, surface):
        image = ui.get_font(self.size, True).render(self.text, True, self.color)
        image.set_alpha(int(255 * (1.0 - self.progress ** 1.8)))
        rect = image.get_rect(center=(int(self.position[0]),
                                      int(self.position[1] - self.rise * self.progress)))
        # 半透明底衬，保证在棋盘上也能看清
        padding = 8
        plate = rect.inflate(padding * 2, padding)
        ui.draw_round_rect_alpha(surface, plate, (0, 0, 0), int(120 * (1.0 - self.progress)), radius=8)
        surface.blit(image, rect)


class FloatingHeart:
    """失去一颗生命值：像素心从管道上弹起、裂成两半，然后淡出。

    这里刻意不写「失去一心」四个字——生命值本身就用心的形状表示，
    心碎的画面比一行文字更直接，也不会和「这里没有管道」那句文字提示混成一片。
    """

    def __init__(self, position, color=config.COLOR_HP, size=40,
                 duration=1.15, rise=52):
        self.position = pygame.Vector2(position)
        self.color = tuple(color)
        self.size = int(size)
        self.duration = duration
        self.rise = float(rise)
        self.elapsed = 0.0
        self.progress = 0.0
        self.left, self.right = self._halves()

    def _halves(self):
        """把整颗心切成左右两半（只做一次），供"心碎"动画使用。"""
        image = ui.heart_surface(self.size, self.color)
        width, height = image.get_size()
        half = width // 2
        left = pygame.Surface((half, height), pygame.SRCALPHA)
        left.blit(image, (0, 0))
        right = pygame.Surface((width - half, height), pygame.SRCALPHA)
        right.blit(image, (-half, 0))
        return left, right

    def update(self, dt):
        self.elapsed += dt
        self.progress = min(1.0, self.elapsed / self.duration)
        return self.progress >= 1.0

    @property
    def lift(self):
        """先向上弹起、再落回来（正弦曲线，最高点约为 rise）。"""
        return -self.rise * math.sin(math.pi * min(1.0, self.progress * 1.15))

    @property
    def alpha(self):
        """前三分之一保持不透明，之后淡出，别让玩家没看清就消失了。"""
        t = self.progress
        if t <= 0.32:
            return 255
        return max(0, int(255 * (1.0 - (t - 0.32) / 0.68) ** 1.3))

    def draw(self, surface):
        t = self.progress
        alpha = self.alpha
        if alpha <= 0:
            return

        center_x = self.position[0]
        base_y = self.position[1] + self.lift

        # 刚扣血时心口泛一圈红光，指出"就是这里出的事"
        flash = max(0.0, 1.0 - t * 2.4)
        if flash > 0:
            ui.draw_glow(surface, (center_x, base_y), int(self.size * 0.85),
                         (198, 62, 62), flash, falloff=2.0)

        # 两半越分越开、并各自向外倾斜——看起来就是心裂开了
        spread = self.size * 0.32 * (t ** 1.5)
        tilt = 18.0 * t
        left_image = pygame.transform.rotate(self.left, tilt)
        right_image = pygame.transform.rotate(self.right, -tilt)
        quarter = self.size * 0.25
        for image, dx in ((left_image, -quarter - spread),
                          (right_image, quarter + spread)):
            image.set_alpha(alpha)
            surface.blit(image, image.get_rect(center=(int(center_x + dx), int(base_y))))
