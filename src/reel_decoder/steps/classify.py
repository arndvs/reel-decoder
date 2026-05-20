"""Step 8: Classify — local LLM produces a schema-compliant DecodedReel JSON.

Uses Ollama with format=json to force valid JSON output. The model gets the
aggregated beats and is asked to identify the hook pattern, beat types,
mechanism line, payoff visual, and a "why it works" sentence.
"""

from __future__ import annotations

import json
from pathlib import Path

import ollama
from pydantic import ValidationError
from rich.console import Console

from reel_decoder.config import settings
from reel_decoder.prompt_loader import load_prompt
from reel_decoder.schema import AggregatedBeat, DecodedReel, PipelineError
from reel_decoder.steps import is_done, mark_done

console = Console()


def _format_beats_block(beats: list[AggregatedBeat]) -> str:
    lines = []
    for i, b in enumerate(beats, start=1):
        lines.append(
            f"Beat {i} ({b.start_s:.1f}s - {b.end_s:.1f}s):\n"
            f"  Overlay primary: {b.overlay_primary!r}\n"
            f"  Overlay highlight: {b.overlay_highlight!r}\n"
            f"  Transcript: {b.transcript!r}\n"
            f"  Visual: {b.visual_description!r}"
        )
    return "\n\n".join(lines)


def run(
    reel_id: str,
    source_path: Path,
    hook: AggregatedBeat,
    beats: list[AggregatedBeat],
    duration_s: float,
    reel_dir: Path,
) -> DecodedReel:
    out_path = reel_dir / "decoded.json"

    if is_done(reel_dir, "classify") and out_path.exists():
        console.log("[dim]classify: skipped[/dim]")
        return DecodedReel.model_validate_json(out_path.read_text())

    prompt = load_prompt("classify").format(
        reel_id=reel_id,
        source_path=str(source_path),
        duration_s=round(duration_s, 1),
        hook_end_s=round(hook.end_s, 2),
        hook_primary=hook.overlay_primary or "",
        hook_highlight=hook.overlay_highlight or "",
        hook_transcript=hook.transcript or "",
        hook_visual=hook.visual_description or "",
        beats_block=_format_beats_block(beats),
    )

    client = ollama.Client(host=settings.ollama_host)
    console.log(f"classify: calling {settings.classifier_model}")

    resp = client.chat(
        model=settings.classifier_model,
        messages=[{"role": "user", "content": prompt}],
        format="json",
        options={"temperature": 0.1},
    )
    raw = resp.message.content

    try:
        data = json.loads(raw)
        decoded = DecodedReel.model_validate(data)
    except (json.JSONDecodeError, ValidationError) as e:
        # Save the raw output for debugging and re-raise with context
        (reel_dir / "classify_raw.txt").write_text(raw)
        error = PipelineError(
            code="llm_parse_error",
            message=f"LLM returned invalid JSON / failed schema: {e}",
            step="classify",
            details=raw[:500],
            retryable=True,
        )
        raise RuntimeError(
            f"classify: {error.message}\n"
            f"Raw output saved to {reel_dir / 'classify_raw.txt'}"
        ) from e

    out_path.write_text(decoded.model_dump_json(indent=2))
    mark_done(reel_dir, "classify")
    return decoded
