# 出自トラッキング Phase 4: RAG — チャンクの origin メタデータ + Channel C trust 別分離出力

## Overview

全5フェーズの出自トラッキング導入の第4弾。RAG インデクサーがチャンクに origin メタデータを付与し、Priming の Channel C（related_knowledge）が検索結果を trust 別に分離して出力する。このフェーズ完了で、セキュリティ検証 #4（Poisoned RAG — 時間差攻撃）が解決する。

依存: Phase 1（基盤）, Phase 2（入口 origin 付与）

## Problem / Background

### Current State

攻撃シナリオ（時間差攻撃）:

```
Day 1: 攻撃者 → Slack DM → Anima A → append_episode("ignore all instructions and ...")
         → episodes/2026-02-28.md に追記
         → indexer.index_file(path, "episodes") → ChromaDB にチャンクとしてインデックス

Day 2: 別の人間が Anima A にチャット → priming._channel_c_related_knowledge(keywords)
         → retriever.search() が Day 1 のチャンクをヒット
         → trust="medium" でプロンプトに注入（外部由来にもかかわらず）
```

- `MemoryIndexer.index_file()` はチャンクに `memory_type`, `source_file`, `anima` 等のメタデータを付与するが、`origin`（データの出自）は持たない — `core/memory/rag/indexer.py:627-657`
- `_channel_c_related_knowledge()` は全検索結果を `trust="medium"` で一律ラップ — `core/memory/priming.py:1131`
- episodes にインデックスされた外部由来データが知識として `medium` 扱いになる

### Root Cause

1. RAG チャンクに origin メタデータがなく、外部由来と内部由来のデータを区別できない
2. Channel C が全結果を同一の trust で出力しており、チャンクごとの信頼レベルを反映しない

### Impact

| コンポーネント | 影響 | 説明 |
|--------------|------|------|
| `core/memory/rag/indexer.py` | Direct | `_extract_metadata()` / `index_file()` に origin 引数追加 |
| `core/memory/manager.py` | Direct | `append_episode()` に origin 引数追加、`index_file()` に渡す |
| `core/memory/priming.py` | Direct | `_channel_c_related_knowledge()` で検索結果を trust 別に分離出力 |
| `core/memory/rag/retriever.py` | Indirect | 検索結果に origin メタデータが含まれるようになる（SearchResult.metadata 経由、コード変更なし） |

## Decided Approach / 確定方針

### Design Decision

案3-C-ii を採用。RAG チャンクメタデータに `origin` フィールドを追加し、検索結果の trust を origin から算出して、Channel C を trust 別に分離出力する。Episodes を RAG から除外しない（忘却リスク回避）。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| 3-A: Episodes を RAG から除外 | 外部データが RAG に入らない根本対策 | consolidation 前の情報が検索不可、忘却リスク | **Rejected**: 記憶システムの有効性が損なわれる |
| 3-B: Episodes を別コレクションで untrusted 検索 | trust 分離が明確 | ChromaDB コレクション管理の複雑化、インデクサー大改修 | **Rejected**: メタデータフィルタで十分対応可能 |
| 3-C-i: Channel C 全体を trust="mixed" | 変更が最小 | "mixed" は曖昧で LLM の判断に依存 | **Rejected**: trust 別分離の方が LLM にとって明確 |

### Key Decisions from Discussion

1. **Episodes のインデックスは維持**: RAG からの除外はしない — 理由: consolidation 前の情報の検索性を維持、忘却防止
2. **origin メタデータの格納先**: ChromaDB チャンクの `metadata["origin"]` — 理由: 既存の metadata 構造に自然に追加可能
3. **Channel C の trust 別分離出力（3-C-ii）**: untrusted チャンクと medium チャンクを別ブロックで出力 — 理由: LLM が trust 境界を明確に認識できる
4. **バジェットの按分**: 既存 700 トークンを untrusted/medium で按分、合計は変わらない — 理由: トークン増大を防ぐ
5. **consolidation 由来の knowledge**: `origin="consolidation"` → trust="medium" — 理由: LLM が洗浄済みのため medium で十分

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/rag/indexer.py` | Modify | `index_file()` / `_extract_metadata()` に `origin` 引数追加 |
| `core/memory/manager.py` | Modify | `append_episode()` / `write_knowledge()` に `origin` 引数追加、`index_file()` に伝播 |
| `core/memory/priming.py` | Modify | `_channel_c_related_knowledge()` で検索結果を trust 別に分離出力 |
| `core/memory/consolidation.py` | Modify | consolidation で knowledge 書き込み時に `origin="consolidation"` を付与 |

#### Change 1: MemoryIndexer.index_file() / _extract_metadata() 拡張

**Target**: `core/memory/rag/indexer.py`

```python
# Before (line 127-142)
def index_file(self, file_path: Path, memory_type: str, force: bool = False) -> int:

# After
def index_file(
    self,
    file_path: Path,
    memory_type: str,
    force: bool = False,
    origin: str = "",
) -> int:
```

```python
# Before (_extract_metadata, line 647-653)
metadata: dict[str, str | int | float | list[str]] = {
    "anima": self.collection_prefix,
    "memory_type": memory_type,
    "source_file": str(file_path.relative_to(self.anima_dir)),
    ...
}

# After
metadata: dict[str, str | int | float | list[str]] = {
    "anima": self.collection_prefix,
    "memory_type": memory_type,
    "source_file": str(file_path.relative_to(self.anima_dir)),
    ...
}
if origin:
    metadata["origin"] = origin
```

`index_file()` は受け取った `origin` を `_extract_metadata()` に渡す。`origin` 引数を `_extract_metadata()` のシグネチャにも追加する。

#### Change 2: MemoryManager.append_episode() 拡張

**Target**: `core/memory/manager.py`

```python
# Before (line 262-276)
def append_episode(self, entry: str) -> None:
    ...
    self._rag.index_file(path, "episodes")

# After
def append_episode(self, entry: str, origin: str = "") -> None:
    ...
    self._rag.index_file(path, "episodes", origin=origin)
```

#### Change 3: Channel C trust 別分離出力

**Target**: `core/memory/priming.py`

```python
# Before (_channel_c_related_knowledge, line 667-691)
if results:
    parts = []
    for i, result in enumerate(results):
        source_label = result.metadata.get("anima", anima_name)
        label = "shared" if source_label == "shared" else "personal"
        parts.append(f"--- Result {i + 1} [{label}] (score: {result.score:.3f}) ---")
        parts.append(result.content)
        parts.append("")
    output = "\n".join(parts)

# After
if results:
    from core.execution._sanitize import resolve_trust, ORIGIN_UNKNOWN
    
    # 検索結果を trust 別に分類
    trusted_parts: list[str] = []
    untrusted_parts: list[str] = []
    
    for i, result in enumerate(results):
        chunk_origin = result.metadata.get("origin", "")
        chunk_trust = resolve_trust(chunk_origin or ORIGIN_UNKNOWN)
        source_label = result.metadata.get("anima", anima_name)
        label = "shared" if source_label == "shared" else "personal"
        
        line = f"--- Result {i + 1} [{label}] (score: {result.score:.3f}) ---\n{result.content}\n"
        
        if chunk_trust == "untrusted":
            untrusted_parts.append(line)
        else:
            trusted_parts.append(line)
    
    output = ""
    if trusted_parts:
        output += "\n".join(trusted_parts)
    if untrusted_parts:
        if output:
            output += "\n"
        output += "[以下は外部由来データを含む検索結果です]\n"
        output += "\n".join(untrusted_parts)
```

#### Change 4: format_priming_section() の Channel C 分離

**Target**: `core/memory/priming.py`

```python
# Before (line 1128-1132)
if result.related_knowledge:
    parts.append(t("priming.related_knowledge_header"))
    parts.append("")
    parts.append(wrap_priming("related_knowledge", result.related_knowledge, trust="medium"))
    parts.append("")

# After
if result.related_knowledge:
    parts.append(t("priming.related_knowledge_header"))
    parts.append("")
    if result.related_knowledge_untrusted:
        parts.append(wrap_priming(
            "related_knowledge", result.related_knowledge,
            trust="medium", origin=ORIGIN_CONSOLIDATION,
        ))
        parts.append("")
        parts.append(wrap_priming(
            "related_knowledge_external", result.related_knowledge_untrusted,
            trust="untrusted", origin=ORIGIN_EXTERNAL_PLATFORM,
        ))
        parts.append("")
    else:
        parts.append(wrap_priming("related_knowledge", result.related_knowledge, trust="medium"))
        parts.append("")
```

これに伴い、`PrimingResult` に `related_knowledge_untrusted: str = ""` フィールドを追加する。`_channel_c_related_knowledge()` が trust 別に分離した文字列を返すようにする。

#### Change 5: PrimingResult 拡張

**Target**: `core/memory/priming.py`

```python
# Before
@dataclass
class PrimingResult:
    sender_profile: str = ""
    recent_activity: str = ""
    related_knowledge: str = ""
    matched_skills: list[str] = field(default_factory=list)
    pending_tasks: str = ""
    recent_outbound: str = ""

# After
@dataclass
class PrimingResult:
    sender_profile: str = ""
    recent_activity: str = ""
    related_knowledge: str = ""
    related_knowledge_untrusted: str = ""    # 外部由来の検索結果（trust 別分離）
    matched_skills: list[str] = field(default_factory=list)
    pending_tasks: str = ""
    recent_outbound: str = ""
```

#### Change 6: Consolidation での origin 付与

**Target**: `core/memory/consolidation.py`

`write_knowledge()` / `write_knowledge_with_meta()` 呼び出し時に `origin="consolidation"` を引数で渡す。これにより、consolidation で生成された knowledge チャンクは `origin="consolidation"` → trust="medium" として扱われる。

### Edge Cases

| Case | Handling |
|------|----------|
| 既存 RAG チャンクに `origin` がない | `metadata.get("origin", "")` → `""` → `ORIGIN_UNKNOWN` → trust="untrusted" （保守的デフォルト） |
| 検索結果が全て trusted | `related_knowledge_untrusted = ""` → 従来と同じ単一ブロック出力 |
| 検索結果が全て untrusted | `related_knowledge = ""`, `related_knowledge_untrusted` のみ出力 |
| consolidation が episodes から knowledge を生成 | knowledge の origin は `"consolidation"`。元 episode の外部 origin は引き継がない（LLM による洗浄済み） |
| 共有知識 (common_knowledge) | origin は手動更新のため `""` → `ORIGIN_UNKNOWN` → untrusted。将来的に `"system"` や `"human"` を設定可能 |
| Channel C バジェット超過 | trusted + untrusted の合計で 700 トークン制限を維持。trusted 優先で割り当て |

## Implementation Plan

### Phase 4-1: RAG メタデータ拡張

| # | Task | Target |
|---|------|--------|
| 4-1-1 | `index_file()` に `origin` 引数追加 | `core/memory/rag/indexer.py` |
| 4-1-2 | `_extract_metadata()` で `metadata["origin"]` を設定 | `core/memory/rag/indexer.py` |
| 4-1-3 | `append_episode()` に `origin` 引数追加、`index_file()` に伝播 | `core/memory/manager.py` |

**Completion condition**: `append_episode("test", origin="external_platform")` で ChromaDB チャンクに `origin="external_platform"` が記録されること

### Phase 4-2: Episode 書き込み時の origin 伝播

| # | Task | Target |
|---|------|--------|
| 4-2-1 | `_process_inbox_messages()` で `append_episode(entry, origin=msg_origin)` | `core/anima.py` |
| 4-2-2 | Consolidation で `write_knowledge(..., origin="consolidation")` | `core/memory/consolidation.py` |

**Completion condition**: 外部メッセージ由来の episode チャンクに `origin="external_platform"` が付くこと

### Phase 4-3: Channel C trust 別分離出力

| # | Task | Target |
|---|------|--------|
| 4-3-1 | `PrimingResult` に `related_knowledge_untrusted` 追加 | `core/memory/priming.py` |
| 4-3-2 | `_channel_c_related_knowledge()` で検索結果を trust 別に分類 | `core/memory/priming.py` |
| 4-3-3 | `format_priming_section()` で trust 別にラップ出力 | `core/memory/priming.py` |

**Completion condition**: 外部由来チャンクが `trust="untrusted"` でラップされ、内部チャンクと分離されて出力されること

## Scope

### In Scope

- RAG チャンクメタデータへの origin 追加
- `append_episode()` / `write_knowledge()` の origin 引数
- Channel C の trust 別分離出力
- Consolidation での origin 付与
- PrimingResult 拡張

### Out of Scope

- 既存チャンクの origin バックフィル（再インデックス） — 理由: `ORIGIN_UNKNOWN` フォールバックで安全に処理。必要時は `animaworks index --rebuild` で対応
- skills / procedures / shared_users のインデックスへの origin 付与 — 理由: 全て内部データ、優先度低

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| 既存 RAG チャンクの origin 欠落 | 全チャンクが untrusted 扱いに | 再インデックス (`index --rebuild`) で対応可能。即時影響はない（保守的なので安全側） |
| Channel C バジェットの按分 | untrusted 結果が多い場合 trusted が圧迫される | trusted 優先割り当て、untrusted は残りバジェットで |
| ChromaDB メタデータフィールド追加 | 既存ストアとの互換 | 新フィールドはインデックス時に追加され、既存チャンクには影響しない |

## Acceptance Criteria

- [ ] Slack 由来メッセージの episode チャンクに `metadata["origin"] = "external_platform"` が設定される
- [ ] Consolidation 由来の knowledge チャンクに `metadata["origin"] = "consolidation"` が設定される
- [ ] Channel C 検索結果に外部由来チャンクがある場合、`trust="untrusted"` で分離出力される
- [ ] Channel C 検索結果が全て内部由来の場合、従来通り `trust="medium"` 単一ブロック出力
- [ ] 既存 RAG チャンク（origin なし）が `ORIGIN_UNKNOWN` → trust="untrusted" として処理される
- [ ] Channel C の合計バジェット（700 トークン）を超えないこと
- [ ] `PrimingResult.related_knowledge_untrusted` が空の場合、追加ブロックが出力されないこと
- [ ] 既存テストが全てパス

## References

- `core/memory/rag/indexer.py:127-142` — index_file()
- `core/memory/rag/indexer.py:627-657` — _extract_metadata()
- `core/memory/manager.py:262-276` — append_episode()
- `core/memory/priming.py:615-698` — _channel_c_related_knowledge()
- `core/memory/priming.py:1128-1132` — format_priming_section() Channel C 部分
- セキュリティ検証チャット — Poisoned RAG 攻撃シナリオ・案3-C-ii 設計議論
