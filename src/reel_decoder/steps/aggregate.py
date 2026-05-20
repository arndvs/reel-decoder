"""Step 7: Aggregate — fuse transcript, OCR, and visual descriptions into beats.

This is the hardest step conceptually. Scene cuts ≠ beat boundaries. We use
overlay text changes as the primary beat boundary signal, and scene cuts as
secondary. The hook is always the first 1.5-2.5 seconds (we treat it specially).
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from rich.console import Console

from reel_decoder.schema import (
    AggregatedBeat,
    FrameDescription,
    OcrDetection,
    Scene,
    Transcript,
)
from reel_decoder.steps import is_done, mark_done

console = Console()


HOOK_END_S = 2.5  # everything before this is hook
MIN_BEAT_DURATION_S = 1.0  # collapse beats shorter than this into neighbors


def _group_ocr_by_window(
    detections: list[OcrDetection],
) -> dict[float, tuple[list[str], list[str]]]:
    """Group OCR detections by timestamp; return per-timestamp (primary, highlight) text lists.

    Returns {timestamp: (primary_texts, highlight_texts)}.
    """
    by_ts: dict[float, tuple[list[str], list[str]]] = defaultdict(lambda: ([], []))
    for d in detections:
        primary, highlight = by_ts[d.timestamp_s]
        if d.is_highlight:
            highlight.append(d.text)
        else:
            primary.append(d.text)
    return by_ts


def _consolidate_text_windows(
    by_ts: dict[float, tuple[list[str], list[str]]],
) -> list[tuple[float, str, str]]:
    """Walk timestamps in order, merge consecutive windows with the same text.

    Returns [(start_timestamp, primary_text, highlight_text), ...].
    """
    out: list[tuple[float, str, str]] = []
    for ts in sorted(by_ts.keys()):
        primary, highlight = by_ts[ts]
        p = " ".join(primary).strip()
        h = " ".join(highlight).strip()
        if out and out[-1][1] == p and out[-1][2] == h:
            continue  # same text continuing — skip
        out.append((ts, p, h))
    return out


def _transcript_in_range(transcript: Transcript, start: float, end: float) -> str:
    """Get transcript text that falls within [start, end]."""
    chunks = []
    for seg in transcript.segments:
        if seg.end < start or seg.start > end:
            continue
        chunks.append(seg.text)
    return " ".join(chunks).strip()


def _visual_for_range(
    visuals: list[FrameDescription], start: float, end: float
) -> str:
    """Combine visual descriptions whose timestamp falls inside the range."""
    matches = [v.description for v in visuals if start <= v.timestamp_s <= end]
    if matches:
        return " | ".join(matches)
    # Fall back to closest
    if visuals:
        closest = min(visuals, key=lambda v: abs(v.timestamp_s - (start + end) / 2))
        return closest.description
    return ""


def run(
    transcript: Transcript,
    scenes: list[Scene],
    ocr_detections: list[OcrDetection],
    visuals: list[FrameDescription],
    reel_dir: Path,
    duration_s: float,
) -> tuple[AggregatedBeat, list[AggregatedBeat]]:
    """Return (hook_beat, [beat, beat, ...]). Idempotent."""
    out_path = reel_dir / "aggregated.json"

    if is_done(reel_dir, "aggregate") and out_path.exists():
        console.log("[dim]aggregate: skipped[/dim]")
        data = json.loads(out_path.read_text())
        return (
            AggregatedBeat(**data["hook"]),
            [AggregatedBeat(**b) for b in data["beats"]],
        )

    by_ts = _group_ocr_by_window(ocr_detections)
    windows = _consolidate_text_windows(by_ts)

    # Build beat boundaries: each text-window change is a boundary
    # Add scene cuts as additional candidate boundaries (only if no text-window
    # change happened within 0.5s — otherwise it's just visual b-roll variation
    # within a beat).
    boundaries: list[float] = [0.0]
    for ts, _, _ in windows:
        if ts > boundaries[-1] + 0.4:
            boundaries.append(ts)
    for scene in scenes[1:]:
        cut = scene.start_s
        if not any(abs(cut - b) < 0.5 for b in boundaries):
            boundaries.append(cut)
    boundaries = sorted(set(boundaries))
    boundaries.append(duration_s)

    # Build candidate beats from boundaries
    candidates: list[tuple[float, float]] = []
    for i in range(len(boundaries) - 1):
        candidates.append((boundaries[i], boundaries[i + 1]))

    # Collapse beats shorter than MIN_BEAT_DURATION_S
    merged: list[tuple[float, float]] = []
    for start, end in candidates:
        if merged and (end - start) < MIN_BEAT_DURATION_S:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))

    # First beat is hook; remaining are beats
    def beat_for(start: float, end: float) -> AggregatedBeat:
        # Find the dominant overlay text for this range
        primary, highlight = "", ""
        for ts, p, h in windows:
            if start <= ts < end:
                if p and not primary:
                    primary = p
                if h and not highlight:
                    highlight = h
        return AggregatedBeat(
            start_s=start,
            end_s=end,
            overlay_primary=primary,
            overlay_highlight=highlight,
            transcript=_transcript_in_range(transcript, start, end),
            visual_description=_visual_for_range(visuals, start, end),
        )

    if not merged:
        # Degenerate — single-beat video
        hook = beat_for(0, min(HOOK_END_S, duration_s))
        if duration_s > HOOK_END_S:
            beats = [beat_for(HOOK_END_S, duration_s)]
        else:
            # Whole video is the hook; synthesise a minimal beat so schema validates
            beats = [beat_for(0, duration_s)]
    else:
        hook = beat_for(merged[0][0], merged[0][1])
        beats = [beat_for(s, e) for s, e in merged[1:]]
        if not beats:
            # Only one merged segment — duplicate as body beat
            beats = [beat_for(merged[0][0], merged[0][1])]

    # Cap to 6 beats — anything past that, merge the tail
    if len(beats) > 6:
        head = beats[:5]
        tail_start = beats[5].start_s
        tail_end = beats[-1].end_s
        tail = beat_for(tail_start, tail_end)
        beats = head + [tail]

    payload = {
        "hook": hook.model_dump(),
        "beats": [b.model_dump() for b in beats],
    }
    out_path.write_text(json.dumps(payload, indent=2))
    mark_done(reel_dir, "aggregate")
    console.log(f"aggregate: hook + {len(beats)} beats")
    return hook, beats
