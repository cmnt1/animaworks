> 確認したコミット: b304b7dc

# モデル実行

モデル名と per-anima の設定から実行モードを解決し、エンジンごとの SDK、CLI、または API 呼び出しに渡す。S、C、X、D、G は専用エンジンを使い、A は LiteLLM を通じて API モデルを実行する。

## 実行モード

| モード | 主なモデル名パターン | エンジン | 認証 | ツール実行 |
|---|---|---|---|---|
| S | `claude-*` | Claude Agent SDK | Claude のサブスクリプション、API key、Bedrock または Vertex AI の認証 | SDK の組み込み機能と MCP を利用し、AnimaWorks の tool handler と接続する。 |
| C | `codex/*`、`openai-codex/*` | Codex SDK / CLI | Codex CLI のログイン情報または設定済み provider credential | Codex 側の実行機能を使い、共通イベントと tool 記録に変換する。 |
| X | `grok/*` | Grok Build CLI | Grok CLI の認証 | CLI の ACP stream を介し、イベントと実行結果を共通化する。 |
| D | `cursor/*` | Cursor Agent CLI | Cursor CLI のログイン情報 | CLI の session と tool 実行を利用する。 |
| G | `gemini/*` | Gemini CLI | Google 側の CLI 認証 | CLI の実行結果を共通イベントとして扱う。 |
| A | `openai/*`、`azure/*`、`bedrock/*`、`google/*`、`vertex_ai/*` など | LiteLLM loop | provider の API key または cloud credential | LiteLLM の function/tool call を AnimaWorks の handler で実行する。 |

モデル名からの解決順は、`status.json` の明示的な per-anima 指定、`models.json`、`config.json` のモデル別 fallback、`core/config/model_mode.py` の既定パターンである。いずれにも一致しないモデルは A に解決される。個別の設定項目は[設定リファレンス](../reference/config.md)を参照する。

## 共通実行層と障害時の動作

各エンジンの実装は `core/execution/engines/` に置かれる。共通層の `core/execution/events.py`、`core/execution/session/session_store.py`、`process_runner.py`、`watchdog.py`、`tool_evidence.py`、`cli_stream.py` はイベント、セッション保存、プロセス制御、tool evidence を共通化する。エラー分類、プロセス終了、バイナリ探索、`clear_session`、応答・エラー判定も中間層で扱う。D と G もこの構成に含まれる。

watchdog は engine event が 1200 秒間届かなかった場合に idle と判定する。全実行時間を計る timeout ではない。rate limit や provider 過負荷の情報は `llm_rate_guard` に provider family ごとに共有され、他の Anima が同じ provider へ連続要求するのを抑える。この guard は読み書きに失敗しても通常の実行を止めない設計である。

主モデルに加え `fallback_model` または `fallback_models` を指定できる。認証・rate limit などの分類結果と fallback 設定に基づき、次の候補へ切り替える。heartbeat と cron には `background_model`、`background_credential`、`background_thinking_effort` を指定できる。

## コンテキストの管理

コンテキストの圧縮方法はエンジンごとに異なる。S は会話の基準量を保存して変化を追跡し、SDK の圧縮機能と idle 時の圧縮を利用する。C は閾値で現在の thread を破棄して新しい thread を開始する。X と D は再開 turn 数を記録し、10 turn で session をローテーションする。A は入力上限への接近や overflow 時に会話を要約し、短縮した履歴で再試行する。G は専用 CLI の session 動作に従い、共通の turn 制限付き session 保存は行わない。

per-anima の context threshold の既定値は 0.50、absolute ceiling は 0.75 である。タスク実行向けの compaction token threshold は 0 が既定で、上限回数の既定値は 6 である。モデル別の compaction threshold は `models.json` でも指定できる。

## 設計判断

- **エージェントループは自作しない。** tool use の反復はエンジン（Claude Agent SDK、Codex、各 CLI、LiteLLM）に任せ、AnimaWorks はその前後の共通処理（prompt 組み立て、権限、セッション、エラー分類、記録）だけを受け持つ。
