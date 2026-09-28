<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/cli.md -->
<!-- i18n: source-sha256=92b56543103c512cc42f576f51d3e9dc48a56d9fd976fa97bbe6d048019e75ba generated=2026-09-28 engine=luna model=gpt-6-luna translator=2 -->

# CLI 참조: `animaworks`

`animaworks` 명령어의 argparse 정의에서 생성되었습니다.

## 전역 옵션

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --gateway-url | option | — | — | Gateway URL |
| --data-dir | option | — | — | 런타임 데이터 디렉터리 재정의 (기본값: ~/.animaworks 또는 ANIMAWORKS_DATA_DIR) |

## `anima`

anima 프로세스 관리

`usage: animaworks anima [-h]
                        {restart,status,create,delete,disable,enable,list,info,repair-bootstrap,permissions,set-model,codex-yolo,set-background-model,set-outbound-limit,reload,set-role,rename,merge,merge-finalize,audit}
                        ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `anima audit`

하위 anima의 최근 활동 감사

`usage: animaworks anima audit [-h] [--all] [--days DAYS] [--since SINCE]
                              [--date DATE]
                              [anima]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | 대상 anima 이름 (--all 사용 시 생략 가능) |
| --all | flag | false | — | 모든 anima 감사 |
| --days | option | 1 | — | 감사할 일수 (기본값: 1, 최대: 30) |
| --since | option | — | — | 시작 시간 (HH:MM 형식, 오늘, JST). 지정 시 --days를 재정의 |
| --date | option | — | — | 특정 날짜 (YYYY-MM-DD, 'today', 또는 'yesterday'). 해당 날짜의 활동만 표시 |

## `anima codex-yolo`

Codex 모드 Anima를 YOLO 샌드박스 기본값으로 설정

`usage: animaworks anima codex-yolo [-h] [--all] [--restart] [anima]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 (--all 사용 시 필요 없음) |
| --all | flag | false | — | 모든 활성 Codex 모드 anima에 적용 |
| --restart | flag | false | — | 서버 실행 중 업데이트된 anima 재시작 |

## `anima create`

새 anima 생성

`usage: animaworks anima create [-h] [--name NAME] [--template TEMPLATE]
                               [--from-md PATH] [--supervisor SUPERVISOR]
                               [--role {engineer,researcher,manager,writer,ops,general}]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --name | option | — | — | Anima 이름 (빈 값일 때 필수, template/md일 때 선택) |
| --template | option | — | — | 명명된 템플릿에서 생성 |
| --from-md | option | — | — | MD 파일에서 생성 |
| --supervisor | option | — | — | 상위 anima 이름 (캐릭터 시트 재정의) |
| --role | option | — | engineer, researcher, manager, writer, ops, general | 적용할 역할 템플릿 (기본값: general) |

## `anima delete`

anima 삭제 (선택적 아카이브 포함)

`usage: animaworks anima delete [-h] [--no-archive] [--force] anima`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | 삭제할 anima 이름 |
| --no-archive | flag | false | — | 삭제 전 ZIP 아카이브 생성 건너뛰기 |
| --force | flag | false | — | 확인 프롬프트 건너뛰기 |

## `anima disable`

anima 비활성화 (休養)

`usage: animaworks anima disable [-h] anima`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | 비활성화할 anima 이름 |

## `anima enable`

anima 활성화 (復帰)

`usage: animaworks anima enable [-h] anima`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | 활성화할 anima 이름 |

## `anima info`

anima의 상세 설정 표시

`usage: animaworks anima info [-h] [--json] anima`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 |
| --json | flag | false | — | JSON으로 출력 |

## `anima list`

모든 anima를 상태와 함께 나열

`usage: animaworks anima list [-h] [--local]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --local | flag | false | — | 파일시스템 직접 스캔 |

## `anima merge`

한 anima를 다른 anima에 병합

`usage: animaworks anima merge [-h] [--dry-run | --execute] [--resume]
                              [--force]
                              source target`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| source | positional | — | — | 병합할 원본 anima |
| target | positional | — | — | 병합 대상 anima |
| --dry-run | flag | false | — | 두 anima를 변경하지 않고 병합 매니페스트 생성 (기본값) |
| --execute | flag | false | — | source 툼스톤을 통해 병합 실행 |
| --resume | flag | false | — | 중단된 --execute 작업 재개 |
| --force | flag | false | — | 복구 가능한 진행 중 상태에 대한 사전 점검 경고에도 계속 진행 |

## `anima merge-finalize`

완료된 병합 툼스톤 아카이브 및 등록 해제

`usage: animaworks anima merge-finalize [-h] [--dry-run | --execute] [--resume]
                                       source target`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| source | positional | — | — | 툼스톤 처리된 원본 anima |
| target | positional | — | — | 병합된 대상 anima |
| --dry-run | flag | false | — | 데이터 변경 없이 최종화 계획 검증 및 표시 (기본값) |
| --execute | flag | false | — | source 아카이브 및 등록 제거 |
| --resume | flag | false | — | 중단된 --execute 작업 재개 |

## `anima permissions`

Anima의 권한 설정 표시

`usage: animaworks anima permissions [-h] anima`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 |

## `anima reload`

status.json에서 anima 설정 핫 리로드

`usage: animaworks anima reload [-h] [--all] [anima]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 (--all 사용 시 필요 없음) |
| --all | flag | false | — | 모든 실행 중인 anima의 설정 리로드 |

## `anima rename`

anima 이름 변경

`usage: animaworks anima rename [-h] [--force] old_name new_name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| old_name | positional | — | — | 현재 anima 이름 |
| new_name | positional | — | — | 새 anima 이름 |
| --force | flag | false | — | 확인 프롬프트 건너뛰기 |

## `anima repair-bootstrap`

초기 부트스트랩 상태를 검사하거나 복구합니다

`usage: animaworks anima repair-bootstrap [-h]
                                         (--status | --retry | --complete | --fresh)
                                         anima`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 |
| --status | flag | false | — | 파일을 변경하지 않고 부트스트랩 상태와 검증 오류를 표시합니다 |
| --retry | flag | false | — | 부트스트랩 아티팩트를 복원하고 다른 부트스트랩 시도를 준비합니다 |
| --complete | flag | false | — | 오래된 부트스트랩 아티팩트를 보관하고 완전히 정의된 Anima를 완료로 표시합니다 |
| --fresh | flag | false | — | 런타임 데이터를 보관하고 모델 설정을 유지하면서 빈 Anima를 다시 생성합니다 |

## `anima restart`

anima 프로세스를 다시 시작합니다

`usage: animaworks anima restart [-h] anima`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 |

## `anima set-background-model`

heartbeat/cron 모델을 설정합니다

`usage: animaworks anima set-background-model [-h] [--credential CREDENTIAL]
                                             [--all] [--clear]
                                             [anima] [model]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 |
| model | positional | — | — | 배경 모델 이름 |
| --credential | option | — | — | 자격 증명 이름 |
| --all | flag | false | — | 모든 활성화된 anima에 적용합니다 |
| --clear | flag | false | — | 배경 모델 재정의를 제거합니다 |

## `anima set-model`

지정된 anima의 기본 모델을 변경합니다.

`usage: animaworks anima set-model [-h] [--credential CREDENTIAL] [--all]
                                  [anima] [model]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 (--all 사용 시 필요 없음) |
| model | positional | — | — | 모델 이름 (예: azure/gpt-4.1-mini) |
| --credential | option | — | — | 자격 증명 이름 |
| --all | flag | false | — | 모든 활성화된 anima에 적용합니다 |

## `anima set-outbound-limit`

Anima별 발신 메시지 한도를 설정합니다

`usage: animaworks anima set-outbound-limit [-h] [--per-hour PER_HOUR]
                                           [--per-day PER_DAY]
                                           [--per-run PER_RUN] [--clear]
                                           name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| name | positional | — | — | Anima 이름 |
| --per-hour | option | — | — | 시간당 최대 발신 메시지 수 |
| --per-day | option | — | — | 일일 최대 발신 메시지 수 |
| --per-run | option | — | — | 실행당 최대 DM 수신자 수 |
| --clear | flag | false | — | 재정의를 지웁니다 (역할 기본값으로 대체) |

## `anima set-role`

anima의 역할을 변경합니다

`usage: animaworks anima set-role [-h] [--status-only] [--no-restart]
                                 anima
                                 {engineer,researcher,manager,writer,ops,general}`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 |
| role | positional | — | engineer, researcher, manager, writer, ops, general | 할당할 새 역할 |
| --status-only | flag | false | — | status.json 역할 필드만 업데이트하고 템플릿 파일 재적용은 건너뜁니다 |
| --no-restart | flag | false | — | 역할 변경 후 자동 재시작을 건너뜁니다 |

## `anima status`

anima 프로세스 상태를 표시합니다

`usage: animaworks anima status [-h] [anima]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 (모든 anima를 보려면 생략) |

## `board`

공유 채널 작업을 관리합니다

`usage: animaworks board [-h] {read,post,dm-history} ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `board dm-history`

피어와의 DM 기록을 읽습니다

`usage: animaworks board dm-history [-h] [--limit LIMIT] from_anima peer`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| from_anima | positional | — | — | 자기 anima 이름 |
| peer | positional | — | — | 피어 anima 이름 |
| --limit | option | 20 | — | 최대 메시지 수 |

## `board post`

채널에 게시합니다

`usage: animaworks board post [-h] from_anima channel text`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| from_anima | positional | — | — | 발신자 anima 이름 |
| channel | positional | — | — | 채널 이름 |
| text | positional | — | — | 메시지 내용 |

## `board read`

채널 메시지를 읽습니다

`usage: animaworks board read [-h] [--limit LIMIT] [--human-only] channel`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| channel | positional | — | — | 채널 이름 (예: general, ops) |
| --limit | option | 20 | — | 최대 메시지 수 |
| --human-only | flag | false | — | 사람 메시지만 표시합니다 |

## `chat`

anima와 대화합니다

`usage: animaworks chat [-h] [--local] [--from FROM_PERSON]
                       [--thread THREAD_ID] [--no-tui] [--resume [SESSION_ID]]
                       [--sessions] [--user USER] [--password PASSWORD]
                       [--no-reattach]
                       [anima] [message]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 |
| message | positional | — | — | 보낼 메시지 (생략하면 대화형 TUI가 열립니다) |
| --local | flag | false | — | (사용되지 않음) 직접 모드 (게이트웨이 없음) |
| --from, --as | option | "human" | — | 발신자 이름 (기본값: human) |
| --thread | option | "default" | — | 스레드 ID (기본값: default) |
| --no-tui | flag | false | — | 메시지가 없을 때 TUI를 열지 않고 stdin을 읽습니다 |
| --resume | option | — | — | 이전 TUI 세션을 재개합니다 (선택적 SESSION_ID, 기본값은 최신) |
| --sessions | flag | false | — | 저장된 TUI 세션을 나열하고 종료합니다 |
| --user | option | — | — | 인증된 게이트웨이용 사용자 이름 |
| --password | option | — | — | 인증된 게이트웨이용 비밀번호 (프로세스 목록에 표시됨) |
| --no-reattach | flag | false | — | 시작 시 진행 중인 스트림에 다시 연결하지 않습니다 |

## `company`

회사 워크스페이스, anima 멤버십, 회사 소유 자산을 관리합니다.

`usage: animaworks company [-h] {create,list,assign,adopt,split,export} ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `company adopt`

회사의 데이터 디렉터리 자산을 이동하되, 먼저 백업을 만들고 일반적으로 이전 경로에 상대 심볼릭 링크를 남깁니다.

`usage: animaworks company adopt [-h] --to NAME [--dest SUBDIR] [--no-symlink]
                                path [path ...]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| path | positional | — | — | 데이터 디렉터리 기준 또는 절대 자산 경로 |
| --to | option | — | — | 대상 회사 |
| --dest | option | — | shared, knowledge, skills, credentials, . | 대상 하위 디렉터리 (기본값: 각 소스에서 추론) |
| --no-symlink | flag | false | — | 이전 경로에 심볼릭 링크를 남기지 않음 |

## `company assign`

하나 이상의 Anima를 회사에 할당하거나 회사 할당을 해제합니다.

`usage: animaworks company assign [-h] (--to NAME | --unassign)
                                 anima [anima ...]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 |
| --to | option | — | — | 대상 회사 |
| --unassign | flag | false | — | 회사 할당 해제 |

## `company create`

회사 작업 공간을 생성하거나 기존 작업 공간에 누락된 스캐폴드를 추가합니다.

`usage: animaworks company create [-h] [--display-name DISPLAY_NAME] name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| name | positional | — | — | 회사 이름 ([a-z0-9][a-z0-9_-]*) |
| --display-name | option | — | — | 사람이 읽을 수 있는 회사 이름 (기본값: 회사 이름) |

## `company export`

회사의 구성원과 자산을 이식 가능한 마이그레이션 번들로 수집하되, 비밀값은 가리고 남은 마이그레이션 작업을 문서화합니다.

`usage: animaworks company export [-h] --out DIR name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| name | positional | — | — | 회사 이름 |
| --out | option | — | — | 출력 디렉터리 (파일이 이미 있으면 안 됨) |

## `company list`

모든 회사, 표시 이름, 구성원 수, 그리고 미할당 Anima를 나열합니다.

`usage: animaworks company list [-h]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `company split`

매니페스트에서 회사 생성, Anima 할당, 자산 채택을 계획하거나 실행합니다.

`usage: animaworks company split [-h] --manifest FILE [--execute]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --manifest | option | — | — | YAML 또는 JSON 분할 매니페스트 |
| --execute | flag | false | — | 계획 실행 (기본값: 드라이런만) |

## `config`

구성 관리

`usage: animaworks config [-h] [--interactive] {get,set,list} ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --interactive, -i | flag | false | — | 대화형 설정 마법사 |

## `config get`

구성 값 가져오기

`usage: animaworks config get [-h] [--show-secrets] key`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| key | positional | — | — | 점 표기법 키 (예: system.timezone) |
| --show-secrets | flag | false | — | API 키 값 표시 |

## `config list`

모든 구성 값 나열

`usage: animaworks config list [-h] [--section SECTION] [--show-secrets]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --section | option | — | — | 섹션별 필터 |
| --show-secrets | flag | false | — | API 키 값 표시 |

## `config set`

구성 값 설정

`usage: animaworks config set [-h] key value`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| key | positional | — | — | 점 표기법 키 |
| value | positional | — | — | 설정할 값 |

## `cost`

cli.cost_help

`usage: animaworks cost [-h] [--days DAYS] [--today] [--json] [anima]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 (모든 Anima는 생략) |
| --days | option | 30 | — | 집계할 일 수 (기본값: 30) |
| --today | flag | false | — | 오늘만 표시 |
| --json | flag | false | — | JSON으로 출력 |

## `cron-guard`

자동 비활성화된 cron 작업을 검사하고 다시 활성화합니다.

`usage: animaworks cron-guard [-h] {list,enable} ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `cron-guard enable`

자동 비활성화된 cron 작업 다시 활성화

`usage: animaworks cron-guard enable [-h] anima task`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 |
| task | positional | — | — | Cron 작업 이름 |

## `cron-guard list`

자동 비활성화된 cron 작업 나열

`usage: animaworks cron-guard list [-h] anima`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 |

## `demo`

3-에이전트 데모 팀 실행 (Claude Code 또는 Codex에 로그인되어 있으면 API 키 불필요)

`usage: animaworks demo [-h]
                       [--preset {en-anime,en-business,ja-anime,ja-business}]
                       [--data-dir DATA_DIR] [--port PORT] [--host HOST]
                       [--reset]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --preset | option | "en-business" | en-anime, en-business, ja-anime, ja-business | — |
| --data-dir | option | "~/.animaworks-demo" | — | — |
| --port | option | 18501 | — | — |
| --host | option | "0.0.0.0" | — | — |
| --reset | flag | false | — | — |

## `heartbeat`

하트비트 트리거

`usage: animaworks heartbeat [-h] [--local] anima`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | Anima 이름 |
| --local | flag | false | — | (더 이상 사용되지 않음) 직접 모드 (게이트웨이 없음) |

## `import`

Hermes 또는 OpenClaw 데이터를 AnimaWorks로 가져오기

`usage: animaworks import [-h] {hermes,openclaw} ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `import hermes`

Hermes 에이전트 데이터 가져오기

`usage: animaworks import hermes [-h] --path PATH [--dry-run | --apply]
                                [--replace] [--json] [--common-skills]
                                [--target-anima TARGET_ANIMA]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --path | option | — | — | 소스 디렉터리, 예: ~/.hermes 또는 ~/.openclaw |
| --dry-run | flag | false | — | 런타임 파일시스템을 변경하지 않고 미리보기 |
| --apply | flag | false | — | 가져올 항목 적용 및 마이그레이션 보고서 작성 |
| --replace | flag | false | — | 백업 매니페스트 후 기존 생성 대상 교체 |
| --json | flag | false | — | Markdown 대신 JSON 출력 |
| --common-skills | flag | false | — | 스킬을 common_skills/community로 가져오기 |
| --target-anima | option | — | — | 개인 스킬, 사용량, 작업, 초안의 대상 Anima |

## `import openclaw`

OpenClaw 데이터 가져오기

`usage: animaworks import openclaw [-h] --path PATH [--dry-run | --apply]
                                  [--replace] [--json] --target-anima
                                  TARGET_ANIMA`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --path | option | — | — | 소스 디렉터리, 예: ~/.hermes 또는 ~/.openclaw |
| --dry-run | flag | false | — | 런타임 파일시스템을 변경하지 않고 미리 보기 |
| --apply | flag | false | — | 가져올 수 있는 항목을 적용하고 마이그레이션 보고서 작성 |
| --replace | flag | false | — | 백업 매니페스트 후 기존 생성 대상 교체 |
| --json | flag | false | — | Markdown 대신 JSON 출력 |
| --target-anima | option | — | — | 생성된 초안의 대상 애니마 |

## `index`

하이브리드 검색을 위해 메모리 파일을 벡터 데이터베이스에 인덱싱합니다.

`usage: animaworks index [-h] [--anima ANIMA] [--full] [--shared] [--dry-run]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --anima | option | — | — | 이 애니마의 메모리만 인덱싱 (기본값: 모든 애니마) |
| --full | flag | false | — | 전체 재인덱싱 강제 (기존 인덱스 삭제 후 재구축) |
| --shared | flag | false | — | 공유 컬렉션(common_knowledge + common_skills)을 각 활성화된 애니마의 DB에 인덱싱 |
| --dry-run | flag | false | — | 실제 인덱싱 없이 인덱싱될 항목 표시 |

## `init`

런타임 디렉터리를 초기화하고, 필요에 따라 애니마를 생성합니다.

`usage: animaworks init [-h]
                       [--force | --template NAME | --from-md PATH | --blank NAME | --skip-anima]
                       [--name NAME]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --force | flag | false | — | 기존 런타임에 누락된 템플릿 파일 병합 |
| --template | option | — | — | 비대화형: 이름이 지정된 템플릿에서 애니마 생성 |
| --from-md | option | — | — | 비대화형: MD 파일에서 애니마 생성 |
| --blank | option | — | — | 비대화형: 지정된 이름으로 빈 애니마 생성 |
| --skip-anima | flag | false | — | 인프라만 초기화, 애니마 생성 건너뛰기 |
| --name | option | — | — | 애니마 이름 재정의 (--from-md와 함께 사용) |

## `internal`

애니마용 내부 도구

`usage: animaworks internal [-h]
                           {archive-memory,check-permissions,create-skill,manage-channel,list-background-tasks,check-background-task}
                           ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `internal archive-memory`

메모리 파일 보관

`usage: animaworks internal archive-memory [-h] path`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| path | positional | — | — | 상대 경로 (예: knowledge/old-notes.md) |

## `internal check-background-task`

특정 작업 확인

`usage: animaworks internal check-background-task [-h] task_id`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| task_id | positional | — | — | 작업 ID |

## `internal check-permissions`

도구 권한 확인

`usage: animaworks internal check-permissions [-h] tool_name [action]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| tool_name | positional | — | — | 도구 이름 |
| action | positional | "" | — | 선택적 작업 |

## `internal create-skill`

스킬 파일 생성

`usage: animaworks internal create-skill [-h] [--content CONTENT] name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| name | positional | — | — | 스킬 이름 (또는 name.md) |
| --content | option | — | — | 내용 (기본값: stdin) |

## `internal list-background-tasks`

백그라운드 작업 목록

`usage: animaworks internal list-background-tasks [-h]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `internal manage-channel`

채널 생성 또는 보관

`usage: animaworks internal manage-channel [-h] {create,archive} channel`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| action | positional | — | create, archive | 작업 |
| channel | positional | — | — | 채널 이름 |

## `logs`

애니마 로그 보기

`usage: animaworks logs [-h] [--all] [--lines LINES] [--date DATE] [anima]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | 애니마 이름 (--all이 아니면 필수) |
| --all | flag | false | — | 모든 로그 표시 (서버 + 모든 애니마) |
| --lines | option | 50 | — | 표시할 줄 수 (기본값: 50) |
| --date | option | — | — | 특정 날짜 (YYYYMMDD 형식) |

## `mcp`

애니마용 stdio MCP 서버 실행

`usage: animaworks mcp [-h] --anima ANIMA [--project PROJECT] [--tools TOOLS]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --anima | option | — | — | 애니마 이름 |
| --project | option | — | — | 기본 프로젝트 아카이브 |
| --tools | option | "search_memory,read_memory_file,write_memory_file" | — | 쉼표로 구분된 노출 도구 |

## `migrate`

런타임 데이터에 필요한 마이그레이션을 실행합니다.

`usage: animaworks migrate [-h] [--dry-run] [--verbose] [--list] [--force]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --dry-run | flag | false | — | 아무것도 수정하지 않고 변경 사항 미리 보기 |
| --verbose | flag | false | — | 상세한 파일 수준 변경 사항 표시 |
| --list | flag | false | — | 모든 마이그레이션 단계와 상태 나열 |
| --force | flag | false | — | 상태와 관계없이 모든 마이그레이션 재적용 |

## `models`

모델 정보 및 카탈로그

`usage: animaworks models [-h] {list,info,show} ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `models info`

모델의 해석된 모드와 컨텍스트 표시

`usage: animaworks models info [-h] model`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| model | positional | — | — | 모델 이름 (예: claude-sonnet-4-6) |

## `models list`

알려진 모델 목록

`usage: animaworks models list [-h] [--mode {A,C,D,G,S,X,a,c,d,g,s,x}] [--json]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --mode | option | — | A, C, D, G, S, X, a, c, d, g, s, x | 실행 모드로 필터링 |
| --json | flag | false | — | JSON으로 출력 |

## `models show`

현재 models.json 내용 표시

`usage: animaworks models show [-h] [--json]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --json | flag | false | — | 원시 JSON 출력 |

## `optimize-assets`

기존 3D 에셋 최적화 (메시 정리, 압축, 단순화)

`usage: animaworks optimize-assets [-h] [--anima ANIMA] [--dry-run]
                                  [--simplify [RATIO]] [--texture-compress]
                                  [--texture-resize RES] [--all]
                                  [--skip-backup]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --anima, -a | option | — | — | 특정 anima만 에셋 최적화 |
| --dry-run | flag | false | — | 변경 없이 수행될 작업만 표시 |
| --simplify | option | — | — | 메시 단순화 (기본 비율: 0.27 ≈ 30K→8K 폴리곤) |
| --texture-compress | flag | false | — | 텍스처를 WebP 형식으로 변환 |
| --texture-resize | option | — | — | 텍스처를 RES×RES로 크기 조정 (기본값: --texture-compress 설정 시 1024) |
| --all | flag | false | — | 모든 최적화 적용: 정리 + 단순화 + 텍스처 + draco |
| --skip-backup | flag | false | — | 원본 에셋 백업 생성 건너뛰기 |

## `profile`

여러 AnimaWorks 인스턴스 관리 (멀티테넌트)

`usage: animaworks profile [-h]
                          {list,add,remove,start,stop,start-all,stop-all} ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `profile add`

새 프로필 등록

`usage: animaworks profile add [-h] [--data-dir DATA_DIR] [--port PORT] name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| name | 위치 인수 | — | — | 프로필 이름 |
| --data-dir | 옵션 | — | — | 데이터 디렉터리(기본값: ~/.animaworks/<name>) |
| --port | 옵션 | — | — | 포트(기본값: 18500부터 10씩 증가하며 자동 할당) |

## `profile list`

상태와 함께 모든 프로필 나열

`usage: animaworks profile list [-h]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `profile remove`

프로필 등록 제거

`usage: animaworks profile remove [-h] name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| name | positional | — | — | 프로필 이름 |

## `profile start`

프로필 서버 시작

`usage: animaworks profile start [-h] [--host HOST] name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| name | positional | — | — | 프로필 이름 |
| --host | option | — | — | 호스트 (기본값: 0.0.0.0) |

## `profile start-all`

모든 프로필 시작

`usage: animaworks profile start-all [-h] [--host HOST]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --host | option | — | — | 호스트 (기본값: 0.0.0.0) |

## `profile stop`

프로필 서버 중지

`usage: animaworks profile stop [-h] [--force] name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| name | positional | — | — | 프로필 이름 |
| --force | flag | false | — | 강제 중지 (시간 초과 후 SIGKILL) |

## `profile stop-all`

실행 중인 모든 프로필 중지

`usage: animaworks profile stop-all [-h] [--force]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --force | flag | false | — | 강제 중지 (시간 초과 후 SIGKILL) |

## `rag-repair-status`

모든 anima의 RAG 복구 상태 표시

`usage: animaworks rag-repair-status [-h] [--json]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --json | flag | false | — | 구조화된 JSON 출력 |

## `remake-assets`

Vibe Transfer를 사용하여 참조 anima의 아트 스타일에 맞게 캐릭터 에셋 재생성. 선택적 단계 실행 및 자동 백업 지원.

`usage: animaworks remake-assets [-h] --style-from STYLE_FROM [--steps STEPS]
                                [--prompt PROMPT]
                                [--vibe-strength VIBE_STRENGTH]
                                [--vibe-info-extracted VIBE_INFO_EXTRACTED]
                                [--seed SEED]
                                [--image-style {anime,realistic}]
                                [--no-backup] [--dry-run]
                                anima`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| anima | positional | — | — | 에셋을 재생성할 anima 이름 |
| --style-from | option | — | — | 스타일 참조로 사용할 anima 이름 (전신 이미지 사용) |
| --steps | option | — | — | 실행할 단계 목록 (쉼표로 구분) (선택지: fullbody, bustup, icon, chibi, 3d, rigging, animations). 기본값: 모든 단계 |
| --prompt | option | — | — | 캐릭터 프롬프트 재정의 (기본값: prompt.txt에서 읽기) |
| --vibe-strength | option | 0.6 | — | Vibe Transfer 강도 0.0-1.0 (기본값: 0.6) |
| --vibe-info-extracted | option | 0.8 | — | Vibe Transfer 정보 추출 0.0-1.0 (기본값: 0.8) |
| --seed | option | — | — | 재현을 위한 시드 (전신 생성 전용) |
| --image-style | option | — | anime, realistic | 이미지 스타일 (기본값: config.json image_gen.image_style에서) |
| --no-backup | flag | false | — | 기존 에셋의 자동 백업 건너뛰기 |
| --dry-run | flag | false | — | API 호출 없이 수행될 작업만 표시 |

## `repair-rag`

활성 phase3 벡터 소유자를 통해 RAG 재구축.

`usage: animaworks repair-rag [-h]
                             [--anima ANIMA | --all | --suspect-only | --list-suspects]
                             [--full] [--shared]
                             [--window-minutes WINDOW_MINUTES]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --anima | option | — | — | 복구할 anima 이름 |
| --all | flag | false | — | 모든 활성 anima 복구 |
| --suspect-only | flag | false | — | 최근 RAG 손상 증거가 있는 anima만 복구 |
| --list-suspects | flag | false | — | 복구 없이 손상 의심 RAG DB 목록만 표시 |
| --full | flag | false | — | 파괴적 격리 및 전체 재구축에 대한 확인 필요 |
| --shared | flag | false | — | 호환성을 위해 허용; phase3는 항상 공유 컬렉션도 재구축 |
| --window-minutes | option | — | — | --suspect-only/--list-suspects 조회 기간 (기본값: 복구 설정 창) |
| --reason | option | "manual_repair_rag_cli" | — | ==SUPPRESS== |

## `reset`

서버 중지, 런타임 디렉터리 삭제, 재초기화

`usage: animaworks reset [-h] [--restart]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --restart | flag | false | — | 리셋 후 서버 시작 |

## `restart`

서버 재시작 (중지 후 시작)

`usage: animaworks restart [-h] [--host HOST] [--port PORT] [--foreground]
                          [--force]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --host | 옵션 | "0.0.0.0" | — | — |
| --port | 옵션 | 18500 | — | — |
| --foreground, -f | 플래그 | false | — | 로그 출력과 함께 포그라운드로 실행 (기본값: 데몬화) |
| --force | 플래그 | false | — | 강제 중지: SIGTERM 시간 초과 후 SIGKILL, 고아 러너도 종료 |

## `send`

애니마에게 메시지 전송 (발신자는 애니마 또는 인간 사용자일 수 있음)

`usage: animaworks send [-h] [--thread-id THREAD_ID] [--reply-to REPLY_TO]
                       [--intent INTENT]
                       from_person to_person message`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| from_person | 위치 인자 | — | — | 발신자 이름 (애니마가 아닌 이름은 인간으로 전송) |
| to_person | 위치 인자 | — | — | 수신자 이름 |
| message | 위치 인자 | — | — | 메시지 내용 |
| --thread-id | 옵션 | — | — | 스레드 ID |
| --reply-to | 옵션 | — | — | 답장할 메시지 ID |
| --intent | 옵션 | "" | — | 메시지 의도: delegation, report, question 또는 빈 값 |

## `serve`

서버 시작 (start의 별칭)

`usage: animaworks serve [-h] [--host HOST] [--port PORT] [--foreground]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --host | 옵션 | "0.0.0.0" | — | — |
| --port | 옵션 | 18500 | — | — |
| --foreground, -f | 플래그 | false | — | 로그 출력과 함께 포그라운드로 실행 (기본값: 데몬화) |

## `skills`

Skill Hub 가져오기 설치 및 관리

`usage: animaworks skills [-h]
                         {install,list,inspect,remove,ledger,rollback,quarantine}
                         ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `skills inspect`

설치되었거나 격리된 스킬 검사

`usage: animaworks skills inspect [-h] [--target {personal,common}]
                                 [--anima ANIMA]
                                 skill_name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| skill_name | 위치 인자 | — | — | 스킬 이름 |
| --target | 옵션 | "personal" | personal, common | 설치 대상 |
| --anima | 옵션 | — | — | personal 대상의 애니마 이름 |

## `skills install`

로컬 경로, URL 또는 GitHub 소스에서 스킬 설치

`usage: animaworks skills install [-h] [--target {personal,common}]
                                 [--anima ANIMA] [--dry-run] [--replace]
                                 [--force] [--quarantine]
                                 [--trust-level {community,untrusted}]
                                 source`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| source | 위치 인자 | — | — | 로컬 경로, 직접 URL 또는 github:owner/repo/path |
| --target | 옵션 | "personal" | personal, common | 설치 대상 |
| --anima | 옵션 | — | — | personal 대상의 애니마 이름 |
| --dry-run | 플래그 | false | — | 설치 없이 스테이징 및 스캔만 수행 |
| --replace | 플래그 | false | — | 백업 생성 후 기존 스킬 교체 |
| --force | 플래그 | false | — | 호환성을 위해 허용됨; 가져오기 정책은 여전히 적용됨 |
| --quarantine | 플래그 | false | — | 활성 카탈로그 대신 격리 영역에 설치 |
| --trust-level | 옵션 | "community" | community, untrusted | 활성 설치에 적용할 신뢰 수준 |

## `skills ledger`

스킬 콘텐츠 변경 내역 나열

`usage: animaworks skills ledger [-h] [--anima ANIMA] [skill_name]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| skill_name | 위치 인자 | — | — | 스킬 이름으로 필터링 |
| --anima | 옵션 | — | — | 개인 기록을 특정 Anima로 필터링 |

## `skills list`

설치된 스킬 목록 표시

`usage: animaworks skills list [-h] [--target {personal,common}]
                              [--anima ANIMA] [--quarantine]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --target | 옵션 | "personal" | personal, common | 설치 대상 |
| --anima | 옵션 | — | — | personal 대상의 애니마 이름 |
| --quarantine | 플래그 | false | — | 격리 항목 목록 표시 |

## `skills quarantine`

격리된 스킬 관리

`usage: animaworks skills quarantine [-h] {list,promote} ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `skills quarantine list`

격리된 스킬 목록 표시

`usage: animaworks skills quarantine list [-h] [--target {personal,common}]
                                         [--anima ANIMA]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --target | 옵션 | "personal" | personal, common | 설치 대상 |
| --anima | 옵션 | — | — | personal 대상의 애니마 이름 |

## `skills quarantine promote`

승인 후 격리된 스킬 승격

`usage: animaworks skills quarantine promote [-h] --approval-id APPROVAL_ID
                                            [--replace]
                                            [--trust-level {community,untrusted}]
                                            [--target {personal,common}]
                                            [--anima ANIMA]
                                            skill_name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| skill_name | 위치 인자 | — | — | 스킬 이름 |
| --approval-id | 옵션 | — | — | 인간 승인 식별자 |
| --replace | 플래그 | false | — | 백업으로 기존 활성 스킬 교체 |
| --trust-level | 옵션 | "community" | community, untrusted | 승격 후 적용할 신뢰 수준 |
| --target | 옵션 | "personal" | personal, common | 설치 대상 |
| --anima | 옵션 | — | — | personal 대상의 애니마 이름 |

## `skills remove`

설치되었거나 격리된 스킬 제거

`usage: animaworks skills remove [-h] [--target {personal,common}]
                                [--anima ANIMA]
                                skill_name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| skill_name | 위치 인자 | — | — | 스킬 이름 |
| --target | 옵션 | "personal" | personal, common | 설치 대상 |
| --anima | 옵션 | — | — | personal 대상의 애니마 이름 |

## `skills rollback`

원장 ID로 스킬 콘텐츠 변경 하나를 롤백

`usage: animaworks skills rollback [-h] --anima ANIMA id`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| id | 위치 인자 | — | — | 원장 항목 ID |
| --anima | 옵션 | — | — | 롤백을 위한 Anima context/owner |

## `start`

AnimaWorks 서버 시작

`usage: animaworks start [-h] [--host HOST] [--port PORT] [--foreground]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --host | 옵션 | "0.0.0.0" | — | — |
| --port | 옵션 | 18500 | — | — |
| --foreground, -f | 플래그 | false | — | 로그 출력과 함께 포그라운드로 실행 (기본값: 데몬화) |

## `status`

게이트웨이에서 시스템 상태 표시

`usage: animaworks status [-h]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `stop`

실행 중인 서버를 종료합니다

`usage: animaworks stop [-h] [--force]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --force | 플래그 | false | — | 강제 종료: SIGTERM 시간 초과 후 SIGKILL, 고아 러너도 종료 |

## `supervisor`

anima용 슈퍼바이저 도구

`usage: animaworks supervisor [-h]
                             {org-dashboard,ping,read-state,task-tracker} ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `supervisor org-dashboard`

상태와 작업이 포함된 조직 트리 표시

`usage: animaworks supervisor org-dashboard [-h]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `supervisor ping`

하위 anima가 살아있는지 확인

`usage: animaworks supervisor ping [-h] [--name NAME]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --name | 옵션 | — | — | 특정 anima 이름 (생략 시 모든 하위 항목) |

## `supervisor read-state`

하위 상태 읽기 (current_state.md, 대기 중)

`usage: animaworks supervisor read-state [-h] name`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| name | 위치 인자 | — | — | 대상 anima 이름 |

## `supervisor task-tracker`

위임된 작업 추적

`usage: animaworks supervisor task-tracker [-h] [--status STATUS]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --status | 옵션 | "delegated" | — | 상태별 필터 (기본값: delegated) |

## `task`

영구 작업 큐 관리

`usage: animaworks task [-h]
                       {board,show,claim,release,done,cancel,note,add,update,resume,list}
                       ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `task add`

새 작업 추가

`usage: animaworks task add [-h] [--source {human,anima}] --instruction
                           INSTRUCTION --assignee ASSIGNEE [--summary SUMMARY]
                           [--relay-chain RELAY_CHAIN] [--workspace WORKSPACE]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --source | 옵션 | "anima" | human, anima | — |
| --instruction | 옵션 | — | — | 원본 지시문 텍스트 |
| --assignee | 옵션 | — | — | 담당 anima 이름 |
| --summary | 옵션 | — | — | 한 줄 요약 (기본값: instruction[:100]) |
| --relay-chain | 옵션 | — | — | 쉼표로 구분된 릴레이 체인 |
| --workspace | 옵션 | — | — | 작업의 working_directory용 워크스페이스 별칭 또는 경로 |

## `task board`

작업 보드의 항목을 확인하고 조작합니다.

`usage: animaworks task board [-h] [--anima ANIMA | --all] [--stale STALE]
                             [--limit LIMIT] [--json]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --anima | 옵션 | — | — | 소유자의 작업 및 위임된 작업 표시 |
| --all | 플래그 | false | — | 모든 소유자 표시 |
| --stale | 옵션 | — | — | DAYS보다 오래된 작업만 표시 |
| --limit | 옵션 | 50 | — | 최대 행 수 (기본값: 50) |
| --json | 플래그 | false | — | JSON 출력 |

## `task cancel`

작업 취소

`usage: animaworks task cancel [-h] --reason REASON [--json] task_id`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| task_id | 위치 인자 | — | — | — |
| --reason | 옵션 | — | — | — |
| --json | 플래그 | false | — | JSON 출력 |

## `task claim`

시간 제한 작업 임대 획득

`usage: animaworks task claim [-h] [--ttl TTL] [--json] task_id`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| task_id | 위치 인자 | — | — | — |
| --ttl | 옵션 | "30m" | — | 최대 4시간까지 임대 기간 (기본값: 30m) |
| --json | 플래그 | false | — | JSON 출력 |

## `task done`

작업 완료 처리

`usage: animaworks task done [-h] --note NOTE [--json] task_id`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| task_id | 위치 인자 | — | — | — |
| --note | 옵션 | — | — | — |
| --json | 플래그 | false | — | JSON 출력 |

## `task list`

작업 목록 표시

`usage: animaworks task list [-h]
                            [--status {pending,in_progress,delegated,done,cancelled}]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --status | 옵션 | — | pending, in_progress, delegated, done, cancelled | — |

## `task note`

작업에 메모 추가

`usage: animaworks task note [-h] [--json] task_id text`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| task_id | 위치 인자 | — | — | — |
| text | 위치 인자 | — | — | — |
| --json | 플래그 | false | — | JSON 출력 |

## `task release`

작업 임대 해제

`usage: animaworks task release [-h] [--json] task_id`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| task_id | 위치 인자 | — | — | — |
| --json | 플래그 | false | — | JSON 출력 |

## `task resume`

저장된 실행 입력으로 작업 재큐

`usage: animaworks task resume [-h] --task-id TASK_ID`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --task-id | 옵션 | — | — | 작업 ID |

## `task show`

전체 작업 세부 정보 표시

`usage: animaworks task show [-h] [--anima ANIMA] [--json] task_id`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| task_id | 위치 인자 | — | — | 작업 ID 또는 위임자 별칭 |
| --anima | 옵션 | — | — | 작업 소유자로 모호성 해소 |
| --json | 플래그 | false | — | JSON 출력 |

## `task update`

작업 상태 업데이트

`usage: animaworks task update [-h] --task-id TASK_ID --status
                              {pending,delegated,done,cancelled}
                              [--summary SUMMARY]`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --task-id | 옵션 | — | — | 작업 ID |
| --status | 옵션 | — | pending, delegated, done, cancelled | — |
| --summary | 옵션 | — | — | 업데이트된 요약 |

## `task-store`

담당자 단위 작업 원본의 유지보수 및 마이그레이션

`usage: animaworks task-store [-h]
                             {status,quiesce,resume,migrate,backup,export} ...`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `task-store backup`

WAL 포함 DB 백업 새로 생성

`usage: animaworks task-store backup [-h] --anima ANIMA --destination
                                    DESTINATION`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --anima | 옵션 | — | — | 대상 담당자 이름 |
| --destination | 옵션 | — | — | 사용되지 않은 출력 경로 |

## `task-store export`

종료 중인 현재 상태를 새 디렉터리로 내보내기

`usage: animaworks task-store export [-h] --anima ANIMA --destination
                                    DESTINATION`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --anima | 옵션 | — | — | 대상 담당자 이름 |
| --destination | 옵션 | — | — | 사용되지 않은 출력 경로 |

## `task-store migrate`

종료 중인 기존 원장 가져오기 (백업 필수)

`usage: animaworks task-store migrate [-h] --anima ANIMA --backup BACKUP`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --anima | 옵션 | — | — | 대상 담당자 이름 |
| --backup | 옵션 | — | — | WAL 포함 DB 백업 새로 생성 |

## `task-store quiesce`

새 실행 획득을 영구 종료

`usage: animaworks task-store quiesce [-h] --anima ANIMA`

| 이름 | 유형 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --anima | 옵션 | — | — | 대상 담당자 이름 |

## `task-store resume`

새 실행 가져오기 재개

`usage: animaworks task-store resume [-h] --anima ANIMA`

| 이름 | 종류 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --anima | option | — | — | 대상 담당자 이름 |

## `task-store status`

종료 게이트와 실행 수 표시

`usage: animaworks task-store status [-h] --anima ANIMA`

| 이름 | 종류 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --anima | option | — | — | 대상 담당자 이름 |

## `tmp`

AnimaWorks 임시 디렉터리 검사 및 정리

`usage: animaworks tmp [-h] {list,clean} ...`

| 이름 | 종류 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `tmp clean`

오래되었거나 큰 임시 파일 제거

`usage: animaworks tmp clean [-h] [--older-than DAYS] [--min-size SIZE] [--all]
                            [--force] [--project] [--dry-run]`

| 이름 | 종류 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --older-than | option | 7 | — | DAYS보다 오래된 항목 제거 (기본값: 7) |
| --min-size | option | — | — | SIZE 이상의 항목도 제거 (예: 100M, 1G) |
| --all | flag | false | — | tmp 아래 모든 항목 제거 (--force 필요) |
| --force | flag | false | — | 전체 정리를 위한 --all과 함께 필요 |
| --project | flag | false | — | 저장소 tmp/도 정리 |
| --dry-run | flag | false | — | 삭제하지 않고 제거될 항목만 표시 |

## `tmp list`

tmp 사용량 요약 표시

`usage: animaworks tmp list [-h] [--project] [--top TOP]`

| 이름 | 종류 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --project | flag | false | — | 런타임 tmp 외에 저장소 tmp/도 포함 |
| --top | option | 20 | — | 루트당 최대 표시 항목 수 (기본값: 20) |

## `vault`

암호화된 볼트 값 관리

`usage: animaworks vault [-h] {status,init,get,store,list,delete} ...`

| 이름 | 종류 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `vault delete`

한 섹션에서 키 제거

`usage: animaworks vault delete [-h] [--shared] key`

| 이름 | 종류 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| key | positional | — | — | 제거할 키 |
| --shared | flag | false | — | Anima 네임스페이스 대신 공유 섹션에서 삭제 (절대 캐스케이드되지 않음) |

## `vault get`

키로 값 가져오기

`usage: animaworks vault get [-h] [--shared] key`

| 이름 | 종류 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| key | positional | — | — | 검색할 키 |
| --shared | flag | false | — | 공유 섹션에서만 검색 (기본값: Anima 네임스페이스, 그 다음 공유) |

## `vault init`

볼트 키가 없으면 생성

`usage: animaworks vault init [-h]`

| 이름 | 종류 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `vault list`

Anima 네임스페이스와 공유 섹션의 키 목록 표시

`usage: animaworks vault list [-h] [--shared]`

| 이름 | 종류 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| --shared | flag | false | — | 공유 섹션만 표시 (ANIMAWORKS_ANIMA_DIR 필요 없음) |

## `vault status`

값 없이 키와 암호화 상태 표시

`usage: animaworks vault status [-h]`

| 이름 | 종류 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| — | — | — | — | — |

## `vault store`

키-값 쌍 저장

`usage: animaworks vault store [-h] [--shared] key [value]`

| 이름 | 종류 | 기본값 | 선택지 | 설명 |
|---|---|---|---|---|
| key | positional | — | — | 저장할 키 |
| value | positional | — | — | 저장할 값 (Anima 범위 호환 모드 전용) |
| --shared | flag | false | — | stdin 또는 숨김 프롬프트에서 값을 읽어 공유 섹션에 저장 |
