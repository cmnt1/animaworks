# 効用ベースの手続き記憶忘却 — PROTECTED解除と段階的アーカイブ

## Overview

手続き記憶（procedures/）の完全保護（PROTECTED_MEMORY_TYPES）を緩和し、効用スコアと使用頻度に基づく段階的忘却を導入する。forgetting.pyの既存3段階モデルに統合する。`20260218_procedural-memory-foundation.md`（基盤整備: メタデータ）と`20260218_procedural-memory-reconsolidation.md`（再固定化: 成功/失敗追跡の活用）の完了を前提とする。

## Problem / Background

### Current State

- `PROTECTED_MEMORY_TYPES = frozenset({"procedures", "skills", "shared_users"})` により、procedures/は忘却から**完全に保護**されている — `core/memory/forgetting.py:42-43`
- 低品質・古い・使われない手順が永久に蓄積する
- RAGインデックスのS/N比が時間とともに低下する
- 脳科学的にも手続き記憶は忘却される（宣言的記憶より緩やかだが）

### Root Cause

1. **完全保護の設計が過剰**: 手続き記憶を一切忘却しない設計は、長期運用で記憶の品質を劣化させる — `core/memory/forgetting.py:57-63`
2. **効用の定量化がない**: 手順の有用性を測る指標がないため、忘却の判断基準がない

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/forgetting.py` | Direct | PROTECTED_MEMORY_TYPESからprocedures除外、効用ベース忘却ロジック追加 |
| `core/memory/consolidation.py` | Indirect | 日次/週次/月次の忘却ステージでprocedures/が処理対象に |
| `core/memory/rag/indexer.py` | Indirect | 忘却されたproceduresのインデックス削除 |

## Decided Approach / 確定方針

### Design Decision

確定: **PROTECTED_MEMORY_TYPESからproceduresを除外し、効用ベースの段階的忘却を導入**。忘却判定は既存の3段階（ダウンスケーリング→再編→完全忘却）に統合するが、procedures専用の閾値（宣言的記憶より緩やか）を適用する。skills/とshared_users/は引き続き保護を維持する。`[IMPORTANT]` タグ付きやcore SOP（手動保護指定）は除外。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| 完全保護を維持 | 手順が失われない | 低品質手順の蓄積でS/N比低下。脳科学的にも不自然 | **Rejected**: 長期運用で品質劣化 |
| 時間ベースのみで忘却 | シンプル | 使用頻度の高い古い手順まで忘却される | **Rejected**: 効用を無視した忘却は有害 |
| **効用ベースの段階的忘却 (Adopted)** | 使用実績に基づく適切な判断 | 成功/失敗メタデータが前提 | **Adopted**: ReMe/ExPeLの知見に基づく効用ベース管理 |
| skills/も保護解除 | 統一的な管理 | skillsはdescription-basedマッチングの起点。削除すると想起経路が断たれる | **Rejected**: skillsは保護を維持 |

### Key Decisions from Discussion

1. **PROTECTED_MEMORY_TYPES変更**: `{"procedures", "skills", "shared_users"}` → `{"skills", "shared_users"}`。proceduresのみ保護解除
2. **procedures専用の忘却閾値（宣言的記憶より緩やか）**:
   - ダウンスケーリング: `last_used`から180日超 + `success_count + failure_count < 3`（knowledgeの90日/3回より緩い）
   - 完全忘却: 低活性マーク後60日アクセスなし（knowledgeと同じ）
3. **効用スコアの計算**: `utility = success_count / max(1, success_count + failure_count)`
4. **効用ベースの追加忘却条件**: `utility < 0.3` かつ `failure_count >= 3` → 即時低活性マーク（失敗の多い手順は早期にアーカイブ対象）
5. **保護例外**:
   - `[IMPORTANT]` タグ付き → 忘却耐性
   - frontmatterに `protected: true` → 手動保護指定
   - `version >= 3` → 再固定化を経て成熟した手順は保護
6. **archive/procedure_versions/のクリーンアップ**: 月次忘却時に直近5バージョン以外のアーカイブを削除

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/forgetting.py` | Modify | PROTECTED_MEMORY_TYPES変更、`_is_protected_procedure()`追加、procedures専用閾値 |
| `core/memory/consolidation.py` | Modify | 月次忘却にarchiveクリーンアップ追加 |

#### Change 1: PROTECTED_MEMORY_TYPES変更

**Target**: `core/memory/forgetting.py:42-43`

```python
# Before
PROTECTED_MEMORY_TYPES = frozenset({"procedures", "skills", "shared_users"})

# After
PROTECTED_MEMORY_TYPES = frozenset({"skills", "shared_users"})
```

#### Change 2: procedures専用の保護判定

**Target**: `core/memory/forgetting.py`

```python
def _is_protected(self, metadata: dict) -> bool:
    if metadata.get("memory_type") in PROTECTED_MEMORY_TYPES:
        return True
    if metadata.get("importance") == "important":
        return True
    # procedures専用の保護例外
    if metadata.get("memory_type") == "procedures":
        return self._is_protected_procedure(metadata)
    return False

def _is_protected_procedure(self, metadata: dict) -> bool:
    """procedures固有の保護判定"""
    # [IMPORTANT]タグ付き
    if metadata.get("importance") == "important":
        return True
    # 手動保護指定
    if metadata.get("protected") is True:
        return True
    # 再固定化を経て成熟した手順（version >= 3）
    if metadata.get("version", 1) >= 3:
        return True
    return False
```

#### Change 3: procedures専用の忘却閾値

**Target**: `core/memory/forgetting.py` — Stage 1 (Synaptic Downscaling)

```python
# procedures用の閾値
PROCEDURE_INACTIVITY_DAYS = 180  # knowledge の 90日 より緩い
PROCEDURE_MIN_USAGE = 3          # success_count + failure_count の最小値
PROCEDURE_LOW_UTILITY_THRESHOLD = 0.3
PROCEDURE_LOW_UTILITY_MIN_FAILURES = 3

async def _should_downscale_procedure(self, metadata: dict) -> bool:
    """procedures専用のダウンスケーリング判定"""
    last_used = metadata.get("last_used") or metadata.get("updated_at", "")
    days_since = self._days_since(last_used)
    total_usage = metadata.get("success_count", 0) + metadata.get("failure_count", 0)

    # 長期未使用 + 低使用回数
    if days_since > PROCEDURE_INACTIVITY_DAYS and total_usage < PROCEDURE_MIN_USAGE:
        return True

    # 高失敗率（効用スコア低い）
    if metadata.get("failure_count", 0) >= PROCEDURE_LOW_UTILITY_MIN_FAILURES:
        utility = metadata.get("success_count", 0) / max(1, total_usage)
        if utility < PROCEDURE_LOW_UTILITY_THRESHOLD:
            return True

    return False
```

### Edge Cases

| Case | Handling |
|------|----------|
| 再固定化（Issue 5）でversion++されたばかりの手順 | failure_count=0にリセットされているため忘却条件に該当しない |
| version >= 3 だが長期未使用の手順 | version >= 3 は保護対象。再固定化を3回以上経た成熟手順は忘却しない |
| `[IMPORTANT]`タグと低効用が両立する場合 | `[IMPORTANT]`が優先。忘却されない |
| archive/procedure_versions/の削除で必要なバージョンが消える場合 | 直近5バージョンは常に保持 |
| procedures/の全ファイルが忘却対象になる場合 | 最低1ファイルは保持（完全空にはしない）する安全弁は不要。空になっても正常動作 |
| forgetting.pyのStage 2（神経新生再編）でprocedures同士がマージされる場合 | 既存の類似ペアマージロジックがそのまま適用される。マージ後のprocedureにはマージ元のmetadataを統合 |

## Implementation Plan

### Phase 1: PROTECTED解除 + 閾値設定

| # | Task | Target |
|---|------|--------|
| 1-1 | PROTECTED_MEMORY_TYPESからprocedures除外 | `core/memory/forgetting.py` |
| 1-2 | `_is_protected_procedure()` 実装（version, protected, IMPORTANT） | `core/memory/forgetting.py` |
| 1-3 | `_should_downscale_procedure()` 実装（180日/3回/低効用） | `core/memory/forgetting.py` |
| 1-4 | Phase 1のユニットテスト | `tests/` |

**Completion condition**: procedures/が忘却対象になり、保護例外が正しく動作する

### Phase 2: 統合 + クリーンアップ

| # | Task | Target |
|---|------|--------|
| 2-1 | Stage 1-3の既存コードにprocedures専用パスを追加 | `core/memory/forgetting.py` |
| 2-2 | archive/procedure_versions/のクリーンアップ（月次、直近5保持） | `core/memory/consolidation.py` |
| 2-3 | Phase 2の統合テスト（日次→週次→月次の全ステージ） | `tests/` |

**Completion condition**: procedures/の忘却が既存3段階モデルに統合され、archiveクリーンアップが動作する

## Scope

### In Scope

- PROTECTED_MEMORY_TYPESからprocedures除外
- procedures専用の保護例外（IMPORTANT, protected: true, version >= 3）
- procedures専用の忘却閾値（180日/3回、効用 < 0.3）
- forgetting.pyの既存3段階への統合
- archive/procedure_versions/のクリーンアップ

### Out of Scope

- skills/の保護解除 — 理由: description-basedマッチングの起点であり、削除すると想起経路断絶
- shared_users/の保護解除 — 理由: 対人記憶は長期保持が必要
- 忘却閾値の動的調整 — 理由: 将来拡張。現時点では固定値で十分
- common_skills/の忘却 — 理由: 管理者配置の共通スキルは手動管理

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| 有用な手順が誤って忘却される | 手順の喪失 | archiveに退避（完全削除ではない）。version >= 3の保護。[IMPORTANT]タグ |
| 忘却閾値が厳しすぎて大量の手順がアーカイブされる | 手順の急激な減少 | 180日の緩い閾値。使用回数3回未満かつ未使用期間の複合条件 |
| 効用スコアの計算が不正確（成功/失敗の検出精度に依存） | 誤った忘却判定 | Issue 3のエージェント明示報告を優先することで精度向上 |

## Acceptance Criteria

- [ ] procedures/がPROTECTED_MEMORY_TYPESから除外されている
- [ ] `[IMPORTANT]`タグ付き、`protected: true`、`version >= 3` の手順が忘却から保護される
- [ ] `last_used`から180日超 + 使用回数3回未満の手順がダウンスケーリングされる
- [ ] 効用スコア < 0.3 かつ failure_count >= 3 の手順が即時低活性マークされる
- [ ] 低活性マーク後60日アクセスなしの手順がアーカイブ（完全忘却）される
- [ ] archive/procedure_versions/の直近5バージョン以外が月次で削除される
- [ ] skills/とshared_users/は引き続き保護されている
- [ ] テストカバレッジ80%以上

## References

- `core/memory/forgetting.py:42-43` — `PROTECTED_MEMORY_TYPES` 定義
- `core/memory/forgetting.py:57-63` — `_is_protected()` 保護判定
- `core/memory/forgetting.py:91-177` — Stage 1: Synaptic Downscaling
- `core/memory/forgetting.py:180-307` — Stage 2: Neurogenesis Reorganization
- `core/memory/forgetting.py:392-490` — Stage 3: Complete Forgetting
- `20260218_procedural-memory-foundation.md` — 前提Issue（メタデータ基盤）
- `20260218_procedural-memory-reconsolidation.md` — 前提Issue（成功/失敗追跡の活用）
- [ReMe](https://arxiv.org/abs/2512.10696) — Utility-based Refinement（効用ベース自動剪定）
- [ExpeL](https://arxiv.org/abs/2308.10144) — 洞察の投票システム（UPVOTE/DOWNVOTE）
- [Synaptic Homeostasis Hypothesis](https://en.wikipedia.org/wiki/Synaptic_homeostasis_hypothesis) — シナプスホメオスタシス仮説（Tononi & Cirelli, 2003）
