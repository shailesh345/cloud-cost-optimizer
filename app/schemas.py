"""Pydantic request/response schemas for the API."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict


# --- Scan ------------------------------------------------------------------
class ScanRequest(BaseModel):
    csv_path: str | None = None  # defaults to the bundled sample CUR
    enrich: bool = False         # run the LLM enrichment layer after scanning


class EnrichResponse(BaseModel):
    scan_id: int
    findings_enriched: int
    distinct_signatures_cached: int
    sources: dict


class AggregateRiskOut(BaseModel):
    total_monthly_waste_usd: float
    aggregate_score: int
    bucket: str
    counts: dict


class FindingOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    scan_id: int
    resource_id: str
    resource_type: str
    finding_type: str
    region: str
    monthly_waste_usd: float
    confidence: float
    risk_score: int
    risk_bucket: str
    details: dict
    llm_impact: str | None = None
    llm_command: str | None = None
    llm_priority: str | None = None
    status: str
    created_at: datetime


class ScanResponse(BaseModel):
    scan_id: int
    source_file: str
    total_findings: int
    total_monthly_waste_usd: float
    aggregate_risk: AggregateRiskOut
    findings: list[FindingOut]


# --- Remediation -----------------------------------------------------------
class RemediateRequest(BaseModel):
    dry_run: bool = True
    confirm: bool = False


class RemediateResponse(BaseModel):
    finding_id: int
    finding_type: str
    resource_id: str
    command: str
    dry_run: bool
    confirmed: bool
    allowlisted: bool
    status: str
    message: str
