# -*- coding: utf-8 -*-
"""录制一段演示 GIF，放进 README 与博客里当作「项目展示」。

原理和 make_screenshots.py 一样：SDL 用 dummy 驱动无头渲染，
区别是这次不停在单张画面，而是连续抓帧再交给 Pillow 拼成 GIF。

用法：
    python tools/make_demo_gif.py            # 默认档：326×422 / 8fps / 64 色 / 1.8MB
    python tools/make_demo_gif.py --fps 10 --colors 128 --scale 0.6
                                             # 高清档：408×528 / 10fps / 128 色 / 3.7MB

输出：assets/demo.gif

尺寸说明
--------
游戏窗口是 680×880（手机竖屏比例），GIF 按 `--scale` 等比缩再存，
所以 GIF 里看到的画面比例和真机一致。别按横屏尺寸去缩——
那样棋盘会被压扁，箭头看着像被踩过。

默认档取 0.48 不是随便定的：**博客园单张图片上限 2MB**，
而这张 GIF 要贴进博客，所以体积是不可协商的硬指标（详见下节）。

体积控制
--------
GIF 是逐帧位图，体积基本正比于「像素数 × 颜色数 × 帧数」，三处都要压：

  * 分辨率（`--scale`）；
  * 调色板颜色数（`--colors`）；
  * 帧率（`--fps`）；
  * 另外中段「一支一支点完剩下的」用快进录（step_scale），帧数直接除以倍率。

三个开关的实际手感（都是这套画面实测的体积）：

    10fps / 128 色 / 0.60 → 3.7MB     ← 背景加动效之前那一版
     8fps /  64 色 / 0.60 → 2.4MB
     8fps /  64 色 / 0.55 → 2.0MB     还是贴边
     8fps /  64 色 / 0.50 → 1.9MB     2MiB 够、2,000,000 字节不够，赌不起
     8fps /  64 色 / 0.48 → 1.8MB     ← 定这一档（1,887,192 字节，两种算法都在限内）

    （顺带试过"关掉抖动"，指望量化噪点变纯色后 LZW 压得更小——**体积一个字节没变**，
      Pillow 这条路不吃这个参数，所以代码里没有这一段。）

为什么最后砍的是尺寸：GIF 里那几行 UI 小字**无论如何都看不清**
（0.6 倍时已经只有 8 像素高），所以"缩尺寸"损失的是最不值钱的东西；
而帧率掉到 6 以下，「整条箭头像绳子一样飞出去」这个要展示的重点就先垮了。

背景一动，GIF 就小不下来（这一版为止最大的一笔体积代价）
--------------------------------------------------------
上面那句「optimize=True 走帧间差分」有个前提：**大部分区域不动**。
棋盘铺满时确实如此，所以早先 12fps 能压到 2.6MB。
但背景现在是活的——极光带、浮尘、光晕每帧都在变，只是变得很慢。
慢不解决问题：差分的单位是矩形，一像素的涟漪和十像素的位移都要写满全屏，
于是 12fps 直接涨到 4.2MB，10fps 是 3.7MB，8fps 还有 2.4MB。
想再往下走，要么把背景关掉（`config.BG_AURORA_COUNT = 0`，但博客里正好有一节
在讲背景动效，拿一张死背景的 GIF 去配它就对不上了），要么就动上面那三个开关。
最后选的是后者。

录制的路线（脚本里每一步都有注释，这里只说叙事）：

    开始界面 → 第 2 关 → 点掉一两支（看整条箭头飞出去）
    → 悬停被挡的箭头（红路径）→ 悬停通畅的箭头（绿路径）
    → 开辅助线 → 用一次提示 → 关辅助线 → 点错扣一颗心
    → 快进点完剩下的 → 通关结算面板

注意：脚本用**临时目录里的存档**，不会动你自己那份 progress.json。
"""

import argparse
import os
import sys

# 必须在 import pygame 之前设置，才能进入无头模式
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOOLS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
sys.path.insert(0, TOOLS)

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from _showcase import (discard_progress, find_blocked, find_free,  # noqa: E402
                       fresh_progress, plan_balance)
from game import config, ui  # noqa: E402
from game.app import Game  # noqa: E402
from game.levels import LEVELS  # noqa: E402

OUT_PATH = os.path.join(ROOT, "assets", "demo.gif")

FRAME = 1.0 / 60.0
# 默认这一档是「能贴进博客园」的档位，三个数字的来由见文件开头「体积控制」。
# 想录高清版就命令行覆盖：--fps 10 --colors 128 --scale 0.6（3.7MB，别拿去交博客）。
CAPTURE_FPS = 8                       # GIF 每秒的帧数（越小体积越小，代价是卡顿）
GRAB_EVERY = max(1, int(round(1.0 / (FRAME * CAPTURE_FPS))))
SCALE = 0.48                          # 680×880 -> 326×422，等比缩放
WIDTH = int(round(config.WINDOW_WIDTH * SCALE))
HEIGHT = int(round(config.WINDOW_HEIGHT * SCALE))
GIF_COLORS = 64                       # 转成多少色的调色板图（越小体积越小）


def parse_args(argv=None):
    """三个体积开关 + 输出路径，默认值就是正式版那一档。"""
    parser = argparse.ArgumentParser(description="录制演示 GIF")
    parser.add_argument("--fps", type=int, default=CAPTURE_FPS,
                        help="GIF 帧率，默认 %d" % CAPTURE_FPS)
    parser.add_argument("--colors", type=int, default=GIF_COLORS,
                        help="调色板颜色数，默认 %d" % GIF_COLORS)
    parser.add_argument("--scale", type=float, default=SCALE,
                        help="等比缩放，默认 %.2f" % SCALE)
    parser.add_argument("--out", default=OUT_PATH,
                        help="输出路径，默认 assets/demo.gif")
    return parser.parse_args(argv)


def configure(args):
    """把命令行参数落到本模块的全局量上（capture/record 读的就是它们）。"""
    global CAPTURE_FPS, GRAB_EVERY, SCALE, WIDTH, HEIGHT, GIF_COLORS, OUT_PATH
    if args.fps <= 0 or args.colors < 2 or args.scale <= 0:
        raise SystemExit("参数不合理：fps>0、colors>=2、scale>0")
    CAPTURE_FPS = args.fps
    GRAB_EVERY = max(1, int(round(1.0 / (FRAME * CAPTURE_FPS))))
    SCALE = args.scale
    WIDTH = int(round(config.WINDOW_WIDTH * SCALE))
    HEIGHT = int(round(config.WINDOW_HEIGHT * SCALE))
    GIF_COLORS = min(256, args.colors)
    OUT_PATH = args.out


def level_index(name):
    """按关卡名取下标，避免写死数字（详见 make_screenshots.py 里的说明）。"""
    for index, level in enumerate(LEVELS):
        if level.name == name:
            return index
    raise SystemExit("关卡表里没有「%s」" % name)


def capture(surface):
    """把当前画面转成缩小的 PIL 图像。"""
    raw = pygame.image.tostring(surface, "RGB")
    image = Image.frombytes("RGB", surface.get_size(), raw)
    return image.resize((WIDTH, HEIGHT), Image.LANCZOS)


def record(game, screen, frames, seconds, step_scale=1):
    """推进 seconds 秒游戏时间，同时按 CAPTURE_FPS 抽帧存进 frames。

    step_scale > 1 就是「快进」：隔 step_scale 倍才抓一帧。
    抓得少了，放进 GIF 的那一段也就过得快了——
    用它来压缩「还有十几支要一支一支点完」这种重复动作，
    既不丢信息，也不让 GIF 变成十几秒的点击流水账。
    """
    for step in range(int(seconds / FRAME) + 1):
        game.update(FRAME)
        game.draw()
        if step % (GRAB_EVERY * step_scale) == 0:
            frames.append(capture(screen))


def hover(game, piece):
    """把鼠标移到这支箭头的尾格上——点它身上任意一格都算选中它。"""
    game.mouse_pos = game.cell_rect(*piece.tail).center
    game.update_hover()


def unhover(game):
    game.mouse_pos = (-1, -1)
    game.update_hover()


def main(argv=None):
    configure(parse_args(argv))
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption(config.WINDOW_TITLE)
    ui.clear_caches()

    # 选「交叉路口」：13×9 的棋盘在 GIF 的宽度下还看得清每支箭头，
    # 开局能直接点的箭头不多（5~7 支），正好演示「扫射线找出口」这件事。
    # start_level 走的是和真实玩家同一套解锁判定，未解锁会直接拒绝开局，
    # 所以先把前面几关标记成已通关。
    target_level = level_index("交叉路口")
    progress, save_path = fresh_progress("demo", range(target_level))
    game = Game(screen, progress=progress)

    frames = []

    # -------- 1. 开始界面（标题 + 进度 + 主按钮） --------
    game.draw()
    record(game, screen, frames, 0.9)

    # -------- 2. 进入第 2 关 --------
    game.start_level(target_level)
    game.toast_timer = 0.0
    unhover(game)
    record(game, screen, frames, 0.6)

    # -------- 3. 先点掉一两支，把盘面点出空档 --------
    # 为什么不直接演示红/绿路径：关卡是逆向构造出来的，铺满率 92% 以上，
    # 开局盘面几乎没有空格——被挡路径只有一格，通畅路径根本不存在
    # （能飞的只剩贴着边、箭头朝盘外那几支，射线长度为 0）。
    # 点掉一两支之后两条路径才画得出长度来。这也是真实玩法的一部分。
    solution = game.board.solution()
    steps = max(1, plan_balance(LEVELS[target_level], max_steps=3))
    for order in range(steps):
        hover(game, solution[order])
        game.click_cell(*solution[order].head)
        record(game, screen, frames, 0.72)
    unhover(game)
    record(game, screen, frames, 0.3)

    # -------- 4. 悬停在一支被挡住的箭头上：红色路径 + 挡路那格套红框 --------
    blocked = find_blocked(game.board)
    hover(game, blocked)
    record(game, screen, frames, 0.9)

    # -------- 5. 悬停在一支能飞出去的箭头上：绿色路径一路画到盘外 --------
    free = find_free(game.board)
    hover(game, free)
    record(game, screen, frames, 0.9)

    # -------- 6. 打开辅助线 + 用一次提示 --------
    # 辅助线把每支箭头的去路都画出来，提示再直接指出先点哪一支。
    game.toggle_guides()
    game.toast_timer = 0.0              # 气泡会挡住棋盘，演示里不需要它
    unhover(game)
    record(game, screen, frames, 0.9)

    game.use_hint()
    record(game, screen, frames, 1.1)

    game.toggle_guides()
    game.toast_timer = 0.0
    record(game, screen, frames, 0.3)

    # -------- 7. 点错：撞击抖动 + 飘出一颗碎心，生命值 -1 --------
    # 被点的这支不会消失，所以后面按解法往下点依然有效。
    game.click_cell(*blocked.cells[0])
    unhover(game)
    record(game, screen, frames, 1.0)

    # -------- 8. 按求解器顺序把这一关打完 --------
    # 头两步正常速度：看清「整条箭头滑出棋盘」这件事；
    # 后面十几步同质重复，快进录制，GIF 里一闪而过即可。
    # 剩下的就是解法的后半段——刚才点错的那支还在盘上，它也在里面，
    # 轮到它时自然会被点掉。
    tail = solution[steps:]
    for order, piece in enumerate(tail):
        game.click_cell(*piece.head)
        hover(game, piece)
        if order < 2:
            record(game, screen, frames, 0.62)
        else:
            record(game, screen, frames, 0.34, step_scale=4)
    unhover(game)
    record(game, screen, frames, 0.5)

    # -------- 9. 通关结算面板：本关得分 + 完美奖励 --------
    record(game, screen, frames, config.RESULT_DELAY + 1.4)

    pygame.quit()

    # -------- 拼成 GIF --------
    # 两个体积开关，缺一不可：
    #   * 转成 GIF_COLORS 色的调色板图（GIF 本来也只支持 256 色，128 色几乎看不出差别，
    #     交博客要压到 2MB 以内时再往下降到 64 色）；
    #   * optimize=True 且**不要**写 disposal=2。
    #     这是踩过的坑：disposal=2（每帧先清成背景再画）配上不透明帧时，
    #     Pillow 会放弃帧间差分、把每帧都按整幅写进去，体积直接翻几倍。
    #     默认的 disposal=0 才会走差分路径——只写这一帧真正变了的矩形，
    #     棋盘这种「大部分区域不动」的画面因此能小一大截。
    palette = [frame.convert("P", palette=Image.ADAPTIVE, colors=GIF_COLORS)
               for frame in frames]
    palette[0].save(
        OUT_PATH,
        save_all=True,
        append_images=palette[1:],
        duration=int(1000 / CAPTURE_FPS),
        loop=0,
        optimize=True,
    )

    discard_progress(save_path)

    size_kb = os.path.getsize(OUT_PATH) / 1024.0
    print("已保存 %s（%d×%d / %d 帧 / %.1f 秒 / %.0f KB）"
          % (os.path.relpath(OUT_PATH, ROOT), WIDTH, HEIGHT, len(palette),
             len(palette) / float(CAPTURE_FPS), size_kb))
    return 0


if __name__ == "__main__":
    sys.exit(main())
