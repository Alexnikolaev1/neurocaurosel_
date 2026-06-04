"""Заглушка слайда, если внешние API картинок недоступны."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from bot.image_overlay import _load_font, slide_text_color


def render_placeholder_slide(
    caption: str,
    *,
    slide_number: int,
    total_slides: int,
    topic: str = "",
) -> bytes:
    """Градиентная заглушка с текстом (всегда отправляется в Telegram)."""
    width, height = 1024, 1024
    img = Image.new("RGB", (width, height), (32, 36, 48))
    draw = ImageDraw.Draw(img)
    for y in range(height):
        shade = int(32 + (y / height) * 40)
        draw.line([(0, y), (width, y)], fill=(shade, shade + 8, shade + 20))

    font_lg = _load_font(42)
    font_sm = _load_font(24)
    color = slide_text_color(slide_number)

    draw.text((48, 48), f"Слайд {slide_number}/{total_slides} · заглушка", font=font_sm, fill=(200, 200, 210))
    if topic:
        short = topic if len(topic) <= 60 else topic[:57] + "…"
        draw.text((48, 90), short, font=font_sm, fill=(160, 165, 180))

    lines = _wrap(caption or "Текст слайда", font_lg, width - 96)
    y = height // 2 - len(lines) * 28
    for line in lines:
        draw.text((48, y), line, font=font_lg, fill=color, stroke_width=2, stroke_fill=(0, 0, 0))
        y += 52

    draw.text(
        (48, height - 120),
        "Настрой POLLINATIONS_API_KEY\nв Vercel → Redeploy",
        font=font_sm,
        fill=(255, 200, 120),
    )

    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _wrap(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    words = text.replace("\n", " ").split()
    lines: list[str] = []
    current = ""
    dummy = Image.new("RGB", (1, 1))
    measure = ImageDraw.Draw(dummy)
    for word in words:
        trial = f"{current} {word}".strip()
        box = measure.textbbox((0, 0), trial, font=font)
        if box[2] - box[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:6]
