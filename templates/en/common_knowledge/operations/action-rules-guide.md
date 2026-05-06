# Action Rules (Action-Aware Priming)

## Overview

Action rules are rules that are automatically reminded before specific tool executions.
By writing them in your knowledge with the `[ACTION-RULE]` marker, the system automatically detects them when the corresponding tool is about to be called, pauses execution, and presents the rule content.

## How It Works

1. You are about to call an "output tool" (call_human, send_message, etc.)
2. The system searches your knowledge for `[ACTION-RULE]` rules via RAG
3. If a highly relevant rule is found, tool execution is paused
4. The rule content is presented to you
5. You review the rule, take any required pre-actions, then retry

## Writing Rules

### Basic Format

```markdown
## [ACTION-RULE] Rule Name
trigger_tools: tool_name1, tool_name2
keywords: keyword1, keyword2
---
Rule body. This is what gets displayed when the tool is paused.
Be specific about "what to check before" the action.
```

### Field Description

| Field | Required | Description |
|-------|----------|-------------|
| `trigger_tools` | Required | Target tool names that trigger this rule (comma-separated) |
| `keywords` | Optional | Related keywords (improves vector search precision) |
| Below `---` | Required | Rule body (displayed as-is when paused) |

### Target Tools

The following tools are subject to action rules (read-only tools are excluded):

- `call_human` — Human notification/reporting
- `send_message` — Inter-Anima messaging
- `post_channel` — Board posting
- `slack_post` — Slack posting
- `chatwork_send` — Chatwork sending
- `gmail_send` — Email sending
- `write_memory_file` — Memory file writing

## Examples

### Pre-report Verification Rule

```markdown
## [ACTION-RULE] Check Chatwork before pending report
trigger_tools: call_human, send_message
keywords: pending, report, progress
---
Before reporting pending items to your supervisor, always check
the latest Chatwork messages first. New information or status
changes may have arrived. Reporting stale information causes confusion.
```

### Pre-email Verification Rule

```markdown
## [ACTION-RULE] Verify recipients before email
trigger_tools: gmail_send
keywords: email, send, mail
---
Before sending an email, verify:
1. Recipients are correct (internal vs external distinction)
2. Whether CC should include your supervisor
3. Cross-reference attachments mentioned in body
```

### Combined with `[IMPORTANT]`

```markdown
## [ACTION-RULE] [IMPORTANT] Approval required before customer data change
trigger_tools: write_memory_file
keywords: customer, client, profile
---
Before modifying any customer-related memory files, obtain supervisor approval.
Unauthorized customer data changes are prohibited.
```

## Behavior Constraints

- **Maximum 2 pauses per session**: From the 3rd match onward, no pause occurs
- **Each rule fires once**: The same rule will not pause you twice in one session
- **Retry executes immediately**: After a pause, calling the same tool again succeeds immediately
- **Score threshold**: Only fires at relevance score 0.80 or above

## Tips for Effective Rules

1. **Include tool names in body text**: Improves RAG search precision
2. **One rule, one responsibility**: Don't pack multiple conditions into one rule
3. **Be specific**: Write "read Chatwork" not "verify appropriately"
4. **Use keywords**: List words likely to appear in tool_input
5. **Make body actionable**: It's displayed as-is, so write clear instructions the model can follow

## Creating Rules

Same as normal knowledge creation:

```
write_memory_file(path="knowledge/action-rule-chatwork-check.md", content="## [ACTION-RULE] ...")
```

After creation, rules take effect at the next RAG index rebuild (daily).
