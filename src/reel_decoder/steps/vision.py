"""Step 6: Vision — describe each scene-midpoint frame using a local VLM via Ollama.

We only describe one frame per scene (the midpoint), not every keyframe.
Per-scene descriptions are what feed the classifier; per-keyframe would be
wasteful and slow.
"""

from __future__ import annotations

import base64
import json
from pathlib import Path

import ollama
from rich.console import Console

from reel_decoder.config import settings
from reel_decoder.prompt_loader import load_prompt
from reel_decoder.schema import FrameDescription, Scene
from reel_decoder.steps import is_done, mark_done

console = Console()


PROMPT = load_prompt("vision")


def _find_closest_frame(scene: Scene, frame_pairs: list[tuple[float, Path]]) -> Path | None:
    if not frame_pairs:
        return None
    target = scene.midpoint
    closest = min(frame_pairs, key=lambda p: abs(p[0] - target))
    return closest[1]


def run(
    scenes: list[Scene],
    frame_pairs: list[tuple[float, Path]],
    reel_dir: Path,
) -> list[FrameDescription]:
    out_path = reel_dir / "visual_descriptions.json"

    if is_done(reel_dir, "vision") and out_path.exists():
        console.log("[dim]vision: skipped[/dim]")
        data = json.loads(out_path.read_text())
        return [FrameDescription(**d) for d in data]

    client = ollama.Client(host=settings.ollama_host)
    console.log(f"vision: describing {len(scenes)} scene midpoints with {settings.vision_model}")

    descriptions: list[FrameDescription] = []
    for scene in scenes:
        frame = _find_closest_frame(scene, frame_pairs)
        if frame is None:
            continue
        try:
            image_bytes = frame.read_bytes()
            image_b64 = base64.b64encode(image_bytes).decode("utf-8")
            resp = client.chat(
                model=settings.vision_model,
                messages=[
                    {
                        "role": "user",
                        "content": PROMPT,
                        "images": [image_b64],
                    }
                ],
                options={"temperature": 0.2},
            )
            desc = resp.message.content.strip()
        except Exception as e:  # noqa: BLE001
            console.log(f"[yellow]vision: failed scene {scene.index}: {e}[/yellow]")
            desc = ""

        descriptions.append(
            FrameDescription(
                frame_path=str(frame),
                timestamp_s=scene.midpoint,
                description=desc,
            )
        )

    out_path.write_text(json.dumps([d.model_dump() for d in descriptions], indent=2))
    mark_done(reel_dir, "vision")
    return descriptions
