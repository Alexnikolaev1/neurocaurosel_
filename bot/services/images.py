"""Image generation: Hugging Face SDXL + Pollinations fallback."""

from __future__ import annotations

import asyncio
import logging
import urllib.parse

import httpx

from bot.config import HF_URL, POLLINATIONS_URL, Settings
from bot.utils import compress_image

logger = logging.getLogger("neurocarousel.images")


class ImageGenerator:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http
        self._headers = {"Authorization": f"Bearer {settings.hf_key}"}

    async def generate(self, prompt: str) -> bytes | None:
        if self._settings.pollinations_only:
            image = await self._generate_pollinations(prompt)
            return self._optimize(image) if image else None

        image = await self._generate_hf(prompt)
        if image:
            return self._optimize(image)
        logger.warning("HF failed, trying Pollinations fallback")
        image = await self._generate_pollinations(prompt)
        return self._optimize(image) if image else None

    def _optimize(self, data: bytes) -> bytes:
        return compress_image(
            data,
            max_size=self._settings.image_max_size,
            quality=self._settings.image_jpeg_quality,
        )

    async def _generate_hf(self, prompt: str) -> bytes | None:
        payload = {
            "inputs": prompt,
            "parameters": {
                "num_inference_steps": 28,
                "guidance_scale": 7.5,
                "width": 1024,
                "height": 1024,
            },
        }

        for attempt in range(1, self._settings.hf_retry_count + 1):
            try:
                logger.info("HF attempt %d: %s", attempt, prompt[:60])
                r = await self._http.post(
                    HF_URL,
                    headers=self._headers,
                    json=payload,
                    timeout=90,
                )

                if r.status_code == 200 and len(r.content) > 1000:
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
                await asyncio.sleep(self._settings.hf_retry_delay)

        return None

    async def _generate_pollinations(self, prompt: str) -> bytes | None:
        encoded = urllib.parse.quote(prompt)
        url = POLLINATIONS_URL.format(prompt=encoded)
        try:
            logger.info("Pollinations fallback: %s", prompt[:60])
            r = await self._http.get(url, timeout=60, follow_redirects=True)
            if r.status_code == 200 and len(r.content) > 1000:
                return r.content
        except Exception as exc:
            logger.error("Pollinations error: %s", exc)
        return None

    @property
    def between_delay(self) -> float:
        return self._settings.hf_between_delay
