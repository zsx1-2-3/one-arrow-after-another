# -*- coding: utf-8 -*-
"""动态背景：极光带 + 漂移光晕 + 浮尘 + 流星 + 四周压暗。

为什么要单独一个模块：
    原来背景只是一张启动时算好的竖直渐变色图，每帧原样贴上去，画面是死的。
    这里把"会动的背景"独立出来，app.py 每个场景只要 update(dt) / draw(screen) 两句。

四层动效（浓淡都在 config.BG_* 里调）：
    1. 极光带   —— 几条斜向柔光带缓缓往下流过，是"画面活着"最主要的来源；
    2. 漂移光晕 —— 两团压得很暗的柔光，沿李萨如曲线游走；
    3. 浮尘     —— 缓慢上浮、左右轻摆、明灭呼吸的小光点；
    4. 流星     —— 隔十几二十秒划一颗。

2026-09-22 的两次调整，方向刚好相反，合起来才是现在这版：
    先是按参考图把底子做"干净"——原版星点和流星在深紫底上显得碎，还和棋盘上的
    箭头抢注意力，所以把两个数量都改成了"相当于不出现"（BG_STAR_COUNT = 0、
    BG_SHOOT_INTERVAL = (999, 1000)）；后来嫌画面太静，又在"不抢戏"的前提下
    把动效加回来：星点改成更慢更暗的浮尘并发数减半，新增极光带当主戏，
    流星间隔从原来的 6~14 秒拉长到 12~26 秒。
    相关数量都在 config 里，想回到"只有两团光晕"把 BG_AURORA_COUNT / BG_STAR_COUNT
    写 0 即可。

两条配色上的约束（都和主题有关）：
    * 夜间是深紫底，光带用**加法**叠加发光；日间主题底子浅，加法只会糊成白斑，
      所以同一张贴图改用**减法**叠加，成了"云影缓缓飘过"。一张贴图两种用法，
      换的只是 blit 时那个 special_flags（见 sunlit）。
    * 背景是衬托，不是主角。光带亮度整体压得很低，叠加之后棋盘区域依然要保持对比度。

性能上的三个约束（都实测过）：
    1. 光带、光晕、浮尘都是**预渲染贴图 + 缓存**，动画里每帧只做 blit，
       不在每帧新建 Surface，也不做逐像素操作——否则 60 帧下必掉帧；
    2. 亮度按档位量化再缓存（光带见 _band_image，光晕见 ui.draw_glow），
       呼吸 / 淡入淡出不会撑爆缓存；
    3. 光带贴图做一张要 smoothscale + rotate，几毫秒起步，只有第一次用到某个
       (光带, 亮度档) 组合时才现做。
"""

import math
import random

import pygame

from . import config, ui

# 极光带的配色：偏冷的靛蓝 / 青 / 紫，和整屏的深紫底子同一色系。
# 亮度整体压得低——底色本身已经提亮了（(63,65,85) 而不是 (24,30,52)），
# 光带再亮就会把底色顶成一块脏斑。
AURORA_COLORS = (
    (44, 60, 126),
    (30, 92, 116),
    (70, 50, 116),
    (26, 76, 100),
)

# 日间（浅底）用的是**减去的量**，所以颜色必须是中性灰蓝、三通道差不多。
# 这里踩过一个坑：一开始日间直接沿用上面那套发光色做减法，结果浅蓝底减掉"偏蓝的光"
# 等于给底子上了补色——青带被减成暗红、紫带被减成绿色，满屏红绿条纹，像蒙了块脏玻璃。
# 换成中性色之后才是干净的"云影"。
AURORA_DAY_COLORS = (
    (30, 33, 44),
    (27, 34, 43),
    (34, 31, 45),
    (28, 34, 41),
)

# 光晕的配色：同样偏冷，比光带更暗更柔。
ORB_COLORS = (
    (58, 52, 108),
    (40, 84, 106),
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
                     (44, 42, 88), 0.55, falloff=2.4)

        # 光带：上下各留一截"屏外"，带子从屏外滑进来、再从另一侧滑出去
        self.aurora_pad = max(40, int(self.height * config.BG_AURORA_PAD_RATIO))
        self._band_cache = {}
        self.aurora = self._make_aurora()

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

        # 浮尘：慢慢往上飘，飘出上边就回到下边；各自不同步地闪烁 + 左右轻摆
        self.stars = []
        for _ in range(config.BG_STAR_COUNT):
            self.stars.append(self._make_star(random_y=True))

        # 流星：隔一段时间来一颗
        self.shooting = None
        self.shoot_interval = config.BG_SHOOT_INTERVAL
        self.shoot_timer = self.rng.uniform(*self.shoot_interval)

        self.vignette = self._make_vignette()
        self.set_scene(scene)

    # ------------------------------------------------------------ 构建
    def _make_aurora(self):
        """几条斜向柔光带，初始沿全高均匀铺开。

        初始位置刻意**铺满整屏**而不是都堆在屏外：不然开局头十几秒画面里一条都没有，
        而那几秒恰好就是"双击打开看一眼"和截图脚本拍到的时刻。
        """
        bands = []
        count = max(1, config.BG_AURORA_COUNT)
        pad = self.aurora_pad
        slot = (self.height + 2 * pad) / float(count)
        low, high = config.BG_AURORA_SPEED
        for index in range(count):
            radius = int(self.rng.uniform(0.036, 0.058) * self.height)
            # 宽度只拉到「刚好盖住整屏还有富余」：光带是一条**有端头的椭圆**，
            # 宽度不够时端头会落在画面里，看着就是一个圆钝的截口
            # （测试图上很像渲染出了 bug）。但也不能一味拉宽——贴图是拿来
            # blit 的，宽一倍就是内存和填充率各翻一倍，见 _tilt 那段。
            stretch = self.width * self.rng.uniform(1.28, 1.42) / (radius * 2.0)
            bands.append({
                "index": index,
                "x": self.rng.uniform(0.44, 0.56) * self.width,
                "y": -pad + slot * (index + 0.5)
                     + self.rng.uniform(-0.35, 0.35) * slot,
                "radius": radius,
                "stretch": stretch,
                "angle": self.rng.uniform(-8.0, 8.0),
                "speed": self.rng.uniform(low, high),
                "color": AURORA_COLORS[index % len(AURORA_COLORS)],
                "peak": self.rng.uniform(0.62, 1.0),
                "sway": self.rng.uniform(0.02, 0.06) * self.width,
                "sway_speed": self.rng.uniform(0.05, 0.13),
                "phase": self.rng.uniform(0.0, 6.28),
                "breath_speed": self.rng.uniform(0.10, 0.26),
            })
        return bands

    def _make_star(self, random_y=False):
        low, high = config.BG_STAR_SPEED
        sway_low, sway_high = config.BG_STAR_SWAY
        return {
            "x": self.rng.uniform(0, self.width),
            "y": self.rng.uniform(0, self.height) if random_y else self.height + 4,
            "radius": self.rng.choice((4, 5, 5, 6, 7)),
            "speed": self.rng.uniform(low, high),
            "bright": self.rng.uniform(0.20, 0.62),
            "phase": self.rng.uniform(0.0, 6.28),
            "twinkle": self.rng.uniform(0.35, 1.10),
            "sway": self.rng.uniform(sway_low, sway_high),
            "sway_speed": self.rng.uniform(0.12, 0.38),
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
        """切换场景浓淡，并按主题决定光带是"发光"还是"云影"。

        日间主题的底子是浅色：加法光会糊成白斑，所以极光带改成减法叠加（云影），
        光晕大幅压暗，浮尘直接关掉（浅底上的小白点本来就看不见，白花这笔钱），
        流星也把间隔拉长。
        """
        self.scene = scene
        play = (scene == config.SCENE_PLAY)
        self.sunlit = (config.THEME == "day")
        dim = config.BG_PLAY_DIM if play else 1.0

        self.aurora_intensity = config.BG_AURORA_DRIFT * dim * (
            config.BG_DAY_DIM if self.sunlit else 1.0)
        self.orb_intensity = (0.55 if play else 0.95) * (0.35 if self.sunlit else 1.0)
        self.star_count = 0 if self.sunlit else (
            config.BG_STAR_COUNT_PLAY if play else config.BG_STAR_COUNT)
        self.shoot_interval = (config.BG_SHOOT_INTERVAL_PLAY if play
                               else config.BG_SHOOT_INTERVAL)
        if self.sunlit:
            self.shoot_interval = tuple(value * 2.4 for value in self.shoot_interval)
        if self.shooting is None:
            self.shoot_timer = min(self.shoot_timer, self.shoot_interval[1])
        self.vignette_on = True

    # ------------------------------------------------------------ 更新
    def update(self, dt):
        self.time += dt

        # 光带：匀速往下走，整条滑到屏幕下边之外就回到上边重新下来
        for band in self.aurora:
            band["y"] += band["speed"] * dt
            if band["y"] - band["radius"] > self.height + self.aurora_pad:
                band["y"] = -band["radius"] - self.aurora_pad

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
                self.shoot_timer = self.rng.uniform(*self.shoot_interval)

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

        self._draw_aurora(surface)

        # 光晕：位置由两条不同周期的正弦合成，看起来像无规则地慢慢游动
        for orb in self.orbs:
            t = self.time * orb["speed"] * 6.283 + orb["phase"]
            center = (orb["x"] + math.sin(t) * orb["sweep"],
                      orb["y"] + math.sin(t * 0.63 + 1.1) * orb["rise"])
            breath = 0.72 + 0.28 * math.sin(t * 0.9)
            ui.draw_glow(surface, center, orb["radius"], orb["color"],
                         self.orb_intensity * breath, falloff=2.6)

        # 浮尘：加法叠加的小亮点，亮度各自按正弦闪烁、横向按另一条正弦轻摆
        for index in range(min(self.star_count, len(self.stars))):
            star = self.stars[index]
            flicker = 0.55 + 0.45 * math.sin(self.time * star["twinkle"] + star["phase"])
            sway = math.sin(self.time * star["sway_speed"] + star["phase"] * 0.7) \
                * star["sway"]
            ui.draw_glow(surface, (star["x"] + sway, star["y"]), star["radius"],
                         (158, 192, 246), star["bright"] * flicker, falloff=2.0, levels=5)

        if self.shooting is not None:
            self._draw_shooting(surface)

        if self.vignette_on:
            surface.blit(self.vignette, (0, 0))

    def _draw_aurora(self, surface):
        """斜向柔光带：夜间加法发光，日间减法做云影（同一张贴图，换 special_flags）。"""
        flags = pygame.BLEND_RGB_SUB if self.sunlit else pygame.BLEND_RGB_ADD
        for band in self.aurora:
            t = self.time * band["sway_speed"] * 6.283 + band["phase"]
            breath = 0.70 + 0.30 * math.sin(
                self.time * band["breath_speed"] * 6.283 + band["phase"] * 1.7)
            strength = self.aurora_intensity * band["peak"] * breath
            if strength <= 0.02:                      # 太淡就不用画了，省一次 blit
                continue
            image = self._band_image(band, strength)
            center = (int(band["x"] + math.sin(t) * band["sway"]), int(band["y"]))
            surface.blit(image, image.get_rect(center=center), special_flags=flags)

    @staticmethod
    def _tilt(image, angle):
        """把贴图切成一条条竖列、逐列上下错位，做出倾斜。

        为什么不用 pygame.transform.rotate：光带是**又宽又扁**的一条
        （一屏多宽、百来像素高），旋转的代价按「外接矩形」算——
        13° 就能把 1360×110 撑成 1340×480，一张贴图白吃四倍内存，
        十几张就是几十兆（实测 21MB -> 8MB 就是换掉它省下来的）。
        逐列错位只多出 tan(角度)×宽 的高度，形状一模一样。

        方向别弄反：要错位的是**竖列**。早先按行错位写过一版，
        结果带子的端头是斜的、带子本身还是水平的，看着像没生效。
        """
        if abs(angle) < 0.5:
            return image
        width, height = image.get_size()
        slope = math.tan(math.radians(angle))
        extra = int(abs(slope) * width) + 2
        tilted = pygame.Surface((width, height + extra), pygame.SRCALPHA)
        base = extra if slope < 0 else 0
        for x in range(width):
            tilted.blit(image, (x, base + int(slope * x)), (x, 0, 1, height))
        return tilted

    def _band_image(self, band, strength):
        """取这条光带在某个亮度档位上的贴图（没有就现做一张并缓存）。

        亮度量化成 config.BG_AURORA_LEVELS 档：呼吸只是在几张现成的贴图之间跳，
        不然每帧一次 smoothscale + 错位，几毫秒就没了。
        """
        levels = config.BG_AURORA_LEVELS
        level = max(1, min(levels, int(round(min(1.0, strength) * levels))))
        key = (band["index"], level, self.sunlit)
        image = self._band_cache.get(key)
        if image is None:
            radius = band["radius"]
            color = (AURORA_DAY_COLORS[band["index"] % len(AURORA_DAY_COLORS)]
                     if self.sunlit else band["color"])
            core = ui.glow_surface(radius, color, 2.6, level / float(levels))
            image = pygame.transform.smoothscale(
                core, (max(2, int(radius * 2 * band["stretch"])), radius * 2))
            image = self._tilt(image, band["angle"])
            self._band_cache[key] = image
        return image

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
