> 確認したコミット: 193a5e72

# 記憶の統合と忘却

記憶の統合は Anima による判断と、フレームワークが行う候補収集・索引保守から成る。時刻は設定可能であり、既定の日次統合は 02:00、週次統合は日曜 03:00 である。週次統合は `weekly_enabled` が有効な場合に実行される。

## 日次処理

`core/supervisor/_mgr_scheduler.py` が日次 job を登録し、`core/lifecycle/system_consolidation.py` の `_handle_daily_consolidation` が対象 Anima を選ぶ。無活動期間や直近 24 時間の記録数に応じて、実行を見送ることがある。

Anima の `run_consolidation` は前日の活動ログを日付付きのエピソードへ要約し、要約から atomic facts を抽出する。その後の framework post-processing は次の順に進む。

1. `ForgettingEngine.synaptic_downscaling` が低活性候補を索引上でマークする。
2. `knowledge_self_correction` が対象となる知識・手順を LLM で見直し、解決済み課題から手順を作成する。

この補正は `core/lifecycle/knowledge_correction.py` が上限を管理しながら実行する。詳細な再固定化条件は後述する。

## 週次処理

週次の Anima cycle は `core/anima/lifecycle.py` の `_run_weekly_consolidation` が担う。`ConsolidationEngine` が merge、fact 間の conflict、忘却候補を用意し、`hygiene.py` が知識ファイルの形式やサイズ上の確認候補をレポートにする。これらは週次プロンプトに含まれ、Anima が内容を判断して記憶ファイルを更新・保管する。hygiene scan 自体は記憶ファイルを移動・削除しない。

週次処理の後には、`ProceduralDistiller.weekly_pattern_distill` が活動ログ中の反復パターンを手順候補へ蒸留する。さらに `skill_autolearn_enabled` が有効なら、適格な手順から低リスクの probation skill を作成する。

## 忘却候補と閾値

`core/memory/maintenance/forgetting.py` の日次 downscaling は、通常の知識・エピソードについて、最終利用から 90 日を超え、利用回数が 3 未満の場合に低活性として印を付ける。手順は別基準で、180 日を超えて未使用かつ利用合計が 3 未満の場合、または失敗が 3 回以上で効用が 0.3 未満の場合に低活性として印を付ける。保護済みの記憶や再利用されている記憶は対象から除外される。

週次の忘却候補には、低活性状態が 90 日を超え、利用回数が 2 以下の記憶が含まれる。これは削除命令ではなく、Anima が本文や周辺情報を見て保管するかを決めるための候補である。候補提示の対象や保護規則の実装は `ForgettingEngine` が担う。

## 手続きの利用追跡と再固定化

手順を使った後は `report_procedure_outcome` で成功または失敗を記録する。結果は frontmatter の `success_count`、`failure_count` と `confidence` の更新に使われる。

`core/memory/maintenance/reconsolidation.py` は手順の `failure_count >= 1` **または** `confidence < 0.6` を満たす場合に再固定化候補とする。LLM が改訂した場合は旧版を保管し、`version` を進め、成功・失敗カウンターと信頼度を初期値に戻す。

## RAG 索引の定期更新

RAG 索引更新は週次統合とは別の単一スケジュールである。`core/supervisor/_mgr_scheduler.py` の日次 indexing job が既定 04:00 に記憶ファイル、facts、共有データを反映し、BM25 と entity 索引も更新する。週次 post-processing が別途 RAG 全体を再構築する経路はない。索引と復旧経路は[意図的想起と検索](retrieval.md)を参照する。
