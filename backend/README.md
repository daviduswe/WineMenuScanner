# Backend (FastAPI)

## API
- `GET /health`
- `POST /api/v1/analyze` (multipart form-data field: `image`)

## OCR
- Uses **Surya OCR** to extract text + geometry (bounding boxes) from menu images.
- If Surya OCR cannot run (missing dependencies/model files), the API still responds but OCR text will include `[OCR unavailable: ...]`.
