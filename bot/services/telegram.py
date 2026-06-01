"""Telegram Bot API client."""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from bot.config import TELEGRAM_API, Settings

logger = logging.getLogger("neurocarousel.telegram")


class TelegramClient:
    """No persistent httpx client — safe for Vercel serverless / ASGI."""

    def __init__(self, settings: Settings) -> None:
        self._token = settings.telegram_token
        self._timeout = settings.request_timeout

    def _url(self, method: str) -> str:
        return TELEGRAM_API.format(token=self._token, method=method)

    async def send_message(
        self,
        chat_id: int,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup: dict | None = None,
    ) -> dict:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        return await self._post("sendMessage", json=payload)

    async def edit_message(
        self,
        chat_id: int,
        message_id: int,
        text: str,
        *,
        parse_mode: str = "HTML",
        reply_markup: dict | None = None,
    ) -> None:
        payload: dict[str, Any] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "text": text,
            "parse_mode": parse_mode,
        }
        if reply_markup:
            payload["reply_markup"] = json.dumps(reply_markup)
        await self._post("editMessageText", json=payload)

    async def send_media_group(
        self,
        chat_id: int,
        media: list[dict],
        files: dict[str, bytes],
    ) -> dict:
        multipart: list[tuple] = [
            ("chat_id", (None, str(chat_id))),
            ("media", (None, json.dumps(media))),
        ]
        for field, data in files.items():
            multipart.append((field, (f"{field}.jpg", data, "image/jpeg")))

        async with httpx.AsyncClient(timeout=120.0) as client:
            r = await client.post(self._url("sendMediaGroup"), files=multipart)
        data = r.json()
        if not data.get("ok"):
            logger.error("sendMediaGroup failed: %s", data)
        return data

    async def send_chat_action(self, chat_id: int, action: str = "upload_photo") -> None:
        await self._post("sendChatAction", json={"chat_id": chat_id, "action": action})

    async def answer_callback_query(
        self,
        callback_query_id: str,
        text: str | None = None,
        *,
        show_alert: bool = False,
    ) -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_query_id}
        if text:
            payload["text"] = text
            payload["show_alert"] = show_alert
        await self._post("answerCallbackQuery", json=payload)

    async def _post(self, method: str, **kwargs: Any) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            r = await client.post(self._url(method), **kwargs)
        data = r.json()
        if not data.get("ok"):
            logger.warning("Telegram %s error: %s", method, data.get("description", data))
        return data
