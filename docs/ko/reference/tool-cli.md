<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/tool-cli.md -->
<!-- i18n: source-sha256=b9ff04d94def616cd790e1887ca962f78541de300e8469605ed371561a1b9716 generated=2026-10-06 engine=luna model=gpt-6-luna-2026-09-22 translator=2 -->

# 도구 CLI 참조: `animaworks-tool`

`animaworks-tool`는 core의 외부 도구 스키마에서 생성되었습니다. common / personal 도구는 런타임 의존이므로 대상에서 제외됩니다.

## `submit`에 의한 백그라운드 실행

`animaworks-tool submit <tool_name> [args...]`는 장시간 실행되는 도구를 pending task로 등록하고, 완료 결과를 inbox로 전달합니다. 실행에는 `ANIMAWORKS_ANIMA_DIR`가 필요합니다.

## `discord_channel_post`

Discord 텍스트 채널에 메시지를 게시합니다. 메시지는 Anima 신원(이름 + 아바타)으로 표시됩니다. 향후 참조를 위해 메시지 ID를 반환합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `channel_id` | string | 예 | Discord 채널 ID |
| `text` | string | 예 | 메시지 텍스트 (Markdown 지원, 최대 2000자) |

## `discord_unreplied`

이름을 언급했지만 답변되지 않은 Discord 메시지를 찾습니다. 하트비트 중 대기 중인 요청을 확인하는 데 유용합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `channel_id` | string | 아니요 | 검색할 Discord 채널 ID (생략 시 모든 캐시된 채널 검색) |
| `limit` | integer | 아니요 | 최대 결과 수 (기본값: 10) |

## `enclave_ask`

격리된 enclave에 질문하고 사실과 근거 ID만 포함된 답변 받기

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `case_id` | string | 아니요 | 선택적 사례 식별자(생략하면 anima 이름과 날짜를 바탕으로 생성) |
| `enclave` | string | 예 | 연결할 enclave의 설정 이름 |
| `question` | string | 예 | 격리된 인스턴스에 보낼 질문 |

## `google_sheets_append_values`

스프레드시트 range/table의 마지막 데이터 뒤에 행을 추가합니다 (append_values). 덮어쓰기에 주의하세요. 기존 데이터 확인에는 read_values를 먼저 사용하세요.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `range` | string | 예 | A1 범위, 시트 이름 포함 가능 (예: 'Sheet1!A1:C10') |
| `spreadsheet_id` | string | 예 | 스프레드시트 ID 또는 전체 docs.google.com URL |
| `value_input_option` | string | 아니요 | 입력 해석 방식: USER_ENTERED (기본값) 또는 RAW |
| `values` | array | 예 | 셀 값의 2D 배열 (행 목록) |

## `google_sheets_read`

스프레드시트 범위에서 셀 값을 읽습니다 (read_values).

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `range` | string | 아니요 | A1 범위, 시트 이름 포함 가능 (예: 'Sheet1!A1:C10') 기본값: A1:Z1000 |
| `spreadsheet_id` | string | 예 | 스프레드시트 ID 또는 전체 docs.google.com URL |

## `google_sheets_tabs`

스프레드시트의 시트 탭과 기본 메타데이터를 나열합니다 (list_tabs).

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `spreadsheet_id` | string | 예 | 스프레드시트 ID 또는 전체 docs.google.com URL |

## `google_sheets_write_values`

스프레드시트 범위의 셀 값을 덮어씁니다 (write_values). 덮어쓰기에 주의하세요. 기존 데이터 확인에는 read_values를 먼저 사용하세요.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `range` | string | 예 | A1 범위, 시트 이름 포함 가능 (예: 'Sheet1!A1:C10') |
| `spreadsheet_id` | string | 예 | 스프레드시트 ID 또는 전체 docs.google.com URL |
| `value_input_option` | string | 아니요 | 입력 해석 방식: USER_ENTERED (기본값) 또는 RAW |
| `values` | array | 예 | 셀 값의 2D 배열 (행 목록) |

## `slack_channel_post`

Bot Token API를 통해 실제 Slack 채널에 메시지를 게시합니다. 향후 slack_channel_update를 위한 메시지 ts를 반환합니다. 외부 Slack 채널(내부 Board 아님)에 사용하세요.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `channel_id` | string | 예 | Slack 채널 ID (예: C0AJ4J5KK46) |
| `text` | string | 예 | 메시지 텍스트 (Markdown은 Slack mrkdwn으로 변환됨) |
| `thread_ts` | string | 아니요 | 스레드에서 답장할 선택적 부모 메시지 ts |

## `slack_channel_update`

ts로 기존 Slack 메시지를 업데이트합니다. 메시지는 조용히 대체됩니다 (알림 없음). task-board 같은 라이브 대시보드에 사용하세요.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `channel_id` | string | 예 | Slack 채널 ID |
| `text` | string | 예 | 새 메시지 텍스트 |
| `ts` | string | 예 | 업데이트할 메시지 타임스탬프 (slack_channel_post 결과에서) |
