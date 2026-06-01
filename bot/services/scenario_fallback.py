"""Запасной сценарий без Gemini (при 429 / перегрузке API)."""

from __future__ import annotations

from bot.config import STYLE_PRESETS
from bot.models import Slide, VisualStyle

# Шаблоны подписей: (slide_number, total) -> не используется; фиксированные роли слайдов
_RU_CAPTIONS = [
    "🎯 {topic} — разберём по шагам. Листай карусель 👉",
    "Почему эта тема сейчас на слуху? Коротко о контексте.",
    "Первый ключевой момент, без которого дальше не понять суть.",
    "Второй инсайт — то, что чаще всего упускают.",
    "Третий пункт: практический взгляд на тему.",
    "Разберём глубже — как это работает на практике.",
    "Пример из жизни, который всё ставит на места.",
    "Главные выводы одной строкой — сохрани себе.",
    "Твой ход! Поделись мнением в комментариях 💬",
]

_EN_CAPTIONS = [
    "🎯 {topic} — let's break it down. Swipe 👉",
    "Why this topic matters right now — quick context.",
    "Key point #1 you need before going further.",
    "Insight #2 that most people miss.",
    "Point #3 — the practical angle.",
    "Going deeper: how it works in real life.",
    "A relatable example that ties it together.",
    "Main takeaways in one slide — save this.",
    "Your turn! Share your thoughts below 💬",
]

_IMAGE_SCENES = [
    "eye-catching cover hero image about {topic}, strong visual hook",
    "contextual scene introducing {topic}, atmospheric wide shot",
    "visual metaphor for first key idea about {topic}",
    "second concept illustration about {topic}, distinct composition",
    "third angle on {topic}, dynamic perspective",
    "detailed close-up scene explaining {topic}, rich details",
    "real-world example scene related to {topic}",
    "summary collage mood board about {topic}, cohesive style",
    "inspiring closing image about {topic}, call to action mood",
]


def generate_fallback_scenario(
    topic: str,
    count: int,
    *,
    language: str,
    style: VisualStyle,
) -> list[Slide]:
    """Единый сюжет из шаблонов — 9 связанных слайдов на одну тему."""
    style_hint = STYLE_PRESETS[style.value]
    captions_tpl = _RU_CAPTIONS if language == "ru" else _EN_CAPTIONS
    topic_short = topic.strip()[:120]

    slides: list[Slide] = []
    for i in range(count):
        cap_tpl = captions_tpl[i] if i < len(captions_tpl) else captions_tpl[-1]
        caption = cap_tpl.format(topic=topic_short)
        scene = _IMAGE_SCENES[i] if i < len(_IMAGE_SCENES) else _IMAGE_SCENES[-1]
        image_prompt = (
            f"{scene.format(topic=topic_short)}, {style_hint}, "
            "high quality, no text, no watermark"
        )
        slides.append(Slide(number=i + 1, caption=caption, image_prompt=image_prompt))

    return slides
