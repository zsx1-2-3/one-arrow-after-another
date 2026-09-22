# -*- coding: utf-8 -*-
"""把 tools/pick_levels.py 的输出（build_levels_out.txt）拼进 game/levels.py。

只替换 LEVELS = ( ... ) 这一块，块前块后的注释、教学关与函数一律不动。
用法：python tools/_splice_levels.py
"""

import io
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "build_levels_out.txt")
DST = os.path.join(ROOT, "game", "levels.py")

new_block = io.open(SRC, encoding="utf-8").read().rstrip() + "\n"
if not new_block.startswith("LEVELS = ("):
    raise SystemExit("build_levels_out.txt 不是以 LEVELS = ( 开头，先跑 pick_levels.py")

src = io.open(DST, encoding="utf-8").read()
start = src.index("LEVELS = (")
end = src.index("\ndef report_for", start) + 1     # 保留 report_for 之前的空行结构
old_block = src[start:end]
if old_block.rstrip().endswith(")"):
    pass
spliced = src[:start] + new_block + "\n" + src[end:]
io.open(DST, "w", encoding="utf-8", newline="\n").write(spliced)
print("已替换 LEVELS 块：%d 字 -> %d 字" % (len(old_block), len(new_block)))
