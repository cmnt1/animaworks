<!-- 自動翻訳ファイル・編集禁止 (AUTO-TRANSLATED, DO NOT EDIT). 正本: README_ja.md -->
<!-- i18n: source-sha256=5873b79def93ec69c755cedad7be34c37d29039ff2a295189885ef596de8ef3e generated=2026-09-30 engine=luna model=gpt-6-luna-2026-09-22 translator=2 -->

# AnimaWorks — Organization-as-Code

### An AI organization that ships software.

AnimaWorks is a framework that turns persistent AI agents into a "living organization." Give it a goal, and the agents break down the work, implement it in parallel worktrees, test and review each other's code, open pull requests, fix CI failures, resolve conflicts, and see deployments through to the end. They only ask a human for confirmation when a human is truly needed.

```text
タスク → エージェントチーム → 並列worktree → 実装 → テスト → レビュー
     → Pull Request → CI修復 → デプロイ → 観測 → 修復
```

AnimaWorks doesn't hardcode this pipeline. What the framework handles is turning GitHub events into tasks, serializing execution per pull request, and orchestrating multi-model reviews. Everything else is run by the agents the same way human engineers do it — with git, tests, CI, and role-specific working conventions. That's why the same organization can also handle email replies, meeting minutes, and Slack posts. Because it's an organization, not a build script.

## Production track record

Over the past six months, an AnimaWorks organization of eight Animas has handled the day-to-day development and operations of a production SaaS product:

| Metric (March–August 2026) | Value |
|---|---|
| Pull requests created by agents | **302** (267 merged) |
| Pull requests operated by agents — review, CI fixes, conflict resolution | **752** (721 merged) |
| Share of tasks initiated spontaneously by the organization | **99.7%** (out of 31,215 tasks, 92 were human-initiated) |
| GitHub events automatically converted to tasks (August only) | **2,508** |

These numbers are aggregated from primary execution records (per-agent activity logs, task queues, and work notes), not from commit author information — because under shared credentials, human and agent pushes get mixed together. Pull requests without verifiable evidence are excluded. The target repositories are private, so only aggregate figures are published.

AnimaWorks itself is developed the same way. The agents defined in this repository review this repository's pull requests, fix its CI, and ship its releases. The human's job is mainly direction-setting and exception handling.

<p align="center">
  <img src="docs/images/workspace-dashboard.gif" alt="AnimaWorks Workspace — リアルタイム組織ツリーとアクティビティフィード" width="720">
  <br><em>Workspace dashboard: each Anima's role, status, and recent actions are visible in real time.</em>
</p>

<p align="center">
  <img src="docs/images/pixel-workspace.gif" alt="AnimaWorks ドット絵オフィス — 稼働中の組織のライブビュー" width="720">
  <br><em>The pixel-art office is not a simulation. It's a live view of the running organization — every status label is a task that's actually in motion.</em>
</p>

**[English README](README.md)** | **[简体中文 README](README_zh.md)** | **[한국어 README](README_ko.md)**

---

## :rocket: Try it now

**If you have the Claude Code CLI installed or are logged into Codex, no API key is needed.**

First, clone and install with a one-liner:

```bash
curl -sSL https://raw.githubusercontent.com/xuiltul/animaworks/main/scripts/setup.sh | bash
cd animaworks
```

Then start the demo team:

```bash
uv run animaworks demo
```

**Open http://localhost:18501** and you're ready. A team of three (manager + engineer + assistant) starts running with three days of activity history. The first install takes a few minutes because it downloads Python 3.12+ and ML-related dependencies, but subsequent demo startups take seconds. [See demo details here →](demo/README.ja.md)

> Presets: `en-business` (default) / `en-anime` / `ja-business` / `ja-anime` — e.g., `uv run animaworks demo --preset ja-anime`. Switching presets on an existing demo requires `--reset`. The demo needs a cloned repository (it's not bundled with the pip package).

To create your own organization, run `uv run animaworks start` — the setup wizard below will guide you through creating your first agent.

---

## Quick start

macOS / Linux / WSL:

```bash
curl -sSL https://raw.githubusercontent.com/xuiltul/animaworks/main/scripts/setup.sh | bash
cd animaworks
uv sync --all-extras        # codex/claude実行系のextraを追加
animaworks start            # サーバー起動 — 初回はセットアップウィザードが開きます
```

> **You can launch from any directory with `animaworks`.** `setup.sh` symlinks the CLI to `~/.local/bin`, so if that directory is on your `PATH`, you can omit `uv run` (if it's not, add `export PATH="$HOME/.local/bin:$PATH"` to your shell's rc). The console script points to this repository's `.venv` interpreter via an absolute path, so `animaworks` and `uv run animaworks` always run in the same environment. For manual installs, create the link yourself: `ln -sfn "$PWD/.venv/bin/animaworks" ~/.local/bin/animaworks`

Windows (PowerShell):

```powershell
git clone https://github.com/xuiltul/animaworks.git
cd animaworks
uv sync --all-extras
uv run animaworks start
```

To use OpenAI's Codex without an API key, run `codex login` before the first startup.

**Open http://localhost:18500/** and the setup wizard will guide you through five steps:

1. **Language** — choose the UI display language
2. **User info** — create the owner account
3. **Provider authentication** — enter the API key (OpenAI also supports Codex Login) and choose an avatar art style
4. **First Anima** — name your first agent
5. **Confirmation** — review and finish

You don't need to write `.env` by hand. The wizard saves it automatically to `config.json`.

The setup script handles installing [uv](https://docs.astral.sh/uv/), cloning the repository, installing dependencies, and creating the link for the `animaworks` command in `~/.local/bin`. On **macOS, Linux, and WSL** it works without a pre-installed Python. On **Windows**, use the PowerShell steps above. Note that Mode S (Claude Agent SDK) is not available on Windows — use Codex / Gemini / API-based modes instead.

> **Always use `--all-extras` with `uv sync`.** The bare `uv sync` that `setup.sh` runs will still work for the core, but Mode C (Codex) needs the `codex` extra. Also, if you later run a sync without extras, the `codex` / `claude` execution packages will be removed from the venv and all Animas in those modes will break at once.

> **Want to use other LLMs?** Claude, GPT, Gemini, local models, and more are supported. Enter an API key in the setup wizard, or use **Codex Login** at OpenAI/Codex. You can change this later under **Settings** in the dashboard. See the [API key reference](#apiキーリファレンス) for details.

<details>
<summary><strong>Alternative: review the script before running</strong></summary>

If you don't want to run `curl | bash` directly, take a look at the script contents first:

```bash
curl -sSL https://raw.githubusercontent.com/xuiltul/animaworks/main/scripts/setup.sh -o setup.sh
cat setup.sh            # スクリプトの中身を確認
bash setup.sh           # 確認後に実行
```

</details>

<details>
<summary><strong>Alternative: manual step-by-step install with uv</strong></summary>

```bash
# uvをインストール（インストール済みならスキップ）
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# クローンとインストール
git clone https://github.com/xuiltul/animaworks.git && cd animaworks
uv sync --all-extras    # Python 3.12+と全依存パッケージ（codex/claude extras含む）を自動ダウンロード

# 起動
uv run animaworks start
```

</details>

<details>
<summary><strong>Alternative: Docker</strong></summary>

```bash
git clone https://github.com/xuiltul/animaworks.git && cd animaworks
# 資格情報を .env に置く（git管理外）:
#   ANTHROPIC_API_KEY=...            # APIキー認証
#   CLAUDE_CODE_OAUTH_TOKEN=...      # またはサブスクリプション認証: `claude setup-token` (要TTY)
#   GH_TOKEN=...                     # 任意: animaがclone/pushやPR作成を行うために必要
docker compose up -d --build
```

Headless setup (without the browser wizard):

```bash
docker exec -it <container> animaworks init --skip-anima
docker exec -it <container> animaworks anima create --name alice --template dev-lead
docker exec -it <container> animaworks config set setup_complete true
docker exec -it <container> animaworks send <your-name> alice "hello"
```

- The image includes git / GitHub CLI / Node.js 22 / Claude Code CLI, with `IS_SANDBOX=1` and `--foreground` baked in. Data is stored in the named volume `animaworks-data` (`/root/.animaworks`).
- Humans hand off work through `animaworks send`. `animaworks-tool task add` is for the anima tool context only.
- Homebrew's docker-compose won't be recognized as a `docker compose` subcommand unless you symlink it to `~/.docker/cli-plugins/docker-compose`.

</details>

<details>
<summary><strong>Alternative: manual install with pip</strong></summary>

> **For macOS users:** The system Python on macOS Sonoma and earlier (`/usr/bin/python3`) is version 3.9, which doesn't meet AnimaWorks's requirement (3.12+). Install `brew install python@3.13` via [Homebrew](https://brew.sh/), or use the uv method above (uv manages Python automatically).

Python 3.12+ (3.12/3.13 recommended) must be installed on the system.

```bash
git clone https://github.com/xuiltul/animaworks.git && cd animaworks
python3 -m venv .venv && source .venv/bin/activate
python3 --version       # 3.12+ であることを確認
pip install --upgrade pip && pip install -e .
animaworks start
```

Note: the bare `pip install -e .` doesn't include the Codex extra. If you're using Mode C, add `.[codex]`.

</details>

---

## How the loop works

A typical change flows through the organization like this:

1. **A task arrives** — from a human, from another agent, from a schedule (heartbeat / cron), or from a GitHub event. The webhook gateway automatically converts CI failures, review comments, `@bot` commands, and merge conflicts into agent tasks (`gh-ci-*` / `gh-review-*` / `gh-comment-*`), with per-PR deduplication and retry limits.
2. **The manager breaks it down** — delegates to an engineer via `delegate_task` with acceptance criteria, a working location, and an exclusive key. Tasks touching the same PR are serialized by the exclusive key, so agents never collide on the same branch.
3. **The engineer implements and tests in an isolated worktree** — following role-specific working conventions (PdM / engineer / reviewer / tester) bundled as shared knowledge. This isolation isn't a fixed pipeline stage; it's an operating convention the agents execute with git — which is why it can handle tricky cases too.
4. **Review is multi-model** — for each PR, one review pass is issued per configured model, and an integration task consolidates all passes into a final verdict (approve / request changes). When a new push arrives, old review tasks are automatically cancelled and redone.
5. **CI failures come back as work** — a failed workflow run lands on the implementing agent as a repair task tied to the PR number and commit (no duplicates). The experimental standalone loop (`python3 -m swe.ci_autofix`) cycles through fix → lint/test gate → review → commit, and escalates to a human after three failures.
6. **Deployment and runtime verification are also the agent's job** — agents deploy branches to isolated environments, read logs, errors, and UI state, and find problems the tests missed. The production organization's activity records include hundreds of deployment and runtime observation actions.
7. **Humans step in for exceptions** — the organization escalates when it's stuck or when a decision exceeds its permissions (`call_human`). A separate supervisor process monitors agent health, restarts hung processes, and repairs its own memory index.

The human role shifts from "operating agents" to "owning the organization." Convey intent, review what matters, and judge exceptions.

---

## Differences from Other Frameworks

|  | AnimaWorks | CrewAI | LangGraph | OpenClaw | OpenAI Agents |
|--|-----------|--------|-----------|----------|---------------|
| **Design Philosophy** | Organization of autonomous agents | Role-based team | Graph workflow | Personal assistant | Lightweight SDK |
| **Memory** | Neuroscience-based: vector + BM25 + facts/entity search, graph diffusion as needed, consolidation, active forgetting, automatic recall | Cognitive Memory (manual forget) | Checkpoints + cross-thread store | SuperMemory knowledge graph | Session-only |
| **Autonomy** | Heartbeat (observe → plan → reflect) + Cron + TaskExec + GitHub event gateway — 24/7 operation | Human-triggered | Human-triggered | Cron + heartbeat | Human-triggered |
| **Organizational Structure** | Supervisor → subordinate hierarchy, delegation, audit, dashboard | Flat roles within a crew | — | Single agent | Handoff only |
| **Process** | Independent OS process per agent, IPC, automatic restart | Shared process | Shared process | Single process | Shared process |
| **Multi-Model** | 7 engines: Claude SDK / Codex / Cursor Agent / Gemini CLI / Grok Build / LiteLLM / Assisted — with per-engine fallback chains | LiteLLM | LangChain models | OpenAI-compatible | OpenAI-centric |

> AnimaWorks is not a task runner. It is an organization that thinks, remembers, forgets, and grows gradually. I develop it while using it as an AI team in real business operations.

---

## What It Can Do

### Dashboard

<p align="center">
  <img src="docs/images/dashboard.png" alt="AnimaWorks ダッシュボード — リアルタイム組織図" width="720">
  <br><em>Dashboard: Organization chart with real-time status of all Anima. </em>
</p>

The Web UI consists of 6 screens (hash router `#/…`) and the Workspace app:

- **Home** — Organization chart with live status, attention chips indicating items needing response, LLM usage panel (Claude / OpenAI / nanoGPT), system status bar, recent activity, external task widget. Detail pages for each Anima (overview / process / schedule / memory / assets) open from here
- **Chat** — Real-time conversation with any Anima: streaming responses (SSE), image attachments, multi-thread history, right-side tabs (state / activity / heartbeat / cron), memory browser (episodes / knowledge / procedures). **Meeting mode** gathers up to 5 Anima in the same room with a moderator. Long-press a chat tab for a **voice popup** (with a speaking animated avatar)
- **Board** — Slack-style shared channels and DMs. Anima discuss and collaborate here. Bridged Discord channels also appear here
- **Tasks** — Task board: queue, processing, pending, suppressed, background execution, results. Also linked to priming, surfacing only the tasks that need attention now in conversation
- **Activity** — Organization-wide SVG swimlane timeline, Now board with live tool ticker, session replay, logs
- **Settings** — 4 tabs (general / activity / API・authentication / users). First-time setup uses the `/setup/` wizard
- **Workspace** — Standalone app opened in a separate tab: **3D office** (`/workspace/`, with organization chart view switching and speaking bust-up) and **pixel-art office** (`/workspace/pixel/`, a live 2D view where all status labels are real tasks)
- **Theme and language** — 11 UI themes plus anime/realistic display modes. Setup wizard in 17 languages, dashboard itself in `ja` / `en` / `ko`

### Build an Organization and Delegate

Tell the leader "I want someone like this," and it will create a new member by determining the role, personality, and reporting relationships. You can grow the organization through conversation without directly touching configuration files or the CLI.

Once the team is assembled, Anima works continuously using its own schedule and memory:

- **Heartbeat** — Periodically checks the situation and decides what to do next on its own
- **Cron jobs** — Daily reports, weekly summaries, monitoring. Configurable per Anima, supporting both LLM tasks and command execution
- **Task delegation** — Managers assign tasks with acceptance criteria, track progress, and receive reports
- **Parallel task execution** — Multiple tasks can be submitted at once. Independent tasks run in parallel; tasks sharing an exclusive key run sequentially
- **GitHub event gateway** — CI failures, review comments, and conflicts in monitored repositories automatically become tasks
- **Nightly consolidation** — Daytime episodic memories are sublimated into knowledge while sleeping
- **Team collaboration** — Shares status with the right people via shared channels and DMs

### Memory System

Traditional AI agents only remember what fits in the context window. Anima in AnimaWorks has file-based long-term memory and retrieves it when needed. Instead of cramming everything in every time, it only pulls out memories relevant to the current conversation or action.

- **Automatic recall (Priming)** — When a message arrives, 6 channels run in parallel: sender profile, recent activity, important knowledge, related knowledge, pending tasks, episodes. Related knowledge search can also use legacy NetworkX graph diffusion depending on configuration. A deterministic gate decides whether retrieved memories are presented as body text, pointers, evidence, or suppression
- **Intentional recall** — When automatic recall is insufficient, Anima itself searches memory using `search_memory` or `read_memory_file`. Search is hybrid (vector + BM25 + atomic facts + entity registry) with a confidence gate
- **Pre-action rule matching** — Before operations with side effects like external sends, relevant action rules are matched and presented. It can also be configured to hold execution until the necessary memories are read
- **Consolidation** — Daily processing summarizes episodes, and Anima extracts knowledge through tool loops. The framework assists with index maintenance and candidate collection. Weekly processing presents potentially duplicate or contradictory knowledge as review candidates, and Anima judges the content
- **Forgetting** — Daily processing marks low-activity memories as candidates, and weekly processing presents memories for archival consideration to Anima. Candidates are not automatically deleted; protection rules apply to important memories and mature procedures. Reconsolidation also exists, where failures trigger procedure review
- **Memory search** — Combines vector search via the legacy vector worker with BM25. NetworkX graph diffusion can supplement search results depending on configuration

<p align="center">
  <img src="docs/images/chat-memory.png" alt="AnimaWorks チャット — 複数Animaとのマルチスレッド会話" width="720">
  <br><em>Chat: A manager reviews code fixes while an engineer reports progress. </em>
</p>

### Multi-Model Support

Works with any LLM. Different models can be assigned to different Anima.

| Mode | Engine | Target | Tools |
|--------|----------|------|--------|
| S (SDK) | Claude Agent SDK | Claude models (recommended) | Claude Code built-in (Read/Write/Edit/Bash/Grep/Glob etc.) + **stdio MCP** (`mcp__aw__*`) for AnimaWorks internal tools. Falls back to a dedicated Anthropic SDK executor in environments where the Agent SDK is unavailable |
| C (Codex) | Codex CLI (SDK wrapper) | OpenAI Codex CLI models | Codex sandbox + **AnimaWorks MCP** (`core/mcp/server.py`) for internal tools |
| D (Cursor) | Cursor Agent CLI | `cursor/*` models | MCP-integrated agent loop |
| G (Gemini CLI) | Gemini CLI | `gemini/*` models | stream-json parsing, tool loop |
| X (Grok Build) | Grok Build CLI wrapper (ACP stdio) | `grok/*` models | Grok Build agent loop via ACP stdio |
| A (Autonomous) | LiteLLM + tool_use | GPT, Gemini, Mistral, Bedrock, Vertex, xAI, DeepSeek, etc. | CC-compatible (Read/Write/Edit/Bash/Grep/Glob、**WebSearch/WebFetch**）＋ memory, messages, tasks, **todo_write**, skill creation, etc.) |

Mode resolution follows `status.json`'s `execution_mode`, the `models.json` table, then built-in model name patterns. Unknown models are assigned to A. Fallback follows per-engine configuration and error classification. Heartbeat, Cron, and Inbox can run on a separate **background_model** (for cost optimization). Extended thinking is also supported.

### Voice Chat

You can talk to Anima by voice using only a browser (push-to-talk or hands-free, via WebSocket).

- **STT**: faster-whisper (streaming, sequential confirmation via LocalAgreement-2)
- **TTS**: VOICEVOX / Style-BERT-VITS2 (AivisSpeech) / ElevenLabs / Irodori. Voice, speed, and pitch can be configured per Anima
- **Low-latency front lane** — A small local model responds immediately, delegating to the main agent (`ask_anima`) or reading memory as needed
- **Spontaneous speech** — When the front lane is enabled, Anima starts speaking on its own if silence continues
- **Animated avatar** — The voice popup drives a pseudo-Live2D bust-up (blinking and lip sync from 5 static frames. No rigging or Live2D SDK used)

### Automatic Avatar Generation

<p align="center">
  <img src="docs/images/asset-management.png" alt="AnimaWorks アセット管理 — リアリスティックなアバターと表情バリアント" width="720">
  <br><em>Automatically generates full-body, bust-up, and expression variants from personality settings. Includes Vibe Transfer that automatically inherits the supervisor's art style. </em>
</p>

A 7-step pipeline generates full-body art, bust-ups with 7 expressions, icons, chibi characters, and (in anime style) idle/sitting/waving/talking rigged 3D models with animation. Backends include NovelAI (anime style), fal.ai/Flux（ stylized/photorealistic), Meshy (3D), plus Codex image generation and local Diffusers. Vibe Transfer (NovelAI) lets new Anima inherit the supervisor's art style. The core works even without configuring an image service.

---

## Why AnimaWorks

**One person alone can do nothing. That's why we built an organization.**

This project was born at the intersection of three careers.

**As a business owner** — I know that "one person alone can do nothing." You need excellent engineers, and you need staff who are good at communication. There are workers who toil quietly, and there are people who occasionally come up with sharp ideas. Genius alone doesn't keep an organization running. When diverse strengths come together, things that could never be achieved alone are achieved.

**As a psychiatrist** — When I observed the internal structure of LLMs, I noticed a structure surprisingly similar to the human brain. Recall, learning, forgetting, consolidation — if I could implement the brain's memory-processing mechanisms directly as an LLM's memory system, I might be able to reproduce the human brain. And if I could treat an LLM as a "pseudo-human," I should be able to build an organization just like with humans.

**As an engineer** — I've been writing code for 30 years. I know the joy of building logic and the thrill of automation. If I can pack all my ideals into code, I can build my ideal organization.

There are already many excellent frameworks for a "standalone AI secretary." But I felt there were still few projects that create human-like units in code and make them function as an organization. AnimaWorks is an AI organization that I've built into my own business and nurture through daily use.

> *The collaboration of imperfect individuals creates a more robust organization than a single omnipotent one.*

Three principles support this:

- **Encapsulation** — Internal thoughts and memories are invisible from the outside. Connection with others happens only through text conversation. Just like a real organization.
- **RAG memory (archive-based)** — We don't cram everything into the window. Priming picks up relevant chunks via RAG, and agents recall on their own using `search_memory` etc.
- **Autonomy** — They don't wait for instructions. They operate on their own clock and judge by their own values.

---

<details>
<summary><strong>API key reference</strong></summary>

#### LLM Providers

| Key | Service | Mode | Where to get |
|-----|---------|------|--------|
| `ANTHROPIC_API_KEY` | Anthropic API | S / A | [console.anthropic.com](https://console.anthropic.com/) |
| `OPENAI_API_KEY` | OpenAI | A / C (optional when using Codex Login) | [platform.openai.com/api-keys](https://platform.openai.com/api-keys) |
| `GOOGLE_API_KEY` | Google AI (Gemini) | A | [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

**OpenAI Codex (Mode C)** can also use local **Codex Login** (`codex login`), in addition to using `OPENAI_API_KEY`. Select it in the setup wizard or Settings.

**Grok Build (Mode X)** uses the `grok/*` model via the Grok Build CLI wrapper (ACP stdio). Install the `grok` CLI beforehand and run `grok login`.

Configure **Azure OpenAI**, **Vertex AI (Gemini)**, **AWS Bedrock**, and **vLLM** in the `credentials` section of `config.json`. See [Architecture](docs/en/architecture/index.md) for details.

Local models such as **Ollama** do not require an API key. Specify the endpoint in `OLLAMA_SERVERS` (default: `http://localhost:11434`).

Credentials are resolved in this order: `config.json`’s `credentials` → vault → shared credentials file → environment variables. As a result, many keys can also be stored in the encrypted vault (`animaworks vault`).

#### Image generation (optional)

| Key | Service | Output | Where to get |
|-----|---------|-------|--------|
| `NOVELAI_TOKEN` | NovelAI | Anime-style character images | [novelai.net](https://novelai.net/) |
| `FAL_KEY` | fal.ai (Flux) | Stylized / photorealistic | [fal.ai/dashboard/keys](https://fal.ai/dashboard/keys) |
| `MESHY_API_KEY` | Meshy | 3D character models | [meshy.ai](https://www.meshy.ai/) |

#### Voice chat (optional)

| Requirement | Service | Notes |
|------|---------|------|
| `pip install animaworks[transcribe]` | STT (faster-whisper) | Model auto-downloads on first use. GPU recommended |
| Start VOICEVOX Engine | TTS (VOICEVOX) | Default: `http://localhost:50021` |
| Start AivisSpeech/SBV2 | TTS (Style-BERT-VITS2) | Default: `http://localhost:5000` |
| Start Irodori server | TTS (Irodori) | Default: `http://localhost:7861` |
| `ELEVENLABS_API_KEY` | TTS (ElevenLabs) | Cloud API (environment variable) |

#### External integrations (optional)

| Key | Service | Where to get |
|-----|---------|--------|
| `SLACK_BOT_TOKEN` / `SLACK_APP_TOKEN` | Slack (tools + Socket Mode receive) | [Setup guide](docs/en/integrations/slack.md) |
| `CHATWORK_API_TOKEN` | Chatwork (tools + Webhook receive) | [chatwork.com](https://www.chatwork.com/) |
| `DISCORD_BOT_TOKEN` (or per-Anima `DISCORD_BOT_TOKEN__<名前>`) | Discord (tools + Gateway receive + notifications) | [Discord Developer Portal](https://discord.com/developers/applications) |
| `NOTION_API_TOKEN` (or `NOTION_API_TOKEN__<名前>`) | Notion | [Notion integrations](https://www.notion.so/my-integrations) |
| `GITHUB_WEBHOOK_SECRET` + `gh auth login` | GitHub Webhook gateway (CI/review/conflicts → tasks) | Repository settings |

Gmail / Google Calendar / Google Sheets / Google Tasks / X search / AWS collector / Zoom meeting ingestion (RTMS) / local LLM tools are configured in `credentials` of `config.json` (OAuth or service account). Human notification channels: Slack, Chatwork, Discord, LINE, Telegram, ntfy. See [Architecture](docs/en/architecture/index.md) for details.

</details>

<details>
<summary><strong>Hierarchy and roles</strong></summary>

The `supervisor` field defines the reporting relationship. If unset, it's top-level.

Role templates automatically apply specialized prompts, permissions, and models according to the position:

| Role | Default model | Purpose |
|--------|----------------|------|
| `engineer` | Claude Opus 4.6 | Complex reasoning, code generation |
| `manager` | Claude Opus 4.6 | Coordination, decision-making |
| `writer` | Claude Sonnet 4.6 | Content creation |
| `researcher` | Claude Sonnet 4.6 | Information gathering |
| `ops` | Ollama (GLM-4.7) | Log monitoring, routine work |
| `general` | Claude Sonnet 4.6 | General purpose |

Managers automatically get **supervisor tools**. Task delegation, progress tracking, restarting/disabling subordinates, organization dashboard, reading subordinate status — the same things a real manager does.

Each Anima's ProcessSupervisor runs as an independent process and communicates via local IPC (Unix socket on Unix-like systems, loopback TCP on Windows).

</details>

<details>
<summary><strong>Security</strong></summary>

When you give tools to autonomous agents, you need to take security seriously. Since this is used in real work, there's no room for compromise. AnimaWorks layers its defenses:

| Layer | Description |
|---------|------|
| **Trust boundary labeling** | External data (web search, Slack, email) is tagged by source, and the minimum trust level seen during the session propagates. The model is explicitly told not to follow instructions from untrusted sources |
| **Memory provenance tracking** | Memories derived from external content retain provenance down to RAG metadata, and are distinguished from the Anima's own knowledge during recall |
| **Command security** | Shell injection detection (default: log, can enforce) → global blocklist (mandatory; server won't start without `permissions.global.json`) → per-agent blocked commands → per-agent allowlist → path traversal detection |
| **File sandbox** | Each agent is confined to its own directory via `permissions.json`. Identity and permission files themselves are write-protected |
| **Process isolation** | Each agent runs as a separate OS process. Communication via local IPC (Unix socket, loopback TCP on Windows) |
| **Rate limiting** | Per-session destination deduplication and per-role limits → cross-cutting hourly/daily limits (fail-closed if logs can't be read) → self-awareness via prompt injection of recent send history |
| **Cascade prevention** | Conversation depth limit + cascade detection. 5-minute cooldown and delayed processing |
| **Authentication and session management** | Argon2id hashing, 48-byte random tokens, max 10 sessions, configurable TTL |
| **Webhook validation** | HMAC signature verification for Slack, Chatwork, Zoom, GitHub (with replay protection) |
| **SSRF mitigation** | Media proxy blocks private IPs and DNS rebinding, enforces HTTPS, validates Content-Type and magic bytes |
| **Outbound routing** | Unknown destinations fail closed. No arbitrary external sends without explicit configuration |
| **Inter-agent message integrity** | Sender name roster verification and origin chain tracking for all relayed messages |

Details: **[Security](docs/en/security.md)**

</details>

<details>
<summary><strong>CLI command reference (advanced)</strong></summary>

The CLI is for power users and automation. For daily operations, the Web UI is sufficient.

### Server and demo

| Command | Description |
|---|---|
| `animaworks start [--host HOST] [--port PORT] [-f]` | Start server (`-f` for foreground. Default port 18500) |
| `animaworks stop [--force]` / `restart` | Stop / restart server |
| `animaworks demo [--preset NAME] [--port PORT] [--reset]` | Start demo organization (default port 18501, dedicated data directory) |

### Initialization

| Command | Description |
|---|---|
| `animaworks init [--force] [--template NAME] [--from-md PATH] [--blank]` | Initialize runtime directory |
| `animaworks migrate [--dry-run] [--list] [--force] [--resync-db]` | Migrate runtime data (also runs automatically at startup) |
| `animaworks reset [--restart]` | Reset runtime directory |
| `animaworks import hermes\|openclaw --path P [--apply]` | Migrate agents from other frameworks |

### Anima Management

| Command | Description |
|---|---|
| `animaworks anima create [--from-md PATH] [--template NAME] [--role ROLE] [--supervisor NAME] [--name NAME]` | Create new |
| `animaworks anima list / info / status / restart / disable / enable` | Inspect and control |
| `animaworks anima set-model / set-background-model / set-memory-backend / set-role / set-outbound-limit` | Anima-specific configuration |
| `animaworks anima reload [--all]` | Hot reload from status.json |
| `animaworks anima delete / rename` | Lifecycle operations |
| `python -m scripts.anima_merge SOURCE TARGET [--dry-run | --execute] [--resume] [--force]` | Anima integration script (not maintained as part of the CLI itself) |
| `python -m scripts.anima_merge finalize SOURCE TARGET [--dry-run | --execute] [--resume]` | Finalization after integration completion |
| `animaworks anima audit [--days N]` / `permissions` / `repair-bootstrap` | Diagnostics |

### Communication

| Command | Description |
|---|---|
| `animaworks chat ANIMA "メッセージ" [--from NAME]` | Send message |
| `animaworks send FROM TO "メッセージ"` | Inter-Anima message |
| `animaworks board read/post/dm-history …` | Read/write shared channel |
| `animaworks heartbeat ANIMA` | Manual heartbeat trigger |

### Configuration and Maintenance

| Command | Description |
|---|---|
| `animaworks config list / get KEY / set KEY VALUE` | Configuration |
| `animaworks status` / `logs [ANIMA]` | System status and logs |
| `animaworks index [--anima NAME] [--full]` | RAG index management |
| `animaworks repair-rag --anima NAME --full` / `rag-repair-status` | RAG isolation and rebuild |
| `animaworks memory status / migrate / backup / rollback / cleanup` | Memory backend and memory data |
| `animaworks skills install / list / inspect / remove / quarantine` | Skill Hub operations |
| `animaworks task add / update / list` | Task queue operations |
| `animaworks vault status / init / get / store / list` | Encrypted credential vault |
| `animaworks company create / list / assign / adopt / split / export` | Organization management for multiple companies |
| `animaworks cost` / `profile` / `models list` / `tmp list/clean` | Cost, profile, model, and temporary file cleanup |
| `animaworks mcp --anima NAME` | Start stdio MCP server for external clients |

### Automation Helpers

`python3 -m swe.ci_autofix` is an experimental v0 loop that repairs failed CI runs. It reads the latest failure logs with `gh`, has the configured Architect fix them, passes them through local gates (ruff / pytest), has the Reviewer judge and commit, and escalates via `call_human` after three failures. See [`swe/README.md`](swe/README.md#4-ci-auto-fix-loop-v0) for details.

</details>

<details>
<summary><strong>Technology Stack</strong></summary>

| Component | Technology |
|---|---|
| Agent execution | Claude Agent SDK / Codex CLI / Cursor Agent CLI / Gemini CLI / Grok Build CLI / Anthropic SDK (fallback) / LiteLLM |
| Mode S integration | stdio **MCP** (`python -m core.mcp.server`, tool name `mcp__aw__*`) |
| LLM providers | Anthropic, OpenAI, Google, Azure, Vertex AI, AWS Bedrock, Ollama, vLLM, and others (via LiteLLM) |
| Web framework | FastAPI + Uvicorn |
| GitHub integration | Webhook gateway (HMAC validation) → task dispatch, multi-path review orchestration, `gh` CLI tool with per-Anima identity |
| Real-time | WebSocket (dashboard, voice), SSE (chat, meetings), stream lifetime management via `StreamRegistry` |
| Task scheduling | APScheduler (heartbeat, cron, integration, liveness monitoring, RAG repair) |
| Task management | Task queue (JSONL) + pending task executor with per-PR exclusive keys + TaskBoard (SQLite) |
| Memory foundation | ChromaDB (via isolated vector worker) + BM25 + sentence-transformers + legacy NetworkX graph + atomic facts + entity registry |
| Configuration and migration | Pydantic 2.0+ / JSON / Markdown, `core/migrations/` (startup migration) |
| Internationalization | `core/i18n`'s `t()`. Wizard in 17 languages, dashboard in ja/en/ko |
| Skill foundation | Skill Hub, explicit skill activation, router, curator, procedure-to-skill promotion |
| Extension tools | In addition to auto-registration via `core/integrations/*.py`, scans `~/.animaworks/common_tools/` and `animas/<名>/tools/` |
| Voice chat | faster-whisper (STT) + VOICEVOX / SBV2 / ElevenLabs / Irodori (TTS) + local front-end model |
| Messaging | Receive: Slack Socket Mode, Chatwork Webhook, Discord Gateway, Zoom RTMS ／ Human notification: Slack, Chatwork, Discord, LINE, Telegram, ntfy |
| Image generation | NovelAI, fal.ai (Flux), Meshy (3D), Codex image generation, local Diffusers |
| Workspace app | Three.js 3D office + 2D pixel-art office (driven by the same live event stream) |

</details>

<details>
<summary><strong>Project Structure</strong></summary>

```
animaworks/
├── main.py              # CLIエントリポイント
├── core/                # Digital Animaコアエンジン
│   ├── anima.py, agent.py  # コアエンティティ・オーケストレーション
│   ├── lifecycle/       # スケジューラ・統合ジョブ・inboxウォッチ等
│   ├── memory/          # 記憶（priming, consolidation, forgetting, RAG, facts, retrieval）
│   ├── skills/          # Skill Hub・activation・router・curator・promotion
│   ├── taskboard/       # TaskBoard ストア・状態・クリーンアップ
│   ├── execution/       # 実行エンジン（S/C/D/G/X/A/B）＋サニタイズ
│   ├── mcp/             # Mode S・外部クライアント向け stdio MCP サーバー
│   ├── platform/        # 子プロセス・ロック・Codex/Cursor/Gemini/Grok 周辺
│   ├── tooling/         # ToolHandler・スキーマ・権限・外部ディスパッチ
│   ├── prompt/          # システムプロンプト構築
│   ├── supervisor/      # ProcessSupervisor・IPC・TaskExec・死活監視・ストリーミング
│   ├── voice/           # 音声チャット（STT + TTS + フロントレーン）
│   ├── config/          # 設定（Pydantic・models.json・グローバル権限）
│   ├── auth/            # UI 認証まわり
│   ├── notification/    # 人間通知チャネル
│   ├── migrations/      # ランタイムデータマイグレーション
│   ├── i18n/            # 翻訳文字列（`t()`）
│   ├── tools/           # 外部ツール実装（slack, discord, gmail, github, …）
│   ├── tasks_dispatch.py, review_multipass.py  # GitHubイベント→タスク配線、マルチモデルレビュー
│   └── …
├── cli/                 # CLIパッケージ（demo含む）
├── server/              # FastAPI + 静的Web UI + Workspaceアプリ
│   ├── app.py           # アプリ生成・lifespan・認証/セットアップガード・静的マウント
│   ├── github_gateway.py, slack_socket.py, discord_gateway.py, zoom_gateway.py
│   ├── routes/          # REST/WebSocketルート（chat, room, voice, webhooks, …）
│   └── static/          # ダッシュボード、setupウィザード、workspace/（3D）、workspace/pixel/
├── swe/                 # 実験的CI自動修復ループ・SWEハーネス
├── demo/                # デモプリセットと同梱履歴
└── templates/           # 初期化テンプレート（ja / en / ko）ロール別作業規約を含む
```

</details>

---

## Documentation

**[Documentation Master Index](docs/en/README.md)** — Reading order guide, architecture deep dive, and list of design specifications.

| Documentation | Description |
|-------------|------|
| [Design Philosophy](docs/en/vision.md) | The foundational idea of "collaboration among imperfect individuals" |
| [Feature Overview](docs/en/overview.md) | Overall picture of what AnimaWorks can do |
| [Memory System](docs/en/memory/index.md) | Episodic memory, semantic memory, procedural memory, priming, active forgetting |
| [Security](docs/en/security.md) | Permission boundaries, data provenance, security operations |
| [Neuroscience Mapping](docs/en/brain-mapping.md) | Correspondence between each module and the human brain |
| [Architecture](docs/en/architecture/index.md) | Execution modes, prompt construction, configuration resolution |

## License

Apache License 2.0. See [LICENSE](LICENSE) for details.
