"""Phase 3 acceptance: full scan -> findings -> remediate flow over the API."""

from __future__ import annotations

from app.services import build_command, is_allowlisted


def _scan(client):
    return client.post("/scan", json={}).json()


# --- /scan ---------------------------------------------------------------
def test_scan_persists_seeded_waste(client):
    data = _scan(client)
    assert data["total_findings"] == 10
    assert data["total_monthly_waste_usd"] == 149.70
    assert len(data["findings"]) == 10
    agg = data["aggregate_risk"]
    assert agg["total_monthly_waste_usd"] == 149.70
    assert sum(agg["counts"].values()) == 10
    assert agg["bucket"] in {"High", "Medium", "Low"}


# --- /findings -----------------------------------------------------------
def test_findings_listed_and_sorted(client):
    _scan(client)
    findings = client.get("/findings").json()
    assert len(findings) == 10
    scores = [f["risk_score"] for f in findings]
    assert scores == sorted(scores, reverse=True)  # highest risk first


def test_findings_filter_by_type(client):
    _scan(client)
    r = client.get("/findings", params={"finding_type": "unattached_ebs_volume"}).json()
    assert len(r) == 3
    assert all(f["finding_type"] == "unattached_ebs_volume" for f in r)


def test_findings_filter_by_bucket(client):
    _scan(client)
    r = client.get("/findings", params={"risk_bucket": "Low"}).json()
    assert all(f["risk_bucket"] == "Low" for f in r)


# --- /remediate ----------------------------------------------------------
def test_remediate_default_is_dry_run(client):
    _scan(client)
    fid = client.get("/findings").json()[0]["id"]
    r = client.post(f"/remediate/{fid}", json={}).json()
    assert r["status"] == "dry_run"
    assert r["allowlisted"] is True
    assert r["command"].endswith("--dry-run")


def test_remediate_real_requires_confirmation(client):
    _scan(client)
    fid = client.get("/findings").json()[0]["id"]
    r = client.post(f"/remediate/{fid}", json={"dry_run": False, "confirm": False}).json()
    assert r["status"] == "proposed"


def test_remediate_confirmed_is_not_executed(client):
    _scan(client)
    fid = client.get("/findings").json()[0]["id"]
    r = client.post(f"/remediate/{fid}", json={"dry_run": False, "confirm": True}).json()
    assert r["status"] == "confirmed_no_exec"
    assert "NOT executed" in r["message"]


def test_remediate_missing_finding_404(client):
    _scan(client)
    assert client.post("/remediate/9999", json={}).status_code == 404


# --- Allowlist guardrail (unit) -----------------------------------------
def test_allowlist_blocks_off_list_command():
    assert is_allowlisted("aged_snapshot", "aws ec2 delete-snapshot --snapshot-id x") is True
    assert is_allowlisted("aged_snapshot", "aws ec2 terminate-instances --x") is False
    assert is_allowlisted("aged_snapshot", "rm -rf /") is False


def test_build_command_matches_allowlist():
    class F:
        finding_type = "unattached_ebs_volume"
        resource_id = "vol-123"
        region = "us-east-1"
    cmd = build_command(F())
    assert is_allowlisted("unattached_ebs_volume", cmd)
    assert "vol-123" in cmd
