# -*- coding: utf-8 -*-
"""《一箭又一箭》游戏入口。

运行方式：
    python main.py

操作：
    鼠标左键点击箭头     让它尝试飞出棋盘
    鼠标左键点击按钮     开始 / 继续 / 重开 / 下一关 / 关卡总览 / 返回主菜单
    R                    重新开始本关
    空格                 在开始界面或关卡总览里继续挑战
    Esc                  返回主菜单或关卡总览（在开始界面按下则退出游戏）

闯关进度会保存在项目根目录的 progress.json 里，通关一关才会解锁下一关。
"""

import sys

import pygame

from game import config, ui
from game.app import Game


# 屏幕装不下逻辑分辨率时的缩放下限：再小按钮和文字就挤成一团了
MIN_WINDOW_SCALE = 0.45


def _setup_screen():
    """决定窗口大小，返回 (给 Game 用的画布, 实际窗口, 缩放比)。

    逻辑分辨率永远是 config 里的 680×880——所有界面代码、截图脚本、
    测试都只认这一套坐标。屏幕装不下时开一个更小的窗口，把整幅逻辑
    画面 smoothscale 缩进去（等比、带抗锯齿），鼠标坐标再按比例换算
    回来——游戏代码完全不用感知缩放，电脑上也能看到完整界面。
    """
    try:
        info = pygame.display.Info()
    except pygame.error:
        info = None
    scale = 1.0
    if info is not None and info.current_w > 0:
        scale = min(1.0,
                    (info.current_w - 60) / config.WINDOW_WIDTH,
                    (info.current_h - 90) / config.WINDOW_HEIGHT)
        scale = max(scale, MIN_WINDOW_SCALE)
    if scale >= 1.0:
        window = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        return window, window, 1.0
    window = pygame.display.set_mode((int(config.WINDOW_WIDTH * scale),
                                      int(config.WINDOW_HEIGHT * scale)))
    canvas = pygame.Surface((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
    return canvas, window, scale


def _rescale_event(event, scale):
    """把窗口坐标系的鼠标事件换算成逻辑画布坐标系（缩小窗口时用）。"""
    if scale >= 1.0 or not hasattr(event, "pos") or event.pos is None:
        return event
    event.pos = (event.pos[0] / scale, event.pos[1] / scale)
    if getattr(event, "rel", None) is not None:
        event.rel = (event.rel[0] / scale, event.rel[1] / scale)
    return event


def main():
    pygame.init()
    try:
        canvas, window, scale = _setup_screen()
    except pygame.error as error:            # 例如没有可用的显示设备
        print("无法创建游戏窗口：%s" % error)
        return 1
    pygame.display.set_caption(config.WINDOW_TITLE)

    if not ui.has_cjk_font():
        print("[警告] 未找到中文字体，界面中的中文可能显示为方块。")

    clock = pygame.time.Clock()
    game = Game(canvas)

    while game.running:
        delta = clock.tick(config.FPS) / 1000.0
        for event in pygame.event.get():
            game.handle_event(_rescale_event(event, scale))
        game.update(min(delta, 0.05))        # 卡顿时限制单帧步长，避免动画跳帧
        game.draw()
        if scale < 1.0:                      # 逻辑画面等比缩进实际窗口
            pygame.transform.smoothscale(canvas, window.get_size(), window)
        pygame.display.flip()

    pygame.quit()
    return 0


if __name__ == "__main__":
    sys.exit(main())
