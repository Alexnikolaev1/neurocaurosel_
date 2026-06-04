"""Gemini scenario generation with retries and model fallback."""

from __future__ import annotations

import asyncio
import logging

import httpx

from bot.config import STYLE_PRESETS, Settings, gemini_url
from bot.models import Slide, VisualStyle
from bot.utils import extract_json_array

logger = logging.getLogger("neurocarousel.gemini")

_DEPRECATED_MODELS = frozenset({
    "gemini-1.5-flash",
    "gemini-1.5-pro",
    "gemini-pro",
})


class GeminiError(Exception):
    """Base Gemini API error."""


class GeminiRateLimitError(GeminiError):
    """All models exhausted with 429."""


class ScenarioGenerator:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http

    def _models(self) -> list[str]:
        if self._settings.serverless_mode:
            return ["gemini-2.0-flash-lite", "gemini-2.0-flash"]

        seen: set[str] = set()
        result: list[str] = []
        for name in self._settings.gemini_models:
            if name in _DEPRECATED_MODELS:
                continue
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result or ["gemini-2.0-flash", "gemini-2.0-flash-lite"]

    def _retry_wait(self, attempt: int) -> float:
        base = self._settings.gemini_retry_base_delay
        if self._settings.serverless_mode:
            return min(18.0, base * attempt)
        return min(25.0, base * (2 ** (attempt - 1)))

    async def generate(
        self,
        topic: str,
        *,
        language: str,
        style: VisualStyle,
    ) -> list[Slide]:
        style_hint = STYLE_PRESETS[style.value]
        count = self._settings.slides_count

        caption_lang = "русский" if language == "ru" else "английский"
        prompt = f"""
Придумай нейрокарусель из {count} слайдов на тему: «{topic}».
Один связный сюжет от обложки до финала.

caption — на {caption_lang}, конкретно про эту тему (факты, советы, примеры, цифры).
Запрещены общие фразы без содержания: «первый ключевой момент», «разберём глубже»,
«на слуху», «листай карусель», «поделись в комментариях».
В каждом caption явно отрази тему или её часть; до 120 символов; без эмодзи.
image_prompt — на английском, сцена про тему, стиль: {style_hint}, no text.

Верни ТОЛЬКО JSON-массив из {count} объектов:
[{{"slide":1,"caption":"...","image_prompt":"..."}}, ...]
""".strip()

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.8,
                "maxOutputTokens": 3072 if self._settings.serverless_mode else 4096,
                "responseMimeType": "application/json",
            },
        }

        last_status: int | None = None
        models = self._models()
        retries = self._settings.gemini_retry_count
        req_timeout = self._settings.gemini_request_timeout
        saw_429 = False

        for model in models:
            url = gemini_url(model, self._settings.gemini_key)
            model_failed_429 = False

            for attempt in range(1, retries + 1):
                logger.info("Gemini %s attempt %d/%d for: %s", model, attempt, retries, topic[:60])
                try:
                    r = await self._http.post(url, json=payload, timeout=req_timeout)
                    last_status = r.status_code

                    if r.status_code in (404, 400):
                        logger.warning("Gemini %s HTTP %s, skip model", model, r.status_code)
                        break

                    if r.status_code == 429:
                        saw_429 = True
                        model_failed_429 = True
                        last_status = 429
                        if attempt < retries:
                            wait = self._retry_wait(attempt)
                            logger.warning(
                                "Gemini 429 on %s, retry %d/%d in %.1fs",
                                model,
                                attempt,
                                retries,
                                wait,
                            )
                            await asyncio.sleep(wait)
                            continue
                        logger.warning("Gemini 429 on %s — try next model", model)
                        break

                    if r.status_code in (503, 500):
                        wait = self._settings.gemini_retry_base_delay * attempt
                        logger.warning("Gemini %s HTTP %s, wait %.1fs", model, r.status_code, wait)
                        await asyncio.sleep(wait)
                        continue

                    r.raise_for_status()
                    return self._parse_response(r.json(), count)

                except httpx.HTTPStatusError as exc:
                    last_status = exc.response.status_code
                    if exc.response.status_code in (404, 400):
                        break
                    if exc.response.status_code == 429:
                        saw_429 = True
                        model_failed_429 = True
                        if attempt < retries:
                            await asyncio.sleep(self._retry_wait(attempt))
                            continue
                        break
                    logger.error("Gemini %s HTTP %s", model, exc.response.status_code)
                    break
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    logger.warning("Gemini transport on %s attempt %d: %s", model, attempt, exc)
                    if attempt < retries:
                        await asyncio.sleep(self._settings.gemini_retry_base_delay)
                        continue
                    break

            if model_failed_429:
                logger.info("Switching model after 429 on %s", model)
                continue

        if last_status == 429 or saw_429:
            raise GeminiRateLimitError("Gemini rate limit (429)")
        raise GeminiError(f"Gemini failed (last HTTP {last_status})")

    def _parse_response(self, data: dict, count: int) -> list[Slide]:
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        slides_raw = extract_json_array(raw_text)

        if not isinstance(slides_raw, list):
            raise ValueError("Gemini response is not a JSON array")

        slides: list[Slide] = []
        for i, item in enumerate(slides_raw):
            s = Slide.from_dict(item)
            if s.number <= 0:
                s = Slide(number=i + 1, caption=s.caption, image_prompt=s.image_prompt)
            slides.append(s)
        slides = [s for s in slides if s.caption and s.image_prompt]

        if len(slides) < count:
            raise ValueError(f"Gemini returned {len(slides)} valid slides, expected {count}")

        return slides[:count]
