> 確認したコミット: 193a5e72

# アクティビティログ

`core/memory/activity/` は、Anima のメッセージ、実行、記憶操作などを時系列に記録する。公開 API は `core/memory/activity/logger.py` の `ActivityLogger` であり、記録は `{anima_dir}/activity_log/{date}.jsonl` に追記される。

## エントリ

各 JSONL 行は1件のイベントである。基本項目は `ts`（時刻）、`type`（イベント種別）、`content`、`summary`、`from`、`to`、`channel`、`tool`、`meta`、`origin`、`origin_chain`、`ctx` である。空の値は保存時に省略される。内部では `from_person` と `to_person` を使い、JSON ではそれぞれ `from` と `to` として出力する。

イベント種別に閉じた列挙型はなく、呼び出し側が用途に応じて記録する。現在の代表例は次の通りである。

| 分類 | イベント例 |
|---|---|
| 会話・通信 | `message_received`、`response_sent`、`message_sent`、`channel_post`、`channel_read`、`human_notify`、`human_reply` |
| 実行・状態 | `tool_use`、`tool_result`、`error`、`heartbeat_start`、`heartbeat_end`、`heartbeat_reflection`、`cron_executed`、`inbox_processing_start`、`inbox_processing_end` |
| 記憶・統合 | `memory_write`、`issue_resolved`、`knowledge_outcome`、`knowledge_reconsolidated`、`procedure_reconsolidated`、`consolidation_start`、`consolidation_end` |
| タスク・スキル | `task_created`、`task_updated`、`task_exec_start`、`task_exec_end`、`skill_auto_created`、`skill_autolearn_summary` |

古い `dm_sent` と `dm_received` は読み込み時にそれぞれ `message_sent`、`message_received` として扱われる。

## ストリーミングジャーナル

`core/memory/conversation/streaming_journal.py` の `StreamingJournal` は、LLM 応答のストリーミング中にテキスト断片とツールの開始・終了を `shortterm/streaming_journal_{session_type}.jsonl` へ逐次記録する。通常終了時には `done` を記録してジャーナルを閉じる。プロセスが異常終了した場合、次回起動時に残った記録から応答テキストやツール実行状況を復旧できる。書込みは 500 文字到達時、または最終 flush から 1 秒経過時に行う。

## 保持とローテーション

`ActivityLogger` は検索・タイムライン表示などの読み出しも提供する。ログの保持量、期間、ローテーション時刻は `activity_log` 設定で管理し、実行は supervisor が担う。設定項目の一覧は[設定リファレンス](../reference/config.md)を参照する。
