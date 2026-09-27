---
name: local-llm-tool
description: >-
  A local LLM execution tool. It requests text generation and chat from models on GPUs via Ollama or vLLM.
  Use when: Use when: on-premise inference, calling Ollama endpoints, or needing summarization and generation with local models.
tags: [llm, local, ollama, external]
---
Understood. I’m ready to translate the Japanese content into natural English while preserving all Markdown structure, headings, tables, links, identifiers, sentinels (including ⟦§number⟧ markers), and YAML frontmatter keys. I’ll keep the literal prefix “Use when:” unchanged and translate only exposed values in the frontmatter. Please provide the content to translate.# Local LLM Tool

An external tool that performs text generation and chat via a local LLM (Ollama/vLLM）).## How to Call

**Bash**: Run with `animaworks-tool local_llm <サブコマンド> [引数]`## List of Actions### generate — Text Generation
```bash
animaworks-tool local_llm generate "プロンプト" [-S "システムプロンプト"]
```
### Chat — Chat (Multiple Turns)
```bash
animaworks-tool local_llm chat [--messages JSON] [-S "システムプロンプト"]
```
### Models — Model List
```bash
animaworks-tool local_llm list
```
### status — Server Status Check
```bash
animaworks-tool local_llm status
```
## CLI Usage

```bash
animaworks-tool local_llm generate "プロンプト" [-S "システムプロンプト"]
animaworks-tool local_llm list
animaworks-tool local_llm status
```
## Notes

- The Ollama server or vLLM server must be running
- Use when: server URL can be specified with -s/--server
- Use when: model can be specified with -m/--model