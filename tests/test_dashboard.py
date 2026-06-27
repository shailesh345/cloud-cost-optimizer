"""Phase 5 acceptance: the dashboard is served and wired to the API."""

from __future__ import annotations


def test_dashboard_served_at_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
    body = r.text
    # Core elements present.
    assert "Cloud Cost Optimizer" in body
    assert "NO LIVE CLOUD" in body          # the $0 disclaimer badge
    assert "Total Monthly Waste" in body
    assert "Aggregate Risk Score" in body
    # Wired to the real endpoints.
    assert "/scan" in body
    assert "/findings" in body
    assert "/remediate/" in body


def test_dashboard_data_endpoints_back_it(client):
    # The endpoints the dashboard calls must return usable data.
    scan = client.post("/scan", json={"enrich": True}).json()
    assert scan["total_monthly_waste_usd"] == 149.70
    assert scan["aggregate_risk"]["counts"]["Medium"] >= 1
    findings = client.get("/findings").json()
    assert findings and findings[0]["llm_command"]
