"""Наложение текста слайда на картинку (Pillow)."""

from __future__ import annotations

import io
import logging
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from bot.config import Settings
from bot.models import TextMode

logger = logging.getLogger("neurocarousel.image_overlay")

_ASSETS_DIR = Path(__file__).resolve().parent / "assets" / "fonts"
_FONT_CANDIDATES = (
    _ASSETS_DIR / "NotoSans-Bold.ttf",
    _ASSETS_DIR / "DejaVuSans-Bold.ttf",
    Path("/usr/share/fonts/truetype/noto/NotoSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    Path("/usr/share/fonts/opentype/noto/NotoSans-Bold.ttf"),
)

_CYRILLIC_PROBE = "Абв"

# Читаемые цвета текста на тёмной плашке (по номеру слайда)
SLIDE_TEXT_COLORS: tuple[tuple[int, int, int], ...] = (
    (255, 255, 255),   # белый
    (255, 228, 92),    # золотой
    (110, 210, 255),   # голубой
    (130, 255, 195),   # мятный
    (255, 175, 150),   # коралловый
    (225, 185, 255),   # лавандовый
    (255, 185, 95),    # янтарный
)


class CyrillicFontMissingError(RuntimeError):
    """Нет TTF с кириллицей — текст на слайде невозможен."""


def slide_text_color(slide_number: int) -> tuple[int, int, int]:
    return SLIDE_TEXT_COLORS[(slide_number - 1) % len(SLIDE_TEXT_COLORS)]


@lru_cache(maxsize=12)
def _load_font(size: int) -> ImageFont.FreeTypeFont:
    for path in _FONT_CANDIDATES:
        if not path.is_file():
            continue
        try:
            font = ImageFont.truetype(str(path), size=size)
            font.getbbox(_CYRILLIC_PROBE)
            logger.debug("Overlay font: %s size=%d", path.name, size)
            return font
        except OSError:
            logger.warning("Cannot load font %s", path)
            continue

    logger.error(
        "Cyrillic font missing. Bundled path expected: %s",
        _ASSETS_DIR / "NotoSans-Bold.ttf",
    )
    raise CyrillicFontMissingError(
        "Добавьте NotoSans-Bold.ttf в bot/assets/fonts/ (см. README)"
    )


def _wrap_lines(
    text: str,
    font: ImageFont.FreeTypeFont,
    max_width: int,
) -> list[str]:
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
    return lines[:6]


def _draw_outlined_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[int, int],
    text: str,
    *,
    font: ImageFont.FreeTypeFont,
    fill: tuple[int, int, int],
    stroke_width: int,
) -> None:
    draw.text(
        xy,
        text,
        font=font,
        fill=(*fill, 255),
        stroke_width=stroke_width,
        stroke_fill=(0, 0, 0, 255),
    )


def overlay_slide_text(
    image_data: bytes,
    caption: str,
    *,
    slide_number: int,
    total_slides: int,
) -> bytes:
    """Рисует подпись поверх изображения (нижняя плашка, цвет по слайду)."""
    caption = caption.strip()
    if not caption:
        return image_data

    text_color = slide_text_color(slide_number)

    with Image.open(io.BytesIO(image_data)) as img:
        img = img.convert("RGBA")
        width, height = img.size

        pad_x = max(36, width // 20)
        pad_y = max(36, height // 28)
        font_size = max(44, width // 11)
        font = _load_font(font_size)
        max_text_w = width - 2 * pad_x
        lines = _wrap_lines(caption, font, max_text_w)
        if not lines:
            return image_data

        measure = ImageDraw.Draw(img)
        line_heights = []
        for line in lines:
            box = measure.textbbox((0, 0), line, font=font)
            line_heights.append(box[3] - box[1])

        line_gap = max(10, font_size // 5)
        stroke = max(3, font_size // 16)
        text_block_h = sum(line_heights) + line_gap * (len(lines) - 1)
        bar_h = text_block_h + pad_y * 2
        bar_top = max(0, height - bar_h)

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle((0, bar_top, width, height), fill=(8, 10, 18, 215))

        badge = f"{slide_number}/{total_slides}"
        badge_font = _load_font(max(24, font_size // 2))
        bb = draw.textbbox((0, 0), badge, font=badge_font)
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        bx1 = width - bw - pad_x - 16
        by1 = pad_x
        draw.rounded_rectangle(
            (bx1 - 10, by1 - 6, width - pad_x, by1 + bh + 14),
            radius=10,
            fill=(0, 0, 0, 175),
        )
        _draw_outlined_text(
            draw,
            (bx1, by1 + 4),
            badge,
            font=badge_font,
            fill=text_color,
            stroke_width=max(2, stroke // 2),
        )

        y = bar_top + pad_y
        for line, lh in zip(lines, line_heights):
            _draw_outlined_text(
                draw,
                (pad_x, y),
                line,
                font=font,
                fill=text_color,
                stroke_width=stroke,
            )
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
        except CyrillicFontMissingError:
            logger.error("Skipping overlay: no Cyrillic font in deployment")
        except Exception:
            logger.exception("Text overlay failed, sending image without overlay")

    return compress_image(
        image_data,
        max_size=settings.image_max_size,
        quality=settings.image_jpeg_quality,
    )
