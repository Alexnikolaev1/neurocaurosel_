"""
Telegram webhook — https://YOUR_DOMAIN.vercel.app/api/bot
Vercel: папка api/bot/ → маршрут /api/bot
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

from fastapi import FastAPI, Request
from fastapi.responses import PlainTextResponse

# Корень репозитория (пакет bot/ — не путать с api/bot/)
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from bot.neuro_carousel import NeuroCarouselBot  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("neurocarousel.webhook")

_bot: NeuroCarouselBot | None = None

app = FastAPI()


def _get_bot() -> NeuroCarouselBot:
    global _bot
    if _bot is None:
        token = os.environ.get("TELEGRAM_TOKEN", "")
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        hf_key = os.environ.get("HF_API_KEY", "")
        missing = [
            n
            for n, v in (
                ("TELEGRAM_TOKEN", token),
                ("GEMINI_API_KEY", gemini_key),
                ("HF_API_KEY", hf_key),
            )
            if not v
        ]
        if missing:
            raise RuntimeError(f"Missing env on Vercel: {', '.join(missing)}")
        _bot = NeuroCarouselBot(token=token, gemini_key=gemini_key, hf_key=hf_key)
    return _bot


@app.get("/")
async def health() -> PlainTextResponse:
    return PlainTextResponse("NeuroCarousel bot is alive!")


@app.post("/")
async def webhook(request: Request) -> PlainTextResponse:
    try:
        update = await request.json()
        logger.info("Update: %s", json.dumps(update, ensure_ascii=False)[:300])
        bot = _get_bot()
        await bot.handle_update(update)
        return PlainTextResponse("OK")
    except Exception:
        logger.exception("Webhook error")
        return PlainTextResponse("error", status_code=500)
