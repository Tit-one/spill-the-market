# Core and page-analysis implementation interfaces

Root owns shared `models.py`, API/jobs/CLI, packaging and integration. Independent workers own only the files in their assignment. All outputs are JSON serializable. `StudySpec` is the canonical browser/CLI payload. Currency values are integer cents, summary means may be floats.

## Engine

- `personas.generate_personas(product: ProductSpec, audience: AudienceSpec, research: TrendReport | None = None, seed: int = 42, limit: int = 200) -> list[Persona]`: bounded displayed representatives, not the numerical population.
- `media.propose_plans(product: ProductSpec, audience: AudienceSpec, budget_cents: int, research: TrendReport | None = None) -> list[MediaPlan]`: exactly three editable product-aware candidates.
- `media.channel_catalog() -> list[dict]`: executable channel/format/cost assumptions.
- `simulation.simulate_scenario(product, audience, plan, days, seed, *, research=None, fatigue_multiplier=1.0, price_elasticity=1.0, on_day=None, checkpoint_path=None, cancel_check=None) -> dict`: numeric individuals. Checkpoint includes deterministic stream/state; cancel raises `SimulationCancelled`.
- `simulation.compare_strategies(spec: StudySpec, plans: list[MediaPlan], *, research=None, on_progress=None, checkpoint_dir=None, cancel_check=None) -> dict`: three candidates plus baseline per distinct price, exploration/validation seeds, bounded cached replicas, reproducible resume. Progress callback receives dict with percent, message, day, scenario. Use own reports.py for financial/statistical summaries.
- Report contract: `schema_version`, `engine_version`, `product`, `population`, `rounds`, `seed`, `winner_id` (nullable), `winner_reason`, `assumptions` (strings), `personas` (bounded), `scenarios` (list), `comparisons` (list), `metadata` (dict). Scenario: `plan_id`, `name`, `is_baseline`, `price_cents`, `mean_revenue_cents`, `median_revenue_cents`, `revenue_interval_cents`, `mean_units`, `mean_spend_cents`, `mean_cac_cents` (nullable), `mean_paid_cac_cents` (nullable), `daily`, `channels`, `traces`, `adjustments`, `replicate_totals`.
- Daily rows: `day`, `units`, `revenue_cents`, `spend_cents`, `cumulative_units`, `cumulative_revenue_cents`, `cumulative_spend_cents`, `mean_intention`, `mean_fatigue`. Channels: `channel`, `impressions`, `unique_reach`, `clicks`, `units`, `revenue_cents`, `spend_cents`, `attributed_conversion_rate`, `exposed_purchase_rate`, `cac_cents`.

## Research / memory / gateway

- `research.run_research(request: ResearchRequest, product: ProductSpec, *, ledger=None) -> TrendReport`: async. Offline/demo do not use network, including inference. `demo` source URLs must be visibly synthetic. `live` requires explicitly configured provider and known reserved cost.
- `memory.LocalMemory(path)` with `ingest_report(study_id, report)`, `search(study_id, query, limit=10) -> list[dict]`, `add_belief(study_id, persona_id, text, source_ids)`, `graph(study_id) -> dict`, `import_mirofish(study_id, path) -> dict`; strict study isolation and source/synthetic status.
- `gateway.BudgetLedger(path, limit_usd, max_calls=300)` with `reserve(provider, maximum_usd, metadata=None) -> str`, `settle(reservation_id, actual_usd, usage=None)`, `mark_uncertain(reservation_id)`, `summary() -> dict`. Immutable initial limit, transactional concurrency checks, unknown charges remain reserved. All provider clients use it. `BudgetExceeded` public exception.
- Optional `gateway.SemanticClient` uses OpenAI-compatible HTTP only when explicitly configured, known prices/output limits, and returns schema-validated JSON through ledger. No private credentials copied into source or fixtures. Costs in USD separate from study currency.

## Browser-facing API

- GET `/api/v1/bootstrap` -> `{version, session_token, capabilities, channels, examples, provider_status}`. Session token required as `X-Spill-Token` for writes. Local origin only.
- POST `/api/v1/studies` with `{spec: StudySpec}` -> study `{id,spec,plans,research,personas,created_at}`. Preparation here is offline only. Live research is a separate explicit request.
- GET `/api/v1/studies`, GET `/api/v1/studies/{id}`, PUT `/api/v1/studies/{id}/plans` with `{plans:[MediaPlan]}`.
- POST `/api/v1/studies/{id}/research` body optional ResearchRequest -> `{report, cost}`; POST `/api/v1/studies/{id}/runs` with `{plans?:[MediaPlan]}` -> `{id,study_id,status,progress}`.
- GET `/api/v1/runs/{id}` -> run `{id,status,progress,error,report?}`; POST `/api/v1/runs/{id}/cancel` and `/resume`. GET `/api/v1/runs/{id}/events` SSE. Polling supported.
- GET `/api/v1/runs/{id}/export?format=json|csv|html|md`.
- GET `/api/v1/studies/{id}/memory?q=...`; GET `/api/v1/roadmap` -> module 5 available, autonomous interaction remains future.
- Demo examples: `game` and `software` IDs in bootstrap with their complete StudySpec. Browser can edit product/age/population/rounds/spend/repetitions/plans and then run. Keep global language toggle EN/FR, accessible keyboard states, mobile layout, actual charts/table/source traces. No external trackers/fonts; Phosphor icons. App brand: expressive blue/ink/white working launch notebook, not generic SaaS cards. First viewport shows a real experiment with editable brief and strategy timeline. Core charts with SVG allowed; no hand-drawn icons.

## Runtime

Root worker calls engine with checkpoint_dir and cancellation callback, persists progress in SQLite. Files under application-data directory (platformdirs); tests under tmp_path. The worker owns each run; parent API never performs CPU simulations in request context. No real campaigns, payments or browsing agent in this version.

## Page analysis (v0.2)

Canonical contracts: `page_models.py`. `PageAuditSpec` accepts one/two variants (A/B), desktop/mobile views, section limit, bounded persona/direct-control sample and prior advertisement context. Sources are demo, public URL, offline HTML or base64-encoded images; browser requests never supply local file paths.

- GET `/api/v1/page-audit/providers` -> public provider descriptors plus Chromium availability.
- GET/POST `/api/v1/studies/{id}/page-audits` -> `{audits:[...]}` / queued audit (202). Capture makes no inference requests.
- GET `/api/v1/page-audits/{id}` -> persisted phase/status/progress/captures/report/cost/error. Cost is the shared study ledger, not an audit-only subtotal. Original HTML/base64 bodies and worker leases remain internal.
- POST `/{id}/analyze` with `{provider_id:demo|configured|local,allow_remote:false}` ->202. Explicit remote consent, known rates, vision opt-in and positive study budget required. Demo is restricted to fictional captures.
- POST `/{id}/cancel`, `/{id}/resume`; GET `/{id}/images/{snapshot_id}` (manifest-scoped JPEG), `/{id}/export?format=json|csv|html|md`.

The worker claims a fresh attempt nonce and registers its actual interpreter PID/creation time, including Windows virtual-environment launchers. Committed captures remain visible after cancellation. Analysis stages are journaled individually; uncertain dispatches block replay.

`capture_pages(spec, assets_dir, on_progress=..., cancel_check=...)` yields viewport-sized snapshots. `analyze_page_audit(audit, assets_dir=..., ledger=..., journal_path=..., provider_id=..., allow_remote=...)` returns `PageAuditReport`. Each reader context contains one persona and its own history. A/B comparisons use the common exposure horizon and disclose unequal coverage. Proposed actions are recorded under a fixed inspection schedule; they are not autonomous navigation.
