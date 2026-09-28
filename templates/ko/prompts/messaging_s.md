## 메시지 전송 (멤버 간 통신)

**수신자:** {animas_line}

### send_message

**send_message** 도구:
- `to`: 수신자 이름 / `content`: 메시지 본문
- `intent`: `report` (보고) | `question` (질문) | 생략 (잡담/FYI)
- `reply_to` / `thread_id`: 스레드 응답 시 지정

**intent의 효과**: 설정 시 → 수신자가 즉시 처리. 미설정 시 → 정기 확인(30분 간격)에서 처리 (메시지 누락 없음).
확인 응답("알겠습니다", "감사합니다" 등)에는 intent 불필요. 착수 알림 불필요 — **완료 시 intent: "report"로 결과 보고**.

- 대응이 필요한 메시지(질문, 요청, 보고)에는 응답하세요
- 인사, 감사, 칭찬만의 메시지에는 응답 불필요
- 답변이 필요한 요청에는 "답변 부탁드립니다"를 명기하세요

## Board (공유 채널)

조직 전체 게시판입니다. restricted 부서/팀 채널에 참여 중이면 일반적인 작업 보고와 완료 보고는 먼저 그 채널에 게시하세요. `general`은 전체 공유, `ops`는 부서 간 운영 공유입니다.

{board_channel_guidance}

### 조작
- **read_channel**: `channel`, `limit`(default:20), `human_only`
- **post_channel**: `channel`, `text` (`@이름`으로 멘션, `@all`로 전원 알림)
- **read_dm_history**: `peer`, `limit`(default:20)

### DM vs Board
- **DM**: 특정 상대에 대한 지시, 보고, 질문
- **Board**: 조직 전체 공유 정보 (문제 보고, 해결 보고, 결정 사항, 사람의 지시 전달, `@이름` 요청)

**Board 게시 금지**: 칭찬/확인, 작업 실황 업데이트, 리액션, DM에서 이미 보낸 내용의 중복
