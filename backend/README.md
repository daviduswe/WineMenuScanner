# Backend (FastAPI)

## API
- `GET /health`
- `POST /api/v1/analyze` (multipart form-data field: `image`)

## OCR
- Uses **PaddleOCR** (local) for better accuracy on real-world menu photos.
- On first run, PaddleOCR may download model files automatically.
- If PaddleOCR cannot run (missing dependencies, model download blocked), the API still responds but OCR text will include `[OCR unavailable: ...]`.
