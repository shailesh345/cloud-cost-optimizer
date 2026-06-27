"""Deterministic Risk Score computation.

Defined here (not in the LLM layer) so it is fully reproducible and unit
testable. The LLM may *explain* a risk ranking, but the number itself is
computed by this module.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import (
    FINANCIAL_NORMALIZATION_CAP_USD,
    RISK_BUCKET_THRESHOLDS,
    RISK_WEIGHTS,
)


def normalize_financial(monthly_waste_usd: float) -> float:
    """Map monthly waste to [0.0, 1.0] against the configured cap."""
    capped = max(0.0, monthly_waste_usd)
    return min(capped / FINANCIAL_NORMALIZATION_CAP_USD, 1.0)


def compute_risk_score(monthly_waste_usd: float, confidence: float) -> int:
    """Blend financial impact and detector confidence into a 0-100 score."""
    confidence = min(max(confidence, 0.0), 1.0)
    financial = normalize_financial(monthly_waste_usd)
    score = 100.0 * (
        RISK_WEIGHTS["financial"] * financial
        + RISK_WEIGHTS["confidence"] * confidence
    )
    return round(score)


def risk_bucket(score: int) -> str:
    """Bucket a 0-100 score into High / Medium / Low."""
    if score >= RISK_BUCKET_THRESHOLDS["high"]:
        return "High"
    if score >= RISK_BUCKET_THRESHOLDS["medium"]:
        return "Medium"
    return "Low"


@dataclass
class AggregateRisk:
    """Dashboard roll-up that derives entirely from per-finding scores."""

    total_monthly_waste_usd: float
    aggregate_score: int          # waste-weighted average of finding scores
    bucket: str                   # High/Med/Low for the aggregate score
    counts: dict                  # {"High": n, "Medium": n, "Low": n}


def aggregate_risk(findings: list) -> AggregateRisk:
    """Roll per-finding risk up into a single portfolio view.

    `findings` is any iterable of objects exposing `monthly_waste_usd` and
    `risk_score` attributes (ORM rows or dataclasses both work).
    """
    counts = {"High": 0, "Medium": 0, "Low": 0}
    total_waste = 0.0
    weighted_sum = 0.0

    for f in findings:
        waste = float(getattr(f, "monthly_waste_usd", 0.0) or 0.0)
        score = int(getattr(f, "risk_score", 0) or 0)
        total_waste += waste
        weighted_sum += waste * score
        counts[risk_bucket(score)] += 1

    # Waste-weighted average so big-money findings dominate the headline score;
    # fall back to a plain mean if there is zero waste but findings exist.
    if total_waste > 0:
        agg = round(weighted_sum / total_waste)
    elif findings:
        agg = round(sum(int(getattr(f, "risk_score", 0) or 0) for f in findings) / len(findings))
    else:
        agg = 0

    return AggregateRisk(
        total_monthly_waste_usd=round(total_waste, 2),
        aggregate_score=agg,
        bucket=risk_bucket(agg),
        counts=counts,
    )
