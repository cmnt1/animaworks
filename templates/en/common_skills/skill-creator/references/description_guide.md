# description Writing Guide (Agent Skills Standard Compliant)
## Basic Rules

The description is the most important field used for skill discovery and selection.
The LLM reads the description to determine whether "this skill is relevant to the current conversation."
### Format

```yaml
description: >-
  [1行目: 何をするスキルかの簡潔な説明（三人称）]
  Use when: [利用シーンをカンマ区切りで列挙]
```

### Rules

1. **Within 250 characters** — Content exceeding 250 characters is truncated in catalog display
2. **Write in third person** — Use forms like "can do ~" or "performs ~." "I" or "you" are not allowed
3. **Must include Use when:** — The LLM uses it as a cue for usage decisions
4. **Use specific verbs and nouns** — Such as "login," "screenshot," "email send"
5. **No XML tags** — `<` `>` are prohibited for security reasons
6. **Do not use `「」` keyword enumeration** — That is the old method. Rely on LLM reasoning
### Good Examples

```yaml
description: >-
  ヘッドレスブラウザ操作CLI。Webページを開いて閲覧・操作・ログイン・スクリーンショット撮影ができる。
  Use when: ブラウザでサイトを開く、Webアプリの操作・確認、ログイン操作、スクショ撮影、画面のUI確認が必要なとき。
```

```yaml
description: >-
  Gmail operations via CLI. Send, receive, search emails, and manage labels.
  Use when: sending emails, checking inbox, searching mail, managing Gmail labels or filters.
```

### Bad Examples

```yaml
# ❌ 「」キーワード列挙（旧方式）
description: >-
  ブラウザ操作CLI。
  「ブラウザで確認」「スクショ撮って」「ブラウザ操作」

# ❌ 曖昧すぎる
description: Helps with documents

# ❌ 一人称
description: I can help you process PDF files

# ❌ 250文字超
description: >-
  （非常に長い説明文...）
```

### Checklist

- [ ] Is it within 250 characters?
- [ ] Is it written in third person?
- [ ] Does it include `Use when:`?
- [ ] Are there specific verbs and nouns?
- [ ] Is there no `「」` keyword enumeration?
- [ ] Are there no XML tags?
### Validation with linter

After creating a skill, you can validate it with the linter:

```bash
python scripts/lint_skill.py /path/to/SKILL.md
```
