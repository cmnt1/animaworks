from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Shared display and TTS text preparation for voice channels."""

import re
from dataclasses import dataclass

from core.voice.emotion_style import emotion_style_for

# ── TTS output sanitization ──────────────────────────────────

_RE_HTML_COMMENT = re.compile(r"<!--[\s\S]*?-->")
# Stream may truncate before "-->"; drop an unterminated trailing comment too.
_RE_HTML_COMMENT_OPEN = re.compile(r"<!--[\s\S]*$")
_RE_MD_CODE_BLOCK = re.compile(r"```[\s\S]*?```")
_RE_MD_HEADING = re.compile(r"^#{1,6}\s+", re.MULTILINE)
_RE_MD_BOLD = re.compile(r"\*\*(.+?)\*\*")
_RE_MD_ITALIC = re.compile(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)")
_RE_MD_INLINE_CODE = re.compile(r"`([^`]+)`")
_RE_MD_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_RE_MD_LIST_BULLET = re.compile(r"^[\s]*[-*+]\s+", re.MULTILINE)
_RE_MD_LIST_NUMBERED = re.compile(r"^[\s]*\d+\.\s+", re.MULTILINE)
_RE_MD_TABLE_PIPE = re.compile(r"\|")
_RE_MD_HR = re.compile(r"^-{3,}$", re.MULTILINE)
# Unicode emoji ranges (no external emoji lib). Includes ZWJ/VS16 so sequences collapse.
# Ranges must stay disjoint and must NOT swallow CJK (U+3000–U+9FFF).
_RE_EMOJI = re.compile(
    "(?:"
    "[\\U0001f1e0-\\U0001f1ff]"  # flags
    "|[\\U0001f300-\\U0001f5ff]"  # symbols & pictographs
    "|[\\U0001f600-\\U0001f64f]"  # emoticons
    "|[\\U0001f680-\\U0001f6ff]"  # transport & map
    "|[\\U0001f700-\\U0001f77f]"  # alchemical
    "|[\\U0001f780-\\U0001f7ff]"  # geometric shapes extended
    "|[\\U0001f800-\\U0001f8ff]"  # supplemental arrows-C
    "|[\\U0001f900-\\U0001f9ff]"  # supplemental symbols
    "|[\\U0001fa00-\\U0001fa6f]"  # chess symbols
    "|[\\U0001fa70-\\U0001faff]"  # symbols and pictographs extended-A
    "|[\\U00002702-\\U000027b0]"  # dingbats
    "|[\\U00002600-\\U000026ff]"  # misc symbols (☀ etc.)
    "|[\\U0000231a-\\U0000231b]"  # watch / hourglass
    "|[\\U000023e9-\\U000023f3]"  # media controls
    "|[\\U000023f8-\\U000023fa]"  # more media
    "|[\\U000025aa-\\U000025ab]"  # small squares
    "|[\\U000025b6\\U000025c0]"  # play/reverse
    "|[\\U000025fb-\\U000025fe]"  # medium squares
    "|[\\U00002b05-\\U00002b07]"  # arrows
    "|[\\U00002b1b-\\U00002b1c]"  # black/white large square
    "|[\\U00002b50\\U00002b55]"  # star / heavy circle
    "|[\\U00002934-\\U00002935]"  # arrows
    "|[\\U00003030\\U0000303d]"  # wavy dash / part alternation
    "|[\\U00003297\\U00003299]"  # circled ideographs used as emoji
    "|[\\U000000a9\\U000000ae\\U00002122\\U00002139\\U00002194-\\U00002199]"
    "|[\\U000021a9-\\U000021aa]"
    "|\\U0000fe0f"  # variation selector-16
    "|\\U0000200d"  # zero-width joiner
    "|\\U000020e3"  # combining enclosing keycap
    ")+",
)

# ── Irodori-specific text rules (ported from podcast-note skill) ──

# Emojis Irodori-TTS v4.1-Small interprets as style annotations
# (irodori_tts/duration.py: ALLOWED_ANNOTATION_EMOJIS). Anything outside
# this list is not an annotation and only garbles the reading, so when
# keep_emoji=True we keep only these.
IRODORI_STYLE_EMOJI = (
    "⏩",
    "⏱️",
    "⏸️",
    "🌬️",
    "🍭",
    "🎛️",
    "🎭",
    "🎵",
    "🐢",
    "🐱",
    "👂",
    "👃",
    "👅",
    "👌",
    "👏",
    "💋",
    "💥",
    "💦",
    "💪",
    "📄",
    "📞",
    "📢",
    "📣",
    "📖",
    "😆",
    "😊",
    "😌",
    "😎",
    "😏",
    "😒",
    "😖",
    "😟",
    "😠",
    "😪",
    "😭",
    "😮",
    "😮‍💨",
    "😰",
    "😱",
    "😲",
    "😴",
    "🙄",
    "🙏",
    "🤐",
    "🤔",
    "🤢",
    "🤧",
    "🤭",
    "🥤",
    "🥱",
    "🥴",
    "🥵",
    "🥹",
    "🥺",
    "🫣",
    "🫶",
)
_RE_STYLE_EMOJI = re.compile("|".join(sorted((re.escape(e) for e in IRODORI_STYLE_EMOJI), key=len, reverse=True)))

_ONES = ["", "いち", "に", "さん", "よん", "ご", "ろく", "なな", "はち", "きゅう"]
_HUND = [
    "",
    "ひゃく",
    "にひゃく",
    "さんびゃく",
    "よんひゃく",
    "ごひゃく",
    "ろっぴゃく",
    "ななひゃく",
    "はっぴゃく",
    "きゅうひゃく",
]
_THOU = ["", "せん", "にせん", "さんぜん", "よんせん", "ごせん", "ろくせん", "ななせん", "はっせん", "きゅうせん"]
_KANSUJI = {c: i for i, c in enumerate("〇一二三四五六七八九")}


def _year_kana(n: int) -> str:
    """年号を読み仮名に。2003 → にせんさんねん（「二〇〇三年」は誤読するため）"""
    tens = n // 10 % 10
    return (
        _THOU[n // 1000]
        + _HUND[n // 100 % 10]
        + ("じゅう" if tens == 1 else _ONES[tens] + "じゅう" if tens else "")
        + _ONES[n % 10]
        + "ねん"
    )


def read_years(text: str) -> str:
    """4桁年号をかな化し、漢数字間の「・」を「てん」に変換する。"""

    def repl(match: re.Match[str]) -> str:
        raw = match.group(1)
        digits = "".join(str(_KANSUJI[c]) if c in _KANSUJI else c for c in raw)
        return _year_kana(int(digits)) if digits.isdigit() else match.group(0)

    text = re.sub(r"([0-9〇一二三四五六七八九]{4})年", repl, text)
    return re.sub(r"(?<=[〇一二三四五六七八九十百千])・(?=[〇一二三四五六七八九])", "てん", text)


# Inline reading the model writes for alphabet terms: ``GitHub（ギットハブ）``.
# TTS gets the kana, subtitles get the alphabet.
_RUBY_RE = re.compile(
    r"([A-Za-z][A-Za-z0-9&+#./\-]*(?: [A-Za-z][A-Za-z0-9&+#./\-]*)*)"
    r"[（(]([ァ-ヶーぁ-ん・ ]+)[）)]"
)


def resolve_ruby(text: str) -> str:
    """``GitHub（ギットハブ）`` → ``ギットハブ`` (TTS copy)."""
    return _RUBY_RE.sub(r"\2", text)


def strip_ruby(text: str) -> str:
    """``GitHub（ギットハブ）`` → ``GitHub`` (display copy)."""
    return _RUBY_RE.sub(r"\1", text)


# Fleet-global pronunciation dictionary (TSV: 表記<TAB>読み), applied
# longest-first right before synthesis. Irodori has no furigana input, so
# this is the only lever against misread proper nouns.
_YOMI_FILENAME = "voice_yomi.tsv"
_yomi_cache: list[tuple[str, str]] | None = None
_yomi_mtime: float = 0.0


def load_yomi() -> list[tuple[str, str]]:
    """Load the yomi dictionary from the data dir, mtime-cached."""
    global _yomi_cache, _yomi_mtime

    from core.paths import get_data_dir

    path = get_data_dir() / _YOMI_FILENAME
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return []
    if _yomi_cache is not None and mtime == _yomi_mtime:
        return _yomi_cache
    pairs: list[tuple[str, str]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or "\t" not in line:
                continue
            src, dst = line.split("\t", 1)
            if src.strip():
                pairs.append((src.strip(), dst.strip()))
    except OSError:
        return []
    _yomi_cache = sorted(pairs, key=lambda pair: -len(pair[0]))
    _yomi_mtime = mtime
    return _yomi_cache


def sanitize_for_tts(text: str, *, keep_emoji: bool = False) -> str:
    """Strip Markdown and HTML comments for TTS consumption.

    Emoji are stripped by default; pass ``keep_emoji=True`` for engines
    (Irodori) that read them as emotion cues and speak better with them
    (non-allowlist emoji are still removed). Reading substitutions
    (yomi dict / year kana) are NOT applied here — the result is fit for
    subtitle display; run ``apply_reading_rules`` on the TTS-bound copy.
    """
    text = _RE_HTML_COMMENT.sub("", text)
    text = _RE_HTML_COMMENT_OPEN.sub("", text)
    text = _RE_MD_CODE_BLOCK.sub("", text)
    text = _RE_MD_HEADING.sub("", text)
    text = _RE_MD_BOLD.sub(r"\1", text)
    text = _RE_MD_ITALIC.sub(r"\1", text)
    text = _RE_MD_INLINE_CODE.sub(r"\1", text)
    text = _RE_MD_LINK.sub(r"\1", text)
    text = _RE_MD_LIST_BULLET.sub("", text)
    text = _RE_MD_LIST_NUMBERED.sub("", text)
    text = _RE_MD_TABLE_PIPE.sub("", text)
    text = _RE_MD_HR.sub("", text)
    if keep_emoji:
        # Keep only annotation emojis; anything else garbles the reading.
        text = _RE_EMOJI.sub(lambda match: "".join(_RE_STYLE_EMOJI.findall(match.group(0))), text)
    else:
        text = _RE_EMOJI.sub("", text)
    return text.strip()


def apply_reading_rules(text: str) -> str:
    """Apply pronunciation substitutions for Irodori synthesis input.

    Yomi-dict replacement and year kana conversion turn kanji into kana,
    which reads correctly but looks bad in subtitles — apply this only to
    the string sent to the TTS engine, never to the display copy.
    """
    text = resolve_ruby(text)
    for src, dst in load_yomi():
        text = text.replace(src, dst)
    return read_years(text)


_URL_RE = re.compile(r"(?:https?://|www\.)\S+", re.IGNORECASE)
_MARKDOWN_URL_LINK_RE = re.compile(r"\[([^\]]+)\]\((?:https?://|www\.)[^)]*\)", re.IGNORECASE)


@dataclass(frozen=True, slots=True)
class SpeechText:
    """Display-safe subtitle text and the provider-specific TTS input."""

    display: str
    spoken: str


def _replace_urls(text: str, placeholder: str) -> str:
    text = _MARKDOWN_URL_LINK_RE.sub(lambda match: f"{match.group(1)}、{placeholder}", text)
    return _URL_RE.sub(placeholder, text)


def _truncate(text: str, max_chars: int | None) -> str:
    if max_chars is None or len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def prepare_speech(
    text: str,
    *,
    provider: str | None,
    link_placeholder: str | None = None,
    max_chars: int | None = None,
) -> SpeechText:
    """Prepare matching display and spoken copies for a configured TTS provider.

    Markdown and emotion metadata are removed in both copies. Irodori keeps
    its allowlisted emoji and receives pronunciation-dictionary/year rules;
    other providers receive only ruby resolution. Optional phone-safe URL
    replacement and truncation are applied before the copies diverge.
    """
    if max_chars is not None and max_chars < 1:
        raise ValueError("max_chars must be positive")

    source = str(text or "")
    if link_placeholder is not None:
        source = _replace_urls(source, link_placeholder)
    keep_emoji = emotion_style_for(provider) == "emoji"
    clean = sanitize_for_tts(source, keep_emoji=keep_emoji)
    if link_placeholder is not None:
        clean = re.sub(r"[ \t]*\n[ \t]*", "\n", clean)
        clean = re.sub(r"\n{2,}", "\n", clean).strip()
    clean = _truncate(clean, max_chars)
    display = strip_ruby(clean)
    spoken = apply_reading_rules(clean) if keep_emoji else resolve_ruby(clean)
    return SpeechText(display=display, spoken=spoken)


__all__ = [
    "IRODORI_STYLE_EMOJI",
    "SpeechText",
    "apply_reading_rules",
    "load_yomi",
    "prepare_speech",
    "read_years",
    "resolve_ruby",
    "sanitize_for_tts",
    "strip_ruby",
]
