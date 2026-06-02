"""Telegram inline keyboards."""

from __future__ import annotations

from bot.config import STYLE_PRESETS
from bot.models import TextMode, VisualStyle

EXAMPLE_TOPICS = [
    "Утренние ритуалы успешных людей",
    "7 принципов стоицизма",
    "Путешествие по Японии: must-see",
    "Эволюция смартфонов за 20 лет",
]

_STYLE_LABELS = {
    VisualStyle.CINEMATIC: "🎬 Кино",
    VisualStyle.MINIMAL: "⬜ Минимал",
    VisualStyle.ANIME: "🌸 Аниме",
    VisualStyle.RETRO: "📼 Ретро",
    VisualStyle.PHOTO: "📷 Фото",
}


_TEXT_MODE_LABELS = {
    TextMode.CAPTION_ONLY: "💬 Текст в подписи",
    TextMode.TEXT_ON_IMAGE: "🖼 Текст на слайде",
}


def text_mode_keyboard(current: TextMode | None = None) -> dict:
    rows = []
    for mode in TextMode:
        label = _TEXT_MODE_LABELS[mode]
        if mode == current:
            label = f"• {label} •"
        rows.append([{"text": label, "callback_data": f"textmode:{mode.value}"}])
    return {"inline_keyboard": rows}


def text_mode_label(mode: TextMode) -> str:
    return _TEXT_MODE_LABELS.get(mode, mode.value)


def style_keyboard(current: VisualStyle | None = None) -> dict:
    rows = []
    row: list[dict] = []
    for style in VisualStyle:
        label = _STYLE_LABELS[style]
        if style == current:
            label = f"• {label} •"
        row.append({"text": label, "callback_data": f"style:{style.value}"})
        if len(row) == 2:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    return {"inline_keyboard": rows}


def examples_keyboard() -> dict:
    rows = [
        [{"text": topic[:40] + ("…" if len(topic) > 40 else ""), "callback_data": f"topic:{i}"}]
        for i, topic in enumerate(EXAMPLE_TOPICS)
    ]
    return {"inline_keyboard": rows}


def retry_keyboard() -> dict:
    return {
        "inline_keyboard": [[{"text": "🔄 Попробовать снова", "callback_data": "retry:last"}]]
    }


def draw_batch_keyboard(slide_from: int, slide_to: int) -> dict:
    return {
        "inline_keyboard": [
            [{
                "text": f"🖼 Нарисовать слайды {slide_from}–{slide_to}",
                "callback_data": "carousel_draw",
            }],
        ]
    }


def style_label(style: VisualStyle) -> str:
    return _STYLE_LABELS.get(style, style.value)
