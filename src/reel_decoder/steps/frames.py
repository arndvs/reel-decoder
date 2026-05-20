"""Step 4: Frames — sample keyframes from the video.

Strategy: 2 fps baseline sampling + the midpoint of every detected scene.
Deduplicate within 0.3s windows so we don't double-sample.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from rich.console import Console

from reel_decoder.config import settings
from reel_decoder.schema import Scene
from reel_decoder.steps import is_done, mark_done

console = Console()


def run(video_path: Path, scenes: list[Scene], reel_dir: Path) -> list[tuple[float, Path]]:
    """Extract keyframes. Returns [(timestamp_s, frame_path), ...]. Idempotent."""
    frames_dir = reel_dir / "frames"
    manifest_path = reel_dir / "frames_manifest.json"

    if is_done(reel_dir, "frames") and manifest_path.exists():
        console.log("[dim]frames: skipped[/dim]")
        data = json.loads(manifest_path.read_text())
        return [(t, Path(p)) for t, p in data]

    frames_dir.mkdir(exist_ok=True)
    for f in frames_dir.glob("*.jpg"):
        f.unlink()

    from reel_decoder.steps.ingest import get_duration_s

    duration = get_duration_s(video_path)

    # Collect target timestamps
    fps = settings.frame_sample_fps
    timestamps = set()
    t = 0.0
    while t < duration:
        timestamps.add(round(t, 2))
        t += 1.0 / fps
    for scene in scenes:
        timestamps.add(round(scene.midpoint, 2))

    # Sort and dedupe near-duplicates
    sorted_ts = sorted(timestamps)
    deduped: list[float] = []
    for ts in sorted_ts:
        if not deduped or ts - deduped[-1] >= 0.3:
            deduped.append(ts)

    console.log(f"frames: extracting {len(deduped)} keyframes")

    # Use ffmpeg with a select filter — one call instead of N
    # Use between() with ±0.02s tolerance to avoid floating-point misses
    select_expr = "+".join(f"between(t\\,{ts - 0.02:.3f}\\,{ts + 0.02:.3f})" for ts in deduped)
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-vf",
        f"select='{select_expr}',scale=720:-2",
        "-vsync",
        "vfr",
        "-q:v",
        "3",
        str(frames_dir / "frame_%04d.jpg"),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg frame extraction failed:\n{result.stderr}")

    # Match extracted files to timestamps (ffmpeg outputs in temporal order)
    files = sorted(frames_dir.glob("frame_*.jpg"))
    if len(files) != len(deduped):
        console.log(
            f"[yellow]warn: requested {len(deduped)} frames, got {len(files)}[/yellow]"
        )
    pairs = list(zip(deduped, files, strict=False))

    manifest_path.write_text(json.dumps([[t, str(p)] for t, p in pairs], indent=2))
    mark_done(reel_dir, "frames")
    return pairs
