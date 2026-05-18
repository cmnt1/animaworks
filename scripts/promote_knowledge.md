# promote_knowledge.py — Anima知見の昇格パイプライン

Animaが各自の `procedures/` `knowledge/` に蓄積した知見のうち、
**confidence と利用実績の閾値を満たし、まだ昇格されていないもの** を
Obsidian の `_ai_rules/_inbox/<Project>/` にレビュー待ち文書として書き出す。

## 設計趣旨

`_ai_rules/_index.md` の原則：

| | Obsidian (`_ai_rules/`) | NotebookLM (Memory NB) |
|---|---|---|
| 性質 | ストック / canonical | フロー / 経緯ログ |
| 編集起点 | ここを直接編集 | 日次バッチで自動投入 |

この原則を守るため、**Animaは Obsidian 正本に直接書き込まない**。
代わりに2段昇格フローで品質を保つ：

```
[即時]   Anima の per-anima procedures/ knowledge/
            ↑ 既存 Consolidation が自動抽出
   ↓ promote_knowledge.py（週次cron想定）
[ステージング] _ai_rules/_inbox/<Project>/YYYY-MM-DD-<anima>-<slug>.md
   ↓ ユーザー or 当番Anima のレビュー（手動）
[正本]   _ai_rules/projects/<Project>/runbooks/<topic>.md
```

## 使い方

```bash
# 全Anima、デフォルト閾値で昇格（実書き込み）
python3 scripts/promote_knowledge.py

# 何も書かずに対象を表示（推奨：初回確認）
python3 scripts/promote_knowledge.py --dry-run

# 特定Animaのみ
python3 scripts/promote_knowledge.py --anima sakura

# 直近7日に更新された分のみ
python3 scripts/promote_knowledge.py --since 7

# 既に昇格済みの分も再昇格（テンプレート見直し時など）
python3 scripts/promote_knowledge.py --force
```

## 動作

1. `~/.animaworks/animas/*/{procedures,knowledge}/*.md` を走査
2. 各ファイルのfrontmatterを読み、以下で絞り込み：
   - `confidence >= threshold`（procedures: 0.7、knowledge: 0.7）
   - procedures は `success_count >= 1`
   - `promoted_to_inbox` フィールドが未設定（`--force` で無視）
   - `--since N` 指定時は `last_used`/`updated_at`/`created_at` が直近N日以内
3. project あたり最大 `max_items_per_project_per_run` 件（デフォルト10）
4. 出力先パス：`_inbox/<Project>/YYYY-MM-DD-<anima>-<slug>.md`
5. ソースfrontmatterに `promoted_to_inbox: <ISO timestamp>` を追記（冪等化）

## project の解決順序

`scripts/promote_knowledge.json` で制御：

1. `anima_override[<anima_name>]` が設定されていればそれを使用
2. なければ `status.json` の `department` を `department_map` で変換
3. それでも未解決なら `default_project`（デフォルト `General`）

現在の自動マッピング（status.json の department より）：

| Anima | department | Project |
|---|---|---|
| sakura | 全社 | General |
| kanna, karen, miyu, ria | Affiliate | Affiliate |
| airi, ayane, momoka, rika | Finance | Finance |
| aoi, hikaru, mai, yuri | Property | Property |
| mira, sora | Administration | General |

## inbox 文書の構造

```markdown
---
project: <Project>
promoted_at: 2026-05-18T12:34:56+09:00
role: runbook
scope: project
source_anima: sakura
source_confidence: 1.0
source_kind: procedures
source_path: C:/Users/cmnt/.animaworks/animas/sakura/procedures/...
source_success_count: 1
status: pending_review
updated: 2026-05-18
---

> [!review] sakura の procedures から昇格された知見。レビュー後 `_ai_rules/projects/General/runbooks/` へ移動してください。
> source: `aff-priority-recovery-and-db-audit.md` (confidence=1.0)

# <元の本文>
```

## レビュー → 正本昇格の手順

1. `_inbox/<Project>/` のファイルを開いて内容確認
2. 採用する場合：
   - frontmatter の `status: pending_review` を削除
   - `source_*` 系のメタは残してよい（出自トレース用）
   - ファイルを `_ai_rules/projects/<Project>/runbooks/` に移動
   - ファイル名から日付・anima名プレフィックスを外す（任意）
3. 不採用 / 重複の場合：
   - `_inbox/` 内のファイルを削除
   - Anima側 `procedures/<file>.md` の `promoted_to_inbox` は残す
     （再昇格を防ぐ。再考したい場合は `--force` で再走）

## 週次cron への組み込み（任意）

`~/.animaworks/animas/sakura/cron.md` 等に追加：

```markdown
## 週次：Anima知見をObsidian _inbox に昇格
schedule: 0 6 * * 1
type: command
command: cd E:/OneDriveBiz/Tools/General/animaworks && .venv/Scripts/python.exe scripts/promote_knowledge.py --since 14
```

## 関連ファイル

- 設定：[`scripts/promote_knowledge.json`](promote_knowledge.json)
- Anima側procedure生成テンプレ：`E:/OneDriveBiz/Obsidian/_ai_rules/_shared/workflows/memory/procedure_from_resolved.md`
- Obsidian SoT原則：`E:/OneDriveBiz/Obsidian/_ai_rules/_index.md`
