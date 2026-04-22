from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
#
# This file is part of AnimaWorks core/server, licensed under Apache-2.0.
# See LICENSE for the full license text.

"""Web approval endpoints for interactive call_human flows (tokenized links)."""

import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)


def create_approve_router() -> APIRouter:
    """Create the approval API router (mounted under ``/api``)."""
    router = APIRouter(prefix="/approve", tags=["approve"])

    @router.get("/{callback_id}", response_class=HTMLResponse)
    async def get_approval_page(callback_id: str, token: str = "") -> HTMLResponse:
        """Serve the approval page for a given callback_id."""
        from core.notification.interactive import get_interaction_router

        rtr = get_interaction_router()

        # Magic-link pattern: the token is the URL secret. Re-verify here so a request
        # without a valid token cannot load the page (even though POST also checks;
        # the HTML embeds the token for the client script, not as a server-side auth bypass).
        if not rtr.verify_approval_token(callback_id, token):
            raise HTTPException(status_code=403, detail="Invalid or expired token")

        req = await rtr.lookup(callback_id)
        if req is None:
            raise HTTPException(status_code=404, detail="Approval request not found or expired")

        html_path = Path(__file__).parent.parent / "static" / "approve.html"
        if not html_path.exists():
            raise HTTPException(status_code=500, detail="Approval page template not found")

        html = html_path.read_text(encoding="utf-8")
        context = {
            "callback_id": callback_id,
            "token": token,
            "category": req.category,
            "options": req.options,
            "anima_name": req.anima_name,
        }
        html = html.replace("__APPROVAL_CONTEXT__", json.dumps(context, ensure_ascii=False))

        return HTMLResponse(content=html)

    @router.post("/{callback_id}")
    async def submit_approval(callback_id: str, request: Request) -> JSONResponse:
        """Process an approval decision from the web page."""
        from core.notification.interactive import get_interaction_router

        rtr = get_interaction_router()

        try:
            body = await request.json()
        except Exception:
            raise HTTPException(status_code=400, detail="Invalid JSON body") from None

        token = body.get("token", "")
        decision = body.get("decision", "")
        comment = body.get("comment", "")
        actor = body.get("actor", "web_user")

        if not token or not decision:
            raise HTTPException(status_code=400, detail="Missing token or decision")

        if not rtr.verify_approval_token(callback_id, token):
            raise HTTPException(status_code=403, detail="Invalid or expired token")

        result = await rtr.resolve(callback_id, decision=decision, actor=actor, source="web", comment=comment)

        if result is None:
            raise HTTPException(status_code=409, detail="Already resolved or expired")

        return JSONResponse(content={"status": "ok", "decision": decision})

    return router
