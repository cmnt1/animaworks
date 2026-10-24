# 不動産日次レポートのDiscord報告

対象は安城市1K賃貸（`PTY-ANJO-1K-DAILY`）とデイリー売買情報（`PROP-07`）。この手順は、現在のローカル環境で運用するレポートの通知設定と復旧記録を扱う。

## 通常の設定

2026-10-25以降、デイリー売買情報（PROP-07）と各物件の投資分析レポートは
Discordスレッド `1563692914620637246` に報告する。
送信スクリプトと生成レポートは `sale_investment_analysis.SALE_DISCORD_THREAD_ID` を共通参照する。
安城市1K賃貸の報告先は従来の `1491411026263146658` を使用する。

`C:\Users\cmnt\.animaworks\animas\sakura\cron.md` の次の4ジョブは、通常運用で `--local-only` を付けない。

| ジョブ | スケジュール | 実行対象 |
|---|---|---|
| 安城市1K賃貸 Productsレビュー・完了報告 | `*/15 6-12 * * *` | `sakura/scripts/review_anjo_1k_product_draft.py` |
| デイリー売買情報レポート Productsレビュー・完了報告 | `*/15 6-12 * * *` | `sakura/scripts/review_daily_sale_product_report.py` |
| 安城市1K賃貸 レビュー滞留の再確認 | `10,40 6-12 * * *` | `scripts/run_report_job.py --job pending-review-surface --task-code PTY-ANJO-1K-DAILY` |
| デイリー売買情報レポート レビュー滞留の再確認 | `12,42 6-12 * * *` | `scripts/run_report_job.py --job pending-review-surface --task-code PROP-07` |

レビュー用スクリプトはAnimaのランタイム配下、`run_report_job.py` はリポジトリ配下にある。実行するPythonのパスは既存のcron設定を維持する。

- `review_hold: false` を明示して承認したものだけ完了更新・完成報告する。保留中・承認不明のものを通知再開のために承認扱いにしない。
- `confirmed` はオーナー管理。通知の復旧・再試行では変更しない。
- `--local-only` は外部送信を行わない限定作業用。通常のcronに残すと、レビューが終わってもDiscord報告が止まる。
- 限定作業時の「外部通知禁止」という説明がcronや作業メモに残っている場合、通常運用への復帰に合わせて説明も更新する。

## 報告がない場合の確認順序

### 新規売買物件の投資可否分析（2026-10-25追加）

`daily-sale-info` は既存の掲載差分 `comparison.new_rows` 全件を対象に、
`E:/OneDriveBiz/Obsidian/_notes/Property/` に物件別Markdownと一覧を作成する。
`31_Property DB.base` の「新規」ビューで表示するため、タグは `新規` とし、
`日付`・`作成日時`・`物件番号`・`書類名` を付与する。`物件` は確認できた物件名だけを記入し、不明なら空欄にする。
ノート名（Baseのname欄）は、物件名が不明なら「所在地・構造・築年・価格」
（例: `今池町・RC・1987年・5000万円`）とする。同名ノートとの衝突時のみ日付等を付ける。
一次通過の有無で対象を絞らない。継続掲載・ID付け替えは既存の差分判定に従う。
新規ゼロは作成対象なし、履歴比較不可は新規判定保留として日次Productsに明示する。

分析には掲載値と出典JSONのSHA-256、一次判断、NOI・返済・CF・DSCRの仮定別試算、
修繕・法務・ハザード・出口の確認事項を含める。試算の空室率・経費率・融資条件は仮定を明記する。
8%は従来の表面利回り一次基準であり、購入可能の確定判断ではない。資料不足は判断保留。

日次Productsから一覧にリンクし、Hikaru証跡の `investment_analysis` に個別ファイルと一覧のパス・SHA-256を保存する。
既存日次分の再実行では未作成の分析を補完し、再収集やProductsの重複作成はしない。
Sakuraのランタイムスクリプト `review_daily_sale_product_report.py` は
`core.reports.property.sale_investment_analysis.validate_evidence_analysis` で分析を検証し、
`notification_text` の分析件数・一覧パスを通常の完成通知に含める。
同スクリプトはレビュー結果にも `investment_analysis` を引き継ぐ。
レビュー保留解除と既存の通知重複防止は引き続き適用する。cron時刻・コマンドは変更不要。

### 売買物件番号

`SalePortals/property-registry.sqlite3` で `PROP-000001` 形式の番号を永続管理する。
初回は保存済みの掲載履歴から採番する。レポートのPコードとは別の番号である。
掲載URLの履歴を優先し、別URLは所在地・築年月・建物面積・土地面積・戸数の一致で照合する。
価格・利回りは照合キーに含めず、価格変更や媒体違いでも同じ番号を維持する。
一致に必要な情報が不足する掲載や、複数候補がある掲載は別番号として保留し、誤統合を避ける。
一覧ページURLは複数物件を含み得るため、URLだけでは統合しない。

日次Productsの各表に物件番号を付加し、全掲載の番号台帳を付ける。
元JSON/CSVは保存証跡として保持し、番号付データは同日の `numbered-listings.json` / `.csv` に出力する。
Hikaru証跡の `property_numbering` にファイルパスとSHA-256、掲載数と重複統合後の物件数を保存する。
新規差分に同じ番号が複数ある場合、分析は物件ごとに1件にまとめ、掲載元と価格差を本文に残す。
2026-10-25は15掲載を8物件に統合し、PROP-000023の既存掲載をユーザー依頼で試行分析した。
試行分析は日次の `new_count` や `investment_analysis` に混入させず、日次本文から別途リンクする。

### 通知の確認

1. Productsの `task_code`・`report_date`・ファイルパスで対象を特定する。Pコードだけでは特定しない。2026-10-17には賃貸と売買で `P-00391` が重複しており、今回の通知復旧では改番していない。
2. レビュー証跡の `status` と `discord.status` を確認する。`done_local` / `deferred` はローカルレビューだけの完了で、Discord送信済みを意味しない。
3. 保留理由が残る場合は、生成証跡・元データとコピー・掲載件数・必要な保存履歴を照合してレビューを閉じる。掲載情報の整合性と、投資適格性・予測モデルの精度検証を分ける。
4. 完了・承認済みの未通知分だけ、対応するレビュー用スクリプトに報告日を `YYYYMMDD` で渡して再実行する。通知するときは `--local-only` を付けない。データの再収集や再生成は不要。
5. 送信応答のmessage IDと、Discord上の実メッセージを照合する。応答不明の場合は実メッセージを調べ、確認前に再送しない。
6. 同じ対象を再実行し、`NOOP_ALREADY_REVIEWED` または未通知0件になることを確認する。
7. cron変更後は `state/cron_registration.json` の再読込時刻と登録結果を確認する。プロセスの再起動が必要なら、作業中でないことを確認したSakuraだけを対象にする。サーバー全体を再起動しない。

## 2026-10-18の復旧結果

前回の復旧で4ジョブに残した `--local-only` が通知停止の原因だった。設定を解除し、通常の完成報告へ戻した。

- 賃貸：10/12〜18の7件を補送。
- 売買：10/13・14・16・17・18の5件を補送。10/15は既に送信済みだったため再送していない。
- 売買10/17・18は、保留中だった正式生成証跡・元/コピーJSON・CSV・Markdown・掲載日数履歴を独立照合。各15掲載・一次通過4件を確認して承認後に送信した。
- 12件すべてのmessage IDを保存し、Discordの実メッセージを再取得して照合。再実行時の承認済み未通知は0件。
- 最新日のmessage ID：売買 `1561328465259528206`、賃貸 `1561328472964599909`。
- 通知先スレッド：`1491411026263146658`。Sakura再起動後、19:43:03 JSTの設定再読込で6ジョブ登録・拒否0件を確認。

ローカル証跡・バックアップ・送信前後のDiscord取得結果は、次の場所に保存した。これらと実際のcron・ProductsはGit管理外で、この文書のコミットだけでは実環境の設定は変更されない。

```text
E:\OneDriveBiz\Obsidian\_data\Property\Products\2026\10\18\discord-recovery\
  audit.json
  send-receipts.json
  verified-message-ids.json
  completion.json
  discord-before.json
  discord-after.json
  backups\
```
