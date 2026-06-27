"""LLM enrichment layer - the ONLY place AI generates output.

For each finding it produces (a) a plain-English impact summary, (b) the exact
remediation CLI command, and (c) a risk-ranked priority. Two disciplines:

  * Caching: enrichment is generated once per finding *signature* (the finding
    type) and cached in the DB. Ten findings of four types cost four Opus calls,
    not ten. This is a deliberate cost-control choice (we are a cost optimizer).
  * Safety: any LLM-suggested command is validated against the allowlist before
    it is ever attached to a finding; on rejection we fall back to the
    deterministic template. The app also runs with NO API key via a fully
    deterministic fallback, so the pipeline is always demoable at $0.
"""

from __future__ import annotations

import os

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import LLM_CACHE_ENABLED, LLM_MODEL
from app.models import EnrichmentCache, Finding
from app.services import build_command, is_allowlisted

# Counts how many times generation actually ran (cache miss). Tests assert on it.
GENERATION_CALLS = 0


class _EnrichmentSchema(BaseModel):
    """Structured output contract for the LLM (per finding TYPE)."""

    impact: str           # 1-2 sentences; may use {resource_id} {region} {monthly_waste_usd}
    command_template: str  # AWS CLI with {resource_id} and {region} placeholders
    priority: str          # High|Medium|Low + brief justification


# Deterministic fallback templates per finding type (used with no API key / on error).
_FALLBACK = {
    "unattached_ebs_volume": _EnrichmentSchema(
        impact=(
            "EBS volume {resource_id} in {region} is unattached and still billed, "
            "wasting about ${monthly_waste_usd}/month for storage nothing is using."
        ),
        command_template="aws ec2 delete-volume --volume-id {resource_id} --region {region}",
        priority="High - unattached volumes are almost always safe to delete after a snapshot.",
    ),
    "idle_instance": _EnrichmentSchema(
        impact=(
            "Instance {resource_id} in {region} is stopped but still incurring "
            "~${monthly_waste_usd}/month in attached storage and reserved costs."
        ),
        command_template="aws ec2 stop-instances --instance-ids {resource_id} --region {region}",
        priority="Medium - confirm the instance is not intentionally parked before acting.",
    ),
    "unassociated_eip": _EnrichmentSchema(
        impact=(
            "Elastic IP {resource_id} in {region} is not associated with any running "
            "resource and is billed ~${monthly_waste_usd}/month while idle."
        ),
        command_template="aws ec2 release-address --allocation-id {resource_id} --region {region}",
        priority="High - idle Elastic IPs are safe to release once confirmed unused.",
    ),
    "aged_snapshot": _EnrichmentSchema(
        impact=(
            "Snapshot {resource_id} in {region} is older than the retention threshold, "
            "costing ~${monthly_waste_usd}/month for likely-obsolete backup data."
        ),
        command_template="aws ec2 delete-snapshot --snapshot-id {resource_id} --region {region}",
        priority="Low - verify the snapshot is not part of a retention policy first.",
    ),
}


def _render(template: str, finding: Finding) -> str:
    """Safely substitute per-finding values without choking on stray braces."""
    return (
        template.replace("{resource_id}", finding.resource_id)
        .replace("{region}", finding.region or "us-east-1")
        .replace("{monthly_waste_usd}", f"{finding.monthly_waste_usd:.2f}")
    )


def _llm_prompt(finding: Finding) -> str:
    return (
        "You are a FinOps assistant. For the AWS waste finding type below, return "
        "a concise plain-English impact summary, an exact AWS CLI remediation "
        "command, and a risk-ranked priority.\n\n"
        f"Finding type: {finding.finding_type}\n"
        f"Resource type: {finding.resource_type}\n\n"
        "Use the placeholders {resource_id}, {region}, and {monthly_waste_usd} in "
        "the impact and command so they can be filled per resource. The command "
        f"MUST begin exactly with the approved verb for this finding type."
    )


def _generate(finding: Finding) -> tuple[_EnrichmentSchema, str]:
    """Generate enrichment for a finding type. Returns (schema, source)."""
    global GENERATION_CALLS
    GENERATION_CALLS += 1

    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            import anthropic

            client = anthropic.Anthropic()
            resp = client.messages.parse(
                model=LLM_MODEL,
                max_tokens=1024,
                thinking={"type": "adaptive"},
                messages=[{"role": "user", "content": _llm_prompt(finding)}],
                output_format=_EnrichmentSchema,
            )
            return resp.parsed_output, "llm"
        except Exception:
            # Any failure (no network, auth, parse) → deterministic fallback.
            pass

    return _FALLBACK[finding.finding_type], "fallback"


def _get_or_create_cache(db: Session, finding: Finding) -> EnrichmentCache:
    signature = finding.finding_type  # identical types share enrichment
    if LLM_CACHE_ENABLED:
        cached = db.query(EnrichmentCache).filter_by(signature=signature).first()
        if cached:
            return cached

    schema, source = _generate(finding)
    entry = EnrichmentCache(
        signature=signature,
        impact=schema.impact,
        command_template=schema.command_template,
        priority=schema.priority,
        source=source,
    )
    db.add(entry)
    db.commit()
    db.refresh(entry)
    return entry


def enrich_finding(db: Session, finding: Finding) -> Finding:
    """Attach impact, validated CLI command, and priority to one finding."""
    entry = _get_or_create_cache(db, finding)

    # Render the cached template against this resource.
    command = _render(entry.command_template, finding)

    # SAFETY: never attach an off-allowlist command, even from the LLM.
    if not is_allowlisted(finding.finding_type, command):
        command = build_command(finding)  # deterministic, guaranteed allowlisted

    finding.llm_impact = _render(entry.impact, finding)
    finding.llm_command = command
    finding.llm_priority = entry.priority
    db.commit()
    db.refresh(finding)
    return finding


def enrich_scan(db: Session, scan_id: int) -> dict:
    """Enrich every finding in a scan. Returns a small summary + cache stats."""
    findings = db.query(Finding).filter(Finding.scan_id == scan_id).all()
    for f in findings:
        enrich_finding(db, f)

    cache_entries = db.query(EnrichmentCache).count()
    sources = {"llm": 0, "fallback": 0}
    for c in db.query(EnrichmentCache).all():
        sources[c.source] = sources.get(c.source, 0) + 1

    return {
        "scan_id": scan_id,
        "findings_enriched": len(findings),
        "distinct_signatures_cached": cache_entries,
        "sources": sources,
    }
