"""Telegram inline keyboards."""

from __future__ import annotations

from bot.config import STYLE_PRESETS
from bot.models import VisualStyle

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


def style_label(style: VisualStyle) -> str:
    return _STYLE_LABELS.get(style, style.value)
