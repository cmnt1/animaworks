---
name: newstaff
description: >-
  AnimaWorks 조직에 새로운 Digital Anima를 고용·생성하는 스킬.
  히어링을 바탕으로 캐릭터 시트(Markdown)를 작성하고, CLI 명령어(animaworks anima create)로
  identity/injection/permissions등을 일괄 생성한다. 생성 후에는 bootstrap으로 자체 정비.
  「새로운 사원을 만들어 줘」「사람을 고용해 줘」「새로운 사원」「고용」「Anima 생성」「채용」「팀 멤버를 늘리기」「인원 추가」「부하 만들기」「스태프 추가」「hire」「recruit」「team member」
---
Understood. Please provide the Japanese content you would like me to translate into Korean.# 스킬: 신규 직원 고용## 전제 조건

- 작성할 사원의 역할 방향성이 정해져 있을 것 (불명확한 경우 히어링을 통해 파악할 것)## 절차### 1. 히어링 (최소한으로 OK)

의뢰자로부터 다음 정보를 히어링한다. **굵은 글씨 항목만 필수**이며, 나머지는 미지정 시 자동 생성한다:

**필수:**
- **영문명** (반각 영문 소문자만. 디렉터리 이름이 됨)
- **역할/전문 영역**: 무엇을 담당하는지 (예: 리서치, 개발, 커뮤니케이션, 인프라 모니터링)
- **성격 방향성**: 직능이 아닌 온도 (예: 활발, 갸루, 천연, 열혈, 아가씨, 누나). 쿨은 조직에 이미 2명이 있다면 선택하지 않음
- **얼굴 타입**: `{data_dir}/prompts/face_types.md` 에서 1개. 기존 멤버와 너무 중복되지 않을 것

**임의 (지정이 있으면 반영, 없으면 자동 생성):**
- 일본어 이름
- 나이
- 기타 고집이 있으면 무엇이든

**기술 설정 (지정이 없으면 기본값 사용):**
- 역할: `commander` (다른 직원에게 위임 가능) 또는 `worker` (위임을 받는 측)
- supervisor: 상급자가 되는 Anima의 영문명 (worker의 경우 필수. 미지정 시 자신)

**두뇌 (LLM 모델) 설정:**

다음 표를 제시하고 선택하도록 한다:

| 레벨 | 실행 모드 | 사용 모델 예 | 특징 | credential |
|--------|-----------|-------------|------|------------|
| S | autonomous | `claude-opus-4-6`, `claude-sonnet-4-6` | Claude Agent SDK. 가장 고기능 | anthropic |
| A | autonomous | `openai/gpt-4.1`, `google/gemini-2.5-pro`, `vertex_ai/gemini-2.5-flash` | LiteLLM 경유. 도구 사용 가능 | openai / google / azure / vertex |
| B | assisted | `ollama/gemma3:27b`, `ollama/qwen2.5-coder:32b` | 도구 없음. 로컬 실행·저비용 | ollama |

※ 지정이 없으면 기본값 (claude-sonnet-4 / autonomous / anthropic)을 사용한다.### 2. 캐릭터 설계 (자동 생성)

히어링에서 얻은 정보로 캐릭터를 구체화한다. **성격이 먼저, 직능은 나중.**

반드시 다음을 이 순서로 Read 한다:
1. `{data_dir}/prompts/face_types.md`
2. `{data_dir}/prompts/character_design_guide.md`

역할에서 쿨한 미인을 연상하지 않는다. 취미는 일의 연장으로 두지 않는다. 기존 멤버의 머리색·얼굴형·말투와 겹치지 않는지 확인한다.### 3. 캐릭터 시트를 작성하고, CLI로 일괄 생성

히어링과 설계 결과를 **캐릭터 시트 사양**에 따라 캐릭터 시트를 파일로 작성하고, CLI 명령으로 생성한다:

1. 캐릭터 시트를 파일로 작성한다 (예: `/tmp/{english_name}.md`)
2. 다음 명령을 실행한다:

```bash
animaworks anima create --from-md /tmp/{english_name}.md --name {english_name} --supervisor {supervisor_english_name}
```

**supervisor 설정:**
- `supervisor` 파라미터로 명시 지정 (권장)
- 생략한 경우: 캐릭터 시트의 `| 上司 |` 항목에서 가져옴
- 둘 다 없는 경우: 자신(호출한 Anima)이 supervisor가 됨

**캐릭터 시트 사양:**

```markdown
# キャラクターシート: {Japanese name}

## 基本情報

| 項目 | 設定 |
|------|------|
| 英名 | {lowercase alphanumeric} |
| 日本語名 | {Japanese full name} |
| 役職/専門 | {Role description} |
| 上司 | {supervisor English name} |
| 役割 | {commander / worker} |
| 実行モード | {autonomous / assisted} |
| モデル | {model name} |
| credential | {anthropic / openai / google / ollama} |

## 人格 (→ identity.md)

{Personality, speaking style, values, backstory, appearance, etc.}

## 役割・行動方針 (→ injection.md)

{Responsible areas, decision criteria, reporting rules, conduct standards, etc.}

## 権限 (→ permissions.json) [省略可]

{If omitted: default template applied}

## 定期業務 (→ heartbeat.md, cron.md) [省略可]

{If omitted: generic template applied. New Anima self-adjusts in bootstrap}

## 初回起動指示 (→ bootstrap.md 追加指示) [省略可]

{If omitted: standard bootstrap only}
```

**필수 섹션**: 기본 정보, 성격, 역할·행동 방침
**생략 가능 섹션**: 권한, 정기 업무, 최초 시작 지침

이로써 다음이 자동 실행된다:
- 디렉터리 구조 일괄 생성
- skeleton 파일 배치
- bootstrap.md 배치
- status.json 생성 (supervisor 포함)
- config.json 등록 (model, supervisor 등)
- 생략 섹션에 대한 기본값 적용### 4. config.json 모델 설정 확인

`animaworks anima create`이 자동으로 config.json에 등록하지만, 다음 사항을 확인하고 보완할 것:

- `model`: 히어링에서 결정한 모델명
- `credential`: 사용할 credential 이름
- `execution_mode`: autonomous 또는 assisted
- `speciality`: 직책/전문 분야### 4.5. 하트비트 주기 제안 및 설정

새로운 직원의 업무 구동 방식에 따라 정기 하트비트 간격을 요청자에게 제안하고, 합의된 값을 설정한다:

| 구동 방식 | 권장 간격 | 예 |
|--------|---------|-----|
| 자발적인 상황 판단·조정이 주 업무 | 30분 (기본값) | 팀 조정 역할, 진행 감독 |
| 메시지·이벤트 구동이 중심 | 60~120분 | 리뷰 담당, 개발 담당 |
| cron 정기 업무가 중심 | 120~240분 | 모니터링, 회계, 법무 |

설정은 `{data_dir}/animas/{英名}/status.json`에 `"heartbeat_interval_minutes": <分>`(1~1440)을 추가한다.
메시지 기반 하트비트와 cron은 이 설정과 무관하게 동작하므로, 간격을 늘려도 응답성은 떨어지지 않는다. 고민되면 더 긴 간격을 선택한다(빈 하트비트는 토큰 낭비가 된다).### 5. 서버에 반영

```
Bash: curl -s -X POST http://localhost:18500/api/system/reload
```
### 6. 의뢰자에게 보고

고용 완료를 보고한다:
- 새 직원의 이름과 역할
- 설정한 기술 스택 (모델, 실행 모드)

⚠️ 아바타 이미지 생성은 보고하지 않는다 (새 Anima 자신이 bootstrap에서 생성한다)### 이후로는 새로운 Anima 자신이 자율적으로 실행:
- identity.md / injection.md 의 충실화
- heartbeat.md / cron.md 의 자기 설계
- 아바타 이미지 생성 (상급자 참조 포함)
- 상급자에게 취임 보고