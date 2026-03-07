# 予測誤差ベースの手続き再固定化 — 失敗駆動の手順自動修正

## Overview

手順に従って実行したタスクの失敗を「予測誤差」として検出し、手順の再評価・更新を自動トリガーする。脳科学の再固定化理論（Reconsolidation Theory）に基づき、失敗時にLLM Reflectionで原因分析を行い、手順の修正版を生成する。`20260218_procedural-memory-foundation.md`（基盤整備: 成功/失敗メタデータ）の完了を前提とする。

## Problem / Background

### Current State

- 手順の更新はエージェントが`write_memory_file`で**上書き**するのみ。フレームワークによる自動更新メカニズムがない
- 手順に従って実行したタスクが失敗しても、手順ファイル自体にフィードバックが反映されない
- バージョン管理がなく、変更履歴が追跡できない
- 古い・不正確な手順がいつまでも残り続ける

### Root Cause

1. **手順の更新トリガーが存在しない**: 失敗が発生しても手順の再評価が自動的に行われない
2. **バージョン管理の不在**: 上書きで古い内容が失われるため、何が変わったか追跡できない
3. **成功/失敗と手順の関連付けがない**: Issue 3で導入する成功/失敗メタデータを活用する仕組みが必要

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/consolidation.py` | Direct | 再固定化トリガー + LLM Reflection + 修正版生成 |
| `core/memory/manager.py` | Direct | バージョン管理メソッド追加 |
| `core/memory/activity.py` | Indirect | 再固定化イベントのログ記録 |

## Decided Approach / 確定方針

### Design Decision

確定: **予測誤差ベースの再固定化**。脳科学の再固定化理論に基づき、手順の失敗を「予測誤差」として検出する。失敗回数が閾値に達しconfidenceが低下した手順に対し、失敗エピソードと現行手順をLLM Reflectionに入力して失敗原因を分析し、修正版を自動生成する。旧バージョンはarchive/に退避し、新バージョンにversion++を付与する。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| 失敗のたびに即時修正 | 即時フィードバック | 1回の失敗で手順を変えるのは過剰反応。環境要因の失敗もある | **Rejected**: ノイズに敏感すぎる |
| エージェントの手動修正のみ | エージェントの判断に委ねる | エージェントが修正を忘れる/面倒がる | **Rejected**: 自動化できる部分を自動化すべき |
| **閾値ベースの再固定化トリガー (Adopted)** | ノイズ耐性があり自動 | 閾値の設定が必要 | **Adopted**: 再固定化理論の「強く訓練された記憶は変更されにくい」に一致 |

### Key Decisions from Discussion

1. **再固定化トリガー条件**: `failure_count >= 2` かつ `confidence < 0.6`。2回以上の失敗で初めてトリガー。1回の失敗では手順を変えない（ノイズ耐性）
2. **LLM Reflection入力**: 失敗エピソード（直近の失敗セッションの差分要約）+ 現行手順の全文 + 成功エピソード（もしあれば）
3. **バージョン管理**: 旧バージョンを`archive/procedure_versions/{name}_v{N}.md`に退避。新バージョンのfrontmatterに`version: N+1`、`previous_version: "archive/procedure_versions/{name}_v{N}.md"`を記録
4. **自動 vs 手動**: 再固定化は**日次固定化時に自動実行**。エージェントの介入なし
5. **Reflection後にfailure_countリセット**: 修正版生成後にfailure_count=0, success_count=0にリセット（新バージョンとして再スタート）

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/consolidation.py` | Modify | `_reconsolidate_procedures()` メソッド追加。日次固定化のステップとして組み込み |
| `core/memory/manager.py` | Modify | `archive_procedure_version()`, `update_procedure_version()` メソッド追加 |

#### Change 1: 再固定化ステージ

**Target**: `core/memory/consolidation.py` — `daily_consolidate()`

```python
# 日次固定化の最終ステップとして追加
async def _reconsolidate_procedures(self) -> list[Path]:
    """失敗が蓄積した手順の再固定化"""
    reconsolidated = []
    for proc_path in self._anima_dir.glob("procedures/*.md"):
        meta = self._memory.read_procedure_metadata(proc_path)
        failure_count = meta.get("failure_count", 0)
        confidence = meta.get("confidence", 0.5)

        if failure_count >= 2 and confidence < 0.6:
            # 再固定化トリガー
            failure_episodes = await self._collect_failure_episodes(proc_path)
            success_episodes = await self._collect_success_episodes(proc_path)
            current_content = self._memory.read_procedure_content(proc_path)

            revised = await self._reflect_and_revise(
                current_content, failure_episodes, success_episodes
            )
            if revised:
                self._memory.archive_procedure_version(proc_path)
                self._memory.update_procedure_version(proc_path, revised, meta)
                reconsolidated.append(proc_path)
    return reconsolidated
```

#### Change 2: LLM Reflectionプロンプト

```
以下の手順書に従ってタスクを実行しましたが、複数回失敗しました。
失敗の原因を分析し、手順書を修正してください。

【現行の手順書】
{current_procedure}

【失敗エピソード】
{failure_episodes}

【成功エピソード（参考）】
{success_episodes}

タスク:
1. 失敗の根本原因を特定してください
2. 手順書のどの部分に問題があるかを指摘してください
3. 修正版の手順書を出力してください

出力形式:
## 分析
(失敗原因と問題箇所の分析)

## 修正版手順書
(修正後の完全な手順書をMarkdown形式で出力)
```

#### Change 3: バージョン管理

**Target**: `core/memory/manager.py`

```python
def archive_procedure_version(self, path: Path) -> Path:
    """現行バージョンをarchiveに退避"""
    meta = self.read_procedure_metadata(path)
    version = meta.get("version", 1)
    archive_dir = self._anima_dir / "archive" / "procedure_versions"
    archive_dir.mkdir(parents=True, exist_ok=True)
    archive_path = archive_dir / f"{path.stem}_v{version}.md"
    shutil.copy2(path, archive_path)
    return archive_path

def update_procedure_version(self, path: Path, new_content: str, old_meta: dict) -> None:
    """修正版で上書き。version++, カウンタリセット"""
    new_meta = {
        **old_meta,
        "version": old_meta.get("version", 1) + 1,
        "success_count": 0,
        "failure_count": 0,
        "confidence": 0.5,  # リセット
        "last_used": None,
        "previous_version": f"archive/procedure_versions/{path.stem}_v{old_meta.get('version', 1)}.md",
    }
    self.write_procedure_with_meta(path, new_content, new_meta)
```

### Edge Cases

| Case | Handling |
|------|----------|
| 失敗が環境要因（API障害等）で手順自体に問題がない場合 | LLM Reflectionが「手順に問題なし」と判断した場合はスキップ。failure_countはリセットしない |
| LLM Reflectionが修正版を生成できない場合 | パース失敗時はスキップ、warningログ。次回の日次固定化で再試行 |
| 手順が一度も成功していない（success_count=0）場合 | 成功エピソードなしでReflection実行。新規手順のデバッグとして有用 |
| archive/のバージョンが大量に蓄積する場合 | 月次忘却（Issue 6）で古いarchiveを削除。直近5バージョンは保持 |
| confidence=0.6ちょうどの場合 | `<` なのでトリガーしない。`< 0.6` が条件 |
| 再固定化対象の手順が同時に複数ある場合 | 順次処理。1回の日次固定化で全対象を処理 |

## Implementation Plan

### Phase 1: 再固定化トリガー + LLM Reflection

| # | Task | Target |
|---|------|--------|
| 1-1 | `_reconsolidate_procedures()` メソッド実装（トリガー判定 + エピソード収集） | `core/memory/consolidation.py` |
| 1-2 | LLM Reflectionプロンプト + レスポンスパーサー実装 | `core/memory/consolidation.py` |
| 1-3 | Phase 1のユニットテスト | `tests/` |

**Completion condition**: 失敗が蓄積した手順に対してLLM Reflectionが実行され、修正版が生成される

### Phase 2: バージョン管理 + パイプライン統合

| # | Task | Target |
|---|------|--------|
| 2-1 | `archive_procedure_version()`, `update_procedure_version()` 実装 | `core/memory/manager.py` |
| 2-2 | `daily_consolidate()` への再固定化ステージ組み込み | `core/memory/consolidation.py` |
| 2-3 | 再固定化イベントのactivity_log記録（`procedure_reconsolidated` イベント） | `core/memory/consolidation.py` |
| 2-4 | Phase 2の統合テスト | `tests/` |

**Completion condition**: 日次固定化で再固定化が自動実行され、バージョン管理が動作する

## Scope

### In Scope

- 予測誤差ベースの再固定化トリガー（failure_count >= 2, confidence < 0.6）
- LLM Reflection（失敗原因分析 + 修正版生成）
- バージョン管理（archive退避 + version++）
- 日次固定化への統合
- activity_logへの再固定化イベント記録

### Out of Scope

- 成功/失敗メタデータの追跡 — 理由: Issue 3（基盤整備）で対応済み
- 手順の段階的最適化（Fittsモデル: 認知→連合→自律） — 理由: 将来拡張
- 手順のA/Bテスト（複数バージョンの並行評価） — 理由: 将来拡張
- skills/の再固定化 — 理由: skillsは短いスニペットであり、再固定化よりも手動更新が適切

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| LLM Reflectionが誤った修正を生成する | 手順の品質低下 | 旧バージョンをarchiveに保持。ロールバック可能 |
| 環境要因の失敗で不要な再固定化がトリガーされる | LLMコストの浪費 | LLM Reflectionが「手順に問題なし」と判断した場合はスキップ |
| 再固定化の頻度が高すぎる | 手順が安定しない | failure_count >= 2 の閾値でノイズ耐性を確保。再固定化後にカウンタリセット |

## Acceptance Criteria

- [ ] failure_count >= 2 かつ confidence < 0.6 の手順に対して再固定化がトリガーされる
- [ ] LLM Reflectionで失敗原因が分析され、修正版手順が生成される
- [ ] 旧バージョンが`archive/procedure_versions/`に退避される
- [ ] 新バージョンのfrontmatterにversion++, previous_versionが記録される
- [ ] 再固定化後にsuccess_count, failure_countがリセットされる
- [ ] 日次固定化の一部として自動実行される
- [ ] activity_logに`procedure_reconsolidated`イベントが記録される
- [ ] テストカバレッジ80%以上

## References

- `core/memory/consolidation.py:53-143` — `daily_consolidate()` メインフロー
- `20260218_procedural-memory-foundation.md` — 前提Issue（成功/失敗メタデータ）
- [Reconsolidation and the Dynamic Nature of Memory](https://pmc.ncbi.nlm.nih.gov/articles/PMC4588064/) — 再固定化理論
- [Memory Reconsolidation - Nature Reviews Neuroscience](https://www.nature.com/articles/nrn2090) — 予測誤差による脱安定化
- [Reflexion](https://arxiv.org/abs/2303.11366) — 言語的強化学習（失敗からの自己内省）
- [Mem^p](https://arxiv.org/abs/2508.06433) — Reflection-based adjustment（失敗時のインプレース更新）
- [ReMe](https://arxiv.org/abs/2512.10696) — 動的手続き記憶フレームワーク
