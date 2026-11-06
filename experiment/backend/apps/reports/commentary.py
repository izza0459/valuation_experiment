"""Filling in the valuation commentary templates (Nov 2026).

The templates leave `xxxxx` and `[bracketed]` blanks: asking and sold ranges,
the subject's size, floor and view, the value. Whatever the job already knows
is filled in for the report from the ticked comparables and the job's own
fields; a blank only the valuer can answer ("[frontage/visibility]") is left,
and the report can't be finalised while one remains (`remaining_blanks`).

The fill works on phrases, not positions, so a valuer who edits the text keeps
whatever they wrote and still gets the blanks they left filled.
"""

import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal

from apps.jobs import calculations

X = "xxxxx"
# What the fill leaves for the valuer: an xxxxx, or a [blank] (not the
# reinstatement figure's [●], checked on its own).
_LEFT = re.compile(r"xxxxx|\[(?!●\])[^\[\]\n]{1,160}\]")

SOLD = {"sold", "sold_primary"}


@dataclass
class Facts:
    """What the commentary can be filled from. Empty values leave the blank."""

    beds: int | None = None
    bua_sqft: Decimal | None = None
    plot_sqft: Decimal | None = None
    floor: str = ""
    views: str = ""
    building: str = ""
    community: str = ""
    category: str = ""  # the property_category value, e.g. "villa"
    occupancy: str = ""  # the occupancy value, e.g. "tenanted"
    upgraded: bool = False
    valuation_date: str = ""
    market_value: Decimal | None = None
    rate_per_sqft: Decimal | None = None
    parkings: int | None = None
    rent_low: Decimal | None = None
    rent_high: Decimal | None = None
    land_value: Decimal | None = None
    replacement_cost: Decimal | None = None
    # The ticked comparables: (status, price, price per sqft).
    comparables: list[tuple[str, Decimal | None, Decimal | None]] = field(default_factory=list)


def _n(value) -> str:
    """1291.67 -> "1,292"; whole numbers, as the templates' figures are."""
    return f"{Decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP):,}"


def _range(values) -> tuple[str, str] | None:
    values = [v for v in values if v]
    return (_n(min(values)), _n(max(values))) if values else None


def _ordinal(floor: str) -> str:
    """"23" -> "23rd floor"; "G" -> "ground floor"; anything else as written."""
    text = (floor or "").strip()
    if not text:
        return ""
    if text.upper() in {"G", "GF", "GROUND", "0"}:
        return "ground floor"
    if text.isdigit():
        n = int(text)
        suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
        return f"{n}{suffix} floor"
    return text if "floor" in text.lower() else f"{text} floor"


def _plural(category: str) -> str:
    plurals = {"villa": "villas", "custom_villa": "villas", "townhouse": "townhouses", "duplex": "duplexes"}
    return plurals.get(category, "")


def _premium(category: str) -> str:
    """The Rare Property template's evidence: like for like at the top end."""
    kinds = {"penthouse": "penthouses", "duplex": "apartments", "apartment": "apartments",
             "villa": "villas", "custom_villa": "villas", "townhouse": "villas"}
    return f"premium {kinds[category]}" if category in kinds else ""


def _finish(category: str) -> str:
    if category.startswith("shell_core"):
        return "shell and core"
    if category.startswith("fitted"):
        return "fitted"
    return ""


def _occupancy(value: str) -> str:
    if value in {"tenanted", "multi_tenanted", "tenanted_short_term"}:
        return "tenanted"
    return {"vacant": "vacant", "assumed_vacant": "vacant", "owner_occupied": "owner occupied"}.get(value, "")


def fill(text: str, facts: Facts) -> str:
    """The commentary with every blank the job can answer filled in."""
    if not text or (X not in text and "[" not in text):
        return text or ""

    asking = [(p, r) for status, p, r in facts.comparables if status.startswith("asking")]
    sold = [(p, r) for status, p, r in facts.comparables if status in SOLD]
    ask_price, ask_rate = _range(p for p, _ in asking), _range(r for _, r in asking)
    sold_price, sold_rate = _range(p for p, _ in sold), _range(r for _, r in sold)
    top_ask_price = ask_price[1] if ask_price else None
    top_ask_rate = ask_rate[1] if ask_rate else None
    mv = _n(facts.market_value) if facts.market_value else None
    rate = _n(facts.rate_per_sqft) if facts.rate_per_sqft else None
    rent_rate = None
    if facts.rent_low and facts.rent_high and facts.bua_sqft:
        rent_rate = (_n(facts.rent_low / facts.bua_sqft), _n(facts.rent_high / facts.bua_sqft))
    net_yield = None
    if facts.rent_low and facts.rent_high and facts.market_value:
        mid = (facts.rent_low + facts.rent_high) / 2
        net_yield = f"{(mid / facts.market_value * 100).quantize(Decimal('0.1'), rounding=ROUND_HALF_UP)}"
    floor = _ordinal(facts.floor)
    area = ", ".join(p for p in (facts.building, facts.community) if p)

    # (phrase, what replaces it, or None to leave it), most specific first.
    steps: list[tuple[str, object]] = [
        # Ranges from the ticked comparables: asking prices, then DLD transactions.
        (r"AED xxxxx to AED xxxxx \(AED xxxxx to AED xxxxx per sq ft\)",
         sold_price and sold_rate and f"AED {sold_price[0]} to AED {sold_price[1]} "
                                      f"(AED {sold_rate[0]} to AED {sold_rate[1]} per sq ft)"),
        (r"(?<=listed from )AED xxxxx to AED xxxxx per sq ft",
         ask_rate and f"AED {ask_rate[0]} to AED {ask_rate[1]} per sq ft"),
        (r"(?<=listed from )AED xxxxx to AED xxxxx",
         ask_price and f"AED {ask_price[0]} to AED {ask_price[1]}"),
        (r"(?<=transactions indicate )AED xxxxx to AED xxxxx per sq ft",
         sold_rate and f"AED {sold_rate[0]} to AED {sold_rate[1]} per sq ft"),
        (r"(?<=Rental evidence indicates )AED xxxxx to AED xxxxx per sq ft",
         rent_rate and f"AED {rent_rate[0]} to AED {rent_rate[1]} per sq ft"),
        (r"(?<=net initial yield of )xxxxx%", net_yield and f"{net_yield}%"),
        # Brokers: listings above the dearest asking; offers around the value.
        (r"(?<=listings above )AED xxxxx per sq ft", top_ask_rate and f"AED {top_ask_rate} per sq ft"),
        (r"(?<=listings above )AED xxxxx", top_ask_price and f"AED {top_ask_price}"),
        (r"(?<=around )AED xxxxx per sq ft", rate and f"AED {rate} per sq ft"),
        (r"(?<=around )AED xxxxx", mv and f"AED {mv}"),
        # The opinion of value.
        (r"(?<=is )AED xxxxx \(AED xxxxx per sq ft\)", mv and rate and f"AED {mv} (AED {rate} per sq ft)"),
        (r"(?<=is )AED xxxxx \(AED xxxxx\)",
         mv and f"AED {mv} ({calculations.amount_in_words(facts.market_value)})"),
        # The optional cost-approach cross-check: kept with its figures, else dropped.
        (r"\[(As a cross-check, we have also adopted the cost approach, comprising land value of )AED xxxxx"
         r"( plus depreciated replacement cost of )AED xxxxx(\.)\]\s?",
         (lambda m: f"{m.group(1)}AED {_n(facts.land_value)}{m.group(2)}AED {_n(facts.replacement_cost)}"
                    f"{m.group(3)} ") if facts.land_value and facts.replacement_cost else (lambda m: "")),
        # The subject's attributes.
        (r"xxxxx-bedroom", facts.beds is not None and f"{facts.beds}-bedroom"),
        (r"xxxxx sq ft BUA", facts.bua_sqft and f"{_n(facts.bua_sqft)} sq ft BUA"),
        (r",? ?\[xxxxx sq ft plot/terrace\]",
         (lambda m: f", {_n(facts.plot_sqft)} sq ft plot") if facts.plot_sqft else None),
        (r"xxxxx sq ft plot", facts.plot_sqft and f"{_n(facts.plot_sqft)} sq ft plot"),
        (r"xxxxx sq ft(?! per)", facts.bua_sqft and f"{_n(facts.bua_sqft)} sq ft"),
        (r"xxxxx floor", floor),
        (r"xxxxx parking spaces",
         facts.parkings is not None and f"{facts.parkings} parking space{'s' if facts.parkings != 1 else ''}"),
        (r"\[ground/podium level\]", floor and f"{floor} level"),
        # Names, views and dates.
        (r"\[valuation date\]", facts.valuation_date),
        (r"\[Development\]", facts.building or facts.community),
        (r"\[Community\]", facts.community),
        (r"\[Building/Area\]", area),
        (r"\[Development/Community/comparable prime locations\]", facts.community or facts.building),
        (r"\[(?:position/)?view\]", facts.views),
        (r"\[villas/townhouses\]", _plural(facts.category)),
        (r"\[premium apartments/villas/penthouses\]", _premium(facts.category)),
        (r"\[shell and core/fitted\]", _finish(facts.category)),
        (r"\[vacant/tenanted\]", _occupancy(facts.occupancy)),
        (r"\[(?:condition|specification)/upgrades\]", "upgraded" if facts.upgraded else "standard specification"),
    ]
    for pattern, value in steps:
        if not value:
            continue
        text = re.sub(pattern, value if callable(value) else str(value).replace("\\", r"\\"), text)
    return text


def remaining_blanks(text: str) -> list[str]:
    """The blanks still in `text`, once each: ["xxxxx", "[frontage/visibility]"]."""
    return list(dict.fromkeys(_LEFT.findall(text or "")))
