from __future__ import annotations

# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
from collections.abc import Callable

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from core.general_db import SnsSearchStore


class SnsSearchInput(BaseModel):
    Division: str = Field(min_length=1, max_length=100)
    Words: str = Field(min_length=1, max_length=2000)


def create_sns_search_router(store_factory: Callable[[], SnsSearchStore] | None = None) -> APIRouter:
    router = APIRouter()
    get_store = store_factory or SnsSearchStore

    @router.get("/sns-search")
    async def list_sns_search_entries():
        store = get_store()
        return {"items": [entry.to_dict() for entry in store.list_entries()]}

    @router.post("/sns-search")
    async def create_sns_search_entry(body: SnsSearchInput):
        store = get_store()
        try:
            entry = store.create_entry(body.Division, body.Words)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        return {"item": entry.to_dict()}

    @router.put("/sns-search/{entry_id}")
    async def update_sns_search_entry(entry_id: int, body: SnsSearchInput):
        store = get_store()
        try:
            entry = store.update_entry(entry_id, body.Division, body.Words)
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        if entry is None:
            raise HTTPException(404, "SNS search entry not found")
        return {"item": entry.to_dict()}

    @router.delete("/sns-search/{entry_id}")
    async def delete_sns_search_entry(entry_id: int):
        store = get_store()
        if not store.delete_entry(entry_id):
            raise HTTPException(404, "SNS search entry not found")
        return {"status": "ok", "deleted": entry_id}

    return router
