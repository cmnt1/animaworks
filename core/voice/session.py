# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Voice session — STT -> Chat -> TTS orchestration."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from core.i18n import t
from core.voice.sentence_splitter import StreamingSentenceSplitter
from core.voice.stt import VoiceSTT
from core.voice.tts_base import BaseTTSProvider, TTSConfig, TTSSynthesisError

logger = logging.getLogger(__name__)

IPC_STREAM_TIMEOUT = 300.0  # chat/streamと同水準。ツール往復する応答が60sを超えるため
MAX_AUDIO_BUFFER_BYTES = 60 * 16_000 * 2  # 60 seconds of 16kHz 16-bit mono PCM
PCM16_SAMPLE_RATE = 16_000
PCM16_BYTES_PER_SAMPLE = 2
MIN_SPEECH_SEC = 0.35
MIN_SPEECH_BYTES = int(MIN_SPEECH_SEC * PCM16_SAMPLE_RATE * PCM16_BYTES_PER_SAMPLE)
SILENCE_RMS_THRESHOLD = 0.008
# Prefetch depth for sentence TTS. TTS backend is serial; larger values only
# buffer more text when synthesis is faster than realtime.
TTS_QUEUE_MAXSIZE = 8

# Concurrency cap for fire-and-forget ``ask_anima`` delegation. When this
# many jobs are still running, further requests get a "please wait" ACK.
MAX_ASK_ANIMA_CONCURRENT = 2
# Truncation length for the result text surfaced back to the front lane.
ASK_ANIMA_MAX_RESULT_CHARS = 1000
# Marker prepended to the delegated request so the full-agent loop knows the
# message came from the voice front lane.
ASK_ANIMA_DELEGATION_NOTE = "\n\n[voice front からの委譲]"

VOICE_MODE_SUFFIX = (
    "\n\n[voice-mode: 音声会話です。感情が伝わる話し言葉で200文字以内で簡潔に回答してください。"
    "絵文字を使ってよい（字幕表示用）。"
    "Markdown記法（見出し・太字・リスト・コードブロック等）は使わないでください。"
    "調査・実装・資料作成など時間のかかる依頼はその場で実行せず、自分宛てにタスクを作成して、"
    "『タスクに積んでやっておきますね』のように短く返答してください。"
    "毎応答の最後の行に必ず感情タグを1つ付けてください:"
    ' <!-- emotion: {"emotion": "<感情名>"} -->'
    "（感情名: neutral/smile/laugh/troubled/surprised/thinking/embarrassed。"
    "neutral以外を優先）]"
)

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
    "[\U0001f1e0-\U0001f1ff]"  # flags
    "|[\U0001f300-\U0001f5ff]"  # symbols & pictographs
    "|[\U0001f600-\U0001f64f]"  # emoticons
    "|[\U0001f680-\U0001f6ff]"  # transport & map
    "|[\U0001f700-\U0001f77f]"  # alchemical
    "|[\U0001f780-\U0001f7ff]"  # geometric shapes extended
    "|[\U0001f800-\U0001f8ff]"  # supplemental arrows-C
    "|[\U0001f900-\U0001f9ff]"  # supplemental symbols
    "|[\U0001fa00-\U0001fa6f]"  # chess symbols
    "|[\U0001fa70-\U0001faff]"  # symbols and pictographs extended-A
    "|[\U00002702-\U000027b0]"  # dingbats
    "|[\U00002600-\U000026ff]"  # misc symbols (☀ etc.)
    "|[\U0000231a-\U0000231b]"  # watch / hourglass
    "|[\U000023e9-\U000023f3]"  # media controls
    "|[\U000023f8-\U000023fa]"  # more media
    "|[\U000025aa-\U000025ab]"  # small squares
    "|[\U000025b6\U000025c0]"  # play/reverse
    "|[\U000025fb-\U000025fe]"  # medium squares
    "|[\U00002b05-\U00002b07]"  # arrows
    "|[\U00002b1b-\U00002b1c]"  # black/white large square
    "|[\U00002b50\U00002b55]"  # star / heavy circle
    "|[\U00002934-\U00002935]"  # arrows
    "|[\U00003030\U0000303d]"  # wavy dash / part alternation
    "|[\U00003297\U00003299]"  # circled ideographs used as emoji
    "|[\U000000a9\U000000ae\U00002122\U00002139\U00002194-\U00002199]"
    "|[\U000021a9-\U000021aa]"
    "|\U0000fe0f"  # variation selector-16
    "|\U0000200d"  # zero-width joiner
    "|\U000020e3"  # combining enclosing keycap
    ")+",
)


def sanitize_for_tts(text: str) -> str:
    """Strip Markdown, HTML comments, and emoji for TTS consumption."""
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
    text = _RE_EMOJI.sub("", text)
    return text.strip()


def _normalized_rms_from_pcm16(audio_data: bytes) -> float:
    """Calculate normalized RMS from 16-bit mono PCM bytes."""
    if len(audio_data) < PCM16_BYTES_PER_SAMPLE:
        return 0.0
    sample_count = len(audio_data) // PCM16_BYTES_PER_SAMPLE
    if sample_count == 0:
        return 0.0
    samples = memoryview(audio_data).cast("h")
    # Downsample for large chunks to keep CPU usage low.
    step = 4 if sample_count > 64_000 else 1
    sum_sq = 0.0
    count = 0
    for i in range(0, sample_count, step):
        value = samples[i] / 32768.0
        sum_sq += value * value
        count += 1
    if count == 0:
        return 0.0
    return (sum_sq / count) ** 0.5


# ── VoiceSession ────────────────────────────────────────────────


class VoiceSession:
    """Manages a single voice conversation session with an Anima."""

    def __init__(
        self,
        anima_name: str,
        ws: Any,
        stt: VoiceSTT,
        tts: BaseTTSProvider,
        tts_config: TTSConfig,
        supervisor: Any,
        voice_config: Any,
        front_model: str | None = None,
        front_api_base: str | None = None,
    ) -> None:
        """Initialize voice session.

        Args:
            anima_name: Target Anima name.
            ws: WebSocket (send_json, send_bytes).
            stt: STT engine.
            tts: TTS provider.
            tts_config: Per-session TTS config.
            supervisor: ProcessSupervisor for IPC.
            voice_config: Voice configuration (stt_refine_enabled, etc.).
            front_model: Optional voice front lane model name. Falls back to
                ``front_model`` on *voice_config* (None → legacy path).
            front_api_base: Optional OpenAI-compatible base URL for the front
                lane. Falls back to ``front_api_base`` on *voice_config*.
        """
        self._anima_name = anima_name
        self._ws = ws
        self._stt = stt
        self._tts = tts
        self._tts_config = tts_config
        self._supervisor = supervisor
        self._voice_config = voice_config
        self._audio_buffer: bytearray = bytearray()
        self._tts_playing = False
        self._interrupted = False
        self._processing = False
        self._tts_available: bool | None = None
        self._splitter = StreamingSentenceSplitter()
        self._consecutive_tts_failures: int = 0
        self._tts_queue: asyncio.Queue[str] | None = None
        self._tts_worker: asyncio.Task[None] | None = None

        # ask_anima delegation state (PR-3). Queues/task are created lazily
        # on first use (inside the running event loop).
        self._delegation_jobs: dict[int, asyncio.Task] = {}
        self._delegation_job_counter: int = 0
        self._delegation_results: asyncio.Queue[str] | None = None
        self._delegation_done: asyncio.Queue[None] | None = None
        self._delegation_watcher: asyncio.Task | None = None
        self._closed = False

        if front_model is None:
            front_model = getattr(voice_config, "front_model", None) or None
        if front_api_base is None:
            front_api_base = getattr(voice_config, "front_api_base", None) or None
        self._front_model = front_model or None
        self._front_api_base = front_api_base or None
        self._front_lane: Any | None = None

    async def handle_audio_chunk(self, data: bytes) -> None:
        """Receive audio chunk from browser, accumulate in buffer."""
        if len(self._audio_buffer) + len(data) > MAX_AUDIO_BUFFER_BYTES:
            self._audio_buffer.clear()
            logger.warning("Audio buffer overflow (%s), cleared", self._anima_name)
        self._audio_buffer.extend(data)

    async def handle_speech_end(self, from_person: str = "human") -> None:
        """Process accumulated audio: STT -> optional refine -> Chat -> TTS."""
        if self._processing:
            logger.debug("speech_end ignored — already processing (%s)", self._anima_name)
            return
        self._processing = True
        try:
            await self._do_speech_end(from_person)
        finally:
            self._processing = False

    async def _check_tts_health(self) -> bool:
        """Check TTS availability. Only caches positive results; retries on failure."""
        if self._tts_available:
            return True
        try:
            ok = await self._tts.health_check()
        except Exception:
            ok = False
        self._tts_available = ok
        if not ok:
            logger.warning(
                "TTS provider unavailable for %s (%s)",
                self._anima_name,
                self._tts_config.provider,
            )
            await self._ws.send_json({"type": "error", "message": "TTS unavailable"})
        return ok

    def invalidate_tts_health(self) -> None:
        """Reset cached TTS health so next speech_end rechecks."""
        self._tts_available = None

    async def _do_speech_end(self, from_person: str) -> None:
        """Inner speech_end logic, guarded by _processing flag."""
        audio_data = bytes(self._audio_buffer)
        self._audio_buffer.clear()

        if not audio_data:
            return
        if len(audio_data) < MIN_SPEECH_BYTES:
            logger.debug("Ignore short voice chunk: bytes=%s", len(audio_data))
            return
        rms = _normalized_rms_from_pcm16(audio_data)
        if rms < SILENCE_RMS_THRESHOLD:
            logger.debug("Ignore likely silence: rms=%.5f bytes=%s", rms, len(audio_data))
            return

        # 1. STT
        try:
            result = await self._stt.transcribe_buffer_async(audio_data)
        except Exception as e:
            logger.exception("STT failed: %s", e)
            await self._send_error(t("voice.stt_failed"))
            return

        text = result.get("raw_text", "").strip()
        if not text:
            return

        # 2. Optional LLM refine
        if getattr(self._voice_config, "stt_refine_enabled", False):
            try:
                from core.tools.transcribe import refine_with_llm

                loop = asyncio.get_running_loop()
                refined = await loop.run_in_executor(
                    None,
                    lambda: refine_with_llm(
                        text,
                        language=result.get("language", "ja") or "ja",
                    ),
                )
                text = refined.get("refined_text", text)
            except Exception as e:
                logger.warning("STT refine failed, using raw: %s", e)

        # 3. Send transcript to client
        await self._ws.send_json({"type": "transcript", "text": text})

        # 4. Check TTS health before entering IPC loop
        tts_ok = await self._check_tts_health()

        # 5. Send to Anima via IPC (streaming)
        await self._ws.send_json({"type": "response_start"})
        self._tts_playing = True
        self._interrupted = False

        timeout = IPC_STREAM_TIMEOUT
        try:
            timeout_attr = getattr(
                getattr(self._voice_config, "_server_config", None),
                "ipc_stream_timeout",
                None,
            )
            if timeout_attr is not None:
                timeout = float(timeout_attr)
        except (TypeError, AttributeError):
            pass

        response_done_sent = False
        if tts_ok:
            await self._start_tts_worker()
        try:
            # Voice front lane: when configured and reachable, handle the turn
            # here and skip the full agent loop (fallback on health failure).
            if self._front_model:
                lane = self._get_or_create_front_lane()
                try:
                    front_ok = await lane.check_health()
                except Exception:
                    front_ok = False
                if front_ok:
                    response_done_sent = await self._run_front_turn(
                        lane, text, from_person, tts_ok
                    )
                    return
                logger.warning(
                    "voice front unavailable (%s) — falling back to process_message",
                    self._front_model,
                )

            async for ipc_response in self._supervisor.send_request_stream(
                anima_name=self._anima_name,
                method="process_message",
                params={
                    "message": text + VOICE_MODE_SUFFIX,
                    "from_person": from_person,
                    "intent": "",
                    "stream": True,
                    "voice_mode": True,
                    "images": [],
                    "attachment_paths": [],
                },
                timeout=timeout,
            ):
                if self._interrupted:
                    break

                if ipc_response.done:
                    result_data = ipc_response.result or {}
                    cycle_result = result_data.get("cycle_result", {})
                    emotion = cycle_result.get("emotion", "neutral")
                    remaining = self._splitter.flush()
                    if remaining and tts_ok:
                        await self._enqueue_tts(remaining)
                    await self._finish_tts_and_response_done(emotion)
                    response_done_sent = True
                    break

                if ipc_response.chunk:
                    try:
                        chunk_data = json.loads(ipc_response.chunk)
                    except json.JSONDecodeError:
                        chunk_data = {"type": "text_delta", "text": ipc_response.chunk}

                    if chunk_data.get("type") == "keepalive":
                        continue

                    if chunk_data.get("type") == "text_delta":
                        delta = chunk_data.get("text", "")
                        if delta:
                            await self._ws.send_json(
                                {
                                    "type": "response_text",
                                    "text": delta,
                                    "done": False,
                                }
                            )
                            if tts_ok:
                                sentences = self._splitter.feed(delta)
                                for sentence in sentences:
                                    if self._interrupted:
                                        break
                                    await self._enqueue_tts(sentence)

                    elif chunk_data.get("type") == "thinking_start":
                        await self._ws.send_json({"type": "thinking_status", "thinking": True})
                    elif chunk_data.get("type") == "thinking_end":
                        await self._ws.send_json({"type": "thinking_status", "thinking": False})
                    elif chunk_data.get("type") == "thinking_delta":
                        delta = chunk_data.get("text", "")
                        if delta:
                            await self._ws.send_json(
                                {
                                    "type": "thinking_delta",
                                    "text": delta,
                                }
                            )

                    elif chunk_data.get("type") == "cycle_done":
                        cycle_result = chunk_data.get("cycle_result", {})
                        emotion = cycle_result.get("emotion", "neutral")
                        remaining = self._splitter.flush()
                        if remaining and tts_ok:
                            await self._enqueue_tts(remaining)
                        await self._finish_tts_and_response_done(emotion)
                        response_done_sent = True
                        break

        except Exception as e:
            logger.exception("Voice session IPC error: %s", e)
            await self._send_error(str(e))
        finally:
            if not response_done_sent:
                try:
                    # Drain any enqueued audio before the fallback terminal frames
                    # unless barge-in already discarded the queue.
                    if tts_ok and not self._interrupted:
                        await self._drain_tts_queue()
                    await self._ws.send_json(
                        {
                            "type": "emotion",
                            "emotion": "neutral",
                        }
                    )
                    await self._ws.send_json(
                        {
                            "type": "response_done",
                            "emotion": "neutral",
                        }
                    )
                except Exception:
                    pass
            await self._stop_tts_worker()
            self._tts_playing = False
            self._interrupted = False
            self._splitter.flush()

    async def _start_tts_worker(self) -> None:
        """Start a single ordered TTS consumer for the current utterance."""
        await self._stop_tts_worker()
        self._tts_queue = asyncio.Queue(maxsize=TTS_QUEUE_MAXSIZE)
        self._tts_worker = asyncio.create_task(
            self._tts_consumer_loop(),
            name=f"tts-worker-{self._anima_name}",
        )

    async def _tts_consumer_loop(self) -> None:
        """Pull sentences in order and synthesize. One consumer preserves order."""
        queue = self._tts_queue
        if queue is None:
            return
        try:
            while True:
                sentence = await queue.get()
                try:
                    if not self._interrupted:
                        await self._synthesize_and_send(sentence)
                except Exception:
                    # Keep the session alive; synthesis errors are handled inside
                    # _synthesize_and_send, this is a last-resort guard.
                    logger.exception("TTS worker unexpected error (%s)", self._anima_name)
                finally:
                    queue.task_done()
        except asyncio.CancelledError:
            raise

    async def _enqueue_tts(self, sentence: str) -> None:
        """Producer side: enqueue a sentence without waiting for synthesis."""
        queue = self._tts_queue
        if not sentence or queue is None or self._interrupted:
            return
        await queue.put(sentence)

    async def _drain_tts_queue(self) -> None:
        """Wait until the consumer finishes every enqueued sentence."""
        queue = self._tts_queue
        if queue is None:
            return
        await queue.join()

    def _clear_tts_queue(self) -> None:
        """Discard pending sentences (barge-in). In-flight item is left to consumer."""
        queue = self._tts_queue
        if queue is None:
            return
        while True:
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                break
            else:
                queue.task_done()

    async def _stop_tts_worker(self) -> None:
        """Cancel consumer task and drop the queue (no leak on disconnect)."""
        worker = self._tts_worker
        queue = self._tts_queue
        self._tts_worker = None
        self._tts_queue = None
        if queue is not None:
            while True:
                try:
                    queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
                else:
                    queue.task_done()
        if worker is not None and not worker.done():
            worker.cancel()
            try:
                await worker
            except asyncio.CancelledError:
                pass
            except Exception:
                logger.debug("TTS worker stop error", exc_info=True)

    async def _finish_tts_and_response_done(self, emotion: str) -> None:
        """Drain TTS then emit emotion + response_done in that order."""
        if not self._interrupted:
            await self._drain_tts_queue()
        await self._ws.send_json({"type": "emotion", "emotion": emotion})
        await self._ws.send_json({"type": "response_done", "emotion": emotion})

    # ── voice front lane ───────────────────────────────────────────

    def _get_or_create_front_lane(self) -> Any:
        """Lazily build and cache the single per-session voice front lane."""
        if self._front_lane is None:
            from core.paths import get_animas_dir
            from core.prompt.builder import build_voice_front_prompt
            from core.voice.front import VoiceFrontLane

            anima_dir = get_animas_dir() / self._anima_name
            system_prompt = build_voice_front_prompt(
                anima_dir,
                anima_name=self._anima_name,
            )
            self._front_lane = VoiceFrontLane(
                model=self._front_model,
                api_base=self._front_api_base or "",
                system_prompt=system_prompt,
            )
        return self._front_lane

    async def _emit_text_delta(self, delta: str, tts_ok: bool) -> None:
        """Send a text delta to the client and feed the TTS sentence splitter."""
        await self._ws.send_json({"type": "response_text", "text": delta, "done": False})
        if tts_ok:
            sentences = self._splitter.feed(delta)
            for sentence in sentences:
                if self._interrupted:
                    break
                await self._enqueue_tts(sentence)

    def _record_front_conversation(
        self, user_text: str, response_text: str, from_person: str
    ) -> None:
        """Persist the front turn into the anima's default conversation.

        Reuses the existing ``ConversationMemory`` record path so the turn is
        visible from the text chat; failures are non-fatal (front chat must
        stay available even if recording is unavailable).  The user turn uses
        ``from_person`` as the role, matching the existing chat path.

        Concurrency note: this runs in the *server* process and writes
        ``state/conversation.json`` via read-modify-write, so it can race
        with writes from the anima's own process (heartbeat etc.).  There is
        currently no supervisor IPC method to append a conversation turn from
        the server side, so the direct write is kept and the risk documented.
        """
        from core.memory.conversation import ConversationMemory

        try:
            from core.paths import get_animas_dir

            conversation = ConversationMemory(get_animas_dir() / self._anima_name, None)
            conversation.append_turn(from_person or "human", user_text)
            conversation.append_turn("assistant", response_text)
            conversation.save()
        except Exception:
            logger.debug("Failed to persist front conversation (%s)", self._anima_name, exc_info=True)

    async def _run_front_turn(self, lane: Any, text: str, from_person: str, tts_ok: bool) -> bool:
        """Stream one front-lane turn into TTS + WebSocket, then finish.

        Returns ``True`` when the terminal response frames were emitted.
        On interrupt the turn stops immediately (no fallback); the caller's
        ``finally`` block emits the neutral terminal frames instead.
        """
        from core.voice.front import ASK_ANIMA_TOOL, extract_emotion

        results = self._drain_delegation_results()
        if results:
            text = f"{results}\n\n{text}"

        lane.reset_turn()
        full: list[str] = []
        try:
            async for delta in lane.stream(
                text,
                tools=[ASK_ANIMA_TOOL],
                tool_executor=self._ask_anima,
            ):
                if self._interrupted:
                    return False
                await self._emit_text_delta(delta, tts_ok)
                full.append(delta)
        except Exception as e:
            logger.exception("Voice front stream error: %s", e)
            await self._send_error(str(e))
            return False
        if self._interrupted:
            return False
        remaining = self._splitter.flush()
        if remaining and tts_ok:
            await self._enqueue_tts(remaining)
        full_text = "".join(full)
        self._record_front_conversation(text, full_text, from_person)
        emotion = extract_emotion(full_text)
        await self._finish_tts_and_response_done(emotion)
        return True

    # ── ask_anima async delegation (PR-3) ─────────────────────────

    def _ensure_delegation_state(self) -> None:
        """Create delegation queues and start the result watcher once."""
        if self._delegation_results is None:
            self._delegation_results = asyncio.Queue()
            self._delegation_done = asyncio.Queue()
        if self._delegation_watcher is None or self._delegation_watcher.done():
            self._delegation_watcher = asyncio.create_task(
                self._delegation_watcher_loop(),
                name=f"ask-anima-watcher-{self._anima_name}",
            )

    def _ask_anima(self, request: str) -> str:
        """Handle ``ask_anima`` from the front lane (synchronous tool).

        Fires a fire-and-forget ``asyncio.Task`` that runs the request through
        the full agent loop (``process_message``) and returns an ACK string
        immediately so the front conversation is not blocked. At most
        ``MAX_ASK_ANIMA_CONCURRENT`` jobs run at once.
        """
        request = (request or "").strip()
        if not request:
            request = "（依頼内容が指定されていません）"
        if len(self._delegation_jobs) >= MAX_ASK_ANIMA_CONCURRENT:
            return f"実行中の依頼が{MAX_ASK_ANIMA_CONCURRENT}件ある。完了を待ってほしい"
        self._ensure_delegation_state()
        self._delegation_job_counter += 1
        job = self._delegation_job_counter
        task = asyncio.create_task(
            self._run_ask_anima_job(job, request),
            name=f"ask-anima-{self._anima_name}-{job}",
        )
        self._delegation_jobs[job] = task
        return f"受理しました (job {job})。完了したら知らせます"

    async def _run_ask_anima_job(self, job: int, request: str) -> None:
        """Consume the full-agent stream for one delegated request and surface
        the result back to the front lane's reflow queue."""
        result_text = ""
        try:
            async for resp in self._supervisor.send_request_stream(
                anima_name=self._anima_name,
                method="process_message",
                params={
                    "message": request + ASK_ANIMA_DELEGATION_NOTE,
                    "from_person": "human",
                    "intent": "",
                    "stream": True,
                    # Full-capability lane: the delegated job must NOT be
                    # downgraded by voice_mode (voice_thinking_effort etc.).
                    "voice_mode": False,
                    "images": [],
                    "attachment_paths": [],
                },
                timeout=IPC_STREAM_TIMEOUT,
            ):
                if getattr(resp, "done", False):
                    result_data = getattr(resp, "result", None) or {}
                    cycle_result = result_data.get("cycle_result", {}) or {}
                    summary = str(cycle_result.get("summary", "") or "")
                    if summary:
                        result_text = summary
                elif getattr(resp, "chunk", None):
                    try:
                        cd = json.loads(resp.chunk)
                    except (json.JSONDecodeError, TypeError):
                        cd = {}
                    if cd.get("type") == "cycle_done":
                        cycle_result = cd.get("cycle_result", {}) or {}
                        summary = str(cycle_result.get("summary", "") or "")
                        if summary:
                            result_text = summary
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # surface the failure so front can report it
            logger.exception(
                "ask_anima job %s failed (%s): %s", job, self._anima_name, exc
            )
            result_text = "処理に失敗しました。詳細はログを確認してほしい"
        finally:
            self._delegation_jobs.pop(job, None)
            message = (
                f"[ask_anima完了 job {job}: {result_text[:ASK_ANIMA_MAX_RESULT_CHARS]}]"
            )
            if self._delegation_results is not None:
                await self._delegation_results.put(message)
            if self._delegation_done is not None:
                await self._delegation_done.put(None)

    def _drain_delegation_results(self) -> str:
        """Collect all completed ask_anima results for injection into the next
        user turn. Returns an empty string when nothing is pending."""
        if self._delegation_results is None:
            return ""
        parts: list[str] = []
        while True:
            try:
                parts.append(self._delegation_results.get_nowait())
            except asyncio.QueueEmpty:
                break
        return "\n".join(parts)

    async def _delegation_watcher_loop(self) -> None:
        """Proactively run a self-turn when an ask_anima result completes while
        no user turn / TTS playback is in progress, so the front reports the
        outcome in its own words. If a user turn is active, results stay in
        the queue for the next user turn instead (no double-reporting)."""
        while not self._closed:
            try:
                await self._delegation_done.get()
            except asyncio.CancelledError:
                return
            # Let a queued user turn (which also drains results) win if it is
            # about to start, avoiding a self-turn in the same breath.
            await asyncio.sleep(0.05)
            if self._processing or self._tts_playing:
                continue
            if self._closed or self._front_lane is None or not self._front_model:
                continue
            pref = self._drain_delegation_results()
            if not pref:
                continue
            lane = self._front_lane
            try:
                ok = await lane.check_health()
            except Exception:
                ok = False
            if not ok:
                continue
            synthetic = f"{pref} この結果を自分の言葉で短く報告して"
            try:
                await self._run_front_turn(
                    lane, synthetic, "human", await self._check_tts_health()
                )
            except Exception:
                logger.exception(
                    "ask_anima self-turn failed (%s)", self._anima_name
                )

    async def close(self) -> None:
        """Cancel TTS worker on session teardown (WS disconnect).

        Running ask_anima delegation tasks are deliberately NOT cancelled —
        they keep the full-agent loop going and the result is persisted in the
        conversation by ``process_message`` itself. The watcher (self-turn)
        is stopped because the WS is gone.
        """
        self._closed = True
        watcher = self._delegation_watcher
        self._delegation_watcher = None
        if watcher is not None and not watcher.done():
            watcher.cancel()
            try:
                await watcher
            except (asyncio.CancelledError, Exception):
                pass
        self._interrupted = True
        self._clear_tts_queue()
        await self._stop_tts_worker()

    async def _synthesize_and_send(self, text: str) -> None:
        """TTS synthesize a sentence and send audio to client."""
        text = sanitize_for_tts(text)
        if not text:
            return
        try:
            # text rides along so the client can show a playback-synced subtitle
            await self._ws.send_json({"type": "tts_start", "text": text})
            async for audio_chunk in self._tts.synthesize(text, self._tts_config):
                if self._interrupted:
                    break
                await self._ws.send_bytes(audio_chunk)
            await self._ws.send_json({"type": "tts_done"})
            self._consecutive_tts_failures = 0
        except TTSSynthesisError as e:
            self._consecutive_tts_failures += 1
            logger.warning("TTS synthesis failed (%d consecutive): %s", self._consecutive_tts_failures, e)
            if self._consecutive_tts_failures >= 3:
                self.invalidate_tts_health()
            try:
                await self._ws.send_json({"type": "tts_error", "message": "TTS synthesis failed"})
                await self._ws.send_json({"type": "tts_done"})
            except Exception:
                pass
        except Exception as e:
            logger.warning("TTS send error: %s", e)
            try:
                await self._ws.send_json({"type": "tts_done"})
            except Exception:
                pass

    async def greet_and_speak(self) -> None:
        """Greet on connect — instant audio feedback that also warms the
        anima's chat runner / priming caches before the first utterance.
        Uses the cached greet path (1h cooldown), so repeated popups are cheap."""
        try:
            # 90s: cold greet = runner spawn + generate (~25s) + slow-exit
            # kill-wait (30s) can exceed 60s. Cached greets return instantly.
            result = await self._supervisor.send_request(
                anima_name=self._anima_name,
                method="greet",
                params={},
                timeout=90.0,
            )
        except Exception as e:
            logger.info("Voice greet skipped (%s): %s", self._anima_name, e)
            return
        text = str((result or {}).get("response", "")).strip()
        if not text or self._processing:
            return
        emotion = (result or {}).get("emotion", "neutral")
        tts_ok = await self._check_tts_health()
        self._interrupted = False
        try:
            await self._ws.send_json({"type": "response_start"})
            await self._ws.send_json({"type": "response_text", "text": text})
            await self._ws.send_json({"type": "emotion", "emotion": emotion})
            if tts_ok:
                self._tts_playing = True
                # Same prefetch worker as speech replies — first audio still
                # arrives after the first sentence synthesizes, later ones pipeline.
                from core.voice.sentence_splitter import split_sentences

                await self._start_tts_worker()
                for sentence in split_sentences(text):
                    if self._interrupted or self._processing:
                        break
                    await self._enqueue_tts(sentence)
                if not self._interrupted and not self._processing:
                    await self._drain_tts_queue()
            await self._ws.send_json({"type": "response_done", "emotion": emotion})
        except Exception as e:
            logger.debug("Voice greet delivery failed (%s): %s", self._anima_name, e)
        finally:
            await self._stop_tts_worker()
            self._tts_playing = False

    async def handle_interrupt(self) -> None:
        """Handle barge-in: stop TTS, drop queued sentences, prepare for new STT."""
        self._interrupted = True
        self._audio_buffer.clear()
        self._clear_tts_queue()

    async def _send_error(self, message: str) -> None:
        """Send error message to client."""
        try:
            await self._ws.send_json({"type": "error", "message": message})
        except Exception:
            logger.debug("Failed to send error to client", exc_info=True)
