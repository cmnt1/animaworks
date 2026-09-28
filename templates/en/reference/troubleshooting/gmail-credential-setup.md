# Gmail Tool Authentication Configuration Guide

## Overview

To use the Gmail tool, in addition to the permission granted in `permissions.json`, you need to place an OAuth token file (`token.json`) in the runtime environment.

## Prerequisites

1. `gmail` must be permitted in `permissions.json` (included in external_tools.allow_all or allow)
2. `~/.animaworks/credentials/gmail/token.json` must exist

**Important**: Being permitted in permissions.json alone is not sufficient. token.json is required.

## Authentication Flow (GmailClient._get_credentials)

GmailClient searches for authentication credentials in the following order:

1. **MCP token** — `~/.mcp-cache/workspace-mcp/token.json` (for MCP-GSuite integration)
2. **Saved token** — `~/.animaworks/credentials/gmail/token.json`
3. **New OAuth flow** — Uses credentials.json or environment variables `GMAIL_CLIENT_ID` / `GMAIL_CLIENT_SECRET` (requires browser authentication)

Normally, step 2 with `token.json` is used for operation.

## Format of token.json

JSON format output by `google.oauth2.credentials.Credentials.to_json()`:

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

**Note**: `client_id` and `client_secret` are included in the JSON. These values are used during token refresh, so they do not need to match `credentials.json` or environment variable values (the values in the JSON take precedence).

## Common Issues

### Symptom: Gmail tool returns an error

```
ValueError: No OAuth credentials found. Place credentials.json or set GMAIL_CLIENT_ID / GMAIL_CLIENT_SECRET.
```

### Cause

`~/.animaworks/credentials/gmail/token.json` does not exist.

### Resolution Steps

1. Ask the administrator to generate token.json
2. Generating token.json requires conversion from an existing OAuth token (such as pickle format) or browser authentication
3. You cannot run the OAuth flow yourself (because browser interaction is required)

### Conversion Procedure from token.pickle (for Administrators)

If an existing pickle-format token is available:

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

### client_id Mismatch Issue

The `client_id` included in token.json must match the ID of the OAuth client that originally generated the token. Using a token generated with a different client ID will cause an authentication error during refresh.

## Related Files

| Path | Description |
|------|------|
| `~/.animaworks/credentials/gmail/token.json` | OAuth authentication token (required) |
| `~/.animaworks/credentials/gmail/credentials.json` | OAuth client information (only for new flow) |
| `~/.animaworks/shared/credentials.json` | Environment variable configuration (`GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`) |
| `core/integrations/gmail.py` | Gmail tool implementation |
