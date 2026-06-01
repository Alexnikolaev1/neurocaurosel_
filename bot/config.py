"""Centralized configuration for NeuroCarousel."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_token: str
    gemini_key: str
    hf_key: str
    slides_count: int = 10
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
        "gemini-2.0-flash-lite",
        "gemini-1.5-flash",
        "gemini-2.0-flash",
    )

    @classmethod
    def from_env(cls) -> Settings:
        models_raw = os.getenv(
            "GEMINI_MODELS",
            "gemini-2.0-flash-lite,gemini-1.5-flash,gemini-2.0-flash",
        )
        return cls(
            telegram_token=_require("TELEGRAM_TOKEN"),
            gemini_key=_require("GEMINI_API_KEY"),
            hf_key=_require("HF_API_KEY"),
            slides_count=int(os.getenv("SLIDES_COUNT", "10")),
            default_style=os.getenv("DEFAULT_STYLE", "cinematic"),
            gemini_models=tuple(m.strip() for m in models_raw.split(",") if m.strip()),
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

# Visual style presets appended to every image prompt
STYLE_PRESETS: dict[str, str] = {
    "cinematic": "cinematic lighting, high quality, detailed, vibrant colors, 8k",
    "minimal": "minimalist flat design, clean composition, soft pastel palette, modern",
    "anime": "anime illustration style, vivid colors, detailed background, studio quality",
    "retro": "retro 80s aesthetic, synthwave colors, grain texture, nostalgic mood",
    "photo": "photorealistic, natural lighting, shallow depth of field, professional photo",
}
