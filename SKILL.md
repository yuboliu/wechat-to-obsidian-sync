---
name: wechat-to-obsidian-sync
description: 微信公众号文章 → Obsidian vault 的转换与落库流水线。把 wechat-article-to-markdown 抓出的原始 Markdown 转成 Obsidian 风味（callout 元信息 / ![[图片]] 嵌入 / 章节层级 / 中英引号归一化），再按「每篇一个子文件夹」的约定写进 vault 并复制被引用的图片。当用户说「保存这篇公众号文章到 obsidian」「同步微信文章到知识库」「微信转 obsidian」，或已跑完抓取+校验需要落库时使用。
agent_created: true
---

# WeChat → Obsidian Sync

把「抓取 → 转换 → 校验 → 落库」中的**转换 + 落库**两段标准化，避免每次重写脚本。

> **本机专用配置**：vault 根、本机解释器路径这类「各人不同」的值**不要写进本文件**。
> 它们放在 `scripts/local_config.py`（已被 `.gitignore` 忽略）；若同目录存在
> `references/LOCAL-NOTES.md`，其中的路径**优先**于本文档的示例。
> **在本机运行前先看 `references/LOCAL-NOTES.md`。**

## 上游 / 下游

| 环节 | 用什么 |
|------|--------|
| 抓取 | `wechat-article-to-markdown`（产出 `output/<目录名>/<目录名>.md` + `images/`） |
| **转换** | 本 skill `scripts/to_obsidian.py` |
| 校验 | `wechat-md-verify`（在转换前后各跑一次） |
| **落库** | 本 skill `scripts/sync_to_vault.py` |

推荐顺序：抓取 → 校验(基线) → 转换 → 校验(结构) → 落库 → 校验(成品)。

## Quick Start

设 `D` 为文章目录名（`output/` 下的子目录名，注意它常与标题不同：抓取脚本会把空格和
`，？` 替换掉）。

```bash
PY="python3"                      # Windows 本机没有 python3，见 references/LOCAL-NOTES.md
SKILL="~/.workbuddy/skills/wechat-to-obsidian-sync"
BASE="<抓取时的 -o 输出根目录>"   # 不传 --base 时默认 cwd/output（见 pitfalls #18）

# 1) 转换（--tags 必给，否则 frontmatter 与文末标签为空）
"$PY" "$SKILL/scripts/to_obsidian.py" "$D" --base "$BASE" --tags 标签1 标签2 标签3 --date 2026-09-23

# 2) 落库（--vault 默认取 local_config.py / 环境变量 WECHAT_VAULT，通常可省略）
"$SKILL/.venv/Scripts/python.exe" "$SKILL/scripts/sync_to_vault.py" "$D" --base "$BASE"
```

落点在 `vault/<subfolder>/<标题>/`，默认 `subfolder=公众号`。

落库脚本**自包含**：只用 pyyaml（本 skill 自带 `.venv` 已装）。2026-09-23 起不再依赖
`obsidian-direct`（该 skill 已卸载），`create_note()` 的实现内联在 `sync_to_vault.py` 里，
输出与原版逐字节一致。

## 上游抓取器（2026-09-23 起）

抓取用 `wechat-article-to-markdown`（jackwener 版 / 本机 git clone，已改用两级抓取）。

**统一入口就是主脚本本身**——默认 `--mode auto`：先 `requests` 直取，命中风控才自动升浏览器：

```bash
SK="$HOME/.workbuddy/skills/wechat-article-to-markdown"
"$SK/.venv/Scripts/python.exe" "$SK/wechat_article_to_markdown.py" "<URL>" -o "<BASE>"
```

只想走最快的非浏览器模式（推荐，公众号正文是服务端渲染的）：

```bash
"$SK/.venv/Scripts/python.exe" "$SK/wechat_article_to_markdown.py" "<URL>" -o "<BASE>" --mode requests
```

> ⚠️ 本机 camoufox 二进制无法被自动化驱动（浏览器进程能起，但 chrome window 初始化不完成，
> Juggler 15s 后抛 `gBrowser never populated`）；已完整验证**与 build/playwright 版本无关**，
> 不必再试"换稳定版"。因此本机若需浏览器兜底，请加 `--browser-engine chromium`。
> `--browser-timeout`（默认 90s）已做硬超时，不会再像旧版那样卡死。
> 排除清单见 `wechat-article-to-markdown/SKILL.md` 的「本机运行方式」。
>
> 2026-09-23 之前的临时脚本 `wechat_fetch_http.py` / `wechat_fetch_chromium.py` 已删除，
> 逻辑全部并入主脚本的 `--mode` / `--browser-engine` 参数。

- 输出 `<BASE>/<safe_title>/<safe_title>.md` + `images/`。
- `safe_title` = 标题把 `/ \ ? % * : | " < >` 换成 `_`、再截断 80 字符 —— **不替换空格和
  全角标点**（这点与已卸载的 v2 不同，v2 会把空格/`，？` 也换掉）。所以 `$D` 常带空格，
  命令里务必加引号。
- v2（ClawHub · benzking 的 Playwright 版）已于 2026-09-23 删除，`--no-playwright` 降级模式
  不再可用；本机 Camoufox 浏览器二进制已下载，走真实浏览器渲染。

## 转换脚本做了什么

1. 剥掉抓取脚本写的 frontmatter，重建为 `created` + `tags` 列表。
2. 顶部生成 `> [!info] 文章信息` callout（标题 / 作者 / 发布日期 / 来源链接）。
3. `![](images/x.png)` → `![[images/x.png]]`，并**保证独占一行**（抓取结果常把图接在段落末尾）。
   同时吃掉 URL 后可能附带的 `"undefined"` title 属性（见 pitfalls 第 10 条）。
4. 截断文末公众号推广：从最后一个 `---` 分隔线往后全是「近期好文 / 投稿 / 点赞引导」。
5. 逐条删除引流语、投稿邮箱、推荐阅读、点赞引导等残留段落。
6. 清理机构文的 `**PART**01**` 标记，合并 `**01**`+`**章节名**` 为二级标题。
7. 合并被微信按 token 切开的加粗标记（`**A****B**` → `**AB**`）。
8. 反斜杠残留：还原 `\_` `\**` 并删除独占一行的 `\`，**不动** `C:\Users` 这类合法路径。
9. 删除空引用行（`^>`）。
10. 中文引号**按行成对交替归一化**为 `“ ”`。
11. 章节 `### ` → `## `（配合唯一的 H1 标题）。
12. 清理零宽空格、行尾空白、3 个以上连续空行。

每步命中时都会在 stdout 打出处理记录，便于复核改了什么。

### 自测

改过转换规则后跑一遍合成样本，确认规则真生效、且不误伤（尤其 `C:\Users` 和独立行 `****`）：

```bash
# 样本放 <BASE>/_selftest/_selftest.md，内容见 references/pitfalls.md 各条的「坏例子」
"$PY" "$SKILL/scripts/to_obsidian.py" "_selftest" --tags 测试 --base "<BASE>"
```

再对本篇已落库的文章重跑一次做回归，产出应与之前逐字节一致（除 `created` 时间）。

## 落库脚本做了什么

1. 从 `.obsidian.md` 的 H1 取标题、frontmatter 取 tags。
2. 落点 `vault/<subfolder>/<标题>/<标题>.md`，默认 `subfolder=公众号`；`--folder` 可整体覆盖。
   **每篇必须是带标题的独立子文件夹**，否则同名 `img_000.png` 会互相覆盖。
3. 只复制正文真正引用的图片到该子目录的 `images/`；推广图/二维码留在 output 里不落库。
4. 开跑前校验 `--vault` 存在、且其下有 `.obsidian`（没有只告警不拦，兼容非标准 vault）。

## 与 obsidian-markdown 的分工

两个 skill 都会碰「Markdown → Obsidian 风味」这件事，边界要划清，否则同一批笔记会出现两种格式：

- `obsidian-markdown`（kepano 出品，prompt 型）：**通用语法参考**。wikilink / 嵌入 / callout 类型表 /
  frontmatter 属性等语法含义拿不准时去查它。它不认微信的抓取瑕疵。
- **本 skill**：微信场景的**确定性转换 + 落库**，用脚本保证每篇产出形态逐字节一致。

原则：**风格规则以本 skill 的脚本为准，语法含义查 `obsidian-markdown`。**
遇到新语法的需求，先改脚本、再更新本文件，不要只在对话里临时处理。

## 硬性约定

- **每篇一个带标题的子文件夹**。若多篇都落到同一个 `images/`，同名 `img_000.png` 会互相覆盖。
- **落库前必须处理掉未引用图片的引用关系**：转换脚本已把推广段的引用连同段落一起删掉，
  所以落库时只复制被引用的图片即可，不要图省事整目录 copy。
- 目录名与标题不一致是正常的，别拿标题去找目录。
- **vault 路径集中在一个常量里**：vault 根 = 含 `.obsidian` 的目录，本机为
  `~\iNote`，笔记落 `iNote\公众号\<标题>\`。
  ⚠️ 2026-09-23 用户重构过目录（原先多一层 `iNote\知识库`，该层已取消）。
  **目录再变时只改 `scripts/sync_to_vault.py` 的 `DEFAULT_VAULT`**，不要散落到别处或写进命令行。

## 已知坑

见 `references/pitfalls.md`。踩坑前先看一遍，尤其是「引号归一化」和「tags 正则」两条 ——
这两个都是看起来能跑、结果悄悄错的那类。
