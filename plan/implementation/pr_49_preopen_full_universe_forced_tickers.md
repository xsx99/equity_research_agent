# PR 49: Preopen Full Universe With Forced Ticker Evaluation

**Goal:** Change the live preopen scan so it always runs the provider full universe scan, while also guaranteeing `manual_include`, watchlist-derived includes, and active manual requests are present in the scan input and flow into signal/strategy evaluation.

**Design:** Keep the generic `apply_universe_filters()` semantics unchanged. Add the behavior at the live preopen universe adapter boundary:

- preopen dependencies instantiate `_ConfiguredLiveUniverseScanPipeline(full_scan=True)`
- full scan mode fetches provider universe assets first
- forced ticker assets are fetched by symbol and merged into the full universe
- forced tickers bypass scanner filter exclusions and appear in `UniverseSnapshotResult.included`
- explicit `manual_exclude` remains a hard exclusion
- scoped mode remains available for manual-review style targeted runs

**Verification Plan:**

- Add a failing unit test that full scan mode calls `fetch_universe_assets()`, supplements forced tickers, and includes forced tickers that would fail normal scanner filters.
- Keep/adjust the existing targeted-scope test to prove scoped mode does not call the full universe provider.
- Run focused runtime tests, then broader trading runtime tests if focused tests pass.

## Progress

- [x] Write failing tests.
- [x] Implement full-scan plus forced-include behavior.
- [x] Verify focused tests.
- [x] Update `plan/progress_tracker.md`.
