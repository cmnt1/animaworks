<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/reference/tool-cli.md -->
<!-- i18n: source-sha256=70a59165699d3f658dee8a9762c751fad73d0048acdadd4bbe79a622aebddb1b generated=2026-10-21 engine=nanogpt model=deepseek/deepseek-v4.1-flash translator=2 -->

# 도구 CLI 참조: `animaworks-tool`

`animaworks-tool`은 core의 외부 도구 스키마에서 생성됩니다. common / personal 도구는 런타임에 따라 달라지므로 대상에서 제외됩니다.

## `submit`을 통한 백그라운드 실행

`animaworks-tool submit <tool_name> [args...]`은 장시간 실행되는 도구를 대기 작업으로 등록하고, 완료 결과를 받은 편지함으로 전달합니다. 실행하려면 `ANIMAWORKS_ANIMA_DIR`가 필요합니다.

## `bluesky_author_feed`

핸들 또는 DID에서 최근 공개 Bluesky 게시물을 가져옵니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `actor` | string | 예 | Bluesky 핸들 또는 DID. |
| `include_replies` | boolean | 아니요 | 답글 및 스레드 포함. 기본값: false. |
| `limit` | integer | 아니요 | 반환할 최대 게시물 수, 1-100. 기본값: 25. |

## `bluesky_search`

Bluesky AppView API를 통해 공개 Bluesky 게시물을 검색합니다. 시장 동향, company/ticker 언급, 뉴스 토론 신호에 유용합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `author` | string | 아니요 | 선택적 작성자 핸들 (@. 없이 또는 포함) |
| `lang` | string | 아니요 | 선택적 언어 코드, 예: ja 또는 en. |
| `limit` | integer | 아니요 | 반환할 최대 게시물 수, 1-100. 기본값: 25. |
| `query` | string | 예 | 검색 쿼리 문자열. |
| `since` | string | 아니요 | 선택적 ISO 날짜시간 하한. |
| `sort` | string | 아니요 | 정렬 모드. 기본값: latest. |
| `tag` | string | 아니요 | 선택적 해시태그 (# 없이 또는 포함). |
| `until` | string | 아니요 | 선택적 ISO 날짜시간 상한. |

## `discord_channel_post`

Discord 텍스트 채널에 메시지를 게시합니다. 메시지는 Anima 아이덴티티(이름 + 아바타)로 표시됩니다. 향후 참조를 위해 메시지 ID를 반환합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `channel_id` | string | 예 | Discord 상위 채널 ID. 스레드에 답글을 달 때는 반드시 상위 텍스트 채널 ID여야 합니다(스레드 ID가 아님) — Discord 웹훅은 상위 채널에 연결되어 있으며 별도의 thread_id 매개변수를 통해 스레드를 대상으로 합니다. |
| `text` | string | 예 | 메시지 텍스트 (Markdown 지원, 최대 2000자) |
| `thread_id` | string | 아니요 | 게시할 스레드 채널 ID. 스레드 내에서 도착한 메시지에 답글을 달 때 필수 — 그렇지 않으면 게시물이 상위 채널에 남습니다. 수신 메시지의 [reply_instruction: ...] 주석에 표시된 값을 사용하세요. |

## `discord_unreplied`

내 이름이 언급되었지만 아직 답변하지 않은 Discord 메시지를 찾습니다. 하트비트 중 대기 중인 요청을 확인할 때 유용합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `channel_id` | string | 아니요 | 검색할 Discord 채널 ID(선택 사항 — 생략하면 캐시된 모든 채널을 검색합니다) |
| `limit` | integer | 아니요 | 최대 결과 수(기본값: 10) |

## `enclave_ask`

격리된 enclave에 질문을 보내고 job_id를 즉시 받습니다. 상태를 확인할 수 있으며, 완료 결과는 inbox에 도착합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `case_id` | string | 아니요 | 선택적 케이스 식별자(생략하면 anima 이름과 날짜를 바탕으로 생성) |
| `enclave` | string | 예 | 연결할 enclave의 설정 이름 |
| `model` | string | 아니요 | 선택적 모델 지정(enclave 측 model_profiles의 이름. 예: luna-max / opus-high. 생략하면 enclave의 기본값) |
| `question` | string | 예 | 격리된 인스턴스에 보낼 질문 |
| `wait_s` | integer | 아니요 | 결과 확인을 위해 대기할 최대 시간(초)(기본값: 0. 0이면 즉시 반환) |

## `enclave_cancel`

실행 중이거나 대기 중인 enclave 작업을 취소합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `enclave` | string | 예 | 연결할 enclave의 설정 이름 |
| `job_id` | string | 예 | enclave ask가 반환한 작업 ID |

## `enclave_status`

enclave 작업의 상태, 경과 시간, 진행 상황 및 완료 시 확인된 사실을 확인합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `enclave` | string | 예 | 연결할 enclave의 설정 이름 |
| `job_id` | string | 예 | enclave ask가 반환한 작업 ID |

## `google_sheets_append_values`

스프레드시트 range/table(append_values)의 마지막 데이터 뒤에 행을 추가합니다. 덮어쓰기에 주의하세요. 기존 데이터를 확인하려면 먼저 read_values를 사용하세요.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `range` | string | 예 | A1 범위. 시트 이름을 지정할 수도 있습니다(예: 'Sheet1!A1:C10') |
| `spreadsheet_id` | string | 예 | 스프레드시트 ID 또는 전체 docs.google.com URL |
| `value_input_option` | string | 아니요 | 입력 해석 방식: USER_ENTERED(기본값) 또는 RAW |
| `values` | array | 예 | 셀 값의 2차원 배열(행 목록) |

## `google_sheets_read`

스프레드시트 범위의 셀 값을 읽습니다(read_values).

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `range` | string | 아니요 | A1 범위. 시트 이름을 지정할 수도 있습니다(예: 'Sheet1!A1:C10'). 기본값: A1:Z1000 |
| `spreadsheet_id` | string | 예 | 스프레드시트 ID 또는 전체 docs.google.com URL |

## `google_sheets_tabs`

스프레드시트의 시트 탭과 기본 메타데이터를 나열합니다(list_tabs).

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `spreadsheet_id` | string | 예 | 스프레드시트 ID 또는 전체 docs.google.com URL |

## `google_sheets_write_values`

스프레드시트 범위의 셀 값을 덮어씁니다(write_values). 덮어쓰기에 주의하세요. 기존 데이터를 확인하려면 먼저 read_values를 사용하세요.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `range` | string | 예 | A1 범위. 시트 이름을 지정할 수도 있습니다(예: 'Sheet1!A1:C10') |
| `spreadsheet_id` | string | 예 | 스프레드시트 ID 또는 전체 docs.google.com URL |
| `value_input_option` | string | 아니요 | 입력 해석 방식: USER_ENTERED(기본값) 또는 RAW |
| `values` | array | 예 | 셀 값의 2차원 배열(행 목록) |

## `notebooklm_add_source_file`

로컬 파일(PDF, DOCX, MD, CSV 등)을 NotebookLM 노트북에 소스로 추가합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `file_path` | string | 예 | 파일의 절대 경로 |
| `notebook_id` | string | 예 | 노트북 ID |

## `notebooklm_add_source_text`

붙여넣은 텍스트를 NotebookLM 노트북에 소스로 추가합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `notebook_id` | string | 예 | 노트북 ID |
| `text` | string | 예 | 추가할 텍스트 콘텐츠 |
| `title` | string | 아니요 | 소스의 선택적 제목 |

## `notebooklm_add_source_url`

웹 페이지 URL을 NotebookLM 노트북에 소스로 추가합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `notebook_id` | string | 예 | 노트북 ID |
| `url` | string | 예 | 추가할 웹 페이지 URL |

## `notebooklm_chat`

NotebookLM 노트북의 소스에 대해 질문합니다. 소스 참조와 함께 답변을 반환합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `message` | string | 예 | 질문할 내용 |
| `notebook_id` | string | 예 | 노트북 ID |

## `notebooklm_create_notebook`

새 Google NotebookLM 노트북을 생성합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `title` | string | 예 | 노트북 제목 |

## `notebooklm_delete_notebook`

Google NotebookLM 노트북을 삭제합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `notebook_id` | string | 예 | 노트북 ID |

## `notebooklm_generate_artifact`

NotebookLM 노트북에서 아티팩트를 생성합니다. 유형: audio_overview, briefing_doc, study_guide, faq, timeline, mind_map. 장시간 실행 — 백그라운드 실행에는 'animaworks-tool submit'을 사용하세요.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `artifact_type` | string | 예 | 생성할 아티팩트 유형 |
| `instructions` | string | 아니요 | 생성에 대한 사용자 지정 지침 |
| `language` | string | 아니요 | 출력 언어 (기본값: en) |
| `notebook_id` | string | 예 | 노트북 ID |

## `notebooklm_get_notebook`

NotebookLM 노트북의 요약, 설명 및 주제를 가져옵니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `notebook_id` | string | 예 | 노트북 ID |

## `notebooklm_get_source_fulltext`

NotebookLM 노트북에 있는 소스의 전체 텍스트 콘텐츠를 가져옵니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `notebook_id` | string | 예 | 노트북 ID |
| `source_id` | string | 예 | 소스 ID (notebooklm_list_sources에서 가져옴) |

## `notebooklm_list_artifacts`

NotebookLM 노트북의 아티팩트를 나열합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `artifact_type` | string | 아니요 | 유형별 필터 (예: AUDIO, REPORT, MIND_MAP) |
| `notebook_id` | string | 예 | 노트북 ID |

## `notebooklm_list_notebooks`

모든 Google NotebookLM 노트북을 나열합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| — | — | — | — |

## `notebooklm_list_sources`

NotebookLM 노트북의 모든 소스를 나열합니다.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `notebook_id` | string | 예 | 노트북 ID |

## `slack_channel_post`

Bot Token API를 통해 실제 Slack 채널에 메시지를 게시합니다. slack_channel_update로 나중에 업데이트할 수 있도록 메시지 ts를 반환합니다. 내부 Board가 아닌 외부 Slack 채널에 사용하세요.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `channel_id` | string | 예 | Slack 채널 ID(예: C0AJ4J5KK46) |
| `text` | string | 예 | 메시지 텍스트(Markdown은 Slack mrkdwn으로 변환됩니다) |
| `thread_ts` | string | 아니요 | 스레드에 답글을 달 때 사용할 상위 메시지 ts(선택 사항) |

## `slack_channel_update`

ts를 기준으로 기존 Slack 메시지를 업데이트합니다. 메시지는 알림 없이 교체됩니다. task-board와 같은 실시간 대시보드에 사용하세요.

| 인수 | 유형 | 필수 | 설명 |
|---|---|---|---|
| `channel_id` | string | 예 | Slack 채널 ID |
| `text` | string | 예 | 새 메시지 텍스트 |
| `ts` | string | 예 | 업데이트할 메시지 타임스탬프(slack_channel_post 결과에서 확인) |
