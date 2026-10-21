---
name: obsidian-product
description: >-
  산출물 보고서를 Obsidian Vault에 작성하고, Bases (`0_Products DB.base`)에 집약하는 스킬.
  Use when: 인간에게 제출하는 산출물(보고서·산출물·배포 기록 등) 및 그 부수 자료를 기록할 때.
  구 Notion T_Products DB의 후속. Vault 상의 md에 직접 작성하므로 캡처가 용이하고, 부수 자료는 wikilink로 추적할 수 있다.
tags: [productivity, obsidian, report, deliverable]
---


# Obsidian Product 보고서

산출물의 제출처는 **Obsidian Vault**로 일원화되었다. Notion `T_Products`은 폐지.
이 스킬은 "보고서를 어디에, 어떤 명명으로, 어떤 frontmatter로 쓸지"의 규약을 제시한다. 쓰기 자체는 일반적인 `Write` / `Edit` / `Bash` 도구로 수행한다.
프로젝트 관리의 계획·진행 상황·결정 사항·확인 대기도 Obsidian Vault의 Markdown을 정본으로 한다. Notion에 대한 읽기/쓰기나 Notion DB로의 산출물 제출은 하지 않는다.

## Vault 경로 (고정)

- **Vault 루트**: `E:\OneDriveBiz\Obsidian\`
- **Products 루트**: `E:\OneDriveBiz\Obsidian\_products\`
- **Base 파일**: `E:\OneDriveBiz\Obsidian\0_Products DB.base` (편집 불필요, Obsidian 측이 자동으로 이 파일을 읽어 표시한다)

## 카테고리 → 폴더 대응

| 카테고리 (frontmatter `category`) | 저장 폴더 |
|---|---|
| `General` | `_products\General\` |
| `Finance` | `_products\Finance\` |
| `Affiliate` | `_products\Affiliate\` |
| `Property` | `_products\Property\` |
| `Business` | `_products\Business\` (구 "경영") |

헷갈리면 `General`.

## 파일 명명 규칙

- 메인 보고서: `P-<5桁ゼロ埋めID>_<slug>.md`
  - 예: `P-00042_aff-recipe-v2.md`
- 부수 자료: 메인과 **같은 카테고리 폴더 바로 아래**에, **메인과 같은 프리픽스**로 나열한다
  - 예: `P-00042_aff-recipe-v2_spec.md`, `P-00042_aff-recipe-v2_data.md`
  - 하위 폴더는 만들지 않는다. 파일명 프리픽스로 부모-자식 관계를 표현한다

`<slug>`는 ASCII 소문자, 구분자는 `-`(하이픈). 일본어 제목에서 기계적으로 변환하기 어려운 경우, 의미를 해치지 않는 영숫자 키워드를 스스로 정하거나, `slug` 부분을 생략하여 `P-00042.md`로 해도 좋다 (`P-` 코드가 있으면 고유).

## 조작

### 1. create — 신규 보고서 작성

1. **다음 ID를 정한다** (채번)
   - Bash로 `_products\` 하위의 모든 md에서 `id:`을 추출하고, max를 구해 +1 한다. 카운터 파일은 사용하지 않는다.
   - 원라이너 예 (Git Bash / PowerShell 양쪽을 상정하여 Python 사용):
     ```bash
     python -c "import re, pathlib; ids=[int(m.group(1)) for p in pathlib.Path(r'E:/OneDriveBiz/Obsidian/_products').rglob('*.md') for m in [re.search(r'^id:\s*(\d+)', p.read_text(encoding='utf-8'), re.M)] if m]; print(max(ids)+1 if ids else 1)"
     ```
   - 결과가 `42`이면 `code = P-00042`.

2. **파일 경로를 정한다**
   - `E:\OneDriveBiz\Obsidian\_products\<Category>\P-<NNNNN>_<slug>.md`

3. **frontmatter + 본문을 Write로 쓴다** (아래 "frontmatter 템플릿 (메인)"을 복사해서 채운다)

4. **필요하면 Bases를 다시 읽어 달라**고 사용자에게 완료 보고 시 코드 (예: `P-00042`)를 덧붙인다. 대화 중에 `P-42 見といて`로 부를 수 있는 것이 본 설계의 장점.

### 2. attach — 부수 자료 추가

1. 메인과 같은 카테고리 폴더 바로 아래에 `P-<NNNNN>_<slug>_<asset>.md`을 만든다 (`<asset>`는 자료명 slug).
2. frontmatter는 "frontmatter 템플릿 (부수 자료)"를 사용한다. `type: product_asset`과 `parent_code: "P-<NNNNN>"` 필수.
3. 메인 보고서에 wikilink를 추가한다:
   ```markdown
   ## 付随資料
   - [[P-00042_aff-recipe-v2_spec]] — 仕様書
   - [[P-00042_aff-recipe-v2_data]] — 元データ
   ```
   Obsidian이 자동으로 링크화한다 (Base의 표에는 `type: product_asset`이므로 표시되지 않는다).

### 3. update — 기존 보고서 업데이트

1. 대상 파일을 Read.
2. frontmatter를 Edit로 고쳐 쓰고, 반드시 `updated:`을 현재 일시(JST)로 업데이트.
3. 상태 전이(`未着手` → `進行中` → `監査待`)를 여기서 수행한다. `完了`로 변경할 수 있는 것은 sakura만. `confirmed`는 인간 확인용이므로, Anima는 신규 작성·업데이트 시 원칙적으로 `false` 그대로 두고, `true`로 변경하지 않는다.
4. `id`과 `code`는 **절대 변경하지 않는다**.

### 4. list — 기존 보고서 목록

Bash에서의 간이 리스트업:
```bash
grep -rH "^code:" "E:/OneDriveBiz/Obsidian/_products/" | sort
```
본격적인 뷰는 Obsidian 측에서 `0_Products DB.base`을 열면 된다.

## frontmatter 템플릿 (메인, 복사용)

```yaml
---
type: product
id: 42
code: "P-00042"
title: "アフィリエイト配信レシピ v2"
category: Finance              # General | Finance | Affiliate | Property | Business
product_type: 報告書            # 報告書 | 成果物 | デプロイ記録 | その他
status: 監査待                  # 未着手 | 進行中 | 監査待 | 完了（完了にできるのは sakura のみ）
task_code: AFF-001             # 対応するタスクコードがあれば。無ければ空文字 ""
assignee: 自分のAnima名          # 作成した Anima 名
submitted: 2026-04-23
requires_reply: false           # 人間からの返信・確認を待ちたい場合 true
confirmed: false                # 人間側が確認して落着済みなら true（基本は人間が後でチェック）
created: 2026-04-23T09:15:00+09:00
updated: 2026-04-23T09:15:00+09:00
tags: [product]
---

# アフィリエイト配信レシピ v2

## 要旨
...

## 本文
...

## 付随資料
- [[P-00042_aff-recipe-v2_spec]] — 仕様書
```

## frontmatter 템플릿 (부수 자료, 복사용)

```yaml
---
type: product_asset
parent_code: "P-00042"
title: "アフィリエイト配信レシピ v2 — 仕様書"
created: 2026-04-23T09:15:00+09:00
updated: 2026-04-23T09:15:00+09:00
tags: [product-asset]
---

# アフィリエイト配信レシピ v2 — 仕様書

（本文）
```

## 규약 정리

- **Vault 일원화**: 산출물도 초안도 `_products\<Category>\`에 둔다 (초안은 `status: 未着手`에서 작성, 완료 시 `status: 完了`로 업데이트). 구 `E:\OneDriveBiz\Downloads\`은 폐지
- **ID 불변·code로 부르기**: 작성 후에는 `id`/`code`을 바꾸지 않는다. 대화에서는 `P-00042` 형식으로 부른다
- **frontmatter는 파일 선두에 1개만**: 선두는 반드시 `---` → `type: product`을 포함하는 YAML → `---` → 본문 순으로 한다. `--- confirmed: ... ---` 같은 작은 frontmatter를 선두에 추가해서는 안 된다
- **저장은 UTF-8 BOM 없이**: Markdown은 UTF-8 without BOM으로 저장한다. PowerShell 5의 `Set-Content -Encoding UTF8`은 BOM을 붙이기 쉬우므로 피하고, PowerShell 7의 `utf8NoBOM`, Python의 `encoding="utf-8"`, 또는 `.NET UTF8Encoding(false)`를 사용한다
- **`status: 完了`로 할 수 있는 것은 sakura만**: sakura 이외의 Anima는 보고서 작성을 마치고 `_products\<Category>\`에 저장하면 `status: 監査待`로 한다. 완료 처리로의 변경은 sakura의 감사 후에 수행한다
- **감사 의뢰를 반드시 낸다**: sakura 이외의 Anima는 `status: 監査待`로 한 후, sakura 앞으로 `P-<NNNNN>`와 파일 경로, 감사해 주었으면 하는 관점을 덧붙여 감사 의뢰를 보낸다
- **`confirmed`은 인간 측 확인 플래그**: Anima는 신규 보고서를 `confirmed: false`로 만든다. 인간이 Obsidian 상에서 확인 후 true로 바꾼다. Anima가 `confirmed: true`를 선두에 추가·덮어쓰기해서는 안 된다
- **부수 자료는 하위 폴더를 만들지 않고 같은 폴더에 나열**: 파일명 프리픽스로 부모-자식 관계를 표현
- **wikilink 권장**: 내부 링크는 `[[P-00042_xxx_yyy]]` 표기. 경로를 쓰지 않는다 (Obsidian이 자동 해결)
- **`type: product` / `type: product_asset`의 구별**: Base 표는 메인만을 수집한다. 부수 자료는 wikilink 경유로 추적할 수 있으면 된다
- **일본어 가능**: `title`, `product_type`, `status`은 일본어 그대로. `category`만은 영문 (폴더명과의 일치를 위해)

## 운용 예

### 시나리오: 주간 보고서를 작성했다

1. 다음 ID를 채번: 예로서 `43`
2. `E:\OneDriveBiz\Obsidian\_products\General\P-00043_weekly-report-2026w17.md`에 Write (frontmatter 포함)
3. 원데이터 CSV의 요약을 붙인다: `..._data.md`를 만들어 wikilink 추가
4. 상급자에게 `send_message(intent="report", content="P-00043 週次レポートを提出しました。")`로 알림

### 시나리오: 작업 수령 → 진행 중 → 완료

1. 작업 수령 시 `status: 未着手`로 뼈대만 작성 (나중에 채움)
2. 착수하면 `status: 進行中`로 Edit, `updated` 업데이트
3. 보고서를 다 쓰면 sakura 이외는 `status: 監査待`, `submitted` 날짜를 넣고 본문을 마무리
4. sakura에 `P-<NNNNN>`와 파일 경로를 덧붙여 감사 의뢰를 보낸다
5. sakura가 감사 후 필요하면 수정하고, 문제없으면 `status: 完了`로 한다
6. `requires_reply: true`로 하여 인간 확인 대기로 하는 경우도 있다
