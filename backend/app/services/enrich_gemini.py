from __future__ import annotations

# MVP placeholder.
# Enrichment is optional; keep implementation minimal and disabled by default.
# Add Gemini integration later behind an environment flag.

import json
import os
from typing import Optional
import traceback

import google.generativeai as genai

from app.models.wine import Wine

# Debug logging (enable with GEMINI_DEBUG=1)
GEMINI_DEBUG = os.getenv("GEMINI_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _is_missing(val: object) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and val.strip() in {"", "-", "n/a", "na"}:
        return True
    return False


def _enabled() -> bool:
    return os.getenv("ENABLE_GEMINI_ENRICHMENT", "").strip().lower() in {"1", "true", "yes", "on"}


def _get_client() -> Optional[tuple[str, str]]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash"
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    return api_key, model


def _extract_json_object(text: str) -> Optional[dict]:
    text = (text or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        val = json.loads(text[start : end + 1])
        return val if isinstance(val, dict) else None
    except Exception:
        return None


def _extract_json_array(text: str) -> Optional[list]:
    text = (text or "").strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        val = json.loads(text[start : end + 1])
        return val if isinstance(val, list) else None
    except Exception:
        return None


def _apply_enrichment(w: Wine, data: dict) -> Wine:
    if _is_missing(w.producer) and isinstance(data.get("producer"), str) and data["producer"].strip():
        w.producer = data["producer"].strip()
    if _is_missing(w.region) and isinstance(data.get("region"), str) and data["region"].strip():
        w.region = data["region"].strip()
    if _is_missing(w.grape) and isinstance(data.get("grape"), str) and data["grape"].strip():
        w.grape = data["grape"].strip()
    # Short, menu-friendly description (enrichment)
    if _is_missing(getattr(w, "description", None)) and isinstance(data.get("description"), str) and data["description"].strip():
        w.description = data["description"].strip()
    if w.vintage is None:
        v = data.get("vintage")
        if isinstance(v, int) and 1900 <= v <= 2100:
            w.vintage = v
    return w


def enrich_wines_gemini_batched(wines: list[Wine]) -> list[Wine]:
    """Enrich all wines in a single Gemini request (MVP).

    Returns the same list instance with fields filled best-effort.
    """

    if not _enabled():
        return wines

    client = _get_client()
    if client is None:
        return wines

    _, model_name = client
    # Conservative config to increase odds of valid JSON.
    model = genai.GenerativeModel(
        model_name,
        generation_config={
            "temperature": 0.0,
            "top_p": 0.1,
            "max_output_tokens": 2048,
        },
    )

    names: list[str] = [(w.name or "").strip() for w in wines]
    indexed = [(i, n) for i, n in enumerate(names) if n]
    if not indexed:
        return wines

    prompt = (
        "You are enriching a restaurant wine list. "
        "Given a JSON array of wine name strings, return ONLY valid JSON: an array of objects of equal length, "
        "in the same order, each object having keys: producer (string or null), region (string or null), "
        "grape (string or null), vintage (integer year or null), description (string or null). "
        "Description must be one short sentence (max ~25 words), menu-friendly, no marketing fluff. "
        "Do not mention prices. "
        "Use null when unknown. "
        "Do not add extra keys.\n\n"
        "Wine names JSON:\n"
        f"{json.dumps([n for _, n in indexed], ensure_ascii=False)}\n"
    )

    try:
        if GEMINI_DEBUG:
            print(f"[gemini] batching {len(indexed)} wines")

        # NOTE: google-generativeai doesn't expose a universal timeout across versions;
        # keep call simple and report details on failure.
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()
        arr = _extract_json_array(text)
        if arr is None:
            if GEMINI_DEBUG:
                print("[gemini] batch no-json-array")
            return wines

        # Apply results back onto wines.
        if len(arr) != len(indexed):
            if GEMINI_DEBUG:
                print(f"[gemini] batch length mismatch: got={len(arr)} expected={len(indexed)}")
            # Still apply min length best-effort.

        for (wine_idx, _), item in zip(indexed, arr):
            if isinstance(item, dict):
                _apply_enrichment(wines[wine_idx], item)

        if GEMINI_DEBUG:
            print("[gemini] batch done")
        return wines
    except Exception as exc:
        if GEMINI_DEBUG:
            print(f"[gemini] batch error: {type(exc).__name__}: {exc}")
            print(traceback.format_exc())

        # Fallback: per-wine calls so you still get enrichment when batching fails.
        out: list[Wine] = []
        if GEMINI_DEBUG:
            print(f"[gemini] falling back to per-wine enrichment for {len(wines)} wines")
        for w in wines:
            out.append(enrich_wine_gemini(w))
        return out


def enrich_wine_gemini(w: Wine) -> Wine:
    """Best-effort enrichment.

    Fills missing fields only (does not overwrite existing values).
    """

    if not _enabled():
        return w

    client = _get_client()
    if client is None:
        return w

    _, model_name = client
    if not w.name or not w.name.strip():
        return w

    model = genai.GenerativeModel(model_name)

    prompt = (
        "You are extracting structured metadata for a wine list. "
        "Given a wine name string from a restaurant menu, return ONLY valid JSON with keys: "
        "producer (string or null), region (string or null), grape (string or null), vintage (integer year or null), "
        "description (string or null). Description must be one short sentence (max ~25 words), menu-friendly. "
        "If unknown, use null. Do not include any other keys.\n\n"
        f"Wine name: {w.name!r}\n"
    )

    try:
        resp = model.generate_content(prompt)
        text = (resp.text or "").strip()

        data = _extract_json_object(text)
        if data is None:
            if GEMINI_DEBUG:
                print(f"[gemini] no-json: {w.name}")
            return w

        before = {"producer": w.producer, "region": w.region, "grape": w.grape, "vintage": w.vintage}
        _apply_enrichment(w, data)

        if GEMINI_DEBUG:
            after = {"producer": w.producer, "region": w.region, "grape": w.grape, "vintage": w.vintage}
            changed = [k for k in after.keys() if before.get(k) != after.get(k) and _is_missing(before.get(k))]
            print(f"[gemini] enriched: {w.name} | filled={changed}" if changed else f"[gemini] no-change: {w.name}")

        return w
    except Exception:
        if GEMINI_DEBUG:
            print(f"[gemini] error: {w.name}")
        return w


def enrich_wines_gemini(wines: list[Wine]) -> list[Wine]:
    """Enrich a list of wines sequentially (MVP)."""

    # Prefer a single batched request.
    return enrich_wines_gemini_batched(wines)
