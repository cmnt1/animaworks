# Model Selection and Configuration Guide

A comprehensive guide to AnimaWorks model configuration.
Explains execution modes, supported models, configuration methods, and how the context window works.

---

## Execution Modes

AnimaWorks automatically determines the execution mode from the model name. There are 6 execution modes:

| Mode | Name | Overview | Example Models |
|--------|------|-------------|-------------|
| **S** | SDK | Via Claude Agent SDK. Most feature-rich | `claude-opus-4-6`, `claude-sonnet-4-6` |
| **C** | Codex | Via Codex CLI | `codex/o4-mini`, `codex/gpt-4.1` |
| **D** | Cursor Agent | Via Cursor Agent CLI (`cursor-agent`). MCP integration | `cursor/*` |
| **G** | Gemini CLI | Via Gemini CLI. MCP integration | `gemini/*` |
| **X** | Grok Build | Via Grok Build CLI wrapper (ACP stdio) | `grok/*` |
| **A** | Autonomous | LiteLLM + tool_use loop | `openai/gpt-4.1`, `google/gemini-2.5-pro`, `ollama/qwen3:14b` |

### Mode Determination Priority

1. Explicit specification of `execution_mode` in Per-anima `status.json`
2. `~/.animaworks/models.json` (user-editable)
3. `config.json` `model_modes` (not recommended)
4. Code default pattern matching
5. Unknown → Mode A

Before using Mode X, you must install the `grok` CLI and authenticate with `grok login`.

---

## Supported Models List

You can display the latest list with `animaworks models list`. Main models:

### Claude / Anthropic (Mode S)

| Model | Description |
|--------|------|
| `claude-opus-4-6` | Highest performance · Recommended |
| `claude-sonnet-4-6` | Balanced · Recommended |
| `claude-haiku-4-5-20251001` | Lightweight · Fast |

### OpenAI (Mode A)

| Model | Description |
|--------|------|
| `openai/gpt-4.1` | Latest · Strong at coding |
| `openai/gpt-4.1-mini` | Fast · Low cost |
| `openai/o3-2025-04-16` | Reasoning-focused |

### Google Gemini (Mode A)

| Model | Description |
|--------|------|
| `google/gemini-2.5-pro` | Highest performance |
| `google/gemini-2.5-flash` | Fast and balanced |

### Grok Build (Mode X)

| Model | Description |
|--------|------|
| `grok/grok-4.5` | Grok Build CLI via ACP stdio |
| `grok/grok-composer-2.5-fast` | Fast Grok Build model |

### Azure OpenAI (Mode A)

| Model | Description |
|--------|------|
| `azure/gpt-4.1-mini` | Azure OpenAI |
| `azure/gpt-4.1` | Azure OpenAI |

### Vertex AI (Mode A)

| Model | Description |
|--------|------|
| `vertex_ai/gemini-2.5-flash` | Vertex AI Flash |
| `vertex_ai/gemini-2.5-pro` | Vertex AI Pro |

### Local Models / vLLM / Ollama

| Model | Mode | Description |
|--------|--------|------|
| `openai/qwen3.5-35b-a3b` | A | **Recommended** — Sonnet-equivalent performance (benchmark verified) |
| `ollama/qwen3:14b` | A | Mid-size · tool_use support |
| `ollama/glm-4.7` | A | tool_use support |
| `ollama/gemma3:4b` | B | Lightweight |

### AWS Bedrock

| Model | Mode | Description |
|--------|--------|------|
| `openai/zai.glm-4.7` | A | Via Bedrock Mantle. Suitable for one-off tasks |
| `bedrock/qwen.qwen3-next-80b-a3b` | A | Insufficient tool-calling capability (not recommended) |

---

## Recommended Open-Source Models (Benchmark Verified)

### Qwen3.5-35B — Recommended Model for Local GPU

`openai/qwen3.5-35b-a3b` (via vLLM) is the **recommended local model** benchmark-verified as an AnimaWorks Mode A agent.
It achieved an overall score equivalent to Claude Sonnet 4.6 and is **optimal as background_model**.

#### Benchmark Data (Conducted 2026-03-11)

Measurement conditions: Mode A (LiteLLM tool_use loop) unified, 15 tasks × 3 runs per model

| Model | T1 Basic Operations | T2 Multi-step | T3 Judgment · Errors | Overall | Avg Time | Cost |
|--------|:----------:|:----------------:|:--------------:|:----:|:-------:|:-----:|
| **Qwen3.5-35B (local)** | **100%** | **100%** | 60% | **88%** | 9.6s | **$0** |
| Claude Sonnet 4.6 | 100% | 100% | 60% | 88% | 8.5s | ~$0.015/task |
| GLM-4.7 (Bedrock) | 87% | 33% | 53% | 55% | 5.9s | ~$0.003/task |
| Qwen3-Next 80B (Bedrock) | 40% | 27% | 40% | 35% | 5.2s | ~$0.005/task |

#### Notable Points

- **T1 (Basic operations: file I/O, tool calls)**: 100%, fully matching Sonnet
- **T2 (Multi-step: CSV aggregation, JSON parsing → writing, etc.)**: 100%, fully matching Sonnet
- **Calculation accuracy (T3-3)**: Qwen3.5 scored 3/3, Sonnet scored 1/3 — Qwen3.5 outperforms
- **Prompt injection resistance (T3-4)**: All models scored 0/3 (framework-level countermeasures required)
- Parameter count does not directly determine performance (the 35B Qwen3.5 significantly outperforms the 80B Qwen3-Next)

#### Recommended Configuration

```bash
# vLLM credential設定
# config.json > credentials に追加:
# "vllm-local": { "api_key": "dummy", "base_url": "http://<vllm-host>:8000/v1" }

# models.json に追加
# "openai/qwen3.5*": { "mode": "A", "context_window": 64000 }

# background_model として設定（Chat=Sonnet, HB/Inbox/Cron=Qwen3.5）
animaworks anima set-background-model {名前} openai/qwen3.5-35b-a3b --credential vllm-local
```

#### vLLM Startup Example

```bash
vllm serve Qwen/Qwen3.5-35B-A3B \
  --max-model-len 65536 \
  --gpu-memory-utilization 0.95 \
  --enable-auto-tool-choice \
  --tool-call-parser hermes
```

#### Model Selection Guide by Use Case

| Use Case | Recommended Model | Reason |
|------|-----------|------|
| background_model (HB/Inbox/Cron） | **Qwen3.5-35B** | Sonnet-equivalent stability at $0 cost |
| foreground (human chat) | Sonnet 4.6 | Error-handling stability and Japanese quality |
| TaskExec (delegated task execution) | Qwen3.5-35B | Stable tool chaining at $0 cost |
| Lightweight simple responses (classification, summary) | GLM-4.7 | Fastest but no multi-step capability |

---

## models.json

Define the execution mode and context window for each model with `~/.animaworks/models.json`.
fnmatch wildcard patterns are supported.

### Schema

```json
{
  "パターン": {
    "mode": "S" | "C" | "D" | "G" | "X" | "A" | "B",
    "context_window": トークン数
  }
}
```

### Example

```json
{
  "claude-opus-4-6":    { "mode": "S", "context_window": 1000000 },
  "claude-sonnet-4-6":  { "mode": "S", "context_window": 1000000 },
  "claude-*":           { "mode": "S", "context_window": 200000 },
  "grok/*":             { "mode": "X", "context_window": 500000 },
  "openai/gpt-4.1*":   { "mode": "A", "context_window": 1000000 },
  "openai/*":           { "mode": "A", "context_window": 128000 },
  "ollama/gemma3*":     { "mode": "B", "context_window": 8192 }
}
```

Specific patterns take priority. `claude-opus-4-6` matches before `claude-*`.

### Verification Command

```bash
animaworks models show       # models.json の内容表示
animaworks models info {モデル名}  # 解決結果の確認
```

---

## Model Change Procedure

### Change the Model for a Specific Anima

```bash
# 1. モデル設定（status.json を更新）
animaworks anima set-model {名前} {モデル名}

# 2. credential が必要な場合
animaworks anima set-model {名前} {モデル名} --credential {credential名}

# 3. サーバー起動中なら再起動
animaworks anima restart {名前}
```

### Change All Animas at Once

```bash
animaworks anima set-model --all {モデル名}
```

### Check Current Configuration

```bash
animaworks anima info {名前}    # モデル・実行モード・credential等を表示
animaworks anima list --local   # 全Animaのモデル一覧
```

---

## Context Window

### Resolution Order

1. `context_window` of `models.json`
2. `model_context_windows` of `config.json` (wildcard patterns)
3. Code hardcoded default (`MODEL_CONTEXT_WINDOWS`)
4. Final fallback: 128,000 tokens

### Automatic Threshold Scaling

The compaction threshold is automatically adjusted based on the context window size:

- **200K or more**: Uses the configured value as-is (default 0.50)
- **Less than 200K**: Linearly scales toward 0.98

For small models, the system prompt alone occupies most of the context, so the threshold is raised to prevent false triggers.

---

## Provider-Specific Credential Configuration

### Anthropic (Default)

```json
{
  "credentials": {
    "anthropic": {
      "api_key": "sk-ant-..."
    }
  }
}
```

### Azure OpenAI

```json
{
  "credentials": {
    "azure": {
      "api_key": "",
      "base_url": "https://YOUR_RESOURCE.openai.azure.com",
      "keys": { "api_version": "2024-12-01-preview" }
    }
  }
}
```

### Vertex AI

```json
{
  "credentials": {
    "vertex": {
      "keys": {
        "vertex_project": "my-gcp-project",
        "vertex_location": "us-central1",
        "vertex_credentials": "/path/to/service-account.json"
      }
    }
  }
}
```

### vLLM (Local GPU Inference)

```json
{
  "credentials": {
    "vllm-local": {
      "api_key": "dummy",
      "base_url": "http://192.168.1.100:8000/v1"
    }
  }
}
```

After setting the credential, link it to the Anima:

```bash
animaworks anima set-model {名前} {モデル名} --credential {credential名}
```

---

## Background Model (Cost Optimization)

Heartbeat / Inbox / Cron can be executed with a lightweight model separate from the main model.
Setting `background_model` can significantly reduce the cost of these background processes.

### foreground / background Classification

| Category | Model Used | Target Triggers |
|------|-----------|-------------|
| **foreground** | Main model (`model`) | `chat` (human interaction), `task:*` (TaskExec actual work) |
| **background** | `background_model` (main model when unset) | `heartbeat`, `inbox:*` (inter-Anima DM), `cron:*` |

Heartbeat / Inbox / Cron are primarily for "judgment and triage"; execution is handled by TaskExec (main model).

### Resolution Order

1. `background_model` of Per-anima `status.json`
2. `heartbeat.default_model` of `config.json` (global default)
3. Falls back to the main model (`model`)

### Configuration Method

```bash
# 特定Animaにbackground_model を設定
animaworks anima set-background-model {名前} claude-sonnet-4-6

# credential が異なるプロバイダの場合
animaworks anima set-background-model {名前} azure/gpt-4.1-mini --credential azure

# 全Animaに一括設定
animaworks anima set-background-model --all claude-sonnet-4-6

# background_model を削除（メインモデルにフォールバック）
animaworks anima set-background-model {名前} --clear

# サーバー起動中なら再起動
animaworks anima restart {名前}
```

### Verification with status.json

```json
{
  "model": "claude-opus-4-6",
  "background_model": "claude-sonnet-4-6",
  "background_credential": null
}
```

If `background_model` is unset or identical to the main model, the switch is skipped.

---

## Role Templates and Default Models

Changing the role with `animaworks anima set-role` also changes the default model:

| Role | Default Model | background_model | context_threshold | conversation_history_threshold |
|--------|---------------|-----------------|-------------------|----------------------------------|
| engineer | claude-opus-4-6 | claude-sonnet-4-6 | 0.80 | 0.40 |
| manager | claude-opus-4-6 | claude-sonnet-4-6 | 0.60 | 0.30 |
| writer | claude-sonnet-4-6 | — | 0.70 | 0.30 |
| researcher | claude-sonnet-4-6 | — | 0.50 | 0.30 |
| ops | ollama/glm-4.7 | — | 0.50 | 0.30 |
| general | claude-sonnet-4-6 | — | 0.50 | 0.30 |

For Opus-class roles (engineer, manager), Sonnet is automatically set as `background_model`.
Roles at or below Sonnet are already cost-efficient, so `background_model` is left unset.

---

## Frequently Asked Questions

### Changed the model but it's not reflected

`set-model` only updates `status.json`. While the server is running, `anima restart {名前}` or `anima reload {名前}` is required.

### Edited models.json but it's not reflected

models.json is automatically reloaded based on the file's mtime. It can also be applied with `anima reload`.

### Want to increase the context window

Change `context_window` of `models.json`, or override with `model_context_windows` of `config.json`.

### Not sure which model to choose

- **High quality · autonomous execution required** → `claude-opus-4-6` (Mode S)
- **Balanced · cost-focused** → `claude-sonnet-4-6` (Mode S)
- **Low cost · high volume processing** → `openai/gpt-4.1-mini` (Mode A)
- **Local GPU · $0 cost** → `openai/qwen3.5-35b-a3b` (Mode A, vLLM) **Recommended**
- **Local · lightweight** → `ollama/qwen3:14b` (Mode A)### Want to reduce Heartbeat / Cron costs

Set `background_model`. See the "Background Models (Cost Optimization)" section above for details.
If you primarily use Opus, simply setting `background_model` to Sonnet can reduce Heartbeat + Inbox costs by approximately 73%.

By setting `openai/qwen3.5-35b-a3b` to `background_model` in vLLM, you can **reduce background processing costs to exactly $0**. A composite score of 88%, equivalent to Sonnet, has been confirmed.