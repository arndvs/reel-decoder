"""Pipeline orchestrator — wires all steps together for one reel."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from rich.console import Console

from reel_decoder.config import settings
from reel_decoder.schema import DecodedReel
from reel_decoder.steps import (
    aggregate,
    classify,
    frames,
    ingest,
    init_manifest,
    load_manifest,
    ocr,
    reset,
    save_manifest,
    scenes,
    transcribe,
    update_step,
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

    # Initialize run manifest
    manifest = init_manifest(reel_dir, reel_id, str(video_path), list(PIPELINE_STEPS))

    # Step 1: audio
    update_step(reel_dir, "ingest", "running")
    audio_path = ingest.run(video_path, reel_dir)
    duration_s = ingest.get_duration_s(video_path)
    update_step(reel_dir, "ingest", "done")

    # Step 2: transcribe
    update_step(reel_dir, "transcribe", "running")
    transcript = transcribe.run(audio_path, reel_dir)
    update_step(reel_dir, "transcribe", "done")

    # Step 3: scenes
    update_step(reel_dir, "scenes", "running")
    scene_list = scenes.run(video_path, reel_dir)
    update_step(reel_dir, "scenes", "done")

    # Step 4: keyframes
    update_step(reel_dir, "frames", "running")
    frame_pairs = frames.run(video_path, scene_list, reel_dir)
    update_step(reel_dir, "frames", "done")

    # Step 5: OCR
    update_step(reel_dir, "ocr", "running")
    ocr_dets = ocr.run(frame_pairs, reel_dir)
    update_step(reel_dir, "ocr", "done")

    # Step 6: vision
    update_step(reel_dir, "vision", "running")
    visuals = vision.run(scene_list, frame_pairs, reel_dir)
    update_step(reel_dir, "vision", "done")

    # Step 7: aggregate
    update_step(reel_dir, "aggregate", "running")
    hook, beats = aggregate.run(
        transcript, scene_list, ocr_dets, visuals, reel_dir, duration_s
    )
    update_step(reel_dir, "aggregate", "done")

    # Step 8: classify
    update_step(reel_dir, "classify", "running")
    decoded = classify.run(reel_id, video_path, hook, beats, duration_s, reel_dir)
    update_step(reel_dir, "classify", "done")

    # Step 9: write
    update_step(reel_dir, "write", "running")
    xlsx_writer.append_row(decoded, settings.swipe_library_path)
    update_step(reel_dir, "write", "done")

    # Finalize manifest
    manifest = load_manifest(reel_dir)
    if manifest is not None:
        manifest.finished_at = datetime.now(UTC)
        save_manifest(reel_dir, manifest)

    console.rule(f"[bold green]done: {reel_id}[/bold green]")
    return decoded
