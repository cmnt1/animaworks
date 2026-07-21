---
name: chatwork-tool
description: >-
  Chatwork連携ツール。メッセージ送受信・検索・未返信確認・ルーム一覧を行う。
  Use when: Chatworkでメッセージ送信、ルーム一覧取得、未返信確認、チャット検索、メンション対応が必要なとき。
tags: [communication, chatwork, external]
---

# Chatwork ツール

Chatworkのメッセージ送受信・検索・管理を行う外部ツール。

## 呼び出し方法

**Bash**: `animaworks-tool chatwork <サブコマンド> [引数]` で実行。構文は下記を参照。

## アクション一覧

### send — メッセージ送信
```bash
animaworks-tool chatwork send ROOM MESSAGE
```

### messages — メッセージ取得
```bash
animaworks-tool chatwork messages ROOM [-n 20]
```

### search — メッセージ検索
```bash
animaworks-tool chatwork search KEYWORD [-r ROOM] [-n 50]
```

### unreplied — 未返信メッセージ確認
```bash
animaworks-tool chatwork unreplied [--json]
```
- `include_toall` (任意, デフォルト: false): 全体宛メッセージを含めるか

### rooms — ルーム一覧
```bash
animaworks-tool chatwork rooms
```

### mentions — メンション取得
```bash
animaworks-tool chatwork mentions [--json]
```
- `include_toall` (任意, デフォルト: false): 全体宛メッセージを含めるか

### delete — メッセージ削除（自分の発言のみ）
```bash
animaworks-tool chatwork delete ROOM MESSAGE_ID
```

### sync — メッセージ同期（キャッシュ更新）
```bash
animaworks-tool chatwork sync [ROOM]
```

## CLI使用法

```bash
animaworks-tool chatwork send ROOM MESSAGE
animaworks-tool chatwork messages ROOM [-n 20]
animaworks-tool chatwork search KEYWORD [-r ROOM] [-n 50]
animaworks-tool chatwork unreplied [--json]
animaworks-tool chatwork rooms
animaworks-tool chatwork mentions [--json]
animaworks-tool chatwork delete ROOM MESSAGE_ID
animaworks-tool chatwork sync [ROOM]
animaworks-tool chatwork <サブコマンド> ... --as <identity>
```

## 注意事項

- 自分専用トークン `CHATWORK_API_TOKEN__<自分の名前>` で動作する。未登録の場合は使用不可
- `--as <identity>` は `chatwork_tool.grants` で委任された場合のみ利用可能。read 委任では write（send/delete 等）は不可
- roomはルーム名でもルームIDでも指定可能
