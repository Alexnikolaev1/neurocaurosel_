"""Carousel: сценарий отдельно, картинки порциями; сессия в Redis/памяти."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from bot.config import BUILD_TAG, Settings
from bot.http_client import http_session
from bot.image_overlay import prepare_slide_image
from bot.placeholder_image import render_placeholder_slide
from bot.models import CarouselJob, CarouselSession, Slide, TextMode
from bot.services.gemini import GeminiRateLimitError, ScenarioGenerator
from bot.services.scenario_fallback import generate_fallback_scenario
from bot.services.images import ImageGenerator
from bot.services.telegram import TelegramClient
from bot.session_store import delete_session, load_session, save_session, storage_mode
from bot.utils import escape_html
from bot import keyboards, texts

logger = logging.getLogger("neurocarousel.carousel")


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

    async def has_session(self, chat_id: int) -> bool:
        session = await load_session(chat_id)
        return session is not None and session.has_more()

    async def start_carousel(self, job: CarouselJob, *, status_message_id: int) -> None:
        chat_id = job.chat_id
        if not self._jobs.try_acquire(chat_id):
            await self._tg.send_message(chat_id, texts.job_in_progress())
            return

        await delete_session(chat_id)
        budget = self._settings.function_timeout_sec - 4
        if self._settings.gemini_scenario_timeout > 0:
            scenario_timeout = min(self._settings.gemini_scenario_timeout, budget)
        else:
            scenario_timeout = budget
        logger.info("Scenario timeout budget=%.0fs", scenario_timeout)

        try:
            async with http_session(self._settings) as http:
                await self._tg.edit_message(
                    chat_id, status_message_id, texts.scenario_progress()
                )

                if self._settings.skip_gemini:
                    logger.info("SKIP_GEMINI=1 — template scenario chat=%s", chat_id)
                    slides = generate_fallback_scenario(
                        job.topic,
                        self._settings.slides_count,
                        language=job.language,
                        style=job.style,
                    )
                    await self._finish_scenario(
                        job,
                        status_message_id,
                        slides,
                        used_fallback=False,
                        template_scenario=True,
                    )
                    return

                gemini = ScenarioGenerator(self._settings, http)

                try:
                    slides = await asyncio.wait_for(
                        gemini.generate(
                            job.topic,
                            language=job.language,
                            style=job.style,
                        ),
                        timeout=scenario_timeout,
                    )
                except asyncio.TimeoutError:
                    logger.warning(
                        "Scenario wait_for timeout (%.0fs) chat=%s",
                        scenario_timeout,
                        chat_id,
                    )
                    await self._tg.edit_message(
                        chat_id, status_message_id, texts.scenario_timeout(scenario_timeout)
                    )
                    return
                except GeminiRateLimitError:
                    logger.warning(
                        "Gemini 429 after all models/retries — fallback chat=%s",
                        chat_id,
                    )
                    slides = generate_fallback_scenario(
                        job.topic,
                        self._settings.slides_count,
                        language=job.language,
                        style=job.style,
                    )
                    await self._finish_scenario(
                        job, status_message_id, slides, used_fallback=True
                    )
                    return
                except Exception:
                    logger.exception("Scenario generation failed")
                    await self._tg.edit_message(
                        chat_id, status_message_id, texts.scenario_error()
                    )
                    return

                await self._finish_scenario(
                    job, status_message_id, slides, used_fallback=False
                )
        finally:
            self._jobs.release(chat_id)

    async def _finish_scenario(
        self,
        job: CarouselJob,
        status_message_id: int,
        slides: list[Slide],
        *,
        used_fallback: bool,
        template_scenario: bool = False,
    ) -> None:
        session = CarouselSession(
            chat_id=job.chat_id,
            topic=job.topic,
            language=job.language,
            style=job.style,
            text_mode=job.text_mode,
            slides=slides,
            status_message_id=status_message_id,
            batch_size=self._settings.batch_size,
        )
        await save_session(session)
        logger.info("Session saved (%s) chat=%s slides=%d", storage_mode(), job.chat_id, len(slides))

        bs = session.batch_size
        if template_scenario:
            ready_text = texts.scenario_ready_template(session.total, job.topic, bs)
        elif used_fallback:
            ready_text = texts.scenario_ready_fallback(session.total, job.topic, bs)
        else:
            ready_text = texts.scenario_ready(session.total, job.topic, bs)
        await self._tg.edit_message(job.chat_id, status_message_id, ready_text)

        end = min(session.batch_size, session.total)
        await self._tg.send_message(
            job.chat_id,
            f"{texts.draw_batch_prompt(1, end)}\n\n{texts.draw_hint_continue_text()}",
            reply_markup=keyboards.draw_actions_keyboard(
                1,
                end,
                retry_gemini=used_fallback,
            ),
        )

    async def retry_gemini_scenario(self, chat_id: int) -> None:
        session = await load_session(chat_id)
        if not session:
            await self._tg.send_message(chat_id, texts.session_not_found())
            return
        if session.next_index > 0:
            await self._tg.send_message(
                chat_id,
                "Уже начали рисовать — для нового сценария Gemini отправь <b>новую тему</b>.",
            )
            return
        if not self._jobs.try_acquire(chat_id):
            await self._tg.send_message(chat_id, texts.job_in_progress())
            return

        budget = self._settings.function_timeout_sec - 4
        scenario_timeout = (
            min(self._settings.gemini_scenario_timeout, budget)
            if self._settings.gemini_scenario_timeout > 0
            else budget
        )

        try:
            await self._tg.edit_message(
                chat_id,
                session.status_message_id,
                texts.scenario_retry_progress(),
            )
            async with http_session(self._settings) as http:
                gemini = ScenarioGenerator(self._settings, http)
                try:
                    slides = await asyncio.wait_for(
                        gemini.generate(
                            session.topic,
                            language=session.language,
                            style=session.style,
                        ),
                        timeout=scenario_timeout,
                    )
                except asyncio.TimeoutError:
                    await self._tg.edit_message(
                        chat_id,
                        session.status_message_id,
                        texts.scenario_timeout(scenario_timeout),
                    )
                    return
                except GeminiRateLimitError:
                    await self._tg.send_message(chat_id, texts.scenario_rate_limit())
                    return
                except Exception:
                    logger.exception("Gemini retry failed chat=%s", chat_id)
                    await self._tg.send_message(chat_id, texts.scenario_error())
                    return

            session.slides = slides
            session.next_index = 0
            await save_session(session)
            bs = session.batch_size
            await self._tg.edit_message(
                chat_id,
                session.status_message_id,
                texts.scenario_ready(session.total, session.topic, bs),
            )
            end = min(bs, session.total)
            await self._tg.send_message(
                chat_id,
                f"{texts.draw_batch_prompt(1, end)}\n\n{texts.draw_hint_continue_text()}",
                reply_markup=keyboards.draw_actions_keyboard(1, end),
            )
            logger.info("Gemini retry ok chat=%s slides=%d", chat_id, len(slides))
        finally:
            self._jobs.release(chat_id)

    async def draw_next_batch(self, chat_id: int) -> None:
        session = await load_session(chat_id)
        if not session:
            logger.warning("Draw: no session chat=%s", chat_id)
            await self._tg.send_message(chat_id, texts.session_not_found())
            return
        if not session.has_more():
            logger.info("Draw: already complete chat=%s", chat_id)
            await self._tg.send_message(chat_id, texts.success_batches(session.total))
            await delete_session(chat_id)
            return

        if not self._jobs.try_acquire(chat_id):
            logger.info("Draw: busy chat=%s", chat_id)
            await self._tg.send_message(chat_id, texts.job_in_progress())
            return

        draw_timeout = self._settings.function_timeout_sec - 3
        logger.info(
            "Draw start [%s] chat=%s idx=%d/%d poll_only=%s poll_key=%s hf_key=%s",
            BUILD_TAG,
            chat_id,
            session.next_index,
            session.total,
            self._settings.pollinations_only,
            bool(self._settings.pollinations_api_key),
            bool(self._settings.hf_key),
        )

        try:
            images_svc = ImageGenerator(self._settings)
            try:
                await asyncio.wait_for(
                    self._run_one_batch(session, images_svc),
                    timeout=draw_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("Draw batch timeout chat=%s", chat_id)
                await save_session(session)
                await self._tg.send_message(
                    chat_id,
                    texts.draw_timeout_continue(session.next_index, session.total),
                )
        except Exception:
            logger.exception("Draw failed chat=%s", chat_id)
            await save_session(session)
            batch = session.batch_slides()
            if batch:
                n = batch[0].number
                await self._tg.send_message(
                    chat_id,
                    texts.batch_images_failed(str(n)),
                    reply_markup=keyboards.draw_batch_keyboard(n, n),
                )
        finally:
            self._jobs.release(chat_id)

    async def redraw_slide(self, chat_id: int, slide_number: int) -> None:
        session = await load_session(chat_id)
        if not session:
            await self._tg.send_message(chat_id, texts.session_not_found())
            return
        if session.next_index <= 0:
            await self._tg.send_message(chat_id, texts.redraw_not_available(slide_number))
            return

        slide = next((s for s in session.slides if s.number == slide_number), None)
        if not slide:
            await self._tg.send_message(chat_id, texts.redraw_not_available(slide_number))
            return

        last_done = session.slides[session.next_index - 1].number
        if slide_number > last_done:
            await self._tg.send_message(chat_id, texts.redraw_not_available(slide_number))
            return

        if not self._jobs.try_acquire(chat_id):
            await self._tg.send_message(chat_id, texts.job_in_progress())
            return

        draw_timeout = self._settings.function_timeout_sec - 3
        logger.info("Redraw slide=%d chat=%s [%s]", slide_number, chat_id, BUILD_TAG)

        try:
            images_svc = ImageGenerator(self._settings)
            await self._tg.send_message(chat_id, texts.redraw_progress(slide_number))
            await asyncio.wait_for(
                self._run_redraw(session, slide, images_svc),
                timeout=draw_timeout,
            )
        except asyncio.TimeoutError:
            logger.warning("Redraw timeout slide=%d chat=%s", slide_number, chat_id)
            if session.has_more():
                next_from = session.next_index + 1
                next_to = min(session.next_index + session.batch_size, session.total)
                markup = keyboards.draw_actions_keyboard(
                    next_from,
                    next_to,
                    redraw_slide=slide_number,
                )
            else:
                markup = keyboards.redraw_only_keyboard(slide_number)
            await self._tg.send_message(
                chat_id,
                texts.draw_timeout_continue(session.next_index, session.total),
                reply_markup=markup,
            )
        except Exception:
            logger.exception("Redraw failed slide=%d chat=%s", slide_number, chat_id)
            await self._tg.send_message(
                chat_id,
                texts.redraw_failed(slide_number),
                reply_markup=keyboards.draw_actions_keyboard(
                    slide_number,
                    slide_number,
                    redraw_slide=slide_number,
                ),
            )
        finally:
            self._jobs.release(chat_id)

    async def _run_redraw(
        self,
        session: CarouselSession,
        slide: Slide,
        images_svc: ImageGenerator,
    ) -> None:
        item = await self._build_slide_image(
            session,
            slide,
            images_svc,
            allow_placeholder=False,
        )
        if not item:
            await self._tg.send_message(
                session.chat_id,
                texts.redraw_failed(slide.number, images_svc.last_trace),
                reply_markup=keyboards.draw_actions_keyboard(
                    slide.number,
                    slide.number,
                    redraw_slide=slide.number,
                ),
            )
            return

        slide_obj, data, _placeholder = item
        ok = await self._send_slides(
            session.chat_id,
            [(slide_obj, data, False)],
            session.total,
            session.text_mode,
        )
        if not ok:
            await self._tg.send_message(session.chat_id, texts.send_error())
            return

        await self._tg.send_message(session.chat_id, texts.redraw_ok(slide.number))

        if session.has_more():
            next_from = session.next_index + 1
            next_to = min(session.next_index + session.batch_size, session.total)
            await self._tg.send_message(
                session.chat_id,
                f"{texts.draw_batch_prompt(next_from, next_to)}\n\n{texts.draw_hint_continue_text()}",
                reply_markup=keyboards.draw_actions_keyboard(next_from, next_to),
            )

    async def _run_one_batch(
        self,
        session: CarouselSession,
        images_svc: ImageGenerator,
    ) -> None:
        batch = session.batch_slides()
        if not batch:
            return

        from_n, to_n = batch[0].number, batch[-1].number
        sent, placeholder_nums = await self._process_one_batch(session, images_svc)
        await save_session(session)
        redraw_slide = placeholder_nums[-1] if placeholder_nums else None

        if sent == 0:
            label = str(from_n) if from_n == to_n else f"{from_n}–{to_n}"
            fail_text = texts.batch_images_failed(
                label,
                images_svc.last_trace,
                pollinations_configured=bool(self._settings.pollinations_api_key),
            )
            await self._tg.edit_message(
                session.chat_id,
                session.status_message_id,
                fail_text,
            )
            await self._tg.send_message(
                session.chat_id,
                fail_text,
                reply_markup=keyboards.draw_actions_keyboard(from_n, to_n),
            )
            return

        if not session.has_more():
            await delete_session(session.chat_id)
            await self._tg.edit_message(
                session.chat_id,
                session.status_message_id,
                texts.success_batches(session.total),
            )
            return

        next_from = session.next_index + 1
        next_to = min(session.next_index + session.batch_size, session.total)
        await self._tg.edit_message(
            session.chat_id,
            session.status_message_id,
            texts.batch_pause(
                done_through=session.next_index,
                total=session.total,
                next_from=next_from,
                next_to=next_to,
            ),
        )
        await self._tg.send_message(
            session.chat_id,
            f"{texts.draw_batch_prompt(next_from, next_to)}\n\n{texts.draw_hint_continue_text()}",
            reply_markup=keyboards.draw_actions_keyboard(
                next_from,
                next_to,
                redraw_slide=redraw_slide,
            ),
        )

    async def _process_one_batch(
        self,
        session: CarouselSession,
        images_svc: ImageGenerator,
    ) -> tuple[int, list[int]]:
        batch = session.batch_slides()
        if not batch:
            return 0, []

        total = session.total
        await self._tg.edit_message(
            session.chat_id,
            session.status_message_id,
            texts.batch_progress(
                batch_num=session.current_batch_number,
                total_batches=session.total_batches,
                slide_from=batch[0].number,
                slide_to=batch[-1].number,
                total_slides=total,
            ),
        )

        images: list[tuple[Slide, bytes, bool]] = []
        placeholder_nums: list[int] = []
        for slide in batch:
            await self._tg.send_chat_action(session.chat_id)
            item = await self._build_slide_image(
                session,
                slide,
                images_svc,
                allow_placeholder=True,
            )
            if item:
                images.append(item)
                if item[2]:
                    placeholder_nums.append(slide.number)
            if slide != batch[-1]:
                await asyncio.sleep(images_svc.between_delay)

        if not images:
            return 0, []

        ok = await self._send_slides(session.chat_id, images, total, session.text_mode)
        if ok and placeholder_nums:
            await self._tg.send_message(
                session.chat_id,
                texts.placeholder_hint(),
            )
        if not ok:
            logger.error("Telegram send failed chat=%s slides=%s", session.chat_id, batch[0].number)
            return 0, []

        session.advance(len(batch))
        return len(images), placeholder_nums

    async def _build_slide_image(
        self,
        session: CarouselSession,
        slide: Slide,
        images_svc: ImageGenerator,
        *,
        allow_placeholder: bool,
    ) -> tuple[Slide, bytes, bool] | None:
        overlay = session.text_mode == TextMode.TEXT_ON_IMAGE
        raw = await images_svc.generate(slide.image_prompt, raw=overlay)
        used_placeholder = False
        if not raw and allow_placeholder and self._settings.placeholder_on_fail:
            logger.warning(
                "Placeholder slide=%d trace=%s",
                slide.number,
                images_svc.last_trace,
            )
            raw = render_placeholder_slide(
                slide.caption,
                slide_number=slide.number,
                total_slides=session.total,
                topic=session.topic,
            )
            used_placeholder = True
        elif not raw:
            logger.error(
                "Image gen failed slide=%d chat=%s trace=%s",
                slide.number,
                session.chat_id,
                images_svc.last_trace,
            )
            return None

        if used_placeholder or not overlay:
            data = raw
        else:
            data = prepare_slide_image(
                raw,
                slide.caption,
                slide_number=slide.number,
                total_slides=session.total,
                text_mode=session.text_mode,
                settings=self._settings,
            )
        return slide, data, used_placeholder

    def _slide_caption(
        self,
        slide: Slide,
        total_slides: int,
        text_mode: TextMode,
    ) -> str:
        if text_mode == TextMode.TEXT_ON_IMAGE:
            return f"<b>{slide.number}/{total_slides}</b> · текст на картинке"[:1024]
        safe = escape_html(slide.caption)
        return f"<b>{slide.number}/{total_slides}</b>\n{safe}"[:1024]

    async def _send_slides(
        self,
        chat_id: int,
        items: list[tuple[Slide, bytes, bool]],
        total_slides: int,
        text_mode: TextMode,
    ) -> bool:
        """Одно фото — sendPhoto; 2+ — sendMediaGroup (Telegram: группа от 2 шт.)."""
        if len(items) == 1:
            slide, data, _placeholder = items[0]
            result = await self._tg.send_photo(
                chat_id,
                data,
                self._slide_caption(slide, total_slides, text_mode),
            )
            return bool(result.get("ok"))

        media: list[dict[str, Any]] = []
        files: dict[str, bytes] = {}

        for i, (slide, data, _placeholder) in enumerate(items):
            field = f"b{i}"
            files[field] = data
            media.append({
                "type": "photo",
                "media": f"attach://{field}",
                "caption": self._slide_caption(slide, total_slides, text_mode),
                "parse_mode": "HTML",
            })

        result = await self._tg.send_media_group(chat_id, media, files)
        return bool(result.get("ok"))
