from __future__ import annotations

from typing import Optional

from pydantic import BaseModel, Field


class Price(BaseModel):
    currency: Optional[str] = Field(default=None, description="Currency symbol/code if detected")
    bottle: Optional[float] = Field(default=None, description="Bottle price if present")
    glass: Optional[float] = Field(default=None, description="Glass price if present")


class Wine(BaseModel):
    id: str
    rawText: str

    # Explicit group header (e.g., "RED WINE", "White Wines", "Sparkling")
    wineGroup: Optional[str] = None

    # Backward-compatible field (older UI used 'section')
    section: Optional[str] = None

    name: Optional[str] = None
    producer: Optional[str] = None
    region: Optional[str] = None
    vintage: Optional[int] = None
    grape: Optional[str] = None

    # Optional enrichment
    description: Optional[str] = None

    price: Price = Field(default_factory=Price)


class AnalyzeResponse(BaseModel):
    rawText: str
    wines: list[Wine]
