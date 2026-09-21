# -*- coding: utf-8 -*-
"""闯关进度：记录已通关的关卡与每关的最高分，控制「过关才解锁下一关」。

刻意不依赖 pygame，这样解锁规则可以用普通的单元测试覆盖，
不用为了测一条 if 去创建窗口。

存档格式（JSON）：

    {"version": 2, "cleared": [0, 1, 2], "scores": {"0": 600, "1": 375}}

设计取舍：
  * 存档只记「哪些关通关了」和「每关最高多少分」，解锁状态每次由 cleared 推导，
    不做冗余存储，避免两份数据不一致。
  * 每关只留**最高分**：重玩一次手感不好，不该把纪录冲掉。
  * 分数不并进 cleared 里，历史存档（version 1，没有 scores 字段）读进来
    就等于「全都没得分」，不会因为升级存档格式而丢进度。
  * 读写失败（目录只读、文件损坏等）不会让游戏崩溃：读失败就当没有存档，
    写失败只在控制台警告一次——作业演示场景下「能继续玩」比「严格报错」更重要。
"""

import json
import os
import sys

# 存档文件名与版本号
PROGRESS_FILENAME = "progress.json"
PROGRESS_VERSION = 2

# 允许用环境变量指定存档位置（测试与截图脚本用，避免污染真实存档）
ENV_PATH = "ARROW_GAME_PROGRESS"

# 项目根目录（game/ 的上一级）
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def default_path():
    """存档的默认路径：环境变量优先，否则放在项目根目录。"""
    return os.environ.get(ENV_PATH) or os.path.join(BASE_DIR, PROGRESS_FILENAME)


class Progress:
    """玩家进度：哪些关卡已经通关、每关最高多少分，以及当前解锁到第几关。"""

    def __init__(self, path=None, cleared=None, scores=None, autoload=True):
        self.path = path or default_path()
        self.cleared = set(cleared or ())
        self.scores = {int(key): int(value) for key, value in dict(scores or {}).items()}
        self._warned = False
        if cleared is None and autoload:
            self.load()

    # ------------------------------------------------------------ 读写
    def load(self):
        """从磁盘读取存档；文件不存在或损坏时静默地当成空进度。"""
        try:
            with open(self.path, "r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, ValueError):
            return self

        if isinstance(data, dict):
            raw = data.get("cleared", [])
            self.scores = self._parse_scores(data.get("scores", {}))
        else:
            raw = data          # 兼容直接存成数组的旧格式

        if isinstance(raw, (list, tuple)):
            self.cleared = {int(item) for item in raw
                            if isinstance(item, int) or str(item).isdigit()}
        return self

    @staticmethod
    def _parse_scores(raw):
        """把存档里的 scores 解析成 {关卡下标: 分数}；坏数据一律忽略。

        JSON 的键只能是字符串，所以关号要转回 int；顺带过滤掉负数、
        非数字这些手改存档留下的垃圾值，避免界面上出现奇怪的分数。
        """
        scores = {}
        if not isinstance(raw, dict):
            return scores
        for key, value in raw.items():
            try:
                index = int(key)
                score = int(value)
            except (TypeError, ValueError):
                continue
            if index >= 0 and score > 0:
                scores[index] = score
        return scores

    def save(self):
        """把进度写回磁盘；失败只警告一次，不影响继续游戏。"""
        payload = {
            "version": PROGRESS_VERSION,
            "cleared": sorted(self.cleared),
            "scores": {str(index): self.scores[index] for index in sorted(self.scores)},
        }
        try:
            with open(self.path, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            return True
        except OSError as error:
            if not self._warned:
                print("[警告] 进度无法保存到 %s（%s），本次进度不会保留。"
                      % (self.path, error), file=sys.stderr)
                self._warned = True
            return False

    # ------------------------------------------------------------ 解锁规则
    def is_cleared(self, index):
        return index in self.cleared

    def highest_unlocked(self, total):
        """返回当前解锁的最大关卡下标（第 1 关永远解锁，所以至少是 0）。

        规则：只有通关了前一关，后一关才解锁。因此从前往后数，
        遇到第一个没通关的关卡就停下——它自己解锁，再往后就都锁着。
        """
        unlocked = 0
        for index in range(max(0, total - 1)):
            if index in self.cleared:
                unlocked = index + 1
            else:
                break
        return unlocked

    def is_unlocked(self, index, total):
        return 0 <= index <= self.highest_unlocked(total)

    def cleared_count(self, total):
        """已通关的关卡数量（只统计确实存在于关卡表里的下标）。"""
        return sum(1 for index in range(total) if index in self.cleared)

    def all_cleared(self, total):
        return self.cleared_count(total) >= total

    def next_index(self, total):
        """下一个该玩的关卡下标：第一个还没通关的关卡；全通关了则回到第 1 关。"""
        for index in range(total):
            if index not in self.cleared:
                return index
        return 0

    # ------------------------------------------------------------ 得分
    def best_score(self, index):
        """某关的历史最高分；没打过（或没得分）返回 0。"""
        return int(self.scores.get(index, 0))

    def total_score(self, total):
        """总分 = 各关最高分之和（只统计确实存在于关卡表里的下标）。"""
        return sum(self.best_score(index) for index in range(total))

    def record_score(self, index, value):
        """记下一次通关得分，只保留最高分；返回比原来多拿了多少分。

        返回值 0 表示没有刷新纪录（打得更差或一样好），
        调用方据此决定要不要在结果面板上标一句「刷新纪录」。
        """
        value = max(0, int(value))
        previous = self.best_score(index)
        if value <= previous:
            return 0
        self.scores[index] = value
        self.save()
        return value - previous

    # ------------------------------------------------------------ 修改
    def mark_cleared(self, index):
        """标记某关通关；返回 True 表示这是一次新通关（会写盘）。"""
        if index in self.cleared:
            return False
        self.cleared.add(index)
        self.save()
        return True

    def reset(self):
        """清空全部进度（含每关最高分），回到只解锁第 1 关的状态。"""
        self.cleared.clear()
        self.scores.clear()
        self.save()

    def mark_all_cleared(self, total):
        """用于测试与截图：一次性把所有关卡标记为已通关。"""
        self.cleared = set(range(total))
        self.save()
