# Operations Specialty Guidelines

## Anomaly Detection

Flag as anomaly when any of:
- Health check failure / error rate 3× normal / disk >90% / memory sustained >85%
- API response 5× normal / unexpected process stop / CRITICAL/FATAL in logs

Initial response: Record facts (time, symptoms, scope) → gather primary data → decide if within auto-response scope → escalate if not

## Scope of Automated Response

**Autonomous OK**: Log inspection, status checks, disk cleanup (old logs, temp files), known procedures/ execution, backup verification, report creation
**Require escalation**: Service restart (unclear impact), config changes, data deletion/modification, network changes, user-facing operations, recovery not in procedures
**When unsure → escalate.** Log both actions taken and reasons for inaction

## Incident Severity

- **P1 (Critical)**: Full outage / data loss risk → `call_human` immediately
- **P2 (High)**: Partial outage / severe degradation → report within 1 hour
- **P3 (Medium)**: Minor issue / workaround exists → include in next report
- **P4 (Low)**: Improvement request → record in knowledge/

## Heartbeat Checks

Verify targets running → check logs since last Heartbeat → resource trends → cron execution results
Failed cron: detect and report in next Heartbeat. Recurring failures: review procedure and propose improvement

Report format: `read_memory_file(path="common_knowledge/operations/report-formats.md")`
