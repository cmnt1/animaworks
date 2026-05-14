# Shadow Skill Router Evaluation — 全件 skill catalog 置換前に hybrid routing 精度を測る

## Overview

AnimaWorks の system prompt は現在、heartbeat 以外で全 skill/procedure catalog を常時注入している。これを削る前段階として、本番 prompt builder には接続しない shadow 実装の `SkillRouter` と評価スクリプトを追加し、metadata-aware hybrid matching の精度・false positive・no-skill 判定を測定する。

この Issue は production prompt を変更しない。目的は、将来の `skill_catalog` 置換に必要なルーティング精度と不足 metadata を可視化することである。

## Problem / Background

### Current State

- `core/prompt/builder.py` は heartbeat 以外で `skill_index.all_skills` を全件 `<available_skills>` として注入している。Relevant code: `core/prompt/builder.py:504`
- mei では `skill_catalog` が約 6.5k chars あり、system prompt bloat とノイズの大きな要因になっている。
- 既存の `match_skills_by_description()` は description 中心の 3-tier matching で、mei 実スキルに対して Gmail/Chatwork/PDF/Obsidian の代表 query を取りこぼす。Relevant code: `core/memory/skill_metadata.py:124`
- `SkillMetadata` は routing 用 field を持たず、未知 field は `extra="ignore"` で捨てられる。Relevant code: `core/skills/models.py:154`
- RAG indexer は skill body を whole-file chunk として index するが、skill frontmatter の routing metadata は汎用 metadata にほぼ保存されない。Relevant code: `core/memory/rag/indexer.py:714`

現行 matcher の mei 実測:

```text
取引先へのメール下書きを作って -> []
Chatworkで森村さんに返信して -> []
PDFにしてDownloadsへ置いて -> []
Obsidianにメモして -> []
cron設定して -> [cron-management]
画像を作って -> []
```

### Root Cause

1. 全件 catalog 注入に依存しており、検索・選抜の精度評価なしにモデルの目視判断へ任せている — `core/prompt/builder.py:504`
2. `SkillMetadata` schema に `use_when`, `do_not_use_when`, `trigger_phrases`, `negative_phrases`, `risk`, `routing_examples` 等がなく、frontmatter で補強しても現在は保持されない — `core/skills/models.py:154`
3. 既存 matcher は description substring / vocab overlap / dense search のみで、deterministic domain trigger・negative phrase・risk-aware abstain を持たない — `core/memory/skill_metadata.py:124`
4. Dense retrieval だけでは false positive/false negative が起きるため、RAG 単独で本番 catalog 置換を行うと既存 workflow を壊すリスクが高い。

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/prompt/builder.py` | Direct | 全 skill catalog 注入による prompt bloat。ただし本 Issue では変更しない。 |
| `core/skills/models.py` | Direct | routing metadata を保存できない。 |
| `core/skills/index.py` | Direct | metadata-aware search API がない。 |
| `core/skills/router.py` | New | shadow router の実装先。 |
| `scripts/evaluate_skill_router.py` | New | mei 実スキルで offline 評価する。 |
| `tests/fixtures/skill_routing_cases.yaml` | New | gold set を保持する。 |

## Decided Approach / 確定方針

### Design Decision

確定: 本番 prompt builder は一切変更せず、shadow implementation として `core/skills/router.py`、評価 fixture、評価スクリプト、単体テストを追加する。Router は deterministic metadata match + BM25-style lexical scoring + optional dense result ingestion + RRF-style merge + confidence gate を行い、候補 skill の pointer path と match reason を返す。精度評価により、将来の `skill_catalog` 置換や metadata consolidation の判断材料を作る。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| RAG 単独 | 実装が簡単。言い換えに強い。 | false positive/negative が既知の問題。明示 trigger や no-skill abstain が弱い。 | **Rejected**: 本番 catalog 置換前の精度担保にならない。 |
| BM25 単独 | 明示語、path、tool name に強い。軽い。 | 言い換え、曖昧依頼、語彙揺れに弱い。 | **Rejected**: recall が不十分。 |
| metadata のみ | prompt 節約と実装単純性が高い。 | 最近の skill routing 研究でも metadata-only は弱い。skill body が routing signal として必要。 | **Rejected**: routing index には body signal も必要。 |
| 全件 catalog を即削除 | prompt がすぐ軽くなる。 | 現行 matcher が代表 query を取りこぼすため regression risk が高い。 | **Rejected**: 先に shadow 評価する。 |
| skill 本文の自動 prompt 注入 | 選ばれた時の実行は楽。 | 誤 activation 時のノイズが大きく、payload→pointer 方針と反する。 | **Rejected**: 初版は pointer/reason のみ返す。 |
| **Shadow Hybrid Skill Router (Adopted)** | 本番影響なしで精度測定できる。deterministic/BM25/dense を比較できる。 | 初回実装では production token 削減は発生しない。 | **Adopted**: 安全に次段階の判断材料を得られる。 |

### Key Decisions from Discussion

1. **本番非接続で実装する**: `build_system_prompt()` の出力は変えない — Reason: 現行 matcher の recall が低く、即置換は危険なため。
2. **初版 rerank は heuristic に限定する**: cross-encoder/LLM rerank は導入しない — Reason: 依存、latency、運用コストを増やさず評価基盤を先に作るため。
3. **skill body は検索 signal として使うが prompt payload にはしない** — Reason: SkillRouter/SkillRet/SRA などの動向と、AnimaWorks の payload→pointer 方針を両立するため。
4. **no-skill を正解として評価する** — Reason: 関係ない skill が出る問題を定量化するため。
5. **metadata 未整備 skill も評価対象に残す** — Reason: 既存 skill corpus を壊さず、metadata 追加が必要な箇所を report で可視化するため。

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/skills/models.py` | Modify | Routing metadata model/fields を追加し、frontmatter で保持できるようにする。 |
| `core/skills/router.py` | New | Shadow hybrid skill router。Production call path からは呼ばない。 |
| `scripts/evaluate_skill_router.py` | New | Gold set と実 skill index を使って Hit@1/Hit@3/false positive/no-skill precision を出力。 |
| `tests/fixtures/skill_routing_cases.yaml` | New | 評価 query と expected skill/no-skill を定義。 |
| `tests/unit/test_skill_router.py` | New | deterministic/BM25/RRF/confidence/no-skill/path/reason の単体テスト。 |
| `core/prompt/builder.py` | No change | 本番 prompt 出力を変えない。 |
| `core/memory/skill_metadata.py` | No change | 既存 matcher 互換を維持する。必要なら router 内で再利用に留める。 |

#### Change 1: Routing Metadata Schema

**Target**: `core/skills/models.py`

Add explicit schema fields so frontmatter values are not dropped:

```python
class SkillRoutingMetadata(BaseModel):
    use_when: list[str] = Field(default_factory=list)
    do_not_use_when: list[str] = Field(default_factory=list)
    trigger_phrases: list[str] = Field(default_factory=list)
    negative_phrases: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)
    routing_examples: list[str] = Field(default_factory=list)
    risk: SkillRiskMetadata = Field(default_factory=SkillRiskMetadata)
```

`SkillMetadata` must expose these fields directly or through a `routing` field. The chosen implementation must accept both:

```yaml
use_when:
  - Gmail下書き
routing:
  trigger_phrases:
    - メール下書き
```

If both are present, values are merged with stable order and duplicates removed.

#### Change 2: Shadow Router

**Target**: `core/skills/router.py`

Router output must be structured:

```python
class SkillRouteCandidate(BaseModel):
    name: str
    path: str
    score: float
    confidence: Literal["high", "medium", "low"]
    reasons: list[str]
    is_common: bool
    is_procedure: bool
    risk: SkillRiskMetadata
```

The router must include:

- deterministic score from exact/normalized match against `name`, `path`, `trigger_phrases`, `use_when`, `tags`, `domains`, `allowed_tools`, `requires_tools`
- negative penalty from `negative_phrases` and `do_not_use_when`
- BM25-style lexical score over metadata + body summary
- optional dense candidates passed by caller, but no hard dependency on vector DB
- RRF-style merge of ranked signals
- confidence gate with abstain/no-match

#### Change 3: Offline Evaluation

**Target**: `scripts/evaluate_skill_router.py`

CLI requirements:

```bash
python3 scripts/evaluate_skill_router.py --anima mei
python3 scripts/evaluate_skill_router.py --anima mei --cases tests/fixtures/skill_routing_cases.yaml --json
```

Output must include:

- total cases
- Hit@1
- Hit@3
- false positive rate
- no-skill precision
- per-case expected / actual / score / reasons / path
- metadata gaps: expected skill found only by body/name fallback, missing `use_when`/`trigger_phrases`, or no matching signal

### Edge Cases

| Case | Handling |
|------|----------|
| Empty query | Return no candidates with reason `empty_query`. |
| no-skill query | Return no candidates when all scores are below threshold. Count as correct for no-skill cases. |
| blocked/quarantine skill | Exclude via `SkillIndex` existing trust filtering. |
| Multiple candidates near score tie | Return top candidates with reasons; evaluation counts Hit@3 separately. |
| Negative phrase matches | Apply strong penalty; if final score below threshold, abstain. |
| Metadata field absent | Fall back to description/name/path/body summary scoring. |
| Common and personal skill same name | Prefer personal when scores are otherwise equivalent, preserving existing local-over-common convention. |
| Procedure file rather than `SKILL.md` | Produce pointer as `procedures/{name}.md`. |
| Dense retriever unavailable | Router still works deterministically and lexically. |

## Implementation Plan

### Phase 1: Schema and Router Core

| # | Task | Target |
|---|------|--------|
| 1-1 | Add routing/risk metadata models and fields | `core/skills/models.py` |
| 1-2 | Normalize list/scalar YAML values into lists | `core/skills/router.py` or loader helper |
| 1-3 | Implement `SkillRouter.route(query, skills, top_k=3)` | `core/skills/router.py` |
| 1-4 | Implement deterministic, lexical, RRF, confidence, negative penalty | `core/skills/router.py` |

**Completion condition**: Router can rank in-memory `SkillMetadata` objects and returns structured candidates without touching prompt builder.

### Phase 2: Evaluation Script and Fixtures

| # | Task | Target |
|---|------|--------|
| 2-1 | Add gold set for Gmail/Chatwork/PDF/Obsidian/cron/image/no-skill | `tests/fixtures/skill_routing_cases.yaml` |
| 2-2 | Implement CLI to load `SkillIndex` for a given anima | `scripts/evaluate_skill_router.py` |
| 2-3 | Compute Hit@1, Hit@3, false positive rate, no-skill precision | `scripts/evaluate_skill_router.py` |
| 2-4 | Print per-case diagnostics and metadata gaps | `scripts/evaluate_skill_router.py` |

**Completion condition**: `python3 scripts/evaluate_skill_router.py --anima mei` runs and prints aggregate + per-case diagnostics.

### Phase 3: Tests and Production Non-Regression

| # | Task | Target |
|---|------|--------|
| 3-1 | Unit tests for exact trigger, negative phrase, no-skill, path formatting, personal priority | `tests/unit/test_skill_router.py` |
| 3-2 | Script smoke test or focused integration test for fixture loading | `tests/unit/test_skill_router.py` |
| 3-3 | Assert builder output is unchanged by this Issue | Existing or new prompt test |
| 3-4 | Run focused tests and relevant existing skill/prompt tests | pytest |

**Completion condition**: New tests pass, relevant existing skill/prompt tests pass, and no production prompt builder behavior changes.

## Scope

### In Scope

- Shadow `SkillRouter` implementation.
- Routing metadata schema additions.
- Offline evaluation script.
- Gold set fixture.
- Unit tests.
- Diagnostics for metadata gaps.
- External-source-informed design comments only where helpful.

### Out of Scope

- Replacing `skill_catalog` in production prompt — Reason: requires evaluated precision/recall first.
- Injecting routing hints into prompt builder — Reason: next Issue after evaluation.
- Cross-encoder / LLM reranking — Reason: initial evaluation should avoid new runtime dependencies and latency.
- Consolidation-generated metadata — Reason: separate memory/consolidation design.
- Large-scale editing of existing skill files — Reason: evaluation should first reveal which metadata is missing.
- Security enforcement based on risk metadata — Reason: risk metadata is a routing/approval hint, not a permission boundary.

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| Router false positives | Future prompt hints could mislead anima | This Issue is shadow-only; measure false positive before production integration. |
| Router false negatives | Future catalog replacement could hide needed skills | Gold set includes known mei workflows; Hit@3 and metadata gaps are reported. |
| Existing tests expect all catalog entries | Regression risk if builder is modified | Builder is explicitly out of scope; add/keep test proving output unchanged. |
| Metadata schema breaks loader behavior | Existing skill parsing could regress | Add tests for old SKILL.md files without routing metadata and for unknown extra field behavior if existing expectations require it. |
| BM25 dependency unavailable | Script failure or inconsistent CI | Implement lightweight internal lexical scorer; no mandatory external package. |
| Dense retrieval unavailable | Lower recall in some cases | Dense is optional; deterministic + lexical must be sufficient for the initial gold set baseline. |

## Acceptance Criteria

- [ ] `core/skills/router.py` exists and exposes a deterministic shadow `SkillRouter`.
- [ ] `SkillMetadata` preserves routing-related frontmatter fields.
- [ ] `scripts/evaluate_skill_router.py --anima mei` executes successfully.
- [ ] Gold set includes Gmail, Chatwork, PDF, Obsidian, cron, image, and no-skill cases.
- [ ] Evaluation output includes Hit@1, Hit@3, false positive rate, and no-skill precision.
- [ ] Per-case output includes expected skill, actual candidates, score, match reasons, and pointer path.
- [ ] Metadata gap diagnostics identify skills that need `use_when`/`trigger_phrases` additions.
- [ ] `build_system_prompt()` production output is unchanged for representative skill catalog tests.
- [ ] New unit tests pass.
- [ ] Relevant existing skill/prompt tests pass.

## References

- `core/prompt/builder.py:504` — Current full skill catalog injection path.
- `core/skills/models.py:154` — Current `SkillMetadata` schema.
- `core/memory/skill_metadata.py:124` — Current description-based matching.
- `core/memory/rag/indexer.py:714` — Skill body indexing strips frontmatter before embedding.
- Anthropic Skills progressive disclosure — https://claude.com/docs/skills/overview
- OpenAI Agents SDK deferred tool loading/tool search — https://openai.github.io/openai-agents-js/guides/tools/
- MCP tool descriptions and annotations — https://modelcontextprotocol.io/specification/2025-06-18/server/tools
- SkillRouter: body-aware retrieve-and-rerank — https://arxiv.org/abs/2603.22455
- SRA: retrieval and incorporation are separate bottlenecks — https://arxiv.org/abs/2604.24594
- SkillRet: tags/taxonomy and evaluation set for skill retrieval — https://arxiv.org/abs/2605.05726
