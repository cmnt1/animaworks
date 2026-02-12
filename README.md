# AnimaWorks

**AIを「ツール」ではなく「人」として扱うフレームワーク**

AnimaWorksは、AIエージェントを組織の一員として自律的に動作させる Digital Person フレームワーク。各エージェントが自分の記憶・判断基準・内部時計を持ち、不完全な情報を自分の言葉で伝え合う――人間の組織と同じ原理で動く。

## 3つの核心

- **カプセル化** — 内部の思考・記憶は外から見えない。他者とはテキスト会話だけでつながる
- **書庫型記憶** — 記憶を切り詰めてプロンプトに詰め込むのではなく、必要な時に自分で書庫を検索して思い出す
- **自律性** — 指示を待つのではなく、自分の時計（ハートビート・cron）で動き、自分の理念で判断する

## アーキテクチャ

```
┌────────────────────────────────────────────┐
│         Digital Person: Sakura             │
├────────────────────────────────────────────┤
│  Identity ────── 自分が誰か（常駐）          │
│  Agent Core ──── Claude Agent SDK（思考）    │
│  Memory ──────── 書庫型。自律検索で想起       │
│  Permissions ─── ツール/ファイル/コマンド制限  │
│  Communication ─ テキスト＋ファイル参照       │
│  Lifecycle ───── メッセージ/ハートビート/cron  │
│  Injection ───── 役割/理念/行動規範（注入式）  │
└────────────────────────────────────────────┘
```

## 記憶システム

従来のAIエージェントは記憶を切り詰めてプロンプトに詰め込む（＝直近の記憶しかない健忘）。AnimaWorks の書庫型記憶は、人間が書庫から資料を引き出すように **必要な時に必要な記憶だけを自分で検索して取り出す。**

| ディレクトリ | 脳科学モデル | 内容 |
|---|---|---|
| `episodes/` | エピソード記憶 | 日別の行動ログ |
| `knowledge/` | 意味記憶 | 教訓・ルール・学んだ知識 |
| `procedures/` | 手続き記憶 | 作業手順書 |
| `state/` | ワーキングメモリ | 今の状態・未完了タスク |

## セットアップ

### 必要環境

- Python 3.12+
- Anthropic API キー

### インストール

```bash
git clone <repository-url>
cd animaworks
pip install -e .
```

### 環境変数

```bash
# 必須
export ANTHROPIC_API_KEY=sk-ant-...

# オプション
export ANIMAWORKS_DATA_DIR=~/.animaworks    # ランタイムデータ（デフォルト: ~/.animaworks）
```

### 初期化

テンプレートからランタイムディレクトリを生成する。

```bash
animaworks init
```

`~/.animaworks/` に company ビジョンと sakura（サンプル人格）の設定ファイルが展開される。

## 実行方法

```bash
animaworks start
```

デフォルトで `http://localhost:18500` でサーバーが起動する。

### Docker

```bash
docker-compose up
```

## CLIコマンド

| コマンド | 説明 |
|---|---|
| `animaworks init [--force]` | ランタイムディレクトリを初期化 |
| `animaworks start` | サーバー起動 |
| `animaworks serve` | サーバー起動（start のエイリアス） |
| `animaworks chat PERSON "メッセージ"` | Digital Person にメッセージを送信 |
| `animaworks heartbeat PERSON` | ハートビートを手動トリガー |
| `animaworks send FROM TO "メッセージ"` | Digital Person 間メッセージ |
| `animaworks list` | 全 Digital Person を一覧表示 |
| `animaworks status` | システムステータス表示 |

## 人格の追加

1人 ＝ 1ディレクトリ。`~/.animaworks/persons/{name}/` に Markdown ファイルを配置するだけ。

```
persons/alice/
├── identity.md      # 性格・得意分野（不変）
├── injection.md     # 役割・理念・行動規範（差替可能）
├── permissions.md   # ツール/ファイル権限
├── config.md        # モデル・API設定
├── heartbeat.md     # 定期チェック間隔
├── cron.md          # 自分の定時タスク
└── skills/          # 拡張スキル
```

Identity を差し替えれば同じフレームワークで全く異なる AI 社員が動く。

## 技術スタック

| コンポーネント | 技術 |
|---|---|
| エージェントループ | Claude Agent SDK |
| LLM API | Anthropic SDK |
| Web フレームワーク | FastAPI + Uvicorn |
| タスクスケジュール | APScheduler |
| 設定管理 | Pydantic + TOML + Markdown |

## プロジェクト構成

```
animaworks/
├── main.py              # CLI エントリポイント
├── core/                # Digital Person コアエンジン
│   ├── person.py        #   カプセル化された人格クラス
│   ├── agent.py         #   Claude Agent SDK ラッパー
│   ├── memory.py        #   書庫型記憶の検索・書き込み
│   ├── messenger.py     #   メッセージ送受信
│   ├── lifecycle.py     #   ハートビート・cron管理
│   └── prompt_builder.py #  システムプロンプト構築
├── server/              # サーバー（FastAPI アプリケーション）
├── gateway/             # (deprecated) 分散ゲートウェイ
├── worker/              # (deprecated) 分散ワーカー
├── broker/              # (deprecated) メッセージブローカー
└── templates/           # デフォルト設定・プロンプトテンプレート
    ├── persons/sakura/  #   サンプル人格
    └── prompts/         #   再利用可能なプロンプト
```

## 設計思想の詳細

詳しい設計理念は [vision.md](vision.md)、技術仕様は [spec.md](spec.md) を参照。
