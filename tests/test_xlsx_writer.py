"""Tests for xlsx_writer — dedup guard and row formatting."""

from __future__ import annotations

from pathlib import Path

from reel_decoder.schema import (
    Beat,
    BeatType,
    CaptionStyle,
    DecodedReel,
    Hook,
    HookPattern,
    MusicVibe,
)
from reel_decoder.writers.xlsx_writer import append_row


def _make_decoded(source_path: str = "inputs/reels/test.mp4") -> DecodedReel:
    return DecodedReel(
        reel_id="test",
        source_path=source_path,
        hook=Hook(pattern=HookPattern.rarity, text="Hook", end_s=2.0),
        beats=[
            Beat(
                index=1,
                type=BeatType.benefit,
                primary_text="t",
                visual="v",
                start_s=2.0,
                end_s=4.0,
            ),
        ],
        length_s=4.0,
        music_vibe=MusicVibe.ambient,
        caption_style=CaptionStyle.karaoke,
    )


def test_append_row_dedup(tmp_path: Path):
    xlsx = tmp_path / "test.xlsx"
    decoded = _make_decoded()

    row1 = append_row(decoded, xlsx)
    row2 = append_row(decoded, xlsx)

    assert row1 == 2  # first data row
    assert row2 == 2  # same row returned, not appended


def test_append_row_different_sources(tmp_path: Path):
    xlsx = tmp_path / "test.xlsx"

    row1 = append_row(_make_decoded("inputs/reels/a.mp4"), xlsx)
    row2 = append_row(_make_decoded("inputs/reels/b.mp4"), xlsx)

    assert row1 == 2
    assert row2 == 3  # new row
