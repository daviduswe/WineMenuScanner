from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.routes import router as v1_router

# Load .env if present (no-op if missing)
load_dotenv()

app = FastAPI(title="Wine Menu Scanner", version="0.1.0")

# MVP-friendly: allow local dev frontends.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"] ,
    allow_headers=["*"],
)

app.include_router(v1_router, prefix="/api/v1")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
