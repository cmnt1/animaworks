# AnimaWorks Demo — Try It in 60 Seconds

**[日本語版はこちら](README.ja.md)**

Spin up a fully working AI office with 3 autonomous agents — no setup wizard, no configuration. Just the repository and an authenticated CLI.

The demo comes pre-loaded with 3 days of activity history, so you'll see a living organization from the moment you open the dashboard.

## Quick Start

Run this from the **repository root** (after cloning with `scripts/setup.sh`, or `git clone` + `uv sync --all-extras`):

```bash
uv run animaworks demo
```

Open **http://localhost:18501** and you're in.

> **No API key needed** if you're already logged into **Claude Code** or **Codex** — authentication is detected automatically, in this order:
>
> 1. `ANTHROPIC_API_KEY` (export it if you have one)
> 2. **Claude Code** login (just log in with `claude`)
> 3. **Codex** login (run `codex login`)
>
> If none are available, the command prints a helpful guide and exits.

---

## What You'll See

When the dashboard loads, you'll find a 3-person team already at work:

| Agent | Role | What They Do |
|-------|------|-------------|
| **Alex** | Product Manager (leader) | Sets priorities, delegates tasks, reviews progress |
| **Kai** | Lead Engineer | Implements features, investigates technical issues |
| **Nova** | Team Coordinator | Manages schedules, keeps communication flowing |

Alex is in charge. Kai and Nova report to Alex. This hierarchy is fully functional — Alex can delegate tasks to them, check their status, and they report back autonomously.

### Things to try

- **Chat with Alex** — Ask about the team's progress or give a new directive
- **Watch the Activity feed** — See agents communicating in real-time
- **Check the Board** — #general channel has ongoing team discussions
- **Open the 3D Workspace** — See characters sitting at desks and moving around
- **Talk to Kai directly** — Ask him a technical question
- **Wait 5 minutes** — Heartbeats fire and agents start acting on their own

### Pre-loaded history

The demo includes 3 days of simulated activity (auto-adjusted to today's date):

- Activity logs showing past conversations and decisions
- Current tasks in progress
- Messages on the shared #general channel

This means the dashboard won't be empty — you'll see a team with context, history, and ongoing work from the first moment.

---

## Presets

Four presets are available, combining language and personality style:

| Preset | Language | Style | Characters |
|--------|----------|-------|------------|
| `en-business` (default) | English | Realistic professional | Alex, Kai, Nova |
| `en-anime` | English | Anime-inspired casual | Alex, Kai, Nova |
| `ja-business` | Japanese | Realistic professional | Kaito, Sora, Hina |
| `ja-anime` | Japanese | Anime-style casual | Kaito, Sora, Hina |

Switch presets with the `--preset` flag:

```bash
uv run animaworks demo --preset ja-anime
```

> **Note:** The preset is applied on first run only. To switch presets, stop the server and re-run with `--reset`:
>
> ```bash
> uv run animaworks demo --reset --preset ja-business
> ```

---

## Data & Reset

Demo data lives in **`~/.animaworks-demo`** — separate from your production `~/.animaworks`, so it never interferes with a real install. It uses port **18501** (one above the default 18500).

To start completely fresh, pass `--reset` — it wipes the demo data directory and re-initializes:

```bash
uv run animaworks demo --reset
```

---

## How the Demo Works

On first launch, the `animaworks demo` command:

1. Initializes the AnimaWorks runtime
2. Creates 3 agents from the selected preset's character sheets
3. Applies preset-specific configuration (heartbeat interval, locale, etc.)
4. Copies pre-built character assets (avatars)
5. Loads 3 days of example activity data with auto-adjusted timestamps
6. Detects your authentication and starts the server

Subsequent launches skip initialization and reuse the existing data in `~/.animaworks-demo`.

### Autonomous Behavior

Once running, the agents operate autonomously:

- **Heartbeat** — Every 5 minutes (demo interval), each agent reviews their situation and decides what to do
- **Cron tasks** — Scheduled tasks defined per agent (daily summaries, monitoring, etc.)
- **Delegation chains** — Alex delegates to Kai/Nova, they execute and report back
- **Board activity** — Agents post updates to shared channels

You don't need to do anything — just watch. Or jump in and give them new instructions.

---

## Troubleshooting

### No authentication found

You need one of `ANTHROPIC_API_KEY`, a **Claude Code** login, or a **Codex** login. Log in with `codex login` (or `claude`), or export your key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
uv run animaworks demo
```

### Port 18501 already in use

Another service is using that port. Stop it, or pass `--port` to use a different one:

```bash
uv run animaworks demo --port 9000   # access via http://localhost:9000
```

### Agents aren't responding

- Verify your authentication is valid (test your key at [console.anthropic.com](https://console.anthropic.com/), or re-run `codex login`)
- Check that your account has API credits available

### Want to reset everything

```bash
uv run animaworks demo --reset
```

---

## Next Steps

Ready to build your own AI organization?

- **Full install** — Run `uv run animaworks start` from the repository root to launch the setup wizard for your own team
- **Create your own agents** — Write a character sheet in Markdown and the framework does the rest
- **Add more LLMs** — AnimaWorks supports Claude, GPT, Gemini, local models, and more
- **Explore the docs** — [Design Philosophy](../docs/vision.md) · [Memory System](../docs/memory.md) · [Security](../docs/security.md)

---

*This demo is part of [AnimaWorks](https://github.com/xuiltul/animaworks) — an open-source framework for building autonomous AI organizations.*
