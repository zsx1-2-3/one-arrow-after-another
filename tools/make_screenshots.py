# -*- coding: utf-8 -*-
"""在无头模式下渲染并保存游戏截图，供 README 与博客使用。

原理：把 SDL 的视频驱动设成 dummy，程序照常运行但不会真的弹出窗口，
再用 pygame.image.save() 把关键画面存成 PNG。

用法：
    python tools/make_screenshots.py

输出：assets/shot-01 ~ shot-11.png

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

from game import config  # noqa: E402
from game.app import Game  # noqa: E402
from game.levels import LEVELS, TOTAL_LEVELS  # noqa: E402
from game.progress import Progress  # noqa: E402

OUT_DIR = os.path.join(ROOT, "assets")
FRAME = 1.0 / 60.0


def level_index(name):
    """按关卡名取下标。

    写死数字的话，以后插一关 / 删一关（教学关独立出去就是这样）脚本会
    静默地截错关卡——改成按名字找，改名的时候这里会直接报错。
    """
    for index, level in enumerate(LEVELS):
        if level.name == name:
            return index
    raise SystemExit("关卡表里没有「%s」" % name)


# 截图里演示用到的关卡（教学关不在 LEVELS 里，走 start_tutorial 单独进）
CHAIN = level_index("连锁反应")
HOVER = level_index("四面楚歌")     # 用来展示红色路径与碰撞

# 截图前预先通关的关卡：让关卡总览呈现出「已通关 / 可挑战 / 未解锁」三种状态
PRECLEARED = (0, 1, 2, 3, 4)


def settle(game, seconds):
    """让动画推进指定的秒数。"""
    for _ in range(int(seconds / FRAME) + 1):
        game.update(FRAME)


def hover(game, row, col):
    """把鼠标"移动"到某个格子上，触发路径高亮。"""
    game.mouse_pos = game.cell_rect(row, col).center
    game.update_hover()


def unhover(game):
    game.mouse_pos = (-1, -1)
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


def find_blocked(board):
    """找一个此刻确实在棋盘上、且被挡住的箭头。"""
    for arrow in board.arrows:
        if board.arrow_at(arrow.row, arrow.col) is arrow and not board.can_fly(arrow.row, arrow.col):
            return arrow
    raise RuntimeError("没有找到被挡住的箭头")


def main():
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption(config.WINDOW_TITLE)

    # 用临时存档，模拟一个「已经玩到一半」的玩家
    save_path = os.path.join(tempfile.gettempdir(), "_arrow_screenshot_progress.json")
    if os.path.exists(save_path):
        os.remove(save_path)
    progress = Progress(path=save_path, autoload=False)
    for index in PRECLEARED:
        progress.cleared.add(index)
    game = Game(screen, progress=progress)

    # -------- 1. 开始界面：标题 + 玩法说明 + 示例 --------
    game.draw()
    save(screen, "shot-01-menu.png")

    # -------- 2. 关卡总览：已通关 / 可挑战 / 未解锁三种状态 --------
    game.enter_levels()
    game.draw()
    save(screen, "shot-02-levels.png")

    # -------- 3. 点未解锁的关卡会给出提示 --------
    game.mouse_pos = game.card_rects[TOTAL_LEVELS - 1].center
    game.update_hover()
    game.handle_click(game.card_rects[TOTAL_LEVELS - 1].center)
    game.draw()
    save(screen, "shot-03-level-locked.png")

    # -------- 4. 教学关：高亮环 + 底部逐步讲解（菜单上的独立入口）
    game.start_tutorial()
    game.mouse_pos = (-1, -1)
    game.update_hover()
    settle(game, 0.2)
    game.draw()
    save(screen, "shot-04-tutorial.png")

    # -------- 5. 游戏界面：悬停在被挡住的箭头上，路径显示为红色 --------
    game.start_level(HOVER)                 # 四面楚歌
    hover(game, 5, 1)                       # (5,1) 的「^」要走过 3 格才被 (1,1) 挡住
    game.draw()
    save(screen, "shot-05-board-hover.png")

    # -------- 6. 撞击反馈：点被挡住的箭头（抓动画中间帧） --------
    game.click_cell(5, 1)
    settle(game, 0.14)
    unhover(game)                           # 移开鼠标，避免路径高亮盖住撞击效果
    game.draw()
    save(screen, "shot-06-collision.png")

    # -------- 7. 飞出动画：第 3 关开一枪，抓中间帧 --------
    game.start_level(CHAIN)                 # 连锁反应
    hover(game, 1, 5)
    game.click_cell(1, 5)
    settle(game, 0.18)
    game.draw()
    save(screen, "shot-07-flyout.png")

    # -------- 8. 通关界面 --------
    game.start_level(HOVER)
    play_solution(game)
    settle(game, config.RESULT_DELAY + 0.2)
    game.draw()
    save(screen, "shot-08-win.png")

    # -------- 9. 失败界面：把生命值故意用光 --------
    game.start_level(HOVER)
    target = find_blocked(game.board)
    for _ in range(game.board.max_hp):
        game.click_cell(target.row, target.col)
        settle(game, 0.5)
    settle(game, config.RESULT_DELAY + 0.3)
    game.draw()
    save(screen, "shot-09-fail.png")

    # -------- 10. 全部通关界面 --------
    progress.mark_all_cleared(TOTAL_LEVELS)
    game.enter_levels()
    game.start_level(TOTAL_LEVELS - 1)
    play_solution(game)
    settle(game, config.RESULT_DELAY + 0.2)
    game.draw()
    save(screen, "shot-10-all-clear.png")

    # -------- 11. 最难的一关：9×9 棋盘塞满 50 支箭头，悬停显示被挡住的路径 --------
    game.start_level(TOTAL_LEVELS - 1)
    target = find_blocked(game.board)
    hover(game, target.row, target.col)
    game.draw()
    save(screen, "shot-11-final-level.png")

    pygame.quit()
    if os.path.exists(save_path):
        os.remove(save_path)
    print("\n全部截图已生成到 assets/ 目录。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
