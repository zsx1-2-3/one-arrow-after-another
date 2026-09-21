# -*- coding: utf-8 -*-
"""《一箭又一箭》—— 点击式箭头解谜小游戏。

模块划分（逻辑与界面解耦，方便单独测试）：

    config.py   全局配置：窗口尺寸、配色、字体路径、动画参数
    board.py    棋盘核心逻辑：路径检测、箭头消除、生命值结算（不依赖 pygame）
    levels.py   关卡数据：用 ASCII 字符描述的棋盘布局
    progress.py 闯关进度：已通关关卡、逐关解锁、JSON 存档（不依赖 pygame）
    ui.py       绘图工具：字体、文字、按钮、箭头与心形图标
    anim.py     动画效果：飞出、撞击抖动、飘字
    app.py      游戏主体：三场景状态机、教学引导、事件分发、渲染
"""

__version__ = "1.1.0"
__all__ = ["config", "board", "levels", "progress", "ui", "anim", "app"]
