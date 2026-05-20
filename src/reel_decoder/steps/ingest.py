"""Step 1: Ingest — extract audio from video using ffmpeg."""

from __future__ import annotations

import subprocess
from pathlib import Path

from rich.console import Console

from reel_decoder.steps import is_done, mark_done

console = Console()


def run(video_path: Path, reel_dir: Path) -> Path:
    """Extract 16kHz mono WAV from video. Idempotent."""
    audio_path = reel_dir / "audio.wav"

    if is_done(reel_dir, "ingest") and audio_path.exists():
        console.log(f"[dim]ingest: skipped ({audio_path.name} exists)[/dim]")
        return audio_path

    reel_dir.mkdir(parents=True, exist_ok=True)
    console.log(f"ingest: extracting audio from {video_path.name}")

    # 16kHz mono WAV — what faster-whisper wants
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        str(audio_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg failed:\n{result.stderr}")

    mark_done(reel_dir, "ingest")
    return audio_path


def get_duration_s(video_path: Path) -> float:
    """Return the duration of a video file in seconds, using ffprobe."""
    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(video_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe failed:\n{result.stderr}")
    return float(result.stdout.strip())
