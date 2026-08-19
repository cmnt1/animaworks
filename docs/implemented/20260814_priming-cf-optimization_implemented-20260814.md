# C/F priming最適化 — 検索機能を維持したまま直列待ちと重複処理を削減する

## Overview

meiのprimingでChannel C/Fが最大約2.8秒を要している。検索クエリ、候補数、graph spreading、rerank、アクセス記録を削らず、同一処理の重複と同期I/Oの配置を修正する。

## Problem / Background

### Current State

- 2026-08-14 08:51の実測はC=2.735秒、F=2.758秒。
- embeddingは0.016〜0.063秒であり主因ではない。
- root MemoryServiceはnative vector操作を1 workerで直列実行する一方、C/F/C0は複数要求を並列発行する。`core/supervisor/memory_service.py:27`
- Fは同じepisode queryをprimary vector経路とgraph経路で二度検索する。`core/memory/retrieval/unified_search.py:941`
- Fの`skip_bm25_validation=True`でも全Markdownの同期検査が走る。`core/memory/bm25.py:620`
- 各queryが個別に`AccessBatch.flush()`を実行し、検索結果確定前にroot workerを占有する。`core/memory/retrieval/unified_search.py:390`
- C/Fは既存のretrieverを取得しても、新しいRAGMemorySearchへ注入せずgraph cacheを二重ロードする。`core/memory/priming/utils.py:118`

### Root Cause

1. `search_many()`が各`search()`に独立AccessBatchを作らせて同期flushする。`core/memory/retrieval/unified_search.py:762`
2. episodes scopeはprimary検索後に空vector groupを追加し、同一embeddingでgraph episodes検索を再実行する。`core/memory/retrieval/unified_search.py:960`
3. BM25 source同期が`validate_sources`と無関係に実行される。`core/memory/bm25.py:635`
4. `build_unified_searcher()`が共有retrieverをRAGMemorySearchへ渡さない。`core/memory/priming/utils.py:118`

## Decided Approach / 確定方針

検索機能を削らず、既存オブジェクトと既存結果を再利用する。AccessBatchは`search_many()`単位で共有してcollection単位に一括flushし、episode graph listはprimary検索のseed/vector結果を再利用して一回だけspreadingを行う。BM25は明示済みのvalidation skip契約にsource同期も合わせ、C/Fは同じretrieverを共有する。

### Rejected Alternatives

| Approach | Verdict |
|----------|---------|
| 短文でC/Fを省略 | **Rejected**: 短い指示でも記憶を想起する要件を壊す |
| root vector workerを複数化 | **Rejected**: native Chromaのsole-owner/repair規約を壊す |
| query結果TTL cache | **Rejected**: access/temporal scoreの無効化が複雑でhit率も低い |
| high-level検索全体をroot RPCへ移設 | **Rejected**: 今回の重複除去に対して変更範囲が大きすぎる |

### Key Decisions from Discussion

1. **C/Fの全クエリとrerankを維持** — 短文でも想起品質を落とさないため。
2. **アクセス記録の意味を維持** — collection単位の一括更新でもqueryごとのretrieved回数を合算する。
3. **Fのvector/graph両ranked listを維持** — RRFへの入力を削らず、共通seedだけ再利用する。
4. **計測ログを維持** — queue/vector/spreading/flush/BM25内訳を再計測可能にする。

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/retrieval/unified_search.py` | Modify | search_many共有AccessBatch、episode seed再利用、flush計測 |
| `core/memory/rag/retriever.py` | Modify | seed結果からspreadingする既存処理の再利用とphase計測 |
| `core/memory/rag_search.py` | Modify | episode graph検索へseedを渡せるようにする |
| `core/memory/bm25.py` | Modify | validation skip時のsource同期省略と内訳計測 |
| `core/memory/priming/utils.py` | Modify | cached retrieverをRAGMemorySearchへ注入 |
| `core/supervisor/memory_service.py` | Modify | queue待ちとnative実行時間の計測 |
| `tests/` | Modify | 結果同一性、呼出回数、一括access、skip契約、retriever共有を検証 |

### Edge Cases

| Case | Handling |
|------|----------|
| 単一query | 従来どおり一度検索し、一度flushする |
| query間で同じdocumentがhit | queryごとのaccess加算量を失わずcollection単位にまとめる |
| graph spreading失敗 | 従来どおりprimary結果へfallbackする |
| BM25 validation有効 | source同期を従来どおり実行する |
| BM25 validation無効 | index/deltaの既存内容を使い、全source scanを行わない |
| Neo4j backend | Legacy unified search変更の対象外で既存経路を維持する |

## Implementation Plan

### Phase 1: 計測と安全なI/O削減

1. MemoryService、retriever、flush、BM25のphaseログを追加する。
2. `validate_sources=False`時のBM25 source同期を省略する。
3. cached retrieverをC/FのRAGMemorySearchで共有する。

**Completion condition**: 検索結果を変えず、不要scanとgraph cache二重ロードが消える。

### Phase 2: 重複vectorとaccess flush統合

1. primary episode結果をgraph spreadingへ再利用する。
2. `search_many()`内でAccessBatchを共有し、全query後に一括flushする。
3. 結果とaccess counterの同値性テストを追加する。

**Completion condition**: Fのepisode vector store queryが一回になり、multi-queryのmetadata updateがcollection単位に集約される。

## Scope

### In Scope

- C/F priming Legacy backendの4最適化
- 計測ログ
- 単体・統合・性能回帰テスト

### Out of Scope

- C/Fチャネル、クエリ、候補、rerankの削減
- native vector workerの並列化
- Neo4j retrieval設計変更
- server再起動・本番反映

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| 一括flushでaccess加算回数が変わる | ranking学習値が変化 | pending updateをcollection/doc単位に正確に合算するテスト |
| seed再利用でgraph順位が変わる | F結果が変化 | vector/graph両listと既存score調整を保持する同値性テスト |
| validation skip中の外部直接編集を即時検出しない | index反映が次回同期まで遅れる | 呼出側が明示したskip契約時のみ省略し、通常検索は従来維持 |

## Acceptance Criteria

- [ ] C/Fのチャネル、build_queries、候補上限、rerank設定を変更しない。
- [ ] F一回の検索でepisode collectionへの同一vector queryを再発行しない。
- [ ] vector/graph両ranked listがRRFへ入力される。
- [ ] multi-query access記録はcollection単位にflushされ、queryごとの加算量を保持する。
- [ ] `validate_sources=False`ではsource同期を呼ばず、Trueでは呼ぶ。
- [ ] C/Fが同じcached retrieverを利用する。
- [ ] queue/vector/spreading/flush/BM25 phaseログが出力される。
- [ ] 関連unit/integration testsとruffが通る。

## References

- `core/memory/priming/channel_c.py:213` — Channel C検索
- `core/memory/priming/channel_f.py:82` — Channel F検索
- `core/memory/retrieval/unified_search.py:762` — multi-query検索
- `core/memory/rag/retriever.py:175` — dense retrievalとspreading
- `core/memory/bm25.py:620` — long-term BM25検索
- `/home/main/.animaworks/logs/animas/mei/20260814.log:31123` — 対象実測ログ
