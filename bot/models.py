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
