---
name: subagent-cli
description: >-
  외부 AI 에이전트 CLI를 Bash에서 비대화형으로 실행하는 스킬. codex exec나 cursor-agent로 코딩 작업을 위임하는 절차를 제공한다.
  Use when: 복잡한 구현의 위임, 코드 리뷰, 여러 파일의 일괄 변경, Bash에서 서브 에이전트를 시작할 때.
---


# subagent-cli

외부 AI 에이전트 CLI를 Bash를 통해 서브프로세스로 실행하고, 복잡한 코딩 작업을 위임한다.
자신의 정체성·판단·기억은 유지한 채, 실행 능력을 확장하기 위한 '파워 툴'로 사용한다.

## 프레임워크 실행 모드와의 관계

이 스킬은 **Bash 도구가 사용 가능한 경우**에만 적용된다.

| 모드 | 구현 | Bash | 이 스킬의 적용 |
|--------|------|------|------------------|
| **Mode S** | `agent_sdk.py` (Claude Agent SDK) | 기본적으로 사용 가능 | 적용됨. Claude Code 서브프로세스 내에서 Read/Write/Edit/Bash/Grep/Glob/WebFetch/WebSearch + MCP(send_message 등) + Task/Agent가 사용 가능. Bash 실행 시 cwd는 anima_dir |
| **Mode C** | `codex_sdk.py` (Codex SDK) | Codex CLI의 도구 세트에 의존 | **codex exec는 불필요** — 프레임워크가 Codex를 직접 실행. cursor-agent / claude -p는 Bash를 통해 호출 가능 (Bash가 사용 가능한 경우) |
| **Mode D** | Cursor Agent (cursor-agent 서브프로세스) | Cursor CLI의 도구 세트에 의존 | **cursor-agent -p는 불필요** — 프레임워크가 cursor-agent를 직접 실행. MCP 통합. Mode S에 가까운 도구 접근이지만 실체는 cursor-agent 바이너리. codex exec / claude -p는 Bash를 통해 호출 가능 (Bash가 사용 가능한 경우) |
| **Mode G** | Gemini CLI (gemini 서브프로세스) | Gemini CLI의 도구 세트에 의존 | **Gemini CLI의 수동 시작은 불필요** — 프레임워크가 직접 실행. MCP 통합, stream-json 출력. 다른 CLI는 Bash를 통해 호출 가능 (Bash가 사용 가능한 경우) |
| **Mode A/B** | LiteLLM + tool_use / 1샷 | permissions.json에서 허용 시에만 | Bash 허용이 있으면 적용 |

**중요**: Mode C (`codex/*`), Mode D (`cursor/*`), Mode G (`gemini/*`)의 Anima는 프레임워크가 각 엔진을 직접 실행한다. 이 경우, 자신이 `codex exec` (Mode C)나 `cursor-agent -p` (Mode D), Gemini CLI (Mode G)를 Bash에서 호출할 필요는 없다. 다른 CLI (cursor-agent / claude -p / codex exec 등)를 명시적으로 사용하고 싶은 경우에만, 이 스킬의 해당 섹션을 참조한다.

**Windows 예외**: 네이티브 Windows 환경에서 shell 실행이 `policy blocked`이 된 경우, 또는 `codex exec exited with code 1`이 반복적으로 발생하는 경우, 로컬 `codex exec`의 재시도를 중단할 것. shell 필수 작업은 상급자 (`supervisor`)에게 에스컬레이션한다.

## 도구 선택의 우선순위

**비용 효율 순으로 선택할 것.**

| 우선순위 | 도구 | 비용 | 강점 분야 |
|--------|--------|--------|----------|
| 1 | `codex exec` | 가장 저렴 (Codex) | 코드 생성·편집·리뷰 |
| 2 | `cursor-agent -p` | 저렴 (Cursor) | 코드 생성·편집·멀티파일 |
| 3 | `claude -p` | 높음 (Claude API) | 최후의 수단. 위 두 가지로 해결되지 않는 경우에만 |

**원칙**: 비Windows 또는 shell 실행이 건강한 환경에서는 `codex exec`을 먼저 시도한다. 네이티브 Windows에서 shell 실행이 blocked / unstable인 경우에는 `codex exec`를 건너뛰고, 상급자 (`supervisor`)에게 에스컬레이션한다. 그 외의 실패 시나 어려운 작업에만 cursor-agent → claude 순으로 폴백.

## 사용해야 하는 시점

- 여러 파일에 걸친 코드 변경
- 테스트 작성·테스트 수정
- 코드 리뷰
- 리팩터링
- 버그 수정의 조사와 구현
- 새 기능의 구현

## 사용하지 말아야 하는 시점

- 1개 파일의 작은 편집 (직접 수행)
- 기억의 읽기·쓰기 (자신의 도구 사용)
- 외부 API 호출 (전용 도구 사용)
- 정보의 검색·조사만 (web_search나 Read로 충분)

---

## 1. codex exec (권장)

**적용 조건**: Mode S 또는 Mode A/B（Bash 허용)일 때. Mode C의 경우 프레임워크가 Codex를 실행하므로, 이 섹션은 불필요. Mode D/G의 경우도 프레임워크가 각 엔진을 실행하므로, 대안으로 codex를 사용할 필요가 없으면 참조 불필요.

### 기본 구문

```bash
codex exec --full-auto -C /path/to/workspace "プロンプト"
```

작업 디렉터리 `-C`에는 대상 프로젝트의 절대 경로를 지정한다. Mode S의 Bash 실행 시에는 `ANIMAWORKS_ANIMA_DIR` (Anima의 데이터 디렉터리)와 `ANIMAWORKS_PROJECT_DIR` (AnimaWorks 프레임워크의 루트)가 환경 변수로 설정된다. AnimaWorks 자체의 개발이 대상인 경우에는 `-C "$ANIMAWORKS_PROJECT_DIR"`를 사용할 수 있다.

### 중요 옵션

| 옵션 | 설명 |
|-----------|------|
| `--full-auto` | 자동 승인 + 샌드박스 (workspace-write) |
| `-C /path` | 작업 디렉터리 지정 (**필수**) |
| `-m model` | 모델 지정 (예: `o4-mini`, `o3`) |
| `--sandbox workspace-write` | 작업 공간 쓰기 허용 (full-auto에 포함) |
| `--json` | JSONL 형식으로 출력 |
| `-o file` | 최종 메시지를 파일에 기록 |
| `--ephemeral` | 세션 파일을 저장하지 않음 |

### 실행 예

#### 코드 생성

```bash
codex exec --full-auto --ephemeral -C /home/user/dev/myproject \
  "src/utils/parser.py にMarkdownパーサーを実装して。既存のテストを壊さないこと。"
```

#### 코드 리뷰

```bash
codex exec --full-auto --ephemeral -C /home/user/dev/myproject \
  review
```

#### 테스트 작성

```bash
codex exec --full-auto --ephemeral -C /home/user/dev/myproject \
  "src/utils/parser.py のユニットテストを tests/test_parser.py に作成して。"
```

#### 결과를 파일에 저장

```bash
codex exec --full-auto --ephemeral -C /home/user/dev/myproject \
  -o /tmp/codex_result.txt \
  "このプロジェクトのアーキテクチャを分析して改善案を出して。"
```

---

## 2. cursor-agent -p (대안)

**적용 조건**: Mode S 또는 Mode A/B（Bash 허용). Mode C/G에서도 Bash가 사용 가능한 경우 적용 가능. Mode D에서는 프레임워크가 cursor-agent를 실행하므로, 이 섹션의 수동 `cursor-agent -p`은 원칙적으로 불필요.

### 기본 구문

```bash
cursor-agent -p --trust --force --workspace /path/to/workspace "プロンプト"
```

### 중요 옵션

| 옵션 | 설명 |
|-----------|------|
| `-p` / `--print` | 비대화형 모드 (**필수**) |
| `--trust` | 작업 공간을 자동 신뢰 |
| `--force` | 명령 자동 승인 |
| `--workspace /path` | 작업 디렉터리 지정 (**필수**) |
| `--model model` | 모델 지정 (예: `sonnet-4`, `gpt-5`) |
| `--output-format text\|json` | 출력 형식 |
| `--mode plan\|ask` | 읽기 전용 모드 (조사용) |

### 실행 예

#### 코드 생성

```bash
cursor-agent -p --trust --force \
  --workspace /home/user/dev/myproject \
  "src/api/routes.py にPOST /users エンドポイントを追加して。バリデーション付き。"
```

#### 읽기 전용 조사

```bash
cursor-agent -p --trust --mode ask \
  --workspace /home/user/dev/myproject \
  "この認証フローにセキュリティ上の問題はある？"
```

#### 결과를 파일에 저장

```bash
cursor-agent -p --trust --force \
  --workspace /home/user/dev/myproject \
  --output-format text \
  "テストカバレッジが低いモジュールを特定して改善して" > /tmp/cursor_result.txt
```

---

## 3. claude -p (폴백)

**적용 조건**: Mode S 또는 Mode A/B（Bash 허용). Mode C/D/G에서도 Bash가 사용 가능한 경우 적용 가능.

codex/cursor-agent로 대응할 수 없을 때만 사용. API 비용이 높다.

### 기본 구문

```bash
claude -p --dangerously-skip-permissions --output-format text "プロンプト"
```

### 중요 옵션

| 옵션 | 설명 |
|-----------|------|
| `-p` / `--print` | 비대화형 모드 (**필수**) |
| `--dangerously-skip-permissions` | 권한 체크 생략 |
| `--model model` | 모델 지정 (예: `sonnet`, `haiku`) |
| `--allowedTools "tools"` | 허용 도구 제한 (예: `"Read Edit Bash(git:*)"`) |
| `--output-format text\|json` | 출력 형식 |
| `--max-budget-usd N` | 비용 상한 (달러) |
| `--no-session-persistence` | 세션 저장 안 함 |

### 실행 예

```bash
claude -p --dangerously-skip-permissions --no-session-persistence \
  --model haiku --max-budget-usd 0.5 \
  --output-format text \
  "src/core/parser.py のエラーハンドリングを改善して"
```

---

## 프롬프트 작성법

서브 에이전트에는 AnimaWorks의 맥락이 없다. 명확하고 자기 완결적인 프롬프트를 작성할 것.

### 좋은 프롬프트

```
以下の要件でPythonモジュールを実装して:

ファイル: src/utils/validator.py

要件:
- Pydantic v2のBaseModelを使ったバリデータ
- email, username, passwordフィールド
- パスワードは8文字以上、英数字混合
- バリデーションエラー時にカスタム例外を投げる

制約:
- from __future__ import annotations を先頭に
- Google-style docstring
- 既存のテストを壊さないこと
```

### 나쁜 프롬프트

```
いい感じにバリデーションを直して
```

→ 맥락이 없고, '좋게'가 불명확.

---

## 출력 처리

### 표준 출력 캡처

```bash
RESULT=$(codex exec --full-auto --ephemeral -C /path "プロンプト" 2>/dev/null)
echo "$RESULT"
```

### 파일 경유 (codex 권장)

```bash
codex exec --full-auto --ephemeral -C /path \
  -o /tmp/result.txt "プロンプト"
# 結果を読む
cat /tmp/result.txt
```

### 종료 코드로 성공 여부 판정

```bash
codex exec --full-auto --ephemeral -C /path "プロンプト"
if [ $? -eq 0 ]; then
  echo "成功"
else
  echo "失敗 — cursor-agentにフォールバック"
  cursor-agent -p --trust --force --workspace /path "同じプロンプト"
fi
```

---

## 백그라운드 실행 (중요)

서브 에이전트의 실행은 **5분~20분 이상** 걸릴 수 있다.
포그라운드에서 기다리면 세션이 블록되므로, **반드시 백그라운드로 실행**할 것.

### 기본 패턴: nohup + 결과 파일

```bash
nohup codex exec --full-auto --ephemeral -C /path/to/workspace \
  -o /tmp/codex_result.txt \
  "プロンプト" > /tmp/codex_stdout.log 2>&1 &
echo "PID: $!"
```

cursor-agent의 경우:

```bash
nohup cursor-agent -p --trust --force \
  --workspace /path/to/workspace \
  "プロンプト" > /tmp/cursor_result.txt 2>&1 &
echo "PID: $!"
```

### 완료 확인

```bash
# プロセスがまだ動いているか確認
ps -p <PID> > /dev/null 2>&1 && echo "実行中" || echo "完了"

# 結果を読む（完了後）
cat /tmp/codex_result.txt
# または
cat /tmp/cursor_result.txt
```

### 타임아웃 포함 실행

폭주를 막기 위해 `timeout`을 병용한다:

```bash
nohup timeout 30m codex exec --full-auto --ephemeral -C /path \
  -o /tmp/codex_result.txt \
  "プロンプト" > /tmp/codex_stdout.log 2>&1 &
```

- 권장 타임아웃: **30분** (`30m`)
- 작은 작업: **10분** (`10m`)
- 큰 리팩터링: **60분** (`60m`)

### 실행 중에 다른 작업 계속

백그라운드 실행 후, 완료를 기다리지 않고 다른 작업을 진행해도 된다.
정기적으로 프로세스의 생존을 확인하고, 완료되면 결과를 읽어 episodes/에 기록한다.

---

## 안전 가이드라인

1. **작업 디렉터리를 반드시 지정** — 미지정 시 현재 디렉터리에서 실행됨
2. **기밀 정보를 프롬프트에 포함하지 않기** — API 키, 비밀번호 등
3. **codex는 `--full-auto`으로 샌드박스 내 실행** — 작업 공간 외부로의 쓰기가 제한됨
4. **실행 후 git diff로 변경 확인** — 의도하지 않은 변경이 없는지 체크
5. **--ephemeral을 붙이기** — 세션 파일이 불필요하게 축적되는 것을 방지

---

## 폴백 전략

```
1. codex exec で試行
   ↓ 失敗 or 品質不足
2. cursor-agent -p で再試行
   ↓ 失敗 or 品質不足
3. claude -p（--max-budget-usd でコスト制限）で最終試行
   ↓ それでも失敗
4. 自分で実行を試みるか、上司に報告する
```

## 주의 사항

- 서브 에이전트는 AnimaWorks의 기억·도구에 접근할 수 없다. 어디까지나 '코딩의 손'
- 실행 결과는 자신의 episodes/에 기록하고, 배운 패턴은 knowledge/에 축적할 것
- 실행에는 5분~20분 이상 걸린다. 반드시 백그라운드로 실행하고, timeout을 설정할 것
- git 관리된 리포지토리에서 작업할 것 (변경의 추적·취소가 용이)
- Mode S에서는 Bash 실행 시 `ANIMAWORKS_ANIMA_DIR` (Anima의 데이터 디렉터리)와 `ANIMAWORKS_PROJECT_DIR` (AnimaWorks 프레임워크의 루트)가 환경 변수로 설정된다 (`agent_sdk.py`의 `_build_env()`에서 주입)
