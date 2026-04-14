---
name: notebooklm-tool
description: >-
  Google NotebookLM integration tool. Manage notebooks, add sources, read full text,
  chat (Q&A against sources), and generate artifacts (audio overviews, reports, etc.).
  Use when: you need to manage NotebookLM notebooks, read source content, ask questions about sources, or generate reports.
tags: [research, notebooklm, knowledge, external]
---

# NotebookLM Tool

External tool for operating Google NotebookLM via API.

## How to call

**Bash**: `animaworks-tool notebooklm <subcommand> [args]`

## Actions

### list — List notebooks
```bash
animaworks-tool notebooklm list
```

### get — Get notebook summary and topics
```bash
animaworks-tool notebooklm get NOTEBOOK_ID
```
Returns the notebook summary and suggested question topics.

### create — Create a notebook
```bash
animaworks-tool notebooklm create "Title"
```

### delete — Delete a notebook
```bash
animaworks-tool notebooklm delete NOTEBOOK_ID
```

### sources — List sources in a notebook
```bash
animaworks-tool notebooklm sources NOTEBOOK_ID
```

### source-text — Get full text of a source
```bash
animaworks-tool notebooklm source-text NOTEBOOK_ID SOURCE_ID
```
Returns the full text content of the source. Use this to read the actual content.

### add-source-url — Add a URL source
```bash
animaworks-tool notebooklm add-source-url NOTEBOOK_ID URL
```

### add-source-text — Add a text source
```bash
animaworks-tool notebooklm add-source-text NOTEBOOK_ID --title "Title" --text "Content"
```

### add-source-file — Add a file source
```bash
animaworks-tool notebooklm add-source-file NOTEBOOK_ID /path/to/file.pdf
```

### chat — Ask a question against notebook sources
```bash
animaworks-tool notebooklm chat NOTEBOOK_ID "Your question here"
```
Returns an answer with source references.

### generate — Generate an artifact
```bash
animaworks-tool notebooklm generate NOTEBOOK_ID --type audio_overview [--language en] [--instructions "..."]
```
Types: `audio_overview`, `briefing_doc`, `study_guide`, `faq`, `timeline`, `mind_map`

Warning: Long-running. Use `animaworks-tool submit notebooklm generate ...` for background execution.

### artifacts — List artifacts
```bash
animaworks-tool notebooklm artifacts NOTEBOOK_ID [--type AUDIO]
```

## Typical workflow

1. `list` to get notebook IDs
2. `get NOTEBOOK_ID` to read the summary
3. `sources NOTEBOOK_ID` to list sources
4. `source-text NOTEBOOK_ID SOURCE_ID` to read source full text
5. `chat NOTEBOOK_ID "question"` to ask about the content

## Notes

- Requires initial authentication via `notebooklm login` (Google login in browser)
- Credentials stored at `~/.notebooklm/storage_state.json`
- Re-run `notebooklm login` if cookies expire
