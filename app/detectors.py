"""Deterministic waste detection engine.

Pure functions only — no DB, no network, no LLM. Each detector takes parsed
CUR rows and returns structured `DetectedFinding` objects. Because remediation
is irreversible, this layer is the source of truth and is exhaustively unit
tested against the seeded sample manifest.
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field, asdict
from pathlib import Path

from app.config import DETECTOR_CONFIDENCE, SNAPSHOT_AGE_THRESHOLD_DAYS
from app.risk import compute_risk_score, risk_bucket


@dataclass
class DetectedFinding:
    """A single deterministic detection (pre-persistence, pre-enrichment)."""

    resource_id: str
    resource_type: str
    finding_type: str
    region: str
    monthly_waste_usd: float
    confidence: float
    risk_score: int
    risk_bucket: str
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _make(resource_id, resource_type, finding_type, region, cost, details):
    """Build a finding, computing confidence + risk score deterministically."""
    confidence = DETECTOR_CONFIDENCE[finding_type]
    score = compute_risk_score(cost, confidence)
    return DetectedFinding(
        resource_id=resource_id,
        resource_type=resource_type,
        finding_type=finding_type,
        region=region,
        monthly_waste_usd=round(float(cost), 2),
        confidence=confidence,
        risk_score=score,
        risk_bucket=risk_bucket(score),
        details=details,
    )


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------
def load_cur(csv_path: str | Path) -> list[dict]:
    """Parse a sample CUR CSV into a list of row dicts."""
    with Path(csv_path).open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def _cost(row: dict) -> float:
    try:
        return float(row.get("monthly_cost_usd") or 0.0)
    except ValueError:
        return 0.0


# ---------------------------------------------------------------------------
# Detectors (one pure function each)
# ---------------------------------------------------------------------------
def detect_unattached_ebs(rows: list[dict]) -> list[DetectedFinding]:
    out = []
    for r in rows:
        if r.get("resource_type") == "ebs_volume" and r.get("attachment_state") == "unattached":
            out.append(_make(
                r["resource_id"], "ebs_volume", "unattached_ebs_volume",
                r.get("region", ""), _cost(r),
                {"size_gb": r.get("size_gb", ""), "tags": r.get("tags", "")},
            ))
    return out


def detect_idle_instances(rows: list[dict]) -> list[DetectedFinding]:
    out = []
    for r in rows:
        if r.get("resource_type") == "ec2_instance" and r.get("instance_state") == "stopped":
            out.append(_make(
                r["resource_id"], "ec2_instance", "idle_instance",
                r.get("region", ""), _cost(r),
                {"instance_type": r.get("instance_type", ""), "tags": r.get("tags", "")},
            ))
    return out


def detect_unassociated_eips(rows: list[dict]) -> list[DetectedFinding]:
    out = []
    for r in rows:
        if r.get("resource_type") == "elastic_ip" and r.get("eip_association") == "unassociated":
            out.append(_make(
                r["resource_id"], "elastic_ip", "unassociated_eip",
                r.get("region", ""), _cost(r), {},
            ))
    return out


def detect_aged_snapshots(rows: list[dict]) -> list[DetectedFinding]:
    out = []
    for r in rows:
        if r.get("resource_type") != "snapshot":
            continue
        try:
            age = int(r.get("snapshot_age_days") or 0)
        except ValueError:
            continue
        if age > SNAPSHOT_AGE_THRESHOLD_DAYS:
            out.append(_make(
                r["resource_id"], "snapshot", "aged_snapshot",
                r.get("region", ""), _cost(r),
                {"age_days": age, "size_gb": r.get("size_gb", "")},
            ))
    return out


DETECTORS = (
    detect_unattached_ebs,
    detect_idle_instances,
    detect_unassociated_eips,
    detect_aged_snapshots,
)


def run_all(rows: list[dict]) -> list[DetectedFinding]:
    """Run every detector and return the combined findings."""
    findings: list[DetectedFinding] = []
    for detector in DETECTORS:
        findings.extend(detector(rows))
    return findings


def scan_file(csv_path: str | Path) -> list[DetectedFinding]:
    """Convenience: load a CUR CSV and run all detectors."""
    return run_all(load_cur(csv_path))
