---
name: workspace-manager
description: >-
  작업 공간(작업 디렉터리)의 등록・목록・삭제・할당을 설정한다.
  Use when: 프로젝트 경로를 Anima에 연결하고, 별칭 관리, 작업 디렉터리 전환이 필요할 때.
tags: [workspace, directory, project, management]
---
Understood. Please provide the Japanese content you would like me to translate into Korean.# 작업 공간 관리

Anima가 작업하는 프로젝트 디렉터리(작업 공간)를 관리하는 스킬.## 概念

Animaは普段「自分の家」（~/.animaworks/animas/{name}/）にいる。
プロジェクトの作業をするときは「仕事場」（ワークスペース）に出かけて作業する。

ワークスペースは組織共有のレジストリ（config.json の workspaces セクション）に登録し、エイリアス#ハッシュで参照する。

## 별칭과 해시

- 별칭: 사람이 붙이는 짧은 이름 (예: `myproject`)
- 해시: 경로의 SHA-256 앞 8자리가 자동 부여됨 (예: `3af4be6e`)
- 완전형: `myproject#3af4be6e` — 충돌 가능성 제로
- 도구 인자에는 별칭만, 완전형, 해시만, 절대 경로 중 어느 것이든 사용 가능## 操作方法

### 등록

인간으로부터 명시적 지시를 받은 최상위 Anima는 `grant_workspace_access`을 사용한다:

```json
{
  "alias": "finance-dashboard",
  "path": "/absolute/path/to/project",
  "make_default": true
}
```

이 도구는 조직 공유 레지스트리 등록, `permissions.json.file_roots`에 대한 쓰기 권한 추가, 필요에 따른 `status.json.default_workspace` 업데이트를 한 번에 수행한다.

**주의**: 디렉토리가 존재하지 않으면 오류가 발생한다.
**주의**: `read_memory_file(path="config.json")`는 자신의 Anima 디렉토리의 `config.json`를 읽는다. 조직 공유 레지스트리 등록에는 사용하지 않는다.### 목록

조직 공유 레지스트리의 목록은 `core.org.workspace.list_workspaces()`에서 확인한다. `read_memory_file(path="config.json")`은 사용하지 않는다.### 삭제

삭제는 관리자 작업으로 취급한다. 일반적인 작업에서는 기존 별칭을 덮어쓰지 않고, 새로운 별칭을 등록한다.### 기본 작업 공간 변경

최상위 Anima는 `grant_workspace_access`에 `make_default: true`을 지정한다.
비최상위 Anima는 스스로 권한을 추가할 수 없다. 최상위 Anima에게 인간이 지침을 내려야 한다.### 부하에게 할당하기 (슈퍼바이저용)

인간으로부터 명시적 지침을 받은 톱레벨 Anima는 `target_anima` 을 지정하여 부하 또는 하위 Anima에게 권한을 부여할 수 있다:

```json
{
  "alias": "finance-dashboard",
  "path": "/absolute/path/to/project",
  "target_anima": "ritsu",
  "make_default": true
}
```
## 도구에서의 사용

- **submit_tasks**: 각 작업의 `workspace` 필드에 별칭 지정
- **delegate_task**: `workspace` 필드에 별칭 지정## 주의사항

- 디렉터리는 등록 시와 사용 시 모두 존재 여부가 확인됨
- 존재하지 않는 디렉터리를 등록하려 하면 오류 발생
- 별칭을 덮어쓰면 해시도 변경되므로, 이전 해시 참조는 해결에 실패함
- 사용자는 해시를 기억할 필요 없음 — 별칭만으로 충분함