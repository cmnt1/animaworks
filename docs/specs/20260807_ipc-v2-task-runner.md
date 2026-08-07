# IPC v2 root⇔task runner wire仕様

## 1. 適用範囲と互換境界

本仕様は Phase 2/3 の anima root と、1 jobにつき1つ生成される task runner の間だけに適用する。task runner は root が公開する1つの endpoint に接続し、jobの開始から終了まで **1本の永続 duplex connection** を使う。transport は Unix socket 固定ではなく、既存の `core/supervisor/transport.py:44-69,141-197,200-236` を使い、`ANIMAWORKS_IPC_TRANSPORT`、Windows、socket path長超過時のloopback TCP fallbackを維持する（C-07）。

server⇔root は現行の `IPCRequest` / `IPCResponse` / `IPCEvent` JSON Linesと、stream専用connectionの IPC-STREAMを変更しない。現行型は `core/supervisor/ipc.py:37-115`、requestごとのconnectionは `core/supervisor/ipc.py:269-291,286-340,342-398,488-506` にある。特に `IPCResponse.chunk` はJSON objectではなくJSON文字列であり、serverが再度 `json.loads()` する二重JSONを維持する（`core/supervisor/streaming_handler.py:150-160`、`server/routes/chat_producer.py:106-136`）。本仕様の実装でserver API、SSE event名、terminal responseを変更してはならない（A-01/B-01）。

## 2. framingと共通envelope

- UTF-8 JSON Lines。1 message = 1 JSON object + `\n`。embedded改行はJSON escapeする。
- `v` は整数 `2`、`kind` は `request | response | event`。
- 全messageに `job_id` と送信側connection内で単調増加する `seq` を持たせる。`seq` は1から始まり、再接続時も同じattemptでは巻き戻さない。
- job識別は `(job_id, attempt, root_epoch)`。`attempt` は1始まり、`root_epoch` はroot起動ごとに変わるUUID。
- request/responseには `request_id` を必須とし、responseは同じ値を返す。eventは `event` と `data` を持つ。
- `lane` はdispatch用の `chat | heartbeat | cron | task | background`。`greet`/`bootstrap`は`chat`、`inbox`は`cron`相当、`consolidation`は`background`へ割り当て、root内でLLMまたは外部CLIを実行する経路を残さない（B-05）。
- `display_lane` はbusy sidecar互換用の具体名で、rootがspawn時に確定してregistryへ保存する。runnerが変更してはならず、`hello`/`progress`との不一致は`PROTOCOL_ERROR`とする。
- 未知の必須field、未知の`kind`、型不一致、不正な`v`は `PROTOCOL_ERROR` を返してconnectionを閉じる。未知の任意capabilityは無視できる。

共通fieldは次のとおり。

| field | 型 | 契約 |
|---|---:|---|
| `v` | integer | 常に`2` |
| `kind` | string | `request` / `response` / `event` |
| `job_id` | string | rootがspawn前に発行した不変ID |
| `seq` | integer | 方向別・attempt内で単調増加 |
| `root_epoch` | string | root process generation UUID |
| `attempt` | integer | 同じ論理taskの実行attempt |
| `lane` | string | 上記5 laneのいずれか |
| `display_lane` | string | 既存busy sidecarの`lanes[]`へ出す具体名 |

`display_lane` は `chat/greet/bootstrap`=`conversation:{thread_id|default}`、`inbox`=`inbox`、`heartbeat/cron/consolidation`=`background`、pool型TaskExec=`background-worker:{slot_id}:{task_id}` とする。poolを使わない互換TaskExecだけは現行どおり`background`とする。rootはactive registryの全jobからこの値を集約し、既存payload、root PID、文字列形式を変えずにbusy sidecarへ書く。

## 3. message例

### 3.1 request

rootとtask runnerのどちらからも送信できる。受信側は `(job_id, attempt, request_id)` で重複排除し、同一requestの再送には最初と同じresponseを返す。

```json
{"v":2,"kind":"request","job_id":"job-7f2","seq":17,"root_epoch":"550e8400-e29b-41d4-a716-446655440000","attempt":1,"lane":"chat","display_lane":"conversation:default","request_id":"req-91","method":"memory.search","params":{"query":"契約更新","limit":5}}
```

### 3.2 response

成功時だけ`result`、失敗時だけ`error`を持つ。両方または両方なしは禁止する。

```json
{"v":2,"kind":"response","job_id":"job-7f2","seq":18,"root_epoch":"550e8400-e29b-41d4-a716-446655440000","attempt":1,"lane":"chat","display_lane":"conversation:default","request_id":"req-91","result":{"status":"ok","items":[{"id":"chunk-12","text":"..."}]}}
```

unavailableの例:

```json
{"v":2,"kind":"response","job_id":"job-7f2","seq":21,"root_epoch":"550e8400-e29b-41d4-a716-446655440000","attempt":1,"lane":"chat","display_lane":"conversation:default","request_id":"req-92","error":{"code":"UNAVAILABLE","message":"memory queue is full","retryable":true,"retry_after_ms":250}}
```

### 3.3 eventとACK

SSE chunkの例。`data.chunk`は意図的にJSON文字列のままとし、objectへ正規化しない。

```json
{"v":2,"kind":"event","job_id":"job-7f2","seq":19,"root_epoch":"550e8400-e29b-41d4-a716-446655440000","attempt":1,"lane":"chat","display_lane":"conversation:default","event":"stream_chunk","data":{"chunk":"{\"type\":\"text_delta\",\"text\":\"更新します\"}"}}
```

ACKはeventとして表し、`ack_seq`まで同方向に連続して受理済みであることを示す累積ACKとする。ACK event自体にACKを返さない。

```json
{"v":2,"kind":"event","job_id":"job-7f2","seq":12,"root_epoch":"550e8400-e29b-41d4-a716-446655440000","attempt":1,"lane":"chat","display_lane":"conversation:default","event":"ack","data":{"ack_seq":19}}
```

## 4. handshake、ACK、再送

1. rootはjob registryへ `job_id`、`attempt`、`root_epoch`、task PID/pgid、`lane`、`display_lane`、run用`request_id`を登録してからspawnする。
2. task runnerが接続し、最初のmessageとして `hello` eventを送る。`display_lane`は他messageと同じくtop-levelに置き、`data`に`capabilities`、`last_received_seq`、`last_acked_seq`を含める。rootはspawn時のregistryと照合し、`hello_ack`を返す。不一致は`STALE_ROOT`または`UNKNOWN_JOB`で拒否する。
3. handshake後、rootはregistryに保存した`request_id`で `method="run"` requestを送り、job入力を`params`へ載せる。runnerのterminal `job_result`は必ずこのrun requestへのresponseで、同じ`request_id`を返す。再接続時もrun request IDを変えない。
4. ACKは「frameを検証し、重複排除/replay stateへ受理した」ことを意味し、request処理の成功を意味しない。処理結果は必ずresponseで返す。
5. ACK未受信messageは送信側replay bufferに保持する。ただし `event="ack"` frameだけはACK対象でもreplay対象でもなく、送信完了時に破棄する（その`seq`自体は受信側の連続seqを進める）。切断後は同じ `(job_id, attempt, root_epoch)` で再接続し、双方が申告した連続seqの次からACK以外の同じmessageを再送する。
6. eventはseqで重複排除する。requestは`request_id`でも重複排除し、state mutationを二度適用しない。terminal responseはrootがjob終了までcacheする。
7. 新しい`root_epoch`へ旧attemptは再接続できない。旧child/pgidを回収し、descriptorをinterrupted/retryableとして処理する。同一attemptを再claimしない。外部副作用のexactly-onceは保証しない。

## 5. payload上限とbackpressure

現行reader上限16 MiB、write chunk 1 MiBは `core/supervisor/ipc.py:29-32,154-176` にある。v2は以下を固定する。

- 1 frameのUTF-8 byte長（末尾`\n`を除く）は最大 **4 MiB**。送信前と受信後の両方で検査する。したがって合法な1 frameは空の未ACK windowへ必ず収容できる。
- 各方向の未ACK windowは **64 frameか4 MiBの小さい方**。connectionのoutbound queue全体は **256 frameか16 MiBの小さい方**。
- windowが満杯なら新規requestの受付を止め、既に受けたrequestには `UNAVAILABLE` / `retryable=true` を返す。root memory APIの有界queue超過も同じであり、空配列や空文字を成功として返さない。
- `writer.drain()`またはACKが5秒進まない場合はslow consumerと判定し、送信可能なら `BACKPRESSURE_TIMEOUT` をterminal errorとして送ってconnectionを閉じる。送信不能ならroot registryへ同errorを記録してjobを失敗扱いにする。無言dropは禁止する。
- 上限超過requestには `PAYLOAD_TOO_LARGE` responseを返す。上限超過response/eventを生成した側は同codeでjobを失敗させる。暗黙のtruncateは禁止する。
- `ack`、`grace`、`cancel`、heartbeatに加え、受理済みrequestへ返す `UNAVAILABLE` / `BACKPRESSURE_TIMEOUT` / `PAYLOAD_TOO_LARGE` error responseはcontrol reserve（8 frame・合計512 KiB）を使い、data window飽和中も送れる。reserve用errorはpayload本体やstack traceを含めず64 KiB以下の定型envelopeとし、`request_id`、code、簡潔なmessage、retry情報だけを返す。したがってwindow満杯を理由にerror responseをdata queueへ待たせたりdropしたりしない。reserveも詰まればconnectionを異常終了し、root registryへ同errorと対象request IDを記録する。

## 6. stream中継

task runnerはthinking/tool/text等の既存chunkを `stream_chunk` eventで送る。`data.chunk`に現在の `json.dumps(chunk, ensure_ascii=False)` の結果をそのまま格納する。rootはこれを現行 `IPCResponse(stream=True, chunk=<JSON文字列>)` に戻してserverへ流す。現行event種別のforwardは `core/supervisor/streaming_handler.py:150-229`、terminalは同ファイル `183-195,231-271` に一致させる。

- runner正常完了: §4でrootが送った`run` requestと同じ`request_id`の `job_result` responseを返す。chatではrootが現行 `stream=true, done=true, result={response,replied_to,cycle_result}` へ変換する。
- runner失敗: `job_result`を空成功にせず、`EXECUTION_ERROR`等のerror responseへ変換する。
- keepaliveは既存server向けchunk形式を維持するが、v2のhalf-open heartbeatとは別物である。
- server死は現行同等にSSE再接続時のresponse ID喪失を許容する。root/task死はjournal回復により最大損失1秒または500文字で、表示済みprefixを重複させない（C-05）。根拠となる現行buffer値は `core/memory/streaming_journal.py:38-40`。

## 7. control event、steer、lane規律

- `progress`: runner→root。`data`にtask PID/pgid、lane、job ID、spawn時の`display_lane`、progress時刻を含め、rootのtask registryを更新する。rootは`display_lane`をregistry値と照合してbusy sidecarを再構成し、runnerはsidecarを直接書かない。
- `inject_message`: root→実行中chat runner。同job/PID/sessionを維持し、対応adapterだけがACK後に注入する。
- `cancel`: root→runner。cancel受付をACKし、終了結果は別のterminal responseで返す。
- `grace`: root→runner。§9のflushを要求する。
- `heartbeat`: idle時のhalf-open検知専用。

steer capabilityはengine別にnegotiationする。Mode SはPR-9b冒頭でadapterが同一clientを公開する改修とSDK並行`query()`の実機検証を行う。Mode C/Xを含め、active turn注入を保証できないengineは `steer=false` とする。fallbackは単純なFIFO待ちへ変えず、現行どおり二件目がinterrupt eventを設定してconversation lockを待つ（現行経路 `core/_anima_messaging.py:882-927,940-955`）（B-09）。

cronは同一task名だけ直列、異なるtask名は並行可能、missed runはskipとする。現行の同名skipと独立spawnは `core/supervisor/scheduler_manager.py:849-876` にある（B-06）。

## 8. 異常検知

- 通常trafficが5秒ない側は`heartbeat`を送る。送信済みheartbeatを含め15秒連続でACK/trafficがなければhalf-openとしてsocketを閉じ、再接続規則へ進む。
- rootはsocketとは別にtask processの終了とpgidを監視する。runnerは親PID/root epochを監視する。EOF、protocol error、PID終了のいずれも無言成功にしない。
- rootのtask watchdogはregistry内のtaskごとの最終progressを使い、threshold超過時に当該pgidだけをkillする。server supervisorはroot健全性のみを監視し、task hangを理由にrootをkillしない（A-03/A-04/B-02/C-01）。
- task runnerはrootが明示注入する `ANIMAWORKS_EMBED_URL` と `ANIMAWORKS_RERANK_URL` の**どちらか一方でも**欠落または空なら、connection確立前に起動エラーとする。親環境の暗黙継承やport既定値推測、local model fallbackは禁止する（C-09）。現行runnerへのURL注入位置は `core/supervisor/process_handle.py:176-185` である。

## 9. SIGTERMとgrace

rootがSIGTERMを受けたら新規job受付を停止し、各runnerへ`grace` eventを送る。runnerは次を順に行う。

1. 新規tool/steer受付を止める。
2. StreamingJournal bufferをflushしfsyncする。
3. engine別resume情報をfsyncする。
4. 未完了のroot state mutation requestのresponse/ACKを待つ。
5. `grace_ack` event（`data.grace_seq`、flush結果、最後のjournal seqを含む）を返し、自然終了する。

rootは`grace_ack`後に当該jobを回収する。deadline超過時だけTERM→KILLへ進み、失敗をjournal orphan recovery対象として記録する。rootはrunner終了ごとにもorphan recoveryを行う。全runnerのgrace処理後、rootはDB queueをdrainしclientをclean closeしてexitする。root drainの観測区間はSIGTERM受信→DB clean close完了とし、`root_drain_duration = db_closed_at - sigterm_received_at - task_grace_wait_seconds` が5秒以内であることを測る。task runner grace待ちは別metricとして記録し、5秒budgetには含めない（A-07）。

## 10. 三値原則とerror code

検索・取得系responseは次の三値を区別する。

1. 成功: `result.status="ok"`。空集合が正しい場合も`items: []`と根拠を持つ。
2. 確認済み不在: `result.status="not_found"`。
3. 判定不能/利用不能: `error.code="UNAVAILABLE"`、`retryable=true`。

主要codeは `PROTOCOL_ERROR`、`UNKNOWN_JOB`、`STALE_ROOT`、`PAYLOAD_TOO_LARGE`、`BACKPRESSURE_TIMEOUT`、`UNAVAILABLE`、`CANCELLED`、`EXECUTION_ERROR`。errorは必ず人間可読`message`、再試行可否`retryable`を持つ。timeout、queue full、切断、DB repair中を `""`、`null`、`[]`、`{"status":"completed"}`へ潰してはならない。

## 11. 決定事項トレーサビリティ

| ID | 本仕様での反映 |
|---|---|
| A-01 / B-01 | duplex 1本、envelope、ACK、上限、再接続、互換境界 |
| A-03 / A-04 / B-02 / C-01 | progress一本化、root task registry、rootのみ監視対象 |
| A-07 | grace→flush/fsync→`grace_ack`→exit |
| B-05 / B-06 | 全lane割当とcron規律 |
| B-09 | capability negotiationと現行interrupt fallback |
| C-05 | server死/root死/task死ごとのstream回復契約 |
| C-07 | 既存transport抽象とTCP fallback |
| C-09 | URL明示注入とfail-closed |
