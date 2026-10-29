> 確認したコミット: 581e20f1

# Zoom RTMS 連携

Zoom RTMS は会議のトランスクリプトを WebSocket で受信し、設定された Anima の inbox へチャンクとして渡す。AnimaWorks はこの経路で会議へ参加して発言するのではなく、受信した文字起こしを処理する。

## 前提

- Zoom 側で RTMS に対応した App とイベント購読を設定する。
- Zoom から届く webhook 用に、サーバーが外部から到達可能な HTTPS endpoint を用意する。
- `ZOOM_SECRET_TOKEN` を署名検証と URL validation に使用し、RTMS 接続用の `ZOOM_CLIENT_ID` と `ZOOM_CLIENT_SECRET` を資格情報として登録する。
- AnimaWorks の設定と資格情報は、値を公開せず安全な保管場所へ登録する。

Zoom の契約条件、RTMS 利用可否、文字起こしの利用条件はアカウントと Zoom 側の設定で確認する。参加者への通知や同意の要件にも従う。

## AnimaWorks の設定

`config.json` の `external_messaging.zoom` で `enabled` を有効にする。`meeting_mapping` は会議 ID から受信先 Anima への対応表であり、対応が無い会議には `default_anima` が使われる。どちらにも割り当てられない場合は受信先がない。チャンク間隔と文字数上限は用途に応じて調整する。項目と既定値は[設定リファレンス](../reference/config.md)を参照する。

```json
{
  "external_messaging": {
    "zoom": {
      "enabled": true,
      "default_anima": "sample-anima",
      "meeting_mapping": {
        "1234567890": "sample-anima"
      },
      "chunk_interval_seconds": 300,
      "chunk_max_chars": 4000
    }
  }
}
```

資格情報と設定を保存してからサーバーを起動または再起動する。Zoom の webhook URL は `/api/webhooks/zoom` を登録する。署名検証と webhook 受信、RTMS stream の接続ログを確認してからテスト会議を行う。

## 運用確認

`/api/system/health` の Zoom gateway 情報とサーバーログで接続・最終受信を確認する。テスト会議では文字起こしが生成されていること、受信先の inbox に transcript メッセージが届くことを確認する。取り込みと Anima の応答処理は別段階であるため、inbox に届いた後の応答が遅い場合は Anima 側の実行状態も確認する。

受信しない場合は、Webhook が HTTPS で到達するか、URL validation が成功するか、署名用 Secret Token と Client ID / Secret が一致するか、Zoom 側で RTMS と transcript が利用可能かを確認する。会議 ID が `meeting_mapping` と一致するか、`default_anima` が指定されているかも確認する。
