---
name: local-llm-tool
description: >-
  로컬 LLM 실행 도구. Ollama나 vLLM으로 GPU 상의 모델에 텍스트 생성·채팅을 요청한다.
  Use when: 온프레미스 추론, Ollama 엔드포인트 호출, 로컬 모델에서의 요약·생성이 필요할 때.
tags: [llm, local, ollama, external]
---
Understood. Please provide the Japanese content you would like me to translate into Korean.# 로컬 LLM 도구

로컬 LLM(Ollama/vLLM） 경유로 텍스트 생성·채팅을 수행하는 외부 도구.## 호출 방법

**Bash**: `animaworks-tool local_llm <サブコマンド> [引数]`에서 실행## 작업 목록### generate — 텍스트 생성
```bash
animaworks-tool local_llm generate "プロンプト" [-S "システムプロンプト"]
```
### chat — 채팅 (복수 턴)
```bash
animaworks-tool local_llm chat [--messages JSON] [-S "システムプロンプト"]
```
### models — 모델 목록
```bash
animaworks-tool local_llm list
```
### status — 서버 상태 확인
```bash
animaworks-tool local_llm status
```
## CLI 사용법

```bash
animaworks-tool local_llm generate "プロンプト" [-S "システムプロンプト"]
animaworks-tool local_llm list
animaworks-tool local_llm status
```
## 주의사항

- Ollama 서버 또는 vLLM 서버가 시작되어 있어야 함
- -s/--server에서 서버 URL 지정 가능
- -m/--model에서 모델 지정 가능