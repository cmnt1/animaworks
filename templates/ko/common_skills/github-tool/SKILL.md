---
name: github-tool
description: >-
  GitHub 연동 도구. Issue·PR 목록 조회 및 생성을 gh CLI를 통해 수행한다.
  Use when: Issue나 PR의 생성·목록, 리포지토리 조작, GitHub 상의 작업 확인이 필요할 때.
tags: [development, github, external]
---


# GitHub 도구

GitHub의 Issue·PR을 gh CLI를 통해 조작하는 외부 도구.

## 호출 방법

**Bash**: `animaworks-tool github <サブコマンド> [引数]`로 실행

## 액션 목록

### list_issues — Issue 목록
```bash
animaworks-tool github issues [--repo OWNER/REPO] [--state open] [--limit 20]
```

### create_issue — Issue 생성
```bash
animaworks-tool github create-issue --title TITLE --body BODY [--labels LABELS]
```

### list_prs — PR 목록
```bash
animaworks-tool github prs [--repo OWNER/REPO] [--state open] [--limit 20]
```

### create_pr — PR 생성
```bash
animaworks-tool github create-pr --title TITLE --body BODY --head BRANCH [--base main]
```
- `draft` (선택, 기본값: false): 드래프트 PR로 생성할지 여부

## CLI 사용법

```bash
animaworks-tool github issues [--repo OWNER/REPO] [--state open] [--limit 20]
animaworks-tool github create-issue --title TITLE --body BODY [--labels LABELS]
animaworks-tool github prs [--repo OWNER/REPO] [--state open] [--limit 20]
animaworks-tool github create-pr --title TITLE --body BODY --head BRANCH [--base main]
```

## 주의사항

- gh CLI가 설치되어 있고 인증이 완료되어 있어야 함
- --repo 생략 시 현재 디렉터리의 리포지토리를 사용
