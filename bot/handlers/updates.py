"""Update routing and handlers."""

from __future__ import annotations

import logging

from bot import keyboards, texts
from bot.carousel import CarouselOrchestrator
from bot.config import Settings
from bot.keyboards import EXAMPLE_TOPICS, style_label
from bot.models import CarouselJob, VisualStyle
from bot.services.telegram import TelegramClient
from bot.utils import detect_language, is_valid_topic

logger = logging.getLogger("neurocarousel.handlers")

# Per-chat user preferences (style) — survives warm invocations
_user_styles: dict[int, VisualStyle] = {}
_last_topics: dict[int, str] = {}


class UpdateRouter:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._tg = TelegramClient(settings)
        self._carousel = CarouselOrchestrator(settings, self._tg)

    def _get_style(self, chat_id: int) -> VisualStyle:
        return _user_styles.get(
            chat_id,
            VisualStyle.from_value(self._settings.default_style),
        )

    def _set_style(self, chat_id: int, style: VisualStyle) -> None:
        _user_styles[chat_id] = style

    async def handle(self, update: dict) -> None:
        if callback := update.get("callback_query"):
            await self._handle_callback(callback)
            return

        message = update.get("message") or update.get("edited_message")
        if not message:
            return

        chat_id: int = message["chat"]["id"]
        text: str = (message.get("text") or "").strip()

        if not text:
            return

        if text.startswith("/start"):
            await self._cmd_start(chat_id)
            return

        if text.startswith("/help"):
            await self._cmd_help(chat_id)
            return

        if text.startswith("/style"):
            await self._cmd_style(chat_id)
            return

        await self._handle_topic(chat_id, text)

    async def _cmd_start(self, chat_id: int) -> None:
        style = self._get_style(chat_id)
        await self._tg.send_message(
            chat_id,
            texts.WELCOME_TEXT,
            reply_markup=keyboards.style_keyboard(style),
        )
        await self._tg.send_message(
            chat_id,
            "👇 Или выбери готовый пример:",
            reply_markup=keyboards.examples_keyboard(),
        )

    async def _cmd_help(self, chat_id: int) -> None:
        await self._tg.send_message(chat_id, texts.help_text())

    async def _cmd_style(self, chat_id: int) -> None:
        style = self._get_style(chat_id)
        await self._tg.send_message(
            chat_id,
            texts.style_current(style_label(style)),
            reply_markup=keyboards.style_keyboard(style),
        )

    async def _handle_callback(self, callback: dict) -> None:
        query_id = callback["id"]
        chat_id: int = callback["message"]["chat"]["id"]
        data: str = callback.get("data", "")

        if data.startswith("style:"):
            style = VisualStyle.from_value(data.split(":", 1)[1])
            self._set_style(chat_id, style)
            await self._tg.answer_callback_query(query_id, f"Стиль: {style_label(style)}")
            await self._tg.edit_message(
                chat_id,
                callback["message"]["message_id"],
                texts.style_selected(style_label(style)),
                reply_markup=keyboards.style_keyboard(style),
            )
            return

        if data.startswith("topic:"):
            idx = int(data.split(":", 1)[1])
            if 0 <= idx < len(EXAMPLE_TOPICS):
                topic = EXAMPLE_TOPICS[idx]
                await self._tg.answer_callback_query(query_id)
                await self._start_generation(chat_id, topic)
            return

        if data == "retry:last":
            topic = _last_topics.get(chat_id)
            await self._tg.answer_callback_query(query_id)
            if topic:
                await self._start_generation(chat_id, topic)
            else:
                await self._tg.send_message(chat_id, "Напиши тему для новой карусели 👇")
            return

        if data == "carousel_next":
            await self._tg.answer_callback_query(query_id, "Рисую следующую порцию…")
            await self._carousel.continue_carousel(chat_id)
            return

        await self._tg.answer_callback_query(query_id)

    async def _handle_topic(self, chat_id: int, text: str) -> None:
        ok, error = is_valid_topic(text, self._settings)
        if not ok:
            if error == "link":
                await self._tg.send_message(chat_id, texts.invalid_topic_link())
            else:
                await self._tg.send_message(
                    chat_id,
                    texts.invalid_topic_length(
                        self._settings.topic_min_len,
                        self._settings.topic_max_len,
                    ),
                )
            return

        await self._start_generation(chat_id, text)

    async def _start_generation(self, chat_id: int, topic: str) -> None:
        if self._carousel.is_chat_busy(chat_id):
            await self._tg.send_message(chat_id, texts.job_in_progress())
            return

        _last_topics[chat_id] = topic
        language = detect_language(topic)
        style = self._get_style(chat_id)

        status = await self._tg.send_message(chat_id, texts.scenario_progress())
        status_id = status.get("result", {}).get("message_id", 0)

        job = CarouselJob(
            chat_id=chat_id,
            topic=topic,
            language=language,
            style=style,
        )
        await self._carousel.start_carousel(job, status_message_id=status_id)
