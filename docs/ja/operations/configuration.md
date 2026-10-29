> 確認したコミット: 581e20f1

# 設定の管理

AnimaWorks の設定は、ランタイム全体の動作、モデルの解決、Anima ごとの状態、権限ポリシーに分かれている。用途の異なるファイルを一つにまとめず、変更対象と反映方法を選ぶ。

## 設定ファイルの役割

| ファイル | 主な役割 | 範囲 |
|---|---|---|
| `config.json` | サーバー、連携、記憶、GPU、共通既定値などのランタイム設定 | ランタイム全体。 |
| `models.json` | モデル名パターンごとの実行モードやモデルメタデータ | モデル解決。 |
| `animas/<name>/status.json` | Anima ごとのモデル、実行モード、所属、状態など | 個別の Anima。 |
| `permissions.global.json` | 全 Anima に適用するコマンド禁止ルールや入力検知設定 | ランタイム全体のセキュリティ境界。 |
| `animas/<name>/permissions.json` | 個別 Anima のファイル、コマンド、外部ツール権限 | 個別の Anima。 |

ファイルの実際の位置は `ANIMAWORKS_DATA_DIR` が設定されていればそのディレクトリ、未設定なら既定のデータディレクトリである。パスと項目の完全な一覧は[設定リファレンス](../reference/config.md)を参照する。

## 優先順位

ランタイム設定の共通値は `config.json` が持ち、Anima 固有の指定はその上書きとして適用される。モデルの実行モードは、Anima の `status.json` に明示した `execution_mode`、`models.json` のパターン、互換用の `config.json` の `model_modes`、コード既定値の順に解決される。モデル名がどのパターンにも一致しない場合は `A` になる。

`permissions.global.json` と `permissions.json` は一般設定とは別の権限ポリシーである。個別の deny は許可より優先される。グローバル設定はサーバー起動時に読み込まれ、実行中のポリシーとしてキャッシュされる。

## 編集方法

`animaworks config get <dot.path>`、`animaworks config set <dot.path> <value>`、`animaworks config list` で `config.json` を参照・編集できる。値は真偽値・数値・`null` として解釈される。秘密値を端末やログへ不用意に表示しない。

Anima のモデル変更には `animaworks anima set-model <name> <model>` を使う。`models.json` はモデル名の対応表である。対応する編集コマンドがない項目を手作業で変更する場合は、ファイルをバックアップし、構文と値を確認してから保存する。権限ファイルはアクセス境界であるため、意図しない許可範囲の拡大がないか必ずレビューする。

## 変更の反映

- `status.json` の Anima 設定変更は `animaworks anima reload <name>` で実行中の Anima に再読込させる。プロセスや実行環境の初期化を伴う変更は `animaworks anima restart <name>` を使う。
- `config.json` の一般設定や接続設定は、対象設定がサポートする hot reload を使うか、サーバーを再起動する。反映方法を判断できない場合は再起動する。
- `permissions.global.json` は起動時にキャッシュされる。変更を反映するにはサーバーを再起動する。
- `models.json` のモデルパターンはキャッシュされるが、ファイル更新を検知して再読込される。変更後に対象 Anima の次回実行で解決を確認する。

再起動の対象を誤ると、設定ファイルだけ変更されて実行中の接続やプロセスに反映されないことがある。変更後は `animaworks anima status <name>` やサーバーの health/status を確認し、意図した値が有効であることを確かめる。
