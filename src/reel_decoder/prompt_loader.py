"""Prompt loader — reads .txt prompt templates from the prompts package."""

from __future__ import annotations

from functools import cache
from importlib import resources


@cache
def load_prompt(name: str) -> str:
    """Load a prompt template by name (without extension)."""
    source = resources.files("reel_decoder.prompts").joinpath(f"{name}.txt")
    return source.read_text(encoding="utf-8")
