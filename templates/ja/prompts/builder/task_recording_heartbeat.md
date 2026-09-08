### Heartbeat でのタスク記録

- 継続タスクは `pending` として読み、同じ task_id で `submit_tasks` に投入して既に承認された範囲を継続する。`done` への更新は完了条件の証跡を確認した後のみ行う
- Anima間の委任もタスクキューに記録し、relay_chainを更新せよ
- タスク完了時は `update_task` でステータスを更新せよ
