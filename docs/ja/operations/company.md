> 確認したコミット: 581e20f1

# 会社の管理

会社機能は、一つの AnimaWorks ランタイム内で Anima、共有資産、チャネルを会社単位に整理する仕組みである。会社名や表示名には架空の例だけを用いる。

## データの配置と所属

会社ごとのデータは `companies/<company>/` に置き、Anima の所属は各 `animas/<name>/status.json` の `company` が示す。会社ディレクトリには表示情報、会社の知識・スキル、共有領域などが含まれる。`companies/<company>/animas/` は所属 Anima を参照するビューであり、Anima の実体は `animas/` 側にある。

情報の共有範囲は次のように分かれる。

- 個別の知識・スキルは、その Anima の領域に置く。
- 会社に共有する知識・スキルや作業ファイルは、その会社の領域に置く。
- 全社共通にしてよい内容だけを共通領域に置く。

会社が異なる Anima 間の直接通信や委任は境界判定の対象となる。他社領域への読み書きも制限される。会社境界を確認できない操作は拒否される。所属を設定していない Anima は会社分離を受けないため、隔離が必要なら明示的に会社へ割り当てる。

## CLI

`cli/commands/company_cmd.py` が `animaworks company` の各コマンドを登録する。

```sh
animaworks company create example-company --display-name "Example Company"
animaworks company list
animaworks company assign sample-anima --to example-company
animaworks company assign sample-anima --unassign
```

`create` は会社領域を作成し、不足している骨格を補う。`list` は会社と所属状況を表示する。`assign` は Anima の所属を変更する。`--unassign` は所属を解除する。

既存資産を会社領域へ移す場合は `animaworks company adopt <path> --to <company>` を使う。移動前にバックアップが作成され、既定では以前の場所に相対リンクが残る。dry-run 可能な `split` は manifest から会社作成・所属変更・資産移動をまとめて計画し、`--execute` を付けた場合にのみ適用する。`export` は会社移行用の bundle を生成する。移動・分割・export は範囲を確認してから実行し、完了後はバックアップと出力内容を照合する。

## チャネルの会社帰属

`config.json` の `channel_company_defaults` は、会社が指定されていない状態で作られる open channel に対し、チャネル名から会社を補うための対応表である。値が適用されたチャネルは会社スコープになり、参加資格と投稿可否は所属の境界に従う。既存チャネルを変更する場合は、対象チャネルの会社とメンバーを確認する。

外部メッセージングから作成する board には、連携ごとの `default_channel_company` も利用できる。設定の全項目は[設定リファレンス](../reference/config.md)を参照する。

## GitHub アカウントの割当て

`config.json` の `github_identities` は、GitHub CLI からどのアカウントの資格情報を使うかを選ぶ対応表である。`anima:<name>` は Anima 単位の指定、会社 slug は会社共通の既定指定として使われ、Anima 単位の指定が優先される。

```json
{
  "github_identities": {
    "example-company": "example-github-account",
    "anima:sample-anima": "sample-github-account"
  }
}
```

対応する GitHub CLI アカウントにログインしていることを確認する。トークン値は設定ファイルへ複製せず、コマンドが必要なアカウントから資格情報を取得する。解決できない場合は通常の GitHub CLI のアクティブアカウントへ戻る。

## 運用上の確認

所属変更は `status.json` を正本として反映される。会社共有資産や検索索引を変更した場合は、所属先と参照範囲を確認し、必要に応じて共有索引を更新する。共通領域には会社固有情報、個人情報、資格情報を置かない。
