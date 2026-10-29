# Slack Bot Token Configuration Guide

This guide explains the mechanism of bot tokens used in Slack integration and the configuration rules for Per-Anima (individual) tokens.

## Two Types of Bot Tokens

AnimaWorks Slack integration supports two types: **Shared Bot** and **Per-Anima Bot**.

| Type | Key Name | Use |
|------|--------|------|
| Shared Bot | `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` | Fallback for the entire system. Used by Anima instances without a Per-Anima token configured |
| Per-Anima Bot | `SLACK_BOT_TOKEN__<name>` / `SLACK_APP_TOKEN__<name>` | Slack App dedicated to a specific Anima. Used only by that Anima |

**If a Per-Anima Bot is configured, it takes priority.** The shared bot is only a fallback.

## Per-Anima Token Naming Convention

Add `__` (double underscore) + Anima name (lowercase) as a suffix.

```
SLACK_BOT_TOKEN__sumire    ← sumire 専用の Bot User OAuth Token
SLACK_APP_TOKEN__sumire    ← sumire 専用の App-Level Token
```

## Storage Location

Store in `shared/credentials.json`.

```json
{
  "SLACK_BOT_TOKEN": "xoxb-...(共有ボット)",
  "SLACK_APP_TOKEN": "xapp-...(共有App)",
  "SLACK_BOT_TOKEN__sumire": "xoxb-...(sumire専用ボット)",
  "SLACK_APP_TOKEN__sumire": "xapp-...(sumire専用App)"
}
```

## Rules That Must Always Be Followed

### Do Not Overwrite the Shared Token

**MUST**: When configuring a Per-Anima token, **add a new key**. Do not replace the existing `SLACK_BOT_TOKEN` or `SLACK_APP_TOKEN` with your own token.

The shared token is used by other Anima instances and the entire system. Overwriting it will:

- Break Slack communication for other Anima instances
- Cause a mismatch between the Socket Mode connection and the Bot Token App
- Trigger unexpected errors such as `not_in_channel`

### How to Add a Token by Editing Files

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

**Note**: Use the method of adding a key to the JSON rather than replacing existing lines with `str_replace` or similar.

## Server Detection and Restart

Per-Anima tokens are detected at **server startup**. After adding a token to `shared/credentials.json`, **a server restart is required**.

At startup, the server performs the following:

1. Detects pairs of `SLACK_BOT_TOKEN__*` and `SLACK_APP_TOKEN__*`
2. Registers a Per-Anima Socket Mode handler for each pair
3. Retrieves the Bot User ID via `auth.test` and uses it for channel routing

After restart, the server log should show the following to confirm success:

```
Per-anima Slack bot registered: <name> (bot_uid=U...)
```

## Troubleshooting

### not_in_channel Error

**Symptom**: The `not_in_channel` error appears when trying to reply to a Slack channel

**Cause**: No Per-Anima token is configured, so the shared bot is being used. The shared bot is not a member of that channel.

**Resolution**:
1. Add `SLACK_BOT_TOKEN__<name>` and `SLACK_APP_TOKEN__<name>` to `shared/credentials.json`
2. Restart the server
3. Confirm that the Per-Anima bot has been invited to the target channel

### Falling Back to the Shared Bot

**Symptom**: Even though you should have your own dedicated bot, posts are being made under the shared bot name

**Cause**: `SLACK_BOT_TOKEN__<name>` / `SLACK_APP_TOKEN__<name>` do not exist in `credentials.json`

**How to verify**:
```bash
cat ~/.animaworks/shared/credentials.json | python3 -c "
import sys, json
d = json.load(sys.stdin)
for k in sorted(d):
    if 'SLACK' in k:
        print(f'{k}: {d[k][:20]}...')
"
```

### How to Obtain Tokens

Ask an administrator (human) to provide the Slack App's Bot User OAuth Token (`xoxb-`) and App-Level Token (`xapp-`).

- Bot Token: Slack App management screen → OAuth & Permissions → Bot User OAuth Token
- App-Level Token: Slack App management screen → Basic Information → App-Level Tokens (scope: `connections:write`)
