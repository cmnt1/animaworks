### リポジトリ作業ルール

- canonical checkout の `main` / `master` は参照専用。実装・検証・commitは必ず専用の `git worktree` で行う
- 使い捨ての作業物（クローン・ビルド成果物・検証ログ・一時スクリプト）は環境変数 `ANIMAWORKS_SCRATCH_DIR` の下に置き、`state/` 直下に作業用ディレクトリを作らない。scratch はタスク終了時または24時間放置で自動削除される
- 他の anima と共有する worktree だけを `{data_dir}/companies/<会社>/shared/worktrees/` に作り、作業後は `git worktree remove` で片付ける。共有しない worktree は scratch に置き、24時間触られない worktree は自動削除される。canonical checkout への操作は `git worktree add` と参照に限る
- パッケージキャッシュは設定済みの共用キャッシュ（`UV_CACHE_DIR` 等）を使い、PR ごとのキャッシュディレクトリを作らない
- worktreeからのmergeは、canonical checkoutがcleanであることを確認してから行う。dirtyなら変更せず報告する
- 他者の変更を独断でstash・破棄・上書きしない
