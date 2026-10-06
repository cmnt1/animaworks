# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Transport-agnostic front-lane conversation and delegation handling."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import re
from collections.abc import AsyncIterator, Callable
from pathlib import Path
from typing import Any

from core.i18n import t
from core.voice.emotion_style import EmotionStyle, VoiceChannel, voice_mode_suffix
from core.voice.front import READ_MEMORY_TOOL, VoiceFrontLane, extract_emotion, localized_ask_anima_tool

logger = logging.getLogger(__name__)

IPC_STREAM_TIMEOUT = 300.0  # chat/streamと同水準。ツール往復する応答が60sを超えるため
MAX_ASK_ANIMA_CONCURRENT = 1
ASK_ANIMA_MAX_RESULT_CHARS = 1000
ASK_ANIMA_DELEGATION_NOTE = "\n\n[voice front からの委譲]"

VOICE_MODE_SUFFIX = voice_mode_suffix()

_MEMORY_TEXT_JA = (
    "## 最近の出来事 ({filename})\n{body}",
    "## 知っていること ({filename})\n{body}",
    "（記憶はまだない）",
    "（「{query}」に関する記憶は見つからなかった）",
    "（記憶の読み取りに失敗した）",
)

_EPISODE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
_NOISE_LINE_RE = re.compile(r"^#+ Raw notes.*$\n?", re.MULTILINE)


def _read_memory_file(path: Path) -> str:
    """Read a memory file safely, limiting large files to their final 200 KiB."""
    if path.stat().st_size > 1024 * 1024:
        with path.open("rb") as file_handle:
            file_handle.seek(-200 * 1024, 2)
            text = file_handle.read().decode("utf-8", errors="replace")
    else:
        text = path.read_text(encoding="utf-8")

    if text.startswith("---"):
        frontmatter_end = re.search(r"\n---(?:\r?\n|$)", text[3:])
        if frontmatter_end is not None:
            text = text[3 + frontmatter_end.end() :]
    return text.strip()


def _memory_files(anima_dir: Path) -> list[Path]:
    """Return searchable memory files, excluding archived knowledge."""
    files: list[Path] = []
    for scope in ("knowledge", "episodes", "procedures"):
        scope_dir = anima_dir / scope
        if not scope_dir.is_dir():
            continue
        for path in scope_dir.rglob("*.md"):
            relative_parts = path.relative_to(scope_dir).parts
            if scope == "knowledge" and "archive" in relative_parts:
                continue
            files.append(path)
    return files


def read_memory_snippets(anima_dir: Path, query: str, *, max_chars: int = 1800, page: int = 0) -> str:
    """Read recent or keyword-matched memory snippets without using the RAG DB.

    ``page`` (empty query only) walks backwards through the latest episode and
    rotates the knowledge picks, so repeated "what happened lately" reads do not
    hand a monologue the same material every time.
    """
    try:
        clean_query = (query or "").strip()
        if not clean_query:
            sections: list[str] = []
            episodes_dir = anima_dir / "episodes"
            # Date-named files first (``recovered_*`` sorts after digits).
            episodes = sorted(
                episodes_dir.rglob("*.md") if episodes_dir.is_dir() else [],
                key=lambda path: (bool(_EPISODE_DATE_RE.match(path.name)), path.name),
                reverse=True,
            )
            if episodes:
                episode = episodes[0]
                episode_text = _read_memory_file(episode)
                episode_limit = int(max_chars * 0.6)
                windows = max(1, -(-len(episode_text) // episode_limit))
                end = len(episode_text) - (page % windows) * episode_limit
                sections.append(
                    _MEMORY_TEXT_JA[0].format(
                        filename=episode.name,
                        body=episode_text[max(0, end - episode_limit) : end],
                    )
                )

            knowledge_dir = anima_dir / "knowledge"
            knowledge_files = []
            if knowledge_dir.is_dir():
                knowledge_files = [
                    path
                    for path in knowledge_dir.rglob("*.md")
                    if "archive" not in path.relative_to(knowledge_dir).parts
                ]
                knowledge_files.sort(key=lambda path: path.stat().st_mtime, reverse=True)
            if knowledge_files:
                offset = (page * 3) % len(knowledge_files)
                knowledge_files = knowledge_files[offset:] + knowledge_files[:offset]
            for knowledge in knowledge_files[:3]:
                sections.append(
                    _MEMORY_TEXT_JA[1].format(
                        filename=knowledge.name,
                        body=_read_memory_file(knowledge)[:200],
                    )
                )
            result = "\n\n".join(sections) or _MEMORY_TEXT_JA[2]
            return result[:max_chars]

        # ponytail: keyword match only; switch to MemoryManager.search_memory_text if recall quality falls short
        terms = clean_query.casefold().split()
        matches: list[tuple[int, Path, str, int]] = []
        for path in _memory_files(anima_dir):
            text = _NOISE_LINE_RE.sub("", _read_memory_file(path))
            folded = text.casefold()
            positions = [folded.find(term) for term in terms if folded.find(term) >= 0]
            if not positions:
                continue
            match_count = sum(folded.count(term) for term in terms)
            matches.append((match_count, path, text, min(positions)))

        if not matches:
            return _MEMORY_TEXT_JA[3].format(query=clean_query)[:max_chars]
        # Newest files first, match count second — old daily logs are huge
        # and would otherwise always win on raw hit count.
        matches.sort(key=lambda match: (-match[1].stat().st_mtime, -match[0]))
        sections = []
        for _count, path, text, position in matches[:4]:
            start = max(0, position - 300)
            end = min(len(text), position + 300)
            sections.append(f"## {path.relative_to(anima_dir)}\n{text[start:end]}")
        return "\n\n".join(sections)[:max_chars]
    except Exception:
        logger.debug("Failed to read voice memory snippets from %s", anima_dir, exc_info=True)
        return _MEMORY_TEXT_JA[4][:max_chars]


class FrontConversation:
    """Own front-lane streaming, tools, delegation, and conversation recording.

    The class deliberately has no transport, subtitle, or TTS dependencies.
    Callers consume text deltas and decide how to present and synthesize them.
    """

    def __init__(
        self,
        *,
        anima_name: str,
        supervisor: Any,
        front_model: str | None,
        front_api_base: str | None,
        animas_dir: Path | None = None,
        thread_id: str | None = None,
        prompt_style: str = "web",
        channel: VoiceChannel = "web",
        emotion_style: EmotionStyle = "emoji",
        delegation_note: str | None = None,
        ipc_timeout: float = IPC_STREAM_TIMEOUT,
        max_concurrent_delegations: int = MAX_ASK_ANIMA_CONCURRENT,
        on_delegation: Callable[[], None] | None = None,
        on_ask_anima: Callable[[], None] | None = None,
    ) -> None:
        self.anima_name = anima_name
        self.supervisor = supervisor
        self.front_model = front_model or None
        self.front_api_base = front_api_base or None
        self.animas_dir = animas_dir
        self.thread_id = thread_id or "default"
        self.prompt_style = prompt_style
        self.channel = channel
        self.emotion_style = emotion_style
        if delegation_note is None and channel == "phone":
            delegation_note = t("phone.delegation_note")
        self.delegation_note = ASK_ANIMA_DELEGATION_NOTE if delegation_note is None else delegation_note
        self.ipc_timeout = ipc_timeout
        self.max_concurrent_delegations = max_concurrent_delegations
        self._on_delegation = on_delegation
        self._on_ask_anima = on_ask_anima

        self._lane: Any | None = None
        self._delegation_jobs: dict[int, asyncio.Task[Any]] = {}
        self._delegation_job_counter = 0
        self._delegation_requests: dict[int, str] = {}
        self._delegation_results: asyncio.Queue[tuple[int, str]] | None = None
        self._delegation_done: asyncio.Queue[None] | None = None
        self._unreported_delegation_results: dict[int, str] = {}
        self._last_drained_delegation_ids: tuple[int, ...] = ()
        self._delegation_notification_started = False
        self._last_full_text = ""
        self._last_emotion = "neutral"
        self._last_completed = False
        self._pending_record: tuple[str, str, str, bool] | None = None

    @property
    def enabled(self) -> bool:
        """Whether a front model is configured."""
        return bool(self.front_model)

    @property
    def existing_lane(self) -> Any | None:
        """Return the cached lane without creating it."""
        return self._lane

    @property
    def delegation_jobs(self) -> dict[int, asyncio.Task[Any]]:
        """Compatibility view of active jobs without moving their ownership."""
        return self._delegation_jobs

    def replace_delegation_jobs(self, jobs: dict[int, asyncio.Task[Any]]) -> None:
        """Replace the active-job mapping for legacy test/session adapters."""
        self._delegation_jobs = jobs

    @property
    def last_full_text(self) -> str:
        """Full text emitted by the most recent front turn."""
        return self._last_full_text

    @property
    def last_emotion(self) -> str:
        """Emotion parsed from the most recent completed front turn."""
        return self._last_emotion

    @property
    def last_completed(self) -> bool:
        """Whether the most recent front turn completed with non-empty text."""
        return self._last_completed

    def set_lane(self, lane: Any | None) -> None:
        """Replace the cached lane (also useful for injecting test doubles)."""
        self._lane = lane

    def lane(self) -> VoiceFrontLane:
        """Lazily build and cache the configured voice front lane."""
        if self._lane is not None:
            return self._lane
        if not self.front_model:
            raise RuntimeError("voice front model is not configured")

        from core.paths import get_animas_dir
        from core.prompt.builder import build_voice_front_prompt

        anima_dir = (self.animas_dir or get_animas_dir()) / self.anima_name
        system_prompt = build_voice_front_prompt(
            anima_dir,
            anima_name=self.anima_name,
            channel=self.channel,
            emotion_style=self.emotion_style,
        )
        api_base, api_key, api_version = self.front_api_base or "", "local", None
        if not api_base and "/" in self.front_model:
            # No explicit endpoint: use the provider credential from config.json
            # (e.g. ``azure/<deployment>``).
            from core.config import load_config

            credential = load_config().credentials.get(self.front_model.split("/", 1)[0])
            if credential is not None:
                api_base = credential.base_url or ""
                api_key = credential.api_key or "local"
                api_version = credential.keys.get("api_version")
        self._lane = VoiceFrontLane(
            model=self.front_model,
            api_base=api_base,
            api_key=api_key,
            api_version=api_version,
            system_prompt=system_prompt,
        )
        return self._lane

    async def check_health(self) -> bool:
        """Check front endpoint health, returning False on any failure."""
        if not self.enabled:
            return False
        try:
            return bool(await self.lane().check_health())
        except Exception:
            logger.debug("voice front health check failed (%s)", self.anima_name, exc_info=True)
            return False

    async def stream_turn(
        self,
        text: str,
        *,
        from_person: str,
        record_user: bool = True,
        record: bool = True,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: str | None = None,
        keep_history: bool = True,
        max_tokens: int | None = None,
        temperature: float | None = None,
        drain_results: bool = True,
        should_stop: Callable[[], bool] | None = None,
        memory_page: int = 0,
        defer_record: bool = False,
    ) -> AsyncIterator[str]:
        """Stream one front-lane turn, yielding text deltas without transport work."""
        self._last_full_text = ""
        self._last_emotion = "neutral"
        self._last_completed = False
        self._pending_record = None
        self._last_drained_delegation_ids = ()
        turn_text = text
        if drain_results:
            results, result_ids = self._take_delegation_results()
            self._last_drained_delegation_ids = result_ids
            if results:
                turn_text = f"{results}\n\n{text}"

        lane = self.lane()
        lane.reset_turn()
        full: list[str] = []
        completed = False
        try:
            if tools is None:
                tools = [localized_ask_anima_tool(), READ_MEMORY_TOOL]
            async for delta in lane.stream(
                turn_text,
                tools=tools,
                tool_executor=self.ask_anima,
                tool_executors={
                    "ask_anima": lambda args: self.ask_anima(str(args.get("request", ""))),
                    "read_memory": lambda args: self.read_memory(args, page=memory_page),
                },
                tool_choice=tool_choice,
                keep_history=keep_history,
                max_tokens=max_tokens,
                temperature=temperature,
            ):
                if should_stop is not None and should_stop():
                    break
                full.append(delta)
                self._last_full_text = "".join(full)
                yield delta
            else:
                completed = True

            if should_stop is not None and should_stop():
                completed = False
            full_text = "".join(full)
            self._last_full_text = full_text
            if not completed or not full_text.strip():
                return

            self._last_emotion = extract_emotion(full_text)
            if record:
                if defer_record:
                    self._pending_record = (turn_text, full_text, from_person, record_user)
                else:
                    await self.record_conversation(
                        turn_text,
                        full_text,
                        from_person,
                        record_user=record_user,
                    )
            self._last_completed = True
        finally:
            if not self._last_completed:
                self._last_full_text = "".join(full)
                if self._delegation_results is not None:
                    for job in self._last_drained_delegation_ids:
                        message = self._unreported_delegation_results.get(job)
                        if message:
                            self._delegation_results.put_nowait((job, message))

    async def record_pending_turn(self) -> None:
        """Persist a completed turn deferred until the transport queued its output."""
        pending = self._pending_record
        self._pending_record = None
        if pending is not None:
            user_text, response_text, from_person, record_user = pending
            await self.record_conversation(user_text, response_text, from_person, record_user=record_user)

    def read_memory(self, args: dict[str, Any], *, page: int = 0) -> str:
        """Read this Anima's file-backed memory for the front lane."""
        from core.paths import get_animas_dir

        anima_dir = (self.animas_dir or get_animas_dir()) / self.anima_name
        return read_memory_snippets(anima_dir, str(args.get("query", "")), page=page)

    async def record_conversation(
        self,
        user_text: str,
        response_text: str,
        from_person: str,
        *,
        record_user: bool = True,
    ) -> None:
        """Persist a front turn to the Anima's default conversation."""
        from core.memory.conversation.memory import ConversationMemory

        try:
            processes = getattr(self.supervisor, "processes", None)
            handle = processes.get(self.anima_name) if isinstance(processes, dict) else None
            if handle is not None:
                alive_check = getattr(handle, "is_alive", None)
                alive = bool(alive_check()) if callable(alive_check) else False
                state = getattr(getattr(handle, "state", None), "value", None)
                if alive and state == "running":
                    turns = []
                    if record_user:
                        turns.append({"role": from_person or "human", "content": user_text})
                    turns.append({"role": "assistant", "content": response_text})
                    await self.supervisor.send_request(
                        self.anima_name,
                        "append_conversation_turns",
                        {"thread_id": self.thread_id, "turns": turns},
                    )
                    return
                if alive:
                    logger.info(
                        "Skipping offline voice conversation write while Anima is stopping (%s)", self.anima_name
                    )
                    return

            from core.paths import get_animas_dir

            anima_dir = (self.animas_dir or get_animas_dir()) / self.anima_name
            conversation = ConversationMemory(anima_dir, None)
            if record_user:
                conversation.append_turn(from_person or "human", user_text)
            conversation.append_turn("assistant", response_text)
            saved = conversation.asave()
            if inspect.isawaitable(saved):
                await saved
            else:
                await asyncio.to_thread(conversation.save)
        except Exception:
            logger.debug("Failed to persist front conversation (%s)", self.anima_name, exc_info=True)

    def _ensure_delegation_state(self) -> None:
        """Create queues lazily on first use inside the running event loop."""
        if self._delegation_results is None:
            self._delegation_results = asyncio.Queue()
        if self._delegation_done is None:
            self._delegation_done = asyncio.Queue()

    def ask_anima(self, request: str) -> str:
        """Schedule a full-agent request and immediately return its ACK."""
        if self._on_ask_anima is not None:
            try:
                self._on_ask_anima()
            except Exception:
                logger.debug("Failed to record ask_anima call (%s)", self.anima_name, exc_info=True)

        request = (request or "").strip()
        if not request:
            request = "（依頼内容が指定されていません）"
        if self._delegation_jobs:
            job = next(iter(self._delegation_jobs))
            running_request = self._delegation_requests.get(job, "")
            summary = running_request[:80]
            if len(running_request) > 80:
                summary += "…"
            return t("voice.ask_anima_in_progress", job=job, request=summary)
        self._ensure_delegation_state()
        self._delegation_job_counter += 1
        job = self._delegation_job_counter
        self._delegation_requests[job] = request
        task = asyncio.create_task(
            self._run_ask_anima_job(job, request),
            name=f"ask-anima-{self.anima_name}-{job}",
        )
        self._delegation_jobs[job] = task
        if self._on_delegation is not None:
            try:
                self._on_delegation()
            except Exception:
                logger.debug("Failed to notify delegation watcher (%s)", self.anima_name, exc_info=True)
        return f"受理しました (job {job})。完了したら知らせます"

    async def _run_ask_anima_job(self, job: int, request: str) -> None:
        """Run one delegated request and queue its summarized result."""
        result_text = ""
        try:
            async for response in self.supervisor.send_request_stream(
                anima_name=self.anima_name,
                method="process_message",
                params={
                    "message": request + self.delegation_note,
                    "from_person": "human",
                    "intent": "",
                    "stream": True,
                    # Delegated work uses the full-capability lane, not voice mode.
                    "voice_mode": False,
                    "images": [],
                    "attachment_paths": [],
                },
                timeout=self.ipc_timeout,
            ):
                if getattr(response, "done", False):
                    result_data = getattr(response, "result", None) or {}
                    cycle_result = result_data.get("cycle_result", {}) or {}
                    summary = str(cycle_result.get("summary", "") or "")
                    if summary:
                        result_text = summary
                elif getattr(response, "chunk", None):
                    try:
                        chunk_data = json.loads(response.chunk)
                    except (json.JSONDecodeError, TypeError):
                        chunk_data = {}
                    if chunk_data.get("type") == "cycle_done":
                        cycle_result = chunk_data.get("cycle_result", {}) or {}
                        summary = str(cycle_result.get("summary", "") or "")
                        if summary:
                            result_text = summary
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("ask_anima job %s failed (%s): %s", job, self.anima_name, exc)
            result_text = "処理に失敗しました。詳細はログを確認してほしい"
        finally:
            self._delegation_jobs.pop(job, None)
            self._delegation_requests.pop(job, None)
            message = f"[ask_anima完了 job {job}: {result_text[:ASK_ANIMA_MAX_RESULT_CHARS]}]"
            self._unreported_delegation_results[job] = message
            if self._delegation_results is not None:
                await self._delegation_results.put((job, message))
            if self._delegation_done is not None:
                await self._delegation_done.put(None)

    @property
    def last_drained_delegation_ids(self) -> tuple[int, ...]:
        """Job IDs included in the latest drained result text."""
        return self._last_drained_delegation_ids

    def _take_delegation_results(self) -> tuple[str, tuple[int, ...]]:
        """Collect completed result text together with the associated job IDs."""
        if self._delegation_results is None:
            return "", ()
        parts: list[str] = []
        job_ids: list[int] = []
        while True:
            try:
                job, message = self._delegation_results.get_nowait()
            except asyncio.QueueEmpty:
                break
            parts.append(message)
            job_ids.append(job)
        self._last_drained_delegation_ids = tuple(job_ids)
        return "\n".join(parts), self._last_drained_delegation_ids

    def drain_delegation_results(self) -> str:
        """Collect completed delegation results, returning an empty string if none."""
        return self._take_delegation_results()[0]

    def mark_delegation_results_reported(self, job_ids: tuple[int, ...] | list[int]) -> None:
        """Mark results as reported after the voice response has been delivered."""
        for job in job_ids:
            self._unreported_delegation_results.pop(job, None)

    def has_unreported_delegations(self) -> bool:
        """Whether any active or completed delegation remains unreported."""
        return bool(self._delegation_jobs or self._unreported_delegation_results)

    def has_pending_delegations(self) -> bool:
        """Whether any delegated full-agent jobs are still running."""
        return bool(self._delegation_jobs)

    def has_delegation_results(self) -> bool:
        """Whether completed delegation results are waiting to be surfaced."""
        return self._delegation_results is not None and not self._delegation_results.empty()

    async def wait_delegation_done(self) -> None:
        """Wait for one delegated job completion notification."""
        self._ensure_delegation_state()
        assert self._delegation_done is not None
        await self._delegation_done.get()

    def delegation_report_prompt(self, results: str) -> str:
        """Build the self-turn prompt used to report completed delegation results."""
        return f"{results} この結果を自分の言葉で短く報告して"

    async def notify_unreported_delegations(
        self,
        human_notification_config: Any,
        *,
        channel: VoiceChannel | None = None,
        wait_timeout: float = 30 * 60,
    ) -> None:
        """Wait at most 30 minutes, then notify humans about unreported work."""
        if self._delegation_notification_started or not self.has_unreported_delegations():
            return
        if not getattr(human_notification_config, "enabled", False):
            return

        self._delegation_notification_started = True
        tasks = tuple(self._delegation_jobs.values())
        if tasks and wait_timeout > 0:
            await asyncio.wait(
                tasks,
                timeout=min(float(wait_timeout), 30 * 60),
                return_when=asyncio.ALL_COMPLETED,
            )

        from core.i18n import t

        notification_channel = channel or self.channel
        string_prefix = "phone" if notification_channel == "phone" else "voice"
        messages = list(self._unreported_delegation_results.values())
        for job, request in self._delegation_requests.items():
            messages.append(t(f"{string_prefix}.delegation_still_running", job=job, request=request[:200]))
        if not messages:
            return

        from core.notification.notifier import HumanNotifier

        subject = t(f"{string_prefix}.delegation_report_subject", anima=self.anima_name)
        try:
            notifier = HumanNotifier.from_config(human_notification_config)
            await notifier.notify(
                subject,
                "\n".join(messages),
                anima_name=self.anima_name,
            )
        except Exception:
            logger.warning("Voice delegation result notification failed (%s)", self.anima_name)

    async def stream_full_agent(
        self,
        text: str,
        *,
        from_person: str,
        extra_params: dict[str, Any] | None = None,
        ipc_timeout: float | None = None,
    ) -> AsyncIterator[Any]:
        """Yield the full agent's process_message stream for a voice turn."""
        params: dict[str, Any] = {
            "message": text + voice_mode_suffix(channel=self.channel, emotion_style=self.emotion_style),
            "from_person": from_person,
            "intent": "",
            "stream": True,
            "voice_mode": True,
            "images": [],
            "attachment_paths": [],
        }
        if self.thread_id != "default":
            params["thread_id"] = self.thread_id
        if extra_params:
            params.update(extra_params)
        async for response in self.supervisor.send_request_stream(
            anima_name=self.anima_name,
            method="process_message",
            params=params,
            timeout=self.ipc_timeout if ipc_timeout is None else ipc_timeout,
        ):
            yield response

    async def aclose(self) -> None:
        """Release cached/session references without cancelling delegated jobs."""
        self._lane = None
        self._on_delegation = None
