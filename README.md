# wechat-to-obsidian-sync

微信公众号文章 → Obsidian vault 的**转换 + 落库**流水线。

把抓取下来的原始 Markdown 转成 Obsidian 风味（callout 元信息 / `![[图片]]` 嵌入 / 章节层级 /
中英引号归一化），再按「每篇一个带标题的子文件夹」的约定写进 vault，并只复制正文真正引用的图片。

> 这是一个 [WorkBuddy](https://www.workbuddy.cn/) Agent Skill，也可以当普通 Python 脚本直接用。

## 它解决什么问题

微信文章的抓取产物有一堆固定瑕疵，逐篇手工修不现实：

- 元信息两种形态（带 YAML frontmatter / 只有正文开头的 `> 公众号: …` 引用块）；
- 文末一大段公众号推广、投稿邮箱、点赞引导、拓展阅读导航条；
- 图片语法是 `![](...)`，且常被粘在段落末尾，Obsidian 里渲染不出来；
- 标题被微信按 token 切开，`**A****B**` 这种加粗标记断裂；
- 中文引号半角全角混用，`\_` `\*` 反斜杠残留；
- 多篇文章的 `img_000.png` 同名，落到同一个 `images/` 会互相覆盖。

本 skill 用脚本把这些**确定性**处理掉，保证同一篇重跑产出逐字节一致。

## 三件套分工

| 环节 | 用什么 |
|------|--------|
| 抓取 | [wechat-article-to-markdown](https://github.com/jackwener/wechat-article-to-markdown) |
| **转换** | 本仓库 `scripts/to_obsidian.py` |
| 校验 | wechat-md-verify |
| **落库** | 本仓库 `scripts/sync_to_vault.py` |

推荐顺序：抓取 → 校验(基线) → 转换 → 校验(结构) → 落库 → 校验(成品)。

## 安装

### 作为 WorkBuddy Skill

```bash
git clone https://github.com/yuboliu/wechat-to-obsidian-sync.git \
  ~/.workbuddy/skills/wechat-to-obsidian-sync
```

### 依赖

只需要 `pyyaml`，脚本自带一个 `.venv` 目录用于跑落库：

```bash
python3 -m venv .venv
.venv/bin/pip install pyyaml        # Windows: .venv/Scripts/pip install pyyaml
```

## 用法

设 `D` 为文章目录名（抓取脚本 `-o` 输出根目录下的子目录名，**常与文章标题不同**，
且可能带空格，命令里务必加引号）。

```bash
SKILL="~/.workbuddy/skills/wechat-to-obsidian-sync"
BASE="<抓取时的 -o 输出根目录>"

# 1) 转换：原始 md -> .obsidian.md
python3 "$SKILL/scripts/to_obsidian.py" "$D" --base "$BASE" \
    --tags 标签1 标签2 标签3 --date 2026-09-23

# 2) 落库：.obsidian.md -> vault
"$SKILL/.venv/Scripts/python.exe" "$SKILL/scripts/sync_to_vault.py" "$D" --base "$BASE"
```

- `--tags` **必给**，否则 frontmatter 与文末标签为空。
- 落点 = `vault/<subfolder>/<标题>/<标题>.md`，默认 `subfolder=公众号`。
- `--vault` 默认取脚本里的 `DEFAULT_VAULT`，通常不用传。

### 配置 vault 路径

vault 根 = 那个装有 `.obsidian` 的目录。脚本里集中在一个常量：

```python
# scripts/sync_to_vault.py
DEFAULT_VAULT = str(Path.home() / "iNote")
```

改目录时**只改这一处**，不要散落到别处或写进命令行。

## 转换脚本做了什么

1. 剥掉抓取脚本写的 frontmatter，重建为 `created` + `tags`；
2. 顶部生成 `> [!info] 文章信息` callout（标题 / 作者 / 发布日期 / 来源链接）；
3. `![](images/x.png)` → `![[images/x.png]]`，并保证独占一行；吃掉 URL 后的 `"undefined"` title；
4. **围栏感知**地截断文末推广（代码块里的 `---` 不会被误当分隔线）；
5. 逐条删除引流语、投稿邮箱、推荐阅读、点赞引导、"后台私信获取原文"、"拓展阅读"导航条；
6. 清理机构文的 `**PART**01**` 标记，合并 `**01**` + `**章节名**` 为二级标题；
7. 合并被微信按 token 切开的加粗标记（`**A****B**` → `**AB**`）；
8. 还原 `\_` `\**` 并删除独占一行的 `\`，但**不动** `C:\Users` 这类合法路径；
9. 删除空引用行（`^>`）；
10. 中文引号按行成对交替归一化为 `“ ”`；
11. 章节 `### ` → `## `（配合唯一的 H1 标题）；
12. 清理零宽空格、行尾空白、3 个以上连续空行。

每步命中时都会在 stdout 打处理记录，便于复核。

## 落库脚本做了什么

1. 从 `.obsidian.md` 的 H1 取标题、frontmatter 取 tags；
2. 落点 `vault/<subfolder>/<标题>/`，**每篇一个独立子文件夹**（否则同名 `img_000.png` 互相覆盖）;
3. 只复制正文真正引用的图片；推广图 / 二维码留在 output 里不落库；
4. 开跑前校验 `--vault` 存在且其下有 `.obsidian`（没有只告警，兼容非标准 vault）。

## 已知坑

见 [`references/pitfalls.md`](references/pitfalls.md)，动手改脚本前先看一遍。
尤其「引号归一化」和「tags 正则」两条 —— 都是看起来能跑、结果悄悄错的那类。

`scripts/to_obsidian.py` 相对初版基线的 6 处修复记录见
[`references/CHANGELOG-local.md`](references/CHANGELOG-local.md)，逐条 diff 见
[`references/to_obsidian.local.diff`](references/to_obsidian.local.diff)。

## 出处与致谢

本 skill 的 `SKILL.md`、`scripts/to_obsidian.py`、`references/` 全部为自研，
演化自 2026 年 7 月起在本地项目 `微信公总号知识库` 中迭代的脚本，于 2026-09-23 固化为 skill。

**唯一的外部代码**：`scripts/sync_to_vault.py` 中的 `format_frontmatter()` 与 `create_note()`
两个函数内联自 [obsidian-direct](https://api.skillhub.cn/ruslanlanket/obsidian-direct)
（作者 **ruslanlanket**，发布于 skillhub.cn）的 `scripts/obsidian_cli.py`，行为保持等价。
该 skill 已从本机卸载，本仓库保留内联实现以去掉运行时依赖。
本仓库未能确认 obsidian-direct 的明确开源许可证；若原作者对此有异议，请联系删除相关部分。

## License

除上述内联部分外，本项目采用 MIT。内联部分的权利归原作者所有。
