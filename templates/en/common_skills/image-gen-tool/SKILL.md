---
name: image-gen-tool
description: >-
  An image and 3D model generation tool. It generates character portraits, bust-up shots, chibi versions, and 3D models using NovelAI, Flux, and Meshy.
  Use when: Use when: illustration generation, character image creation, 3D model and Meshy output, or image pipeline execution is needed.
tags: [image, 3d, generation, external]
---
Understood. I’m ready to translate the Japanese content into natural English while preserving all Markdown structure, headings, tables, links, identifiers, sentinels (including ⟦§number⟧ markers), and YAML frontmatter keys. I’ll keep the literal prefix “Use when:” unchanged and translate only exposed values. Please provide the content to translate.# Image Gen Tool

An external tool for generating character images and 3D models.## How to Call

**Bash**: Run with `animaworks-tool image_gen <サブコマンド> [引数]`. For long-running processes, execute in the background with `animaworks-tool submit image_gen pipeline ...`.## List of Actions### character_assets — Pipeline Batch Generation
```bash
animaworks-tool image_gen pipeline "1girl, ..." --anima-dir $ANIMAWORKS_ANIMA_DIR
```
### fullbody — Full-body Standing Illustration
```bash
animaworks-tool image_gen fullbody "1girl, standing, ..."
```
### Bust Enhancement
```bash
animaworks-tool image_gen bustup reference.png
```
### chibi — chibi character
```bash
animaworks-tool image_gen chibi reference.png
```
### 3d_model — 3D Model Generation
```bash
animaworks-tool image_gen 3d image.png
```
## CLI Usage

```bash
animaworks-tool image_gen pipeline "1girl, ..." --anima-dir $ANIMAWORKS_ANIMA_DIR
animaworks-tool image_gen fullbody "1girl, standing, ..."
animaworks-tool image_gen bustup reference.png
animaworks-tool image_gen chibi reference.png
animaworks-tool image_gen 3d image.png
```
## Notes

- Recommended for background execution in `animaworks-tool submit image_gen pipeline ...` due to long processing times
- Requires a NovelAI API key or fal.ai API key
- A Meshy API key is required for 3D generation