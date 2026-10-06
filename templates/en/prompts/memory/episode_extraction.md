# Episode Extraction from Activity Log

{anima_name}, organize your activity records into a structured timeline.

## Target period: {time_range}

## Existing Episode Content

{existing_episode}

## Activity Log

{activity_chunk}

---

## Output Format

Use the following Markdown format. Separate sections by time period using `## HH:MM — Title` headers, with bullet points for events.

```
## HH:MM — Section Title

- HH:MM Event summary
  - Details, results, related information
- HH:MM Next event
```

## Rules

1. **Group by time period**: Group related activities into time periods of approximately 30 minutes to 2 hours.
2. **Be concise and use bullet lists**: Keep only facts useful for later reference; do not copy email bodies or tool output. For tool runs, record only what was done, whether it succeeded, and the conclusion.
3. **Eliminate redundant repetition**: Keep only one copy of identical `current_state.md` dumps or duplicate REFLECTION entries.
4. **Tool run results**: Record only what was done, whether it succeeded or failed, and the conclusion; do not copy the output. Summarize items that showed no change during routine checks in a single line.
5. **Communication**: Record the gist of sent and received messages (who sent what to whom, and about what).
6. **Do not speculate**: Record only facts stated in the activity log. Do not add inferences or interpretations.
7. **Use existing content to remove duplicates**: If existing episode content is available, absorb duplicate information into the timeline and do not record the same fact twice.
8. **Use only Markdown `##` headers**: Do not use `#` or `###`.
