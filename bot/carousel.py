"""Carousel: один сценарий, картинки порциями по batch_size."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from bot.config import Settings
from bot.http_client import http_session
from bot.models import CarouselJob, CarouselSession, Slide
from bot.services.gemini import GeminiRateLimitError, ScenarioGenerator
from bot.services.images import ImageGenerator
from bot.services.telegram import TelegramClient
from bot import keyboards, texts

logger = logging.getLogger("neurocarousel.carousel")

# chat_id → активная сессия (общий сценарий между порциями)
_sessions: dict[int, CarouselSession] = {}


class JobRegistry:
    def __init__(self) -> None:
        self._active: set[int] = set()

    def try_acquire(self, chat_id: int) -> bool:
        if chat_id in self._active:
            return False
        self._active.add(chat_id)
        return True

    def release(self, chat_id: int) -> None:
        self._active.discard(chat_id)

    def is_busy(self, chat_id: int) -> bool:
        return chat_id in self._active


class CarouselOrchestrator:
    def __init__(self, settings: Settings, tg: TelegramClient) -> None:
        self._settings = settings
        self._tg = tg
        self._jobs = JobRegistry()

    def is_chat_busy(self, chat_id: int) -> bool:
        return self._jobs.is_busy(chat_id)

    def has_session(self, chat_id: int) -> bool:
        return chat_id in _sessions and _sessions[chat_id].has_more()

    async def start_carousel(self, job: CarouselJob, *, status_message_id: int) -> None:
        """Новая тема: Gemini-сценарий на все слайды, затем порции по 3."""
        chat_id = job.chat_id
        if not self._jobs.try_acquire(chat_id):
            await self._tg.send_message(chat_id, texts.job_in_progress())
            return

        try:
            async with http_session(self._settings) as http:
                await self._tg.edit_message(
                    chat_id, status_message_id, texts.scenario_progress()
                )
                gemini = ScenarioGenerator(self._settings, http)

                try:
                    slides = await gemini.generate(
                        job.topic,
                        language=job.language,
                        style=job.style,
                    )
                except GeminiRateLimitError:
                    await self._tg.edit_message(
                        chat_id, status_message_id, texts.scenario_rate_limit()
                    )
                    return
                except Exception:
                    logger.exception("Scenario generation failed")
                    await self._tg.edit_message(
                        chat_id, status_message_id, texts.scenario_error()
                    )
                    return

                session = CarouselSession(
                    chat_id=chat_id,
                    topic=job.topic,
                    language=job.language,
                    style=job.style,
                    slides=slides,
                    status_message_id=status_message_id,
                    batch_size=self._settings.batch_size,
                )
                _sessions[chat_id] = session

                images_svc = ImageGenerator(self._settings, http)
                await self._run_batches(session, images_svc)
        finally:
            self._jobs.release(chat_id)

    async def continue_carousel(self, chat_id: int) -> None:
        """Продолжить ту же карусель (тот же сценарий, следующие 3 слайда)."""
        session = _sessions.get(chat_id)
        if not session or not session.has_more():
            await self._tg.send_message(
                chat_id, "Нет активной карусели. Напиши новую тему 👇"
            )
            return

        if not self._jobs.try_acquire(chat_id):
            await self._tg.send_message(chat_id, texts.job_in_progress())
            return

        try:
            async with http_session(self._settings) as http:
                images_svc = ImageGenerator(self._settings, http)
                await self._run_batches(session, images_svc)
        finally:
            self._jobs.release(chat_id)

    async def _run_batches(self, session: CarouselSession, images_svc: ImageGenerator) -> None:
        """Сколько порций успеем за лимит Vercel — без кнопки; иначе кнопка «Продолжить»."""
        deadline = time.monotonic() + self._settings.function_timeout_sec - 5
        batches_done = 0

        while session.has_more() and time.monotonic() < deadline:
            sent = await self._process_one_batch(session, images_svc)
            if sent == 0:
                await self._tg.edit_message(
                    session.chat_id,
                    session.status_message_id,
                    texts.batch_images_failed(session.slide_range_label()),
                )
                return
            batches_done += 1

        if not session.has_more():
            _sessions.pop(session.chat_id, None)
            await self._tg.edit_message(
                session.chat_id,
                session.status_message_id,
                texts.success_batches(session.total),
            )
            return

        # Ещё есть слайды — просим продолжить (тот же сценарий уже в session)
        start, end = session.next_index + 1, min(
            session.next_index + session.batch_size, session.total
        )
        await self._tg.edit_message(
            session.chat_id,
            session.status_message_id,
            texts.batch_pause(
                done_through=session.next_index,
                total=session.total,
                next_from=start,
                next_to=end,
            ),
        )
        await self._tg.send_message(
            session.chat_id,
            texts.batch_continue_prompt(start, end),
            reply_markup=keyboards.continue_carousel_keyboard(),
        )

    async def _process_one_batch(
        self,
        session: CarouselSession,
        images_svc: ImageGenerator,
    ) -> int:
        batch = session.batch_slides()
        if not batch:
            return 0

        total = session.total
        batch_num = session.current_batch_number
        total_batches = session.total_batches

        await self._tg.edit_message(
            session.chat_id,
            session.status_message_id,
            texts.batch_progress(
                batch_num=batch_num,
                total_batches=total_batches,
                slide_from=batch[0].number,
                slide_to=batch[-1].number,
                total_slides=total,
            ),
        )

        images: list[tuple[Slide, bytes]] = []
        for slide in batch:
            await self._tg.send_chat_action(session.chat_id)
            img = await images_svc.generate(slide.image_prompt)
            if img:
                images.append((slide, img))
            if slide != batch[-1]:
                await asyncio.sleep(images_svc.between_delay)

        if not images:
            return 0

        await self._send_batch_as_group(session.chat_id, images, total)
        session.advance(len(batch))
        return len(images)

    async def _send_batch_as_group(
        self,
        chat_id: int,
        items: list[tuple[Slide, bytes]],
        total_slides: int,
    ) -> None:
        media: list[dict[str, Any]] = []
        files: dict[str, bytes] = {}

        for i, (slide, data) in enumerate(items):
            field = f"b{i}"
            files[field] = data
            caption = f"<b>{slide.number}/{total_slides}</b>\n{slide.caption}"[:1024]
            entry: dict[str, Any] = {
                "type": "photo",
                "media": f"attach://{field}",
                "caption": caption,
                "parse_mode": "HTML",
            }
            media.append(entry)

        await self._tg.send_media_group(chat_id, media, files)
