---
name: obsidian-product
description: >-
  Write deliverable reports to the Obsidian Vault and have them aggregated by the `0_Products DB.base` Base.
  Use when: producing a deliverable for a human (report, artifact, deploy log, etc.) or attaching supporting material.
  Replaces the retired Notion `T_Products` DB. Reports live as plain md in the Vault; supporting files are reachable via wikilinks.
tags: [productivity, obsidian, report, deliverable]
---

# Obsidian Product Report

Deliverables now go to the **Obsidian Vault** only. The Notion `T_Products` DB is retired.
This skill specifies *where to write*, *how to name the file*, and *what frontmatter to include*. The write itself uses the usual `Write` / `Edit` / `Bash` tools.

## Vault Paths (fixed)

- **Vault root**: `E:\OneDriveBiz\Obsidian\`
- **Products root**: `E:\OneDriveBiz\Obsidian\_products\`
- **Base file**: `E:\OneDriveBiz\Obsidian\0_Products DB.base` (do not edit; Obsidian reads it automatically)

## Category → Folder

| Category (frontmatter `category`) | Folder |
|---|---|
| `General` | `_products\General\` |
| `Finance` | `_products\Finance\` |
| `Affiliate` | `_products\Affiliate\` |
| `Property` | `_products\Property\` |
| `Business` | `_products\Business\` (formerly "経営") |

Default to `General` when unsure.

## File Naming

- Main report: `P-<5-digit zero-padded id>_<slug>.md`
  - Example: `P-00042_aff-recipe-v2.md`
- Attachments: placed **in the same category folder**, sharing the main file's prefix
  - Example: `P-00042_aff-recipe-v2_spec.md`, `P-00042_aff-recipe-v2_data.md`
  - Do not create subfolders. Parent/child linkage is encoded in the filename prefix.

`<slug>` is lowercase ASCII, hyphen-separated. If the title resists romanization, pick short English keywords yourself, or drop the slug and just use `P-00042.md` (the `P-` code is already unique).

## Operations

### 1. create — new report

1. **Pick the next id** (allocation)
   - Bash: scan every md under `_products\`, extract `id:`, take max, add 1. No counter file.
   - One-liner using Python (works in Git Bash and PowerShell):
     ```bash
     python -c "import re, pathlib; ids=[int(m.group(1)) for p in pathlib.Path(r'E:/OneDriveBiz/Obsidian/_products').rglob('*.md') for m in [re.search(r'^id:\s*(\d+)', p.read_text(encoding='utf-8'), re.M)] if m]; print(max(ids)+1 if ids else 1)"
     ```
   - If the result is `42`, then `code = P-00042`.

2. **Choose the file path**
   - `E:\OneDriveBiz\Obsidian\_products\<Category>\P-<NNNNN>_<slug>.md`

3. **Write frontmatter + body** (paste the "frontmatter template (main)" below and fill in).

4. **Tell the human the code** in the completion report (e.g. `P-00042`). Compact codes like `P-42` are the whole point of this design — use them in chat.

### 2. attach — add supporting material

1. Create `P-<NNNNN>_<slug>_<asset>.md` in the *same* category folder (`<asset>` is a short slug for the asset).
2. Use the "frontmatter template (attachment)" below. `type: product_asset` and `parent_code: "P-<NNNNN>"` are required.
3. Append a wikilink to the main report:
   ```markdown
   ## Attachments
   - [[P-00042_aff-recipe-v2_spec]] — spec
   - [[P-00042_aff-recipe-v2_data]] — source data
   ```
   Obsidian resolves these automatically, and the Base table skips `type: product_asset`, so attachments don't clutter the ledger.

### 3. update — modify an existing report

1. Read the target file.
2. Edit the frontmatter; always bump `updated:` to the current JST timestamp.
3. Status transitions (`未着手` → `進行中` → `完了`) and `confirmed` flips happen here.
4. **Never change `id` or `code`.**

### 4. list — quick listing

Ad-hoc shell listing:
```bash
grep -rH "^code:" "E:/OneDriveBiz/Obsidian/_products/" | sort
```
For the real view, open `0_Products DB.base` in Obsidian.

## Frontmatter Template (main, paste-ready)

```yaml
---
type: product
id: 42
code: "P-00042"
title: "Affiliate Delivery Recipe v2"
category: Finance              # General | Finance | Affiliate | Property | Business
product_type: 報告書            # 報告書 | 成果物 | デプロイ記録 | その他
status: 完了                    # 未着手 | 進行中 | 完了
task_code: AFF-001             # corresponding task code, or "" if none
assignee: your-anima-name       # the Anima that produced this
submitted: 2026-04-23
requires_reply: false           # true if you want human confirmation before closing
confirmed: false                # true after the human has reviewed and accepted
created: 2026-04-23T09:15:00+09:00
updated: 2026-04-23T09:15:00+09:00
tags: [product]
---

# Affiliate Delivery Recipe v2

## Summary
...

## Body
...

## Attachments
- [[P-00042_aff-recipe-v2_spec]] — spec
```

(Note: `product_type` and `status` values are kept in Japanese so they match the Base views used by the human operator.)

## Frontmatter Template (attachment, paste-ready)

```yaml
---
type: product_asset
parent_code: "P-00042"
title: "Affiliate Delivery Recipe v2 — Spec"
created: 2026-04-23T09:15:00+09:00
updated: 2026-04-23T09:15:00+09:00
tags: [product-asset]
---

# Affiliate Delivery Recipe v2 — Spec

(body)
```

## Conventions Summary

- **Vault only**: both drafts and final deliverables live in `_products\<Category>\` (create drafts with `status: 未着手`, flip to `status: 完了` when finished). The former `E:\OneDriveBiz\Downloads\` workflow is retired.
- **Immutable id / refer by code**: never change `id` or `code` after creation. Refer to products in chat as `P-00042`.
- **Attachments stay flat**: no subfolders; the filename prefix carries parent/child.
- **Wikilinks preferred**: internal links use `[[P-00042_xxx_yyy]]` form — no paths (Obsidian resolves by filename).
- **`type: product` vs `type: product_asset`**: the Base ledger only shows main reports. Attachments are reachable via wikilinks only.
- **Japanese values allowed**: `product_type`, `status`, and `title` may be Japanese. Only `category` is forced to ASCII (to match folder names).

## Usage Examples

### Scenario: weekly report

1. Allocate next id, say `43`
2. Write `E:\OneDriveBiz\Obsidian\_products\General\P-00043_weekly-report-2026w17.md` with frontmatter
3. Summarize source CSV into a sibling `..._data.md` and wikilink it from the main report
4. Notify the supervisor: `send_message(intent="report", content="P-00043 weekly report filed.")`

### Scenario: task intake → in-progress → done

1. On intake: create with `status: 未着手` and a skeleton body
2. On start: flip to `status: 進行中`, bump `updated`
3. On completion: set `status: 完了`, fill `submitted`, finalize body
4. Optionally set `requires_reply: true` to flag for human review
