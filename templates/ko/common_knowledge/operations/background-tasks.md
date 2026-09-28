# 백그라운드 작업 실행 가이드

## 개요

일부 외부 도구(이미지 생성, 3D 모델 생성, 로컬 LLM 추론, 음성 텍스트 변환 등)는
실행에 수 분~수십 분이 걸린다. 이를 직접 실행하면 실행 내내 잠금이 유지되어
메시지 수신과 heartbeat가 중단된다.

`animaworks-tool submit`을 사용하면 작업을 백그라운드에서 실행하고,
자신은 즉시 다음 작업으로 넘어갈 수 있다.

런타임에서는 `core/tasks/background.py`의 **BackgroundTaskManager**가 도구 실행과
`state/background_tasks/{task_id}.json`로의 상태 영속화를 담당하고,
Anima 자식 프로세스 내의 **PendingTaskExecutor**(`core/tasks/pending_executor.py`)가
`animaworks-tool submit`이 작성한 대기 큐를 모니터링하여 `BackgroundTaskManager`로 옮긴다.

## 언제 submit을 사용할까

### 반드시 submit을 사용해야 하는 도구

도구 가이드(시스템 프롬프트)에 ⚠ 표시가 있는 하위 명령:

- `image_gen pipeline` / `fullbody` / `bustup` / `icon` / `chibi` / `3d` / `rigging` / `animations`
- `local_llm generate` / `chat`
- `transcribe audio`(하위 명령 이름은 `audio`)

각 도구의 `EXECUTION_PROFILE`에서 `background_eligible: true`인 것은 프로필을 통해
백그라운드 실행 후보로 등록된다(예: `chatwork sync` / `download` 등).
운영 방침은 계속해서 **⚠ 표시**를 우선할 것.

### submit이 필요 없는 도구

실행 시간이 짧은(수십 초 미만 기준) 도구:

- `web_search`, `x_search`
- `slack`, `chatwork`, `gmail`(일반적인 조작)
- `github`, `aws_collector`

### 판단 기준

- ⚠ 표시 있음 → 반드시 submit
- ⚠ 표시 없음 → 직접 실행(`animaworks-tool submit` 실행 시, 프로필상 "단시간"인 경우 stderr에 경고가 출력될 수 있음)

## 사용 방법

### 기본 문법

```bash
animaworks-tool submit <ツール名> <サブコマンド> [引数...]
```

### 실행 예

```bash
# 3Dモデル生成（Meshy API 等）
animaworks-tool submit image_gen 3d assets/avatar_chibi.png

# キャラクター画像一括生成（全ステップ）
animaworks-tool submit image_gen pipeline "1girl, black hair, ..." --negative "lowres, ..." --anima-dir $ANIMAWORKS_ANIMA_DIR

# ローカルLLM推論（Ollama）
animaworks-tool submit local_llm generate "要約してください: ..."

# 音声文字起こし（Whisper 等）— サブコマンドは audio
animaworks-tool submit transcribe audio "/path/to/audio.wav" --language ja
```

### 반환 값

submit은 즉시 JSON을 표준 출력으로 내보내고 종료한다(`task_id`은 12자리 hex):

```json
{
  "task_id": "a1b2c3d4e5f6",
  "status": "submitted",
  "tool": "image_gen",
  "subcommand": "3d",
  "message": "バックグラウンドタスクを投入しました。完了時にinboxに通知されます。(task_id: a1b2c3d4e5f6)"
}
```

## 결과 수신

1. submit 후, **PendingTaskExecutor**가 `state/background_tasks/pending/`의 기술자를 가져와
   `BackgroundTaskManager.submit`에서 백그라운드 실행한다(Anima의 대화 잠금 외부).
2. 실행 중~완료까지, 동일한 `task_id`의 상태는 **`state/background_tasks/{task_id}.json`**에도 저장된다.
   `BackgroundTaskManager.submit` / `submit_async`이 기록하는 시점에는 **최초부터 `running`**(UUID 12자리 `task_id`을 채번한 직후 디스크에 저장). 완료 시 `completed`, 예외 시 `failed`.
   데이터 타입상 `pending` 열거 값도 있지만, 매니저의 일반 투입 흐름에서는 사용되지 않는다. **큐 대기**는 별개로, `state/background_tasks/pending/*.json`의 기술자가 나타낸다.
3. 완료 시 `_on_background_task_complete`이 **`state/background_notifications/{task_id}.md`**에 Markdown 알림을 작성한다.
4. 다음 **heartbeat**에서 `drain_background_notifications()`이 해당 `.md`을 읽고 삭제하여 컨텍스트에 주입한다.
5. Web UI의 WebSocket이나 `call_human` 계열의 인간 알림이 활성화되어 있으면, 같은 완료 시점에 그쪽에도 게시될 수 있다.

도구 **`list_background_tasks`**으로 메모리와 디스크를 병합한 목록을, **`check_background_task`**으로 `task_id` 지정 상태를 참조할 수 있다(모두 `BackgroundTaskManager`의 `list_tasks` / `get_task`에 해당).

## 실패 시 대응

- 알림에 "실패"라고 기재된 경우:
  1. 오류 내용을 확인한다
  2. 원인을 파악한다(API 키 미설정, 타임아웃, 인수 오류 등)
  3. 수정하여 다시 submit한다
  4. 해결할 수 없으면 상급자에게 보고한다

- **크래시나 비정상 종료**로 `processing/`에 JSON이 남은 경우, Anima 프로세스 시작 시 **PendingTaskExecutor**가 회수한다:
  - **명령형**(`animaworks-tool submit`): `state/background_tasks/pending/processing/*.json` → `state/background_tasks/pending/failed/`
  - **LLM형**은 정규 작업과 시도 ID로 관리하며, 기술자를 회수하지 않는다. 미완료 작업은 pending과 영구적인 확인 필요 알림을 남긴다. 실제 부작용을 확인한 후 명시적으로 재개한다.
  기존 LLM 파일은 마이그레이션의 증거일 뿐이다. 재개를 위해 이동하거나 재생성하지 않는다.

## 흔한 실수

### 직접 실행해 버리는 경우

```bash
# 悪い例: 直接実行 → 長時間ロックされうる
animaworks-tool image_gen 3d assets/avatar_chibi.png -j

# 良い例: submit で非同期実行
animaworks-tool submit image_gen 3d assets/avatar_chibi.png
```

직접 실행해 버린 경우, 작업이 완료될 때까지 기다릴 수밖에 없다.
다음부터는 반드시 submit을 사용할 것.

### transcribe의 하위 명령 생략

```bash
# 悪い例: audio サブコマンドがないと意図したプロファイル判定にならない
animaworks-tool submit transcribe "/path/to/audio.wav"

# 良い例
animaworks-tool submit transcribe audio "/path/to/audio.wav"
```

### submit 후 결과를 계속 기다리는 경우

submit하면 즉시 다음 작업으로 넘어갈 것.
결과는 heartbeat용 알림 파일을 통해 수집되므로 폴링이나 대기는 필요 없다.

## 기술적 구조(참고)

### BackgroundTaskManager(`core/tasks/background.py`)

- **역할**: 장시간 도구 호출을 `asyncio` 작업으로 백그라운드 실행하고, 완료·실패 시 `on_complete`(임의의 비동기 콜백)을 `await`한다. 생성자에서 `state/background_tasks/`을 `mkdir(parents=True)`한다.
- **동기 도구**: `submit(tool_name, tool_args, execute_fn)` → `execute_fn(name, args) -> str | None`을 `run_in_executor(None, ...)`로 스레드 풀 실행.
- **비동기 도구**: `submit_async`(동일 시그니처로 `execute_fn`이 `Awaitable[str]`) → 이벤트 루프에서 `await execute_fn(...)`.
- **스케줄링**: `asyncio.create_task(..., name=f"bg-{task_id}")`으로 래핑. 완료 시 `_async_tasks`에서 해당 항목을 제거.
- **영속화**: 각 변경 후 `_save_task`로 `state/background_tasks/{task_id}.json`에 `to_dict()`(`ensure_ascii=False`, `indent=2`). 손상된 JSON은 `_load_task`으로 경고 로그 후 `None`.
- **조회**: `get_task`는 인메모리 우선, 없으면 디스크. `list_tasks(status=...)`은 디스크의 `*.json`과 병합하고, `created_at` 내림차순. `active_count`은 인메모리의 `RUNNING` 개수.
- **`on_complete`**: 콜백 내에서 예외가 발생해도 작업의 완료/실패 상태는 유지되며, 실패는 로그에 기록될 뿐.
- **자격 있는 도구 이름**(`is_eligible`)은 다음 **3계층**을 병합(나중 것이 우선). 키는 그대로 사전 조회(Mode A의 스키마 이름 `generate_3d_model`과 Mode S 제출용 `image_gen:3d`의 **둘 다** 가능):
  1. 코드 내 기본값 `_DEFAULT_ELIGIBLE_TOOLS`(값은 기준 초. 현재 키):
     `generate_character_assets`, `generate_fullbody`, `generate_bustup`, `generate_icon`, `generate_chibi`, `generate_3d_model`, `generate_rigged_model`, `generate_animations`(각 30), `local_llm` / `run_command`(각 60)
  2. `BackgroundTaskManager.from_profiles`을 통해 각 모듈의 `EXECUTION_PROFILE`에서 `background_eligible: true`의 하위 명령을 추출(`core.integrations._base.get_eligible_tools_from_profiles`). 키는 `"{tool_name}:{subcmd}"`, 초는 `expected_seconds`(미설정 시 60)
  3. `config.json`의 `background_task.eligible_tools` — 각 키에 대해 `threshold_s`을 초로 덮어쓰기
- **비활성화**: `config.json`로 `background_task.enabled: false`으로 하면 `BackgroundTaskManager` 자체가 생성되지 않음(그 경우, submit 큐는 가져와도 실행 측에서 경고가 됨).
- **정리**: `cleanup_old_tasks(max_age_hours=24)`는 (1) `completed` / `failed`로 `completed_at`이 **24시간 초과** 지난 JSON을 삭제, (2) `running` 상태로 `created_at`이 **48시간 초과** 지난 파일(프로세스 크래시 등의 고아)을 삭제. 반환 값은 삭제 개수. `config.json`의 `background_task.result_retention_hours`는 스키마에 존재하지만, **현행 `BackgroundTaskManager` 구현에서는 참조되지 않음**(호출 측이 `cleanup_old_tasks`에 임의의 `max_age_hours`을 전달하는 API만 있음).

### 같은 파일 내 기타 API: `rotate_dm_logs`

`core/tasks/background.py`에는 **백그라운드 도구 실행과는 독립적으로** `rotate_dm_logs(shared_dir, max_age_days=7)`가 있다. `shared/dm_logs/*.jsonl` 중, 항목의 `ts`이 임계값보다 오래된 행을 `{stem}.{YYYYMMDD}.archive.jsonl`로 추가 아카이브하고, 활성 파일에서는 제외한다. 실제 처리는 `_rotate_dm_logs_sync`(`run_in_executor`로 오프로드).

### 명령형 작업(`animaworks-tool submit`)

1. `animaworks-tool submit`이 `state/background_tasks/pending/{task_id}.json`에 기술자를 작성한다(`ANIMAWORKS_ANIMA_DIR` 필수).
2. PendingTaskExecutor의 watcher가 최대 **3초** 간격(`wake()`로 즉시도 가능)으로 `pending/`을 모니터링.
3. `pending/*.json` → `pending/processing/`로 이름을 바꾼 후 `execute_pending_task`.
4. 명령형은 내부에서 `animaworks-tool … -j`을 **하위 프로세스**로 시작. **1회당 벽시계 타임아웃은 1800초(30분)**(`pending_executor._PENDING_TASK_SUBPROCESS_TIMEOUT`). 성공 후 processing 내 파일은 삭제. 예외 시 `pending/failed/`로.
5. 실제 처리는 `BackgroundTaskManager.submit(composite_name, tool_args, execute_fn)`에 위임. `composite_name`은 `tool:subcommand`(예: `image_gen:3d`). 이것이 `is_eligible`과 대조된다.
6. 완료 시 `_on_background_task_complete`이 `state/background_notifications/{task_id}.md`을 작성하고, heartbeat에서 `drain_background_notifications()`이 읽는다.

### LLM형 작업(정규 작업 스토어)

1. `submit_tasks` / `delegate_task`이 완전한 지침·컨텍스트·완료 조건·제약·모델·의존 관계를 원자적으로 등록한다.
2. watcher는 실행 가능한 작업의 획득과 시도 생성을 같은 transaction에서 수행한다. 의존 대상과 설정된 워커 용량을 확인하고, 비병렬 제약은 같은 배치 내로 한정한다.
3. `done` / `cancelled` 선언 없이 시도가 끝나면 pending으로 돌아가지만 자동 재실행은 하지 않는다. 부작용을 확인하고, 필요하면 `submit_tasks(batch_id="resume", tasks=[{"task_id":"ID","resume":true}])`로 명시적 재개한다.
4. 결과는 `state/task_results/{task_id}.md`을 참조할 수 있는 경우가 있지만, 상태·입력·시도는 정규 스토어가 원본이다. 완료는 `update_task`으로 선언하고, LLM의 응답이나 파일 존재로 추측하지 않는다.
5. 확인 필요·완료 알림은 영속화하고, 정기 heartbeat에 의존하지 않고 전달한다. DM에서 실행 입력을 재구성하지 않는다.

SQLite나 기존 작업 파일을 직접 편집하지 말고, 작업 도구를 사용한다. 위의 명령형 파이프라인과는 다른 구조.

### 파일의 라이프사이클

**명령형**(`animaworks-tool submit`의 대기 큐):

```
state/background_tasks/pending/*.json
  → pending/processing/*.json
  → 成功: 削除 | 失敗: pending/failed/*.json
```

아울러 **작업 상태 파일**(실행 전체):

```
state/background_tasks/{task_id}.json   # running → completed / failed
```

**LLM형**(`submit_tasks` / `delegate_task`):

```
保存済み入力 → 実行可能pending → 取得済み試行（in_progress）
  → done/cancelled宣言、またはpending + 永続的な要確認通知
  → 明示resumeで保存済み入力を使う新しい試行
```

위의 명령형 파일 회수는 LLM 작업에는 적용하지 않는다. 기존 LLM의 JSONL·기술자는 마이그레이션·export 형식이며, 실행 시작의 신호가 아니다.
