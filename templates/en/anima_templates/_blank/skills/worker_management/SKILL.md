---
name: worker-management
description: >-
  Operational management skill for the AnimaWorks server process.
  Performs hot reload after code updates (server reload), restart of Anima processes,
  and server status checks (list of running Anima instances, memory usage).
  "Reload it," "Apply the update," "Reload again," "System status," "Restart the server," "Check processes"
---


# Skill: System Administration

## CLI Commands (Recommended)

`animaworks` Individual Anima management is possible via the CLI. **Prefer the CLI over direct API calls.**

```bash
# 個別Animaのリスタート（設定変更の反映等）
animaworks anima restart <name>

# ステータス確認（全体 or 個別）
animaworks anima status
animaworks anima status <name>

# モデル変更（root APIでstatusを更新 + 起動中ならreload）
animaworks anima set-model <name> <model>

# ロール変更
animaworks anima set-role <name> <role>

# Anima一覧
animaworks anima list

# 無効化 / 有効化
animaworks anima disable <name>
animaworks anima enable <name>

# 削除（--archive でバックアップ可）
animaworks anima delete <name>
```

### Common Use Cases

```bash
# config.json変更後に特定Animaだけリスタート
animaworks anima restart aoi

# モデルを変更して起動中プロセスに自動reload
animaworks anima set-model aoi claude-sonnet-5-5
```

## API Reference (When CLI Is Unavailable)

Base URL: `$ANIMAWORKS_SERVER_URL` (if not set, `http://localhost:18500`)

| Endpoint | Method | Purpose |
|--------------|---------|------|
| `/api/system/status` | GET | Check system status |
| `/api/system/reload` | POST | **Hot reload all anima** |
| `/api/animas` | GET | List anima |
| `/api/animas/{name}` | GET | Anima details |
| `/api/animas/{name}/restart` | POST | Restart individual anima |
| `/api/animas/{name}/stop` | POST | Stop individual anima |
| `/api/animas/{name}/start` | POST | Start stopped anima |
| `/api/animas/{name}/chat` | POST | Send message |
| `/api/animas/{name}/trigger` | POST | Execute heartbeat immediately |

## Reload Procedure (After Program Update)

```bash
curl -s -X POST "${ANIMAWORKS_SERVER_URL:-http://localhost:18500}"/api/system/reload | python3 -m json.tool
```

- `added`: Newly detected anima
- `refreshed`: Reloaded anima (file changes are reflected)
- `removed`: Anima deleted from disk
- **No server restart required. Configuration and prompt changes are reflected immediately via this endpoint**

## Notes

- Stopping a worker does not delete anima data (memory, configuration)
- **Do not perform operations that stop yourself**
- For individual operations, use CLI → API in that order of priority
