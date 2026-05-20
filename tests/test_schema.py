"""Tests for the schema — pure unit tests, no external deps."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from reel_decoder.schema import (
    Beat,
    BeatType,
    CaptionStyle,
    DecodedReel,
    Hook,
    HookPattern,
    MusicVibe,
)


def make_minimal_decoded() -> DecodedReel:
    return DecodedReel(
        reel_id="test-reel",
        source_path="inputs/reels/test-reel.mp4",
        hook=Hook(
            pattern=HookPattern.rarity,
            text="Rarest ingredient on earth",
            visual="Close-up pour of dark tea",
            start_s=0.0,
            end_s=2.0,
        ),
        beats=[
            Beat(
                index=1,
                type=BeatType.benefit,
                primary_text="Strengthen",
                highlight_text="immunity",
                visual="Liquid pouring into mug",
                start_s=2.0,
                end_s=4.5,
            ),
            Beat(
                index=2,
                type=BeatType.mechanism,
                primary_text="Adenosine optimizes",
                highlight_text="oxygen flow",
                visual="Older hiker on summit",
                start_s=4.5,
                end_s=8.0,
            ),
        ],
        mechanism_line="Adenosine optimizes oxygen flow",
        payoff_visual="Older hiker at sunset on mountain summit",
        length_s=14.0,
        music_vibe=MusicVibe.cinematic,
        caption_style=CaptionStyle.mixed,
        why_it_works="Curiosity-gap hook plus 3-benefit stack plus science credibility",
        stop_scroll_rating=5,
    )


def test_minimal_decoded_validates():
    decoded = make_minimal_decoded()
    assert decoded.hook.pattern == HookPattern.rarity
    assert len(decoded.beats) == 2


def test_end_before_start_rejected():
    with pytest.raises(ValidationError):
        Beat(
            index=1,
            type=BeatType.benefit,
            primary_text="x",
            highlight_text="y",
            visual="z",
            start_s=5.0,
            end_s=2.0,
        )


def test_to_xlsx_row_shape():
    decoded = make_minimal_decoded()
    row = decoded.to_xlsx_row()
    # Expected length: 29 columns to match the Swipe Library schema
    assert len(row) == 29
    # Date is in column 2 (index 1)
    assert row[1] == date.today()
    # Hook pattern in column 6 (index 5)
    assert row[5] == "Rarity"
    # Hook text in column 7
    assert row[6] == "Rarest ingredient on earth"
    # Beat 1 text in column 9
    assert row[8] == "Strengthen"
    assert row[9] == "Benefit"


def test_to_xlsx_row_pads_empty_beats():
    decoded = make_minimal_decoded()  # only 2 beats
    row = decoded.to_xlsx_row()
    # Beats 3 and 4 should be empty strings (12 slots starting at col 9)
    # Beat 3 text = column 15 (index 14)
    assert row[14] == ""
    assert row[15] == ""
    assert row[16] == ""
    # Beat 4
    assert row[17] == ""


def test_stop_scroll_range():
    with pytest.raises(ValidationError):
        DecodedReel(
            reel_id="x",
            source_path="y",
            hook=Hook(pattern=HookPattern.rarity, text="t", end_s=1.0),
            beats=[
                Beat(
                    index=1,
                    type=BeatType.benefit,
                    primary_text="x",
                    visual="x",
                    start_s=1.0,
                    end_s=2.0,
                )
            ],
            length_s=2.0,
            stop_scroll_rating=99,
        )


def test_too_many_beats_rejected():
    base = make_minimal_decoded()
    extra_beats = [
        Beat(
            index=i,
            type=BeatType.benefit,
            primary_text="t",
            visual="v",
            start_s=float(i),
            end_s=float(i + 1),
        )
        for i in range(1, 8)
    ]
    with pytest.raises(ValidationError):
        DecodedReel(
            reel_id=base.reel_id,
            source_path=base.source_path,
            hook=base.hook,
            beats=extra_beats,
            length_s=10.0,
        )
