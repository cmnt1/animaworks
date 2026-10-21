---
name: notebooklm-tool
description: >-
  Google NotebookLM integration tool. Performs notebook management, source addition, content retrieval, chat (Q&A),
  and artifact generation (audio summaries, reports, etc.).
  Use when: When you need to operate NotebookLM notebooks, check source content, ask questions to a notebook, or generate reports.
tags: [research, notebooklm, knowledge, external]
---


# NotebookLM Tool

An external tool that operates Google NotebookLM via API.

## How to Invoke

**Bash**: Run with `animaworks-tool notebooklm <サブコマンド> [引数]`

## Action List

### list — List notebooks
```bash
animaworks-tool notebooklm list
```

### get — Get notebook summary and topics
```bash
animaworks-tool notebooklm get NOTEBOOK_ID
```
Returns the notebook summary and suggested question topics.

### create — Create notebook
```bash
animaworks-tool notebooklm create "タイトル"
```

### delete — Delete notebook
```bash
animaworks-tool notebooklm delete NOTEBOOK_ID
```

### sources — List sources
```bash
animaworks-tool notebooklm sources NOTEBOOK_ID
```

### source-text — Get source text
```bash
animaworks-tool notebooklm source-text NOTEBOOK_ID SOURCE_ID
```
Returns the full text of a source. Use this when you want to check the content.

### add-source-url — Add URL source
```bash
animaworks-tool notebooklm add-source-url NOTEBOOK_ID URL
```

### add-source-text — Add text source
```bash
animaworks-tool notebooklm add-source-text NOTEBOOK_ID --title "タイトル" --text "本文"
```

### add-source-file — Add file source
```bash
animaworks-tool notebooklm add-source-file NOTEBOOK_ID /path/to/file.pdf
```

### chat — Ask questions to a notebook
```bash
animaworks-tool notebooklm chat NOTEBOOK_ID "質問テキスト"
```
Returns answers based on sources and their citations.

### generate — Generate artifact
```bash
animaworks-tool notebooklm generate NOTEBOOK_ID --type audio_overview [--language ja] [--instructions "指示"]
```
Types: `audio_overview`, `briefing_doc`, `study_guide`, `faq`, `timeline`, `mind_map`

⚠️ Long-running process. Recommended to run in the background with `animaworks-tool submit notebooklm generate ...`.

### artifacts — List artifacts
```bash
animaworks-tool notebooklm artifacts NOTEBOOK_ID [--type AUDIO]
```

## Typical Workflow

1. Get the notebook list with `list` (check the IDs)
2. Check the summary with `get NOTEBOOK_ID`
3. Get the source list with `sources NOTEBOOK_ID`
4. Read the source text with `source-text NOTEBOOK_ID SOURCE_ID`
5. Ask questions about the content with `chat NOTEBOOK_ID "質問"`

## Notes

- Authentication with `notebooklm login` is required before first use (Google login in the browser)
- Credentials are saved in `~/.notebooklm/storage_state.json`
- If the cookie expires, re-run `notebooklm login`
