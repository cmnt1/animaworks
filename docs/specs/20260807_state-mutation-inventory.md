# anima state mutation棚卸し・lease v2仕様

## 1. 所有権の原則

本表は現HEAD `b2586dcc0a87981cb3c3d2eeb57be500a89aea1c` の書込み経路を対象とする。

- Phase 2はstateの直接書込みを維持する。ただしカナリア中は `background_task.worker_pool_size=1` に固定し、`current_state.md` とconversation JSONにはプロセス間advisory lockを追加する（A-06/C-04）。
- busy sidecarはPhase 2からrootが唯一のwriterとなる。task runnerの既存busy helperはDIで無効化し、IPC progressだけをrootへ送る（A-03/A-04/B-02/C-01）。
- Phase 3はconversation stateと`index_meta.json`をroot APIへ移す。完成形ではmemory/state mutationをroot APIへ集約する。ただしStreamingJournal、stream checkpoint、engine resume情報はtask runnerの単一writerを維持し、終了前fsyncを必須にする（A-08/C-06）。
- `status.json`はmanagement planeの正本であり、本PRではmodel-facing file toolによる自己書込みだけを拒否する。詳細は `20260807_process-model-flag.md` に記す。

## 2. 必須stateの棚卸し

| file/resource | 現行writer（process・コード位置） | 現行排他/耐障害性 | Phase 2 | Phase 3 |
|---|---|---|---|---|
| `state/current_state.md` | runner/model tool: `core/memory/manager.py:460-461`, `core/tooling/handler_files.py:461-477,538-593`, `core/tooling/handler_memory.py:868-969,1107-1114`; HB: `core/_anima_heartbeat.py:406-425`; conversation finalize: `core/memory/conversation_finalize.py:264-278`; server housekeeping: `core/memory/taskboard_housekeeping.py:228-270,555-575` | atomic replaceまたはplain write。tool経路だけprocess内`threading.Lock`（`core/anima.py:124-135`, `core/tooling/handler.py:461-481`）。プロセス間排他なし | **advisory lock追加対象**。全writerがread-modify-write全体を同じlockで囲む | root state API、root sole-writer |
| `state/conversation.json`, `state/conversations/{thread}.json` | runner `ConversationMemory`。path/cache/lock: `core/memory/conversation.py:103-131`; save: `178-190`; clear: `293-296` | thread別`asyncio.Lock`はprocess内のみ。cached whole-fileをatomic replaceするため複数processでlost updateし得る | **advisory lock追加対象**。lock取得後にdiskから再loadし、mutationとreplaceまで保持。カナリアpool=1 | 決定済みroot conversation API、root sole-writer |
| `transcripts/{date}.jsonl` | runner `ConversationMemory.write_transcript`: `core/memory/conversation.py:227-264` | append+flush+fsync、lockなし | conversation lane規律下の直接append。conversation lock範囲に参加 | root conversation API経由append |
| `index_meta.json` | runner/vector indexer `core/memory/rag/indexer.py:257-263,518-523,684-687`; shared hash RMW `core/memory/rag_search.py:74-86,231-251,266-294,316-346,387-406`; server daily index `core/supervisor/_mgr_scheduler.py:667-803`; repair `core/memory/rag/repair_rebuild.py:179-184,289-293`; skill curator `core/skills/curator.py:491-501` | 一部plain truncate、複数経路の無lock RMW | vector worker所有は現行のまま。直接writeを維持し既存競合を既知リスクとして扱う | 決定済みroot Memory API sole-writer。DB操作成功後だけmetadata commit |
| `vectordb/**` | global vector worker `core/memory/rag/vector_worker.py:51-54,217-247`; repair staging/swap `core/memory/rag/repair_rebuild.py:218-283` | worker内`ThreadPoolExecutor(max_workers=1)`。repair operationは`state/rag_repair.lock`（`core/memory/rag/repair_utils.py:120-136`） | global worker/proxy維持 | anima rootごとの単一client/単一worker thread/有界queue。staging repair subprocessだけdirect access可 |
| `run/animas/{name}.busy.json` | 現runner `DigitalAnima`: write `core/anima.py:318-385`; clear `389-408`; server reader/kill `core/supervisor/_mgr_health.py:37-75,180-237,627-639` | PID付きtemp+replace、lockなし。子がhelperを使うと相互上書き可能 | **root sole-writer**。既存payload、root PID、lane名を維持。task healthはroot registryで判定し当該pgidだけkill | 同左。server supervisorはroot healthだけ監視 |
| `state/task_queue.jsonl`, `task_queue_archive.jsonl` | runner/tool/serverの `TaskQueueManager`: `core/memory/task_queue.py:147-165,208-342,351-457`; pending同期 `core/supervisor/pending_executor.py:429-456`; server API `server/routes/taskboard.py:292-310` | appendはprocess内lock + `.lock` advisory lockを試行してfsyncする（`core/memory/task_queue.py:890-938`）。ただしlock file open/acquire失敗時は現実装が**無lockへfail-open**し、`compact()`のarchive/rewriteもlock外（`845-886`） | 既存方式を基礎にするが、後続lock実装ではfail-closed化。pool=1。`compact()`も同lock対象 | root task/state API sole-writer |
| `shared/taskboard.sqlite3` | server API、runner queue同期、goal/housekeepingから `TaskBoardStore`; write `core/taskboard/store.py:167-263,265-346,388-432` | SQLite transaction + WAL、短命connection（`core/taskboard/store.py:104-129`）。queueとの跨りtransactionなし | SQLiteのwriter serializationを維持 | fleet/UI DBはserver所有、anima更新はroot API。後続PRでownerを一意にする |
| `state/pending/**`, `state/background_tasks/pending/**` descriptor | tool/SDK/MCP/server作成: `core/tools/__init__.py:152-231`, `core/tooling/handler_delegation.py:240-263`, `core/execution/_sdk_hooks.py:155-203,358-379`, `core/goals/manager.py:171-220`; runner claim/move/delete `core/supervisor/pending_executor.py:921-1133` | pending→processingのrenameがclaim。process内active setだけでprocess間CASなし | 直接descriptor維持、pool=1。root registryのjob/attemptと対応させる | root task API、root sole-writer |
| `state/background_tasks/{task_id}.json` | runner `BackgroundTaskManager._save_task`: `core/background.py:187-264,300-380,443-452` | plain overwrite、lock/atomic replaceなし | task IDごとの直接write。pool=1 | root task registry/API sole-writer |
| `state/task_results/{task_id}.md` | runner pending executor write `core/supervisor/pending_executor.py:402-410`; inboxはread-only `core/_anima_inbox.py:234-260`; server housekeeping delete `core/memory/housekeeping.py:1457-1484` | task IDごとのplain overwrite、retention deleteと共通lockなし | task runner単一writer + server retention cleanup。実行中task IDは削除対象外にfence | root task APIがwrite/deleteを一元化 |
| processing descriptor隣接 `*.json.lease` | 現runner write/validate `core/platform/processing_lease.py:15-95`; claim `core/supervisor/pending_executor.py:301-315` | plain write。現schemaは`pid/anima/leased_at/task_id`、cmdlineは`core.supervisor.runner`固定 | §4のlease v2。rootがlease writer、task processをfence | root sole-writer、同じv2 schema |
| `shortterm/{lane}/{thread}/session_state.{json,md}`, archive | runner `ShortTermMemory`: `core/memory/shortterm.py:64-145,186-305` | plain overwrite/rename、lock/fsyncなし | task runner直接、lane規律とpool=1で単一writer | task runner所有の例外。終了前fsync |
| `shortterm/**/stream_checkpoint.json` | runner `core/memory/shortterm.py:206-245`; stream cleanup `core/supervisor/streaming_handler.py:60-73` | plain overwrite/unlink、lock/fsyncなし | task runner単一writer | 同左、grace/終了前fsync |
| `shortterm/streaming_journal_*.jsonl`, thread journal | runner `StreamingJournal`: path/open `core/memory/streaming_journal.py:63-130`; buffer/finalize `132-224`; fsync `442-472` | 同一path 1 writerが暗黙前提。eventはflush+fsync、textは最大1秒/500文字buffer | task runner sole-writer。root SIGTERM→grace→child flush+ACK。rootはtask終了時もorphan回収 | 同左（A-07） |
| Mode S `state/current_session_*.json` | runner `core/execution/_sdk_session.py:125-197` | plain overwrite/unlink、lock/fsyncなし | task runner直接 | 現行配置を維持し終了前fsync |
| Mode C `shortterm/**/codex_thread_id.txt` | runner `core/execution/codex_sdk.py:381-418` | plain overwrite/unlink | 同上 | 同上 |
| Mode X `shortterm/**/grok_session_id.txt` | runner `core/execution/grok_cli.py:123-164` | plain overwrite/unlink | 同上 | 同上 |
| Mode D `shortterm/**/cursor_chat_id.txt` | runner `core/execution/cursor_agent.py:91-139` | plain overwrite/unlink | 同上。A-08のS/C/X列挙外だが実在するため同じ規律 | 同上 |
| `state/heartbeat_checkpoint.json`, `state/recovery_note.md` | HB runner `core/_anima_heartbeat.py:551-575,669-677,738-742,788-834`; runner orphan recovery `core/supervisor/runner.py:369-462` | plain write/unlink、lockなし | heartbeat task runner単一writer、grace対象 | root trigger + task runner実行。回収/次回注入はroot管理 |
| `state/cron_logs/*.jsonl` | runner `CronLogger`: `core/memory/cron_logger.py:22-84` | `.lock` + advisory lock + append/fsync。bounded rewriteもlock内 | 維持 | root append APIまたはroot sole-writer |
| `state/cron_stats.json`, `state/cron_disabled.json` | runner scheduler `core/supervisor/scheduler_manager.py:407-428,460-557` | temp+replace、プロセス間lockなし | scheduling ownerとなるrootへ寄せる | root sole-writer |
| `state/background_notifications/*.md` | runner completion `core/anima.py:569-586`; scheduler `core/supervisor/scheduler_manager.py:580-590,726-745`; token cap `core/_agent_cycle.py:183-207` | ID/timestamp別file、lockなし | 直接write維持、rootが回収 | root notification API |
| `state/inbox_read_counts.json`, `overflow_inbox/*.md` | inbox runner `core/_anima_inbox.py:977-1038`; overflow `core/memory/dedup.py:31-93` | countsは無lockRMW、overflowはunique filename | inbox=cron相当laneの直接write | root inbox/state API |
| `state/goal_state.jsonl` | runner/tool `GoalManager`: `core/goals/manager.py:301-323` | append+fsync、goal lockはthreadingのみ | pool=1で直接append | root task/state API |
| `state/entity_registry.json` | runner entity index `core/memory/entity_index.py:38-119,333-361` | process lock + advisory lock + atomic replace | 維持 | root Memory API |
| `state/bm25_longterm_index.*` | runner/server `core/memory/bm25.py:249-278,286-398` | atomic replace、rebuildはO_EXCL singleflight lock | 維持 | root Memory API |
| `state/rag_upsert_failures.json` | indexer `core/memory/rag/indexer.py:265-301` | temp+replace、無lockRMW | 現indexer owner | root Memory API |
| `state/rag_repair.json`, `state/rag_repair.lock` | server/repair `core/memory/rag/repair_state.py:27-50`; operation flock `core/memory/rag/repair_utils.py:120-136` | repair operation単位排他、state writeはplain overwrite | server supervisor所有 | root repair owner |

## 3. その他に発見したmutable state

| group | 現行writer・位置 | 現行排他 | Phase 2 → Phase 3 |
|---|---|---|---|
| `episodes/*.md`, `knowledge/**`, `procedures/**`, archive | `core/memory/manager.py:440-494`, `core/memory/consolidation.py:116-142`; forgetting merge/archive/delete `core/memory/forgetting.py:1058-1083,1435-1455` | 多くはlockなし。episode appendはfsync、consolidation/forgettingの一部はatomic replace、archive copy/deleteは共通lockなし | 直接write/archive/delete → root Memory API |
| `facts/*.jsonl` | `core/memory/facts.py:434-487` | process lock + flock + append/fsync/atomic rewrite | 維持 → root Memory API |
| `activity_log/*.jsonl` | runner/server/MCP `core/memory/activity.py:145-185,291-307` | append+fsync、lockなし | 直接append → root event API |
| `token_usage/*.jsonl` | runner `core/memory/token_usage.py:134-208` | append、lock/fsyncなし | task runner直接 → root集約 |
| `token_usage/rollup.json` | token集計時のcache再構築 `core/memory/token_usage.py:317-348,378-402` | JSONLを正本としてatomic write、共通lockなし | cache直接write → root集約。破損時はJSONLから再生成 |
| `run/action_memory_gate/*.json`, `no_rule_holds.jsonl` | model tool action gate `core/memory/action_gate.py:214-281,286-295,425-497` | session JSONはtemp+replace、notify stateは無lockRMW、hold trailは無lockappend | task runner直接 → root tool-session/state API |
| `run/replied_to/{session}/{thread}.jsonl` | ToolHandler/engine base `core/tooling/handler.py:548-574`, `core/execution/base.py:661-684` | 無lockappend、engine間で同pathへ書込み得る | task runner直接 → root session API |
| `state/.consolidation_mode` | consolidation lane `core/_anima_lifecycle.py:401-456`; MCP reader `core/mcp/server.py:623` | plain create/unlink、例外時finally cleanup | background task runner所有 → root registryの明示状態へ移行 |
| `run/completion_gate_called`, `run/min_trust_seen` | completion gate `core/tooling/handler.py:366-379`, `core/execution/_completion_gate.py:28-68`; trust marker `core/tooling/handler_memory.py:1091-1114,1197-1205`, `core/execution/_sdk_hooks.py:637-645` | session markerのplain write/create、共通lockなし | task runner session artifact。終了時回収 → root session API/registry |
| `state/pending/.wake`, `state/sdk_stderr.log` | Mode S hook/options `core/execution/_sdk_options.py:247-251,381-390` | wakeはtouch、stderrはSDK subprocess append | task runner artifact。rootはdescriptor wake/diagnosticsとして回収 |
| `state/skill_usage.jsonl`, curator/promotion/activation state | `core/skills/usage.py:78-123`, `core/skills/curator.py:205-280,410-438`, `core/skills/activation_state.py:30-91`, `core/skills/autolearn.py:51-64,180-191` | append/plain/temp+replace、共通lockなし | 直接write → root skill/state API |
| `skills/**`, `state/skill_hub_lock.jsonl`, `state/skill_hub_backups/**` | skill hub install/remove/frontmatter/lock `core/skills/hub.py:136-210,247-267,303-323,350-395`; trust/promotion `core/skills/trust.py:95-113`, `core/skills/promotion.py:501-514`; model-facing scan `core/tooling/handler_skills.py:490-510` | directory move/copy、個別atomic writeまたはplain write、hub audit append。全経路共通のprocess間lockなし | approved tool/management経路の直接mutation。task runner間はskill名単位に直列化 → root skill API/sole-writer |
| `state/skill_curator/report-*.json`, proposals/reference rewrites | server housekeeping report生成・retention delete `core/memory/housekeeping.py:653-683,1419-1454`; runner curator `core/skills/curator.py:131-149,217-218`; reference rewrite `core/skills/reference_rewriter.py:49-147` | report plain write/delete、提案file単位、共通lockなし | server scheduler/curator laneの直接mutation → root skill APIが生成・削除を一元化 |
| `state/memory_hygiene.json`, consolidation carryover | `core/memory/hygiene.py:35-95`, `core/memory/consolidation.py:146-235` | atomic replace、lockなし | scheduler/lane owner → root |
| `state/cmd_output/**` | task runner tool `core/tooling/handler_files.py:604-618`; machine toolのwrite本体 `core/tools/machine.py:450-490` とpath/call `682-699` | ID別artifact、lockなし | task runner artifactのまま。root registryは参照だけ保持 |
| `state/bootstrap_state.json`, archive | management/server `core/bootstrap_state.py:41-82,367-449` | temp+replace | root起動前management plane。task runner書込み禁止 |
| `state/event_export_spool/*` | activity/token exporter `core/event_export.py:32-109,185-241` | UUID+atomic rename、worker thread lock | runnerごと → root observability worker |
| `vectordb/knowledge_graph.json` | server/index `core/memory/rag/graph.py:341-366`, `core/supervisor/_mgr_scheduler.py:741-765` | direct overwrite、lockなし | server scheduler → root DB owner |
| `status.json` | factory `core/anima_factory.py:468-570`; server API `server/routes/animas.py:427-470`; CLI `core/config/cli.py:168-193,320-344`; management tool `core/tooling/handler_subordinate_control.py:35-64,104-134,260-286`; reconcile `core/supervisor/_mgr_reconcile.py:101-125` | 複数の無lock RMW | management-plane正本。model-facing自己file tool書込み拒否。flag変更はrestart経路、DB handoffは停止中だけ |

server housekeepingは上記の個別行に加えてepisode/hygiene archive、DM/cron log削除、shortterm episode化・削除、facts lock削除、`archive/superseded`・failed descriptor・runtime artifact削除を行う（`core/memory/housekeeping.py:383-650,988-1514,1524-1935`）。Phase 2ではserver maintenance writerと各runnerが競合しないよう対象path/実行中jobをfenceし、Phase 3では各resourceのroot APIへdelete/archive操作も含める。mutation棚卸しの「writer」にはcreate/updateだけでなくrename/archive/deleteも含む。

停止中のanimaを対象にするmerge/migration/factoryも、memory tree、conversation/task queue、status、旧stateのrename/copy/deleteを行うmanagement-plane writerである（`core/lifecycle/anima_merge/service.py:720-770,772-775,1578-1599,1665-1687`, `core/lifecycle/anima_merge/task_refs.py:60-94,202-227`, `core/migrations/steps.py:745-820`, `core/anima_factory.py:468-570,698-704`）。これらはPhase 2/3のruntime writerではなく、対象root/task runner/DB ownerが全停止したことを確認してからだけ実行するoffline mutationと分類する。実行中なら変更せず拒否し、完了後の起動時にresolver/rootが再読込する。

## 4. Phase 2 advisory lock契約

流用元は `TaskQueueManager._locked_queue()` の `threading.RLock + <resource>.lock + acquire_file_lock(exclusive=True)`（`core/memory/task_queue.py:890-920`）、OS抽象は `core/platform/locks.py:32-58` とする。ただし現行task queueはlock file open/acquire失敗時に無lockで処理を続ける。新規2 lockでは構造だけを流用し、失敗時は例外/`UNAVAILABLE`へ**fail-closed**に直す。新しい独自lock方式を作らない。

### 4.1 `current_state.md`

- lock pathは `state/current_state.md.lock`。
- tool、MemoryManager、HB、conversation finalize、server housekeepingを含む**全writer**が参加する。
- lock範囲はread/mtime確認から内容merge、temp write、`os.replace()`まで。最終writeだけをlockしてはならない。
- acquisition失敗時は無lockへfallbackせず、明示error/unavailableとする。state updateを空成功にしない。

### 4.2 conversation JSON

- defaultは `state/conversation.json.lock`、threadは `state/conversations/{thread}.json.lock`。
- lock取得後にin-memory cacheを捨ててdiskを再読込し、append/compress/finalize/clearとatomic replaceを同じcritical sectionで行う。
- transcript appendも同threadのconversation mutationに付随する場合は同じlock内で行う。

これらのlock追加実装は後続Phase 2 PRの範囲であり、本PRでは仕様だけを確定する。task queue appendは同patternを試行済みだがfail-openであり、`compact()`もlock外であるため、後続PRで取得失敗をfail-closedにして両方を同lockへ含める。

## 5. processing lease schema v2

### 5.1 JSON schema

v2は既存fieldを残し、次を必須にする（A-05/C-02/B-03）。`pid`はroot PID、`task_pid`は実行child PIDであり、同一値にしてはならない。

```json
{
  "schema_version": 2,
  "pid": 4100,
  "anima": "sakura",
  "leased_at": 1786070400.125,
  "task_id": "task-abc",
  "job_id": "job-7f2",
  "task_pid": 4123,
  "pgid": 4123,
  "root_epoch": "550e8400-e29b-41d4-a716-446655440000",
  "attempt": 1,
  "process_start_time": 1786070400.02
}
```

| field | 型/制約 | 意味 |
|---|---|---|
| `schema_version` | integer=`2` | version discriminator |
| `pid` | positive integer | leaseを発行・所有するroot PID（旧fieldを維持） |
| `anima` | non-empty string | anima名 |
| `leased_at` | finite number | lease作成Unix time |
| `task_id` | non-empty string | taskboard/descriptor ID |
| `job_id` | non-empty string | IPC v2 job ID |
| `task_pid` | positive integer | task runner PID |
| `pgid` | positive integer | task runnerと子CLIを含むkill単位 |
| `root_epoch` | UUID string | root起動generation |
| `attempt` | integer >= 1 | 論理taskの実行attempt。同一attemptは再claim不可 |
| `process_start_time` | finite number | `psutil.Process(task_pid).create_time()` のUnix time |

writeは同directoryの一時fileへJSONを書いてflush+fsyncし、`os.replace()`した後directory fsyncを行う。rootだけが作成・更新・削除する。

### 5.2 validatorとPID reuse fence

validatorは内部的に `live | dead | unknown` を返し、既存bool APIは`unknown`を保守的にliveとして扱う。rootはunknown processをkillまたはdescriptor回収してはならず、診断を記録して次周期で再検査する。

1. schema/type/anima/task/job/attemptを検証する。
2. `root_epoch`を現在のroot registryと照合する。同一なら継続、異なればstale child回収候補とする。
3. `os.kill(task_pid, 0)`またはpsutilで存在確認する。
4. 現在の `psutil.Process(task_pid).create_time()` を保存値と比較する。platform精度に合わせて両方をcentisecondへ丸め、一致しなければPID再利用として`dead`とする。
5. cmdlineに `core.supervisor.task_runner`、対象anima、`job_id`がすべて存在することを確認する。旧rootを確認する場合は `core.supervisor.runner` も許容する。新validatorは `core.supervisor.task_runner` を必ずlive対象に加える。
6. stale `root_epoch`でもprocess identityが一致するchildだけをpgid単位で回収し、消滅確認後にdescriptorをinterrupted/failedへ移す。PID/開始時刻不一致のprocessへsignalを送らない。

root restart時は「旧child/pgid回収→消滅確認→descriptor recovery」の順とする。同じ`attempt`を再claimしない。明示的な再委譲/再試行は`attempt+1`を新規発行する。外部commitやmessageのexactly-onceは保証せず、現行のVerify要求文言（`core/supervisor/pending_executor.py:821-836,859-875`）を維持する（C-03）。idempotency key導入はスコープ外である。

### 5.3 旧schema互換

`schema_version`がなく、既存4 field `pid/anima/leased_at/task_id`が妥当なfileはv1として読む。v1は現行どおりPID存在とcmdlineの `core.supervisor.runner` + animaで判定する（現行実装 `core/platform/processing_lease.py:45-95`）。

- live v1 leaseは実行中とみなし、その場で書換えない。
- dead v1 leaseは現行orphan recoveryへ渡す。
- malformed fileはdead扱いにするが、descriptorを失わずfailed側へ移して監査可能にする。
- 新規claimと再試行は必ずv2を書く。v1 readerはrollback猶予中および旧fileが残る限り維持する。

## 6. state競合・回復の受入条件

- chat、heartbeat、複数TaskExecを同時実行し、conversation turn、`current_state.md` update、task queue eventが欠落しない。
- busy hang試験はtask PID/pgidを明示し、threshold + poll周期2回以内に当該pgidだけが消え、root PIDが変わらない。
- root restart後に同一attemptが再claimされず、旧pgid消滅、descriptor移動、Layer 2 status、notification回数を確認する。
- task/root死のjournal回復は最大損失1秒または500文字、表示済みprefix重複なしをassertする。

## 7. 決定事項トレーサビリティ

| ID | 本仕様での反映 |
|---|---|
| A-03 / A-04 / B-02 / C-01 | busy root sole-writer、task registry、監視分離 |
| A-05 / C-02 / B-03 | lease v2、task runner cmdline、PID reuse fence、旧schema |
| C-03 | 同一attempt再claim禁止、exactly-once非保証 |
| A-06 / C-04 / B-04 | 全mutation棚卸し、Phase 2 lock、Phase 3 root API |
| A-07 | journal grace/ACKとtask終了時orphan recovery |
| A-08 / C-06 | engine別resume配置維持とfsync |
