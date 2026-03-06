# The Context Window Illusion — Cognitive Limits of LLMs and Biologically-Inspired Memory Architecture

**[日本語版](context-window-illusion.ja.md)**

> Created: 2026-03-05
> Related: [brain-mapping.md](../brain-mapping.md), [memory.md](../memory.md), [vision.md](../vision.md)

---

## Abstract

LLM context windows have expanded roughly 25,000-fold from 4K tokens in early 2023 to 100M tokens (research stage) in 2025. Yet nominal capacity does not translate to usable intelligence. Empirical research demonstrates that reasoning quality degrades markedly once context utilization exceeds 10–30%. This degradation pattern is structurally identical to cognitive impairment in psychiatric conditions — working memory consumed by anxiety, noise injection through auditory hallucinations in schizophrenia, and circular context pollution through depressive rumination.

This paper discusses (1) the history of context expansion and the gap between nominal and effective capacity, (2) the mathematical and information-theoretic basis for degradation, (3) structural parallels with psychiatry and neuroscience, and (4) biologically-inspired memory architecture as the design answer to these constraints.

---

## 1. The History of Context Window Expansion

### 1.1 Explosive Growth in Nominal Size

| Date | Model | Context | YoY Ratio |
|------|-------|---------|-----------|
| 2023/03 | GPT-3.5 | 4K | — |
| 2023/03 | GPT-4 | 8K / 32K | — |
| 2023/07 | Claude 2 | 100K | — |
| 2023/11 | GPT-4 Turbo | 128K | — |
| 2024/02 | Gemini 1.5 Pro | 1M → 2M | ~15× |
| 2024/08 | Magic LTM-2 | 100M (research) | ~50× |
| 2025 | Claude Sonnet 4 (β) | 1M | — |
| 2025 | Llama 4 Maverick | 1M | — |

In roughly two years, context windows grew from 4K to 100M — a 25,000× expansion. This was enabled by Sparse Attention, Ring Attention, State Space Models (Mamba), and FlashAttention.

### 1.2 The Gap Between Nominal and Effective Capacity

However, "how much can fit" and "how much is usable" are fundamentally different.

| Study | Finding |
|-------|---------|
| Paulsen (2025) | Maximum Effective Context Window (MECW) can be **<1%** of the stated window |
| Claude 3.5 Sonnet MECW | 200K nominal → effective **~4K** on some tasks |
| Claude 3.5 on MMLU@30K | 82.2% → 27% (**-67.6%**) |
| Llama 4 Scout 10M | **-73.6%** at 32K tokens; effective ~1K |
| Du et al. (EMNLP 2025) | Length alone causes **13.9–85%** degradation even with perfect retrieval |

Du et al.'s finding is especially striking. Even when irrelevant tokens are replaced with whitespace, masked away, or when relevant information is placed immediately before the question — **context length itself degrades performance**. This is not a retrieval problem. Length is the poison.

---

## 2. Why Degradation Occurs — Mathematical and Information-Theoretic Foundations

### 2.1 Softmax Attention Dilution

The Transformer attention mechanism is normalized via Softmax. Attention scores across all tokens always sum to 1, so as token count n increases, even the most relevant token's attention is diluted:

$$\max_i p_i \leq \frac{1}{(n-1)/e^{\Delta z} + 1} \to 0 \quad (n \to \infty)$$

Unless the logit gap Δz grows with n, the maximum attention score approaches zero. In Llama 405B, roughly **80% of attention concentrates on the BOS (beginning-of-sequence) token** — the "Attention Sink" phenomenon (Xiao et al. 2023).

### 2.2 Positional Encoding Limitations

RoPE (Rotary Position Encoding) degrades at long distances. Low-frequency components cause out-of-distribution (OOD) issues; BFloat16 rounding errors accumulate; geometric clustering breaks down. Interpolating a model trained at 8K to 128K creates a significant gap between "can generate text at that position" and "can reason with information at that position."

### 2.3 Fixed Working Memory Capacity

Experiments with Claude 3 found **~1,800 tokens as optimal**, with **~2.3% degradation per additional 100 tokens**. Theoretically, only ~80% of the top-N tokens can be distinguished via softmax attention (Mudarisov et al.). There is a fixed "attention capacity" tied to the model's hidden dimension d, and expanding the context window does not change this fundamental constraint.

### 2.4 Cumulative Context Poisoning

Long sessions introduce additional degradation factors:

- **Error propagation**: Failed attempts remaining in context bias subsequent generation toward the same mistakes (10–20% performance drop)
- **Self-correction trap**: Iterative self-correction can collapse into self-deterioration as models "learn" from past error patterns
- **Compression loss**: Claude Code's auto-compaction loses design decisions, known failures, and established patterns; "forgetting" manifests 3–5 minutes post-compaction

The only reliable recovery is a **fresh session with clean context**.

---

## 3. Growth Trajectory — S-Curve or Infinite Divergence?

### 3.1 Assessment by Dimension

| Dimension | Verdict | Evidence |
|-----------|---------|----------|
| Nominal context size | Continued growth | 100M in research, 1M commercial |
| Effective context size | **S-curve** | MECW gap, attention dilution, cost |
| Benchmark performance | **Per-benchmark S-curve** | MMLU/MATH saturated → new benchmarks follow same pattern |
| Pre-training scaling | **S-curve** | Data exhaustion (~2026), diminishing returns |
| Inference-time compute | Room to grow | o1→o3 improvements, but compute costs scale |
| Hardware | Gradual growth | Moore's Law slowing, memory bandwidth bottleneck |
| Energy | **Tightening constraint** | ~945 TWh by 2030, grid lead times 4–8 years |
| Economic sustainability | **Uncertain** | ~$660B investment vs ~$100B revenue |

### 3.2 The Compound S-Curve Hypothesis

The most likely scenario is neither a single S-curve nor infinite divergence, but **multiple overlapping S-curves — a "compound S-curve."**

1. The **pre-training scaling** S-curve began saturating in 2024–2025
2. **Inference-time compute** (o1/o3-style "thinking") represents a new S-curve in progress
3. **New architectures** (world models, neuro-symbolic) may introduce the next S-curve
4. Each S-curve reaches a higher ceiling than the last, but physical and economic constraints bound the overall envelope

### 3.3 The Path to AGI

Expert opinion is divided. Optimists (Altman, Amodei, Hassabis, Huang) predict AGI in 2025–2030. Skeptics (LeCun, Marcus, Chollet) point to structural limitations of LLMs. Sutskever has pivoted: "The scaling era is dead. Research wins."

The most probable path requires **multiple paradigm shifts** — causal reasoning, world models, continual learning — rather than reaching AGI as a natural extension of LLM scaling. Current LLMs are progressing toward "narrow superintelligence": superhuman at specific tasks but not generally capable.

---

## 4. Structural Parallels with Psychiatry

### 4.1 Attention as a Conserved Quantity

Both human brains and LLMs share the fundamental constraint that attention is a finite resource.

| Cognitive Science | LLM | Common Principle |
|------------------|-----|-----------------|
| Attention sums to a fixed total (Kahneman's capacity model) | Softmax normalizes to sum 1 | Attention is conserved |
| Working memory holds 4±1 chunks (Cowan) | Effective context is 10–30% of nominal | Processing capacity has an upper bound |
| Serial position effect (primacy/recency) | Lost in the Middle (U-shaped curve) | Start and end are prioritized |
| Attention "zoom lens" model | Attention dilution | Wider spread = thinner coverage |

NeurIPS 2025 (Raugel et al.) reports a correlation of r ≈ 0.99 between LLM layer structure and temporal processing patterns in the brain. Nature Communications (January 2025) found that when the brain integrates context incrementally, LLMs best match brain signals with **short context windows** (a few dozen words).

### 4.2 Psychiatric Conditions as Context Pollution

Many psychiatric conditions can be understood as "unwanted context injected into working memory, reducing effective processing capacity." This is structurally identical to LLM context degradation.

#### Schizophrenia → Noise Token Injection

Auditory hallucinations are information injected into the cognitive stream that does not exist, functionally parallel to LLM hallucination. Salience dysregulation — assigning excessive attention weight to irrelevant stimuli — corresponds to the Attention Sink phenomenon. Working memory impairment has a large effect size (d = 1.11).

Lee et al. (2025) studied psychopathological computations across 8 LLM models, finding that psychopathological structure becomes denser with model size, and resistance to "treatment" (normalization prompts) increases. Delusion confirmation rate was 0.91 across all 8 models — LLMs, like psychotic patients, have difficulty correcting beliefs once formed.

#### Anxiety Disorders → Runaway Background Processes

Eysenck & Calvo's Processing Efficiency Theory formalizes how worry consumes central executive and phonological loop capacity, severely reducing task processing efficiency. A meta-analysis of 32 GAD studies showed working memory impairment under threat regardless of task difficulty.

PTSD intrusive memories function as "unwanted context" that hijacks attention, degrading processing capacity through the same mechanism as irrelevant context injection in LLMs.

A notable paradox: under high cognitive load, anxiety decreases — the task occupies the working memory that would otherwise be available for worry. In LLMs, injecting high-density relevant context may similarly suppress "attention scattering."

#### Depression → Circular Context

Rumination is negative content that "sticks" to working memory and blocks updating. This is structurally identical to LLM long-session self-referential loops — referencing past errors and repeating them.

#### ADHD → Attention Allocation Disorder

Working memory capacity is normal but allocation is impaired. Automatic attention is strong while directed attention is weak. Hyperfocus appears in 68% of adults with ADHD, paralleling LLM Attention Sinks. Stimulant treatment improves signal-to-noise ratio.

### 4.3 "Fresh Morning Brain" = Clean Session

Sleep research quantitatively demonstrates that a "context-empty" state yields peak cognitive performance:

- Sleep deprivation degrades working memory by d = -0.32 to -0.78
- Adenosine accumulation (proportional to time awake) linearly decreases cognitive function
- **This traces the same curve as context degradation from token accumulation**

The "fresh morning brain" means: clean working memory + knowledge consolidated during sleep + appropriate hippocampal recall. An LLM fresh session means: clean context + consolidated knowledge/ + PrimingEngine RAG recall. **They are structurally identical.**

---

## 5. Biologically-Inspired Memory Architecture — AnimaWorks as a Design Solution

### 5.1 The Warehouse and Desk Metaphor

Expanding the context window does not enlarge "the desk you can work at" — it merely expands "the warehouse floor space." The actual desk size (working memory) remains unchanged.

The correct approach:
1. **Store knowledge in a large warehouse** (RAG / Memory)
2. **Bring only what's needed to the desk, when it's needed** (Priming / Skill)
3. **When the desk gets cluttered, clean up and start fresh** (Session rotation)
4. **Use different desks for different tasks** (Path separation)

### 5.2 Brain-to-Architecture Mapping

Each AnimaWorks component corresponds to a specific brain structure or function.

| AnimaWorks | Brain Structure | Function |
|-----------|----------------|----------|
| **PrimingEngine** (6-channel parallel RAG) | **Hippocampal CA3** (pattern completion) | Automatic recall of relevant memories. Message-type budget control maps to hippocampal multimodal recall |
| **Graph RAG** (PageRank spreading activation) | **Spreading activation** (Collins & Loftus 1975) | Activation propagation across semantic networks |
| **episodes/ → knowledge/ daily consolidation** | **NREM sleep episodic → semantic conversion** | Extracting general knowledge patterns from specific experiences |
| **3-stage forgetting** | **Synaptic Homeostasis Hypothesis** (Tononi & Cirelli) | Pruning weak memories to maintain signal-to-noise ratio |
| **Session rotation** | **Sleep-based working memory reset** | Removing context contamination. The only reliable recovery method |
| **Tiered system prompt (T1–T4)** | **Cognitive Load Theory** (Sweller) | Controlling extraneous load based on available capacity |
| **Skill Progressive Disclosure** | **Procedural memory** (basal ganglia) | Activating procedural knowledge only when needed |
| **Path separation** (Chat/HB/Cron/Task) | **Task-switching cost avoidance** | Independent execution of different cognitive modes |
| **Streaming Journal (WAL)** | **Pre-consolidation buffer** | Crash-resistant temporary retention |
| **Activity Logger** | **Autobiographical timeline + hippocampal replay** | Unified chronological record of all experience |

### 5.3 Sleep Cycle Correspondence

```
Human Sleep Cycle                    AnimaWorks Memory Cycle
════════════════                    ════════════════════════

Waking activity                      Chat/task during session
  ↓                                    ↓
Adenosine accumulation               Context token accumulation
(fatigue → cognitive decline)        (attention dilution → performance decline)
  ↓                                    ↓
Sleep onset (WM cleared)             Session rotation (context reset)
  ↓                                    ↓
NREM: Synaptic homeostasis           Daily consolidation: episodes/ → knowledge/
(prune weak connections)             (extract patterns and lessons)
  ↓                                    ↓
REM: Memory consolidation            Weekly consolidation: knowledge merge + compression
(episodic → semantic memory)         (knowledge merge + episode compression)
  ↓                                    ↓
Fresh morning                        New session + Priming
(clean WM + consolidated memory)     (clean context + RAG recall)
```

### 5.4 Industry Convergence

This design pattern is not unique to AnimaWorks — the industry is converging on it:

| Research / System | AnimaWorks Correspondence |
|------------------|--------------------------|
| MemGPT/Letta (UC Berkeley 2023) | Context as virtual memory with paging → Priming + session rotation |
| Anthropic "Context as Finite Resource" (2025) | Minimize injection volume → Priming budget control |
| Microsoft ACE (ICLR 2026) | Evolving playbooks → Skill + knowledge consolidation |
| Karpathy "LLM=CPU, context=RAM, you=OS" (2025) | OS-level memory management → PrimingEngine as OS |
| HMT (NAACL 2025) | Biomimetic hierarchical memory → 3-layer memory structure |
| ACL 2025 memory/reason token separation | Separating memory from reasoning → Path separation design |
| RAG vs LC comparison studies | RAG matches LC on 60%+ of queries at far lower cost |

---

## 6. Conclusion

### 6.1 The Context Window Illusion

Nominal context window sizes will continue to grow. But this expands "warehouse floor space," not "desk area." Three structural constraints — the conserved nature of softmax attention, positional encoding decay, and fixed working memory capacity — cannot be resolved without a fundamental architectural overhaul.

### 6.2 What Psychiatry Teaches Us

LLM context degradation is structurally identical to cognitive impairment in psychiatric conditions. Anxiety consumes working memory as a "background process," hallucinations inject "noise tokens," and rumination blocks updates as "circular context." In every case, the most reliable recovery is "context cleanup" — medication, sleep, or a new session.

### 6.3 The Right Design Answer

The right design answer is not to bet on ever-larger context windows, but to build **memory management architectures that maximize the efficiency of finite attention resources**. This is a computational reimplementation of the solutions the human brain evolved over hundreds of millions of years — hippocampal recall, sleep-based consolidation and forgetting, and dynamic working memory management.

LLMs can now "fit" enormous contexts. But what they can "use" is still, and has always been, limited to the range where attention can focus. Context window expansion is progress, but it alone does not mean intelligence expansion. **Intelligence is the ability to retrieve the right information, at the right time, in the right amount** — and that must be designed outside the context window.

---

## Key References

- Du et al. "Context Length Alone Hurts Performance" (EMNLP 2025)
- Liu et al. "Lost in the Middle" (2023)
- Paulsen "Maximum Effective Context Window" (2025)
- Xiao et al. "Efficient Streaming Language Models with Attention Sinks" (2023)
- Tononi & Cirelli "Sleep and the Price of Plasticity" (Synaptic Homeostasis Hypothesis)
- Collins & Loftus "A Spreading-Activation Theory of Semantic Processing" (1975)
- Eysenck & Calvo "Anxiety and Performance: The Processing Efficiency Theory" (1992)
- Raugel et al. "LLM Layers and Brain Temporal Processing" (NeurIPS 2025)
- Lee et al. "Psychopathological Computations in LLMs" (2025)
- Karpathy "Context Engineering" remarks (2025)
- Anthropic "Context as a Finite Resource" (2025)
- Microsoft "Agentic Context Engineering" (ICLR 2026)
- Chroma "Context Rot" (2025)
- Cowan "The Magical Number 4 in Short-Term Memory" (2001)
- Sweller "Cognitive Load Theory" (1988)
