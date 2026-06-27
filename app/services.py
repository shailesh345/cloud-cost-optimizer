"""Service layer: persistence + safety-gated remediation.

No remediation is ever executed against any account ($0 / no live cloud).
Remediation = build command -> validate against allowlist -> require human
confirmation -> audit-log. The command is returned for review only.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.orm import Session

from app.config import (
    DATA_DIR,
    REMEDIATION_ALLOWLIST,
    REMEDIATION_COMMAND_TEMPLATES,
)
from app.detectors import scan_file
from app.models import Finding, RemediationLog, Scan
from app.sample_data import generate


# ---------------------------------------------------------------------------
# Scan persistence
# ---------------------------------------------------------------------------
def default_sample_csv() -> Path:
    """Return the bundled sample CUR, generating it if missing."""
    csv_path = DATA_DIR / "sample_cur.csv"
    if not csv_path.exists():
        generate()
    return csv_path


def run_scan(db: Session, csv_path: str | Path | None = None) -> Scan:
    """Load a CUR CSV, run detectors, and persist Scan + Findings."""
    path = Path(csv_path) if csv_path else default_sample_csv()
    detected = scan_file(path)

    scan = Scan(
        source_file=str(path.name),
        total_findings=len(detected),
        total_monthly_waste_usd=round(sum(d.monthly_waste_usd for d in detected), 2),
    )
    db.add(scan)
    db.flush()  # assign scan.id

    for d in detected:
        db.add(Finding(
            scan_id=scan.id,
            resource_id=d.resource_id,
            resource_type=d.resource_type,
            finding_type=d.finding_type,
            region=d.region,
            monthly_waste_usd=d.monthly_waste_usd,
            confidence=d.confidence,
            risk_score=d.risk_score,
            risk_bucket=d.risk_bucket,
            details=d.details,
        ))

    db.commit()
    db.refresh(scan)
    return scan


# ---------------------------------------------------------------------------
# Remediation (validate + propose only — never executes)
# ---------------------------------------------------------------------------
def build_command(finding: Finding) -> str:
    """Deterministically render a remediation command for a finding."""
    template = REMEDIATION_COMMAND_TEMPLATES.get(finding.finding_type, "")
    if not template:
        return ""
    return template.format(resource_id=finding.resource_id, region=finding.region or "us-east-1")


def is_allowlisted(finding_type: str, command: str) -> bool:
    """A command is allowed only if it starts with the approved verb prefix."""
    prefix = REMEDIATION_ALLOWLIST.get(finding_type)
    return bool(prefix) and command.startswith(prefix)


def propose_remediation(
    db: Session, finding: Finding, dry_run: bool = True, confirm: bool = False
) -> RemediationLog:
    """Validate and audit-log a remediation request. Executes nothing.

    Status semantics:
      * blocked            -> command not on the allowlist (hard stop)
      * dry_run            -> default safe path; would simulate via --dry-run
      * proposed           -> real action requested but not yet confirmed
      * confirmed_no_exec  -> confirmed, but NOT executed ($0 / no live cloud)
    """
    # Prefer an LLM-suggested command if present, else the deterministic template.
    command = finding.llm_command or build_command(finding)
    allowed = is_allowlisted(finding.finding_type, command)

    if not allowed:
        status = "blocked"
        message = (
            f"Command rejected: not on the allowlist for '{finding.finding_type}'. "
            "Nothing was executed."
        )
        shown_command = command
    elif dry_run:
        status = "dry_run"
        shown_command = f"{command} --dry-run"
        message = "Dry-run: command validated. No changes made (and no live cloud)."
    elif not confirm:
        status = "proposed"
        shown_command = command
        message = "Real remediation requires confirm=true. Command proposed for review."
    else:
        status = "confirmed_no_exec"
        shown_command = command
        message = (
            "Confirmed and allowlisted. NOT executed: this MVP targets no live "
            "cloud account ($0 spend by design). Command is provided for review."
        )

    log = RemediationLog(
        finding_id=finding.id,
        command=shown_command,
        dry_run=dry_run,
        confirmed=confirm,
        allowlisted=allowed,
        status=status,
        message=message,
    )
    db.add(log)
    if allowed and status != "blocked":
        finding.status = "remediation_proposed"
    db.commit()
    db.refresh(log)
    return log
