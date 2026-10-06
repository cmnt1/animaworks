---
name: subordinate-management
description: >-
  부하 Anima의 슈퍼바이저 조작. 일시정지・복귀・모델 변경・재시작・작업 위임・상태 읽기・감사를 수행한다.
  Use when: 부하의 무효화・재유효화, 메인 또는 BG 모델 변경, 프로세스 재시작, delegate_task, 조직 대시보드 확인이 필요할 때.
---


# 스킬: 부하 관리 (슈퍼바이저 도구)

부하를 가진 Anima에 자동으로 활성화되는 슈퍼바이저 도구 모음. 모든 하위(자식・손자・증손자…)의 일시정지・복귀・모델 변경・백그라운드 모델 변경・재시작・상태 확인, 직속 부하에게 작업 위임과 진행 상황 추적을 수행한다.

## 사용 가능한 도구

### 모든 하위(자식·손자·증손자…전부)에 대해 조작 가능

| 도구 | 용도 |
|--------|------|
| `disable_subordinate` | root에 status.json `enabled: false` 설정을 요청 (프로세스 종료 + 자동 복귀 방지) |
| `enable_subordinate` | 휴지 중인 하위를 복귀 |
| `set_subordinate_model` | root에 status.json 메인 모델 업데이트와 실행 중 프로세스의 reload를 요청 |
| `set_subordinate_background_model` | root에 heartbeat/cron용 모델 업데이트를 요청. 다음 백그라운드 작업부터 적용 (빈 문자열로 클리어) |
| `restart_subordinate` | 하위 프로세스를 재시작 (status.json `restart_requested` 플래그. Reconciliation이 약 30초 이내에 재시작) |
| `delegate_task` | 직속 부하에게 작업을 위임 (큐 추가 + DM 전송 + 자신 측 추적 엔트리 생성) |
| `org_dashboard` | 하위 전체의 프로세스 상태·최종 활동·현재 작업·작업 수를 트리로 표시 |
| `ping_subordinate` | 하위의 생존 확인 (`name` 생략 시 전체 일괄, 지정 시 단일) |
| `read_subordinate_state` | 하위의 `current_state.md`를 읽기 |
| `audit_subordinate` | 하위의 최근 활동을 포괄 감사 (활동 요약·작업 상황·오류 빈도·도구 사용 통계·통신 패턴) |

### 위임 작업 추적

| 도구 | 용도 |
|--------|------|
| `task_tracker` | `delegate_task`로 위임한 작업의 진행 상황을 부하 측 큐에서 추적 (`status`: all / active / completed. 기본값: active) |

위임자의 추적 카드는 위임 대상의 정본 작업 기록을 참조한다. 상태 확인에는 `task_tracker`을 사용한다.

## 중요: disable_subordinate와 send_message의 차이

- **disable_subordinate**: status.json을 `enabled: false`으로 변경. Reconciliation이 자동 복귀시키지 않음. **이것을 사용할 것**
- send_message로 "쉬어"라고 전달만 하면 **프로세스는 종료되지 않는다**. 메시지를 보내도 Reconciliation이 재시작한다

## 사용 방법

### 일시정지・복귀

여러 명을 일시정지할 경우 한 명씩 `disable_subordinate`을 호출:

```
disable_subordinate(name="aoi", reason="業務縮小のため一時休止")
disable_subordinate(name="taro", reason="業務縮小のため一時休止")
enable_subordinate(name="aoi")
```

### 모델 변경 및 재시작

이 도구들은 root에게 root 소유 `status.json`의 업데이트를 요청한다. Anima 프로세스에서 직접 편집하지 않는다. 메인 모델은 시작 중인 프로세스에 reload되며, 종료된 Anima는 다음 시작 시 새 설정을 읽는다:

```
set_subordinate_model(name="aoi", model="claude-sonnet-5-5", reason="負荷分散のため")
```

백그라운드 모델(heartbeat/cron용)은 다음 작업 러너 시작부터 적용되며, 실행 중인 작업은 그대로 완료된다:

```
set_subordinate_background_model(name="aoi", model="claude-sonnet-5-5", reason="heartbeat負荷軽減")
```

백그라운드 모델을 지우고 메인 모델로 되돌리는 경우:

```
set_subordinate_background_model(name="aoi", model="", reason="メインモデルに統一")
```

프로세스 전체의 재시작이 정말로 필요한 경우에만, 별도로 `restart_subordinate`를 사용한다.

### 상태 확인・감사

```
org_dashboard()                         # 配下全体のダッシュボード
ping_subordinate()                      # 全配下の生存確認
ping_subordinate(name="aoi")            # 単一の生存確認
read_subordinate_state(name="aoi")      # 現在タスク・保留タスクの内容
audit_subordinate(name="aoi")           # 直近1日の包括監査レポート
audit_subordinate(name="aoi", days=7)   # 直近7日間の監査（days は 1〜30）
audit_subordinate(since="09:00")        # 全配下の今日9時以降の監査
audit_subordinate(name="aoi", since="13:00")  # aoi の今日13時以降
```

CLI에서도 실행 가능 (S/C/D/G-mode의 Bash 경유로 사용할 때 편리):

```bash
animaworks anima audit aoi              # 直近1日の監査
animaworks anima audit aoi --days 7     # 直近7日間の監査
animaworks anima audit --all --since 09:00  # 全Anima、今日9時以降
```

### 작업 위임

```
delegate_task(name="aoi", instruction="週次レポートをまとめて", summary="週次レポート作成")
# 必須: `name`, `instruction`。任意: `summary`, `workspace`, `acceptance_criteria`, `model`
# workspace を指定すると委譲先がそのワークスペースで作業する（workspace-manager スキル参照）
task_tracker(status="active")      # 委譲タスクの進捗確認（status: all / active / completed）
```

부하에게 작업 공간 할당(주요 작업 디렉터리 지정)은 `workspace-manager` 스킬을 참조할 것.

## 권한

- **모든 하위(자식・손자・증손자…재귀)**: 상태 확인・관리 도구 사용 가능
- **직속 부하만**: `delegate_task`(작업 위임)
- 자신에 대한 조작은 불가
