"""Tests for aggregate helpers — pure logic, no external deps."""

from __future__ import annotations

from reel_decoder.schema import OcrDetection
from reel_decoder.steps.aggregate import _consolidate_text_windows, _group_ocr_by_window


def make_det(ts: float, text: str, highlight: bool = False) -> OcrDetection:
    return OcrDetection(
        frame_path=f"frames/{ts}.jpg",
        timestamp_s=ts,
        text=text,
        bbox=(0, 0, 100, 50),
        confidence=0.9,
        is_highlight=highlight,
    )


def test_group_ocr_by_window_separates_primary_and_highlight():
    dets = [
        make_det(1.0, "STRENGTHEN", highlight=False),
        make_det(1.0, "immunity", highlight=True),
        make_det(2.0, "FOR", highlight=False),
        make_det(2.0, "Better Defense", highlight=True),
    ]
    grouped = _group_ocr_by_window(dets)
    assert grouped[1.0] == (["STRENGTHEN"], ["immunity"])
    assert grouped[2.0] == (["FOR"], ["Better Defense"])


def test_consolidate_text_windows_dedupes_consecutive_duplicates():
    dets = [
        make_det(1.0, "STRENGTHEN", highlight=False),
        make_det(1.0, "immunity", highlight=True),
        make_det(1.5, "STRENGTHEN", highlight=False),
        make_det(1.5, "immunity", highlight=True),
        make_det(3.0, "FOR", highlight=False),
        make_det(3.0, "Better Defense", highlight=True),
    ]
    grouped = _group_ocr_by_window(dets)
    consolidated = _consolidate_text_windows(grouped)
    # Should collapse the two identical 1.0 / 1.5 windows
    assert len(consolidated) == 2
    assert consolidated[0] == (1.0, "STRENGTHEN", "immunity")
    assert consolidated[1] == (3.0, "FOR", "Better Defense")
