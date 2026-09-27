> 確認したコミット: 193a5e72

# 意図的想起と検索

Anima は自動想起で足りない情報を `search_memory` で明示的に探し、必要に応じて `read_memory_file` で元ファイルを読む。ツール定義は `core/tooling/schemas/memory.py`、引数の処理は `core/tooling/handler_memory.py` にある。

## `search_memory` の引数

| 引数 | 用途 |
|---|---|
| `query` | 自然言語の検索語。必須である。 |
| `scope` | `knowledge`、`episodes`、`procedures`、`facts`、`common_knowledge`、`skills`、`activity_log`、`code`、`all` から検索対象を選ぶ。省略時は `all`。 |
| `offset` | 結果のページ位置。1ページは 10 件で、最大 offset は 50。 |
| `project` | 登録された project archive に結果を限定する。 |
| `time_range` | `after` と `before` に ISO 形式の日付または時刻を指定し、期間を絞る。 |

引数の詳細と CLI の使用方法は[ツール CLI リファレンス](../reference/tool-cli.md)を参照する。コード検索には `scope="code"` と `project` が必要である。

## 検索パイプライン

`core/memory/retrieval/unified_search.py` は trigger と scope に基づいて候補を集める。ベクトル検索は意味的な近さを、BM25 は語句の一致を使う。両経路などから得た順位リストを RRF で融合し、設定と候補数に応じて rerank する。実際の主な順序は次の通りである。

1. クエリを拡張し、ベクトル検索向けと語句検索向けの入力を用意する。
2. ベクトルと BM25 の候補を取得する。`activity_log` は活動記録向け BM25 検索を使う。
3. `core/memory/retrieval/pipeline.py` で順位リストを RRF 融合する。
4. 期間と entity に基づく補正を行い、条件を満たすと cross-encoder で rerank する。
5. rerank 後に期間・entity の補正を反映し、アクセス履歴の補正を適用する。
6. confidence gate は結果の確からしさを判定するが、閾値を下回る候補も捨てずに低信頼として示す。候補そのものがない場合は検索結果を返さない。

期間指定がない場合も、クエリ中の日付や時間表現が検索候補の補正に使われることがある。trigger 別の scope と rerank 方針は[自動想起](priming.md)に記載する。

## Atomic facts と entity index

`facts/` には `core/memory/facts/store.py` の `FactRecord` が日付別 JSONL として保存される。レコードは文章、source/target entity、関係種別、有効時点・有効期限、出典エピソード、信頼度などを持つ。エピソードなどから抽出され、通常の意味記憶と同じく検索対象にできる。

`core/memory/facts/entity_index.py` は facts から `state/entity_registry.json` を構成し、entity 名や別名を検索時の候補補正に利用する。RAG 索引化は `core/memory/rag/indexer.py` が Markdown や facts をチャンク化し、メタデータとともにベクトル索引へ登録する。索引はファイル内容を正本とする派生データであり、定期処理が変更分を反映する。

## ベクトル経路

Chroma の永続ストアは Anima ごとの root プロセスの `MemoryService` が所有する。`core/memory/rag/vector_client.py` の共通 client と `vector_registry.py` が接続を選び、root 自身は in-process bridge を使う。server 側の内部 vector API は root へ IPC 転送し、ほかのプロセスは HTTP client 経由でアクセスする。埋め込み処理も server 側に集約される。

## RAG の修復

`core/memory/rag/repair_service.py` は破損の兆候を受けて修復を依頼する。root の `MemoryService` は元の記憶ファイルから staging 索引を作り、検証した後に切り替える。運用時に明示的な修復が必要な場合は、[CLI リファレンスの `repair-rag`](../reference/cli.md)を参照する。
