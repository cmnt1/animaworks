# Customer Success Full Team — Overview

## Two-role layout

| Role | Responsibility | Suggested `--role` | Example `speciality` | Details |
|------|----------------|---------------------|----------------------|---------|
| **CS Lead** | Customer strategy, onboarding planning [machine], health analysis [machine], retention actions [machine], VoC aggregation [machine], escalation | `manager` | `cs-lead` | `customer-success/cs-lead/` |
| **Support** | Ticket handling, FAQ management, onboarding execution, first response, VoC material collection | `administration` | `cs-support` | `customer-success/support/` |

Putting every step in one Anima invites context competition between customer analysis and first response, self-verification blind spots in health scoring, and priority conflicts between VoC aggregation and ticket handling.

Each role directory has `injection.template.md` (injection skeleton), `machine.md` (machine usage patterns for CS Lead only), and `checklist.md` (quality checklist).

> Core principles: `team-design/guide.md`

## Two execution modes

### Onboarding mode (plan-driven)

```
Sales Director → cs-handoff.md (draft)
  → CS Lead → Phase A: machine creates onboarding plan → CS Lead verifies
    → onboarding-plan.md (approved) → delegate_task → Support
      → Support: executes onboarding → reports completion to CS Lead
```

When a deal closes, the sales team sends `cs-handoff.md`. CS Lead uses machine to analyze the customer and create an onboarding plan, then delegates execution to Support.

### Maintenance mode (periodic patrol)

```
CS Lead → Phase B: Health Tracker periodic analysis (heartbeat/cron)
  → Yellow/Red detected → Phase C: machine drafts retention action → CS Lead verifies → customer outreach
  → Critical → escalate upward
  → All Green → monitor

CS Lead → Phase D: VoC aggregation (cron: periodic)
  → voc-report.md → feedback to dev team via COO

Support → ticket handling + FAQ management (cron: daily)
  → issue detected → report to CS Lead
  → non-CS inquiry (sales etc.) → escalate to relevant team
```

## Handoff chain

```
Sales Director → cs-handoff.md (draft)
  → CS Lead → Phase A: machine analysis & planning → CS Lead verifies
    → onboarding-plan.md (approved) → delegate_task → Support
      → Support: onboarding execution → report completion to CS Lead
        → CS Lead: register in Health Tracker → enter Maintenance mode

CS Lead → Phase B: Health Tracker analysis (heartbeat/cron)
  → Yellow/Red → Phase C: machine retention action → CS Lead verifies → execute
  → Phase D: VoC aggregation → voc-report.md → COO

Support → autonomous patrol (cron)
  → ticket handling → report to CS Lead
```

### Handoff documents

| From → To | Document | Condition | Channel |
|-----------|----------|-----------|---------|
| Sales Director → CS Lead | `cs-handoff.md` | On deal close | `send_message (intent: report)` |
| CS Lead → Support | `onboarding-plan.md` | `status: approved` | `delegate_task` |
| Support → CS Lead | Ticket report | On issue detection | `send_message (intent: report)` |
| CS Lead → COO | `voc-report.md` | Periodic (cron) | `send_message (intent: report)` |
| CS Lead → upper management | Escalation | Critical health score | `send_message (intent: report)` |

### Operating rules

- **Fix cycle**: Critical → immediate intervention + upward escalation / Warning → draft retention action / Still unresolved after 3 rounds → escalate to humans
- **Customer Health Score Tracker**: Track customer health scores. Silent drop forbidden
- **3-layer escalation**: Support → CS Lead → upper management (COO, etc.)
- **Machine failure**: Record in `current_state.md` → reassess on next heartbeat

## Scaling

| Scale | Composition | Notes |
|-------|-------------|-------|
| Solo | CS Lead covers all roles (quality via checklists) | Few customers, routine handling |
| Pair | Two roles as in this template | Standard operation |
| Scaled | CS Lead + multiple Supports (by segment, etc.) | Large customer base |

## Mapping to other teams

| Development role | Legal role | Sales & MKT role | CS role | Why it maps |
|------------------|------------|------------------|---------|-------------|
| PdM (plan, decide) | Director (analysis plan, judgment) | Director (strategy, sales execution) | CS Lead (customer strategy, analysis) | Sets what to do |
| Engineer (implement) | Director + machine | Director + machine | CS Lead + machine | Machine executes analysis & production |
| Reviewer (static verification) | Verifier (independent verification) | {compliance reviewer name} (compliance) | — | CS needs no independent verification role (quality ensured via KPIs) |
| Tester (dynamic verification) | Researcher (evidence verification) | Researcher (market research) | Support (first response, information gathering) | Collects information at the customer touchpoint |

## KPI system (4 metrics)

| Metric | Summary | Positioning in AI CS |
|--------|---------|----------------------|
| **CSAT** | Customer Satisfaction Score | Survey-based. Direct indicator of service quality |
| **NPS** | Net Promoter Score | Recommendation intent. Long-term relationship indicator |
| **Churn rate** | Cancellation rate | Health Tracker Yellow/Red detects early signals |
| **Onboarding completion rate** | New customer initial setup completion | Tracked from cs-handoff.md receipt to onboarding completion |

Time-based KPIs (first response time, resolution time, etc.) are excluded because AI agent CS provides near-instant responses (≈ 0).

## Customer Health Score Tracker — health tracking table

Tracks customer health scores. When Yellow/Red is detected, retention actions are drafted in Phase C.

### Tracking rules

- Register new customers in this table after onboarding completion
- Update all items' statuses on each Heartbeat / review
- Draft retention actions in Phase C for Yellow/Red customers
- Silent drop (disappearance without mention) is forbidden

### Template

```markdown
# Customer health score tracking table: {team-name}

| # | Company | Health score | Last contact | Next action | Notes |
|---|---------|-------------|--------------|-------------|-------|
| CS-1 | {name} | {Green/Yellow/Red} | {date} | {action} | {notes} |

Health score legend:
- Green: Healthy (active usage, good CSAT, few inquiries)
- Yellow: Watch (declining usage, unanswered surveys, rising inquiries)
- Red: At risk (usage stopped, CSAT decline, churn signals)
```
