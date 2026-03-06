# AnimaWorks Memory Architecture: Neuroscience Mapping Analysis

> **Created**: 2026-03-05  
> **Related**: [brain-mapping.md](../brain-mapping.md), [memory.md](../memory.md)  
> **Purpose**: Detailed component-by-component mapping of AnimaWorks memory architecture to neuroscience concepts, with validity assessment, alignment analysis, and research-backed recommendations.

---

## Executive Summary

AnimaWorks implements a memory architecture that closely mirrors human neurocognitive systems. This document maps each component to specific brain structures and cognitive processes, evaluates the validity of each mapping, assesses alignment with current neuroscience, identifies where the artificial design may exceed biological capabilities, and suggests neuroscience-informed improvements.

**Key finding**: The framework's design is remarkably well-grounded in cognitive neuroscience. The Priming Engine, 3-stage forgetting, consolidation pipeline, and graph-based RAG all have direct, well-documented biological analogs. Recent AI research (2024–2025) on biologically-inspired memory architectures validates this approach and suggests AnimaWorks is aligned with emerging best practices.

---

## 1. Priming Engine — Hippocampal Pattern Completion & Automatic Recall

### Neuroscience Mapping

| AnimaWorks Component | Brain Structure/Process | Functional Similarity |
|---------------------|-------------------------|------------------------|
| PrimingEngine (6 channels) | Hippocampal CA3 auto-associative network + cortical retrieval pathways | Automatic, pre-conscious memory activation before deliberate processing |
| Sole activity reader for prompt construction | Hippocampal "gatekeeper" role in memory systems theory | Single point of memory access for downstream processing |
| 6-channel parallel retrieval | Distributed cortical-hippocampal circuits | Multiple memory systems activated in parallel |

### Why This Mapping Is Valid

**Priming** is a well-established psychological phenomenon (Neely, 1977; Tulving & Schacter, 1990). When one stimulus (prime) is encountered, related concepts in memory become partially activated, reducing retrieval latency for subsequent targets. The semantic priming effect—faster response to "doctor" when preceded by "nurse"—demonstrates that activation spreads through associative networks automatically and unconsciously.

The hippocampus performs **pattern completion**: partial cues trigger full memory retrieval via the CA3 recurrent network's auto-associative properties. This occurs in ~250–500 ms, before conscious awareness. AnimaWorks' PrimingEngine replicates this by pre-injecting relevant context into the system prompt before the LLM (analogous to PFC) processes the message—the agent "receives" already-activated memories without explicit search.

### Alignment with Neuroscience

**Strong match.** The design aligns with:
- **Dual-process theory of memory** (Atkinson & Shiffrin): Automatic vs. controlled retrieval
- **Spreading activation** (Collins & Loftus, 1975): Related concepts activated in parallel
- **Hippocampal indexing theory** (Teyler & DiScenna, 1986): Hippocampus as pointer to cortical traces

### Where AnimaWorks May Be More Optimal

- **Explicit channel separation**: Biology has overlapping circuits; AnimaWorks' 6 discrete channels (sender_profile, recent_activity, related_knowledge, skill_match, pending_tasks, episodes) provide cleaner resource budgeting than diffuse neural activation
- **Token budgets**: Fixed budgets prevent "priming overload"—biology has no equivalent hard limit, and over-priming can cause interference

### Neuroscience Insights to Incorporate

- **Priming replication crisis** (2012): Some priming effects failed to replicate. Consider A/B testing whether all 6 channels contribute measurably to task performance
- **Negative priming**: When a prime inhibits rather than facilitates. Could add "suppression" for recently rejected/irrelevant memories to reduce interference

---

## 2. Spreading Activation — Collins & Loftus (1975) and AnimaWorks' Graph-Based RAG

### Theory Overview

Collins & Loftus (1975) proposed that semantic memory is organized as a network of concept nodes connected by associative links. When a concept is activated (e.g., by encountering the word "red"), activation spreads to neighboring nodes with strength proportional to link strength and distance. Activation decays over "hops." This explains:
- **Semantic priming**: "nurse" primes "doctor" because they share pathways
- **Categorization speed**: Closer concepts in the network are verified faster
- **Fan effect**: Concepts with many associations are slower to retrieve (activation spreads thin)

### AnimaWorks Implementation

| Collins & Loftus Concept | AnimaWorks Implementation |
|-------------------------|---------------------------|
| Concept nodes | RAG chunks (knowledge, episodes, procedures) |
| Associative links | Explicit: Markdown `[[filename]]` links; Implicit: vector similarity ≥ 0.75 |
| Activation spread | Personalized PageRank (α=0.85) over directed graph |
| Decay | MAX_HOPS=2 limits propagation depth |
| Link strength | Edge weights from similarity scores |

**Source**: `core/memory/rag/graph.py` — `KnowledgeGraph` builds NetworkX DiGraph from markdown links + vector similarity; spreading activation expands initial dense search results via graph traversal.

### Mapping Validity

**Strong.** The implementation directly instantiates spreading activation:
1. **Multi-hop association**: PageRank propagates activation through the graph, so chunks linked (explicitly or implicitly) to query-relevant chunks receive secondary activation
2. **Decay**: Limited hops prevent unbounded spread (biological activation also decays)
3. **Personalization**: Query/sender acts as "origin node"—activation originates from context-relevant seeds

### Alignment with Neuroscience

**Matches** the core mechanism. One difference: Collins & Loftus modeled **semantic** memory; AnimaWorks applies it to **episodic + semantic + procedural** chunks. This is consistent with modern views that episodic and semantic memory share retrieval mechanisms (Tulving, 2002).

### Potential Improvements from Neuroscience

- **Fan effect**: Concepts with many links may dilute activation. Consider inverse-fan weighting (fewer links = stronger per-link activation) to prioritize "focused" chunks
- **Temporal decay**: Collins & Loftus did not model time; AnimaWorks has time-decay in forgetting. Could add **recency-weighted activation** in the graph (recently accessed nodes get boost) to mirror hippocampal recency effects

---

## 3. Schemas and Knowledge Consolidation

### Schema Theory (Bartlett, 1932)

**Schemas** are abstract mental structures that organize knowledge and guide interpretation. Bartlett showed that memory is **reconstructive**—people distort new information to fit existing schemas and omit schema-inconsistent details. Schemas:
- Contain "slots" for variable information
- Connect related concepts in semantic networks
- Are built and revised through repeated exposure
- Enable prediction and inference from partial information

### AnimaWorks Mapping

| Schema Concept | AnimaWorks Implementation |
|----------------|---------------------------|
| Schema formation | Daily: episodes → knowledge (LLM extracts patterns, lessons) |
| Schema revision | Reconsolidation when new info contradicts existing memory |
| Schema slots | YAML frontmatter (tags, confidence, success_count) |
| Schema integration | Weekly: knowledge merge + episode compression |
| Procedural schemas | issue_resolved → procedures (resolved-to-procedure pipeline) |

**Source**: `core/memory/consolidation.py`, `core/memory/rag/indexer.py` — Daily consolidation runs LLM-based extraction from episodes to knowledge; weekly runs merge and compression.

### Mapping Validity

**Strong.** The episode → knowledge pipeline is a computational analog of **schema abstraction**: specific experiences (episodes) are distilled into generalizable patterns (knowledge) that lose contextual detail. This mirrors:
- **Systems consolidation** (Squire & Alvarez, 1995): Hippocampus-dependent episodic traces become neocortical semantic knowledge over time
- **Semanticization** (Tulving): Episodic memories "semanticize" with repetition—context fades, gist remains

### Alignment with Neuroscience

**Matches** the transformation from episodic to semantic. Neuroscience debate: Does the hippocampus "transfer" memories to cortex, or does it remain involved? AnimaWorks keeps both—episodes/ and knowledge/ coexist; RAG can retrieve from both. This aligns with **Multiple Trace Theory** (Nadel & Moscovitch): detailed episodic traces remain hippocampus-dependent; generalized knowledge is cortical.

### Where AnimaWorks May Be More Optimal

- **Explicit extraction**: Biology does consolidation during sleep (offline); AnimaWorks uses LLM to explicitly extract—more controlled, less "dream-like" drift
- **Confidence scoring**: Schema strength in biology is implicit (synaptic weight); AnimaWorks' `confidence`, `success_count` provide interpretable, adjustable schema strength

### Neuroscience Insights to Incorporate

- **Schema distortion**: Bartlett's work suggests consolidation may introduce systematic bias (fitting to existing schemas). Consider: Does LLM extraction over-fit to existing knowledge/? Add "surprise" or "novelty" detection to flag schema-inconsistent episodes for special handling
- **Schema competition**: Multiple schemas can compete. When similar episodes map to different knowledge chunks, consider explicit schema conflict resolution

---

## 4. Session Rotation & Tiered Context — Working Memory and Cognitive Load

### Neuroscience Mapping

| AnimaWorks Component | Brain Structure/Process |
|----------------------|-------------------------|
| Chat vs. Heartbeat vs. TaskExec session separation | Task switching / context switching costs |
| Tiered context (Full, Background-Auto, Minimal) | Working memory capacity limits (Cowan: 4±1 chunks) |
| Tiered system prompt (T1–T4 by context window) | Attentional resource allocation (Kahneman, 1973) |
| Session compaction/rotation | Working memory refresh / rehearsal |

### Why This Mapping Is Valid

**Working memory** has limited capacity (Miller, 1956; Cowan, 2001: ~4 chunks). This is not a bug but a feature—it enforces selective attention. **Task switching** imposes additional costs (Monsell, 2003): switching between Chat and Heartbeat contexts would cause interference if they shared the same "workspace."

AnimaWorks' design:
- **Separate session files** (`current_session_chat.json` vs. `current_session_heartbeat.json`): Avoids cross-task interference—analogous to maintaining separate "task sets" in PFC
- **Tiered context by trigger**: Heartbeat/Cron omit specialty, emotion, a_reflection—reducing cognitive load for autonomous patrol vs. human chat
- **Tiered prompt by context window**: T1 (128K+) full; T4 (<16K) minimal—scales "what fits in consciousness" to available resources

### Alignment with Neuroscience

**Strong match.** The tiered design implements **Cognitive Load Theory** (Sweller, 1988): intrinsic load (task complexity) + extraneous load (irrelevant info) must not exceed working memory capacity. AnimaWorks explicitly reduces extraneous load for smaller contexts and lighter triggers.

### Where AnimaWorks May Be More Optimal

- **Explicit capacity limits**: Biology has soft limits; AnimaWorks uses hard token budgets—prevents overflow and enables predictable behavior
- **Trigger-based filtering**: Biology doesn't have "modes" as cleanly separated; AnimaWorks' chat/inbox/heartbeat/cron/task triggers provide deterministic context selection

---

## 5. 3-Stage Forgetting System — Synaptic Homeostasis Hypothesis

### Neuroscience Mapping

| AnimaWorks Stage | Brain Process | Source |
|------------------|---------------|--------|
| **Stage 1: Synaptic downscaling** (daily) | Sleep-dependent synaptic down-selection | Tononi & Cirelli (2003, 2006); SHY hypothesis |
| **Stage 2: Neurogenesis reorganization** (weekly) | Hippocampal neurogenesis, circuit reorganization | Frankland et al. (2013); Aimone et al. (2014) |
| **Stage 3: Complete forgetting** (monthly) | Elimination of sub-threshold synapses | Synaptic pruning |

### Why This Mapping Is Valid

**Synaptic Homeostasis Hypothesis (SHY)**: During wakefulness, learning causes net synaptic potentiation. This creates problems: energy cost, saturation, reduced SNR. **Sleep** enables synaptic downscaling—selective weakening of synapses while protecting recently active ones. The result: signal-to-noise ratio improves; the brain is ready for new learning.

AnimaWorks' Stage 1:
- **90-day unaccessed, <3 access** → marked for downscaling
- **Selective**: Protects procedures, skills, high-success knowledge
- **Daily**: Mirrors sleep cycle

**Neurogenesis**: New neurons in the dentate gyrus integrate into circuits and can "displace" old memories. AnimaWorks' Stage 2: **merge similar (≥0.80) low-activity chunks**—reorganizing the memory graph rather than adding new nodes. Analogous to circuit reorganization.

**Complete forgetting**: Stage 3 archives then deletes. Biology: synapses below threshold are pruned. AnimaWorks: chunks below activation threshold for 90+ days are removed (`FORGETTING_LOW_ACTIVATION_DAYS`).

### Alignment with Neuroscience

**Strong match.** The design explicitly cites Tononi & Cirelli. The 3-stage cascade (mark → merge → delete) is a plausible computational analog of the biological sequence.

### Implementation Details (from `forgetting.py`)

- `DOWNSCALING_DAYS_THRESHOLD = 90`
- `DOWNSCALING_ACCESS_THRESHOLD = 3`
- `REORGANIZATION_SIMILARITY_THRESHOLD = 0.80`
- `FORGETTING_LOW_ACTIVATION_DAYS = 90` (knowledge) / 180 (procedures)
- `PROTECTED_MEMORY_TYPES`: skills, shared_users

### Where AnimaWorks May Be More Optimal

- **Explicit protection rules**: Biology's protection is activity-dependent; AnimaWorks' `importance == "important"`, `success_count >= 2` provide explicit, auditable criteria
- **Archive before delete**: Enables recovery; biology has no "undo"

### Neuroscience Insights to Incorporate

- **Sleep stages**: NREM vs. REM may have different consolidation/forgetting roles. Consider whether "light" vs. "deep" forgetting stages could be differentiated (e.g., weekly = light, monthly = deep)
- **Reactivation during sleep**: Protected memories may be reactivated during sleep. Could simulate by periodically "touching" high-value chunks to refresh access timestamps

---

## 6. Memory Consolidation — Hippocampal-Cortical Systems

### Neuroscience Mapping

| AnimaWorks Process | Brain Process |
|-------------------|---------------|
| Daily: episodes → knowledge | NREM slow-wave → spindle → ripple cascade; hippocampal-neocortical dialogue |
| Daily: issue_resolved → procedures | Skill consolidation in basal ganglia-cerebellar circuit |
| Weekly: knowledge merge + episode compression | Neocortical long-term consolidation | 
| NLI + LLM validation | Hippocampal pattern separation; hallucination detection |

### Why This Mapping Is Valid

**Systems consolidation** (Squire, 1992): The hippocampus rapidly encodes episodic memories; during offline periods (sleep), these are gradually integrated into neocortical circuits. The result: memories become more generic, less context-dependent.

AnimaWorks' daily consolidation:
- **Episodes → knowledge**: LLM extracts patterns, lessons—explicit semanticization
- **issue_resolved → procedures**: Resolved problems become reusable procedures—analogous to proceduralization of repeated actions (Doyon & Benali, 2005)

**Contextual Binding Theory** (alternative view): Hippocampus may not "transfer" but rather "bind" item and context. AnimaWorks keeps episodes/ and knowledge/ separate—consistent with both views: episodes remain; knowledge is extracted copy.

### Alignment with Neuroscience

**Matches** the transformation pipeline. The dual-timescale (daily extraction, weekly merge) mirrors sleep-stage differentiation (NREM for declarative, REM for procedural in some models).

---

## 7. Skill Progressive Disclosure — Procedural Memory and Selective Activation

### Neuroscience Mapping

| AnimaWorks Component | Brain Structure/Process |
|----------------------|-------------------------|
| Skill match by description (names only initially) | Basal ganglia procedural memory activation |
| Full content on-demand via `skill` tool | Conscious retrieval from procedural store |
| 3-stage matching (keyword → lexical → vector) | Cascaded activation (fast associative → slow strategic) |

### Why This Mapping Is Valid

**Procedural memory** (Squire, 1992): "How to" knowledge—skills, habits. Stored in basal ganglia and cerebellum. **Not declarative**—hard to verbalize; accessed through performance. Procedural memory is **resistant to forgetting** (AnimaWorks: skills in `PROTECTED_MEMORY_TYPES`).

**Progressive disclosure**: Biology doesn't load full procedural traces into working memory at once. Skills are "activated" by context (e.g., seeing a piano primes finger movements) but full execution requires retrieval. AnimaWorks: match skills by description → return names only → agent requests full content when needed. Reduces context bloat while preserving access.

### Alignment with Neuroscience

**Strong match.** The description-based matching mirrors **skill priming**—context activates relevant procedures; explicit retrieval (tool call) loads full content. The protection of skills from forgetting aligns with basal ganglia resistance to decay.

---

## 8. Streaming Journal (WAL) — Short-Term Buffer Before Consolidation

### Neuroscience Mapping

| AnimaWorks Component | Brain Process |
|----------------------|---------------|
| Write-ahead log for streaming output | Sensory buffer / iconic memory |
| Crash recovery | Resilience of pre-consolidation traces |
| Flush every 1s or 500 chars | Chunking before transfer to stable storage |

### Why This Mapping Is Valid

Before memories consolidate, they exist in a **labile** state. Sensory information is briefly held in buffers (iconic: ~100ms; echoic: ~2s) before encoding. The hippocampus has a similar role: rapid, labile encoding before offline consolidation.

**StreamingJournal** holds streaming LLM output in a buffer, flushing incrementally. If the process crashes, the journal survives—recoverable. This is analogous to: (1) holding information in a labile buffer, (2) incremental transfer to stable storage, (3) crash = buffer survives, consolidation interrupted but recoverable.

### Alignment with Neuroscience

**Conceptual match.** The WAL is more of an engineering pattern (database WAL) than a direct brain analog, but the functional role—protecting in-flight data from loss—parallels the brain's need to protect pre-consolidation traces from interruption (e.g., sleep deprivation disrupts consolidation).

---

## 9. Activity Logger — Unified Timeline and Priming Source

### Neuroscience Mapping

| AnimaWorks Component | Brain Process |
|----------------------|---------------|
| Unified activity log (all interactions) | Autobiographical memory timeline |
| Sole source for Priming "Recent Activity" | Hippocampal replay / recent episode reactivation |
| Format for priming (1300 token budget) | Attentional selection over recent experience |

### Why This Mapping Is Valid

**Autobiographical memory** (Conway, 2005): A timeline of self-relevant events. The hippocampus supports temporal organization—"what happened when." ActivityLogger provides exactly this: a chronological record of messages, tool use, heartbeats, etc.

**Hippocampal replay**: During rest/sleep, the hippocampus replays recent experiences. Priming's "Recent Activity" channel injects recent events into context—analogous to making recently replayed content available to the "conscious" (LLM) processor.

**Sole reader**: The "hippocampal model" in design docs—PrimingEngine is the only component that reads ActivityLogger for prompt construction. This mirrors the hippocampus as the primary gateway for episodic information into cortical processing.

### Alignment with Neuroscience

**Strong match.** The architecture correctly identifies the hippocampus as the activity reader; the builder does not read ActivityLogger directly.

---

## 10. RAG with Graph-Based Spreading Activation — Integrated Retrieval

### Summary Mapping

| Component | Neuroscience Analog |
|-----------|---------------------|
| Dense vector search (ChromaDB) | Semantic similarity / pattern matching in temporal cortex |
| Knowledge graph (NetworkX) | Associative network (Collins & Loftus) |
| Personalized PageRank | Spreading activation with decay |
| Episodes + knowledge + procedures | Episodic + semantic + procedural memory systems |
| Time-decay, access-count | Hebbian strengthening / long-term potentiation |

### Alignment

The integrated system—vector search for initial retrieval, graph for expansion—realizes a **hybrid** model: similarity-based access (like cortical pattern completion) + associative spreading (like semantic network). This is consistent with modern views that episodic and semantic retrieval share mechanisms but differ in content (Tulving, 2002).

---

## 11. Recent AI/Neuroscience Research (2024–2026)

### Biologically-Inspired AI Memory Architectures

| Paper / System | Key Finding | Relevance to AnimaWorks |
|----------------|-------------|-------------------------|
| **Dzhivelikian & Panov (2025)** — Episodic memories into cognitive maps | Hebbian-like learning structures episodic memories into cognitive maps; no backpropagation; hippocampus-like first level | AnimaWorks' episode → knowledge consolidation mirrors cognitive map formation; could explore Hebbian-like chunk linking |
| **RoboMemory (2025)** | Multi-memory framework: Spatial, Temporal, Episodic, Semantic. Dynamic knowledge graph for embodied agents | AnimaWorks has similar multi-memory separation; RoboMemory's spatial/temporal could inform future extensions (e.g., workspace layout) |
| **Nature Comm. (2025)** — Corticohippocampal hybrid networks | Dual representations (specific + generalized) mitigate catastrophic forgetting | AnimaWorks' episodes (specific) + knowledge (generalized) implements this dual representation |
| **ProcMEM, ReMe, MemSkill (2025)** | Procedural memory from experience; distillation; utility-based refinement | AnimaWorks' procedures/ and issue_resolved pipeline aligns; could adopt utility-based refinement for procedure pruning |
| **COLMA** | Scenario-driven framework with sensory, short-term, long-term memory | AnimaWorks' tiered context and session separation aligns with layered memory |

### Validation

AnimaWorks' design is **aligned with** and in some cases **ahead of** recent research. The episodic/semantic/procedural separation, consolidation pipeline, and forgetting system are all represented in the 2024–2025 literature. The graph-based spreading activation is less common in AI systems but well-grounded in cognitive psychology.

---

## 12. Recommendations: Neuroscience-Informed Improvements

### High Priority

1. **Recency-weighted activation in graph**: Add time-decay to PageRank so recently accessed chunks receive a boost—mirrors hippocampal recency effects.
2. **Schema conflict detection**: When consolidation produces knowledge that contradicts existing knowledge/, flag for review—Bartlett's schema distortion.
3. **Priming channel ablation study**: Empirically verify which of the 6 channels contribute to task performance—address priming replication concerns.

### Medium Priority

4. **Fan effect mitigation**: Weight graph edges inversely to node degree (fewer links = stronger activation per link).
5. **Differentiated forgetting stages**: Consider "light" (weekly) vs. "deep" (monthly) forgetting with different thresholds.
6. **Procedural utility refinement**: Adopt ReMe-style utility-based pruning for procedures (beyond success_count).

### Lower Priority

7. **Negative priming**: Suppress recently rejected memories to reduce interference.
8. **Spatial/temporal memory**: If workspace/embodied use cases emerge, consider RoboMemory-style spatial and temporal memory channels.

---

## 13. Summary Table

| AnimaWorks Component | Neuroscience Analog | Match Quality | Notes |
|----------------------|---------------------|---------------|-------|
| Priming Engine | Hippocampal CA3 + cortical retrieval | Strong | 6 channels; sole activity reader |
| Spreading activation (graph) | Collins & Loftus (1975) | Strong | PageRank + similarity links |
| Schemas / consolidation | Bartlett, systems consolidation | Strong | Episode → knowledge; schema abstraction |
| Session rotation | Working memory, task switching | Strong | Separate sessions per path |
| Tiered context | Cognitive load, WM capacity | Strong | T1–T4; trigger-based filtering |
| 3-stage forgetting | SHY, neurogenesis, pruning | Strong | Daily/weekly/monthly cascade |
| Skill progressive disclosure | Procedural memory, basal ganglia | Strong | Names first; full on demand |
| Streaming Journal | Pre-consolidation buffer | Conceptual | WAL for crash recovery |
| Activity Logger | Autobiographical timeline | Strong | Sole Priming source |
| RAG + graph | Episodic + semantic + procedural | Strong | Integrated retrieval |

---

## References

- Bartlett, F. C. (1932). *Remembering: A Study in Experimental and Social Psychology*. Cambridge University Press.
- Collins, A. M., & Loftus, E. F. (1975). A spreading-activation theory of semantic processing. *Psychological Review*, 82(6), 407–428.
- Cowan, N. (2001). The magical number 4 in short-term memory. *Behavioral and Brain Sciences*, 24(1), 87–114.
- Dzhivelikian, E. A., & Panov, A. I. (2025). A biologically interpretable cognitive architecture for online structuring of episodic memories into cognitive maps. *arXiv:2510.03286*.
- Kahneman, D. (1973). *Attention and Effort*. Prentice-Hall.
- Squire, L. R. (1992). Memory and the hippocampus. *Psychological Review*, 99(2), 195–231.
- Tononi, G., & Cirelli, C. (2003). Sleep and synaptic homeostasis. *Sleep Medicine Reviews*, 7(1), 49–62.
- Tulving, E. (1972). Episodic and semantic memory. In *Organization of Memory* (pp. 381–403). Academic Press.
- Tulving, E., & Schacter, D. L. (1990). Priming and human memory systems. *Science*, 247(4940), 301–306.
