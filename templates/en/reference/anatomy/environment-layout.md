## Runtime Data Directory

All runtime data is stored in `{data_dir}/`.

```
{data_dir}/
├── company/          # 会社のビジョン・方針（読み取り専用）
├── animas/          # 全社員のデータ
│   ├── {anima_name}/    # ← あなた自身
│   └── ...               # 他の社員
├── prompts/          # プロンプトテンプレート（キャラクター設計ガイド等）
├── vault.json        # 共有クレデンシャル保管庫
├── shared/           # 社員間の共有領域
│   ├── channels/     # Board共有チャネル（general.jsonl, ops.jsonl 等）
│   ├── credentials.json  # レガシー互換用フォールバック
│   ├── inbox/        # メッセージ受信箱
│   └── users/        # 共有ユーザー記憶（ユーザーごとのサブディレクトリ）
├── common_skills/    # 全社員共通スキル（読み取り専用）
└── tmp/              # 作業用ディレクトリ
    └── attachments/  # メッセージ添付ファイル
```

## Scope of Activity Rules

1. **Your own directory** (`{data_dir}/animas/{anima_name}/`): Read and write freely
2. **Shared area** (`{data_dir}/shared/`): Read and write. Used for sending and receiving messages and sharing user memory
3. **Common skills** (`{data_dir}/common_skills/`): Only top-level members (supervisor not set) can write. Other members have read-only access. Skills available to everyone
4. **Company information** (`{data_dir}/company/`): Only top-level members can write
5. **Prompts** (`{data_dir}/prompts/`): Read-only. Templates such as character design guides
6. **Other employees' directories**: Only accessible within the scope specified in permissions.json
7. **Subordinate directories** (supervisor only. Same permission for all subordinates: children, grandchildren, great-grandchildren, etc.):
   - **Management files**: `injection.md`, `cron.md`, `heartbeat.md`, `status.json` are **readable and writable** (necessary for organization operations: personnel orders and configuration changes)
   - **Status reference**: `activity_log/` and `state/current_state.md` are **read-only**. Check subordinate tasks using the authorized task tool. The master copy is managed by the host; direct editing is prohibited.
   - **identity.md**: **Read-only** (write-protected)
8. **Colleagues' activity_log**: `activity_log/` of colleagues with the same supervisor is readable (for validation). Writing is not allowed