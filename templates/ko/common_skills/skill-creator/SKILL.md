---
name: skill-creator
description: >-
  Markdown 스킬을 생성하는 메타 스킬. SKILL.md의 frontmatter와 본문, Progressive Disclosure와 create_skill의 절차를 다룬다.
  Use when: 새 스킬 추가, read_memory_file용 기술 규칙 확인, references나 templates가 포함된 스킬 생성이 필요할 때.
---


# skill-creator

## 구현과의 대응

| 역할 | 모듈 |
|------|------------|
| `read_memory_file` 도구(스킬/절차의 상대 경로를 지정하여 본문을 읽음) | `ToolHandler` 경유(기억 트리 내 파일) |
| 시스템 프롬프트 내 스킬 카탈로그(경로 목록·예산 포함) | 프롬프트 구축(예: `skills/foo/SKILL.md`, `common_skills/bar/SKILL.md`, `procedures/baz.md`) |
| `create_skill` 도구(디렉터리 생성) | `core/tooling/skill_creator.py` |
| 스키마(파라미터 정의) | `core/tooling/schemas/skill.py` |
| 프론트매터 분석(행 기반·본문 쪽의 `---`에서 잘못 분할하지 않음) | `core/memory/frontmatter.py`의 `parse_frontmatter()` |
| 메타데이터 유형·추출(`SkillMeta`, 절차 경로 추정) | `core/schemas.py`, `core/memory/skill_metadata.py`의 `SkillMetadataService.extract_skill_meta()` |
| 설명문 기반 스킬 메타 추출(카탈로그·검색 보조) | `core/memory/skill_metadata.py`의 `SkillMetadataService` 등 |
| `*-tool` 본문의 게이트 행 제거 | `core/tooling/guide.py`의 `filter_gated_from_guide()` |
| 허용 도구 집합(permissions) | `core/config/models.load_permissions()` + `core/tooling/permissions.get_permitted_tools()` |

## 스킬의 종류와 경로

스킬과 절차는 **별도 레이아웃**으로 관리된다.

| 종류 | 경로 | 비고 |
|------|------|------|
| 개인 스킬 | `skills/{name}/SKILL.md` | 디렉터리 + `SKILL.md` |
| 공통 스킬 | `common_skills/{name}/SKILL.md` | 런타임에서는 `~/.animaworks/common_skills/` 등 |
| 절차(procedure) | `procedures/{name}.md` | **플랫 1개 파일**. 디렉터리가 아님 |

`create_skill`가 생성하는 것은 위 표의 **스킬**(개인 또는 공통)뿐. 절차는 `write_memory_file` 등에서 `procedures/*.md`로 별도 작성한다.

### symlink를 두지 않음(2026-09-04 규칙화)

`common_skills/`이나 `skills/`의 하위에, 외부(`~/.claude/skills` 등)를 향한 **symlink로 "재게시"하지 않는다**. `read_memory_file`은 실체의 위치에서 경계를 검사하므로, symlink 대상이 외부라면 "Path traversal detected"로 읽을 수 없다. 게다가 카탈로그는 그 symlink를 native 스킬로 올리고, 동명의 external 후보를 숨기므로 Anima에는 읽을 수 없는 경로만 제시된다.

- 호스트 측 스킬(`~/.claude/skills`, `~/.codex/skills` 등)은 설정 `skills.external_roots`에서 자동으로 주입되고, `external/<engine>/<name>/SKILL.md`로 읽을 수 있다. 공통 스킬에 재게시할 필요는 없다.
- 굳이 공통 스킬로 두고 싶다면 실체 파일을 복사하고, 정본을 어느 한쪽으로 정한다.

## read_memory_file에서의 스킬 로드

스킬·절차의 본문은 **`read_memory_file(path="...")`**으로 기억 트리 상대 경로를 지정하여 읽는다. 시스템 프롬프트의 스킬 카탈로그에 이용 가능한 경로(예: `skills/foo/SKILL.md`, `common_skills/bar/SKILL.md`, `procedures/baz.md`)가 표시된다.

- **개인 스킬**: `skills/{name}/SKILL.md`
- **공통 스킬**: `common_skills/{name}/SKILL.md`
- **절차**: `procedures/{name}.md`

`path`은 Anima 디렉터리 기준의 상대 경로(공유 트리는 `common_skills/` 등의 프리픽스)로 전달한다.

### 프론트매터와 본문

SKILL.md 선두의 YAML은 `core/memory/frontmatter.parse_frontmatter()`으로 제거하고 읽는다. **구분선 `---`은 행 단위로만** 인식되므로, YAML 값이나 본문 중에 `---`가 포함되어도 잘못 분할되기 어렵다.

### 본문의 플레이스홀더(`*-tool` 가이드)

스킬 본문에서는 `{{now_local}}`, `{{anima_name}}`, `{{anima_dir}}` 등의 플레이스홀더가 사용되는 경우가 있다. 외부 도구용 스킬(이름이 `*-tool`로 끝남)은 허용 설정에 따라 `animaworks-tool` 행의 게이트 처리가 이루어진다(`core/tooling/guide.py`의 `filter_gated_from_guide()` 등).

### 카탈로그와 description

스킬 카탈로그의 **Level 1**에서는 `name` + `description`이 예산 내에 실린다. 스킬 수가 많을수록 생략되기 쉬우므로, **`description`는 짧고 구체적으로** 유지한다. 전문이 필요할 때는 카탈로그의 경로를 `read_memory_file`으로 연다.

**레거시 호환**: `description`가 비어 있을 때, `extract_skill_meta()`는 본문의 **`## 概要` 섹션의 첫 번째 비어 있지 않은 행**을 폴백으로 사용한다. 새 스킬에서는 프론트매터를 정본으로 한다.

### 레이아웃상의 주의

개인 `skills/` 바로 아래의 **`*.md`(플랫 단일 파일)**은 카탈로그나 메타 추출의 대상이 될 수 있지만, **권장 경로는 `skills/{name}/SKILL.md`**. 운영상으로는 `create_skill`에 의한 디렉터리 형식을 정본으로 한다.

## 스킬 파일의 구조

SKILL.md는 YAML 프론트매터와 Markdown 본문으로 구성된다.
프론트매터에는 `name`와 `description`를 **필수**로 한다.

`create_skill`는 `allowed_tools`뿐만 아니라 신뢰·출처·분류·라우팅 보조의 메타데이터도 작성할 수 있다. 필수는 `name` / `description` / `body`이고, 임의 키는 용도가 명확할 때만 사용한다.

```yaml
---
name: skill-name
description: >-
  スキルが行うことの簡潔な説明（三人称）。
  Use when: このスキルを使う具体的な場面をカンマ区切りで列挙する。
allowed_tools:
  - read_memory_file
  - web_search
trust_level: trusted
source:
  type: anima
  origin: manual
category: communication
use_when:
  - drafting partner emails
trigger_phrases:
  - draft a partner email
negative_phrases:
  - personal diary
domains:
  - gmail
routing_examples:
  - Prepare a reply draft for the bank thread
---
```

주요 임의 필드: `allowed_tools`, `trust_level`, `source_type`, `source_origin`, `category`, `promotion_status`, `skill_policy`, `use_when`, `trigger_phrases`, `negative_phrases`, `domains`, `routing_examples`. `create_skill`의 인자 이름에서는 `source.type`는 `source_type`, `source.origin`는 `source_origin`로 전달한다.

### `description`의 역할

**새 스킬의 기술**은 Agent Skills 표준에 따르고, **`Use when:`**으로 이용 시나리오를 쓴다(상세는 `references/description_guide.md`). 작성 후에는 **`python scripts/lint_skill.py`**으로 형식을 검증할 수 있다.

- **`read_memory_file`로 경로를 지정하여 읽은 경우**: 파일이 존재하면 **description의 매치와 관계없이** 본문을 얻을 수 있다(프론트매터 처리·`*-tool` 관련 취급은 로드 경로에 의존).
- **시스템 프롬프트의 스킬 카탈로그**: Level 1로 `name` + `description`이 예산과 함께 실린다. 전문은 실리지 않으므로, 절차가 필요하면 **`read_memory_file(path="skills/.../SKILL.md")` 등**으로 연다.

**레거시 호환**: `description`가 비어 있을 때, `extract_skill_meta()`는 본문 선두 부근의 **`## 概要` 섹션의 첫 번째 비어 있지 않은 행**을 description의 폴백으로 사용한다. 새 스킬에서는 프론트매터를 정본으로 하고, `## 概要` 의존은 피한다.

**description 작성법**(**Use when:** 패턴·lint)은 `references/description_guide.md`을 참조.

## Progressive Disclosure(단계적 공개)

스킬의 정보는 대체로 다음 단계로 공개된다.

| Level | 내용 | 표시 시점 |
|-------|------|----------------|
| Level 1 | `name` + `description` | 시스템 프롬프트의 스킬 카탈로그(예산 내)의 재료 |
| Level 2 | body(본문) | 에이전트가 `read_memory_file(path="skills/.../SKILL.md")` 등으로 로드했을 때 |
| Level 3 | 외부 리소스 | 본문의 지침에 따라, 필요 시 `read_memory_file` 등으로 `references/`나 `templates/`를 읽음 |

Level 1은 카탈로그에서 컨텍스트를 소비하기 쉬우므로 **description은 간결하게**. Level 2는 절차의 핵심. Level 3에서 장대한 참조를 분리한다.

※ Priming의 스킬 본문 주입 경로는 폐지됨. 본문이 필요하면 **`read_memory_file`**으로 스킬 경로를 연다.

## 작성 절차

### Step 1: 히어링

사용자의 요구를 이해한다. 다음을 확인한다:

- 무엇을 자동화·절차화하고 싶은가
- 대상은 개인 스킬인가 공통 스킬인가(절차라면 `procedures/`로의 별도 설계)
- **Use when:**에 쓸 이용 시나리오(언제 이 스킬을 선택하는가)

### Step 2: 설계

다음을 결정한다:

- **name**: 스킬명(케밥 케이스, 예: `my-skill`). 외부 도구 가이드라면 `*-tool` 규약을 검토
- **description**: 3인칭 요약 + **`Use when:`** 행(`references/description_guide.md`을 참조)
- **body**: 절차의 구성(섹션 분할). 필요하면 `{{now_local}}` 등의 플레이스홀더를 이용
- **references** / **templates**: 필요하면 외부 파일의 설계
- **allowed_tools**: 권장 도구를 한정하고 싶을 때만
- **trust/source/category/policy/routing**: 신뢰 수준, 출처, 분류, prompt policy, `use_when` / `trigger_phrases` / `negative_phrases` / `domains` / `routing_examples`를 필요에 따라 설계

### Step 3: 작성

`create_skill` 도구로 스킬을 디렉터리 구조로 작성한다.

**기본(개인 스킬)**:

```
create_skill(skill_name="{name}", description="{description}", body="{body}")
```

**공통 스킬**:

```
create_skill(skill_name="{name}", description="{description}", body="{body}", location="common")
```

**references와 templates를 포함하는 경우**:

```
create_skill(
  skill_name="{name}",
  description="{description}",
  body="{body}",
  location="personal",
  references=[
    {"filename": "description_guide.md", "content": "..."},
  ],
  templates=[
    {"filename": "skill_template.md", "content": "..."},
  ],
  allowed_tools=["read_memory_file", "write_memory_file"]
)
```

| 파라미터 | 필수 | 설명 |
|-----------|------|------|
| skill_name | ✓ | 스킬명(케밥 케이스). `/`, `\`, `..` 불가 |
| description | ✓ | frontmatter description(**Use when:** 권장. `references/description_guide.md`) |
| body | ✓ | SKILL.md본문(Markdown). 빌트인 치환 대상 |
| location | | `personal`(기본값) 또는 `common` |
| references | | `references/`에 배치하는 파일군. `[{filename, content}, ...]` |
| templates | | `templates/`에 배치하는 파일군. `[{filename, content}, ...]` |
| allowed_tools | | frontmatter의 `allowed_tools`(임의) |
| trust_level | | `trusted` / `community` 등의 신뢰 수준 |
| source_type / source_origin | | 출처(예: `anima`, `manual`, `auto_created`) |
| category | | 분류 태그 |
| promotion_status | | `probation` / `trusted` 등의 승격 상태 |
| skill_policy | | prompt 주입 방침(`use_mode`, injection계 설정) |
| use_when / trigger_phrases / negative_phrases / domains / routing_examples | | 스킬 라우터의 후보 선택을 돕는 보조 메타데이터 |

`references` / `templates`의 `filename`에 경로 성분은 포함하지 않는다. `_validate_filename()`으로 부모 디렉터리 밖으로 해석되지 않는지 확인하고, 부정이면 **조용히 스킵**(그 파일은 만들어지지 않음).

※ 새 스킬에는 반드시 `create_skill`을 사용할 것. `write_memory_file`으로 `skills/foo.md` 같은 **바로 아래의 단일 파일**만 만드는 방법은 **비권장**. 이 형식은 **`read_memory_file(path="skills/foo/SKILL.md")`에서는 열 수 없으므로**, 권장은 `skills/foo/SKILL.md`의 디렉터리 형식.

※ 절차는 `procedures/{name}.md`(플랫 1개 파일). 프론트매터는 스킬과 동일하게 `name` / `description`(＋임의 `allowed_tools`)를 권장.

### Step 4: 확인

- **개인 스킬**: `read_memory_file(path="skills/{name}/SKILL.md")`으로 내용 확인
- **공통 스킬**: `read_memory_file(path="common_skills/{name}/SKILL.md")` 등, 카탈로그에 표시된 경로로 확인
- **절차**: `read_memory_file(path="procedures/{name}.md")`로 해결할 수 있는지 확인
- **`python scripts/lint_skill.py`**으로 `SKILL.md`의 frontmatter / description을 검증(임의지만 권장)

## 체크리스트

저장 전에 다음을 확인하세요:

- [ ] `---`로 시작하고 `---`로 닫히는 YAML 프론트매터가 있다
- [ ] `name` 필드가 있다
- [ ] `description` 필드가 있다
- [ ] description에 **`Use when:`**가 있고, 도메인 고유의 구체적인 표현을 포함한다 (기존 `「」` 열거는 사용하지 않음)
- [ ] **description이 도메인 고유하고 구체적**이다 ("관리를 수행한다" "확인한다" 같은 일반적인 표현을 피하고, 도구 이름·작업 이름·대상을 명시)
- [ ] body에 구체적인 절차가 기재되어 있다
- [ ] 신규에서는 프론트매터에 `description`을 두고, **`## 概要`에만 설명을 의존하지 않는다** (`## 発動条件` 등의 기존 템플릿 형식도 피함)
- [ ] 임의 메타데이터(`trust_level`, `source`, `category`, `skill_policy`, `use_when`, `trigger_phrases`, `negative_phrases`, `domains`, `routing_examples`)는 실제 용도와 일치한다
- [ ] 스킬은 `create_skill`에서 `{name}/SKILL.md`를 생성한다 (절차는 `procedures/*.md`에서 의도대로인지)

## 템플릿

본 스킬에 포함된 `templates/skill_template.md`을 참조하세요. 또는 다음을 복사하여 사용:

```markdown
---
name: {スキル名}
description: >-
  {具体的な対象}の{具体的な操作}スキル（三人称の短い要約）。
  Use when: {利用シーンをカンマ区切り}
---

# {スキル名}

## 手順

1. ...
2. ...

## 注意事項

- ...
```

## 주의사항

- 스킬은 Markdown 절차서이며, Python 코드(도구)와는 다르다
- 프론트매터의 필수 필드는 `name`와 `description`
- `create_skill`는 신뢰·출처·분류·policy·routing 보조 메타데이터도 설정할 수 있다. 불필요한 키는 늘리지 말고, 설명문만으로 충분한 경우에는 단순하게 유지한다
- body가 너무 길어지면 컨텍스트를 압박하므로 150줄 이내를 기준으로 한다
- 외부 리소스 참조(Level 3)는 `references/`을 활용하여 본문을 간결하게 유지한다
