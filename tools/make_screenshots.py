# -*- coding: utf-8 -*-
"""在无头模式下渲染并保存游戏截图，供 README 与博客使用。

原理：把 SDL 的视频驱动设成 dummy，程序照常运行但不会真的弹出窗口，
再用 pygame.image.save() 把关键画面存成 PNG。

用法：
    python tools/make_screenshots.py

输出：assets/shot-*.png
"""

import os
import sys

# 必须在 import pygame 之前设置，才能进入无头模式
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import pygame  # noqa: E402

from game import config  # noqa: E402
from game.app import Game  # noqa: E402

OUT_DIR = os.path.join(ROOT, "assets")
FRAME = 1.0 / 60.0


def settle(game, seconds):
    """让动画推进指定的秒数。"""
    for _ in range(int(seconds / FRAME) + 1):
        game.update(FRAME)


def hover(game, row, col):
    """把鼠标"移动"到某个格子上，触发路径高亮。"""
    game.mouse_pos = game.cell_rect(row, col).center
    game.update_hover()


def save(screen, name):
    path = os.path.join(OUT_DIR, name)
    pygame.image.save(screen, path)
    print("已保存 %s" % os.path.relpath(path, ROOT))
    return path


def play_solution(game):
    """按求解器给出的顺序把当前关卡打通。"""
    for row, col in game.board.solution():
        game.click_cell(row, col)
        settle(game, 0.5)          # 等飞行动画播完（飞出 0.45 秒）


def main():
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption(config.WINDOW_TITLE)
    game = Game(screen)

    # -------- 1. 开始界面 --------
    game.draw()
    save(screen, "shot-01-menu.png")

    # -------- 2. 游戏界面：悬停在被挡住的箭头上，路径显示为红色 --------
    game.start_level(1)                     # 第 2 关「交叉路口」
    hover(game, 1, 1)                       # (row=1, col=1) 的「>」被 (1,3) 的「v」挡住
    game.draw()
    save(screen, "shot-02-board-hover.png")

    # -------- 3. 撞击反馈：点被挡住的箭头 --------
    game.click_cell(1, 1)
    settle(game, 0.14)
    game.mouse_pos = (-1, -1)            # 把鼠标移开，避免路径高亮盖住撞击效果
    game.update_hover()
    game.draw()
    save(screen, "shot-03-collision.png")

    # -------- 4. 通关这件事：打完这一关 --------
    play_solution(game)
    settle(game, config.RESULT_DELAY + 0.2)
    game.draw()
    save(screen, "shot-04-win.png")

    # -------- 5. 飞出动画：第 3 关开一枪，抓中间帧 --------
    game.start_level(2)                     # 第 3 关「连锁反应」
    hover(game, 1, 5)
    game.click_cell(1, 5)
    settle(game, 0.18)
    game.draw()
    save(screen, "shot-05-flyout.png")

    # -------- 6. 失败界面：第 4 关只有 2 次失误 --------
    game.start_level(3)
    game.click_cell(5, 3)                   # 「<」被左边的「^」挡住
    settle(game, 0.5)
    game.click_cell(5, 3)
    settle(game, config.RESULT_DELAY + 0.3)
    game.draw()
    save(screen, "shot-06-fail.png")

    # -------- 7. 全部通关界面 --------
    game.start_level(3)
    play_solution(game)
    settle(game, config.RESULT_DELAY + 0.2)
    game.draw()
    save(screen, "shot-07-all-clear.png")

    pygame.quit()
    print("\n全部截图已生成到 assets/ 目录。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
