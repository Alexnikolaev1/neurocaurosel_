"""User-facing copy and message templates."""

from __future__ import annotations

from bot.config import STYLE_PRESETS

def welcome_text(style_label: str, text_mode_label: str) -> str:
    return f"""
👋 Привет! Я <b>NeuroCarousel</b> — бот, который превращает идею в карусель из картинок.

<b>Как использовать:</b>
1. Стиль: <b>{style_label}</b> (кнопки ниже)
2. Текст: <b>{text_mode_label}</b> (команда /text)
3. Напиши тему одним сообщением

<b>Режимы текста:</b>
• <i>В подписи</i> — текст под фото в Telegram (как раньше)
• <i>На слайде</i> — текст рисуется на картинке (Pillow)

Сценарий на 7 слайдов · по 1 картинке, кнопка «Нарисовать» 🎨
""".strip()

HELP_TEXT = """
<b>📖 Справка NeuroCarousel</b>

<b>Команды:</b>
/start — приветствие, стиль и режим текста
/help — эта справка
/style — визуальный стиль картинок
/text — где показывать текст слайда (подпись или на картинке)

<b>Как создать карусель:</b>
Просто отправь тему текстом. Бот сам:
1. Сгенерирует сценарий из 7 слайдов (Gemini)
2. Нарисует картинки по одной (меньше нагрузка на сервер)
3. Отправит каждый слайд в Telegram

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


def text_mode_selected(mode_label: str) -> str:
    return (
        f"✅ Режим текста: <b>{mode_label}</b>\n\n"
        "Теперь напиши тему для карусели 👇"
    )


def text_mode_current(mode_label: str) -> str:
    return (
        f"📝 Текст слайдов: <b>{mode_label}</b>\n\n"
        "• <b>В подписи</b> — полный текст под фото в Telegram\n"
        "• <b>На слайде</b> — текст на картинке, подпись короткая"
    )


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


def _batch_info(total: int, batch_size: int) -> str:
    if batch_size == 1:
        return f"{total} шагов · по 1 картинке"
    batches = (total + batch_size - 1) // batch_size
    return f"{batches} порции по {batch_size}"


def scenario_ready_template(total: int, topic: str, batch_size: int = 1) -> str:
    """Шаблонный сценарий (без вызова Gemini на Vercel)."""
    return scenario_ready(total, topic, batch_size)


def scenario_ready_fallback(total: int, topic: str, batch_size: int = 1) -> str:
    return scenario_ready_template(total, topic, batch_size)


def scenario_ready(total: int, topic: str, batch_size: int = 1) -> str:
    short = topic if len(topic) <= 80 else topic[:77] + "…"
    if batch_size == 1:
        action = f"Нажми кнопку — нарисую <b>слайд 1</b> ({_batch_info(total, batch_size)})."
    else:
        end = min(batch_size, total)
        action = (
            f"Нажми кнопку — нарисую слайды 1–{end} "
            f"({_batch_info(total, batch_size)})."
        )
    return (
        f"✅ Сценарий на <b>{total}</b> слайдов готов!\n"
        f"Тема: <i>{short}</i>\n\n"
        f"{action}"
    )


def draw_batch_prompt(slide_from: int, slide_to: int) -> str:
    if slide_from == slide_to:
        return f"Готов нарисовать слайд <b>{slide_from}</b> 👇"
    return f"Готов нарисовать слайды <b>{slide_from}–{slide_to}</b> 👇"


def draw_hint_continue_text() -> str:
    return "Или напиши: <b>далее</b>"


def session_not_found() -> str:
    return (
        "❌ Сессия карусели не найдена (сервер перезапустился).\n"
        "Отправь <b>новую тему</b> — сценарий создастся заново."
    )


def draw_timeout_continue(done: int, total: int) -> str:
    return (
        f"⏱ Лимит времени сервера. Готово <b>{done}/{total}</b> слайдов.\n"
        "Нажми кнопку ещё раз или напиши <b>далее</b> — продолжу тот же сценарий."
    )


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
    return "☁️ 7 слайдов · по 1 картинке · один сценарий."


def batch_progress(
    *,
    batch_num: int,
    total_batches: int,
    slide_from: int,
    slide_to: int,
    total_slides: int,
) -> str:
    if slide_from == slide_to:
        return f"🖼 Рисую слайд <b>{slide_from}/{total_slides}</b>..."
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
    if next_from == next_to:
        return (
            f"✅ Готов слайд <b>{done_through}</b> из {total}.\n"
            f"Далее: слайд <b>{next_from}</b> (тот же сценарий)."
        )
    return (
        f"✅ Готово слайдов 1–{done_through} из {total}.\n"
        f"Осталось: {next_from}–{next_to} (тот же сценарий)."
    )


def batch_continue_prompt(slide_from: int, slide_to: int) -> str:
    if slide_from == slide_to:
        return f"Нажми кнопку — дорисую слайд <b>{slide_from}</b> 👇"
    return f"Нажми кнопку — дорисую слайды <b>{slide_from}–{slide_to}</b> 👇"


def placeholder_hint() -> str:
    return (
        "⚠️ Это <b>заглушка</b> (API картинок не отвечает).\n"
        "Открой в браузере: <code>https://neurocaurosel.vercel.app/api/bot</code> — "
        "должно быть <code>\"build\": \"v7-placeholder\"</code> и "
        "<code>\"pollinations_key_loaded\": true</code>.\n"
        "Иначе добавь <b>POLLINATIONS_API_KEY</b> в Vercel и сделай <b>Redeploy</b>."
    )


def batch_images_failed(
    range_label: str,
    trace: str = "",
    *,
    pollinations_configured: bool = False,
) -> str:
    from bot.utils import escape_html

    hints: list[str] = []
    if "gen-poll:no-key" in trace or not pollinations_configured:
        hints.append(
            "В Vercel добавь <b>POLLINATIONS_API_KEY</b> (имя точно так) "
            "и нажми <b>Redeploy</b> — Save без деплоя не подхватывает ключ."
        )
    if ":401" in trace:
        hints.append(
            "<b>HF_API_KEY</b> не принят (401). Новый токен на huggingface.co → "
            "Fine-grained → Inference Providers."
        )
    if "gen-poll:" in trace and ":401" in trace:
        hints.append("Ключ Pollinations неверный — проверь на enter.pollinations.ai.")
    if "402" in trace:
        hints.append("Старый image.pollinations.ai не работает — нужен ключ gen.pollinations.ai.")

    hint_block = "\n".join(f"• {h}" for h in hints) if hints else (
        "Проверь <b>POLLINATIONS_API_KEY</b> или <b>HF_API_KEY</b> в Vercel."
    )
    detail = ""
    if trace:
        detail = f"\n\n<i>Технически:</i>\n<code>{escape_html(trace[:350])}</code>"

    return (
        f"😔 Слайд {range_label}: картинка не сгенерировалась.{detail}\n\n"
        f"{hint_block}\n\n"
        "Исправь в Vercel → Redeploy → нажми кнопку снова."
    )


def success_batches(total: int) -> str:
    return (
        f"✅ Карусель из {total} слайдов готова!\n\n"
        "Новая тема — просто напиши текст 👇"
    )
