# 문제 발생 시 플로우차트

문제가 발생했을 때 "스스로 해결해야 하는지" "누군가에게 상담하거나 보고해야 하는지"를 판단하기 위한 플로우차트.

이 문서는 판단이 어려울 때 참조한다. 명백히 스스로 해결할 수 있는 문제에 이 플로우차트는 필요 없다.

---

## 판단 플로우차트

문제가 발생하면 다음 단계를 순서대로 판단한다.

### Step 1: 문제의 유형 파악

문제를 다음 중 하나로 분류한다:

| 유형 | 설명 | 예 |
|------|------|----|
| **A. 기술적 문제** | 도구나 시스템의 작동 관련 문제 | 도구 오류, 권한 부족, 파일 부재 |
| **B. 업무적 문제** | 작업 진행 방식이나 판단 관련 문제 | 사양 불명, 우선순위 판단, 블록 |
| **C. 대인적 문제** | 다른 Anima와의 협업 관련 문제 | 응답 없음, 지침 모순, 담당 불명 |
| **D. 긴급 문제** | 즉각적인 대응이 필요한 문제 | 데이터 손실 위험, 보안 우려 |

### Step 2: 긴급도 판단

| 긴급도 | 기준 | 대응 |
|--------|------|------|
| **높음** | 방치하면 데이터 손실·보안 위험이 있음 | MUST: 즉시 상급자에게 보고 |
| **높음** | 다른 Anima의 작업이 완전히 중단됨 | MUST: 즉시 상급자에게 보고 |
| **중간** | 자신의 작업이 차단되지만 다른 작업에 착수 가능 | SHOULD: 1시간 이내에 상급자에게 보고 |
| **낮음** | 작업 효율이 떨어지지만 진행 가능 | MAY: 다음 하트비트에서 보고 |

**긴급도가 "높음"인 경우** → Step 5로 진행 (즉시 에스컬레이션)

### Step 3: 자력 해결 시도

다음 절차로 자력 해결을 시도한다. 각 단계에서 해결되면 그 시점에 종료한다.

1. **기억 검색**
   ```
   search_memory(query="問題に関連するキーワード", scope="all")
   ```
   - 과거에 같은 문제를 경험했는지 확인
   - 절차서(procedures/）에 대처 방법이 있는지 확인
   - **방금 한 일을 떠올리고 싶다면**(최근 도구 결과·메일 본문·검색 결과 등) `scope="activity_log"`를 시도한다. `scope="all"`에서도 activity_log는 BM25 경유로 RRF 병합되지만, 명시적으로 activity_log로 좁히면 노이즈가 줄기 쉽다

2. **공유 지식 검색**
   ```
   search_memory(query="問題に関連するキーワード", scope="common_knowledge")
   ```
   - `troubleshooting/common-issues.md`에 해당하는 문제가 있는지 확인

3. **다른 접근 방식 검토**
   - 목적을 달성할 대체 수단이 없는지 생각
   - 권한 부족이면 다른 경로, 도구 오류면 다른 도구

4. **자력 해결 제한 시간**
   - 기술적 문제: 15분 이내에 해결하지 못하면 에스컬레이션
   - 업무적 문제: 판단이 어려우면 즉시 에스컬레이션 (잘못된 판단의 위험을 피함)
   - 대인적 문제: 1회 재시도 후 에스컬레이션

### Step 4: 에스컬레이션 대상 결정

| 문제 유형 | 먼저 상담할 대상 | 상담해도 해결되지 않는 경우 |
|-----------|----------------|----------------------|
| **A. 기술적 문제** | 동료 (같은 전문 분야인 경우) | 상급자 |
| **B. 업무적 문제** | 상급자 | ― |
| **C. 대인적 문제** | 상급자 (중재 요청) | ― |
| **D. 긴급 문제** | 상급자 (즉시) | ― |

**판단 기준:**
- 동료에게 상담해도 되는 조건: 같은 상급자를 두는 동료이고, 상대의 전문 분야와 관련된 문제인 경우
- 상급자에게 보고 MUST인 조건: 업무 판단 필요, 다른 부서가 관여, 긴급도가 높음
- 다른 부서의 Anima에게는 직접 연락하지 않는다 (MUST: 상급자 경유)

### Step 5: 에스컬레이션 실행

보고 메시지에는 다음 요소를 MUST로 포함한다:

1. **상황**: 무엇이 일어나고 있는가
2. **원인**: 무엇이 원인으로 생각되는가 (불명이면 "원인 조사 중")
3. **시도**: 스스로 무엇을 시도했는가
4. **요청**: 상급자에게 무엇을 해주길 바라는가 (판단, 권한 부여, 중재 등)

**send_message의 제약 (구현 준수)**:
- `intent`은 MUST: `report`(보고), `question`(질문) 중 하나. 생략 불가. `intent="delegation"`은 **거부**된다 (작업 위임은 `delegate_task`만)
- acknowledgment(확인 응답)·감사·FYI는 DM 불가. Board(post_channel) 사용
- 한 run에서 같은 수신처에 DM을 한 번만 보낼 수 있다. 수신처 수 상한은 없다
- 시간·일 단위 발신 예산이나 대화 깊이에 따른 발신 차단은 없다. 자세한 내용은 `communication/sending-limits.md` 참조
- **수신자**: Anima 이름, 또는 인간 별칭 (config에서 설정된 경우 Slack/Chatwork 등으로 외부 배송)
- **채팅 중**: 인간 사용자에 대한 응답은 직접 텍스트로 한다. `send_message`은 다른 Anima 대상(또는 설정된 별칭 경유 외부)에만 사용
- **인간에게 연락**(별칭 미설정 등 `send_message`로 도달하지 않는 수신자): 톱레벨 Anima이고 알림 설정이 있는 경우 `call_human`을 사용한다 (아래)
- 스레드 답변 시 `reply_to`와 `thread_id`을 지정하여 맥락을 유지한다
- 긴급도가 "높음"이고 인간의 즉시 대응이 필요한 경우 `call_human`을 검토한다 (`subject`, `body`, `priority`)

**post_channel(Board)의 제약** (팀 전체 공유에 사용):
- 메타 미설정 채널(general, ops 등)은 모두 이용 가능. 멤버제 채널은 멤버만 게시 가능(ACL). 접근 권한이 없으면 `manage_channel(action="info", channel="チャネル名")`로 멤버를 확인할 수 있다
- 한 run에서 같은 채널에 한 번 게시할 수 있다. run 간 게시 쿨다운은 없다
- 본문에 `@名前`로 멘션 가능. 멘션 대상에게는 DM 알림이 도착한다

**call_human과 인간 알림 기반 (`core/notification/` 구현 준수)**:

- **도구의 유효 조건**: `config.json`의 `human_notification.enabled`이 true이고, `HumanNotifier.from_config`가 **실제로 1건 이상의 전송 채널**을 구축했을 것(`channels[]` 중 `enabled: true`이고 등록된 `type`만 대상. `enabled: false`은 스킵, 미등록 `type`은 경고 로그 후 스킵)
- **톱레벨 한정 (supervisor 게이트)**: `config.animas`에 **그 Anima 이름의 엔트리가 있고**, `supervisor`가 비 null일 때, `HumanNotifier`은 부여되지 않고 `call_human`은 사용할 수 없다 (부하는 상급자에게 `send_message`로 에스컬레이션). **`animas`에 미등록된 Anima는 이 게이트를 통과하지 않으므로**, 이론상 알림 채널만으로 `call_human`가 붙을 가능성이 있다. 운영에서는 모든 Anima를 `animas`에 명시하고, `supervisor: null`만 인간 알림을 갖도록 하면 안전
- **전송 방식**: `HumanNotifier.notify`이 유효한 각 채널로 **병렬 전송**(`asyncio.gather(..., return_exceptions=True)`). 채널마다 성공 문자열 또는 `ERROR`를 포함한 실패 문자열이 반환되고, **예외는 1채널에서 삼켜지고 나머지는 계속 진행**
- **대응 채널 유형**(`human_notification.channels[].type`): `slack`, `chatwork`, `line`, `telegram`, `ntfy`(`core/notification/channels/*.py`의 `@register_channel`에 대응). 복수 채널을 병렬로 정의 가능
- **파라미터**: `subject`, `body`는 필수. `priority`은 임의. 열거는 `low` / `normal` / `high` / `urgent`(생략 시 `normal`). **`PRIORITY_LEVELS` 외의 문자열은 `HumanNotifier.notify` 내에서 `normal`로 정규화**
- **우선순위 표시**:
  - **Slack / Chatwork / LINE / Telegram**: `high` / `urgent`일 때 앞에 **`[HIGH]` / `[URGENT]`**(`priority.upper()`). `low` / `normal`에서는 부여하지 않음
  - **ntfy**: HTTP 헤더 `Priority`에 `low=2`, `normal=3`, `high=4`, `urgent=5`을 설정. 본문은 요청 바디(최대 약 4096자), `Title` 헤더에 제목 + 필요하면 `(from Anima名)`
- **Slack**(`channels/slack.py`):
  - **Bot Token + `channel`**(`chat.postMessage`) 또는 **Incoming Webhook**. 본문은 `md_to_slack_mrkdwn`으로 Slack용으로 정형화
  - **Bot이고 `anima_name`이 있는 경우**: API의 `username`에 Anima 이름을 전달하므로, **본문 쪽의 `(from Anima名)`는 붙이지 않는다**(Webhook 모드에서는 본문에 `(from Anima名)`을 부여). 설정과 에셋이 갖춰지면 `icon_url`도 부여 가능
  - **스레드 답변 라우팅**(`reply_routing.py`): Bot으로 게시하고, `anima_name`이 비어 있지 않고, API 응답에 `ts`가 있을 때만 `notification_map.json`에 저장. 경로는 `{data_dir}/run/notification_map.json`(보통 `~/.animaworks/run/`). 엔트리는 **생성 후 최대 7일**로 폐기. Webhook은 `ts`을 얻을 수 없어 매핑 불가
  - 라우팅 시 가능하면 Slack API로 스레드 요약을 획득하고, 실패 시 저장된 알림 문의 요약으로 폴백. Inbox로의 외부 메시지는 `intent="question"`
- **Chatwork**: `room_id`은 **숫자만** 허용. 본문은 `md_to_chatwork` 변환 후 `[info][title]…[/title]…[/info]` 형식
- **LINE**: Push API. 텍스트는 최대 5000자로 잘라냄
- **Telegram**: `parse_mode=HTML`. 제목은 `<b>…</b>`, 전체 4096자 이내로 조정(이스케이프 후 잘라냄)
- **크레덴셜**: 기본 `NotificationChannel._resolve_credential_with_vault`은 **설정 키의 env → `{キー}__{anima_name}`(vault/shared）→ 원시 키**의 순. Slack Bot은 이에 더해 `get_credential("slack", "notification", …)`의 폴백 있음(각 `channels/*.py` 참조)
- **채팅 UI**: 스트리밍 응답으로 **`notification_sent`** 이벤트가 전송된다(`core/anima/messaging.py` 경유. 외부 채널과는 다른 경로)
- **기록**: `call_human` 실행 시, 통합 활동 로그에 **`human_notify`**(`via`은 구현상 고정으로 `configured_channels`). 함께 `tool_result`도 남는다. Priming의 "Pending Human Notifications"는 **과거 24시간·최대 10건**의 `human_notify`을 집약(`core/memory/priming/outbound.py`)
- **기타 HumanNotifier 이용**: 백그라운드 도구 완료 등, **동일한 `HumanNotifier`**으로 프레임워크가 인간에게 보내는 경로가 있다(`call_human` 도구 외. 톱레벨 Anima에 한정하는 점은 동일)
- **Mode S(CLI)**: `animaworks-tool call_human "件名" "本文" [--priority …]`에서도 같은 계열의 알림을 보낼 수 있다

**call_human의 파라미터 (요약)**:
- `subject`, `body`는 필수. `priority`은 임의(`low` / `normal` / `high` / `urgent`, 기본 `normal`. 잘못된 값은 `normal` 취급)

---

## 에스컬레이션 메시지 템플릿

### 템플릿 1: 블록 보고

```
send_message(
    to="上司の名前",
    content="""【ブロック報告】

■ 状況
タスク「月次レポート作成」がブロックされています。

■ 原因
売上データが格納されている /data/sales/ ディレクトリへの読み取り権限がありません。

■ 試行済み
- permissions.json を確認 → /data/sales/ は未許可
- 代替データソースを検索 → 該当なし

■ 依頼
/data/sales/ への読み取り権限の追加をお願いします。""",
    intent="report"
)
```

### 템플릿 2: 판단 요청

```
send_message(
    to="上司の名前",
    content="""【判断依頼】

■ 状況
タスク「顧客対応フロー改善」で2つの方針が考えられます。

■ 選択肢
A案: 既存フローを段階的に修正（工数: 小、リスク: 低、効果: 中）
B案: フローを全面刷新（工数: 大、リスク: 中、効果: 高）

■ 私の見解
A案を推奨します。理由: 現行フローの問題点は限定的であり、段階的修正で十分対応可能なため。

■ 依頼
方針の決定をお願いします。""",
    intent="question"
)
```

### 템플릿 3: 동료에게 기술 상담

```
send_message(
    to="同僚の名前",
    content="""【技術相談】

Slack APIの rate limit に引っかかっています。

■ 状況
- 100件以上のメッセージを一括送信しようとしている
- 50件目あたりで 429 Too Many Requests が返される

■ 質問
Slack API の rate limit 回避策について知見はありますか？
バッチ処理の間隔を空ける方法を検討していますが、適切な間隔がわかりません。""",
    intent="question"
)
```

### 템플릿 4: 긴급 보고

긴급도가 "높음"이고 인간의 즉시 대응이 필요한 경우 `call_human`도 병용한다 (**톱레벨 Anima**이고 `human_notification`이 유효할 때만 도구를 이용 가능. 부하 Anima는 상급자에게 `send_message`로 한정).

```
send_message(
    to="上司の名前",
    content="""【緊急報告】

■ 状況
外部API（XXXサービス）から認証エラーが継続的に発生しています。

■ 影響
- YYYタスクが完全に停止
- ZZZタスクも同じAPIを使用しており影響の可能性あり

■ 試行済み
- リトライ3回実施 → すべて失敗
- APIキーの有効性は自分では確認できない

■ 依頼
APIキーの確認と、影響範囲の調査をお願いします。""",
    intent="report"
)
```

인간에게 즉시 알림이 필요한 경우:
```
call_human(
    subject="【緊急】外部API認証エラー継続発生",
    body="XXXサービスから認証エラーが継続しています。YYYタスク停止中。APIキー確認をお願いします。",
    priority="urgent"
)
```

---

## 자주 있는 에스컬레이션 시나리오

### 시나리오 1: 지침 내용이 불명확

**상황**: 상급자로부터 "보고서를 작성해"라는 지침을 받았지만, 대상 기간·형식·제출처가 불명.

**올바른 대응**:
1. 스스로 추정할 수 있는 범위를 정리한다
2. 불명확한 점을 구체적으로 질문한다

```
send_message(
    to="上司の名前",
    content="""レポート作成の件、以下を確認させてください。

1. 対象期間: 今月分でよろしいでしょうか？
2. フォーマット: 前回と同じMarkdown形式でよろしいでしょうか？
3. 提出先: knowledge/ に保存でよろしいでしょうか？

上記で問題なければ着手します。""",
    intent="question"
)
```

**해서는 안 되는 대응**:
- 확인 없이 독자 해석으로 작업을 진행
- "지침이 불명확합니다"라고만 답한다 (구체적인 질문이 없음)
- `send_message`에서 `intent`를 생략한다 (`report` / `question` 중 하나가 필수. 생략하면 오류가 된다)

### 시나리오 2: 여러 상급자로부터 상충되는 지침

**상황**: 직접 상급자가 "A를 우선해"라고 했지만, 다른 Anima가 "B를 먼저 해줘"라고 요청했다.

**올바른 대응**:
1. 직접 상급자의 지침을 우선한다 (MUST)
2. 상황을 직접 상급자에게 보고한다

```
send_message(
    to="直属の上司の名前",
    content="""【優先順位の確認】

現在タスクAに着手中ですが、XXXさんからタスクBの優先依頼がありました。
指示通りタスクAを優先して進めますが、問題ないでしょうか？

タスクBの依頼内容: YYYの対応（XXXさんからの依頼）""",
    intent="question"
)
```

### 시나리오 3: 작업 중 오류가 연속 발생

**상황**: Chatwork API로의 메시지 전송이 3회 연속으로 실패했다.

**올바른 대응**:
1. 오류 내용을 기록한다
2. 3회 재시도해도 해결되지 않으면 에스컬레이션한다
3. 차단되지 않은 다른 작업에 착수한다

```
# エラーを記録
write_memory_file(
    path="state/current_state.md",
    content="## ブロック中\n\nChatwork API連続エラー\n- 1回目: 10:00 - 500 Internal Server Error\n- 2回目: 10:05 - 500 Internal Server Error\n- 3回目: 10:10 - 500 Internal Server Error\n\n上司に報告済み。他タスクに着手中。",
    mode="overwrite"
)

# 上司に報告
send_message(
    to="上司の名前",
    content="【ブロック報告】Chatwork APIが3回連続で500エラーを返しています。外部障害の可能性があります。復旧を待ちつつ、他のタスクに着手します。",
    intent="report"
)
```

### 시나리오 4: 자신의 책임 범위 밖의 문제를 발견

**상황**: 자신의 작업 중에 다른 Anima가 관리하는 데이터의 불일치를 발견했다.

**올바른 대응**:
1. 발견 사실을 기록한다
2. 직접 상급자에게 보고한다 (다른 부서의 Anima에게는 직접 연락하지 않는다)

```
send_message(
    to="上司の名前",
    content="""【情報共有】

作業中に以下の不整合を発見しました。私の担当外ですが共有します。

■ 発見内容
/data/reports/monthly.md の売上合計と /data/sales/summary.md の値が一致しません。
- monthly.md: 1,234,567円
- summary.md: 1,234,000円

■ 発見経緯
月次レポート作成中にデータ参照した際に気づきました。

対応の要否はお任せします。""",
    intent="report"
)
```

---

## 판단이 어려울 때의 체크리스트

다음 중 하나에 해당하는 경우, MUST로 에스컬레이션할 것:

- [ ] 이 판단을 잘못했을 경우, 되돌릴 수 없는 영향이 있다
- [ ] 자신의 권한 범위를 초과하는 조작이 필요하다
- [ ] 다른 부서의 Anima에 영향을 준다
- [ ] 15분 이상 해결책을 찾지 못하고 있다
- [ ] 같은 문제가 2회 이상 발생하고 있다
- [ ] 보안이나 데이터의 안전성과 관련된다

다음에 해당하는 경우, 자력 해결을 MAY로 시도해도 좋다:

- [ ] 과거에 유사한 문제를 해결한 경험이 있다
- [ ] 절차서(procedures/）에 대처 방법이 기재되어 있다
- [ ] 공유 지식(common_knowledge/）에 해결 방법이 있다
- [ ] 자신의 권한 범위 내에서 완결된다
- [ ] 실패해도 영향이 제한적이다
