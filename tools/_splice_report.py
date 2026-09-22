# -*- coding: utf-8 -*-
"""把最新的 verify_levels 输出与关卡一览表拼回 docs/test-report.md。"""

import io
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from game.levels import LEVELS, TUTORIAL  # noqa: E402

verify = io.open(os.path.join(ROOT, "build_verify_out.txt"),
                 encoding="utf-8").read().rstrip()
path = os.path.join(ROOT, "docs", "test-report.md")
src = io.open(path, encoding="utf-8").read()

TICK = "`" * 3
start_marker = (TICK + "\n" + "=" * 78 + "\n"
                + "《一箭又一箭》关卡校验报告")
end_marker = TICK + "\n\n校验脚本的退出码为 0"
i = src.index(start_marker)
j = src.index(end_marker)
src = src[:i] + TICK + "\n" + verify + "\n" + TICK + src[j + len(TICK):]

rows = []


def row(label, name, lv, scored):
    used = sum(p.length for p in lv.pieces)
    stars = "不计分" if not scored else "★" * lv.stars
    score = "—" if not scored else "%d" % (lv.stars * 300)
    return ("| %s | %s | %d×%d | %d | %d | %.2f | %d | ♥×%d | %s | %s |"
            % (label, name, lv.rows, lv.cols, lv.arrow_count, used,
               lv.density, lv.free_count, lv.max_hp, stars, score))


rows.append(row("教学关", "教学关", TUTORIAL, False))
for index, lv in enumerate(LEVELS, start=1):
    rows.append(row(str(index), lv.name, lv, True))

old_start = src.index("| 教学关 | 教学关")
old_end = src.index("9 个编号关卡合计")
src = src[:old_start] + "\n".join(rows) + "\n\n" + src[old_end:]

io.open(path, "w", encoding="utf-8", newline="\n").write(src)
print("附录块与一览表已替换")
