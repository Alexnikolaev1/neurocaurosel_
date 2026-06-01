"""Carousel generation orchestration."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

from bot.config import Settings
from bot.models import CarouselJob, Slide
from bot.services.gemini import ScenarioGenerator
from bot.services.images import ImageGenerator
from bot.services.telegram import TelegramClient
from bot import texts

logger = logging.getLogger("neurocarousel.carousel")


class ScenarioCache:
    """In-memory cache keyed by chat+topic+style for safe retries."""

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
    """Prevents concurrent generations per chat on warm serverless instances."""

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
        self._http: httpx.AsyncClient | None = None
        self._scenario_cache = ScenarioCache(settings.scenario_cache_max)
        self._jobs = JobRegistry()

    async def _http_client(self) -> httpx.AsyncClient:
        if self._http is None or self._http.is_closed:
            self._http = httpx.AsyncClient(timeout=self._settings.request_timeout)
        return self._http

    async def generate_carousel(
        self,
        job: CarouselJob,
        *,
        status_message_id: int,
        use_cache: bool = True,
    ) -> None:
        chat_id = job.chat_id
        cache_key = job.topic_key

        if not self._jobs.try_acquire(chat_id):
            await self._tg.send_message(chat_id, texts.job_in_progress())
            return

        try:
            http = await self._http_client()
            gemini = ScenarioGenerator(self._settings, http)
            images_svc = ImageGenerator(self._settings, http)

            # Step 1: scenario
            await self._tg.edit_message(chat_id, status_message_id, texts.scenario_progress())

            try:
                cached = self._scenario_cache.get(cache_key) if use_cache else None
                if cached:
                    logger.info("Scenario cache hit: %s", cache_key)
                    slides = cached
                else:
                    slides = await gemini.generate(
                        job.topic,
                        language=job.language,
                        style=job.style,
                    )
                    self._scenario_cache.set(cache_key, slides)
                job.slides = slides
            except Exception:
                logger.exception("Scenario generation failed")
                await self._tg.edit_message(
                    chat_id, status_message_id, texts.scenario_error()
                )
                return

            # Step 2: images
            total = len(slides)

            try:
                images = await self._generate_all_images(
                    slides, chat_id, status_message_id, images_svc
                )
            except Exception:
                logger.exception("Image generation failed")
                await self._tg.edit_message(
                    chat_id, status_message_id, texts.images_error()
                )
                return

            # Step 3: send
            await self._tg.edit_message(chat_id, status_message_id, texts.sending_carousel())

            try:
                await self._send_carousel(chat_id, slides, images)
            except Exception:
                logger.exception("Carousel send failed")
                await self._tg.send_message(chat_id, texts.send_error())
                return

            self._scenario_cache.pop(cache_key)
            await self._tg.edit_message(chat_id, status_message_id, texts.success())

        finally:
            self._jobs.release(chat_id)

    async def _generate_all_images(
        self,
        slides: list[Slide],
        chat_id: int,
        progress_msg_id: int,
        images_svc: ImageGenerator,
    ) -> list[bytes | None]:
        images: list[bytes | None] = []
        total = len(slides)

        for i, slide in enumerate(slides, start=1):
            await self._tg.edit_message(
                chat_id, progress_msg_id, texts.image_progress(i, total)
            )
            await self._tg.send_chat_action(chat_id)

            img = await images_svc.generate(slide.image_prompt)
            images.append(img)

            if i < total:
                await asyncio.sleep(images_svc.between_delay)

        return images

    async def _send_carousel(
        self,
        chat_id: int,
        slides: list[Slide],
        images: list[bytes | None],
    ) -> None:
        media_items: list[dict[str, Any]] = []
        files: dict[str, bytes] = {}
        failed_captions: list[str] = []

        for i, (slide, img) in enumerate(zip(slides, images)):
            if img is None:
                failed_captions.append(f"Слайд {slide.number}: {slide.caption}")
                continue

            field = f"photo_{i}"
            files[field] = img
            caption = slide.caption[:1024]

            item: dict[str, Any] = {
                "type": "photo",
                "media": f"attach://{field}",
                "caption": caption,
                "parse_mode": "HTML",
            }
            media_items.append(item)

        if not media_items:
            await self._tg.send_message(chat_id, texts.no_images_generated())
            return

        chunk_size = 10
        for start in range(0, len(media_items), chunk_size):
            chunk_media = media_items[start : start + chunk_size]
            chunk_files = {}
            for item in chunk_media:
                field = item["media"].replace("attach://", "")
                if field in files:
                    chunk_files[field] = files[field]
            await self._tg.send_media_group(chat_id, chunk_media, chunk_files)

        if failed_captions:
            await self._tg.send_message(chat_id, texts.partial_failure(failed_captions))

    def is_chat_busy(self, chat_id: int) -> bool:
        return self._jobs.is_busy(chat_id)
