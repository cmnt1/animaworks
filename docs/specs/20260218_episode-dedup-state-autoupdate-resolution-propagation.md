# エピソード記憶重複修正・ステート自動更新・解決伝播メカニズム

## ステータス

- 作成日: 2026-02-18
- 状態: 実装待ち
- 優先度: 高
- 依存: `20260218_priming-format-redesign.md` の実装完了後に着手

## Overview

エピソード記憶の大量重複、ステートファイルの手動更新依存、解決情報の非伝播という3つの構造的問題を一括修正する。`finalize_session()` を「セッション境界で1回だけ差分要約し、ステート変更も抽出する統合ポイント」に再設計し、3層の解決伝播メカニズムを導入する。

Priming Issue（`20260218_priming-format-redesign.md`）が先行実装されるため、本Issueの実装時点で activity.py の type_map は ASCII 化済み、`format_for_priming()` はグループベース、builder.py のセクション9は削除済みであることを前提とする。

## Problem / Background

### Current State

1. **エピソード記憶の大量重複**: sakura の `episodes/2026-02-17.md` に同一会話の要約が30回以上追記されている。同じ会話内容がタイムスタンプ違いで繰り返し記録される
2. **ステートファイルの非更新**: ユーザーが「AIシュライバーのエラーは解決した」と何度伝えても、sakura は毎回同じ問題を報告し続ける。`state/current_task.md` が更新されないため
3. **解決情報の非伝播**: sakura に伝えた解決情報がミオ等の他 Anima に伝わらない。各 Anima が独立して古い情報を保持し続ける

### Root Cause

1. **per-message fire-and-forget `finalize_session()`** — `core/anima.py:355`, `core/anima.py:537`
   - メッセージ応答のたびに `asyncio.create_task(conv_memory.finalize_session(min_turns=3))` が呼ばれる
   - `finalize_session()` は**全蓄積ターン**を毎回 LLM で再要約する（`conversation.py:381-439`）
   - `append_episode()` は重複チェックなしで追記するだけ（`manager.py:730-745`）
   - N メッセージの会話 → N-2 回の重複要約が episodes/ に追記される

2. **ステートファイルのフレームワーク側書き込みパスが存在しない** — `core/memory/manager.py:747-751`
   - `update_state()` メソッドは存在するが、フレームワークからの呼び出し元がゼロ
   - Anima 自身が Write ツールで手動書き換えする設計だが、実際には行われない
   - プロセス再起動で会話コンテキストを失うため、口頭の「承知しました」が消え、state/ の古い情報で再初期化される

3. **解決情報の伝播メカニズムが存在しない**
   - activity_log は Anima 単位（`{anima_dir}/activity_log/`）で、他 Anima からは不可視
   - 組織横断の状態共有レジストリが存在しない
   - consolidation プロンプトに解決情報を注入する仕組みがない

### Impact

| Component | Impact | Description |
|-----------|--------|-------------|
| `core/memory/conversation.py` | Direct | finalize_session の大改修 |
| `core/anima.py` | Direct | fire-and-forget 呼び出し削除、heartbeat に finalize 統合 |
| `core/memory/activity.py` | Direct | `issue_resolved` イベントタイプ + ASCII ラベル追加 |
| `core/memory/consolidation.py` | Direct | 解決イベント収集 + プロンプト注入 |
| `core/prompt/builder.py` | Direct | 解決レジストリセクション追加 |
| `core/memory/manager.py` | Direct | 解決レジストリ読み書きメソッド追加 |
| `core/memory/priming.py` | Indirect | `issue_resolved` がチャネル B で自動表示される（Priming Issue 側で対応済み前提） |

## 確定方針

### Design Decision

`finalize_session()` を「セッション境界で1回だけ、差分のみ要約し、同時にステート変更を抽出して自動適用する統合ポイント」に再設計する。セッション境界は「10分アイドル or heartbeat」で検出する。解決情報は3層（ActivityLogger イベント、consolidation プロンプト注入、共有レジストリ）で伝播する。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| per-message finalize のまま重複チェック追加 | 変更が小さい | 毎回全ターン再要約する根本原因が残る。LLM コスト無駄 | **Rejected**: 対症療法であり構造的問題が残存 |
| ハッシュベースのエピソード重複検出 | 実装が単純 | LLM 要約は同一入力でも出力が微妙に異なりハッシュ一致しない | **Rejected**: LLM 出力の非決定性により信頼できない |
| パス2,3（DM受信記録・heartbeat結果記録）も finalize_session に統合 | 書き込みパスが1本に統一される | パス2（DM 生データ保存）とパス3（heartbeat 行動結果）は固有の情報種別。パス1修正だけで重複量は十分減る | **Rejected**: 過剰な統合。情報種別の区別が失われる |
| SessionSummary の JSON 出力 | パース確実 | 安価なモデルで JSON 破損リスク。consolidation が既に Markdown パースで動いている | **Rejected**: 既存パターンとの不整合 |
| Anima 自身にステート書き換えを促すプロンプト改善 | コード変更なし | プロセス再起動で忘れる。Anima 依存で信頼性が低い | **Rejected**: フレームワーク自動化の方が確実 |
| 解決レジストリを builder.py 独立セクションのみで対応 | 実装が単純 | 自 Anima の解決イベントが activity_log 経由で Priming に出ない | **Rejected**: 自 Anima + 他 Anima 両方のパスが必要 |

### Key Decisions from Discussion

1. **セッション境界 = 10分アイドル or heartbeat**: このプロジェクトのAnimaにはセッション概念がなくタイムライン形式で流れるため、「最終ターンから10分経過」または「heartbeat到達」をセッション境界とする — 理由: 自然なチェックポイントであり、データ喪失リスクもない（conversation.json は毎ターン保存済み）
2. **差分要約方式**: `last_finalized_turn_index` で記録済み位置を追跡し、未記録ターンのみを要約 — 理由: 同じターンの再要約を構造的に防止
3. **パス2,3はそのまま維持**: DM受信記録（`anima.py:784-796`）と heartbeat 結果記録（`anima.py:876-889`）は変更しない — 理由: 固有の情報種別であり、パス1の修正だけで重複量は十分減る
4. **Markdown セクション形式でパース**: `## エピソード要約` `## ステート変更` に分割し正規表現パース。consolidation と同じ手法 — 理由: 既存パターンとの統一。パース失敗時はエピソード部分のみ記録し安全側に倒す
5. **finalize_session がターン圧縮も兼ねる**: 記録済みターンは削除ではなく `compressed_summary` に統合。`compress_if_needed` はセーフティネットとして残存 — 理由: 責務の統合で conversation.json の肥大化も同時解決
6. **解決伝播は A+B 併用**: 自 Anima の解決は activity_log → Priming チャネル B（Priming Issue のグルーピングで自動表示）。他 Anima の解決は `shared/resolutions.jsonl` → builder.py 独立セクション — 理由: Anima 単位と組織横断の両方のパスが必要
7. **`issue_resolved` の ASCII ラベルは既存 type_map に追加**: Priming Issue で ASCII 化済みの type_map に `"issue_resolved": "RSLV"` を追加 — 理由: ラベル体系の整合性維持
8. **解決レジストリの配置位置**: builder.py の Priming セクション直前（旧セクション9の位置、Priming Issue で削除済み）— 理由: 活動情報に隣接する位置が文脈的に自然

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/memory/conversation.py` | Modify | `ConversationState` に `last_finalized_turn_index` 追加、`finalize_session()` を差分要約+ステート抽出+ターン圧縮に改修、`finalize_if_session_ended()` 新設、`_parse_session_summary()` 新設、`_update_state_from_summary()` 新設 |
| `core/anima.py` | Modify | `process_message()` L355 と `process_message_streaming()` L537 の fire-and-forget 削除（2箇所）。heartbeat 処理に `finalize_if_session_ended()` 呼び出し追加 |
| `core/memory/activity.py` | Modify | type_map に `"issue_resolved": "RSLV"` 追加（Priming Issue で ASCII 化済みの前提） |
| `core/memory/consolidation.py` | Modify | `daily_consolidate()` に解決イベント収集 + プロンプト注入を追加 |
| `core/prompt/builder.py` | Modify | `build_system_prompt()` に解決レジストリ注入セクション追加（Priming セクション直前） |
| `core/memory/manager.py` | Modify | `read_resolutions()` と `append_resolution()` メソッド追加 |
| `core/memory/priming.py` | No change | `issue_resolved` は Priming Issue のグルーピングで `type="single"` として自動表示される |

#### Change 1: ConversationState に記録済みインデックス追加

**Target**: `core/memory/conversation.py:60-69`

```python
# Before
@dataclass
class ConversationState:
    anima_name: str = ""
    turns: list[ConversationTurn] = field(default_factory=list)
    compressed_summary: str = ""
    compressed_turn_count: int = 0

# After
@dataclass
class ConversationState:
    anima_name: str = ""
    turns: list[ConversationTurn] = field(default_factory=list)
    compressed_summary: str = ""
    compressed_turn_count: int = 0
    last_finalized_turn_index: int = 0  # episode記録済み位置
```

`save()` / `load()` で `last_finalized_turn_index` をシリアライズ/デシリアライズする。既存 JSON にフィールドがない場合はデフォルト 0。

#### Change 2: finalize_session() の大改修

**Target**: `core/memory/conversation.py:381-439`

```python
# Before
async def finalize_session(self, min_turns: int = 3) -> bool:
    state = self.load()
    if len(state.turns) < min_turns:
        return False
    summary = await self._summarize_session(state.turns, activity_context)
    memory_mgr.append_episode(episode_entry)
    return True

# After
async def finalize_session(self, min_turns: int = 3) -> bool:
    state = self.load()
    new_turns = state.turns[state.last_finalized_turn_index:]
    if len(new_turns) < min_turns:
        return False

    activity_context = self._gather_activity_context(new_turns)
    raw_summary = await self._summarize_session_with_state(new_turns, activity_context)
    parsed = self._parse_session_summary(raw_summary)

    # 1. エピソード記録（差分のみ）
    memory_mgr = MemoryManager(self.anima_dir)
    timestamp = datetime.now().strftime("%H:%M")
    episode_entry = f"## {timestamp} — {parsed.title}\n\n{parsed.episode_body}\n"
    memory_mgr.append_episode(episode_entry)

    # 2. ステート自動更新（パース成功時のみ）
    if parsed.has_state_changes:
        self._update_state_from_summary(memory_mgr, parsed)

    # 3. 解決イベント記録（パース成功時のみ）
    if parsed.resolved_items:
        self._record_resolutions(memory_mgr, parsed.resolved_items)

    # 4. 記録済みターンをcompressed_summaryに統合
    turn_text = self._format_turns_for_compression(new_turns)
    old_summary = state.compressed_summary
    try:
        compressed = await self._call_compression_llm(old_summary, turn_text)
        state.compressed_summary = compressed
    except Exception:
        logger.warning("Compression failed during finalization; keeping raw turns")

    state.last_finalized_turn_index = len(state.turns)
    state.compressed_turn_count += len(new_turns)
    self.save()
    return True
```

#### Change 3: 要約プロンプトの拡張

**Target**: `core/memory/conversation.py:488-` (`_summarize_session` を `_summarize_session_with_state` に改名)

```python
system = (
    "あなたは会話記録の要約者です。以下の会話をエピソード記憶として記録し、"
    "同時にステート変更を抽出してください。\n\n"
    "出力形式:\n"
    "## エピソード要約\n"
    "{会話の要約タイトル（20文字以内）}\n\n"
    "**相手**: {相手の名前}\n"
    "**トピック**: {主なトピック、カンマ区切り}\n"
    "**要点**:\n"
    "- {要点1}\n"
    "- {要点2}\n\n"
    "**決定事項**: {あれば記載}\n\n"
    "## ステート変更\n"
    "### 解決済み\n"
    "- {解決した課題があればリスト。なければ「なし」}\n"
    "### 新規タスク\n"
    "- {新たに発生したタスク。なければ「なし」}\n"
    "### 現在の状態\n"
    "{「idle」または現在取り組み中の内容}\n"
)
```

#### Change 4: SessionSummary パーサー

**Target**: `core/memory/conversation.py` (新規メソッド)

```python
@dataclass
class ParsedSessionSummary:
    title: str
    episode_body: str
    resolved_items: list[str]
    new_tasks: list[str]
    current_status: str
    has_state_changes: bool

@staticmethod
def _parse_session_summary(raw: str) -> ParsedSessionSummary:
    """Markdownセクション形式のLLM出力をパース。

    パース失敗時はエピソード部分のみ抽出し、ステート変更は空とする。
    """
    # ## エピソード要約 セクションを抽出
    episode_match = re.search(
        r"##\s*エピソード要約\s*\n(.+?)(?=##\s*ステート変更|\Z)",
        raw, re.DOTALL,
    )
    episode_body = episode_match.group(1).strip() if episode_match else raw.strip()

    lines = episode_body.splitlines()
    title = lines[0][:50] if lines else "会話"
    body = "\n".join(lines[1:]).strip() if len(lines) > 1 else episode_body

    # ## ステート変更 セクションを抽出
    state_match = re.search(
        r"##\s*ステート変更\s*\n(.+)",
        raw, re.DOTALL,
    )

    resolved_items: list[str] = []
    new_tasks: list[str] = []
    current_status = ""

    if state_match:
        state_text = state_match.group(1)

        # ### 解決済み
        resolved_match = re.search(
            r"###\s*解決済み\s*\n(.+?)(?=###|\Z)",
            state_text, re.DOTALL,
        )
        if resolved_match:
            for line in resolved_match.group(1).strip().splitlines():
                item = line.strip().lstrip("- ").strip()
                if item and item != "なし":
                    resolved_items.append(item)

        # ### 新規タスク
        tasks_match = re.search(
            r"###\s*新規タスク\s*\n(.+?)(?=###|\Z)",
            state_text, re.DOTALL,
        )
        if tasks_match:
            for line in tasks_match.group(1).strip().splitlines():
                item = line.strip().lstrip("- ").strip()
                if item and item != "なし":
                    new_tasks.append(item)

        # ### 現在の状態
        status_match = re.search(
            r"###\s*現在の状態\s*\n(.+?)(?=###|\Z)",
            state_text, re.DOTALL,
        )
        if status_match:
            current_status = status_match.group(1).strip()

    return ParsedSessionSummary(
        title=title,
        episode_body=body,
        resolved_items=resolved_items,
        new_tasks=new_tasks,
        current_status=current_status,
        has_state_changes=bool(resolved_items or new_tasks or current_status),
    )
```

#### Change 5: ステート自動更新

**Target**: `core/memory/conversation.py` (新規メソッド)

```python
def _update_state_from_summary(
    self, memory_mgr: MemoryManager, parsed: ParsedSessionSummary
) -> None:
    """current_task.md を会話の結論に基づいて自動更新。"""
    current = memory_mgr.read_current_state()
    updated = False

    # 解決済みアイテムを「### 解決済み」セクションに追記
    for item in parsed.resolved_items:
        if item not in current:
            marker = f"   - ✅ {item}（自動検出: {datetime.now().strftime('%m/%d %H:%M')}）"
            # 「未解決課題」セクションがあれば、そこに解決マークを追記
            if "未解決" in current or "継続監視" in current:
                current += f"\n{marker}"
            updated = True

    # 新規タスクを末尾に追記
    for task in parsed.new_tasks:
        if task not in current:
            current += f"\n- [ ] {task}（自動検出: {datetime.now().strftime('%m/%d %H:%M')}）"
            updated = True

    if updated:
        memory_mgr.update_state(current)
        logger.info("State auto-updated from session summary")
```

#### Change 6: 解決イベント記録（3層）

**Target**: `core/memory/conversation.py` (新規メソッド)

```python
def _record_resolutions(
    self, memory_mgr: MemoryManager, resolved_items: list[str]
) -> None:
    """解決情報を3層に記録。"""
    from core.memory.activity import ActivityLogger

    activity = ActivityLogger(self.anima_dir)

    for item in resolved_items:
        # 層1: ActivityLogger に issue_resolved イベント
        try:
            activity.log(
                "issue_resolved",
                content=item,
                summary=f"解決済み: {item[:100]}",
            )
        except Exception:
            logger.debug("Failed to log issue_resolved event", exc_info=True)

        # 層3: shared/resolutions.jsonl に組織横断記録
        try:
            memory_mgr.append_resolution(
                issue=item,
                resolver=self.anima_dir.name,
            )
        except Exception:
            logger.debug("Failed to write resolution registry", exc_info=True)
```

#### Change 7: セッション境界検出

**Target**: `core/memory/conversation.py` (新規メソッド)

```python
SESSION_GAP_MINUTES = 10

async def finalize_if_session_ended(self) -> bool:
    """最終ターンからSESSION_GAP_MINUTES経過していれば要約を実行。

    heartbeat から呼ばれることを想定。
    """
    state = self.load()
    if not state.turns:
        return False
    # 未記録ターンがなければスキップ
    new_turns = state.turns[state.last_finalized_turn_index:]
    if not new_turns:
        return False
    last_ts = datetime.fromisoformat(new_turns[-1].timestamp)
    elapsed = (datetime.now() - last_ts).total_seconds()
    if elapsed < self.SESSION_GAP_MINUTES * 60:
        return False
    return await self.finalize_session()
```

#### Change 8: fire-and-forget 削除 + heartbeat 統合

**Target**: `core/anima.py:354-355`, `core/anima.py:535-538`

```python
# Before (process_message, L355):
asyncio.create_task(conv_memory.finalize_session(min_turns=3))

# After: 削除（行ごと削除）

# Before (process_message_streaming, L536-538):
asyncio.create_task(
    conv_memory.finalize_session(min_turns=3)
)

# After: 削除（3行ごと削除）
```

**Target**: `core/anima.py` heartbeat 処理（L875 付近、heartbeat_end activity.log の直後に追加）

```python
# heartbeat episode 記録（既存パス3）の後に追加:

# Session boundary: finalize pending conversation turns
try:
    conv_mem = ConversationMemory(self.anima_dir, self.model_config)
    await conv_mem.finalize_if_session_ended()
except Exception:
    logger.debug("[%s] finalize_if_session_ended failed", self.name, exc_info=True)
```

#### Change 9: type_map に `issue_resolved` 追加

**Target**: `core/memory/activity.py` の type_map（Priming Issue で ASCII 化済みの前提）

```python
# Priming Issue 実装後の type_map に追加:
type_map: dict[str, str] = {
    "message_received": "MSG<",
    "response_sent": "MSG>",
    # ... (Priming Issue で定義済み)
    "issue_resolved": "RSLV",  # 本 Issue で追加
}
```

Priming Issue のグルーピングルールでは `issue_resolved` は `type="single"` として扱われる（DM/HB/CRON 以外はすべて single）。

#### Change 10: 解決レジストリ読み書き

**Target**: `core/memory/manager.py` (新規メソッド)

```python
def append_resolution(self, issue: str, resolver: str) -> None:
    """shared/resolutions.jsonl に解決情報を追記。"""
    shared_dir = get_shared_dir()
    path = shared_dir / "resolutions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.now().isoformat(),
        "issue": issue,
        "resolver": resolver,
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")

def read_resolutions(self, days: int = 7) -> list[dict[str, str]]:
    """shared/resolutions.jsonl から直近N日分の解決情報を読み込む。"""
    shared_dir = get_shared_dir()
    path = shared_dir / "resolutions.jsonl"
    if not path.exists():
        return []
    cutoff = (datetime.now() - timedelta(days=days)).isoformat()
    entries: list[dict[str, str]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
            if entry.get("ts", "") >= cutoff:
                entries.append(entry)
        except json.JSONDecodeError:
            continue
    return entries
```

#### Change 11: builder.py に解決レジストリ注入

**Target**: `core/prompt/builder.py` `build_system_prompt()` 内、Priming セクション直前

```python
# 解決レジストリ注入（Priming セクション直前）
resolutions = memory.read_resolutions(days=7)
if resolutions:
    res_lines = []
    for r in resolutions[-10:]:  # 直近10件まで
        ts_short = r.get("ts", "")[:16]  # YYYY-MM-DDTHH:MM
        resolver = r.get("resolver", "unknown")
        issue = r.get("issue", "")
        res_lines.append(f"- [{ts_short}] {resolver}: {issue}")
    parts.append(
        "## 解決済み案件（組織横断）\n\n"
        "以下は直近7日間に解決された案件です。"
        "これらの問題については再調査・再報告は不要です。\n\n"
        + "\n".join(res_lines)
    )

# Priming section (automatic memory recall)
if priming_section:
    parts.append(priming_section)
```

#### Change 12: consolidation に解決イベント注入

**Target**: `core/memory/consolidation.py` `daily_consolidate()` 内

```python
# _summarize_episodes() の前に解決イベントを収集
resolved_events = self._collect_resolved_events(hours=24)

# プロンプトに追加
if resolved_events:
    prompt += f"""
【解決済み案件】
以下の案件は解決済みです。既存の知識ファイルに「未解決」「対応中」「調査中」等の
記載がある場合は、「解決済み」に更新してください。

{resolved_events_text}
"""
```

新規メソッド:

```python
def _collect_resolved_events(self, hours: int = 24) -> list[dict]:
    """activity_log から issue_resolved イベントを収集。"""
    from core.memory.activity import ActivityLogger
    activity = ActivityLogger(self.anima_dir)
    return activity.recent(days=1, limit=50, types=["issue_resolved"])
```

### Edge Cases

| Case | Handling |
|------|----------|
| マイグレーション: 既存 conversation.json に `last_finalized_turn_index` がない | `load()` で `data.get("last_finalized_turn_index", 0)` とし、デフォルト 0。初回 finalize で全既存ターンを1回要約（1回限りの移行コスト） |
| SessionSummary のパース失敗 | `_parse_session_summary()` が `## ステート変更` セクションを見つけられない場合、`raw` 全体をエピソード本文として扱う。`has_state_changes=False` となりステート更新・解決記録スキップ |
| finalize_session 中のプロセスクラッシュ | conversation.json は事前保存済み。`last_finalized_turn_index` が更新されていないため、次回起動時に同じターンを再試行。重複は1回限り（次回成功すればインデックス更新） |
| 10分以内に heartbeat が来た場合 | `finalize_if_session_ended()` で最終ターンからの経過時間をチェック。10分未満ならスキップ |
| ターン数が min_turns 未満のまま10分経過 | 短い会話（挨拶のみ等）はスキップ。ただし min_turns は finalize 済み以降のターン数でカウント |
| resolutions.jsonl の肥大化 | `read_resolutions(days=7)` で直近7日分のみ読み込み。古いエントリは読み飛ばし。月次で別途 truncate 可能（スコープ外） |
| compressed_summary への統合失敗（LLM エラー） | `logger.warning` のみ。生ターンはそのまま残り、次回 `compress_if_needed()` がセーフティネットとして機能 |

## Implementation Plan

### Phase 1: エピソード重複の根本修正

| # | Task | Target |
|---|------|--------|
| 1-1 | `ConversationState` に `last_finalized_turn_index` フィールド追加、`save()` / `load()` 更新 | `core/memory/conversation.py` |
| 1-2 | `finalize_session()` を差分要約に改修（`turns[last_finalized_turn_index:]` のみ要約）| `core/memory/conversation.py` |
| 1-3 | `finalize_if_session_ended()` メソッド新設（10分アイドル検出） | `core/memory/conversation.py` |
| 1-4 | `process_message()` L355 と `process_message_streaming()` L537 の fire-and-forget 削除 | `core/anima.py` |
| 1-5 | heartbeat 処理に `finalize_if_session_ended()` 呼び出し追加 | `core/anima.py` |
| 1-6 | finalize 後の記録済みターンを `compressed_summary` に統合する処理追加 | `core/memory/conversation.py` |

**テスト**:

| テスト | 検証内容 |
|--------|---------|
| `test_finalize_session_incremental` | 2回目の finalize で差分ターンのみ要約されること |
| `test_finalize_session_updates_index` | finalize 後に `last_finalized_turn_index` が更新されること |
| `test_finalize_session_compresses_turns` | finalize 後に記録済みターンが `compressed_summary` に統合されること |
| `test_finalize_if_session_ended_skips_recent` | 最終ターンから10分未満ならスキップ |
| `test_finalize_if_session_ended_triggers` | 10分超でfinalize実行 |
| `test_load_migration_default_index` | 古い conversation.json で `last_finalized_turn_index` が 0 になること |
| `test_fire_and_forget_removed` | `process_message` 内に `finalize_session` の直接呼び出しがないことを grep で検証 |

**完了条件**: 同一会話内で複数メッセージを送っても episodes/ に要約が1回しか追記されない。heartbeat で未記録ターンが要約される。

### Phase 2: ステート自動更新

| # | Task | Target |
|---|------|--------|
| 2-1 | `_summarize_session_with_state()` — 要約プロンプトにステート抽出セクション追加 | `core/memory/conversation.py` |
| 2-2 | `ParsedSessionSummary` dataclass + `_parse_session_summary()` パーサー新設 | `core/memory/conversation.py` |
| 2-3 | `_update_state_from_summary()` — パース結果から state/current_task.md を自動更新 | `core/memory/conversation.py` |

**テスト**:

| テスト | 検証内容 |
|--------|---------|
| `test_parse_session_summary_full` | 正常な Markdown 出力から全フィールドが抽出されること |
| `test_parse_session_summary_no_state_section` | `## ステート変更` がない場合、エピソード部分のみ抽出されステート変更は空 |
| `test_parse_session_summary_resolved_none` | 「なし」と書かれた場合、空リストになること |
| `test_update_state_appends_resolved` | 解決済みアイテムが state に追記されること |
| `test_update_state_appends_new_tasks` | 新規タスクが state に追記されること |
| `test_update_state_no_duplicate` | 既に state に含まれるアイテムは重複追記されないこと |

**完了条件**: 会話で「この問題は解決した」と伝えた後の finalize_session で、state/current_task.md に解決マークが自動追記される。

### Phase 3: 解決伝播メカニズム

| # | Task | Target |
|---|------|--------|
| 3-1 | type_map に `"issue_resolved": "RSLV"` 追加 | `core/memory/activity.py` |
| 3-2 | `_record_resolutions()` — ActivityLogger + shared/resolutions.jsonl への書き込み | `core/memory/conversation.py` |
| 3-3 | `append_resolution()` / `read_resolutions()` メソッド追加 | `core/memory/manager.py` |
| 3-4 | builder.py に解決レジストリ注入セクション追加（Priming セクション直前） | `core/prompt/builder.py` |
| 3-5 | `_collect_resolved_events()` + consolidation プロンプトへの解決情報注入 | `core/memory/consolidation.py` |

**テスト**:

| テスト | 検証内容 |
|--------|---------|
| `test_issue_resolved_ascii_label` | `_format_entry()` で `issue_resolved` タイプに `RSLV` ラベルが出力されること |
| `test_record_resolutions_writes_activity` | ActivityLogger に `issue_resolved` イベントが記録されること |
| `test_record_resolutions_writes_registry` | `shared/resolutions.jsonl` に書き込まれること |
| `test_read_resolutions_filters_by_days` | 7日以上古いエントリが除外されること |
| `test_builder_injects_resolutions` | `build_system_prompt()` の出力に「解決済み案件」セクションが含まれること |
| `test_builder_no_resolutions_section_when_empty` | 解決レジストリが空の場合はセクションなし |
| `test_consolidation_includes_resolved_events` | consolidation プロンプトに解決イベントが含まれること |

**完了条件**: 解決イベントが activity_log と shared/resolutions.jsonl に記録され、他 Anima のシステムプロンプトに「解決済み案件」として表示される。

## Scope

### In Scope

- finalize_session の差分要約化（`last_finalized_turn_index` 追跡）
- per-message fire-and-forget の削除
- セッション境界検出（10分アイドル + heartbeat）
- 記録済みターンの compressed_summary 統合
- SessionSummary パーサー（Markdown セクション形式）
- state/current_task.md の自動更新（解決・新規タスク）
- ActivityLogger への `issue_resolved` イベント（ASCII ラベル `RSLV` 付き）
- `shared/resolutions.jsonl` 解決レジストリ
- builder.py 解決レジストリ注入セクション
- consolidation プロンプトへの解決イベント注入

### Out of Scope

- パス2（DM受信エピソード記録 `anima.py:784-796`）の変更 — 理由: 固有の情報種別（生メッセージ原文）、パス1修正で十分
- パス3（heartbeat エピソード記録 `anima.py:876-889`）の変更 — 理由: 固有の情報種別（heartbeat 行動結果）
- 既存 episodes/ ファイルの遡及的重複クリーンアップ — 理由: 新規記録が正常化されれば過去分は consolidation/forgetting で自然に処理される
- Anima 間のリアルタイム状態変更通知（pub/sub 等）— 理由: 解決レジストリ + Priming で十分
- ConversationMemory の DB 化 — 理由: ファイルベースで十分
- consolidation の dedup_key ロジック改善（先頭200文字判定）— 理由: エピソード重複が根本修正されれば dedup の重要度は低下
- resolutions.jsonl の月次 truncate 自動化 — 理由: 7日フィルタで read 時に対応。自動削除は別途検討

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| finalize_session の LLM 呼び出し回数が減りすぎてエピソードが粗くなる | 中 | SESSION_GAP_MINUTES=10 で十分な粒度。heartbeat（30分間隔）でも finalize される |
| SessionSummary パースの信頼性（LLM がフォーマットを守らない） | 中 | パース失敗時はエピソード部分のみ記録。ステート更新はスキップ（安全側）。エラーログで検知可能 |
| ステート自動更新で誤った「解決」判定 | 低 | LLM が「解決済み」として抽出したもののみ。state/ への追記は追記形式（既存内容は削除しない） |
| Priming Issue との実装順序の競合 | 低 | 本 Issue は Priming Issue 完了後に着手。type_map は追加のみで競合なし |
| 既存 compress_if_needed との二重圧縮 | 低 | finalize_session が先に圧縮するため、compress_if_needed は通常発火しない。発火しても問題ない（冪等） |

## Acceptance Criteria

- [ ] 同一会話内で `finalize_session()` が2回以上呼ばれても、同じターンが重複要約されない
- [ ] per-message の fire-and-forget `finalize_session()` 呼び出しが process_message / process_message_streaming から削除されている
- [ ] セッション境界（10分アイドル or heartbeat）でのみエピソード記録が実行される
- [ ] finalize_session 後、記録済みターンが compressed_summary に統合されている
- [ ] LLM 応答から「解決済みアイテム」がパースされ、`state/current_task.md` に自動追記される
- [ ] SessionSummary のパース失敗時、エピソード記録は正常に動作する（ステート更新のみスキップ）
- [ ] 解決イベントが ActivityLogger に `issue_resolved` タイプで記録される
- [ ] `shared/resolutions.jsonl` に解決情報が書き込まれる
- [ ] `build_system_prompt()` の出力に直近7日分の解決レジストリが注入される
- [ ] 解決レジストリが空の場合はセクションが注入されない
- [ ] consolidation プロンプトに解決イベント情報が含まれる
- [ ] `issue_resolved` の ASCII ラベルが `RSLV` である（Priming Issue の type_map 体系と整合）
- [ ] 既存テスト（conversation, consolidation, activity 関連）がすべて通る
- [ ] 新規テスト（Phase 1: 7件、Phase 2: 6件、Phase 3: 7件）がすべて通る

## References

- `core/memory/conversation.py:381-439` — 現在の finalize_session 実装
- `core/anima.py:355` — fire-and-forget 呼び出し箇所（process_message）
- `core/anima.py:537` — fire-and-forget 呼び出し箇所（process_message_streaming）
- `core/anima.py:876-889` — heartbeat エピソード記録（パス3、変更なし）
- `core/anima.py:784-796` — DM 受信エピソード記録（パス2、変更なし）
- `core/memory/manager.py:730-745` — append_episode（重複チェックなし）
- `core/memory/manager.py:747-751` — update_state / update_pending（呼び出し元なし）
- `core/memory/consolidation.py:209-217` — dedup_key（先頭200文字判定）
- `core/memory/activity.py:251-292` — _format_entry（Priming Issue で ASCII 化予定）
- `core/prompt/builder.py:393-400` — state 注入（⚠️ 進行中タスク MUST セクション）
- `core/prompt/builder.py:408-416` — セクション9（Priming Issue で削除予定）
- `core/prompt/builder.py:418-420` — Priming セクション（解決レジストリはこの直前に配置）
- `docs/issues/20260218_priming-format-redesign.md` — 先行実装 Issue（type_map ASCII 化、グルーピング、セクション9削除）
