# Contributing

Small, reproducible changes are welcome. Include the user-visible behavior, a minimal case and relevant tests.

1. Use Python 3.11/3.12, `uv sync` and Node 22 for frontend development.
2. Run `uv run pytest -q` and `uv run ruff check src tests`.
3. For UI changes, run `npm ci`, `npm test` and `npm run build` in `frontend/`. Verify desktop/mobile and both locales. Commit the updated bundled assets.
4. Use synthetic fixtures. Never commit keys, actual customer data, private screenshots or application databases.
5. Keep offline tests network-free. Live provider qualification must be explicit, priced and separately reported.
6. Explain new numerical coefficients, provenance and uncertainty. Preserve pairwise experiment fairness, integer accounting and recovery invariants.

Useful issue reports include version, OS, minimal StudySpec without private text/keys, seed and expected/observed behavior. A replay should not require sharing credentials.

Before changing the model, read [methodology](docs/METHODOLOGY.md). A new channel needs executable behavior and tests, not a new display label. A new provider needs bounded costs, stage recovery and cancellation semantics.
