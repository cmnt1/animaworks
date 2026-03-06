# LLM Scaling: Physical, Hardware, and Energy Constraints (2023–2026+)

**Research Date:** 2026-03-05  
**Scope:** Training compute, hardware, energy, data, and economic constraints on frontier LLM scaling.

---

## 1. Training Compute Trajectory

### Historical Baseline

| Model | Training Compute | Release |
|-------|------------------|---------|
| GPT-3 | ~3.14×10²³ FLOPs | 2020 |
| GPT-4 | ~2×10²⁵ FLOPs (first 10²⁵-scale model) | Mar 2023 |
| Frontier models (30+ at GPT-4 scale) | ≥10²⁵ FLOPs | By Jun 2025 |

**Growth rate:** Frontier open-weight model training compute grows ~4.7× per year (90% CI: 3.6×–6.1×). Some estimates put overall frontier scaling at ~5× per year.

### Current Frontier (2025–2026)

- **Epoch AI:** First open-weight model above 10²⁶ FLOPs projected by **November 2025** (90% CI: Aug 2025 – Nov 2026).
- **Meta Llama 4:** Training on clusters >100k H100s; likely to exceed 10²⁶ FLOPs; planned release 2025.
- **GPT-5:** Used *less* training compute than GPT-4.5, reflecting a shift to post-training scaling (reasoning, fine-tuning) rather than raw pre-training.
- **GPT-6:** Expected to return to higher training compute once post-training methods mature.

### Mega-Scale Clusters

| Project | Scale | Timeline |
|---------|------|----------|
| Microsoft–OpenAI Stargate | $100B+ | Target ~2028 |
| Broader Stargate (OpenAI, SoftBank, Oracle, Microsoft, Nvidia) | $500B over 4 years | 2025+ |
| Stargate capacity | 10 GW total, >5 GW under development | Oracle +4.5 GW announced Jul 2025 |
| Chips | >2M chips | — |

**Cost context:** Training at 10²⁵+ FLOPs costs tens of millions of dollars with current hardware.

---

## 2. Hardware Scaling

### NVIDIA Roadmap (2025–2028)

| Generation | Product | Key Specs | Timeline |
|------------|---------|-----------|----------|
| Hopper | H100/H200 | 80GB HBM3, 3.35 TB/s | Current |
| Blackwell | B100/B200 | 208B transistors, 192GB HBM3e, 8 TB/s, ~2.5× training, ~4× inference vs H100 | Shipping 2025 |
| Blackwell Ultra | — | Higher FP4 performance | H2 2025 |
| Rubin | NVL144 | 50 PF FP4, 288GB HBM4, NVLink 6 (260 TB/s) | H2 2026 |
| Rubin Ultra | NVL576 | 15 exaflops FP4, 5 exaflops FP8, HBM4e, 4.6 PB/s | H2 2027 |
| Feynman | — | Next-gen HBM | 2028 |

**Cadence:** NVIDIA moved to a one-year release cycle instead of two years.

### Memory Bandwidth as Bottleneck

- **HBM3e (H100):** 3.35 TB/s, 1024-bit interface.
- **HBM4 (2025+):** 2048-bit interface, ~2.8 TB/s per stack, 16-high stacks.
- **Bandwidth wall:** For transformers, memory access can be as low as ~1 FLOP/byte (batch-size-1 inference), far below the ~591 FLOPS/byte inflection point on H100. Memory bandwidth is now the main constraint, not compute.
- **HBM supply:** Contract prices up ~30% in Q4 2025; 2025 supply effectively sold out by mid-2024.

### Chip Fabrication

| Node | Status | Notes |
|------|--------|-------|
| 3nm | Production | TSMC ~90% yield; Samsung ~50% |
| 2nm (N2) | Mass production 2025 | TSMC GAA; 1.15× density, ~15% perf, ~35% efficiency vs 3nm |
| 1.4nm | ~2027–2028 | Samsung path |
| 18Å (~1.8nm) | 2026 | Intel |

**Moore’s Law:** Scaling continues, but “2nm” is largely marketing; physical gate pitch ~45nm.

### Custom AI Chips

- **Google TPU:** v5e/v6 in production; strong alternative to NVIDIA for internal workloads.
- **Amazon Trainium:** Trainium2 for training; Inferentia for inference.
- **Microsoft Maia:** Custom silicon for Azure AI.
- **Cerebras:** Wafer-scale engine; different architecture, not yet mainstream for large-scale training.

---

## 3. Energy and Infrastructure Constraints

### Current Demand

| Metric | Value |
|--------|-------|
| Global data center electricity (2024) | ~415 TWh (~1.5% of global demand) |
| US data center share | ~45% of global |
| US data center consumption (2024) | ~183 TWh (~4% of US total) |
| Typical AI data center | ~100,000 households equivalent |
| Largest under construction | ~20× that |

### Projections

| Source | 2030 | 2035 |
|-------|------|------|
| IEA Base Case | ~945 TWh | ~1,200 TWh |
| IEA High Case | — | ~1,700 TWh |
| IEA Low Case | — | ~700 TWh |
| US data center share of electricity | — | Up to ~12% by 2028–2030 |

**Growth:** Data center demand has grown ~12%/year since 2017 vs ~3%/year for total electricity.

### Grid and Infrastructure

- **IEA:** ~20% of planned data center projects at risk of delays without grid upgrades.
- **Transmission:** New lines can take 4–8 years in advanced economies.
- **Components:** Lead times for transformers and cables roughly doubled in 3 years.
- **Cost:** ~$10M per megawatt for new data center construction; AI facilities ~10× more capital-intensive than aluminum smelters.

### Nuclear and Clean Energy

| Company | Deal | Capacity |
|---------|------|----------|
| Microsoft | Three Mile Island (Constellation) | 835 MW, online ~2028 |
| Google | Kairos Power SMRs | Multiple reactors through 2035 |
| Amazon | Talen Energy (Susquehanna) | Up to 1,920 MW to 2042 |
| Amazon | X-Energy SMR (Washington) | Up to 960 MW |

**IEA:** Nuclear adds ~175 TWh to meet data center demand; first SMRs around 2030.

### Water Cooling

- **Power density:** AI racks 30–120 kW vs historical ~15 kW; NVIDIA racks ~132 kW; next-gen systems targeting ~240 kW.
- **Water use:** Up to ~2.4 gallons per kWh; US AI could need ~720B gallons/year by 2028 (~18.5M households).
- **Liquid cooling:** Direct-to-chip liquid cooling dominant; ~25× cost savings, ~300× more water-efficient than air cooling.

---

## 4. Data Constraints

### The “Data Wall”

- **Epoch AI:** ~300T tokens of high-quality public text; exhaustion between **2026 and 2032** (80% confidence for 2026).
- **Goldman Sachs:** “We’ve already run out of data”; OpenAI’s former chief scientist: “peak data.”
- **Growth mismatch:** AI consumption of data outpaces new human-generated content (data doubles every 3–4 years).

### Synthetic Data

- **Current use:** Top LLMs trained on ~99% synthetic data.
- **SynthLLM (Microsoft):** Synthetic data can follow scaling laws; gains plateau around ~300B tokens.
- **Risks:** “AI slop,” contamination from recycled AI output.

### Model Collapse

- **Definition:** Performance degrades when training on successive generations of synthetic data.
- **Trigger:** As little as 1 in 1,000 synthetic examples can cause collapse.
- **Mitigation:**
  - **Accumulate** real + synthetic data (do not replace real with synthetic) → collapse avoided.
  - External verifiers (human or model) to filter synthetic data.
  - Mix synthetic data with exogenous signal.
- **Conclusion:** Collapse is not inevitable; it depends on workflow design and maintaining a link to real or verified data.

### Expansion Paths

- Multimodal data (vision, audio, video).
- Proprietary corporate data (trading, client interactions).
- Over-training on existing data (diminishing returns).

---

## 5. Economic Constraints

### Training Costs

| Model | Est. Cost |
|-------|-----------|
| GPT-4 | ~$79M |
| Gemini Ultra | ~$191M |
| Llama 3.1 405B | ~$60–170M |
| DeepSeek R1 | ~$294K (highly optimized) |
| GPT-5 class (2026) | $500M+ |
| Next frontier | $1B+ |

**Growth:** ~2–3× per year over the past eight years; ~2.4× annually in recent estimates.

**Breakdown:** GPU compute 60–70%; data prep ~15%; engineering ~12%; infrastructure ~8%.

### Investment vs Revenue (2025–2026)

| Metric | Value |
|--------|-------|
| AI CAPEX (2026) | ~$660–700B |
| Global cumulative AI investment | >$2.5T (44% YoY) |
| OpenAI ARR (end 2025) | ~$20B |
| Anthropic run rate (Jan 2026) | ~$9B |
| Enterprise AI revenue | ~$100B |
| Enterprise AI investment | ~$30–40B |
| MIT finding | ~95% of enterprise AI projects deliver zero ROI |

**Gap:** ~$400B+ infrastructure spend vs ~$100B enterprise AI revenue.

### Market Sentiment

- Stock declines on large CAPEX announcements (e.g., Amazon −5.5%, Google −7%).
- Meta seen as strong on AI monetization; NVIDIA as main beneficiary.
- Market shows both boom and bubble traits; ROI is the central question.

---

## 6. Conclusion: S-Curve Ceiling or Continued Growth?

### Arguments for an S-Curve Ceiling (2026+ Inflection)

1. **Diminishing returns:** GPT-5 and DeepSeek R1 show smaller gains vs prior generations despite higher cost.
2. **Data wall:** High-quality text data exhaustion by 2026–2032; synthetic data has limits and collapse risks.
3. **Energy:** Grid capacity, lead times, and siting constrain rapid expansion.
4. **Capital:** Training costs growing ~2.4×/year; only a few players can afford frontier scale.
5. **Memory bandwidth:** HBM supply and bandwidth are the binding constraint, not raw FLOPs.

### Arguments for Engineering Overcoming Limits

1. **Hardware roadmap:** Annual NVIDIA generations (Rubin, Feynman); HBM4/4e; 2nm and beyond.
2. **Post-training scaling:** GPT-5’s strategy shows alternatives to raw pre-training compute.
3. **Efficiency:** DeepSeek R1 shows large gains from optimization, not just scale.
4. **Software:** Forethought.org: software could add ~12 orders of magnitude before hitting physical limits.
5. **Capital deployment:** $500B+ Stargate-scale projects; hyperscalers committing to nuclear and clean energy.
6. **Data:** Accumulation strategies and verification can mitigate model collapse; multimodal and proprietary data expand the pool.

### Timeline Assessment

| Period | Outlook |
|--------|---------|
| 2025–2026 | Continued scaling; 10²⁶ FLOP open models; Stargate construction; grid and power as growing bottlenecks |
| 2027–2028 | Rubin Ultra, Feynman; nuclear/SMR capacity coming online; data wall increasingly binding |
| 2029–2032 | Likely inflection: data exhaustion, flattening scaling laws, and capital discipline may slow frontier growth |
| Beyond 2032 | Progress depends on algorithmic breakthroughs, new data sources, and sustained infrastructure investment |

### Verdict

Physical constraints do not impose a hard ceiling in the near term, but they are tightening. The system is moving from a regime where **compute** was the main limit to one where **data**, **memory bandwidth**, **energy**, and **capital** matter more. Engineering (hardware, algorithms, post-training methods, data strategies) can extend growth, but the rate of improvement is likely to slow. A gradual S-curve flattening by **2027–2030** is plausible, with a sharper inflection if data exhaustion, grid constraints, or economic pressure bite earlier.

---

## Sources

- Epoch AI (epoch.ai): Training compute, data exhaustion, model counts
- IEA: Energy and AI report (2024)
- NVIDIA: GTC 2025 roadmap, Next Platform, Tom’s Hardware
- EnosTech, ChipEstimate: HBM and memory bandwidth
- Reuters, The Verge, TechCrunch: Stargate, nuclear deals
- OpenReview, Stanford: Model collapse and synthetic data
- MIT, Articsledge: AI market and ROI
- Forethought.org: Physical limits of AI
