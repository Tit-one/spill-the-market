# Product-page analysis implementation plan

**Goal:** Implement the previously approved module 5: local captures, grounded visual observations and progressive reactions from the study's age-bounded personas.
**Spec:** ../../PAGE-ANALYSIS.md and the user's explicit request to develop it on 8 November 2026.
**Architecture:** Independent persisted page-audit jobs and local assets; isolated capture subprocess; a bounded observer/persona pipeline sharing the study's real-services ledger. Existing numerical sales simulation stays independent.
**Stack:** Python/FastAPI/Pydantic/SQLite, Playwright Chromium, Pillow, existing compatible-provider HTTP conventions, React/TypeScript.

## Decisions and constraints

- Reuse the approved shared-observer approach plus a small blind direct-image control. Calling a vision model separately for every synthetic individual is unnecessary; reports disclose the sampled personas.
- Accept one or two page variants, rendered public URLs, untrusted HTML, imported images or an explicitly fictional offline demonstration. Capture and analysis are separate actions.
- New browser contexts have no personal cookies, no application-origin access, no downloads, and bounded public-resource retrieval. HTML imports execute with networking and JavaScript disabled. Record blocked/missing resources and truncated capture coverage.
- Images and DOM remain local until the user explicitly chooses a configured remote provider and authorizes transmission. A local vision backend remains possible. No credentials are copied, created or billed during development.
- Each persona receives only its current viewport and its own prior reactions. Product specifications, observer recommendations, later sections and the other page variant must not leak into first impressions.
- Use actual ages and diverse needs/trust/budgets; no deterministic age stereotype. Pair A/B profiles, exposure order and initial intentions; pair direct-image controls with the same persona.
- Every finding cites snapshot and evidence IDs; visual uncertainty and interpretation are separate from observed text. Outputs are synthetic hypotheses, never real conversion measurements.
- Paid stages are durably journaled; dispatch uncertainty blocks automatic replay. Capture jobs and inference run outside the HTTP request process. Cancellation preserves committed stages.

## Tasks

- [x] Contracts/persistence/API: page_models.py, page_store.py, page_jobs.py, page_worker.py, page_api.py; install routes before frontend mount; API/CLI integration and isolation/idempotency regressions.
- [x] Capture: page_capture.py + tests; local image normalization, bounded viewport capture, visible DOM boxes, public-resource isolation, real Chromium qualification.
- [x] Observer/persona pipeline: page_vision.py + page_analysis.py + tests; provider descriptors, image-aware bounds/accounting, stage cache, progressive prompts, blind direct controls and paired A/B findings.
- [x] Interface: PageAnalysis.tsx + isolated types/styles/tests, existing App tab; capture/import/consent/analyze/progress/evidence/reactions/comparison/export, bilingual/mobile.
- [x] Release preparation: focused regressions then full tests/build, actual capture/browser/installed worker checks, scoped independent review, current docs and downloadable package. Publication is gated on terminal CI success; the exact release run and assets are recorded in the GitHub release notes.

## Review focus

Cross-study asset access; private-network/redirect/resource capture; misleading DOM-only visual claims; unseen-information leakage; duplicate or uncertain billed work; delayed UI responses crossing study boundaries; A/B comparisons with mismatched people or exposure; missing browser/provider actionable errors.
