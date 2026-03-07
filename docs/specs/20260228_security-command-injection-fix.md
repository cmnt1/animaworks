# セキュリティ修正: コマンドインジェクション — `| sh` ブロック + 改行検出

## Overview

`execute_command` のブロックパターンに `| sh` / `| bash` の汎用パターンが欠落しており、`echo "payload" | sh` で任意コード実行が可能。また `_INJECTION_RE` が改行文字を検出しないため、改行によるコマンド分離も可能。Critical 脆弱性。

## Problem / Background

### 脆弱性 1: `| sh` / `| bash` のブロック不足

`core/tooling/handler_base.py` の `_BLOCKED_CMD_PATTERNS` は `curl|wget` を起点とする `| sh` のみをブロックしているが、任意コマンドからの `| sh` をブロックしていない。

```python
# 現在のパターン（curl/wget のみ対象）
(re.compile(r"(curl|wget)\b.*\|\s*(ba)?sh\b"),
 "Remote code execution (curl/wget|sh) is blocked"),
```

攻撃例:
- `echo "rm -rf /" | sh`
- `cat /tmp/script.sh | bash`
- `printf '%s' 'malicious_command' | sh`

`permissions.md` で `echo`, `cat`, `printf` が許可されている場合、ブロックを完全にバイパスできる。

### 脆弱性 2: 改行文字の未検出

`_INJECTION_RE` は `;`, バッククォート, `$()`, `${}`, `$VAR` を検出するが、改行文字 `\n` を含んでいない。

```python
_INJECTION_RE = re.compile(r"[;`]|\$\(|\$\{|\$[A-Za-z_]")
```

`use_shell=True` のとき（パイプ/リダイレクト含む場合）、bash は改行をコマンド区切りとして解釈するため、改行を含む入力でインジェクション可能。

### Impact

| コンポーネント | 影響 | 説明 |
|--------------|------|------|
| `core/tooling/handler_base.py` | Direct | `_BLOCKED_CMD_PATTERNS` にパターン追加、`_INJECTION_RE` に改行追加 |
| `core/tooling/handler_perms.py` | Related | セグメント分割ロジックの改行対応 |

## Decided Approach / 確定方針

### 修正 1: `| sh` / `| bash` の汎用ブロック

`_BLOCKED_CMD_PATTERNS` に汎用的な `| sh` / `| bash` パターンを追加:

```python
(re.compile(r"\|\s*(ba)?sh\b"),
 "Piping to sh/bash is blocked for security"),
```

既存の `curl|wget` 専用パターンはこの汎用パターンに包含されるため、残しても冗長なだけだが、後方互換性のために残置してもよい。

### 修正 2: 改行文字の検出

`_INJECTION_RE` に改行を追加:

```python
_INJECTION_RE = re.compile(r"[;\n`]|\$\(|\$\{|\$[A-Za-z_]")
```

または、`_check_command_safety()` の冒頭で改行を含むコマンドを別途拒否:

```python
if "\n" in command:
    return "Error: newline characters in commands are not allowed."
```

### 修正 3: `| python` / `| perl` / `| ruby` の検討

`sh`/`bash` 以外のインタープリタ（`python`, `perl`, `ruby`, `node`）へのパイプも同様に危険。ただし正当なユースケースとの兼ね合いがあるため、要検討。最低限 `| sh` / `| bash` はブロック必須。

## Test Plan

- [ ] `echo "test" | sh` が拒否されること
- [ ] `cat file.sh | bash` が拒否されること
- [ ] `printf 'x' | sh` が拒否されること
- [ ] 正規のパイプ（`ls | grep foo`）が正常動作すること
- [ ] 改行を含むコマンドが拒否されること
- [ ] `curl https://example.com | sh` が引き続き拒否されること（既存テスト互換）
- [ ] `| python` / `| perl` のブロック方針が確定し、テストが追加されていること（Phase 2）
