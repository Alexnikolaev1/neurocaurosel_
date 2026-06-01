"""
NeuroCarousel Bot — Vercel Serverless Webhook Handler
======================================================
Точка входа: POST /api/bot
Vercel вызывает эту функцию при каждом апдейте от Telegram.
"""

import json
import logging
import os
import sys
from http.server import BaseHTTPRequestHandler

# Добавляем корень проекта в path, чтобы импортировать bot/
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from bot.neuro_carousel import NeuroCarouselBot  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("neurocarousel.webhook")

# Синглтон бота — переиспользуется между горячими вызовами Vercel
_bot: NeuroCarouselBot | None = None


def _get_bot() -> NeuroCarouselBot:
    global _bot
    if _bot is None:
        token = os.environ["TELEGRAM_TOKEN"]
        gemini_key = os.environ["GEMINI_API_KEY"]
        hf_key = os.environ["HF_API_KEY"]
        _bot = NeuroCarouselBot(token=token, gemini_key=gemini_key, hf_key=hf_key)
    return _bot


class handler(BaseHTTPRequestHandler):
    """Vercel ожидает класс `handler`, наследующий BaseHTTPRequestHandler."""

    def do_POST(self):  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            update = json.loads(body)
            logger.info("Received update: %s", json.dumps(update)[:300])

            import asyncio

            bot = _get_bot()
            asyncio.run(bot.handle_update(update))

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

        except Exception as exc:
            logger.exception("Unhandled error in webhook: %s", exc)
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"Internal Server Error")

    def do_GET(self):  # noqa: N802
        """Health-check для мониторинга."""
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"NeuroCarousel bot is alive!")

    def log_message(self, format, *args):  # noqa: A002
        # Отключаем дефолтный вывод BaseHTTPRequestHandler — используем logging
        logger.debug(format, *args)
