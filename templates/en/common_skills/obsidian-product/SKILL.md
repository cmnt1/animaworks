---
name: obsidian-product
description: >-
  A skill that writes deliverable reports to an Obsidian Vault and aggregates them into Bases (`0_Products DB.base`).
  Use when: When recording deliverables submitted to humans (reports, deliverables, deployment records, etc.) and their accompanying materials.
  Successor to the old Notion T_Products DB. Because it is written directly to md on the Vault, capture is easy, and accompanying materials can be traced via wikilinks.
tags: [productivity, obsidian, report, deliverable]
---


# Obsidian Product Report

The submission destination for deliverables has been unified into the **Obsidian Vault**. Notion `T_Products` is abolished.
This skill defines the conventions for "where to write a report, with what naming, and with what frontmatter." The writing itself is done with the usual `Write` / `Edit` / `Bash` tools.
Plans, progress, decisions, and items awaiting confirmation for project management also use Markdown in the Obsidian Vault as the source of truth. Do not read from or write to Notion, and do not submit deliverables to Notion DBs.

## Vault Path (Fixed)

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
  - Do not create subfolders. Express parent-child relationships via the filename prefix

`<slug>` is ASCII lowercase, and the separator is `-` (hyphen). If it is difficult to convert mechanically from a Japanese title, decide on an alphanumeric keyword yourself that does not lose the meaning, or omit the `slug` part and use `P-00042.md` (if there is a `P-` code, it is unique).

## Operations

### 1. create — Create a new report

1. **Decide the next ID** (numbering)
   - Use Bash to extract `id:` from all md files under `_products\`, take the max, and add +1. Do not use a counter file.
   - One-liner example (using Python assuming both Git Bash / PowerShell):
     ```bash
     python -c "import re, pathlib; ids=[int(m.group(1)) for p in pathlib.Path(r'E:/OneDriveBiz/Obsidian/_products').rglob('*.md') for m in [re.search(r'^id:\s*(\d+)', p.read_text(encoding='utf-8'), re.M)] if m]; print(max(ids)+1 if ids else 1)"
     ```
   - If the result is `42`, then `code = P-00042`.

2. **Decide the file path**
   - `E:\OneDriveBiz\Obsidian\_products\<Category>\P-<NNNNN>_<slug>.md`

3. **Write the frontmatter + body with Write** (copy and fill in the "frontmatter template (main)" below)

4. **If necessary, ask the user to reload Bases**, and include the code (e.g., `P-00042`) in the completion report to the user. Being able to call it `P-42 見といて` during conversation is an advantage of this design.

### 2. attach — Add accompanying materials

1. Create `P-<NNNNN>_<slug>_<asset>.md` directly in the same category folder as the main (`<asset>` is the material name slug).
2. Use the "frontmatter template (accompanying material)" for the frontmatter. `type: product_asset` and `parent_code: "P-<NNNNN>"` are required.
3. Add a wikilink to the main report:
   ```markdown
   ## 付随資料
   - [[P-00042_aff-recipe-v2_spec]] — 仕様書
   - [[P-00042_aff-recipe-v2_data]] — 元データ
   ```
   Obsidian automatically turns it into a link (it is `type: product_asset` in the Base table, so it is not displayed).

### 3. update — Update an existing report

1. Read the target file.
2. Rewrite the frontmatter with Edit, and always update `updated:` to the current date and time (JST).
3. Perform status transitions (`未着手` → `進行中` → `監査待`) here. Only sakura can change it to `完了`. `confirmed` is for human confirmation, so in principle Anima should leave it as `false` when creating or updating, and should not change it to `true`.
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

## Convention Summary

- **Unify on the Vault**: Place both deliverables and drafts in `_products\<Category>\` (create drafts with `status: 未着手`, and update to `status: 完了` upon completion). The old `E:\OneDriveBiz\Downloads\` is abolished
- **ID immutable, refer by code**: After creation, do not change `id`/`code`. In conversation, refer to it in the `P-00042` format
- **Only one frontmatter at the top of the file**: The beginning must always be in the order `---` → YAML containing `type: product` → `---` → body. Do not add a small frontmatter like `--- confirmed: ... ---` at the beginning
- **Save as UTF-8 without BOM**: Save Markdown as UTF-8 without BOM. PowerShell 5's `Set-Content -Encoding UTF8` tends to add a BOM, so avoid it; use PowerShell 7's `utf8NoBOM`, Python's `encoding="utf-8"`, or `.NET UTF8Encoding(false)`
- **Only sakura can set `status: 完了`**: Anima other than sakura should set it to `status: 監査待` after finishing the report and storing it in `_products\<Category>\`. Changing it to completion status is done after sakura's audit
- **Always issue an audit request**: Anima other than sakura should, after setting it to `status: 監査待`, send an audit request to sakura with `P-<NNNNN>`, the file path, and the points to be audited
- **`confirmed` is a human-side confirmation flag**: Anima creates new reports with `confirmed: false`. After the human confirms in Obsidian, it is changed to true. Anima must not append or overwrite `confirmed: true` at the beginning
- **Place accompanying materials in the same folder without creating subfolders**: Express parent-child relationships via the filename prefix
- **wikilink recommended**: Use `[[P-00042_xxx_yyy]]` notation for internal links. Do not write paths (Obsidian resolves automatically)
- **Distinguish `type: product` / `type: product_asset`**: The Base table picks up only the main. Accompanying materials only need to be traceable via wikilinks
- **Japanese allowed**: `title`, `product_type`, `status` remain in Japanese. Only `category` is in English letters (to match the folder name)

## Operational Examples

### Scenario: Wrote a weekly report

1. Number the next ID: for example `43`
2. Write to `E:\OneDriveBiz\Obsidian\_products\General\P-00043_weekly-report-2026w17.md` (with frontmatter)
3. Attach a summary of the source CSV data: create `..._data.md` and add a wikilink
4. Notify the supervisor with `send_message(intent="report", content="P-00043 週次レポートを提出しました。")`

### Scenario: Task received → in progress → completed

1. When receiving the task, write only the skeleton with `status: 未着手` (fill it in later)
2. When starting, Edit to `status: 進行中`, update `updated`
3. When the report is finished, non-sakura set it to `status: 監査待`, enter the `submitted` date, and finish the body
4. Send an audit request to sakura with `P-<NNNNN>` and the file path
5. After the audit, sakura makes corrections if necessary, and if there are no problems, sets it to `status: 完了`
6. In some cases, it may be set to `requires_reply: true` to wait for human confirmation
