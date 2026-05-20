# Copilot instructions for reel-decoder

This repo is a local Python pipeline that decodes Instagram reel videos into
structured Swipe Library rows. **Zero cloud calls**: everything runs locally
through Ollama (models) and ffmpeg (media).

When suggesting code in this repo, follow these conventions:

## Stack

- **Python 3.11+**, fully type-hinted with `from __future__ import annotations`.
- **Pydantic v2** for all data shapes. The canonical schema lives in
  `src/reel_decoder/schema.py`. Don't introduce TypedDict or dataclasses —
  use Pydantic BaseModel for anything that crosses a step boundary.
- **Typer** for CLI commands (in `src/reel_decoder/__main__.py`).
- **Rich** for console output (`from rich.console import Console`).
- **openpyxl** for xlsx writes (in `writers/xlsx_writer.py`).
- **ffmpeg-python** or subprocess to ffmpeg for media operations.
- **Ollama** Python client for both vision (`qwen2-vl:7b`) and text
  (`qwen2.5:7b`) inference. Always read model names from `settings`, not
  hardcoded strings.

## Architecture

Pipeline orchestrator: `src/reel_decoder/pipeline.py`. Each step lives in
`src/reel_decoder/steps/<name>.py` and exposes a `run(...)` function. Steps are
**idempotent** — they check a `.{step}.done` sentinel file in the reel's output
directory and skip if it exists. Use the helpers in `steps/__init__.py`:
`is_done(reel_dir, "<step>")` and `mark_done(reel_dir, "<step>")`.

Pipeline order: ingest → transcribe → scenes → frames → ocr → vision →
aggregate → classify → write.

## Conventions

- **No print statements**. Use `console.log()` for progress, `console.print()`
  for user-facing summaries.
- **Cache models with module-level dicts**, not class state, so reruns within
  the same process don't reload weights. See `steps/transcribe.py` and
  `steps/ocr.py` for the pattern.
- **Always validate LLM output against a Pydantic model**. If parsing fails,
  save the raw text to `<reel_dir>/<step>_raw.txt` for debugging before
  re-raising.
- **Paths are `pathlib.Path`**, never strings. Convert only at subprocess
  boundaries with `str(path)`.
- **Settings come from `reel_decoder.config.settings`** (a pydantic-settings
  instance). Don't read os.environ directly.

## Schema is the contract

`DecodedReel` in `schema.py` is the final output. Its shape mirrors the columns
of the Swipe Library xlsx. The classifier prompt in `steps/classify.py` must
produce JSON matching this schema exactly. If you need to add a field to the
xlsx output, update in this order: (1) `DecodedReel`, (2) `to_xlsx_row()`,
(3) the prompt template, (4) `HEADERS` in `xlsx_writer.py`.

## Error handling

- Use `try/except` around LLM and OCR calls (they can fail per-frame). Log a
  warning and continue — don't fail the whole pipeline for one bad frame.
- Use `raise RuntimeError(...) from e` for unrecoverable errors so the original
  traceback is preserved.

## Testing

Tests live in `tests/`. Use pytest. Mock Ollama calls with monkeypatch — don't
hit a real server in unit tests. Integration tests that need ffmpeg/Ollama
should be marked with `@pytest.mark.integration` and skipped by default.

## What NOT to suggest

- Don't suggest cloud APIs (OpenAI, Anthropic, Google) for any step. The whole
  point of this repo is local execution.
- Don't suggest downloading reels from Instagram inside this repo — that's a
  user responsibility outside the pipeline.
- Don't suggest moving Ollama calls behind a "provider abstraction" — keep it
  direct. v2 if needed.
