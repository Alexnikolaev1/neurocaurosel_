"""Gemini scenario generation with retries and model fallback."""

from __future__ import annotations

import asyncio
import logging

import httpx

from bot.config import STYLE_PRESETS, Settings, gemini_url
from bot.models import Slide, VisualStyle
from bot.utils import extract_json_array

logger = logging.getLogger("neurocarousel.gemini")

# Модели, снятые с API — пропускаем даже если указаны в GEMINI_MODELS
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
            # На Vercel — одна быстрая модель, без перебора
            return ["gemini-2.0-flash-lite"]

        seen: set[str] = set()
        result: list[str] = []
        for name in self._settings.gemini_models:
            if name in _DEPRECATED_MODELS:
                logger.warning("Skipping deprecated Gemini model: %s", name)
                continue
            if name not in seen:
                seen.add(name)
                result.append(name)
        return result or ["gemini-2.0-flash", "gemini-2.0-flash-lite"]

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
                "temperature": 0.8,
                "maxOutputTokens": 3072 if self._settings.serverless_mode else 4096,
                "responseMimeType": "application/json",
            },
        }

        last_status: int | None = None
        models = self._models()

        for model in models:
            url = gemini_url(model, self._settings.gemini_key)
            for attempt in range(1, self._settings.gemini_retry_count + 1):
                logger.info("Gemini %s attempt %d for: %s", model, attempt, topic[:60])
                try:
                    req_timeout = 40.0 if self._settings.serverless_mode else 60.0
                    r = await self._http.post(url, json=payload, timeout=req_timeout)
                    last_status = r.status_code

                    # Модель не существует — сразу следующая, без ретраев
                    if r.status_code in (404, 400):
                        logger.warning(
                            "Gemini %s HTTP %s, skip model: %s",
                            model,
                            r.status_code,
                            r.text[:200],
                        )
                        break

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
                    if exc.response.status_code in (404, 400):
                        logger.warning("Gemini %s HTTP %s, skip", model, last_status)
                        break
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
