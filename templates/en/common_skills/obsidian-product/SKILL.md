---
name: obsidian-product
description: >-
  A skill that writes deliverable reports to an Obsidian Vault and aggregates them in Bases (`0_Products DB.base`).
  Use when: When recording deliverables submitted to humans (reports, deliverables, deployment records, etc.) and their accompanying materials.
  Successor to the former Notion T_Products DB. Because it is written directly to md files in the Vault, capture is easy, and accompanying materials can be traced via wikilinks.
tags: [productivity, obsidian, report, deliverable]
---


# Obsidian Product Report

The destination for deliverables has been unified into the **Obsidian Vault**. Notion `T_Products` has been abolished.
This skill defines the conventions for "where to write reports, with what naming, and with what frontmatter." The writing itself is done with the usual `Write` / `Edit` / `Bash` tools.
Plans, progress, decisions, and pending confirmations for project management also use Markdown in the Obsidian Vault as the source of truth. Do not read from or write to Notion, and do not submit deliverables to Notion DBs.

## Vault Paths (Fixed)

- **Vault root**: `E:\OneDriveBiz\Obsidian\`
- **Products root**: `E:\OneDriveBiz\Obsidian\_products\`
- **Base file**: `E:\OneDriveBiz\Obsidian\0_Products DB.base` (no editing required; Obsidian automatically reads and displays this file)

## Category → Folder Mapping

| Category (frontmatter `category`) | Storage folder |
|---|---|
| `General` | `_products\General\` |
| `Finance` | `_products\Finance\` |
| `Affiliate` | `_products\Affiliate\` |
| `Property` | `_products\Property\` |
| `Business` | `_products\Business\` (formerly "Management") |

If unsure, use `General`.

## File Naming Rules

- Main report: `P-<5桁ゼロ埋めID>_<slug>.md`
  - Example: `P-00042_aff-recipe-v2.md`
- Accompanying materials: place them **directly in the same category folder** as the main, with the **same prefix** as the main
  - Example: `P-00042_aff-recipe-v2_spec.md`, `P-00042_aff-recipe-v2_data.md`
  - Do not create subfolders. Express parent-child relationships via filename prefixes

`<slug>` must be ASCII lowercase, with `-` (hyphen) as the separator. If mechanical conversion from a Japanese title is difficult, decide on an alphanumeric keyword yourself that does not lose the meaning, or omit the `slug` part and use `P-00042.md` (unique if there is a `P-` code).

## Operations

### 1. create — Create a new report

1. **Determine the next ID** (numbering)
   - Use Bash to extract `id:` from all md files under `_products\`, take the max, and add 1. Do not use a counter file.
   - One-liner example (using Python to support both Git Bash / PowerShell):
     ```bash
     python -c "import re, pathlib; ids=[int(m.group(1)) for p in pathlib.Path(r'E:/OneDriveBiz/Obsidian/_products').rglob('*.md') for m in [re.search(r'^id:\s*(\d+)', p.read_text(encoding='utf-8'), re.M)] if m]; print(max(ids)+1 if ids else 1)"
     ```
   - If the result is `42`, then `code = P-00042`.

2. **Determine the file path**
   - `E:\OneDriveBiz\Obsidian\_products\<Category>\P-<NNNNN>_<slug>.md`

3. **Write the frontmatter + body with Write** (copy and fill in the "frontmatter template (main)" below)

4. **If necessary, include the code (e.g., `P-00042`) in the completion report to the user** so they can reload Bases. The advantage of this design is that it can be called `P-42 見といて` during conversation.

### 2. attach — Add accompanying materials

1. Create `P-<NNNNN>_<slug>_<asset>.md` directly in the same category folder as the main (`<asset>` is the material name slug).
2. Use the "frontmatter template (accompanying material)" for the frontmatter. `type: product_asset` and `parent_code: "P-<NNNNN>"` are required.
3. Append a wikilink to the main report:
   ```markdown
   ## 付随資料
   - [[P-00042_aff-recipe-v2_spec]] — 仕様書
   - [[P-00042_aff-recipe-v2_data]] — 元データ
   ```
   Obsidian automatically turns it into a link (it does not appear in the Base table because `type: product_asset`).

### 3. update — Update an existing report

1. Read the target file.
2. Rewrite the frontmatter with Edit, and always update `updated:` to the current date and time (JST).
3. Perform status transitions (`未着手` → `進行中` → `監査待`) here. Only sakura can change to `完了`. `confirmed` is for human confirmation, so Anima should in principle leave it as `false` when creating or updating, and must not change it to `true`.
4. **Never change** `id` and `code`.

### 4. list — List existing reports

Simple listing with Bash:
```bash
grep -rH "^code:" "E:/OneDriveBiz/Obsidian/_products/" | sort
```
For a full-fledged view, just open `0_Products DB.base` on the Obsidian side.

## frontmatter template (main, for copy-paste)

```yaml
---
type: product
id: 42
code: "P-00042"
title: "アフィリエイト配信レシピ v2"
category: Finance              # General | Finance | Affiliate | Property | Business
product_type: 報告書            # 報告書 | 成果物 | デプロイ記録 | その他
status: 監査待                  # 未着手 | 進行中 | 監査待 | 完了（完了にできるのは sakura のみ）
task_code: AFF-001             # 対応するタスクコードがあれば。無ければ空文字 ""
assignee: 自分のAnima名          # 作成した Anima 名
submitted: 2026-04-23
requires_reply: false           # 人間からの返信・確認を待ちたい場合 true
confirmed: false                # 人間側が確認して落着済みなら true（基本は人間が後でチェック）
created: 2026-04-23T09:15:00+09:00
updated: 2026-04-23T09:15:00+09:00
tags: [product]
---

# アフィリエイト配信レシピ v2

## 要旨
...

## 本文
...

## 付随資料
- [[P-00042_aff-recipe-v2_spec]] — 仕様書
```

## frontmatter template (accompanying material, for copy-paste)

```yaml
---
type: product_asset
parent_code: "P-00042"
title: "アフィリエイト配信レシピ v2 — 仕様書"
created: 2026-04-23T09:15:00+09:00
updated: 2026-04-23T09:15:00+09:00
tags: [product-asset]
---

# アフィリエイト配信レシピ v2 — 仕様書

（本文）
```

## Conventions Summary

- **Unify in the Vault**: Place both deliverables and drafts in `_products\<Category>\` (create drafts with `status: 未着手`, update to `status: 完了` upon completion). The former `E:\OneDriveBiz\Downloads\` is abolished
- **ID immutable, refer by code**: After creation, do not change `id`/`code`. In conversation, refer to it in the `P-00042` format
- **Only one frontmatter at the top of the file**: The top must always be `---` → YAML containing `type: product` → `---` → body, in that order. Do not add a small frontmatter like `--- confirmed: ... ---` at the top
- **Save as UTF-8 without BOM**: Save Markdown as UTF-8 without BOM. Avoid PowerShell 5's `Set-Content -Encoding UTF8` because it tends to add a BOM; use PowerShell 7's `utf8NoBOM`, Python's `encoding="utf-8"`, or `.NET UTF8Encoding(false)`
- **Only sakura can set `status: 完了`**: Anima other than sakura should set `status: 監査待` after finishing the report and storing it in `_products\<Category>\`. Changing to completion status is done after sakura's audit
- **Always send an audit request**: After setting `status: 監査待`, Anima other than sakura sends an audit request to sakura with `P-<NNNNN>`, the file path, and the perspectives to be audited
- **`confirmed` is a human-side confirmation flag**: Anima creates new reports with `confirmed: false`. Humans change it to true after confirming in Obsidian. Anima must not append or overwrite `confirmed: true` at the top
- **Place accompanying materials in the same folder without creating subfolders**: Express parent-child relationships via filename prefixes
- **wikilink recommended**: Use `[[P-00042_xxx_yyy]]` notation for internal links. Do not write paths (Obsidian resolves automatically)
- **Distinguish `type: product` / `type: product_asset`**: The Base table picks up only the main. Accompanying materials only need to be traceable via wikilinks
- **Japanese allowed**: `title`, `product_type`, `status` remain in Japanese. Only `category` must be in English letters (to match the folder name)

## Usage Examples

### Scenario: Wrote a weekly report

1. Number the next ID: for example `43`
2. Write to `E:\OneDriveBiz\Obsidian\_products\General\P-00043_weekly-report-2026w17.md` (with frontmatter)
3. Attach a summary of the source CSV data: create `..._data.md` and append a wikilink
4. Notify the supervisor via `send_message(intent="report", content="P-00043 週次レポートを提出しました。")`

### Scenario: Task received → in progress → completed

1. When receiving the task, write only the skeleton with `status: 未着手` (fill in later)
2. When starting, Edit to `status: 進行中`, update `updated`
3. When the report is finished, non-sakura set `status: 監査待`, enter the `submitted` date, and finalize the body
4. Send an audit request to sakura with `P-<NNNNN>` and the file path
5. Sakura audits, makes corrections if necessary, and sets `status: 完了` if there are no problems
6. In some cases, set `requires_reply: true` to wait for human confirmation
