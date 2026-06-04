"""Image generation: Pollinations (Vercel) / HF (локально)."""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
import urllib.request

import httpx

from bot.config import HF_URL, POLLINATIONS_URL, Settings
from bot.utils import compress_image

logger = logging.getLogger("neurocarousel.images")

_MIN_BYTES = 2000
_HTTP_ERRORS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.TransportError,
    httpx.NetworkError,
)
_USER_AGENT = "NeuroCarouselBot/1.0"


class ImageGenerator:
    """Свой HTTP-клиент на запрос — не делим пул с Gemini (Vercel EBUSY)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._hf_headers = {"Authorization": f"Bearer {settings.hf_key}"}

    async def generate(self, prompt: str, *, raw: bool = False) -> bytes | None:
        short_prompt = self._shorten_prompt(prompt)

        if self._settings.pollinations_only:
            image = await self._generate_pollinations(short_prompt)
            if not image:
                image = await self._generate_pollinations_urllib(short_prompt)
            return self._finalize(image, raw=raw)

        image = await self._generate_hf(short_prompt)
        if image:
            return self._finalize(image, raw=raw)
        image = await self._generate_pollinations(short_prompt)
        return self._finalize(image, raw=raw)

    def _finalize(self, image: bytes | None, *, raw: bool) -> bytes | None:
        if not image:
            return None
        return image if raw else self._optimize(image)

    def _shorten_prompt(self, prompt: str) -> str:
        p = " ".join(prompt.split())
        limit = 200 if self._settings.serverless_mode else 700
        if len(p) > limit:
            p = p[: limit - 3] + "..."
        return p

    def _optimize(self, data: bytes) -> bytes:
        return compress_image(
            data,
            max_size=self._settings.image_max_size,
            quality=self._settings.image_jpeg_quality,
        )

    async def _http_get(self, url: str, *, timeout: float) -> httpx.Response | None:
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            ) as client:
                return await client.get(url, headers={"User-Agent": _USER_AGENT})
        except _HTTP_ERRORS as exc:
            logger.warning("httpx GET failed: %s", exc)
            return None

    async def _http_post_json(
        self,
        url: str,
        *,
        json: dict,
        headers: dict,
        timeout: float,
    ) -> httpx.Response | None:
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            ) as client:
                return await client.post(url, headers=headers, json=json)
        except _HTTP_ERRORS as exc:
            logger.warning("httpx POST failed: %s", exc)
            return None

    def _fetch_urllib_sync(self, url: str, timeout: float) -> bytes | None:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": _USER_AGENT})
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if len(data) >= _MIN_BYTES:
                    return data
        except Exception as exc:
            logger.warning("urllib GET failed: %s", exc)
        return None

    async def _generate_pollinations_urllib(self, prompt: str) -> bytes | None:
        timeout = int(25 if self._settings.serverless_mode else 60)
        for url in self._pollinations_urls(prompt):
            logger.info("Pollinations urllib: %s", prompt[:40])
            data = await asyncio.to_thread(self._fetch_urllib_sync, url, float(timeout))
            if data:
                logger.info("Pollinations urllib ok bytes=%d", len(data))
                return data
        return None

    async def _generate_hf(self, prompt: str, *, serverless: bool = False) -> bytes | None:
        payload = {
            "inputs": prompt,
            "parameters": {
                "num_inference_steps": 16 if serverless else 28,
                "guidance_scale": 7.0,
                "width": 768,
                "height": 768,
            },
        }
        timeout = 22.0 if serverless else 90.0
        r = await self._http_post_json(
            HF_URL,
            json=payload,
            headers=self._hf_headers,
            timeout=timeout,
        )
        if r and r.status_code == 200 and len(r.content) >= _MIN_BYTES:
            return r.content
        if r:
            logger.warning("HF status=%s bytes=%d", r.status_code, len(r.content))
        return None

    def _pollinations_urls(self, prompt: str) -> list[str]:
        encoded = urllib.parse.quote(prompt, safe="")
        return [
            POLLINATIONS_URL.format(prompt=encoded),
            f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512&nologo=true",
        ]

    async def _generate_pollinations(self, prompt: str) -> bytes | None:
        timeout = 22.0 if self._settings.serverless_mode else 60.0

        for url_idx, url in enumerate(self._pollinations_urls(prompt)):
            for attempt in range(1, 3):
                logger.info("Pollinations httpx url=%d try=%d", url_idx + 1, attempt)
                r = await self._http_get(url, timeout=timeout)
                if r is None:
                    continue
                if r.status_code == 200 and len(r.content) >= _MIN_BYTES:
                    logger.info("Pollinations httpx ok bytes=%d", len(r.content))
                    return r.content
                logger.warning(
                    "Pollinations httpx status=%s bytes=%d",
                    r.status_code,
                    len(r.content),
                )

        return None

    @property
    def between_delay(self) -> float:
        return self._settings.hf_between_delay
