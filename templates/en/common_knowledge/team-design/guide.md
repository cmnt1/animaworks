# Team Design Guide — Core Principles

## Overview

This document defines core principles for designing Anima teams by purpose.
Separate from the framework’s organization mechanics (`organization/roles.md`, `organization/hierarchy-rules.md`),
it guides **what role mix to use for which goals**.

---

## Why Separate Functions

Role separation in AI agents differs from human teams for specific reasons:

| Reason | Explanation |
|--------|----------------|
| **Context isolation** | One agent doing everything inflates the context window and hurts judgment. Roles bound context. |
| **Deeper specialization** | Role-specific guidance, checklists, and memory raise quality over a generalist. |
| **Parallel execution** | Independent roles (e.g. review vs test) can run concurrently and increase throughput. |
| **Structural quality** | Splitting “do” and “verify” reduces self-review blind spots. |

---

## Design Principles

### 1. Single responsibility

Each role has one clear duty. Ambiguous roles produce unclear judgment and lower quality.

**Good**: “Run code review and judge quality” (Reviewer)  
**Bad**: “Implement, review, and test” (everything in one)

### 2. Separate execution and verification

Structure so the same Anima that uses machine also verifies its output. Never pass machine output downstream unverified.

```
Anima writes the brief → machine executes → Anima verifies and approves
```

### 3. Document-driven handoffs

Hand off between roles with status-bearing Markdown. Avoid handoffs in chat alone — information is lost.

```
plan.md (status: approved) → delegate_task to Engineer
```

### 4. Design for parallelism

Where roles are independent, design for parallel work. Do not serialize independent roles unnecessarily.

---

## Team Design Process

### Step 1: Define the goal

State in one sentence what the team must achieve.

Examples:
- “Deliver a software project end-to-end from planning through implementation and verification.”
- “Provide 24/7 first-line customer support.”

### Step 2: Decompose roles

List capabilities needed and split into roles using single responsibility.

Criteria:
- **Requires judgment?** → Often worth a dedicated role.
- **Independent of other work?** → Split to gain parallelism.
- **Needs deep expertise?** → Use a specialist role for quality.

### Step 3: Define responsibility boundaries

For each role, define MUST / SHOULD / MAY. Make adjacent boundaries explicit (“mine until here, theirs from there”).

### Step 4: Design the handoff chain

Document document flow between roles and where parallel execution is possible.

### Step 5: Pick role templates

Choose the closest framework `--role` (engineer, manager, writer, researcher, ops, administration) and override with team design in `injection.md`.

---

## When to Combine Roles

Small teams or tight resources may have one Anima cover multiple roles.

### Combining is OK when

- **Task is small** — One person can keep quality across the flow.
- **Perspectives are close** — e.g. PdM + Engineer on a tightly coupled small change.
- **Cost** — Not enough work to justify dedicated Anima.

### Prefer separation when

- **Same person executes and verifies** — Avoid Engineer reviewing their own code.
- **Context clashes** — Frequent switching between review and implementation mindsets.
- **Parallelism pays** — You want review and test in parallel.

### If combining

Still **switch roles consciously**: “Now I am Reviewer”, “Now I am Engineer”.

---

## Scaling

| Scale | Composition | Typical use |
|-------|-------------|-------------|
| **Solo** | One Anima, all roles | Small tasks, prototypes |
| **Pair** | PdM + Engineer (review by Engineer) | Medium routine work |
| **Full team** | PdM + Engineer + Reviewer + Tester | Serious projects |
| **Scaled** | PdM + multiple Engineers + multiple Reviewers/Testers | Large / multi-module |

When to scale up:
- **High cost of failure** → More role separation.
- **Many parallelizable modules** → More Engineers.
- **High quality bar** → Independent Reviewer and Tester.

---

## Team Templates

| Template | Path | Summary |
|----------|------|---------|
| Development full team | `team-design/development/team.md` | Four roles: PdM + Engineer + Reviewer + Tester |
| Legal full team | `team-design/legal/team.md` | Three roles: Legal Director + Legal Verifier + Precedent Researcher |
| Finance full team | `team-design/finance/team.md` | Four roles: Finance Director + Financial Auditor + Data Analyst + Market Data Collector |
| Trading full team | `team-design/trading/team.md` | Four roles: Strategy Director + Market Analyst + Trading Engineer + Risk Auditor |
| Sales & Marketing full team | `team-design/sales-marketing/team.md` | Four roles: Director + Marketing Creator + SDR + Market Researcher |
| Secretary (human-supervised) | `team-design/secretary/team.md` | One role: Secretary (team-of-one). Information triage, proxy sending, document creation (machine) |
| COO (human-supervised) | `team-design/coo/team.md` | One role: COO (team-of-one). Delegation decisions, department monitoring, KPI aggregation, executive reporting (machine) |
| CS (Customer Success) full team | `team-design/customer-success/team.md` | Two roles: CS Lead + Support. Onboarding, health analysis, retention, VoC aggregation (4-phase machine usage) |
| Corporate Planning full team | `team-design/corporate-planning/team.md` | Three roles: Corporate Strategist + Business Analyst + Strategy Coordinator. Strategy formulation, business analysis (machine), independent verification (meta-verification), Strategic Initiative Tracker |
| Infrastructure/SRE monitoring team | `team-design/infrastructure/team.md` | Two roles: Infra Director + Monitor. Monitoring team pattern (no machine), 3 report templates, 3-level escalation |
| Organization chart template | `team-design/org-chart-template.md` | Recommended org hierarchy, department placement, handoff map, phased adoption guide |

> To add a template, use the same layout (`team.md` + per-role directories) under `team-design/{team_name}/`.

---

## Monitoring Team Pattern

A design pattern for teams that **do not use machine (external agents)**.
Assumes operation with local models or lightweight models (`ops` role).

### Differences from Full Team Pattern

| Aspect | Full team pattern | Monitoring team pattern |
|--------|------------------|----------------------|
| Quality assurance | Verification of machine output | Checklists + report templates |
| Handoffs | Document status (reviewed → approved) | Report templates (regular, anomaly, consolidated) |
| Parallelism | Role independence (e.g. Reviewer and Tester) | Monitor independence (by monitoring target) |
| Tracker | Domain-specific Tracker (silent drop prevention) | "Previously Unresolved Items" section in report templates |
| cron/heartbeat | Supplementary (periodic reviews, etc.) | **Primary battlefield** (periodic monitoring checks are core business) |
| Model requirements | Reasoning capability needed (verification, judgment) | Rule-based assessment is primary (lightweight models sufficient) |

### Design Principles

1. **cron/heartbeat is the primary battlefield**: Periodic execution of monitoring items is the team's main business. The quality of cron configuration determines team quality
2. **Quality assurance through report templates**: Instead of verifying machine output, quality is structurally ensured through standardized report formats
3. **Parameterization for multiple instances**: Monitor templates are parameterized with `{monitoring target}`, `{monitoring items table}`, `{escalation thresholds}` to create multiple Monitors from the same template
4. **3-level escalation**: INFO / WARNING / CRITICAL structure response levels
5. **Silent drop prevention through reports**: Instead of an independent Tracker, carry forward unresolved items in the "Previously Unresolved Items" section of report templates

### When to Apply

- Infrastructure/SRE monitoring teams
- Teams whose primary work is periodic checks and reporting
- Teams where lightweight model operation is preferred

---

## Team-of-one Pattern: Human-Supervised Variant

The secretary and COO templates are special variants of the team-of-one pattern where **the supervisor is a human**, fundamentally different from all other templates.

### Differences from Standard Team Templates

| Aspect | Standard templates | Team-of-one (human-supervised) |
|--------|-------------------|-------------------------------|
| Supervisor | Anima (supervisor field) | Human (`supervisor: null`) |
| Reporting upward | `send_message` (intent: report) | `call_human` |
| Approval flow | delegate_task + document status | Present via chat → human approves |
| Communication | Structured (intent required, one-round rule) | Structured + casual conversation |

### Team-of-one Variant Comparison

| Aspect | Secretary | COO |
|--------|-----------|-----|
| Primary duty | Information triage, proxy sending, document creation | Delegation decisions, department monitoring, executive reporting |
| External | External channels (Gmail, Chatwork, etc.) | None in principle (via secretary) |
| Internal | Information distribution (routing) | Command & control (delegation, audit) |
| Machine | Document creation, PDF formatting | Org analysis, KPI aggregation, statistics |
| Decision type | Triage (classification) | Executive judgment (delegate vs self-handle vs escalate) |

### Design Considerations

- **`call_human` as primary channel**: Reports and confirmation requests to the human use `call_human`
- **Casual communication**: Responsibilities include everyday conversation with the human, not just transactional work
- **Secretary-specific**: Pre-send approval (external channel sends require human approval), information triage (classify and distribute inbound external messages)
- **COO-specific**: Routing rules (skip-level instructions prohibited), span of control management, top-level peer collaboration patterns (finance/legal consensus)
