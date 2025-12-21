from __future__ import annotations

# MVP placeholder.
# Enrichment is optional; keep implementation minimal and disabled by default.
# Add Gemini integration later behind an environment flag.

import json
import os
from typing import Optional
import traceback
import re
import time
import hashlib
import sqlite3

import google.generativeai as genai

from app.models.wine import Wine

# Debug logging (enable with GEMINI_DEBUG=1)
GEMINI_DEBUG = os.getenv("GEMINI_DEBUG", "").strip().lower() in {"1", "true", "yes", "on"}


def _response_text(resp: object) -> str:
    """Best-effort extraction of full text from google-generativeai responses.

    You cannot do `resp["text"]` reliably: the response is not guaranteed to be a dict.
    Some SDK versions also provide multi-part responses where `.text` can be empty/partial.
    """

    # 1) Common path
    try:
        t = getattr(resp, "text", None)
        if isinstance(t, str) and t.strip():
            return t.strip()
    except Exception:
        pass

    # 2) Candidate parts path
    try:
        candidates = getattr(resp, "candidates", None)
        if candidates:
            chunks: list[str] = []
            for cand in candidates:
                content = getattr(cand, "content", None)
                parts = getattr(content, "parts", None) if content is not None else None
                if not parts:
                    continue
                for p in parts:
                    pt = getattr(p, "text", None)
                    if isinstance(pt, str) and pt:
                        chunks.append(pt)
            joined = "".join(chunks).strip()
            if joined:
                return joined
    except Exception:
        pass

    return ""


def _is_missing(val: object) -> bool:
    if val is None:
        return True
    if isinstance(val, str) and val.strip() in {"", "-", "n/a", "na"}:
        return True
    return False


def _enabled() -> bool:
    return os.getenv("ENABLE_GEMINI_ENRICHMENT", "").strip().lower() in {"1", "true", "yes", "on"}


# --- Cache (best-effort) ------------------------------------------------------

_CACHE_MEM: dict[str, tuple[float, dict]] = {}


def _cache_enabled() -> bool:
    return os.getenv("GEMINI_CACHE", "1").strip().lower() in {"1", "true", "yes", "on"}


def _cache_ttl_seconds() -> int:
    # Default: 30 days
    try:
        return int(os.getenv("GEMINI_CACHE_TTL_SECONDS", str(30 * 24 * 60 * 60)).strip())
    except Exception:
        return 30 * 24 * 60 * 60


def _cache_path() -> str:
    # Store under backend/ by default; override if desired.
    p = os.getenv("GEMINI_CACHE_PATH", "backend/.gemini_cache.sqlite").strip() or "backend/.gemini_cache.sqlite"
    # Resolve relative paths against CWD.
    return os.path.abspath(p)


def _normalize_name(name: str) -> str:
    # Stable keying: lowercase, collapse whitespace.
    t = (name or "").strip().lower()
    t = re.sub(r"\s+", " ", t)
    return t


def _cache_key(name: str) -> str:
    norm = _normalize_name(name)
    # Hash to keep keys short and avoid sqlite performance issues with long text.
    return hashlib.sha256(norm.encode("utf-8")).hexdigest()


def _cache_conn() -> sqlite3.Connection:
    # Ensure directory exists.
    path = _cache_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute(
        "CREATE TABLE IF NOT EXISTS gemini_cache (key TEXT PRIMARY KEY, name TEXT, data_json TEXT NOT NULL, updated_at INTEGER NOT NULL)"
    )
    return conn


def _cache_get(name: str) -> Optional[dict]:
    if not _cache_enabled():
        return None
    n = (name or "").strip()
    if not n:
        return None

    now = time.time()
    key = _cache_key(n)
    ttl = _cache_ttl_seconds()

    # Memory cache first
    mem = _CACHE_MEM.get(key)
    if mem is not None:
        ts, data = mem
        if now - ts <= ttl:
            return data
        _CACHE_MEM.pop(key, None)

    # Disk cache
    try:
        with _cache_conn() as conn:
            row = conn.execute(
                "SELECT data_json, updated_at FROM gemini_cache WHERE key = ?",
                (key,),
            ).fetchone()
            if not row:
                return None
            data_json, updated_at = row
            if now - float(updated_at) > ttl:
                return None
            data = json.loads(data_json)
            if isinstance(data, dict):
                _CACHE_MEM[key] = (now, data)
                return data
    except Exception:
        return None

    return None


def _cache_set(name: str, data: dict) -> None:
    if not _cache_enabled():
        return
    n = (name or "").strip()
    if not n or not isinstance(data, dict):
        return

    key = _cache_key(n)
    now = time.time()
    _CACHE_MEM[key] = (now, data)

    try:
        with _cache_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO gemini_cache(key, name, data_json, updated_at) VALUES(?, ?, ?, ?)",
                (key, _normalize_name(n), json.dumps(data, ensure_ascii=False), int(now)),
            )
            conn.commit()
    except Exception:
        return


def _get_client() -> Optional[tuple[str, str]]:
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    model = os.getenv("GEMINI_MODEL", "gemini-1.5-flash").strip() or "gemini-1.5-flash"
    if not api_key:
        return None
    genai.configure(api_key=api_key)
    return api_key, model


def _strip_code_fences(text: str) -> str:
    """Remove common Markdown code fences while preserving inner content."""
    t = (text or "").strip()
    # ```json ... ``` or ``` ... ```
    t = re.sub(r"^```(?:json)?\s*\n", "", t, flags=re.IGNORECASE)
    t = re.sub(r"\n```\s*$", "", t)
    return t.strip()


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
    text = _strip_code_fences(text)

    start = text.find("[")
    if start == -1:
        return None

    # First attempt: strict JSON parse of the first array.
    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(text[start:])
        return obj if isinstance(obj, list) else None
    except Exception:
        pass

    # Second attempt: common model issue is a trailing comma before ']' or '}'
    # which is invalid JSON. Apply a very small, targeted fix and retry.
    candidate = text[start:]
    candidate = re.sub(r",\s*(\]|\})", r"\1", candidate)
    try:
        decoder = json.JSONDecoder()
        obj, _ = decoder.raw_decode(candidate)
        return obj if isinstance(obj, list) else None
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

    # Cache hits first; only send missing ones to Gemini.
    indexed: list[tuple[int, str]] = []
    for i, w in enumerate(wines):
        name = (w.name or "").strip()
        if not name:
            continue

        cached = _cache_get(name)
        if isinstance(cached, dict):
            _apply_enrichment(w, cached)
            continue

        indexed.append((i, name))

    if not indexed:
        return wines

    client = _get_client()
    if client is None:
        return wines

    _, model_name = client
    # Conservative config to increase odds of valid JSON.
    model = genai.GenerativeModel(
        model_name,
        generation_config={
            # Hint to return JSON only (supported on newer APIs; ignored otherwise).
            "response_mime_type": "application/json",
        },
    )

    prompt = (
        "You are enriching a restaurant wine list. "
        "Given a JSON array of wine name strings, return ONLY valid JSON (no prose, no markdown): "
        "an array of objects of equal length, in the same order, each object having keys: "
        "producer (string or null), region (string or null), grape (string or null), "
        "vintage (integer year or null), description (string or null). "
        "Description must be one short sentence (max ~25 words), menu-friendly, no marketing fluff. "
        "Do not mention prices. "
        "Use null when unknown. "
        "Do not add extra keys. "
        "Return JSON only, starting with '[' and ending with ']'.\n\n"
        "Wine names JSON:\n"
        f"{json.dumps([n for _, n in indexed], ensure_ascii=False)}\n"
    )

    try:
        if GEMINI_DEBUG:
            print(f"[gemini] batching {len(indexed)} wines")
            print(f"[gemini] batch prompt: {prompt}")

        resp = model.generate_content(prompt)

        text = _response_text(resp)
        if GEMINI_DEBUG:
            print(f"[gemini] batch raw len: {len(text)}")
            print(f"[gemini] batch raw preview: {resp}")

        arr = _extract_json_array(text)
        if arr is None:
            return wines

        if len(arr) != len(indexed):
            if GEMINI_DEBUG:
                print(f"[gemini] batch length mismatch: got={len(arr)} expected={len(indexed)}")

        for (wine_idx, name), item in zip(indexed, arr):
            if isinstance(item, dict):
                # Persist each enrichment result by name.
                _cache_set(name, item)
                _apply_enrichment(wines[wine_idx], item)

        if GEMINI_DEBUG:
            print("[gemini] batch done")
        return wines
    except Exception as exc:
        if GEMINI_DEBUG:
            print(f"[gemini] batch error: {type(exc).__name__}: {exc}")
            print(traceback.format_exc())

        return wines


def enrich_wine_gemini(w: Wine) -> Wine:
    """Best-effort enrichment.

    Fills missing fields only (does not overwrite existing values).
    """

    if not _enabled():
        return w

    # Single-wine path also consults cache.
    if w.name and w.name.strip():
        cached = _cache_get(w.name)
        if isinstance(cached, dict):
            return _apply_enrichment(w, cached)

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
        _cache_set(w.name, data)
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
