"""Pipeline step utilities — idempotency helpers and run manifest."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from reel_decoder.schema import PipelineError, RunManifest, StepStatus

MANIFEST_FILENAME = "run_manifest.json"


def is_done(reel_dir: Path, step: str) -> bool:
    """Has this step completed for this reel?

    Checks the manifest first, falls back to sentinel files.
    """
    manifest = load_manifest(reel_dir)
    if manifest is not None:
        for s in manifest.steps:
            if s.name == step and s.status == "done":
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
    """Load the run manifest from disk, or None if it doesn't exist."""
    path = reel_dir / MANIFEST_FILENAME
    if not path.exists():
        return None
    return RunManifest.model_validate_json(path.read_text(encoding="utf-8"))


def save_manifest(reel_dir: Path, manifest: RunManifest) -> None:
    """Write the run manifest to disk."""
    reel_dir.mkdir(parents=True, exist_ok=True)
    path = reel_dir / MANIFEST_FILENAME
    path.write_text(manifest.model_dump_json(indent=2), encoding="utf-8")


def init_manifest(reel_dir: Path, reel_id: str, source_path: str, step_names: list[str]) -> RunManifest:
    """Create a fresh manifest with all steps in pending state."""
    manifest = RunManifest(
        reel_id=reel_id,
        source_path=source_path,
        steps=[StepStatus(name=name) for name in step_names],
    )
    save_manifest(reel_dir, manifest)
    return manifest


def update_step(
    reel_dir: Path,
    step_name: str,
    status: str,
    error: PipelineError | None = None,
) -> None:
    """Update a step's status in the manifest."""
    manifest = load_manifest(reel_dir)
    if manifest is None:
        return
    now = datetime.now(UTC)
    for s in manifest.steps:
        if s.name == step_name:
            s.status = status  # type: ignore[assignment]
            if status == "running":
                s.started_at = now
            elif status in ("done", "failed", "skipped"):
                s.finished_at = now
            if error is not None:
                s.error = error
                manifest.errors.append(error)
            break
    save_manifest(reel_dir, manifest)
