"""Step 3: Scenes — detect cut boundaries with PySceneDetect."""

from __future__ import annotations

import json
from pathlib import Path

from rich.console import Console
from scenedetect import ContentDetector, SceneManager, open_video

from reel_decoder.config import settings
from reel_decoder.schema import Scene
from reel_decoder.steps import is_done, mark_done

console = Console()


def run(video_path: Path, reel_dir: Path) -> list[Scene]:
    """Detect scene cuts. Returns a list of Scene objects. Idempotent."""
    out_path = reel_dir / "scenes.json"

    if is_done(reel_dir, "scenes") and out_path.exists():
        console.log("[dim]scenes: skipped[/dim]")
        data = json.loads(out_path.read_text())
        return [Scene(**s) for s in data]

    console.log(f"scenes: detecting cuts (threshold={settings.scene_threshold})")
    video = open_video(str(video_path))
    sm = SceneManager()
    sm.add_detector(ContentDetector(threshold=settings.scene_threshold))
    sm.detect_scenes(video, show_progress=False)
    scene_list = sm.get_scene_list()

    scenes: list[Scene] = []
    if not scene_list:
        # Single-scene reel — make one scene covering the whole duration
        from reel_decoder.steps.ingest import get_duration_s

        duration = get_duration_s(video_path)
        scenes = [Scene(index=1, start_s=0.0, end_s=duration)]
    else:
        for i, (start, end) in enumerate(scene_list, start=1):
            scenes.append(
                Scene(
                    index=i,
                    start_s=start.get_seconds(),
                    end_s=end.get_seconds(),
                )
            )

    out_path.write_text(json.dumps([s.model_dump() for s in scenes], indent=2))
    mark_done(reel_dir, "scenes")
    console.log(f"scenes: {len(scenes)} detected")
    return scenes
