# LLM Performance Degradation as Context Window Fills: Empirical Evidence Research

**Date:** 2026-03-05  
**Scope:** Quantitative and qualitative evidence for quality degradation (not just retrieval accuracy) as context utilization increases.

---

## 1. "Lost in the Middle" — Quantitative Studies

### Original Liu et al. 2023 Paper

**Source:** Liu et al., "Lost in the Middle: How Language Models Use Long Contexts" (Stanford, 2023/2024)

**Core finding:** U-shaped performance curve — models perform best at the beginning and end of context, worst in the middle.

**Exact performance numbers (multi-document QA, ~4K tokens, 20 documents):**

| Position | GPT-3.5-Turbo Accuracy |
|----------|-------------------------|
| Beginning (position 1) | ~75% |
| Middle (position ~10) | ~55% (below closed-book baseline of 56.1%) |
| End | ~65% |

**Interpretation:** ~20 percentage point drop from beginning to middle. Middle-position performance fell below the model's closed-book baseline, meaning the long context actively hurt performance when the answer was in the middle.

**Models tested:** GPT-3.5-Turbo, Claude-1.3, MPT-30B-Instruct, LongChat-13B (16K context). Both Claude-1.3 100K and GPT-3.5-Turbo-16K exhibited the effect.

**Tasks:** Multi-document QA, key-value retrieval.

### Follow-up Studies (2024–2025)

- **2024:** GPT-4 still shows a U-shaped curve, though with improved overall performance.
- **2025 (Chroma Context Rot):** Needle position showed "no notable variation" in their NIAH extension — suggesting that for some tasks, **context length alone** (not position) drives degradation. This complements rather than contradicts Lost-in-the-Middle.
- **2025 (Du et al., "Context Length Alone Hurts..."):** Evidence placed at the **beginning** (best position per Lost-in-the-Middle) still degrades with length — proving degradation is driven by **sheer input length**, not just position.

### Performance at Different Context Utilization Levels

| Utilization | Evidence |
|-------------|----------|
| **10%** | Greg Kamradt: GPT-4 recall degrades when fact is at 7–50% document depth. Best at top and bottom. |
| **30%** | Kamradt: Low recall when needle at 7–50% depth. GPT-4 degradation starts above ~73K of 128K (~57% utilization). |
| **50%** | Lost-in-the-Middle: Worst performance when answer in middle. |
| **80%** | Chroma: "Model performance consistently degrades with increasing input length" across all experiments. |
| **100%** | Paulsen MECW: Models can fall short of MCW by up to 99%. Some fail with 100 tokens. |

---

## 2. Effective Context Utilization & MECW

### Maximum Effective Context Window (MECW)

**Source:** Norman Paulsen, "Context Is What You Need: The Maximum Effective Context Window for Real World Limits of LLMs" (2025, arXiv:2509.21361)

**Definition:** MECW = longest span of input tokens where the model maintains stable, high-quality performance without significant degradation.

**Findings:**

- **99% shortfall:** All tested models fell short of their Maximum Context Window (MCW) by up to **99%**.
- **Early failure:** Some top-tier models failed with as little as **100 tokens** in context.
- **1,000-token cliff:** Most models showed severe accuracy degradation by **1,000 tokens**.
- **Task-dependent:** MECW varies by problem type — no single effective limit.

### Models Perform Best at 10–30% of Stated Window

**Evidence:**

- **Llama 4 Scout (10M claimed):** Effective context ~**1K tokens** on NoLiMa (semantic retrieval). **-73.6%** performance drop at 32K tokens (0.3% of capacity). At 32K, accuracy collapsed to **21.6%** on semantic retrieval.
- **Claude 3.5 Sonnet (200K claimed):** Effective context ~**4K tokens** in some benchmarks.
- **GPT-4 (128K):** Kamradt: degradation starts above **73K tokens** (~57%); best performance within 8K–32K range. Performance degrades significantly beyond ~10% of max capacity when filtering for genuine context-based answers.

### Attention Dilution & Attention Sink

**Attention dilution:** Attention weights sum to 1 (softmax). Adding tokens monotonically decreases attention per token. More context → thinner attention per token.

**Attention sink (2024):**

- **~80% of attention** can concentrate on the beginning-of-sequence (BOS) token in Llama 405B.
- Emerges during pretraining; correlated with loss and data distribution.
- When softmax is replaced with sigmoid (no normalization), attention sinks do not emerge in models up to 1B parameters.
- "Attention sinks and compression valleys are two sides of the same coin" — both stem from massive activations in the residual stream, especially at BOS in middle layers.

**Why models focus on beginning and end:**

- Primacy and recency effects (analogous to human memory).
- BOS acts as an "attention sink" that absorbs disproportionate attention.
- Information retrieval demands during pretraining favor recent (end) and early (beginning) information.

---

## 3. Claude / GPT-4 Specific Degradation

### Needle-in-a-Haystack Results

**Greg Kamradt (GPT-4 128K):**

- Recall degraded above **73K tokens**.
- Low recall when fact at **7–50%** document depth.
- Facts at the **beginning** recalled regardless of context length.
- Best recall at top and in second half of document.

**Chroma Context Rot (2025) — 18 models including GPT-4.1, Claude 4, Gemini 2.5, Qwen3:**

- NIAH (lexical) overestimates capability; models perform well on it.
- With **semantic matching**, **distractors**, and **ambiguous questions**, performance degrades significantly as input length increases.
- "Model performance consistently degrades with increasing input length" across all experiments.
- Lower needle-question similarity → faster degradation with length.
- Distractors have non-uniform impact that amplifies with input length.

### Reasoning Quality (Not Just Retrieval)

**Du et al. 2025 — "Context Length Alone Hurts LLM Performance Despite Perfect Retrieval":**

- **13.9%–85%** performance degradation as input length increases, **even with perfect retrieval**.
- Tested: math (GSM8K), QA (MMLU), coding (HumanEval), variable summation.
- Degradation occurs when:
  - Irrelevant tokens replaced with **whitespace** (minimal distraction)
  - Irrelevant tokens **masked** (model attends only to evidence + question)
  - Evidence placed **immediately before** the question

**Specific numbers (Du et al.):**

| Model | Task | 0 tokens | 7.5K | 15K | 30K |
|-------|------|----------|------|-----|-----|
| Llama-3-8B | VarSum | 97% | -11% | -35% | -50% |
| Llama-3-8B | MMLU | 62.8% | -11.3% | -15.9% | -21.1% |
| Llama-3-8B | HumanEval | 57.3% | -5.5% | -22% | -50% |
| Mistral-7B | VarSum | 66% | -5% | -11% | -34% |
| Claude-3.5 | MMLU | 82.2% | -41.7% | -38.8% | -67.6% |

**Llama-3.1-8B (128K claimed):** On MMLU extended to 30K tokens with irrelevant tokens — retrieval exact match 970/1000, but **accuracy dropped 24.2%** vs short-context. On VarSum with essay distraction: **59%** drop from 96% baseline (Llama); **44%** drop from 68% (Mistral) at 30K context.

**Closed-source (whitespace distraction):** GPT-4o, Claude-3.7, Gemini-2.0 more robust but still degrade. Claude-3.5 showed **-67.6%** on MMLU at 30K context.

### Softmax Bottleneck

- Attention scores diluted across tokens; softmax normalization forces zero-sum allocation.
- More tokens → smaller per-token attention → weaker signal for reasoning.
- Directly supports "attention budget" interpretation.

---

## 4. Qualitative Behavior Changes at High Context

### Confusion & Hallucination

- **2026 study (fact distribution):** Longer contexts can be detrimental when relevant evidence is dispersed. Performance varies significantly across models.
- **Anti-hallucination instructions:** Can reduce fabrication but make models "overly conservative," sharply reducing accuracy on literal extraction and logical inference.
- **Self-conditioning effect (2025):** Models more likely to err when context contains their own prior errors; degrades execution on long-horizon tasks.
- **LVLMs (ICCV 2025):** Hallucinations increase in longer responses due to greater reliance on context for coherence and completeness.

### Instruction Following

- **Context rot (Chroma):** Models "effectively forget information in the middle 60% of long conversations."
- **Claude Opus 4.5 reports (2026):** "Severe laziness," refusal to follow constraints, rapid context loss, minimal changes to complex problems, substantial tokens without meaningful results.
- **Reasoning paradox:** More reasoning compute does not improve hallucination detection for most models; some use it to rationalize false premises.

### Creativity & Problem-Solving

- **Du et al.:** Reasoning, QA, and coding degrade with longer inputs even under perfect retrieval.
- **RAG saturation:** Performance often saturates or degrades as more documents are added (Cuconasu, Jin, Yu et al.).
- **Long CoT:** Excessively long chain-of-thought can hurt reasoning (Zeng et al. 2025).

### Production Reports

- **Context rot:** "Advertised context windows largely unusable in practice" — models forget middle 60%.
- **Claude Opus 4.6 (Feb 2026):** Claimed to address context rot with 76% accuracy on long-context benchmarks at 1M tokens — implying prior versions had persistent limitations.

---

## 5. "Attention Budget" Theory

### Fixed Attention Budget

- **Zero-sum attention:** Weights sum to 1; more tokens → less attention per token.
- **Attention dilution:** Core mechanism; adding tokens monotonically decreases attention each token receives.
- **Attention sink:** Early tokens (especially BOS) absorb ~80% of attention, further reducing effective budget for middle tokens.

### KV Cache Pressure

- Quality degrades when KV cache approaches or exceeds the model's pre-trained context window.
- Token eviction strategies can disrupt positional encoding coherence → performance deterioration.
- KV cache optimization leverages attention sinks but introduces trade-offs.

### Position Encoding Degradation

**RoPE long-term decay (2024):**

- Relative upper bound on token correlations decreases as relative distance increases.
- Position interpolation for longer contexts degrades position resolution.
- Base parameter bounds context length; power-law relationship between context length and required base value.

**Proposed fixes:** Ms-PoE, 3D-RoPE, CREAM, HoPE — all address long-term decay and position resolution.

### Why Beginning and End Are Favored

1. **Primacy:** Early tokens receive more attention (attention sink at BOS).
2. **Recency:** Autoregressive training favors recent tokens for next-token prediction.
3. **Pretraining:** Information retrieval demands balance long-term (uniform) and short-term (recent) recall.
4. **Architecture:** "Mix-Compress-Refine" — early mixing, middle compression, late refinement.

---

## Summary Table: Key Numbers

| Finding | Source | Numbers |
|---------|--------|---------|
| Lost-in-the-Middle drop | Liu et al. 2023 | 75% → 55% (beginning → middle) |
| Context length degradation | Du et al. 2025 | 13.9%–85% with perfect retrieval |
| MECW shortfall | Paulsen 2025 | Up to 99% short of MCW |
| Early failure | Paulsen 2025 | Some fail at 100 tokens; most by 1K |
| Llama 4 Scout effective | NoLiMa 2025 | ~1K effective vs 10M claimed; -73.6% at 32K |
| GPT-4 degradation start | Kamradt | Above 73K of 128K |
| Attention on BOS | 2024 research | ~80% in Llama 405B |
| Claude MMLU at 30K | Du et al. 2025 | -67.6% (82.2% → ~27%) |
| VarSum at 30K (Llama) | Du et al. 2025 | 97% → 47% (-50%) |
| Middle 60% forgotten | Chroma / industry | "Context rot" in long conversations |

---

## Mitigation Strategies (from research)

1. **Retrieve-then-reason (Du et al.):** Prompt model to recite evidence before solving → up to 4% improvement on GPT-4o (RULER), up to 31.2% on Mistral (GSM8K).
2. **Shorter context:** Prefer less context when possible.
3. **Positioning:** Place critical information at beginning or end when controllable.
4. **RAG:** Limit retrieved documents; more documents can hurt performance.
5. **CoT length:** Avoid excessively long chain-of-thought.

---

## References (Key Papers)

- Liu et al., "Lost in the Middle: How Language Models Use Long Contexts" (2023/2024)
- Du et al., "Context Length Alone Hurts LLM Performance Despite Perfect Retrieval" (2025, arXiv:2510.05381)
- Paulsen, "Context Is What You Need: The Maximum Effective Context Window for Real World Limits of LLMs" (2025, arXiv:2509.21361)
- Chroma, "Context Rot: How Increasing Input Tokens Impacts LLM Performance" (2025)
- "When Attention Sink Emerges in Language Models" (2024, arXiv:2410.10781)
- "Why do LLMs attend to the first token?" (2025, arXiv:2504.02732)
- Greg Kamradt, "Pressure Testing GPT-4 & Claude 2.1 Long Context"
- NoLiMa (Non-Literal Matching benchmark)
