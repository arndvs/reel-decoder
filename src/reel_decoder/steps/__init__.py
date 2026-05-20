"""Pipeline step utilities — idempotency helpers."""

from __future__ import annotations

from pathlib import Path


def is_done(reel_dir: Path, step: str) -> bool:
    """Has this step completed for this reel?"""
    return (reel_dir / f".{step}.done").exists()


def mark_done(reel_dir: Path, step: str) -> None:
    reel_dir.mkdir(parents=True, exist_ok=True)
    (reel_dir / f".{step}.done").touch()


def reset(reel_dir: Path, step: str) -> None:
    sentinel = reel_dir / f".{step}.done"
    if sentinel.exists():
        sentinel.unlink()
