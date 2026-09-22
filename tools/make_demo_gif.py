# -*- coding: utf-8 -*-
"""录制一段演示 GIF，放进 README 与博客里当作「项目展示」。

原理和 make_screenshots.py 一样：SDL 用 dummy 驱动无头渲染，
区别是这次不停在单张画面，而是连续抓帧再交给 Pillow 拼成 GIF。

用法：
    python tools/make_demo_gif.py

输出：assets/demo.gif（约 480×360 / 12fps，控制在 3MB 以内）

演示脚本走的是一条「能一次讲清玩法」的路线：

    开始界面 → 第 2 关（只有一支能飞）→ 悬停看红色路径
    → 开辅助线、点一次提示 → 点错掉一颗心 → 点对飞出
    → 连着点完剩下的 → 通关结算面板

注意：脚本用**临时目录里的存档**，不会动你自己那份 progress.json。
"""

import os
import sys
import tempfile

# 必须在 import pygame 之前设置，才能进入无头模式
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402
from PIL import Image  # noqa: E402

from game import config  # noqa: E402
from game.app import Game  # noqa: E402
from game.levels import LEVELS  # noqa: E402
from game.progress import Progress  # noqa: E402

OUT_PATH = os.path.join(ROOT, "assets", "demo.gif")

FRAME = 1.0 / 60.0
CAPTURE_FPS = 12                      # GIF 每秒的帧数（越小体积越小）
GRAB_EVERY = max(1, int(round(1.0 / (FRAME * CAPTURE_FPS))))
WIDTH, HEIGHT = 480, 360              # 缩放后的尺寸，避免 GIF 过大


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


def record(game, screen, frames, seconds):
    """推进 seconds 秒，同时按 CAPTURE_FPS 抽帧存进 frames。"""
    for step in range(int(seconds / FRAME) + 1):
        game.update(FRAME)
        game.draw()
        if step % GRAB_EVERY == 0:
            frames.append(capture(screen))


def main():
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption(config.WINDOW_TITLE)

    save_path = os.path.join(tempfile.gettempdir(), "_arrow_demo_progress.json")
    if os.path.exists(save_path):
        os.remove(save_path)
    # 关掉自动读取，避免录演示时把真实进度念进来
    progress = Progress(path=save_path, autoload=False)
    # 第 2 关「交叉路口」最适合演示「找出唯一的出口」：全场只有一支能直接飞。
    # 但 start_level 和真实玩家走同一套解锁判定，未解锁会直接拒绝开局，
    # 所以先把第 1 关标记成已通关。
    progress.cleared.add(0)
    game = Game(screen, progress=progress)

    frames = []

    # -------- 1. 开始界面（玩法说明 + 主按钮） --------
    game.draw()
    record(game, screen, frames, 0.9)

    # -------- 2. 进入第 2 关：全场只有一支能直接飞 --------
    game.start_level(level_index("交叉路口"))
    game.mouse_pos = (-1, -1)
    game.update_hover()
    record(game, screen, frames, 0.5)

    # -------- 3. 悬停在一支被挡住的箭头上：路径显示为红色 --------
    target = None
    for arrow in game.board.arrows:
        if game.board.arrow_at(arrow.row, arrow.col) is arrow \
                and not game.board.can_fly(arrow.row, arrow.col):
            target = arrow
            break
    if target is None:
        raise SystemExit("第 2 关里没有找到被挡住的箭头")

    game.mouse_pos = game.cell_rect(target.row, target.col).center
    game.update_hover()
    record(game, screen, frames, 0.7)

    # 解的顺序现在就算好：开局之后还要故意点错一次，
    # 但那次点击不会消除箭头，棋盘布局没变，解依然有效。
    solution = game.board.solution()

    # -------- 3.5 打开辅助线 + 用一次提示：这一版新加的两个小工具 --------
    # 放在这里是因为此刻棋盘还是开局状态，最能看出它们在帮什么忙：
    # 辅助线把每支箭头的去路画出来，提示再直接指出先点哪一支。
    game.toggle_guides()
    game.toast_timer = 0.0              # 气泡会挡住棋盘，演示里不需要它
    record(game, screen, frames, 0.8)

    game.use_hint()
    record(game, screen, frames, 1.0)

    game.toggle_guides()
    game.toast_timer = 0.0
    record(game, screen, frames, 0.3)

    # -------- 4. 点错：撞击抖动 + 飘出一颗碎心，生命值 -1 --------
    game.click_cell(target.row, target.col)
    game.mouse_pos = (-1, -1)
    game.update_hover()
    record(game, screen, frames, 1.0)

    # -------- 5. 按求解器顺序把这一关打完（前两步慢一点，后面快进） --------
    for order, (row, col) in enumerate(solution):
        game.click_cell(row, col)
        game.mouse_pos = game.cell_rect(row, col).center
        game.update_hover()
        # 第一步留足看清「飞出」的时间，后面几步加快，避免 GIF 太长
        record(game, screen, frames, 0.62 if order == 0 else 0.30)
    game.mouse_pos = (-1, -1)
    game.update_hover()

    # -------- 6. 通关结算面板：本关得分 + 完美奖励 --------
    record(game, screen, frames, config.RESULT_DELAY + 1.4)

    pygame.quit()

    # -------- 拼成 GIF --------
    # 转成 128 色的调色板图，体积能小一大半；GIF 本来也只支持 256 色
    palette = [frame.convert("P", palette=Image.ADAPTIVE, colors=128) for frame in frames]
    palette[0].save(
        OUT_PATH,
        save_all=True,
        append_images=palette[1:],
        duration=int(1000 / CAPTURE_FPS),
        loop=0,
        optimize=True,
        disposal=2,
    )

    if os.path.exists(save_path):
        os.remove(save_path)

    size_kb = os.path.getsize(OUT_PATH) / 1024.0
    print("已保存 %s（%d 帧 / %.1f 秒 / %.0f KB）"
          % (os.path.relpath(OUT_PATH, ROOT), len(palette),
             len(palette) / float(CAPTURE_FPS), size_kb))
    return 0


if __name__ == "__main__":
    sys.exit(main())
