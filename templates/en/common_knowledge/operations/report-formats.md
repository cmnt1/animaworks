# Report Formats

Standard report templates and checklists used by each role.

## Manager: Status Report

```markdown
## Status Report

### Completed
- [Completed tasks and outcomes]

### In Progress
- [Task name]: [Progress % / status] — [Next step]

### Issues and Risks
- [Issue and impact] — [Response plan]

### Decisions Needed
- [What decision is needed and options]
```

## Researcher: Research Report

```markdown
# Research Report: [Topic]

## Summary
[1–3 sentence summary of findings]

## Research Objective
[What you were trying to clarify]

## Method
[How you researched — search terms, references]

## Findings
### Main Findings
- [Bullet list]

### Details
[Detailed explanation of each finding]

## Sources and Confidence
| Source | Type | Confidence |
|--------|------|------------|
| [URL/name] | [Official/Primary/Secondary] | [High/Medium/Low] |

## Conclusion and Recommendations
[Judgment and next actions based on findings]
```

## Operations: Regular Monitoring Report

```markdown
## Regular Monitoring Report

### Check Time
[YYYY-MM-DD HH:MM]

### System State
- [Target]: [Normal/Caution/Anomaly] — [notes]

### Resources
- Disk: [usage]%
- Memory: [usage]%

### Recent Events
- [Event summary]

### Follow-up
- [Actions needed, if any]
```

## Operations: Incident Record

```markdown
## Incident Record

- Occurrence: [YYYY-MM-DD HH:MM]
- Detected via: [heartbeat/cron/manual]
- Severity: [P1–P4]
- Impact: [Concrete impact]
- Cause: [Identified cause / under investigation]
- Response: [Actions taken]
- Prevention: [Required measures]
```

## Writer: Self-Review Checklist

### Content
- [ ] Purpose is clearly stated at the start
- [ ] No logical gaps
- [ ] Explanation level matches reader's background
- [ ] Nothing essential is missing
- [ ] No unnecessary information

### Expression
- [ ] Sentences not too long (target: ~60 chars)
- [ ] No unnecessary repetition
- [ ] Not overly passive (prefer active voice)
- [ ] Vague wording made concrete where possible

### Format
- [ ] Heading hierarchy is consistent
- [ ] Bullet granularity is uniform
- [ ] Code blocks, links, tables render correctly
- [ ] No typos or grammar errors
