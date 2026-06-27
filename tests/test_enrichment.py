"""Phase 4 acceptance: LLM enrichment is cached, safe, and always runs ($0 path).

These tests run with NO ANTHROPIC_API_KEY, so the deterministic fallback is
exercised — the full pipeline is demoable offline.
"""

from __future__ import annotations

import app.enrichment as enrichment
from app.enrichment import enrich_scan
from app.services import is_allowlisted


def _scan(client):
    return client.post("/scan", json={}).json()


def test_enrichment_populates_all_fields(client):
    scan = _scan(client)
    client.post(f"/enrich/{scan['scan_id']}")
    for f in client.get("/findings").json():
        assert f["llm_impact"]
        assert f["llm_command"]
        assert f["llm_priority"]


def test_enriched_commands_are_allowlisted(client):
    scan = _scan(client)
    client.post(f"/enrich/{scan['scan_id']}")
    for f in client.get("/findings").json():
        assert is_allowlisted(f["finding_type"], f["llm_command"])


def test_impact_is_rendered_with_resource_specifics(client):
    scan = _scan(client)
    client.post(f"/enrich/{scan['scan_id']}")
    findings = client.get("/findings").json()
    # Each finding's own resource_id should appear in its rendered impact text.
    for f in findings:
        assert f["resource_id"] in f["llm_impact"]
        assert "{resource_id}" not in f["llm_impact"]  # placeholder fully substituted


def test_caching_collapses_calls_per_signature(client, monkeypatch):
    # 10 findings across 4 finding types -> exactly 4 generation calls.
    monkeypatch.setattr(enrichment, "GENERATION_CALLS", 0)
    scan = _scan(client)
    summary = client.post(f"/enrich/{scan['scan_id']}").json()
    assert summary["findings_enriched"] == 10
    assert summary["distinct_signatures_cached"] == 4
    assert enrichment.GENERATION_CALLS == 4


def test_reenrichment_uses_cache_no_new_calls(client, monkeypatch):
    monkeypatch.setattr(enrichment, "GENERATION_CALLS", 0)
    scan = _scan(client)
    client.post(f"/enrich/{scan['scan_id']}")
    assert enrichment.GENERATION_CALLS == 4
    # Re-enrich the same scan: cache is warm, no further generation.
    client.post(f"/enrich/{scan['scan_id']}")
    assert enrichment.GENERATION_CALLS == 4


def test_scan_with_enrich_flag(client):
    data = client.post("/scan", json={"enrich": True}).json()
    assert all(f["llm_impact"] for f in data["findings"])


def test_fallback_source_without_api_key(client, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    scan = _scan(client)
    summary = client.post(f"/enrich/{scan['scan_id']}").json()
    assert summary["sources"]["fallback"] == 4
    assert summary["sources"]["llm"] == 0
