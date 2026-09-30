<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/architecture/messaging.md -->
<!-- i18n: source-sha256=0975054575d95fdef233b9b53480548abb790dd9b8d8f084e1d3a0a4a55e18d4 generated=2026-09-30 engine=local model=deepseek-v4-flash translator=2 -->

> 확인된 커밋: b304b7dc

# 메시징

Anima 간의 메시지는 `send_message`에서 대상으로 전달한다. 메시지에는 임의의 `intent`을 붙일 수 있으며, inbox dispatcher는 `delegation` 등의 intent와 발신자를 사용하여 즉시 처리 필요 여부를 판단한다. 대화 기록은 활동 로그를 중심으로 읽고, 공유 설정에 따라 DM 기록을 보완한다.

## 공유 채널과 회사 경계

`post_channel`은 shared channel에 게시하고, `read_channel`은 접근 가능한 최근 게시물을 읽는다. channel의 metadata에서 member, closed 상태, company scope를 관리한다. company가 지정된 open channel은 해당 회사 내의 Anima에서 보이는 범위로 제한된다. DM과 channel의 전송 경로, 외부 대상의 alias 해결은 `core/messaging/`가 담당한다.

## 전송 제한과 수신 dispatch

전송 시에는 다음 3가지 종류의 체크를 사용한다. `send_message`의 1회 실행당 recipient 수는 `max_recipients_per_run`로 제한된다. Anima 간의 전송 수는 `max_outbound_per_hour`와 일 단위 상한으로 제어된다. 또한, 같은 Anima 조합으로 단시간에 대화가 순환하지 않도록 depth limit을 확인한다. role별 기본값은 `core/config/schemas.py`, Anima 고유의 재정의는 `status.json`에 있다. 설정의 전체 항목은 [설정 참조](../reference/config.md)를 참조한다.

수신 측에서는 `core/supervisor/inbox_rate_limiter.py`가 cooldown, cascade 감지, 수신 intent를 확인하여 inbox lane의 시작을 조정한다. 따라서 전송 상한 판정과 수신 처리 시작의 억제는 별도의 책임으로 구현되어 있다.

| role | 1시간 | 24시간 | 1회 실행의 대상 수 |
|---|---:|---:|---:|
| manager | 60 | 300 | 10 |
| engineer | 40 | 200 | 5 |
| writer / researcher | 30 | 150 | 3 |
| ops | 20 | 80 | 2 |
| general | 15 | 50 | 2 |

## 인간에 대한 알림과 외부 연동

`call_human`은 인간에게 알림·확인 요청을 보내는 경로이다. 세션별 확인 키를 요구하는 모드가 있으며, 런타임에 발급된 키를 사용하여 확인한다. CLI / tool의 사용 방법은 [CLI 참조](../reference/tool-cli.md)를 참조한다.

외부로의 메시지 전송은 설정된 Slack, Chatwork, Discord의 대상에 대응하며, Zoom은 회의의 음성 연동에 사용한다. channel의 설정과 개별 연동 절차는 [연동 가이드](../integrations/index.md)를 참조한다.
