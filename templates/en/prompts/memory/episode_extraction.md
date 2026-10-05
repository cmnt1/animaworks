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

1. **Group by time period**: Cluster related activities into 30-minute to 2-hour blocks
2. **Be concise and use bullets**: Keep only facts useful for later reference; do not copy email bodies or tool output. For each tool execution, record only what was done, whether it succeeded, and the conclusion
3. **Eliminate redundant repetition**: Deduplicate repeated `current_state.md` dumps or duplicate REFLECTION blocks — keep only one instance
4. **Tool execution results**: State what was done, success/failure, and the conclusion without copying output. Summarize periodic checks with no changes in one line
5. **Communication content**: Record the key points of sent/received messages (who, to whom, about what)
6. **No speculation**: Record only facts from the activity log. Do not add inferences or interpretations
7. **Use existing content for deduplication**: If existing episode content is provided, absorb overlapping details into the timeline and avoid repeating the same facts twice
8. **Use only `##` markdown headers**: Do not use `#` or `###`
