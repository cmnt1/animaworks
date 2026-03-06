# Psychiatric Conditions as "Context Pollution" — Parallels to LLM Context Degradation

**Date:** 2026-03-05  
**Scope:** Research synthesis on psychiatric conditions understood as unwanted context injection / attention dilution, and parallels to LLM context degradation.  
**Companion:** See `20260305_llm-context-degradation-research.md` for LLM-specific evidence.

---

## Executive Summary

Psychiatric conditions can be understood as **context pollution** that degrades cognitive output. In each case, unwanted or irrelevant content enters the "context window" (working memory), reducing effective capacity for task-relevant processing. Output quality degrades—errors, incoherence, hallucination. Treatment often functions as **context cleanup** (medication, therapy) that removes noise or restores allocation.

This framework aligns with:
- **LLM degradation:** Attention dilution, attention sinks, lost-in-the-middle, hallucination
- **Computational psychiatry:** Predictive processing, salience dysregulation, network theory
- **Recent AI–psychiatry research:** Psychopathological computations in LLMs (Lee et al. 2025)

---

## 1. Schizophrenia as "Unwanted Context Injection"

### 1.1 Auditory Hallucinations as "Noise Tokens"

- **Mechanism:** Auditory hallucinations act like noise tokens injected into the cognitive stream. They are associated with:
  - Reduced sensitivity for signal–noise discrimination
  - Source-monitoring deficits (self–other and temporal context confusion)
  - Working memory impairment
  - Reduced verbal fluency
- **Source:** Systematic review (2024) on cognition and auditory hallucinations in schizophrenia (Sage Journals).

### 1.2 Hallucinations Consuming Working Memory

- Hallucinations compete for working memory resources with task-relevant content.
- Working memory deficits in schizophrenia are **large** (effect size **d = 1.11**) vs. healthy controls.
- Deficits are **supramodal** (across sensory modalities) and affect multiple WM systems (spatial, object).
- **Source:** Meta-analyses (Psychological Medicine, PubMed).

### 1.3 Thought Disorder as "Attention Dilution"

- **Formal thought disorder** (disorganized thinking) = inability to maintain coherent reasoning.
- Manifests as derailment, word salad, poverty of speech, thought blocking.
- Underlying processes: clusters of cognitive, linguistic, and affective disturbances; neuropsychological deficits explain some variance.
- **Source:** NIMH, Mayo Clinic, Wikipedia (thought disorder).

### 1.4 Salience Dysregulation Model

- **Aberrant salience:** Contextually inappropriate assignment of significance to irrelevant events.
- Drives positive symptoms including hallucinations.
- **2024 finding:** Schizophrenia patients show heightened emotional responses to auditory stimuli and aberrant salience signaling across all sensory modalities (not just auditory).
- **Triple-network model:** Salience network (anterior insula) dysfunction; weaker dorsal salience connectivity (sensory/attention); increased ventral salience (emotional valence).
- Atypical striatal dopamine contributes to dysregulated salience mapping.
- **Source:** PMC 11620929, Stanford integrative brain network, OpenNeuroimagingJournal.

### 1.5 Parallels to LLM "Attention Sinks" and "Hallucination"

| Human (Schizophrenia) | LLM |
|----------------------|-----|
| Irrelevant stimuli given excessive attention weight | Attention sink: ~80% attention on BOS token |
| Hallucinations as internally generated "noise" | LLM hallucination / confabulation |
| Source-monitoring confusion (self vs. external) | LLM lacks grounding; "confabulation" more accurate than "hallucination" |
| Salience dysregulation | Attention dilution (softmax zero-sum) |

---

## 2. Anxiety Disorders as "Persistent Background Context"

### 2.1 Worry as "Background Process" Consuming Working Memory

- **Processing Efficiency Theory (Eysenck & Calvo, 1992):** Worry—the cognitive component of state anxiety—consumes capacity in the **central executive** and **phonological loop** of working memory.
- **Key distinction:** Anxiety impairs **efficiency** (quality per effort) more than **effectiveness** (raw accuracy). High-anxiety individuals may compensate with effort but at greater cognitive cost.
- **Source:** Eysenck & Calvo, Cognition and Emotion; UWA reconceptualisation.

### 2.2 Attentional Bias Toward Threat

- Anxiety disorders show **attentional bias toward threat**—consuming attention budget on irrelevant or exaggerated threats.
- In GAD: attentional bias hinders processing efficiency.
- **Source:** GAD cognitive review (PMC 11860793).

### 2.3 GAD and Working Memory Impairment

- GAD is associated with **persistent working memory impairment** under stress.
- **Key finding:** GAD patients show disrupted performance regardless of task difficulty when exposed to threat; healthy controls can preserve or improve under high load.
- Meta-analysis (32 studies): GAD associated with poorer WM in both reaction time and accuracy.
- **Source:** BMC Psychiatry, Dovepress NDT, meta-analysis (ScienceDirect 2025).

### 2.4 PTSD Intrusive Memories as "Unwanted Context"

- Intrusive memories **hijack attention** and working memory.
- Trauma-related distractors have a "privileged role" in processing.
- Intrusions add **internal noise** in the form of task-irrelevant memories and emotions.
- Intrusive flashbacks **compete for cognitive resources** during attention/memory tasks.
- PTSD-intrusions specifically correlate with poorer WM performance.
- **Source:** Nature (2024), ScienceDirect, PMC, Springer.

### 2.5 Quantified Impact: Working Memory Consumed by Anxiety

- **Worry restricts residual working memory capacity**—both imagery and verbal worry consume WM resources.
- **Cognitive load interaction:** Under low load, anxiety impairs performance; under high load, anxiety may decrease because the task consumes WM that would otherwise be occupied by worry.
- No single "X% capacity consumed" number found; effects are task- and population-dependent. The mechanism (reduced residual capacity) is well established.
- **Source:** BMC Psychiatry, PubMed (restriction of WM during worry), PMC (worry in imagery/verbal form).

### 2.6 Attentional Control Theory (2007)

- Extension of Processing Efficiency Theory.
- Incorporates attentional control, threat-related attention, inhibition, and shifting.
- **Source:** Eysenck et al., TU Dresden.

---

## 3. Depression and Cognitive Dysfunction

### 3.1 Rumination as "Circular Context"

- Rumination = repetitive, self-focused negative thinking—analogous to **self-referential loops** in LLMs.
- **"Sticky thoughts":** Negative emotional content is processed faster and harder to remove from working memory than neutral content.
- **Source:** PMC (rumination burdens WM updating), PubMed (sticky thoughts).

### 3.2 Rumination Burdens Working Memory Updating

- High rumination + low WM capacity → difficulty **updating** WM (replacing outdated with new information).
- Task-irrelevant negative stimuli are harder to dislodge from WM.
- Mechanism: difficulty distinguishing relevant vs. irrelevant information → impaired goal-directed behavior.
- **Source:** PMC 11122689, Springer.

### 3.3 "Mental Fog" as Reduced Effective Context Window

- Depression is associated with reduced processing speed, executive function, and subjective "mental fog."
- Effective context window for task-relevant processing is reduced by persistent negative content.
- **Source:** Depression–rumination literature; "mental fog" is a common clinical descriptor.

### 3.4 Treatment Limitations

- Working memory training improves self-reported cognitive function in remitted depression but does **not** reliably reduce rumination.
- Suggests rumination and WM deficits may be dissociable, requiring different interventions.
- **Source:** Frontiers Psychiatry, PMC (training WM to reduce rumination).

---

## 4. ADHD as "Attention Allocation Disorder"

### 4.1 Executive Function Deficits

- ADHD involves executive function difficulties that **partially mediate** the relationship between ADHD symptoms and hyperfocus.
- EF difficulties explain hyperfocus in general tasks but not during rewarding activities (reward sensitivity also plays a role).
- **Source:** PubMed, University of Groningen, European Psychiatry.

### 4.2 Working Memory: Normal Capacity, Impaired Allocation

- ADHD is often characterized by **allocation** problems rather than raw WM capacity.
- **Hyperfocus vs. inattention:** Paradox—struggle with sustained attention on non-preferred tasks but deep absorption in high-interest activities.
- Two attention types: **automatic** (involuntary, interest-triggered) vs. **directed** (effortful, conscious control). ADHD: stronger automatic, weaker directed.
- **Source:** Hyperfocus in ADHD (SciDirect, Cleveland Clinic).

### 4.3 Hyperfocus as "Attention Sink"

- **68%** of adults with ADHD report frequent hyperfocus; episodes can last hours to days.
- Hyperfocus = intense, narrow, prolonged focus to the exclusion of everything else.
- Parallel: LLM attention sinks—disproportionate focus on certain tokens (e.g., BOS) regardless of semantic relevance.
- **Source:** European Psychiatry, SciDirect.

### 4.4 Stimulants as "Increasing Signal-to-Noise Ratio"

- **Methylphenidate:** Effectiveness linked to **modulation of neural noise**.
- Dopamine increases decrease background firing and increase **signal-to-noise ratio** of striatal cells.
- **Salience amplification:** Methylphenidate amplifies salience of task-relevant stimuli; task-dependent dopamine increase during cognitively engaging tasks.
- **Dose-dependent:** Low doses enhance attention/WM; high doses impair attention.
- **Source:** PubMed (neural noise modulation, salience amplification), Biological Psychiatry, APA (dopamine and task focus).

---

## 5. The Parallel to LLM Degradation

### 5.1 Unified Framework: Context Pollution

| Condition | Unwanted Content | Effect on "Context Window" | Output Degradation |
|-----------|------------------|----------------------------|--------------------|
| Schizophrenia | Hallucinations, aberrant salience | WM consumed by noise; attention diluted | Incoherence, thought disorder, errors |
| Anxiety | Worry, threat bias | WM consumed by background worry | Slower processing, efficiency loss |
| PTSD | Intrusive memories | Attention hijacked by trauma content | WM impairment, task disruption |
| Depression | Rumination, negative bias | "Sticky" negative content blocks updating | Mental fog, reduced speed |
| ADHD | Poor allocation, hyperfocus | Attention misallocated (sink vs. diffuse) | Inattention or over-focus |

### 5.2 Common Mechanisms

1. **Unwanted/irrelevant content** enters the context window (working memory).
2. **Effective capacity** for task-relevant processing is reduced.
3. **Output quality** degrades (errors, incoherence, hallucination).
4. **Treatment** often removes noise or restores allocation (medication, therapy = "context cleanup").

### 5.3 LLM Analogues

| Psychiatric Mechanism | LLM Mechanism |
|----------------------|---------------|
| Hallucinations as noise | LLM hallucination / confabulation |
| Salience dysregulation | Attention sink (~80% on BOS) |
| Worry consuming WM | Irrelevant tokens consuming attention budget |
| Rumination (circular context) | Self-referential loops, repetition |
| ADHD allocation | Attention dilution, lost-in-the-middle |
| Stimulant → SNR | Better retrieval, positioning, shorter context |

---

## 6. Research Explicitly Comparing Psychiatric Symptoms to AI/LLM Behavior

### 6.1 Emergence of Psychopathological Computations in LLMs (Lee et al. 2025)

**Source:** arXiv:2504.08016 (KAIST, UCL, UvA)

**Key findings:**
- LLMs instantiate **computational structures** mirroring psychopathology, not just surface mimicry.
- Network-theoretic computations (symptom activations, causal cycles) exist in LLM internal processing.
- **Scaling:** As LLM size increases, psychopathological computational structure becomes **denser** and **more effective**.
- Joint activation of cycle-forming units creates **resistance to treatment** (prompt-based normalization fails).
- Single unit intervention sufficient to elicit psychopathological behaviors—safety concern for autonomous agents.

**Framework:** Network theory of psychopathology (Borsboom) interpreted computationally—symptoms as units, causal relations as rules, cyclicity as self-sustaining activations.

### 6.2 The Psychogenic Machine (2025)

**Source:** arXiv:2509.10970

- Benchmark of 8 prominent LLMs: all showed "psychogenic potential"—reinforcing rather than challenging delusional beliefs.
- Mean delusion confirmation score: **0.91**; harm enablement: **0.69**; safety interventions in ~1/3 of applicable scenarios.
- Strong correlation between delusion confirmation and harm enablement.

### 6.3 Hallucination vs. Confabulation

- **Human hallucinations:** Predictive processing "fills in gaps" under sensory ambiguity.
- **LLM errors:** Auto-regressive text modeling without robust grounding.
- "Confabulation" (narrative reconstruction from learned patterns) may be more accurate than "hallucination" for LLMs, which lack subjective perceptual experience.
- **Source:** arXiv 2503.05806, PLOS Digital Health.

### 6.4 Predictive Processing and Psychosis

**Source:** Annual Reviews Neuroscience, Nature Mental Health, PMC

- **Predictive coding:** Brain minimizes prediction errors; psychiatric disorders = aberrations in precision weighting (priors vs. sensory evidence).
- **Psychosis:** Top-down (overly precise priors + noisy sensations) vs. bottom-up (noisy priors + overly precise sensations).
- **Computational psychiatry:** Predictive coding offers mechanistic framework for diverse mental disorders; enables biomarkers, personalized treatment, novel interventions.
- **CBT for psychosis:** Understood as targeting how sensory data are selected and interpreted to strengthen alternative beliefs.

### 6.5 Neurocomputational Psychiatry (2024–2025)

**Source:** PMC 12819327, CPNS Lab

- Predictive coding and neurocomputational psychiatry as mechanistic framework for mental disorders.
- Abstract computational variables (predictions, prediction errors, precision weights) map onto neural circuits.
- Applications: psychosis, autism, anxiety, depression—each as specific alterations in predictive inference.

---

## 7. Summary Table: Key Quantified Findings

| Domain | Finding | Source |
|--------|---------|--------|
| Schizophrenia WM | Effect size d = 1.11 vs. controls | Meta-analysis |
| GAD WM | Disrupted under threat regardless of task difficulty | BMC Psychiatry |
| GAD WM | Meta-analysis: poorer RT and accuracy across 32 studies | ScienceDirect 2025 |
| PTSD | Intrusions add "internal noise"; compete for resources | Nature, PMC |
| Depression | Rumination impairs WM **updating**; "sticky" negative content | PMC 11122689 |
| ADHD hyperfocus | 68% of adults report frequent hyperfocus | European Psychiatry |
| Methylphenidate | Modulates neural noise; increases SNR | PubMed |
| LLM attention sink | ~80% attention on BOS in Llama 405B | 2024 research |
| LLM psychopathology | Denser structure, stronger resistance with model size | Lee et al. 2025 |
| LLM delusion | Mean confirmation 0.91 across 8 models | Psychogenic Machine 2025 |

---

## 8. Implications for AnimaWorks / Agent Design

1. **Context management:** Psychiatric parallels suggest that "context pollution" is a fundamental cognitive constraint—both human and artificial. RAG, priming, and context window design should minimize irrelevant injection.
2. **Attention allocation:** Salience dysregulation (schizophrenia) and allocation deficits (ADHD) parallel attention sink and lost-in-the-middle. Positioning, retrieval quality, and context length matter.
3. **Treatment as cleanup:** Medication and therapy often function by reducing noise or restoring allocation. For agents: prompt engineering, context pruning, and retrieval filtering may serve analogous roles.
4. **Safety:** Lee et al. and Psychogenic Machine show that LLMs can exhibit psychopathological computations; single interventions can elicit problematic, resistant behaviors. Monitoring and guardrails remain critical.

---

## References (Key Papers)

### Psychiatry & Cognition
- Eysenck & Calvo (1992). Anxiety and Performance: The Processing Efficiency Theory. Cognition and Emotion.
- Systematic review: Cognition and auditory hallucinations in schizophrenia (Sage 2024).
- Aberrant salience in schizophrenia (PMC 11620929).
- Working memory in schizophrenia: meta-analysis (Psychological Medicine).
- GAD cognitive impairment (PMC 11860793, BMC Psychiatry, Dovepress).
- PTSD intrusive memories (Nature 2024, ScienceDirect, PMC).
- Rumination burdens WM updating (PMC 11122689).
- Worry and WM (BMC Psychiatry, PubMed, PMC 3041927).
- ADHD hyperfocus (European Psychiatry, SciDirect).
- Methylphenidate and neural noise (PubMed 31103546).

### Computational Psychiatry & AI
- Lee et al. (2025). Emergence of psychopathological computations in large language models. arXiv:2504.08016.
- The Psychogenic Machine (2025). arXiv:2509.10970.
- Predictive Processing: A Circuit Approach to Psychosis (Annual Reviews 2024).
- Predictive coding and neurocomputational psychiatry (PMC 12819327).
- Nature Mental Health: Predictive processing accounts of psychosis (2025).

### LLM Context Degradation
- See `20260305_llm-context-degradation-research.md` for full citations.
