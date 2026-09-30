<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: docs/ja/architecture/messaging.md -->
<!-- i18n: source-sha256=0975054575d95fdef233b9b53480548abb790dd9b8d8f084e1d3a0a4a55e18d4 generated=2026-09-30 engine=local model=deepseek-v4-flash translator=2 -->

> 확인된 커밋: b304b7dc

# 메시징

Anima 간의 메시지는 `send_message`로 수신처에 전달한다. `intent`는 메시지 목적을 나타내는 메타데이터이며 Inbox 시작을 필터링하는 데 사용하지 않는다. 대화 기록은 활동 로그를 중심으로 읽고 공유 설정에 따라 DM 기록을 보완한다.

## 공유 채널과 회사 경계

`post_channel`은 shared channel에 게시하고, `read_channel`은 접근 가능한 최근 게시물을 읽는다. channel의 metadata에서 member, closed 상태, company scope를 관리한다. company가 지정된 open channel은 해당 회사 내의 Anima에서 보이는 범위로 제한된다. DM과 channel의 전송 경로, 외부 대상의 alias 해결은 `core/messaging/`가 담당한다.

## 발신 규칙과 수신 dispatch

`send_message`는 `report` / `question` intent를 사용하며, 한 run에서 같은 수신처로 두 번째 DM을 보내면 거부된다. 수신처 수 상한은 없다. `post_channel`은 한 run에서 같은 채널에 한 번 게시할 수 있지만 run 간 쿨다운은 없다. 시간·일 단위 발신 예산이나 대화 깊이에 따른 발신 차단도 없다. `Messenger.send`는 activity log에 메시지를 기록하고, 깊이를 진단용으로 로그에 남겨도 전달을 거부하지 않는다.

수신 측에서는 `core/supervisor/inbox_rate_limiter.py`가 Inbox JSON 파일 변경을 감시하고 읽지 않은 메시지가 있으면 Inbox lane을 시작한다. 동시에 하나의 작업만 실행하며, 실행 중 도착한 메시지는 다음 한 번의 처리로 모은다. 알림 누락을 대비해 45초마다 재확인하고, Provider 오류 시 `rate_guard` 복구 시간을 기다리며 읽지 않은 메시지를 보존한다. `overflow_inbox`는 용량 보호로 유지된다.

## 인간에 대한 알림과 외부 연동

`call_human`은 인간에게 알림·확인 요청을 보내는 경로이다. 세션별 확인 키를 요구하는 모드가 있으며, 런타임에 발급된 키를 사용하여 확인한다. CLI / tool의 사용 방법은 [CLI 참조](../reference/tool-cli.md)를 참조한다.

외부로의 메시지 전송은 설정된 Slack, Chatwork, Discord의 대상에 대응하며, Zoom은 회의의 음성 연동에 사용한다. channel의 설정과 개별 연동 절차는 [연동 가이드](../integrations/index.md)를 참조한다.
