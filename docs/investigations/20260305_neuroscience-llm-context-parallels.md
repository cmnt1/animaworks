# Neuroscience of Working Memory, Attention, and Cognitive Load: Parallels to LLM Context Window Mechanics

**Date:** 2026-03-05  
**Scope:** Research synthesis on human cognition (working memory, attention, cognitive load, PFC) and direct parallels to LLM attention/context mechanisms. Includes 2024–2026 papers explicitly drawing cognitive–LLM parallels.

---

## 1. Working Memory Capacity and Limits

### 1.1 Miller's 7±2 vs. Cowan's 4±1

**Miller (1956):** "Magical number seven plus or minus two" — people can hold ~7 chunks in working memory. This figure inadvertently stalled capacity research for ~40 years.

**Cowan's revision:** Central storage capacity is more limited — approximately **3–5 meaningful items** for young adults, often cited as **4±1**. Young adults recall only 3–4 longer verbal chunks (idioms, short sentences) vs. Miller's findings with shorter items.

**Reconciliation (2024, Journal of Cognition):** Miller and Cowan measure different aspects under different conditions. Capacity varies by:
- **Presentation time and attention:** Longer presentation enables recoding/chunking → higher apparent capacity
- **Task demands:** Different measurement methods yield different results
- **Item complexity:** Simpler items (digits, letters) allow higher recall than complex items (idioms, sentences)

*Source: Journal of Cognition, "Modelling Working Memory Capacity: Is the Magical Number Four, Seven, or Does it Depend on What You Are Counting?" (2024)*

### 1.2 Baddeley's Working Memory Model

| Component | Function |
|-----------|----------|
| **Central Executive** | Supervisory control: selective attention, inhibition, task switching, binding, updating |
| **Phonological Loop** | Verbal/speech storage, preserves order |
| **Visuospatial Sketchpad** | Visual and spatial information storage |
| **Episodic Buffer** | Integrates phonological, visuospatial, and LTM into unified episodes |

**Key principle:** Tasks using different components can run simultaneously with minimal interference; tasks using the same component cannot. Model dominant for 50+ years.

### 1.3 Working Memory and General Intelligence (g Factor)

- **Correlation:** WMC and fluid intelligence (Gf) typically **r = 0.75–0.85** with multiple indicators
- **Causal debate:** Capacity hypothesis (WMC causally influences Gf) challenged — WMC–reasoning correlation does not strengthen with more capacity-demanding tasks
- **Alternative:** High WMC enables accurate problem representation and stable maintenance; high Gf involves disengaging from outdated hypotheses and generating new ones. Both organized around top-down processing goals
- **Strategy use:** Individual differences in problem-solving strategies partially mediate the WMC–gF relationship

### 1.4 Working Memory Overload → Reasoning Degradation

**When capacity is exceeded:**
- **Long-term encoding bottleneck:** Overloading WM during encoding degrades subsequent LTM retrieval — limits both specific details and gist
- **Neural effects:** Performance decline predicted by (1) task failure during overload, (2) amygdala activation, (3) reduced amygdala–DLPFC coupling
- **Mechanism:** Overload reduces activation in regions essential for task performance and suppression of negative affect; impairs prefrontal–limbic coordination

*Source: "Long-term representational costs of overloading working memory" (Psychonomic Bulletin & Review, 2025); "Working Memory Overload: Fronto-Limbic Interactions" (2010)*

---

## 2. Attention as a Finite Resource

### 2.1 Broadbent's Filter Theory

- First to describe attention using information-processing metaphor
- **Limited capacity:** Selective filter allows certain stimuli through; unattended stimuli filtered out and lost
- **Bottleneck model:** Only a limited amount of information passes through at any time
- Filter operates early (physical characteristics) before semantic processing

### 2.2 Kahneman's Capacity Model (1973, "Attention and Effort")

- Attention as a **capacity-limited system** requiring effort allocation
- Complements Broadbent: attention fundamentally finite, not unlimited

### 2.3 Spotlight Metaphor and Zoom Lens Model

- **Spotlight:** Attention as illuminated beam enhancing processing within focus, reducing processing outside
- **Zoom lens model:** Attention can vary in size like a camera lens
- **Width–intensity trade-off:** As spotlight widens, processing efficiency decreases — **wider beam = less intensity per stimulus**
- Broader beam distributes limited cognitive resources across larger area

*Source: Eriksen & St. James (1986); "Selective spatial enhancement: Attentional spotlight size impacts spatial but not temporal perception" (2015)*

### 2.4 Inattentional Blindness

- Failure to perceive unexpected stimuli in plain sight when attention is engaged elsewhere
- **Gorilla experiment:** Most participants counting basketball passes fail to notice person in gorilla costume
- **Key factor:** Attentional goals (not stimulus properties alone) most influential
- Without attention: can perceive presence, location, color — but not shape
- Age increases susceptibility; ADHD patients may perform better

### 2.5 Normalization Model (Reynolds & Heeger, 2009)

- **Divisive inhibition:** Output divided by (constant + local stimulus contrast)
- Attention produces response gain, contrast gain, tuning sharpening, or suppression depending on conditions
- **Canonical neural computation** — operates in vision, olfaction, attention, value encoding
- Conceptually similar to softmax: constrained allocation where total resources are fixed and distributed across competing stimuli

---

## 3. Cognitive Load Theory (Sweller)

### 3.1 Three Types of Load

| Type | Definition | Source |
|------|------------|--------|
| **Intrinsic** | Complexity of information/task; element interactivity | Task difficulty, prior knowledge |
| **Extraneous** | Effort from design/presentation, independent of content | Instructional design |
| **Germane** | Resources devoted to deeper learning, schema formation | Meaningful processing |

**Foundation:** Limited-capacity working memory vs. unlimited long-term memory with automated schemas.

### 3.2 Extraneous Load Actively Harms Performance

- Not just "wastes resources" — **actively degrades** learning and performance
- Consumes cognitive resources that should be available for actual learning

### 3.3 Split-Attention Effect

- **Definition:** Learners must mentally integrate information from separate locations/formats (e.g., text + diagram, formula + graphic)
- **Mechanism:** Forcing mental integration increases extraneous WM load
- **Evidence:** Students with **integrated instruction** (diagrams + text combined) spent less time processing and outperformed split-attention conditions
- **Design principle:** Physically or temporally integrate disparate sources to eliminate mental integration demand

*Source: Sweller et al., "Managing split-attention and redundancy in multimedia instruction" (1999)*

---

## 4. Prefrontal Cortex as "Context Window"

### 4.1 PFC and Working Memory

- **Traditional view:** PFC neurons maintain task-relevant information through persistent delay-period activity
- **Revised view:** PFC may generate top-down signals influencing posterior sensory areas where representations are maintained
- **Capacity control:** PFC implements crucial capacity control; allocates limited memory resources among competing demands
- **Prioritization:** PFC prioritizes which information receives WM resources — manages fundamental cognitive bottleneck

### 4.2 Dynamic Coding

- Working memory does not rely solely on static persistent activity
- **Dynamic coding:** Information encoded in patterns of functional connectivity that change across task phases
- Layer-specific: superficial DLPFC layers preferentially respond to WM load during critical periods

### 4.3 PFC Overload → Default Mode Network / Mind Wandering

- **dlPFC:** Promotes mind-wandering initiation but decreases awareness of wandering thoughts
- **vmPFC:** Downregulates mind-wandering, increases awareness
- **DMN:** Medial PFC, posterior cingulate, inferior parietal lobule — engaged during mind wandering
- **Coordinated interaction:** dlPFC and vmPFC interact via theta oscillations; when PFC is overloaded, DMN takes over

### 4.4 Dopamine's Role

- **Maintenance:** Dopamine D1 signaling organizes network dynamics underlying WM
- **Updating:** PFC and midbrain dopamine system work together for WM updating (manipulating, refreshing)
- Dopamine release from ventral mesencephalon essential for sustained PFC firing during delay periods

### 4.5 Stress (Cortisol) Reduces Effective PFC Capacity

- **Acute stress:** Reduces WM-related activity in DLPFC; reallocates resources away from executive networks
- **Chronic stress:** Sustained corticosterone in PFC directly causes WM deficits; blocking corticosterone synthesis prevents deficits
- **Causal confirmation:** Injecting corticosterone into unstressed animals induces same deficits as chronic stress
- Glucocorticoids enhance consolidation but impair WM through common neural mechanism

*Source: "Acute Psychological Stress Reduces Working Memory-Related Activity in the Dorsolateral Prefrontal Cortex"; "Sustained corticosterone rise in the prefrontal cortex..." (2019)*

---

## 5. Direct Parallels to LLM Attention Mechanism

### 5.1 Attention as Fixed Total (Softmax Parallel)

- **Human:** Attention sums to a fixed total; more items competing = less attention per item
- **LLM:** Softmax attention weights sum to 1; more tokens = attention distributed across more positions
- **Normalization model:** Divisive inhibition in brain implements constrained allocation analogous to softmax

### 5.2 Primacy/Recency ↔ "Lost in the Middle"

| Human (Serial Position Effect) | LLM (Lost in the Middle) |
|-------------------------------|---------------------------|
| Primacy: first 3–4 items best recalled | Best performance at context beginning |
| Recency: last ~8 items best recalled | Strong performance at context end |
| U-shaped curve by position | U-shaped performance by token position |
| Murdock 1962: primacy over first 3–4 words, recency over last 8 | Liu et al. 2023: ~75% at position 1, ~55% at middle, ~65% at end |

**2025 interpretation:** "Lost in the middle" may be emergent adaptation to different retrieval demands during pre-training — some tasks require uniform recall (long-term), others prioritize recent (short-term). Not simply a flaw.

### 5.3 Chunking ↔ Context Compression

- **Human:** Chunking increases apparent WM capacity (Miller); 4±1 "chunks" not raw items
- **LLM:** Cognitive chunking (PIC), incremental memory, compressed memory slots
- **2024 methods:** ICAE achieves 4× compression; Cognitive Chunking shows 29.8% F1, 40.7% EM improvement at 64× compression; IMDC 1.45× faster, 23.3% GPU memory reduction

---

## 6. Recent Papers: Human Cognition ↔ LLM Architecture (2024–2026)

### 6.1 "Scaling and context steer LLMs along the same computational path as the human brain" (Raugel et al., NeurIPS 2025)

**Key findings:**
- LLM layers and brain generate representations in **similar temporal order**: early layers ↔ early brain responses, deeper layers ↔ later responses
- **Temporal score r = 0.99** (p < 1e-06) between layer depth and MEG response timing
- Holds across transformers and recurrent architectures (Mamba, RecurrentGemma)
- **Model size:** Alignment increases with size — from r = 0.44 (14M params) to r = 0.96 (12B); correlation with log model size r = 0.87
- **Context size:** Alignment increases with context — from r = 0.19 (no context) to r = 0.93 (1000 words); r = 0.81 with context length
- Unpretrained models show no alignment
- SSMs (recurrent hidden state) may be more brain-like than transformers for long context

### 6.2 "Cognitive Mirrors: Exploring the Diverse Functional Roles of Attention Heads in LLM Reasoning" (Ma et al., 2025)

**Key findings:**
- Attention heads exhibit **functional specialization** analogous to brain regions
- Human: frontal lobe (retrieval), language areas (semantic), parietal/PFC (reasoning)
- LLM: Sparse "cognitive heads" — <7% of heads have importance >0.001 across 8 functions
- **Hierarchical structure:** Lower-level heads (retrieval, recall) modulate higher-level (inference, decision); masking retrieval heads causes 100% drop in downstream reasoning
- **Intervention:** Masking cognitive heads → large accuracy drops; masking random heads → marginal degradation
- Functional clustering mirrors brain (reasoning/inference/decision group together; math distinct)

### 6.3 "Incremental accumulation of linguistic context in artificial and biological neural networks" (Nature Communications, Jan 2025)

**Key findings:**
- **Critical difference:** LLMs process large text windows in parallel; brain integrates context **incrementally**
- LLMs predict brain activity well only with **short context windows** (few dozen words)
- **Incremental-context model:** Short-term input + dynamically updated summary of prior context → better prediction of neural activity in higher-order regions
- 219 participants, fMRI during spoken narratives
- Brain's hierarchical temporal processing enables flexible integration over extended periods

### 6.4 "Lost in the Middle: An Emergent Property from Information Retrieval Demands in LLMs" (2025)

- Proposes U-shaped pattern is **emergent adaptation** to pre-training retrieval demands
- Some tasks: uniform recall; others: prioritize recent
- Intrinsic U-shaped attention patterns; attention sinks; autoregressive properties contribute

---

## 7. Summary: Parallels Table

| Human Cognition | LLM Equivalent | Evidence |
|-----------------|----------------|----------|
| **4±1 chunks** (Cowan) | Effective context utilization | ~4–7 meaningful items before degradation |
| **WM overload → reasoning degrades** | Context length → quality degradation | Fronto-limbic disruption ↔ lost-in-middle |
| **Attention = fixed budget** | Softmax sums to 1 | Normalization model; divisive inhibition |
| **Spotlight: wider = less intensity** | More tokens = diluted attention | Attention distributed across positions |
| **Split-attention harms** | Extraneous context harms | Irrelevant tokens consume capacity |
| **PFC bottleneck** | Context window limit | Both prioritize, both overload |
| **Stress reduces PFC** | ? | No direct LLM analog studied |
| **Primacy/recency** | Lost in the middle | U-shaped curves; similar position effects |
| **Chunking** | Context compression | PIC, ICAE, IMDC methods |
| **DMN when PFC overloaded** | ? | Mind-wandering ↔ model degradation? |

---

## 8. References (Key Papers)

- Cowan, N. — Working memory capacity 4±1
- Baddeley & Hitch (1974) — Multi-component model
- Sweller — Cognitive load theory, split-attention
- Broadbent — Filter theory
- Kahneman (1973) — Attention and Effort
- Reynolds & Heeger (2009) — Normalization model of attention
- Liu et al. (2023) — Lost in the Middle
- Raugel et al. (2025) — Scaling and context steer LLMs along brain path
- Ma et al. (2025) — Cognitive Mirrors
- Nature Communications (2025) — Incremental accumulation of linguistic context
- Murdock (1962) — Serial position effect
- Glanzer & Cunitz (1966) — Primacy-recency

---

*Document generated from web search and paper retrieval. Verify specific claims against primary sources.*
