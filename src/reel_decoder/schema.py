"""Pydantic schema for decoded reels.

This is the contract. Every downstream step (LLM classifier, xlsx writer)
validates against these models. The shape mirrors the Swipe Library columns.
"""

from __future__ import annotations

from datetime import date
from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class HookPattern(StrEnum):
    """The 8 hook archetypes from the swipe library."""

    rarity = "Rarity"
    contrarian = "Contrarian"
    stat = "Stat"
    problem_agitate = "Problem/Agitate"
    authority = "Authority"
    transformation = "Transformation"
    question = "Question"
    demonstration = "Demonstration"


class BeatType(StrEnum):
    benefit = "Benefit"
    mechanism = "Mechanism"
    aspiration = "Aspiration"
    social_proof = "Social Proof"
    demonstration = "Demonstration"
    reveal = "Reveal"


class MusicVibe(StrEnum):
    ambient = "Ambient"
    driving = "Driving/EDM"
    cinematic = "Cinematic"
    hiphop = "Hip-Hop"
    pop = "Pop"
    none_silent = "None/Silent"


class CaptionStyle(StrEnum):
    karaoke = "Karaoke"
    static_cards = "Static cards"
    voiceover_only = "Voiceover only"
    mixed = "Mixed"


class Beat(BaseModel):
    """One beat in the reel (between scene cuts, aligned to overlay-text changes)."""

    index: int = Field(ge=1, description="1-indexed beat number after the hook")
    type: BeatType
    primary_text: str = Field(default="", max_length=80, description="White / main overlay text")
    highlight_text: str = Field(default="", max_length=40, description="Accent (yellow) text")
    visual: str = Field(default="", description="One-sentence description of what's on screen")
    start_s: float = Field(ge=0)
    end_s: float = Field(ge=0)

    @field_validator("end_s")
    @classmethod
    def end_after_start(cls, v: float, info) -> float:
        if "start_s" in info.data and v < info.data["start_s"]:
            raise ValueError("end_s must be >= start_s")
        return v


class Hook(BaseModel):
    pattern: HookPattern
    text: str = Field(max_length=200, description="Exact words on screen in first 1-2s")
    visual: str = Field(default="", description="What's shown during the hook")
    start_s: float = 0.0
    end_s: float


class DecodedReel(BaseModel):
    """A fully-decoded reel — one row in the Swipe Library."""

    reel_id: str
    schema_version: Literal[1] = 1
    source_path: str
    date_decoded: date = Field(default_factory=date.today)
    creator: str = ""
    niche: str = ""

    hook: Hook
    beats: list[Beat] = Field(min_length=1, max_length=6)

    mechanism_line: str = Field(default="", description="The 'because science' beat if present")
    payoff_visual: str = Field(default="", description="Final aspirational shot description")
    cta: str = ""

    length_s: float = Field(ge=0)
    music_vibe: MusicVibe = MusicVibe.none_silent
    caption_style: CaptionStyle = CaptionStyle.static_cards

    why_it_works: str = Field(default="", max_length=500)
    stop_scroll_rating: int = Field(default=3, ge=1, le=5)

    notes: str = ""

    def to_xlsx_row(self) -> list:
        """Flatten to a list matching the Swipe Library column order."""
        beats_padded = list(self.beats) + [None] * (6 - len(self.beats))
        beats_padded = beats_padded[:6]  # cap at 6

        row = [
            None,  # # — left blank, sheet auto-numbers
            self.date_decoded,
            self.source_path,
            self.creator,
            self.niche,
            self.hook.pattern.value,
            self.hook.text,
            self.hook.visual,
        ]
        for b in beats_padded:
            if b is None:
                row.extend(["", "", ""])
            else:
                row.extend([b.primary_text, b.type.value, b.visual])
        row.extend(
            [
                self.mechanism_line,
                self.payoff_visual,
                self.cta,
                round(self.length_s, 1),
                self.music_vibe.value,
                self.caption_style.value,
                self.why_it_works,
                self.stop_scroll_rating,
                self.notes,
            ]
        )
        return row


# Intermediate data shapes for pipeline steps —
# These don't go to the xlsx, but they're persisted as JSON for idempotency.


class WordTimestamp(BaseModel):
    word: str
    start: float
    end: float
    probability: float = 1.0


class TranscriptSegment(BaseModel):
    start: float
    end: float
    text: str
    words: list[WordTimestamp] = Field(default_factory=list)


class Transcript(BaseModel):
    language: str
    segments: list[TranscriptSegment]
    duration_s: float


class Scene(BaseModel):
    index: int
    start_s: float
    end_s: float

    @property
    def duration(self) -> float:
        return self.end_s - self.start_s

    @property
    def midpoint(self) -> float:
        return (self.start_s + self.end_s) / 2


class OcrDetection(BaseModel):
    frame_path: str
    timestamp_s: float
    text: str
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    confidence: float
    is_highlight: bool = Field(
        default=False,
        description="True if pixel color in bbox is yellow-ish (accent text)",
    )


class FrameDescription(BaseModel):
    frame_path: str
    timestamp_s: float
    description: str


class AggregatedBeat(BaseModel):
    """Pre-classification beat: raw data merged from all sources."""

    start_s: float
    end_s: float
    overlay_primary: str = ""
    overlay_highlight: str = ""
    transcript: str = ""
    visual_description: str = ""
