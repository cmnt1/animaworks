# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0

"""Transport protocol for voice-session output."""

from __future__ import annotations

from typing import Any, Protocol


class VoiceTransport(Protocol):
    """Outbound transport used by :class:`core.voice.session.VoiceSession`."""

    async def send_event(self, event: dict[str, Any]) -> None:
        """Send one structured event to the voice client."""
        ...

    async def send_audio(self, data: bytes) -> None:
        """Send one binary audio frame to the voice client."""
        ...
