> 確認したコミット: 193a5e72

# 記憶システム

AnimaWorks の記憶は、必要なものだけを実行時コンテキストへ取り出すファイルベースの書庫である。Anima は記憶を読み書きし、記録の統合や整理を判断する。フレームワークは検索用の索引や候補を用意するが、古い記録を一律の機械規則で移動・削除する設計ではない。自動索引の役割は[意図的想起と検索](retrieval.md)を参照する。

## 人間の記憶モデルとの対応

| 人間の記憶 | AnimaWorks | 役割 |
|---|---|---|
| ワーキングメモリ | LLM のコンテキスト | 現在の判断に必要な情報を一時的に保持する。 |
| エピソード記憶 | `episodes/` | いつ何が起きたかを時系列で記録する。 |
| 意味記憶 | `knowledge/` | 経験から得た知識、教訓、方針を保持する。 |
| 手続き記憶 | `procedures/`、`skills/` | 作業の進め方や再利用可能な手順を保持する。 |
| 構造化された事実 | `facts/` | 会話や記録から抽出した、entity と時点を伴う atomic fact を保存する。 |

長期記憶の正本はファイルであり、検索用ベクトル索引や BM25 索引は再生成できる派生データである。自動想起と明示的な検索の使い分けは[自動想起](priming.md)と[検索](retrieval.md)を参照する。

## 記憶ディレクトリ

Anima ごとの記憶領域は `~/.animaworks/animas/{name}/` の下にある。

| ディレクトリ | 役割 |
|---|---|
| `episodes/` | 日々の出来事や作業のエピソード記録。 |
| `knowledge/` | 意味記憶。知識、教訓、方針などを Markdown で保持する。 |
| `procedures/` | 手順を Markdown で保持し、実行結果を使って信頼度や版を追跡する。 |
| `facts/` | 日付単位の JSONL に atomic fact を保存する。 |
| `skills/` | 手順書やツール利用の再利用可能なスキル文書を保持する。 |
| `state/` | 現在状態や、fact から再構成可能な entity registry などの状態データを保持する。 |
| `shortterm/` | セッション中の短期データとストリーミングジャーナルを保持する。 |

対人プロフィールは共有領域の `shared/users/` に置かれ、Anima 固有の長期記憶とは別に参照される。

## Frontmatter

`knowledge/` と `procedures/` の Markdown には YAML frontmatter を付けられる。`core/memory/frontmatter.py` は共通の読み書き、修復、既定値の補完を担う。キーを一律必須とする閉じたスキーマではなく、内容や用途に応じたメタデータである。

`knowledge/` では、`created_at`、`updated_at`、`confidence`、`source_episodes`、`auto_consolidated`、`version` が作成・保守時に使われる。`success_count`、`failure_count` は `confidence` とともに報告された有用性を追跡し、`valid_from`・`valid_until` は事実の有効期間、`description` は検索結果の要約に使える。`always_prime: true` は自動想起への明示的な opt-in である。意味と適用範囲は[自動想起](priming.md)を参照する。

`procedures/` では `description`、`confidence`、`success_count`、`failure_count`、`version`、`created_at`、`updated_at` が手順の説明と利用結果の追跡に使われる。`auto_distilled` は自動蒸留で作られた手順を示し、`protected` は保護指定である。`core/memory/skill_metadata.py` は手順のメタデータを skill catalog と共通の形式で扱う。`description` がない場合は文書の `## 概要` から補える。スキル文書のメタデータ読込は `core/skills/loader.py` が担う。

設定項目の一覧と既定値は[設定リファレンス](../reference/config.md)を参照する。日々の統合と手順の利用追跡は[統合と忘却](consolidation.md)に記載する。
