---
name: skill-creator
description: >-
  A meta-skill for creating Markdown skills. Handles SKILL.md frontmatter and body, Progressive Disclosure, and the create_skill procedure.
  Use when: Use when: adding new skills, checking description rules for read_memory_file, or generating skills with references or templates.
---


# skill-creator

## Implementation mapping

| Role | Module |
|------|------------|
| `read_memory_file` tool (reads body by specifying relative path of skill/procedure) | Via `ToolHandler` (files in memory tree) |
| Skill catalog in system prompt (path list with budget) | Prompt construction (e.g., `skills/foo/SKILL.md`, `common_skills/bar/SKILL.md`, `procedures/baz.md`) |
| `create_skill` tool (directory creation) | `core/tooling/skill_creator.py` |
| Schema (parameter definitions) | `core/tooling/schemas/skill.py` |
| Frontmatter parsing (line-based, not mis-split by `---` in body) | `core/memory/frontmatter.py`'s `parse_frontmatter()` |
| Metadata types and extraction (`SkillMeta`, procedure path estimation) | `core/schemas.py`, `core/memory/skill_metadata.py`'s `SkillMetadataService.extract_skill_meta()` |
| Description-based skill meta extraction (catalog and search assistance) | `core/memory/skill_metadata.py`'s `SkillMetadataService`, etc. |
| Gate line removal from `*-tool` body | `core/tooling/guide.py`'s `filter_gated_from_guide()` |
| Allowed tool set (permissions) | `core/config/models.load_permissions()` + `core/tooling/permissions.get_permitted_tools()` |

## Skill types and paths

Skills and procedures are managed in **separate layouts**.

| Type | Path | Notes |
|------|------|------|
| Personal skill | `skills/{name}/SKILL.md` | Directory + `SKILL.md` |
| Common skill | `common_skills/{name}/SKILL.md` | At runtime, `~/.animaworks/common_skills/`, etc. |
| Procedure | `procedures/{name}.md` | **Flat single file**. Not a directory |

What `create_skill` generates is only the **skill** (personal or common) in the table above. Procedures are created separately as `procedures/*.md` via `write_memory_file`, etc.

### Do not place symlinks (rule established 2026-09-04)

Do not "re-post" via **symlinks** pointing outside (e.g., `~/.claude/skills`) under `common_skills/` or `skills/`. `read_memory_file` checks boundaries at the actual file location, so if the symlink target is outside, it cannot be read due to "Path traversal detected." Furthermore, the catalog lists that symlink as a native skill and hides the same-name external candidate, so Anima is only shown paths it cannot read.

- Host-side skills (`~/.claude/skills`, `~/.codex/skills`, etc.) are automatically injected from configuration `skills.external_roots` and can be read via `external/<engine>/<name>/SKILL.md`. No need to re-post them as common skills.
- If you must place something as a common skill, copy the actual file and designate one of the two as the canonical source.

## Reading skills with read_memory_file

Skill and procedure bodies are read by specifying a memory-tree relative path via **`read_memory_file(path="...")`**. The skill catalog in the system prompt shows available paths (e.g., `skills/foo/SKILL.md`, `common_skills/bar/SKILL.md`, `procedures/baz.md`).

- **Personal skill**: `skills/{name}/SKILL.md`
- **Common skill**: `common_skills/{name}/SKILL.md`
- **Procedure**: `procedures/{name}.md`

`path` is passed as a relative path based on the Anima directory (shared tree uses prefixes like `common_skills/`).

### Frontmatter and body

The YAML at the top of SKILL.md is removed with `core/memory/frontmatter.parse_frontmatter()` before reading. Since the **separator line `---` is recognized only line-by-line**, even if `---` appears in YAML values or the body, mis-splitting is unlikely.

### Placeholders in the body (`*-tool` guide)

Skill bodies may use placeholders such as `{{now_local}}`, `{{anima_name}}`, `{{anima_dir}}`. For external-tool skills (names ending in `*-tool`), gate processing of the `animaworks-tool` line is performed according to permission settings (e.g., `filter_gated_from_guide()` in `core/tooling/guide.py`).

### Catalog and description

At **Level 1** of the skill catalog, `name` + `description` appear within the budget. The more skills there are, the more likely they are to be truncated, so keep **`description` short and specific**. When the full text is needed, open the catalog path with `read_memory_file`.

**Legacy compatibility**: When `description` is empty, `extract_skill_meta()` uses the **first non-empty line of the `## 概要` section** in the body as a fallback. For new skills, the frontmatter is authoritative.

### Layout notes

A **`*.md` (flat single file)** directly under personal `skills/` can be a target for catalog and meta extraction, but the **recommended path is `skills/{name}/SKILL.md`**. In practice, the directory format via `create_skill` is the standard.

## Skill file structure

SKILL.md consists of YAML frontmatter and Markdown body.
The frontmatter requires **`name` and `description`**.

`create_skill` can write out not only `allowed_tools` but also metadata for trust, provenance, classification, and routing assistance. Required fields are `name` / `description` / `body`; optional keys are used only when their purpose is clear.

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

Main optional fields: `allowed_tools`, `trust_level`, `source_type`, `source_origin`, `category`, `promotion_status`, `skill_policy`, `use_when`, `trigger_phrases`, `negative_phrases`, `domains`, `routing_examples`. For argument names in `create_skill`, `source.type` is passed as `source_type`, and `source.origin` as `source_origin`.

### Role of `description`

**New skill descriptions** follow the Agent Skills standard, with **`Use when:`** used to write the use case (see `references/description_guide.md` for details). After creation, **`python scripts/lint_skill.py`** can validate the format.

- **When read by specifying a path with `read_memory_file`**: If the file exists, the body is obtained **regardless of description matching** (frontmatter processing and `*-tool`-related handling depend on the read path).
- **Skill catalog in system prompt**: Level 1 includes `name` + `description` with a budget. The full text is not included, so if procedures are needed, open via **`read_memory_file(path="skills/.../SKILL.md")`, etc.**

**Legacy compatibility**: When `description` is empty, `extract_skill_meta()` uses the **first non-empty line of the `## 概要` section** near the top of the body as a description fallback. For new skills, the frontmatter is authoritative; avoid `## 概要` dependency.

**How to write descriptions** (**Use when:** pattern and lint): see `references/description_guide.md`.

## Progressive Disclosure

Skill information is disclosed roughly in the following stages.

| Level | Content | Display timing |
|-------|------|----------------|
| Level 1 | `name` + `description` | Material for the skill catalog in the system prompt (within budget) |
| Level 2 | body | When the agent loads it via `read_memory_file(path="skills/.../SKILL.md")`, etc. |
| Level 3 | External resources | Following body instructions, read `references/` or `templates/` via `read_memory_file`, etc. as needed |

Level 1 tends to consume context in the catalog, so **keep descriptions concise**. Level 2 is the core of the procedure. Level 3 separates lengthy references.

Note: The Priming skill body injection path has been removed. If the body is needed, open the skill path with **`read_memory_file`**.

## Creation procedure

### Step 1: Interview

Understand the user's requirements. Confirm the following:

- What they want to automate or proceduralize
- Whether the target is a personal skill or common skill (if a procedure, design separately for `procedures/`)
- The use case to write in **Use when:** (when to choose this skill)

### Step 2: Design

Decide the following:

- **name**: Skill name (kebab-case, e.g., `my-skill`). For external tool guides, consider the `*-tool` convention
- **description**: Third-person summary + **`Use when:`** line (see `references/description_guide.md`)
- **body**: Procedure structure (sectioning). Use placeholders like `{{now_local}}` as needed
- **references** / **templates**: Design external files if needed
- **allowed_tools**: Only if you want to restrict recommended tools
- **trust/source/category/policy/routing**: trust level, provenance, classification, prompt policy, `use_when` / `trigger_phrases` / `negative_phrases` / `domains` / `routing_examples`** as needed

### Step 3: Creation

Create the skill as a directory structure using the `create_skill` tool.

**Basic (personal skill)**:

```
create_skill(skill_name="{name}", description="{description}", body="{body}")
```

**Common skill**:

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
|-----------|------|------|
| skill_name | ✓ | Skill name (kebab-case). `/`, `\`, `..` not allowed |
| description | ✓ | Frontmatter description (**Use when: recommended; `references/description_guide.md`) |
| body | ✓ | SKILL.md body (Markdown). Target of built-in substitution |
| location | | `personal` (default) or `common` |
| references | | Files placed in `references/`. `[{filename, content}, ...]` |
| templates | | Files placed in `templates/`. `[{filename, content}, ...]` |
| allowed_tools | | `allowed_tools` in frontmatter (optional) |
| trust_level | | Trust levels such as `trusted` / `community` |
| source_type / source_origin | | Provenance (e.g., `anima`, `manual`, `auto_created`) |
| category | | Classification tag |
| promotion_status | | Promotion status such as `probation` / `trusted` |
| skill_policy | | Prompt injection policy (`use_mode`, injection-related settings) |
| use_when / trigger_phrases / negative_phrases / domains / routing_examples | | Auxiliary metadata to help the skill router select candidates |

Do not include path components in `filename` of `references` / `templates`. Confirm via `_validate_filename()` that resolution does not go outside the parent directory; if invalid, **silently skip** (that file is not created).

Note: Always use `create_skill` for new skills. Creating only a **single file directly under** something like `skills/foo.md` via `write_memory_file` is **not recommended**. This format **cannot be opened with `read_memory_file(path="skills/foo/SKILL.md")`**, so the recommended approach is the directory format of `skills/foo/SKILL.md`.

Note: Procedures are `procedures/{name}.md` (flat single file). Frontmatter follows the same pattern as skills, with `name` / `description` (plus optional `allowed_tools`) recommended.

### Step 4: Verification

- **Personal skill**: Verify content with `read_memory_file(path="skills/{name}/SKILL.md")`
- **Common skill**: Verify via paths shown in the catalog, such as `read_memory_file(path="common_skills/{name}/SKILL.md")`
- **Procedure**: Confirm it can be resolved with `read_memory_file(path="procedures/{name}.md")`
- Validate the frontmatter / description of `SKILL.md` with **`python scripts/lint_skill.py`** (optional but recommended)

## Checklist

Before saving, verify the following:

- [ ] YAML frontmatter starts with `---` and closes with `---`
- [ ] `name` field is present
- [ ] `description` field is present
- [ ] description contains **`Use when:`** and includes domain-specific concrete terms (do not use the old `「」` enumeration)
- [ ] **description is domain-specific and concrete** (avoid generic expressions like "perform management" or "confirm"; specify the tool name, operation name, and target)
- [ ] body contains concrete procedures
- [ ] For new items, place `description` in the frontmatter and **do not rely solely on `## 概要` for the description** (also avoid old template formats such as `## 発動条件`)
- [ ] Optional metadata (`trust_level`, `source`, `category`, `skill_policy`, `use_when`, `trigger_phrases`, `negative_phrases`, `domains`, `routing_examples`) matches actual usage
- [ ] Skills are created with `create_skill` using `{name}/SKILL.md` (verify that the procedure works as intended with `procedures/*.md`)

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

- A skill is a Markdown procedure document, distinct from Python code (tools)
- Required frontmatter fields are `name` and `description`
- `create_skill` can also set trust, provenance, classification, policy, and routing auxiliary metadata. Do not add unnecessary keys; keep it simple if the description alone is sufficient
- If the body becomes too long, it will consume context; aim for 150 lines or fewer
- For external resource references (Level 3), use `references/` to keep the body concise
