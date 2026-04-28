from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""CommsToolsMixin — messaging, channel, DM history, and human notification handlers."""

import json as _json
import logging
import re
from typing import TYPE_CHECKING, Any

from core.i18n import t
from core.time_utils import now_iso
from core.tooling.handler_base import (
    OnMessageSentFn,
    _error_result,
    active_session_type,
    build_outgoing_origin_chain,
    suppress_board_fanout,
)

if TYPE_CHECKING:
    from core.memory.activity import ActivityLogger
    from core.messenger import Messenger
    from core.notification.notifier import HumanNotifier

logger = logging.getLogger("animaworks.tool_handler")

_OPS_ESCALATION_RE = re.compile(
    r"(escalat|エスカレ|緊急|urgent|critical|重大|障害|incident|停止|異常|blocked|"
    r"ブロック|call_human|owner|オーナー|人間|human)",
    re.IGNORECASE,
)


class CommsToolsMixin:
    """Message sending, channel posting/reading, DM history, and human notification."""

    # Declared for type-checker visibility
    _messenger: Messenger | None
    _anima_name: str
    _activity: ActivityLogger
    _on_message_sent: OnMessageSentFn | None
    _replied_to: dict[str, set[str]]
    _posted_channels: dict[str, set[str]]
    _human_notifier: HumanNotifier | None
    _pending_notifications: list[dict[str, Any]]
    _interactive_human_notifications: dict[str, list[str]]
    _session_origin: str
    _session_origin_chain: list[str]

    def _is_subordinate_anima(self) -> bool:
        try:
            from core.config.models import load_config

            anima_cfg = load_config().animas.get(self._anima_name)
            return bool(anima_cfg and anima_cfg.supervisor)
        except Exception:
            logger.debug("Failed to resolve supervisor for %s", self._anima_name, exc_info=True)
            return False

    def _interactive_human_notifications_for(self, session_type: str) -> list[str]:
        store = getattr(self, "_interactive_human_notifications", None)
        if store is None:
            store = {"chat": [], "background": []}
            self._interactive_human_notifications = store
        return store.setdefault(session_type, [])

    def _has_ops_human_escalation(self) -> bool:
        return bool(self._interactive_human_notifications_for(active_session_type.get()))

    def _record_ops_human_escalation(self, callback_id: str) -> None:
        if callback_id:
            self._interactive_human_notifications_for(active_session_type.get()).append(callback_id)

    def _consume_ops_human_escalation(self) -> str:
        callbacks = self._interactive_human_notifications_for(active_session_type.get())
        if not callbacks:
            return ""
        return callbacks.pop(0)

    @staticmethod
    def _has_successful_notification_result(results: list[str]) -> bool:
        for result in results:
            lowered = result.lower()
            if "error" not in lowered and "no notification channels configured" not in lowered:
                return True
        return False

    @staticmethod
    def _human_notification_config_error(config: Any) -> tuple[str, str, str] | None:
        if not getattr(config, "enabled", False):
            return (
                "NotificationDisabled",
                "Human notification is disabled",
                "Set human_notification.enabled to true in config.json",
            )

        enabled_channels = [ch for ch in getattr(config, "channels", []) if getattr(ch, "enabled", False)]
        if not enabled_channels:
            return (
                "NoNotificationChannels",
                "No enabled notification channels configured",
                "Add an enabled channel to human_notification.channels in config.json",
            )

        discord_channels = [ch for ch in enabled_channels if getattr(ch, "type", "") == "discord"]
        if discord_channels and len(discord_channels) == len(enabled_channels):
            has_discord_target = False
            for ch in discord_channels:
                cfg = getattr(ch, "config", {}) or {}
                if any(cfg.get(k) for k in ("user_id", "channel_id", "webhook_url", "webhook_url_env")):
                    has_discord_target = True
                    break
            if not has_discord_target:
                return (
                    "DiscordTargetMissing",
                    "Discord notification channel has no user_id, channel_id, or webhook_url configured",
                    "Set human_notification.channels[].config.user_id, channel_id, or webhook_url",
                )

        return None

    def _reload_human_notifier_from_config(self) -> tuple[HumanNotifier | None, tuple[str, str, str] | None]:
        try:
            from core.config.models import load_config
            from core.notification.notifier import HumanNotifier

            config = load_config().human_notification
            config_error = self._human_notification_config_error(config)
            if config_error is not None:
                self._human_notifier = None
                return None, config_error

            notifier = HumanNotifier.from_config(config)
            if notifier.channel_count == 0:
                config_error = (
                    "NoNotificationChannels",
                    "No supported notification channels configured",
                    "Check human_notification.channels[].type in config.json",
                )
                self._human_notifier = None
                return None, config_error

            self._human_notifier = notifier
            return notifier, None
        except Exception as exc:
            logger.debug("Failed to reload HumanNotifier", exc_info=True)
            return None, (
                "NotificationConfigError",
                f"Failed to load human notification config: {exc}",
                "Check config.json syntax and human_notification settings",
            )

    def _handle_send_message(self, args: dict[str, Any]) -> str:
        if not self._messenger:
            return "Error: messenger not configured"

        from core.tooling.org_helpers import resolve_anima_name

        to = resolve_anima_name(args["to"]) if args.get("to") else args.get("to", "")
        content = args["content"]
        intent = args.get("intent", "")

        # ── Block send_message to Discord sender during inbox auto-reply ──
        # AutoResponder handles posting to the originating channel/thread.
        # send_message would route to #dm-{anima}, not the thread.
        if self._trigger.startswith("inbox"):
            _to_lower = to.lower() if to else ""
            if _to_lower.startswith("discord:") or _to_lower.startswith("slack:"):
                return (
                    "send_message to external users is unnecessary during inbox processing. "
                    "Your text response is automatically posted to the originating Discord "
                    "channel/thread. Just write your response as plain text."
                )

        # ── Per-run DM limits ──
        if intent == "delegation":
            return t("handler.delegation_intent_deprecated")
        if intent not in ("report", "question"):
            return t("handler.dm_intent_error")

        current_replied = self.replied_to_for(active_session_type.get())
        if to in current_replied:
            return t("handler.dm_already_sent", to=to)

        from core.config.models import resolve_outbound_limits
        from core.paths import get_animas_dir as _get_animas_dir

        _anima_dir = _get_animas_dir() / self._anima_name if _get_animas_dir().exists() else None
        limits = resolve_outbound_limits(self._anima_name, _anima_dir)
        max_recipients = limits["max_recipients_per_run"]
        if len(current_replied) >= max_recipients and to not in current_replied:
            return t("handler.dm_max_recipients", limit=max_recipients)

        # ── Resolve recipient ──
        try:
            from core.config.models import load_config
            from core.outbound import resolve_recipient, send_external
            from core.paths import get_animas_dir

            config = load_config()
            animas_dir = get_animas_dir()
            known_animas = {d.name for d in animas_dir.iterdir() if d.is_dir()} if animas_dir.exists() else set()

            resolved = resolve_recipient(
                to,
                known_animas,
                config.external_messaging,
            )
        except (ValueError, Exception) as e:
            from core.exceptions import RecipientNotFoundError

            if isinstance(e, (ValueError, RecipientNotFoundError)):
                session = active_session_type.get()
                if session == "chat":
                    return t("handler.send_msg_chat_hint", to=to)
                return t("handler.send_msg_non_chat_hint", to=to)
            logger.warning(
                "Recipient resolution failed for '%s': %s",
                to,
                e,
                exc_info=True,
            )
            return _error_result(
                "RecipientResolutionError",
                f"Failed to resolve recipient '{to}': {e}",
                suggestion="Check config.json external_messaging settings",
            )

        # ── Build outgoing origin_chain (provenance Phase 3) ──
        outgoing_chain = build_outgoing_origin_chain(
            self._session_origin,
            self._session_origin_chain,
        )

        # ── External routing ──
        if resolved is not None and not resolved.is_internal:
            # Block external send during inbox — AutoResponder handles it
            if self._trigger.startswith("inbox") and resolved.channel in ("discord", "slack"):
                return (
                    "send_message to external users is unnecessary during inbox processing. "
                    "Your text response is automatically posted to the originating Discord "
                    "channel/thread. Just write your response as plain text."
                )
            logger.info(
                "send_message routed externally: to=%s channel=%s",
                to,
                resolved.channel,
            )
            self._replied_to.setdefault(active_session_type.get(), set()).add(to)
            self._persist_replied_to(to, success=True)

            try:
                meta: dict[str, Any] = {"from_type": "external", "channel": resolved.channel}
                if intent:
                    meta["intent"] = intent
                self._activity.log(
                    "message_sent",
                    content=content,
                    to_person=to,
                    summary=f"→ {to}: {content[:80]}",
                    meta=meta,
                )
            except Exception:
                logger.warning("Activity logging failed for external send to %s", to)

            if self._on_message_sent:
                try:
                    self._on_message_sent(
                        self._messenger.anima_name,
                        to,
                        content,
                    )
                except Exception:
                    logger.exception("on_message_sent callback failed")

            from core.outbound import send_external

            result = send_external(
                resolved,
                content,
                sender_name=self._anima_name,
                anima_name=self._anima_name,
            )
            return result

        # ── Internal messaging ──
        internal_to = resolved.name if resolved else to
        msg = self._messenger.send(
            to=internal_to,
            content=content,
            thread_id=args.get("thread_id", ""),
            reply_to=args.get("reply_to", ""),
            intent=intent,
            origin_chain=outgoing_chain,
        )

        if msg.type == "error":
            return f"Error: {msg.content}"

        logger.info("send_message to=%s thread=%s", internal_to, msg.thread_id)
        self._replied_to.setdefault(active_session_type.get(), set()).add(internal_to)
        self._persist_replied_to(internal_to, success=True)

        if self._on_message_sent:
            try:
                self._on_message_sent(
                    self._messenger.anima_name,
                    internal_to,
                    content,
                )
            except Exception:
                logger.exception("on_message_sent callback failed")

        return f"Message sent to {internal_to} (id: {msg.id}, thread: {msg.thread_id})"

    # ── Channel tool handlers ────────────────────────────────

    def _handle_post_channel(self, args: dict[str, Any]) -> str:
        if not self._messenger:
            return "Error: messenger not configured"
        channel = args.get("channel", "")
        text = args.get("text", "")
        if not channel or not text:
            return _error_result("InvalidArguments", "channel and text are required")

        fallback_from_ops = False
        if channel == "ops" and not self._has_ops_human_escalation():
            channel = "general"
            fallback_from_ops = True
            logger.info(
                "Redirecting non-escalation #ops post to #general: anima=%s",
                self._anima_name,
            )

        # ── ACL gate ──
        from core.messenger import is_channel_member

        if not is_channel_member(self._messenger.shared_dir, channel, self._anima_name):
            return t("handler.channel_acl_denied", channel=channel)

        current_posted = self.posted_channels_for(active_session_type.get())
        if channel in current_posted:
            alt_channels = {"general", "ops"} - {channel} - current_posted
            alt_hint = ""
            if alt_channels:
                alt_hint = t(
                    "handler.post_alt_hint",
                    channels=", ".join(f"#{c}" for c in sorted(alt_channels)),
                )
            return t(
                "handler.post_already_posted",
                channel=channel,
                alt_hint=alt_hint,
            )

        # ── Unified outbound budget check (DM + Board share the same pool) ──
        from core.cascade_limiter import get_depth_limiter
        from core.paths import get_animas_dir as _get_animas_dir

        _limiter = get_depth_limiter()
        _anima_dir_for_budget = getattr(self, "_anima_dir", None) or (_get_animas_dir() / self._anima_name)
        outbound_check = _limiter.check_global_outbound(self._anima_name, _anima_dir_for_budget)
        if outbound_check is not True:
            return str(outbound_check)

        # ── Cross-run guard: file-based cooldown check ──
        try:
            from core.config.models import load_config

            cooldown = load_config().heartbeat.channel_post_cooldown_s
        except Exception:
            cooldown = 300
        if cooldown > 0:
            last = self._messenger.last_post_by(self._anima_name, channel)
            if last:
                from datetime import datetime

                from core.time_utils import ensure_aware, now_local

                try:
                    ts = ensure_aware(datetime.fromisoformat(last["ts"]))
                    elapsed = (now_local() - ts).total_seconds()
                    if elapsed < cooldown:
                        return t(
                            "handler.post_cooldown",
                            channel=channel,
                            ts=last["ts"][11:16],
                            elapsed=int(elapsed),
                            cooldown=cooldown,
                        )
                except (ValueError, TypeError):
                    pass

        ops_callback_id = self._consume_ops_human_escalation() if channel == "ops" else ""

        self._messenger.post_channel(channel, text)
        self._posted_channels.setdefault(active_session_type.get(), set()).add(channel)
        logger.info(
            "post_channel channel=%s anima=%s ops_callback_id=%s fallback_from_ops=%s",
            channel,
            self._anima_name,
            ops_callback_id,
            fallback_from_ops,
        )

        if not suppress_board_fanout.get():
            self._fanout_board_mentions(channel, text)
        else:
            logger.info(
                "Suppressed board fanout for board_mention reply: channel=%s anima=%s",
                channel,
                self._anima_name,
            )

        # Sync board post to mapped Slack channel (fire-and-forget)
        self._fire_board_slack_sync(channel, text)

        # Sync board post to mapped Discord channel (fire-and-forget)
        self._fire_board_discord_sync(channel, text)

        result = f"Posted to #{channel}"
        if ops_callback_id:
            result += f" (linked call_human callback: {ops_callback_id})"
        if fallback_from_ops:
            result += " (redirected from #ops: interactive Human escalation required)"

        # Guardrail: warn when posting to board during thread-sourced inbox processing
        if getattr(self, "_trigger", "").startswith("inbox") and getattr(self, "_has_thread_source", False):
            result += f"\n{t('discord.thread_post_channel_warning')}"

        return result

    def _fanout_board_mentions(self, channel: str, text: str) -> None:
        """Send DM notifications to mentioned Animas when posting to a board channel."""
        if not self._messenger:
            return

        mentions = re.findall(r"@(\w+)", text)
        if not mentions:
            return

        is_all = "all" in mentions

        if is_all and channel == "ops":
            logger.info(
                "Suppressed @all board fanout for #%s to preserve department routing",
                channel,
            )
            return

        from core.paths import get_data_dir

        sockets_dir = get_data_dir() / "run" / "sockets"
        if sockets_dir.exists():
            running = {p.stem for p in sockets_dir.glob("*.sock")}
        else:
            running = set()

        if is_all:
            targets = running - {self._anima_name}
        else:
            named = {m for m in mentions if m != "all"}
            targets = (named & running) - {self._anima_name}

        # ── ACL filter: only notify channel members ──
        from core.messenger import is_channel_member

        targets = {t for t in targets if is_channel_member(self._messenger.shared_dir, channel, t)}

        if not targets:
            return

        from_name = self._anima_name
        fanout_content = f"[board_reply:channel={channel},from={from_name}]\n" + t(
            "handler.board_mention_content", from_name=from_name, channel=channel, text=text
        )

        outgoing_chain = build_outgoing_origin_chain(
            self._session_origin,
            self._session_origin_chain,
        )

        for target in sorted(targets):
            try:
                self._messenger.send(
                    to=target,
                    content=fanout_content,
                    msg_type="board_mention",
                    origin_chain=outgoing_chain,
                )
                logger.info(
                    "board_mention fanout: %s -> %s (channel=%s)",
                    from_name,
                    target,
                    channel,
                )
            except Exception:
                logger.warning(
                    "Failed to fanout board_mention to %s",
                    target,
                    exc_info=True,
                )

    def _fire_board_slack_sync(self, channel: str, text: str) -> None:
        """Sync a board post to the mapped Slack channel.

        The MCP tool handler dispatches ``handle()`` via
        ``asyncio.to_thread()``, so this method runs in a thread-pool
        worker with no running event loop.  We therefore create a
        short-lived loop via ``asyncio.run()`` to execute the async
        HTTP call.  The ~1 s blocking is acceptable because we are
        already off the main event loop.
        """
        # Board→Slack sync disabled – Discord migration
        # try:
        #     import asyncio
        #     from core.outbound_auto import BoardSlackSync
        #     sync = BoardSlackSync()
        #     coro = sync.sync_board_post(
        #         board_name=channel, text=text,
        #         from_person=self._anima_name, source="anima",
        #     )
        #     try:
        #         loop = asyncio.get_running_loop()
        #     except RuntimeError:
        #         loop = None
        #     if loop is not None and loop.is_running():
        #         loop.create_task(coro)
        #     else:
        #         asyncio.run(coro)
        # except Exception:
        #     logger.warning("Board→Slack sync failed for #%s", channel, exc_info=True)

    def _fire_board_discord_sync(self, channel: str, text: str) -> None:
        """Sync a board post to the mapped Discord channel.

        Uses ``BoardDiscordSync`` which calls the synchronous
        ``DiscordWebhookManager.send_as_anima()``, so no async
        boilerplate is needed.
        """
        try:
            from core.outbound_auto import BoardDiscordSync

            sync = BoardDiscordSync()
            sync.sync_board_post(
                board_name=channel,
                text=text,
                from_person=self._anima_name,
                source="anima",
            )
        except Exception:
            logger.warning("Board→Discord sync failed for #%s", channel, exc_info=True)

    def _handle_read_channel(self, args: dict[str, Any]) -> str:
        if not self._messenger:
            return "Error: messenger not configured"
        channel = args.get("channel", "")
        if not channel:
            return _error_result("InvalidArguments", "channel is required")
        _ch_lower = channel.strip().lower()
        if _ch_lower == "inbox" or _ch_lower.startswith("inbox/") or _ch_lower.startswith("inbox\\"):
            return _error_result(
                "InvalidArguments",
                f"'{channel}' is not a channel. Inbox messages are processed automatically; "
                "do not use read_channel for inbox.",
            )

        # ── ACL gate ──
        from core.exceptions import RecipientNotFoundError
        from core.messenger import _validate_name, is_channel_member

        try:
            _validate_name(channel, "channel name")
        except RecipientNotFoundError:
            return _error_result("InvalidArguments", f"Invalid channel name: {channel!r}")
        if not is_channel_member(self._messenger.shared_dir, channel, self._anima_name):
            return t("handler.channel_acl_denied", channel=channel)

        limit = args.get("limit", 20)
        human_only = args.get("human_only", False)
        messages = self._messenger.read_channel(channel, limit=limit, human_only=human_only)
        if not messages:
            return f"No messages in #{channel}"
        return _json.dumps(messages, ensure_ascii=False, indent=2)

    def _handle_read_dm_history(self, args: dict[str, Any]) -> str:
        if not self._messenger:
            return "Error: messenger not configured"
        peer = args.get("peer", "")
        if not peer:
            return _error_result("InvalidArguments", "peer is required")
        limit = args.get("limit", 20)
        messages = self._messenger.read_dm_history(peer, limit=limit)
        if not messages:
            return f"No DM history with {peer}"
        return _json.dumps(messages, ensure_ascii=False, indent=2)

    # ── Channel management handler ────────────────────────────

    def _handle_manage_channel(self, args: dict[str, Any]) -> str:
        if not self._messenger:
            return "Error: messenger not configured"

        action = args.get("action", "")
        channel = args.get("channel", "")
        if not action or not channel:
            return _error_result("InvalidArguments", "action and channel are required")

        from core.exceptions import RecipientNotFoundError
        from core.messenger import (
            ChannelMeta,
            _validate_name,
            is_channel_member,
            load_channel_meta,
            save_channel_meta,
        )

        try:
            _validate_name(channel, "channel name")
        except RecipientNotFoundError:
            return _error_result("InvalidArguments", f"Invalid channel name: {channel!r}")

        shared_dir = self._messenger.shared_dir

        if action == "create":
            channel_file = shared_dir / "channels" / f"{channel}.jsonl"
            if channel_file.exists():
                return t("handler.channel_already_exists", channel=channel)
            members = args.get("members", [])
            if self._anima_name not in members:
                members = [self._anima_name] + members
            meta = ChannelMeta(
                members=members,
                created_by=self._anima_name,
                created_at=now_iso(),
                description=args.get("description", ""),
            )
            channels_dir = shared_dir / "channels"
            channels_dir.mkdir(parents=True, exist_ok=True)
            channel_file.write_text("", encoding="utf-8")
            save_channel_meta(shared_dir, channel, meta)
            members_str = ", ".join(members) if members else "open"
            logger.info("manage_channel create: #%s by %s", channel, self._anima_name)
            return t("handler.channel_created", channel=channel, members=members_str)

        elif action == "add_member":
            meta = load_channel_meta(shared_dir, channel)
            channel_file = shared_dir / "channels" / f"{channel}.jsonl"
            if not channel_file.exists():
                return t("handler.channel_not_found", channel=channel)
            new_members = args.get("members", [])
            if not new_members:
                return _error_result("InvalidArguments", "members list is required for add_member")
            # Reject add_member on open/legacy channels to prevent accidental restriction
            if meta is None:
                return t("handler.channel_add_member_open_denied", channel=channel)
            # Caller must be a member of the channel
            if not is_channel_member(shared_dir, channel, self._anima_name):
                return t("handler.channel_acl_not_member", channel=channel)
            for m in new_members:
                if m not in meta.members:
                    meta.members.append(m)
            save_channel_meta(shared_dir, channel, meta)
            logger.info("manage_channel add_member: #%s += %s", channel, new_members)
            return t("handler.channel_members_added", channel=channel, members=", ".join(new_members))

        elif action == "remove_member":
            meta = load_channel_meta(shared_dir, channel)
            channel_file = shared_dir / "channels" / f"{channel}.jsonl"
            if not channel_file.exists():
                return t("handler.channel_not_found", channel=channel)
            if meta is None:
                return t("handler.channel_open", channel=channel)
            # Caller must be a member of the channel
            if not is_channel_member(shared_dir, channel, self._anima_name):
                return t("handler.channel_acl_not_member", channel=channel)
            remove_members = args.get("members", [])
            if not remove_members:
                return _error_result("InvalidArguments", "members list is required for remove_member")
            meta.members = [m for m in meta.members if m not in remove_members]
            save_channel_meta(shared_dir, channel, meta)
            logger.info("manage_channel remove_member: #%s -= %s", channel, remove_members)
            return t("handler.channel_members_removed", channel=channel, members=", ".join(remove_members))

        elif action == "info":
            channel_file = shared_dir / "channels" / f"{channel}.jsonl"
            if not channel_file.exists():
                return t("handler.channel_not_found", channel=channel)
            meta = load_channel_meta(shared_dir, channel)
            if meta is None or not meta.members:
                return t("handler.channel_open", channel=channel)
            info = {
                "channel": channel,
                "members": meta.members,
                "created_by": meta.created_by,
                "created_at": meta.created_at,
                "description": meta.description,
            }
            return _json.dumps(info, ensure_ascii=False, indent=2)

        else:
            return _error_result(
                "InvalidArguments",
                f"Unknown action: {action!r}. Use create, add_member, remove_member, or info.",
            )

    # ── Human notification handler ────────────────────────────

    def _handle_call_human(self, args: dict[str, Any]) -> str:
        notifier, config_error = self._reload_human_notifier_from_config()
        if config_error is not None:
            error_type, message, suggestion = config_error
            return _error_result(
                error_type,
                message,
                suggestion=suggestion,
            )
        if not notifier:
            return _error_result("NotConfigured", "Human notification is not configured")

        import asyncio

        subject = args.get("subject", "")
        body = args.get("body", "")
        priority = args.get("priority", "normal")
        interactive = bool(args.get("interactive", False))
        category = str(args.get("category") or "approval")
        raw_opts = args.get("options", "approve,reject,comment")

        raw_allowed = args.get("allowed_users")
        allowed_list: list[str]
        if raw_allowed is None:
            allowed_list = []
        elif isinstance(raw_allowed, list):
            allowed_list = [str(x).strip() for x in raw_allowed if str(x).strip()]
        else:
            s = str(raw_allowed).strip()
            allowed_list = [s] if s else []

        if not subject or not body:
            return _error_result(
                "InvalidArguments",
                "subject and body are required",
            )

        interaction_req = None
        if interactive:
            from core.config.models import load_config
            from core.notification.interactive import InteractionRequest, get_interaction_router

            cfg = load_config()
            defaults = list(cfg.interaction.default_approver_ids)
            merged = list(dict.fromkeys(allowed_list + defaults))
            if isinstance(raw_opts, list):
                opts_list = [str(x).strip() for x in raw_opts if str(x).strip()]
            else:
                opts_list = [p.strip() for p in str(raw_opts).split(",") if p.strip()]
            if not opts_list:
                opts_list = ["approve", "reject", "comment"]
            aud: dict[str, list[str]] = {"slack": merged} if merged else {}

            async def _create_interaction() -> InteractionRequest:
                return await get_interaction_router().create(
                    self._anima_name,
                    category,
                    opts_list,
                    allowed_users=aud or None,
                )

            try:
                try:
                    _loop = asyncio.get_running_loop()
                except RuntimeError:
                    _loop = None
                if _loop is not None:
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        interaction_req = pool.submit(asyncio.run, _create_interaction()).result(timeout=60)
                else:
                    interaction_req = asyncio.run(_create_interaction())
            except ValueError as ve:
                return _error_result("InvalidArguments", str(ve))

        try:
            coro = notifier.notify(
                subject,
                body,
                priority,
                anima_name=self._anima_name,
                interaction=interaction_req,
            )
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None

            if loop is not None:
                import concurrent.futures

                with concurrent.futures.ThreadPoolExecutor() as pool:
                    results = pool.submit(asyncio.run, coro).result(timeout=60)
            else:
                results = asyncio.run(coro)
        except Exception as e:
            return _error_result("NotificationError", f"Failed to send notification: {e}")

        notif_data = {
            "anima": self._anima_name,
            "subject": subject,
            "body": body,
            "priority": priority,
            "timestamp": now_iso(),
        }
        self._pending_notifications.append(notif_data)

        payload: dict[str, Any] = {"status": "sent", "results": results}
        if interactive and interaction_req is not None:
            payload["interactive"] = True
            payload["callback_id"] = interaction_req.callback_id
            if self._has_successful_notification_result(results):
                self._record_ops_human_escalation(interaction_req.callback_id)

        return _json.dumps(payload, ensure_ascii=False)
