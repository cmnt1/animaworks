# 出自トラッキング Phase 3: 伝播 — Anima 間メッセージの origin_chain 伝播

## Overview

全5フェーズの出自トラッキング導入の第3弾。Anima 間のメッセージ送信（`send_message` ツール）で `origin_chain` を伝播し、外部由来データが中継で trusted に昇格する「信頼ロンダリング」を防止する。このフェーズ完了で、セキュリティ検証 #5（信頼ロンダリング）が解決する。

依存: Phase 1（基盤）, Phase 2（入口 origin 付与）

## Problem / Background

### Current State

攻撃シナリオ:

```
攻撃者 → Slack DM → Anima A (inbox, source="slack")
  → Anima A が send_message(to="Anima B", content=悪意テキスト)
  → Anima B は「Anima A からの指示」として受け取る（source="anima" = trusted）
```

- `Messenger.send()` は `source` を設定せず、デフォルト `"anima"` になる — `core/messenger.py:99-107`
- `origin_chain` の伝播メカニズムがなく、元の外部 origin が消失する
- Anima B 側では `meta={"from_type": "anima"}` と記録され、外部由来であることが検出不能

### Root Cause

`Messenger.send()` が送信元 Anima のコンテキスト（現在処理中のメッセージの origin）を引き継がない。

### Impact

| コンポーネント | 影響 | 説明 |
|--------------|------|------|
| `core/messenger.py` | Direct | `send()` に `origin_chain` 引数追加 |
| `core/tooling/handler_comms.py` | Direct | `_handle_send_message()` で現在セッションの origin を渡す |
| `core/anima.py` | Direct | セッションの origin コンテキストを ToolHandler に伝播 |
| `core/tooling/handler.py` | Direct | ToolHandler に `session_origin` / `session_origin_chain` を保持 |

## Decided Approach / 確定方針

### Design Decision

Anima がメッセージを送信する際、**現在処理中のセッションの origin** を `origin_chain` に追記して伝播する。ToolHandler がセッション開始時に origin コンテキストを受け取り、`send_message` ツール実行時に `Messenger.send()` に渡す。

### Rejected Alternatives

| Approach | Pros | Cons | Verdict |
|----------|------|------|---------|
| content に origin タグを埋め込む | Messenger 変更不要 | テキスト解析が必要、偽装可能 | **Rejected**: 構造化データでないと信頼できない |
| 全メッセージを untrusted にする | 確実 | Anima 間の正常な指示・報告が制約される | **Rejected**: 過剰制限で組織機能が損なわれる |
| send_message を禁止し channel 経由のみにする | チャネルに trust を設定可能 | DM の利便性を完全に失う | **Rejected**: アーキテクチャの大幅変更が必要 |

### Key Decisions from Discussion

1. **origin_chain の構築ルール**: 送信元セッションの `origin_chain` + `origin` を新メッセージの `origin_chain` にする — 理由: 完全な中継履歴
2. **セッション origin の保持場所**: `ToolHandler` にインスタンス変数 `_session_origin` / `_session_origin_chain` を追加 — 理由: ToolHandler は各セッションのツール実行を担う中心点
3. **origin_chain がない send_message**: セッション origin が human / anima 直接なら `origin_chain=["anima"]` — 理由: Anima 自身が生成したメッセージの origin は "anima"

### Changes by Module

| Module | Change Type | Description |
|--------|------------|-------------|
| `core/messenger.py` | Modify | `send()` に `origin_chain` 引数追加、Message に設定 |
| `core/tooling/handler.py` | Modify | `set_session_origin()` メソッド追加、`_session_origin` / `_session_origin_chain` 保持 |
| `core/tooling/handler_comms.py` | Modify | `_handle_send_message()` で `_session_origin_chain` を Messenger に渡す |
| `core/anima.py` | Modify | `process_message()` / `_process_inbox_messages()` で ToolHandler にセッション origin を設定 |

#### Change 1: Messenger.send() 拡張

**Target**: `core/messenger.py`

```python
# Before (line 57-107)
def send(self, to, content, msg_type="message", thread_id="", reply_to="",
         skip_logging=False, intent="") -> Message:
    ...
    msg = Message(
        from_person=self.anima_name,
        to_person=to,
        ...
    )

# After
def send(self, to, content, msg_type="message", thread_id="", reply_to="",
         skip_logging=False, intent="",
         origin_chain: list[str] | None = None) -> Message:
    ...
    msg = Message(
        from_person=self.anima_name,
        to_person=to,
        ...
        origin_chain=origin_chain or [],
    )
```

#### Change 2: ToolHandler にセッション origin 保持

**Target**: `core/tooling/handler.py`

```python
# After
class ToolHandler:
    def __init__(self, ...):
        ...
        self._session_origin: str = ""
        self._session_origin_chain: list[str] = []

    def set_session_origin(self, origin: str, origin_chain: list[str] | None = None) -> None:
        """Set the origin context for the current session."""
        self._session_origin = origin
        self._session_origin_chain = origin_chain or []
```

#### Change 3: send_message で origin_chain 伝播

**Target**: `core/tooling/handler_comms.py`

```python
# _handle_send_message() 内
# 送信元のセッション origin を chain に追記して伝播
from core.execution._sanitize import ORIGIN_ANIMA, MAX_ORIGIN_CHAIN_LENGTH

outgoing_chain = list(self._session_origin_chain)
if self._session_origin and self._session_origin not in outgoing_chain:
    outgoing_chain.append(self._session_origin)
outgoing_chain.append(ORIGIN_ANIMA)  # 自分（Anima）が中継した記録
outgoing_chain = outgoing_chain[:MAX_ORIGIN_CHAIN_LENGTH]

msg = self.messenger.send(
    to=to,
    content=content,
    ...
    origin_chain=outgoing_chain,
)
```

#### Change 4: セッション開始時に origin 設定

**Target**: `core/anima.py`

```python
# process_message() 内（Chat API 経由）
self.tool_handler.set_session_origin(ORIGIN_HUMAN)

# _process_inbox_messages() 内
msg_origin = _SOURCE_TO_ORIGIN.get(m.source, ORIGIN_UNKNOWN)
msg_origin_chain = m.origin_chain if m.origin_chain else [msg_origin]
self.tool_handler.set_session_origin(msg_origin, msg_origin_chain)
```

### Edge Cases

| Case | Handling |
|------|----------|
| Anima が heartbeat/cron で自発的に send_message | `_session_origin = ORIGIN_SYSTEM`, `origin_chain = ["system", "anima"]` |
| Anima A → Anima B → Anima C の多段中継 | chain は `["external_platform", "anima", "anima"]` のように積み上がる |
| origin_chain が MAX_ORIGIN_CHAIN_LENGTH (10) を超える | 先頭 10 要素で打ち切り |
| delegate_task ツール | send_message と同様に origin_chain を伝播（handler_org.py 内） |
| ack / error / system_alert メッセージ | origin_chain 不要（msg_type で判別可能） |

## Implementation Plan

### Phase 3-1: Messenger 拡張

| # | Task | Target |
|---|------|--------|
| 3-1-1 | `send()` に `origin_chain` 引数追加 | `core/messenger.py` |

**Completion condition**: `send(to, content, origin_chain=["external_platform", "anima"])` で Message.origin_chain が正しく設定されること

### Phase 3-2: ToolHandler セッション origin

| # | Task | Target |
|---|------|--------|
| 3-2-1 | `set_session_origin()` メソッド追加 | `core/tooling/handler.py` |
| 3-2-2 | `_handle_send_message()` で origin_chain 伝播 | `core/tooling/handler_comms.py` |
| 3-2-3 | `_handle_delegate_task()` でも origin_chain 伝播 | `core/tooling/handler_org.py` |

**Completion condition**: send_message ツール実行時に outgoing Message.origin_chain にセッション origin が含まれること

### Phase 3-3: Anima セッション origin 設定

| # | Task | Target |
|---|------|--------|
| 3-3-1 | `process_message()` で `set_session_origin(ORIGIN_HUMAN)` | `core/anima.py` |
| 3-3-2 | `_process_inbox_messages()` で Message.source → origin 変換 + `set_session_origin()` | `core/anima.py` |
| 3-3-3 | heartbeat / cron で `set_session_origin(ORIGIN_SYSTEM)` | `core/anima.py` |

**Completion condition**: E2E で「Slack → Anima A → send_message → Anima B の Inbox」の Message.origin_chain に `"external_platform"` が含まれること

## Scope

### In Scope

- `Messenger.send()` の origin_chain 引数追加
- ToolHandler のセッション origin 管理
- send_message / delegate_task での origin_chain 伝播
- Anima の各パス（chat, inbox, heartbeat, cron）でのセッション origin 設定

### Out of Scope

- 受信側 Anima での origin_chain 解析（Priming での trust 解決は Phase 2 の tool_data_interpretation.md で対応済み）
- 共有チャネル (post_channel) の origin 伝播 — 将来課題
- 外部配信 (send_external) の origin 伝播 — セキュリティ上不要（外部に送るだけ）

## Risk

| Risk | Impact | Mitigation |
|------|--------|------------|
| origin_chain の無限成長 | メモリ・トークン増大 | MAX_ORIGIN_CHAIN_LENGTH (10) で打ち切り |
| セッション origin の設定漏れ | 新パス追加時 | フォールバック: `_session_origin` 未設定なら `"unknown"` |
| 既存テストの send() 呼び出し互換 | テスト破損 | `origin_chain` は optional 引数（デフォルト None） |

## Acceptance Criteria

- [ ] Slack → Anima A(inbox) → send_message → Anima B の Inbox Message.origin_chain に `"external_platform"` が含まれる
- [ ] Chat API → Anima → send_message → 他 Anima の Inbox Message.origin_chain が `["human", "anima"]`
- [ ] Heartbeat → send_message → 他 Anima の origin_chain が `["system", "anima"]`
- [ ] 3段中継（A→B→C）で origin_chain が正しく積み上がる
- [ ] origin_chain が 10 要素を超えた場合に打ち切られる
- [ ] delegate_task でも origin_chain が伝播する
- [ ] `send()` を origin_chain なしで呼んだ既存コードが正常動作する
- [ ] 既存テストが全てパス

## References

- `core/messenger.py:57-114` — Messenger.send()
- `core/messenger.py:436-470` — Messenger.receive_external()
- `core/tooling/handler_comms.py` — _handle_send_message()
- `core/tooling/handler_org.py` — _handle_delegate_task()
- `core/anima.py:461-525` — process_message()
- `core/anima.py:874-937` — process_inbox_message()
- セキュリティ検証チャット — 信頼ロンダリング攻撃シナリオ
