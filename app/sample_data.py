"""Deterministic sample AWS Cost & Usage Report (CUR) generator.

$0 / NO LIVE CLOUD. This produces a self-contained, fully reproducible sample
dataset with *deliberately seeded waste*. There is no randomness: the rows are
declared explicitly so the unit tests in Phase 2 can assert exact counts and
dollar amounts against the manifest emitted here.

Schema note: a real AWS CUR carries cost line items; the orphaned/idle *state*
of a resource normally comes from EC2 describe-* APIs. For an offline, $0,
reproducible MVP we enrich the CUR with the state columns the detectors need,
so the file is self-contained. Snapshot age is stored as an explicit integer
(not computed from a creation date vs. "now") to guarantee reproducibility.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

from app.config import DATA_DIR

# Fixed billing period so output is byte-identical on every run.
BILLING_START = "2026-06-01"
BILLING_END = "2026-06-30"

CSV_PATH = DATA_DIR / "sample_cur.csv"
MANIFEST_PATH = DATA_DIR / "sample_manifest.json"

CSV_COLUMNS = [
    "line_item_id",
    "resource_id",
    "resource_type",
    "region",
    "usage_start_date",
    "usage_end_date",
    "monthly_cost_usd",
    "attachment_state",   # ebs_volume: attached | unattached
    "instance_state",     # ec2_instance: running | stopped
    "eip_association",     # elastic_ip: associated | unassociated
    "snapshot_age_days",  # snapshot: integer age in days
    "size_gb",
    "instance_type",
    "tags",
]


def _row(line_id, resource_id, rtype, region, cost, **extra):
    base = {c: "" for c in CSV_COLUMNS}
    base.update(
        line_item_id=line_id,
        resource_id=resource_id,
        resource_type=rtype,
        region=region,
        usage_start_date=BILLING_START,
        usage_end_date=BILLING_END,
        monthly_cost_usd=f"{cost:.2f}",
    )
    base.update(extra)
    return base


# ---------------------------------------------------------------------------
# Resource inventory. Each row is either WASTEFUL (should be flagged) or
# HEALTHY (must NOT be flagged — proves the detectors don't over-fire).
# ---------------------------------------------------------------------------
RESOURCES = [
    # --- WASTE: 3 unattached EBS volumes ($60.00) ---
    _row("li-001", "vol-0a1aaaa", "ebs_volume", "us-east-1", 8.00,
         attachment_state="unattached", size_gb="100", tags="env=dev"),
    _row("li-002", "vol-0b2bbbb", "ebs_volume", "us-west-2", 40.00,
         attachment_state="unattached", size_gb="500", tags="env=staging"),
    _row("li-003", "vol-0c3cccc", "ebs_volume", "us-east-1", 12.00,
         attachment_state="unattached", size_gb="150", tags=""),

    # --- WASTE: 2 stopped-but-billed / idle instances ($45.00) ---
    _row("li-004", "i-0d4dddd", "ec2_instance", "us-east-1", 30.00,
         instance_state="stopped", instance_type="m5.large", tags="env=dev"),
    _row("li-005", "i-0e5eeee", "ec2_instance", "eu-west-1", 15.00,
         instance_state="stopped", instance_type="t3.medium", tags="env=test"),

    # --- WASTE: 2 unassociated Elastic IPs ($7.20) ---
    _row("li-006", "eipalloc-0f6ffff", "elastic_ip", "us-east-1", 3.60,
         eip_association="unassociated"),
    _row("li-007", "eipalloc-0a7aaaa", "elastic_ip", "us-west-2", 3.60,
         eip_association="unassociated"),

    # --- WASTE: 3 aged snapshots > 90 days ($37.50) ---
    _row("li-008", "snap-0b8bbbb", "snapshot", "us-east-1", 5.00,
         snapshot_age_days="120", size_gb="100"),
    _row("li-009", "snap-0c9cccc", "snapshot", "us-west-2", 30.00,
         snapshot_age_days="200", size_gb="500"),
    _row("li-010", "snap-0dadddd", "snapshot", "us-east-1", 2.50,
         snapshot_age_days="95", size_gb="50"),

    # --- HEALTHY: must NOT be flagged ---
    _row("li-101", "vol-1aaaaaa", "ebs_volume", "us-east-1", 20.00,
         attachment_state="attached", size_gb="250", tags="env=prod"),
    _row("li-102", "i-1bbbbbb", "ec2_instance", "us-east-1", 80.00,
         instance_state="running", instance_type="m5.xlarge", tags="env=prod"),
    _row("li-103", "eipalloc-1cccccc", "elastic_ip", "us-east-1", 0.00,
         eip_association="associated"),
    _row("li-104", "snap-1dddddd", "snapshot", "us-east-1", 4.00,
         snapshot_age_days="30", size_gb="80"),
]

# Map a wasteful row to the finding_type it should trigger (ground truth).
_WASTE_RULES = {
    "ebs_volume": ("attachment_state", "unattached", "unattached_ebs_volume"),
    "ec2_instance": ("instance_state", "stopped", "idle_instance"),
    "elastic_ip": ("eip_association", "unassociated", "unassociated_eip"),
}


def _expected_findings():
    """Derive the ground-truth waste manifest directly from RESOURCES."""
    from app.config import SNAPSHOT_AGE_THRESHOLD_DAYS

    findings = []
    for r in RESOURCES:
        rtype = r["resource_type"]
        cost = float(r["monthly_cost_usd"])
        if rtype in _WASTE_RULES:
            col, bad_value, finding_type = _WASTE_RULES[rtype]
            if r[col] == bad_value:
                findings.append({
                    "resource_id": r["resource_id"],
                    "finding_type": finding_type,
                    "monthly_waste_usd": cost,
                })
        elif rtype == "snapshot":
            if int(r["snapshot_age_days"]) > SNAPSHOT_AGE_THRESHOLD_DAYS:
                findings.append({
                    "resource_id": r["resource_id"],
                    "finding_type": "aged_snapshot",
                    "monthly_waste_usd": cost,
                })
    return findings


def build_manifest() -> dict:
    """Compute exact expected counts & dollar amounts (test ground truth)."""
    findings = _expected_findings()
    by_type: dict[str, dict] = {}
    for f in findings:
        t = by_type.setdefault(f["finding_type"], {"count": 0, "monthly_waste_usd": 0.0})
        t["count"] += 1
        t["monthly_waste_usd"] = round(t["monthly_waste_usd"] + f["monthly_waste_usd"], 2)

    return {
        "billing_period": {"start": BILLING_START, "end": BILLING_END},
        "total_findings": len(findings),
        "total_monthly_waste_usd": round(sum(f["monthly_waste_usd"] for f in findings), 2),
        "by_finding_type": by_type,
        "findings": findings,
    }


def generate(data_dir: Path | None = None) -> tuple[Path, Path]:
    """Write sample_cur.csv and sample_manifest.json. Returns their paths."""
    base = data_dir or DATA_DIR
    base.mkdir(parents=True, exist_ok=True)
    csv_path = base / "sample_cur.csv"
    manifest_path = base / "sample_manifest.json"

    with csv_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_COLUMNS)
        writer.writeheader()
        writer.writerows(RESOURCES)

    with manifest_path.open("w", encoding="utf-8") as fh:
        json.dump(build_manifest(), fh, indent=2)

    return csv_path, manifest_path


if __name__ == "__main__":
    c, m = generate()
    man = build_manifest()
    print(f"Wrote {c}")
    print(f"Wrote {m}")
    print(f"Seeded waste: {man['total_findings']} findings, "
          f"${man['total_monthly_waste_usd']:.2f}/mo")
    for t, v in man["by_finding_type"].items():
        print(f"  - {t}: {v['count']} findings, ${v['monthly_waste_usd']:.2f}/mo")
