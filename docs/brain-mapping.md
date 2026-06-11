# AnimaWorks Brain Mapping — Architecture Mapped to the Human Brain

**[日本語版](brain-mapping.ja.md)**

> Created: 2026-02-19 | Updated: 2026-05-21
> Related: [vision.md](vision.md), [memory.md](memory.md)

---

## Background

The designer of AnimaWorks is a psychiatrist with over 30 years of programming experience. AnimaWorks' memory system, autonomic mechanisms, and execution architecture are **intentionally** mapped to the structure of the human brain, grounded in clinical neuroscience. This is not merely a metaphor — it is an attempt to reuse the brain's information-processing architecture as a design pattern.

In psychiatric practice, one routinely observes dysfunctions of the brain's various subsystems: memory disorders, attention disorders, executive function disorders, and more. Knowing what happens when each subsystem is impaired made it possible to identify the subsystems an AI agent requires and to design a clear separation of their respective roles.

---

## Overall Mapping

### Neocortex — LLM Model

| LLM Function | Brain Region | Description |
|---|---|---|
| Reasoning & decision-making | Prefrontal cortex (PFC) | Executive function. Receives memories injected by priming and makes judgments |
| Language comprehension | Wernicke's area (temporal lobe) | Semantic understanding of input messages |
| Language production | Broca's area (frontal lobe) | Generation of response text |
| Pre-trained knowledge | Crystallized patterns in temporal cortex | World knowledge baked into LLM weights. A separate system from file-based memory — "innate intelligence" |
| Transformer attention | Parietal association cortex + PFC selective attention | Allocation of attention to relevant information within the context |

The LLM in its entirety corresponds to the **neocortex** as a whole. However, in AnimaWorks' design, because the framework handles subcortical functions (memory consolidation, forgetting, arousal maintenance), the role left to the LLM is effectively distilled into the **conscious processing of the prefrontal cortex (PFC)**.

As memory.md states:

> The agent (LLM) is "the one who thinks," not "the administrator of its own brain."

### Duality of Pre-trained Knowledge and File-based Memory

The knowledge baked into the LLM's pre-trained weights and AnimaWorks' file-based memory are **separate systems**. In the human brain as well, patterns crystallized in the cerebral cortex (implicit knowledge / crystallized intelligence) and episodic memory via the hippocampus function as independent systems.

| Type of Knowledge | Human Brain | AnimaWorks |
|---|---|---|
| Innate intelligence | Crystallized intelligence (cortical patterns) | LLM pre-trained weights |
| Experientially acquired knowledge | Fluid intelligence + episodic memory | File-based memory (episodes/, knowledge/, procedures/) |

This distinction aligns with the "imperfect individual" design philosophy described in vision.md. Precisely because pre-trained knowledge alone is insufficient, an experience-based memory system is necessary.

---

### Memory System — Hippocampus, Cerebral Cortex, & Basal Ganglia

| Human Memory | Brain Region | AnimaWorks Implementation | Characteristics |
|---|---|---|---|
| **Working memory** | Prefrontal cortex | LLM context window | Capacity-limited. Temporary holding of "what is currently being thought about" |
| **Episodic memory** | Hippocampus → neocortex | `episodes/` | Chronological record of "when and what happened" |
| **Semantic memory** | Temporal cortex | `knowledge/` | Lessons and knowledge decoupled from context |
| **Procedural memory** | Basal ganglia, cerebellum | `procedures/`, `skills/` | "How to do it." Strengthened through repetition |
| **Person memory** | Fusiform gyrus, temporal pole | `shared/users/` | Automatic recall of "who is this person" |

### Internal Structure of Working Memory — Baddeley's Model

Based on Baddeley (2000):

| Baddeley's Component | Function | AnimaWorks Implementation |
|---|---|---|
| **Central executive** | Attentional control; orchestration of retrieval from long-term memory | Agent orchestrator |
| **Episodic buffer** | Integration of multiple sources into a unified representation | Context assembly layer (priming results + conversation history) |
| **Phonological loop** | Temporary holding of verbal information | Text buffer (recent conversation turns) |

Following Cowan (2005), working memory is understood as a "spotlight on activated long-term memory." The context window is not an independent store, but rather the portion of long-term memory that currently has attention directed toward it.

---

### Memory Recall — Dual Pathways

| Recall Pathway | Brain Process | AnimaWorks Implementation |
|---|---|---|
| **Automatic recall** | Pattern completion by the CA3 auto-associative network of the hippocampus. Unconscious, fast (250–500 ms), unsuppressible | Priming layer (multi-source parallel search + deterministic gate) |
| **Deliberate recall** | Strategic search by the prefrontal cortex (PFC). Conscious, slow | `search_memory` / `read_memory_file` tools |

### Spreading Activation — Collins & Loftus (1975)

| Search Signal | Brain Counterpart | AnimaWorks Implementation |
|---|---|---|
| Semantic neighborhood discovery | Spreading activation among concept nodes | Dense vector similarity search (ChromaDB) |
| Prioritization of recent memories | Recency effect | Time-decay function (half-life: 30 days) |
| Strengthening of frequently used memories | Hebb's rule / long-term potentiation (LTP) | Access frequency boost |
| Multi-hop association | Propagation through associative networks | Knowledge graph + Personalized PageRank (implicit-link vector similarity threshold 0.75; procedural distillation RAG duplicate detection at 0.85 is a separate pathway) |

### Priming and Dynamic Budget — Selective Attention

`PrimingEngine` pulls from multiple memory sources in parallel and raises the relevant parts into the LLM's working memory. In brain terms, this resembles the hippocampus reactivating related memories from environmental cues while the prefrontal cortex selects what enters attention.

The current implementation mainly uses these sources:

| Source | Function | Brain counterpart | Base token guide |
|---|---|---|---|
| Sender profile | "Who is talking to me?" | Fusiform face area / temporal pole (person recognition) | 500 |
| Recent activity | "What happened recently?" | Hippocampal replay (recent episode reactivation) | 1300 |
| Important + related knowledge | "What do I know about this?" | Semantic memory retrieval (temporal cortex) | 500 + 1000 |
| Pending tasks | "What am I supposed to do?" | Prospective memory / intention monitoring (rostral PFC) | 500 |
| Episodes | "Have I had similar experiences?" | Episodic semantic search (hippocampus-cortex) | 800 |
| Graph context | "What relationships surround this?" | Multi-hop activation in associative networks | 500 |

Recent outbound messages and pending human-facing notifications are also included as auxiliary context. They remind the Anima what it just sent and help prevent duplicate sends or missed notifications.

Retrieved memories pass through the deterministic priming gate. The gate treats each item as an `anchor`, `guardrail`, `pointer`, `evidence`, or `suppress` item, deciding whether to include full text, provide only a pointer, highlight evidence, or omit it for this turn. This corresponds to prefrontal selection of what enters the attentional spotlight.

Skills are no longer automatically injected by the main priming body. Active skills, the Skill Router, Skill Hub, promotion, and curator in `core/skills/` operate as a separate procedural-memory system. Skill body text or pointers are read only when needed.

Pending tasks prefer TaskBoard and fall back to the legacy task queue when unavailable. TaskBoard retains processing, deferred, suppressed, and background states, and selects which tasks should surface in the current context. This maps to prospective memory: keeping future intentions at low activation until the right cue recalls them.

#### Dynamic Budget Allocation — Attentional Resource Management

In normal chat paths, the priming token budget is adjusted dynamically by message type — **selective attention** at the system level:

| Message Type | Budget (default, `PrimingConfig`) | Brain Analogy |
|---|---|---|
| Greeting | 500 | Low attentional load (routine social interaction) |
| Question | 2000 | Moderate-to-high attentional load (retrieval-oriented) |
| Request | 3000 | High attentional load (task-oriented, maximal resource allocation) |
| Heartbeat | max(200, context_window * 5%) | Tonic alertness (minimum arousal maintenance) |

The heartbeat formula `max(budget_heartbeat, int(context_window * heartbeat_context_pct))` gives larger-context models more priming data during autonomous patrol — analogous to tonic firing of the reticular activating system scaling with overall cortical capacity.

This mirrors Kahneman's (1973) attention-as-resource theory: more cognitive resources for demanding tasks, fewer for routine stimuli, optimizing signal-to-noise within the limited context window.

#### Tiered Prompt and Trigger-Based Filtering

Depending on context window size, `build_system_prompt()` adjusts injected sections across four tiers (T1–T4). At 128k+ all sections; 32k–128k reduced; 16k–32k omits bootstrap/vision/specialty/DK/memory_guide; below 16k also omits permissions/org/messaging/emotion. This implements **selective inclusion under attentional limits**.

Section selection also depends on trigger (`chat` / `inbox` / `heartbeat` / `cron` / `task`, etc.). Heartbeat and cron are lighter; task paths use the minimum context needed for execution. Controlling what enters "consciousness" per path optimizes cognitive load.

#### Unified Activity Log

As the primary source for recent activity, `ActivityLogger` records incoming messages, responses, DMs, channel posts, notifications, tool use, cron, memory writes, errors, resolved events, task updates, and related activity on one timeline. This is a hippocampal log that preserves event order and can later be reactivated. Streaming crash resilience is handled by the streaming journal, while daily housekeeping cleans up short-term memory and old logs.

---

### Memory Consolidation — Sleep and Integration

| AnimaWorks | Brain Process | Description |
|---|---|---|
| **Immediate encoding** (session boundary) | Hippocampal rapid one-shot encoding | At conversation end, a differential summary is recorded in episodes/ |
| **Daily consolidation** (midnight cron) | NREM slow-wave — spindle — ripple cascade | Substantive summarization and extraction are executed by the Anima's tool loop. `ConsolidationEngine` (`core/memory/consolidation.py`) is a module focused on **pre-processing** (episode collection, `issue_resolved` collection) and **post-processing** (RAG index update/rebuild, monthly forgetting invocation, legacy knowledge migration, etc.) |
| **issue_resolved → procedure** | Proceduralization of resolutions | Nightly knowledge self-correction scans activity_log for `issue_resolved` events; ProceduralDistiller generates procedures (`create_procedures_from_resolved`) |
| **Weekly integration** | Neocortical long-term consolidation | Deduplication and merging of knowledge/, pattern distillation |
| **Contradiction scan** | Hippocampal pattern separation | NLI-assisted consistency checks across knowledge files, with LLM resolution for conflicts |
| **Prediction-error-based reconsolidation** (`reconsolidation.py`) | Reconsolidation theory, Nader et al. (2000) | LLM revision of procedures whose failure count exceeds threshold. Versioning and archival |

---

### Forgetting — Synaptic Homeostasis

Based on the synaptic homeostasis hypothesis of Tononi & Cirelli (2003):

| AnimaWorks | Brain Process | Description |
|---|---|---|
| **Daily downscaling** | Synaptic downscaling during NREM sleep | Marking low-activity chunks |
| **Neurogenesis-inspired reorganization** | Memory circuit reorganization via dentate neurogenesis | LLM merge of low-activity + similar chunks |
| **Complete forgetting** (monthly) | Elimination of sub-threshold synapses | Knowledge-like chunks: archive → delete when low activation exceeds **90 days** and `access_count` is below threshold (`FORGETTING_LOW_ACTIVATION_DAYS` / `FORGETTING_MAX_ACCESS_COUNT`). **Procedure** downscaling uses separate thresholds (e.g. **180 days** unused with low use counts) via `PROCEDURE_INACTIVITY_DAYS` etc. Procedure archives keep only **`PROCEDURE_ARCHIVE_KEEP_VERSIONS`** (5 versions) |
| **Forgetting resistance** (procedures, skills, knowledge) | Basal ganglia procedural memory resists forgetting | Important knowledge, mature procedures, explicitly protected procedures, skills, and user memories are harder to forget. Detailed thresholds are maintained in the [Memory System](memory.md) document |

### Procedural Distillation and Metaplasticity

Beyond the three-stage forgetting cycle, AnimaWorks adds memory subsystems aligned with finer aspects of neural plasticity:

| AnimaWorks | Brain Process | Description |
|---|---|---|
| **Procedural distillation** (`distillation.py`) | Skill consolidation in basal ganglia–cerebellar circuits | LLM sorts episodic memory into knowledge vs procedures. Detects repeated action patterns from activity logs and distills reusable procedure files — analogous to motor sequences automating through basal ganglia loops |
| **Weekly pattern detection** | Metaplasticity (Abraham & Bear, 1996) | Activity-log clustering over 7-day windows finds recurrent behavior. Expresses "learning how to learn" — adapting memory formation, not just content |
| **RAG duplicate detection** (similarity ≥ 0.85) | Hippocampal pattern separation | `RAG_DUPLICATE_THRESHOLD = 0.85` in `distillation.py`. Vector similarity before saving new procedures avoids redundant encoding — like dentate orthogonalization of similar memories |
| **Resolution tracking** (`resolution_tracker.py`) | Organizational long-term memory (transactive memory) | Cross-Anima shared resolution log in `shared/resolutions.jsonl`. Organizational knowledge of "who resolved what" — Wegner (1987) |
| **TaskBoard / task queue** | Prospective memory / working-memory extension | Externalizes deadlines, stale items, processing, deferred, suppressed, and background work. Extends working memory past the context window, like an external notepad for the central executive |
| **Skill Hub / Promotion / Curator** | Procedural memory consolidation and pruning | Promotes frequently useful procedures into skills and reviews unused or failure-prone skills. Maps to repeated actions becoming skills in basal-ganglia circuits and unused action patterns weakening over time |

The procedural distillation pipeline runs on two timescales:

- **Daily**: LLM classifies episode sections into knowledge / procedures / skip; writes structured procedure files with YAML front matter (confidence scores, success/failure counts)
- **Weekly**: Vector clustering on activity entries detects repeated patterns and distills generalized procedures

This dual-timescale design mirrors skill-acquisition neuroscience: explicit daily classification shifts toward implicit procedural knowledge via weekly pattern distillation — the hippocampus-to-basal-ganglia transition Doyon & Benali (2005) describe.

---

### Arousal & Autonomic Mechanisms

| AnimaWorks | Brain Region | Description |
|---|---|---|
| **Heartbeat** (periodic patrol) | **Reticular activating system (ARAS)** | Maintains arousal. Does not fix the content of consciousness; provides its preconditions. Fires rhythmically — without it, dormancy (coma) |
| **Cron** (scheduled tasks) | Hypothalamic circadian rhythm (SCN) | Time-based periodic triggers. Sleep–wake and daily/weekly/monthly biorhythms |
| **ProcessSupervisor** | Autonomic nervous system | Process life cycle outside awareness: start, monitor, restart each Anima |
| **Unix domain socket IPC** | White-matter tracts | Physical pathways between Anima processes |
| **Messenger** | Synaptic transmission | Message send/receive; text links encapsulated individuals |

#### Heartbeat = Reticular Activating System (ARAS) in Detail

The ascending reticular activating system (ARAS) projects from the brainstem reticular formation through the thalamus to the cortex, sustaining arousal. It maps to AnimaWorks heartbeat as follows:

| ARAS Characteristic | Heartbeat Characteristic |
|---|---|
| Sustains arousal (does not specify conscious content) | Periodically activates the Anima (what to think is left to heartbeat.md) |
| Automatic, rhythmic firing | Runs automatically at the configured interval |
| Failure leads to coma | Without heartbeat, the Anima sleeps unless messaged |
| Precondition for consciousness, not consciousness itself | Precondition for autonomous action, not the judgment itself |
| Arousal varies with sensory input | Wakes immediately on inbound messages (even off heartbeat cadence) |

---

### Organizational Structure — The Social Brain

| AnimaWorks | Brain / Psychology Counterpart | Description |
|---|---|---|
| **Supervisor–subordinate hierarchy** | Neural basis of social hierarchy (PFC–amygdala circuit) | Flow of orders and reports |
| **Encapsulation (internals invisible)** | Theory of mind | Others' internal states are only inferable |
| **Messaging** | Linguistic communication | Text-only links; no shared memory or direct reference |
| **identity.md (personality)** | Personality (stable PFC–limbic patterns) | Immutable baseline for judgment |
| **injection.md (role)** | Social / occupational role | Mutable organizational guidance |

### Execution Modes — Levels of Autonomy

Memory subsystems are mode-agnostic, but cortical (LLM) executor choice changes how autonomous the agent is. Current code distinguishes **six modes** (`resolve_execution_mode()`):

| Mode | Executor | Brain Analogy | Description |
|---|---|---|---|
| **S** (SDK) | Claude Agent SDK | Full cortical function with executive control | Native Claude tools and session continuity |
| **C** (Codex) | Codex CLI | Cortical function close to S | OpenAI Codex-family models via Codex |
| **D** (Cursor Agent) | Cursor Agent CLI | External agent loop | MCP-integrated alternate path |
| **G** (Gemini CLI) | Gemini CLI | External agent loop | stream-json and tool loop |
| **A** (Autonomous) | LiteLLM + tool_use loop | Cortical function via external mediation | Multi-provider tool use managed by the framework |
| **B** (Basic) | One-shot (assisted) | Heavy external scaffolding | Framework handles memory I/O; session chaining largely unsupported |

Wildcard rules in `models.json` (and related config) auto-select mode; `status.json` `execution_mode` can override. S/C/D/G favor tools plus continued sessions; B strongly externalizes working memory — consistent with the memory mapping in this document.

---

## Neuroscientific Rationale for Design Principles

### Why Context Window Limits Are a "Feature"

Human working memory capacity is limited to about 4 ± 1 chunks (Cowan, 2001). This is not a defect but an **evolutionary adaptation that enforces selective attention and preserves judgment quality**. If all memories surfaced at once, relevant information could not be selected and decisions would degrade.

AnimaWorks adopts this as a deliberate design feature: prime only what is needed so the model decides in a clean context.

### Why Forgetting Is Necessary

Sleep-related synaptic downscaling weakens wake-strengthened synapses globally, preserving signal-to-noise ratio. Without forgetting, accumulated memories become noise and retrieval quality falls.

Active forgetting in AnimaWorks mimics this biology and helps keep vector search accurate long term.

### Why Collaboration Among "Imperfect Individuals" Beats One Omniscient Agent

Human organizations work because each member decides with limited view and memory, exchanging imperfect information in their own words (vision.md). That aligns with cognitive load theory (Sweller, 1988) and distributed cognition (Hutchins, 1995).

---

## Summary

AnimaWorks is a design born at the intersection of psychiatric clinical practice and engineering. The brain's information architecture is a **reusable design pattern** independent of its biological substrate (neurons); AnimaWorks is a system that demonstrates that reuse.

By mapping the LLM to the neocortex, the memory system to the hippocampal–cortical complex, heartbeat to the reticular activating system, and forgetting to synaptic homeostasis — integrated end to end — it realizes an entity that thinks, learns, forgets, and collaborates autonomously.
