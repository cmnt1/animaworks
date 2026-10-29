---
name: transcribe-tool
description: >-
  음성 텍스트 변환 도구. Whisper로 음성 파일을 텍스트로 변환하고, 필요에 따라 LLM 후처리를 수행한다.
  Use when: 회의 녹음 전사, 팟캐스트 받아쓰기, 음성 파일에서 텍스트 추출이 필요할 때.
tags: [audio, transcription, whisper, external]
---


# Transcribe 도구

Whisper (faster-whisper)를 사용한 음성 텍스트 변환 도구.

## 호출 방법

**Bash**: `animaworks-tool transcribe transcribe <音声ファイル> [オプション]`로 실행

### audio — 음성 텍스트 변환
```bash
animaworks-tool transcribe transcribe audio_file.wav [-l ja] [-m large-v3-turbo]
```

## 파라미터

| 파라미터 | 타입 | 기본값 | 설명 |
|-----------|-----|-----------|------|
| audio_path | string | (필수) | 음성 파일의 경로 |
| language | string | null | 언어 코드 (ja, en 등). null이면 자동 감지 |
| model | string | "large-v3-turbo" | Whisper 모델 이름 |
| raw | boolean | false | true인 경우, LLM 후처리를 건너뜀 |

## CLI 사용법

```bash
animaworks-tool transcribe transcribe audio_file.wav [-l ja] [-m large-v3-turbo]
```

## 주의사항

- faster-whisper 설치 필요
- GPU 사용 시 CUDA 호환 ctranslate2 필요
- 최초 실행 시 모델이 자동 다운로드됨
