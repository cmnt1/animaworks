---
name: transcribe-tool
description: >-
  Audio transcription tool. Converts audio files to text using Whisper, with optional LLM post-processing as needed.
  Use when: Use when: transcribing meeting recordings, transcribing podcasts, or extracting text from audio files.
tags: [audio, transcription, whisper, external]
---
Understood. Please provide the Japanese content you’d like me to translate, and I’ll follow all the specified rules.# Transcribe Tool

A speech transcription tool using Whisper (faster-whisper).## How to Call

**Bash**: Run with `animaworks-tool transcribe transcribe <音声ファイル> [オプション]`### audio — Audio Transcription
```bash
animaworks-tool transcribe transcribe audio_file.wav [-l ja] [-m large-v3-turbo]
```
## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| audio_path | string | (required) | Path to the audio file |
| language | string | null | Language code (e.g., ja, en). Auto-detected if null |
| model | string | "large-v3-turbo" | Whisper model name |
| raw | boolean | false | If true, skips LLM post-processing |## CLI Usage

```bash
animaworks-tool transcribe transcribe audio_file.wav [-l ja] [-m large-v3-turbo]
```
## Notes

- Installation of faster-whisper is required
- When using a GPU, CUDA-compatible ctranslate2 is required
- The model is automatically downloaded on first runtime