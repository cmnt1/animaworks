---
name: image-posting
description: >-
  A skill for embedding and displaying images in chat responses. It handles URL detection from tool results, Markdown image syntax, and the display procedure for files under the assets directory.
  Use when: Use when: including images from search or generation tools in replies, inserting images with Markdown, or displaying attached files.
---
Understood. Please provide the Japanese content you’d like translated, and I’ll follow all the specified rules.# image-posting — Displaying images in chat responses## Overview

There are two mechanisms for including images in chat responses:

1. **Automatic extraction from tool results** — When tool results contain image URLs or paths, the framework automatically detects them and displays them in chat bubbles
2. **Markdown image syntax** — Writing `![alt](url)` in the response text causes the frontend to render it## Method 1: Automatic Display from Tool Results

If the results of a tool call (web_search, image_gen, etc.) include image information, the framework will automatically display the image in the chat bubble. No special operation is required on the Anima side.### Automatically Detected Conditions

The following are treated as images when detected in the tool result JSON:

- **Path detection**: Values of the `path`, `file`, `filepath`, `asset_path` keys, or paths in the result string starting with `assets/` / `attachments/` (`.png` `.jpg` `.jpeg` `.gif` `.webp`) → `source: generated` (trusted)
- **URL detection**: When image URLs are present in the `url`, `image_url`, `thumbnail`, `src` keys → `source: searched` (via proxy, allowed domains only)
- **image_gen only**: The entire tool result is scanned with a regular expression, and paths containing `assets/` or `attachments/` are automatically extracted

Up to 5 images per response.### Implementation of the image_gen tool and pipeline

- **Entry**: `core/integrations/image_gen.py`'s `dispatch()` processes `generate_character_assets` and other tool names. It is also a facade that proxies test-related mutable attributes for GLB (such as `_FBX2GLTF_PATH`) to `_image_glb`.
- **Batch generation core**: `core/integrations/_image_pipeline.py`'s `ImageGenPipeline.generate_all()` orchestrates 7 steps.
- **API client, constants, and prompts**: `core/integrations/image/` (e.g., `novelai.py`, `fal.py`, `meshy.py`, `constants.py`'s `NOVELAI_MODEL` / `_DEFAULT_ANIMATIONS`, `prompts.py`'s expression prompts).

**Content of the 7 steps** (for the full pipeline in anime style when `steps` is unspecified):

1. **fullbody** — **Anime** (when `image_style` is not `realistic`): if `NOVELAI_TOKEN` exists, use NovelAI (`NOVELAI_MODEL` = `nai-diffusion-4-5-full`). If not, and `FAL_KEY` exists, use Fal Flux Pro. If neither exists, raise an error. **Realistic**: always use Fal Flux Pro only (`FAL_KEY` required; no fallback to NovelAI). `config.image_gen`'s `style_prefix` / `style_suffix` / `negative_prompt_extra`, `style_reference` (image bytes), and `vibe_strength` / `vibe_info_extracted` for Vibe Transfer are reflected here.
2. **bustup** — Bust-up via Flux Kontext (fal). **Expression names** are valid only for `core.schemas.VALID_EMOTIONS` (`neutral`, `smile`, `laugh`, `troubled`, `surprised`, `thinking`, `embarrassed`). By default, all of the above are generated. `neutral` references the full-body image; others reference a neutral bust if possible (falling back to full-body if unavailable). Separate prompts and guidance for realistic/anime (`prompts.py`).
3. **icon** — Square icon via Flux Kontext referencing the neutral bust. On success, attempt to update the icon paste template with `persist_anima_icon_path_template()` (continue even if it fails).
4. **chibi** — Chibi character image via Flux Kontext referencing the full-body image.
5. **3d** — Meshy Image-to-3D (default `ai_model`: `meshy-6`) from chibi to produce `avatar_chibi.glb`.
6. **rigging** — Within the pipeline, rig from **the immediately preceding Image-to-3D's `task_id`** via `create_rigging_task` (through `input_task_id`). After saving the rigged GLB, `optimize_glb`; attached walk cycles etc. are converted to `anim_*.glb` via `download_rigging_animations` (using `strip_mesh_from_glb` if possible). **Standalone tool** `generate_rigged_model` / `generate_animations`'s `dispatch` side uses a route that converts an existing GLB to a data URI and POSTs it to `MESHY_RIGGING_URL` (note that the input route differs from pipeline step 6).
7. **animations** — If the `animations` argument is not provided, use `_DEFAULT_ANIMATIONS` (`idle`, `sitting`, `waving`, `talking` and Meshy action IDs). If rigging was not performed in the same run, re-fetch `rig_task_id` from the existing `avatar_chibi.glb` via `create_rigging_task_from_glb` before generating additional animations.

**Realistic style** (`config.image_gen.image_style == "realistic"`): when `steps` is unspecified, the **default enabled steps are `fullbody` / `bustup` / `icon` only** (chibi, 3D, rigging, and additional animations do not run by default). In `dispatch`'s `generate_character_assets`, if the prompt looks like Danbooru-style tags, `_looks_like_anime_prompt` may automatically convert it via `_convert_anime_to_realistic` for realistic use.

**Style reference (Vibe Transfer)**: `ImageGenPipeline` passes the path of `config.style_reference` (if it exists) to full-body generation. Additionally, if `supervisor_name` is specified via `generate_character_assets` and the supervisor's `assets/` contains `avatar_fullbody.png` or `avatar_fullbody_realistic.png` (depending on style), it is loaded as an override for `style_reference`. `generate_all()` also includes `vibe_image` / `vibe_strength` / `vibe_info_extracted` / `seed` / `expressions` / `steps` / `progress_callback`, but **the current `dispatch` passes only** `prompt`, `negative_prompt`, `skip_existing`, `steps`, `animations`, `supervisor_name` (and handler-injected `anima_dir`) from tool arguments.

**`generate_fullbody` (standalone)**: The `dispatch` implementation is **always `NovelAIClient` only** (no fallback even if Fal is available in the environment). It also does not reference `image_style`. Output is always `avatar_fullbody.png`. If a realistic full-body or pipeline consistency is needed, **use `generate_character_assets`**.### Return value of `generate_character_assets` (JSON)

Keys equivalent to `PipelineResult.to_dict()` (paths are strings, or `null` if absent):

| Key | Description |
|------|------|
| `fullbody` | Full-body PNG |
| `bustup` | Representative bust-up (usually neutral) |
| `bustup_expressions` | Dictionary of expression name → path |
| `icon` | Chat icon PNG |
| `chibi` | Chibi image PNG |
| `model` | `avatar_chibi.glb` |
| `rigged_model` | Rigged GLB |
| `animations` | Animation name → GLB path |
| `errors` / `skipped` | Array of error messages / names of skipped steps |

PNG paths are targets for automatic chat display. GLB files are handled separately for asset storage, workspace, etc.### Output File Name Correspondence Table

**Pipeline (Anime `image_style`)**

| Step | Output Example | Auto-Display in Chat |
|----------|--------|------------------|
| fullbody | `avatar_fullbody.png` | ○ |
| bustup | `avatar_bustup.png` (neutral), `avatar_bustup_smile.png`, etc. | ○ |
| icon | `icon.png` | ○ |
| chibi | `avatar_chibi.png` | ○ |
| 3d | `avatar_chibi.glb` | — |
| rigging | `avatar_chibi_rigged.glb`, `anim_*.glb` (walking, etc.) | — |
| animations | `anim_idle.glb`, `anim_sitting.glb`, … | — |

**Pipeline (Realistic)** — Full body, bust, expression, and icon files have `_realistic` appended to the end of the file name:

- Full body: `avatar_fullbody_realistic.png`
- Neutral bust: `avatar_bustup_realistic.png`
- Expressions: `avatar_bustup_smile_realistic.png`, etc. (consolidated into `bustup_expressions`)
- Icon: `icon_realistic.png`

**Standalone Dispatch** (individual tools within `dispatch`)

| Tool Name | Output | Auto-Display in Chat | Notes |
|----------|------|------------------|------|
| `generate_fullbody` | `avatar_fullbody.png` | ○ | **NovelAI only** (`NOVELAI_TOKEN`). Fal fallback and `image_style` not supported. Fixed file name |
| `generate_bustup` | `avatar_bustup.png` | ○ | Reference uses `avatar_fullbody.png` only |
| `generate_icon` | `icon.png` / `icon_realistic.png` | ○ | Reference bust uses file name based on `image_style` in configuration |
| `generate_chibi` | `avatar_chibi.png` | ○ | Reference uses `avatar_fullbody.png` only |
| `generate_3d_model` | `avatar_chibi.glb` | — | |
| `generate_rigged_model` | `avatar_chibi_rigged.glb` + `animations` dictionary | — | Sends GLB as data URI to Meshy rigging API |
| `generate_animations` | `animations` dictionary (`anim_*.glb`) | — | Retrieves rig task from existing `avatar_chibi.glb` to generate |

Default additional animation names and Meshy action IDs (pipeline `animations` step): `idle: 0`, `sitting: 32`, `waving: 28`, `talking: 307` (can be overridden with `animations` argument).### Searched Image Proxy Restrictions

External URL images are served through a proxy for security. **At the time of artifact extraction**, only the following allowed domains are detected:

- `cdn.search.brave.com`
- `images.unsplash.com`
- `images.pexels.com`
- `upload.wikimedia.org`

URLs from domains other than those above will not be automatically displayed even if included in tool results. The proxy itself performs safety checks such as HTTPS enforcement, private/local rejection, magic bytes validation, SVG rejection, size and rate limiting (the `config.server.media_proxy` setting allows switching between `open_with_scan` / `allowlist` modes).## Method 2: Markdown Image Syntax

Display images by writing Markdown image syntax directly in the response text.### Shortened Path (Recommended)

The frontend automatically completes the API path with its own Anima name. Just write the file name:

```
![説明](attachments/ファイル名)
![説明](assets/ファイル名)
```

Example:

```
スクショ撮りました！
![ANAトップページ](attachments/ana_top.png)
```
### Full Path

You can also write the API path explicitly:

```
![説明](/api/animas/{自分の名前}/assets/{ファイル名})
![説明](/api/animas/{自分の名前}/attachments/{ファイル名})
```
## Screenshot save location

When taking screenshots with agent-browser or similar tools, it is reliable to **save them directly to your own attachments directory**:

```bash
agent-browser screenshot ~/.animaworks/animas/{自分の名前}/attachments/screenshot.png
```

Example (for aoi):

```bash
agent-browser screenshot ~/.animaworks/animas/aoi/attachments/page_screenshot.png
```

After saving, write the following in your response to display it:

```
![ページのスクショ](attachments/page_screenshot.png)
```

If saved to `~/.animaworks/tmp/attachments/`, it will also be displayed as a fallback, but since it is a temporary directory, persistence is not guaranteed.## Notes

- Other Anima asset paths cannot be referenced directly (outside permission)
- Direct links to external URLs are not recommended. Content outside the allowed domains will not be displayed automatically and may be blocked by the proxy's safety check
- The result of `generate_character_assets` includes paths such as `fullbody` / `bustup` / `bustup_expressions` / `icon` / `chibi` in the JSON, so PNGs are displayed automatically and Markdown syntax is often unnecessary
- Standalone `generate_bustup` / `generate_chibi` references are **fixed to `avatar_fullbody.png`** (the `avatar_fullbody_realistic.png` for realistic use is not read). Standalone `generate_fullbody` is NovelAI-only as shown in the table above, and its file name and generation path do not match the pipeline's realistic full-body output. If mixing the pipeline and standalone tools, check the actual file of `assets/`
- Image generation takes a long time. In the framework, it is subject to dedicated thread pool execution and background tool configuration. From the CLI, asynchronous execution such as `animaworks-tool submit image_gen …` may be recommended (see `common_knowledge/operations/background-tasks.md` etc.)
- Maximum of 5 images displayed automatically per response