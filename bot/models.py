"""Domain models for carousel generation."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class VisualStyle(str, Enum):
    CINEMATIC = "cinematic"
    MINIMAL = "minimal"
    ANIME = "anime"
    RETRO = "retro"
    PHOTO = "photo"

    @classmethod
    def from_value(cls, value: str | None) -> VisualStyle:
        try:
            return cls(value or cls.CINEMATIC)
        except ValueError:
            return cls.CINEMATIC


@dataclass(slots=True)
class Slide:
    number: int
    caption: str
    image_prompt: str

    @classmethod
    def from_dict(cls, data: dict) -> Slide:
        return cls(
            number=int(data.get("slide", 0)),
            caption=str(data.get("caption", "")).strip(),
            image_prompt=str(data.get("image_prompt", "")).strip(),
        )

    def to_dict(self) -> dict:
        return {
            "slide": self.number,
            "caption": self.caption,
            "image_prompt": self.image_prompt,
        }


@dataclass(slots=True)
class CarouselJob:
    chat_id: int
    topic: str
    language: str
    style: VisualStyle = VisualStyle.CINEMATIC
    slides: list[Slide] = field(default_factory=list)

    @property
    def topic_key(self) -> str:
        return f"{self.chat_id}:{self.topic.strip().lower()}:{self.style.value}"


@dataclass(slots=True)
class CarouselSession:
    """Единый сценарий; картинки рисуются порциями по batch_size."""

    chat_id: int
    topic: str
    language: str
    style: VisualStyle
    slides: list[Slide]
    status_message_id: int
    next_index: int = 0
    batch_size: int = 2

    @property
    def total(self) -> int:
        return len(self.slides)

    @property
    def total_batches(self) -> int:
        return (self.total + self.batch_size - 1) // self.batch_size

    @property
    def current_batch_number(self) -> int:
        return self.next_index // self.batch_size + 1

    def has_more(self) -> bool:
        return self.next_index < self.total

    def batch_slides(self) -> list[Slide]:
        return self.slides[self.next_index : self.next_index + self.batch_size]

    def advance(self, count: int) -> None:
        self.next_index = min(self.next_index + count, self.total)

    def slide_range_label(self) -> str:
        batch = self.batch_slides()
        if not batch:
            return ""
        first = batch[0].number
        last = batch[-1].number
        return f"{first}–{last}"
