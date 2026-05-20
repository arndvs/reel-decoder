"""Pipeline orchestrator — wires all steps together for one reel."""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import ollama
from rich.console import Console

from reel_decoder.config import settings
from reel_decoder.schema import DecodedReel, PipelineError
from reel_decoder.steps import (
    aggregate,
    classify,
    frames,
    ingest,
    init_manifest,
    is_done,
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


_SUPPORTED_EXTENSIONS = {".mp4", ".mov", ".webm", ".mkv", ".avi"}


def _preflight(video_path: Path) -> None:
    """Validate prerequisites before running the pipeline."""
    # 1. Supported format
    if video_path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        raise RuntimeError(
            f"Unsupported video format: {video_path.suffix}. "
            f"Supported: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
        )

    # 2. ffprobe can read the file
    try:
        subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration", str(video_path)],
            capture_output=True,
            check=True,
        )
    except FileNotFoundError:
        raise RuntimeError("ffprobe not found — install ffmpeg and ensure it's on PATH") from None
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"ffprobe cannot read {video_path}: {e.stderr.decode().strip()}") from e

    # 3. Ollama host responds and required models exist
    try:
        client = ollama.Client(host=settings.ollama_host)
        available = {m.model for m in client.list().models}
    except Exception as e:
        raise RuntimeError(f"Cannot connect to Ollama at {settings.ollama_host}: {e}") from e

    for model_name in (settings.vision_model, settings.classifier_model):
        if model_name not in available:
            raise RuntimeError(
                f"Ollama model {model_name!r} not found. "
                f"Run: ollama pull {model_name}"
            )


def decode_reel(video_path: Path, force_steps: list[str] | None = None) -> DecodedReel:
    """Run the full decoding pipeline for one reel. Returns the DecodedReel."""
    if not video_path.exists():
        raise FileNotFoundError(video_path)

    _preflight(video_path)

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
    init_manifest(reel_dir, reel_id, str(video_path), list(PIPELINE_STEPS))

    try:
        # Step 1: audio
        if is_done(reel_dir, "ingest"):
            update_step(reel_dir, "ingest", "skipped")
        else:
            update_step(reel_dir, "ingest", "running")
        audio_path = ingest.run(video_path, reel_dir)
        duration_s = ingest.get_duration_s(video_path)
        if not is_done(reel_dir, "ingest"):
            update_step(reel_dir, "ingest", "done")

        # Step 2: transcribe
        if is_done(reel_dir, "transcribe"):
            update_step(reel_dir, "transcribe", "skipped")
        else:
            update_step(reel_dir, "transcribe", "running")
        transcript = transcribe.run(audio_path, reel_dir)
        if not is_done(reel_dir, "transcribe"):
            update_step(reel_dir, "transcribe", "done")

        # Step 3: scenes
        if is_done(reel_dir, "scenes"):
            update_step(reel_dir, "scenes", "skipped")
        else:
            update_step(reel_dir, "scenes", "running")
        scene_list = scenes.run(video_path, reel_dir)
        if not is_done(reel_dir, "scenes"):
            update_step(reel_dir, "scenes", "done")

        # Step 4: keyframes
        if is_done(reel_dir, "frames"):
            update_step(reel_dir, "frames", "skipped")
        else:
            update_step(reel_dir, "frames", "running")
        frame_pairs = frames.run(video_path, scene_list, reel_dir)
        if not is_done(reel_dir, "frames"):
            update_step(reel_dir, "frames", "done")

        # Step 5: OCR
        if is_done(reel_dir, "ocr"):
            update_step(reel_dir, "ocr", "skipped")
        else:
            update_step(reel_dir, "ocr", "running")
        ocr_dets = ocr.run(frame_pairs, reel_dir)
        if not is_done(reel_dir, "ocr"):
            update_step(reel_dir, "ocr", "done")

        # Step 6: vision
        if is_done(reel_dir, "vision"):
            update_step(reel_dir, "vision", "skipped")
        else:
            update_step(reel_dir, "vision", "running")
        visuals = vision.run(scene_list, frame_pairs, reel_dir)
        if not is_done(reel_dir, "vision"):
            update_step(reel_dir, "vision", "done")

        # Step 7: aggregate
        if is_done(reel_dir, "aggregate"):
            update_step(reel_dir, "aggregate", "skipped")
        else:
            update_step(reel_dir, "aggregate", "running")
        hook, beats = aggregate.run(
            transcript, scene_list, ocr_dets, visuals, reel_dir, duration_s
        )
        if not is_done(reel_dir, "aggregate"):
            update_step(reel_dir, "aggregate", "done")

        # Step 8: classify
        if is_done(reel_dir, "classify"):
            update_step(reel_dir, "classify", "skipped")
        else:
            update_step(reel_dir, "classify", "running")
        decoded = classify.run(reel_id, video_path, hook, beats, duration_s, reel_dir)
        if not is_done(reel_dir, "classify"):
            update_step(reel_dir, "classify", "done")

        # Step 9: write
        update_step(reel_dir, "write", "running")
        xlsx_writer.append_row(decoded, settings.swipe_library_path)
        update_step(reel_dir, "write", "done")

    except Exception as exc:
        # Mark the currently-running step as failed
        failed_manifest = load_manifest(reel_dir)
        if failed_manifest is not None:
            for s in failed_manifest.steps:
                if s.status == "running":
                    error = PipelineError(
                        code="unknown",
                        message=str(exc),
                        step=s.name,
                    )
                    update_step(reel_dir, s.name, "failed", error=error)
                    break
            failed_manifest = load_manifest(reel_dir)
            if failed_manifest is not None:
                failed_manifest.finished_at = datetime.now(UTC)
                save_manifest(reel_dir, failed_manifest)
        raise

    # Finalize manifest
    manifest = load_manifest(reel_dir)
    if manifest is not None:
        manifest.finished_at = datetime.now(UTC)
        save_manifest(reel_dir, manifest)

    console.rule(f"[bold green]done: {reel_id}[/bold green]")
    return decoded
