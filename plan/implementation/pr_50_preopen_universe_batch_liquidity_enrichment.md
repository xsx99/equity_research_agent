# PR 50: Preopen Universe Batch Liquidity Enrichment

**Goal:** Enrich live preopen full-universe assets with batched daily bars before applying `min_price` and `min_avg_dollar_volume`, while keeping provider requests bounded.

**Design:** Keep generic `apply_universe_filters()` deterministic and local. Add a provider-side batch daily-bars method for Alpaca and a live-universe adapter enrichment step that uses batched bars when available. Missing prices should be classified as `missing_price` rather than `below_min_price`.

**Scope:**
- Add `missing_price` and `missing_avg_dollar_volume` exclusion reasons for absent scanner inputs.
- Add an Alpaca multi-symbol daily-bars helper that requests symbols in chunks.
- Enrich full-universe assets from batched bars in `LiveUniverseProvider.fetch_universe_assets()`.
- Keep targeted symbol enrichment behavior unchanged.
- Do not add profile/sector/context enrichment in this slice.
- Add a standalone low-volume smoke script for manually checking a small ticker list without scanning the full universe.

**Verification Plan:**
- Write failing unit tests for `missing_price` and batched enrichment.
- Run focused tests:
  - `source ~/.venv/bin/activate && pytest tests/trading/test_universe.py tests/trading/test_runtime_live.py -k "missing_price or batch or live_universe_provider" -q`
- Run broader relevant tests:
  - `source ~/.venv/bin/activate && pytest tests/trading/test_universe.py tests/trading/test_runtime_live.py tests/trading/test_runtime_manual_review_live.py -q`
- Validate the smoke wrapper without live API calls:
  - `source ~/.venv/bin/activate && pytest tests/scripts/test_run_trading_universe_batch_enrichment_smoke.py -q`

## Progress

- [x] Write failing tests.
- [x] Implement batch daily-bars enrichment.
- [x] Verify focused and broader tests.
- [x] Update `plan/progress_tracker.md`.
