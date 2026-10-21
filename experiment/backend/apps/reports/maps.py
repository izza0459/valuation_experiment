"""The report's location map (CRM feedback RP-01): a static map around the
property's latitude and longitude, with a pin on it. No screenshot or upload.

Built from OpenStreetMap's tiles (free, no key; the credit line their terms
require is printed on the image) and stored with the job's files, so it is
fetched once per location. Google Static Maps (CLAUDE.md §8) can replace
`_tile` later without touching the report.
"""

from __future__ import annotations

import io
import logging
import math
import urllib.request
from decimal import Decimal

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)

TILE = 256
ZOOM = 16
WIDTH, HEIGHT = 900, 420
TILE_URL = "https://tile.openstreetmap.org/{z}/{x}/{y}.png"
# OpenStreetMap asks every app to identify itself.
USER_AGENT = "BayutValuationPlatform/1.0 (property valuation reports)"
CREDIT = "© OpenStreetMap contributors"


def _pixel(lat: float, lon: float, zoom: int) -> tuple[float, float]:
    """Web Mercator: where a point sits on the whole-world image at `zoom`."""
    scale = TILE * 2**zoom
    x = (lon + 180.0) / 360.0 * scale
    lat_rad = math.radians(lat)
    y = (1.0 - math.log(math.tan(lat_rad) + 1.0 / math.cos(lat_rad)) / math.pi) / 2.0 * scale
    return x, y


def _tile(z: int, x: int, y: int) -> bytes:
    request = urllib.request.Request(TILE_URL.format(z=z, x=x, y=y), headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=8) as response:  # noqa: S310 - a fixed https URL
        return response.read()


def render_map(lat: float, lon: float, *, zoom: int = ZOOM, width: int = WIDTH, height: int = HEIGHT) -> bytes:
    """A JPEG centred on the point, with a pin and the map credit."""
    from PIL import Image, ImageDraw

    cx, cy = _pixel(lat, lon, zoom)
    left, top = cx - width / 2, cy - height / 2
    image = Image.new("RGB", (width, height), "#e8e8e8")
    for tx in range(int(left // TILE), int((left + width) // TILE) + 1):
        for ty in range(int(top // TILE), int((top + height) // TILE) + 1):
            tile = Image.open(io.BytesIO(_tile(zoom, tx % 2**zoom, ty))).convert("RGB")
            image.paste(tile, (int(tx * TILE - left), int(ty * TILE - top)))

    draw = ImageDraw.Draw(image)
    # The pin: a teardrop whose point is exactly on the property.
    px, py = width / 2, height / 2
    draw.polygon([(px, py), (px - 11, py - 22), (px + 11, py - 22)], fill="#c62828")
    draw.ellipse([px - 14, py - 44, px + 14, py - 16], fill="#c62828", outline="white", width=3)
    draw.ellipse([px - 5, py - 35, px + 5, py - 25], fill="white")
    # The credit, bottom right on a pale band.
    text_w = draw.textlength(CREDIT)
    draw.rectangle([width - text_w - 12, height - 18, width, height], fill="#ffffffcc")
    draw.text((width - text_w - 6, height - 15), CREDIT, fill="#333333")

    out = io.BytesIO()
    image.save(out, "JPEG", quality=85, optimize=True)
    return out.getvalue()


def map_key(job, lat, lon) -> str:
    return f"jobs/{job.bayut_internal_reference_no}/map/{Decimal(lat):.6f}_{Decimal(lon):.6f}.jpg"


def location_map_key(job, lat, lon) -> str:
    """The stored map for this location, made the first time it's asked for.
    Empty when maps are switched off or the tiles can't be fetched: the report
    then shows the coordinates in place of the map."""
    if lat is None or lon is None or not settings.LOCATION_MAPS:
        return ""
    key = map_key(job, lat, lon)
    if default_storage.exists(key):
        return key
    try:
        png = render_map(float(lat), float(lon))
    except Exception:  # offline, rate-limited: the report still renders
        logger.warning("Couldn't build the location map for %s", job.bayut_internal_reference_no, exc_info=True)
        return ""
    return default_storage.save(key, ContentFile(png))
