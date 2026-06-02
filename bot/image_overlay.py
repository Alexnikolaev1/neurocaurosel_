"""Наложение текста слайда на картинку (Pillow)."""

from __future__ import annotations

import io
import logging
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from bot.config import Settings
from bot.models import TextMode

logger = logging.getLogger("neurocarousel.image_overlay")

_ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT_CANDIDATES = (
    _ASSETS_DIR / "DejaVuSans-Bold.ttf",
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                continue
    logger.warning("Cyrillic font not found, using default (Latin only)")
    return ImageFont.load_default()


def _wrap_lines(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = text.replace("\n", " ").split()
    if not words:
        return []

    lines: list[str] = []
    current = ""
    dummy = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy)

    for word in words:
        trial = f"{current} {word}".strip()
        box = draw.textbbox((0, 0), trial, font=font)
        if box[2] - box[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines[:8]


def overlay_slide_text(
    image_data: bytes,
    caption: str,
    *,
    slide_number: int,
    total_slides: int,
) -> bytes:
    """Рисует подпись поверх изображения (нижняя плашка)."""
    caption = caption.strip()
    if not caption:
        return image_data

    with Image.open(io.BytesIO(image_data)) as img:
        img = img.convert("RGBA")
        width, height = img.size

        pad_x = max(24, width // 28)
        font_size = max(22, width // 22)
        font = _load_font(font_size)
        max_text_w = width - 2 * pad_x
        lines = _wrap_lines(caption, font, max_text_w)
        if not lines:
            return image_data

        dummy = ImageDraw.Draw(img)
        line_heights = [
            dummy.textbbox((0, 0), line, font=font)[3]
            - dummy.textbbox((0, 0), line, font=font)[1]
            for line in lines
        ]
        line_gap = max(6, font_size // 8)
        block_h = sum(line_heights) + line_gap * (len(lines) - 1) + pad_x * 2
        bar_top = height - block_h - pad_x

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle(
            (0, bar_top, width, height),
            fill=(0, 0, 0, 170),
        )

        # Номер слайда в углу
        badge = f"{slide_number}/{total_slides}"
        badge_font = _load_font(max(16, font_size // 2))
        bb = draw.textbbox((0, 0), badge, font=badge_font)
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        draw.rectangle(
            (width - bw - pad_x - 12, pad_x, width - pad_x, pad_x + bh + 12),
            fill=(0, 0, 0, 140),
        )
        draw.text(
            (width - bw - pad_x - 6, pad_x + 6),
            badge,
            font=badge_font,
            fill=(255, 255, 255, 230),
        )

        y = bar_top + pad_x
        for line, lh in zip(lines, line_heights):
            draw.text((pad_x, y), line, font=font, fill=(255, 255, 255, 255))
            y += lh + line_gap

        composed = Image.alpha_composite(img, overlay).convert("RGB")
        buf = io.BytesIO()
        composed.save(buf, format="JPEG", quality=92, optimize=True)
        return buf.getvalue()


def prepare_slide_image(
    image_data: bytes,
    caption: str,
    *,
    slide_number: int,
    total_slides: int,
    text_mode: TextMode,
    settings: Settings,
) -> bytes:
    """Сжатие + опционально текст на картинке."""
    from bot.utils import compress_image

    if text_mode == TextMode.TEXT_ON_IMAGE:
        try:
            image_data = overlay_slide_text(
                image_data,
                caption,
                slide_number=slide_number,
                total_slides=total_slides,
            )
        except Exception:
            logger.exception("Text overlay failed, sending image without overlay")

    return compress_image(
        image_data,
        max_size=settings.image_max_size,
        quality=settings.image_jpeg_quality,
    )
