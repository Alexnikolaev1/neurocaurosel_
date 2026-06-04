"""Image generation: Hugging Face SDXL + Pollinations fallback."""

from __future__ import annotations

import asyncio
import logging
import urllib.parse

import httpx

from bot.config import HF_URL, POLLINATIONS_URL, Settings
from bot.utils import compress_image

logger = logging.getLogger("neurocarousel.images")

_MIN_BYTES = 2000


class ImageGenerator:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http
        self._headers = {"Authorization": f"Bearer {settings.hf_key}"}

    async def generate(self, prompt: str, *, raw: bool = False) -> bytes | None:
        short_prompt = self._shorten_prompt(prompt)

        if self._settings.pollinations_only:
            image = await self._generate_pollinations(short_prompt)
            if not image and self._settings.serverless_mode:
                image = await self._generate_hf(short_prompt, fast=True)
            return self._finalize(image, raw=raw)

        image = await self._generate_hf(short_prompt)
        if image:
            return self._finalize(image, raw=raw)
        logger.warning("HF failed, trying Pollinations")
        image = await self._generate_pollinations(short_prompt)
        return self._finalize(image, raw=raw)

    def _finalize(self, image: bytes | None, *, raw: bool) -> bytes | None:
        if not image:
            return None
        return image if raw else self._optimize(image)

    def _shorten_prompt(self, prompt: str) -> str:
        p = " ".join(prompt.split())
        limit = 380 if self._settings.serverless_mode else 700
        if len(p) > limit:
            p = p[: limit - 3] + "..."
        return p

    def _optimize(self, data: bytes) -> bytes:
        return compress_image(
            data,
            max_size=self._settings.image_max_size,
            quality=self._settings.image_jpeg_quality,
        )

    async def _generate_hf(self, prompt: str, *, fast: bool = False) -> bytes | None:
        payload = {
            "inputs": prompt,
            "parameters": {
                "num_inference_steps": 18 if fast else 28,
                "guidance_scale": 7.5,
                "width": 768 if fast else 1024,
                "height": 768 if fast else 1024,
            },
        }
        timeout = 25.0 if fast else 90.0
        attempts = 1 if fast else self._settings.hf_retry_count

        for attempt in range(1, attempts + 1):
            try:
                logger.info("HF attempt %d: %s", attempt, prompt[:60])
                r = await self._http.post(
                    HF_URL,
                    headers=self._headers,
                    json=payload,
                    timeout=timeout,
                )

                if r.status_code == 200 and len(r.content) >= _MIN_BYTES:
                    return r.content

                if r.status_code in (429, 503):
                    wait = self._settings.hf_retry_delay * attempt
                    logger.warning("HF rate-limit %s, waiting %.1fs", r.status_code, wait)
                    await asyncio.sleep(wait)
                    continue

                logger.error("HF error %s: %s", r.status_code, r.text[:200])
                return None

            except httpx.TimeoutException:
                logger.warning("HF timeout on attempt %d", attempt)
                if not fast:
                    await asyncio.sleep(self._settings.hf_retry_delay)

        return None

    def _pollinations_timeout(self) -> float:
        return 28.0 if self._settings.serverless_mode else 60.0

    async def _generate_pollinations(self, prompt: str) -> bytes | None:
        encoded = urllib.parse.quote(prompt, safe="")
        url = POLLINATIONS_URL.format(prompt=encoded)
        timeout = self._pollinations_timeout()
        retries = 2 if self._settings.serverless_mode else 1

        for attempt in range(1, retries + 1):
            try:
                logger.info("Pollinations attempt %d: %s", attempt, prompt[:50])
                r = await self._http.get(url, timeout=timeout, follow_redirects=True)
                size = len(r.content)
                if r.status_code == 200 and size >= _MIN_BYTES:
                    logger.info("Pollinations ok bytes=%d", size)
                    return r.content
                logger.warning(
                    "Pollinations bad response status=%s bytes=%d",
                    r.status_code,
                    size,
                )
            except httpx.TimeoutException:
                logger.warning("Pollinations timeout attempt %d", attempt)
            except Exception as exc:
                logger.error("Pollinations error: %s", exc)
            if attempt < retries:
                await asyncio.sleep(1.5)

        return None

    @property
    def between_delay(self) -> float:
        return self._settings.hf_between_delay
