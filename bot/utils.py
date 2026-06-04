"""Shared utilities."""

from __future__ import annotations

import hashlib
import html
import io
import json
import re

from PIL import Image

from bot.config import Settings


def is_valid_topic(text: str, settings: Settings) -> tuple[bool, str | None]:
    """
    Validate user topic.
    Returns (ok, error_code) where error_code is 'link' | 'length' | None.
    """
    text = text.strip()
    if re.match(r"https?://", text, re.IGNORECASE) or re.match(r"www\.", text, re.IGNORECASE):
        return False, "link"
    if len(text) < settings.topic_min_len or len(text) > settings.topic_max_len:
        return False, "length"
    return True, None


def detect_language(text: str) -> str:
    return "ru" if re.search(r"[а-яёА-ЯЁ]", text) else "en"


def extract_json_array(raw: str) -> list[dict]:
    """Extract JSON array from Gemini response (may include markdown fences)."""
    cleaned = re.sub(r"```(?:json)?", "", raw).strip().rstrip("`").strip()
    match = re.search(r"\[.*\]", cleaned, re.DOTALL)
    if match:
        cleaned = match.group(0)
    return json.loads(cleaned)


def escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def topic_hash(topic: str) -> str:
    return hashlib.sha256(topic.strip().lower().encode()).hexdigest()[:16]


def compress_image(data: bytes, max_size: int, quality: int) -> bytes:
    """Resize and compress image for faster Telegram upload."""
    try:
        with Image.open(io.BytesIO(data)) as img:
            img = img.convert("RGB")
            img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=quality, optimize=True)
            return buf.getvalue()
    except Exception:
        return data


def progress_bar(current: int, total: int, width: int = 10) -> str:
    filled = int(width * current / total) if total else 0
    return "▓" * filled + "░" * (width - filled)
