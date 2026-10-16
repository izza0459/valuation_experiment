"""Pure calculation helpers shared by the tab-data models and the report
generator (CLAUDE.md §2, §5, §6; build order step 3: "calculations: sqft,
age, rate/sqft, forced sale, DMS, value-in-words")."""

from datetime import date
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from num2words import num2words


def sqm_to_sqft(sqm) -> Decimal:
    if sqm in (None, ""):
        return None
    return (Decimal(sqm) * Decimal(str(settings.SQFT_PER_SQM))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def sqft_to_sqm(sqft) -> Decimal:
    if sqft in (None, ""):
        return None
    return (Decimal(sqft) / Decimal(str(settings.SQFT_PER_SQM))).quantize(
        Decimal("0.01"), rounding=ROUND_HALF_UP
    )


def format_area(sqft) -> str:
    """Areas are entered in sqft (field dictionary): `519 sqft (48.22 sqm)`."""
    if sqft in (None, ""):
        return "Not Applicable"
    sqft = Decimal(sqft)
    whole = sqft == sqft.to_integral_value()
    return f"{sqft:,.0f} sqft ({sqft_to_sqm(sqft):,.2f} sqm)" if whole else \
        f"{sqft:,.2f} sqft ({sqft_to_sqm(sqft):,.2f} sqm)"


def decimal_to_dms(value: float, is_lat: bool) -> str:
    """25.0403° -> 25°2'25.1"N (CLAUDE.md §4 Tab 2)."""
    if value is None:
        return ""
    hemisphere = ("N" if value >= 0 else "S") if is_lat else ("E" if value >= 0 else "W")
    value = abs(float(value))
    degrees = int(value)
    minutes_full = (value - degrees) * 60
    minutes = int(minutes_full)
    seconds = (minutes_full - minutes) * 60
    return f"{degrees}°{minutes}'{seconds:.1f}\"{hemisphere}"


def lat_long_to_dms(latitude, longitude) -> str:
    if latitude is None or longitude is None:
        return ""
    return f"{decimal_to_dms(latitude, is_lat=True)} {decimal_to_dms(longitude, is_lat=False)}"


def exact_age(built_date: date, as_of: date | None = None) -> int | None:
    if built_date is None:
        return None
    as_of = as_of or date.today()
    years = as_of.year - built_date.year
    if (as_of.month, as_of.day) < (built_date.month, built_date.day):
        years -= 1
    return max(years, 0)


def age_from_year(built_year: int, as_of: date | None = None) -> int | None:
    if not built_year:
        return None
    return max((as_of or date.today()).year - built_year, 0)


def views_summary(front_views: str, rear_views: str) -> str:
    """One line for the report's Property Details table, from the front and
    rear views the inspector recorded: 'Front: Marina; Rear: Road'."""
    parts = []
    if (front_views or "").strip():
        parts.append(f"Front: {front_views.strip()}")
    if (rear_views or "").strip():
        parts.append(f"Rear: {rear_views.strip()}")
    return "; ".join(parts)


def _utility_phrase(status: str) -> str:
    return (status or "").replace("_", " ") or "not recorded"


def utilities_summary(electrical: str, water: str, sewerage: str) -> str:
    """Utilities connection status for the report (CLAUDE.md §4 'missing
    fields'), from the three statuses already captured on the Inspection tab.

    All the same reads as one sentence; otherwise each is stated, so a
    'not connected' or 'assumed connected' is never folded into a blanket
    claim. Says nothing until at least one status has been recorded."""
    statuses = {"Electricity": electrical, "Water": water, "Sewerage": sewerage}
    if not any(statuses.values()):
        return ""
    if len(set(statuses.values())) == 1:
        return f"Electricity, water and sewerage: {_utility_phrase(electrical)}."
    return "; ".join(f"{name}: {_utility_phrase(status)}" for name, status in statuses.items()) + "."


def rate_per_sqft(value, bua_sqft) -> Decimal | None:
    if not value or not bua_sqft:
        return None
    bua_sqft = Decimal(bua_sqft)
    if bua_sqft == 0:
        return None
    return (Decimal(value) / bua_sqft).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def forced_sale_value(market_value, discount_pct) -> Decimal | None:
    if market_value is None:
        return None
    discount_pct = Decimal(discount_pct if discount_pct is not None else 10)
    return (Decimal(market_value) * (Decimal(100) - discount_pct) / Decimal(100)).quantize(
        Decimal("1"), rounding=ROUND_HALF_UP
    )


def _capitalise_words(raw: str) -> str:
    def cap_word(word: str) -> str:
        if word == "and":
            return word
        return "-".join(p.capitalize() for p in word.split("-"))

    return " ".join(cap_word(w) for w in raw.replace(",", "").split(" "))


def amount_in_words(amount) -> str:
    """725000 -> 'Seven Hundred and Twenty-Five Thousand UAE Dirhams'
    (CLAUDE.md §5).

    The words appear on a signed report alongside the figures, so they must
    never disagree with them: a fractional amount is rendered down to fils
    rather than silently rounded to a different whole number of dirhams.
    """
    if amount is None:
        return ""

    value = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if value < 0:
        # A negative market value is not a thing; printing "Minus ..." onto a
        # bank report is worse than refusing to produce it.
        raise ValueError(f"Cannot render a negative amount in words: {amount!r}")

    dirhams = int(value)
    fils = int((value - dirhams) * 100)

    unit = "Dirham" if dirhams == 1 else "Dirhams"
    words = f"{_capitalise_words(num2words(dirhams, lang='en'))} UAE {unit}"
    if fils:
        words += f" and {_capitalise_words(num2words(fils, lang='en'))} Fils"
    return words


def format_address_as_per_document(property_no, plot_no, municipality_no, building_no,
                                    building_name, community, emirate="Dubai",
                                    country="United Arab Emirates") -> str:
    """CLAUDE.md §4 Tab 2: "Property No. X, Plot No. Y, Municipality No. Z,
    Building No. 1, <Building>, <Community>, Dubai, United Arab Emirates"."""
    parts = []
    if property_no:
        parts.append(f"Property No. {property_no}")
    if plot_no:
        parts.append(f"Plot No. {plot_no}")
    if municipality_no:
        parts.append(f"Municipality No. {municipality_no}")
    if building_no:
        parts.append(f"Building No. {building_no}")
    if building_name:
        parts.append(building_name)
    if community:
        parts.append(community)
    parts.append(emirate)
    parts.append(country)
    return ", ".join(parts)
