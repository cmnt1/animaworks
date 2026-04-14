---
name: notebooklm-tool
description: >-
  Google NotebookLM連携ツール。ノートブック管理・ソース追加・本文取得・チャット（Q&A）・
  アーティファクト生成（音声概要・レポート等）を行う。
  Use when: NotebookLMのノートブック操作、ソース内容の確認、ノートブックへの質問、レポート生成が必要なとき。
tags: [research, notebooklm, knowledge, external]
---

# NotebookLM ツール

Google NotebookLMをAPI経由で操作する外部ツール。

## 呼び出し方法

**Bash**: `animaworks-tool notebooklm <サブコマンド> [引数]` で実行

## アクション一覧

### list — ノートブック一覧
```bash
animaworks-tool notebooklm list
```

### get — ノートブックのサマリー・トピック取得
```bash
animaworks-tool notebooklm get NOTEBOOK_ID
```
ノートブックの要約と推奨質問トピックを返す。

### create — ノートブック作成
```bash
animaworks-tool notebooklm create "タイトル"
```

### delete — ノートブック削除
```bash
animaworks-tool notebooklm delete NOTEBOOK_ID
```

### sources — ソース一覧
```bash
animaworks-tool notebooklm sources NOTEBOOK_ID
```

### source-text — ソース本文取得
```bash
animaworks-tool notebooklm source-text NOTEBOOK_ID SOURCE_ID
```
ソースの全文テキストを返す。内容を確認したいときはこれを使う。

### add-source-url — URLソース追加
```bash
animaworks-tool notebooklm add-source-url NOTEBOOK_ID URL
```

### add-source-text — テキストソース追加
```bash
animaworks-tool notebooklm add-source-text NOTEBOOK_ID --title "タイトル" --text "本文"
```

### add-source-file — ファイルソース追加
```bash
animaworks-tool notebooklm add-source-file NOTEBOOK_ID /path/to/file.pdf
```

### chat — ノートブックに質問
```bash
animaworks-tool notebooklm chat NOTEBOOK_ID "質問テキスト"
```
ソースに基づいた回答と引用元を返す。

### generate — アーティファクト生成
```bash
animaworks-tool notebooklm generate NOTEBOOK_ID --type audio_overview [--language ja] [--instructions "指示"]
```
タイプ: `audio_overview`, `briefing_doc`, `study_guide`, `faq`, `timeline`, `mind_map`

⚠️ 長時間処理。`animaworks-tool submit notebooklm generate ...` でバックグラウンド実行推奨。

### artifacts — アーティファクト一覧
```bash
animaworks-tool notebooklm artifacts NOTEBOOK_ID [--type AUDIO]
```

## 典型的なワークフロー

1. `list` でノートブック一覧を取得（IDを確認）
2. `get NOTEBOOK_ID` でサマリーを確認
3. `sources NOTEBOOK_ID` でソース一覧を取得
4. `source-text NOTEBOOK_ID SOURCE_ID` でソース本文を読む
5. `chat NOTEBOOK_ID "質問"` で内容について質問

## 注意事項

- 初回使用前に `notebooklm login` で認証が必要（ブラウザでGoogleログイン）
- 認証情報は `~/.notebooklm/storage_state.json` に保存される
- Cookie期限切れ時は `notebooklm login` を再実行
