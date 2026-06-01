"""
NeuroCarousel — Vercel Serverless Webhook (POST /api/bot)
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

# Корень репозитория в PYTHONPATH (пакет bot/ не путать с этим файлом api/bot.py)
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

from http.server import BaseHTTPRequestHandler

from bot.neuro_carousel import NeuroCarouselBot  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("neurocarousel.webhook")

_bot: NeuroCarouselBot | None = None


def _get_bot() -> NeuroCarouselBot:
    global _bot
    if _bot is None:
        token = os.environ.get("TELEGRAM_TOKEN", "")
        gemini_key = os.environ.get("GEMINI_API_KEY", "")
        hf_key = os.environ.get("HF_API_KEY", "")
        if not all((token, gemini_key, hf_key)):
            missing = [
                n
                for n, v in (
                    ("TELEGRAM_TOKEN", token),
                    ("GEMINI_API_KEY", gemini_key),
                    ("HF_API_KEY", hf_key),
                )
                if not v
            ]
            raise RuntimeError(f"Missing env on Vercel: {', '.join(missing)}")
        _bot = NeuroCarouselBot(token=token, gemini_key=gemini_key, hf_key=hf_key)
    return _bot


class handler(BaseHTTPRequestHandler):
    """Vercel Python: класс handler (BaseHTTPRequestHandler)."""

    def do_POST(self):  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            update = json.loads(body)
            logger.info("Update: %s", json.dumps(update, ensure_ascii=False)[:300])

            bot = _get_bot()
            asyncio.run(bot.handle_update(update))

            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")
        except Exception:
            logger.exception("Webhook error")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"error")

    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"NeuroCarousel bot is alive!")

    def log_message(self, format, *args):  # noqa: A002
        logger.debug(format, *args)
