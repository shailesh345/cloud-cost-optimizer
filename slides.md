<!--
Submission deck — reveal.js compatible markdown.
Slides separated by `---` (horizontal). Render with reveal.js Markdown plugin:
  <section data-markdown="slides.md"
           data-separator="^\n---\n$"></section>
or any reveal.js markdown loader / VS Code reveal preview.
-->

# Cloud Cost Optimizer & Remediation Engine

**Architect directs, AI executes.**

API-first FinOps engine · deterministic detection · AI-written remediation

---

## The defining decision

**Deterministic code decides what is true. The LLM only writes what humans read.**

- Detection of anything irreversible is pure, rule-based Python — 100% reproducible and unit-tested.
- The LLM never decides what counts as waste, and never decides what gets deleted.
- It writes the human-facing layer only: plain-English impact, the remediation command, the risk narrative.

Why this line is drawn here: remediation is irreversible. A hallucinated finding could delete a live volume. So the irreversible path carries **zero** AI — the AI advises, it does not adjudicate.

---

## Architecture

> **[ architecture diagram ]**
>
> _(image placeholder — to be inserted)_

Sample CUR → deterministic detectors → risk score → LLM enrichment (cached) → safety-gated remediation → API + dashboard.

---

## Safety model

- **Dry-run by default** — every remediation returns the command with `--dry-run`.
- **Command allowlist** — one approved verb per finding type; anything off-list is blocked, even if the LLM emits it.
- **Human confirmation** — real action requires an explicit `confirm=true`.
- **Never piped to a shell** — the command is rendered and shown for review, never executed.

> From the brief: _"Never auto-execute: dry-run flag + command allowlist + human confirmation required."_

---

## Cost discipline

- **$0 build** — a sample Cost & Usage Report, no AWS account, no live cloud.
- **Runs offline** with no API key (deterministic fallback path).
- **LLM enrichment cached by finding-type** — 10 findings cost 4 Opus calls; 10,000 resources across the same 4 waste classes still cost 4 calls.

A cost optimizer that practices what it preaches.

---

## Results

_Numbers verified from a clean checkout._

- **33 tests passing** — detection, API, enrichment, dashboard.
- **10 findings detected**, **$149.70/mo** waste (~$1,796/yr).
- **Aggregate risk 47/100 (Medium)**, rolled up from per-finding scores.
- **Runs at $0** on the deterministic fallback — no API key required.
- **Reproducible from a fresh clone** with the README steps alone.

---

## Deliberate deferred scope

_What I chose not to build, and why — judgment, not gaps._

- **Live cloud connectors** — detection had to be reproducible first. A pluggable adapter swaps the CSV reader for `boto3` later without touching the detectors.
- **Auto-remediation execution** — irreversible by nature. The safety model intentionally stops at "validated + proposed."
- **Multi-cloud** — one provider's waste model proven end-to-end beats four half-wired ones.

Every cut protects the thesis: correctness on the irreversible path.
