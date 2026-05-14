# mei chat session repeat root fixes

## Overview

meiの2026-05-14 16:31〜17:29のactivity/transcriptで、ユーザーの1回の指示に対して同じ調査・回答・完了報告が複数回繰り返された。表面的には`emotion: smile`などが何度も出ているように見えるが、根本は「タスクが完了しているにもかかわらず、同一チャットセッション内または復旧処理で同じ回答ブロックが再混入している」こと。

このIssueでは、今回の調査で特定した3つの原因を修正する。

1. `completion_gate`未呼び出し時のストリーミング出力が最終応答に残る
2. chat / heartbeat / cron / inboxが同じ`AgentCore`可変状態を別ロックで扱い、セッション種別やinterruptイベントを上書きし得る
3. streaming journal復旧が冪等でなく、既に復旧済みの応答を再度会話・activityへ復元し得る

## Evidence

- `mei/transcripts/2026-05-14.jsonl`の16:35 assistant turnに、同一質問への回答ブロックが複数個連結されている。
- 同日のactivityでは、16:31の`message_received`後、16:33に`heartbeat_start`、16:35に`response_sent`が発生しており、chat応答中にheartbeatが開始している。
- 17:29にはchatとheartbeat両方のstreaming journal recovery errorが出ており、長い未完了streamが復旧対象になっている。
- 出力本文に`問題なし`, `No response needed`, `emotion` markerなど、completion gate用の追加確認や内部的な継続指示が混入している。

## Root Causes

### 1. completion_gate retry text is committed too early

`core/execution/_litellm_streaming.py`では、streaming iterationの`iter_text`を`completion_gate`確認より前に`all_response_text`へ追加している。gate未呼び出しの場合はassistantへリマインダーを追加して`continue`するが、その時点で仮回答が最終応答用バッファに残る。

そのため、モデルがgate retryごとに同じ結論を出すと、最終`full_text`に複数の回答ブロックが連結される。

### 2. DigitalAnima has per-purpose locks but no shared agent session lock

`DigitalAnima`には会話用`_conversation_locks`とbackground用`_background_lock`があるが、chat / heartbeat / cron / inboxが共有する`AgentCore`の可変状態を守る共通ロックがない。

特に以下は`AgentCore.run_cycle_streaming()`内部のthread lockより前に設定されるため、別セッションが待機中でも上書きされ得る。

- `agent.set_interrupt_event(...)`
- `tool_handler.set_active_session_type(...)`
- heartbeat時の一時model swap

`AgentCore`のthread lockはcycle本体を直列化するが、DigitalAnima側の事前状態設定までは守っていない。

### 3. Streaming recovery is not idempotent

`core/supervisor/runner.py`の`_recover_streaming_journal()`は、復旧可能なchat journalがあるとconversation memoryへassistant turnを追加し、activityへrecovery logを書く。既に同じjournalを復元済みかどうかを確認していないため、復旧処理が再実行されると同一本文が再挿入され得る。

## Decided Approach

### 1. Commit streaming text only after completion_gate passes

- LiteLLM streamingの通常branchで、`iter_text`を`completion_gate`確認前に`all_response_text`へ入れない。
- gate未呼び出しでretryする場合、仮回答は最終`full_text`に残さない。
- Ollama streaming branchにも同等の扱いを入れる。
- `completion_gate`のチェック文言や`問題なし`系の内部指示が、最終応答に連結されないことをテストする。

### 2. Add a DigitalAnima-wide agent session lock

- `DigitalAnima`に`_agent_session_lock`を追加する。
- chat, heartbeat, cron, inboxで、`AgentCore`の可変状態を設定してcycleを実行する区間をこのロックで直列化する。
- 既存のconversation lock / background lockは役割ごとに残す。
- chat応答中にheartbeat/cron/inboxが開始されても、agent stateの事前設定が割り込まないことをテストする。

### 3. Make streaming recovery idempotent

- journal recovery前に、同じrecovered textが既にconversation memoryへ入っていないか確認する。
- 同一journalのactivity recovery logが既に存在する場合は、重複logを避ける。
- 既に復旧済みでもjournal自体はconfirmして、次回起動で再度復旧対象にならないようにする。
- 同じjournalを2回復旧してもassistant turnが1回だけ追加されることをテストする。

## Scope

In scope:

- `core/execution/_litellm_streaming.py`
- `core/anima.py`
- `core/_anima_messaging.py`
- `core/_anima_lifecycle.py`
- `core/_anima_inbox.py`
- `core/supervisor/runner.py`
- 関連unit tests

Out of scope:

- Chatwork未返信ロジック自体の改善
- Google Calendar照合やSalesforce連携
- mei固有knowledgeの追加更新
- UI上に既にstream済みのdeltaを取り消す仕組み

## Acceptance Criteria

1. `completion_gate`未呼び出しによるretryが複数回発生しても、最終`cycle_done.full_text`や保存されるassistant responseに前回retryの仮回答が重複しない。
2. chat session実行中にheartbeat/cron/inboxが始まっても、`agent.set_interrupt_event()`と`active_session_type`が別セッションから上書きされない。
3. streaming journal recoveryを同一journalに対して2回走らせても、conversation memoryとactivity logに同じ復旧内容が重複挿入されない。
4. 既存のheartbeat/conversation並行性テストは、用途別lockの並行性を保ったまま通る。
5. 追加・既存の関連unit testsが通る。

## Implementation Notes

- `completion_gate`の修正では、streaming deltaとして既に送られたテキストの取り消しまでは扱わない。ここでは最終応答・永続化・復旧対象への重複混入を止める。
- `_agent_session_lock`はDigitalAnima層のlockであり、`AgentCore`のthread lockを置き換えない。
- recoveryの重複判定は完全なsemantic判定ではなく、同一journalの本文・metadata一致による実用的なidempotencyを優先する。
