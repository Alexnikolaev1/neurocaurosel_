"""Carousel generation orchestration."""

from __future__ import annotations

import asyncio
import logging

from bot.config import Settings
from bot.http_client import http_session
from bot.models import CarouselJob, Slide
from bot.services.gemini import GeminiRateLimitError, ScenarioGenerator
from bot.services.images import ImageGenerator
from bot.services.telegram import TelegramClient
from bot import texts

logger = logging.getLogger("neurocarousel.carousel")


class ScenarioCache:
    def __init__(self, max_size: int) -> None:
        self._max_size = max_size
        self._store: dict[str, list[Slide]] = {}

    def get(self, key: str) -> list[Slide] | None:
        return self._store.get(key)

    def set(self, key: str, slides: list[Slide]) -> None:
        if len(self._store) >= self._max_size:
            oldest = next(iter(self._store))
            del self._store[oldest]
        self._store[key] = slides

    def pop(self, key: str) -> None:
        self._store.pop(key, None)


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
        self._scenario_cache = ScenarioCache(settings.scenario_cache_max)
        self._jobs = JobRegistry()

    async def generate_carousel(
        self,
        job: CarouselJob,
        *,
        status_message_id: int,
        use_cache: bool = True,
    ) -> None:
        chat_id = job.chat_id
        if not self._jobs.try_acquire(chat_id):
            await self._tg.send_message(chat_id, texts.job_in_progress())
            return

        timeout = self._settings.function_timeout_sec
        try:
            await asyncio.wait_for(
                self._generate_carousel_inner(job, status_message_id, use_cache),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Carousel timeout after %.0fs for chat %s", timeout, chat_id)
            await self._tg.edit_message(
                chat_id,
                status_message_id,
                texts.timeout_error(self._settings.slides_count),
            )
        finally:
            self._jobs.release(chat_id)

    async def _generate_carousel_inner(
        self,
        job: CarouselJob,
        status_message_id: int,
        use_cache: bool,
    ) -> None:
        chat_id = job.chat_id
        cache_key = job.topic_key

        async with http_session(self._settings) as http:
            gemini = ScenarioGenerator(self._settings, http)
            images_svc = ImageGenerator(self._settings, http)

            await self._tg.edit_message(
                chat_id, status_message_id, texts.scenario_progress()
            )

            try:
                cached = self._scenario_cache.get(cache_key) if use_cache else None
                if cached:
                    slides = cached
                else:
                    slides = await gemini.generate(
                        job.topic,
                        language=job.language,
                        style=job.style,
                    )
                    self._scenario_cache.set(cache_key, slides)
                job.slides = slides
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

            total = len(slides)
            sent = await self._generate_and_send_slides(
                slides, chat_id, status_message_id, images_svc
            )

            self._scenario_cache.pop(cache_key, None)

            if sent == 0:
                await self._tg.edit_message(
                    chat_id, status_message_id, texts.no_images_generated()
                )
            elif sent < total:
                await self._tg.edit_message(
                    chat_id, status_message_id, texts.partial_success(sent, total)
                )
            else:
                await self._tg.edit_message(chat_id, status_message_id, texts.success())

    async def _generate_and_send_slides(
        self,
        slides: list[Slide],
        chat_id: int,
        progress_msg_id: int,
        images_svc: ImageGenerator,
    ) -> int:
        """Generate and send each slide immediately (survives partial serverless runs)."""
        total = len(slides)
        sent = 0

        for i, slide in enumerate(slides, start=1):
            await self._tg.edit_message(
                chat_id, progress_msg_id, texts.image_progress(i, total)
            )
            await self._tg.send_chat_action(chat_id)

            img = await images_svc.generate(slide.image_prompt)
            if img:
                caption = f"<b>Слайд {i}/{total}</b>\n\n{slide.caption}"
                await self._tg.send_photo(chat_id, img, caption)
                sent += 1

            if i < total:
                await asyncio.sleep(images_svc.between_delay)

        return sent

    def is_chat_busy(self, chat_id: int) -> bool:
        return self._jobs.is_busy(chat_id)
