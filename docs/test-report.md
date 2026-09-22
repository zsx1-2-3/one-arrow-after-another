# 测试与关卡校验报告

本文件记录《一箭又一箭》的自动化测试结果与关卡可解性校验结果，对应作业要求中的
「5. 测试要求」与「3.1 至少设计 3 个可以正常通关的关卡」。

* 测试用例总数：**222 个，全部通过**（`Ran 222 tests` → `OK`）
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
Ran 222 tests in 17.765s

OK
```

222 个用例全部通过，分为十组：

| 测试类 | 用例数 | 覆盖内容 |
| --- | --- | --- |
| `BoardRuleTestCase` | 45 | 箭头写法解析与格式化、布局校验、相邻不同色、单次点击的规则判定（T01~T03）、边界、生命值、复位 |
| `SolverTestCase` | 7 | 贪心求解器、单调性、无解布局判定、开局可点数统计 |
| `LevelBalanceTestCase` | 19 | 9 关的可解性、竖屏尺寸、铺满率与可点数阶梯、难度与星级、生命值表、满分、教学关数据 |
| `ScoringTestCase` | 9 | 得分公式、完美奖励、失败 0 分、总分上限、单调性 |
| `ProgressTestCase` | 12 | 解锁规则、跳关不算解锁、存档读写与容错、最高分、全通关 |
| `RenderPrimitiveTestCase` | 25 | 箭头贴图缓存与几何、中文折行、滑杆取值、图标与像素心 |
| `AnimationTestCase` | 11 | 整条箭头飞出、撞击抖动与泛红、飘字、心碎 |
| `BackgroundTestCase` | 2 | 三个场景带背景渲染、背景跟随主题 |
| `GameFlowTestCase` | 83 | 场景切换、关卡总览、解锁链路、教学引导、T04~T06、结算面板、计时 / 提示 / 辅助线 / 缩放平移、界面分区、键盘快捷键 |
| `VisualVarietyTestCase` | 9 | 相邻箭头不同色、配色来自调色板、各关渲染、悬停高亮、渲染不改棋盘 |

> 用例数是从 `tests/test_game.py` 里现数的（按 `def test_` 前缀统计），
> 不是沿用上一版的数字——项目每加一轮功能，这个数就会变。

---

## 三、作业要求的六个测试用例

| 编号 | 测试内容 | 预期结果 | 实际结果 |
| --- | --- | --- | --- |
| T01 | 点击前方无阻挡的箭头 | 整条箭头飞出棋盘并消失 | ✅ 通过 |
| T02 | 点击前方有阻挡的箭头 | 箭头不消失，失误次数减 1 | ✅ 通过 |
| T03 | 点击位于边缘且朝向棋盘外的箭头 | 箭头正常消失，不发生越界错误 | ✅ 通过 |
| T04 | 消除本关全部箭头 | 显示通关并进入下一关 | ✅ 通过 |
| T05 | 失误次数耗尽 | 显示失败并允许重新开始 | ✅ 通过 |
| T06 | 游戏进行中重新开始 | 箭头布局和失误次数恢复 | ✅ 通过 |

> 说明：本作的「失误次数」做成了**生命值**（用像素心表示，点错一次丢一颗心），
> 判定逻辑与作业要求完全一致，只是换了一个更直观的呈现方式和更自然的字段语义。

### 每个用例的具体做法

* **T01**（`test_t01_free_piece_flies_out_and_disappears`）：在测试关卡点击 `(2,3)` 那支
  竖着、箭头朝下的箭头（下方一路空到盘外），断言返回 `fly`、被点的正是这一支、没有阻挡者、
  该格变空、剩余箭头 3 → 2、生命值仍为满、`history` 里留下了它。
* **T02**（`test_t02_blocked_piece_loses_one_heart`）：点击 `(2,0)` 那支横躺、箭头朝右的箭头
  （正前方 `(2,3)` 被另一支的身子压住），断言返回 `blocked`、阻挡者是**整支箭头**
  `((2,3),(3,3),(4,3))`、箭头仍在原位、剩余数不变、生命值 4 → 3。

  同组还有两条：
  * `test_t02_blocker_is_the_nearest_piece_on_the_ray`——射线上可能有好几支箭头，
    挡住它的必须是**最先遇到**的那一支；而且挡路的通常是那支的**身子**，它的箭头在别处
    （这一例里挡路那支的头在 `(2,1)`，根本不在射线上）；断言 `path` 只到被占的那一格为止。
  * `test_t02_blocking_piece_moves_away_then_it_can_fly`——先把挡路的点掉，原本被挡的那支就能飞，
    这就是「连锁」的最小例子。
* **T03**（`test_t03_pieces_at_edges_face_outward_and_can_fly`）：构造 4×5 的边界布局，
  四条边上各一支朝向**棋盘外**的箭头；逐个点击断言返回 `fly`，
  并断言 `ray()` 返回的坐标全部落在棋盘内（不会算出越界坐标），最后 `remaining` 归零、状态 `cleared`。
* **T04**（`test_t04_clear_level_then_go_to_next_level`）：按求解器给出的顺序清空第 1 关 →
  断言 `state == cleared`、剩余为 0；推进到结果面板弹出 → 断言是「通关」面板、
  得分等于本关满分、零失误、已写入存档、下一关已解锁；
  再调用面板上的「下一关」（`next_level()`）→ 断言关卡序号 +1、棋盘已按新关卡重新初始化。
* **T05**（`test_t05_fail_then_restart`）：反复点击一支被挡住的箭头，直到生命值扣到 0 →
  断言 `state == failed`；推进到结果面板弹出 → 断言是「失败」面板、本关 0 分、存档里也是 0；
  再点失败面板的主按钮「重新开始本关」（`restart_level()`）→ 断言状态回到进行中、
  生命值回满、剩余箭头数恢复、面板关闭。
* **T06**（`test_t06_restart_mid_game`）：开局后先点掉一支能飞的（剩余数减少），
  再故意点错一次（生命值 -1），确认两个数都已经变了 → 点「重新开始」→ 断言剩余箭头数恢复为总数、
  生命值回满、状态回到进行中、计时归零、动画列表清空，并且**逐个断言每支箭头都回到了它原来的格子上**。

> 六个用例的编号与命名是刻意对齐作业要求的：`test_t04_*` / `test_t05_*` / `test_t06_*`
> 覆盖的就是作业表格里的第 4~6 项。规则层级（`BoardRuleTestCase`）里测「点到空格子」这类
> 细枝末节的用例**不占用** T 编号，避免出现「名字叫 T04、测的却是别的事」这种对不上的情况。

---

## 四、玩法机制对应的用例

除了作业要求的六条，核心玩法机制每一项都有对应用例兜底。

### 4.1 箭头模型与关卡数据

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_parse_single_cell_piece` | 不带路径段的写法 = 只占一格 | ✅ |
| `test_parse_multi_segment_path` | 路径按「方向字母 + 格数」累加，从尾到头有序 | ✅ |
| `test_parse_default_segment_count_is_one` | 字母后面不写数字就是走一格 | ✅ |
| `test_parse_downward_piece_is_not_broken_by_upper` | 朝下的 `v` 不能被 `upper()` 变成 `V` 而解析失败 | ✅ |
| `test_parse_accepts_lowercase_path_and_extra_spaces` | 大小写混杂、多余空格都要能吃下 | ✅ |
| `test_parse_rejects_bad_specs` | 写法不合法时抛 `ValueError` | ✅ |
| `test_format_piece_round_trip` | `format_piece` 与 `parse_piece` 互为逆运算 | ✅ |
| `test_format_piece_merges_repeated_steps` | 连续同向的步数合并成 `D3` 这种紧凑写法 | ✅ |
| `test_format_piece_rejects_diagonal_step` | 斜着连过去的两格要报错 | ✅ |
| `test_piece_head_tail_and_length` | 头的定义是 `cells[-1]`、尾是 `cells[0]` | ✅ |
| `test_piece_ray_stops_at_board_edge` | 射线只沿一个方向走，到边界为止 | ✅ |
| `test_validate_layout_accepts_good_level` | 合法布局通过校验 | ✅ |
| `test_validate_layout_rejects_empty_level` | 一支箭头都没有的关卡直接报错 | ✅ |
| `test_validate_layout_rejects_out_of_board` | 跑到棋盘外的箭头直接报错 | ✅ |
| `test_validate_layout_rejects_overlap` | 两支箭头重叠在一格上直接报错 | ✅ |
| `test_validate_layout_rejects_broken_path` | 路径不是逐格相邻直接报错 | ✅ |
| `test_validate_layout_rejects_self_crossing` | 自己交叉的路径直接报错 | ✅ |
| `test_validate_layout_rejects_head_direction_mismatch` | 最后一段和箭头方向不一致直接报错（否则箭头会歪在拐角上） | ✅ |
| `test_validate_layout_rejects_piece_facing_own_body` | 箭头正对着自己的箭头直接报错（这种永远飞不出去） | ✅ |
| `test_faces_own_body_false_for_clean_shape` | 正常的拐弯箭头不会被误判成「对着自己」 | ✅ |
| `test_build_grid_marks_owner_index` | 格子表里存的是「这一格属于第几支」 | ✅ |
| `test_assign_colors_gives_every_piece_a_palette_color` | 每支箭头都拿到了调色板里的颜色 | ✅ |
| `test_adjacent_pieces_never_share_a_color` | 上下左右相邻的两支箭头不许同色 | ✅ |
| `test_assign_colors_is_deterministic` | 同样的布局必须得到同样的配色 | ✅ |
| `test_clicking_any_cell_of_a_pipe_selects_the_whole_pipe` | 点箭头的哪一格都算选中它 | ✅ |
| `test_find_blocker_ignores_the_pieces_own_body` | 箭头绕回来贴着自己箭头前方时不算「被自己挡住」 | ✅ |
| `test_click_result_carries_the_ray_path` | 点击结果带上「箭头前方直到边界」的格子 | ✅ |
| `test_path_to_blocker_stops_at_the_nearest_piece` | 红段只画到被占的那一格为止 | ✅ |
| `test_path_to_blocker_returns_the_whole_ray_when_clear` | 通畅时返回整条射线 | ✅ |
| `test_edge_ray_does_not_run_off_the_board` | 边上的射线不越界 | ✅ |
| `test_ray_covers_corner_pieces_correctly` | 角落箭头的射线正确 | ✅ |

### 4.2 求解器

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_solve_simple_level` | 简单关卡能求出通关顺序 | ✅ |
| `test_two_pieces_facing_each_other_are_unsolvable` | 面对面互挡的死锁被判为无解 | ✅ |
| `test_solver_order_actually_clears_the_board` | 求出的顺序真的能按它点完 | ✅ |
| `test_solver_is_monotonic` | 消除一支只让射线更空——单调性（贪心完备的依据） | ✅ |
| `test_solver_rejects_a_layout_with_no_free_piece` | 开局没有出口的布局判无解 | ✅ |
| `test_count_free_pieces_matches_board_query` | 统计口径与 `Board` 的查询一致 | ✅ |
| `test_count_free_pieces_is_monotonic_after_removing_a_piece` | 拿掉一支之后可点数不会减少 | ✅ |

### 4.3 生命值（失误次数）

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_running_out_of_hearts_fails_the_level` | 点错一次固定扣 1；扣到 0 就失败，不会扣成负数 | ✅ |
| `test_clicks_after_failure_are_ignored` | 失败之后再点棋盘不再改变状态 | ✅ |
| `test_hp_left_and_hearts_lost_are_consistent` | `hp_left` 与 `hearts_lost` 两个数始终对得上 | ✅ |
| `test_hp_follows_the_star_table` | 每关的生命值正好是「星级 → 生命值」表里的值 | ✅ |
| `test_tutorial_is_separate_from_numbered_levels` | 教学关单独给 6 颗心，不走星级表 | ✅ |
| `test_draw_hearts_handles_every_count` | 心数从 0 到上限都能画出来，不会越界 | ✅ |

### 4.4 得分机制

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_base_score_is_stars_times_250` | 基础分 = 星级 × 250 | ✅ |
| `test_perfect_bonus_is_20_percent_of_base` | 零失误奖励正好是基础分的 20% | ✅ |
| `test_full_hp_gives_max_score` | 满心通关拿本关满分 | ✅ |
| `test_zero_hp_gives_zero_score` | 生命值耗尽时本关 0 分 | ✅ |
| `test_score_never_exceeds_max_and_never_negative` | 越界参数也算不出超过满分或负数的结果 | ✅ |
| `test_score_is_monotonic_in_remaining_hp` | 剩的心越多分越高（不会出现跳变） | ✅ |
| `test_losing_one_heart_costs_more_than_nothing` | 丢一颗心确实要付出代价 | ✅ |
| `test_lost_hearts_helper` | `lost_hearts` 辅助函数正确 | ✅ |
| `test_total_max_score_sums_levels` | 九关满分合计 = 各关满分之和 | ✅ |
| `test_max_score_is_stars_times_300` | 每关满分 = 星级 × 300 | ✅ |
| `test_total_max_score_is_stable` | 总分上限稳定在 **8400**（改关卡时会立刻报警） | ✅ |
| `test_score_drops_as_hearts_are_lost` | 棋盘自己就知道当前能拿多少分，点错立刻掉 | ✅ |

### 4.5 关卡数据与难度曲线

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_level_count_and_names` | 标准关正好 9 关，编号次序正确 | ✅ |
| `test_every_level_is_solvable` | 九个关卡都存在通关顺序 | ✅ |
| `test_solution_covers_every_piece_exactly_once` | 参考顺序里每支箭头恰好出现一次 | ✅ |
| `test_boards_are_portrait` | 棋盘一律是**竖长方形**（行数 > 列数），贴合手机竖屏 | ✅ |
| `test_board_size_grows_with_level_number` | 棋盘逐关变大，11×8 → 26×18 | ✅ |
| `test_piece_count_grows_with_level_number` | 箭头数逐关变多，21 → 44 | ✅ |
| `test_boards_are_densely_filled` | 铺满率逐关不下降，且整体在 0.9 以上 | ✅ |
| `test_free_pieces_never_increase` | 开局可点数整体不上升（7 → 3），难度不会被顺手改掉 | ✅ |
| `test_difficulty_and_stars_never_go_backwards` | 难度分严格上升、星级单调不减 | ✅ |
| `test_level_rejects_invalid_specs_at_construction` | 构造 `Level` 时就把非法箭头写法拦下来 | ✅ |
| `test_level_rejects_zero_size` | 零尺寸的棋盘直接报错 | ✅ |
| `test_tutorial_has_guided_steps` | 教学关必须带引导步骤，否则界面上没有任何提示 | ✅ |
| `test_tutorial_steps_both_explain_ways` | 教学关的步骤既讲「被挡住」也讲「畅通能飞」 | ✅ |
| `test_tutorial_is_solvable_and_small` | 教学关自己可解，而且足够小（3 支箭头） | ✅ |
| `test_report_shape` | `report_for` 产出的数据结构完整，报告脚本能直接用 | ✅ |

### 4.6 进度与解锁

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_fresh_progress_only_has_level_one_unlocked` | 全新存档只解锁第 1 关 | ✅ |
| `test_clearing_a_level_unlocks_the_next_one` | 通关一关才解锁下一关 | ✅ |
| `test_clearing_is_idempotent` | 重复标记同一关不会出错 | ✅ |
| `test_mark_all_cleared_opens_everything` | 「全部通关」状态下每关都可进入 | ✅ |
| `test_scores_keep_the_best_result` | 每关只留最高分，重玩手感差不会冲掉纪录 | ✅ |
| `test_total_score_sums_best_scores` | 总分 = 各关最高分之和 | ✅ |
| `test_best_score_of_unknown_level_is_zero` | 不存在的关卡取分返回 0，不抛异常 | ✅ |
| `test_save_and_load_round_trip` | 存档写到磁盘后能原样读回来 | ✅ |
| `test_saved_file_is_valid_json_with_version` | 落盘的是合法 JSON，且带 version 字段 | ✅ |
| `test_corrupt_save_file_falls_back_to_fresh_progress` | 存档损坏时当成空进度，而不是崩溃 | ✅ |
| `test_save_file_with_wrong_shapes_is_sanitised` | 存档里的字段类型被人改坏时会被清洗掉 | ✅ |
| `test_reset_clears_everything` | 清空进度后回到只解锁第 1 关，最高分一并清掉 | ✅ |

### 4.7 计时、提示、辅助线与缩放（四个小工具）

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_timer_only_runs_while_playing` | 只在进行中走秒，结束 / 重开后停住、归零 | ✅ |
| `test_hint_picks_a_piece_that_can_actually_fly` | 提示指的那一支必须真的能飞出 | ✅ |
| `test_hint_prefers_unlocking_the_most_pieces` | 提示挑的是「消掉它最能解锁其它箭头」的那一支 | ✅ |
| `test_hint_does_not_corrupt_the_board` | 算提示不会改棋盘状态 | ✅ |
| `test_use_hint_sets_and_expires_the_highlight` | 提示环到时间自己消失，不会一直挂着 | ✅ |
| `test_clicking_the_hinted_piece_clears_the_highlight` | 点了被提示的那支之后环立刻收掉 | ✅ |
| `test_use_hint_outside_a_level_only_toasts` | 不在关卡里点提示只弹一句话，不崩 | ✅ |
| `test_guides_toggle_updates_the_button_state` | 辅助线开关：状态、按钮 `on` 标记、渲染三者一致 | ✅ |
| `test_guides_draw_for_every_level` | 九关都能开着辅助线正常画出来 | ✅ |
| `test_guide_segment_is_parallel_to_the_arrow` | 辅助线必须沿箭头方向（叉积为 0），且长度与射线一致 | ✅ |
| `test_guide_segment_ends_inside_the_blocking_cell` | 被挡时线的终点落在**射线上被占的那一格**里 | ✅ |
| `test_guide_segment_disappears_with_the_piece` | 箭头飞走之后它的辅助线也要消失 | ✅ |
| `test_zoom_range_is_respected` / `test_zoom_by_moves_by_one_step` | 缩放范围 60%~180%，步进正确 | ✅ |
| `test_zoom_is_rounded_to_two_decimals` | 反复缩放不会积累浮点误差 | ✅ |
| `test_zoom_ratio_reports_current_position` / `test_slider_drag_sets_the_zoom` | 滑杆位置与缩放倍率双向一致 | ✅ |
| `test_cell_size_scales_with_zoom` / `test_base_cell_is_within_limits` | 格子边长随缩放变化，且有上下限 | ✅ |
| `test_board_fits_the_viewport_at_default_zoom` | 默认 100% 时棋盘完整落在视口内（不溢出） | ✅ |
| `test_board_fills_the_viewport_vertically` | 竖屏下棋盘把视口纵向填满，不留空白条 | ✅ |
| `test_board_never_leaves_the_viewport` | 拖动到极值也不会把棋盘拖出视口 | ✅ |
| `test_small_board_is_centred` | 小棋盘居中显示，不贴着左上角 | ✅ |
| `test_pan_is_clamped_back_into_range` | 平移量被夹回合法区间 | ✅ |
| `test_zoom_sweep_keeps_the_piece_cache_bounded` | 反复缩放不会让箭头贴图缓存无限增长 | ✅ |
| `test_cell_rect_and_center_agree` / `test_cell_at_pos_round_trip` | 格子坐标 ↔ 像素坐标互为逆运算 | ✅ |
| `test_cell_at_pos_outside_the_board_is_none` | 棋盘外取格返回 None | ✅ |

**「提示」里的「最优」是怎么定义的。** 这个玩法有个性质：点掉一支能飞的箭头，
只会让其它箭头的射线更空，不会把自己玩死。所以提示挑的是
「消掉它之后能连带解锁最多其它箭头」的那一支——第一步点对了，后面往往就顺了。
测试就直接拿这条定义去对：临时把候选从棋盘上摘掉、数一遍还剩几支能飞、再放回去，
最后和 `Game.best_hint()` 给出的选择逐个比对。

**辅助线为什么不按「能不能飞」上色。** 那条线只帮玩家看清方向关系；
一旦畅通画绿、被挡画红，等于把答案画在脸上，这一局该有的思考就没了。
所以两个状态用同一个颜色（`config.COLOR_GUIDE`），
只有鼠标悬停某支箭头时，才用绿 / 红两色高亮那一条具体路径。

**辅助线几何为什么单独抽出来测。** 早先画悬停 / 辅助线时是直接拿
「挡路那支的**箭头**」（`blocker.head`）当终点的，可一支箭头是好几格，
压在射线上的往往是它的**身子**，箭头可能在很远的另一头——
于是线会斜穿整个棋盘连到一个方向无关的格子上（悬停到这类箭头上还会直接抛 `ValueError`）。
现在抽成 `Game.guide_segment(piece)`，测试用叉积卡「必须共线」、
用点积卡「长度与射线一致」、再用矩形包含卡「被挡时终点落在哪一格」，
三条一起把这处几何钉住。

### 4.8 界面与渲染

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_piece_surface_is_cached` / `test_clear_caches_drops_piece_surfaces` | 箭头贴图有缓存，改配置时能清掉 | ✅ |
| `test_piece_surface_differs_by_cell_size` | 不同格距得到不同尺寸的贴图 | ✅ |
| `test_piece_surface_geometry_places_each_cell_correctly` | 贴图里每一格的位置都对得上 | ✅ |
| `test_piece_surface_big_enough_for_the_whole_pipe` | 贴图装得下整条箭头，拐弯也不会被裁掉 | ✅ |
| `test_piece_color_falls_back_to_palette` | 颜色缺失时回退到调色板，不崩 | ✅ |
| `test_piece_surface_cache_stays_bounded` | 贴图缓存条数有上限 | ✅ |
| `test_draw_piece_accepts_alpha_and_offset` | 箭头绘制支持半透明与偏移（飞出动画要用） | ✅ |
| `test_wrap_text_respects_max_width` | 中文折行不超宽 | ✅ |
| `test_wrap_text_never_starts_a_line_with_punctuation` | 折行后不允许有行以收尾标点开头 | ✅ |
| `test_wrap_text_handles_short_and_empty_input` | 空串 / 极短文本不会死循环 | ✅ |
| `test_text_width_and_draw_text_agree` | 量出来的宽度和实际画出来的一致 | ✅ |
| `test_draw_paragraph_returns_consumed_height` | 段落绘制返回真实占用高度，布局靠它排 | ✅ |
| `test_slider_helpers_round_trip` / `test_slider_ratio_is_clamped` | 滑杆取值与比例互为逆运算，且被夹在 0~1 | ✅ |
| `test_slider_track_leaves_room_for_the_knob` | 滑杆两端给滑钮留了位置，不会画到轨道外面 | ✅ |
| `test_icons_do_not_raise` / `test_stars_and_lock_do_not_raise` / `test_round_rect_alpha_does_not_raise` | 图标、星级、挂锁、圆角半透明矩形都能画 | ✅ |
| `test_mix_color_endpoints` / `test_lighten_and_darken_move_toward_the_right_end` | 颜色混合与提亮 / 压暗的方向正确 | ✅ |
| `test_vertical_gradient_size` | 竖向渐变尺寸正确 | ✅ |
| `test_panel_geometry_holds_content` / `test_overlay_buttons_stay_inside_the_panel` | 结果面板装得下内容，按钮不会跑到面板外 | ✅ |
| `test_play_buttons_stay_inside_the_window` / `test_menu_buttons_stay_inside_the_window` | 游戏界面与主菜单的按钮都在窗口内 | ✅ |
| `test_level_cards_stay_inside_the_window` / `test_level_cards_do_not_overlap` | 关卡卡片的 3×3 排布不越界、不重叠 | ✅ |
| `test_tutorial_bar_is_inside_the_window` / `test_tutorial_bar_does_not_overlap_the_toolbar` / `test_tutorial_viewport_leaves_room_for_the_bar` | 教学讲解条在窗口内、不压工具栏，且棋盘为它让出了位置 | ✅ |
| `test_menu_demo_specs_match_their_captions` / `test_demo_specs_parse_and_are_deterministic` / `test_demo_colors_are_distinct` | 主菜单上那两张小示例图与说明文字对得上、能解析、颜色可区分 | ✅ |
| `test_event_handling_smoke` / `test_quit_sets_the_running_flag` | 事件分发能跑完；退出标志正确 | ✅ |

### 4.9 观感回归（画面相关的用例）

这一组是「逻辑全对但看着不对」的问题逼出来的，用来钉住视觉上的几个约定：

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_levels_use_a_variety_of_colors` | 一色到底太单调：每关用到的颜色种类要够多 | ✅ |
| `test_colors_come_from_the_palette` | 箭头颜色只可能来自那 12 色调色板 | ✅ |
| `test_no_two_adjacent_pieces_share_a_color_in_any_level` | 所有关卡都守住「相邻不同色」 | ✅ |
| `test_every_level_draws_and_saves` | 九关都能画出来并截图 | ✅ |
| `test_every_level_draws_with_guides_and_hover` | 开着辅助线 + 悬停时也能画 | ✅ |
| `test_every_level_draws_with_animations_running` | 有动画在跑时也能画 | ✅ |
| `test_hover_highlight_works_on_any_cell_of_a_pipe` | 悬停箭头的任何一格都能高亮整条 | ✅ |
| `test_hover_on_empty_cell_highlights_nothing` | 悬停空格不该亮任何东西 | ✅ |
| `test_render_does_not_mutate_the_board` | 画一遍不能改棋盘状态——渲染和逻辑必须完全分开 | ✅ |
| `test_background_follows_theme` / `test_every_scene_draws` | 背景跟随主题切换，三个场景都画得出来 | ✅ |

**「去底格」的改动。** 新版棋盘不再画每一格的底框，只有一片极淡的点阵
（`app.draw_board()`）。原因是这个玩法的难度来自「在一堆箭头里找出能点的那支」，
而几十个空方框会让视线一直被拽住——那是「乱」不是「难」。

**「相邻不同色」的改动。** 参照画面里同色的箭头挨在一起会连成一片、看不出有几支，
所以 `pieces.assign_colors` 用贪心给每支挑一个邻居没用过的颜色。
注意这和上一版的方向色是两回事：**上一版**「一个方向一个颜色」（上=青绿 下=橙 左=紫 右=粉），
**这一版**改成糖果色随机、只约束相邻不同色。测试也跟着换成三条：
颜色必须来自调色板、相邻不许同色、颜色种类不能太少。

## 五、边界与容错用例

| 用例 | 验证内容 | 结果 |
| --- | --- | --- |
| `test_clicking_empty_cell_does_nothing` | 点到空格子不扣生命值、不改变棋盘 | ✅ |
| `test_click_outside_board_is_ignored` | 点击负数 / 超界坐标返回 `ignored`，不抛异常 | ✅ |
| `test_clicks_after_clearing_are_ignored` | 本关通关后再点棋盘状态不再变化 | ✅ |
| `test_clicks_after_failure_are_ignored` | 失败后再点棋盘状态不再变化 | ✅ |
| `test_reset_restores_initial_state` | `reset()` 能完整恢复布局与生命值 | ✅ |
| `test_starts_in_menu` / `test_enter_levels_and_back` | 启动落在主菜单，主菜单 ↔ 关卡总览能来回切 | ✅ |
| `test_start_level_rejects_out_of_range` | 用越界的关卡号开局会被拦住 | ✅ |
| `test_locked_level_cannot_be_started_and_shows_a_toast` | 未解锁的关卡绕过界面也进不去，并给出提示 | ✅ |
| `test_clicking_a_locked_card_does_not_enter` | 点锁着的卡片不开局 | ✅ |
| `test_clicking_an_unlocked_card_enters_the_level` | 点已解锁的卡片直接进那一关 | ✅ |
| `test_escape_returns_to_the_menu` / `test_escape_closes_the_settings_panel_first` | `Esc` 先关浮层、再返回主菜单 | ✅ |
| `test_r_restarts_the_level` / `test_h_and_g_shortcuts` / `test_plus_and_minus_zoom_shortcuts` | `R` / `H` / `G` / `+` / `-` 快捷键都能用 | ✅ |
| `test_space_starts_the_game_from_the_menu` | 主菜单与关卡总览里按空格继续挑战 | ✅ |
| `test_toast_expires` | 提示气泡到时间自己消失 | ✅ |
| `test_reset_progress_needs_two_clicks` | 「清空进度」要点两次才真的清，避免手滑 | ✅ |
| `test_settings_overlay_opens_and_closes` / `test_theme_toggle_switches_and_returns` / `test_theme_toggle_works_in_every_scene` | 设置面板开关正常；夜间 / 日间能来回切，各场景都生效 | ✅ |
| `test_drag_on_board_does_not_count_as_a_click` | 放大后拖动棋盘不会被误判成「点了那支箭头」 | ✅ |
| `test_short_press_is_treated_as_a_click` / `test_tiny_mouse_jitter_still_counts_as_a_click` | 短按与轻微手抖仍然算点击 | ✅ |
| `test_pressing_a_button_is_not_a_board_drag` / `test_pressing_the_viewport_targets_the_board` | 按在按钮上 / 按在视口上各自路由正确 | ✅ |
| `test_slider_is_not_draggable_outside_a_level` | 不在关卡里时滑杆不响应 | ✅ |
| `test_default_zoom_sits_at_one_third_of_the_slider` | 默认 100% 在 60%~180% 区间里正好落在三分之一处 | ✅ |
| `test_tutorial_runs_through_all_steps` | 照着引导点，4 步依次推进，最后引导结束 | ✅ |
| `test_tutorial_skips_steps_that_no_longer_apply` | 玩家不按提示点时，失效的步骤被自动跳过，不卡住 | ✅ |
| `test_tutorial_does_not_score_or_unlock` | 走完教学关：不算分、不解锁、不写存档 | ✅ |
| `test_tutorial_can_be_replayed` | 教学关随时可以从主菜单重进 | ✅ |
| `test_tutorial_shows_a_hint_ring_on_the_current_target` | 高亮环只圈在当前该点的那一支上 | ✅ |
| `test_final_level_clear_shows_all_clear` / `test_next_level_advances_after_winning` | 打通最后一关弹「全部通关」面板；点「下一关」正确推进 | ✅ |
| `test_click_cell_returns_none_while_an_overlay_is_open` | 结果面板打开时点棋盘无效 | ✅ |

---

## 六、完整测试日志

```
test_animations_draw_without_raising ... ok
test_floating_heart_rises_and_ends ... ok
test_floating_heart_splits_into_two_halves ... ok   「心碎」动画把整颗心切成左右两半，两半拼起来必须还是整颗心。
test_floating_text_rises_and_ends ... ok
test_fly_out_finishes_and_keeps_moving_away ... ok
test_fly_out_respects_direction ... ok
test_fly_out_tail_follows_the_bend ... ok   L 形箭头：尾巴没过弯时沿第一段滑，过弯后沿箭头方向直线出视口。
test_impact_fades_out_and_ends ... ok
test_impact_offset_moves_along_its_direction ... ok
test_impact_tint_is_cached_per_level ... ok
test_impact_tint_moves_toward_red ... ok   被撞的箭头要真的泛红——这是「点错了」最直接的反馈。
test_background_follows_theme ... ok
test_every_scene_draws ... ok
test_adjacent_pieces_never_share_a_color ... ok   相邻箭头同色会「糊成一片」，看不出是几支——所有关卡都要守住这条。
test_assign_colors_gives_every_piece_a_palette_color ... ok
test_assign_colors_is_deterministic ... ok   同样的布局必须得到同样的配色，否则每次打开画面都不一样。
test_build_grid_marks_owner_index ... ok
test_clearing_every_piece_clears_the_level ... ok
test_click_outside_board_is_ignored ... ok
test_click_result_carries_the_ray_path ... ok   点击结果要带上「箭头前方直到边界」的格子，界面靠它画路径提示。
test_clicking_any_cell_of_a_pipe_selects_the_whole_pipe ... ok   点箭头的哪一格都算选中它——玩家看到的是整条箭头。
test_clicking_empty_cell_does_nothing ... ok
test_clicks_after_clearing_are_ignored ... ok
test_clicks_after_failure_are_ignored ... ok
test_edge_ray_does_not_run_off_the_board ... ok   边上的射线只到边界为止，不能越界算出负坐标或越界的格子。
test_faces_own_body_false_for_clean_shape ... ok
test_find_blocker_ignores_the_pieces_own_body ... ok   箭头绕回来贴着自己的箭头前方时，不算「被自己挡住」。
test_format_piece_merges_repeated_steps ... ok
test_format_piece_rejects_diagonal_step ... ok
test_format_piece_round_trip ... ok   format_piece 是 parse_piece 的逆运算，生成器靠它打印布局。
test_hp_left_and_hearts_lost_are_consistent ... ok
test_parse_accepts_lowercase_path_and_extra_spaces ... ok   关卡数据是手写与脚本混着的，大小写与多余空格都要能吃下。
test_parse_default_segment_count_is_one ... ok   字母后面不写数字就是走一格。
test_parse_downward_piece_is_not_broken_by_upper ... ok   朝下的 'v' 不能被 upper() 变成 'V' 而解析失败。
test_parse_multi_segment_path ... ok   路径按「方向字母 + 格数」累加，从尾到头有序。
test_parse_rejects_bad_specs ... ok
test_parse_single_cell_piece ... ok   不带路径段的写法 = 只占一格。
test_path_to_blocker_returns_the_whole_ray_when_clear ... ok
test_path_to_blocker_stops_at_the_nearest_piece ... ok   悬停路径要截断在挡路那一格，再往后跟「为什么飞不出去」无关。
test_piece_head_tail_and_length ... ok
test_piece_ray_stops_at_board_edge ... ok   射线从箭头出发、直到棋盘边界，且**不含箭头自己**。
test_ray_covers_corner_pieces_correctly ... ok
test_reset_restores_initial_state ... ok
test_running_out_of_hearts_fails_the_level ... ok
test_score_drops_as_hearts_are_lost ... ok   棋盘上的 score 是「此刻通关能拿多少」，丢心就往下掉。
test_t01_free_piece_flies_out_and_disappears ... ok
test_t02_blocked_piece_loses_one_heart ... ok
test_t02_blocker_is_the_nearest_piece_on_the_ray ... ok   射线上可能有好几支箭头，挡住它的应当是**最先遇到**的那一支。
test_t02_blocking_piece_moves_away_then_it_can_fly ... ok   把挡路的点掉之后，原本被挡的那支就能飞了（连锁的最小例子）。
test_t03_pieces_at_edges_face_outward_and_can_fly ... ok
test_validate_layout_accepts_good_level ... ok
test_validate_layout_rejects_broken_path ... ok   路径必须逐格相邻，不能跳格。
test_validate_layout_rejects_empty_level ... ok
test_validate_layout_rejects_head_direction_mismatch ... ok   最后一段必须和箭头方向一致，否则画出来的箭头会歪在拐角上。
test_validate_layout_rejects_out_of_board ... ok
test_validate_layout_rejects_overlap ... ok
test_validate_layout_rejects_piece_facing_own_body ... ok   箭头正对着自己的箭头 -> 永远飞不出去，必须在关卡校验里拦掉。
test_validate_layout_rejects_self_crossing ... ok
test_base_cell_is_within_limits ... ok
test_board_fills_the_viewport_vertically ... ok   竖屏棋盘应当把视口高度基本占满，否则上下会各空出一条。
test_board_fits_the_viewport_at_default_zoom ... ok
test_board_never_leaves_the_viewport ... ok
test_cell_at_pos_outside_the_board_is_none ... ok
test_cell_at_pos_round_trip ... ok
test_cell_rect_and_center_agree ... ok
test_cell_size_scales_with_zoom ... ok
test_click_cell_returns_none_while_an_overlay_is_open ... ok
test_clicking_a_blocked_pipe_shows_a_floating_heart ... ok
test_clicking_a_free_pipe_starts_a_fly_animation ... ok
test_clicking_a_locked_card_does_not_enter ... ok
test_clicking_an_unlocked_card_enters_the_level ... ok
test_clicking_empty_cell_does_nothing_in_game ... ok
test_clicking_outside_the_board_does_nothing ... ok
test_clicking_the_hinted_piece_clears_the_highlight ... ok
test_default_zoom_sits_at_one_third_of_the_slider ... ok   默认缩放是 100%，它对应的滑杆位置应当就是三分之一处。
test_demo_colors_are_distinct ... ok
test_demo_specs_parse_and_are_deterministic ... ok
test_drag_on_board_does_not_count_as_a_click ... ok   拖动查看棋盘时松手不能顺手点掉一支箭头。
test_enter_levels_and_back ... ok
test_escape_closes_the_settings_panel_first ... ok
test_escape_returns_to_the_menu ... ok
test_event_handling_smoke ... ok   走一遍真实事件分发：移动 / 按下 / 松开 / 按键，都不能抛异常。
test_every_scene_draws_without_raising ... ok
test_final_level_clear_shows_all_clear ... ok
test_guide_segment_disappears_with_the_piece ... ok   已经飞走的箭头不再有辅助线。
test_guide_segment_ends_inside_the_blocking_cell ... ok   被挡住时，辅助线的终点要落在**射线上被占的那一格**里。
test_guide_segment_is_parallel_to_the_arrow ... ok   辅助线必须和箭头同向、且在射线不为空时有长度。
test_guides_draw_for_every_level ... ok
test_guides_toggle_updates_the_button_state ... ok
test_h_and_g_shortcuts ... ok
test_hint_does_not_corrupt_the_board ... ok   回归测试：提示的试算必须把 grid 原样还原。
test_hint_picks_a_piece_that_can_actually_fly ... ok
test_hint_prefers_unlocking_the_most_pieces ... ok   提示要挑「点掉之后能连带解锁最多」的那一支，而不是随便一支。
test_level_cards_do_not_overlap ... ok
test_level_cards_stay_inside_the_window ... ok
test_locked_level_cannot_be_started_and_shows_a_toast ... ok
test_menu_buttons_stay_inside_the_window ... ok
test_menu_demo_specs_match_their_captions ... ok   主菜单那两张小图的画面必须和说明文字一致。
test_next_level_advances_after_winning ... ok
test_overlay_buttons_stay_inside_the_panel ... ok
test_pan_is_clamped_back_into_range ... ok   拖到边界之后 pan 要记回实际偏移，否则往回拖有一段是空转。
test_panel_geometry_holds_content ... ok   结算面板要在 64 像素高的窗口里放得下，还要在窗口内。
test_play_buttons_stay_inside_the_window ... ok
test_plus_and_minus_zoom_shortcuts ... ok
test_pressing_a_button_is_not_a_board_drag ... ok
test_pressing_the_viewport_targets_the_board ... ok
test_quit_sets_the_running_flag ... ok
test_r_restarts_the_level ... ok
test_reset_progress_needs_two_clicks ... ok   清空进度是不可逆的，第一次点只提醒、第二次才真的清。
test_settings_overlay_opens_and_closes ... ok
test_short_press_is_treated_as_a_click ... ok
test_slider_drag_sets_the_zoom ... ok   按住滑杆拖动：滑杆中点对应 120%，两端是最小 / 最大。
test_slider_is_not_draggable_outside_a_level ... ok
test_small_board_is_centred ... ok
test_space_starts_the_game_from_the_menu ... ok
test_start_level_rejects_out_of_range ... ok
test_starting_a_level_sets_up_the_board ... ok
test_starts_in_menu ... ok
test_t04_clear_level_then_go_to_next_level ... ok   T04：清空本关全部箭头 -> 弹「通关」面板并记分 -> 点「下一关」进入下一关。
test_t05_fail_then_restart ... ok   T05：把生命值点光 -> 弹「失败」面板且不得分 -> 「重新开始本关」能接着玩。
test_t06_restart_mid_game ... ok   T06：进行中点掉一支、再故意点错一次，重新开始后布局与生命值都要恢复。
test_theme_toggle_switches_and_returns ... ok
test_theme_toggle_works_in_every_scene ... ok
test_timer_only_runs_while_playing ... ok   分出胜负之后时钟要停下来，否则玩家盯着结算面板那几秒用时还在涨。
test_tiny_mouse_jitter_still_counts_as_a_click ... ok   手抖了几像素不该被当成拖动——阈值是 DRAG_THRESHOLD。
test_toast_expires ... ok
test_tutorial_bar_does_not_overlap_the_toolbar ... ok
test_tutorial_bar_is_inside_the_window ... ok
test_tutorial_can_be_replayed ... ok
test_tutorial_does_not_score_or_unlock ... ok
test_tutorial_runs_through_all_steps ... ok   教学关的每一步期望值都必须和实际结果对上——教程骗人会直接误导玩家。
test_tutorial_shows_a_hint_ring_on_the_current_target ... ok
test_tutorial_skips_steps_that_no_longer_apply ... ok   玩家完全可以乱点；不管怎么点，引导都不能指着一支已经飞走的箭头。
test_tutorial_viewport_leaves_room_for_the_bar ... ok   讲解条要占掉一块地方，棋盘视口得相应让出来，否则会叠在一起。
test_use_hint_outside_a_level_only_toasts ... ok
test_use_hint_sets_and_expires_the_highlight ... ok
test_zoom_by_moves_by_one_step ... ok
test_zoom_is_rounded_to_two_decimals ... ok   zoom 量化到两位小数：滑杆连着拖不会留下几百个无意义的中间值。
test_zoom_range_is_respected ... ok
test_zoom_ratio_reports_current_position ... ok
test_zoom_sweep_keeps_the_piece_cache_bounded ... ok   一路拖过整条滑杆也不能把贴图缓存撑爆。
test_board_size_grows_with_level_number ... ok
test_boards_are_densely_filled ... ok   这一版棋盘是密密麻麻铺满的（参照画面就是这样）。
test_boards_are_portrait ... ok   九关都取竖长方形（行数 > 列数）。
test_difficulty_and_stars_never_go_backwards ... ok
test_every_level_is_solvable ... ok
test_free_pieces_never_increase ... ok   开局可点数逐关不增：这是玩家真正感觉得到的难度。
test_hp_follows_the_star_table ... ok
test_level_count_and_names ... ok
test_level_rejects_invalid_specs_at_construction ... ok   关卡数据写错时要在 import 阶段就炸，而不是等到玩家点进去。
test_level_rejects_zero_size ... ok
test_max_score_is_stars_times_300 ... ok
test_piece_count_grows_with_level_number ... ok   箭头数整体上一路变多。
test_report_shape ... ok
test_solution_covers_every_piece_exactly_once ... ok
test_total_max_score_is_stable ... ok
test_tutorial_has_guided_steps ... ok
test_tutorial_is_separate_from_numbered_levels ... ok   教学关不占编号、不在 LEVELS 里，主菜单上有单独入口。
test_tutorial_is_solvable_and_small ... ok
test_tutorial_steps_both_explain_ways ... ok   教学关必须把「能飞」和「被挡」两种情形各讲一遍。
test_best_score_of_unknown_level_is_zero ... ok
test_clearing_a_level_unlocks_the_next_one ... ok
test_clearing_is_idempotent ... ok
test_corrupt_save_file_falls_back_to_fresh_progress ... ok   存档坏了不能让游戏打不开——退回全新进度就好。
test_fresh_progress_only_has_level_one_unlocked ... ok
test_mark_all_cleared_opens_everything ... ok
test_reset_clears_everything ... ok
test_save_and_load_round_trip ... ok
test_save_file_with_wrong_shapes_is_sanitised ... ok
test_saved_file_is_valid_json_with_version ... ok
test_scores_keep_the_best_result ... ok   重玩只留最高分，不会越玩越低。
test_total_score_sums_best_scores ... ok
test_clear_caches_drops_piece_surfaces ... ok
test_draw_dashed_line_does_not_raise ... ok
test_draw_hearts_handles_every_count ... ok
test_draw_paragraph_returns_consumed_height ... ok
test_draw_piece_accepts_alpha_and_offset ... ok
test_draw_slider_does_not_raise ... ok
test_icons_do_not_raise ... ok
test_lighten_and_darken_move_toward_the_right_end ... ok
test_mix_color_endpoints ... ok
test_piece_color_falls_back_to_palette ... ok
test_piece_surface_big_enough_for_the_whole_pipe ... ok
test_piece_surface_cache_stays_bounded ... ok   缓存上限是硬要求：缩放滑杆一路拖过去会生成上百个格距。
test_piece_surface_differs_by_cell_size ... ok
test_piece_surface_geometry_places_each_cell_correctly ... ok   贴图 + 偏移必须能把每一格摆回它该在的位置。
test_piece_surface_is_cached ... ok   同一支箭头重复取贴图必须命中缓存，否则每帧都在重新渲染。
test_round_rect_alpha_does_not_raise ... ok
test_slider_helpers_round_trip ... ok
test_slider_ratio_is_clamped ... ok
test_slider_track_leaves_room_for_the_knob ... ok
test_stars_and_lock_do_not_raise ... ok
test_text_width_and_draw_text_agree ... ok
test_vertical_gradient_size ... ok
test_wrap_text_handles_short_and_empty_input ... ok
test_wrap_text_never_starts_a_line_with_punctuation ... ok   逐字折行很容易把句号甩到下一行，中文排版上很难看。
test_wrap_text_respects_max_width ... ok
test_base_score_is_stars_times_250 ... ok
test_full_hp_gives_max_score ... ok
test_losing_one_heart_costs_more_than_nothing ... ok   丢一颗心必须真的掉分，否则「别点错」这件事就没有反馈。
test_lost_hearts_helper ... ok
test_perfect_bonus_is_20_percent_of_base ... ok
test_score_is_monotonic_in_remaining_hp ... ok
test_score_never_exceeds_max_and_never_negative ... ok
test_total_max_score_sums_levels ... ok
test_zero_hp_gives_zero_score ... ok
test_count_free_pieces_is_monotonic_after_removing_a_piece ... ok   每消掉一支，可点数只可能变多或不变（不会变少）。
test_count_free_pieces_matches_board_query ... ok
test_solve_simple_level ... ok
test_solver_is_monotonic ... ok   消除一支箭头只会让别的射线更空，所以「能飞」不会因为等待而失效。
test_solver_order_actually_clears_the_board ... ok   求解器给出的顺序拿去真的点一遍，必须能清空。
test_solver_rejects_a_layout_with_no_free_piece ... ok   一个连开局都点不动的循环，应当被判定为无解。
test_two_pieces_facing_each_other_are_unsolvable ... ok   互相指着的两支谁也飞不出去——求解器必须报「无解」而不是死循环。
test_colors_come_from_the_palette ... ok
test_every_level_draws_and_saves ... ok   每个关卡都完整画一遍——渲染报错在这一步就该暴露。
test_every_level_draws_with_animations_running ... ok   动画播到一半时也要能画——撞击那支的染色贴图只在闪得厉害时才用到。
test_every_level_draws_with_guides_and_hover ... ok   辅助线 + 悬停高亮一起上的时候最容易漏画或画错层，逐关过一遍。
test_hover_highlight_works_on_any_cell_of_a_pipe ... ok
test_hover_on_empty_cell_highlights_nothing ... ok
test_levels_use_a_variety_of_colors ... ok   一支一色但整体太单调也不行——每关用到的颜色种类要够多。
test_no_two_adjacent_pieces_share_a_color_in_any_level ... ok
test_render_does_not_mutate_the_board ... ok   画一遍不能改棋盘状态——渲染和逻辑必须完全分开。
```

---

## 七、关卡可解性校验

执行 `python tools/verify_levels.py`（完整输出，含每关的布局图与参考通关顺序）。
布局图里 `.` 是空格、`o` 是箭头身子、`^v<>` 是箭头：

```
==============================================================================
《一箭又一箭》关卡校验报告
==============================================================================

教学关（主菜单独立入口：不计分、不占关卡编号、不用解锁）
             棋盘 5×5   箭头  3 支   密度 0.32   开局可点 2 支
         难度 ★   生命值 6 颗   本关满分 不计分
------------------------------------------------------------------------------
    0 | ....o
    1 | ....v
    2 | oo>o.
    3 | ...o.
    4 | ...v.
------------------------------------------------------------------------------
   [OK] 可解，共 3 步
   参考顺序：(4,3)下 -> (1,4)下 -> (2,2)右
   引导步骤：4 步（点哪里、为什么，都在关卡里的高亮环上）

第  1 关  初次拉弓   棋盘 11×8   箭头 21 支   密度 0.92   开局可点 7 支
         难度 ★   生命值 4 颗   本关满分 300 分
------------------------------------------------------------------------------
    0 | oooooooo
    1 | voooooo>
    2 | oovooooo
    3 | voovv..v
    4 | ooooo..o
    5 | ovooo..o
    6 | oooov<oo
    7 | <ovvoo<o
    8 | o>oooooo
    9 | oooovooo
   10 | ov.vvvvo
------------------------------------------------------------------------------
   [OK] 可解，共 21 步
   参考顺序：(10,1)下 -> (10,6)下 -> (7,0)左 -> (10,5)下 -> (10,3)下 -> (10,4)下 -> (1,7)右 -> (7,2)下 -> (7,3)下 -> (9,4)下 -> (7,6)左 -> (6,4)下 -> (2,2)下 -> (3,4)下 -> (6,5)左 -> (3,3)下 -> (8,1)右 -> (3,7)下 -> (5,1)下 -> (3,0)下 -> (1,0)下

第  2 关  交叉路口   棋盘 13×9   箭头 23 支   密度 0.97   开局可点 6 支
         难度 ★   生命值 4 颗   本关满分 300 分
------------------------------------------------------------------------------
    0 | voooooo.^
    1 | ooo>ooooo
    2 | vooooooo^
    3 | ooooooooo
    4 | ooovovoo>
    5 | oooooooo>
    6 | voovo>o>>
    7 | ooooo>.o>
    8 | oooooooo^
    9 | vooooo.oo
   10 | ooovoooo^
   11 | v.ooooooo
   12 | <ooooo^oo
------------------------------------------------------------------------------
   [OK] 可解，共 23 步
   参考顺序：(12,0)左 -> (4,8)右 -> (0,8)上 -> (7,8)右 -> (5,8)右 -> (6,8)右 -> (11,0)下 -> (7,5)右 -> (2,8)上 -> (6,7)右 -> (8,8)上 -> (9,0)下 -> (10,3)下 -> (6,5)右 -> (10,8)上 -> (4,5)下 -> (6,0)下 -> (6,3)下 -> (1,3)右 -> (4,3)下 -> (2,0)下 -> (0,0)下 -> (12,6)上

第  3 关  连锁反应   棋盘 14×10   箭头 22 支   密度 0.94   开局可点 5 支
         难度 ★★   生命值 5 颗   本关满分 600 分
------------------------------------------------------------------------------
    0 | o^oo>ooooo
    1 | ooooooooo>
    2 | ooooooo..o
    3 | vooovooo.o
    4 | oooooooo.o
    5 | oooovooooo
    6 | ooooovoo.o
    7 | ovoooooo.o
    8 | vooo.vvooo
    9 | ooovoo<oo^
   10 | voooo<oooo
   11 | <ooooooooo
   12 | .oooooooo>
   13 | <o<o<o<ooo
------------------------------------------------------------------------------
   [OK] 可解，共 22 步
   参考顺序：(13,0)左 -> (11,0)左 -> (0,1)上 -> (12,9)右 -> (1,9)右 -> (13,2)左 -> (10,0)下 -> (8,0)下 -> (7,1)下 -> (10,5)左 -> (13,4)左 -> (9,3)下 -> (3,0)下 -> (13,6)左 -> (9,6)左 -> (8,5)下 -> (8,6)下 -> (6,5)下 -> (5,4)下 -> (3,4)下 -> (0,4)右 -> (9,9)上

第  4 关  四面楚歌   棋盘 16×11   箭头 27 支   密度 0.94   开局可点 5 支
         难度 ★★★   生命值 6 颗   本关满分 900 分
------------------------------------------------------------------------------
    0 | ooo>.^o>^^^
    1 | ooooo>ooooo
    2 | o>oooooooo^
    3 | oooo.^oo>oo
    4 | ooo>^oooooo
    5 | oo>oo.^^^oo
    6 | oooo.oooo.o
    7 | ooo..oooo.o
    8 | ooooooo^ooo
    9 | ooooooooooo
   10 | oooooo^o..^
   11 | ooooooooooo
   12 | ^oooo^^^oo^
   13 | ooooooooooo
   14 | oooooooooo>
   15 | ^oooooooooo
------------------------------------------------------------------------------
   [OK] 可解，共 27 步
   参考顺序：(0,8)上 -> (0,10)上 -> (0,9)上 -> (14,10)右 -> (0,5)上 -> (0,7)右 -> (2,10)上 -> (0,3)右 -> (1,5)右 -> (3,8)右 -> (2,1)右 -> (3,5)上 -> (4,4)上 -> (12,0)上 -> (4,3)右 -> (5,8)上 -> (5,7)上 -> (5,6)上 -> (15,0)上 -> (10,10)上 -> (5,2)右 -> (8,7)上 -> (10,6)上 -> (12,10)上 -> (12,7)上 -> (12,6)上 -> (12,5)上

第  5 关  错位走廊   棋盘 18×12   箭头 28 支   密度 0.93   开局可点 4 支
         难度 ★★★   生命值 6 颗   本关满分 900 分
------------------------------------------------------------------------------
    0 | <o<oo<o^o<oo
    1 | .oooooooo<oo
    2 | .<ooooo<oooo
    3 | .oo<oo<ooooo
    4 | <oooooo<oooo
    5 | ^^..oooooooo
    6 | ooo..ooooooo
    7 | ooo.^.ooooo^
    8 | ^ooooooooooo
    9 | oooo^oooooo.
   10 | oooooo.oooo.
   11 | ^oo^^oooooo.
   12 | ooooooooooo.
   13 | oooooo^^^ooo
   14 | oooooooooo.^
   15 | ^.oo>ooooooo
   16 | ooooooooooo^
   17 | oooooooooooo
------------------------------------------------------------------------------
   [OK] 可解，共 28 步
   参考顺序：(0,0)左 -> (2,1)左 -> (4,0)左 -> (0,7)上 -> (5,0)上 -> (5,1)上 -> (0,2)左 -> (3,3)左 -> (0,5)左 -> (2,7)左 -> (8,0)上 -> (4,7)左 -> (7,4)上 -> (3,6)左 -> (11,0)上 -> (0,9)左 -> (13,8)上 -> (1,9)左 -> (13,7)上 -> (13,6)上 -> (9,4)上 -> (7,11)上 -> (11,3)上 -> (11,4)上 -> (14,11)上 -> (16,11)上 -> (15,4)右 -> (15,0)上

第  6 关  纵横交错   棋盘 20×14   箭头 33 支   密度 0.95   开局可点 4 支
         难度 ★★★★   生命值 6 颗   本关满分 1200 分
------------------------------------------------------------------------------
    0 | ^oo<oo<ooo<o<o
    1 | oooo.ooooooooo
    2 | <o^o...ooooooo
    3 | <oooo<ooo<o<oo
    4 | oo^.oooooooooo
    5 | o^oo.<oooooooo
    6 | oooooo<ooooooo
    7 | o^oooo<ooo<ooo
    8 | ^ooooooooooooo
    9 | ooooooo...oooo
   10 | ^^^ooooo..oooo
   11 | oooooooooooooo
   12 | ooooo>ooo.oooo
   13 | o^ooo^oo..oooo
   14 | ooo^o^ooo>oooo
   15 | oooooooooooo^^
   16 | ^ooooooooooooo
   17 | oooooooooooooo
   18 | ooooooooooo^o>
   19 | oooooooooooooo
------------------------------------------------------------------------------
   [OK] 可解，共 33 步
   参考顺序：(2,0)左 -> (0,0)上 -> (18,13)右 -> (3,0)左 -> (0,3)左 -> (2,2)上 -> (0,6)左 -> (8,0)上 -> (3,5)左 -> (5,1)上 -> (4,2)上 -> (10,0)上 -> (0,10)左 -> (3,9)左 -> (5,5)左 -> (6,6)左 -> (7,1)上 -> (16,0)上 -> (0,12)左 -> (10,1)上 -> (10,2)上 -> (3,11)左 -> (7,6)左 -> (13,1)上 -> (7,10)左 -> (15,13)上 -> (15,12)上 -> (12,5)右 -> (14,9)右 -> (14,3)上 -> (13,5)上 -> (18,11)上 -> (14,5)上

第  7 关  长蛇阵   棋盘 22×15   箭头 38 支   密度 0.96   开局可点 3 支
         难度 ★★★★   生命值 6 颗   本关满分 1200 分
------------------------------------------------------------------------------
    0 | ooooooooooooooo
    1 | oooooooooooooov
    2 | oooooooooooooov
    3 | ovooooooooovooo
    4 | vooooooooooooov
    5 | oovooooovvooooo
    6 | oooooooooooooov
    7 | voooooooooooooo
    8 | ooooooovoooooov
    9 | voovooooooooooo
   10 | ooooooovooooooo
   11 | voooooooooooooo
   12 | oooooooooo.oooo
   13 | oooooovvvo.oooo
   14 | vvoo.oooooooooo
   15 | ooovoovoooooooo
   16 | ooooo.<oooooooo
   17 | ooooo..<ooooooo
   18 | ovooo<oooo.oooo
   19 | oovo...oo..oooo
   20 | <oov<o.oo.ooooo
   21 | <ov<ooooo<o<o<o
------------------------------------------------------------------------------
   [OK] 可解，共 38 步
   参考顺序：(21,2)下 -> (21,0)左 -> (20,0)左 -> (19,2)下 -> (18,1)下 -> (21,3)左 -> (14,0)下 -> (14,1)下 -> (20,3)下 -> (11,0)下 -> (15,3)下 -> (16,6)左 -> (17,7)左 -> (20,4)左 -> (18,5)左 -> (9,0)下 -> (9,3)下 -> (21,9)左 -> (15,6)下 -> (7,0)下 -> (5,2)下 -> (21,11)左 -> (13,7)下 -> (13,8)下 -> (13,6)下 -> (4,0)下 -> (3,1)下 -> (21,13)左 -> (10,7)下 -> (8,14)下 -> (8,7)下 -> (3,11)下 -> (6,14)下 -> (5,9)下 -> (5,8)下 -> (4,14)下 -> (2,14)下 -> (1,14)下

第  8 关  十面埋伏   棋盘 23×17   箭头 43 支   密度 0.94   开局可点 3 支
         难度 ★★★★★   生命值 7 颗   本关满分 1500 分
------------------------------------------------------------------------------
    0 | ooooo>ooooooooooo
    1 | ooooooooooooooooo
    2 | ooooooooooooooooo
    3 | vooooooooooooooov
    4 | oovoooooovoovvooo
    5 | voooooooooooooooo
    6 | oo.oooooooooooooo
    7 | voovoooooovvooovo
    8 | ooo..oooooooovoov
    9 | <ov..ooooo.oooooo
   10 | ooooooovo..ooooov
   11 | ooooooooo..oooooo
   12 | oooooooo...oooooo
   13 | vvvoooooooooooooo
   14 | oooooo<o<oooooooo
   15 | voooooo<ooooooooo
   16 | oooooooo<oo<ooooo
   17 | o.o..<ooooo<ooooo
   18 | o.o.....ooo<ooooo
   19 | voo.<o.oooo<ooooo
   20 | oooooooo<oooooooo
   21 | vooooooooooo<oooo
   22 | <o<o<ooooovo<oo<o
------------------------------------------------------------------------------
   [OK] 可解，共 43 步
   参考顺序：(22,0)左 -> (9,0)左 -> (22,10)下 -> (22,2)左 -> (21,0)下 -> (22,4)左 -> (19,0)下 -> (22,12)左 -> (21,12)左 -> (19,4)左 -> (15,0)下 -> (17,5)左 -> (22,15)左 -> (13,0)下 -> (13,1)下 -> (13,2)下 -> (20,8)左 -> (16,8)左 -> (14,6)左 -> (15,7)左 -> (10,16)下 -> (7,0)下 -> (9,2)下 -> (7,3)下 -> (10,7)下 -> (18,11)左 -> (19,11)左 -> (17,11)左 -> (16,11)左 -> (14,8)左 -> (5,0)下 -> (8,16)下 -> (7,15)下 -> (4,2)下 -> (8,13)下 -> (7,11)下 -> (7,10)下 -> (3,16)下 -> (3,0)下 -> (4,13)下 -> (4,12)下 -> (4,9)下 -> (0,5)右

第  9 关  万箭归一   棋盘 26×18   箭头 44 支   密度 0.94   开局可点 2 支
         难度 ★★★★★   生命值 7 颗   本关满分 1500 分
------------------------------------------------------------------------------
    0 | ooooo>o>oo>oooo>o>
    1 | oooo>oooooooo>oo>^
    2 | o.oo>oooooo>ooo.oo
    3 | ooooo>ooooooooo>oo
    4 | oooooooooooooooo>o
    5 | oo>ooooooooooooo.^
    6 | ooooo>oooooooooo.o
    7 | oooooo>o>oooooo.oo
    8 | ooo>ooooooo>..ooo^
    9 | ooooooooo....ooooo
   10 | oooooooo...ooooo^^
   11 | oooooooo...ooooooo
   12 | ^ooooooo..oooooooo
   13 | o^oooooo..o^ooooo^
   14 | oooooo...ooooooo^o
   15 | oooooo.ooooooooooo
   16 | oooo^ooooooooooooo
   17 | oooooooooooooo^oo^
   18 | ^oooooooooooooo^^o
   19 | oooooooooooooooooo
   20 | ^oo^oooooooooooooo
   21 | oooooooooooooooooo
   22 | ^ooooooooooo^oooo>
   23 | oooooooooooooo..oo
   24 | oooooooooooo^oo^oo
   25 | ^oooooooooooooo<oo
------------------------------------------------------------------------------
   [OK] 可解，共 44 步
   参考顺序：(0,17)右 -> (22,17)右 -> (0,15)右 -> (1,17)上 -> (0,10)右 -> (5,17)上 -> (1,16)右 -> (3,15)右 -> (4,16)右 -> (0,7)右 -> (8,17)上 -> (1,13)右 -> (0,5)右 -> (1,4)右 -> (10,17)上 -> (10,16)上 -> (7,8)右 -> (8,11)右 -> (2,11)右 -> (13,17)上 -> (2,4)右 -> (14,16)上 -> (3,5)右 -> (6,5)右 -> (13,11)上 -> (7,6)右 -> (17,17)上 -> (18,16)上 -> (18,15)上 -> (12,0)上 -> (16,4)上 -> (17,14)上 -> (5,2)右 -> (8,3)右 -> (24,15)上 -> (18,0)上 -> (13,1)上 -> (20,0)上 -> (20,3)上 -> (22,0)上 -> (22,12)上 -> (25,0)上 -> (24,12)上 -> (25,15)左

校验结果：教学关 + 全部 9 个编号关卡均可正常通关。
难度参考：棋盘逐关放大，最大的一关是第 9 关 26×18（468 格）；
          箭头逐关变多（21 → 44 支），开局可点的反而从 7 支收到 2 支。
          出口更少、要扫的射线更长，这才是难度真正的来源。
生命值参考：按难度星级给，第 1 关 4 颗心、最后一关 7 颗心。
            关卡越难容错越高，一次手滑不至于被打回原点。
            教学关不参与计分，单独给 6 颗心，是个随便点的沙盒。
得分参考：本关得分 = 星级×250 × 剩余生命值 ÷ 生命值上限，
          一颗心都没丢再 +20%；第 1~9 关满分合计 8400 分。
```

校验脚本的退出码为 0（全部可解）；若存在无解关卡，退出码为 1，
可直接接入 CI 或提交前的检查流程。

### 关卡一览

| 关卡 | 名称 | 棋盘 | 箭头 | 占格 | 铺满率 | 开局可点 | 生命值 | 难度 | 本关满分 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 教学关 | 教学关 | 5×5 | 3 | 8 | 0.32 | 2 | ♥×6 | 不计分 | — |
| 1 | 初次拉弓 | 11×8 | 21 | 81 | 0.92 | 7 | ♥×4 | ★ | 300 |
| 2 | 交叉路口 | 13×9 | 23 | 113 | 0.97 | 6 | ♥×4 | ★ | 300 |
| 3 | 连锁反应 | 14×10 | 22 | 132 | 0.94 | 5 | ♥×5 | ★★ | 600 |
| 4 | 四面楚歌 | 16×11 | 27 | 166 | 0.94 | 5 | ♥×6 | ★★★ | 900 |
| 5 | 错位走廊 | 18×12 | 28 | 200 | 0.93 | 4 | ♥×6 | ★★★ | 900 |
| 6 | 纵横交错 | 20×14 | 33 | 266 | 0.95 | 4 | ♥×6 | ★★★★ | 1200 |
| 7 | 长蛇阵 | 22×15 | 38 | 316 | 0.96 | 3 | ♥×6 | ★★★★ | 1200 |
| 8 | 十面埋伏 | 23×17 | 43 | 367 | 0.94 | 3 | ♥×7 | ★★★★★ | 1500 |
| 9 | 万箭归一 | 26×18 | 44 | 441 | 0.94 | 2 | ♥×7 | ★★★★★ | 1500 |

9 个编号关卡合计 **279 支箭头**（单支 1~18 格）、满分合计 **8400 分**。
九个编号关卡全部由 `tools/generate_levels.py` **逆向构造**生成（从构造方式上就保证可解），
再由 `tools/pick_levels.py` 从同一尺寸的候选里挑出「铺满率最高 + 开局可点数最接近目标 +
箭头长短差（标准差）大」的那一版，
最后仍由 `verify_levels.py` 的求解器逐关复核，三道保险。

**难度曲线的数据**：九个关卡的难度分是
`23.2 / 32.8 / 37.0 / 49.3 / 58.7 / 74.4 / 91.4 / 106.7 / 120.6`，
一路单调递增（测试 `test_difficulty_and_stars_never_go_backwards` 卡着这条）。
难度分 = `箭头数 × 1.6 + 棋盘格数 × 0.12 − 开局可点数 × 3.0`，
再按阈值 `(<35, <45, <70, <100, 其余)` 映射成 1~5 颗星。

**难度轴换过一次。** 上一版棋盘尺寸冻结在 9×9、靠「密度」继续加难；
这一版改成棋盘一直放大到 26×18，难度更多地来自**要扫的射线变多**：
棋盘越大、箭头越长（平均单支从 3.9 格一路涨到 10.0 格），越难一眼找出能点的那支。
不变的判断是那条最要紧的：**开局可点数从 7 支一路收到 2 支**，
这才是真正决定手感的那一项。

### 关于第 2 关的一次真实修复

第 2 关最早的布局是 5×5 里四支单格箭头首尾相接：

```
.....
.>.v.
.....
.^.<.
.....
```

校验时报出 `开局可点 0 支 / 可解=False`：`(1,1)` 的 `>` 被 `(1,3)` 的 `v` 挡住，
`v` 被 `(3,3)` 的 `<` 挡住，`<` 被 `(3,1)` 的 `^` 挡住，`^` 又被 `(1,1)` 的 `>` 挡住——
四支箭头围成一个死环。把 `<` 从 `(3,3)` 移到 `(3,4)` 之后即恢复可解。
（这一版关卡重做成弯曲箭头之后，第 2 关已经换成了 13×9 的新布局，
但「关卡不能靠眼睛验收」这条教训一直留着：
现在 `validate_layout` 在导入关卡时就拦非法形状，`verify_levels.py` 与单元测试再各解一遍。）

### 另一件值得记的事：手写的关号会过期

校验脚本的报告里原本有一句「棋盘尺寸到第 7 关就封顶在 9×9」，
后来插了一关，实际已经变成第 8 关，但这句写死的描述**照样打印、退出码照样是 0**，
不报错也不警告。已经改成从关卡表里现算。教训是：能现算的数字一律不要手写，
否则过期之后只会静静地印一句错话。

---

## 八、手动试玩验证

> **这一节的结论需要由本人实际试玩后确认**；如果手感和这里写的不一致，以真实感受为准改掉。
> 自动化测试只能证明「逻辑上可解」，不能证明「玩起来是对的」。
> 九关的参考通关顺序见上面第七节，卡关时可以对照着看。

| 关卡 | 待确认的试玩要点 |
| --- | --- |
| 教学关 | 3 支箭头配 6 颗心，跟着黄色高亮环一步步点即可；第一步是**故意**让玩家点一支被挡住的箭头，用来体验撞击反馈和掉心 |
| 第 1 关 初次拉弓 | 11×8 / 21 支，开局有 7 支能直接飞，适合建立信心 |
| 第 2 关 交叉路口 | 13×9 / 23 支，开局只剩 6 支能点，盘面铺满率 0.97，要顺着射线一支一支解 |
| 第 3 关 连锁反应 | 箭头开始变长（均 6.0 格，最长 11 格），先点能走的那几支，连锁反馈是否明显 |
| 第 4 关 四面楚歌 | 16×11 / 27 支，均长 6.1 格（1~12 格），横竖都要扫一遍 |
| 第 5~7 关 | 18×12 → 22×15，箭头 28 / 33 / 38 支，开局可点 4 → 4 → 3；扫视量明显变大，缩放滑杆好不好用 |
| 第 8~9 关 | 23×17 / 26×18，箭头 43 / 44 支，均长 8.5 / 10.0 格，开局 3 / 2 支能先飞；心给了 7 颗 |
| 通用 | 「重新开始本关」后布局与生命值正确复位；`R` 重开、`H` 提示、`G` 辅助线、`+` / `-` 缩放都正常；放大后拖动棋盘顺不顺手 |
| 进度 | 关掉游戏再打开，已解锁到哪一关、每关最高分都会被记住；「清空进度」需连点两次 |
| 双主题 | 顶栏月亮开关切到日间，棋盘上的箭头与文字是否都还看得清 |
