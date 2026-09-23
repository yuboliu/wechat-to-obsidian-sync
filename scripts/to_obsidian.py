# -*- coding: utf-8 -*-
"""wechat_to_md 产物 -> Obsidian 风味 Markdown。

用法:
  python to_obsidian.py "<文章目录名>" --tags t1 t2 ... [--date YYYY-MM-DD] [--base DIR]

输入: <BASE>/<文章目录名>/<文章目录名>.md   (wechat-article-to-markdown 的产物)
产出: <BASE>/<文章目录名>/<文章目录名>.obsidian.md

做的事:
  1. 剥掉原 frontmatter，重建为 Obsidian 风格（created + tags 列表）
  2. 顶部加 "> [!info] 文章信息" callout（标题/作者/发布日期/来源）
  3. 图片 ![](...) -> ![[...]]，并保证独占一行
  4. 截断文末公众号推广（最后一个分隔线 '---' 之后的内容）
  5. 删除引流语 / 投稿 / 点赞引导等残留
  6. 中文引号按行成对归一化为 “ ”
  7. 章节 ### -> ##（配合 H1 标题）

抓取产物有两种形态，脚本都吃：
  A. 自带 YAML frontmatter（title/tags/date/source…）——元信息取自 frontmatter
  B. 无 frontmatter，元信息在正文开头的 `> 公众号: x / > 发布时间: y / > 原文链接: z` 引用块里
     ——由 read_quote_meta() 兜底提取，并把该引用块与正文自带的一级标题剥掉
"""
import argparse
import datetime
import os
import re
import sys

# 2026-09-23：原写死的 `~\WorkBuddy\微信公总号知识库\output` 已不存在，
# 无 --base 时会静默把 output 重建到死路径（pitfalls #18）。改为跟随当前工作目录，
# 与抓取器 wechat_article_to_markdown.py 的 DEFAULT_OUTPUT_DIR（cwd/output）保持一致。
DEFAULT_BASE = os.path.join(os.getcwd(), "output")


def read_fm(text):
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        return {}, text
    raw = m.group(1)
    fm = {}
    for key in ("title", "author", "date", "source", "description"):
        mm = re.search(r'^%s:\s*"?([^"\n]*)"?\s*$' % key, raw, re.MULTILINE)
        if mm:
            fm[key] = mm.group(1).strip()
    return fm, text[m.end():]


# 抓取器把元信息写成中文键，这里映射到内部字段名
QUOTE_KEYS = {
    "公众号": "author",
    "作者": "author",
    "发布时间": "date",
    "发布日期": "date",
    "原文链接": "source",
    "来源": "source",
    "摘要": "description",
}


def read_quote_meta(text):
    """形态 B 的兜底：摘掉「正文自带的一级标题 + 后面的 `> key: value` 引用块」。

    返回 (meta, h1, rest)。引用块一行都没认出来时原样返回，避免误删正文引言。
    """
    lines = text.split("\n")
    i = 0
    while i < len(lines) and not lines[i].strip():
        i += 1
    h1 = ""
    if i < len(lines) and re.match(r"^#\s+", lines[i]):
        h1 = lines[i].lstrip("#").strip()
        i += 1
        while i < len(lines) and not lines[i].strip():
            i += 1

    meta, j = {}, i
    while j < len(lines) and lines[j].lstrip().startswith(">"):
        m = re.match(
            r"^>\s*(?:\*\*)?([^:：*\s]+)(?:\*\*)?\s*[:：]\s*(.+?)\s*$",
            lines[j].lstrip(),
        )
        if not m or m.group(1).strip() not in QUOTE_KEYS:
            break
        meta.setdefault(QUOTE_KEYS[m.group(1).strip()], m.group(2).strip())
        j += 1

    if not meta:
        return {}, h1, "\n".join(lines) if h1 else text
    return meta, h1, "\n".join(lines[j:])


def fence_map(lines):
    """每行是否位于 ``` 代码围栏内部。"""
    flags, inside = [], False
    for ln in lines:
        if ln.lstrip().startswith("```"):
            flags.append(inside)
            inside = not inside
        else:
            flags.append(inside)
    return flags


def find_promo_sep(text):
    """从后往前找「文末推广分隔线」，返回截断点（字符下标），找不到返回 -1。

    两个坑：
      1. 代码块里常有 `---`（DOT 图、表格分隔），旧版 `text.rfind("\\n---\\n")` 会
         把它当成推广分隔线，把正文从中间腰斩 —— 故跳过围栏内的 `---`。
      2. 形态 B 的抓取产物在正文最前面就有一条 `---`（元信息引用块之后的分隔线），
         它后面还跟着整篇正文 —— 真正推广尾巴不会占正文的一大半，故按「尾巴比例」过滤。
    """
    lines = text.split("\n")
    flags = fence_map(lines)
    total = len(text)
    offset = 0
    starts = []
    for ln in lines:
        starts.append(offset)
        offset += len(ln) + 1
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].strip() != "---" or flags[i]:
            continue
        tail = total - starts[i]
        if tail <= 0.40 * total:
            return starts[i]
    return -1


QUOTES = "“”"


def normalize_quotes(line):
    out, toggle = [], 0
    for ch in line:
        if ch in QUOTES:
            out.append("“" if toggle == 0 else "”")
            toggle ^= 1
        else:
            out.append(ch)
    return "".join(out)


GLUE_RE = re.compile(r"[\u4e00-\u9fa5]\s+[A-Za-z]")
IMG_ALT_RE = re.compile(r"^Image(?=\S)")


def fix_heading_lines(lines):
    """修标题行，两件事：

    1. 去掉抓取器残留的 `Image` alt 前缀（`## Image结论：…` -> `## 结论：…`）。
       `!\\[Image\\](url)` 的方括号与链接被剥掉后只剩这个词，会让标题带上脏前缀。
    2. 拆分「标题里塞进了正文句子」的行 —— 断点取「汉字 + 空格 + 拉丁字母」
       （正文常以英文术语开头），但切出来的正文必须是完整句子（含 `。`）。
       没有这道闸门，`范围 vs 精度：…？`、`徐文辉    S068…` 这类正常标题会被误拆。

    代码围栏内的 `# 创建 Skill` 是文章里的示例代码，必须原样保留。
    """
    out, inside = [], False
    for ln in lines:
        if ln.lstrip().startswith("```"):
            inside = not inside
            out.append(ln)
            continue
        m = None if inside else re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            text = IMG_ALT_RE.sub("", m.group(2))
            hit = GLUE_RE.search(text)
            if hit and "。" in text[hit.end():]:
                cut = hit.start() + 1
                head, body = text[:cut].rstrip(), text[cut:].strip()
                if head and body:
                    out.extend(["%s %s" % (m.group(1), head), "", body])
                    continue
            if text != m.group(2):
                out.append("%s %s" % (m.group(1), text))
                continue
        out.append(ln)
    return out


def convert(dir_name, base, tags, date_override=None):
    art_dir = os.path.join(base, dir_name)
    src = os.path.join(art_dir, dir_name + ".md")
    dst = os.path.join(art_dir, dir_name + ".obsidian.md")
    notes = []

    with open(src, encoding="utf-8") as f:
        text = f.read()

    fm, text = read_fm(text)
    quote_meta, raw_h1, text = read_quote_meta(text)
    if quote_meta:
        notes.append("从正文引用块兜底提取元信息：" + "、".join(sorted(quote_meta)))

    title = fm.get("title") or raw_h1 or dir_name
    title = IMG_ALT_RE.sub("", re.sub(r"!\[[^\]]*\]\([^)]*\)", "", title)).strip() or dir_name
    author = fm.get("author") or quote_meta.get("author", "")
    pubdate = date_override or fm.get("date") or quote_meta.get("date") or ""
    source = fm.get("source") or quote_meta.get("source", "")

    # 尾部推广截断（围栏感知 + 尾巴比例过滤）
    idx = find_promo_sep(text)
    if idx != -1:
        notes.append("截断尾部推广 %d 字符" % (len(text) - idx))
        text = text[:idx]

    # 引流语 / 残留段落
    kill = [
        (r"^★\s*点击名片，关注我们不迷路\s*★\s*$", "引流语『点击名片关注』"),
        (r"^投稿邮箱：.*$", "投稿邮箱"),
        (r'^“?[\w\u4e00-\u9fa5]+”?公众号诚邀.*$', "投稿邀请"),
        (r"^(近期好文|相关阅读|推荐阅读)：\s*$", "推荐阅读"),
        (r"^!\[[^\]]*\]\(images/[^)]*\)“?点赞.*$", "点赞引导"),
        (r"^.*后台私信.*(?:获取|领取|下载).*(?:原文|报告|文件|资料|PDF).*$", "『后台私信获取原文』引导"),
        (r"^#{1,6}\s*[^\n]*拓展阅读[^\n]*$", "『拓展阅读』导航条"),
    ]
    for pat, label in kill:
        if re.search(pat, text, flags=re.MULTILINE):
            text = re.sub(pat, "", text, flags=re.MULTILINE)
            notes.append("删除残留：" + label)

    # 图片 -> Obsidian embed，独占一行
    # 注意 (?:\s+"[^"]*")? 用于吃掉微信偶尔附带的 title 属性，
    # 形如 ![](images/img_0.png "undefined")；漏掉它会把 "undefined" 当成文件名的一部分。
    text = re.sub(
        r'!\[[^\]]*\]\(images/([^)\s]+)(?:\s+"[^"]*")?\)',
        lambda m: "\n![[images/%s]]\n" % m.group(1),
        text,
    )

    # 机构文的 PART 标记：**PART**01** / **PART****02** / **PART02**
    # 必须先于「加粗分裂合并」执行：否则 **PART****02** 会先被合并成 **PART02** 而漏掉。
    if re.search(r"\*\*PART\*{0,4}\s*\d+\*{0,4}", text):
        text = re.sub(r"\*\*PART\*{0,4}\s*\d+\*{0,4}[ \t]*\n?", "", text)
        notes.append("清理 PART 标记")

    # 加粗分裂合并：微信常把一段加粗按 token 切成 **A****B****C**
    # 只在行内合并（前后都是非空白），以免误伤独占一行的 ****（Markdown 水平分割线）。
    merged = re.sub(r"(?<=\S)\*\*\*\*(?=\S)", "", text)
    if merged != text:
        notes.append("合并微信分裂的加粗标记")
        text = merged

    # **01** + 「**章节名**」两行合并为 ## 01 章节名
    merged = re.sub(r"\*\*0(\d)\*\*[ \t]*\n[ \t]*\*\*(.+?)\*\*", r"## 0\1 \2", text)
    if merged != text:
        notes.append("合并『**01**+章节名』为二级标题")
        text = merged

    # 反斜杠残留：只处理「转义标点/下划线」与独占一行的 \，
    # 不动 C:\Users 这类后跟字母的合法反斜杠。
    text = re.sub(r"\\([_*\[\]()#!`>+\-.])", r"\1", text)
    text = re.sub(r"^\\[ \t]*$", "", text, flags=re.MULTILINE)

    # 空引用行
    text = re.sub(r"^>[ \t]*$", "", text, flags=re.MULTILINE)

    # 中文引号按行成对归一化（跳过代码围栏）
    lines, in_fence, changed = [], False, False
    for line in text.split("\n"):
        if line.lstrip().startswith("```"):
            in_fence = not in_fence
            lines.append(line)
            continue
        new = line if in_fence else normalize_quotes(line)
        if new != line:
            changed = True
        lines.append(new)
    text = "\n".join(lines)
    if changed:
        notes.append("归一化中文引号（按行成对）")

    # 章节层级
    text = re.sub(r"^###\s+", "## ", text, flags=re.MULTILINE)

    # 标题-正文粘连拆分
    fixed = fix_heading_lines(text.split("\n"))
    if fixed != text.split("\n"):
        notes.append("拆分粘连的标题-正文")
        text = "\n".join(fixed)

    # 全文清理
    text = text.replace("\u200b", "")
    text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()

    created = datetime.datetime.now().isoformat()
    fm_out = "---\ncreated: '%s'\ntags:\n%s---\n\n" % (
        created,
        "".join("- %s\n" % t for t in tags),
    )
    callout = "> [!info] 文章信息\n> **标题**：%s\n" % title
    if author:
        callout += "> **作者**：%s\n" % author
    if pubdate:
        callout += "> **发布日期**：%s\n" % pubdate
    if source:
        callout += "> **来源**：[微信原文](%s)\n" % source
    tail = " ".join("#" + t for t in tags)

    out = "%s# %s\n\n%s\n%s\n\n%s\n" % (fm_out, title, callout, text, tail)
    with open(dst, "w", encoding="utf-8", newline="\n") as f:
        f.write(out)

    print("WROTE:", dst)
    for n in notes:
        print("  *", n)
    print("  图片引用:", ", ".join(re.findall(r"!\[\[([^\]]+)\]\]", out)) or "无")
    return dst


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("dir_name", help="文章目录名（output 下的子目录）")
    ap.add_argument("--base", default=DEFAULT_BASE, help="output 根目录")
    ap.add_argument("--tags", nargs="*", default=[], help="标签")
    ap.add_argument("--date", help="覆盖发布日期 (YYYY-MM-DD)")
    a = ap.parse_args()
    convert(a.dir_name, a.base, a.tags, a.date)


if __name__ == "__main__":
    main()
