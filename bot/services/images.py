"""Image generation: HF Router (Vercel) / Pollinations (опционально)."""

from __future__ import annotations

import asyncio
import logging
import urllib.parse
import urllib.request

import httpx

from bot.config import (
    GEN_POLLINATIONS_TEMPLATE,
    HF_IMAGE_MODELS,
    HF_ROUTER_TEMPLATE,
    HF_URL,
    POLLINATIONS_URL,
    Settings,
)
from bot.utils import compress_image

logger = logging.getLogger("neurocarousel.images")

_MIN_BYTES = 1500
_HTTP_ERRORS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.TransportError,
    httpx.NetworkError,
)
_USER_AGENT = "NeuroCarouselBot/1.0"


def _looks_like_image(data: bytes) -> bool:
    if len(data) < _MIN_BYTES:
        return False
    if data[:2] == b"\xff\xd8":
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:4] == b"RIFF" and len(data) > 12 and data[8:12] == b"WEBP":
        return True
    return False


class ImageGenerator:
    """Отдельный HTTP-клиент на запрос (не делим с Gemini)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._hf_headers = {"Authorization": f"Bearer {settings.hf_key}"}

    async def generate(self, prompt: str, *, raw: bool = False) -> bytes | None:
        short_prompt = self._shorten_prompt(prompt)

        if self._settings.pollinations_only:
            image = await self._try_pollinations(short_prompt)
            return self._finalize(image, raw=raw)

        image = await self._generate_serverless_chain(short_prompt)
        if image:
            return self._finalize(image, raw=raw)

        image = await self._generate_hf_legacy(short_prompt)
        if image:
            return self._finalize(image, raw=raw)

        image = await self._try_pollinations(short_prompt)
        return self._finalize(image, raw=raw)

    async def _generate_serverless_chain(self, prompt: str) -> bytes | None:
        if not self._settings.serverless_mode:
            return None

        for model in HF_IMAGE_MODELS:
            image = await self._generate_hf_router(prompt, model)
            if image:
                return image

        if self._settings.pollinations_api_key:
            image = await self._generate_gen_pollinations(prompt)
            if image:
                return image

        return None

    async def _try_pollinations(self, prompt: str) -> bytes | None:
        image = await self._generate_pollinations_legacy(prompt)
        if image:
            return image
        return await self._generate_pollinations_urllib(prompt)

    def _finalize(self, image: bytes | None, *, raw: bool) -> bytes | None:
        if not image:
            return None
        return image if raw else self._optimize(image)

    def _shorten_prompt(self, prompt: str) -> str:
        p = " ".join(prompt.split())
        limit = 180 if self._settings.serverless_mode else 700
        if len(p) > limit:
            p = p[: limit - 3] + "..."
        return p

    def _optimize(self, data: bytes) -> bytes:
        return compress_image(
            data,
            max_size=self._settings.image_max_size,
            quality=self._settings.image_jpeg_quality,
        )

    async def _http_get(self, url: str, *, timeout: float, headers: dict | None = None) -> httpx.Response | None:
        hdrs = {"User-Agent": _USER_AGENT}
        if headers:
            hdrs.update(headers)
        try:
            async with httpx.AsyncClient(
                timeout=timeout,
                follow_redirects=True,
                limits=httpx.Limits(max_connections=1, max_keepalive_connections=0),
            ) as client:
                return await client.get(url, headers=hdrs)
        except _HTTP_ERRORS as exc:
            logger.warning("httpx GET %s: %s", url[:60], exc)
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
            logger.warning("httpx POST %s: %s", url[:60], exc)
            return None

    def _fetch_urllib_sync(self, url: str, timeout: float, headers: dict | None = None) -> bytes | None:
        try:
            hdrs = {"User-Agent": _USER_AGENT}
            if headers:
                hdrs.update(headers)
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                data = resp.read()
                if _looks_like_image(data):
                    return data
                logger.warning("urllib not image bytes=%d head=%r", len(data), data[:80])
        except Exception as exc:
            logger.warning("urllib GET failed: %s", exc)
        return None

    async def _generate_hf_router(self, prompt: str, model: str) -> bytes | None:
        url = HF_ROUTER_TEMPLATE.format(model=model)
        payload = {"inputs": prompt}
        timeout = 42.0 if self._settings.serverless_mode else 90.0

        logger.info("HF router %s: %s", model, prompt[:50])
        r = await self._http_post_json(
            url,
            json=payload,
            headers=self._hf_headers,
            timeout=timeout,
        )
        if r is None:
            return None
        if r.status_code == 200 and _looks_like_image(r.content):
            logger.info("HF router ok model=%s bytes=%d", model, len(r.content))
            return r.content

        logger.warning(
            "HF router fail model=%s status=%s bytes=%d body=%s",
            model,
            r.status_code,
            len(r.content),
            r.text[:200],
        )
        return None

    async def _generate_hf_legacy(self, prompt: str) -> bytes | None:
        if self._settings.serverless_mode:
            return None
        payload = {
            "inputs": prompt,
            "parameters": {
                "num_inference_steps": 28,
                "guidance_scale": 7.5,
                "width": 1024,
                "height": 1024,
            },
        }
        r = await self._http_post_json(
            HF_URL,
            json=payload,
            headers=self._hf_headers,
            timeout=90.0,
        )
        if r and r.status_code == 200 and _looks_like_image(r.content):
            return r.content
        return None

    async def _generate_gen_pollinations(self, prompt: str) -> bytes | None:
        key = self._settings.pollinations_api_key
        if not key:
            return None
        encoded = urllib.parse.quote(prompt, safe="")
        url = (
            f"{GEN_POLLINATIONS_TEMPLATE.format(prompt=encoded)}"
            f"?width=512&height=512&model=flux&key={urllib.parse.quote(key, safe='')}"
        )
        logger.info("gen.pollinations.ai: %s", prompt[:40])
        r = await self._http_get(url, timeout=40.0)
        if r and r.status_code == 200 and _looks_like_image(r.content):
            logger.info("gen.pollinations ok bytes=%d", len(r.content))
            return r.content
        if r:
            logger.warning("gen.pollinations status=%s bytes=%d", r.status_code, len(r.content))
        return None

    def _legacy_pollinations_urls(self, prompt: str) -> list[str]:
        encoded = urllib.parse.quote(prompt, safe="")
        return [
            POLLINATIONS_URL.format(prompt=encoded),
            f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512",
        ]

    async def _generate_pollinations_legacy(self, prompt: str) -> bytes | None:
        timeout = 25.0
        for url in self._legacy_pollinations_urls(prompt):
            r = await self._http_get(url, timeout=timeout)
            if r and r.status_code == 200 and _looks_like_image(r.content):
                logger.info("legacy pollinations ok bytes=%d", len(r.content))
                return r.content
            if r:
                logger.warning("legacy pollinations status=%s bytes=%d", r.status_code, len(r.content))
        return None

    async def _generate_pollinations_urllib(self, prompt: str) -> bytes | None:
        timeout = 25.0
        for url in self._legacy_pollinations_urls(prompt):
            data = await asyncio.to_thread(self._fetch_urllib_sync, url, timeout)
            if data:
                logger.info("legacy pollinations urllib ok bytes=%d", len(data))
                return data
        return None

    @property
    def between_delay(self) -> float:
        return self._settings.hf_between_delay
