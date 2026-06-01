"""
Telegram webhook — POST/GET https://YOUR_DOMAIN.vercel.app/api/bot
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
import os
import sys
import threading
from http.server import BaseHTTPRequestHandler

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _ROOT not in sys.path:
    sys.path.insert(0, _ROOT)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("neurocarousel.webhook")

_bot = None
_bot_lock = threading.Lock()


def _load_bot_class():
    path = os.path.join(_ROOT, "bot", "neuro_carousel.py")
    spec = importlib.util.spec_from_file_location("nc_neuro_carousel", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load bot from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.NeuroCarouselBot


def _get_bot():
    global _bot
    with _bot_lock:
        if _bot is None:
            token = os.environ.get("TELEGRAM_TOKEN", "")
            gemini_key = os.environ.get("GEMINI_API_KEY", "")
            hf_key = os.environ.get("HF_API_KEY", "")
            missing = [n for n, v in (
                ("TELEGRAM_TOKEN", token),
                ("GEMINI_API_KEY", gemini_key),
                ("HF_API_KEY", hf_key),
            ) if not v]
            if missing:
                raise RuntimeError(f"Missing env on Vercel: {', '.join(missing)}")
            BotClass = _load_bot_class()
            _bot = BotClass(token=token, gemini_key=gemini_key, hf_key=hf_key)
        return _bot


def _process_update(update: dict) -> None:
    try:
        bot = _get_bot()
        asyncio.run(bot.handle_update(update))
    except Exception:
        logger.exception("Background processing failed")


class handler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.end_headers()
        self.wfile.write(b"NeuroCarousel bot is alive!")

    def do_POST(self):  # noqa: N802
        try:
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            update = json.loads(body)
            logger.info("Update: %s", json.dumps(update, ensure_ascii=False)[:300])

            # Сразу 200 — иначе Telegram шлёт повторные webhook (504/дубли)
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"OK")

            thread = threading.Thread(
                target=_process_update,
                args=(update,),
                daemon=True,
            )
            thread.start()
        except Exception:
            logger.exception("Webhook error")
            self.send_response(500)
            self.end_headers()
            self.wfile.write(b"error")

    def log_message(self, format, *args):  # noqa: A002
        logger.debug(format, *args)
