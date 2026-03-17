# エンジニア専門ガイドライン

## コーディング原則

- **最小変更**: 既存コードへの変更は必要最小限。大規模リファクタは明示指示時のみ。スコープ外修正は別タスク記録
- **YAGNI**: 将来の拡張を予測してコードを複雑にしない。抽象化は同パターン3回出現後（Rule of Three）
- **セキュリティ**: 入力バリデーション必須、SQLはパラメータバインディング、シークレットのハードコード禁止、`pathlib.Path`でパストラバーサル防止、`shell=True`回避

## コード品質

- `from __future__ import annotations` + `str | None` 形式の型ヒント必須
- `pathlib.Path` でパス操作、Google-style docstring、`logging.getLogger(__name__)`
- Pydantic Model / dataclass でデータ定義
- セマンティックコミット: `feat:` / `fix:` / `refactor:` / `docs:` / `test:` / `chore:`

## テスト・エラーハンドリング

- コード変更後は関連テスト確認。新関数にはユニットテスト追加
- 具体的な例外をキャッチ（裸の `except:` 禁止）。リトライには指数バックオフ
- `async/await` + `asyncio.Lock()`。CPU-boundは `asyncio.to_thread()`

プロジェクト固有の規約はリポジトリの `.cursorrules` / `CLAUDE.md` を参照
