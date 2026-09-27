# Gmail 도구 인증 설정 가이드

## 개요

Gmail 도구를 사용하려면 `permissions.json`에서의 허가에 더해, 런타임에 OAuth 토큰 파일(`token.json`)을 배치해야 한다.

## 전제 조건

1. `permissions.json`에 `gmail`이 허가되어 있을 것 (external_tools.allow_all 또는 allow에 포함)
2. `~/.animaworks/credentials/gmail/token.json`이 존재할 것

**중요**: permissions.json에서 허가된 것만으로는 동작하지 않는다. token.json이 필요하다.

## 인증 흐름 (GmailClient._get_credentials)

GmailClient는 다음 순서로 인증 정보를 탐색한다:

1. **MCP 토큰** — `~/.mcp-cache/workspace-mcp/token.json` (MCP-GSuite 연동용)
2. **저장된 토큰** — `~/.animaworks/credentials/gmail/token.json`
3. **새 OAuth 흐름** — credentials.json 또는 환경 변수 `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` 사용 (브라우저 인증 필요)

일반적으로는 절차 2의 `token.json`로 운영한다.

## token.json의 형식

`google.oauth2.credentials.Credentials.to_json()`이 출력하는 JSON 형식:

```json
{
  "token": "ya29.xxx...",
  "refresh_token": "1//xxx...",
  "token_uri": "https://oauth2.googleapis.com/token",
  "client_id": "xxxxx.apps.googleusercontent.com",
  "client_secret": "GOCSPX-xxx...",
  "scopes": [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.modify"
  ]
}
```

**주의**: `client_id`와 `client_secret`이 JSON 내에 포함된다. 토큰 업데이트 시 이 값이 사용되므로, `credentials.json`나 환경 변수의 값과 일치할 필요는 없다 (JSON 내의 값이 우선된다).

## 자주 발생하는 문제

### 증상: Gmail 도구가 오류가 됨

```
ValueError: No OAuth credentials found. Place credentials.json or set GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET.
```

### 원인

`~/.animaworks/credentials/gmail/token.json`이 존재하지 않는다.

### 조치 절차

1. 관리자에게 token.json의 생성을 요청한다
2. token.json의 생성에는 기존 OAuth 토큰(pickle 형식 등)에서의 변환, 또는 브라우저 인증이 필요하다
3. 스스로 OAuth 흐름을 실행할 수는 없다 (브라우저 조작이 필요하기 때문)

### token.pickle에서의 변환 절차 (관리자용)

기존 pickle 형식 토큰이 있는 경우:

```python
import pickle
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request

# 1. pickle読み込み
with open("path/to/token.pickle", "rb") as f:
    creds = pickle.load(f)

# 2. client_secretが含まれていない場合は設定
if not creds.client_secret:
    creds._client_secret = "対応するclient_secret"

# 3. リフレッシュ
creds.refresh(Request())

# 4. JSON形式で保存
import os
target = os.path.expanduser("~/.animaworks/credentials/gmail/token.json")
os.makedirs(os.path.dirname(target), exist_ok=True)
with open(target, "w") as f:
    f.write(creds.to_json())
```

### client_id 불일치 문제

token.json에 포함된 `client_id`은 그 토큰을 처음 생성한 OAuth 클라이언트의 ID와 일치해야 한다. 다른 클라이언트 ID로 생성된 토큰을 사용하면, 리프레시 시 인증 오류가 발생한다.

## 관련 파일

| 경로 | 내용 |
|------|------|
| `~/.animaworks/credentials/gmail/token.json` | OAuth 인증 토큰 (필수) |
| `~/.animaworks/credentials/gmail/credentials.json` | OAuth 클라이언트 정보 (새 흐름 시에만) |
| `~/.animaworks/shared/credentials.json` | 환경 변수 설정 (`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`) |
| `core/integrations/gmail.py` | Gmail 도구의 구현 |