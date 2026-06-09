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

# Нижняя плашка: не больше ~36% высоты кадра; шрифт подбирается вниз, если не влезает.
_MAX_BAR_HEIGHT_RATIO = 0.36
_MAX_TEXT_LINES = 8


def _bottom_inset(height: int) -> int:
    """Зазор между низом плашки и краем кадра + запас под обводку текста."""
    return max(22, height // 32)


def _text_bottom_margin(stroke_width: int) -> int:
    """Доп. запас под обводку и вынос букв (р, у, д) ниже baseline."""
    return stroke_width * 2 + 6

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
    *,
    max_lines: int = _MAX_TEXT_LINES,
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
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        while last and _text_width(last + "…", font) > max_width:
            last = last[:-1]
        lines[-1] = (last + "…") if last else "…"
    return lines


def _text_width(text: str, font: ImageFont.FreeTypeFont) -> int:
    dummy = Image.new("RGB", (1, 1))
    box = ImageDraw.Draw(dummy).textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def _line_metrics(
    lines: list[str],
    font: ImageFont.FreeTypeFont,
    *,
    stroke_width: int = 0,
) -> list[int]:
    measure = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(measure)
    heights: list[int] = []
    for line in lines:
        box = draw.textbbox((0, 0), line, font=font, stroke_width=stroke_width)
        heights.append(box[3] - box[1])
    return heights


def _fit_overlay_layout(
    caption: str,
    *,
    width: int,
    height: int,
) -> tuple[ImageFont.FreeTypeFont, list[str], list[int], int, int, int]:
    """Подбор шрифта и отступов: плашка компактная, текст влезает."""
    pad_x = max(20, width // 26)
    pad_y = max(16, height // 42)
    bottom_gap = _bottom_inset(height)
    max_text_w = width - 2 * pad_x
    max_bar_h = max(int(height * _MAX_BAR_HEIGHT_RATIO), pad_y * 4)

    base_size = max(28, width // 15)
    min_size = max(18, width // 26)

    best: tuple | None = None
    for size in range(base_size, min_size - 1, -2):
        font = _load_font(size)
        stroke = max(2, size // 18)
        lines = _wrap_lines(caption, font, max_text_w)
        if not lines:
            continue
        line_heights = _line_metrics(lines, font, stroke_width=stroke)
        line_gap = max(6, size // 6)
        text_block_h = sum(line_heights) + line_gap * (len(lines) - 1)
        bar_h = text_block_h + pad_y * 2 + _text_bottom_margin(stroke)
        if bar_h <= max_bar_h:
            best = (font, lines, line_heights, line_gap, pad_x, pad_y)
            break

    if best is None:
        font = _load_font(min_size)
        stroke = max(2, min_size // 18)
        lines = _wrap_lines(caption, font, max_text_w)
        line_heights = _line_metrics(lines, font, stroke_width=stroke)
        line_gap = max(5, min_size // 6)
        best = (font, lines, line_heights, line_gap, pad_x, pad_y)

    return best


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

        font, lines, line_heights, line_gap, pad_x, pad_y = _fit_overlay_layout(
            caption,
            width=width,
            height=height,
        )
        if not lines:
            return image_data

        font_size = font.size
        stroke = max(2, font_size // 18)
        bottom_gap = _bottom_inset(height)
        text_block_h = sum(line_heights) + line_gap * (len(lines) - 1)
        bar_h = text_block_h + pad_y * 2 + _text_bottom_margin(stroke)
        bar_bottom = height - bottom_gap
        bar_top = max(0, bar_bottom - bar_h)

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(overlay)
        draw.rectangle((0, bar_top, width, bar_bottom), fill=(8, 10, 18, 200))

        badge = f"{slide_number}/{total_slides}"
        badge_font = _load_font(max(18, font_size // 2))
        bb = draw.textbbox((0, 0), badge, font=badge_font)
        bw, bh = bb[2] - bb[0], bb[3] - bb[1]
        bx1 = width - bw - pad_x - 10
        by1 = max(10, pad_x // 2)
        draw.rounded_rectangle(
            (bx1 - 8, by1 - 4, width - pad_x, by1 + bh + 10),
            radius=8,
            fill=(0, 0, 0, 160),
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
