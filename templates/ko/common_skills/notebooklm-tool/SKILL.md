---
name: notebooklm-tool
description: >-
  Google NotebookLM 연동 도구. 노트북 관리·소스 추가·본문 가져오기·채팅(Q&A)·
  아티팩트 생성(음성 개요·보고서 등)을 수행한다.
  Use when: NotebookLM의 노트북 조작, 소스 내용 확인, 노트북에 대한 질문, 보고서 생성이 필요할 때.
tags: [research, notebooklm, knowledge, external]
---


# NotebookLM 도구

Google NotebookLM을 API 경유로 조작하는 외부 도구.

## 호출 방법

**Bash**: `animaworks-tool notebooklm <サブコマンド> [引数]` 로 실행

## 액션 목록

### list — 노트북 목록
```bash
animaworks-tool notebooklm list
```

### get — 노트북 요약·토픽 가져오기
```bash
animaworks-tool notebooklm get NOTEBOOK_ID
```
노트북의 요약과 추천 질문 토픽을 반환한다.

### create — 노트북 생성
```bash
animaworks-tool notebooklm create "タイトル"
```

### delete — 노트북 삭제
```bash
animaworks-tool notebooklm delete NOTEBOOK_ID
```

### sources — 소스 목록
```bash
animaworks-tool notebooklm sources NOTEBOOK_ID
```

### source-text — 소스 본문 가져오기
```bash
animaworks-tool notebooklm source-text NOTEBOOK_ID SOURCE_ID
```
소스의 전체 텍스트를 반환한다. 내용을 확인하고 싶을 때는 이것을 사용한다.

### add-source-url — URL 소스 추가
```bash
animaworks-tool notebooklm add-source-url NOTEBOOK_ID URL
```

### add-source-text — 텍스트 소스 추가
```bash
animaworks-tool notebooklm add-source-text NOTEBOOK_ID --title "タイトル" --text "本文"
```

### add-source-file — 파일 소스 추가
```bash
animaworks-tool notebooklm add-source-file NOTEBOOK_ID /path/to/file.pdf
```

### chat — 노트북에 질문
```bash
animaworks-tool notebooklm chat NOTEBOOK_ID "質問テキスト"
```
소스에 기반한 답변과 인용 출처를 반환한다.

### generate — 아티팩트 생성
```bash
animaworks-tool notebooklm generate NOTEBOOK_ID --type audio_overview [--language ja] [--instructions "指示"]
```
타입: `audio_overview`, `briefing_doc`, `study_guide`, `faq`, `timeline`, `mind_map`

⚠️ 장시간 처리. `animaworks-tool submit notebooklm generate ...` 로 백그라운드 실행 권장.

### artifacts — 아티팩트 목록
```bash
animaworks-tool notebooklm artifacts NOTEBOOK_ID [--type AUDIO]
```

## 전형적인 워크플로

1. `list` 로 노트북 목록 가져오기(ID 확인)
2. `get NOTEBOOK_ID` 로 요약 확인
3. `sources NOTEBOOK_ID` 로 소스 목록 가져오기
4. `source-text NOTEBOOK_ID SOURCE_ID` 로 소스 본문 읽기
5. `chat NOTEBOOK_ID "質問"` 로 내용에 대해 질문

## 주의사항

- 최초 사용 전에 `notebooklm login` 로 인증 필요(브라우저에서 Google 로그인)
- 인증 정보는 `~/.notebooklm/storage_state.json` 에 저장된다
- Cookie 마감일 만료 시 `notebooklm login` 를 재실행
