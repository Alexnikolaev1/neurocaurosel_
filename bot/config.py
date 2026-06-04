"""Centralized configuration for NeuroCarousel."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

BUILD_TAG = "v7-placeholder"


def pollinations_key_from_env() -> str:
    """Несколько имён переменной — на Vercel часто опечатка в имени."""
    for name in (
        "POLLINATIONS_API_KEY",
        "POLLINATIONS_KEY",
        "POLLEN_API_KEY",
        "POLLINATIONS_TOKEN",
    ):
        value = os.getenv(name, "").strip()
        if value:
            return value
    return ""


def deployment_status_json() -> str:
    """Для GET /api/bot — проверка деплоя и env без секретов."""
    poll = pollinations_key_from_env()
    poll_names = sorted(k for k in os.environ if "POLL" in k.upper())
    data = {
        "build": BUILD_TAG,
        "pollinations_key_loaded": bool(poll),
        "pollinations_key_length": len(poll),
        "poll_env_variable_names": poll_names,
        "hf_api_key_length": len(os.getenv("HF_API_KEY", "").strip()),
        "skip_gemini": os.getenv("SKIP_GEMINI", "(default 1 on Vercel)"),
        "pollinations_only": os.getenv("POLLINATIONS_ONLY", "0"),
        "vercel": bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV")),
    }
    return json.dumps(data, ensure_ascii=False, indent=2)


def _is_vercel() -> bool:
    return bool(os.getenv("VERCEL") or os.getenv("VERCEL_ENV"))


@dataclass(frozen=True, slots=True)
class Settings:
    telegram_token: str
    gemini_key: str
    hf_key: str
    slides_count: int = 7
    batch_size: int = 1
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
    gemini_retry_count: int = 2
    gemini_retry_base_delay: float = 3.0
    gemini_models: tuple[str, ...] = (
        "gemini-2.0-flash",
        "gemini-2.0-flash-lite",
    )
    serverless_mode: bool = False
    pollinations_only: bool = False
    pollinations_api_key: str = ""
    skip_gemini: bool = False
    placeholder_on_fail: bool = True
    function_timeout_sec: float = 55.0

    @classmethod
    def from_env(cls) -> Settings:
        return build_settings(
            telegram_token=_require("TELEGRAM_TOKEN"),
            gemini_key=_require("GEMINI_API_KEY"),
            hf_key=os.getenv("HF_API_KEY", "").strip(),
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

    default_slides = "7" if serverless else "10"
    default_batch = "1" if serverless else "3"
    slides = int(os.getenv("SLIDES_COUNT", default_slides))
    batch_size = int(os.getenv("BATCH_SIZE", default_batch))

    pollinations_only = os.getenv("POLLINATIONS_ONLY", "0" if serverless else "0") == "1"
    between_delay = float(os.getenv("HF_BETWEEN_DELAY", "0.5" if serverless else "2.5"))

    timeout = float(os.getenv("FUNCTION_TIMEOUT_SEC", "55" if serverless else "300"))
    poll_key = pollinations_key_from_env()

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
        pollinations_api_key=poll_key,
        skip_gemini=os.getenv("SKIP_GEMINI", "1" if serverless else "0") == "1",
        placeholder_on_fail=os.getenv("PLACEHOLDER_ON_FAIL", "1") == "1",
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

HF_ROUTER_TEMPLATE = "https://router.huggingface.co/hf-inference/models/{model}"

HF_IMAGE_MODELS = (
    "black-forest-labs/FLUX.1-schnell",
    "stabilityai/stable-diffusion-xl-base-1.0",
)

GEN_POLLINATIONS_TEMPLATE = "https://gen.pollinations.ai/image/{prompt}"

POLLINATIONS_URL = (
    "https://image.pollinations.ai/prompt/{prompt}"
    "?width=512&height=512&nologo=true"
)

STYLE_PRESETS: dict[str, str] = {
    "cinematic": "cinematic lighting, high quality, detailed, vibrant colors, 8k",
    "minimal": "minimalist flat design, clean composition, soft pastel palette, modern",
    "anime": "anime illustration style, vivid colors, detailed background, studio quality",
    "retro": "retro 80s aesthetic, synthwave colors, grain texture, nostalgic mood",
    "photo": "photorealistic, natural lighting, shallow depth of field, professional photo",
}
