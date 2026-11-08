# Guided market study implementation plan

> **For agentic workers:** Use subagent-driven development for independent UI/numerical work and native execution for service/evidence integration.

**Goal:** Launch understandable campaigns in a few clicks and explore age, channels, alternatives, switching and barriers through an evidence-aware market report.

**Architecture:** Guided UI calls one free/offline prepare-and-launch operation; existing durable workers run the numerical comparison. A deterministic market analysis combines full-population aggregates with bounded research provenance.

**Tech Stack:** Existing Python/Pydantic/FastAPI/NumPy/SQLite, React/TypeScript and Playwright; no new dependencies.

**Spec:** `docs/superpowers/specs/2026-11-08-guided-market-study-design.md`.

## Global constraints

- Preserve current local studies, credentials, page analysis and worker recovery; no additional paid tests.
- Existing campaign mathematics stay neutral; only discovery enables explicit switching assumptions.
- Do not invent competitors, market size, demographics or real migration counts.
- Keep MiroFish-inspired white/black/orange identity and expose technical controls only progressively.

## Review focus

- Old saved specifications without the new fields remain loadable and runnable.
- Empty/failed/demonstration research cannot produce a factual market claim.
- All-zero/small-sample/tied results cannot produce a confident target/channel winner.
- Switching counts reconcile with buyers, and every age band reconciles with the full population.
- Guided launch must never silently enable paid search, inference or remote screenshots.

### Task1: Numerical segmentation and switching

**Owner:** core agent. **Files:** models.py, simulation.py, reports.py, focused numerical tests and legacy projection exclusions.

**Produces:** defaulted objective/market specification; scenario age_segments and market_switching; validation means/intervals; numeric11 checkpoint compatibility.

- [x] Write failing boundary/reconciliation/neutrality/resume tests.
- [x] Implement isolated switching streams, friction on all adoption routes and full-population aggregates.
- [x] Pass focused tests and ordinary legacy fixture projections; document exact interfaces to integration owner.

### Task2: Evidence-aware market report and guided launch

**Owner:** root. **Files:** market_analysis.py, services.py, api.py, exports.py and tests.

**Consumes:** StudySpec and current TrendReport plus validation summaries. **Produces:** `build_market_analysis(spec,research,report)->dict`; `POST /api/v1/studies/launch {spec}` returning `{study,run,research_error?}` without any implicit paid research.

- [x] Test source/demo separation, competitor references, unknown market size, inconclusive rankings and migration subset reporting.
- [x] Implement grounded excerpts, conditional age/channel suggestions, barriers and next actions; preserve JSON/CSV/HTML/MD exports.
- [x] Test and implement no-source/free-URL guided launch; retain created study if research fails and expose a warning.

### Task3: Guided frontend and verification

**Owner:** frontend agent. **Files:** frontend source/types/styles/tests/design documents; built bundled assets after checks.

**Consumes:** guided launch API and market_analysis report. **Produces:** two intuitive objectives, minimal inputs, automatic product-adapted strategies, advanced disclosures and readable market results.

- [x] Test both objectives, few-click launch, old-study compatibility and advanced access.
- [x] Implement guided entry and early market result panels; preserve original laboratory/page controls.
- [x] Inspect ready desktop/mobile views in isolated data; independent UX review.

### Task4: Final integration and distribution

- [ ] Full Python/frontend checks and actual worker/export smoke; independent review of new data and UI boundaries.
- [ ] Rebuild and requalify current wheel/source, current six-job CI, source/credential/archive checks.
- [ ] Publish only the final matching artifacts, keep local app on the latest build and report concrete limitations.
