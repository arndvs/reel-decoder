#!/usr/bin/env bash
# Pull the local models used by reel-decoder.
# Cross-platform: works on macOS, Linux, Windows (via WSL or Git Bash).

set -euo pipefail

echo "==> Checking that Ollama is reachable..."
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama CLI not found. Install from https://ollama.com/download" >&2
  exit 1
fi

if ! curl -sf http://localhost:11434/api/tags >/dev/null; then
  echo "Ollama server not reachable on localhost:11434."
  echo "On macOS Ollama should auto-start after install."
  echo "Otherwise run:  ollama serve"
  exit 1
fi

echo "==> Pulling vision model (qwen2-vl:7b, ~6 GB)..."
ollama pull qwen2-vl:7b

echo "==> Pulling classifier model (qwen2.5:7b, ~4.5 GB)..."
ollama pull qwen2.5:7b

echo
echo "Done. Verify with: ollama list"
echo
echo "If you're on a low-VRAM machine, also pull the fallback vision model:"
echo "  ollama pull moondream:1.8b"
echo "Then set VISION_MODEL=moondream:1.8b in .env"
