# 백그라운드 작업 실행 가이드

## 개요

일부 외부 도구(이미지 생성, 3D 모델 생성, 로컬 LLM 추론, 음성 텍스트 변환 등)는
실행에 수 분~수십 분이 걸린다. 이를 직접 실행하면 실행 내내 잠금이 유지되어
메시지 수신과 heartbeat가 중단된다.

`animaworks-tool submit`을 사용하면 작업을 백그라운드에서 실행하고,
자신은 즉시 다음 작업으로 넘어갈 수 있다.

`animaworks-tool submit`은 `task_type="command"` 입력을 TaskStore에 등록한다.
Anima 자식 프로세스의 **PendingTaskExecutor**(`core/tasks/pending_executor.py`)가 실행 시도를 가져오고,
**BackgroundTaskManager**(`core/tasks/background.py`)가 도구를 백그라운드에서 실행한다.
시도는 TaskStore에 기록되고, 호환용 결과 JSON은 `state/background_tasks/{task_id}.json`에 저장된다.

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

1. submit은 `task_type="command"` 입력을 TaskStore에 원자적으로 등록한다. PendingTaskExecutor가 실행 시도를 가져와 BackgroundTaskManager에 대화 잠금 외부 실행을 맡긴다.
2. TaskStore가 시도와 결과 참조를 기록한다. 기존 조회 도구와의 호환을 위해 `state/background_tasks/{task_id}.json`도 같은 task_id로 `running` → `completed` / `failed` 상태를 저장한다.
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

- 프로세스가 비정상 종료되면 TaskStore가 시도 소유자의 생존 여부를 확인한다. 종료가 확인된 시도는 검토가 필요한 pending으로 기록하며, 부작용이 이미 발생했을 수 있으므로 자동 재실행하지 않는다. 결과 JSON이 `running` 상태로 남아 있어도 완료로 판단하지 말고 실제 상태를 확인한 후 명시적으로 재개한다.

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

### BackgroundTaskManager（`core/tasks/background.py`）

- **역할**: 장시간 도구 호출을 `asyncio` 작업으로 백그라운드에서 실행하고, 완료·실패 시 `on_complete`(임의의 비동기 콜백)을 `await` 한다. 생성자에서 `state/background_tasks/` 를 `mkdir(parents=True)` 한다.
- **동기 도구**: `submit(tool_name, tool_args, execute_fn, task_id=None)` → `execute_fn(name, args) -> str | None`를 `run_in_executor(None, ...)`로 스레드 풀에서 실행한다. task_id를 생략하면 매니저가 생성하고, CLI 명령 작업은 TaskStore ID를 전달한다.
- **비동기 도구**: `submit_async`(동일한 시그니처로 `execute_fn` 가 `Awaitable[str]`) → 이벤트 루프에서 `await execute_fn(...)`.
- **스케줄링**: `asyncio.create_task(..., name=f"bg-{task_id}")` 로 감싼다. 완료 시 `_async_tasks` 에서 해당 항목을 제거한다.
- **영속화**: 변경 후마다 `_save_task` 로 `state/background_tasks/{task_id}.json` 에 `to_dict()` 한다(`ensure_ascii=False`, `indent=2`). 손상된 JSON은 `_load_task` 에서 경고 로그를 남긴 뒤 `None`.
- **조회**: `get_task` 는 메모리 내 데이터를 우선하며, 없으면 디스크를 조회한다. `list_tasks(status=...)` 는 디스크의 `*.json` 와 병합한 뒤 `created_at` 내림차순으로 정렬한다. `active_count` 은 메모리에 있는 `RUNNING` 의 개수다.
- **`on_complete`**: 콜백 안에서 예외가 발생해도 작업의 완료/실패 상태는 유지되며, 실패는 로그에만 기록된다.
- **자격이 있는 도구 이름**(`is_eligible`)은 다음 **3개 계층**을 병합한다(뒤에 오는 값이 우선). 키는 그대로 딕셔너리에서 조회한다(Mode A의 스키마 이름 `generate_3d_model` 과 Mode S 제출용 `image_gen:3d` 이 **모두** 있을 수 있음):
  1. 코드 내 기본값 `_DEFAULT_ELIGIBLE_TOOLS`(값은 대략적인 초 단위 시간. 현재 키):
     `generate_character_assets`, `generate_fullbody`, `generate_bustup`, `generate_icon`, `generate_chibi`, `generate_3d_model`, `generate_rigged_model`, `generate_animations`(각 30), `local_llm` / `run_command`(각 60)
  2. `BackgroundTaskManager.from_profiles` 를 통해 각 모듈의 `EXECUTION_PROFILE` 에서 `background_eligible: true` 의 하위 명령을 추출한다(`core.integrations._base.get_eligible_tools_from_profiles`). 키는 `"{tool_name}:{subcmd}"`, 초 단위 시간은 `expected_seconds`(설정되지 않은 경우 60)
  3. `config.json` 의 `background_task.eligible_tools` — 각 키에 대해 `threshold_s` 를 초 단위 시간으로 덮어쓴다.
- **비활성화**: `config.json`에서 `background_task.enabled: false`로 설정하면 `BackgroundTaskManager`가 생성되지 않는다. submit 입력은 TaskStore에 등록되지만 실행 시도는 pending으로 돌아가고 확인 필요 알림이 생성된다.
- **정리**: `cleanup_old_tasks(max_age_hours=24)` 는 (1) `completed` / `failed` 에서 `completed_at` 가 지정된 시간을 초과한 JSON 파일, (2) `running` 상태인 채 `created_at` 가 **48시간 넘게** 지난 파일(프로세스 충돌 등으로 남은 고아 파일)을 삭제한다. 반환값은 삭제 건수다. 보존 기간은 호출 측에서 `max_age_hours` 로 지정하며, 이에 대응하는 `config.json` 설정 키는 없다.

### 같은 파일 내 기타 API: `rotate_dm_logs`

`core/tasks/background.py`에는 **백그라운드 도구 실행과는 독립적으로** `rotate_dm_logs(shared_dir, max_age_days=7)`가 있다. `shared/dm_logs/*.jsonl` 중, 항목의 `ts`이 임계값보다 오래된 행을 `{stem}.{YYYYMMDD}.archive.jsonl`로 추가 아카이브하고, 활성 파일에서는 제외한다. 실제 처리는 `_rotate_dm_logs_sync`(`run_in_executor`로 오프로드).

### 명령형 작업(`animaworks-tool submit`)

1. `animaworks-tool submit`은 `task_type="command"`, 도구명, 인수, Anima, `task_id`를 포함한 입력을 TaskStore에 원자적으로 등록한다(`ANIMAWORKS_ANIMA_DIR` 필수).
2. TaskStore watcher는 기존 claim / attempt 구조로 작업을 가져온다. BackgroundTaskManager도 호환 결과 JSON에 같은 task_id를 사용한다.
3. 명령형은 내부에서 `animaworks-tool … -j`을 **하위 프로세스**로 시작하며, **1회당 벽시계 타임아웃은 1800초(30분)**이다(`pending_executor._PENDING_TASK_SUBPROCESS_TIMEOUT`).
4. stdout 또는 오류는 `state/task_results/{task_id}/{attempt_token}.md`에 저장하고 TaskStore 시도에 결과 참조를 기록한다. 입력·상태·시도의 정본은 TaskStore다.
5. BackgroundTaskManager는 `state/background_tasks/{task_id}.json`에 `running` → `completed` / `failed`를 저장한다. `_on_background_task_complete`는 `state/background_notifications/{task_id}.md`를 작성하고 heartbeat가 이를 가져온다.

### 이전 명령 디스크립터 마이그레이션

기존 `state/background_tasks/pending/*.json` 파일은 새 런타임에서 감시하지 않는다. Anima를 중지한 상태에서 `animaworks task-store migrate --anima NAME --backup PATH`를 실행하면 미처리 최상위 디스크립터를 검증해 TaskStore로 가져온다. 원본 파일은 증거로 보존한다. `processing/`과 `failed/`는 자동 재실행하거나 가져오지 않으며, 부작용 검토를 위해 경고와 함께 남긴다.

### LLM형 작업(정규 작업 스토어)

1. `submit_tasks` / `delegate_task`이 완전한 지침·컨텍스트·완료 조건·제약·모델·의존 관계를 원자적으로 등록한다.
2. watcher는 실행 가능한 작업의 획득과 시도 생성을 같은 transaction에서 수행한다. 의존 대상과 설정된 워커 용량을 확인하고, 비병렬 제약은 같은 배치 내로 한정한다.
3. `done` / `cancelled` 선언 없이 시도가 끝나면 pending으로 돌아가지만 자동 재실행은 하지 않는다. 부작용을 확인하고, 필요하면 `submit_tasks(batch_id="resume", tasks=[{"task_id":"ID","resume":true}])`로 명시적 재개한다.
4. 결과는 `state/task_results/{task_id}.md`을 참조할 수 있는 경우가 있지만, 상태·입력·시도는 정규 스토어가 원본이다. 완료는 `update_task`으로 선언하고, LLM의 응답이나 파일 존재로 추측하지 않는다.
5. 확인 필요·완료 알림은 영속화하고, 정기 heartbeat에 의존하지 않고 전달한다. DM에서 실행 입력을 재구성하지 않는다.

SQLite나 기존 작업 파일을 직접 편집하지 말고, 작업 도구를 사용한다. 위의 명령형 파이프라인과는 다른 구조.

### 파일의 라이프사이클

**명령형**(`animaworks-tool submit`):

```
TaskStore command 입력 → claim / attempt
  → 성공: done | 실패·중단: 확인이 필요한 pending (자동 재실행 없음)
state/task_results/{task_id}/{attempt_token}.md  # 시도 결과 / 오류
state/background_tasks/{task_id}.json           # 호환 결과: running → completed / failed
```

**LLM형**(`submit_tasks` / `delegate_task`):

```
保存済み入力 → 実行可能pending → 取得済み試行（in_progress）
  → done/cancelled宣言、またはpending + 永続的な要確認通知
  → 明示resumeで保存済み入力を使う新しい試行
```

명령형과 LLM형은 입력 형식은 다르지만 모두 TaskStore의 claim / attempt로 실행·추적한다. 기존 LLM JSONL과 `state/pending/` 디스크립터는 마이그레이션·export 형식이며, 실행 시작 신호가 아니다.
