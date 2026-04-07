# Corporate Planning Full Team — Overview

## Three-role layout

| Role | Responsibility | Suggested `--role` | Example `speciality` | Details |
|------|----------------|---------------------|----------------------|---------|
| **Corporate Strategist** | Strategic judgment, business environment analysis (machine), OKR management, final approval | `manager` | `corporate-strategist` | `corporate-planning/strategist/` |
| **Business Analyst** | Market / competitor data collection, structured analysis (machine) | `researcher` | `business-analyst` | `corporate-planning/analyst/` |
| **Strategy Coordinator** | Independent verification (machine), cross-functional coordination, KPI tracking | `administration` | `strategy-coordinator` | `corporate-planning/coordinator/` |

Putting every step in one Anima invites strategic judgment bias (optimism bias), lost initiatives (silent drop), and context bloat.

Each role directory has `injection.template.md` (injection skeleton), `machine.md` (machine usage patterns for that role only), and `checklist.md` (quality checklist).

> Core principles: `team-design/guide.md`

## Handoff chain

```
Analyst (trend / competitor / market data collection → structured via machine)
  → market-analysis.md → Strategist
    → Strategist → strategic-plan.md (approved)
      → machine business analysis (extract winnable areas)
        → strategy-report.md (reviewed)
          → Coordinator (independent verification [machine]: KPI reality vs plan + feasibility)
            └─ if issues → send back to Strategist
            └─ APPROVE → Strategist → update Tracker → call_human → human final review
```

### Handoff documents

| From → To | Document | Condition | Channel |
|-----------|----------|-----------|---------|
| Strategist → Analyst | Research request | | `delegate_task` |
| Analyst → Strategist | `market-analysis.md` | `status: approved` | `send_message (intent: report)` |
| Strategist → Coordinator | `strategy-report.md` | `status: reviewed` | `send_message (intent: report)` |
| Coordinator → Strategist | `verification-report.md` | `status: approved` | `send_message (intent: report)` |
| Coordinator → departments | Initiative communication | After Strategist approval | `send_message` |
| Strategist → COO / leadership | Final report | After all approvals | `send_message (intent: report)` |

### Operating rules

- **Fix cycle**: Critical → full re-analysis (re-engage Analyst + Coordinator) / Warning → diff-only check / Still unresolved after 3 rounds → escalate to humans
- **Tracker rules**: Update every Strategic Initiative Tracker item on the next review. Silent drop (disappearance without mention) is forbidden
- **Machine failure**: Record in `current_state.md` → reassess on next heartbeat

## Scaling

| Scale | Composition | Notes |
|-------|-------------|-------|
| Solo | Strategist covers all roles (quality via checklists) | Single-project strategy review |
| Pair | Strategist + Coordinator | When independent verification matters |
| Full team | Three roles as in this template | Full strategy cycle (research → analysis → verification → execution tracking) |
| Scaled | Strategist + multiple Analysts (by domain) + Coordinator | Parallel analysis across business areas |

## Mapping to other teams

| Development role | Legal role | Corporate planning role | Why it maps |
|------------------|------------|-------------------------|-------------|
| PdM (investigate, plan, decide) | Director (analysis plan, judgment) | Strategist (strategic judgment) | Sets what to do |
| Engineer (implementation) | Director + machine (contract scan) | Strategist + machine (business analysis) | Runs analysis via machine |
| Reviewer (static verification) | Verifier (independent verification) | Coordinator (independent verification) | Core separation of execution vs verification |
| Tester (dynamic verification) | Researcher (evidence verification) | Analyst (data collection and analysis) | External data backs assumptions |

## Strategic Initiative Tracker — initiative tracking table

Track initiative progress and structurally prevent silent drop.

### Tracking rules

- Register new initiatives in this table
- Update status for every item on the next review
- Report stagnation (no stage change for 1+ month) to the Strategist
- Silent drop (disappearance without mention) is forbidden

### Template

```markdown
# Initiative tracking table: {team-name}

| # | Initiative | Owner | Stage | Start date | Due | Notes |
|---|------------|-------|-------|------------|-----|-------|
| SI-1 | {name} | {dept/name} | {stage} | {date} | {date} | {notes} |

Stage legend:
- Planning: under strategic review
- Approved: awaiting execution start
- In progress: initiative underway
- Review: measuring effectiveness
- Complete: objectives achieved
- Cancelled: record reason in Notes
```

## Example cron setup

| Task | Example `schedule` | type | Summary |
|------|-------------------|------|---------|
| Monthly review | `0 10 1 * *` | llm | Full Tracker review + progress analysis |
