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
上記テキストから、後で参照する価値のある事実の主語・目的語になるエンティティ（人物・anima・組織・案件・Issue/PR・成果物・決定事項など）を抽出し、以下のJSON形式で返してください。エンティティが見つからない場合は空リストを返してください。
ファイルパス・コマンド・ツール名・CIジョブ名・設定キー・時刻だけのものは、それ自体が依頼・決定・障害の中心でない限りエンティティにしないでください。

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

## 抽出する事実の基準
「1か月後に知識として参照して役に立つか」で選んでください。迷ったら抽出しないでください。
- 抽出する: 人や案件についての新しい情報、決定・判断、依頼・約束とその担当者と期限、障害・不具合の原因と対処・結論、設定や運用ルールの変更、成果物（PR・Issue・文書）の所在と内容の要点
- 抽出しない: 定期巡回・cron の定型（記録先・手順に従った・何時に実行した・状態遷移・異常なし）、構成要素の列挙（「CI には X が含まれる」等）、ファイルパスやコマンドの列挙、コマンド出力の数値、一時的な状態、何時に何を受信・確認したという経過、ツールの使い方の一般論
- 同じ内容を言い換えて複数件にしないでください。1つのテキストから多くても15件程度、重要な順に出してください。

上記エンティティ間の関係（事実）を抽出し、以下のJSON形式で返してください。関係が見つからない場合は空リストを返してください。

```json
{{
  "facts": [
    {{"source_entity": "エンティティA", "target_entity": "エンティティB", "fact": "AとBの関係を自然言語で記述", "edge_type": "WORKS_AT", "valid_at": "YYYY-MM-DDTHH:MM:SS or null"}}
  ]
}}
```"""

# ── Combined entity / fact extraction ─────────────────────

COMBINED_SYSTEM = (
    "あなたは情報抽出エージェントです。"
    "与えられたテキストから、後で参照する価値のある事実と、"
    "その事実に直接使われるエンティティを1回の処理でJSON形式で抽出してください。"
)

COMBINED_USER = """## テキスト
{content}

## 既知のエンティティ（参考）
{previous_entities}

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

## 抽出する事実の基準
「1か月後に知識として参照して役に立つか」で選んでください。迷ったら抽出しないでください。
- 抽出する: 人や案件についての新しい情報、決定・判断、依頼・約束とその担当者と期限、障害・不具合の原因と対処・結論、設定や運用ルールの変更、成果物（PR・Issue・文書）の所在と内容の要点
- 抽出しない: 定期巡回・cron の定型（記録先・手順に従った・何時に実行した・状態遷移・異常なし）、構成要素の列挙（「CI には X が含まれる」等）、ファイルパスやコマンドの列挙、コマンド出力の数値、一時的な状態、何時に何を受信・確認したという経過、ツールの使い方の一般論
- 同じ内容を言い換えて複数件にしないでください。1つのテキストから多くても15件程度、重要な順に出してください。

## エンティティの基準
事実の主語または目的語として使われるエンティティだけを出力してください。entities は facts の source_entity / target_entity に現れるものだけにし、テキストに出てくる名前を網羅しないでください（多くても30件程度）。
entity_type は Person、Place、Organization、Concept、Event、Object、Time の7種類から選んでください。Issue・PR・成果物は Object、案件や決定事項は Concept または Event として分類してください。

先に facts を出力し、そのあとで facts に現れるエンティティだけを entities に出力してください。形式は以下のJSONです。事実が見つからない場合は facts を空リストにし、entities も空リストにしてください。

```json
{{
  "facts": [
    {{"source_entity": "エンティティA", "target_entity": "エンティティB", "fact": "AとBの関係を自然言語で記述", "edge_type": "WORKS_AT", "valid_at": "YYYY-MM-DDTHH:MM:SS or null"}}
  ],
  "entities": [
    {{"name": "正規化された名前", "entity_type": "Person|Place|Organization|Concept|Event|Object|Time", "summary": "1-2文の説明"}}
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
