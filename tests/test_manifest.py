"""Tests for run manifest and step helpers."""

from __future__ import annotations

from reel_decoder.steps import (
    init_manifest,
    is_done,
    load_manifest,
    mark_done,
    update_step,
)


def test_manifest_step_transitions(tmp_path):
    reel_dir = tmp_path / "reel-1"
    reel_dir.mkdir()

    manifest = init_manifest(reel_dir, "reel-1", "inputs/reels/reel-1.mp4", ["ingest", "transcribe"])

    assert len(manifest.steps) == 2
    assert manifest.steps[0].status == "pending"

    update_step(reel_dir, "ingest", "running")
    manifest = load_manifest(reel_dir)
    assert manifest.steps[0].status == "running"
    assert manifest.steps[0].started_at is not None

    update_step(reel_dir, "ingest", "done")
    manifest = load_manifest(reel_dir)
    assert manifest.steps[0].status == "done"
    assert manifest.steps[0].finished_at is not None


def test_is_done_reads_manifest(tmp_path):
    reel_dir = tmp_path / "reel-2"
    reel_dir.mkdir()

    init_manifest(reel_dir, "reel-2", "inputs/reels/reel-2.mp4", ["ingest"])
    assert not is_done(reel_dir, "ingest")

    update_step(reel_dir, "ingest", "done")
    assert is_done(reel_dir, "ingest")


def test_mark_done_updates_manifest(tmp_path):
    reel_dir = tmp_path / "reel-3"
    reel_dir.mkdir()

    init_manifest(reel_dir, "reel-3", "inputs/reels/reel-3.mp4", ["ocr"])
    mark_done(reel_dir, "ocr")

    manifest = load_manifest(reel_dir)
    assert manifest.steps[0].status == "done"
    # Sentinel file also created
    assert (reel_dir / ".ocr.done").exists()


def test_is_done_falls_back_to_sentinel(tmp_path):
    reel_dir = tmp_path / "reel-4"
    reel_dir.mkdir()

    # No manifest — fall back to sentinel
    assert not is_done(reel_dir, "ingest")
    (reel_dir / ".ingest.done").touch()
    assert is_done(reel_dir, "ingest")
