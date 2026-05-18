# 知見昇格レビュー — Obsidian `_inbox/` の判定フロー

各Animaが `procedures/` `knowledge/` に蓄積した知見のうち、`promote_knowledge.py`（週次cron）が
Obsidian `_ai_rules/_inbox/<Project>/` にステージングする。本ドキュメントは、その staging を
**正本（`_ai_rules/projects/<Project>/runbooks/`）に昇格させるか・破棄するか**を判定するための
共通フレームワーク。

> 設計趣旨: Obsidian `_ai_rules/` は「ストック / canonical」、Animaの per-anima 記憶は「フロー」。
> Animaが直接 Obsidian 正本に書き込むことは禁止。`_inbox/` を一段噛ませることで、正本の品質を保つ。

## 関係者と責任分担

| 区分 | 対象inbox | 判定者 | 補助 |
|---|---|---|---|
| 全社・組織横断 | `_inbox/General/` | **オーナー（人間）** | sakuraがレビュー観点を整理してcall_human |
| 部門固有 | `_inbox/<部門>/` | **部門GL** | sakuraがdelegate_taskで依頼、GLが判定 |
| 部門横断ノウハウ | `_inbox/<部門>/` の一部 | **部門GL → sakura → オーナー** | GLが「General候補」フラグして上申 |

部門GL（project_manager）:

- Affiliate → kanna
- Finance → ayane
- Property → hikaru
- Administration → sora（※ `_ai_rules/projects/Administration/` は未整備、当面 General 扱い）

## 採用基準（昇格判定）

以下を**すべて満たす**ものだけ runbooks に昇格させる:

1. **再利用性**: 同種の状況が将来また起きうる（1回限りの状況メモは不採用）
2. **再現可能性**: 具体的なコマンド・設定値・判断ポイントが書かれている
3. **非重複**: 既存の runbooks / common_knowledge と内容が重複しない
4. **正確性**: 古くなった情報・誤った推測を含まない
5. **粒度適切**: 細かすぎ（1コマンドメモ）でも雑すぎ（章レベル）でもない

## 不採用にすべきパターン

- 日付固有のスナップショット（`weekly-consolidation-2026w20.md` のような週次振り返り）
- 一度きりの障害対応で再発しないもの
- 既存ドキュメントと内容がほぼ同じで追加価値がないもの
- Anima自身の感想・気付きのみで手順化されていないもの
- 当該Animaの per-anima knowledge/ に置いておけば十分なもの

## 判定フロー

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

## 部門GL への delegate_task テンプレート（sakura用）

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

## 整形ルール（採用時）

frontmatter例:

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

ファイル名:

- before: `2026-05-18-kanna-sql-server-334-trigger-output-fix.md`
- after:  `sql-server-334-trigger-output-fix.md`

> 注意: Obsidian view（`AI Rules DB.base`）が `status: pending_review` で `_inbox/` を絞り込んでいる
> 場合があるため、status を削除しない限り正本扱いにならない。

## 関連

- 昇格スクリプト: `E:/OneDriveBiz/Tools/General/animaworks/scripts/promote_knowledge.py`
- 設定: `scripts/promote_knowledge.json`
- 運用ドキュメント: `scripts/promote_knowledge.md`
- SoT原則: `E:/OneDriveBiz/Obsidian/_ai_rules/_index.md`
