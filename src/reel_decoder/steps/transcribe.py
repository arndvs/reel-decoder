"""Step 2: Transcribe — faster-whisper with word-level timestamps."""

from __future__ import annotations

from pathlib import Path

from rich.console import Console

from reel_decoder.config import settings
from reel_decoder.schema import Transcript, TranscriptSegment, WordTimestamp
from reel_decoder.steps import is_done, mark_done

console = Console()


_model_cache = {}


def _get_model():
    """Lazy-load and cache the Whisper model."""
    from faster_whisper import WhisperModel

    key = (settings.whisper_model, settings.whisper_device, settings.whisper_compute_type)
    if key in _model_cache:
        return _model_cache[key]

    device = settings.whisper_device
    compute_type = settings.whisper_compute_type

    if device == "auto":
        # MPS isn't supported by ctranslate2 yet, so on Mac we use CPU with int8
        # (still very fast on Apple Silicon).
        try:
            import torch

            device = "cuda" if torch.cuda.is_available() else "cpu"
        except ImportError:
            device = "cpu"

    if compute_type == "auto":
        compute_type = "float16" if device == "cuda" else "int8"

    console.log(
        f"transcribe: loading {settings.whisper_model} on {device} ({compute_type})"
    )
    model = WhisperModel(settings.whisper_model, device=device, compute_type=compute_type)
    _model_cache[key] = model
    return model


def run(audio_path: Path, reel_dir: Path) -> Transcript:
    """Transcribe audio with word-level timestamps. Idempotent."""
    out_path = reel_dir / "transcript.json"

    if is_done(reel_dir, "transcribe") and out_path.exists():
        console.log("[dim]transcribe: skipped[/dim]")
        return Transcript.model_validate_json(out_path.read_text())

    console.log("transcribe: running faster-whisper")
    model = _get_model()

    segments_iter, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 250},
    )

    segments: list[TranscriptSegment] = []
    for seg in segments_iter:
        words = [
            WordTimestamp(
                word=w.word.strip(),
                start=w.start,
                end=w.end,
                probability=w.probability,
            )
            for w in (seg.words or [])
        ]
        segments.append(
            TranscriptSegment(
                start=seg.start,
                end=seg.end,
                text=seg.text.strip(),
                words=words,
            )
        )

    transcript = Transcript(
        language=info.language,
        segments=segments,
        duration_s=info.duration,
    )

    out_path.write_text(transcript.model_dump_json(indent=2))
    mark_done(reel_dir, "transcribe")
    console.log(f"transcribe: {len(segments)} segments, lang={info.language}")
    return transcript
