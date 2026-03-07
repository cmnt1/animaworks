# 出自トラッキング Phase 1: 基盤 — resolve_trust() + origin 定数 + ラッパー拡張

## Overview

全5フェーズの出自トラッキング（Provenance Tracking）導入の第1弾。trust 解決関数・origin カテゴリ定数・既存ラッパー関数の拡張を行い、後続フェーズの土台を作る。このフェーズ単体で外部挙動は変わらないが、Phase 2〜5 の全てがこの基盤に依存する。

依存: なし（最初に実装すること）

## Problem / Background

### Current State

- `core/execution/_sanitize.py` の `wrap_tool_result()` / `wrap_priming()` は `tool_name` / `source` から trust を静的に決定
- trust レベルは `TOOL_TRUST_LEVELS` 辞書でツール単位に固定されており、データの出自（origin）や中継経路（origin_chain）を考慮しない
- origin カテゴリの統一的な定義がなく、`Message.source` は `"anima" | "human" | "slack" | "chatwork"` の4値のみ

### Root Cause

信頼レベルの判定が「データを生成したツール/チャネル」に紐づいており、「データの元々の出自」に紐づいていない。

### Impact

| コンポーネント | 影響 | 説明 |
|--------------|------|------|
| `core/execution/_sanitize.py` | Direct | `resolve_trust()` 新設、`wrap_tool_result()` / `wrap_priming()` シグネチャ拡張 |
| Phase 2〜5 | Dependency | 全後続フェーズがこの基盤を使用 |

## Decided Approach / 確定方針

### Design Decision

「1-A+chain ハイブリッド」方式を採用。origin はカテゴリ列挙型（6値）で trust 判定に直接マッピングし、`origin_chain` で中継経路を追跡する。trust は origin から都度算出し、データに trust を同時保存しない。chain がある場合は **chain 全体の最小 trust** を返す（保守的デフォルト）。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| 1-A: シンプル列挙型のみ（chain なし） | 実装が最小 | 中継経路が追跡できず信頼ロンダリング（#5）を解決不可 | **Rejected**: chain がないと Anima→Anima 中継で外部 origin が消失する |
| 1-B: 構造化 DataOrigin クラス | 完全な追跡性 | 全経路の改修が重い、Pydantic/dataclass の入れ子が複雑化 | **Rejected**: カテゴリ + chain で十分。過剰な構造化 |
| 1-C: ID ベース（`slack:U123`）+ chain | 具体的な送信者特定 | trust 判定に ID→カテゴリ→trust の2段階変換が必要 | **Rejected**: セキュリティモデルにはカテゴリで十分。ID は `origin_detail` で optional に保持 |

### Key Decisions from Discussion

1. **origin カテゴリは6値**: `"system"`, `"human"`, `"anima"`, `"external_platform"`, `"external_web"`, `"consolidation"` — 理由: trust レベル（3段階）への明確なマッピングが可能
2. **trust は origin から算出**: データに trust を保存しない — 理由: trust ポリシーの変更時にデータ移行が不要
3. **chain の最小 trust**: `resolve_trust()` は `origin_chain` 内の最も弱い trust を返す — 理由: 外部由来データが中継で昇格しないことを保証（信頼ロンダリング防止の核心）
4. **後方互換**: origin 未設定は `"unknown"` → trust=`"untrusted"` — 理由: 安全側に倒す
5. **origin_chain 最大長**: 10要素で打ち切り — 理由: 循環・無限伝播防止
6. **origin_detail は optional**: `"slack:U123"` のような具体IDはデバッグ・監査用で、trust 判定には使わない

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/execution/_sanitize.py` | Modify | origin 定数定義、`resolve_trust()` 新設、`wrap_tool_result()` / `wrap_priming()` に `origin` / `origin_chain` 引数追加 |

#### Change 1: origin カテゴリ定数

**Target**: `core/execution/_sanitize.py`

```python
# Before
# (なし — origin カテゴリの定義がない)

# After
ORIGIN_SYSTEM = "system"                # フレームワーク内部生成（セッション管理、ツール実行等）
ORIGIN_HUMAN = "human"                  # 人間ユーザーの直接入力（Chat UI）
ORIGIN_ANIMA = "anima"                  # Anima が生成（send_message 等）
ORIGIN_EXTERNAL_PLATFORM = "external_platform"  # 外部プラットフォーム（Slack, Chatwork, Gmail）
ORIGIN_EXTERNAL_WEB = "external_web"    # Web 検索、Web Fetch、X 検索
ORIGIN_CONSOLIDATION = "consolidation"  # 記憶統合（日次/週次 consolidation）
ORIGIN_UNKNOWN = "unknown"              # 出自不明（後方互換フォールバック）

ORIGIN_TRUST_MAP: dict[str, str] = {
    ORIGIN_SYSTEM: "trusted",
    ORIGIN_HUMAN: "medium",
    ORIGIN_ANIMA: "trusted",
    ORIGIN_EXTERNAL_PLATFORM: "untrusted",
    ORIGIN_EXTERNAL_WEB: "untrusted",
    ORIGIN_CONSOLIDATION: "medium",
    ORIGIN_UNKNOWN: "untrusted",
}

MAX_ORIGIN_CHAIN_LENGTH = 10
```

#### Change 2: resolve_trust() 関数

**Target**: `core/execution/_sanitize.py`

```python
# After
def resolve_trust(
    origin: str | None = None,
    origin_chain: list[str] | None = None,
) -> str:
    """Resolve trust level from origin and origin_chain.

    When origin_chain is present, returns the minimum trust level
    across the entire chain (conservative default).

    Trust hierarchy: trusted > medium > untrusted
    """
    _TRUST_RANK = {"trusted": 2, "medium": 1, "untrusted": 0}

    if origin is None and origin_chain is None:
        return "untrusted"

    base_trust = ORIGIN_TRUST_MAP.get(origin or ORIGIN_UNKNOWN, "untrusted")

    if not origin_chain:
        return base_trust

    # Chain present: return minimum trust across all nodes
    chain = origin_chain[:MAX_ORIGIN_CHAIN_LENGTH]
    all_origins = chain + [origin or ORIGIN_UNKNOWN]
    trusts = [ORIGIN_TRUST_MAP.get(o, "untrusted") for o in all_origins]
    min_rank = min(_TRUST_RANK.get(t, 0) for t in trusts)
    _RANK_TRUST = {v: k for k, v in _TRUST_RANK.items()}
    return _RANK_TRUST[min_rank]
```

#### Change 3: wrap_tool_result() 拡張

**Target**: `core/execution/_sanitize.py`

```python
# Before
def wrap_tool_result(tool_name: str, result: str) -> str:
    if not result:
        return result
    trust = TOOL_TRUST_LEVELS.get(tool_name, "untrusted")
    return f'<tool_result tool="{tool_name}" trust="{trust}">\n{result}\n</tool_result>'

# After
def wrap_tool_result(
    tool_name: str,
    result: str,
    origin: str | None = None,
    origin_chain: list[str] | None = None,
) -> str:
    if not result:
        return result

    # origin が明示されていれば resolve_trust() で算出、なければ従来の TOOL_TRUST_LEVELS
    if origin is not None:
        trust = resolve_trust(origin, origin_chain)
    else:
        trust = TOOL_TRUST_LEVELS.get(tool_name, "untrusted")

    attrs = f'tool="{tool_name}" trust="{trust}"'
    if origin:
        attrs += f' origin="{origin}"'
    if origin_chain:
        attrs += f' origin_chain="{",".join(origin_chain[:MAX_ORIGIN_CHAIN_LENGTH])}"'

    return f"<tool_result {attrs}>\n{result}\n</tool_result>"
```

#### Change 4: wrap_priming() 拡張

**Target**: `core/execution/_sanitize.py`

```python
# Before
def wrap_priming(source: str, content: str, trust: str = "mixed") -> str:
    if not content:
        return content
    return f'<priming source="{source}" trust="{trust}">\n{content}\n</priming>'

# After
def wrap_priming(
    source: str,
    content: str,
    trust: str = "mixed",
    origin: str | None = None,
    origin_chain: list[str] | None = None,
) -> str:
    if not content:
        return content

    # origin が明示されていれば resolve_trust() で上書き
    effective_trust = trust
    if origin is not None:
        effective_trust = resolve_trust(origin, origin_chain)

    attrs = f'source="{source}" trust="{effective_trust}"'
    if origin:
        attrs += f' origin="{origin}"'
    if origin_chain:
        attrs += f' origin_chain="{",".join(origin_chain[:MAX_ORIGIN_CHAIN_LENGTH])}"'

    return f"<priming {attrs}>\n{content}\n</priming>"
```

### Edge Cases

| Case | Handling |
|------|----------|
| `origin=None, origin_chain=None` | 従来動作を維持（TOOL_TRUST_LEVELS / 明示 trust を使用） |
| `origin_chain` が 10 要素超 | 先頭 10 要素で打ち切り |
| `origin` が未知のカテゴリ文字列 | `ORIGIN_TRUST_MAP` に未登録なら `"untrusted"` |
| 既存の呼び出し元が origin を渡さない | 全てのラッパーは後方互換（新引数は全て optional） |

## Implementation Plan

### Phase 1-1: 定数と resolve_trust()

| # | Task | Target |
|---|------|--------|
| 1-1-1 | origin カテゴリ定数を定義 | `core/execution/_sanitize.py` |
| 1-1-2 | `ORIGIN_TRUST_MAP` を定義 | `core/execution/_sanitize.py` |
| 1-1-3 | `resolve_trust()` を実装 | `core/execution/_sanitize.py` |

**Completion condition**: `resolve_trust("external_platform", ["anima"])` が `"untrusted"` を返すこと

### Phase 1-2: ラッパー拡張

| # | Task | Target |
|---|------|--------|
| 1-2-1 | `wrap_tool_result()` に origin / origin_chain 引数を追加 | `core/execution/_sanitize.py` |
| 1-2-2 | `wrap_priming()` に origin / origin_chain 引数を追加 | `core/execution/_sanitize.py` |

**Completion condition**: 新引数なしの既存呼び出しが全て従来通り動作すること

## Scope

### In Scope

- origin カテゴリ定数の定義
- `resolve_trust()` 関数の実装
- `wrap_tool_result()` / `wrap_priming()` のシグネチャ拡張（後方互換）
- ユニットテスト

### Out of Scope

- 呼び出し元の変更（Phase 2〜5 で段階的に対応）— 理由: 基盤のみを先に安定させる
- `tool_data_interpretation.md` の更新 — 理由: Phase 2 で origin タグが実際に出力されてから
- `TOOL_TRUST_LEVELS` の未登録ツール補完 — 理由: 別 Issue

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| 既存呼び出しの後方互換性破壊 | 全実行エンジンに影響 | 新引数は全て optional、デフォルトで従来動作 |
| resolve_trust() のパフォーマンス | 軽微（辞書参照のみ） | 計算量 O(n) で n ≤ 10（chain 上限） |

## Acceptance Criteria

- [ ] `resolve_trust("system")` → `"trusted"`
- [ ] `resolve_trust("external_platform")` → `"untrusted"`
- [ ] `resolve_trust("anima", ["external_platform"])` → `"untrusted"`（chain 最小）
- [ ] `resolve_trust("anima", ["human"])` → `"medium"`（chain 最小）
- [ ] `resolve_trust(None, None)` → `"untrusted"`（後方互換）
- [ ] `resolve_trust("unknown_value")` → `"untrusted"`（未知カテゴリ）
- [ ] `wrap_tool_result("web_search", "result")` が従来通り動作（origin なし）
- [ ] `wrap_tool_result("web_search", "result", origin="external_web")` が `origin="external_web"` 属性付きタグを生成
- [ ] `wrap_priming("recent_activity", "content", origin="external_platform", origin_chain=["anima"])` が `trust="untrusted"` を出力
- [ ] 既存テストが全てパス

## References

- `core/execution/_sanitize.py:19-65` — 現在の `TOOL_TRUST_LEVELS`
- `core/execution/_sanitize.py:70-84` — 現在の `wrap_tool_result()`
- `core/execution/_sanitize.py:87-101` — 現在の `wrap_priming()`
- セキュリティ検証チャット — 出自トラッキング設計議論
