> 確認したコミット: b304b7dc

# Anima のファイル

各 Anima は `~/.animaworks/animas/{name}/` にディレクトリを持つ。個性や行動方針、実行設定はテキストと JSON に分けて保存し、セッション中に更新される情報は `state/` に置く。

## 定義と設定

| ファイル | 役割 |
|---|---|
| `identity.md` | 人格、話し方、自己紹介など、Anima の恒常的な個性を記述する。 |
| `injection.md` | 専門性や追加の行動指針を記述し、system prompt に取り込む。 |
| `permissions.json` | 個別 Anima のツール、コマンド、ファイルアクセスに関する権限を表す。 |
| `status.json` | 有効状態、role、担当、モデル、認証、supervisor、heartbeat の有効化など、実行時に解決する per-anima 情報を保持する。 |
| `heartbeat.md` | heartbeat の指示と活動時間帯を記述する。実行間隔は全体設定または `status.json` の値から決まり、このファイルの本文からは設定しない。 |
| `cron.md` | 定期実行するタスクを見出しごとに記述する。スケジュールと実行内容は supervisor が読み取る。 |

`status.json` は ModelConfig に関わる per-anima 値の正本である。対応キーと既定値の一覧は[設定リファレンス](../reference/config.md)を参照する。`permissions.json` と全体の `permissions.global.json` が権限の判断に使われる。権限の境界と評価方法は[セキュリティ](../security.md)を参照する。

## 実行状態

| パス | 役割 |
|---|---|
| `state/current_state.md` | 進行中の作業、判断、次の手順などを保持する作業状態である。prompt に必要な範囲で取り込まれ、更新は状態ファイル用の lock を介して保護される。 |
| `state/task_queue.jsonl` | 旧形式のタスクデータが残る場合の移行入力である。現在のタスクの正本は共有 SQLite TaskStore であり、このファイルを実行時の別キューとして扱わない。 |
| `state/background_tasks/` | `animaworks-tool submit` で開始したバックグラウンド処理の状態と結果を保存する。完了結果は会話や後続の背景実行から通知・参照される。 |

Anima の長期記憶、会話履歴、スキルなどは用途別のサブディレクトリに分かれている。記憶の詳細は `docs/ja/memory/` の各章を参照する。

## 設計判断

- **記憶は Markdown ファイルで持つ。** AI が自然に読み書きでき、grep とも相性がよい。JSON は設定と状態に限る。
- **書庫型の記憶を採る。** 直近 N 件を prompt に詰める切り詰め型では記憶量に上限ができる。必要なものを検索して想起する書庫型なら、記憶は増え続けてよい。
- **権限は視野の制限である。** 知らないことがあるから他者に尋ねる。全員が全てを見られると組織は意味を失う。
