# Cloud Cost Optimizer & Remediation Engine

> ### ⚠️ $0 SPEND / NO LIVE CLOUD — BY DESIGN
> This project does **not** connect to any AWS account, uses **no** cloud
> credentials, and incurs **$0 spend**. It ingests a **sample AWS Cost & Usage
> Report (CSV)** with deliberately seeded waste. This is an intentional design
> choice: detection logic must be 100% reproducible and remediation is
> irreversible, so we never point it at a real account. "Remediation" here
> means *validate + propose a reviewed CLI command* — it is never executed
> against any account.

API-first engine that ingests sample cloud billing/inventory data, deterministically
detects wasted spend, scores each finding by priority, and proposes (never executes)
safe remediation commands.

---

## Architecture

```
Dashboard ──▶ FastAPI ──▶ SQLite
                │   │
   Ingestion ◀──┘   └──▶ Detection Engine (deterministic, unit-tested)
   (sample CSV)              │
                             ├─▶ Risk Score (deterministic, 0-100)
                             └─▶ LLM Enrichment (Opus 4.8, cached) ─▶ Remediation (dry-run only)
```

| Layer | Responsibility | AI involved? |
|---|---|---|
| Ingestion | Load sample CUR CSV + resource inventory | No |
| Detection | 4 deterministic rules, fully unit-tested | **No — by design** |
| Risk Score | Prioritization score per finding | No (deterministic formula) |
| LLM enrichment | Impact summary, CLI command, risk ranking | **Yes — only here** |
| Remediation | Validate + propose command (dry-run, allowlist, human confirm) | No |

### Detection rules (deterministic)
1. **Unattached EBS volumes** — provisioned storage attached to nothing.
2. **Stopped-but-billed / idle instances** — instances incurring cost while unused.
3. **Unassociated Elastic IPs** — EIPs not bound to a running resource (billed when idle).
4. **Aged snapshots** — snapshots older than the configured threshold (default 90 days).

Detection is pure Python with unit tests asserting exact counts/amounts against the
seeded sample data. No LLM participates in deciding what counts as waste.

---

## Risk Score (prioritization)

Each finding gets a **0–100 Risk Score** — a normalized blend of **financial impact**
and **detector confidence** that the resource is orphaned and safe to remediate:

```
financial_norm = min(monthly_waste_usd / CAP, 1.0)        # CAP = $100/mo
risk_score      = round(100 * (0.6 * financial_norm + 0.4 * confidence))
```

| Score | Bucket |
|---|---|
| ≥ 66 | **High** |
| 33–65 | **Medium** |
| < 33 | **Low** |

- **Financial impact** rewards findings that recover more money.
- **Confidence** (0–1, assigned by each detector) rewards findings that are clearly
  orphaned and safe to act on — so high-confidence, high-waste items rise to the top.

The dashboard's **aggregate Risk Score** rolls up from these per-finding scores as a
**waste-weighted average** (big-money findings dominate the headline), alongside
High/Medium/Low counts. All weights, the cap, and bucket thresholds live in
`app/config.py`.

---

## Cost discipline: LLM caching

Because this *is* a cost optimizer, the LLM layer practices what it preaches:
enrichment responses are **cached by finding signature** (finding-type + normalized
resource attributes). Identical findings never trigger duplicate Opus calls. This is a
deliberate cost-control choice, not an accident of implementation.

The app also runs **without** an API key — it falls back to deterministic enrichment so
the full pipeline is always demoable at $0.

---

## Stack
- **FastAPI** + Uvicorn (API-first; OpenAPI docs at `/docs`)
- **SQLite** (free, zero-config, file-based)
- **SQLAlchemy** ORM
- **Anthropic Claude Opus 4.8** for enrichment (optional, cached)
- **pytest** for the deterministic detection suite

## API
| Method | Path | Purpose |
|---|---|---|
| `POST` | `/scan` | Ingest sample CSV → run detectors → persist findings |
| `GET` | `/findings` | List findings with risk scores & enrichment |
| `POST` | `/remediate/{id}` | Validate + propose remediation (dry-run, allowlist, confirm) |
| `GET` | `/health` | Liveness probe |

---

## Quick start

```bash
python -m venv .venv
# Windows:  .venv\Scripts\activate
# Unix:     source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Then open:
- **Dashboard:** http://127.0.0.1:8000/  (auto-runs a scan + enrichment on load)
- **API docs (OpenAPI):** http://127.0.0.1:8000/docs
- Sample calls: see `requests.http`

Run tests:
```bash
pytest          # 33 tests, all run at $0 (no API key needed)
```

Regenerate the sample data:
```bash
python -m app.sample_data
```

### Enabling the real LLM (optional)
The app runs fully at **$0 with no API key** via a deterministic fallback. To use
real Claude Opus 4.8 enrichment instead, set a key before starting:
```bash
# Windows (PowerShell):  $env:ANTHROPIC_API_KEY="sk-ant-..."
# Unix:                  export ANTHROPIC_API_KEY="sk-ant-..."
```
Enrichment is cached per finding type, so even a large account costs only one
Opus call per distinct waste class.

---

## Project structure
```
cloud-cost-optimizer/
├── README.md                 # this file ($0 / no-cloud disclaimer up top)
├── prompts.md                # decision log (Intent / Constraint / Acceptance)
├── requirements.txt
├── requests.http             # sample API calls
├── app/
│   ├── config.py             # risk weights, allowlist, command templates, LLM cfg
│   ├── risk.py               # deterministic risk score + aggregate roll-up
│   ├── sample_data.py        # CUR generator + ground-truth manifest
│   ├── detectors.py          # 4 deterministic, unit-tested detectors
│   ├── enrichment.py         # LLM layer (Opus 4.8, cached, $0 fallback)
│   ├── services.py           # scan persistence + safety-gated remediation
│   ├── schemas.py            # Pydantic request/response models
│   ├── models.py             # SQLAlchemy ORM
│   ├── database.py           # SQLite engine/session
│   ├── main.py               # FastAPI app + endpoints + dashboard route
│   └── static/dashboard.html # single-page dashboard (Chart.js)
├── data/
│   ├── sample_cur.csv        # seeded sample Cost & Usage Report
│   └── sample_manifest.json  # exact expected waste (test ground truth)
└── tests/                    # 33 tests: detectors, API, enrichment, dashboard
```

---

## Build status — MVP COMPLETE ✅
- [x] **Phase 0** — Scaffold, DB models, booting FastAPI, README, prompts.md
- [x] **Phase 1** — Sample data generator (seeded waste: 10 findings / $149.70/mo)
- [x] **Phase 2** — Detection engine + unit tests (deterministic, zero false positives)
- [x] **Phase 3** — API wiring (scan / findings / remediate, safety-gated)
- [x] **Phase 4** — LLM enrichment (Opus 4.8, cached per signature, $0 fallback)
- [x] **Phase 5** — Dashboard (total waste, findings table, risk score, charts)
- [x] **Phase 6** — Hardening & docs (sample requests, structure, final test pass)
