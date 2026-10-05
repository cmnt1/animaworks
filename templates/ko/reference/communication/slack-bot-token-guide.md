# Slack 봇 토큰 설정 가이드

Slack 연동에서 사용하는 봇 토큰의 구조와 Per-Anima(개별) 토큰의 설정 규칙.

## 두 종류의 봇 토큰

AnimaWorks의 Slack 연동에는 **공유 봇**과 **Per-Anima 봇** 두 종류가 있다.

| 종류 | 키 이름 | 용도 |
|------|--------|------|
| 공유 봇 | `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` | 전체 폴백용. Per-Anima 토큰이 설정되지 않은 Anima가 사용 |
| Per-Anima 봇 | `SLACK_BOT_TOKEN__<name>` / `SLACK_APP_TOKEN__<name>` | 특정 Anima 전용 Slack App. 해당 Anima만 사용 |

**Per-Anima 봇이 설정된 경우, 그것이 우선된다.** 공유 봇은 어디까지나 폴백이다.

## Per-Anima 토큰의 명명 규칙

`__`(밑줄 2개) + Anima 이름(소문자)을 접미사로 추가한다.

```
SLACK_BOT_TOKEN__sumire    ← sumire 専用の Bot User OAuth Token
SLACK_APP_TOKEN__sumire    ← sumire 専用の App-Level Token
```

## 저장 위치

`shared/credentials.json`에 저장한다.

```json
{
  "SLACK_BOT_TOKEN": "xoxb-...(共有ボット)",
  "SLACK_APP_TOKEN": "xapp-...(共有App)",
  "SLACK_BOT_TOKEN__sumire": "xoxb-...(sumire専用ボット)",
  "SLACK_APP_TOKEN__sumire": "xapp-...(sumire専用App)"
}
```

## 반드시 지켜야 할 규칙

### 공유 토큰을 덮어쓰면 안 된다

**MUST**: Per-Anima 토큰을 설정할 때는 **새 키를 추가**한다. 기존의 `SLACK_BOT_TOKEN`이나 `SLACK_APP_TOKEN`을 자신의 토큰으로 바꿔서는 안 된다.

공유 토큰은 다른 Anima나 시스템 전체가 사용하고 있다. 덮어쓰면:

- 다른 Anima의 Slack 통신이 깨진다
- Socket Mode 연결과 Bot Token의 App이 불일치하게 된다
- `not_in_channel` 등의 예기치 않은 오류가 발생한다

### 파일 편집으로 토큰을 추가하는 방법

```bash
# credentials.json を読み取り、新しいキーを追加して書き戻す
python3 -c "
import json
from pathlib import Path
p = Path.home() / '.animaworks/shared/credentials.json'
d = json.loads(p.read_text())
d['SLACK_BOT_TOKEN__<自分の名前>'] = 'xoxb-...'
d['SLACK_APP_TOKEN__<自分の名前>'] = 'xapp-...'
p.write_text(json.dumps(d, indent=2))
"
```

**주의**: `str_replace` 등으로 기존 행을 치환하는 것이 아니라, JSON에 키를 추가하는 방법을 사용할 것.

## 서버의 감지와 재시작

Per-Anima 토큰은 **서버 시작 시**에 감지된다. `shared/credentials.json`에 토큰을 추가한 후, **서버의 재시작이 필요**하다.

서버는 시작 시 다음을 수행한다:

1. `SLACK_BOT_TOKEN__*`와 `SLACK_APP_TOKEN__*`의 쌍을 감지
2. 각 쌍에 대해 Per-Anima Socket Mode 핸들러를 등록
3. `auth.test`로 Bot User ID를 가져와 채널 라우팅에 사용

재시작 후, 서버 로그에 다음과 같이 표시되면 성공:

```
Per-anima Slack bot registered: <name> (bot_uid=U...)
```

## 트러블슈팅

### not_in_channel 오류

**증상**: Slack 채널에 답장하려고 하면 `not_in_channel` 오류가 발생한다

**원인**: Per-Anima 토큰이 설정되지 않아 공유 봇이 사용되고 있다. 공유 봇은 해당 채널의 멤버가 아니다.

**조치**:
1. `shared/credentials.json`에 `SLACK_BOT_TOKEN__<name>`와 `SLACK_APP_TOKEN__<name>`을 추가
2. 서버를 재시작
3. 대상 채널에 Per-Anima 봇이 초대되었는지 확인

### 공유 봇으로 폴백되고 있다

**증상**: 자신 전용 봇이 있어야 하는데, 공유 봇 이름으로 게시된다

**원인**: `credentials.json`에 `SLACK_BOT_TOKEN__<name>` / `SLACK_APP_TOKEN__<name>`이 존재하지 않는다

**확인 방법**:
```bash
cat ~/.animaworks/shared/credentials.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
for k in sorted(d):
    if 'SLACK' in k:
        print(f'{k}: {d[k][:20]}...')
"
```

### 토큰의 획득 방법

관리자(사람)에게 Slack App의 Bot User OAuth Token(`xoxb-`)과 App-Level Token(`xapp-`)을 제공받는다.

- Bot Token: Slack App 관리 화면 → OAuth & Permissions → Bot User OAuth Token
- App-Level Token: Slack App 관리 화면 → Basic Information → App-Level Tokens(scope: `connections:write`)
