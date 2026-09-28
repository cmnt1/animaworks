# description 작성 가이드 (Agent Skills 표준 준수)

## 기본 규칙

description은 스킬의 발견과 선택에 사용되는 가장 중요한 필드입니다.
LLM이 description을 읽고 "이 스킬이 현재 대화와 관련이 있는지"를 판단합니다.

### 형식

```yaml
description: >-
  [1行目: 何をするスキルかの簡潔な説明（三人称）]
  Use when: [利用シーンをカンマ区切りで列挙]
```

### 규칙

1. **250자 이내** — 카탈로그 표시에서 250자를 초과하는 부분은 잘려서 표시됨
2. **3인칭으로 작성** — "~할 수 있다" "~를 수행한다" 형식. "나는" "당신은" 사용 불가
3. **Use when: 을 반드시 포함** — LLM이 활용 판단의 단서로 삼음
4. **구체적인 동사·명사 사용** — "로그인" "스크린샷" "메일 전송" 등
5. **XML 태그 사용 불가** — `<` `>` 은 보안상 금지
6. **`「」` 키워드 나열은 사용하지 않음** — 구방식. LLM 추론에 맡김

### 좋은 예

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

### 나쁜 예

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

### 체크리스트

- [ ] 250자 이내인가
- [ ] 3인칭으로 작성되었는가
- [ ] `Use when:` 을 포함하고 있는가
- [ ] 구체적인 동사·명사가 있는가
- [ ] `「」` 키워드 나열이 없는가
- [ ] XML 태그가 없는가

### linter로 검증

스킬 작성 후에는 linter로 검증할 수 있습니다:

```bash
python scripts/lint_skill.py /path/to/SKILL.md
```
