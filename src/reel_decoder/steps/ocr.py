"""Step 5: OCR — extract overlay text per frame, classify primary vs highlight.

The trick: after EasyOCR returns bounding boxes, we sample pixel colors inside
each box. Yellow-ish = highlight text (the accent word). White-ish = primary
text. This is what lets us reconstruct the "STRENGTHEN immunity" pattern where
the words are styled differently.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image
from rich.console import Console

from reel_decoder.config import settings
from reel_decoder.schema import OcrDetection
from reel_decoder.steps import is_done, mark_done

console = Console()

_reader_cache = None


def _get_reader():
    global _reader_cache
    if _reader_cache is None:
        import easyocr

        # gpu=False is safest cross-platform; flip to True if you have CUDA
        _reader_cache = easyocr.Reader(["en"], gpu=False, verbose=False)
    return _reader_cache


def _classify_color(img_np: np.ndarray, bbox: tuple[int, int, int, int]) -> bool:
    """Sample pixels inside bbox, return True if dominant text color is yellow-ish.

    Heuristic: convert to HSV, count pixels that are
      - high saturation (>80) AND hue in yellow range (35-75 in OpenCV/PIL HSV)
      vs
      - low saturation AND high value (white)
    If yellow count > 20% of high-value pixels, classify as highlight.
    """
    x1, y1, x2, y2 = bbox
    h, w = img_np.shape[:2]
    x1, x2 = max(0, x1), min(w, x2)
    y1, y2 = max(0, y1), min(h, y2)
    if x2 <= x1 or y2 <= y1:
        return False

    crop = img_np[y1:y2, x1:x2]
    if crop.size == 0:
        return False

    # Convert RGB -> HSV via PIL for cross-platform consistency
    hsv = np.array(Image.fromarray(crop).convert("HSV"))
    h_chan, s_chan, v_chan = hsv[..., 0], hsv[..., 1], hsv[..., 2]

    # Only consider "text" pixels — high value, since text is bright on dark bg
    text_mask = v_chan > 180
    if text_mask.sum() < 10:
        return False

    # Yellow in PIL HSV: hue ~35-65 (0-255 scale → ~50-90)
    yellow_mask = text_mask & (s_chan > 80) & (h_chan >= 30) & (h_chan <= 75)
    yellow_ratio = yellow_mask.sum() / max(text_mask.sum(), 1)

    return yellow_ratio > 0.2


def run(frame_pairs: list[tuple[float, Path]], reel_dir: Path) -> list[OcrDetection]:
    """Run OCR on every keyframe. Returns all detections across all frames."""
    out_path = reel_dir / "overlay_text.json"

    if is_done(reel_dir, "ocr") and out_path.exists():
        console.log("[dim]ocr: skipped[/dim]")
        data = json.loads(out_path.read_text())
        return [OcrDetection(**d) for d in data]

    console.log(f"ocr: scanning {len(frame_pairs)} frames")
    reader = _get_reader()
    detections: list[OcrDetection] = []

    for ts, frame_path in frame_pairs:
        try:
            img = Image.open(frame_path).convert("RGB")
            img_np = np.array(img)
            results = reader.readtext(img_np)
            for bbox_poly, text, conf in results:
                if conf < settings.ocr_confidence_threshold:
                    continue
                text = text.strip()
                if not text:
                    continue
                # bbox_poly is a quadrilateral; reduce to axis-aligned rect
                xs = [int(p[0]) for p in bbox_poly]
                ys = [int(p[1]) for p in bbox_poly]
                bbox = (min(xs), min(ys), max(xs), max(ys))
                is_highlight = _classify_color(img_np, bbox)
                detections.append(
                    OcrDetection(
                        frame_path=str(frame_path),
                        timestamp_s=ts,
                        text=text,
                        bbox=bbox,
                        confidence=float(conf),
                        is_highlight=is_highlight,
                    )
                )
        except Exception as e:  # noqa: BLE001
            console.log(f"[yellow]ocr: skipped {frame_path.name}: {e}[/yellow]")

    out_path.write_text(json.dumps([d.model_dump() for d in detections], indent=2))
    mark_done(reel_dir, "ocr")
    console.log(f"ocr: {len(detections)} detections")
    return detections
