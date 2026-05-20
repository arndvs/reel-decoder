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
from reel_decoder.schema import AggregatedBeat, DecodedReel
from reel_decoder.steps import is_done, mark_done

console = Console()


PROMPT_TEMPLATE = """You are decoding a short-form social video into structured metadata.

Below is the aggregated data for one reel: a hook beat and a sequence of body beats.
Each beat has overlay text (primary white text + highlight yellow text),
the spoken transcript that fell during that beat, and a visual description.

Your job: produce a JSON object matching this exact schema.

SCHEMA (return ONLY this JSON, no markdown, no commentary):

{{
  "reel_id": "{reel_id}",
  "source_path": "{source_path}",
  "creator": "",
  "niche": "<one of: Supplements, Fitness, Finance, Beauty, Food, Productivity, Lifestyle, Other>",
  "hook": {{
    "pattern": "<one of: Rarity | Contrarian | Stat | Problem/Agitate | Authority | Transformation | Question | Demonstration>",
    "text": "<exact words on screen during hook, preserving capitalization>",
    "visual": "<one sentence describing what's shown during the hook>",
    "start_s": 0.0,
    "end_s": <hook end in seconds>
  }},
  "beats": [
    {{
      "index": 1,
      "type": "<one of: Benefit | Mechanism | Aspiration | Social Proof | Demonstration | Reveal>",
      "primary_text": "<white text overlay, max 80 chars>",
      "highlight_text": "<yellow text overlay, max 40 chars>",
      "visual": "<one sentence>",
      "start_s": <number>,
      "end_s": <number>
    }}
  ],
  "mechanism_line": "<the 'because science' line if present (names a chemical, study, or biological process); otherwise empty string>",
  "payoff_visual": "<one sentence describing the final aspirational shot>",
  "cta": "<call to action if any, otherwise empty string>",
  "length_s": {duration_s},
  "music_vibe": "<one of: Ambient | Driving/EDM | Cinematic | Hip-Hop | Pop | None/Silent>",
  "caption_style": "<one of: Karaoke | Static cards | Voiceover only | Mixed>",
  "why_it_works": "<one sentence explaining what makes this reel effective>",
  "stop_scroll_rating": <integer 1-5>,
  "notes": ""
}}

HOOK PATTERN GUIDE:
- Rarity: frames the subject as scarce/unique ("rarest", "only 1%")
- Contrarian: tells viewer to stop a common behavior ("stop doing X")
- Stat: opens with a number ("99%", "3 minutes")
- Problem/Agitate: names a pain point ("tired by 2pm?")
- Authority: cites credentials/studies ("Harvard found", "Navy SEALs use")
- Transformation: promises change ("I added X to my routine")
- Question: direct question ("why do monks live to 100?")
- Demonstration: shows the thing happening ("watch what happens")

BEAT TYPE GUIDE:
- Benefit: a claim about what the viewer gets ("strengthens immunity")
- Mechanism: the "because science" line naming a chemical/process ("adenosine optimizes oxygen flow")
- Aspiration: future-state framing ("for peak performance", "for better defense")
- Social Proof: testimonial or implied proof others use it
- Demonstration: visual proof of process or transformation
- Reveal: the moment the product appears for the first time

DATA:

Reel duration: {duration_s} seconds

HOOK (0.0s - {hook_end_s}s):
  Overlay primary: {hook_primary}
  Overlay highlight: {hook_highlight}
  Transcript: {hook_transcript}
  Visual: {hook_visual}

BODY BEATS:
{beats_block}

Return ONLY the JSON. No markdown fences. No explanation.
"""


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

    prompt = PROMPT_TEMPLATE.format(
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
        raise RuntimeError(
            f"classify: LLM returned invalid JSON / failed schema.\n"
            f"Raw output saved to {reel_dir / 'classify_raw.txt'}\n"
            f"Error: {e}"
        ) from e

    out_path.write_text(decoded.model_dump_json(indent=2))
    mark_done(reel_dir, "classify")
    return decoded
