<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/architecture/anima-files.md -->
<!-- i18n: source-sha256=4058b5992b84f0303184a18c77cce99d86e2e702820420c335ccde9d598710f8 generated=2026-09-27 engine=local model=deepseek-v4-flash translator=2 -->

> 확인된 커밋: b304b7dc

# Anima의 파일

각 Anima는 `~/.animaworks/animas/{name}/`에 디렉토리를 가진다. 개성이나 행동 방침, 실행 설정은 텍스트와 JSON으로 나누어 저장하고, 세션 중에 업데이트되는 정보는 `state/`에 둔다.

## 정의와 설정

| 파일 | 역할 |
|---|---|
| `identity.md` | 성격, 말투, 자기소개 등 Anima의 항상적인 개성을 기술한다. |
| `injection.md` | 전문성이나 추가 행동 지침을 기술하고, system prompt에 포함한다. |
| `permissions.json` | 개별 Anima의 도구, 명령, 파일 접근에 관한 권한을 나타낸다. |
| `status.json` | 유효 상태, role, 담당, 모델, 인증, supervisor, heartbeat의 활성화 등 런타임에 해결하는 per-anima 정보를 보유한다. |
| `heartbeat.md` | heartbeat의 지침과 활동 시간대를 기술한다. 실행 간격은 전체 설정 또는 `status.json`의 값에서 결정되며, 이 파일의 본문에서는 설정하지 않는다. |
| `cron.md` | 정기 실행하는 작업을 제목별로 기술한다. 스케줄과 실행 내용은 supervisor가 읽는다. |

`status.json`은 ModelConfig와 관련된 per-anima 값의 정본이다. 대응 키와 기본값의 목록은 [설정 참조](../reference/config.md)를 참조한다. `permissions.json`과 전체의 `permissions.global.json`가 권한 판단에 사용된다. 권한의 경계와 평가 방법은 [보안](../security.md)을 참조한다.

## 실행 상태

| 경로 | 역할 |
|---|---|
| `state/current_state.md` | 진행 중인 작업, 판단, 다음 절차 등을 보유하는 작업 상태이다. prompt에 필요한 범위에서 포함되며, 업데이트는 상태 파일용 lock을 통해 보호된다. |
| `state/task_queue.jsonl` | 구형식의 작업 데이터가 남아 있는 경우의 마이그레이션 입력이다. 현재 작업의 정본은 공유 SQLite TaskStore이며, 이 파일을 런타임의 별도 큐로 취급하지 않는다. |
| `state/background_tasks/` | `animaworks-tool submit`에서 시작한 백그라운드 처리의 상태와 결과를 저장한다. 완료 결과는 대화나 후속 배경 실행에서 알림·참조된다. |

Anima의 장기 기억, 대화 기록, 스킬 등은 용도별 하위 디렉토리로 나뉘어 있다. 기억의 상세는 `docs/ja/memory/`의 각 장을 참조한다.

## 설계 판단

- **기억은 Markdown 파일로 가진다.** AI가 자연스럽게 읽고 쓸 수 있고, grep과도 궁합이 좋다. JSON은 설정과 상태에 한정한다.
- **서고형 기억을 채택한다.** 최근 N건을 prompt에 채우는 절단형은 기억량에 상한이 생긴다. 필요한 것을 검색하여 회상하는 서고형이라면 기억은 계속 늘어나도 된다.
- **권한은 시야의 제한이다.** 모르는 것이 있으므로 타인에게 묻는다. 모두가 모든 것을 볼 수 있으면 조직은 의미를 잃는다.