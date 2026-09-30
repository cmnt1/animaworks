> 確認したコミット: b304b7dc

# メッセージング

Anima 間のメッセージは `send_message` で宛先へ届ける。`intent` はメッセージの目的を示すメタデータで、Inbox の起動をふるい分ける用途には使わない。対話履歴は活動ログを中心に読み取り、共有設定によって DM 履歴を補う。

## 共有チャネルと会社境界

`post_channel` は shared channel に投稿し、`read_channel` はアクセス可能な最近の投稿を読む。channel の metadata で member、closed 状態、company scope を管理する。company が指定された open channel は、その会社内の Anima から見える範囲に限定される。DM と channel の送信経路、外部宛ての alias 解決は `core/messaging/` が担当する。

## 送信ルールと受信 dispatch

`send_message` は `report` / `question` intent を使い、同一 run では同じ宛先への2通目を拒否する。宛先数の上限はない。`post_channel` は同一 run で同じチャネルへ1回まで投稿できるが、run 間 cooldown はない。時間・日単位の送信予算や会話深度による送信拒否もない。`Messenger.send` はメッセージを activity log に記録し、深度を診断ログに記録する場合も配送を拒否しない。

受信側では `core/supervisor/inbox_rate_limiter.py` が Inbox JSON のファイル変更通知を監視し、未読があれば Inbox lane を起動する。同時実行は1本で、実行中に届いたメッセージは次の1回にまとめる。通知を取りこぼした場合に備え45秒ごとに再確認し、Provider エラー時は `rate_guard` の回復時間を待ちながら未読を保持する。`overflow_inbox` は容量保護として残る。

## 人間への通知と外部連携

`call_human` は人間への通知・確認依頼を送る経路である。セッションごとの確認キーを求めるモードがあり、実行時に発行されたキーを使って確認する。CLI / tool の利用方法は[CLI リファレンス](../reference/tool-cli.md)を参照する。

外部へのメッセージ送信は設定した Slack、Chatwork、Discord の宛先に対応し、Zoom は会議の音声連携に利用する。channel の設定と個別連携手順は[連携ガイド](../integrations/index.md)を参照する。
