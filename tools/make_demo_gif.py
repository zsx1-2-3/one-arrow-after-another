# -*- coding: utf-8 -*-
"""录制一段演示 GIF，放进 README 与博客里当作「项目展示」。

原理和 make_screenshots.py 一样：SDL 用 dummy 驱动无头渲染，
区别是这次不停在单张画面，而是连续抓帧再交给 Pillow 拼成 GIF。

用法：
    python tools/make_demo_gif.py

输出：assets/demo.gif（360×576 / 12fps，控制在 3MB 以内）

尺寸说明
--------
游戏窗口是 600×960（手机竖屏比例），GIF 按 0.6 等比缩到 360×576 再存，
所以 GIF 里看到的画面比例和真机一致。别按横屏尺寸去缩——
那样棋盘会被压扁，箭头看着像被踩过。

体积控制
--------
GIF 是逐帧位图，体积基本正比于「像素数 × 颜色数 × 帧数」，三处都要压：

  * 分辨率 0.6 倍；
  * 调色板 128 色（画面本来就是大色块的扁平配色，看不出差别）；
  * 中段「一支一支点完剩下的」用快进录（step_scale），帧数直接除以倍率。

录制的路线（脚本里每一步都有注释，这里只说叙事）：

    开始界面 → 第 2 关 → 点掉一两支（看整条箭头飞出去）
    → 悬停被挡的箭头（红路径）→ 悬停通畅的箭头（绿路径）
    → 开辅助线 → 用一次提示 → 关辅助线 → 点错扣一颗心
    → 快进点完剩下的 → 通关结算面板

注意：脚本用**临时目录里的存档**，不会动你自己那份 progress.json。
"""

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
CAPTURE_FPS = 12                      # GIF 每秒的帧数（越小体积越小）
GRAB_EVERY = max(1, int(round(1.0 / (FRAME * CAPTURE_FPS))))
SCALE = 0.6                           # 600×960 -> 360×576，等比缩放
WIDTH = int(round(config.WINDOW_WIDTH * SCALE))
HEIGHT = int(round(config.WINDOW_HEIGHT * SCALE))
GIF_COLORS = 128                      # 转成多少色的调色板图（越小体积越小）


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


def main():
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
    #   * 转成 128 色的调色板图（GIF 本来也只支持 256 色，128 色几乎看不出差别）；
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
