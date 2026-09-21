# -*- coding: utf-8 -*-
"""得分规则：生命值留得越多，得分越高。

规则
----
一关能拿多少分，只由两件事决定——**这关有多难**（难度星级）和
**这一关里丢了几颗心**：

    基础分   = 星级 × 250                    难度越高，底分越高（1 星 250 … 5 星 1250）
    本关得分 = 基础分 × 剩余生命值 ÷ 生命值上限
    完美奖励 = 一颗心都没丢时，再额外 +20% 基础分

于是「本关满分 = 星级 × 300」。每丢一颗心都会按比例扣掉一部分，
而生命值上限是**按难度给的**（见 levels.HP_BY_STARS）：越难的关卡心越多，
丢一颗心扣掉的比例反而越小，容错随难度一起变高——
这和「按难度给生命值」本来就是同一件事的两面。

生命值耗尽（失败）不给分：先通关，再谈分数。重玩只保留最高分，不会越玩越低。

为什么按比例折算，而不是「每错一次扣固定分」：
    生命值上限逐关变大，固定扣分会让后面的关卡因为心多而显得无所谓
    （第 9 关丢 1 颗心还剩 6 颗，扣的却和第 1 关一样多）。
    按比例折算则始终是「这一颗心占本关全部容错的多大一份」，
    越到后面越宽容，和玩家的直觉一致。
"""

SCORE_PER_STAR = 250         # 每颗难度星对应的基础分
PERFECT_BONUS_RATIO = 0.2    # 零失误奖励：基础分的 20%


def base_score(level):
    """本关基础分 = 星级 × 250。"""
    return level.stars * SCORE_PER_STAR


def perfect_bonus(level):
    """零失误奖励分 = 基础分的 20%（向下取整）。"""
    return int(base_score(level) * PERFECT_BONUS_RATIO)


def max_score(level):
    """本关满分 = 基础分 + 零失误奖励 = 星级 × 300。"""
    return base_score(level) + perfect_bonus(level)


def lost_hearts(level, hp_left):
    """本关已经失去的生命值（点错了几次），失败时等于上限。"""
    return max(0, min(level.max_hp, level.max_hp - hp_left))


def level_score(level, hp_left):
    """按剩余生命值折算本关得分；生命值耗尽返回 0。

    整数运算，不引入浮点误差；一手未错时再加上完美奖励。
    """
    if hp_left <= 0:
        return 0
    hp_left = min(hp_left, level.max_hp)                 # 防止越界传参
    score = base_score(level) * hp_left // level.max_hp
    if hp_left == level.max_hp:
        score += perfect_bonus(level)
    return score


def total_max_score(levels):
    """全部关卡的满分之和（界面上的「总分 x / y」用它的 y）。"""
    return sum(max_score(level) for level in levels)
