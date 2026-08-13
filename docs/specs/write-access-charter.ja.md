# 書き込み権限定款（正本）

制定: 2026-08-13（taka承認）。本書はanimaのファイル書き込み権限に関する**唯一の正本**である。
サンドボックスプロファイル・permissions.json・procedures・指示書は全て本書に従う。
本書と実装が食い違う場合、それはバグであり実装側を直す。

## 原理原則（3行ルール）

anima が書き込めるのは次の**2種類の場所だけ**である。例外リストを育てない。

1. **`companies/<自社>/shared/`** — 無条件・常に読み書き可。全エンジン（codexシェル・MCP・grok・ネイティブfileツール）で同一。
2. **作業ディレクトリ** — `permissions.json` の `file_roots` に列挙された **data_dir 外**のパス（例: `~/dev/AI-Schreiber`）。`.git` を含め全権限。宣言＝実効を常に一致させる。

そして配置規則:

3. **worktree は必ず `companies/<自社>/shared/worktrees/` に作る。** それ以外の場所への worktree 作成は禁止。

## 派生規則

- `file_roots` に data_dir（`~/.animaworks`）配下のパスを書くことは**起動時エラー**とする。「宣言したのに効かない」状態を構造的に禁止する。
- タスクで明示された workspace（`task_cwd`）は書き込み可（オプトイン）。指示で明示されたディレクトリで作業が止まってはならない。
- deny 側（他社ディレクトリ・秘密情報・`permissions.json` 自身の保護・`shell_internal_deny_paths`）は本書の対象外で現状維持。
- グローバル `shared/repos`・`shared/worktrees` は廃止。会社 shared へ移設する。
- 個別の carve-out（特定サブツリーの再許可）を今後追加してはならない。書けない場所が必要になったら、会社 shared への移設か作業ディレクトリへの追加で解決する。

## 設計上の禁止事項（実装者への指示）

- **複雑にしない。** 新しい抽象・設定項目・例外分岐を追加しない。本定款の実装は「削除＋バリデーション」が主であるべき。
- 「安全のため」を理由に本ルールへ条件を追加しない。安全性の根拠は以下で完結している:
  - ホストのプロンプト組み立てが読むのは `companies/<社>/knowledge`・`skills`・`vision.md`・`company.json` のみで `shared/` は読まない（2026-07-22 検証済み）→ symlink 差し替え攻撃面は増えない
  - 秘密情報・他社領域は deny 側で従来どおり遮断される
- エンジン間（codexシェル/MCP・grok・ネイティブ）で権限判定を重複実装しない。共通ヘルパー1本に集約する。

## 背景

2026-07-17 の FS 分離以降、「data_dir 配下の write root を一律無効化し、必要箇所を carve-out で個別復活」という方式が EROFS 障害を7回以上再発させた（notification_map / delegate_task / company shared / .git / cache / shared/worktrees / dev直下worktree）。原因は宣言（file_roots）と実効権限の二重帳簿。本定款はこれを「書ける場所は2種類だけ」に畳むことで根絶する。
