"""Prompt loader — reads .txt prompt templates from the prompts directory."""

from __future__ import annotations

from functools import cache
from pathlib import Path

_PROMPTS_DIR = Path(__file__).parent / "prompts"


@cache
def load_prompt(name: str) -> str:
    """Load a prompt template by name (without extension)."""
    path = _PROMPTS_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")
    return path.read_text(encoding="utf-8")
