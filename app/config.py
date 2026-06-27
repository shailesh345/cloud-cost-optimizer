"""Central configuration & tunable constants.

Everything that influences a *decision* (risk weighting, buckets, the
remediation allowlist, caching) lives here so it is auditable in one place.
"""

from __future__ import annotations

from pathlib import Path

# --- Paths -----------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
DB_PATH = BASE_DIR / "costs.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

# --- Risk Score model ------------------------------------------------------
# Risk Score = prioritization score per finding in the range 0-100.
# It is a normalized blend of:
#   * financial impact  -> monthly_waste_usd, normalized against a cap
#   * detector confidence -> how certain the resource is orphaned & safe to act on
# Higher score = higher priority to remediate (big waste AND safe to remove).
RISK_WEIGHTS = {
    "financial": 0.6,   # weight on normalized monthly waste
    "confidence": 0.4,  # weight on detector confidence
}

# Monthly waste at or above this maps to a normalized financial impact of 1.0.
FINANCIAL_NORMALIZATION_CAP_USD = 100.0

# Score thresholds for bucketing.
RISK_BUCKET_THRESHOLDS = {
    "high": 66,    # score >= 66        -> High
    "medium": 33,  # 33 <= score < 66   -> Medium
    # else                              -> Low
}

# --- Detection thresholds --------------------------------------------------
SNAPSHOT_AGE_THRESHOLD_DAYS = 90  # snapshots older than this are flagged

# Per-detector confidence that a flagged resource is genuinely orphaned and
# safe to remediate. Feeds the Risk Score. Higher = more certain.
#   * unattached EBS / unassociated EIP: very clear signal -> high confidence
#   * stopped instance: could be intentionally parked -> moderate
#   * aged snapshot: age alone is a weaker safety signal -> lower
DETECTOR_CONFIDENCE = {
    "unattached_ebs_volume": 0.95,
    "idle_instance": 0.70,
    "unassociated_eip": 0.90,
    "aged_snapshot": 0.60,
}

# --- Remediation safety ----------------------------------------------------
# Remediation NEVER auto-executes. Commands are validated against this
# allowlist (by leading verb) and returned for human review only.
REMEDIATION_ALLOWLIST = {
    "unattached_ebs_volume": "aws ec2 delete-volume",
    "idle_instance": "aws ec2 stop-instances",
    "unassociated_eip": "aws ec2 release-address",
    "aged_snapshot": "aws ec2 delete-snapshot",
}

# Deterministic command templates. The LLM layer (Phase 4) may also produce a
# command, but EVERY command — LLM or template — is validated against the
# allowlist prefix above before it is ever shown as actionable.
REMEDIATION_COMMAND_TEMPLATES = {
    "unattached_ebs_volume": "aws ec2 delete-volume --volume-id {resource_id} --region {region}",
    "idle_instance": "aws ec2 stop-instances --instance-ids {resource_id} --region {region}",
    "unassociated_eip": "aws ec2 release-address --allocation-id {resource_id} --region {region}",
    "aged_snapshot": "aws ec2 delete-snapshot --snapshot-id {resource_id} --region {region}",
}
REMEDIATION_DRY_RUN_DEFAULT = True

# --- LLM enrichment --------------------------------------------------------
LLM_MODEL = "claude-opus-4-8"
LLM_CACHE_ENABLED = True  # cache by finding signature to avoid duplicate Opus calls
