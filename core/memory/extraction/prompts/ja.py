# Copyright 2026 AnimaWorks
# Licensed under the Apache License, Version 2.0
"""Japanese prompts for entity / fact extraction."""

from __future__ import annotations

# ── Entity extraction ──────────────────────────────────────

ENTITY_SYSTEM = (
    "あなたは情報抽出エージェントです。"
    "与えられたテキストからエンティティ"
    "（人物・場所・組織・概念・イベント・物・時間）を"
    "JSON形式で抽出してください。"
)

ENTITY_USER = """## テキスト
{content}

## 既知のエンティティ（参考）
{previous_entities}

## 指示
上記テキストからエンティティを抽出し、以下のJSON形式で返してください。エンティティが見つからない場合は空リストを返してください。

```json
{{
  "entities": [
    {{"name": "正規化された名前", "entity_type": "Person|Place|Organization|Concept|Event|Object|Time", "summary": "1-2文の説明"}}
  ]
}}
```"""

# ── Fact extraction ────────────────────────────────────────

FACT_SYSTEM = "あなたは関係抽出エージェントです。与えられたエンティティのペア間の関係をJSON形式で抽出してください。"

FACT_USER = """## テキスト
{content}

## 抽出済みエンティティ
{entities_json}

## 指示
上記エンティティ間の関係（事実）を抽出し、以下のJSON形式で返してください。関係が見つからない場合は空リストを返してください。

```json
{{
  "facts": [
    {{"source_entity": "エンティティA", "target_entity": "エンティティB", "fact": "AとBの関係を自然言語で記述", "valid_at": "YYYY-MM-DDTHH:MM:SS or null"}}
  ]
}}
```"""

# ── Entity deduplication ──────────────────────────────────

DEDUPE_SYSTEM = (
    "あなたはエンティティ重複判定エージェントです。新しいエンティティが既存の候補と同一かどうかを判定してください。"
)

DEDUPE_USER = """## 新規エンティティ
名前: {new_entity_name}
タイプ: {new_entity_type}
概要: {new_entity_summary}

## 既存エンティティ候補
{candidates_json}

## 指示
新規エンティティが既存候補のいずれかと同一の実体を指す場合、そのUUIDと統合サマリーをJSON形式で返してください。
同一でない場合、または判断に自信がない場合は duplicate_of_uuid を null にしてください。

```json
{{"duplicate_of_uuid": "既存のUUID or null", "merged_summary": "統合した1-2文の説明"}}
```"""
