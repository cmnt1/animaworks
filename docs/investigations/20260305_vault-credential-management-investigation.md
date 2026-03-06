# Vault / Credential 管理ツール 徹底調査レポート

**調査日**: 2026-03-05  
**対象**: AnimaWorks プロジェクト (`/home/main/dev/animaworks-private`)

---

## 1. エグゼクティブサマリー

| 項目 | 結論 |
|------|------|
| **VaultManager** | `core/config/vault.py` に実装済み。PyNaCl SealedBox による暗号化 |
| **Animaツールとして公開** | **されていない**。schemas.py に vault 関連ツール定義なし |
| **Mode S (MCP)** | Vault ツールは **公開されていない** |
| **Anima による vault 読み書き** | **不可**。Anima は vault に直接アクセスできない |
| **vault.json の存在** | `~/.animaworks/vault.json` は **存在しない**（未初期化環境） |
| **最近の変更** | v0.4.10 (2026-03-04) で credential vault 暗号化を実装 |

---

## 2. core/config/vault.py — VaultManager 全機能

### 2.1 概要

- **暗号方式**: PyNaCl SealedBox（Curve25519 + X25519）
- **キーファイル**: `{data_dir}/vault.key`（秘密鍵、base64、mode 0o600）
- **Vault ファイル**: `{data_dir}/vault.json`（暗号化 credential ストア、mode 0o600）
- **フォールバック**: PyNaCl 未インストール時は平文パススルー（警告ログ付き）

### 2.2 主要メソッド

| メソッド | 説明 |
|---------|------|
| `generate_key()` | Curve25519 秘密鍵を生成し vault.key に保存 |
| `encrypt(plaintext)` | 平文を暗号化して base64 文字列で返す |
| `decrypt(ciphertext)` | base64 暗号文を復号して平文を返す |
| `store(section, key, value)` | vault.json の section に key=value を暗号化して保存 |
| `get(section, key)` | vault.json から key を取得して復号 |
| `delete(section, key)` | vault.json から key を削除 |
| `load_vault()` | vault.json を読み込み（生 JSON dict） |
| `save_vault(data)` | vault.json に書き込み（アトミック） |
| `encrypt_config_credentials(credentials)` | config の credentials 辞書を暗号化 |
| `decrypt_config_credentials(encrypted)` | 暗号化 credentials を復号 |
| `migrate_shared_credentials()` | `shared/credentials.json` → vault.json `shared` セクションへ移行 |

### 2.3 シングルトン

```python
get_vault_manager(data_dir=None)  # モジュールレベルシングルトン
invalidate_vault_cache()          # キャッシュリセット
```

### 2.4 Anima からの利用

**VaultManager は Anima のツールとして公開されていない**。Anima が `store()` / `get()` を直接呼ぶ手段はない。

---

## 3. core/tooling/schemas.py — ツール定義

### 3.1 vault / credential / secret 関連ツール

**存在しない**。schemas.py を全文検索した結果:

- `vault`, `credential`, `secret`, `key`, `password` を名前に含むツール定義は **0件**
- 唯一のヒットは `search_memory` の `query` パラメータ説明内の `"keyword"` のみ

### 3.2 定義済みツールカテゴリ

- MEMORY_TOOLS, CHANNEL_TOOLS, FILE_TOOLS, SEARCH_TOOLS
- NOTIFICATION_TOOLS, USE_TOOL, ADMIN_TOOLS, SUPERVISOR_TOOLS
- CHECK_PERMISSIONS_TOOLS, PROCEDURE_TOOLS, KNOWLEDGE_TOOLS
- SKILL_TOOLS, BACKGROUND_TASK_TOOLS, PLAN_TASKS_TOOLS, TASK_TOOLS

**vault 系ツールは含まれていない。**

---

## 4. core/tooling/handler.py — vault 関連ハンドリング

**vault 専用のハンドリングはない**。handler.py 内の vault 関連 grep は `args_keys` の 1 件のみ（無関係）。

---

## 5. core/tools/ — vault 関連ツール実装

**vault 専用のツールファイルは存在しない**。`*vault*` で検索しても 0 件。

### 5.1 外部ツールでの vault 利用

`core/tools/_base.py` の `get_credential()` が vault を **内部的に** 参照する:

```python
# 解決順序:
# 1. config.json credentials
# 2. vault.json (shared セクション、env_var をキーに検索)
# 3. shared/credentials.json (レガシー)
# 4. 環境変数
```

`_lookup_vault_credential(key)` は `vm.get("shared", key)` を呼ぶ。  
これは **ツール実装側の内部ロジック** であり、Anima が vault を直接操作するツールではない。

---

## 6. ~/.animaworks/vault.json — 実ファイル

**存在しない**。`~/.animaworks/` には以下があるが vault.json は含まれない:

- config.json, auth.json, index_meta.json
- credentials/ ディレクトリ
- animas/, common_skills/, common_knowledge/ 等

vault.json は初回 `store()` または `migrate_shared_credentials()` 実行時に作成される。

---

## 7. core/mcp/server.py — MCP 公開ツール

### 7.1 _EXPOSED_TOOL_NAMES

```python
_EXPOSED_TOOL_NAMES = frozenset({
    "send_message", "post_channel", "read_channel", "manage_channel",
    "read_dm_history", "add_task", "update_task", "list_tasks",
    "call_human", "search_memory", "report_procedure_outcome",
    "report_knowledge_outcome", "disable_subordinate", "enable_subordinate",
    "set_subordinate_model", "restart_subordinate", "org_dashboard",
    "ping_subordinate", "read_subordinate_state", "delegate_task",
    "task_tracker", "audit_subordinate", "skill", "plan_tasks",
    "check_background_task", "list_background_tasks",
})
```

**vault, credential, secret 関連ツールは含まれていない。**

### 7.2 Mode S での Vault 利用

**不可**。Mode S は MCP 経由でツールを呼ぶが、vault ツールは MCP に登録されていない。

---

## 8. Git ログ — 最近の vault/credential 関連コミット

### 8.1 vault 関連

```
8cc6ca1a feat: implement credential vault encryption with PyNaCl SealedBox
d9f806a8 fix: update credential resolver test to expect vault.json in error message
004f2cc6 feat: integrate credential vault into config, tools, server, and CLI (Phases 2-4)
d0316bc2 Merge feat/credential-vault-encryption: credential vault with PyNaCl SealedBox
```

### 8.2 credential 関連（抜粋）

```
32fd668d feat: get_credential()にshared/credentials.jsonフォールバックを追加
16c45b9e feat: 統一Credential管理 — config.json優先カスケードと汎用スキーマ
fb6c38e5 Merge issue-20260217-070929: クレデンシャルをshared/credentials.jsonに一元化
539197be feat: ConversationMemory LLM呼び出しにプロバイダ別credential適用
00a53943 feat: credential-aware _build_env() for Mode S per-Anima auth
```

### 8.3 直近 50 コミット内の vault/credential 関連

- v0.4.10 リリース (2026-03-04) に credential vault 暗号化が含まれる
- それ以前の credential 関連は主に config.json / shared/credentials.json の統合

---

## 9. スキル定義 — vault / credential / secret / apikey

### 9.1 ~/.animaworks/common_skills/

| スキル | 該当内容 |
|--------|----------|
| animaworks-guide | `animaworks config list --show-secrets`, `animaworks anima set-model ... --credential` |
| slack-tool | "Slack Bot Token は credentials に事前設定が必要" |
| google-calendar-tool | "credentials.json を ~/.animaworks/credentials/ に配置" |
| gmail-tool | "credentials.json と token.json が ~/.animaworks/ に配置" |
| chatwork-tool | "API Token は credentials に事前設定が必要" |
| aws-collector-tool | "AWS認証情報（環境変数またはcredentials）の設定が必要" |
| tool-creator | `get_credential()` の使用例、認証情報の取得方法 |

**vault 専用スキルはない**。credential は「設定方法」として言及されるのみ。

### 9.2 ~/.animaworks/animas/ritsu/

grep 結果は activity_log の `tool_result` や `list_tasks` の JSON のみ。  
vault / credential / secret / apikey を扱うスキルは **見つからない**。

---

## 10. クレデンシャル解決フロー（詳細）

```
get_credential(credential_name, tool_name, key_name, env_var)
    │
    ├─ 1. config.json credentials[credential_name]
    │      → api_key または keys[key_name]
    │
    ├─ 2. vault.json (env_var が指定されている場合)
    │      → vm.get("shared", env_var)
    │      ※ 例: env_var="CHATWORK_API_TOKEN" → vault["shared"]["CHATWORK_API_TOKEN"]
    │
    ├─ 3. shared/credentials.json (レガシー)
    │      → data[env_var]
    │
    ├─ 4. 環境変数 os.environ[env_var]
    │
    └─ 5. ToolConfigError（上記すべてで未解決の場合）
```

vault は **config.json に credential が無い場合のフォールバック** として使われる。  
各外部ツール（slack, chatwork, gmail 等）は `get_credential(..., env_var="XXX")` を呼び、内部で vault が参照される。

---

## 11. 結論と推奨

### 11.1 現状まとめ

| 観点 | 状態 |
|------|------|
| VaultManager 実装 | 実装済み（PyNaCl SealedBox） |
| Anima ツール公開 | **未公開** |
| Mode S MCP | **未公開** |
| Anima による vault 読み書き | **不可** |
| 管理者による vault 操作 | CLI サブコマンドなし（config 経由の get/set のみ） |
| vault.json 初期化 | 未使用環境ではファイル未作成 |

### 11.2 設計上の位置づけ

Vault は **インフラ層の credential ストア** として機能し、Anima には直接露出していない。

- 外部ツールが `get_credential()` 経由で vault を参照
- Anima は「vault に何が入っているか」「vault に書き込む」といった操作ができない
- セキュリティ上、Anima に vault 読み書きを許可していない設計と解釈できる

### 11.3 今後の拡張案（参考）

Anima に vault 操作を許可する場合:

1. `core/tooling/schemas.py` に `vault_get`, `vault_store`, `vault_list` 等のツール定義を追加
2. `core/tooling/handler.py` にハンドラを実装
3. `core/mcp/server.py` の `_EXPOSED_TOOL_NAMES` に追加（Mode S で使用する場合）
4. `permissions.md` で vault ツールの許可を制御

現状の設計では、vault は **人間管理者が config / env / 移行スクリプトで管理する前提** となっている。
