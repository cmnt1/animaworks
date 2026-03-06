---
name: google-calendar-tool
description: >-
  Googleカレンダー連携ツール。予定一覧取得・予定追加。OAuth2認証でCalendar APIに直接アクセス。
  「カレンダー」「予定」「スケジュール」「Google Calendar」「イベント」
tags: [calendar, google, schedule, external]
---

# Google Calendar ツール

GoogleカレンダーのイベントをOAuth2で直接操作する外部ツール。

## use_tool での呼び出し

```json
{"tool": "use_tool", "arguments": {"tool_name": "google_calendar", "action": "ACTION", "args": {...}}}
```

## アクション一覧

### list — 予定一覧取得
```json
{"tool_name": "google_calendar", "action": "list", "args": {"max_results": 20, "days": 7, "calendar_id": "primary"}}
```

| パラメータ | 型 | デフォルト | 説明 |
|-----------|-----|-----------|------|
| max_results | integer | 20 | 最大取得件数 |
| days | integer | 7 | 何日先まで取得するか |
| calendar_id | string | "primary" | カレンダーID |

### add — 予定追加
```json
{"tool_name": "google_calendar", "action": "add", "args": {"summary": "会議", "start": "2026-03-04T10:00:00+09:00", "end": "2026-03-04T11:00:00+09:00", "description": "週次定例", "location": "会議室A"}}
```

| パラメータ | 型 | 必須 | 説明 |
|-----------|-----|------|------|
| summary | string | Yes | イベントタイトル |
| start | string | Yes | 開始時刻（ISO8601またはYYYY-MM-DD） |
| end | string | Yes | 終了時刻（ISO8601またはYYYY-MM-DD） |
| description | string | No | 詳細説明 |
| location | string | No | 場所 |
| calendar_id | string | No | カレンダーID（デフォルト: primary） |
| attendees | array | No | 参加者メールアドレスのリスト |

## CLI使用法（Sモード）

```bash
animaworks-tool google_calendar list [-n 20] [-d 7] [--calendar-id primary]
animaworks-tool google_calendar add "会議" --start 2026-03-04T10:00:00+09:00 --end 2026-03-04T11:00:00+09:00
```

## 注意事項

- 初回使用時にOAuth2認証フローが必要
- credentials.json を ~/.animaworks/credentials/google_calendar/ に配置すること
- 終日イベントは start/end を YYYY-MM-DD 形式で指定
