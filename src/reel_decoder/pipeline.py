"""Pipeline orchestrator — wires all steps together for one reel."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from reel_decoder.config import settings
from reel_decoder.schema import DecodedReel
from reel_decoder.steps import (
    aggregate,
    classify,
    frames,
    ingest,
    ocr,
    reset,
    scenes,
    transcribe,
    vision,
)
from reel_decoder.writers import xlsx_writer

console = Console()


PIPELINE_STEPS = (
    "ingest",
    "transcribe",
    "scenes",
    "frames",
    "ocr",
    "vision",
    "aggregate",
    "classify",
    "write",
)


def decode_reel(video_path: Path, force_steps: list[str] | None = None) -> DecodedReel:
    """Run the full decoding pipeline for one reel. Returns the DecodedReel."""
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    reel_id = video_path.stem
    reel_dir = settings.reel_dir(reel_id)
    reel_dir.mkdir(parents=True, exist_ok=True)

    # Reset sentinels for forced steps
    for step in force_steps or []:
        if step not in PIPELINE_STEPS:
            raise ValueError(f"Unknown step: {step!r}. Valid: {PIPELINE_STEPS}")
        reset(reel_dir, step)
        console.log(f"[yellow]forced re-run: {step}[/yellow]")

    console.rule(f"[bold cyan]decoding {reel_id}[/bold cyan]")

    # Step 1: audio
    audio_path = ingest.run(video_path, reel_dir)
    duration_s = ingest.get_duration_s(video_path)

    # Step 2: transcribe
    transcript = transcribe.run(audio_path, reel_dir)

    # Step 3: scenes
    scene_list = scenes.run(video_path, reel_dir)

    # Step 4: keyframes
    frame_pairs = frames.run(video_path, scene_list, reel_dir)

    # Step 5: OCR
    ocr_dets = ocr.run(frame_pairs, reel_dir)

    # Step 6: vision
    visuals = vision.run(scene_list, frame_pairs, reel_dir)

    # Step 7: aggregate
    hook, beats = aggregate.run(
        transcript, scene_list, ocr_dets, visuals, reel_dir, duration_s
    )

    # Step 8: classify
    decoded = classify.run(reel_id, video_path, hook, beats, duration_s, reel_dir)

    # Step 9: write
    xlsx_writer.append_row(decoded, settings.swipe_library_path)

    console.rule(f"[bold green]done: {reel_id}[/bold green]")
    return decoded
