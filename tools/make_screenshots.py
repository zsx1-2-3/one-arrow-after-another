# -*- coding: utf-8 -*-
"""在无头模式下渲染并保存游戏截图，供 README 与博客使用。

原理：把 SDL 的视频驱动设成 dummy，程序照常运行但不会真的弹出窗口，
再用 pygame.image.save() 把关键画面存成 PNG。

用法：
    python tools/make_screenshots.py

输出：assets/shot-01 ~ shot-16.png

两条不成文的规矩（踩过坑才立的）：

  * 脚本用**临时目录里的存档**，不会动你自己那份 progress.json；
  * 悬停、撞击这类画面要精确定位到某一格，所以一律**按状态找目标**
    （先问棋盘「哪一支被挡住了」再悬停过去），不写死坐标——
    关卡数据一改，写死的坐标就会静默指向别的箭头，截出来的图还是"能看"的，
    只是已经不能说明它要说明的那件事了。

还有一件事得先做：关卡的铺满率在 92% 以上，**开局盘面上几乎没有空格**。
不先点掉几支，红色被挡路径只有一格、绿色通畅路径根本不存在（射线长度为 0）。
所以演示路径的两张图（05 / 06）都是先按解法点掉几步、盘面出现空档之后再拍的。
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

from _showcase import (discard_progress, find_blocked, find_free,  # noqa: E402
                       fresh_progress, plan_balance, plan_long_green)
from game import config, ui  # noqa: E402
from game.app import Game  # noqa: E402
from game.levels import LEVELS, TOTAL_LEVELS  # noqa: E402

OUT_DIR = os.path.join(ROOT, "assets")
FRAME = 1.0 / 60.0


def level_index(name):
    """按关卡名取下标。

    写死数字的话，以后插一关 / 删一关脚本会静默地截错关卡——
    改成按名字找，改名的时候这里会直接报错。
    """
    for index, level in enumerate(LEVELS):
        if level.name == name:
            return index
    raise SystemExit("关卡表里没有「%s」" % name)


# 截图里演示用到的关卡（教学关不在 LEVELS 里，走 start_tutorial 单独进）
CHAIN = level_index("连锁反应")      # 中等难度，适合演示连锁
HOVER = level_index("四面楚歌")      # 用来展示红色路径与撞击
FINAL = TOTAL_LEVELS - 1             # 最难的一关

# 截图前预先通关的关卡：让关卡总览呈现出「已通关 / 可挑战 / 未解锁」三种状态
PRECLEARED = (0, 1, 2, 3, 4)

# 每个「要点掉几支才拍得出效果」的局面，都在这里先算好：
#   * 路径对照图（05/06）要红绿两条都有长度 -> plan_balance；
#   * 辅助线（14/15）要盘面够空，线才拉得长 -> plan_long_green。
# 放在模块级是刻意的：同一关的几张图共用同一个局面，对照起来才成立。
GAP_BALANCE_HOVER = plan_balance(LEVELS[HOVER], max_steps=6)
GAP_BALANCE_CHAIN = plan_balance(LEVELS[CHAIN], max_steps=6)
GAP_BALANCE_FINAL = plan_balance(LEVELS[FINAL], max_steps=6)
GAP_GUIDES_FINAL = plan_long_green(LEVELS[FINAL], max_steps=8, floor=7)


def settle(game, seconds):
    """让动画推进指定的秒数。"""
    for _ in range(int(seconds / FRAME) + 1):
        game.update(FRAME)


def hover(game, piece):
    """把鼠标"移动"到这支箭头的尾格上，触发路径高亮。

    点箭头身上任意一格都算选中它，所以悬停哪一格都一样，取尾格只是方便。
    """
    game.mouse_pos = game.cell_rect(*piece.tail).center
    game.update_hover()


def unhover(game):
    game.mouse_pos = (-1, -1)
    game.update_hover()


def save(screen, name):
    path = os.path.join(OUT_DIR, name)
    pygame.image.save(screen, path)
    print("已保存 %s" % os.path.relpath(path, ROOT))
    return path


def open_gap(game, index, steps):
    """进入第 index 关，按解法点掉前 steps 支，把盘面点出空档。

    步数由 _showcase 里的取景策略算好（plan_balance / plan_long_green）。
    不点空档的话，铺满的盘面上红色路径只有一格、绿色路径长度为 0，
    两张"路径"图都白拍。
    """
    game.start_level(index)
    game.toast_timer = 0.0
    solution = game.board.solution()
    for order in range(steps):
        game.click_cell(*solution[order].head)
        settle(game, 0.45)              # 等飞行动画播完
    unhover(game)


def play_solution(game):
    """按求解器给出的顺序把当前关卡打通。"""
    for piece in game.board.solution():
        game.click_cell(*piece.head)
        settle(game, 0.45)              # 等飞行动画播完


def main():
    pygame.init()
    screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    pygame.display.set_caption(config.WINDOW_TITLE)
    ui.clear_caches()

    # 用临时存档，模拟一个「已经玩到一半」的玩家
    progress, save_path = fresh_progress("screenshot", PRECLEARED)
    game = Game(screen, progress=progress)

    # -------- 1. 开始界面：标题 + 玩法说明 + 两张示例小图 --------
    game.draw()
    save(screen, "shot-01-menu.png")

    # -------- 2. 关卡总览：已通关 / 可挑战 / 未解锁三种状态 --------
    game.enter_levels()
    game.draw()
    save(screen, "shot-02-levels.png")

    # -------- 3. 点未解锁的关卡会给出提示 --------
    game.mouse_pos = game.card_rects[FINAL].center
    game.update_hover()
    game.handle_click(game.card_rects[FINAL].center)
    game.draw()
    save(screen, "shot-03-level-locked.png")

    # -------- 4. 教学关：高亮环 + 底部逐步讲解（菜单上的独立入口） --------
    game.start_tutorial()
    unhover(game)
    settle(game, 0.2)
    game.draw()
    save(screen, "shot-04-tutorial.png")

    # -------- 5 / 6. 同一局面下的两条路径：红=被挡，绿=通畅 --------
    # 两张图故意拍同一局面，放在一起才看得出差别只在"前方通不通"。
    open_gap(game, HOVER, GAP_BALANCE_HOVER)
    hover(game, find_blocked(game.board))
    game.draw()
    save(screen, "shot-05-hover-blocked.png")

    hover(game, find_free(game.board))
    game.draw()
    save(screen, "shot-06-hover-clear.png")

    # -------- 7. 撞击反馈：点一支被挡住的箭头（抓动画中间帧） --------
    open_gap(game, HOVER, GAP_BALANCE_HOVER)
    blocked = find_blocked(game.board)
    game.click_cell(*blocked.cells[0])
    settle(game, 0.12)
    unhover(game)                    # 移开鼠标，避免路径高亮盖住撞击效果
    game.draw()
    save(screen, "shot-07-collision.png")

    # -------- 8. 飞出动画：整条箭头滑出棋盘（抓中间帧） --------
    open_gap(game, CHAIN, GAP_BALANCE_CHAIN)
    free = find_free(game.board)
    hover(game, free)
    game.click_cell(*free.head)
    settle(game, 0.16)
    game.draw()
    save(screen, "shot-08-flyout.png")

    # -------- 9. 通关界面 --------
    game.start_level(HOVER)
    play_solution(game)
    settle(game, config.RESULT_DELAY + 0.2)
    game.draw()
    save(screen, "shot-09-win.png")

    # -------- 10. 失败界面：把生命值故意用光 --------
    game.start_level(HOVER)
    blocked = find_blocked(game.board)
    for _ in range(game.board.max_hp):
        game.click_cell(*blocked.cells[0])
        settle(game, 0.5)
    settle(game, config.RESULT_DELAY + 0.3)
    game.draw()
    save(screen, "shot-10-fail.png")

    # -------- 11. 全部通关界面 --------
    progress.mark_all_cleared(TOTAL_LEVELS)
    game.enter_levels()
    game.start_level(FINAL)
    play_solution(game)
    settle(game, config.RESULT_DELAY + 0.2)
    game.draw()
    save(screen, "shot-11-all-clear.png")

    # -------- 12. 最难的一关：26×18 棋盘铺满箭头，悬停显示被挡住的路径 --------
    open_gap(game, FINAL, GAP_BALANCE_FINAL)
    hover(game, find_blocked(game.board))
    game.draw()
    save(screen, "shot-12-final-level.png")

    # -------- 13. 提示：高亮一支「点掉它最能解锁局面」的箭头 --------
    game.start_level(HOVER)
    unhover(game)
    game.use_hint()
    settle(game, 0.25)               # 等呼吸环胀到中间那一帧
    game.draw()
    save(screen, "shot-13-hint.png")

    # -------- 14. 辅助线：给每支箭头画出它箭头前方的去路 --------
    open_gap(game, FINAL, GAP_GUIDES_FINAL)
    game.toggle_guides()
    game.toast_timer = 0.0           # 气泡会盖住棋盘，截图里不需要它
    unhover(game)
    settle(game, 0.2)
    game.draw()
    save(screen, "shot-14-guides.png")

    # -------- 15. 放大 + 拖动：棋盘满屏时放大看边角 --------
    open_gap(game, FINAL, GAP_GUIDES_FINAL)
    game.toggle_guides()             # 关掉辅助线，这张图只看缩放
    game.toast_timer = 0.0
    game.set_zoom_ratio(1.0)         # 放到最大
    game.pan = [200, 200]
    game.layout_board()
    unhover(game)
    game.draw()
    save(screen, "shot-15-zoomed.png")

    # -------- 16. 日间主题 + 设置面板 --------
    game.toggle_theme()
    game.toast_timer = 0.0
    game.restart_level()             # 顺便把缩放 / 平移复位（重开会回到 100%）
    game.toast_timer = 0.0
    game.open_settings()
    game.draw()
    save(screen, "shot-16-settings-day.png")

    # 复位，免得把主题留在日间影响后续
    game.toggle_theme()
    game.close_overlay()

    pygame.quit()
    discard_progress(save_path)
    print("\n全部截图已生成到 assets/ 目录。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
