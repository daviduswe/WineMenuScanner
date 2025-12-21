from __future__ import annotations

from fastapi import APIRouter, File, HTTPException, UploadFile

from app.models.wine import AnalyzeResponse
from app.services.enrich_gemini import enrich_wines_gemini
from app.services.normalize import normalize_wines
from app.services.ocr import ocr_image_bytes
from app.services.parser import parse_wines_from_text

router = APIRouter()


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze_menu(image: UploadFile = File(...)) -> AnalyzeResponse:
    if image.content_type not in {"image/jpeg", "image/png"}:
        raise HTTPException(status_code=400, detail="Only JPEG/PNG images are supported in MVP")

    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="Empty upload")

    raw_text = ocr_image_bytes(data)
    wines = parse_wines_from_text(raw_text)
    # Optional, best-effort enrichment (fills missing fields only).
    wines = enrich_wines_gemini(wines)
    wines = normalize_wines(wines)

    return AnalyzeResponse(rawText=raw_text, wines=wines)
