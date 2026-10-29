> 確認したコミット: b304b7dc

# 機能概観

AnimaWorks は、複数の Digital Anima が記憶、ツール、組織内メッセージを使って継続的に作業するための実行基盤である。各機能の実装詳細は、以下の担当章と[アーキテクチャ全体図](architecture/index.md)を参照する。

## 自律エージェント

Anima は定義ファイルと状態を持ち、chat、受信メッセージ、heartbeat、cron、task から実行される。プロセス構成は[process](architecture/process.md)、個別ファイルは[Anima のファイル](architecture/anima-files.md)を参照する。

## 記憶

会話履歴、現在の作業状態、長期記憶、共有知識を目的別に扱う。prompt への反映と Anima データの構成は[Anima のファイル](architecture/anima-files.md)と[prompt 構築](architecture/prompt.md)を参照する。

## マルチモデル実行

モデル名と per-anima 設定から6種類の実行モードを選び、SDK、CLI、または API で呼び出す。エンジンと fallback の概要は[モデル実行](architecture/execution.md)にまとめている。

## 組織

Anima は会社・role・supervisor を持ち、組織内で仕事を委任し、共有 workspace や channel を使う。権限と組織境界は[セキュリティ](security.md)、メッセージの仕組みは[メッセージング](architecture/messaging.md)を参照する。

## メッセージング

Anima 間の DM、共有 Board、外部サービス経由の連絡を扱う。Inbox はファイル変更通知で起動し、メッセージの集約・重複防止は[メッセージング](architecture/messaging.md)に記載する。

## タスク管理

タスクを共有 TaskStore に永続化し、委任・attempt・lease と Web Task Board を一元的に扱う。CLI と background task の役割は[タスク管理](architecture/tasks.md)を参照する。

## スキルとツール

MCP は trigger に応じて利用可能なツールを絞り、Anima ごとのスキル catalog は依頼に合わせて選択する。prompt と tool guide の構成は[prompt 構築](architecture/prompt.md)、`animaworks-tool` の引数は[ツール CLI リファレンス](reference/tool-cli.md)を参照する。

## Web UI

Web UI には Home、Chat、Animas、Activity、Logs、Settings、Board、Task Board、Users のページがある。API の一覧は[API リファレンス](reference/api.md)を参照する。

## キャラクターアセット

Anima はキャラクター画像や表情などのアセットを持ち、Web UI や会話表現で利用する。ファイル配置と Anima 定義は[Anima のファイル](architecture/anima-files.md)を参照する。

## セキュリティ

個別・全体の権限設定、tool 実行時の検査、外部連携の認証を組み合わせる。権限境界と設定方法は[セキュリティ](security.md)を参照する。

## プロセス管理

server と supervisor が Anima root、task runner の起動、通信、再起動を管理する。詳細は[プロセス構成](architecture/process.md)を参照する。

## CLI

`animaworks` は初期化、設定、Anima、タスク、記憶などの管理を提供する。コマンド名と引数の一覧は[CLI リファレンス](reference/cli.md)を参照する。

## 設定管理

全体設定、モデル選択、per-anima の `status.json`、権限設定を分けて管理する。設定値と既定値の一覧は[設定リファレンス](reference/config.md)を参照する。

## 運用

起動準備、ログ確認、データ保守、異常時の確認手順を提供する。運用手順は[運用ガイド](operations/index.md)を参照する。

## MCP

MCP の許可リスト `MCP_TOOL_NAMES` とトリガー・役割に応じた `resolve_tool_surface` は `core/tooling/surface.py` に集約されている。実際に公開される一覧はトリガーと Anima の実行条件によって異なる。
