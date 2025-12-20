from __future__ import annotations

import io
import re
from dataclasses import dataclass
from typing import Any, Optional

from PIL import Image

# Surya predictors can be expensive to initialize (model download/load), so we cache them.
_SURYA_FOUNDATION: Optional[object] = None
_SURYA_RECOGNIZER: Optional[object] = None
_SURYA_DETECTOR: Optional[object] = None

# Surya CPU performance is highly sensitive to image resolution.
# Cap width to keep inference fast on phone photos.
_MAX_OCR_WIDTH_PX = 2048


def _get_surya_predictors():
    global _SURYA_FOUNDATION, _SURYA_RECOGNIZER, _SURYA_DETECTOR

    if _SURYA_RECOGNIZER is not None and _SURYA_DETECTOR is not None:
        return _SURYA_RECOGNIZER, _SURYA_DETECTOR

    # Local import so the backend can still boot without Surya installed.
    from surya.foundation import FoundationPredictor  # type: ignore
    from surya.detection import DetectionPredictor  # type: ignore
    from surya.recognition import RecognitionPredictor  # type: ignore

    if _SURYA_FOUNDATION is None:
        _SURYA_FOUNDATION = FoundationPredictor()

    if _SURYA_DETECTOR is None:
        _SURYA_DETECTOR = DetectionPredictor()

    if _SURYA_RECOGNIZER is None:
        _SURYA_RECOGNIZER = RecognitionPredictor(_SURYA_FOUNDATION)

    return _SURYA_RECOGNIZER, _SURYA_DETECTOR


def _as_mapping_or_object(x: Any) -> tuple[Optional[dict], Any]:
    """Return (mapping, obj) where mapping is a dict if x is dict-like."""
    return (x if isinstance(x, dict) else None), x


def _get_bbox_from_line(line_obj: Any) -> Optional[tuple[float, float, float, float]]:
    """Best-effort extraction of (x1, y1, x2, y2) from a Surya text line."""

    mapping, obj = _as_mapping_or_object(line_obj)

    bbox = None
    if mapping is not None:
        bbox = mapping.get("bbox")
        polygon = mapping.get("polygon")
    else:
        bbox = getattr(obj, "bbox", None)
        polygon = getattr(obj, "polygon", None)

    # bbox is expected to be [x1, y1, x2, y2]
    if bbox and isinstance(bbox, (list, tuple)) and len(bbox) == 4:
        try:
            x1, y1, x2, y2 = [float(v) for v in bbox]
            return (x1, y1, x2, y2)
        except Exception:
            return None

    # polygon is expected to be 4 points; derive bbox
    if polygon and isinstance(polygon, (list, tuple)) and len(polygon) >= 4:
        try:
            xs: list[float] = []
            ys: list[float] = []
            for p in polygon:
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    xs.append(float(p[0]))
                    ys.append(float(p[1]))
            if xs and ys:
                return (min(xs), min(ys), max(xs), max(ys))
        except Exception:
            return None

    return None


def _reading_order_sort(lines: list[tuple[str, Optional[tuple[float, float, float, float]]]]) -> list[str]:
    """Sort by y then x with a tolerance to keep same-row items left-to-right.

    This is a lightweight heuristic that works well for typical single-column menus.
    Multi-column menus can still be imperfect without a full layout/ordering model.
    """

    # If we don't have any geometry, keep original order.
    if not any(b is not None for _, b in lines):
        return [t for t, _ in lines]

    # Compute a typical line height for row bucketing.
    heights = [b[3] - b[1] for _, b in lines if b is not None and (b[3] - b[1]) > 0]
    median_h = sorted(heights)[len(heights) // 2] if heights else 20.0
    row_tol = max(8.0, median_h * 0.6)

    def row_key(item: tuple[str, Optional[tuple[float, float, float, float]]]):
        _, b = item
        if b is None:
            return (10**9, 10**9)  # push unknowns to bottom
        x1, y1, x2, y2 = b
        y_mid = (y1 + y2) / 2.0
        return (int(y_mid // row_tol), x1)

    return [t for t, _ in sorted(lines, key=row_key)]


# Remove simple HTML-like tags that sometimes appear in OCR output.
_TAG_RE = re.compile(r"</?\w+[^>]*>")
# Collapse runs of dash-like characters often used as separators.
_DASH_RUN_RE = re.compile(r"[\-\u2013\u2014\u2212_]{3,}")


def _clean_ocr_line(s: str) -> str:
    s = _TAG_RE.sub("", s)
    s = _DASH_RUN_RE.sub(" ", s)
    # Remove trailing separator dashes (single or short runs) at line end.
    s = re.sub(r"\s*[\-\u2013\u2014\u2212_]+\s*$", "", s)
    # Normalize whitespace
    s = " ".join(s.split())
    return s.strip()


@dataclass
class _OcrItem:
    text: str
    bbox: tuple[float, float, float, float]


def _median(values: list[float], default: float) -> float:
    if not values:
        return default
    values = sorted(values)
    return values[len(values) // 2]


def _group_lines_into_rows(
    items: list[_OcrItem],
    *,
    y_tol_factor: float = 0.60,
    min_y_tol: float = 8.0,
) -> list[str]:
    """Group OCR line items into visual rows using bbox geometry.

    Strategy:
    - Compute typical line height (median).
    - Bucket by Y (using y-mid / tolerance band).
    - Within each bucket, sort by X and concatenate texts.
    """

    if not items:
        return []

    heights = [(it.bbox[3] - it.bbox[1]) for it in items if (it.bbox[3] - it.bbox[1]) > 0]
    median_h = _median(heights, default=20.0)
    row_tol = max(min_y_tol, median_h * y_tol_factor)

    # Bucket items by y-band, then order bands top->bottom.
    buckets: dict[int, list[_OcrItem]] = {}
    for it in items:
        x1, y1, x2, y2 = it.bbox
        y_mid = (y1 + y2) / 2.0
        key = int(y_mid // row_tol)
        buckets.setdefault(key, []).append(it)

    out_rows: list[str] = []
    for band in sorted(buckets.keys()):
        row_items = buckets[band]
        row_items.sort(key=lambda it: it.bbox[0])  # left-to-right

        # Join with single spaces; preserve prices as separate tokens.
        row_text = " ".join(it.text for it in row_items if it.text)
        row_text = _clean_ocr_line(row_text)
        if row_text:
            out_rows.append(row_text)

    return out_rows


def _extract_text_lines(pred: Any) -> list[str]:
    """Extract line texts from Surya prediction.

    If bbox is present, merge same-row items using geometry so output becomes
    more human-like for menus (wine text + prices on the same row).
    """

    mapping, obj = _as_mapping_or_object(pred)

    text_lines = None
    if mapping is not None:
        text_lines = mapping.get("text_lines")
    else:
        text_lines = getattr(obj, "text_lines", None)

    collected: list[tuple[str, Optional[tuple[float, float, float, float]]]] = []
    items: list[_OcrItem] = []
    if text_lines:
        for tl in text_lines:
            tl_map, tl_obj = _as_mapping_or_object(tl)
            if tl_map is not None:
                text = tl_map.get("text")
            else:
                text = getattr(tl_obj, "text", None)

            if not text:
                continue

            bbox = _get_bbox_from_line(tl)
            cleaned = _clean_ocr_line(str(text))
            if cleaned:
                collected.append((cleaned, bbox))
                if bbox is not None:
                    items.append(_OcrItem(text=cleaned, bbox=bbox))

    # Prefer geometry-based row grouping when we have any bboxes.
    if items:
        return _group_lines_into_rows(items)

    # Sort to match image reading order as closely as possible.
    return [ln for ln in _reading_order_sort(collected) if ln]


def _extract_fallback_text(pred: Any) -> Optional[str]:
    mapping, obj = _as_mapping_or_object(pred)
    if mapping is not None:
        val = mapping.get("text")
    else:
        val = getattr(obj, "text", None)
    if isinstance(val, str) and val.strip():
        return _clean_ocr_line(val)
    return None


def _downscale_for_ocr(img: Image.Image) -> Image.Image:
    """Downscale very large images to speed up OCR on CPU.

    Keeps aspect ratio. Does nothing if image is already small enough.
    """

    try:
        w, h = img.size
        if w <= _MAX_OCR_WIDTH_PX:
            return img
        scale = _MAX_OCR_WIDTH_PX / float(w)
        new_size = (_MAX_OCR_WIDTH_PX, max(1, int(h * scale)))
        return img.resize(new_size, Image.Resampling.LANCZOS)
    except Exception:
        # If anything goes wrong, fall back to original image.
        return img


def ocr_image_bytes(image_bytes: bytes) -> str:
    """OCR wrapper using Surya OCR.

    Notes:
    - Uses Surya for document-style OCR (menus, forms, PDFs) with strong multilingual support.
    - Returns plain text lines joined by newlines.
    - If OCR cannot run (missing deps/model download issues), returns a clear
      placeholder string so the API stays functional.

    Installation (backend):
    - pip install surya-ocr
    - plus a compatible PyTorch build for your machine (CPU or CUDA)
    """

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img = _downscale_for_ocr(img)

    try:
        recognizer, detector = _get_surya_predictors()

        predictions = recognizer([img], det_predictor=detector)
        if not predictions:
            return ""

        pred0 = predictions[0]

        lines = _extract_text_lines(pred0)
        if lines:
            return "\n".join(lines).strip()

        fallback = _extract_fallback_text(pred0)
        return fallback or ""

    except Exception as exc:
        return f"[OCR unavailable: {exc}]"
