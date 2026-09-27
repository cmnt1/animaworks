# Rules Between Hierarchy Levels

Communication between Anima in AnimaWorks is governed by rules based on the organizational hierarchy.
This documentation defines the rules for each relationship (supervisor, subordinate, colleague, other department).

## Basic Principles

- All interactions within the organization are conducted via `send_message` (messaging)
- Direct sharing of internal state is prohibited. Compress and interpret in your own words before conveying
- Each message must clearly state its purpose. MUST include "what you want done" and "what you want to convey"

## Communication with Supervisors (Reports, Updates, Consultations)

A supervisor is the Anima specified in the `supervisor` field.
It is displayed in the "supervisor" section of the system prompt.

### MUST (Obligations)

- MUST report results upon task completion
- MUST promptly report any problems or blockers encountered during work
- MUST consult when a decision beyond your scope of judgment is required
- MUST confirm when instructions from a supervisor are unclear

### SHOULD (Recommended)

- SHOULD report intermediate progress for long-term tasks
- When reporting problems, SHOULD include "what happened," "what was tried," and "proposed solutions" as a set
- Keep reports concise. If details are needed, SHOULD write them in a file and send a reference

### Message Examples

Task completion report:
```
bob宛: APIエンドポイントの実装が完了しました。
- GET /api/users — ユーザー一覧取得
- POST /api/users — ユーザー新規作成
- テストも全件パス済みです。
次のタスクがあればご指示ください。
```

Problem report:
```
bob宛: DB接続でタイムアウトが頻発しています。
- 発生: 本日14:00頃から
- 試したこと: コネクションプールのサイズ拡大（改善せず）
- 推測: 同時接続数が上限に達している可能性
- 提案: コネクションプールの最大値を50→100に変更してよいか確認したいです。
```

Decision consultation:
```
alice宛: キャッシュ戦略について判断をお願いしたいです。
- 選択肢A: Redis導入（高速だがインフラコスト増）
- 選択肢B: ファイルキャッシュ（低コストだが速度に限界）
- 私の推奨はAですが、コスト面の判断はお任せします。
```

## Supervisor Tools

Anima with subordinates automatically have dedicated tools for organization management enabled.

### ツール一覧

| ツール | 対象範囲 | 概要 | 主なパラメータ |
|--------|---------|------|----------------|
| `org_dashboard` | 全配下（再帰） | 配下全体のプロセス状態・最終アクティビティ・現在タスク・タスク数をツリー表示 | なし |
| `ping_subordinate` | 全配下（再帰） | 配下の生存確認。`name` 省略で全員一括、指定で単一 Anima のみ | `name`（任意） |
| `read_subordinate_state` | 全配下（再帰） | 配下の `state/current_state.md` を読み取り | `name`（必須） |
| `delegate_task` | 直属部下のみ | 完全な実行入力と追跡参照を原子的に登録し、部下へ通知 | `name`, `instruction`（必須）, `summary`, `acceptance_criteria`, `workspace`, `model`（任意） |
| `task_tracker` | 自分の委譲タスク | `delegate_task` で委譲したタスクの進捗を配下側キューから追跡 | `status`（任意: "all"/"active"/"completed", デフォルト "active"） |
| `audit_subordinate` | 全配下（再帰） | 活動タイムラインまたは統計サマリーを生成。`name` 省略で全配下を一括監査（統合タイムライン） | `name`（任意）, `mode`（任意: `"report"`/`"summary"`, デフォルト `"report"`）, `hours`（任意: 1〜168, デフォルト 24）, `direct_only`（任意: boolean）, `since`（任意: `"HH:MM"` 当日の開始時刻、指定時はhoursより優先） |
| `disable_subordinate` | 全配下（再帰） | 配下を休止（status.json enabled=false、約30秒でプロセス停止） | `name`（必須）, `reason`（任意） |
| `enable_subordinate` | 全配下（再帰） | 休止した配下を再開 | `name`（必須） |
| `set_subordinate_model` | 全配下（再帰） | 配下のモデルを変更（status.json 更新。反映には `restart_subordinate` が必要） | `name`, `model`（必須）, `reason`（任意） |
| `set_subordinate_background_model` | 全配下（再帰） | 配下のバックグラウンドモデル（Heartbeat/Cron用。Inboxはメイン）を変更。空文字でクリア。反映には `restart_subordinate` が必要 | `name`, `model`（必須）, `credential`, `reason`（任意） |
| `restart_subordinate` | 全配下（再帰） | 配下プロセスを再起動（restart_requested フラグ、約30秒で再起動） | `name`（必須）, `reason`（任意） |

`check_permissions` は全 Anima が利用可能（自分の権限一覧を確認）。

### Task Delegation Flow

1. Execute `delegate_task(name="dave", instruction="目的・成果物・制約・期限・必要な文脈", acceptance_criteria=["確認可能な完了条件"])`.
2. The complete input and tracking reference are atomically registered in the regular task store.
3. The worker checks dependencies and available capacity, then retrieves executable tasks.
4. Notify dave via DM. The DM is not execution input and should not be used as material to regenerate missing tasks.
5. Your delegation tracking entry is a reference to the same task, not a separate mutable copy.
6. Track ongoing delegated tasks with `task_tracker(status="active")` (`status="all"` for all, `status="completed"` for completed only)

### Checking Subordinate Status (should be done regularly)

```
org_dashboard()                        # 配下全体の状態をツリー表示
read_subordinate_state(name="dave")    # dave の現在タスクと保留タスクを確認
ping_subordinate()                     # 全員の生存確認
audit_subordinate(name="dave")         # dave の直近24時間の活動タイムライン
audit_subordinate(name="dave", mode="summary", hours=168)  # dave の直近7日間の統計サマリー
audit_subordinate()                    # 全配下の統合タイムライン（直近24時間）
audit_subordinate(direct_only=true)    # 直属部下のみの統合タイムライン
audit_subordinate(since="09:00")       # 全配下の今日9時以降の統合タイムライン
audit_subordinate(name="dave", since="13:00")  # dave の今日13時以降
```

#### audit_subordinate Modes

| Mode | Output Content | Use Case |
|--------|---------|------|
| `report` (default) | Chronological timeline. Displays icon, time, and content for each event. Tool usage is shown as a summary at the bottom | Understanding "what was done today" |
| `summary` | Statistical display of event counts, task status, communication partners, and error details | Quantitative activity assessment |

When `name` is omitted and multiple Anima are targeted, the `report` mode generates a **merged timeline** that combines events from all Anima in chronological order.

### Organization Expansion (Creating New Anima)

Anima holding `skills/newstaff/SKILL.md` can create new Anima using the `create_anima` tool.
Specify a character sheet (`character_sheet_content` or `character_sheet_path`),
and after creation, it is automatically registered in config.json and activated upon server reload.
If `supervisor` is omitted, the calling Anima is set as the supervisor.

## Communication with Subordinates (Instructions, Confirmations)

Subordinates are the Anima displayed in the "subordinates" section of the system prompt.
All Anima that set you as `supervisor` fall under this category.

### MUST (Obligations)

- When giving task instructions, MUST include the following:
  - **Purpose**: Why this task is needed
  - **Expected deliverable**: What to create or what to do
  - **Deliverable path**: The delegatee's own directory or `common_knowledge/` (your own `knowledge/` cannot be specified — subordinates cannot write to it)
  - **Deadline and priority**: By when, and how urgent
- Upon receiving a subordinate's completion report, MUST provide feedback on the results
- MUST regularly check subordinate status with `org_dashboard`

### SHOULD (Recommended)

- SHOULD assign tasks considering the subordinate's speciality
- Instructions should be specific. SHOULD avoid vague expressions (e.g., "make it look nice")
- When there are multiple subordinates, SHOULD organize task dependencies before giving instructions

### MAY (Optional)

- MAY assign slightly challenging tasks for subordinate growth
- When collaboration between subordinates is needed, MAY specify the parties involved in the instruction

### Message Examples

Task instruction:
```
dave宛: ユーザー認証APIの実装をお願いします。
- 目的: フロントエンドからのログイン機能を実現するため
- 成果物: POST /api/auth/login エンドポイント（JWT返却）
- 仕様: メールアドレス+パスワードでの認証。失敗時は401を返す
- 期限: 今週金曜まで
- 関連: eve がフロントエンド側のログイン画面を並行で作成中です。
  API仕様の質問があれば eve と直接やりとりして構いません。
```

Confirmation and feedback:
```
dave宛: 認証APIの実装、確認しました。
- ログイン・ログアウトとも正常動作を確認
- 1点: トークンの有効期限が設定されていないようです。24時間で期限切れにしてください
- それ以外は問題ありません。修正後に再度報告をお願いします。
```

## Communication with Colleagues (Collaboration, Coordination)

Colleagues are Anima with the same `supervisor`.
They are displayed in the "colleagues" section of the system prompt.

### SHOULD (Recommended)

- SHOULD communicate directly with colleagues handling related work
- SHOULD share in advance when your work affects a colleague's work
- In joint work, SHOULD clarify who is responsible for what

### MAY (Optional)

- MAY consult colleagues on insights related to their speciality
- MAY request reviews or opinions

### Message Examples

Collaboration request:
```
eve宛: 認証APIの実装が完了したので共有します。
- エンドポイント: POST /api/auth/login
- リクエスト: { "email": "...", "password": "..." }
- レスポンス: { "token": "JWT文字列", "expires_in": 86400 }
- エラー時: 401 { "error": "Invalid credentials" }
フロントエンド側のログイン画面で使ってください。質問があればいつでもどうぞ。
```

Consultation:
```
carol宛: 管理画面のUIについて相談したいのですが、
ユーザー一覧画面のテーブルレイアウトについて、
20列以上のカラムがあるのですが、どう表示するのが良いでしょうか。
あなたのUXの観点からアドバイスいただけると助かります。
```

## Communication with Members of Other Departments

Other departments refer to Anima with a different `supervisor` from yours.
Anima not displayed in the colleagues section fall under this category.

### MUST (Obligations)

- MUST generally not contact members of other departments directly
- When coordination with another department is needed, MUST inform your supervisor
- The contact goes through your supervisor to the other department's supervisor, who then issues instructions to the relevant person

### Communication Path

Example: dave (under bob) wants to contact frank (under carol)

```
正しい経路:
  dave → bob(自分の上司) → alice(共通の上司) → carol(frankの上司) → frank

間違い:
  dave → frank（直接連絡は禁止）
```

### Message Example

Request to supervisor (when cross-department coordination is needed):
```
bob宛: 顧客データのエクスポート機能について、
営業部の frank さんが必要とするCSVフォーマットの詳細を知りたいです。
carol さん経由で確認していただけますか？
```

### Why Direct Contact Is Avoided

- The supervisor loses visibility of the overall picture of the work
- The chain of command becomes confused, with a risk of contradictory instructions
- Department supervisors lose the opportunity to assess priorities

## Top-Level Anima Contacting Humans

Top-level Anima without a configured supervisor have the responsibility to contact human administrators directly.
Use the `call_human` tool for contact.

### MUST (Obligations)

- MUST contact via `call_human` when detecting problems, errors, or failures
- MUST report when a decision beyond your scope of judgment is required
- MUST report matters escalated from subordinates that you cannot resolve yourself

### SHOULD (Recommended)

- SHOULD report when important tasks are completed
- SHOULD report when there are concerns about subordinate work status

### MAY (Optional)

- MAY not report when routine patrols find no particular issues
- MAY not report when minor automatic repairs have been completed

### Message Examples

Problem report:
```
call_human:
  subject: "本番環境のAPI応答遅延を検出"
  body: |
    14:00頃からAPIの応答時間が通常の3倍に増加しています。
    - 影響: ユーザー向けAPIの全エンドポイント
    - 試したこと: コネクションプールの状態確認（異常なし）
    - 推測: DBサーバーの負荷が高い可能性
    - 提案: DBサーバーのスケールアップを検討してください
  priority: high
```

Decision request:
```
call_human:
  subject: "新機能リリースの承認依頼"
  body: |
    ユーザー認証機能の実装が完了し、全テストがパスしました。
    本番環境へのリリースについて承認をお願いします。
  priority: normal
```

## Exception Rules for Emergencies

The following exceptions apply to the normal hierarchy rules.

### Definition of an Emergency

The exception rules MAY be applied as an "emergency" when the following apply:

- A system failure or service outage is occurring
- A security incident is occurring
- A supervisor has been unresponsive for an extended period
- A deadline is approaching and cannot be met through the normal path

### Actions Permitted in Emergencies

- MAY contact members of other departments directly (but MUST report to your supervisor afterward)
- MAY bypass your supervisor and contact their supervisor directly (but MUST also report to your direct supervisor)
- MAY make decisions yourself that would normally require consultation (but MUST report and obtain approval afterward)

### Emergency Contact Message Example

```
frank宛: 【緊急】dave です。通常は上司経由ですが、緊急のためご連絡します。
本番環境でユーザーデータの不整合が発生しています。
営業側で顧客から問い合わせが来ていないか確認していただけますか？
bob と carol にも同時に報告しています。
```

Post-incident report to supervisor:
```
bob宛: 【事後報告】本番障害の対応で、frank さん（carol配下）に直接連絡しました。
- 理由: 顧客データ不整合の影響範囲を緊急確認する必要があった
- 対応内容: frank さんに顧客からの問い合わせ状況を確認依頼
- 結果: 3件の問い合わせが来ており、frank さんが対応中
事後報告となり申し訳ありませんが、ご確認をお願いします。
```

## Summary of Rule Priorities

| Priority | Rule | Classification |
|--------|--------|------|
| 1 | Report problems and escalate to supervisor | MUST |
| 2 | Report task completion | MUST |
| 3 | Include purpose, deliverable, and deadline in instructions to subordinates | MUST |
| 4 | No direct contact with other departments | MUST |
| 5 | Direct collaboration with colleagues | SHOULD |
| 6 | Report intermediate progress | SHOULD |
| 7 | Apply emergency exceptions | MAY |