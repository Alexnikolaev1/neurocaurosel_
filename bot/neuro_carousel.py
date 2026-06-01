"""
NeuroCarousel — публичный фасад бота.

Сохраняет обратную совместимость с api/bot.py и setup_webhook.
"""

from __future__ import annotations

from bot.config import Settings
from bot.handlers.updates import UpdateRouter


class NeuroCarouselBot:
    """Thin facade delegating to UpdateRouter."""

    def __init__(self, token: str, gemini_key: str, hf_key: str) -> None:
        settings = Settings(
            telegram_token=token,
            gemini_key=gemini_key,
            hf_key=hf_key,
        )
        self._router = UpdateRouter(settings)

    async def handle_update(self, update: dict) -> None:
        await self._router.handle(update)
