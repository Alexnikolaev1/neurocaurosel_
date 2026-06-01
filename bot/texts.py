"""User-facing copy and message templates."""

from __future__ import annotations

from bot.config import STYLE_PRESETS

WELCOME_TEXT = """
👋 Привет! Я <b>NeuroCarousel</b> — бот, который превращает любую идею в профессиональную карусель из 10 картинок.

<b>Как использовать:</b>
1. Выбери стиль картинок кнопками ниже (или оставь по умолчанию)
2. Напиши тему одним сообщением

<b>Примеры тем:</b>
• <i>Утренние ритуалы успешных людей</i>
• <i>Эволюция смартфонов за 20 лет</i>
• <i>7 принципов стоицизма</i>

Я придумаю сценарий на 9 слайдов, потом нарисую карусель порциями по 3 — кнопкой «Нарисовать» 🎨
""".strip()

HELP_TEXT = """
<b>📖 Справка NeuroCarousel</b>

<b>Команды:</b>
/start — приветствие и выбор стиля
/help — эта справка
/style — текущий визуальный стиль

<b>Как создать карусель:</b>
Просто отправь тему текстом. Бот сам:
1. Сгенерирует сценарий из 10 слайдов (Gemini)
2. Нарисует картинки (Stable Diffusion XL)
3. Отправит медиагруппу в Telegram

<b>Стили:</b>
{styles}

<b>Ограничения:</b>
• Тема: 3–500 символов, без ссылок
• Генерация занимает 1–3 минуты
• Не отправляй новую тему, пока идёт генерация
""".strip()


def help_text() -> str:
    styles = "\n".join(f"• <b>{name}</b> — {desc[:60]}…" for name, desc in STYLE_PRESETS.items())
    return HELP_TEXT.format(styles=styles)


def style_selected(style_label: str) -> str:
    return f"✅ Стиль: <b>{style_label}</b>\n\nТеперь напиши тему для карусели 👇"


def style_current(style_label: str) -> str:
    return f"🎨 Текущий стиль: <b>{style_label}</b>\n\nСменить можно кнопками ниже или в /start"


def invalid_topic_link() -> str:
    return (
        "🔗 Похоже, ты прислал ссылку. Напиши <b>тему</b> для карусели — "
        "одним предложением или несколькими словами.\n\n"
        "Например: <i>Как научиться рисовать с нуля</i>"
    )


def invalid_topic_length(min_len: int, max_len: int) -> str:
    return (
        f"✏️ Тема должна быть от {min_len} до {max_len} символов.\n"
        "Попробуй короче или чуть подробнее."
    )


def job_in_progress() -> str:
    return (
        "⏳ У тебя уже идёт генерация карусели.\n"
        "Подожди завершения — обычно это 1–3 минуты."
    )


def scenario_progress() -> str:
    return "🎨 Генерирую сценарий..."


def image_progress(current: int, total: int) -> str:
    filled = "▓" * current
    empty = "░" * (total - current)
    pct = int(current / total * 100) if total else 0
    return f"🖼 Рисую слайд <b>{current}/{total}</b>...\n{filled}{empty} {pct}%"


def sending_carousel() -> str:
    return "📤 Отправляю карусель..."


def scenario_error() -> str:
    return "😔 Не удалось придумать сценарий. Попробуй переформулировать тему."


def scenario_timeout() -> str:
    return (
        "⏱ Сценарий не успел сгенерироваться за лимит сервера.\n"
        "Попробуй тему короче или повтори через минуту."
    )


def scenario_ready(total: int, topic: str) -> str:
    short = topic if len(topic) <= 80 else topic[:77] + "…"
    return (
        f"✅ Сценарий на <b>{total}</b> слайдов готов!\n"
        f"Тема: <i>{short}</i>\n\n"
        "Нажми кнопку ниже — нарисую первую порцию (3 картинки)."
    )


def draw_batch_prompt(slide_from: int, slide_to: int) -> str:
    return f"Готов нарисовать слайды <b>{slide_from}–{slide_to}</b> 👇"


def scenario_rate_limit() -> str:
    return (
        "⏳ Gemini временно перегружен (лимит запросов).\n\n"
        "Подожди 1–2 минуты и отправь тему ещё раз — не жми несколько раз подряд.\n\n"
        "Если повторяется: проверь ключ на <a href=\"https://aistudio.google.com/apikey\">"
        "aistudio.google.com</a> (формат <code>AIza...</code>)."
    )


def images_error() -> str:
    return "😔 Ошибка при генерации изображений. Попробуй позже."


def send_error() -> str:
    return "😔 Не удалось отправить карусель. Попробуй позже."


def no_images_generated() -> str:
    return (
        "😔 Не удалось сгенерировать ни одного изображения.\n"
        "Попробуй другую тему или повтори запрос чуть позже."
    )


def partial_failure(failed: list[str]) -> str:
    items = "\n".join(f"• {c}" for c in failed)
    return f"⚠️ Некоторые слайды не удалось нарисовать:\n{items}\n\nМожешь отправить новую тему."


def success() -> str:
    return (
        "✅ Твоя нейрокарусель готова!\n\n"
        "Хочешь ещё одну? Напиши новую тему или выбери пример 👇"
    )


def partial_success(sent: int, total: int) -> str:
    return (
        f"⚠️ Отправлено {sent} из {total} слайдов (лимит времени сервера).\n\n"
        "Можешь отправить тему ещё раз для полной карусели."
    )


def timeout_error(slides: int) -> str:
    return (
        f"⏱ Не успел закончить за лимит Vercel (~60 сек).\n\n"
        f"На бесплатном тарифе ставлю {slides} слайдов и быстрые картинки.\n"
        "Попробуй ещё раз одной темой (без повторных нажатий)."
    )


def serverless_mode_hint() -> str:
    return "☁️ 9 слайдов · 3 порции по 3 картинки · один сценарий."


def batch_progress(
    *,
    batch_num: int,
    total_batches: int,
    slide_from: int,
    slide_to: int,
    total_slides: int,
) -> str:
    return (
        f"🖼 Порция <b>{batch_num}/{total_batches}</b> "
        f"(слайды {slide_from}–{slide_to} из {total_slides})..."
    )


def batch_pause(
    *,
    done_through: int,
    total: int,
    next_from: int,
    next_to: int,
) -> str:
    return (
        f"✅ Готово слайдов 1–{done_through} из {total}.\n"
        f"Осталось: {next_from}–{next_to} (тот же сценарий)."
    )


def batch_continue_prompt(slide_from: int, slide_to: int) -> str:
    return f"Нажми кнопку — дорисую слайды <b>{slide_from}–{slide_to}</b> 👇"


def batch_images_failed(range_label: str) -> str:
    return f"😔 Не удалось нарисовать порцию ({range_label}). Попробуй «Продолжить» или новую тему."


def success_batches(total: int) -> str:
    return (
        f"✅ Карусель из {total} слайдов готова!\n\n"
        "Новая тема — просто напиши текст 👇"
    )
