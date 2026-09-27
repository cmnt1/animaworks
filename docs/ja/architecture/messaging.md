> 確認したコミット: b304b7dc

# メッセージング

Anima 間のメッセージは `send_message` で宛先へ届ける。メッセージには任意の `intent` を付けられ、inbox dispatcher は `delegation` などの intent と送信元を使って即時処理の要否を判断する。対話履歴は活動ログを中心に読み取り、共有設定によって DM 履歴を補う。

## 共有チャネルと会社境界

`post_channel` は shared channel に投稿し、`read_channel` はアクセス可能な最近の投稿を読む。channel の metadata で member、closed 状態、company scope を管理する。company が指定された open channel は、その会社内の Anima から見える範囲に限定される。DM と channel の送信経路、外部宛ての alias 解決は `core/messaging/` が担当する。

## 送信制限と受信 dispatch

送信時には次の3種類のチェックを使う。`send_message` の1実行あたり recipient 数は `max_recipients_per_run` に制限される。Anima 間の送信数は `max_outbound_per_hour` と日単位の上限で制御される。また、同じ Anima の組み合わせで短時間に会話が循環しないように depth limit を確認する。role ごとの既定値は `core/config/schemas.py`、Anima 固有の上書きは `status.json` にある。設定の全項目は[設定リファレンス](../reference/config.md)を参照する。

受信側では `core/supervisor/inbox_rate_limiter.py` が cooldown、cascade 検知、受信 intent を確認して inbox lane の起動を調整する。従って送信上限の判定と受信処理開始の抑制は、別の責務として実装されている。

| role | 1時間 | 24時間 | 1実行の宛先数 |
|---|---:|---:|---:|
| manager | 60 | 300 | 10 |
| engineer | 40 | 200 | 5 |
| writer / researcher | 30 | 150 | 3 |
| ops | 20 | 80 | 2 |
| general | 15 | 50 | 2 |

## 人間への通知と外部連携

`call_human` は人間への通知・確認依頼を送る経路である。セッションごとの確認キーを求めるモードがあり、実行時に発行されたキーを使って確認する。CLI / tool の利用方法は[CLI リファレンス](../reference/tool-cli.md)を参照する。

外部へのメッセージ送信は設定した Slack、Chatwork、Discord の宛先に対応し、Zoom は会議の音声連携に利用する。channel の設定と個別連携手順は[連携ガイド](../integrations/index.md)を参照する。
