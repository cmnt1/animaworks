---
name: newstaff
description: >-
  AnimaWorks 조직에 새로운 Digital Anima를 고용 및 생성하는 스킬.
  인터뷰를 기반으로 캐릭터 시트(Markdown)를 작성한 후 CLI 명령어
  (animaworks anima create)로 identity/injection/permissions 등을 일괄 생성합니다. 생성 후 bootstrap으로 자체 설정합니다.
  "새 직원 만들기", "사람 고용", "신규 직원", "고용", "Anima 생성", "채용"
---

# 스킬: 신규 직원 고용

## 전제 조건

- 생성할 직원의 역할 방향이 결정되어 있어야 합니다(불명확한 경우 인터뷰를 진행하세요)

## 절차

### 1. 인터뷰 (최소한으로 충분)

요청자에게 다음 정보를 인터뷰합니다. **굵은 글씨 항목만 필수**이며, 나머지는 미지정 시 자동 생성됩니다:

**필수:**
- **영문 이름** (소문자 영숫자만 허용, 디렉터리명이 됩니다)
- **역할/전문 분야**: 무엇을 담당하는지 (예: 리서치, 개발, 커뮤니케이션, 인프라 모니터링)

**선택 (지정 시 반영, 미지정 시 자동 생성):**
- 한국어 이름
- 성격 방향 (예: "밝은", "쿨한", "느긋한" 정도면 충분)
- 나이
- 기타 요구사항

**기술 설정 (미지정 시 기본값 사용):**
- 역할: `commander` (다른 직원에게 위임 가능) 또는 `worker` (위임을 받는 쪽)
- supervisor: 상사가 되는 Anima의 영문 이름 (worker의 경우 필수, 미지정 시 자신)

**두뇌(LLM 모델) 설정:**

다음 표를 제시하여 선택받습니다:

| 레벨 | 실행 모드 | 모델 예시 | 특징 | credential |
|--------|-----------|-------------|------|------------|
| S | autonomous | `claude-opus-4-6`, `claude-sonnet-4-6` | Claude Agent SDK. 최고 성능 | anthropic |
| A | autonomous | `openai/gpt-4.1`, `google/gemini-2.5-pro`, `vertex_ai/gemini-2.5-flash` | LiteLLM 경유. 도구 사용 가능 | openai / google / azure / vertex |
| B | assisted | `ollama/gemma3:27b`, `ollama/qwen2.5-coder:32b` | 도구 없음. 로컬 실행, 저비용 | ollama |

※ 미지정 시 기본값(claude-sonnet-4 / autonomous / anthropic)을 사용합니다.

### 2. 캐릭터 설계 (자동 생성)

인터뷰에서 얻은 최소한의 정보로 **일관성 있는 깊이 있는 캐릭터 프로필**을 창작합니다.

런타임 데이터 디렉터리의 **캐릭터 설계 가이드**(`{data_dir}/prompts/character_design_guide.md`)를 Read하여 해당 규칙에 따라 캐릭터를 구체화하세요.

### 3. 캐릭터 시트 작성 및 CLI로 일괄 생성

인터뷰와 설계 결과에 따라 **캐릭터 시트 사양**을 준수하여 캐릭터 시트를 파일로 작성하고 CLI 명령어로 생성합니다:

1. 캐릭터 시트를 파일에 작성합니다 (예: `/tmp/{english_name}.md`)
2. 다음 명령어를 실행합니다:

```bash
animaworks anima create --from-md /tmp/{english_name}.md --name {english_name} --supervisor {supervisor_english_name}
```

**supervisor 설정:**
- `supervisor` 파라미터로 명시 지정 (권장)
- 생략 시: 캐릭터 시트의 `| 상사 |` 항목에서 가져옵니다
- 둘 다 없는 경우: 호출한 Anima 자신이 supervisor가 됩니다

**캐릭터 시트 사양:**

```markdown
# 캐릭터 시트: {Korean name}

## 기본 정보

| 항목 | 설정 |
|------|------|
| 영문명 | {lowercase alphanumeric} |
| 한국어명 | {한국어 성명} |
| 직책/전문 | {역할 설명} |
| 상사 | {supervisor 영문 이름} |
| 역할 | {commander / worker} |
| 실행 모드 | {autonomous / assisted} |
| 모델 | {model name} |
| credential | {anthropic / openai / google / ollama} |

## 인격 (→ identity.md)

{성격, 말투, 가치관, 배경 스토리, 외모 등}

## 역할 및 행동 방침 (→ injection.md)

{담당 영역, 판단 기준, 보고 규칙, 행동 기준 등}

## 권한 (→ permissions.json) [생략 가능]

{생략 시: 기본 템플릿 적용}

## 정기 업무 (→ heartbeat.md, cron.md) [생략 가능]

{생략 시: 범용 템플릿 적용. 새 Anima가 bootstrap에서 자체 조정}

## 초기 실행 지시 (→ bootstrap.md 추가 지시) [생략 가능]

{생략 시: 표준 bootstrap만 수행}
```

**필수 섹션**: 기본 정보, 인격, 역할 및 행동 방침
**생략 가능 섹션**: 권한, 정기 업무, 초기 실행 지시

이로써 다음이 자동으로 수행됩니다:
- 디렉터리 구조 일괄 생성
- skeleton 파일 배치
- bootstrap.md 배치
- status.json 생성 (supervisor 포함)
- config.json에 등록 (model, supervisor 등)
- 생략된 섹션에 기본값 적용

### 4. config.json의 모델 설정 확인

`animaworks anima create`가 자동으로 config.json에 등록하지만, 다음을 확인/보완하세요:

- `model`: 인터뷰에서 결정한 모델명
- `credential`: 사용할 credential명
- `execution_mode`: autonomous 또는 assisted
- `speciality`: 직책/전문

### 5. 서버에 반영

**Bash**를 사용하여 서버를 리로드합니다:

```bash
curl -s -X POST http://localhost:18500/api/system/reload
```

### 6. 요청자에게 보고

고용 완료를 보고합니다:
- 새 직원의 이름과 역할
- 설정한 기술 스택(모델, 실행 모드)

⚠️ 아바타 이미지 생성은 보고하지 마세요(새 Anima가 bootstrap에서 자체 생성합니다)

### 이후 새 Anima가 자율적으로 실행하는 항목:
- identity.md / injection.md 충실화
- heartbeat.md / cron.md 자체 설계
- 아바타 이미지 생성 (상사 참조 포함)
- 상사에게 착임 보고
