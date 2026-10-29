> 確認したコミット: 581e20f1

# Slack 連携

Slack 連携は、Slack のイベントを Anima の inbox へ取り込み、設定に応じてメッセージ送信や検索等を行う。NAT 内のサーバーでは Socket Mode を利用できる。Webhook Mode を使う場合は、外部から到達可能な HTTPS endpoint が必要である。

## Slack App の準備

Slack API の App 設定で Bot を作成し、必要な Bot Token Scopes と受信イベントを追加する。受信イベントには、利用する範囲に応じてチャンネル、DM、グループ DM の message と `app_mention` を指定する。Socket Mode では Socket Mode を有効化し、`connections:write` を持つ App-Level Token を発行する。Webhook Mode では Event Subscriptions の Request URL に `/api/webhooks/slack/events` を登録し、Signing Secret を用意する。

必要な権限は実際に使う機能に絞る。読み取り・送信・ユーザー情報取得などの scope は、Slack App に登録するイベントと利用するツールの範囲に合わせて設定する。

## 資格情報

Bot Token は `SLACK_BOT_TOKEN`、Socket Mode の App-Level Token は `SLACK_APP_TOKEN`、Webhook の署名検証には `SLACK_SIGNING_SECRET` を使う。値は vault、共有 credentials、または環境変数などの資格情報管理方法に登録し、公開設定ファイルや文書へ実値を記載しない。Socket Mode 以外では App-Level Token は不要である。

## AnimaWorks の設定

`config.json` の `external_messaging.slack` で連携を有効化し、`mode` を `socket` または `webhook` にする。共有 Bot の `anima_mapping` は Slack channel ID から Anima 名への対応、`default_anima` は明示 mapping が無い場合の既定宛先である。値を空にした channel は既定 Anima へ流さず無視できる。設定項目の一覧は[設定リファレンスの external_messaging](../reference/config.md)を参照する。

```json
{
  "external_messaging": {
    "slack": {
      "enabled": true,
      "mode": "socket",
      "anima_mapping": {
        "C0123456789": "sample-anima"
      },
      "default_anima": ""
    }
  }
}
```

channel ID は Slack のチャンネル詳細から確認する。Bot は受信対象のチャンネルへ招待する。個別 Bot を利用する場合は、その資格情報が個別 Anima の名前空間に登録されていることを確認する。

## 接続と確認

Slack の接続設定を保存してから、サーバーを再起動するか、構成が対応していれば Slack の hot reload を実行する。サーバーログに接続成功が出ることを確認し、テスト用チャンネルからメッセージを送って、正しい Anima の inbox に届くことを確かめる。Webhook Mode は公開 endpoint、署名検証、イベント購読の全てを確認する。

届かない場合は `enabled` と `mode`、資格情報、channel ID と Anima の対応、Bot の招待状況、Slack App に登録したイベントと scope を順に確認する。Webhook の場合は Signing Secret と HTTPS 経路を確認する。受信を確認した後、外部返信や Board 同期を必要最小限の範囲で有効にする。
