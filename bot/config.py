"""Centralized configuration for NeuroCarousel."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _is_vercel() -> bool:
    return bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_token: str
    gemini_key: str
    hf_key: str
    slides_count: int = 9
    batch_size: int = 3
    topic_min_len: int = 3
    topic_max_len: int = 500
    hf_retry_count: int = 3
    hf_retry_delay: float = 3.0
    hf_between_delay: float = 2.5
    request_timeout: float = 60.0
    image_max_size: int = 1280
    image_jpeg_quality: int = 85
    scenario_cache_max: int = 200
    default_style: str = "cinematic"
    gemini_retry_count: int = 4
    gemini_retry_base_delay: float = 2.0
    gemini_models: tuple[str, ...] = (
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    )
    serverless_mode: bool = False
    pollinations_only: bool = False
    function_timeout_sec: float = 55.0

    @classmethod
    def from_env(cls) -> Settings:
        return build_settings(
            telegram_token=_require("TELEGRAM_TOKEN"),
            gemini_key=_require("GEMINI_API_KEY"),
            hf_key=_require("HF_API_KEY"),
        )


def build_settings(
    *,
    telegram_token: str,
    gemini_key: str,
    hf_key: str,
) -> Settings:
    models_raw = os.getenv(
        "GEMINI_MODELS",
        "gemini-2.0-flash,gemini-2.0-flash-lite",
    )
    vercel = _is_vercel()
    serverless = os.getenv("SERVERLESS_MODE", "1" if vercel else "0") == "1"

    default_slides = "9" if serverless else "10"
    slides = int(os.getenv("SLIDES_COUNT", default_slides))
    batch_size = int(os.getenv("BATCH_SIZE", "3"))

    pollinations_only = os.getenv("POLLINATIONS_ONLY", "1" if serverless else "0") == "1"
    between_delay = float(os.getenv("HF_BETWEEN_DELAY", "0.5" if serverless else "2.5"))

    timeout = float(os.getenv("FUNCTION_TIMEOUT_SEC", "55" if serverless else "300"))

    return Settings(
        telegram_token=telegram_token,
        gemini_key=gemini_key,
        hf_key=hf_key,
        slides_count=slides,
        batch_size=batch_size,
        default_style=os.getenv("DEFAULT_STYLE", "cinematic"),
        gemini_models=tuple(m.strip() for m in models_raw.split(",") if m.strip()),
        serverless_mode=serverless,
        pollinations_only=pollinations_only,
        hf_between_delay=between_delay,
        function_timeout_sec=timeout,
        image_max_size=int(os.getenv("IMAGE_MAX_SIZE", "1024" if serverless else "1280")),
    )


def _require(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"


def gemini_url(model: str, key: str) -> str:
    return f"{GEMINI_API_BASE}/{model}:generateContent?key={key}"

HF_URL = "https://api-inference.huggingface.co/models/stabilityai/stable-diffusion-xl-base-1.0"

POLLINATIONS_URL = (
    "https://image.pollinations.ai/prompt/{prompt}?width=1024&height=1024&nologo=true"
)

STYLE_PRESETS: dict[str, str] = {
    "cinematic": "cinematic lighting, high quality, detailed, vibrant colors, 8k",
    "minimal": "minimalist flat design, clean composition, soft pastel palette, modern",
    "anime": "anime illustration style, vivid colors, detailed background, studio quality",
    "retro": "retro 80s aesthetic, synthwave colors, grain texture, nostalgic mood",
    "photo": "photorealistic, natural lighting, shallow depth of field, professional photo",
}
