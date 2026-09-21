# -*- coding: utf-8 -*-
"""《一箭又一箭》—— 点击式箭头解谜小游戏。

模块划分（逻辑与界面解耦，方便单独测试）：

    config.py   全局配置：窗口尺寸、配色、字体路径、动画参数
    board.py    棋盘核心逻辑：路径检测、箭头消除、失误计数（不依赖 pygame）
    levels.py   关卡数据：用 ASCII 字符描述的棋盘布局
    ui.py       绘图工具：字体、文字、按钮、箭头图形
    anim.py     动画效果：飞出、撞击抖动、飘字
    app.py      游戏主体：场景状态机、事件分发、渲染
"""

__version__ = "1.0.0"
__all__ = ["config", "board", "levels", "ui", "anim", "app"]
