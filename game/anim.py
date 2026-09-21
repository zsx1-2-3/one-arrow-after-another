# -*- coding: utf-8 -*-
"""动画效果：箭头飞出、撞击抖动、飘字提示。

每个动画对象都提供统一的接口：
    update(dt) -> bool   返回 True 表示动画播完，可以从列表里移除
    draw(surface)        把自己画到屏幕上
"""

import math

import pygame

from . import config, ui
from .board import DIRECTIONS


def _unit_vector(direction):
    """方向 -> 屏幕坐标下的单位向量（x 向右，y 向下）。"""
    d_row, d_col = DIRECTIONS[direction]
    return pygame.Vector2(d_col, d_row)


class FlyOut:
    """箭头沿着自己的方向飞出棋盘。"""

    def __init__(self, arrow, cell_rect, travel, duration=config.FLY_DURATION):
        self.direction = arrow.direction
        # 用和棋盘上完全相同的颜色，否则箭头一飞出去就"换了个颜色"
        self.color = ui.arrow_color(arrow.direction)
        self.side = min(cell_rect.width, cell_rect.height) * config.ARROW_RATIO
        self.start = pygame.Vector2(cell_rect.center)
        self.vector = _unit_vector(self.direction)
        self.travel = float(travel)
        self.duration = duration
        self.elapsed = 0.0
        self.progress = 0.0

    def update(self, dt):
        self.elapsed += dt
        self.progress = min(1.0, self.elapsed / self.duration)
        return self.progress >= 1.0

    @property
    def position(self):
        # 用 1.7 次方做缓入，看起来像被"抽"出去一样越来越快
        eased = self.progress ** 1.7
        return self.start + self.vector * (self.travel * eased)

    @property
    def alpha(self):
        if self.progress < 0.72:
            return 255
        return int(255 * (1.0 - (self.progress - 0.72) / 0.28))

    def draw(self, surface):
        ui.draw_arrow(surface, self.position, self.side, self.direction,
                      color=self.color, alpha=self.alpha)


class Impact:
    """撞击反馈：向前冲一下再弹回 + 抖动 + 单元格泛红 + 红框扩散。"""

    def __init__(self, arrow, cell_rect, duration=config.IMPACT_DURATION):
        self.direction = arrow.direction
        self.color = ui.arrow_color(arrow.direction)
        cell_size = min(cell_rect.width, cell_rect.height)
        self.cell_size = cell_size
        self.side = cell_size * config.ARROW_RATIO
        self.center = pygame.Vector2(cell_rect.center)
        self.rect = pygame.Rect(cell_rect)
        self.vector = _unit_vector(self.direction)
        self.perpendicular = pygame.Vector2(-self.vector.y, self.vector.x)
        self.duration = duration
        self.elapsed = 0.0
        self.progress = 0.0

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
        push = math.sin(math.pi * min(t / 0.45, 1.0)) * self.cell_size * config.IMPACT_PUSH_RATIO
        # 垂直于前进方向的抖动，幅度随时间衰减
        wobble = math.sin(t * math.pi * 8.0) * self.cell_size * 0.05 * (1.0 - t)
        return self.vector * push + self.perpendicular * wobble

    def draw(self, surface):
        flash = self.flash
        if flash > 0:
            # 单元格染红
            ui.draw_round_rect_alpha(surface, self.rect, config.COLOR_DANGER,
                                     int(96 * flash), radius=config.CELL_RADIUS)
            pygame.draw.rect(surface, config.COLOR_DANGER, self.rect, 3,
                             border_radius=config.CELL_RADIUS)
            # 向外扩散的红框
            grow = int(self.cell_size * 0.12 * self.progress)
            ring = self.rect.inflate(grow * 2, grow * 2)
            ui.draw_round_rect_alpha(surface, ring, config.COLOR_DANGER,
                                     int(130 * flash), radius=config.CELL_RADIUS, width=2)

        color = ui.mix_color(self.color, config.COLOR_DANGER, flash)
        ui.draw_arrow(surface, self.center + self.offset, self.side, self.direction, color=color)


class FloatingText:
    """向上飘动并淡出的提示文字（例如「这里没有箭头」）。"""

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
    """失去一颗生命值：像素心从格子里弹起、裂成两半，然后淡出。

    这里刻意不写「失去一心」四个字——生命值本身就用心的形状表示，
    心碎的画面比一行文字更直接，也不会和「这里没有箭头」那句文字提示混成一片。
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
