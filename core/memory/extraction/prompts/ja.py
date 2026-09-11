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

## エッジ型（edge_type）
以下の型から最も適切なものを選んでください。該当しない場合は "RELATES_TO" を使用してください。
{edge_types_list}

## 参照時刻 (reference_time)
{reference_time}

## 指示
各事実(fact)について、その事実が現実世界で有効になった日時（valid_at）を推定してください。
- 明示的な日付・時刻がテキストにあればそれを使用
- 「昨日」「先週」等の相対表現は reference_time を基準に解決
- 不明な場合は reference_time をそのまま使用（ISO 8601 形式で出力）

上記エンティティ間の関係（事実）を抽出し、以下のJSON形式で返してください。関係が見つからない場合は空リストを返してください。

```json
{{
  "facts": [
    {{"source_entity": "エンティティA", "target_entity": "エンティティB", "fact": "AとBの関係を自然言語で記述", "edge_type": "WORKS_AT", "valid_at": "YYYY-MM-DDTHH:MM:SS or null"}}
  ]
}}
```"""

# ── Community summarization ───────────────────────────────

COMMUNITY_SYSTEM = "あなたはグループ分析エージェントです。関連するエンティティのグループに名前と要約を付けてください。"

COMMUNITY_USER = """## グループメンバー
{members}

## 指示
上記メンバーの共通テーマに基づいて、このグループに名前と要約を付けてください。

```json
{{"name": "グループ名（10文字以内）", "summary": "このグループの1-2文の説明"}}
```"""
