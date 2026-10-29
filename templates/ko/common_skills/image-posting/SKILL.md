---
name: image-posting
description: >-
  채팅 응답에 이미지를 임베딩하여 표시하는 스킬. 도구 결과의 URL 감지, Markdown 이미지 구문, assets 하위의 표시 절차를 다룬다.
  Use when: 검색·생성 도구의 이미지를 답변에 포함하거나, Markdown으로 이미지를 첨부하거나, 첨부 파일을 표시할 때.
---


# image-posting — 채팅 응답에 이미지 표시

## 개요

채팅 응답에 이미지를 포함하는 메커니즘은 두 가지 계열이 있다:

1. **도구 결과에서 자동 추출** — 도구 결과에 이미지 URL이나 경로가 포함되면 프레임워크가 자동으로 감지하여 채팅 버블에 표시한다
2. **Markdown 이미지 구문** — 응답 텍스트 내에 `![alt](url)`를 작성하면 프론트엔드가 렌더링한다

## 방법 1: 도구 결과에서 자동 표시

도구(web_search, image_gen 등)를 호출한 결과에 이미지 정보가 포함되어 있으면 프레임워크가 자동으로 채팅 버블에 이미지를 표시한다. Anima 쪽에서 특별한 조작은 필요 없다.

### 자동 감지 조건

도구 결과의 JSON 내에서 다음이 감지되면 이미지로 처리된다:

- **경로 감지**: `path`, `file`, `filepath`, `asset_path` 키의 값, 또는 결과 문자열 내에 `assets/` / `attachments/`로 시작하는 경로(`.png` `.jpg` `.jpeg` `.gif` `.webp`) → `source: generated`(신뢰됨)
- **URL 감지**: `url`, `image_url`, `thumbnail`, `src` 키에 이미지 URL이 있는 경우 → `source: searched`(프록시 경유, 허용 도메인만)
- **image_gen 전용**: 도구 결과 전체를 정규 표현식으로 검색하여 `assets/` 또는 `attachments/`을 포함하는 경로를 자동 추출

응답 1개당 최대 5장까지.

### image_gen 도구의 구현과 파이프라인

- **엔트리**: `core/integrations/image_gen.py`의 `dispatch()`이 `generate_character_assets` 외 각 도구 이름을 처리한다. GLB 관련 테스트용 가변 속성(`_FBX2GLTF_PATH` 등)은 `_image_glb`로 프록시되는 파사드이기도 하다.
- **일괄 생성의 본체**: `core/integrations/_image_pipeline.py`의 `ImageGenPipeline.generate_all()`이 7단계를 오케스트레이션한다.
- **API 클라이언트·상수·프롬프트**: `core/integrations/image/`(예: `novelai.py`, `fal.py`, `meshy.py`, `constants.py`의 `NOVELAI_MODEL` / `_DEFAULT_ANIMATIONS`, `prompts.py`의 표정용 프롬프트).

**7단계의 내용**(애니메이션 계열에서 `steps` 미지정 시 풀 파이프라인):

1. **fullbody** — **애니메이션**(`image_style`이 `realistic` 이외): `NOVELAI_TOKEN`이 있으면 NovelAI(`NOVELAI_MODEL` = `nai-diffusion-4-5-full`). 없으면 `FAL_KEY`이 있으면 Fal Flux Pro. 둘 다 없으면 오류. **리얼리스틱**: 항상 Fal Flux Pro만(`FAL_KEY` 필수. NovelAI로 폴백하지 않음). `config.image_gen`의 `style_prefix` / `style_suffix` / `negative_prompt_extra`, `style_reference`(이미지 바이트) 및 Vibe Transfer용 `vibe_strength` / `vibe_info_extracted`가 여기서 반영된다.
2. **bustup** — Flux Kontext(fal)로 버스트업. **표정 이름**은 `core.schemas.VALID_EMOTIONS`(`neutral`, `smile`, `laugh`, `troubled`, `surprised`, `thinking`, `embarrassed`)만 유효. 기본적으로 위 전체를 생성. `neutral`은 전신 참조에서, 그 외는 가능하면 중립 버스트를 참조(없으면 전신으로 폴백). 리얼/애니메이션에서 별도 프롬프트·가이던스(`prompts.py`).
3. **icon** — 중립 버스트를 참조하여 Flux Kontext로 정사각형 아이콘. 성공 시 `persist_anima_icon_path_template()`로 아이콘 패스 템플릿을 업데이트하려고 시도(실패해도 처리는 계속).
4. **chibi** — 전신을 참조하여 Flux Kontext로 치비 캐릭터 이미지.
5. **3d** — Meshy Image-to-3D(기본 `ai_model`: `meshy-6`)로 chibi에서 `avatar_chibi.glb`.
6. **rigging** — 파이프라인 내에서는 **직전 Image-to-3D의 `task_id`에서** `create_rigging_task`로 리깅(`input_task_id` 경유). 리그 완료 GLB 저장 후 `optimize_glb`, 부속 보행 등은 `download_rigging_animations`로 `anim_*.glb`화(가능하면 `strip_mesh_from_glb`). **단독 도구** `generate_rigged_model` / `generate_animations`의 `dispatch` 쪽은 기존 GLB를 data URI로 만들어 `MESHY_RIGGING_URL`로 POST하는 경로(파이프라인 6과 입력 경로가 다르다는 점에 주의).
7. **animations** — `animations` 인수가 전달되지 않으면 `_DEFAULT_ANIMATIONS`(`idle`, `sitting`, `waving`, `talking` 및 Meshy 액션 ID). 동일 실행에서 리깅하지 않은 경우, 기존 `avatar_chibi.glb`에서 `create_rigging_task_from_glb`로 `rig_task_id`을 다시 가져온 후 추가 애니메이션을 생성한다.

**리얼리스틱 스타일**(`config.image_gen.image_style == "realistic"`)에서는 `steps` 미지정 시 **기본 유효 단계는 `fullbody` / `bustup` / `icon`만**(chibi·3D·리깅·추가 애니메이션은 기본적으로 실행되지 않음). `dispatch`의 `generate_character_assets`에서는 프롬프트가 Danbooru 스타일 태그로 보이는 경우 `_looks_like_anime_prompt`에 의해 `_convert_anime_to_realistic`로 리얼용으로 자동 변환될 수 있다.

**스타일 참조(Vibe Transfer)**: `ImageGenPipeline`은 `config.style_reference`의 경로(존재 시)를 전신 생성에 전달한다. 추가로 `generate_character_assets`에서 `supervisor_name`이 지정되고, 상급자의 `assets/`에 `avatar_fullbody.png` 또는 `avatar_fullbody_realistic.png`(스타일에 따라)가 있으면 그것을 `style_reference`으로 덮어써서 로드한다. `generate_all()`에는 `vibe_image` / `vibe_strength` / `vibe_info_extracted` / `seed` / `expressions` / `steps` / `progress_callback` 등도 있지만, **현재의 `dispatch`가 도구 인수로 전달하는 것은** `prompt`, `negative_prompt`, `skip_existing`, `steps`, `animations`, `supervisor_name`(및 핸들러 주입의 `anima_dir`)에 한정된다.

**`generate_fullbody`(단독)**: `dispatch` 구현은 **항상 `NovelAIClient`만**(환경에 Fal이 있어도 폴백하지 않음). `image_style`도 참조하지 않음. 출력은 항상 `avatar_fullbody.png`. 리얼리스틱용 전신이나 파이프라인 정합이 필요하면 **`generate_character_assets`를 사용**.

### `generate_character_assets`의 반환값(JSON)

`PipelineResult.to_dict()`에 해당하는 키(경로는 문자열, 없으면 `null`):

| 키 | 내용 |
|------|------|
| `fullbody` | 전신 PNG |
| `bustup` | 대표 버스트업(보통 중립) |
| `bustup_expressions` | 표정 이름 → 경로의 사전 |
| `icon` | 채팅 아이콘 PNG |
| `chibi` | 치비 이미지 PNG |
| `model` | `avatar_chibi.glb` |
| `rigged_model` | 리깅 완료 GLB |
| `animations` | 애니메이션 이름 → GLB 경로 |
| `errors` / `skipped` | 오류 문장의 배열 / 건너뛴 단계 이름 |

PNG의 경로는 채팅 자동 표시 대상. GLB는 에셋 저장·작업 공간 등에서 별도 취급.

### 출력 파일 이름 대응표

**파이프라인(애니메이션 `image_style`)**

| 단계 | 출력 예 | 채팅 자동 표시 |
|----------|--------|------------------|
| fullbody | `avatar_fullbody.png` | ○ |
| bustup | `avatar_bustup.png`(중립), `avatar_bustup_smile.png` 등 | ○ |
| icon | `icon.png` | ○ |
| chibi | `avatar_chibi.png` | ○ |
| 3d | `avatar_chibi.glb` | — |
| rigging | `avatar_chibi_rigged.glb`, `anim_*.glb`(보행 등) | — |
| animations | `anim_idle.glb`, `anim_sitting.glb`, … | — |

**파이프라인(리얼리스틱)** — 전신·버스트·표정·아이콘은 파일 이름 끝에 `_realistic`이 붙는다:

- 전신: `avatar_fullbody_realistic.png`
- 중립 버스트: `avatar_bustup_realistic.png`
- 표정: `avatar_bustup_smile_realistic.png` 등(`bustup_expressions`로 집약)
- 아이콘: `icon_realistic.png`

**단독 디스패치**(`dispatch` 내의 개별 도구)

| 도구 이름 | 출력 | 채팅 자동 표시 | 비고 |
|----------|------|------------------|------|
| `generate_fullbody` | `avatar_fullbody.png` | ○ | **NovelAI만**(`NOVELAI_TOKEN`). Fal 폴백·`image_style` 미지원. 파일 이름 고정 |
| `generate_bustup` | `avatar_bustup.png` | ○ | 참조는 `avatar_fullbody.png`만 |
| `generate_icon` | `icon.png` / `icon_realistic.png` | ○ | 참조 버스트는 설정의 `image_style`에 따른 파일 이름 |
| `generate_chibi` | `avatar_chibi.png` | ○ | 참조는 `avatar_fullbody.png`만 |
| `generate_3d_model` | `avatar_chibi.glb` | — | |
| `generate_rigged_model` | `avatar_chibi_rigged.glb` + `animations` 사전 | — | GLB를 data URI로 Meshy 리깅 API에 전송 |
| `generate_animations` | `animations` 사전(`anim_*.glb`) | — | 기존 `avatar_chibi.glb`에서 리그 작업을 가져와 생성 |

기본 추가 애니메이션 이름과 Meshy 액션 ID(파이프라인 `animations` 단계): `idle: 0`, `sitting: 32`, `waving: 28`, `talking: 307`(`animations` 인수로 덮어쓰기 가능).

### 검색 이미지의 프록시 제한

외부 URL 이미지는 보안을 위해 프록시를 경유하여 배포된다. **아티팩트 추출 시점**에 다음 허용 도메인만 감지 대상이 된다:

- `cdn.search.brave.com`
- `images.unsplash.com`
- `images.pexels.com`
- `upload.wikimedia.org`

위 이외의 도메인 URL은 도구 결과에 포함되어 있어도 자동 표시되지 않는다. 프록시 자체는 HTTPS 강제·private/local 거부·magic bytes 검증·SVG 거부·크기·레이트 제한 등의 안전 검사를 실시한다(`config.server.media_proxy`에서 `open_with_scan` / `allowlist` 모드를 전환 가능).

## 방법 2: Markdown 이미지 구문

응답 텍스트 내에 Markdown 이미지 구문을 직접 작성하여 이미지를 표시한다.

### 단축 경로(권장)

프론트엔드가 자동으로 자신의 Anima 이름으로 API 경로를 보완한다. 파일 이름만 쓰면 OK:

```
![説明](attachments/ファイル名)
![説明](assets/ファイル名)
```

예:

```
スクショ撮りました！
![ANAトップページ](attachments/ana_top.png)
```

### 전체 경로

명시적으로 API 경로를 작성할 수도 있다:

```
![説明](/api/animas/{自分の名前}/assets/{ファイル名})
![説明](/api/animas/{自分の名前}/attachments/{ファイル名})
```

## 스크린샷 저장 위치

agent-browser 등으로 스크린샷을 촬영하는 경우, **자신의 attachments 디렉터리에 직접 저장**하는 것이 확실하다:

```bash
agent-browser screenshot ~/.animaworks/animas/{自分の名前}/attachments/screenshot.png
```

예(aoi의 경우):

```bash
agent-browser screenshot ~/.animaworks/animas/aoi/attachments/page_screenshot.png
```

저장 후 응답에 다음을 작성하면 표시된다:

```
![ページのスクショ](attachments/page_screenshot.png)
```

`~/.animaworks/tmp/attachments/`에 저장한 경우도 폴백으로 표시되지만, 임시 디렉터리이므로 영속성은 보장되지 않는다.

## 주의 사항

- 다른 Anima의 에셋 경로는 직접 참조할 수 없다(권한 외)
- 외부 URL의 직접 링크는 비권장. 허용 도메인 외는 자동 표시되지 않고, 프록시의 안전 검사에서 차단될 수 있다
- `generate_character_assets`의 결과는 `fullbody` / `bustup` / `bustup_expressions` / `icon` / `chibi` 등의 경로가 JSON에 포함되므로 PNG는 자동 표시되고, Markdown 구문이 필요 없는 경우가 많다
- 단독의 `generate_bustup` / `generate_chibi`은 참조가 **`avatar_fullbody.png` 고정**(리얼리스틱용 `avatar_fullbody_realistic.png`는 읽지 않음). 단독 `generate_fullbody`은 위 표대로 NovelAI 전용이며, 파이프라인의 리얼리스틱 전신과 파일 이름·생성 경로가 맞지 않는다. 파이프라인과 단독 도구를 혼용하는 경우 `assets/`의 실제 파일을 확인할 것
- 이미지 생성은 처리 시간이 길다. 프레임워크에서는 전용 스레드 풀 실행·백그라운드 도구 설정의 대상이 된다. CLI에서는 `animaworks-tool submit image_gen …` 등의 비동기 실행이 권장되는 경우가 있다(`common_knowledge/operations/background-tasks.md` 등을 참조)
- 응답 1개당 자동 표시는 최대 5장
