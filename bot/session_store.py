"""Хранение сессии карусели между вызовами Vercel (память + Upstash Redis)."""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import httpx

from bot.models import CarouselSession, Slide, TextMode, VisualStyle

logger = logging.getLogger("neurocarousel.session_store")

_memory: dict[int, str] = {}
_TTL_SEC = 86400  # 24 ч


def _redis_configured() -> bool:
    return bool(os.getenv("UPSTASH_REDIS_REST_URL") and os.getenv("UPSTASH_REDIS_REST_TOKEN"))


def _redis_key(chat_id: int) -> str:
    return f"nc:session:{chat_id}"


def serialize_session(session: CarouselSession) -> str:
    return json.dumps(
        {
            "chat_id": session.chat_id,
            "topic": session.topic,
            "language": session.language,
            "style": session.style.value,
            "status_message_id": session.status_message_id,
            "next_index": session.next_index,
            "batch_size": session.batch_size,
            "text_mode": session.text_mode.value,
            "slides": [s.to_dict() for s in session.slides],
        },
        ensure_ascii=False,
    )


def deserialize_session(raw: str) -> CarouselSession | None:
    try:
        data = json.loads(raw)
        slides = [Slide.from_dict(item) for item in data["slides"]]
        return CarouselSession(
            chat_id=int(data["chat_id"]),
            topic=str(data["topic"]),
            language=str(data["language"]),
            style=VisualStyle.from_value(data.get("style")),
            slides=slides,
            status_message_id=int(data["status_message_id"]),
            next_index=int(data.get("next_index", 0)),
            batch_size=int(data.get("batch_size", 2)),
            text_mode=TextMode.from_value(data.get("text_mode")),
        )
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        logger.exception("Bad session JSON")
        return None


async def _redis_command(command: list[Any]) -> dict | None:
    url = os.getenv("UPSTASH_REDIS_REST_URL", "").rstrip("/")
    token = os.getenv("UPSTASH_REDIS_REST_TOKEN", "")
    if not url or not token:
        return None
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            r = await client.post(
                url,
                json=command,
                headers={"Authorization": f"Bearer {token}"},
            )
            r.raise_for_status()
            return r.json()
    except Exception:
        logger.exception("Upstash command failed: %s", command[0])
        return None


async def save_session(session: CarouselSession) -> None:
    payload = serialize_session(session)
    _memory[session.chat_id] = payload

    if not _redis_configured():
        return

    result = await _redis_command(["SET", _redis_key(session.chat_id), payload, "EX", _TTL_SEC])
    if result and result.get("result") != "OK":
        logger.warning("Upstash SET unexpected: %s", result)


async def load_session(chat_id: int) -> CarouselSession | None:
    payload = _memory.get(chat_id)

    if not payload and _redis_configured():
        result = await _redis_command(["GET", _redis_key(chat_id)])
        if result and result.get("result"):
            payload = result["result"]
            _memory[chat_id] = payload

    if not payload:
        return None
    return deserialize_session(payload)


async def delete_session(chat_id: int) -> None:
    _memory.pop(chat_id, None)
    if _redis_configured():
        await _redis_command(["DEL", _redis_key(chat_id)])


def storage_mode() -> str:
    return "upstash+memory" if _redis_configured() else "memory-only"
