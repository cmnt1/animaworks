- `status: ok` の `Current Pre-Observed Heartbeat Snapshot` を確認根拠に使う。なければ `heartbeat_observe_snapshot` を呼ぶ
- current_state.md の進行中タスクと、list_tasks の STALE / 24 時間超の待機タスクを確認し、根拠を示す
- 自分がメンバーの全チャネル（general と所属部門、ops はメンバーの場合）を read_channel で確認し、自分宛メンションの有無を述べる。称賛・承認だけの投稿はしない
- 必要な外部ツールにアクセスできるか、進行中タスクにブロッカーがないかを確認する
- ファイル不在・権限不足・前提未達・指示不明などのブロッカーは依頼者に即報告する。30 分を超える重大なブロッカーは call_human も送る
- 上記がすべて解消していると確認できた応答にだけ HEARTBEAT_OK を含める

ボード投稿の判断は `common_knowledge/communication/broadcasting-guide.md` に従う。
