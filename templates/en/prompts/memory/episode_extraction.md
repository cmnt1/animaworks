# Episode Extraction from Activity Logs

Organize your ({anima_name}) action records into a structured timeline.

## Target Period: {time_range}

## Existing Episode Content

{existing_episode}

## Activity Log

{activity_chunk}

---

## Output Format

Output in the following Markdown format. Separate sections by time period with "## HH:MM — Title" and record events in bullet lists.

```
## HH:MM — セクションタイトル

- HH:MM 出来事の要約
  - 詳細・結果・関連情報
- HH:MM 次の出来事
```

## Rules

1. **Group by time period**: Combine related activities into time blocks of about 30 minutes to 2 hours
2. **Preserve specific information**: Keep details such as key points from email bodies, summaries of command execution results, file changes, and message content for later reference as knowledge
3. **Eliminate redundant repetition**: Keep only one copy of identical `current_state.md` dumps or duplicate REFLECTION entries
4. **Tool execution results**: Record a summary of results on success, or the error content on failure
5. **Communication content**: Record key points of sent and received messages (from whom to whom, about what)
6. **Do not add speculation**: Record only facts present in the action log. Do not make inferences or interpretations
7. **Use existing content for deduplication**: If existing episode content is present, absorb duplicate information into the timeline and do not write the same fact twice
8. **Use only Markdown `##` headers**: Do not use `#` or `###`
