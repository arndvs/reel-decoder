"""Pipeline step utilities — idempotency helpers and run manifest."""

from __future__ import annotations

import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from pydantic import ValidationError
from rich.console import Console

from reel_decoder.schema import PipelineError, RunManifest, StepStatus

console = Console()

MANIFEST_FILENAME = "run_manifest.json"


def is_done(reel_dir: Path, step: str) -> bool:
    """Has this step completed for this reel?

    Checks the manifest first, falls back to sentinel files.
    """
    manifest = load_manifest(reel_dir)
    if manifest is not None:
        for s in manifest.steps:
            if s.name == step and s.status in ("done", "skipped"):
                return True
    return (reel_dir / f".{step}.done").exists()


def mark_done(reel_dir: Path, step: str) -> None:
    reel_dir.mkdir(parents=True, exist_ok=True)
    (reel_dir / f".{step}.done").touch()
    # Also update manifest if it exists
    manifest = load_manifest(reel_dir)
    if manifest is not None:
        update_step(reel_dir, step, "done")


def reset(reel_dir: Path, step: str) -> None:
    sentinel = reel_dir / f".{step}.done"
    if sentinel.exists():
        sentinel.unlink()


def load_manifest(reel_dir: Path) -> RunManifest | None:
    """Load the run manifest from disk, or None if it doesn't exist or is malformed."""
    path = reel_dir / MANIFEST_FILENAME
    if not path.exists():
        return None
    try:
        return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))
    except (ValidationError, ValueError):
        console.log(f"[yellow]manifest: corrupt file at {path} — ignoring[/yellow]")
        return None


def save_manifest(reel_dir: Path, manifest: RunManifest) -> None:
    """Write the run manifest to disk atomically."""
    reel_dir.mkdir(parents=True, exist_ok=True)
    path = reel_dir / MANIFEST_FILENAME
    data = manifest.model_dump_json(indent=2)
    tmp = tempfile.NamedTemporaryFile(  # noqa: SIM115
        mode="w", dir=reel_dir, suffix=".tmp", delete=False, encoding="utf-8",
    )
    try:
        tmp.write(data)
        tmp.close()
        Path(tmp.name).replace(path)
    except BaseException:
        tmp.close()
        Path(tmp.name).unlink(missing_ok=True)
        raise


def init_manifest(reel_dir: Path, reel_id: str, source_path: str, step_names: list[str]) -> RunManifest:
    """Create a fresh manifest with all steps in pending state."""
    manifest = RunManifest(
        reel_id=reel_id,
        source_path=source_path,
        steps=[StepStatus(name=name) for name in step_names],
    )
    save_manifest(reel_dir, manifest)
    return manifest


StepStatusValue = Literal["pending", "running", "done", "failed", "skipped"]


def update_step(
    reel_dir: Path,
    step_name: str,
    status: StepStatusValue,
    error: PipelineError | None = None,
) -> None:
    """Update a step's status in the manifest."""
    manifest = load_manifest(reel_dir)
    if manifest is None:
        return
    now = datetime.now(UTC)
    for s in manifest.steps:
        if s.name == step_name:
            s.status = status
            if status == "running":
                s.started_at = now
            elif status in ("done", "failed", "skipped"):
                s.finished_at = now
            if error is not None:
                s.error = error
                manifest.errors.append(error)
            break
    save_manifest(reel_dir, manifest)
