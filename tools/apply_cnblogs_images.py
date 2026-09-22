# -*- coding: utf-8 -*-
"""把博客园自己图床的地址填回正文，产出「图片稳如泰山」的最终版。

为什么需要这个脚本
------------------
博客园是**另一台服务器**，读不到你仓库里的 `assets/`，所以正文里的
`../assets/shot-01-menu.png` 粘过去只会变成 17 个破图。

`make_blog_for_cnblogs.py` 给出的第一版对策是把图片换成 jsDelivr 外链。
但 2026-09-22 实测：**在大陆这台机器上，jsDelivr / GitHub raw 全线连不上**
（直连超时，`gcore.jsdelivr.net` 浏览器里直接 ERR_CONNECTION_CLOSED），
换 cdn / fastly / b-cdn 也一样。原因不是配置写错，是这些域名本身在国内不可达——
连得上才是意外。所以外链这条路对**看博客的人**（老师、同学）同样不通。

真正稳的做法只有一个：**让图片住在博客园自己的图库里**。
博客园的图片地址长这样：

    https://img2023.cnblogs.com/blog/1234567/202609/1234567-20260922231234567-123456789.png

同一个平台上，谁、什么网络、过多久都能打开。这也是博客园文章图片的常态。

三条路线（从省事到麻烦）
------------------------
1. **一键转存**：把 `docs/blog-cnblogs.md` 粘进博客园 Markdown 编辑器，
   点编辑器右下角的「**提取图片**」。博客园会去下载外链图片、转存到自己的图库，
   并把正文里的地址改成 `img*.cnblogs.com`。成功就不用往下看了。
   （能不能成取决于博客园服务器抓不抓得到那个外链；外链恰好不通时它会失败。）
2. **本脚本**（下面这套）：转存失败时，用「拖图 → 复制地址 → 跑脚本」三步得到
   一份地址已经填好的正文，再把这份正文粘进去发布。
3. **手动**：把 17 个地址一个个粘到对应位置——不推荐，17 处很容易错位。

路线 2 的完整操作（约 2 分钟）
------------------------------
    1. 打开 assets/ 文件夹，**全选 17 个文件**（demo.gif + shot-01 ~ shot-16）；
    2. 博客园 → 写随笔 → 编辑器切到 **Markdown** → 把那 17 个文件一次拖进编辑区，
       编辑器会自动上传并插入 17 行图片链接；
    3. **全选复制**这一段（也可以只复制图片那几行），存成
       `docs/cnblogs-urls.txt`；
    4. 本地跑：

           python tools/apply_cnblogs_images.py docs/cnblogs-urls.txt

       得到 `docs/blog-final.md`；
    5. 回到编辑器，**全选删除**刚才那些图片行，再把 `blog-final.md` 全文粘进去，
       预览确认图片都在，然后发布。

为什么不用按顺序核对文件名
--------------------------
正文引用这 17 张图的顺序，正好就是文件名的升序：

    demo.gif, shot-01-menu.png, shot-02-levels.png … shot-16-settings-day.png

Windows 的资源管理器按名称排序，"全选拖动"天然就是这个顺序，脚本按下标一一对应
替换即可。万一以后改了引用顺序，脚本会报「数量对不上」并停下，不会默默错位。

用法
----
    python tools/apply_cnblogs_images.py docs/cnblogs-urls.txt
    python tools/apply_cnblogs_images.py -            # 地址直接从标准输入读
    python tools/apply_cnblogs_images.py urls.txt --out docs/blog-final.md
"""

import argparse
import os
import re
import sys

TOOLS = os.path.dirname(os.path.abspath(__file__))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

from make_blog_for_cnblogs import RELATIVE_IMAGE  # noqa: E402

ROOT = os.path.dirname(TOOLS)
BLOG = os.path.join(ROOT, "docs", "blog.md")
DEFAULT_OUT = os.path.join(ROOT, "docs", "blog-final.md")

# 从「粘过来的一大段」里把地址抠出来：中英文标点、markdown 的 ]( ) 都当边界
URL_RE = re.compile(r"https?://[^\s()\[\]<>\"',，。；）】]+")

HEADER = (
    "<!-- 本文件由 tools/apply_cnblogs_images.py 自动生成："
    "图片地址已换成博客园自己图床的地址，正文与 docs/blog.md 一字不差。"
    "要改内容请改 docs/blog.md，再重新走一遍拖图 + 脚本。 -->\n"
)


def extract_urls(text):
    """把粘贴内容里的所有网址按出现顺序抓出来。"""
    return URL_RE.findall(text)


def apply_urls(text, urls):
    """按顺序把正文里的 17 处相对图片路径换成给定网址。

    数量必须完全相等——对不上就抛错，绝不「尽力而为」地错位填。
    """
    names = RELATIVE_IMAGE.findall(text)
    if len(urls) != len(names):
        raise ValueError(
            "数量对不上：正文里有 %d 处图片引用（%s…），你给了 %d 个地址。\n"
            "  * 少给了：是不是没把 17 个文件全拖进去？\n"
            "  * 多给了：编辑器里可能还残留着上一次的图片行，清空后重来。"
            % (len(names), "、".join(names[:3]), len(urls)))
    pool = list(urls)

    def take(match):
        return "](" + pool.pop(0) + ")"

    text = RELATIVE_IMAGE.sub(take, text)
    if pool:
        raise ValueError("还有 %d 个地址没用上，正文里的图片引用数算错了" % len(pool))
    return text


def inspect(urls):
    """体检：地址看着像不像博客园图床的（不像只提醒，不拦）。"""
    notes = []
    outside = [u for u in urls if "cnblogs.com" not in u]
    if outside:
        notes.append("有 %d 个地址不是博客园图床（前几个：%s）——"
                     "如果它们指向的图床在国内打不开，博客里照样是破图"
                     % (len(outside), "、".join(u[:60] for u in outside[:2])))
    if len(set(urls)) != len(urls):
        notes.append("出现了重复地址——同一个文件拖了两次？对应位置的图片会重复")
    return notes


def build(text, urls):
    return HEADER + apply_urls(text, urls)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="把博客园图床地址填回正文，生成 docs/blog-final.md")
    parser.add_argument("urls", help="放着图片地址的文本文件（- 表示从标准输入读）")
    parser.add_argument("--out", default=DEFAULT_OUT, help="输出路径")
    args = parser.parse_args(argv)

    if args.urls == "-":
        raw = sys.stdin.read()
        source_name = "标准输入"
    else:
        with open(args.urls, encoding="utf-8", errors="replace") as f:
            raw = f.read()
        source_name = os.path.relpath(args.urls, ROOT)

    urls = extract_urls(raw)
    if not urls:
        print("[x] %s 里一个网址都没找到" % source_name)
        return 1

    with open(BLOG, encoding="utf-8") as f:
        text = f.read()

    try:
        final = build(text, urls)
    except ValueError as exc:
        print("[x] %s" % exc)
        return 1

    for note in inspect(urls):
        print("[!]", note)

    with open(args.out, "w", encoding="utf-8", newline="\n") as f:
        f.write(final)

    print("[ok] %d 个地址已按顺序填回正文" % len(urls))
    print("[ok] 写出 %s（%.0f KB）——把它全文粘进博客园编辑器再发布"
          % (os.path.relpath(args.out, ROOT), os.path.getsize(args.out) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
