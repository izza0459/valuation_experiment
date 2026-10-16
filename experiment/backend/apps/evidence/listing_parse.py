"""Reading a listing someone copied from a property portal.

The valuer opens a listing (Bayut, Property Finder, Property Monitor ...) in
their own browser, selects all, copies, and pastes the text here with the
link. We pick out what a comparable needs and prefill the form for them to
check; nothing is fetched from the portal.
"""

from __future__ import annotations

import re
from datetime import date
from decimal import Decimal, InvalidOperation
from urllib.parse import urlparse

SOURCES = {
    "bayut.com": "bayut",
    "propertyfinder.ae": "property_finder",
    "propertymonitor.ae": "property_monitor",
    "propertymonitor.com": "property_monitor",
    "dubailand.gov.ae": "dld",
}
TYPES = ["Penthouse", "Townhouse", "Villa", "Duplex", "Apartment", "Office", "Shop", "Retail", "Hotel Apartment"]
SQFT_PER_SQM = Decimal("10.76391")
FLOOR = r"floor\s*(?:no\.?|number)?\s*:?\s*(\d{1,3}(?:st|nd|rd|th)?|ground|high|mid|low)\b"
VIEW = r"\b(sea|marina|golf|burj khalifa|canal|park|community|pool|city|lake)\s*views?\b"


def _number(text: str) -> Decimal | None:
    try:
        return Decimal(text.replace(",", ""))
    except InvalidOperation:
        return None


def _scaled(amount: str, unit: str) -> Decimal | None:
    """'1.45' + 'M' -> 1,450,000."""
    value = _number(amount)
    if value is None:
        return None
    unit = (unit or "").lower()
    if unit.startswith("m"):
        value *= 1_000_000
    elif unit.startswith("k"):
        value *= 1_000
    return value


def source_for(link: str) -> str:
    host = urlparse(link or "").netloc.lower()
    return next((source for domain, source in SOURCES.items() if host.endswith(domain)), "other")


def parse(text: str, link: str = "") -> dict:
    """What we could read, plus `found`: the fields we're confident of. The
    valuer checks everything before adding it."""
    text = text or ""
    flat = re.sub(r"[ \t ]+", " ", text)
    joined = re.sub(r"\s*\n\s*", "\n", flat)
    one_line = joined.replace("\n", " ")
    out: dict = {"source": source_for(link), "link": link.strip(), "status": "asking"}

    # Price: the first AED amount large enough to be a sale price ("AED 1,450,000",
    # "1,450,000 AED", "AED 1.45M").
    for match in re.finditer(
        r"(?:AED|Dhs?\.?)\s*([\d][\d,]*(?:\.\d+)?)\s*(M|Million|K)?\b|([\d][\d,]*(?:\.\d+)?)\s*(M|Million|K)?\s*AED",
        one_line, flags=re.I,
    ):
        value = _scaled(match.group(1) or match.group(3), match.group(2) or match.group(4) or "")
        if value and value >= 100_000:
            out["price_aed"] = str(value.quantize(Decimal(1)))
            break

    # Size: sqft first, else sqm converted.
    if m := re.search(r"([\d][\d,]*(?:\.\d+)?)\s*(?:sq\.?\s*ft|sqft|square feet)", one_line, flags=re.I):
        out["bua_sqft"] = str(_number(m.group(1)))
    elif m := re.search(r"([\d][\d,]*(?:\.\d+)?)\s*(?:sq\.?\s*m|sqm|square met)", one_line, flags=re.I):
        sqm = _number(m.group(1))
        if sqm:
            out["bua_sqft"] = str((sqm * SQFT_PER_SQM).quantize(Decimal("0.01")))

    # Bedrooms: "Studio", "1 Bed", "2 Beds", "Bedrooms 3", "3 BR".
    if re.search(r"\bstudio\b", one_line, flags=re.I):
        out["beds"] = 0
    elif m := re.search(r"(\d+)\s*(?:beds?\b|bedrooms?\b|br\b|b/r\b)", one_line, flags=re.I):
        out["beds"] = int(m.group(1))
    elif m := re.search(r"bedrooms?\s*:?\s*(\d+)", one_line, flags=re.I):
        out["beds"] = int(m.group(1))

    # Type: "Type Apartment", "Property type Villa", else the first type word.
    if m := re.search(r"(?:property\s*)?type\s*:?\s*(" + "|".join(TYPES) + r")", one_line, flags=re.I):
        out["property_type"] = m.group(1).title()
    elif m := re.search(r"\b(" + "|".join(TYPES) + r")\b", one_line, flags=re.I):
        out["property_type"] = m.group(1).title()

    # Location: a line like "Marina Gate 1, Marina Gate, Dubai Marina, Dubai".
    for line in joined.split("\n"):
        line = line.strip().strip(".")
        parts = [p.strip() for p in line.split(",") if p.strip()]
        if 3 <= len(parts) <= 6 and parts[-1].lower() in ("dubai", "abu dhabi", "sharjah", "ajman") and len(line) < 160:
            out["building_name"] = parts[0]
            out["community_name"] = parts[-2]
            break

    # Floor and view, when the listing states them.
    if m := re.search(FLOOR, one_line, flags=re.I):
        out["floor"] = m.group(1).title()
    if m := re.search(VIEW, one_line, flags=re.I):
        out["view"] = m.group(1).title()

    out["transaction_date"] = date.today().isoformat()  # an asking price is as of today
    out["found"] = [k for k in ("price_aed", "bua_sqft", "beds", "property_type", "building_name", "community_name")
                    if k in out]
    return out
