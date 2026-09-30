# Voice Chat Guide

Reference for voice conversation features with Anima.
Browser microphone input → STT (speech recognition) → chat pipeline → TTS (speech synthesis) → browser playback.

## Architecture Overview

```
ブラウザ (AudioWorklet 16kHz mono PCM)
  → WebSocket /ws/voice/{name}
    → VoiceSTT (faster-whisper)
      → ProcessSupervisor IPC → Animaチャット（既存パイプライン）
    → StreamingSentenceSplitter (文分割)
      → TTS Provider (VOICEVOX / SBV2 / ElevenLabs)
    ← audio binary + JSON制御メッセージ
  ← VoicePlayback (Web Audio API)
```

Voice chat goes through the existing text chat pipeline. From Anima's perspective, it is processed the same as a normal chat message (the text converted by STT arrives).

---

## Dependencies and Installation

### STT (Speech Recognition)

`faster-whisper` is required:

```bash
pip install faster-whisper
# または pip install animaworks[transcribe]
```

The Whisper model (default: `large-v3-turbo`) is automatically downloaded on the first STT execution.
When using a GPU, CUDA-compatible `ctranslate2` is required.

### TTS (Speech Synthesis)

TTS must be started separately as an external service:

| Provider | Features | Startup Method | Default URL |
|-----------|------|---------|-------------|
| **VOICEVOX** | Free, Japanese-focused, many character voices | Docker: `docker run -p 50021:50021 voicevox/voicevox_engine` | `http://localhost:50021` |
| **Style-BERT-VITS2** | High quality, custom voice model support | Start SBV2 or AivisSpeech Engine | `http://localhost:5000` |
| **ElevenLabs** | Cloud API, multilingual, high quality | Set environment variable `ELEVENLABS_API_KEY` | Cloud (no local startup required) |

---

## Configuration

### Global Configuration (config.json section of `voice`)

Default settings common to all Anima:

```json
{
  "voice": {
    "stt_model": "large-v3-turbo",
    "stt_device": "auto",
    "stt_compute_type": "default",
    "stt_language": null,
    "stt_refine_enabled": false,
    "default_tts_provider": "voicevox",
    "voicevox": { "base_url": "http://localhost:50021" },
    "elevenlabs": { "api_key_env": "ELEVENLABS_API_KEY", "model_id": "eleven_flash_v2_5" },
    "style_bert_vits2": { "base_url": "http://localhost:5000" }
  }
}
```

| Field | Default | Description |
|-----------|-----------|------|
| `stt_model` | `large-v3-turbo` | Whisper model name. Options: `tiny`, `base`, `small`, `medium`, `large-v3`, `large-v3-turbo` |
| `stt_device` | `auto` | `auto` (GPU preferred) / `cpu` / `cuda` |
| `stt_compute_type` | `default` | CTranslate2 quantization type: `default`, `int8`, `float16` |
| `stt_language` | `null` | Language code (`ja`, `en`, etc.). Auto-detection with `null` |
| `stt_refine_enabled` | `false` | LLM post-processing of STT results (adds 1-3 seconds latency when enabled) |
| `default_tts_provider` | `voicevox` | Default TTS provider: `voicevox` / `style_bert_vits2` / `elevenlabs` |

### Per-Anima Voice Settings (status.json section of `voice`)

Individual settings for each Anima under `status.json` with the `voice` key:

```json
{
  "voice": {
    "tts_provider": "voicevox",
    "voice_id": "3",
    "speed": 1.0,
    "pitch": 0.0,
    "extra": {}
  }
}
```

| Field | Description |
|-----------|------|
| `tts_provider` | TTS provider used for this Anima. Falls back to global default when unset |
| `voice_id` | Provider-specific voice ID (described below) |
| `speed` | Speech speed (1.0 = standard) |
| `pitch` | Pitch (0.0 = standard) |
| `extra` | Provider-specific additional parameters (optional). For ElevenLabs, the model can be overridden with `model_id` |

#### How to Specify voice_id

| Provider | voice_id format | How to check |
|-----------|----------------|---------|
| VOICEVOX | Speaker ID (numeric string) e.g., `"3"` = Zundamon | Get list with `curl http://localhost:50021/speakers` |
| Style-BERT-VITS2 | `model_id:speaker_id` or `model_id:speaker_id:style`. e.g., `0:0` | Get list with `curl http://localhost:5000/models/info` |
| ElevenLabs | voice_id string | Check in ElevenLabs dashboard or via API |

If no setting exists or `voice_id` is empty, the provider's default voice is used.

---

## WebSocket Protocol

Endpoint: `ws://HOST/ws/voice/{anima_name}`

### Authentication

On connection, authentication is performed by one of the following:

- **local_trust mode**: No authentication required
- **trust_localhost enabled and localhost connection**: Connections from loopback addresses require no authentication (with CSRF validation)
- **Otherwise**: Validated with the `session_token` cookie. Closes with 4001 Unauthorized if invalid

Since WebSocket sends cookies during the HTTP Upgrade, authentication happens automatically from a logged-in browser.

### Connection Limits

- **1 Anima = 1 active session**: A new connection to the same Anima replaces the existing session (the existing side closes with 4000 "Replaced by new session")
- **Invalid name**: Closes with 4000 "Invalid anima name" if `name` contains `/` or `..`, is empty, or starts with `.`

### Client → Server

| Type | Format | Description |
|--------|------|------|
| Audio data | binary | 16kHz mono 16-bit PCM binary |
| `{"type": "speech_end"}` | JSON | Speech end notification → triggers STT execution |
| `{"type": "interrupt"}` | JSON | TTS playback interruption (barge-in) |
| `{"type": "config", "vad_mode": "ptt"}` or `{"type": "config", "vad_mode": "vad"}` | JSON | Optional. Mode switch notification (server does not currently process) |

### Server → Client

| Type | Format | Description |
|--------|------|------|
| `{"type": "status", "state": "loading"}` | JSON | Session initializing (STT loading) |
| `{"type": "status", "state": "ready"}` | JSON | Session ready |
| `{"type": "transcript", "text": "..."}` | JSON | STT result text |
| `{"type": "response_start"}` | JSON | Anima response stream start |
| `{"type": "response_text", "text": "...", "done": false}` | JSON | Anima response text (chunk) |
| `{"type": "response_done", "emotion": "..."}` | JSON | Anima response completion (with emotion metadata) |
| `{"type": "thinking_status", "thinking": true/false}` | JSON | Extended thinking start/end |
| `{"type": "thinking_delta", "text": "..."}` | JSON | Extended thinking text chunk |
| TTS audio data | binary | TTS audio binary |
| `{"type": "tts_start"}` | JSON | TTS audio send start |
| `{"type": "tts_error", "message": "..."}` | JSON | On TTS synthesis failure (sent just before tts_done) |
| `{"type": "tts_done"}` | JSON | TTS audio send complete |
| `{"type": "error", "message": "..."}` | JSON | Error notification |

---

## Frontend UI

A microphone button appears in both the dashboard and workspace chat screens.

After connecting, the server sends `status: loading` → `status: ready`, and voice input can begin once ready.

### Voice Input Modes

| Mode | Operation | Description |
|--------|------|------|
| **PTT (Push-to-Talk)** | Press and hold microphone button → release | Reliable control. Records only while pressed |
| **VAD (Voice Activity Detection)** | Automatic | Automatically detects speech start to begin recording, auto-sends on silence |

Can be switched via the UI toggle.

### Features

- **Volume control**: Slider to adjust TTS playback volume
- **TTS indicator**: Visual feedback while Anima is speaking (separate from the recording indicator)
- **Barge-in**: Starting to speak during TTS playback automatically interrupts Anima's audio

---

## TTS Provider Details

### VOICEVOX

- Free, open-source Japanese speech synthesis engine
- 50+ character voices
- Runs locally (no internet required)
- Docker: `docker run -p 50021:50021 voicevox/voicevox_engine`
- GPU version: `docker run --gpus all -p 50021:50021 voicevox/voicevox_engine`

### Style-BERT-VITS2 / AivisSpeech

- High-quality Japanese speech synthesis
- Custom voice model training and usage supported
- AivisSpeech Engine is an easy-install SBV2-compatible version
- Runs locally

### ElevenLabs

- Cloud-based multilingual speech synthesis API
- High quality, natural voices
- API key required (`ELEVENLABS_API_KEY` environment variable)
- Pay-as-you-go pricing

---

## Troubleshooting

### STT Not Working

- Check that `faster-whisper` is installed: `pip show faster-whisper`
- When using a GPU, check that the CUDA version of `ctranslate2` matches
- Switch to `stt_device: "cpu"` and try CPU mode

### TTS Returns No Audio

- Check that the TTS provider is running
  - VOICEVOX: Check for a response at `curl http://localhost:50021/speakers`
  - SBV2: Check for a response at `curl http://localhost:5000/models/info`
  - ElevenLabs: Check that the `ELEVENLABS_API_KEY` environment variable is set
- Check the server log for `TTS unavailable` errors
- Check whether the client received the `tts_error` message (on TTS synthesis failure)
- If TTS is unavailable, only text responses are returned (no audio)

### Audio Drops Out / High Latency

- Check network bandwidth (audio streaming is real-time)
- Change `stt_model` to a lighter model (`base`, `small`)
- Check `stt_refine_enabled: false` (LLM post-processing increases latency)
- Start VOICEVOX/SBV2 in GPU mode

### Invalid voice_id Produces No Audio

- Check that the specified `voice_id` exists in the provider
- If invalid, falls back to the provider's default voice + warning log
- VOICEVOX: Check valid IDs with `curl http://localhost:50021/speakers | jq`
- SBV2: Check the model list with `curl http://localhost:5000/models/info` and specify in `model_id:speaker_id` format

---

## Technical Notes

### VoiceSession Internal Behavior

`core/voice/session.py` manages one voice conversation session:

1. **Audio buffer management**: Up to 60 seconds (16kHz × 16bit × 60s ≈ 1.9MB). Cleared on overflow
2. **Minimum utterance filter**: Audio shorter than 0.35 seconds or silence (below RMS threshold) is discarded
3. **STT execution**: Transcribes the buffer in one batch when `speech_end` is received
4. **Voice mode attachment**: Appends `[voice-mode: 音声会話です。話し言葉で200文字以内で簡潔に...]` to the end of the message before passing it to Anima
5. **Chat integration**: Sends text to the existing chat pipeline via ProcessSupervisor IPC
6. **Pre-TTS sanitization**: Removes Markdown formatting (headings, bold, lists, code blocks, etc.) before passing to TTS
7. **Streaming response**: Splits Anima response text into sentence units (by punctuation: 。！？、line breaks)
8. **Sentence-level TTS**: Runs TTS for each split sentence to minimize first-byte latency
9. **TTS health check**: Checks provider availability on first call. Caches only on success; re-checks on failure. Disables the cache after 3 consecutive TTS synthesis failures
10. **Concurrency guard**: Prevents multiple `speech_end` from being processed simultaneously

The IPC stream timeout defaults to 60 seconds. Can be overridden with `server.ipc_stream_timeout` in `config.json`.

### Sentence Splitting (StreamingSentenceSplitter)

Streaming sentence splitting for Japanese text (`core/voice/sentence_splitter.py`):
- Splits immediately after punctuation (。！？!?)
- Also splits on line breaks
- Buffers to hold incomplete sentences

### Barge-in (Interruption)

If the user starts speaking during TTS playback:
1. The client sends `{"type": "interrupt"}`
2. The server interrupts the ongoing TTS processing
3. The client clears the playback queue
4. Processing of the new user utterance begins
