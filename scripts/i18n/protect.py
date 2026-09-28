"""Protect non-translatable Markdown/YAML fragments with verifiable sentinels."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

_SENTINEL_RE = re.compile(r"⟦P\d+⟧")


class ProtectionError(ValueError):
    """Raised when protected data cannot be restored exactly once."""


@dataclass(frozen=True)
class ProtectedText:
    text: str
    values: dict[str, str]

    def restore(self, translated: str) -> str:
        """Restore every sentinel, rejecting loss, duplication, or invention."""
        counts = Counter(_SENTINEL_RE.findall(translated))
        expected = Counter({sentinel: 1 for sentinel in self.values})
        if counts != expected:
            missing = sorted((expected - counts).elements())
            extra = sorted((counts - expected).elements())
            raise ProtectionError(f"Sentinel mismatch (missing={missing}, extra={extra})")

        result = translated
        for sentinel, value in self.values.items():
            result = result.replace(sentinel, value)
        return result


class _Protector:
    def __init__(self, start_index: int = 0) -> None:
        self.values: dict[str, str] = {}
        self.next_index = start_index

    def keep(self, value: str) -> str:
        # A later pattern can span sentinels from an earlier pass (a path around
        # {placeholders}); fold them back in so every sentinel stays top-level.
        value = _SENTINEL_RE.sub(lambda match: self.values.pop(match.group(0), match.group(0)), value)
        sentinel = f"⟦P{self.next_index}⟧"
        self.next_index += 1
        self.values[sentinel] = value
        return sentinel

    def patterns(self, text: str, patterns: tuple[re.Pattern[str], ...]) -> str:
        for pattern in patterns:
            text = pattern.sub(lambda match: self.keep(match.group(0)), text)
        return text


def _protect_fenced_code(text: str, protector: _Protector) -> str:
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    code: list[str] = []
    fence_char: str | None = None
    fence_size = 0

    for line in lines:
        match = re.match(r"^ {0,3}(`{3,}|~{3,})", line)
        if fence_char is None:
            if match:
                fence = match.group(1)
                fence_char = fence[0]
                fence_size = len(fence)
                code = [line]
            else:
                output.append(line)
            continue

        code.append(line)
        close = re.match(r"^ {0,3}(`+|~+)[ \t]*(?:\r?\n)?$", line)
        if close and close.group(1)[0] == fence_char and len(close.group(1)) >= fence_size:
            output.append(protector.keep("".join(code)))
            code = []
            fence_char = None
            fence_size = 0

    if code:
        output.append(protector.keep("".join(code)))
    return "".join(output)


_INLINE_PATTERNS = (
    re.compile(r"⟦§\d+⟧"),
    re.compile(r"(`+)[^`\n]*?\1"),
    re.compile(r"(?<=\]\()([^\s)]+)(?=[^)]*\))"),
    re.compile(r"<!--.*?-->", re.DOTALL),
    re.compile(r"</?[A-Za-z][^<>]*?>"),
    re.compile(r"\{\{|\}\}"),
    re.compile(r"\{[A-Za-z_][A-Za-z0-9_.]*\}"),
    re.compile(r"https?://[^\s<>()`\u3000-\u9fff\uff00-\uffef]+"),
    re.compile(r"\$\{[A-Za-z_][A-Za-z0-9_]*\}|\$[A-Za-z_][A-Za-z0-9_]*"),
    re.compile(r"(?<![\w])(?:~?/|(?:[A-Za-z0-9_.-]+/)+)[^\s`<>()[\]{}ぁ-んァ-ン一-龯々〆ヵヶ]+"),
    re.compile(r"(?<![A-Za-z0-9_])[A-Za-z0-9_./~-]+\.(?:md|py|json|toml|yaml|sh)(?![A-Za-z0-9_])", re.IGNORECASE),
    re.compile(r"(?<![\w@])@[A-Za-z0-9_.-]+"),
    re.compile(r"Use when:"),
)

_FRONTMATTER_LINE_RE = re.compile(r"^(\s*)([A-Za-z_][A-Za-z0-9_-]*)(\s*:\s*)(.*?)(\r?\n)?$")
_ALLOWED_FRONTMATTER_KEYS = {"description", "title", "summary"}


def _protect_frontmatter(text: str, protector: _Protector) -> str:
    lines = text.splitlines(keepends=True)
    output: list[str] = []
    block_indent: int | None = None
    for line in lines:
        stripped = line.rstrip("\r\n")
        newline = line[len(stripped) :]
        if stripped in {"---", "..."}:
            output.append(protector.keep(line))
            block_indent = None
            continue

        indent = len(line) - len(line.lstrip(" "))
        if block_indent is not None:
            if not stripped.strip() or indent > block_indent:
                leading = line[:indent]
                content = line[indent:]
                output.append(protector.keep(leading) if leading else "")
                output.append(protector.patterns(content, _INLINE_PATTERNS))
                continue
            block_indent = None

        match = _FRONTMATTER_LINE_RE.match(line)
        if not match or match.group(2) not in _ALLOWED_FRONTMATTER_KEYS:
            output.append(protector.keep(line))
            continue

        leading, key, separator, value, _newline = match.groups()
        output.append(protector.keep(f"{leading}{key}{separator}"))
        if re.match(r"[|>][+-]?(?:\s*(?:#.*)?)?$", value):
            output.append(protector.keep(value + newline))
            block_indent = len(leading)
            continue

        quote = value[:1] if value[:1] in {"'", '"'} else ""
        if quote and len(value) >= 2 and value.endswith(quote):
            output.append(protector.keep(quote))
            output.append(protector.patterns(value[1:-1], _INLINE_PATTERNS))
            output.append(protector.keep(quote))
        else:
            comment_match = re.search(r"\s+#.*$", value)
            value_text = value
            suffix = ""
            if comment_match:
                value_text = value[: comment_match.start()]
                suffix = value[comment_match.start() :]
            output.append(protector.patterns(value_text, _INLINE_PATTERNS))
            if suffix:
                output.append(protector.keep(suffix))
        if newline:
            output.append(protector.keep(newline))

    return "".join(output)


def protect_text(text: str, *, frontmatter: bool = False, sentinel_start: int = 0) -> ProtectedText:
    """Replace code, identifiers, links, paths, and structural syntax with sentinels."""
    if re.search(r"⟦P\d+⟧", text):
        raise ProtectionError("Source text already contains a reserved sentinel")
    protector = _Protector(sentinel_start)
    if frontmatter:
        protected = _protect_frontmatter(text, protector)
    else:
        protected = _protect_fenced_code(text, protector)
        protected = protector.patterns(protected, _INLINE_PATTERNS)
    return ProtectedText(protected, protector.values)
