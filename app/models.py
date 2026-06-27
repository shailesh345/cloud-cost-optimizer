"""SQLAlchemy ORM models: Scan, Finding, RemediationLog."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Scan(Base):
    """One ingestion run over a sample Cost & Usage Report."""

    __tablename__ = "scans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)
    source_file: Mapped[str] = mapped_column(String, default="")
    total_findings: Mapped[int] = mapped_column(Integer, default=0)
    total_monthly_waste_usd: Mapped[float] = mapped_column(Float, default=0.0)

    findings: Mapped[list["Finding"]] = relationship(
        back_populates="scan", cascade="all, delete-orphan"
    )


class Finding(Base):
    """A single deterministic waste detection."""

    __tablename__ = "findings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_id: Mapped[int] = mapped_column(ForeignKey("scans.id"))

    # --- Resource identity (from sample data) ---
    resource_id: Mapped[str] = mapped_column(String, index=True)
    resource_type: Mapped[str] = mapped_column(String)   # ebs_volume, ec2_instance, eip, snapshot
    finding_type: Mapped[str] = mapped_column(String, index=True)  # matches REMEDIATION_ALLOWLIST keys
    region: Mapped[str] = mapped_column(String, default="")

    # --- Deterministic economics & scoring ---
    monthly_waste_usd: Mapped[float] = mapped_column(Float, default=0.0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)  # 0..1 orphaned/safe-to-act
    risk_score: Mapped[int] = mapped_column(Integer, default=0)    # 0..100
    risk_bucket: Mapped[str] = mapped_column(String, default="Low")
    details: Mapped[dict] = mapped_column(JSON, default=dict)

    # --- LLM enrichment (Phase 4; nullable until enriched) ---
    llm_impact: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_command: Mapped[str | None] = mapped_column(String, nullable=True)
    llm_priority: Mapped[str | None] = mapped_column(String, nullable=True)

    status: Mapped[str] = mapped_column(String, default="open")  # open|remediation_proposed
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    scan: Mapped["Scan"] = relationship(back_populates="findings")
    remediations: Mapped[list["RemediationLog"]] = relationship(
        back_populates="finding", cascade="all, delete-orphan"
    )


class EnrichmentCache(Base):
    """Cached LLM enrichment keyed by finding signature (cost discipline).

    Identical finding *types* reuse one Opus call instead of one call per
    finding. The per-resource specifics (id, region, $) are rendered locally.
    """

    __tablename__ = "enrichment_cache"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    signature: Mapped[str] = mapped_column(String, unique=True, index=True)
    impact: Mapped[str] = mapped_column(String, default="")
    command_template: Mapped[str] = mapped_column(String, default="")
    priority: Mapped[str] = mapped_column(String, default="")
    source: Mapped[str] = mapped_column(String, default="")  # llm | fallback
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)


class RemediationLog(Base):
    """Audit trail for every remediation request (always dry-run by default)."""

    __tablename__ = "remediation_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    finding_id: Mapped[int] = mapped_column(ForeignKey("findings.id"))

    command: Mapped[str] = mapped_column(String, default="")
    dry_run: Mapped[bool] = mapped_column(Boolean, default=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    allowlisted: Mapped[bool] = mapped_column(Boolean, default=False)
    status: Mapped[str] = mapped_column(String, default="")  # proposed|rejected|blocked
    message: Mapped[str] = mapped_column(String, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_utcnow)

    finding: Mapped["Finding"] = relationship(back_populates="remediations")
