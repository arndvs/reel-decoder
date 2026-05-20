"""Configuration loaded from environment / .env."""

from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Whisper
    whisper_model: str = "large-v3-turbo"
    whisper_device: str = "auto"
    whisper_compute_type: str = "auto"

    # Ollama
    ollama_host: str = "http://localhost:11434"
    vision_model: str = "qwen2-vl:7b"
    classifier_model: str = "qwen2.5:7b"

    # Pipeline tuning
    scene_threshold: float = 27.0
    frame_sample_fps: float = 2.0
    ocr_confidence_threshold: float = 0.5

    # Paths
    inputs_dir: Path = Path("inputs/reels")
    outputs_dir: Path = Path("outputs")

    @property
    def per_reel_dir(self) -> Path:
        return self.outputs_dir / "per-reel"

    @property
    def swipe_library_path(self) -> Path:
        return self.outputs_dir / "swipe-library.xlsx"

    def reel_dir(self, reel_id: str) -> Path:
        return self.per_reel_dir / reel_id


settings = Settings()
