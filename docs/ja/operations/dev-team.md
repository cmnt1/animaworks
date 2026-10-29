> 確認したコミット: 581e20f1

# 開発チームの構成

AnimaWorks には、開発チーム向けの役割テンプレートが含まれる。テンプレートはチームを始めるための出発点であり、具体的な開発手順や知識は各チームの運用に合わせて整える。

## 役割の例

| テンプレート | 主な役割 |
|---|---|
| `dev-lead` | 作業を分解し、実装担当や調査担当へ委任し、品質確認とエスカレーションを行う。 |
| `dev-engineer` | 隔離された作業環境で実装し、テストと変更内容を報告する。 |
| `dev-researcher` | 読み取り専用で調査し、根拠と未確認事項を分けて報告する。 |

役割の人数や階層は固定ではない。小規模なチームでは一人が複数の責務を持たせず、必要な担当だけを作成する。

## 作成

```sh
animaworks anima create --name lead --template dev-lead
animaworks anima create --name engineer --template dev-engineer --supervisor lead
animaworks anima create --name researcher --template dev-researcher --supervisor lead
```

名前は例である。作成後は組織図、モデル、権限、heartbeat/cron の設定を確認し、テンプレートの指示がチームの承認・レビュー基準と一致するよう調整する。Anima 作成方法は[CLI リファレンス](../reference/cli.md)を参照する。

## 開発パイプラインとの接続

GitHub webhook を有効化すると、対象イベントを指定した dispatcher Anima へ通知できる。通知処理と実装・レビューの工程は別の責務であり、受信イベントが自動的に安全な変更やマージを保証するわけではない。リポジトリの権限、CI、レビュー承認、ブランチ保護は GitHub 側でも構成する。

チームが扱う作業では、原則として作業ツリーを分離し、変更対象を明確にしてテストを実行する。調査報告には参照したパスとシンボルを含め、実装結果には検証内容と残る制約を添える。
