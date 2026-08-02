# pi-fix3: Action Memory Gate fail_mode 段階移行ガイド

## Summary

Action Memory Gate (`core/memory/action_gate.py`) は、副作用ツール実行前に
関連 `[ACTION-RULE]` knowledge の読了を要求する。pi-fix3 で soft-fail 3ケース
（`no_matching_rule` / `search_failed` / `below_threshold`）の扱いを
`config.action_gate.fail_mode` で段階制御できるようにした。

**デフォルトは `open`（従来互換・fail-open）**。このフリートは vector 検索障害の
頻度実績が高く（FD 枯渇・repair ループ・CUDA 全滅等）、いきなり `close` にすると
検索インフラ障害＝全外部送信停止になり得るため。

## Config

`~/.animaworks/config.json`（または該当 data dir の config）:

```json
{
  "action_gate": {
    "fail_mode": "open",
    "no_rule_notify_cooldown_seconds": 21600
  }
}
```

| キー | 値 | 既定 |
|------|-----|------|
| `fail_mode` | `"open"` \| `"middle"` \| `"close"` | `"open"` |
| `no_rule_notify_cooldown_seconds` | `no_matching_rule` 通知の再送抑制秒 | `21600` (6h) |

スキーマ: `core.config.schemas.ActionGateConfig`

## 挙動マトリクス

| ケース | open | middle | close |
|--------|------|--------|-------|
| `search_failed`（検索例外） | 許可 + 構造化ログ | **ブロック** | **ブロック** |
| `no_matching_rule`（ルール0件） | 許可 + 構造化ログ | 許可 + warn ログ | **保留**（明示 allow 無ければブロック + 通知） |
| `below_threshold`（類似度 < 0.80） | 許可 + 構造化ログ | **読了/レビューフロー継続**（素通ししない） | 同左 |
| 正しくルール読了済み | 通過 | 通過 | 通過 |

## 構造化ログ（全モード共通）

soft-fail 時は必ず次を含む WARNING ログを出す（可観測性先行）:

```
action_gate_soft_fail anima=... tool=... fail_kind=... fail_mode=...
  would_block=... blocked=... score=...
```

- `fail_kind`: `no_matching_rule` | `search_failed` | `below_threshold`
- `would_block`: `close` なら止まっていたか
- `blocked`: 今回実際に止めたか

ログ検索例:

```bash
rg 'action_gate_soft_fail' ~/.animaworks/logs/  # パスは環境依存
rg 'action_gate_soft_fail.*would_block=True' ...
```

## 段階移行手順

### 1. open（リリース直後・現状）

- 何もしない。既定のまま。
- **観察**: `would_block=True` かつ `blocked=False` の頻度を数日〜1週間測る。
  - `search_failed` が多い → まだ middle に上げない（インフラ安定化優先）
  - `no_matching_rule` が多い → ACTION-RULE knowledge の整備を先に行う

### 2. middle へ

```json
{ "action_gate": { "fail_mode": "middle" } }
```

- 検索障害時のみ外部送信が止まる。ルール未整備はまだ通る。
- 観察: 業務影響（送信停止クレーム）と `search_failed` ログ。
- 戻し方: `"fail_mode": "open"` に戻して reload / 再起動。

### 3. close へ

```json
{ "action_gate": { "fail_mode": "close" } }
```

- ルール未整備の action は **保留**。
- 通知: 同一 anima × tool は `no_rule_notify_cooldown_seconds` で重複抑制。
  クールダウン後は再通知（永久無音凍結を防ぐ）。
- 解除経路（必須）:
  1. **正規**: knowledge に `[ACTION-RULE]` + `trigger_tools: <tool>` を追加し再 index
  2. **運用緊急**: セッション単位で明示 allow

```python
from pathlib import Path
from core.memory.action_gate import grant_no_rule_allow

grant_no_rule_allow(Path("~/.animaworks/animas/mei").expanduser(), "gmail_send")
```

状態は `{anima_dir}/run/action_memory_gate/{session}.json` の `no_rule_allows`。
保留トレイル: `{anima_dir}/run/action_memory_gate/no_rule_holds.jsonl`

- 戻し方: `"fail_mode": "middle"` または `"open"`。

## ロールバック

1. config の `action_gate.fail_mode` を `"open"` に戻す
2. 設定を再読込（プロセス再起動、または config reload 経路があればそれ）
3. コード差し戻しは不要（open が従来互換）

## スコープ外

- machine / execute_command / github の Gate 対象追加（別 Issue）
- pi-fix2 gated permissions との統合変更
