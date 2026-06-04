"""
NeuroCarousel — публичный фасад бота.

Сохраняет обратную совместимость с api/bot.py и setup_webhook.
"""

from __future__ import annotations

from bot.config import build_settings
from bot.handlers.updates import UpdateRouter


class NeuroCarouselBot:
    """Thin facade delegating to UpdateRouter."""

    def __init__(self, token: str, gemini_key: str, hf_key: str) -> None:
        self._token = token
        self._gemini_key = gemini_key
        self._hf_key = hf_key

    def _router(self) -> UpdateRouter:
        settings = build_settings(
            telegram_token=self._token,
            gemini_key=self._gemini_key,
            hf_key=self._hf_key,
        )
        return UpdateRouter(settings)

    async def handle_update(self, update: dict) -> None:
        await self._router().handle(update)
