from __future__ import annotations

import io

from PIL import Image


def ocr_image_bytes(image_bytes: bytes) -> str:
    """MVP OCR wrapper using PaddleOCR.

    Notes:
    - Uses PaddleOCR for higher accuracy than Tesseract on real-world menu photos.
    - Returns plain text lines joined by newlines.
    - If OCR cannot run (missing deps/model download issues), returns a clear
      placeholder string so the API stays functional.
    """

    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")

    try:
        import numpy as np  # type: ignore
        from paddleocr import PaddleOCR  # type: ignore

        # Create OCR instance lazily. For a real production system, we'd cache
        # this globally to avoid re-loading models on every request.
        ocr = PaddleOCR(use_angle_cls=True, lang="en")

        arr = np.array(img)
        result = ocr.ocr(arr, cls=True)

        lines: list[str] = []
        # result: List[ [ [box], (text, score) ], ... ]
        for page in result or []:
            for item in page or []:
                if not item or len(item) < 2:
                    continue
                text = item[1][0] if item[1] and len(item[1]) >= 1 else ""
                if text:
                    lines.append(text)

        return "\n".join(lines).strip()

    except Exception as exc:
        return f"[OCR unavailable: {exc}]"
