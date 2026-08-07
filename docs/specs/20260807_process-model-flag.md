# process_model flag・status.json保護仕様

## 1. 正本とschema

animaごとのprocess topologyの正本は `<anima_dir>/status.json` とする（B-07/B-08）。`config.json`、環境変数、DB、in-memory値を正本にしてはならない。

```json
{
  "process_model": "phase2",
  "task_process_isolation": {
    "cron": true,
    "heartbeat": false,
    "task": false,
    "background": false
  },
  "restart_requested": true
}
```

### 1.1 `process_model`

| 値 | 意味 |
|---|---|
| field欠落 | 後方互換のため`legacy` |
| `legacy` | 現runner内で全laneを実行し、現global vector workerを使う |
| `phase2` | DB所有はlegacyのまま。レーン別サブflagでtask runnerへ段階移行 |
| `phase3` | chatを含む全LLM/CLI laneをtask runnerへ移し、anima rootが自DBを排他所有 |

値はcase-sensitiveなstringに限定する。未知値、空文字、非stringは`legacy`へ黙ってfallbackしてはならない。resolverは `invalid` として理由を返し、稼働中animaは現在topologyを維持、新規start/restartは拒否してoperator-visible errorを出す。誤値をDB owner切替として適用しない。

### 1.2 `task_process_isolation`

Phase 2だけで使用するobjectで、keyは `cron | heartbeat | task | background`、valueはstrict booleanとする。resolverはまず`process_model`を検証し、`phase2`の場合だけsubflag objectを検証する。Phase 2でobject自体が欠落した場合は全keyを`false`、object内の欠落keyは`false`とする。objectが`null`、array、string等の場合、既知keyのvalueがboolean以外の場合、または未知keyがある場合は設定全体を`invalid`とし、`process_model`不正時と同じく現在topologyを維持して新規start/restartを拒否する。型不正をtruthy/falsey変換してはならない。意味は次のとおり。

| key | `true`時にtask runnerへ移す実行 |
|---|---|
| `cron` | scheduled cron、およびcron相当laneのinbox |
| `heartbeat` | scheduled/manual heartbeat |
| `task` | TaskExec/pending descriptor |
| `background` | background tool/LLM、およびconsolidation |

`process_model=legacy`ではsubflagの形や値を検証対象にせず、fieldがあれば無視して全てfalseとして解決しwarningを出す。`phase2`では上記strict validation後の各値を使い、chat/greet/bootstrapはlegacy側に残る。`phase3`でもsubflagの形や値を検証対象にせず、fieldがあればwarningを出した上で全laneをisolation済みとして解決する。phase3書込みtransactionでは `task_process_isolation` を削除する。古いwriterが不正なobjectを残してもresolverはphase3を優先し、stale subflagでlaneをlegacyへ戻さない。`process_model`自体が不正ならsubflagに関係なく常にinvalidである。

Phase 3のlane割当はchat/greet/bootstrap→`chat`、inbox→`cron`、consolidation→`background`であり、rootがLLMまたは外部CLIを実行する経路をゼロにする（B-05）。

### 1.3 有効設定の決定表

| `process_model` | subflag | effective topology |
|---|---|---|
| 欠落/`legacy` | 任意（malformed含む） | 全legacy。subflagは無視し、fieldがあればwarning |
| `phase2` | key欠落 | そのlaneはlegacy |
| `phase2` | key=`true` | そのlaneだけtask runner |
| `phase2` | subflag object/value/keyが不正 | invalid。現在topologyを変えずstart/restart拒否 |
| `phase3` | 任意（malformed含む） | 全task runner + root DB owner。subflagは無視 |
| 不正なprocess値/型 | 任意 | invalid。現在topologyを変えずstart/restart拒否 |

## 2. resolver拡張位置

現行は `core/config/resolver.py:23-75` が `status.json` を読み、field列挙でmodel設定だけを抽出し、`core/config/resolver.py:93-155` がstatusを最優先SSoTとしてmergeする。process fieldは現行schema `core/config/schemas.py:61-107` に存在しない。

後続実装では次を行う。

1. `core/config/schemas.py:61-107` 付近に `ProcessModel = Literal["legacy", "phase2", "phase3"]` とstrictなlane subflag modelを追加する。topology設定をLLM用`AnimaDefaults`へ混ぜない。
2. `core/config/resolver.py:23-75` と同じstatus loaderを使う `resolve_process_model_config(anima_dir)` を追加し、§1のdefault/validation/統合規則を一箇所で適用する。manager、root、UIがJSONを個別解釈してはならない。
3. process spawn/reconcile側はresolverのtyped結果だけを参照する。field変更を現runner内のmodel reloadだけで適用しない。

既存 `/api/animas/{name}/reload` は `server/routes/animas.py:633-671` からrunner `core/supervisor/runner.py:953-957`、`core/anima.py:498-507`、`core/memory/config_reader.py:27-80` へ進み、ModelConfigをhot reloadする経路である。このAPIはprocess topologyやDB ownershipを切り替えない。

## 3. 反映とrestart契約

management planeがprocess fieldを変更するときは、同じatomic status updateで `restart_requested=true` を設定する。反映経路は既存reconcile `core/supervisor/_mgr_reconcile.py:101-125` とし、flagをconsumeして自動restartする。単なるreload API呼出し、mtime検知、次回job開始によるlazy切替は禁止する。

reconcileは次の順序を守る。

1. statusをvalidationし、現在値とdesired topologyを比較する。
2. 新規job受付を停止し、実行中taskへIPC v2 graceを送る。
3. 対象animaを完全停止し、旧task pgid消滅、旧DB ownerのclose完了を確認する。
4. `phase3`へ移る場合だけglobal worker側の当該anima DB handleが閉じたことをfenceで確認する。**DB ownership切替はanima停止中だけ適用**する。
5. desired topologyで起動し、startup ACK後に受付を再開する。
6. 成功したrestart requestをclearする。失敗を空成功にせず、status/監査ログへerrorを残す。

Phase 2ではDB ownerを変更しない。phase3→phase2/legacy rollbackも同じ停止・close・handoff順序を逆向きに行う。新旧ownerが同時にDBをopenする瞬間を作らない。

現行reconcileはrestart前に `restart_requested` を消す（`core/supervisor/_mgr_reconcile.py:115-125`）。後続実装では失敗時にdesired topologyと失敗理由を保持し、再試行/人手修正を可能にする必要がある。

## 4. rollout、統合、rollback

1. 初期状態はfield欠落=`legacy`。
2. `process_model=phase2` とし、低リスクanimaで `cron` から1 keyずつtrueにする。カナリア中は `worker_pool_size=1` 固定。
3. `cron → heartbeat → task → background` を検証後、chat切出しとDB handoffの準備が整った時だけ `process_model=phase3` へ一括統合し、subflag objectを削除する。
4. 全anima phase3化後もlegacy/phase2実装を **1週間** 保持する。この間のrollbackはflag変更+自動restartで行える。
5. legacy削除は別PRとし、1週間の観測完了後に **takaの明示承認** をgateとする。削除PR merge後は`legacy` rollback不能になるため、resolver/schemaから値を除く変更も同PRで行う（C-08）。

## 5. status.jsonのmodel-facing file tool保護

### 5.1 本PRで保護する経路

`status.json`はreadableだが、anima自身の汎用file toolからはwrite/edit不可とする。deny rootへ追加するとreadまで壊すため、write-onlyの既存protected listを拡張する。

| 経路 | 保護位置 | 結果 |
|---|---|---|
| ToolHandler/MCP/LiteLLMの`write_memory_file`, `write_file`, `edit_file` | protected set `core/tooling/handler_base.py:82-92`; canonical判定 `core/tooling/handler_base.py:344-372`; own anima適用 `core/tooling/handler_perms.py:242-249` | `PermissionDenied`。`Path.resolve()`により自己statusへのsymlinkも拒否 |
| Mode S native Write/Edit | protected set `core/execution/_sdk_security.py:32-40`; check `core/execution/_sdk_security.py:66-150`; hook `core/execution/_sdk_hooks.py:795-819` | write/edit拒否、read許可 |

read pathはwrite flagを立てないため変更しない。回帰testは `tests/unit/tooling/test_handler.py` でstatus write拒否・内容不変・status read許可・通常knowledge write成功を、`tests/unit/execution/test_agent_sdk_security.py` でMode S status write拒否/read許可・通常knowledge write許可を検証する。

### 5.2 残存経路（本PRでは封鎖しない）

以下は調査記録であり、封鎖はスコープ外である。

| 残存経路 | 現状と理由 |
|---|---|
| `execute_command` / Mode S Bash | protected-file predicateを通らず、redirectやscriptでwrite可能（`core/tooling/handler_perms.py:362-474`, `core/execution/_sdk_security.py:153-283`）。command sandboxの仕様変更は別PR |
| Mode C shell / bwrap相当profile | deny有効時もMCP profileはanima rootを書込み可とし、file-specific read-onlyは`permissions.json`だけ（`core/execution/codex_sdk.py:1266-1315`）。denyなしworkspace-write/danger-full-accessも直接write可能 |
| Mode X Grok sandbox | anima rootが`read_write`で、条件によりsandbox自体を無効化する（`core/execution/grok_cli.py:317-385`） |
| superuser/debug mode | ToolHandler/Mode Sの保護を明示的にbypassする（`core/tooling/handler_perms.py:185-186`, `core/execution/_sdk_security.py:82-83`） |
| supervisorの汎用file toolによる配下anima status | descendant management fileとしてwrite許可が先に評価される（`core/tooling/handler.py:204-215`, `core/tooling/handler_perms.py:281-284`, `core/execution/_sdk_security.py:121-125`）。本PRの「animaが自分で書換える穴」とは別 |
| 専用subordinate management tool | enable/disable/model等の固定fieldを意図的にwriteする `core/tooling/handler_subordinate_control.py:35-64,104-134,260-286`。汎用file toolではなく管理API |
| human-origin workspace grant | 明示human origin gate後に`default_workspace`を更新する `core/tooling/handler_workspace.py:47-139,241-255` |
| trusted host/server/CLI/factory/migration/reconcile | management planeとして正当にwriteする。例: `core/anima_factory.py:468-570`, `server/routes/animas.py:427-470`, `core/config/cli.py:168-193,320-344`, `core/supervisor/_mgr_reconcile.py:101-125` |

残存shell経路があるため、本PRの保護は「全filesystem writeをsecurity boundaryとして防ぐ」ものではない。process flagの実運用writeは認証済みmanagement API/CLIに限定し、shell経路のread-only mount化は別Issueで扱う。

## 6. DB ownership safety

- `legacy`/`phase2`: global vector workerがDB owner。root/task runnerがdirect Chromaをopenしない。
- `phase3`: anima rootが自anima DBの唯一のowner。task runnerはroot Memory APIだけを使う。
- handoffは停止中のみ、旧owner close ACK→process/handle消滅確認→新owner openの順。
- flag parse error、restart失敗、close確認不能では旧ownerを維持し、新ownerをopenしない。errorを`UNAVAILABLE`として表面化する。
- `ANIMAWORKS_EMBED_URL`/`ANIMAWORKS_RERANK_URL`はrootがtask runnerへ明示注入し、欠落時はfail-closedとする。flagでlocal fallbackを有効化できない。

## 7. 決定事項トレーサビリティ

| ID | 本仕様での反映 |
|---|---|
| B-07 | status正本、enum/default/invalid、Phase 2 subflagとPhase 3統合 |
| B-08 | restart_requested、自動restart、停止中DB handoff、status保護 |
| C-08 | 1週間rollback猶予、legacy削除別PR、taka承認gate |
| B-05 | phase3の未列挙lane割当とroot LLMゼロ |
