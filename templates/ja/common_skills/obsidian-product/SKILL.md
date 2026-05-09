---
name: obsidian-product
description: >-
  成果物レポートを Obsidian Vault に書き出し、Bases (`0_Products DB.base`) に集約するスキル。
  Use when: 人間への提出成果物（報告書・成果物・デプロイ記録など）、およびその付随資料を記録するとき。
  旧 Notion T_Products DB の後継。Vault 上の md に直書きするためキャプチャ容易で、付随資料は wikilink で辿れる。
tags: [productivity, obsidian, report, deliverable]
---

# Obsidian Product レポート

成果物の提出先は **Obsidian Vault** に一本化された。Notion `T_Products` は廃止。
本スキルは「レポートをどこに、どの命名で、どの frontmatter で書くか」の規約を示す。書き込み自体は通常の `Write` / `Edit` / `Bash` ツールで行う。
プロジェクト管理の計画・進捗・決定事項・確認待ちも Obsidian Vault の Markdown を正本にする。Notion への読み書きや Notion DB への成果物提出は行わない。

## Vault パス（固定）

- **Vault ルート**: `E:\OneDriveBiz\Obsidian\`
- **Products ルート**: `E:\OneDriveBiz\Obsidian\_products\`
- **Base ファイル**: `E:\OneDriveBiz\Obsidian\0_Products DB.base`（編集不要、Obsidian 側が自動でこのファイルを読み表示する）

## カテゴリ → フォルダ対応

| カテゴリ（frontmatter `category`） | 格納フォルダ |
|---|---|
| `General` | `_products\General\` |
| `Finance` | `_products\Finance\` |
| `Affiliate` | `_products\Affiliate\` |
| `Property` | `_products\Property\` |
| `Business` | `_products\Business\`（旧「経営」） |

迷ったら `General`。

## ファイル命名規則

- メインレポート: `P-<5桁ゼロ埋めID>_<slug>.md`
  - 例: `P-00042_aff-recipe-v2.md`
- 付随資料: メインと**同じカテゴリフォルダ直下**に、**メインと同じプレフィックス**で並べる
  - 例: `P-00042_aff-recipe-v2_spec.md`, `P-00042_aff-recipe-v2_data.md`
  - サブフォルダは作らない。ファイル名プレフィックスで親子関係を表現する

`<slug>` は ASCII 小文字、区切りは `-`（ハイフン）。日本語タイトルから機械的に変換しづらい場合は、意味を損なわない英数字キーワードを自分で決めるか、`slug` 部分を省略して `P-00042.md` としてもよい（`P-` コードがあれば一意）。

## 操作

### 1. create — 新規レポート作成

1. **次の ID を決める**（採番）
   - Bash で `_products\` 配下の全 md から `id:` を抽出し、max を取り、+1 する。カウンターファイルは使わない。
   - ワンライナー例（Git Bash / PowerShell 双方を想定して Python を使う）:
     ```bash
     python -c "import re, pathlib; ids=[int(m.group(1)) for p in pathlib.Path(r'E:/OneDriveBiz/Obsidian/_products').rglob('*.md') for m in [re.search(r'^id:\s*(\d+)', p.read_text(encoding='utf-8'), re.M)] if m]; print(max(ids)+1 if ids else 1)"
     ```
   - 結果が `42` なら `code = P-00042`。

2. **ファイルパスを決める**
   - `E:\OneDriveBiz\Obsidian\_products\<Category>\P-<NNNNN>_<slug>.md`

3. **frontmatter ＋本文を Write で書く**（下の「frontmatter テンプレ（メイン）」をコピペして埋める）

4. **必要なら Bases を再読み込みしてもらう**よう、ユーザーへの完了報告でコード (例: `P-00042`) を添える。会話中で `P-42 見といて` と呼べるのが本設計の利点。

### 2. attach — 付随資料を足す

1. メインと同じカテゴリフォルダ直下に `P-<NNNNN>_<slug>_<asset>.md` を作る（`<asset>` は資料名 slug）。
2. frontmatter は「frontmatter テンプレ（付随資料）」を使う。`type: product_asset` と `parent_code: "P-<NNNNN>"` 必須。
3. メインレポートに wikilink を追記する:
   ```markdown
   ## 付随資料
   - [[P-00042_aff-recipe-v2_spec]] — 仕様書
   - [[P-00042_aff-recipe-v2_data]] — 元データ
   ```
   Obsidian が自動でリンク化する（Base のテーブルには `type: product_asset` なので表示されない）。

### 3. update — 既存レポートの更新

1. 対象ファイルを Read。
2. frontmatter を Edit で書き換え、必ず `updated:` を現在日時（JST）に更新。
3. 状態遷移（`未着手` → `進行中` → `監査待`）をここで行う。`完了` に変更できるのは sakura のみ。`confirmed` は人間確認用なので、Anima は新規作成・更新時に原則 `false` のままにし、`true` へ変更しない。
4. `id` と `code` は**絶対に変更しない**。

### 4. list — 既存レポートの一覧

Bash での簡易リストアップ:
```bash
grep -rH "^code:" "E:/OneDriveBiz/Obsidian/_products/" | sort
```
本格的なビューは Obsidian 側で `0_Products DB.base` を開けばよい。

## frontmatter テンプレ（メイン、コピペ用）

```yaml
---
type: product
id: 42
code: "P-00042"
title: "アフィリエイト配信レシピ v2"
category: Finance              # General | Finance | Affiliate | Property | Business
product_type: 報告書            # 報告書 | 成果物 | デプロイ記録 | その他
status: 監査待                  # 未着手 | 進行中 | 監査待 | 完了（完了にできるのは sakura のみ）
task_code: AFF-001             # 対応するタスクコードがあれば。無ければ空文字 ""
assignee: 自分のAnima名          # 作成した Anima 名
submitted: 2026-04-23
requires_reply: false           # 人間からの返信・確認を待ちたい場合 true
confirmed: false                # 人間側が確認して落着済みなら true（基本は人間が後でチェック）
created: 2026-04-23T09:15:00+09:00
updated: 2026-04-23T09:15:00+09:00
tags: [product]
---

# アフィリエイト配信レシピ v2

## 要旨
...

## 本文
...

## 付随資料
- [[P-00042_aff-recipe-v2_spec]] — 仕様書
```

## frontmatter テンプレ（付随資料、コピペ用）

```yaml
---
type: product_asset
parent_code: "P-00042"
title: "アフィリエイト配信レシピ v2 — 仕様書"
created: 2026-04-23T09:15:00+09:00
updated: 2026-04-23T09:15:00+09:00
tags: [product-asset]
---

# アフィリエイト配信レシピ v2 — 仕様書

（本文）
```

## 規約まとめ

- **Vault 一本化**: 成果物も下書きも `_products\<Category>\` に置く（下書きは `status: 未着手` で作成、完了時に `status: 完了` へ更新）。旧 `E:\OneDriveBiz\Downloads\` は廃止
- **ID 不変・code で呼ぶ**: 作成後は `id`/`code` を変えない。会話では `P-00042` 形式で呼ぶ
- **frontmatter はファイル先頭に1個だけ**: 先頭は必ず `---` → `type: product` を含む YAML → `---` → 本文の順にする。`--- confirmed: ... ---` のような小さい frontmatter を先頭に追加してはいけない
- **保存は UTF-8 BOM なし**: Markdown は UTF-8 without BOM で保存する。PowerShell 5 の `Set-Content -Encoding UTF8` は BOM を付けやすいので避け、PowerShell 7 の `utf8NoBOM`、Python の `encoding="utf-8"`、または `.NET UTF8Encoding(false)` を使う
- **`status: 完了` にできるのは sakura のみ**: sakura 以外の Anima は、報告書を書き終えて `_products\<Category>\` に格納したら `status: 監査待` にする。完了扱いへの変更は sakura の監査後に行う
- **監査依頼を必ず出す**: sakura 以外の Anima は `status: 監査待` にした後、sakura 宛てに `P-<NNNNN>` とファイルパス、監査してほしい観点を添えて監査依頼を送る
- **`confirmed` は人間側の確認フラグ**: Anima は新規レポートを `confirmed: false` で作る。人間が Obsidian 上で確認後に true へ変える。Anima が `confirmed: true` を先頭へ追記・上書きしてはいけない
- **付随資料はサブフォルダを作らず同じフォルダに並べる**: ファイル名プレフィックスで親子関係を表現
- **wikilink 推奨**: 内部リンクは `[[P-00042_xxx_yyy]]` 記法。パスを書かない（Obsidian が自動解決）
- **`type: product` / `type: product_asset` の区別**: Base テーブルはメインだけを拾う。付随資料は wikilink 経由で辿れればよい
- **日本語可**: `title`、`product_type`、`status` は日本語のまま。`category` だけは英字（フォルダ名との一致のため）

## 運用例

### シナリオ: 週次レポートを書いた

1. 次の ID を採番: 例として `43`
2. `E:\OneDriveBiz\Obsidian\_products\General\P-00043_weekly-report-2026w17.md` に Write（frontmatter 付き）
3. 元データ CSV の要約を付ける: `..._data.md` を作って wikilink 追記
4. 上司に `send_message(intent="report", content="P-00043 週次レポートを提出しました。")` で通知

### シナリオ: タスク受領 → 進行中 → 完了

1. タスク受領時に `status: 未着手` で骨組みだけ書き出し（後で埋める）
2. 着手したら `status: 進行中` に Edit、`updated` 更新
3. 報告書を書き上げたら sakura 以外は `status: 監査待`、`submitted` 日付を入れ、本文を仕上げる
4. sakura に `P-<NNNNN>` とファイルパスを添えて監査依頼を送る
5. sakura が監査後に必要なら修正し、問題なければ `status: 完了` にする
6. `requires_reply: true` にして人間確認待ちにする場合もある
