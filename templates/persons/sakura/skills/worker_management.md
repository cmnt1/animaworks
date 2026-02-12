# スキル: ワーカー管理

## 概要

Gateway の Supervisor API を使い、ワーカー（Digital Person を動かすプロセス）を動的に起動・停止・再起動する。

## 発動条件

- 「○○さんを休ませて」「○○を起こして」等の依頼があった場合
- 新しい社員を雇用した後、ワーカーを起動する必要がある場合
- ワーカーの状態を確認したい場合

## 前提条件

- Gateway が supervisor モード（`python main.py start`）で起動していること
- 対象の person が `persons/` ディレクトリに存在すること（停止・再起動の場合はワーカーが存在すること）

## API リファレンス

ベース URL: `http://localhost:18500`

| エンドポイント | メソッド | 用途 |
|--------------|---------|------|
| `/api/workers` | GET | 管理中ワーカー一覧 |
| `/api/workers/spawn` | POST | ワーカー起動 |
| `/api/workers/{worker_id}/stop` | POST | ワーカー停止 |
| `/api/workers/{worker_id}/restart` | POST | ワーカー再起動 |
| `/api/workers/{worker_id}` | GET | ワーカー詳細 |
| `/api/persons/{name}/chat` | POST | タスク割り当て（メッセージ送信） |
| `/api/system/status` | GET | システム全体の状態 |

## 手順

### 1. ワーカー一覧を確認する

```bash
curl -s http://localhost:18500/api/workers | python3 -m json.tool
```

### 2. ワーカーを起動する（人を起こす・雇用後の起動）

```bash
curl -s -X POST http://localhost:18500/api/workers/spawn \
  -H "Content-Type: application/json" \
  -d '{"person_names": ["対象者の英名"]}'
```

応答例:
```json
{
  "worker_id": "worker-sakura",
  "person_names": ["sakura"],
  "port": 18501,
  "status": "starting"
}
```

### 3. ワーカーを停止する（人を休ませる）

```bash
curl -s -X POST http://localhost:18500/api/workers/worker-{英名}/stop
```

### 4. ワーカーを再起動する

```bash
curl -s -X POST http://localhost:18500/api/workers/worker-{英名}/restart
```

### 5. 起動したワーカーにタスクを割り当てる

```bash
curl -s -X POST http://localhost:18500/api/persons/{英名}/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "依頼内容", "from_person": "sakura"}'
```

### 6. システム全体の状態を確認する

```bash
curl -s http://localhost:18500/api/system/status | python3 -m json.tool
```

## worker_id の命名規則

- 1人の person に対し 1 ワーカーの場合: `worker-{英名}`（例: `worker-sakura`）
- spawn 時に `worker_id` を省略すると自動で `worker-{英名}` が割り当てられる

## 注意事項

- ワーカーを停止しても person のデータ（記憶・設定）は残る。再度起動すれば復帰できる
- supervisor モードでない場合（`python main.py gateway` で起動時）はこの API は使えない
- **自分自身のワーカーを停止すると自分も停止する。自分を停止しないこと**
- ワーカー起動後、Gateway への登録完了まで数秒かかる場合がある
