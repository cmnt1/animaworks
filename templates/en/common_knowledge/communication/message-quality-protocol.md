# Message Quality Protocol

Required items to check before sending a message.
See `communication/reporting-guide.md` / `communication/instruction-patterns.md` for detailed examples.

---

## 1. Four Required Items for Delegation Instructions

Must be included in `delegate_task` or in the request message:

| # | Item | Content |
|---|------|------|
| 1 | Task description | What to do (1-2 line summary including background) |
| 2 | Completion criteria | What constitutes completion |
| 3 | Reference information | File path / Issue or PR URL / related materials |
| 4 | Deadline and report destination | By when, and to whom to report |

**Pre-delegation check**: Verify in `list_tasks` that there are no incomplete delegations for the same Issue/PR.

---

## 2. Three Required Items for Completion Reports

Must be included in completion reports (intent="report"):

| # | Item | Content |
|---|------|------|
| 1 | Result | What was completed (1 line) |
| 2 | Deliverables | File path / PR URL / numerical results |
| 3 | Validation evidence | Means, count, and time of verification |

**Required even when "no anomalies"**: State what was checked, how many, and when.

- Bad example: "All items normal"
- Good example: "Checked Slack 3 channels and Chatwork 2 rooms, 0 ERRORs, last check 14:52 JST"

---

## 3. Four Required Items for Escalations

Must be included in problem reports and decision requests:

| # | Item | Content |
|---|------|------|
| 1 | Facts | What happened (time + observed facts only. No evaluative or emotional language) |
| 2 | Impact | Who/what is blocked |
| 3 | Attempted measures | What you tried and the results |
| 4 | Options | Two or more action plans and a recommendation |

**Prohibited**: Using evaluative language instead of facts (e.g., "terrible state," "not done at all").
Write facts and time first; if evaluation is needed, add one sentence at the end.