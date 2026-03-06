---
name: image-posting
description: >-
  チャット応答に画像を添付・表示するスキル。
  ツール結果(web_search、image_gen等)に含まれる画像URL・パスの自動検出・表示の仕組み、
  応答テキスト内でのMarkdown画像構文による埋め込み方法、
  自分のassets/attachments画像の表示方法を提供する。
  「画像を貼る」「画像を見せて」「イラスト表示」「画像添付」「写真を貼って」「検索画像を表示」
---

# image-posting — チャット応答への画像表示

## 概要

チャット応答に画像を含める仕組みは2系統ある:

1. **ツール結果からの自動抽出** — ツール結果に画像URLやパスが含まれると、フレームワークが自動検出してチャットバブルに表示する
2. **Markdown画像構文** — 応答テキスト内に `![alt](url)` を書くとフロントエンドがレンダリングする

## 方法1: ツール結果からの自動表示

ツール（web_search、image_gen等）を呼び出した結果に画像情報が含まれていれば、フレームワークが自動でチャットバブルに画像を表示する。Anima側で特別な操作は不要。

### 自動検出される条件

ツール結果のJSON内で以下が検出されると画像として扱われる:

- **パス検出**: `path`, `file`, `filepath`, `asset_path` キーの値、または結果文字列内に `assets/` / `attachments/` で始まるパス（`.png` `.jpg` `.jpeg` `.gif` `.webp`）→ `source: generated`（信頼済み）
- **URL検出**: `url`, `image_url`, `thumbnail`, `src` キーに画像URLがある場合 → `source: searched`（プロキシ経由、許可ドメインのみ）
- **image_gen専用**: ツール結果全体を正規表現で走査し、`assets/` または `attachments/` を含むパスを自動抽出

1応答あたり最大5枚まで。

### image_genツールの出力ファイル

画像生成ツール（`core/tools/image_gen.py`）は以下のアセットを `assets/` に出力する。**PNG画像**は自動表示対象、GLB（3Dモデル）はアセットとして保存されワークスペース等で別途表示される:

| ツール | 出力ファイル例 | チャット自動表示 |
|--------|----------------|------------------|
| `generate_character_assets` | 一括パイプライン（fullbody, bustup, chibi, 3D, リグ, アニメーション） | PNGのみ |
| `generate_fullbody` | `avatar_fullbody.png` / `avatar_fullbody_realistic.png` | ○ |
| `generate_bustup` | `avatar_bustup.png` / `avatar_bustup_realistic.png` | ○ |
| `generate_chibi` | `avatar_chibi.png` | ○ |
| `generate_3d_model` | `avatar_chibi.glb` | —（3D表示用） |
| `generate_rigged_model` | `avatar_chibi_rigged.glb`, `anim_*.glb` | —（3D表示用） |
| `generate_animations` | `anim_idle.glb`, `anim_sitting.glb` 等 | —（3D表示用） |

リアルティックスタイル（`image_style: realistic`）時は `*_realistic.png` が生成される。表情バリエーション（`bustup_expressions`）は `avatar_bustup_smile.png` 等。

### searched画像のプロキシ制限

外部URL画像はセキュリティのためプロキシ経由で配信される。**アーティファクト抽出時点**で以下の許可ドメインのみが検出対象となる:

- `cdn.search.brave.com`
- `images.unsplash.com`
- `images.pexels.com`
- `upload.wikimedia.org`

上記以外のドメインのURLはツール結果に含まれていても自動表示されない。プロキシ自体はHTTPS強制・private/local拒否・magic bytes検証・SVG拒否・サイズ・レート制限などの安全検査を実施する（`config.server.media_proxy` で `open_with_scan` / `allowlist` モードを切り替え可能）。

## 方法2: Markdown画像構文

応答テキスト内にMarkdown画像構文を直接書いて画像を表示する。

### 短縮パス（推奨）

フロントエンドが自動的に自分のAnima名でAPIパスを補完する。ファイル名だけ書けばOK:

```
![説明](attachments/ファイル名)
![説明](assets/ファイル名)
```

例:

```
スクショ撮りました！
![ANAトップページ](attachments/ana_top.png)
```

### フルパス

明示的にAPIパスを書くこともできる:

```
![説明](/api/animas/{自分の名前}/assets/{ファイル名})
![説明](/api/animas/{自分の名前}/attachments/{ファイル名})
```

## スクリーンショットの保存先

agent-browser等でスクリーンショットを撮る場合、**自分のattachmentsディレクトリに直接保存する**のが確実:

```bash
agent-browser screenshot ~/.animaworks/animas/{自分の名前}/attachments/screenshot.png
```

例（aoiの場合）:

```bash
agent-browser screenshot ~/.animaworks/animas/aoi/attachments/page_screenshot.png
```

保存後、応答に以下を書けば表示される:

```
![ページのスクショ](attachments/page_screenshot.png)
```

`~/.animaworks/tmp/attachments/` に保存した場合もフォールバックで表示されるが、一時ディレクトリなので永続性は保証されない。

## 注意事項

- 他のAnimaのアセットパスは直接参照できない（権限外）
- 外部URLの直リンクは非推奨。許可ドメイン外は自動表示されず、プロキシの安全検査でブロックされる場合がある
- 画像生成ツール（`generate_character_assets`, `generate_fullbody`, `generate_bustup`, `generate_chibi` 等）の結果は自動表示されるため、Markdown構文は不要
- 1応答あたりの自動表示は最大5枚
