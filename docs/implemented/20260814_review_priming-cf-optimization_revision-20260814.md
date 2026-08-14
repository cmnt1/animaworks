# Code Review: C/F priming最適化 - Revision Required

**Review Date**: 2026-08-14
**Original Issue**: `docs/issues/20260814_priming-cf-optimization.md`
**Worktree**: `/home/main/dev/animaworks-issue-20260814-priming-cf-optimization`
**Status**: ❌ REVISION REQUIRED

## Summary

4最適化の基本実装と関連テストは成功したが、cold-start raceとspreading重複が残る。access flushも一括化のみで同期クリティカルパスとstale overwrite riskが残るため、root sole-workerでの原子的遅延更新へ改修する。

## Review Findings

### 1. Issue Requirement Alignment

**Status**: ⚠️ PARTIAL

- ✅ BM25 validation skipは実装済み。
- ✅ episode vector queryは1回になった。
- ❌ spreadingはprimary/graphで2回実行される。
- ❌ C/F cached retriever共有はcold-start raceで保証されない。
- ⚠️ access flushはcollection単位に統合されたが同期経路に残る。

### 2. Test Coverage

**Status**: ⚠️ PARTIAL

- 関連148テスト成功、memory全体2685 passed / 19 skipped。
- E2E 2件成功。
- repo coverage checkerは既存設定との非互換で0%を返し測定不能。
- cold-start concurrency、spreading回数、root deferred access更新のテストが不足。

### 3. Code Quality / Regression

**Status**: ⚠️ PARTIAL

- public APIの既存引数は維持。
- `AccessBatch.absorb()`はquery内score overlay分離を保つ。
- absolute metadata patchの遅延flushは別channel更新を上書きし得る。

### 4. Independent Reviews

- Cursor Agent: Failed（プロセス終了、stdout/logとも空）
- Codex reviewer: Completed、High 2件・Medium 2件

## Priority Changes

### High

1. `RetrieverCache.get_or_create()`をlockでsingle-flight化し、並行cold-startテストを追加する。
2. primaryで生成済みのexpanded episode listをgraph ranked listへ再利用し、spreadingを一回にする。

### Medium

1. access更新をroot sole-workerへ非同期委譲し、応答クリティカルパスから外す。
2. root側で現在metadataを読み、deltaを原子的に加算してchannel間のstale overwriteを防ぐ。

## Next Steps

Iteration 2で全High/Mediumを実装し、関連・memory全体・E2Eを再実行して再レビューする。
