# Reel Decoder

Local Python pipeline that takes Instagram reel `.mp4` files and decodes them into
structured rows for the Reel Swipe Library. Transcribes audio, detects scene cuts,
OCRs overlay text, describes visuals, and classifies hook patterns + beat types
using local LLMs via Ollama.

**Zero cloud APIs. Zero data leaves your machine.**

---

## What it produces

For each reel, you get:

1. A per-reel artifact folder with intermediate outputs (transcript, scenes,
   frames, OCR, vision descriptions) — useful for debugging and iteration.
2. A `decoded.json` matching the Swipe Library schema.
3. An appended row in `outputs/swipe-library.xlsx`.

---

## Requirements

- **Python 3.11+**
- **ffmpeg** (`brew install ffmpeg` on Mac, `winget install ffmpeg` on Windows,
  `apt install ffmpeg` on Linux)
- **Ollama** (https://ollama.com/download) — runs the vision and text models locally
- Roughly **8 GB free RAM** for the 7B models; 16 GB recommended.
  Apple Silicon Macs with unified memory work great.

---

## Setup

```bash
git clone <this repo>
cd reel-decoder

# Python env
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e .

# Pull the local models (one-time, ~10 GB total)
bash scripts/setup_ollama.sh

# Verify Ollama is running
ollama list
```

If Ollama isn't running, start it: `ollama serve` (or it auto-starts on Mac after install).

---

## Usage

1. Drop reel `.mp4` files into `inputs/reels/`. Name them whatever you want —
   the filename (minus extension) becomes the reel ID.

2. Decode a single reel:

   ```bash
   python -m reel_decoder decode inputs/reels/alchemy-dose.mp4
   ```

3. Decode everything in the inputs folder:

   ```bash
   python -m reel_decoder decode-all
   ```

4. Re-run a specific step (useful when iterating on prompts):

   ```bash
   python -m reel_decoder decode inputs/reels/alchemy-dose.mp4 --force classify
   ```

---

## Downloading reels from Instagram

The pipeline doesn't download from Instagram (we want zero risk of TOS issues
or account flags). Use a separate tool of your choosing. Common options:

- `yt-dlp` (open source, requires Instagram login cookie for private reels)
- Browser screen-record (most reliable, no account risk)
- Mobile screen-record + AirDrop / `adb pull`

Drop the resulting `.mp4` into `inputs/reels/`.

---

## Pipeline steps

Each step writes to `outputs/per-reel/<reel_id>/` and is idempotent. A `.done`
sentinel file marks completion. To force re-run a step, delete its sentinel or
pass `--force <step>` to the CLI.

| Step          | Output                       | What it does                                                    |
| ------------- | ---------------------------- | --------------------------------------------------------------- |
| `ingest`      | `audio.wav`                  | Extract 16kHz mono WAV via ffmpeg                               |
| `transcribe`  | `transcript.json`            | faster-whisper with word-level timestamps                       |
| `scenes`      | `scenes.json`                | PySceneDetect cut boundaries                                    |
| `frames`      | `frames/*.jpg`               | Keyframe sampling (scene midpoints + 2 fps)                     |
| `ocr`         | `overlay_text.json`          | EasyOCR + color classification (white primary vs yellow accent) |
| `vision`      | `visual_descriptions.json`   | qwen2-vl per keyframe                                           |
| `aggregate`   | `aggregated.json`            | Merge transcript + OCR + vision into beat-aligned data          |
| `classify`    | `decoded.json`               | qwen2.5 classifies hook pattern, beats, why-it-works            |
| `write`       | row appended to xlsx         | Append to `outputs/swipe-library.xlsx`                          |

---

## Tuning

Edit `src/reel_decoder/config.py` to change:

- Model selection (swap `qwen2.5:7b` for `llama3.1:8b`, etc.)
- Scene detection threshold (default 27.0)
- Frame sampling rate (default 2 fps)
- OCR confidence threshold (default 0.5)

Prompts live in `src/reel_decoder/prompts/*.txt` — edit them and re-run with
`--force classify` to iterate without re-running expensive earlier steps.

---

## Running in VS Code

Open the folder in VS Code. The `.vscode/` directory ships with:

- **Launch configs**: F5 to debug "Decode single reel" or "Decode all"
- **Tasks**: Cmd-Shift-P → "Run Task" → set up env, pull models, run tests
- **Recommended extensions**: Python, Pylance, Ruff

GitHub Copilot reads `.github/copilot-instructions.md` and will suggest code
matching this repo's conventions (Pydantic schema, ffmpeg patterns, Ollama
client usage).

---

## Troubleshooting

**"Ollama connection refused"** — Start it. `ollama serve`. On Mac it should
auto-start; on Linux you need to run it manually or set up the systemd service.

**"CUDA out of memory" on a small GPU** — Set `VISION_MODEL=moondream:1.8b` in
your `.env`. Tiny model, runs on CPU if needed.

**Whisper is slow on CPU** — Set `WHISPER_MODEL=small` in `.env`. Less accurate
on tricky audio but 5× faster. Or run `WHISPER_DEVICE=mps` on Apple Silicon for
GPU acceleration.

**EasyOCR misses styled text** — Edit `src/reel_decoder/steps/ocr.py`, lower the
confidence threshold from 0.5 to 0.3. Tradeoff is more false positives.

**Scene detection is too aggressive / too lax** — Edit `SCENE_THRESHOLD` in
`config.py`. Lower = more cuts detected.

---

## Cost

$0. Everything runs locally. First-time model downloads are ~10 GB.

---

## What this does NOT do

- Download reels (use a separate tool)
- Audio fingerprinting / music identification (out of scope for v1)
- Detect specific products or brands in frames
- Translate non-English captions (Whisper transcribes any language but the
  classifier prompts are English-only)
