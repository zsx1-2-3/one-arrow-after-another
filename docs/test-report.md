# 测试与关卡校验报告

本文件记录《一箭又一箭》的自动化测试结果与关卡可解性校验结果，对应作业要求中的
「5. 测试要求」与「3.1 至少设计 3 个可以正常通关的关卡」。

* 测试用例总数：**103 个，全部通过**
* 关卡校验：**教学关 + 9 个编号关卡全部可解**（`tools/verify_levels.py` 退出码 0）
* 本文件里的输出全部是真实运行的结果，没有手工润色过的数字

---

## 一、测试环境

| 项目 | 内容 |
| --- | --- |
| 操作系统 | Windows 11 |
| Python | 3.11.3 |
| Pygame | 2.6.1（SDL 2.28.4） |
| 运行方式 | 无头模式（`SDL_VIDEODRIVER=dummy`），不需要显示器 |
| 测试框架 | 标准库 `unittest` |

执行命令：

```bash
python tests/test_game.py
# 或（带每个用例的说明）
python -m unittest discover -s tests -v
```

## 二、总体结果

```
Ran 103 tests in 1.996s

OK
```

103 个用例全部通过，分为八组：

| 测试类 | 用例数 | 覆盖内容 |
| --- | --- | --- |
| `BoardRuleTestCase` | 11 | 单次点击的规则判定（T01~T03、边界、生命值、复位） |
| `SolverTestCase` | 15 | 10 个关卡的可解性、难度阶梯、尺寸冻结、教学关数据合法性 |
| `LevelBalanceTestCase` | 4 | 生命值按难度给、容错逐关变高、星级从 1 铺到 5 |
| `ScoringTestCase` | 6 | 得分公式、完美奖励、失败 0 分、总分上限 |
| `ColorSpreadTestCase` | 4 | 布局同色扎堆比例、打散后仍可解且没变简单 |
| `ProgressTestCase` | 12 | 进度存档的读写、解锁计算、损坏容错、最高分 |
| `GameFlowTestCase` | 39 | 场景切换、关卡总览、解锁链路、教学引导、T04~T06、结算面板、计时 / 提示 / 辅助线、界面分区 |
| `VisualVarietyTestCase` | 12 | 四方向配色亮度、中文折行、背景动效、像素心图标 |

> 用例数是从 `tests/test_game.py` 里现数的（按 `def test_` 前缀统计），
> 不是沿用上一版的数字——项目每加一轮功能，这个数就会变。

---

## 三、作业要求的六个测试用例

| 编号 | 测试内容 | 预期结果 | 实际结果 |
| --- | --- | --- | --- |
| T01 | 点击前方无阻挡的箭头 | 箭头飞出棋盘并消失 | ✅ 通过 |
| T02 | 点击前方有阻挡的箭头 | 箭头不消失，失误次数减 1 | ✅ 通过 |
| T03 | 点击位于边缘且朝向棋盘外的箭头 | 箭头正常消失，不发生越界错误 | ✅ 通过 |
| T04 | 消除本关全部箭头 | 显示通关并进入下一关 | ✅ 通过 |
| T05 | 失误次数耗尽 | 显示失败并允许重新开始 | ✅ 通过 |
| T06 | 游戏进行中重新开始 | 箭头布局和失误次数恢复 | ✅ 通过 |

> 说明：本作的「失误次数」做成了**生命值**（用像素心表示，点错一次丢一颗心），
> 判定逻辑与作业要求完全一致，只是换了一个更直观的呈现方式和更自然的字段语义。

### 每个用例的具体做法

* **T01**（`test_t01_click_free_arrow_flies_out`）：在测试关卡点击 `(1,2)` 处朝下的箭头
  （下方无阻挡），断言返回 `fly`、该格变空、剩余箭头 3 → 2、生命值仍为满。
* **T02**（`test_t02_click_blocked_arrow_costs_hp`）：点击 `(1,1)` 处朝右的箭头
  （被 `(1,2)` 处的箭头挡住），断言返回 `blocked`、记录的阻挡者坐标是 `(1,2)`、
  箭头仍在原位、剩余箭头数不变、生命值 4 → 3。
* **T03**（`test_t03_arrows_on_the_edge_fly_out_safely`）：构造两条边界布局并逐个点击：

  * `.^..` / `...>` / `<...` / `..v.` —— 四条边各一支朝向棋盘外的箭头；
  * `v...` / `....` / `....` / `...^` —— 四个角各一支朝棋盘内部的箭头。

  对每次点击断言返回 `fly`，并额外断言 `path_cells()` 返回的所有坐标都落在棋盘内、
  且 `remaining` 最终归零、状态变为 `cleared`（不出现索引越界）。
* **T04**（`test_t04_clear_level_then_go_to_next_level`）：按求解器给出的顺序点完第 1 关 →
  断言 `state == cleared`、剩余箭头为 0；推进 1.5 秒 → 断言弹出通关面板；
  再点击面板上的「下一关」按钮 → 断言关卡序号 +1、场景仍为游戏界面、棋盘已按新关卡重新初始化。
  另外单独验证打完第 9 关（最后一关）会出现「全部通关」面板。
* **T05**（`test_t05_fail_then_restart`）：反复点击一支被挡住的箭头，直到生命值扣到 0 →
  断言 `state == failed`、生命值为 0；推进 1.5 秒 → 断言弹出失败面板；
  点击「重新开始本关」→ 断言面板关闭、状态回到进行中、生命值回满、箭头全部复位。
* **T06**（`test_t06_restart_mid_game`）：用第 2 关（交叉路口）来测——
  它同时存在「能飞」和「被挡住」的箭头，而教学关里消掉一支之后全场就畅通了，制造不出失误。
  先点掉一支可以直接飞出的箭头（剩余箭头减少），再故意点一次被挡住的箭头（生命值 -1）
  → 点击「重新开始」按钮 → 断言剩余箭头数恢复为总数、生命值回满、状态回到进行中，
  并且**逐个断言每支箭头都回到了它原来的格子**。

---

## 四、玩法机制对应的用例

除了作业要求的六条，核心玩法机制每一项都有对应用例兜底。

### 4.1 生命值（失误次数）

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_hp_drops_one_per_blocked_click` | 点错一次固定扣 1 点生命值；扣到 0 就失败，且不会再往下扣成负数 | ✅ |
| `test_fail_when_hp_used_up` | 生命值用尽后棋盘进入失败状态 | ✅ |
| `test_hp_is_granted_by_difficulty` | 每关的生命值必须正好是「星级 → 生命值」表里对应的值 | ✅ |
| `test_tolerance_grows_from_first_level_to_last` | 生命值上限整体不下降，最后一关明显比第 1 关宽容（4 → 7 颗心） | ✅ |
| `test_one_mistake_hurts_less_on_harder_levels` | 点错一次的代价逐关变小（37.7% → 28.6%），这是「容错越来越高」的量化说法 | ✅ |
| `test_tutorial_is_a_forgiving_sandbox` | 教学关是给人放胆点的沙盒，生命值比同星级关卡更宽裕 | ✅ |
| `test_blocked_click_pops_a_broken_heart_not_hanzi` | 点错时飘出来的是一颗「碎掉的像素心」，而不是「失去一心」四个汉字 | ✅ |
| `test_broken_heart_animation_renders_and_fades_out` | 心碎动画：两半分开、心往上飘、末端淡出，每一帧都画得出来 | ✅ |
| `test_hud_hearts_are_pixel_hearts` | HUD 那一排生命值画的也是像素心：还有的用亮色、失去的用暗色 | ✅ |
| `test_heart_icon_is_a_pixel_art_grid` | 生命值图标是规整网格：左右对称、顶部中间留凹口、底部有尖 | ✅ |
| `test_lost_heart_is_an_empty_outline` | 已经失去的那颗心只剩外沿，内部镂空，和实心的一眼能区分 | ✅ |

### 4.2 得分机制

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_full_score_follows_the_difficulty_stars` | 满分 = 星级 × 300（基础分 250 + 20% 完美奖励） | ✅ |
| `test_perfect_bonus_only_when_nothing_is_lost` | 零失误奖励只在满心通关时给，而且正好是基础分的 20% | ✅ |
| `test_every_mistake_costs_points` | 同一关里，失去的心越多得分越低，且是严格下降 | ✅ |
| `test_failing_the_level_is_worth_nothing` | 生命值耗尽时本关 0 分（越界的参数也不会算出一个负数） | ✅ |
| `test_total_full_score_is_the_sum_of_all_levels` | 九关满分合计 9300 分 | ✅ |
| `test_board_exposes_a_live_score` | 棋盘自己就知道当前能拿多少分，HUD 直接用这个数（点错立刻掉） | ✅ |
| `test_clearing_without_mistakes_pays_the_full_score` | 零失误通关：拿满分、记进存档，结算面板写出完美奖励 | ✅ |
| `test_every_mistake_lowers_the_score` | 丢一颗心，HUD 上的得分立刻按比例下降，最终结算也跟着少 | ✅ |
| `test_a_worse_replay_keeps_the_old_record` | 重玩打得差不会把最高分冲掉（存档只记最好的一次） | ✅ |

### 4.3 关卡总览与解锁

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_level_select_lists_all_levels` | 关卡总览里每张卡片对应一个关卡，数量与 `LEVELS` 一致 | ✅ |
| `test_clicking_an_unlocked_card_starts_that_level` | 点已解锁的卡片直接开局，且进入的是那一关 | ✅ |
| `test_clicking_a_locked_card_only_shows_a_hint` | 点未解锁的卡片不会开局，只提示要先通关哪一关 | ✅ |
| `test_locked_level_cannot_be_started` | 绕过界面直接调用开局也一样被拦住 | ✅ |
| `test_clearing_a_level_unlocks_the_next_one` | 通关后下一关立刻变为可进入 | ✅ |
| `test_primary_button_follows_progress` | 主按钮文字随进度变化：从「开始游戏」到「继续第 N 关」 | ✅ |
| `test_all_levels_can_be_cleared_in_order` | 按顺序把 9 关全部打通，验证整条解锁链可用 | ✅ |
| `test_only_first_level_unlocked_at_start` | 全新存档只解锁第 1 关 | ✅ |
| `test_clearing_unlocks_the_next_level` | 通关一关才解锁下一关 | ✅ |
| `test_skipping_a_level_does_not_unlock_further` | 跳着通关不算数：第 2 关没过，第 3 关依然锁着 | ✅ |
| `test_reset_clears_everything` | 清空进度后回到只解锁第 1 关，最高分一并清掉并且已落盘 | ✅ |
| `test_reset_progress_needs_two_clicks` | 「清空进度」要点两次才真的清，避免手滑 | ✅ |
| `test_save_and_reload` | 存档写到磁盘后能被重新读回来 | ✅ |
| `test_mark_cleared_is_idempotent` | 重复标记同一关不会出错，也不重复写盘 | ✅ |
| `test_missing_or_broken_save_file_is_tolerated` | 存档不存在或内容损坏时当成空进度，而不是崩溃 | ✅ |
| `test_old_save_without_scores_still_loads` | 老存档（version 1，没有 scores 字段）不会因为升级格式丢进度 | ✅ |
| `test_broken_scores_in_the_save_file_are_ignored` | 存档里的分数被人手改坏了（非数字、负数）时，只丢掉坏的那几条 | ✅ |
| `test_scores_are_recorded_and_only_the_best_one_wins` | 每关只留最高分：重玩手感差不会把纪录冲掉 | ✅ |
| `test_total_score_is_the_sum_of_each_levels_best` | 总分 = 各关最高分之和；不存在关卡里的分数不计入 | ✅ |
| `test_cleared_count_next_index_and_all_cleared` | 已通关数量、「下一关」取值、「全部通关」判定 | ✅ |

### 4.4 教学关

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_tutorial_is_not_a_numbered_level` | 教学关独立于关卡表：不占第 1 关的位置，也不参与编号 | ✅ |
| `test_tutorial_has_its_own_entry_on_the_menu` | 教学关是菜单上的独立入口：不用解锁，点了就能进 | ✅ |
| `test_tutorial_steps_advance_one_by_one` | 照着引导点，步骤一步步推进，最后引导结束 | ✅ |
| `test_tutorial_resyncs_when_player_deviates` | 玩家不按提示点时，引导自动跳过已失效的步骤，不卡住 | ✅ |
| `test_tutorial_ring_only_drawn_for_current_step` | 引导高亮只在教学关且步骤未走完时出现 | ✅ |
| `test_tutorial_level_must_have_steps` | 教学关必须带引导步骤，否则界面上没有任何提示 | ✅ |
| `test_tutorial_is_solvable_and_playable` | 教学关自己也要可解、能一路点到通关 | ✅ |
| `test_finishing_the_tutorial_scores_nothing` | 教学关走完：不进存档、不解锁、不算分，只引导去第 1 关 | ✅ |
| `test_tutorial_can_be_failed_and_retried_without_penalty` | 教学关点光生命值也只是重来一遍：不记分、不锁关 | ✅ |

### 4.5 关卡数据与难度曲线

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_level_count_and_difficulty_ramp` | 标准关正好 9 关，且难度整条曲线是递增的 | ✅ |
| `test_levels_one_to_four_get_harder_step_by_step` | 第 1~4 关是入门段，棋盘只许变大、箭头只许变多、难度分严格上升、星级不下降 | ✅ |
| `test_difficulty_steps_stay_smooth_across_nine_levels` | 九个关卡的难度一级一级加，任意相邻两关都不能顶出一个大台阶 | ✅ |
| `test_later_levels_gain_density_not_board_size` | 后半段的难度不靠放大棋盘，而是靠提高密度：尺寸冻结在 9×9，分数公式里也用密度而不是面积 | ✅ |
| `test_stars_within_range` | 难度星级落在 1~5，且不随难度提高而下降 | ✅ |
| `test_star_ramp_starts_at_one_and_ends_at_five` | 星级从第 1 关的 1 星升到最后一关的 5 星（教学关不在这条链上） | ✅ |
| `test_every_level_has_at_least_one_playable_arrow` | 每关开局至少有一支能点的箭头，避免一上手就是死局 | ✅ |
| `test_level_sizes_are_within_screen` | 关卡尺寸不超过窗口可容纳的范围 | ✅ |

### 4.6 观感回归（画面相关的用例）

这一组是「逻辑全对但看着不对」的问题逼出来的，用来钉住视觉上的几个约定：

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_every_arrow_takes_its_direction_color` | 箭头颜色只由方向决定：同一方向的箭头颜色完全一致 | ✅ |
| `test_direction_colors_have_matched_brightness` | 四个方向的颜色感知亮度要拉平（差 1.7 以内），整屏看起来才像「一套」 | ✅ |
| `test_direction_colors_are_distinct_and_all_used` | 四个方向颜色互不相同，且确实都在关卡里用到 | ✅ |
| `test_level_colors_are_only_direction_colors` | 一关里出现的颜色只可能来自那 4 个方向色，不会有第 5 种 | ✅ |
| `test_adjacent_arrows_are_mostly_different_directions` | 每关「相邻且同向」的箭头对不能太多（≤ 28%） | ✅ |
| `test_same_color_blocks_stay_small` | 同方向的箭头不该连成一大块（最大 4 格） | ✅ |
| `test_deshuffle_keeps_the_level_solvable_and_no_easier` | 打散工具只换方向：换完仍然可解，开局可点数不会变多 | ✅ |
| `test_arrow_colors_are_still_decided_only_by_direction` | 打散配色只动关卡布局，不动调色板 | ✅ |
| `test_hud_has_room_for_the_widest_level` | 信息行四组内容（计时 / 生命值 / 剩余箭头 / 得分）按最宽情形算一遍，居中后不越界、也不压到提示条 | ✅ |
| `test_wrap_text_keeps_punctuation_off_line_start` | 折行后不允许有行以收尾标点开头（中文排版的基本要求） | ✅ |
| `test_background_actually_moves` | 背景要真的在动：推进 3 秒后整屏像素确实变了 | ✅ |
| `test_background_can_still_spawn_a_shooting_star` | 流星机制没烂掉：临时把间隔调短，它确实会被触发（跑完还原配置） | ✅ |
| `test_every_scene_renders_with_background` | 三个场景都要能带着动态背景正常画出来 | ✅ |
| `test_heart_surface_matches_the_grid` | 渲染出来的心和网格一一对应：格子在就是实心，不在就是透明 | ✅ |

### 4.7 计时、提示与辅助线（这一版新加的三个小工具）

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_play_clock_counts_up_and_resets_on_restart` | 计时从 0 开始、玩的时候往前走，重新开始要归零 | ✅ |
| `test_play_clock_stops_once_the_level_is_over` | 本关分出胜负之后时钟就停住，不再往上涨 | ✅ |
| `test_clock_text_formats_minutes_and_hours` | 计时文本是 MM:SS；超过一小时进位成 H:MM:SS，不会显示成 62:05 | ✅ |
| `test_hint_picks_an_arrow_that_can_really_fly` | 提示指的那一支必须真的能飞出，且和暴力枚举出的最优解一致 | ✅ |
| `test_hint_ring_fades_away_by_itself` | 提示环到时间自己消失，不会一直挂在棋盘上 | ✅ |
| `test_hint_when_nothing_can_fly_gives_a_message` | 全场没有能飞的箭头时，提示不崩、给一句话 | ✅ |
| `test_guides_toggle_keeps_the_button_in_sync` | 辅助线开关：逻辑状态、按钮上的 on 标记、渲染三者一致 | ✅ |
| `test_guides_survive_a_restart` | 辅助线是玩家偏好，重开本关不该把它关掉 | ✅ |
| `test_play_layout_areas_do_not_overlap` | 信息栏 / 提示条 / 棋盘 / 工具栏四块区域逐关算一遍，不许互相压住 | ✅ |

**「提示」里的「最优」是怎么定义的。** 这个玩法有个性质：点掉一支能飞的箭头，
只会让其它箭头的路更空，不会把自己玩死。所以提示挑的是
「消掉它之后能连带解锁最多其它箭头」的那一支——第一步点对了，后面往往就顺了。
测试就直接拿这条定义去对：临时把候选从格子上摘掉、数一遍还剩几支能飞、再放回去，
最后和 `Game.best_hint()` 给出的坐标逐个比对。

**辅助线为什么不按「能不能飞」上色。** 那条线只帮玩家看清方向关系；
一旦畅通画绿、被挡画红，等于把答案画在脸上，这一局该有的思考就没了。
所以两个状态用同一个颜色（`config.COLOR_GUIDE`），
只有鼠标悬停某支箭头时，才用绿 / 红两色高亮那一条具体路径。

**顺带记一笔棋盘的「去底格」改动。** 新版棋盘不再画每一格的底框，只有一片极淡的点阵
（`app.draw_board()`）。原因是这个玩法的难度来自「在一堆箭头里找出能点的那支」，
而几十个空方框会让视线一直被拽住——那是「乱」不是「难」。

## 五、边界与容错用例

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_click_empty_cell_is_harmless` | 点到空格子不扣生命值、不改变棋盘 | ✅ |
| `test_click_outside_board_is_ignored` | 点击负数坐标 / 超界坐标返回 `ignored`，不抛异常 | ✅ |
| `test_click_after_level_finished_is_ignored` | 本关结束后再点棋盘状态不再变化 | ✅ |
| `test_deadlock_is_detected` | 同一行两支箭头面对面的死锁布局被判为无解 | ✅ |
| `test_level_layout_validation` | 行长度不一致 / 含非法字符 / 没有箭头 → 抛 `ValueError` | ✅ |
| `test_all_levels_are_solvable` | 教学关 + 9 个关卡都存在通关顺序 | ✅ |
| `test_every_level_can_be_played_to_the_end` | 按求解器顺序实际点击，全部关卡都能打通 | ✅ |
| `test_corner_arrow_path_never_leaves_the_board` | 角落箭头的路径坐标不越界 | ✅ |
| `test_reset_restores_the_level` | `reset()` 能完整恢复布局与生命值 | ✅ |
| `test_victory_condition` | 清空全部箭头后进入通关状态 | ✅ |
| `test_start_screen_and_start_button` | 开始界面存在，点「开始游戏」能进入第 1 关 | ✅ |
| `test_menu_explains_the_rules` | 主菜单必须有玩法说明，以及教学关 / 关卡总览 / 退出三个入口 | ✅ |
| `test_render_every_scene_without_error` | 各个画面都能正常渲染 | ✅ |
| `test_mouse_click_routes_to_the_board` | 鼠标坐标能正确换算成棋盘格子并触发点击 | ✅ |
| `test_keyboard_shortcuts` | `R` 重开本关、`Esc` 返回主菜单 | ✅ |

---

## 六、完整测试日志

```
test_a_worse_replay_keeps_the_old_record ... ok   重玩打得差不会把最高分冲掉（存档只记最好的一次）。
test_adjacent_arrows_are_mostly_different_directions ... ok   每关「相邻且同向」的箭头对不能太多。
test_all_levels_are_solvable ... ok   作业要求：每个关卡都必须存在合理的通关顺序。
test_all_levels_can_be_cleared_in_order ... ok   按顺序把 9 关全部打通，验证解锁链路与关卡数据整体可用。
test_arrow_colors_are_still_decided_only_by_direction ... ok   打散配色只动关卡布局，不动调色板：一个方向仍然只有一种颜色。
test_background_actually_moves ... ok   背景要真的在动：时间推进之后，整屏像素确实变了。
test_background_can_still_spawn_a_shooting_star ... ok   流星机制没烂掉：把间隔调短之后，它确实会被触发。
test_blocked_click_pops_a_broken_heart_not_hanzi ... ok   点错时飘出来的是一颗「碎掉的像素心」，不是「失去一心」四个汉字。
test_board_exposes_a_live_score ... ok   棋盘自己就知道当前能拿多少分，HUD 直接用这个数（点错立刻掉）。
test_broken_heart_animation_renders_and_fades_out ... ok   心碎动画：两半分开、心往上飘、末端淡出，每一帧都画得出来。
test_broken_scores_in_the_save_file_are_ignored ... ok   存档里的分数被人手改坏了（非数字、负数）时，只丢掉坏的那几条。
test_cleared_count_next_index_and_all_cleared ... ok   统计与「下一关」的取值。
test_clearing_a_level_unlocks_the_next_one ... ok   通关之后，下一关立刻变成可进入。
test_clearing_unlocks_the_next_level ... ok   通关一关之后才解锁下一关。
test_clearing_without_mistakes_pays_the_full_score ... ok   零失误通关：拿满分、记进存档，结算面板写出完美奖励。
test_click_after_level_finished_is_ignored ... ok   本关结束后再点棋盘不再改变任何状态。
test_click_empty_cell_is_harmless ... ok   点到空格子不扣生命值，也不改变棋盘。
test_click_outside_board_is_ignored ... ok   点到棋盘外不会抛异常。
test_clicking_a_locked_card_only_shows_a_hint ... ok   点未解锁的卡片不会开局，只提示先通关哪一关。
test_clicking_an_unlocked_card_starts_that_level ... ok   点已解锁的卡片直接开局。
test_clock_text_formats_minutes_and_hours ... ok   计时文本：MM:SS；超过一小时进位成 H:MM:SS，不会显示成 62:05。
test_corner_arrow_path_never_leaves_the_board ... ok   路径检测返回的坐标必须全部落在棋盘内。
test_deadlock_is_detected ... ok   互相阻挡的死锁布局必须被判定为无解。
test_deshuffle_keeps_the_level_solvable_and_no_easier ... ok   打散工具只换方向：换完仍然可解，开局可点数不会变多。
test_difficulty_steps_stay_smooth_across_nine_levels ... ok   九个关卡的难度是一级一级加的，任意相邻两关都不能顶出一个大台阶。
test_direction_colors_are_distinct_and_all_used ... ok   四个方向颜色互不相同，且确实都在关卡里用到。
test_direction_colors_have_matched_brightness ... ok   四个方向的颜色感知亮度要拉平，整屏看起来才像「一套」。
test_every_arrow_takes_its_direction_color ... ok   箭头颜色只由方向决定：同一方向的箭头颜色完全一致。
test_every_level_can_be_played_to_the_end ... ok   按求解器给出的顺序实际点击，每个关卡都能通关。
test_every_level_has_at_least_one_playable_arrow ... ok   每个关卡开局都必须至少有一支能点的箭头，否则玩家一上手就是死局。
test_every_mistake_costs_points ... ok   同一关里，失去的心越多得分越低，且是严格下降。
test_every_mistake_lowers_the_score ... ok   丢一颗心，HUD 上的得分立刻按比例下降，最终结算也跟着少。
test_every_scene_renders_with_background ... ok   三个场景都要能带着动态背景正常画出来。
test_fail_when_hp_used_up ... ok   生命值用尽后棋盘进入失败状态。
test_failing_a_level_scores_zero ... ok   生命值耗尽：本关 0 分，也不写进存档。
test_failing_the_level_is_worth_nothing ... ok   生命值耗尽时本关 0 分（越界的参数也不会算出一个负数）。
test_finishing_the_tutorial_scores_nothing ... ok   教学关走完：不进存档、不解锁、不算分，只引导去第 1 关。
test_full_score_follows_the_difficulty_stars ... ok   满分 = 星级 × 300（基础分 250 + 20% 完美奖励）。
test_guides_survive_a_restart ... ok   辅助线是玩家偏好：重开本关不该把它关掉。
test_guides_toggle_keeps_the_button_in_sync ... ok   辅助线开关：状态、按钮上的 on 标记、渲染三者要一致。
test_heart_icon_is_a_pixel_art_grid ... ok   生命值图标是「像素心」：规整网格、左右对称、顶部中间留凹口。
test_heart_surface_matches_the_grid ... ok   渲染出来的心和网格一一对应：格子在就是实心，不在就是透明。
test_hint_picks_an_arrow_that_can_really_fly ... ok   提示高亮的那一支，必须是当下真的能飞出去的箭头、而且是最优的那一支。
test_hint_ring_fades_away_by_itself ... ok   提示环到时间自己消失，不会一直挂在棋盘上。
test_hint_when_nothing_can_fly_gives_a_message ... ok   一开局就没有能飞的箭头时，提示按钮不能崩，要给一句话。
test_hp_drops_one_per_blocked_click ... ok   点错一次固定扣 1 点生命值；扣到 0 就失败，且不会再往下扣成负数。
test_hp_is_granted_by_difficulty ... ok   每关的生命值必须正好是「星级 → 生命值」表里对应的值。
test_hud_has_room_for_the_widest_level ... ok   HUD 信息行排得下：最宽的一组内容（7 颗心 + 四位数得分）也不会越界。
test_hud_hearts_are_pixel_hearts ... ok   HUD 那一排生命值画的也是像素心：还有的用亮色、失去的用暗色。
test_keyboard_shortcuts ... ok   R 重开本关、Esc 返回主菜单。
test_later_levels_gain_density_not_board_size ... ok   后半段的难度不靠放大棋盘，而是靠提高密度。
test_level_colors_are_only_direction_colors ... ok   一关里出现的颜色只可能来自那 4 个方向色，不会有第 5 种。
test_level_count_and_difficulty_ramp ... ok   标准关正好 9 关，且难度整条曲线是递增的。
test_level_layout_validation ... ok   布局不合法时应当直接报错，避免出现隐蔽的坏关卡。
test_level_select_lists_all_levels ... ok   关卡总览里每张卡片对应一个关卡。
test_level_sizes_are_within_screen ... ok   关卡尺寸不能超过窗口能容纳的范围。
test_levels_one_to_four_get_harder_step_by_step ... ok   第 1~4 关是入门段，难度必须一关比一关高，而且步子要看得出来。
test_locked_level_cannot_be_started ... ok   没通关前一关时，后面的关卡进不去，并且给出提示。
test_lost_heart_is_an_empty_outline ... ok   已经失去的那颗心只剩外沿：内部镂空，和实心的一眼能区分。
test_mark_cleared_is_idempotent ... ok   重复标记同一关不会出错，也不重复写盘。
test_menu_explains_the_rules ... ok   主菜单必须有玩法说明，以及教学关 / 关卡总览 / 退出三个入口。
test_missing_or_broken_save_file_is_tolerated ... ok   存档不存在或内容损坏时，应当当成空进度而不是崩溃。
test_mouse_click_routes_to_the_board ... ok   鼠标点击棋盘坐标能正确换算到对应的格子。
test_old_save_without_scores_still_loads ... ok   老存档（version 1，没有 scores 字段）不能因为升级格式丢进度。
test_one_mistake_hurts_less_on_harder_levels ... ok   点错一次的代价逐关变小——这就是「容错越来越高」的量化说法。
test_only_first_level_unlocked_at_start ... ok   全新存档只解锁第 1 关。
test_perfect_bonus_only_when_nothing_is_lost ... ok   零失误奖励只在满心通关时给，而且正好是基础分的 20%。
test_play_clock_counts_up_and_resets_on_restart ... ok   计时从 0 开始、玩的时候往前走，重新开始要归零。
test_play_clock_stops_once_the_level_is_over ... ok   本关分出胜负之后时钟就停住，不再往上涨。
test_play_layout_areas_do_not_overlap ... ok   游戏界面那几块区域不许互相压住：信息栏 / 提示条 / 棋盘 / 工具栏。
test_primary_button_follows_progress ... ok   主按钮文字会随进度变化：从「开始游戏」到「继续第 N 关」。
test_render_every_scene_without_error ... ok   各个画面都能正常渲染（顺便覆盖绘制代码）。
test_reset_clears_everything ... ok   清空进度后回到只解锁第 1 关的状态，最高分也一并清掉，且已经落盘。
test_reset_progress_needs_two_clicks ... ok   「清空进度」要点两次才真的清，避免手滑。
test_reset_restores_the_level ... ok   reset() 把箭头布局和生命值都恢复原样。
test_same_color_blocks_stay_small ... ok   同方向的箭头不该连成一大块。
test_save_and_reload ... ok   存档写到磁盘后能被重新读回来。
test_scores_are_recorded_and_only_the_best_one_wins ... ok   每关只留最高分：重玩手感差不会把纪录冲掉。
test_skipping_a_level_does_not_unlock_further ... ok   跳着通关不算数：第 2 关没过，第 3 关依然锁着。
test_star_ramp_starts_at_one_and_ends_at_five ... ok   星级从第 1 关的 1 星升到最后一关的 5 星（教学关不在这条链上）。
test_stars_within_range ... ok   难度星级必须落在 1~5 之间，且不随难度提高而下降。
test_start_screen_and_start_button ... ok   开始界面存在，点「开始游戏」能进入第 1 关。
test_t01_click_free_arrow_flies_out ... ok   T01 点击前方无阻挡的箭头 -> 箭头飞出棋盘并消失。
test_t02_click_blocked_arrow_costs_hp ... ok   T02 点击前方有阻挡的箭头 -> 箭头不消失，生命值减 1。
test_t03_arrows_on_the_edge_fly_out_safely ... ok   T03 点击边缘且朝向棋盘外的箭头 -> 正常消失，不发生越界错误。
test_t04_clear_level_then_go_to_next_level ... ok   T04 消除本关全部箭头 -> 显示通关并进入下一关。
test_t04_clearing_the_last_level_shows_all_clear ... ok   打完最后一关显示「全部通关」。
test_t05_fail_then_restart ... ok   T05 生命值耗尽 -> 显示失败并允许重新开始。
test_t06_restart_mid_game ... ok   T06 游戏进行中重新开始 -> 箭头布局和生命值都恢复。
test_tolerance_grows_from_first_level_to_last ... ok   生命值上限整体不下降，最后一关要明显比第 1 关宽容。
test_total_full_score_is_the_sum_of_all_levels ... ok   全部关卡的满分加起来等于总分上限（结算面板里的「总分 x / y」用它）。
test_total_score_is_the_sum_of_each_levels_best ... ok   总分 = 各关最高分之和；不存在关卡里的分数不计入。
test_tutorial_can_be_failed_and_retried_without_penalty ... ok   教学关点光生命值也只是重来一遍：不记分、不锁关。
test_tutorial_has_its_own_entry_on_the_menu ... ok   教学关是菜单上的独立入口：不用解锁，点了就能进。
test_tutorial_is_a_forgiving_sandbox ... ok   教学关是给人放胆点的沙盒，生命值要比同星级的关卡宽裕。
test_tutorial_is_not_a_numbered_level ... ok   教学关独立于关卡表：不占第 1 关的位置，也不参与编号。
test_tutorial_is_solvable_and_playable ... ok   教学关自己也要可解、能一路点到通关。
test_tutorial_level_must_have_steps ... ok   教学关必须带引导步骤，否则界面上会没有任何提示。
test_tutorial_resyncs_when_player_deviates ... ok   玩家不按提示点时，引导会自动跳过已经失效的步骤，而不是卡住。
test_tutorial_ring_only_drawn_for_current_step ... ok   引导高亮只在教学关且步骤未走完时出现（顺带覆盖绘制代码）。
test_tutorial_steps_advance_one_by_one ... ok   照着引导点，步骤会一步步推进，最后引导结束。
test_victory_condition ... ok   清空全部箭头后棋盘进入通关状态。
test_wrap_text_keeps_punctuation_off_line_start ... ok   折行后不允许有行以收尾标点开头（中文排版的基本要求）。
```

---

## 七、关卡可解性校验

执行 `python tools/verify_levels.py`（完整输出，含每关的布局图与参考通关顺序）：

```
==============================================================================
《一箭又一箭》关卡校验报告
==============================================================================

教学关（主菜单独立入口：不计分、不占关卡编号、不用解锁）
          棋盘 4×5   箭头 3 支   密度 0.15   开局可点 2 支   生命值 6 颗
------------------------------------------------------------------------------
   0 | . . . . .
   1 | . > . v .
   2 | . . . . .
   3 | . . ^ . .
------------------------------------------------------------------------------
   [OK] 可解，共 3 步
   参考顺序：(1,3)下 -> (3,2)上 -> (1,1)右
   引导步骤：4 步（点哪里、为什么，都在关卡里的黄色高亮环上）

第  1 关  初次拉弓   棋盘 5×5   箭头  4 支   密度 0.16   开局可点 3 支
         难度 ★   生命值 4 颗（容错随难度递增）   本关满分 300 分
------------------------------------------------------------------------------
   0 | . . v . .
   1 | . . . . .
   2 | . ^ . . .
   3 | . . . . >
   4 | . . v . .
------------------------------------------------------------------------------
   [OK] 可解，共 4 步
   参考顺序：(2,1)上 -> (3,4)右 -> (4,2)下 -> (0,2)下

第  2 关  交叉路口   棋盘 5×5   箭头  4 支   密度 0.16   开局可点 1 支
         难度 ★★   生命值 4 颗（容错随难度递增）   本关满分 600 分
------------------------------------------------------------------------------
   0 | . . . . .
   1 | . > . v .
   2 | . . . . .
   3 | . ^ . . <
   4 | . . . . .
------------------------------------------------------------------------------
   [OK] 可解，共 4 步
   参考顺序：(1,3)下 -> (1,1)右 -> (3,1)上 -> (3,4)左

第  3 关  连锁反应   棋盘 7×6   箭头 10 支   密度 0.24   开局可点 2 支
         难度 ★★★   生命值 5 颗（容错随难度递增）   本关满分 900 分
------------------------------------------------------------------------------
   0 | . . . . . .
   1 | . > > v > v
   2 | . . . . . .
   3 | . . . . . .
   4 | . ^ < > ^ .
   5 | . . . . v .
   6 | . . . . . .
------------------------------------------------------------------------------
   [OK] 可解，共 10 步
   参考顺序：(1,5)下 -> (5,4)下 -> (1,4)右 -> (4,4)上 -> (4,3)右 -> (1,3)下 -> (1,2)右 -> (1,1)右 -> (4,1)上 -> (4,2)左

第  4 关  四面楚歌   棋盘 7×7   箭头 12 支   密度 0.24   开局可点 2 支
         难度 ★★★   生命值 5 颗（容错随难度递增）   本关满分 900 分
------------------------------------------------------------------------------
   0 | . . . . v . .
   1 | . > > v > v .
   2 | . . . . . . .
   3 | . . ^ v . . .
   4 | . . . . . . .
   5 | . ^ < v < . .
   6 | . . . . . . .
------------------------------------------------------------------------------
   [OK] 可解，共 12 步
   参考顺序：(1,5)下 -> (5,3)下 -> (1,4)右 -> (3,3)下 -> (1,3)下 -> (1,2)右 -> (3,2)上 -> (1,1)右 -> (5,1)上 -> (5,2)左 -> (5,4)左 -> (0,4)下

第  5 关  错位走廊   棋盘 7×7   箭头 18 支   密度 0.37   开局可点 3 支
         难度 ★★★★   生命值 6 颗（容错随难度递增）   本关满分 1200 分
------------------------------------------------------------------------------
   0 | > . . v . . .
   1 | . > v > . . .
   2 | v . . . < < v
   3 | . > . v . . .
   4 | > . > v . . .
   5 | . > . . . . .
   6 | . ^ . . . ^ <
------------------------------------------------------------------------------
   [OK] 可解，共 18 步
   参考顺序：(1,3)右 -> (4,3)下 -> (5,1)右 -> (3,3)下 -> (4,2)右 -> (0,3)下 -> (1,2)下 -> (3,1)右 -> (4,0)右 -> (0,0)右 -> (1,1)右 -> (2,0)下 -> (2,4)左 -> (2,5)左 -> (6,1)上 -> (6,5)上 -> (6,6)左 -> (2,6)下

第  6 关  纵横交错   棋盘 8×8   箭头 24 支   密度 0.38   开局可点 3 支
         难度 ★★★★   生命值 6 颗（容错随难度递增）   本关满分 1200 分
------------------------------------------------------------------------------
   0 | . v . > ^ . v .
   1 | > . v . . . . .
   2 | . . . v ^ < . <
   3 | > . . > ^ . . .
   4 | . > . . ^ . . .
   5 | . . . . ^ . < .
   6 | > . > . > . > .
   7 | . . . < ^ . . ^
------------------------------------------------------------------------------
   [OK] 可解，共 24 步
   参考顺序：(0,4)上 -> (2,4)上 -> (3,4)上 -> (4,4)上 -> (5,4)上 -> (5,6)左 -> (6,6)右 -> (7,3)左 -> (0,6)下 -> (3,3)右 -> (4,1)右 -> (6,4)右 -> (7,4)上 -> (0,1)下 -> (0,3)右 -> (2,3)下 -> (2,5)左 -> (2,7)左 -> (3,0)右 -> (6,2)右 -> (7,7)上 -> (1,2)下 -> (6,0)右 -> (1,0)右

第  7 关  长蛇阵   棋盘 8×8   箭头 30 支   密度 0.47   开局可点 3 支
         难度 ★★★★   生命值 6 颗（容错随难度递增）   本关满分 1200 分
------------------------------------------------------------------------------
   0 | > v > . > . . .
   1 | . v . . . . . <
   2 | > . v > . > ^ .
   3 | ^ . . ^ > ^ . .
   4 | . . v < . < . <
   5 | > v . > . . ^ .
   6 | ^ > . . . > ^ .
   7 | . . . . ^ . ^ <
------------------------------------------------------------------------------
   [OK] 可解，共 30 步
   参考顺序：(0,4)右 -> (2,6)上 -> (4,2)下 -> (4,3)左 -> (4,5)左 -> (4,7)左 -> (5,6)上 -> (6,6)上 -> (7,6)上 -> (0,2)右 -> (2,2)下 -> (2,5)右 -> (3,5)上 -> (5,3)右 -> (6,5)右 -> (2,3)右 -> (3,3)上 -> (3,4)右 -> (6,1)右 -> (7,4)上 -> (7,7)左 -> (2,0)右 -> (5,1)下 -> (1,1)下 -> (1,7)左 -> (5,0)右 -> (0,1)下 -> (0,0)右 -> (3,0)上 -> (6,0)上

第  8 关  十面埋伏   棋盘 9×9   箭头 40 支   密度 0.49   开局可点 4 支
         难度 ★★★★★   生命值 7 颗（容错随难度递增）   本关满分 1500 分
------------------------------------------------------------------------------
   0 | v . < > . . . v .
   1 | v > . v . . > v .
   2 | > . . > . > ^ . ^
   3 | . ^ . . . . v . <
   4 | . v . < < v . v .
   5 | > v . . ^ > v . .
   6 | . . > . . v > v .
   7 | . . . . ^ < . < .
   8 | > . v . ^ > > v .
------------------------------------------------------------------------------
   [OK] 可解，共 40 步
   参考顺序：(2,8)上 -> (5,1)下 -> (8,2)下 -> (8,7)下 -> (4,1)下 -> (4,3)左 -> (4,4)左 -> (5,4)上 -> (7,4)上 -> (7,5)左 -> (7,7)左 -> (8,4)上 -> (8,6)右 -> (6,7)下 -> (8,5)右 -> (4,7)下 -> (6,5)下 -> (6,6)右 -> (8,0)右 -> (1,7)下 -> (5,6)下 -> (6,2)右 -> (0,7)下 -> (1,6)右 -> (2,6)上 -> (3,6)下 -> (5,5)右 -> (0,3)右 -> (2,5)右 -> (4,5)下 -> (5,0)右 -> (2,3)右 -> (1,3)下 -> (2,0)右 -> (1,0)下 -> (1,1)右 -> (3,1)上 -> (3,8)左 -> (0,0)下 -> (0,2)左

第  9 关  万箭归一   棋盘 9×9   箭头 50 支   密度 0.62   开局可点 5 支
         难度 ★★★★★   生命值 7 颗（容错随难度递增）   本关满分 1500 分
------------------------------------------------------------------------------
   0 | . > . > v . > . >
   1 | > v ^ v . > v > ^
   2 | ^ > . > v ^ . ^ .
   3 | > . . . > . > ^ .
   4 | > . . > v > . > ^
   5 | ^ > ^ > . ^ v ^ ^
   6 | > v . . v > . > ^
   7 | . . ^ . . . . < v
   8 | ^ . < . . . . ^ <
------------------------------------------------------------------------------
   [OK] 可解，共 50 步
   参考顺序：(0,8)右 -> (1,2)上 -> (1,8)上 -> (4,8)上 -> (5,2)上 -> (5,6)下 -> (5,8)上 -> (6,1)下 -> (6,4)下 -> (6,8)上 -> (7,2)上 -> (7,7)左 -> (0,6)右 -> (1,7)右 -> (2,7)上 -> (3,7)上 -> (4,4)下 -> (4,7)右 -> (5,7)上 -> (6,7)右 -> (8,7)上 -> (3,6)右 -> (4,5)右 -> (6,5)右 -> (1,6)下 -> (3,4)右 -> (4,3)右 -> (6,0)右 -> (1,5)右 -> (2,4)下 -> (2,5)上 -> (3,0)右 -> (4,0)右 -> (5,5)上 -> (0,4)下 -> (2,3)右 -> (5,3)右 -> (0,3)右 -> (1,3)下 -> (2,1)右 -> (5,1)右 -> (0,1)右 -> (1,1)下 -> (1,0)右 -> (2,0)上 -> (5,0)上 -> (8,0)上 -> (8,2)左 -> (8,8)左 -> (7,8)下

校验结果：教学关 + 全部 9 个编号关卡均可正常通关。
难度参考：棋盘尺寸逐关放大，第 8 关到 9×9 就封顶，
          之后同样的格子里塞进更多箭头，靠密度继续加难；
          开局可点的箭头越少，越要在开局仔细找出口。
生命值参考：按难度星级给，第 1 关 4 颗心、最后一关 7 颗心。
            关卡越难容错越高，一次手滑不至于被打回原点。
            教学关不参与计分，单独给 6 颗心，是个随便点的沙盒。
得分参考：本关得分 = 星级×250 × 剩余生命值 ÷ 生命值上限，
          一颗心都没丢再 +20%；第 1~9 关满分合计 9300 分。
```

校验脚本的退出码为 0（全部可解）；若存在无解关卡，退出码为 1，
可直接接入 CI 或提交前的检查流程。

### 关卡一览

| 关卡 | 名称 | 棋盘 | 箭头 | 密度 | 开局可点 | 生命值 | 难度 | 本关满分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 教学关 | 教学关 | 4×5 | 3 | 0.15 | 2 | ♥×6 | 不计分 | — |
| 1 | 初次拉弓 | 5×5 | 4 | 0.16 | 3 | ♥×4 | ★ | 300 |
| 2 | 交叉路口 | 5×5 | 4 | 0.16 | 1 | ♥×4 | ★★ | 600 |
| 3 | 连锁反应 | 7×6 | 10 | 0.24 | 2 | ♥×5 | ★★★ | 900 |
| 4 | 四面楚歌 | 7×7 | 12 | 0.24 | 2 | ♥×5 | ★★★ | 900 |
| 5 | 错位走廊 | 7×7 | 18 | 0.37 | 3 | ♥×6 | ★★★★ | 1200 |
| 6 | 纵横交错 | 8×8 | 24 | 0.38 | 3 | ♥×6 | ★★★★ | 1200 |
| 7 | 长蛇阵 | 8×8 | 30 | 0.47 | 3 | ♥×6 | ★★★★ | 1200 |
| 8 | 十面埋伏 | 9×9 | 40 | 0.49 | 4 | ♥×7 | ★★★★★ | 1500 |
| 9 | 万箭归一 | 9×9 | 50 | 0.62 | 5 | ♥×7 | ★★★★★ | 1500 |

9 个编号关卡合计 192 支箭头、满分合计 9300 分。
第 5~9 关由 `tools/generate_levels.py` **逆向构造**生成（从构造方式上就保证可解），
生成后仍由 `verify_levels.py` 的求解器逐关复核，两道保险。

**难度曲线的数据**：九个关卡的难度分是
`5.2 / 9.2 / 19.1 / 22.5 / 33.8 / 43.7 / 56.1 / 70.8 / 88.5`，
相邻差 `4.0 / 9.9 / 3.4 / 11.3 / 9.9 / 12.4 / 14.7 / 17.7`。
越往后加得越多：前面留足台阶让人上手，后面才开始认真。
（中间有一版 8 关时出现过 22.3 分的大台阶，新关是插在最陡的那一处把它拆开的，
而不是顺手追加到末尾。）

### 关于第 2 关的一次真实修复

第 2 关最初的布局是：

```
.....
.>.v.
.....
.^.<.
.....
```

校验时报出 `开局可点 0 支 / 可解=False`：`(1,1)` 的 `>` 被 `(1,3)` 的 `v` 挡住，
`v` 被 `(3,3)` 的 `<` 挡住，`<` 被 `(3,1)` 的 `^` 挡住，`^` 又被 `(1,1)` 的 `>` 挡住——
四支箭头首尾相接形成死环。把 `<` 从 `(3,3)` 移到 `(3,4)` 之后即恢复可解，
同时保留了「全场只有一个出口、四步连锁」的设计意图。

### 另一件值得记的事：手写的关号会过期

校验脚本的报告里原本有一句「棋盘尺寸到第 7 关就封顶在 9×9」，
后来插了一关，实际已经变成第 8 关，但这句写死的描述**照样打印、退出码照样是 0**，
不报错也不警告。已经改成从关卡表里现算（`sizes.index(max(side)) + 1`）。
教训是：能现算的数字一律不要手写，否则过期之后只会静静地印一句错话。

---

## 八、手动试玩验证

> 这一节的结论需要在**本人实际试玩后确认**；如果手感和这里写的不一致，以真实感受为准改掉。

| 关卡 | 试玩结论 |
| --- | --- |
| 教学关 | 3 支箭头配 6 颗心，跟着屏幕高亮一步步点即可；第一步故意让玩家点一支被挡住的箭头，用来体验碰撞反馈和掉心 |
| 第 1 关 初次拉弓 | 4 支箭头里有 3 支能直接飞，点两下就通关，适合建立信心 |
| 第 2 关 交叉路口 | 开局只有一支能飞，要顺着链条一支一支解；点错立刻掉一颗心，4 颗心的容错够用 |
| 第 3 关 连锁反应 | 先点掉能飞的那一支，同行的箭头会依次飞出去，连锁反馈明显 |
| 第 4 关 四面楚歌 | 开局只有 2 支能飞；棋盘来到 7×7，横竖都要扫一遍 |
| 第 5~7 关 | 棋盘 7×7 → 8×8，箭头 18 / 24 / 30 支，开局可点 3 支；密度上去之后扫视量明显变大 |
| 第 8~9 关 | 9×9 塞了 40 / 50 支箭头，只有 4~5 支能先飞；心给了 7 颗，容错够但也得认真找 |
| 通用 | 「重新开始」后布局与生命值正确复位；`R` 重开、`Esc` 返回主菜单均正常 |
| 进度 | 关掉游戏再打开，已解锁到哪一关、每关最高分都会被记住；「清空进度」需连点两次 |
