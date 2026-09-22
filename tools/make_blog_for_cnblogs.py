# -*- coding: utf-8 -*-
"""把 docs/blog.md 转成「粘到博客园就能正常显示图片」的版本。

为什么需要这个脚本
------------------
blog.md 里的 17 张图用的是**相对路径**（`../assets/shot-01-menu.png`）。
在 GitHub 上点开 blog.md 时相对路径是对的（图片就在同仓库的 assets/ 里），
但博客园是另一台服务器，它不认识「../assets」——粘过去只会看到 17 个破图占位，
所以需要一份把图片地址换成绝对外链的版本。

外链走 jsDelivr：它反过来代理 GitHub 仓库里的文件，
`https://gcore.jsdelivr.net/gh/用户/仓库@分支/assets/文件名` 就能拿到，
国内一般能直连（GitHub 自己的 raw 域名经常打不开）。

正文一个字都不改，只换图片地址，粘的时候用这个文件、不要用 blog.md。

用法
----
    python tools/make_blog_for_cnblogs.py            # 生成 docs/blog-cnblogs.md
    python tools/make_blog_for_cnblogs.py --host cdn # 换一条 CDN 线路
    python tools/make_blog_for_cnblogs.py --check    # 只体检，不写文件

线路参数 --host（默认 gcore）：
    gcore / cdn / fastly   都是 jsDelivr 的入口，实测 gcore 最快
    raw                    直接用 GitHub raw，只在有代理时可用
"""

import argparse
import os
import re
import sys

REPO = "zsx1-2-3/one-arrow-after-another"
BRANCH = "main"

HOSTS = {
    "gcore": "https://gcore.jsdelivr.net/gh/%s@%s/" % (REPO, BRANCH),
    "cdn": "https://cdn.jsdelivr.net/gh/%s@%s/" % (REPO, BRANCH),
    "fastly": "https://fastly.jsdelivr.net/gh/%s@%s/" % (REPO, BRANCH),
    "raw": "https://raw.githubusercontent.com/%s/%s/" % (REPO, BRANCH),
}
DEFAULT_HOST = "gcore"

# blog.md 里图片的老写法：](…/assets/xxx.png)
RELATIVE_IMAGE = re.compile(r"\]\(\.\./assets/([^)]+)\)")

HEADER = (
    "<!-- 本文件由 tools/make_blog_for_cnblogs.py 自动生成："
    "图片换成 jsDelivr 外链，正文与 docs/blog.md 一字不差。"
    "要改内容请改 docs/blog.md，再重新生成这个文件。 -->\n"
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BLOG = os.path.join(ROOT, "docs", "blog.md")
OUT = os.path.join(ROOT, "docs", "blog-cnblogs.md")
ASSETS = os.path.join(ROOT, "assets")


def asset_url(name, host=DEFAULT_HOST):
    """把 assets/ 下的文件名拼成绝对外链。"""
    if host not in HOSTS:
        raise ValueError("未知的 CDN 线路：%s（可选 %s）"
                         % (host, "/".join(sorted(HOSTS))))
    return HOSTS[host] + "assets/" + name


def convert(text, host=DEFAULT_HOST):
    """把正文里的相对图片路径换成绝对外链，其余原样返回。"""
    return RELATIVE_IMAGE.sub(lambda m: "](" + asset_url(m.group(1), host) + ")",
                              text)


def local_images(text):
    """列出正文引用到的 assets 文件名。"""
    return RELATIVE_IMAGE.findall(text)


def check(text, host=DEFAULT_HOST):
    """体检：图名有没有写错、有没有漏掉的相对路径。返回问题列表。"""
    problems = []
    names = local_images(text)
    if not names:
        problems.append("正文里一张相对路径的图片都没有，是不是改过写法了？")
    for name in names:
        if not os.path.exists(os.path.join(ASSETS, name)):
            problems.append("assets/ 里没有这个文件：%s" % name)
    leftover = RELATIVE_IMAGE.findall(convert(text, host))
    if leftover:
        problems.append("换完之后仍有相对路径：%s" % "、".join(leftover))
    return problems


def build(host=DEFAULT_HOST):
    """生成完整的博客园版文本（带自动生成提示的注释头）。"""
    with open(BLOG, encoding="utf-8") as f:
        text = f.read()
    return HEADER + convert(text, host)


def main(argv=None):
    parser = argparse.ArgumentParser(description="生成博客园可用的博客版本")
    parser.add_argument("--host", default=DEFAULT_HOST, choices=sorted(HOSTS),
                        help="图片走哪条 CDN 线路（默认 %s）" % DEFAULT_HOST)
    parser.add_argument("--check", action="store_true",
                        help="只做体检，不写文件")
    args = parser.parse_args(argv)

    with open(BLOG, encoding="utf-8") as f:
        source = f.read()

    problems = check(source, args.host)
    for line in problems:
        print("[x]", line)
    if problems:
        return 1

    names = local_images(source)
    if args.check:
        print("[ok] %d 张图片都有对应的文件，地址也都能换干净" % len(names))
        return 0

    text = HEADER + convert(source, args.host)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("[ok] %d 张图片已指向 %s" % (len(names), HOSTS[args.host]))
    print("[ok] 写出 %s（%.0f KB），粘到博客园请用这个文件"
          % (os.path.relpath(OUT, ROOT), os.path.getsize(OUT) / 1024.0))
    return 0


if __name__ == "__main__":
    sys.exit(main())
