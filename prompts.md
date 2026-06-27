# Prompts & Decision Log

This is a **decision log**, not a raw transcript. Each entry records the
*Intent*, *Constraint*, and *Acceptance Criteria* behind a build decision.
User prompts are seeded first, in order, followed by the architect's notes.

---

## [2026-06-27 — Entry 1] User: Engage Lead Architect Mode
- **Intent:** Build a Python-based, API-first Cloud Cost Optimizer & Remediation
  Engine using a free database and a dashboard. Operate in "Lead Architect" mode.
- **Constraint:**
  - No manual edits by the user — the assistant provides all logic and fixes.
  - Maintain `prompts.md` as an audit log, updated every turn.
  - MVP target 4–6h (max window 16h); report elapsed time each turn.
- **Acceptance Criteria:** Architecture acknowledged; timer started; work begins.

## [2026-06-27 — Entry 2] User: Lock Architecture
- **Intent:** Pin down the system shape before scaffolding.
- **Constraint:**
  - **Data source:** ingest a SAMPLE AWS Cost & Usage Report (CSV); no live cloud,
    no AWS account, $0 spend — stated in README. Generate realistic seeded waste.
  - **Detection (deterministic, no LLM):** unattached EBS, stopped/idle instances,
    unassociated Elastic IPs, aged snapshots. Rule-based Python + unit tests;
    100% reproducible because remediation is irreversible.
  - **LLM layer (only AI output):** per finding produce (a) plain-English impact,
    (b) exact remediation CLI command, (c) risk-ranked priority. Never auto-execute:
    dry-run flag + command allowlist + human confirmation.
  - **Stack:** FastAPI, SQLite. Endpoints: `POST /scan`, `GET /findings`,
    `POST /remediate/{id}`. Minimal dashboard: total waste (currency), findings
    table, Risk Score.
  - **prompts.md format:** decision log (Intent / Constraint / Acceptance), not a
    transcript.
- **Acceptance Criteria:** Architecture confirmed; phased build plan proposed;
  wait for go-ahead on Phase 0.

## [2026-06-27 — Entry 3] User: Three additions, then GO on Phase 0
- **Intent:** Refine the plan, then start building.
- **Constraint:**
  - **Risk Score:** per-finding prioritization score = normalized blend of
    `monthly_waste_usd` (financial impact) and detector confidence (orphaned &
    safe to remediate). Bucket High/Med/Low. Document the formula in README. The
    dashboard's aggregate Risk Score rolls up from per-finding scores.
  - **LLM caching:** cache enrichment by finding-type/signature so identical
    findings don't trigger duplicate Opus calls. Note in README as deliberate
    cost discipline.
  - **prompts.md:** seed with the user's two prior prompts first, then notes.
- **Acceptance Criteria:** Additions folded in; Phase 0 scaffolded; acceptance +
  elapsed time reported.

---

## [2026-06-27 — Architect Note] Phase 0 — Scaffold & Foundation
- **Intent:** Stand up the project skeleton everything else builds on.
- **Constraint:** Booting FastAPI app; SQLite via SQLAlchemy; risk formula and
  remediation allowlist centralized in `app/config.py`; README leads with the
  $0/no-cloud disclaimer.
- **Acceptance Criteria:** `uvicorn app.main:app` starts clean; `/health` returns
  200; `/docs` live; SQLite tables created on startup.
- **Delivered:** `requirements.txt`, `.gitignore`, `app/{__init__,config,risk,
  database,models,main}.py`, `tests/__init__.py`, `README.md`, `prompts.md`.

## [2026-06-27 — Entry 4] User: go-ahead on Phase 1
- **Intent:** Build the deterministic sample data generator.
- **Constraint:** CUR-style CSV with deliberately seeded, countable waste; a
  committed manifest of exact counts/dollars; byte-reproducible; snapshot age
  stored as an integer (never derived from "now").
- **Acceptance Criteria:** Deterministic CSV + manifest; SHA-256 stable across
  regenerations; seeded total = 10 findings / $149.70/mo.
- **Delivered:** `app/sample_data.py`, `data/sample_cur.csv`,
  `data/sample_manifest.json`. Verified: hashes stable; manifest exact.

## [2026-06-27 — Entry 5] User: go-ahead on Phase 2
- **Intent:** Deterministic detection engine + unit tests.
- **Constraint:** 4 pure-function detectors, no DB/LLM; exact assertions vs the
  manifest; zero false positives on healthy decoys; risk score computed here.
- **Acceptance Criteria:** `pytest` green; detectors find exactly the seeded
  waste; decoys clean; age boundary correct.
- **Delivered:** `app/detectors.py`, `app/config.py` (DETECTOR_CONFIDENCE),
  `tests/test_detectors.py`. Verified: 14 tests pass.

## [2026-06-27 — Entry 6] User: go-ahead on Phase 3
- **Intent:** Wire the REST API.
- **Constraint:** `POST /scan`, `GET /findings` (filterable), `POST /remediate/{id}`
  with dry-run default + allowlist validation + human-confirm gate; remediation
  never executes ($0 / no live cloud).
- **Acceptance Criteria:** Full scan→findings→remediate flow works; tests green.
- **Delivered:** `app/{schemas,services,main}.py`, `app/config.py` (command
  templates), `tests/{conftest,test_api}.py`. Verified: 24 tests pass; live flow
  confirmed (dry_run / proposed / confirmed_no_exec; allowlist blocks off-list).

## [2026-06-27 — Entry 7] User: go-ahead on Phase 4
- **Intent:** LLM enrichment layer — the only AI-generated output.
- **Constraint:** Per finding produce impact summary + exact CLI command +
  risk-ranked priority. Cache by finding signature (one Opus call per type, not
  per finding) as deliberate cost discipline. Every LLM command re-validated
  against the allowlist. Must run at $0 with no API key (deterministic fallback).
  Model `claude-opus-4-8`, structured outputs via `messages.parse`, adaptive
  thinking (confirmed against the claude-api skill).
- **Acceptance Criteria:** Findings enriched; allowlist rejects non-approved
  commands; caching collapses calls per signature; tests green.
- **Delivered:** `app/enrichment.py`, `app/models.py` (EnrichmentCache),
  `app/schemas.py` + `app/main.py` (`/enrich/{scan_id}`, `enrich` flag on
  `/scan`), `tests/test_enrichment.py`. Verified: 31 tests pass; 10 findings →
  4 generation calls; re-enrich uses cache (0 new calls); fallback path at $0.

## [2026-06-27 — Entry 8] User: go-ahead on Phase 5
- **Intent:** Minimal dashboard.
- **Constraint:** Single page served by FastAPI; show total waste (currency),
  findings table, and a Risk Score; pull live from the API.
- **Acceptance Criteria:** Dashboard renders live data; total waste, aggregate
  risk, findings table all present; remediation reachable from the UI.
- **Delivered:** `app/static/dashboard.html` (Chart.js), `GET /` route in
  `app/main.py`, `tests/test_dashboard.py`. Verified: 33 tests pass; rendered in
  Chrome against a live server — cards ($149.70 / risk 47 Medium / 0-8-2),
  waste-by-type bar + risk doughnut charts, findings table sorted by risk with
  enriched impact + CLI per row, and a Remediate button showing the dry-run
  (allowlisted) safety toast.

## [2026-06-27 — Entry 9] User: go-ahead on Phase 6
- **Intent:** Harden and document; close out the MVP.
- **Constraint:** Sample request file, README run instructions + project tree +
  real-LLM toggle, final full test pass.
- **Acceptance Criteria:** Tests green; app boots clean; docs complete; build
  status marked done.
- **Delivered:** `requests.http`, README (run instructions, structure, $0 LLM
  toggle, all phases checked), final pass: 33 tests green; clean boot verified
  (5 endpoints + dashboard). **MVP COMPLETE.**
