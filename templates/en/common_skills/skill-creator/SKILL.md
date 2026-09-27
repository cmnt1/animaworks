---
name: skill-creator
description: >-
  A meta-skill for creating Markdown skills. It covers the frontmatter and body of SKILL.md, Progressive Disclosure, and the create_skill procedure.
  Use when: Use when: adding new skills, checking description rules for read_memory_file, or generating skills with references or templates.
---
Understood. I’m ready to translate the Japanese content into natural English while preserving all Markdown structure, headings, tables, links, identifiers, section markers (⟦§number⟧), YAML frontmatter keys, and the literal prefix “Use when:”. Please provide the content to translate.# skill-creator## Correspondence with Implementation

| Role | Module |
|------|------------|
| `read_memory_file` Tool (reads body text by specifying relative path of skill/procedure) | Via `ToolHandler` (file in memory tree) |
| Skill catalog in system prompt (with path list and budget) | Prompt construction (e.g., `skills/foo/SKILL.md`, `common_skills/bar/SKILL.md`, `procedures/baz.md`) |
| `create_skill` Tool (directory creation) | `core/tooling/skill_creator.py` |
| Schema (parameter definitions) | `core/tooling/schemas/skill.py` |
| Frontmatter parsing (line-based, avoiding mis-splitting at `---` in body) | `parse_frontmatter()` of `core/memory/frontmatter.py` |
| Metadata type and extraction (`SkillMeta`, procedure path estimation) | `core/schemas.py`, `SkillMetadataService.extract_skill_meta()` of `core/memory/skill_metadata.py` |
| Description-based skill metadata extraction (for catalog and search assistance) | `SkillMetadataService` of `core/memory/skill_metadata.py`, etc. |
| Gate line removal from `*-tool` body | `filter_gated_from_guide()` of `core/tooling/guide.py` |
| Allowed tool set (permissions) | `core/config/models.load_permissions()` + `core/tooling/permissions.get_permitted_tools()` |## Skill Types and Paths

Skills and procedures are managed in **separate layouts**.

| Type | Path | Notes |
|------|------|-------|
| Personal skill | `skills/{name}/SKILL.md` | Directory + `SKILL.md` |
| Common skill | `common_skills/{name}/SKILL.md` | At runtime, `~/.animaworks/common_skills/` etc. |
| Procedure | `procedures/{name}.md` | **Flat single file**. Not a directory |

What `create_skill` generates is only the **skill** (personal or common) in the table above. Procedures are created separately as `procedures/*.md` via `write_memory_file` etc.### Do not place symlinks (rule established 2026-09-04)

Under `common_skills/` or `skills/`, do not **repost** content via **symlinks** pointing to external locations (such as `~/.claude/skills`). Since `read_memory_file` checks boundaries at the actual file location, if the symlink target is outside, it will be unreadable due to "Path traversal detected." Additionally, the catalog registers that symlink as a native skill and hides the same-named external candidate, so Anima is only presented with paths it cannot read.

- Host-side skills (`~/.claude/skills`, `~/.codex/skills`, etc.) are automatically injected from configuration `skills.external_roots` and can be read at `external/<engine>/<name>/SKILL.md`. There is no need to repost them as common skills.
- If you must place them as common skills, copy the actual file and designate one of the two locations as the authoritative source.## Loading Skills with read_memory_file

The body of skills and procedures is read by specifying a **`read_memory_file(path="...")`** memory tree relative path. The system prompt's skill catalog shows the available paths (e.g., `skills/foo/SKILL.md`, `common_skills/bar/SKILL.md`, `procedures/baz.md`).

- **Personal skills**: `skills/{name}/SKILL.md`
- **Shared skills**: `common_skills/{name}/SKILL.md`
- **Procedures**: `procedures/{name}.md`

`path` is passed as a relative path based on the Anima directory (shared trees use prefixes like `common_skills/`).### Frontmatter and Body

SKILL.md The leading YAML is removed and read at `core/memory/frontmatter.parse_frontmatter()`. **The delimiter line `---` is recognized only on a per-line basis**, so even if `---` is included in YAML values or in the body text, it is unlikely to cause incorrect splitting.### Body Placeholder (`*-tool` Guide)

In the skill body, placeholders such as `{{now_local}}`, `{{anima_name}}`, and `{{anima_dir}}` may be used. Skills for external tools (those whose names end with `*-tool`) are gated by the `animaworks-tool` line depending on the permission configuration (e.g., `filter_gated_from_guide()` in `core/tooling/guide.py`).### Catalog and description

In **Level 1** of the skill catalog, `name` + `description` are included within the budget. The more skills there are, the more likely they are to be omitted, so keep **`description` short and specific**. When the full text is needed, open the catalog path with `read_memory_file`.

**Legacy compatibility**: When `description` is empty, `extract_skill_meta()` uses the **first non-empty line of the `## 概要` section** in the body as a fallback. For new skills, the frontmatter is authoritative.### Layout Notes

Under the individual `skills/`, the **`*.md` (flat single file)** may be subject to cataloging or meta-extraction, but the **recommended path is `skills/{name}/SKILL.md`**. In practice, the directory format based on `create_skill` is considered the standard.## Skill File Structure

SKILL.md consists of YAML frontmatter and Markdown body.
The frontmatter **requires** `name` and `description`.

`create_skill` can include not only `allowed_tools` but also metadata for trust, provenance, classification, and routing assistance. The required fields are `name` / `description` / `body`, and optional keys should only be used when their purpose is clear.

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

Main optional fields: `allowed_tools`, `trust_level`, `source_type`, `source_origin`, `category`, `promotion_status`, `skill_policy`, `use_when`, `trigger_phrases`, `negative_phrases`, `domains`, `routing_examples`. In the argument names of `create_skill`, `source.type` is passed as `source_type`, and `source.origin` is passed as `source_origin`.### Role of `description`

**Descriptions of new skills** follow the Agent Skills standard, and **`Use when:`** is used to describe use cases (see `references/description_guide.md` for details). After creation, the format can be validated with **`python scripts/lint_skill.py`**.

- **When reading with a path specified via `read_memory_file`**: If the file exists, the body is obtained **regardless of description matching** (frontmatter processing and handling related to `*-tool` depend on the loading path).
- **Skill catalog in the system prompt**: As Level 1, `name` + `description` are included with a budget. The full text is not included, so if procedures are needed, open them via **`read_memory_file(path="skills/.../SKILL.md")` or similar**.

**Legacy compatibility**: When `description` is empty, `extract_skill_meta()` uses the **first non-empty line of the `## 概要` section near the beginning of the body** as a fallback for the description. For new skills, treat frontmatter as authoritative and avoid relying on `## 概要`.

**How to write descriptions** (the **Use when:** pattern and lint) can be found in `references/description_guide.md`.## Progressive Disclosure

Skill information is generally disclosed in the following stages.

| Level | Content | Display timing |
|-------|------|----------------|
| Level 1 | `name` + `description` | Material for the skill catalog (within budget) in the system prompt |
| Level 2 | body (main text) | When the agent loads it via `read_memory_file(path="skills/.../SKILL.md")`, etc. |
| Level 3 | External resources | Following the instructions in the main text, read `references/` or `templates/` via `read_memory_file`, etc. as needed |

Level 1 tends to consume context in the catalog, so **keep the description concise**. Level 2 is the core of the procedure. Level 3 separates lengthy references.

※ The Priming skill main-text injection path has been deprecated. If the main text is needed, open the skill path via **`read_memory_file`**.## Creation Procedure### Step 1: Hearing

Understand the user's requirements. Confirm the following:

- What they want to automate or turn into a procedure
- Whether the target is a personal skill or a common skill (if it is a procedure, design separately for `procedures/`)
- The use case to write in **Use when:** (when to choose this skill)

Use when:### Step 2: Design

Decide on the following:

- **name**: Skill name (kebab-case, e.g., `my-skill`). If it's an external tool guide, consider the `*-tool` convention
- **description**: Third-person summary + **`Use when:`** line (see `references/description_guide.md`)
- **body**: Structure of the procedure (sectioning). Use placeholders like `{{now_local}}` if needed
- **references** / **templates**: Design external files if necessary
- **allowed_tools**: Only if you want to narrow down recommended tools
- **trust/source/category/policy/routing**: trust level, provenance, classification, prompt policy, `use_when` / `trigger_phrases` / `negative_phrases` / `domains` / `routing_examples` as needed

Use when: designing a new skill or reviewing an existing one.### Step 3: Creation

`create_skill` Create the skill as a directory structure using the tool.

**Basic (personal skills)**:

```
create_skill(skill_name="{name}", description="{description}", body="{body}")
```

**Common skills**:

```
create_skill(skill_name="{name}", description="{description}", body="{body}", location="common")
```

**When including references and templates**:

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

| Parameter | Required | Description |
|-----------|------|-------------|
| skill_name | ✓ | Skill name (kebab-case). `/`, `\`, `..` not allowed |
| description | ✓ | Frontmatter description (**Use when:** recommended. `references/description_guide.md`) |
| body | ✓ | SKILL.md body (Markdown). Built-in replacement target |
| location | | `personal` (default) or `common` |
| references | | Files placed in `references/`. `[{filename, content}, ...]` |
| templates | | Files placed in `templates/`. `[{filename, content}, ...]` |
| allowed_tools | | `allowed_tools` in frontmatter (optional) |
| trust_level | | Trust level such as `trusted` / `community` |
| source_type / source_origin | | Origin (e.g., `anima`, `manual`, `auto_created`) |
| category | | Classification tag |
| promotion_status | | Promotion status such as `probation` / `trusted` |
| skill_policy | | Prompt injection policy (`use_mode`, injection-related configuration) |
| use_when / trigger_phrases / negative_phrases / domains / routing_examples | | Auxiliary metadata to help the skill router select candidates |

`references` / `templates` Do not include path components in `filename`. `_validate_filename()` Verify that resolution does not go outside the parent directory; if invalid, **silently skip** (the file is not created).

※ For new skills, always use `create_skill`. `write_memory_file` Creating only a **single file directly under** something like `skills/foo.md` is **not recommended**. This format **cannot be opened in `read_memory_file(path="skills/foo/SKILL.md")`**, so the recommended approach is the directory format of `skills/foo/SKILL.md`.

※ The procedure is `procedures/{name}.md` (flat single file). For frontmatter, `name` / `description` (plus optional `allowed_tools`) is recommended, same as for skills.### Step 4: Confirmation

- **Individual skills**: Confirm content at `read_memory_file(path="skills/{name}/SKILL.md")`
- **Common skills**: Confirm via paths shown in the catalog, such as `read_memory_file(path="common_skills/{name}/SKILL.md")`
- **Procedures**: Confirm that `read_memory_file(path="procedures/{name}.md")` can resolve the issue
- Use `python scripts/lint_skill.py` to validate the frontmatter / description of `SKILL.md` (optional but recommended)## Checklist

Before saving, verify the following:

- [ ] YAML frontmatter starts with `---` and closes with `---`
- [ ] `name` field is present
- [ ] `description` field is present
- [ ] description contains **`Use when:`** and includes domain-specific concrete terms (do not use the old `「」` enumeration)
- [ ] **description is domain-specific and concrete** (avoid generic expressions like "perform management" or "check"; specify the tool name, operation name, and target)
- [ ] body contains concrete procedures
- [ ] For new items, place `description` in the frontmatter and **do not rely solely on `## 概要` for the description** (also avoid old template formats such as `## 発動条件`)
- [ ] Optional metadata (`trust_level`, `source`, `category`, `skill_policy`, `use_when`, `trigger_phrases`, `negative_phrases`, `domains`, `routing_examples`) matches actual usage
- [ ] Skills are created with `create_skill` using `{name}/SKILL.md` (verify the procedure works as intended with `procedures/*.md`)
## Template

Refer to `templates/skill_template.md` included with this skill. Alternatively, copy and use the following:

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

## Notes

- A skill is a Markdown procedure document, not Python code (a tool)
- The required frontmatter fields are `name` and `description`
- `create_skill` can also set auxiliary metadata for trust, provenance, classification, policy, and routing. Do not add unnecessary keys; keep it simple if the description alone is sufficient
- If the body becomes too long, it will strain the context, so aim for 150 lines or fewer
- For external resource references (Level 3), use `references/` to keep the body concise