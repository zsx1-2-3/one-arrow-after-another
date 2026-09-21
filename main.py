# -*- coding: utf-8 -*-
"""《一箭又一箭》游戏入口。

运行方式：
    python main.py

操作：
    鼠标左键点击箭头     让它尝试飞出棋盘
    鼠标左键点击按钮     开始 / 重开 / 下一关 / 返回主菜单
    R                    重新开始本关
    Esc                  返回主菜单（在开始界面按下则退出游戏）
"""

import sys

import pygame

from game import config, ui
from game.app import Game


def main():
    pygame.init()
    try:
        screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    except pygame.error as error:            # 例如没有可用的显示设备
        print("无法创建游戏窗口：%s" % error)
        return 1
    pygame.display.set_caption(config.WINDOW_TITLE)

    if not ui.has_cjk_font():
        print("[警告] 未找到中文字体，界面中的中文可能显示为方块。")

    clock = pygame.time.Clock()
    game = Game(screen)

    while game.running:
        delta = clock.tick(config.FPS) / 1000.0
        for event in pygame.event.get():
            game.handle_event(event)
        game.update(min(delta, 0.05))        # 卡顿时限制单帧步长，避免动画跳帧
        game.draw()
        pygame.display.flip()

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
