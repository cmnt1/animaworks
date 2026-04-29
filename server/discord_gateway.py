from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Discord Gateway integration for real-time message reception.

Uses a single Gateway Bot + per-channel webhooks.  All Animas share one
bot connection; routing is based on Anima name detection in message text
and channel-member configuration.
"""

import asyncio
import collections
import logging
import re
import threading
import time
from typing import Any

from core.config.models import load_config
from core.i18n import t
from core.messenger import Messenger
from core.paths import get_data_dir, get_shared_dir
from core.tools._base import get_credential
from core.tools._discord_markdown import clean_discord_markup

logger = logging.getLogger("animaworks.discord_gateway")

_BROADCAST_ONLY_BOARDS = {"ops"}


def _board_name_for_channel(channel_id: str, channel_name: str, discord_cfg: Any) -> str:
    """Return the AnimaWorks board name associated with a Discord channel."""
    try:
        mapped = discord_cfg.board_mapping.get(channel_id)
        if mapped:
            return str(mapped).lower()
    except Exception:
        pass
    return (channel_name or "").lower()


def _is_broadcast_only_channel(channel_id: str, channel_name: str, discord_cfg: Any) -> bool:
    """Whether ambiguous messages should be mirrored but not inbox-routed."""
    return _board_name_for_channel(channel_id, channel_name, discord_cfg) in _BROADCAST_ONLY_BOARDS


# ── Dedup ────────────────────────────────────────────────────


def _config_value(config: Any, key: str, default: Any = "") -> Any:
    if isinstance(config, dict):
        return config.get(key, default)
    return getattr(config, key, default)


def _system_agent_for_author(discord_cfg: Any, author_id: str) -> Any | None:
    """Return configured System Agent metadata for a Discord author ID."""
    agents = getattr(discord_cfg, "system_agents", {}) or {}
    if not isinstance(agents, dict):
        return None
    return agents.get(str(author_id)) or agents.get(author_id)


def _system_agent_board_from(system_agent: Any, fallback: str) -> str:
    """Return the board display name for a System Agent post."""
    for key in ("board_from", "name"):
        value = _config_value(system_agent, key, "")
        if str(value or "").strip():
            return str(value).strip()
    return fallback or "system_agent"


_DEDUP_TTL_SEC = 10
_dedup_lock = threading.Lock()
_recent_ids: collections.OrderedDict[str, float] = collections.OrderedDict()


def _is_duplicate_id(message_id: str) -> bool:
    """Return True if *message_id* was already processed."""
    now = time.monotonic()
    with _dedup_lock:
        while _recent_ids and next(iter(_recent_ids.values())) < now - _DEDUP_TTL_SEC:
            _recent_ids.popitem(last=False)
        if message_id in _recent_ids:
            return True
        _recent_ids[message_id] = now
        return False


# ── User name cache ──────────────────────────────────────────

_USER_NAME_CACHE_MAX = 500
_name_cache_lock = threading.Lock()
_user_name_cache: dict[str, str] = {}


def _cache_user_name(uid: str, name: str) -> None:
    with _name_cache_lock:
        if len(_user_name_cache) >= _USER_NAME_CACHE_MAX and uid not in _user_name_cache:
            try:
                _user_name_cache.pop(next(iter(_user_name_cache)))
            except StopIteration:
                pass
        _user_name_cache[uid] = name


def _get_cached_user_name(uid: str) -> str | None:
    with _name_cache_lock:
        return _user_name_cache.get(uid)


# ── Board routing dedup ──────────────────────────────────────

_board_dedup_lock = threading.Lock()
_board_dedup_ids: collections.OrderedDict[str, float] = collections.OrderedDict()
_BOARD_DEDUP_TTL_SEC = 10


def _route_to_board(
    channel_id: str,
    text: str,
    user_name: str,
    *,
    message_id: str = "",
    board_mapping: dict[str, str] | None = None,
    source: str = "discord",
) -> None:
    """Post a Discord message to the mapped AnimaWorks board (if any)."""
    if message_id:
        now = time.monotonic()
        with _board_dedup_lock:
            while _board_dedup_ids and next(iter(_board_dedup_ids.values())) < now - _BOARD_DEDUP_TTL_SEC:
                _board_dedup_ids.popitem(last=False)
            if message_id in _board_dedup_ids:
                return
            _board_dedup_ids[message_id] = now

    try:
        if board_mapping is None:
            board_mapping = load_config().external_messaging.discord.board_mapping
        board_name = board_mapping.get(channel_id)
        if not board_name:
            return
        messenger = Messenger(get_shared_dir(), user_name or source)
        messenger.post_channel(board_name, text, source=source, from_name=user_name or source)
    except Exception:
        logger.debug("Board routing failed for channel %s", channel_id, exc_info=True)


# ── Annotation builder ───────────────────────────────────────


def _interaction_custom_id(interaction_data: Any) -> str:
    """Return ``custom_id`` from discord.py interaction data (object or mapping)."""
    if interaction_data is None:
        return ""
    cid = getattr(interaction_data, "custom_id", None)
    if isinstance(cid, str) and cid:
        return cid
    if isinstance(interaction_data, dict):
        return str(interaction_data.get("custom_id") or "")
    return ""


def _modal_extract_comment_text(interaction_data: Any) -> str:
    """Extract ``comment_text`` value from a modal_submit payload."""
    rows: Any = getattr(interaction_data, "components", None)
    if rows is None and isinstance(interaction_data, dict):
        rows = interaction_data.get("components", [])
    if not rows:
        return ""
    for row in rows:
        comps: Any = getattr(row, "components", None)
        if comps is None and isinstance(row, dict):
            comps = row.get("components", [])
        if not comps:
            continue
        for comp in comps:
            cc = getattr(comp, "custom_id", None)
            if cc is None and isinstance(comp, dict):
                cc = comp.get("custom_id")
            if str(cc or "") != "comment_text":
                continue
            val = getattr(comp, "value", None)
            if val is None and isinstance(comp, dict):
                val = comp.get("value")
            return str(val or "")
    return ""


def _build_discord_comment_modal(dpy: Any, callback_id: str) -> Any:
    """Build a discord.py :class:`ui.Modal` for interactive comment input."""
    title = t("interactive.comment_modal_title")
    label = t("interactive.comment_modal_label")

    class _InteractiveCommentModal(dpy.ui.Modal):
        def __init__(self) -> None:
            super().__init__(
                title=title,
                custom_id=f"aw_interact_comment:{callback_id}",
            )
            self._comment = dpy.ui.TextInput(
                label=label,
                style=dpy.TextStyle.paragraph,
                custom_id="comment_text",
                required=True,
                max_length=2000,
            )
            self.add_item(self._comment)

    return _InteractiveCommentModal()


async def _handle_discord_interaction(interaction: Any, dpy: Any) -> None:
    """Handle button and modal interactions for :mod:`core.notification.interactive`."""
    # ── Modal submit (comment) ─────────────────────────────────────
    if interaction.type is dpy.InteractionType.modal_submit:
        modal_cid = _interaction_custom_id(interaction.data)
        if not modal_cid.startswith("aw_interact_comment:"):
            return
        callback_id = modal_cid.removeprefix("aw_interact_comment:")
        comment_text = _modal_extract_comment_text(interaction.data)
        user_id = str(interaction.user.id)
        user_name = interaction.user.display_name or interaction.user.name

        from core.notification.interactive import get_interaction_router

        router = get_interaction_router()
        try:
            req = await router.lookup(callback_id)
        except Exception:
            logger.exception("InteractionRouter.lookup failed for modal callback_id=%s", callback_id)
            try:
                await interaction.response.send_message(t("interactive.expired"), ephemeral=True)
            except Exception:
                logger.debug("ephemeral send after lookup error failed", exc_info=True)
            return

        if req is None:
            try:
                await interaction.response.send_message(t("interactive.expired"), ephemeral=True)
            except Exception:
                logger.debug("ephemeral send for expired modal failed", exc_info=True)
            return

        allowed = req.allowed_users.get("discord", [])
        if allowed and user_id not in allowed:
            try:
                await interaction.response.send_message(t("interactive.unauthorized"), ephemeral=True)
            except Exception:
                logger.debug("ephemeral send for unauthorized modal failed", exc_info=True)
            return

        try:
            result = await router.resolve(
                callback_id,
                decision="comment",
                actor=user_name,
                source="discord",
                comment=comment_text,
            )
        except Exception:
            logger.exception("InteractionRouter.resolve failed for modal callback_id=%s", callback_id)
            try:
                await interaction.response.send_message(t("interactive.already_resolved"), ephemeral=True)
            except Exception:
                logger.debug("ephemeral send after resolve error failed", exc_info=True)
            return

        if result is None:
            try:
                await interaction.response.send_message(t("interactive.already_resolved"), ephemeral=True)
            except Exception:
                logger.debug("ephemeral send for already_resolved modal failed", exc_info=True)
            return

        try:
            await interaction.response.send_message(t("interactive.comment_submitted"), ephemeral=True)
        except Exception:
            logger.debug("ephemeral send comment_submitted failed", exc_info=True)
        return

    # ── Message components (buttons) ───────────────────────────────
    if interaction.type is not dpy.InteractionType.component:
        return

    custom_id = _interaction_custom_id(interaction.data)
    if not custom_id.startswith("aw_interact:"):
        return

    parts = custom_id.split(":", 2)
    if len(parts) != 3:
        return
    _, callback_id, option = parts

    user_id = str(interaction.user.id)
    user_name = interaction.user.display_name or interaction.user.name

    from core.notification.interactive import get_interaction_router

    router = get_interaction_router()

    try:
        req = await router.lookup(callback_id)
    except Exception:
        logger.exception("InteractionRouter.lookup failed for callback_id=%s", callback_id)
        try:
            await interaction.response.send_message(t("interactive.expired"), ephemeral=True)
        except Exception:
            logger.debug("ephemeral send after lookup error failed", exc_info=True)
        return

    if req is None:
        try:
            await interaction.response.send_message(t("interactive.expired"), ephemeral=True)
        except Exception:
            logger.debug("ephemeral send for expired interaction failed", exc_info=True)
        return

    allowed = req.allowed_users.get("discord", [])
    if allowed and user_id not in allowed:
        try:
            await interaction.response.send_message(t("interactive.unauthorized"), ephemeral=True)
        except Exception:
            logger.debug("ephemeral send for unauthorized failed", exc_info=True)
        return

    if option == "comment":
        try:
            await interaction.response.send_modal(_build_discord_comment_modal(dpy, callback_id))
        except Exception:
            logger.exception("send_modal for comment failed callback_id=%s", callback_id)
        return

    try:
        result = await router.resolve(
            callback_id,
            decision=option,
            actor=user_name,
            source="discord",
        )
    except Exception:
        logger.exception("InteractionRouter.resolve failed for callback_id=%s", callback_id)
        try:
            await interaction.response.send_message(t("interactive.already_resolved"), ephemeral=True)
        except Exception:
            logger.debug("ephemeral send after resolve error failed", exc_info=True)
        return

    if result is None:
        try:
            await interaction.response.send_message(t("interactive.already_resolved"), ephemeral=True)
        except Exception:
            logger.debug("ephemeral send for already_resolved failed", exc_info=True)
        return

    resolved_text = t("interactive.resolved_by", actor=user_name, decision=option)
    try:
        if interaction.message is None:
            await interaction.response.send_message(resolved_text, ephemeral=True)
        else:
            await interaction.response.edit_message(content=resolved_text, view=None)
    except Exception:
        logger.exception("edit_message after interactive resolve failed callback_id=%s", callback_id)


def _build_discord_annotation(
    is_dm: bool,
    has_mention: bool,
    ch_name: str = "",
    *,
    routed_as_lead: bool = False,
) -> str:
    if is_dm:
        return "[discord:DM]\n"
    ch_label = f"#{ch_name}" if ch_name else "channel"
    if has_mention:
        return f"[discord:{ch_label} — {t('discord.annotation_mentioned')}]\n"
    if routed_as_lead:
        return f"[discord:{ch_label} — {t('discord.annotation_channel_lead')}]\n"
    return f"[discord:{ch_label} — {t('discord.annotation_no_mention')}]\n"


# ── Thread context ───────────────────────────────────────────

_THREAD_CTX_SUMMARY_LIMIT = 150


async def _fetch_thread_context(
    channel: Any,
    reference: Any,
) -> str:
    """Fetch Discord thread context for a reply message."""
    if reference.message_id is None:
        return ""
    try:
        parent = await channel.fetch_message(reference.message_id)
        parent_user = parent.author.display_name or str(parent.author)
        parent_text = (parent.content or "").replace("\n", " ")[:_THREAD_CTX_SUMMARY_LIMIT]
        parent_text = clean_discord_markup(parent_text)
        lines = [
            "[Thread context — this message is a reply in a Discord thread]",
            f"  @{parent_user}: {parent_text}",
            "[/Thread context]",
            "",
        ]
        return "\n".join(lines)
    except Exception:
        logger.warning("Failed to fetch Discord thread context", exc_info=True)
        return ""


# ── Gateway Manager ──────────────────────────────────────────


class DiscordGatewayManager:
    """Manages a single Discord Gateway connection for all Animas.

    Inbound messages are routed to Animas based on:
    1. Thread reply mapping (previous conversation context)
    2. Anima name detection in message text
    3. Channel-member configuration
    4. Default anima fallback
    """

    def __init__(self) -> None:
        self._client: Any = None  # discord.Client (lazy import)
        self._bot_user_id: int = 0
        self._anima_name_re: re.Pattern[str] | None = None
        self._known_anima_names: set[str] = set()
        self._alias_to_canonical: dict[str, str] = {}  # lowercase alias/name → canonical
        self._webhook_names: set[str] = set()
        self._started = False

    @property
    def client(self) -> Any:
        return self._client

    async def start(self) -> None:
        """Start the Discord Gateway connection if enabled."""
        config = load_config()
        discord_config = config.external_messaging.discord
        if not discord_config.enabled:
            logger.info("Discord Gateway is disabled")
            return

        try:
            token = get_credential("discord", "discord", env_var="DISCORD_BOT_TOKEN")
        except Exception:
            logger.error("DISCORD_BOT_TOKEN not configured — Discord Gateway cannot start")
            return

        try:
            import discord as _discord
        except ImportError:
            logger.error("discord.py is not installed — run: pip install 'animaworks[discord]'")
            return

        self._build_anima_patterns()

        intents = _discord.Intents(
            guilds=True,
            guild_messages=True,
            dm_messages=True,
            message_content=True,
            members=False,
        )

        client = _discord.Client(intents=intents)
        self._client = client

        @client.event
        async def on_ready() -> None:
            if client.user:
                self._bot_user_id = client.user.id
                logger.info(
                    "Discord Gateway connected: %s (id=%s)",
                    client.user.name,
                    client.user.id,
                )

        @client.event
        async def on_message(message: Any) -> None:
            await self._handle_message(message)

        @client.event
        async def on_interaction(interaction: Any) -> None:
            try:
                await _handle_discord_interaction(interaction, _discord)
            except Exception:
                logger.exception("Error handling Discord interaction")
                try:
                    if interaction.response.is_done():
                        return
                    await interaction.response.send_message(t("interactive.error"), ephemeral=True)
                except Exception:
                    pass

        # Start in background task (client.start is blocking)
        asyncio.create_task(self._run_client(client, token))

        # Wait for ready with timeout
        for _ in range(60):
            if self._bot_user_id:
                break
            await asyncio.sleep(0.5)

        if not self._bot_user_id:
            logger.error("Discord Gateway did not become ready within 30s")
            return

        self._started = True
        logger.info("Discord Gateway started")

    async def _run_client(self, client: Any, token: str) -> None:
        """Run client.start in a way that doesn't block the event loop."""
        try:
            await client.start(token)
        except Exception as exc:
            if type(exc).__name__ == "LoginFailure":
                logger.error("Discord login failed — check DISCORD_BOT_TOKEN")
            else:
                logger.exception("Discord Gateway connection error")

    async def stop(self) -> None:
        """Gracefully close the Discord Gateway connection."""
        if self._client and not self._client.is_closed():
            await self._client.close()
            logger.info("Discord Gateway stopped")
        self._started = False

    def reload(self) -> None:
        """Rebuild Anima name patterns from current config."""
        self._build_anima_patterns()
        logger.info("Discord Gateway patterns reloaded")

    async def health_check(self) -> dict[str, Any]:
        """Return gateway health status."""
        if not self._client or self._client.is_closed():
            return {"status": "disconnected"}
        latency = self._client.latency
        return {
            "status": "connected",
            "latency_ms": round(latency * 1000, 1) if latency != float("inf") else None,
            "bot_user_id": str(self._bot_user_id),
            "guilds": len(self._client.guilds),
        }

    # ── Internal ─────────────────────────────────────────────

    def _build_anima_patterns(self) -> None:
        """Build regex pattern and alias→canonical mapping from config."""
        try:
            cfg = load_config()
            anima_names: set[str] = set()
            alias_map: dict[str, str] = {}
            for name in cfg.animas:
                anima_names.add(name)
                alias_map[name.lower()] = name
                anima_cfg = cfg.animas[name]
                for alias in anima_cfg.aliases:
                    anima_names.add(alias)
                    alias_map[alias.lower()] = name
            self._known_anima_names = anima_names
            self._alias_to_canonical = alias_map
            if anima_names:
                escaped = [re.escape(n) for n in sorted(anima_names, key=len, reverse=True)]
                self._anima_name_re = re.compile(
                    r"(?:^|\b|(?<=[^a-zA-Z0-9]))(" + "|".join(escaped) + r")(?:\b|(?=[^a-zA-Z0-9])|$)",
                    re.IGNORECASE,
                )
            else:
                self._anima_name_re = None
        except Exception:
            logger.debug("Failed to build Anima name patterns", exc_info=True)

    def _resolve_canonical_name(self, matched: str) -> str | None:
        """Resolve a matched name (possibly alias) to canonical Anima name.

        Uses the cached ``_alias_to_canonical`` mapping built by
        ``_build_anima_patterns()`` — no config reload needed.
        """
        return self._alias_to_canonical.get(matched.lower())

    def _detect_target_anima(
        self,
        text: str,
        channel_id: str,
        discord_cfg: Any,
    ) -> str | None:
        """Detect the first Anima a message is targeting.

        Returns canonical anima name or None. For messages naming multiple
        Animas, use :meth:`_detect_all_target_animas` instead.
        """
        targets = self._detect_all_target_animas(text)
        if targets:
            return targets[0]

        # Channel-member config (if only one member, route to them)
        members = discord_cfg.channel_members.get(channel_id, [])
        if len(members) == 1:
            return members[0]

        return None

    def _detect_all_target_animas(self, text: str) -> list[str]:
        """Return every canonical Anima name mentioned in *text*, in order.

        Duplicates are removed while preserving first-occurrence order so
        that messages like ``"sora mira ..."`` route to both Animas.
        """
        if not (self._anima_name_re and text):
            return []
        seen: set[str] = set()
        out: list[str] = []
        for m in self._anima_name_re.finditer(text):
            canonical = self._resolve_canonical_name(m.group(1))
            if canonical and canonical not in seen:
                seen.add(canonical)
                out.append(canonical)
        return out

    @staticmethod
    def _is_anima_in_channel(anima_name: str, channel_id: str, discord_cfg: Any) -> bool:
        """Check if an Anima may participate in a channel.

        Uses the unified ``is_channel_member`` ACL (meta.json is SSoT). This
        guarantees the gateway drops messages that the posting side
        (``DiscordAutoResponder``) would later refuse anyway, so we don't
        spend LLM tokens generating replies that can't be delivered.

        Falls back to the config-based empty-is-open rule for channels that
        aren't yet mapped (first-sync edge case) to avoid blocking during
        initial bootstrap.
        """
        try:
            from core.messenger import is_channel_member
            from core.paths import get_shared_dir

            board_name = discord_cfg.board_mapping.get(channel_id)
            if board_name:
                return is_channel_member(get_shared_dir(), board_name, anima_name)
        except Exception:
            pass
        # Fallback: unmapped channel — permissive if no members configured.
        members = discord_cfg.channel_members.get(channel_id, [])
        if not members:
            return True
        return anima_name in members

    async def _handle_message(self, message: Any) -> None:
        """Core message handler for all Discord events."""
        # Ignore own messages
        if message.author.id == self._bot_user_id:
            return

        # Ignore webhook messages from AnimaWorks (echo prevention)
        if message.webhook_id is not None:
            author_name = message.author.display_name or message.author.name
            if author_name.lower() in {n.lower() for n in self._known_anima_names}:
                return

        # Dedup
        msg_id = str(message.id)
        if _is_duplicate_id(msg_id):
            return

        # Cache author name
        author_display = message.author.display_name or message.author.name
        _cache_user_name(str(message.author.id), author_display)

        # Build user name cache from mentions
        mention_cache: dict[str, str] = {}
        for user in message.mentions:
            mention_cache[str(user.id)] = user.display_name or user.name
            _cache_user_name(str(user.id), user.display_name or user.name)

        # Clean content
        with _name_cache_lock:
            name_snapshot = dict(_user_name_cache)
        cleaned_text = clean_discord_markup(message.content or "", cache=name_snapshot)

        channel_id = str(message.channel.id)
        # For threads, use parent channel ID for membership/lead routing
        parent_id = getattr(message.channel, "parent_id", None)
        routing_channel_id = str(parent_id) if parent_id else channel_id
        ch_name = getattr(message.channel, "name", "") or ""
        is_dm = message.guild is None or ch_name.startswith("dm-")

        # Bot mentioned?
        bot_mentioned = any(u.id == self._bot_user_id for u in message.mentions)

        # Thread context
        thread_ctx = ""
        reference_id: str | None = None
        if message.reference and message.reference.message_id:
            reference_id = str(message.reference.message_id)
            thread_ctx = await _fetch_thread_context(message.channel, message.reference)

        # Load config once per message for routing decisions
        try:
            cfg = load_config()
            discord_cfg = cfg.external_messaging.discord
        except Exception:
            logger.debug("Failed to load config for Discord routing", exc_info=True)
            return
        suppress_implicit_routing = (not is_dm) and _is_broadcast_only_channel(
            routing_channel_id,
            ch_name,
            discord_cfg,
        )
        board_from = author_display
        board_source = "discord"
        system_agent = _system_agent_for_author(discord_cfg, str(message.author.id))
        if system_agent:
            board_from = _system_agent_board_from(system_agent, author_display)
            board_source = "system_agent"
            if not bool(_config_value(system_agent, "route_to_animas", False)):
                _route_to_board(
                    routing_channel_id,
                    cleaned_text,
                    board_from,
                    message_id=msg_id,
                    board_mapping=discord_cfg.board_mapping,
                    source=board_source,
                )
                logger.info(
                    "Discord routing: system agent %s mirrored to board only",
                    board_from,
                )
                return

        # Determine target Anima(s). A single message can name multiple
        # Animas (e.g. "sora mira に..."); deliver to each in turn.
        target_animas: list[str] = []
        routed_as_lead = False

        # 1. Thread reply mapping — route replies to the Anima that sent the parent
        if reference_id:
            try:
                from core.discord_webhooks import get_webhook_manager

                thread_anima = get_webhook_manager().lookup_thread_anima(reference_id)
                if thread_anima:
                    target_animas = [thread_anima]
            except Exception:
                logger.debug("Thread map lookup failed", exc_info=True)

        # 2. DM single-member precedence — a DM channel bound to exactly one
        # Anima is always for that Anima, regardless of text. Anima aliases
        # can collide with common Japanese words (e.g. `空`=sora vs. `空`=empty)
        # so body-name detection must not override the channel owner here.
        if not target_animas and is_dm:
            members = discord_cfg.channel_members.get(routing_channel_id, [])
            if len(members) == 1:
                target_animas = [members[0]]

        # 3. Collect every Anima named in the text (preserves order, dedup).
        if not target_animas:
            target_animas = self._detect_all_target_animas(cleaned_text)

        # 4. Single-member channel fallback (non-DM). Broadcast-only boards
        # such as #ops are mirrored for visibility but should not create work
        # unless a specific Anima is named or a thread reply is already mapped.
        if not target_animas and not suppress_implicit_routing:
            members = discord_cfg.channel_members.get(routing_channel_id, [])
            if len(members) == 1:
                target_animas = [members[0]]

        # 5. No name detected: bot-mention / channel-lead fallback
        if not target_animas and not is_dm and not suppress_implicit_routing:
            if bot_mentioned and discord_cfg.default_anima:
                target_animas = [discord_cfg.default_anima]
            else:
                members = discord_cfg.channel_members.get(routing_channel_id, [])
                if members:
                    target_animas = [members[0]]
                    routed_as_lead = True
                elif discord_cfg.default_anima and self._is_anima_in_channel(
                    discord_cfg.default_anima, routing_channel_id, discord_cfg
                ):
                    target_animas = [discord_cfg.default_anima]
                    routed_as_lead = True
        elif not target_animas and suppress_implicit_routing:
            logger.info(
                "Discord routing: #%s is broadcast-only; suppressing implicit inbox delivery",
                ch_name,
            )

        # Enforce channel membership per target
        if not is_dm:
            filtered: list[str] = []
            for name in target_animas:
                if self._is_anima_in_channel(name, routing_channel_id, discord_cfg):
                    filtered.append(name)
                else:
                    logger.info(
                        "Discord routing: '%s' not a member of channel %s (#%s) — dropping",
                        name,
                        channel_id,
                        ch_name,
                    )
            target_animas = filtered

        logger.info(
            "Discord routing: channel=#%s (%s) routing=%s is_dm=%s bot_mentioned=%s -> targets=%s",
            ch_name,
            channel_id,
            routing_channel_id,
            is_dm,
            bot_mentioned,
            target_animas,
        )

        # Board routing (always, regardless of target)
        # Use routing_channel_id so thread messages map to the parent channel's board.
        # DMs are mirrored to the mapped `dm-{name}` board too — otherwise the
        # human side of a DM conversation has no record on the AnimaWorks board
        # and only the Anima's replies (via webhook echo) would show up.
        _route_to_board(
            routing_channel_id,
            cleaned_text,
            board_from,
            message_id=msg_id,
            board_mapping=discord_cfg.board_mapping,
            source=board_source,
        )

        # Deliver to each target's inbox
        if target_animas:
            has_mention = bot_mentioned or (
                self._anima_name_re is not None and self._anima_name_re.search(cleaned_text) is not None
            )
            annotation = _build_discord_annotation(
                is_dm,
                has_mention,
                ch_name,
                routed_as_lead=routed_as_lead,
            )
            intent = "question"
            full_content = annotation + thread_ctx + cleaned_text
            is_thread = parent_id is not None
            data_dir = get_data_dir()

            for target_anima in target_animas:
                try:
                    anima_dir = data_dir / "animas" / target_anima
                    if not anima_dir.is_dir():
                        logger.warning("Anima directory not found: %s", target_anima)
                        continue

                    messenger = Messenger(get_shared_dir(), target_anima)
                    # For threads: external_channel_id = parent channel (webhook target),
                    # external_thread_ts = thread channel ID (for webhook thread_id param).
                    # For normal channels: external_channel_id = channel, thread_ts = "".
                    messenger.receive_external(
                        content=full_content,
                        source="discord",
                        source_message_id=msg_id,
                        external_user_id=str(message.author.id),
                        external_channel_id=routing_channel_id,
                        external_thread_ts=channel_id if is_thread else "",
                        intent=intent,
                    )

                    logger.info(
                        "Discord message routed: %s -> %s (channel=%s, intent=%s)",
                        author_display,
                        target_anima,
                        channel_id,
                        intent or "none",
                    )
                except Exception:
                    logger.exception(
                        "Failed to deliver Discord message to %s",
                        target_anima,
                    )
