"""Image generation: HF Hub / Router / gen.pollinations.ai."""

from __future__ import annotations

import asyncio
import io
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

_MIN_BYTES = 800
_HTTP_ERRORS = (
    httpx.ConnectError,
    httpx.TimeoutException,
    httpx.TransportError,
    httpx.NetworkError,
)
_USER_AGENT = "NeuroCarouselBot/1.0"

# (provider_label, hf_hub_provider or "", model)
_HF_HUB_ATTEMPTS = (
    ("hf-hub:fal-ai", "fal-ai", "black-forest-labs/FLUX.1-schnell"),
    ("hf-hub:hf-inference", "hf-inference", "black-forest-labs/FLUX.1-schnell"),
    ("hf-hub:hf-inference-sdxl", "hf-inference", "stabilityai/stable-diffusion-xl-base-1.0"),
)


def _looks_like_image(data: bytes) -> bool:
    if len(data) < _MIN_BYTES:
        return False
    head = data.lstrip()[:20]
    if head.startswith(b"<!") or head.startswith(b"{"):
        return False
    if data[:2] == b"\xff\xd8":
        return True
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return True
    if data[:4] == b"RIFF" and len(data) > 12 and data[8:12] == b"WEBP":
        return True
    return False


class ImageGenerator:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._hf_headers = {"Authorization": f"Bearer {settings.hf_key}"}
        self.last_trace: str = ""

    async def generate(self, prompt: str, *, raw: bool = False) -> bytes | None:
        short_prompt = self._shorten_prompt(prompt)
        trace: list[str] = []

        if self._settings.pollinations_only:
            chain = (
                self._try_gen_pollinations(short_prompt, trace),
                self._try_legacy_pollinations(short_prompt, trace),
            )
        else:
            chain = (
                self._try_hf_hub(short_prompt, trace),
                self._try_hf_router(short_prompt, trace),
                self._try_gen_pollinations(short_prompt, trace),
                self._try_legacy_pollinations(short_prompt, trace),
            )

        for coro in chain:
            image = await coro
            if image:
                self.last_trace = f"ok:{trace[-1]}"
                logger.info("Image OK %s bytes=%d", self.last_trace, len(image))
                return self._finalize(image, raw=raw)

        self.last_trace = " | ".join(trace) or "no attempts"
        logger.error("IMAGE_ALL_FAILED %s", self.last_trace)
        return None

    def _finalize(self, image: bytes | None, *, raw: bool) -> bytes | None:
        if not image:
            return None
        return image if raw else self._optimize(image)

    def _shorten_prompt(self, prompt: str) -> str:
        p = " ".join(prompt.split())
        limit = 120 if self._settings.serverless_mode else 500
        return p[:limit] if len(p) > limit else p

    def _optimize(self, data: bytes) -> bytes:
        return compress_image(
            data,
            max_size=self._settings.image_max_size,
            quality=self._settings.image_jpeg_quality,
        )

    async def _try_hf_hub(self, prompt: str, trace: list[str]) -> bytes | None:
        if not self._settings.hf_key:
            trace.append("hf-hub:no-key")
            return None
        for label, provider, model in _HF_HUB_ATTEMPTS:
            try:
                data = await asyncio.wait_for(
                    asyncio.to_thread(self._hf_hub_sync, prompt, provider, model),
                    timeout=45.0,
                )
                if data:
                    trace.append(label)
                    return data
                trace.append(f"{label}:empty")
            except asyncio.TimeoutError:
                trace.append(f"{label}:timeout")
            except Exception as exc:
                trace.append(f"{label}:{type(exc).__name__}")
                logger.warning("%s: %s", label, exc)
        return None

    def _hf_hub_sync(self, prompt: str, provider: str, model: str) -> bytes | None:
        from huggingface_hub import InferenceClient

        logger.info("HF hub %s %s: %s", provider, model, prompt[:40])
        client = InferenceClient(api_key=self._settings.hf_key, provider=provider)
        image = client.text_to_image(prompt, model=model)
        buf = io.BytesIO()
        image.convert("RGB").save(buf, format="JPEG", quality=90)
        data = buf.getvalue()
        return data if _looks_like_image(data) else None

    async def _try_hf_router(self, prompt: str, trace: list[str]) -> bytes | None:
        if not self._settings.hf_key:
            trace.append("hf-router:no-key")
            return None
        for model in HF_IMAGE_MODELS:
            label = f"hf-router:{model.split('/')[-1]}"
            url = HF_ROUTER_TEMPLATE.format(model=model)
            r = await self._http_post_json(
                url,
                json={"inputs": prompt},
                headers=self._hf_headers,
                timeout=40.0,
            )
            if r is None:
                trace.append(f"{label}:net")
                continue
            if r.status_code == 200 and _looks_like_image(r.content):
                trace.append(label)
                return r.content
            trace.append(f"{label}:{r.status_code}")
            logger.warning("%s status=%s body=%s", label, r.status_code, r.text[:120])
        return None

    async def _try_gen_pollinations(self, prompt: str, trace: list[str]) -> bytes | None:
        key = self._settings.pollinations_api_key
        if not key:
            trace.append("gen-poll:no-key")
            return None

        encoded = urllib.parse.quote(prompt, safe="")
        base = GEN_POLLINATIONS_TEMPLATE.format(prompt=encoded)
        attempts = [
            (
                "gen-poll:query",
                f"{base}?width=512&height=512&model=flux&key={urllib.parse.quote(key, safe='')}",
                None,
            ),
            (
                "gen-poll:bearer",
                f"{base}?width=512&height=512&model=turbo",
                {"Authorization": f"Bearer {key}"},
            ),
            (
                "gen-poll:query-turbo",
                f"{base}?width=512&height=512&model=turbo&key={urllib.parse.quote(key, safe='')}",
                None,
            ),
        ]
        for label, url, headers in attempts:
            r = await self._http_get(url, timeout=45.0, headers=headers)
            if r and r.status_code == 200 and _looks_like_image(r.content):
                trace.append(label)
                return r.content
            code = r.status_code if r else "net"
            trace.append(f"{label}:{code}")
            if r:
                logger.warning("%s status=%s head=%r", label, r.status_code, r.content[:80])
        return None

    async def _try_legacy_pollinations(self, prompt: str, trace: list[str]) -> bytes | None:
        encoded = urllib.parse.quote(prompt, safe="")
        urls = [
            POLLINATIONS_URL.format(prompt=encoded),
            f"https://image.pollinations.ai/prompt/{encoded}?width=512&height=512",
        ]
        for i, url in enumerate(urls):
            label = f"legacy-poll:{i + 1}"
            r = await self._http_get(url, timeout=22.0)
            if r and r.status_code == 200 and _looks_like_image(r.content):
                trace.append(label)
                return r.content
            code = r.status_code if r else "net"
            trace.append(f"{label}:{code}")
        return None

    async def _http_get(
        self,
        url: str,
        *,
        timeout: float,
        headers: dict | None = None,
    ) -> httpx.Response | None:
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
            logger.warning("GET fail: %s", exc)
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
            logger.warning("POST fail: %s", exc)
            return None

    @property
    def between_delay(self) -> float:
        return self._settings.hf_between_delay
