# -*- coding: utf-8 -*-
"""动态背景：缓慢漂移的光晕 + 星点 + 偶发流星 + 四周压暗。

为什么要单独一个模块：
    原来背景只是一张启动时算好的竖直渐变色图，每帧原样贴上去，画面是死的。
    这里把"会动的背景"独立出来，app.py 每个场景只要 update(dt) / draw(screen) 两句。

性能上的两个约束（都实测过）：
    1. 光晕、星点都是**预渲染贴图 + 缓存**，动画里每帧只做 blit，
       不在每帧新建 Surface，也不做逐像素操作——否则 60 帧下必掉帧；
    2. 亮度按档位量化再缓存（见 ui.draw_glow），呼吸 / 淡入淡出不会撑爆缓存。

观感上的一个约束：
    背景是衬托，不是主角。光晕压得很暗、星点也很淡，
    叠加上去之后棋盘区域依然要保持对比度，不能出现"背景比箭头还抢眼"的情况。
"""

import math
import random

import pygame

from . import config, ui

# 光晕的配色：偏冷的蓝紫 / 青，和整体深蓝底子同一色系，不突兀
ORB_COLORS = (
    (54, 46, 128),
    (18, 74, 118),
    (26, 92, 92),
)


class Background:
    """一个会缓慢变化的背景。

    scene 用来切换"浓淡"：菜单可以热闹一点，游戏里要收敛，别和棋盘抢注意力。
    """

    def __init__(self, size, scene="menu", seed=20260921):
        self.width, self.height = size
        self.rng = random.Random(seed)
        self.time = 0.0

        # 底：竖直渐变 + 顶部一团静态柔光（让画面有纵深，不是一块平板）
        self.base = ui.make_vertical_gradient(
            size, config.COLOR_BG_TOP, config.COLOR_BG_BOTTOM)
        ui.draw_glow(self.base, (self.width * 0.5, -60), 330,
                     (40, 60, 120), 0.85, falloff=2.4)

        # 光晕：每个沿一条缓慢的李萨如曲线漂移，基本看不出"在动"，但画面是活的
        self.orbs = []
        for index in range(config.BG_ORB_COUNT):
            self.orbs.append({
                "x": self.rng.uniform(0.12, 0.88) * self.width,
                "y": self.rng.uniform(0.10, 0.80) * self.height,
                "radius": self.rng.uniform(0.22, 0.34) * min(self.width, self.height),
                "color": ORB_COLORS[index % len(ORB_COLORS)],
                "sweep": self.rng.uniform(0.18, 0.34) * self.width,
                "rise": self.rng.uniform(0.08, 0.16) * self.height,
                "phase": self.rng.uniform(0.0, 6.28),
                "speed": config.BG_ORB_SPEED * self.rng.uniform(0.7, 1.7),
                "breathe": self.rng.uniform(0.09, 0.17),
            })

        # 星点：慢慢往上飘，飘出上边就回到下边；带一点各自不同步的闪烁
        self.stars = []
        for _ in range(config.BG_STAR_COUNT):
            self.stars.append(self._make_star(random_y=True))

        # 流星：隔一段时间来一颗
        self.shooting = None
        self.shoot_timer = self.rng.uniform(*config.BG_SHOOT_INTERVAL)

        self.vignette = self._make_vignette()
        self.set_scene(scene)

    # ------------------------------------------------------------ 构建
    def _make_star(self, random_y=False):
        return {
            "x": self.rng.uniform(0, self.width),
            "y": self.rng.uniform(0, self.height) if random_y else self.height + 4,
            "radius": self.rng.choice((3, 3, 4, 4, 5)),
            "speed": self.rng.uniform(4.0, 15.0),
            "bright": self.rng.uniform(0.28, 0.92),
            "phase": self.rng.uniform(0.0, 6.28),
            "twinkle": self.rng.uniform(0.7, 2.1),
        }

    def _make_vignette(self):
        """四周压暗。

        做法：先在一张很小的图上按「到中心的距离」算好每个像素的 alpha，
        再用 smoothscale 放大到全屏。

        这里踩过一个坑：最早的写法是"一圈圈内缩、每圈画一条 1px 边框"，
        结果四个角上相邻两圈的圆角排不齐，留下了四条很明显的斜向条纹
        （本来是压暗，反而多出四条边）。改小图放大之后既干净又快。
        """
        small_w, small_h = 80, 60
        small = pygame.Surface((small_w, small_h), pygame.SRCALPHA)
        diag = math.sqrt(2.0)
        for y in range(small_h):
            ny = (y + 0.5) / small_h * 2.0 - 1.0
            for x in range(small_w):
                nx = (x + 0.5) / small_w * 2.0 - 1.0
                distance = math.hypot(nx, ny) / diag          # 0=中心, 1=四角
                ratio = max(0.0, min(1.0, (distance - 0.30) / 0.74))
                alpha = int(config.BG_VIGNETTE_ALPHA * ratio ** 1.7)
                if alpha:
                    small.set_at((x, y), (0, 0, 0, alpha))
        return pygame.transform.smoothscale(small, (self.width, self.height))

    def set_scene(self, scene):
        """切换场景浓淡：游戏界面里星点减半、光晕更暗。"""
        self.scene = scene
        play = (scene == config.SCENE_PLAY)
        self.star_count = config.BG_STAR_COUNT_PLAY if play else config.BG_STAR_COUNT
        self.orb_intensity = 0.55 if play else 0.95
        self.vignette_on = True

    # ------------------------------------------------------------ 更新
    def update(self, dt):
        self.time += dt

        for star in self.stars:
            star["y"] -= star["speed"] * dt
            if star["y"] < -6:                        # 飘出上边就回到下边重新来
                fresh = self._make_star()
                star.update(fresh)
                star["y"] = self.height + 4

        if self.shooting is None:
            self.shoot_timer -= dt
            if self.shoot_timer <= 0:
                self._spawn_shooting()
        else:
            shot = self.shooting
            shot["elapsed"] += dt
            shot["x"] += shot["vx"] * dt
            shot["y"] += shot["vy"] * dt
            if shot["elapsed"] >= shot["duration"]:
                self.shooting = None
                self.shoot_timer = self.rng.uniform(*config.BG_SHOOT_INTERVAL)

    def _spawn_shooting(self):
        start_x = self.rng.uniform(-0.1, 0.7) * self.width
        angle = math.radians(self.rng.uniform(22, 38))
        speed = self.rng.uniform(430, 640)
        duration = self.rng.uniform(0.75, 1.15)
        self.shooting = {
            "x": start_x,
            "y": self.rng.uniform(-40, 0.25 * self.height),
            "vx": math.cos(angle) * speed,
            "vy": math.sin(angle) * speed,
            "elapsed": 0.0,
            "duration": duration,
            "length": self.rng.uniform(70, 130),
        }

    # ------------------------------------------------------------ 绘制
    def draw(self, surface):
        surface.blit(self.base, (0, 0))

        # 光晕：位置由两条不同周期的正弦合成，看起来像无规则地慢慢游动
        for orb in self.orbs:
            t = self.time * orb["speed"] * 6.283 + orb["phase"]
            center = (orb["x"] + math.sin(t) * orb["sweep"],
                      orb["y"] + math.sin(t * 0.63 + 1.1) * orb["rise"])
            breath = 0.72 + 0.28 * math.sin(t * 0.9)
            ui.draw_glow(surface, center, orb["radius"], orb["color"],
                         self.orb_intensity * breath, falloff=2.6)

        # 星点：加法叠加的小亮点，亮度各自按正弦闪烁
        for index in range(min(self.star_count, len(self.stars))):
            star = self.stars[index]
            flicker = 0.55 + 0.45 * math.sin(self.time * star["twinkle"] + star["phase"])
            ui.draw_glow(surface, (star["x"], star["y"]), star["radius"],
                         (150, 186, 246), star["bright"] * flicker, falloff=2.2, levels=5)

        if self.shooting is not None:
            self._draw_shooting(surface)

        if self.vignette_on:
            surface.blit(self.vignette, (0, 0))

    def _draw_shooting(self, surface):
        """流星：头部一个亮点 + 一条逐渐变淡的尾巴。"""
        shot = self.shooting
        life = shot["elapsed"] / shot["duration"]
        # 淡入快、淡出慢
        fade = min(1.0, life / 0.18) * (1.0 - life) ** 1.6
        if fade <= 0.01:
            return
        norm = math.hypot(shot["vx"], shot["vy"]) or 1.0
        back_x = shot["vx"] / norm
        back_y = shot["vy"] / norm

        segments = 10
        for step in range(segments):
            ratio = step / float(segments)
            distance = shot["length"] * ratio
            strength = (1.0 - ratio) ** 2 * fade
            ui.draw_glow(surface,
                         (shot["x"] - back_x * distance, shot["y"] - back_y * distance),
                         3 + int(4 * (1.0 - ratio)),
                         (168, 206, 255), strength * 0.85, falloff=1.6, levels=5)

        ui.draw_glow(surface, (shot["x"], shot["y"]), 22, (198, 224, 255),
                     fade, falloff=2.2, levels=6)
