"""Gemini scenario generation with retries and model fallback."""

from __future__ import annotations

import asyncio
import logging

import httpx

from bot.config import STYLE_PRESETS, Settings, gemini_url
from bot.models import Slide, VisualStyle
from bot.utils import extract_json_array

logger = logging.getLogger("neurocarousel.gemini")


class GeminiError(Exception):
    """Base Gemini API error."""


class GeminiRateLimitError(GeminiError):
    """All models exhausted with 429."""


class ScenarioGenerator:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http

    async def generate(
        self,
        topic: str,
        *,
        language: str,
        style: VisualStyle,
    ) -> list[Slide]:
        style_hint = STYLE_PRESETS[style.value]
        count = self._settings.slides_count

        prompt = f"""
Ты — креативный директор соцсетей. Придумай нейрокарусель из {count} слайдов на тему: «{topic}».

Требования:
- Все {count} слайдов — ОДИН общий сюжет (не начинай тему заново на середине).
- Слайды связаны единой прогрессией от обложки к финалу.
- caption — живая, вовлекающая подпись на языке темы ({language}). 1–3 предложения, без хэштегов.
- image_prompt — детальный промт для Stable Diffusion XL на АНГЛИЙСКОМ. Стиль: {style_hint}. Без имён реальных людей и брендов.
- Первый слайд — яркая обложка (hook), последний — вывод или призыв к действию.
- Каждый image_prompt описывает уникальную сцену, но в единой стилистике.

Верни ТОЛЬКО валидный JSON-массив из ровно {count} объектов:
[
  {{"slide": 1, "caption": "...", "image_prompt": "..."}},
  ...
  {{"slide": {count}, "caption": "...", "image_prompt": "..."}}
]
""".strip()

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": 0.85,
                "maxOutputTokens": 4096,
                "responseMimeType": "application/json",
            },
        }

        last_status: int | None = None
        models = self._settings.gemini_models

        for model in models:
            url = gemini_url(model, self._settings.gemini_key)
            for attempt in range(1, self._settings.gemini_retry_count + 1):
                logger.info(
                    "Gemini %s attempt %d for: %s",
                    model,
                    attempt,
                    topic[:60],
                )
                try:
                    r = await self._http.post(url, json=payload)
                    last_status = r.status_code

                    if r.status_code == 429:
                        wait = self._settings.gemini_retry_base_delay * (2 ** (attempt - 1))
                        logger.warning("Gemini 429 on %s, wait %.1fs", model, wait)
                        await asyncio.sleep(wait)
                        continue

                    if r.status_code in (503, 500):
                        wait = self._settings.gemini_retry_base_delay * attempt
                        logger.warning("Gemini %s on %s, wait %.1fs", r.status_code, model, wait)
                        await asyncio.sleep(wait)
                        continue

                    r.raise_for_status()
                    return self._parse_response(r.json(), count)

                except httpx.HTTPStatusError as exc:
                    last_status = exc.response.status_code
                    if exc.response.status_code == 429:
                        wait = self._settings.gemini_retry_base_delay * (2 ** (attempt - 1))
                        await asyncio.sleep(wait)
                        continue
                    logger.error(
                        "Gemini %s HTTP %s: %s",
                        model,
                        exc.response.status_code,
                        exc.response.text[:300],
                    )
                    break
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    logger.warning("Gemini transport error on %s: %s", model, exc)
                    await asyncio.sleep(self._settings.gemini_retry_base_delay * attempt)

        if last_status == 429:
            raise GeminiRateLimitError("Gemini rate limit (429) on all models")
        raise GeminiError(f"Gemini failed (last HTTP {last_status})")

    def _parse_response(self, data: dict, count: int) -> list[Slide]:
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        slides_raw = extract_json_array(raw_text)

        if not isinstance(slides_raw, list):
            raise ValueError("Gemini response is not a JSON array")

        slides = [Slide.from_dict(item) for item in slides_raw]
        slides = [s for s in slides if s.caption and s.image_prompt]

        if len(slides) < count:
            raise ValueError(f"Gemini returned {len(slides)} valid slides, expected {count}")

        return slides[:count]
