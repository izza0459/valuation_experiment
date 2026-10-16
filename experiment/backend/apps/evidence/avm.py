"""AVM v1 (CLAUDE.md §6): simple and explainable.

The suggested value is the median AED/sqft of the comparables the valuer
ticked, applied to the subject's BUA. The range comes from the spread of
those rates (the middle half once there are four or more, otherwise lowest to
highest). Confidence follows how many there are and how tightly they agree.
Every step is kept in `workings` so the screen can show it. The valuer always
sets and signs the final value.

TODO (CLAUDE.md §6): configurable adjustments for size, floor, view, date and
condition. None are applied yet.
"""

from __future__ import annotations

import statistics
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

THOUSAND = Decimal(1000)


def _round_value(value: Decimal) -> Decimal:
    """Valuations are stated to the nearest thousand dirhams."""
    return (value / THOUSAND).quantize(Decimal(1), rounding=ROUND_HALF_UP) * THOUSAND


def _quartiles(rates: list[Decimal]) -> tuple[Decimal, Decimal]:
    if len(rates) < 4:
        return min(rates), max(rates)
    q1, _, q3 = statistics.quantiles(rates, n=4, method="inclusive")
    return Decimal(q1), Decimal(q3)


def confidence(count: int, spread: Decimal) -> str:
    """`spread` is the range's width as a share of the median rate."""
    if count >= 5 and spread <= Decimal("0.15"):
        return "high"
    if count >= 3 and spread <= Decimal("0.30"):
        return "medium"
    return "low"


def compute(comparables: list, subject_bua_sqft, market_value=None) -> dict:
    """`comparables`: Comparable rows. Returns the run's figures and workings,
    or `{"error": ...}` when there is nothing to work from."""
    usable = [c for c in comparables if c.price_aed and c.bua_sqft and c.bua_sqft > 0]
    if not usable:
        return {"error": "Tick at least one comparable with a price and a BUA."}
    if not subject_bua_sqft:
        return {"error": "Enter the subject property's BUA on the Summary tab."}

    subject = Decimal(subject_bua_sqft)
    rates = [(c, (c.price_aed / c.bua_sqft).quantize(Decimal("0.01"))) for c in usable]
    values = sorted(r for _, r in rates)
    median = Decimal(statistics.median(values)).quantize(Decimal("0.01"))
    low_rate, high_rate = _quartiles(values)
    spread = (high_rate - low_rate) / median if median else Decimal(1)

    result = {
        "suggested_value": _round_value(median * subject),
        "low_value": _round_value(low_rate * subject),
        "high_value": _round_value(high_rate * subject),
        "aed_per_sqft": median,
        "confidence": confidence(len(usable), spread),
        "workings": {
            "subject_bua_sqft": str(subject),
            "comparables": [
                {"id": c.id, "label": c.building_name or c.community_name or f"#{c.id}",
                 "price_aed": str(c.price_aed), "bua_sqft": str(c.bua_sqft), "aed_per_sqft": str(r)}
                for c, r in rates
            ],
            "median_aed_per_sqft": str(median),
            "range_aed_per_sqft": [str(low_rate.quantize(Decimal("0.01"))), str(high_rate.quantize(Decimal("0.01")))],
            "range_basis": "middle half of the rates" if len(values) >= 4 else "lowest to highest rate",
            "spread_pct": str((spread * 100).quantize(Decimal("0.1"))),
            "formula": "median AED/sqft × subject BUA (sqft), rounded to the nearest AED 1,000",
            "adjustments": [],
            "skipped": len(comparables) - len(usable),
        },
    }
    if market_value:
        deviation = (Decimal(market_value) - result["suggested_value"]) / result["suggested_value"] * 100
        result["workings"]["market_value"] = str(market_value)
        result["workings"]["deviation_pct"] = str(deviation.quantize(Decimal("0.1")))
        result["workings"]["deviation_over_threshold"] = abs(deviation) > Decimal(
            str(settings.AVM_DEVIATION_THRESHOLD_PCT)
        )
    return result
