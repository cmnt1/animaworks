# 자주 있는 문제와 대처법

업무 중에 자주 마주치는 문제와 그 대처 절차를 정리한 참조.
각 문제는 "증상 → 원인 → 대처 절차" 형식으로 기재되어 있다.

막힐 때는 먼저 이 문서를 읽고 해당 항목의 절차를 따를 것.
여기서 해결되지 않으면 `troubleshooting/escalation-flowchart.md` 를 참조하여 적절히 에스컬레이션할 것.

---

## 메시지가 도착하지 않음

### 증상

- 보냈어야 할 메시지에 답변이 없음
- 상대방이 메시지를 받지 못했다고 함
- `send_message` 를 실행했지만 상대가 반응하지 않음

### 원인

1. 수신처 지정 오류(Anima 정식 명칭・사용자 별칭・`slack:` / `chatwork:` 프리픽스 등) 또는 해결 순서에 맞지 않는 지정
2. 서버가 종료되어 있음
3. 상대가 하트비트 간격 사이에 있음(다음 시작까지 읽지 않은 상태)
4. 전송 처리가 오류로 실패했음(글로벌 전송 상한・대화 깊이 상한・세션 내 DM 상한, `RecipientResolutionError` 등)
5. `intent` 가 미지정 또는 부정. DM에서는 `report` / `question` 만. 작업 위임은 `delegate_task` 을 사용(`send_message` 에 `intent="delegation"` 을 붙이면 비권장 메시지가 반환됨)
6. 세션 내 DM 제한 초과(**동일 수신처에는 1세션 1통까지**. **다른 수신처의 최대 인원수**는 `status.json` 의 `role` 에 따른 `max_recipients_per_run` — 아래 표. 개별 덮어쓰기는 `status.json` 의 동일 이름 필드)

**역할별 `max_recipients_per_run`(`core/config/schemas.py` `ROLE_OUTBOUND_DEFAULTS`)**

| role | 1세션당 최대 수신처 수(각 1통) |
|------|--------------------------------------|
| manager | 10 |
| engineer | 5 |
| writer | 3 |
| researcher | 3 |
| ops | 2 |
| general | 2 |

### 대처 절차

1. **전송 대상의 이름・수신처 형식을 확인한다**
   - `send_message` 의 `to` 파라미터가 의도한 상대에게 해결되는지 확인
   - 구현(`core/messaging/outbound.py` `resolve_recipient`)의 해결 순서는 대략 다음과 같음:
     1. 알려진 Anima 이름과의 **완전 일치**(대소문자 구분) → 내부
     2. `config.json` `external_messaging.user_aliases` 의 **별칭**(대소문자 무시) → 외부(preferred_channel)
     3. `slack:USERID` / `chatwork:ROOMID` → 외부 직접
     4. 베어 Slack 사용자 ID(`U` + 영숫자 8자 이상) → Slack 직접
     5. 알려진 Anima 이름의 **대소문자 무시 일치** → 내부
     6. 그 외 → 해결 실패
   - 내부 Anima로 확실히 전달하려면 `~/.animaworks/animas/<名前>/` 또는 `reference/organization/structure.md` 상의 **정식 명칭**을 사용
   - 확인 방법:
     ```
     search_memory(query="조직", scope="common_knowledge")
     ```
     또는 `read_memory_file(path="reference/organization/structure.md")` 로 조직의 모든 Anima 이름을 확인
   - **주의**: 채팅 중에 사람에게 보낼 경우 `send_message` 는 사용할 수 없음. 직접 텍스트로 답하면 사람에게 도달함. 채팅 외(heartbeat 등)에서 사람에게 연락할 경우 `call_human` 를 사용

2. **서버의 가동 상태를 확인한다**
   - 자신이 동작하고 있는 시점에 서버는 가동 중이어야 함
   - 그래도 불안하면 상급자에게 "메시지가 도착하지 않는다"는 내용을 보고

3. **상대의 응답을 기다린다**
   - 상대는 하트비트 간격(예: 30분마다)으로 수신함을 확인함
   - 즉시 답변이 없어도 다음 하트비트에서 처리됨
   - 긴급한 경우 상급자에게 "급히 연락을 취하고 싶다"고 보고하고 수동 시작을 요청

4. **전송 오류가 발생한 경우**
   - 오류 메시지를 기록
   - `state/current_state.md` 에 상황을 기재
   - 상급자에게 보고

### 구체적인 예

```
# 名前を間違えていた場合
send_message(to="Aoi", content="...", intent="report")   # OK
send_message(to="aoi", content="...", intent="report")  # 名前が異なればエラーになる可能性あり

# DM は intent 必須（report / question のみ）。委譲は delegate_task
# 1セッションあたりの「別宛先」数はロールにより異なる（例: general は最大2人、engineer は5人まで）。同一宛先へは1回のみ
send_message(
    to="aoi",
    content="了解しました。作業を開始します。",
    intent="report",           # 必須: report / question
    reply_to="msg-abc123",     # 任意: 元メッセージのID
    thread_id="thread-xyz789"  # 任意: スレッドID
)

# 確認・お礼・お知らせのみのDMは不可 → post_channel（Board）を使用
```

---

## 작업을 진행할 수 없음

"조건이 갖춰질 때까지 기다린다" "블록 중"이라는 상태는 존재하지 않음(`blocked` 은 폐지됨). 선택할 수 있는 것은 진행・종료・상담의 3가지뿐.

### 증상

- 작업을 진행하려 했지만 필요한 정보나 권한이 부족함
- 다른 Anima의 작업 완료를 기다리는 상태
- 외부 서비스가 오류를 반환함

### 원인

1. 의존 작업이 미완료
2. 권한 부족(`permissions.json` 에서 허용되지 않은 조작. `permissions.md` 만 있는 환경에서도 첫 `load_permissions` 에서 JSON이 생성되고 MD는 `.bak` 으로 피신됨)
3. 필요한 정보가 부족함
4. 외부 서비스의 장애

### 대처 절차

1. **같은 조작을 반복하지 않는다**
   - 무엇이 부족한지 구체적으로 특정
   - "누구의" "무엇 작업이" "언제까지" 필요한지 정리

2. **스스로 해결할 수 있는지 판단한다**
   - 다른 접근 방식으로 회피할 수 없는지 검토
   - 기억을 검색하여 과거에 비슷한 문제가 없었는지 확인:
     ```
     search_memory(query="오류 내용이나 키워드", scope="episodes")
     search_memory(query="회피", scope="knowledge")
     ```

3. **해결할 수 없으면 의뢰자에게 보고한다**(`troubleshooting/escalation-flowchart.md` 참조). 보고에는 다음을 포함할 것:
   - 무엇을 하려 했는지
   - 무엇이 부족한지・무엇을 기다리고 있는지
   - 스스로 시도한 대처와 권장 사항
   ```
   send_message(
       to="上司の名前",
       content="【進捗報告】\nタスク: XXXの実装\n事実: YYYのAPI権限が不足\n試行: permissions.jsonを確認したが該当設定なし\n推奨: API権限の追加をお願いします",
       intent="report"
   )
   ```

4. **작업의 취급을 결정한다**
   - 계속할 가능성이 있다면 아무것도 하지 않아도 됨(작업은 `pending` 그대로. 선언 없이 세션이 끝나도 자동으로 `pending` 로 돌아감)
   - 필요 없어지면 `update_task(status="cancelled", summary="理由")` 으로 함

5. **기다리는 동안 진행할 수 있는 작업이 없는지 확인한다**
   - 영속 작업 큐: 도구를 사용할 수 있으면 `list_tasks`, 또는 `Bash: animaworks-tool task list` 로 확인
   - `list_tasks(detail=true)` 로 미착수・의존 관계・대응 필요 사유를 확인. 기존 작업의 복제나 수동 재투입은 하지 않음
   - 다른 작업에 착수

---

## 기억을 찾을 수 없음

### 증상

- 과거에 했던 일을 떠올릴 수 없음
- 절차서가 있어야 하는데 찾을 수 없음
- 검색해도 해당 결과가 반환되지 않음

### 원인

1. 검색 키워드가 적절하지 않음
2. 검색 스코프(scope)가 너무 좁음
3. 아직 기억으로 기록되지 않음(처음 하는 작업)
4. 파일 경로를 잘못 지정함

### 대처 절차

1. **스코프를 넓혀 재검색한다**
   - 먼저 `all` 스코프로 넓게 검색:
     ```
     search_memory(query="검색할 키워드", scope="all")
     ```
   - 결과가 너무 많으면 스코프를 좁힘:
     ```
     search_memory(query="Slack설정", scope="procedures")    # 절차서로 한정
     search_memory(query="Slack장애", scope="episodes")      # 과거 사건으로 한정
     search_memory(query="Slack", scope="knowledge")         # 배운 지식으로 한정
     ```

2. **키워드를 바꿔 재검색한다**
   - 동의어나 관련어로 시도(예: "전송" "메시지" "알림" "연락")
   - 영어 키워드로도 시도(예: "slack", "message", "send")
   - 부분 일치를 의식(예: "Chatwork" → "chatwork" "챗워크")

3. **공유 지식을 검색한다**
   - 개인 기억에 없으면 공유 지식에 존재할 가능성이 있음:
     ```
     search_memory(query="검색 키워드", scope="common_knowledge")
     ```
   - 공유 지식의 목차를 확인:
     ```
     read_memory_file(path="common_knowledge/00_index.md")
     ```

4. **디렉터리를 직접 확인한다**
   - Mode S(Claude Agent SDK) 등에서는 내장 `Glob` 로 Anima 디렉터리 아래를 나열할 수 있음. Mode A 등에서는 `read_memory_file` 로 알려진 경로를 열거나 `search_memory` 로 넓게 탐색
   - 파일 이름을 알면 직접 읽음:
     ```
     read_memory_file(path="procedures/slack-setup.md")
     read_memory_file(path="knowledge/xxx-findings.md")
     ```

5. **기억이 존재하지 않는 경우**
   - 처음 하는 작업일 가능성이 있음
   - 공유 지식(`common_knowledge/`)에 관련 가이드가 있는지 확인
   - 상급자나 동료에게 노하우가 있는지 문의
   - 작업 완료 후에는 MUST로 기억으로 기록(다음 번을 위해)
   - 오래되거나 중복된 기억은 `archive_memory_file(path="...", reason="...")` 로 archive/ 에 피신할 수 있음(삭제가 아니라 이동. `reason` 은 필수)

### 검색 스코프 목록

| scope | 검색 대상 | 용도 |
|-------|---------|------|
| `knowledge` | 배운 지식・노하우 | 대응 방침, 기술 메모 |
| `episodes` | 과거 행동 로그 | "언제 무엇을 했는지"의 사실 확인 |
| `procedures` | 절차서 | "어떻게 하는지"의 절차 확인 |
| `common_knowledge` | 모든 Anima 공유 지식 | 조직 규칙, 시스템 가이드 |
| `skills` | 스킬・공통 스킬(벡터 검색) | 스킬의 발견・검색 |
| `activity_log` | 최근 행동 로그(도구 실행 결과・메시지 등) | "방금 읽은 메일" "아까의 검색 결과" 등 최근 사실 확인 |
| `all` | 위 모든 것(벡터 검색 + activity_log BM25를 RRF로 통합) | 키워드 존재 확인, 광범위한 검색 |

---

## 권한이 없음

### 증상

- 도구를 실행했더니 "권한이 없습니다" "Permission denied" 등의 오류가 반환됨
- 파일을 읽거나 쓰려 했지만 접근할 수 없음
- 명령을 실행하려 했지만 거부됨

### 원인

1. `permissions.json` 에서 허용되지 않은 조작(`permissions.md` 만 있는 경우 `load_permissions` 가 읽기 시에 JSON 상당으로 정규화. 무효 JSON은 경고 후 개방 기본값으로 폴백하기도 함)
2. 외부 도구의 카테고리가 레지스트리에 미활성화(`check_permissions` 의 `available_but_not_enabled`)
3. 파일 경로가 허용 범위 밖(보호 파일에 쓰기, `file_roots` 밖 등). 추가로 **글로벌** 거부는 `permissions.global.json` 와 프레임워크 측 패턴이 있음

### 対処手順

1. **自分の権限を確認する**
   ```
   check_permissions()
   ```
   - JSON で返る。`internal_tools`・`external_tools.enabled` / `available_but_not_enabled`・`file_access`（read/write）・`restrictions`（コマンド deny 等）を確認する
   - 生の設定は `read_memory_file(path="permissions.json")`（存在しない場合は `permissions.md`）で確認可能
   - システムプロンプトに注入される権限説明は、ランタイムが JSON から整形したテキストになる

2. **許可されている操作か確認する**
   - 自分の `anima_dir` 内は原則読み書き可能（`identity.md` 等の保護ファイルは除く）。上司・同僚の `activity_log` や配下の `state/` 読み取りはロール次第で `check_permissions` の `file_access` に反映される
   - シェルコマンド: `permissions.json` の `commands`（allow/deny）に従う。グローバル危険パターンはフレームワーク側でもブロックされる

3. **権限が必要な場合の対応**
   - その操作が本当に必要か再検討する
   - 別のアプローチ（許可された範囲内の操作）で代替できないか考える
   - 代替不可能な場合は上司に権限追加を依頼する:
   ```
   send_message(
       to="上司の名前",
       content="【権限追加依頼】\n目的: XXXの作業のため\n必要な権限: /path/to/dir の読み取り\n理由: YYYの情報を参照する必要があるため",
       intent="question"
   )
   ```

4. **絶対にやってはいけないこと**
   - 権限チェックを回避しようとすること
   - 許可されていないコマンドを別の方法で実行しようとすること
   - 他のAnimaの権限を利用しようとすること

---

## 도구를 사용할 수 없음

### 증상

- 도구를 호출했지만 "도구를 찾을 수 없습니다" 등의 오류가 반환됨
- 외부 도구(Slack, Gmail 등)를 사용할 수 없음

### 원인

1. 해당 도구가 `permissions.json`(또는 로드 시 정규화된 MD 유래 설정)에서 허용되지 않았거나, 게이트가 있는 액션이 명시적으로 허용되지 않음
2. 스킬 파일을 찾을 수 없음
3. 외부 서비스의 인증 정보가 설정되지 않음

### 조치 절차

1. **스킬에서 도구 사용법 확인**
   - `read_memory_file`로 시스템 프롬프트의 스킬 카탈로그에 표시된 경로(예: `skills/foo/SKILL.md`, `common_skills/bar/SKILL.md`)를 지정하고 절차 전문을 가져옴
   - B-mode에서 외부 도구가 허용된 경우 `Bash: animaworks-tool <ツール> <サブコマンド>`로 호출 가능

2. **권한 확인**
   ```
   check_permissions()
   ```
   - `external_tools.enabled`: 이 Anima의 도구 레지스트리에 등록된 외부 도구 카테고리(세션에 실제로 전달되는 것)
   - `external_tools.available_but_not_enabled`: 프레임워크에 구현은 있지만 이 Anima에서는 레지스트리에 없는 카테고리. `permissions.json`의 허용·게이트 액션·실행 모드와 함께 확인

3. **사용할 수 없는 경우**
   - `permissions.json`로 해당 도구/액션이 허용되었는지, 인증 정보(`shared/credentials.json` 등)가 있는지 확인
   - 그래도 안 되면 상급자에게 요청("왜 그 도구가 필요한지"를 명시)

4. **MCP 통합 모드(S/C/D/G: Claude Agent SDK / Codex CLI / Cursor Agent / Gemini CLI)의 경우**
   - 내장 도구는 프리픽스 없이 사용 가능(예: `send_message`). 찾을 수 없으면 프로세스 재시작 필요
   - 외부 도구는 `read_memory_file`로 스킬 본문을 읽고 CLI 사용법을 확인한 후 **Bash** 경유로 `animaworks-tool <ツール> <サブコマンド>`를 실행(에이전트의 Bash 도구 사용)
   - 장시간 도구(이미지 생성, 로컬 LLM 등)는 `animaworks-tool submit`로 비동기 실행

5. **D-mode(Cursor Agent) 특유의 흔한 문제**
   - **CLI를 찾을 수 없음**: 호스트에 `cursor-agent` CLI가 설치되어 있는지 확인
   - **인증 오류**: 터미널에서 `agent login`를 실행하여 로그인
   - **폴백**: 해결되지 않으면 `execution_mode`을 `A`으로 바꾸거나, 모델을 LiteLLM 경유(Mode A)로 전환하여 운영

6. **G-mode(Gemini CLI) 특유의 흔한 문제**
   - **CLI를 찾을 수 없음**: 호스트에 `gemini` CLI가 설치되어 있는지 확인
   - **인증 오류**: `gemini auth login`를 실행하거나 환경 변수 `GEMINI_API_KEY`를 설정
   - **폴백**: 해결되지 않으면 `execution_mode`을 `A`으로 바꾸거나, 모델을 LiteLLM 경유(Mode A)로 전환. `gemini/` 프리픽스는 Google 프로바이더용으로 `google/`에 리매핑될 수 있음

7. **A-mode(LiteLLM)의 경우**
   - 외부 도구는 `read_memory_file`로 스킬 본문을 읽고 사용법을 확인한 후 **Bash** 경유로 `animaworks-tool <ツール> <サブコマンド>`를 실행

8. **도구가 오류를 반환하는 경우**
   - 오류 메시지를 정확히 기록
   - 인증 오류면 상급자에게 보고(인증 정보 설정은 관리자의 책임)
   - 일시적인 타임아웃·레이트 제한이면 잠시 기다렸다가 재시도(횟수·간격은 도구 구현·서버 설정에 따름)
   - 개선되지 않으면 요청자에게 사실·시도한 것을 보고

도구 체계의 전체 모습은 `operations/tool-usage-overview.md`를 참조.

---

## 컨텍스트가 너무 길어짐

### 증상

- 세션이 오래 지속됨
- 응답이 느려짐
- 시스템에서 "컨텍스트 상한에 가까워지고 있음" 알림이 옴

### 원인

- 장시간 작업이나 다수의 도구 호출로 컨텍스트 윈도우가 소비됨
- 대량의 파일 내용을 읽음

### 조치 절차

1. **작업 상태를 단기 기억에 저장**(MUST)
   - 현재 작업 상태를 `shortterm/`에 기록(채팅 세션 시에는 `shortterm/chat/`):
   ```
   write_memory_file(
       path="shortterm/chat/session_state.md",
       content="## 作業状態\n\n### 実行中のタスク\n- XXXの実装（50%完了）\n\n### 次のステップ\n1. YYYを完了する\n2. ZZZをテストする\n\n### 重要な中間結果\n- AAAの調査結果: BBB\n- CCCの設定値: DDD",
       mode="overwrite"
   )
   ```
   - 하트비트 세션 시에는 `shortterm/heartbeat/session_state.md` 사용

2. **`state/current_state.md` 업데이트**(MUST)
   ```
   write_memory_file(
       path="state/current_state.md",
       content="## 現在のタスク\n\nXXXの実装\n\n### 進捗\n- 50%完了\n- 次回はYYYから再開\n\n### メモ\n- 重要な発見事項をここに記載",
       mode="overwrite"
   )
   ```

3. **중요한 지식은 영구 기억에 저장**(SHOULD)
   - 작업 중 얻은 지식은 `knowledge/`에 저장:
   ```
   write_memory_file(
       path="knowledge/xxx-findings.md",
       content="# XXXに関する知見\n\n## 発見事項\n...",
       mode="overwrite"
   )
   ```

4. **세션 지속을 기다림**
   - 시스템이 자동으로 새 세션을 시작
   - 새 세션에서는 `shortterm/chat/`(또는 `shortterm/heartbeat/`)의 내용이 컨텍스트에 포함됨
   - `state/current_state.md`을 다시 읽고 작업 재개

### 예방책

- 큰 파일은 전체를 읽지 말고 필요한 부분만 검색
- 긴 작업은 정기적으로 `state/current_state.md` 업데이트
- 중간 결과는 수시로 기억에 기록

---

## 메시지 전송이 제한됨

### 증상

- `send_message`이나 `post_channel`을 실행했더니 오류가 반환됨
- `GlobalOutboundLimitExceeded: 1時間あたりの送信上限（N通）に到達しています...` 또는 24시간 버전의 동종 메시지가 표시됨
- `GlobalOutboundLimitExceeded: アクティビティログ読み取り失敗のため送信をブロックしました`으로 표시됨(`core/messaging/cascade_limiter.py` — 발신자의 `activity_log`을 읽을 수 없을 때)
- `ConversationDepthExceeded: {相手}との会話が10分間に6ターンに達しました...`으로 표시됨

### 원인

- **역할별 글로벌 상한**: `dm_sent` / `message_sent` / `channel_post`를 activity_log에서 집계하여 1시간·24시간 건수로 판정(`ConversationDepthLimiter.check_global_outbound`). 상한은 `status.json`의 `max_outbound_per_hour` / `max_outbound_per_day`으로 개별 덮어쓰기하고, 미설정이면 `role`의 기본값(`ROLE_OUTBOUND_DEFAULTS`) 사용

**역할별 1시간 / 24시간 상한(코드 기본값)**

| role | 1시간 | 24시간 |
|------|-------|--------|
| manager | 60 | 300 |
| engineer | 40 | 200 |
| writer | 30 | 150 |
| researcher | 30 | 150 |
| ops | 20 | 80 |
| general | 15 | 50 |

- 동일 채널에 연속 게시가 쿨다운 기간 내였음(`config.json` `heartbeat.channel_post_cooldown_s`, 기본 300초)
- 양자 간 왕복이 깊이 제한을 초과(`Messenger.send` 내의 `ConversationDepthLimiter.check_depth`. **내부 Anima 대상 DM만** 해당. `heartbeat.depth_window_s` / `heartbeat.max_depth`, 기본 **600초**·**최대 6턴**. 문구는 "10분·6턴")
- 활동 로그 읽기 오류(디스크·권한·손상 등) → 안전 측에서 전송 차단

### 조치 절차

1. **오류 메시지 확인**: 시간 제한·24시간 제한·깊이 제한·activity_log 실패 중 하나를 식별
2. **전송 이력 돌아보기**: 불필요한 전송이 없었는지 확인
3. **대기**: 시간 제한이면 다음 1시간 프레임까지(메시지에 "다음 전송 가능 시각(참고)"이 붙을 수 있음), 24시간 제한이면 다음 날까지, 깊이 제한이면 윈도우가 비워질 때까지
4. **전송 내용 기록**: 상한 도달 시 메시지 지시대로 이번 턴에서는 `send_message`을 사용하지 않고 `state/current_state.md`에 쓴 다음, 다음 세션에서 전송
5. **activity_log 실패 시**: 관리자에게 로그·디스크·해당 Anima의 `activity_log/`를 확인 요청(차단은 발신자 측 로그 읽기에 의존)
6. **긴급 연락**: `call_human`은 이러한 글로벌 상한의 대상 외
7. **전송 통합**: 여러 보고를 한 통으로 정리. 깊이 제한에 도달하면 Board(`post_channel`)로 전환

자세한 내용은 `communication/sending-limits.md`를 참조.

---

## 명령이 차단됨

### 증상

- 명령을 실행하려 했더니 "PermissionDenied" "Command blocked" 등의 오류가 반환됨
- 특정 명령만 실행할 수 없음

### 원인

1. 프레임워크/`permissions.global.json`의 글로벌 거부 패턴에 해당하는 명령(예: `rm -rf /` 등)
2. `permissions.json`의 `commands.deny`에 열거된 명령

### 조치 절차

1. **자신의 권한 확인**
   ```
   check_permissions()
   ```
   - `restrictions`에 deny된 명령이 열거됨. 함께 `read_memory_file(path="permissions.json")`로 설정을 직접 확인(레거시 환경에서는 `permissions.md`)

2. **대체 수단 검토**
   - 차단된 명령과 동등한 작업을 허용된 도구로 실현할 수 없는지 생각
   - 예: `rm -rf`가 차단된 경우 개별 파일 삭제는 허용될 가능성 있음

3. **권한 변경이 필요한 경우**
   - 상급자에게 차단 해제 요청
   - 요청 시 "왜 그 명령이 필요한지"를 명시

---

## 프롬프트가 축소됨

### 증상

- 평소보다 시스템 프롬프트가 얇음, Priming(자동 회상)이 빈 상태에 가까움
- 긴 대화나 큰 사용자 메시지 이후, 응답 전에 프롬프트가 재구축된 듯한 동작이 있음

### 원인

크게 2개 층이 있음.

**1. Priming(자동 회상)의 티어** — `core/prompt/builder.py`의 `resolve_prompt_tier(context_window)`이 추정 컨텍스트 윈도우에서 티어를 결정. 윈도우의 해결 순서는 `core/prompt/context.py` `resolve_context_window`: **`~/.animaworks/models.json`(SSoT)** → 비권장 `config.json` `model_context_windows` → `MODEL_CONTEXT_WINDOWS` 등의 코드 내 폴백 → 기본 128k.

| 티어 | 조건(`context_window`) | Priming 처리(`core/agent/priming.py`) |
|--------|--------------------------|---------------------------------------------|
| full | **≥ 128_000** | 6채널분을 `format_priming_section`로 정형화하여 그대로 게재 |
| standard | **≥ 32_000 그리고 < 128_000** | 위와 동일하게 가져온 후, **정형화된 텍스트가 4000자를 초과하면 앞 4000자 + 생략 마커** |
| light | **≥ 16_000 그리고 < 32_000** | **발신자 프로필(Channel A)만**(i18n 헤더 포함). 다른 채널은 버림 |
| minimal | **< 16_000** | **Priming 전체를 스킵**(빈 문자열) |

하트비트/cron용 쿼리 문은 최근 `[REFLECTION]`을 activity_log에서 모은 텍스트가 됨(긴 템플릿 전문이 아님).

**2. 시스템 프롬프트 본체의 수축** — `core/agent/priming.py` `_fit_prompt_to_context_window`: 시스템+사용자의 추정 토큰 + 도구 스키마 overhead가 **컨텍스트 윈도우의 약 80%**를 초과하면 `build_system_prompt`을 **시스템 예산 75% → 50% → 25%**로 단계적으로 줄여 재구축. **25% 이하 단계**에서는 **Priming 블록과 인간용 알림 블록을 비운 후** 적용. 그래도 들어가지 않으면 시스템 프롬프트를 **바이트 단위로 하드 트렁케이트**.

### 조치 절차

1. **부족한 컨텍스트는 명시적으로 획득**: `search_memory` / `read_memory_file`로 조직·절차·공유 지식을 읽음(특히 `minimal` / `light`에서는 Priming이 약함)
2. **작업 상태를 디스크에 남김**: `state/current_state.md`이나 `shortterm/`에 요약을 써 두고, 세션이 끊겨도 재개할 수 있게 함
3. **상급자·관리자와 상담**: 실제 운영에서 빠듯하면 `models.json`의 `context_window`이나 모델 변경을 검토

---

## 기타 흔한 문제

### 파일을 찾을 수 없음

- **원인**: 경로 지정 실수, 파일이 존재하지 않음
- **조치**: Mode S에서는 `Glob`, 그 외에는 `search_memory`이나 알려진 경로의 `read_memory_file`로 탐색
- **주의**: `read_memory_file`은 Anima 디렉터리 상대(예: `knowledge/xxx.md`)에 더해 `common_knowledge/`·`reference/`·`common_skills/` 프리픽스로 공유 디렉터리를 읽을 수 있음. `Read`(에이전트 내장)은 별도 규칙으로 경로가 결정됨

### read_channel에서 inbox를 지정할 수 없음

- **원인**: `read_channel`은 Board의 공유 채널용. inbox(받은 편지함)는 채널이 아님
- **조치**: inbox의 메시지는 시스템이 자동 처리. `read_channel`에 `inbox`이나 `inbox/`을 지정하면 오류가 됨

### 명령이 타임아웃됨

- **원인**: 처리 시간이 `timeout`를 초과함
- **조치**: Bash 런타임의 `timeout` 파라미터를 늘림 (기본값: 30초)
- **주의**: 장시간 실행되는 명령에는 적절한 타임아웃 값을 설정할 것

### 상대방의 Anima가 존재하지 않음

- **원인**: Anima 이름의 오류, 또는 해당 Anima가 아직 생성되지 않음
- **조치**: 상급자에게 확인할 것. 조직 구조는 `reference/organization/structure.md`를 참조

### venv 재구축 후 SEGV가 빈번하게 발생

- **원인**: ChromaDB나 PyTorch의 메이저 버전이 올라가면 기존 vectordb(HNSW 세그먼트)와 호환되지 않게 되어 읽기 시 SEGV(Segmentation Fault)가 발생함. ChromaDB 1.5.x의 Rust 바인딩은 손상된 인덱스에 대해 Python 예외가 아닌 SEGV를 일으키는 알려진 문제가 있음 (chromadb #6852, #6949, #6979)
- **조치**: venv를 재구축한 후에는 vectordb도 반드시 전체 재구축할 것
  1. 서버를 종료함
  2. `~/.animaworks/vectordb/`와 각 `~/.animaworks/animas/*/vectordb/`를 삭제(또는 백업 후 삭제)
  3. `~/.animaworks/index_meta.json`를 삭제
  4. 서버를 시작함 (시작 시 자동으로 재인덱싱됨)
- **예방**: 패키지 업데이트 시 chromadb·torch·sentence-transformers의 버전 변경을 확인하고, 변경이 있으면 vectordb를 재구축할 것
