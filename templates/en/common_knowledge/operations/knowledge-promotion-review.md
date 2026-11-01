# Knowledge Promotion Review — Obsidian `_inbox/` Decision Flow

Of the knowledge each Anima accumulates in `procedures/` `knowledge/`, `promote_knowledge.py` (weekly cron)
stages it into the Obsidian `_ai_rules/_inbox/<Project>/`. This documentation defines a
common framework for deciding **whether to promote that staging to
the canonical source (`_ai_rules/projects/<Project>/runbooks/`) or discard it**.

> Design intent: The Obsidian `_ai_rules/` is the "stock / canonical," and each Anima's per-anima memory is the "flow."
> Anima is prohibited from writing directly to the Obsidian canonical source. By inserting `_inbox/` as an intermediate step, the quality of the canonical source is maintained.

## Stakeholders and Responsibility Allocation

| Category | Target inbox | Decider | Support |
|---|---|---|---|
| Company-wide / cross-organization | `_inbox/General/` | **Owner (human)** | sakura organizes review perspectives and calls call_human |
| Department-specific | `_inbox/<部門>/` | **Department GL** | sakura requests via delegate_task, GL decides |
| Cross-department know-how | Part of `_inbox/<部門>/` | **Department GL → sakura → Owner** | GL flags as "General candidate" and escalates |

Department GLs (project_manager):

- Affiliate → kanna
- Finance → ayane
- Property → hikaru
- Administration → sora (* `_ai_rules/projects/Administration/` is not yet in place; treated as General for the time being)

## Adoption Criteria (Promotion Decision)

Promote to runbooks only those that **satisfy all** of the following:

1. **Reusability**: The same kind of situation may occur again in the future (one-off situation notes are not adopted)
2. **Reproducibility**: Specific commands, configuration values, and decision points are written
3. **Non-duplication**: Content does not duplicate existing runbooks / common_knowledge
4. **Accuracy**: Does not contain outdated information or incorrect speculation
5. **Appropriate granularity**: Neither too fine (single-command note) nor too coarse (chapter level)

## Patterns That Should Not Be Adopted

- Date-specific snapshots (weekly retrospectives like `weekly-consolidation-2026w20.md`)
- One-time incident responses that will not recur
- Content that is nearly identical to existing documentation and adds no value
- Anima's own impressions/realizations only, not turned into procedures
- Content that is sufficient to keep in the Anima's per-anima knowledge/

## Decision Flow

```
_inbox/<Project>/<file>.md を開く
   ↓
採用基準1-5をすべて満たすか？
   ├─ Yes → 「採用」
   │         ├─ frontmatter `status: pending_review` を削除
   │         ├─ frontmatter `promoted_at` `source_*` は残す（出自トレース）
   │         ├─ ファイル名から `YYYY-MM-DD-<anima>-` プレフィックスを除去
   │         └─ `_ai_rules/projects/<Project>/runbooks/` に移動
   │
   ├─ 部門横断（General候補） → 「上申」
   │         └─ そのまま `_inbox/General/` に移動し、sakura に報告
   │
   └─ No → 「不採用」
             └─ `_inbox/` から削除（source側の `promoted_to_inbox` スタンプは残るので再昇格されない）
```

## delegate_task Template for Department GLs (for sakura)

```
to: <gl_name>
intent: delegation
content:
  Obsidian の `E:/OneDriveBiz/Obsidian/_ai_rules/_inbox/<Project>/` 配下に、今週Animaから昇格された
  知見が staging されています。`common_knowledge/operations/knowledge-promotion-review.md` の
  「採用基準」と「判定フロー」に従って各ファイルを判定し、以下を行ってください。

  完了条件:
  - 採用したファイル: `_ai_rules/projects/<Project>/runbooks/` に移動済み（frontmatter整形・ファイル名整形済み）
  - 不採用ファイル: `_inbox/<Project>/` から削除済み
  - General候補としてsakuraへ上申するファイル: `_inbox/General/` に移動し、報告に列挙
  - 報告に含めるもの: 採用件数 / 不採用件数 / 上申件数 / 各ファイル名と一行理由

  期限: <YYYY-MM-DD HH:MM>
```

## Formatting Rules (When Adopting)

frontmatter example:

```yaml
---
# 残す（出自トレース用）
project: Affiliate
promoted_at: 2026-05-18T12:34:56+09:00
role: runbook
scope: project
source_anima: kanna
source_confidence: 1.0
source_kind: procedures
source_path: C:/Users/cmnt/.animaworks/animas/kanna/procedures/xxx.md
updated: 2026-05-18

# 削除する
status: pending_review
```

File name:

- before: `2026-05-18-kanna-sql-server-334-trigger-output-fix.md`
- after:  `sql-server-334-trigger-output-fix.md`

> Note: The Obsidian view (`AI Rules DB.base`) may filter `_inbox/` by `status: pending_review`,
> so unless status is removed, it will not be treated as canonical.

## Related

- Promotion script: `E:/OneDriveBiz/Tools/General/animaworks/scripts/promote_knowledge.py`
- Configuration: `scripts/promote_knowledge.json`
- Operations documentation: `scripts/promote_knowledge.md`
- SoT principle: `E:/OneDriveBiz/Obsidian/_ai_rules/_index.md`
