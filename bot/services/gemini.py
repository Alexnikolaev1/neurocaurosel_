"""Gemini scenario generation."""

from __future__ import annotations

import logging

import httpx

from bot.config import GEMINI_URL, STYLE_PRESETS, Settings
from bot.models import Slide, VisualStyle
from bot.utils import extract_json_array

logger = logging.getLogger("neurocarousel.gemini")


class ScenarioGenerator:
    def __init__(self, settings: Settings, http: httpx.AsyncClient) -> None:
        self._settings = settings
        self._http = http
        self._url = GEMINI_URL.format(key=settings.gemini_key)

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
- Слайды связаны единым визуальным сюжетом или прогрессией.
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
                "maxOutputTokens": 8192,
                "responseMimeType": "application/json",
            },
        }

        logger.info("Gemini scenario for topic: %s (style=%s)", topic[:80], style.value)
        r = await self._http.post(self._url, json=payload)
        r.raise_for_status()

        data = r.json()
        raw_text = data["candidates"][0]["content"]["parts"][0]["text"]
        slides_raw = extract_json_array(raw_text)

        if not isinstance(slides_raw, list):
            raise ValueError("Gemini response is not a JSON array")

        slides = [Slide.from_dict(item) for item in slides_raw]
        slides = [s for s in slides if s.caption and s.image_prompt]

        if len(slides) < count:
            raise ValueError(f"Gemini returned {len(slides)} valid slides, expected {count}")

        return slides[:count]
