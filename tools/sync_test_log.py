# -*- coding: utf-8 -*-
"""把 docs/test-report.md 里的「六、完整测试日志」块与真实测试同步。

文档里那一大段 ``test_xxx ... ok`` 是照 ``python -m unittest -v`` 的输出抄的，
每加一轮功能就会过期——这一版抄出来一比对：**少 11 条，还留着 2 个改过名的
旧用例名**。手抄的日志迟早会和代码对不上，所以改成脚本生成：

* 用例顺序用 ``unittest`` 的加载器现取（类名字母序 + 方法名字母序，
  和 ``-v`` 的输出一致），不依赖文档里原有的顺序；
* 块里已经写过的中文说明**原样保留**（那是对着 docstring 再润色过的），
  新用例才用 docstring 首行补说明；
* 已经不在代码里的旧名字会被删掉，并在报告里点名。

用法
----
    python tools/sync_test_log.py            # 就地更新 docs/test-report.md
    python tools/sync_test_log.py --check    # 只报告差异，不写文件

注意：它只动「六、完整测试日志」这个代码块，其余一个字不碰；
用例总数、分组表那些数字仍然要手工同步（脚本会把真实总数打出来提醒）。
"""

import os
import re
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if os.path.join(ROOT, "tools") not in sys.path:
    sys.path.insert(0, os.path.join(ROOT, "tools"))

# 必须在 import pygame 之前设置，才能无头跑（导入测试模块会初始化 pygame）
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
os.environ.setdefault("SDL_AUDIODRIVER", "dummy")

REPORT = os.path.join(ROOT, "docs", "test-report.md")
SECTION = "## 六、完整测试日志"
ENTRY = re.compile(r"^(test_\w+) \.\.\. ok(.*)$")


def collect_cases():
    """按 unittest 的加载顺序取回 (类名, 方法名, 说明) 列表，说明可能为空。"""
    import tests.test_game as module                      # noqa: E402  延迟导入

    cases = []

    def walk(suite):
        for item in suite:
            if isinstance(item, unittest.TestSuite):
                walk(item)
            else:
                class_name, method = item.id().rsplit(".", 2)[-2:]
                doc = (getattr(getattr(module, class_name), method).__doc__ or "")
                first = doc.strip().splitlines()
                cases.append((class_name, method, first[0] if first else ""))

    walk(unittest.TestLoader().loadTestsFromModule(module))
    return cases


def block_bounds(lines):
    """返回（块内容起始行, 结束行）——两个 ``` 之间的行号区间。"""
    start = next(i for i, line in enumerate(lines) if line.startswith(SECTION))
    open_fence = next(i for i in range(start, len(lines)) if lines[i].startswith("```"))
    close_fence = next(i for i in range(open_fence + 1, len(lines))
                       if lines[i].startswith("```"))
    return open_fence + 1, close_fence


def main():
    check_only = "--check" in sys.argv
    raw = open(REPORT, "rb").read()
    newline = "\r\n" if b"\r\n" in raw else "\n"
    lines = raw.decode("utf-8").replace("\r\n", "\n").split("\n")

    begin, end = block_bounds(lines)
    old_body = lines[begin:end]

    # 旧块里已经有的条目：名字 -> 整行（中文说明照抄，不重新从 docstring 生成）
    known = {}
    for line in old_body:
        match = ENTRY.match(line)
        if match:
            known[match.group(1)] = line

    cases = collect_cases()
    fresh = []
    added, dropped = [], []
    for class_name, method, summary in cases:
        if method in known:
            fresh.append(known[method])
        else:
            added.append("%s.%s" % (class_name, method))
            fresh.append("%s ... ok%s" % (method, ("   " + summary) if summary else ""))
    live = {method for _, method, _ in cases}
    dropped = [name for name in known if name not in live]

    print("真实用例 %d 条；块里原有 %d 条" % (len(cases), len(known)))
    print("新增 %d 条：%s" % (len(added), added if added else "无"))
    print("移除 %d 条（代码里已经没有了）：%s" % (len(dropped), dropped if dropped else "无"))

    if check_only:
        print("--check：没有写文件")
        return 1 if (added or dropped) else 0

    if not added and not dropped:
        print("块已经是最新的，无需改动")
        return 0

    lines[begin:end] = fresh
    text = "\n".join(lines)
    if newline == "\r\n":
        text = text.replace("\n", "\r\n")
    with open(REPORT, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)
    print("已更新 %s" % os.path.relpath(REPORT, ROOT))
    print("提醒：文档第二节的「用例总数 / 分组用例数」要手工同步成 %d。" % len(cases))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
