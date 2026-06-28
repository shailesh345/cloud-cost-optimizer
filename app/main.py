"""FastAPI application entrypoint.

Endpoints:
  GET  /health             liveness
  POST /scan               ingest sample CUR -> run detectors -> persist
  GET  /findings           list findings (filterable) + aggregate risk
  POST /remediate/{id}     validate + propose remediation (never executes)
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from app import __version__
from app.config import BASE_DIR
from app.database import get_db, init_db
from app.models import Finding, Scan
from app.risk import aggregate_risk
from app.enrichment import enrich_scan
from app.schemas import (
    AggregateRiskOut,
    EnrichResponse,
    FindingOut,
    RemediateRequest,
    RemediateResponse,
    ScanRequest,
    ScanResponse,
)
from app.services import propose_remediation, run_scan


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(
    title="Cloud Cost Optimizer & Remediation Engine",
    description=(
        "API-first cost optimizer. Detection is deterministic and testable; "
        "the LLM layer only enriches findings; remediation never auto-executes."
    ),
    version=__version__,
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
def dashboard() -> FileResponse:
    """Serve the single-page dashboard."""
    return FileResponse(BASE_DIR / "app" / "static" / "dashboard.html")


@app.get("/health", tags=["system"])
def health() -> dict:
    return {"status": "ok", "version": __version__}


@app.post("/scan", response_model=ScanResponse, tags=["scan"])
def scan(body: ScanRequest | None = None, db: Session = Depends(get_db)) -> ScanResponse:
    """Ingest the sample CUR, run deterministic detectors, persist results."""
    csv_path = body.csv_path if body else None
    if csv_path is not None and not Path(csv_path).is_file():
        raise HTTPException(
            status_code=400,
            detail=(
                f"csv_path '{csv_path}' is not a readable file. "
                "Leave csv_path null/empty to scan the bundled sample CUR."
            ),
        )
    scan_row = run_scan(db, csv_path)
    if body and body.enrich:
        enrich_scan(db, scan_row.id)
        db.refresh(scan_row)
    agg = aggregate_risk(scan_row.findings)
    return ScanResponse(
        scan_id=scan_row.id,
        source_file=scan_row.source_file,
        total_findings=scan_row.total_findings,
        total_monthly_waste_usd=scan_row.total_monthly_waste_usd,
        aggregate_risk=AggregateRiskOut(**agg.__dict__),
        findings=[FindingOut.model_validate(f) for f in scan_row.findings],
    )


@app.get("/findings", response_model=list[FindingOut], tags=["findings"])
def list_findings(
    db: Session = Depends(get_db),
    scan_id: int | None = Query(None, description="Limit to one scan (default: all)"),
    finding_type: str | None = Query(None),
    risk_bucket: str | None = Query(None, description="High | Medium | Low"),
) -> list[Finding]:
    q = db.query(Finding)
    if scan_id is not None:
        q = q.filter(Finding.scan_id == scan_id)
    if finding_type:
        q = q.filter(Finding.finding_type == finding_type)
    if risk_bucket:
        q = q.filter(Finding.risk_bucket == risk_bucket)
    return q.order_by(Finding.risk_score.desc()).all()


@app.post("/enrich/{scan_id}", response_model=EnrichResponse, tags=["enrichment"])
def enrich(scan_id: int, db: Session = Depends(get_db)) -> EnrichResponse:
    """Run the LLM enrichment layer over a scan's findings (cached per type)."""
    summary = enrich_scan(db, scan_id)
    return EnrichResponse(**summary)


@app.post("/remediate/{finding_id}", response_model=RemediateResponse, tags=["remediation"])
def remediate(
    finding_id: int,
    body: RemediateRequest | None = None,
    db: Session = Depends(get_db),
) -> RemediateResponse:
    """Validate + propose a remediation command. Executes nothing."""
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=404, detail=f"Finding {finding_id} not found")

    req = body or RemediateRequest()
    log = propose_remediation(db, finding, dry_run=req.dry_run, confirm=req.confirm)
    return RemediateResponse(
        finding_id=finding.id,
        finding_type=finding.finding_type,
        resource_id=finding.resource_id,
        command=log.command,
        dry_run=log.dry_run,
        confirmed=log.confirmed,
        allowlisted=log.allowlisted,
        status=log.status,
        message=log.message,
    )
