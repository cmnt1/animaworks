from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Judgement and formatting helpers for mirroring Slack conversations.

The chat view mirrors both directions of a user's Slack conversation:

* replies the Anima sent (``external_reply_sent``) are recorded at send time
  and can also be derived from historical ``animaworks-tool slack send``
  Bash tool calls;
* messages an alias-registered user posted are recorded as ``human_reply``
  when the gateway hands them to the inbox.

This module keeps the addressability rules and Slack-markup formatting in
one place so the gateway, the Slack tool dispatcher and the conversation
reader all agree on what belongs in the chat view.
"""

import logging
import re
import shlex
from datetime import datetime
from typing import Any

from core.config.io import load_config

logger = logging.getLogger("animaworks.activity.slack_mirror")

_SLACK_SEND_RE = re.compile(r"\banimaworks-tool\s+slack\s+send\b")
_THREAD_CONTEXT_RE = re.compile(r"\[Thread context[^\]]*\].*?\[/Thread context\]\s*", re.DOTALL)
_ANNOTATION_LINE_RE = re.compile(
    r"^\s*\[(?:slack:|宛先注意:|Addressee notice:|슬랙:)[^\]]*\]\s*$",
    re.MULTILINE,
)
_MENTION_RE = re.compile(r"<@([A-Z0-9]+)>")
_CHANNEL_REF_RE = re.compile(r"<#([A-Z0-9]+)\|([^>]+)>")
_CHANNEL_BARE_RE = re.compile(r"<#([A-Z0-9]+)>")
_LINK_RE = re.compile(r"<(https?://[^|>]+)\|([^>]+)>")
_BARE_URL_RE = re.compile(r"<(https?://[^>]+)>")
_SHELL_STOP_TOKENS = frozenset({"&&", "||", ";", "|", "&", ">", ">>", "<"})
_THREAD_OPTIONS = frozenset({"--thread", "--thread-ts", "-t"})
_DERIVED_DUPLICATE_WINDOW_SEC = 600
_INBOUND_PAIR_WINDOW_SEC = 30


def aliased_slack_users() -> dict[str, str]:
    """Return ``{Slack user ID: alias}`` for configured user aliases."""
    try:
        aliases = load_config().external_messaging.user_aliases
    except Exception:
        logger.debug("Failed to load Slack user aliases", exc_info=True)
        return {}
    result: dict[str, str] = {}
    for alias, alias_cfg in (aliases or {}).items():
        slack_user_id = str(getattr(alias_cfg, "slack_user_id", "") or "").strip()
        if slack_user_id:
            result[slack_user_id] = str(alias)
    return result


def _alias_for_slack_user(
    *,
    text: str,
    channel: str,
    thread_ts: str,
    trigger: str,
    anima_name: str,
    aliases: dict[str, str],
    notification_thread_owner: str | None = None,
) -> str | None:
    """Resolve an alias with an already-loaded alias map (see public wrapper)."""
    if not aliases:
        return None

    # (a) The text mentions an alias-registered user.
    for uid in _MENTION_RE.findall(text or ""):
        if uid in aliases:
            return aliases[uid]

    # (b) The channel itself addresses an alias: a Slack user ID (DM) or "@alias".
    channel_value = str(channel or "").strip()
    if channel_value in aliases:
        return aliases[channel_value]
    if channel_value.startswith("@"):
        alias = channel_value[1:].strip()
        if alias in aliases.values():
            return alias

    # (c) This run is handling a Slack message from an alias-registered user.
    trigger_value = str(trigger or "").strip()
    if trigger_value.startswith("inbox:slack:"):
        uid = trigger_value[len("inbox:slack:") :].split(",", 1)[0].strip()
        if uid in aliases:
            return aliases[uid]

    # (d) The thread is a notification thread owned by this anima. The caller looks the
    # thread up (notification routing sits above this layer) and passes its owner.
    if thread_ts and anima_name and notification_thread_owner == anima_name:
        # The mapping has no per-user ID; the first configured alias is the
        # notification recipient (the current configuration has one).
        return next(iter(aliases.values()), None)

    return None


def slack_reply_recipient(
    *,
    text: str,
    channel: str,
    thread_ts: str,
    trigger: str,
    anima_name: str,
    notification_thread_owner: str | None = None,
) -> str | None:
    """Return the alias this Slack post is addressed to, or ``None``.

    A post counts as user-addressed when any of these holds:

    (a) *text* mentions an alias-registered Slack user,
    (b) *channel* is an alias-registered Slack user ID or ``@alias``,
    (c) *trigger* is ``inbox:slack:<UID>`` for an alias-registered UID,
    (d) *thread_ts* belongs to a notification thread owned by *anima_name*
        (*notification_thread_owner* is the owner the caller looked up).
    """
    return _alias_for_slack_user(
        text=text,
        channel=channel,
        thread_ts=thread_ts,
        trigger=trigger,
        anima_name=anima_name,
        aliases=aliased_slack_users(),
        notification_thread_owner=notification_thread_owner,
    )


def _display_text(text: str, aliases: dict[str, str], names: dict[str, str] | None = None) -> str:
    if not text:
        return ""

    value = text.lstrip()
    # Drop the leading mention of the addressee itself.
    leading = _MENTION_RE.match(value)
    if leading:
        value = value[leading.end() :].lstrip()

    names = names or {}

    def _replace_mention(match: re.Match[str]) -> str:
        uid = match.group(1)
        return "@" + aliases.get(uid, names.get(uid, uid))

    value = _MENTION_RE.sub(_replace_mention, value)
    value = _CHANNEL_REF_RE.sub(lambda m: f"#{m.group(2)}", value)
    value = _CHANNEL_BARE_RE.sub(lambda m: f"#{m.group(1)}", value)
    value = _LINK_RE.sub(lambda m: f"[{m.group(2)}]({m.group(1)})", value)
    value = _BARE_URL_RE.sub(lambda m: m.group(1), value)
    value = value.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    return value.strip()


def display_text_for_slack(text: str, names: dict[str, str] | None = None) -> str:
    """Convert Slack markup to Markdown suitable for the chat view.

    The leading ``<@UID>`` mention is removed (it addresses the recipient,
    not part of the message), other mentions become ``@alias``/display
    names, channels become ``#name`` and links become Markdown links.
    """
    return _display_text(text, aliased_slack_users(), names)


def strip_thread_context(text: str) -> str:
    """Remove thread-context and Slack annotation preludes from *text*."""
    if not text:
        return ""
    value = _THREAD_CONTEXT_RE.sub("", text, count=1)
    value = _ANNOTATION_LINE_RE.sub("", value)
    return value.strip()


def is_slack_send_command(command: str) -> bool:
    """Return True when *command* contains ``animaworks-tool slack send``."""
    return bool(command and _SLACK_SEND_RE.search(command))


def is_slack_send_tool_use(entry: Any) -> bool:
    """Return True when *entry* is a Bash tool_use running ``slack send``."""
    if getattr(entry, "type", "") != "tool_use":
        return False
    if getattr(entry, "tool", "") != "Bash":
        return False
    return is_slack_send_command(_tool_command(entry))


def is_user_addressed_slack_tool_use(
    entry: Any,
    *,
    anima_name: str = "",
    aliases: dict[str, str] | None = None,
) -> bool:
    """Return True when *entry* is a Slack send addressed to a configured user."""
    if not is_slack_send_tool_use(entry):
        return False
    parsed = parse_slack_send_command(_tool_command(entry))
    if parsed is None:
        return False
    channel, body, thread_ts = parsed
    alias_map = aliased_slack_users() if aliases is None else aliases
    meta = getattr(entry, "meta", {})
    trigger = str(meta.get("trigger", "")) if isinstance(meta, dict) else ""
    return (
        _alias_for_slack_user(
            text=body,
            channel=channel,
            thread_ts=thread_ts,
            trigger=trigger,
            anima_name=anima_name,
            aliases=alias_map,
        )
        is not None
    )


def _tool_command(entry: Any) -> str:
    meta = getattr(entry, "meta", None)
    if not isinstance(meta, dict):
        return ""
    args = meta.get("args")
    if isinstance(args, dict):
        command = args.get("command")
        if isinstance(command, str):
            return command
        return ""
    if isinstance(args, str):
        return args
    return ""


def _is_shell_redirection(token: str) -> bool:
    return token in {"<", ">", ">>", "<<", "&>"} or bool(re.fullmatch(r"\d*(?:>>?|<<?)(?:&\d+)?", token))


def parse_slack_send_command(command: str) -> tuple[str, str, str] | None:
    """Parse a ``animaworks-tool slack send`` shell command.

    Returns ``(channel, message, thread_ts)`` or ``None`` when the command is
    not parseable (e.g. truncated by the tool-call summary).  Shell prefixes
    such as ``cd ... && ...`` are accepted, and quoted messages may contain
    newlines or escapes.
    """
    if not command or not _SLACK_SEND_RE.search(command):
        return None
    try:
        tokens = shlex.split(command, posix=True)
    except ValueError:
        return None

    start = None
    for index in range(len(tokens) - 2):
        if tokens[index] == "animaworks-tool" and tokens[index + 1] == "slack" and tokens[index + 2] == "send":
            start = index + 3
            break
    if start is None or start >= len(tokens):
        return None

    positionals: list[str] = []
    thread_ts = ""
    index = start
    while index < len(tokens):
        token = tokens[index]
        if token in _SHELL_STOP_TOKENS or _is_shell_redirection(token):
            break
        if token in _THREAD_OPTIONS:
            if index + 1 >= len(tokens):
                return None
            thread_ts = tokens[index + 1]
            index += 2
            continue
        if token.startswith("--thread=") or token.startswith("--thread-ts="):
            thread_ts = token.split("=", 1)[1]
            index += 1
            continue
        if token.startswith("-t") and token != "-t":
            thread_ts = token[2:]
            index += 1
            continue
        positionals.append(token)
        index += 1

    if not positionals:
        return None
    channel = positionals[0]
    message = " ".join(positionals[1:])
    if not channel or not message:
        return None
    return channel, message, thread_ts


def _normalise(text: str) -> str:
    return " ".join(str(text or "").split())


def _seconds_between(earlier: str, later: str) -> float | None:
    try:
        first = datetime.fromisoformat(str(earlier).replace("Z", "+00:00"))
        second = datetime.fromisoformat(str(later).replace("Z", "+00:00"))
        return (second - first).total_seconds()
    except (TypeError, ValueError):
        return None


def _trigger_in_inbox_window(tool_use: Any, context_entries: list[Any]) -> str:
    """Return the Slack trigger of the inbox run that contains *tool_use*."""
    start_index = None
    for index, entry in enumerate(context_entries):
        if getattr(entry, "ts", "") > getattr(tool_use, "ts", ""):
            break
        if getattr(entry, "type", "") == "inbox_processing_start":
            start_index = index
    if start_index is None:
        return ""

    trigger = ""
    for entry in context_entries[start_index + 1 :]:
        if getattr(entry, "ts", "") > getattr(tool_use, "ts", ""):
            break
        entry_type = getattr(entry, "type", "")
        if entry_type == "inbox_processing_end":
            return ""
        if entry_type != "message_received":
            continue
        meta = getattr(entry, "meta", {})
        candidate = str(meta.get("trigger", "")) if isinstance(meta, dict) else ""
        if candidate.startswith("inbox:slack:"):
            trigger = candidate
    return trigger


def _has_duplicate_external_reply(
    tool_use_ts: str,
    display: str,
    context_entries: list[Any],
) -> bool:
    normalised = _normalise(display)
    if not normalised:
        return False
    for entry in context_entries:
        if getattr(entry, "type", "") != "external_reply_sent":
            continue
        if _normalise(getattr(entry, "content", "")) != normalised:
            continue
        elapsed = _seconds_between(tool_use_ts, getattr(entry, "ts", ""))
        if elapsed is not None and 0 <= elapsed <= _DERIVED_DUPLICATE_WINDOW_SEC:
            return True
    return False


def derive_sent_reply_entry(
    tool_use: Any,
    *,
    context_entries: list[Any],
    anima_name: str,
    aliases: dict[str, str] | None = None,
) -> Any | None:
    """Build an ``external_reply_sent`` entry from a historical Bash send."""
    if not is_slack_send_tool_use(tool_use):
        return None
    parsed = parse_slack_send_command(_tool_command(tool_use))
    if parsed is None:
        return None
    channel, body, thread_ts = parsed
    alias_map = aliased_slack_users() if aliases is None else aliases
    trigger = _trigger_in_inbox_window(tool_use, context_entries)
    recipient = _alias_for_slack_user(
        text=body,
        channel=channel,
        thread_ts=thread_ts,
        trigger=trigger,
        anima_name=anima_name,
        aliases=alias_map,
    )
    if recipient is None:
        return None

    tool_use_id = ""
    meta = getattr(tool_use, "meta", {})
    if isinstance(meta, dict):
        tool_use_id = str(meta.get("tool_use_id", ""))
    for entry in context_entries:
        if getattr(entry, "type", "") != "tool_result":
            continue
        entry_meta = getattr(entry, "meta", {})
        if not isinstance(entry_meta, dict):
            continue
        if tool_use_id and str(entry_meta.get("tool_use_id", "")) == tool_use_id:
            if entry_meta.get("is_error"):
                return None
            break

    display = _display_text(body, alias_map)
    if not display:
        return None
    if _has_duplicate_external_reply(getattr(tool_use, "ts", ""), display, context_entries):
        return None

    from core.activity.models import ActivityEntry

    return ActivityEntry(
        ts=getattr(tool_use, "ts", ""),
        type="external_reply_sent",
        content=display,
        to_person=recipient,
        via="slack",
        channel="slack",
        ctx=getattr(tool_use, "ctx", ""),
        meta={
            "thread_id": "default",
            "external_channel_id": channel,
            "external_thread_ts": thread_ts,
            "external_ts": "",
            "derived": True,
        },
    )


def mirror_inbound_message(
    entry: Any,
    *,
    context_entries: list[Any],
    aliases: dict[str, str] | None = None,
) -> Any | None:
    """Turn an inbox ``message_received`` from an alias user into ``human_reply``.

    Returns ``None`` when *entry* is not a candidate, or when a ``human_reply``
    for the same message was already recorded within the preceding 30 seconds
    (the notification-thread path), so the message is not duplicated.
    """
    if getattr(entry, "type", "") != "message_received":
        return None
    meta = getattr(entry, "meta", {})
    if not isinstance(meta, dict) or str(meta.get("from_type", "")) != "slack":
        return None
    trigger = str(meta.get("trigger", ""))
    if not trigger.startswith("inbox:slack:"):
        return None
    alias_map = aliased_slack_users() if aliases is None else aliases
    uid = trigger[len("inbox:slack:") :].split(",", 1)[0].strip()
    alias = alias_map.get(uid)
    if alias is None:
        return None

    for other in context_entries:
        if getattr(other, "type", "") != "human_reply" or getattr(other, "via", "") != "slack":
            continue
        elapsed = _seconds_between(getattr(other, "ts", ""), getattr(entry, "ts", ""))
        if elapsed is not None and 0 <= elapsed <= _INBOUND_PAIR_WINDOW_SEC:
            return None

    content = strip_thread_context(getattr(entry, "content", ""))
    if not content.strip():
        return None

    from core.activity.models import ActivityEntry

    mirrored_meta = dict(meta)
    mirrored_meta["derived"] = True
    mirrored_meta["mirror"] = "slack_inbound"
    return ActivityEntry(
        ts=getattr(entry, "ts", ""),
        type="human_reply",
        content=content,
        from_person=alias,
        channel="slack",
        via="slack",
        ctx=getattr(entry, "ctx", ""),
        meta=mirrored_meta,
    )


def apply_slack_mirror(
    entries: list[Any],
    *,
    context_entries: list[Any] | None = None,
    anima_name: str,
    aliases: dict[str, str] | None = None,
) -> list[Any]:
    """Return *entries* with historical Slack sends/receives mirrored.

    The returned list keeps the input order.  Candidate ``tool_use`` entries
    that cannot be turned into a reply are dropped when they came from inbox
    processing (where they were previously hidden from the default thread).
    """
    alias_map = aliased_slack_users() if aliases is None else aliases
    if not alias_map:
        return entries
    context = context_entries if context_entries is not None else entries
    result: list[Any] = []
    for entry in entries:
        if getattr(entry, "type", "") == "message_received":
            meta = getattr(entry, "meta", {})
            trigger = str(meta.get("trigger", "")) if isinstance(meta, dict) else ""
            is_candidate = (
                isinstance(meta, dict)
                and meta.get("from_type") == "slack"
                and trigger.startswith("inbox:slack:")
                and trigger[len("inbox:slack:") :].split(",", 1)[0].strip() in alias_map
            )
            if not is_candidate:
                result.append(entry)
                continue
            mirrored = mirror_inbound_message(entry, context_entries=context, aliases=alias_map)
            if mirrored is not None:
                result.append(mirrored)
            continue
        if getattr(entry, "type", "") == "tool_use" and is_slack_send_tool_use(entry):
            derived = derive_sent_reply_entry(
                entry,
                context_entries=context,
                anima_name=anima_name,
                aliases=alias_map,
            )
            if derived is not None:
                result.append(derived)
                continue
            if getattr(entry, "ctx", "") == "inbox":
                continue
            parsed = parse_slack_send_command(_tool_command(entry))
            if parsed is not None:
                display = _display_text(parsed[1], alias_map)
                if _has_duplicate_external_reply(getattr(entry, "ts", ""), display, context):
                    continue
        result.append(entry)
    return result


async def record_inbound_slack_reply(
    *,
    anima_name: str,
    text: str,
    slack_user_id: str,
    channel_id: str,
    thread_ts: str = "",
    source_message_id: str = "",
) -> bool:
    """Record an alias user's Slack message as ``human_reply`` (best effort)."""
    aliases = aliased_slack_users()
    if slack_user_id not in aliases:
        return False
    content = strip_thread_context(text)
    if not content.strip():
        return False
    try:
        from core.activity.logger import ActivityLogger
        from core.paths import get_animas_dir

        await ActivityLogger(get_animas_dir() / anima_name).alog(
            "human_reply",
            content=content,
            from_person=slack_user_id,
            via="slack",
            channel="slack",
            ctx="chat",
            meta={
                "thread_ts": thread_ts or source_message_id,
                "external_channel_id": channel_id,
                "mirror": "slack_inbound",
            },
            safe=True,
        )
    except Exception:
        logger.warning("Failed to log inbound Slack reply for anima=%s", anima_name, exc_info=True)
        return False
    return True


# Keep the formatting helper import alive for callers that want the
# canonical Slack markup conversion alongside mirror formatting.
__all__ = [
    "aliased_slack_users",
    "apply_slack_mirror",
    "derive_sent_reply_entry",
    "display_text_for_slack",
    "is_slack_send_command",
    "is_slack_send_tool_use",
    "is_user_addressed_slack_tool_use",
    "mirror_inbound_message",
    "parse_slack_send_command",
    "record_inbound_slack_reply",
    "slack_reply_recipient",
    "strip_thread_context",
]
