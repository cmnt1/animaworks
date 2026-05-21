# AnimaWorks Documentation

**[日本語](README.ja.md)**

No one can do anything alone. So I built an organization.

A team of imperfect individuals will always outperform a lone genius. As a psychiatrist examining LLMs, I saw the same architecture as the human brain. So I gave them the same kind of memory — the kind that accumulates experience, distills lessons, and forgets what no longer matters. A growing team of people, defined in code. That's AnimaWorks.

This page is your starting point for understanding the whole picture.

---

## Where to Start

### Getting up and running

1. **[Features](features.md)** — What AnimaWorks can do, end to end
2. **[CLI Reference](cli-reference.md)** — Every command from setup to daily operations
3. **[API Reference](api-reference.md)** — REST API specification for the web UI and scripting
4. **[Slack Integration](slack-socket-mode-setup.md)** — Connect Slack to your Animas (no public URL required)

### Understanding the architecture

1. **[Vision](vision.md)** — The core philosophy: imperfect individuals collaborating beats a single omniscient model
2. **[Technical Spec](spec.md)** — Execution modes, prompt construction, configuration resolution
3. **[Memory System](memory.md)** — Episodic, semantic, and procedural memory; priming; forgetting
4. **[Security](security.md)** — Defense-in-depth model and adversarial threat analysis

### Neuroscience and research

1. **[The Context Window Illusion](paper/context-window-illusion.md)** — Why bigger context doesn't mean better cognition, and the case for biologically-inspired memory
2. **[Brain Mapping](brain-mapping.md)** — How each AnimaWorks module maps to a region of the human brain
3. **[Memory System](memory.md)** — The hippocampus, neocortex, and basal ganglia, reimplemented in code
4. **[Vision](vision.md)** — Why a psychiatrist built this framework

---

## All Documents

### Core Concepts

| Document | Description |
|----------|-------------|
| [Vision](vision.md) | "Imperfect individuals collaborating create a more resilient organization than a single omniscient model." Encapsulation, library-style memory, autonomy, and heterogeneous multi-model design |
| [Features](features.md) | Autonomous agents, memory lifecycle, organizational hierarchy, multi-model support, voice chat, and everything else AnimaWorks does |

### Reference

| Document | Description |
|----------|-------------|
| [CLI Reference](cli-reference.md) | Every `animaworks` subcommand and option — initialization, server management, Anima operations, chat, model management, RAG repair, memory backends, Skill Hub, TaskBoard |
| [API Reference](api-reference.md) | All REST endpoints — authentication, Anima management, chat (SSE streaming), memory operations, configuration, webhooks |
| [Slack Integration](slack-socket-mode-setup.md) | Step-by-step Socket Mode setup. Create the Slack App, configure tokens, connect to your Animas. Works behind NAT |

### Architecture Deep Dive

| Document | Description |
|----------|-------------|
| [Technical Spec](spec.md) | Full specification. Six execution modes (S/C/D/G/A/B), prompt construction, execution-path isolation, configuration resolution precedence |
| [Memory System](memory.md) | Mapping to human memory models, RAG search, automatic recall, action memory gate, daily/weekly consolidation, active forgetting |
| [Security](security.md) | Threat model, data provenance tracking, trust-level classification, command execution control, path traversal defense, authentication |
| [Brain Mapping](brain-mapping.md) | LLM as neocortex, priming as hippocampus, forgetting as sleep-dependent homeostasis. Designed from clinical psychiatric experience |

### Research

| Document | Description |
|----------|-------------|
| [The Context Window Illusion](paper/context-window-illusion.md) | Context utilization degrades beyond 10–30%. Structural parallels with psychiatric cognitive impairment. The case for biologically-inspired memory architecture |

### Release Notes

| Version | Description |
|---------|-------------|
| [v0.5](release/v0.5.md) | Full RAG migration, 4-phase provenance security, Workspace UI overhaul, streaming performance 3–5x improvement |

---

## Design Specs (specs/)

Implementation specifications for individual features. Useful for contributors or anyone who wants to understand the engineering decisions behind AnimaWorks.

### Memory System

| Date | Spec |
|------|------|
| 2026-02-14 | [Priming Layer Design](specs/20260214_priming-layer_design.md) |
| 2026-02-18 | [Priming Format Redesign](specs/20260218_priming-format-redesign_implemented-20260218.md) |
| 2026-02-18 | [Unified Activity Log](specs/20260218_unified-activity-log-implemented-20260218.md) |
| 2026-02-18 | [Activity Log Spec Compliance](specs/20260218_activity-log-spec-compliance-fixes-implemented-20260218.md) |
| 2026-02-18 | [Streaming Journal (WAL)](specs/20260218_streaming-journal-implemented-20260218.md) |
| 2026-02-18 | [Episode Dedup, State Auto-update, Resolution Propagation](specs/20260218_episode-dedup-state-autoupdate-resolution-propagation.md) |
| 2026-02-18 | [Consolidation Validation Pipeline](specs/20260218_consolidation-validation-pipeline-20260218.md) |
| 2026-02-18 | [Knowledge Contradiction Detection & Resolution](specs/20260218_knowledge-contradiction-detection-resolution-20260218.md) |
| 2026-02-18 | [Memory System Enhancement Checklist](specs/20260218_memory-system-enhancement-checklist-20260218.md) |

### Procedural Memory

| Date | Spec |
|------|------|
| 2026-02-18 | [Procedural Memory Foundation](specs/20260218_procedural-memory-foundation-20260218.md) |
| 2026-02-18 | [Procedural Memory Auto-distillation](specs/20260218_procedural-memory-auto-distillation-20260218.md) |
| 2026-02-18 | [Procedural Memory Reconsolidation](specs/20260218_procedural-memory-reconsolidation-20260218.md) |
| 2026-02-18 | [Procedural Memory Utility & Forgetting](specs/20260218_procedural-memory-utility-forgetting-20260218.md) |

### Security

| Date | Spec |
|------|------|
| 2026-02-15 | [Memory Write Security](specs/20260215_memory-write-security-20260216.md) |
| 2026-02-28 | [Command Injection Fix](specs/20260228_security-command-injection-fix.md) |
| 2026-02-28 | [Path Traversal Fix](specs/20260228_security-path-traversal-fix.md) |

### Data Provenance

| Date | Spec |
|------|------|
| 2026-02-28 | [Phase 1: Foundation](specs/20260228_provenance-1-foundation.md) |
| 2026-02-28 | [Phase 2: Input Boundary](specs/20260228_provenance-2-input-boundary.md) |
| 2026-02-28 | [Phase 3: Propagation](specs/20260228_provenance-3-propagation.md) |
| 2026-02-28 | [Phase 4: RAG Provenance](specs/20260228_provenance-4-rag-provenance.md) |
| 2026-02-28 | [Phase 5: Mode S Trust](specs/20260228_provenance-5-mode-s-trust.md) |

### Tools

| Date | Spec |
|------|------|
| 2026-03-07 | [Generic Notion Tool](specs/20260307_generic-notion-tool_implemented-20260307.md) |
