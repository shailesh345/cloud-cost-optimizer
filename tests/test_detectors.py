"""Phase 2 acceptance: detectors find EXACTLY the seeded waste, no more, no less.

The ground truth comes from app.sample_data.build_manifest(), which is derived
from the same RESOURCES list the CSV is written from — so data and expectations
cannot drift.
"""

from __future__ import annotations

import pytest

from app.config import DETECTOR_CONFIDENCE
from app.detectors import (
    detect_aged_snapshots,
    detect_idle_instances,
    detect_unassociated_eips,
    detect_unattached_ebs,
    load_cur,
    run_all,
    scan_file,
)
from app.risk import compute_risk_score, risk_bucket
from app.sample_data import build_manifest, generate


@pytest.fixture(scope="module")
def sample(tmp_path_factory):
    """Generate a fresh sample dataset in an isolated temp dir."""
    data_dir = tmp_path_factory.mktemp("data")
    csv_path, _ = generate(data_dir)
    rows = load_cur(csv_path)
    findings = run_all(rows)
    return {"csv": csv_path, "rows": rows, "findings": findings, "manifest": build_manifest()}


# --- Totals --------------------------------------------------------------
def test_total_finding_count(sample):
    assert len(sample["findings"]) == sample["manifest"]["total_findings"] == 10


def test_total_monthly_waste(sample):
    total = round(sum(f.monthly_waste_usd for f in sample["findings"]), 2)
    assert total == sample["manifest"]["total_monthly_waste_usd"] == 149.70


# --- Per-finding-type counts & dollars ----------------------------------
@pytest.mark.parametrize("finding_type", [
    "unattached_ebs_volume", "idle_instance", "unassociated_eip", "aged_snapshot",
])
def test_per_type_count_and_waste(sample, finding_type):
    expected = sample["manifest"]["by_finding_type"][finding_type]
    matched = [f for f in sample["findings"] if f.finding_type == finding_type]
    assert len(matched) == expected["count"]
    assert round(sum(f.monthly_waste_usd for f in matched), 2) == expected["monthly_waste_usd"]


def test_each_detector_in_isolation(sample):
    rows = sample["rows"]
    assert len(detect_unattached_ebs(rows)) == 3
    assert len(detect_idle_instances(rows)) == 2
    assert len(detect_unassociated_eips(rows)) == 2
    assert len(detect_aged_snapshots(rows)) == 3


# --- No false positives (healthy decoys stay clean) ---------------------
def test_healthy_resources_not_flagged(sample):
    flagged = {f.resource_id for f in sample["findings"]}
    decoys = {"vol-1aaaaaa", "i-1bbbbbb", "eipalloc-1cccccc", "snap-1dddddd"}
    assert decoys.isdisjoint(flagged)


# --- Snapshot age boundary (threshold = 90) -----------------------------
def test_snapshot_age_boundary(sample):
    flagged = {f.resource_id for f in sample["findings"]}
    assert "snap-0dadddd" in flagged      # age 95 > 90 -> flagged
    assert "snap-1dddddd" not in flagged  # age 30 -> clean


# --- Risk Score correctness ---------------------------------------------
def test_confidence_matches_config(sample):
    for f in sample["findings"]:
        assert f.confidence == DETECTOR_CONFIDENCE[f.finding_type]


def test_risk_scores_are_self_consistent(sample):
    for f in sample["findings"]:
        assert 0 <= f.risk_score <= 100
        assert f.risk_bucket == risk_bucket(f.risk_score)
        assert f.risk_score == compute_risk_score(f.monthly_waste_usd, f.confidence)


def test_spot_check_known_scores(sample):
    by_id = {f.resource_id: f for f in sample["findings"]}
    # $40 unattached EBS, conf 0.95 -> round(100*(0.6*0.40 + 0.4*0.95)) = 62
    assert by_id["vol-0b2bbbb"].risk_score == 62
    assert by_id["vol-0b2bbbb"].risk_bucket == "Medium"
    # $5 aged snapshot, conf 0.60 -> round(100*(0.6*0.05 + 0.4*0.60)) = 27 (Low)
    assert by_id["snap-0b8bbbb"].risk_score == 27
    assert by_id["snap-0b8bbbb"].risk_bucket == "Low"


# --- Determinism --------------------------------------------------------
def test_detection_is_reproducible(sample):
    again = [f.to_dict() for f in run_all(sample["rows"])]
    first = [f.to_dict() for f in sample["findings"]]
    assert again == first


def test_scan_file_matches_run_all(sample):
    assert [f.to_dict() for f in scan_file(sample["csv"])] == \
           [f.to_dict() for f in sample["findings"]]
