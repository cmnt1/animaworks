# Mode S (Agent SDK) Authentication Mode Configuration Guide

How to switch the authentication method used in Mode S (Claude Agent SDK) for each Anima.
The authentication mode is specified through an explicit configuration called **`mode_s_auth`** (not automatic credential detection).

Implementation: `_build_env()` in `core/execution/engines/claude/executor.py` builds the environment variables for the Claude Code child process.

## Authentication Mode List

| Mode | mode_s_auth Value | Connection Target | Use Case |
|--------|----------------|--------|------|
| **Direct API** | `"api"` | Anthropic API | Fastest streaming. Consumes API credits |
| **Bedrock** | `"bedrock"` | AWS Bedrock | AWS integration, use within VPC |
| **Vertex AI** | `"vertex"` | Google Vertex AI | GCP integration |
| **Max plan** | `"max"` or unset | Anthropic Max plan | Subscription authentication. No API credits needed |

If `mode_s_auth` is unset (`null` or omitted), Max plan is used.

## Configuration Priority

`mode_s_auth` is resolved in the following order:

1. **status.json** (per-Anima) — highest priority
2. **config.json anima_defaults** — global default

It is not auto-detected from credential contents. Explicitly specify `mode_s_auth`.

## Configuration Methods

### 1. Direct API Mode

Connects directly to the Anthropic API. Streaming is the smoothest.

**config.json credential configuration:**

```json
{
  "credentials": {
    "anthropic": {
      "api_key": "sk-ant-api03-xxxxx"
    }
  }
}
```

- `api_key`: Anthropic API key. Falls back to environment variable `ANTHROPIC_API_KEY` if empty
- `base_url`: Custom endpoint (optional). When specified, it is passed to the child process as `ANTHROPIC_BASE_URL` (for proxy or on-premises use)

**status.json (per-Anima):**

```json
{
  "model": "claude-sonnet-4-6",
  "credential": "anthropic",
  "mode_s_auth": "api"
}
```

If `mode_s_auth` is `"api"` and the credential has no `api_key` and the environment variable is also absent, it falls back to Max plan.

### 2. Bedrock Mode

Connects via AWS Bedrock. The credential's `keys` is passed to ModelConfig as `extra_keys` and mapped to environment variables.

**config.json credential configuration:**

```json
{
  "credentials": {
    "bedrock": {
      "api_key": "",
      "keys": {
        "aws_access_key_id": "AKIA...",
        "aws_secret_access_key": "...",
        "aws_region_name": "us-east-1",
        "aws_session_token": "",
        "aws_profile": ""
      }
    }
  }
}
```

| keys Key | Environment Variable | Description |
|-----------|----------|------|
| aws_access_key_id | AWS_ACCESS_KEY_ID | Required |
| aws_secret_access_key | AWS_SECRET_ACCESS_KEY | Required |
| aws_region_name | AWS_REGION | Region |
| aws_session_token | AWS_SESSION_TOKEN | Temporary authentication (optional) |
| aws_profile | AWS_PROFILE | Profile name (optional) |

Items without values in `keys` fall back to the corresponding environment variables above. In production, it is possible to set only `AWS_PROFILE` and not write keys in the config.

**status.json (per-Anima):**

```json
{
  "model": "claude-sonnet-4-6",
  "credential": "bedrock",
  "execution_mode": "S",
  "mode_s_auth": "bedrock"
}
```

When using Bedrock with Mode S, specify both `execution_mode: "S"` and `mode_s_auth: "bedrock"`.

### 3. Vertex AI Mode

Connects via Google Vertex AI. The credential's `keys` is passed to ModelConfig as `extra_keys` and mapped to environment variables.

**config.json credential configuration:**

```json
{
  "credentials": {
    "vertex": {
      "api_key": "",
      "keys": {
        "vertex_project": "my-gcp-project",
        "vertex_location": "us-central1",
        "vertex_credentials": "/path/to/service-account.json"
      }
    }
  }
}
```

| keys Key | Environment Variable | Description |
|-----------|----------|------|
| vertex_project | CLOUD_ML_PROJECT_ID | GCP project ID |
| vertex_location | CLOUD_ML_REGION | Region (e.g., us-central1) |
| vertex_credentials | GOOGLE_APPLICATION_CREDENTIALS | Service account JSON path |

Items without values in `keys` fall back to the corresponding environment variables above. When using ADC (Application Default Credentials), `vertex_credentials` can be omitted.

**status.json (per-Anima):**

```json
{
  "model": "claude-sonnet-4-6",
  "credential": "vertex",
  "execution_mode": "S",
  "mode_s_auth": "vertex"
}
```

### 4. Max Plan Mode (Default)

Uses Claude Code's subscription authentication (Max plan, etc.).

**config.json credential configuration:**

```json
{
  "credentials": {
    "max": {
      "api_key": ""
    }
  }
}
```

**status.json (per-Anima):**

```json
{
  "model": "claude-sonnet-4-6",
  "credential": "max"
}
```

Omitting `mode_s_auth` or setting it to `"max"` results in Max plan.

## Example of Per-Anima Usage

When mixing authentication modes within the same organization, specify `mode_s_auth` and `credential` in each Anima's status.json:

```json
{
  "credentials": {
    "anthropic": { "api_key": "sk-ant-api03-xxxxx" },
    "max": { "api_key": "" },
    "bedrock": {
      "api_key": "",
      "keys": {
        "aws_access_key_id": "AKIA...",
        "aws_secret_access_key": "...",
        "aws_region_name": "us-east-1"
      }
    }
  }
}
```

| Example (Role) | credential | mode_s_auth | Authentication Mode | Reason |
|-----------|-----------|-------------|-----------|------|
| Anima using Max plan | `"max"` | Omitted | Max plan | No API cost |
| Anima using Direct API | `"anthropic"` | `"api"` | Direct API | Fast streaming needed |
| Anima using Bedrock | `"bedrock"` | `"bedrock"` | Bedrock | Access only from within AWS VPC |

**How to check the current configuration:** Check `credential` and `mode_s_auth` in each Anima's `status.json`:

```bash
# 特定 Anima の mode_s_auth 確認
cat ~/.animaworks/animas/{name}/status.json | python3 -c "import sys,json; d=json.load(sys.stdin); print(f'model={d.get(\"model\")}, credential={d.get(\"credential\")}, mode_s_auth={d.get(\"mode_s_auth\")}')"

# 全 Anima の一覧
for d in ~/.animaworks/animas/*/; do name=$(basename "$d"); python3 -c "import json; d=json.load(open('$d/status.json')); print(f'$name: credential={d.get(\"credential\")}, mode_s_auth={d.get(\"mode_s_auth\")}')" 2>/dev/null; done
```

## Global Default (anima_defaults)

To set Bedrock as the default for all Animas, configure it in `anima_defaults` of config.json:

```json
{
  "anima_defaults": {
    "mode_s_auth": "bedrock"
  },
  "credentials": {
    "bedrock": { "api_key": "", "keys": { "aws_access_key_id": "...", ... } }
  }
}
```

Individual Anima's status.json can override `mode_s_auth`.

## Notes

- The authentication mode is passed as an environment variable to the Claude Code child process via `_build_env()`
- `mode_s_auth` is not auto-detected from credential contents. Explicit specification is required
- If `mode_s_auth=api` has no `api_key` in the credential and the environment variable is also absent, it falls back to Max plan
- For Bedrock / Vertex, the credential's `keys` is passed as `extra_keys` and mapped to environment variables. Items without `keys` set fall back to environment variables with the same name
- When using a custom endpoint in API mode, specifying `base_url` in the credential passes it to the child process as `ANTHROPIC_BASE_URL`
- A server restart is required after configuration changes
- In Mode A/B, LiteLLM continues to use the credential as before (this setting is Mode S only)
