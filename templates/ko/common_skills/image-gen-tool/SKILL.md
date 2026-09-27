---
name: image-gen-tool
description: >-
  이미지・3D 모델 생성 도구. NovelAI・Flux・Meshy로 서 있는 그림・버스트 업・치비・3D 모델을 생성한다.
  Use when: 일러스트 생성, 캐릭터 이미지 제작, 3D 모델・Meshy 출력, 이미지 파이프라인 실행이 필요할 때.
tags: [image, 3d, generation, external]
---
Understood. Please provide the Japanese content you would like me to translate into Korean.# Image Gen 도구

캐릭터 이미지・3D 모델을 생성하는 외부 도구.## 호출 방법

**Bash**: `animaworks-tool image_gen <サブコマンド> [引数]`에서 실행. 장시간 처리는 `animaworks-tool submit image_gen pipeline ...`에서 백그라운드 실행.## 작업 목록### character_assets — 파이프라인 일괄 생성
```bash
animaworks-tool image_gen pipeline "1girl, ..." --anima-dir $ANIMAWORKS_ANIMA_DIR
```
### fullbody — 전신 입상
```bash
animaworks-tool image_gen fullbody "1girl, standing, ..."
```
### bustup — 가슴 확대
```bash
animaworks-tool image_gen bustup reference.png
```
### chibi — 치비 캐릭터
```bash
animaworks-tool image_gen chibi reference.png
```
### 3d_model — 3D 모델 생성
```bash
animaworks-tool image_gen 3d image.png
```
## CLI 사용법

```bash
animaworks-tool image_gen pipeline "1girl, ..." --anima-dir $ANIMAWORKS_ANIMA_DIR
animaworks-tool image_gen fullbody "1girl, standing, ..."
animaworks-tool image_gen bustup reference.png
animaworks-tool image_gen chibi reference.png
animaworks-tool image_gen 3d image.png
```
## 주의사항

- 장시간 처리를 위해 `animaworks-tool submit image_gen pipeline ...`에서 백그라운드 실행 권장
- NovelAI API 키 또는 fal.ai API 키 필요
- 3D 생성에는 Meshy API 키 필요