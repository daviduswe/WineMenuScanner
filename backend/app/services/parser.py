from __future__ import annotations

import re
from typing import Optional

from app.models.wine import Price, Wine

# Prices can be: 12, 12.5, 12,5, $12, €12.5, etc.
PRICE_RE = re.compile(r"(?P<currency>[$€£])?\s*(?P<price>\d{1,4}(?:[\.,]\d{1,2})?)")
VINTAGE_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

# Treat these tokens as explicit missing values (case-insensitive).
NA_RE = re.compile(r"\b(?:na|n/a|n\.a\.|none|nil|-)\b", re.IGNORECASE)

# Header/table column tokens that often appear to the right of group headers.
# These should NOT make a line become a wine row.
HEADER_TOKEN_RE = re.compile(
    r"\b(?:glass|bottle|btg|btl|ml|cl|oz|\d{2,4}\s?(?:ml|cl|oz))\b",
    re.IGNORECASE,
)


def _to_float(s: str) -> Optional[float]:
    s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def _is_plausible_price(val: Optional[float]) -> bool:
    if val is None:
        return False
    # Typical menu price range; avoids treating sizes like 175ml as price.
    return 1.0 <= val <= 500.0


def _extract_price_tokens(line: str) -> tuple[Optional[str], list[Optional[float]]]:
    """Extract up to two price columns from a line.

    IMPORTANT: this function now only returns price columns when the line
    *ends* with 1–2 plausible price tokens (or N/A tokens). This prevents group
    headers with right-side labels like "glass", "bottle", or "175ml" from being
    misclassified as wine rows.
    """

    # Quick header-label hint: if the line contains common header tokens and does not
    # contain obvious currency, prefer treating it as a header.
    contains_header_tokens = HEADER_TOKEN_RE.search(line) is not None

    # Identify vintages to ignore when extracting prices
    vintage_spans = [m.span() for m in VINTAGE_RE.finditer(line)]

    def is_inside_vintage(idx: int) -> bool:
        for a, b in vintage_spans:
            if a <= idx < b:
                return True
        return False

    currency: Optional[str] = None

    # Build a token stream in reading order
    token_stream: list[tuple[int, int, Optional[str], Optional[float], str]] = []

    for m in NA_RE.finditer(line):
        token_stream.append((m.start(), m.end(), None, None, "na"))

    for m in PRICE_RE.finditer(line):
        if is_inside_vintage(m.start()):
            continue
        cur = m.group("currency")
        val = _to_float(m.group("price"))
        token_stream.append((m.start(), m.end(), cur, val, "num"))

    token_stream.sort(key=lambda t: t[0])

    if not token_stream:
        return None, []

    # Consider only the last 1–2 tokens as columns. Require that they are at the end.
    cols = token_stream[-2:] if len(token_stream) > 2 else token_stream

    # Ensure the last token is near the end of the line (allow trailing punctuation/space)
    last_end = cols[-1][1]
    if line[last_end:].strip(" \t.:|/"):
        # There is other non-trailing content after the last numeric/NA token.
        # This is likely not a price column layout.
        return None, []

    values: list[Optional[float]] = []

    for _, __, cur, val, kind in cols:
        if cur and not currency:
            currency = cur
        if kind == "num":
            values.append(val)
        else:
            values.append(None)

    # If header tokens exist and we have no currency symbol, be stricter:
    # reject if parsed numbers are implausible prices (e.g., 175 from 175ml).
    if contains_header_tokens and not currency:
        if any(v is not None and not _is_plausible_price(v) for v in values):
            return None, []

    # Also reject if *all* numeric values are implausible and there is no explicit currency.
    if not currency:
        numeric_vals = [v for v in values if v is not None]
        if numeric_vals and all(not _is_plausible_price(v) for v in numeric_vals):
            return None, []

    return currency, values


def parse_wines_from_text(raw_text: str) -> list[Wine]:
    """Parse OCR text into wine objects.

    Your menu format:
    - Group headers can appear multiple times.
    - A wine entry may appear as either:
      (A) single line: name + 1-2 price columns, OR
      (B) multi-line: group header, then wine name line (no prices), followed by
          one or two lines that are just prices (e.g., 'n/a' then '64').

    Key heuristic:
    - If a no-price line appears while we already have a group, it is treated as a
      wine name (pending wine) unless it looks like a header/footer label.
    """

    wines: list[Wine] = []
    current_group: Optional[str] = None

    pending_wine: Optional[Wine] = None
    pending_price_slots_filled = 0  # 0 = none, 1 = glass slot consumed, 2 = bottle slot consumed

    def looks_like_header_label(line: str) -> bool:
        # Header lines usually contain words like glass/bottle or sizes.
        if HEADER_TOKEN_RE.search(line):
            return True
        # Very short uppercase-ish labels are likely headers (e.g., RED WINE, WHITE)
        compact = re.sub(r"[^A-Za-z]", "", line)
        if compact and len(compact) <= 18 and compact.upper() == compact:
            return True
        return False

    lines = [ln.strip() for ln in (raw_text or "").splitlines()]
    for ln in lines:
        if not ln:
            continue

        currency, prices = _extract_price_tokens(ln)

        # Pure price-line continuation (n/a, 64, $12.5)
        is_pure_price_line = False
        if prices:
            tmp = ln
            tmp = NA_RE.sub(" ", tmp)
            tmp = PRICE_RE.sub(" ", tmp)
            tmp = VINTAGE_RE.sub(" ", tmp)
            if tmp.strip(" \t|:.-") == "":
                is_pure_price_line = True

        # If we have a pure price line but *no* pending wine name, drop it.
        # This commonly happens when OCR reads the menu in columns/out-of-order and
        # separates the price column from the wine-name column.
        if pending_wine is None and is_pure_price_line:
            continue

        if pending_wine is not None and is_pure_price_line:
            # Assign in order: glass first, then bottle.
            # Special case: if the line is a single numeric value and we already consumed
            # a glass slot with an explicit N/A earlier, treat this as bottle.

            # Determine if this line contains at least one numeric price token
            numeric_in_line = any(v is not None for v in prices)
            only_one_col = len(prices) == 1

            for val in prices:
                if pending_price_slots_filled == 0:
                    pending_wine.price.glass = val
                    pending_price_slots_filled = 1
                elif pending_price_slots_filled == 1:
                    pending_wine.price.bottle = val
                    pending_price_slots_filled = 2
                else:
                    break

            # If we consumed a glass slot earlier via explicit N/A and now we see a single
            # numeric column, ensure it lands in bottle.
            if (
                numeric_in_line
                and only_one_col
                and pending_price_slots_filled == 1
                and pending_wine.price.glass is None
            ):
                pending_wine.price.bottle = prices[0]
                pending_price_slots_filled = 2

            if currency and not pending_wine.price.currency:
                pending_wine.price.currency = currency

            # Flush rules:
            # - flush immediately if we now have both columns, OR
            # - flush immediately if we just filled bottle, OR
            # - flush if this line had 2 columns.
            if pending_price_slots_filled >= 2:
                wines.append(pending_wine)
                pending_wine = None
                pending_price_slots_filled = 0
            continue

        # No price tokens on this line.
        if len(prices) == 0:
            # If we have no group yet, this is the first group header.
            if current_group is None:
                current_group = ln.strip().rstrip(":")
                continue

            # If this looks like a header label row (e.g., 'Glass Bottle 175ml'), ignore it.
            if looks_like_header_label(ln):
                continue

            # Otherwise treat as wine name line under the current group.
            if pending_wine is None:
                pending_wine = Wine(
                    id="",
                    rawText=ln,
                    wineGroup=current_group,
                    section=current_group,
                    name=ln,
                    vintage=None,
                    price=Price(currency=None, glass=None, bottle=None),
                )
                pending_price_slots_filled = 0
                continue

            # If somehow we already have a pending wine and another name line appears,
            # flush the pending (without prices) and start a new pending wine.
            wines.append(pending_wine)
            pending_wine = Wine(
                id="",
                rawText=ln,
                wineGroup=current_group,
                section=current_group,
                name=ln,
                vintage=None,
                price=Price(currency=None, glass=None, bottle=None),
            )
            pending_price_slots_filled = 0
            continue

        # This line has prices and is not a pure continuation for a pending wine.
        vintage_match = VINTAGE_RE.search(ln)
        vintage = int(vintage_match.group(1)) if vintage_match else None

        name = ln
        if vintage_match:
            name = name.replace(vintage_match.group(1), " ")

        # Remove last two price-ish tokens from the name
        name_clean = name
        spans: list[tuple[int, int]] = []
        for m in NA_RE.finditer(name_clean):
            spans.append(m.span())
        for m in PRICE_RE.finditer(name_clean):
            spans.append(m.span())
        spans.sort(key=lambda s: s[0])
        for a, b in reversed(spans[-2:]):
            name_clean = (name_clean[:a] + " " + name_clean[b:]).strip()

        name_clean = " ".join(name_clean.split()).strip("-–— ")

        glass = prices[0] if len(prices) >= 1 else None
        bottle = prices[1] if len(prices) >= 2 else None

        wine = Wine(
            id="",
            rawText=ln,
            wineGroup=current_group,
            section=current_group,
            name=name_clean or None,
            vintage=vintage,
            price=Price(currency=currency, glass=glass, bottle=bottle),
        )
        wines.append(wine)

    if pending_wine is not None:
        wines.append(pending_wine)

    for i, w in enumerate(wines, start=1):
        w.id = str(i)

    return wines
