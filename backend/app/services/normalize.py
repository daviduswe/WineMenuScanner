from __future__ import annotations

from app.models.wine import Wine


def normalize_wines(wines: list[Wine]) -> list[Wine]:
    # Minimal normalization for MVP.
    for w in wines:
        if w.name:
            w.name = " ".join(w.name.split())
        if w.producer:
            w.producer = " ".join(w.producer.split())
        if w.region:
            w.region = " ".join(w.region.split())
        if w.grape:
            w.grape = " ".join(w.grape.split())
    return wines
