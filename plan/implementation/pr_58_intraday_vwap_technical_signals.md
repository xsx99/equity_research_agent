# Intraday VWAP Technical Signals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add regular-session VWAP metrics to canonical technical signals and carry them into live intraday rebalance requests.

**Architecture:** Add optional provider support for regular-session 1-minute bars, store those raw bars in the existing technical source payload, and keep derived VWAP calculations inside `src/trading/signals/technical.py`. Intraday refresh then reuses the same technical builder instead of duplicating calculations in runtime helpers.

**Tech Stack:** Python, pytest, existing Alpaca provider, existing source ingestion service, existing intraday runtime helpers

---

## File Map

- Modify `src/providers/market_data/types.py`: add `IntradayBar` and optional provider protocol method.
- Modify `src/providers/market_data/alpaca_provider.py`: implement `fetch_intraday_bars()`.
- Modify `src/trading/signals/source_ingestion.py`: attach `intraday_bars` to technical source payload when provider support exists.
- Modify `src/trading/signals/technical.py`: compute `vwap_now`, `price_vs_vwap_now`, `vwap_return_since_open`, `vwap_return_since_last_close`, and `vwap_ma_20`.
- Modify `src/trading/phases/intraday/helpers.py`: build refreshed technical values through the canonical technical builder.
- Test `tests/tools/test_market_data.py`: lock Alpaca request normalization.
- Test `tests/trading/test_signal_sources.py`: lock ingestion payload behavior.
- Test `tests/trading/test_technical_signals.py`: lock VWAP calculations.
- Test `tests/trading/test_runtime_intraday_live.py`: lock intraday refresh propagation.

## Task 1: Technical Builder VWAP Fields

- [x] Write a failing test in `tests/trading/test_technical_signals.py` that provides daily bars plus regular-session `intraday_bars` and asserts `vwap_now`, `price_vs_vwap_now`, `vwap_return_since_open`, `vwap_return_since_last_close`, and `vwap_ma_20`.
- [x] Run `source ~/.venv/bin/activate && pytest tests/trading/test_technical_signals.py::test_technical_signals_build_intraday_vwap_fields -q` and verify it fails because the fields do not exist.
- [x] Implement minimal VWAP helpers in `src/trading/signals/technical.py`.
- [x] Re-run the focused test and verify it passes.

## Task 2: Provider Intraday Bars

- [x] Write a failing test in `tests/tools/test_market_data.py` that exercises `AlpacaMarketDataProvider.fetch_intraday_bars()` with a fake client and verifies a 09:30 ET start, `1Min` timeframe, ascending normalized OHLCV bars, and no bars after `as_of`.
- [x] Run the focused test and verify it fails because `fetch_intraday_bars()` is missing.
- [x] Add `IntradayBar` and `fetch_intraday_bars()` to `src/providers/market_data/types.py`.
- [x] Implement `fetch_intraday_bars()` in `src/providers/market_data/alpaca_provider.py`, reusing existing Alpaca bars parsing conventions.
- [x] Re-run the focused provider test and verify it passes.

## Task 3: Source Ingestion Payload

- [x] Write a failing test in `tests/trading/test_signal_sources.py` that injects a fake market provider with `fetch_intraday_bars()` and asserts technical source payload includes `intraday_bars`.
- [x] Add a second assertion or test that a provider without `fetch_intraday_bars()` still succeeds with no `intraday_bars` key or an empty list.
- [x] Run the focused ingestion test and verify it fails because `_refresh_technical()` does not fetch intraday bars.
- [x] Update `SourceIngestionService._refresh_technical()` to call optional `fetch_intraday_bars()` through the existing market-bars resilience policy.
- [x] Re-run the focused ingestion tests and verify they pass.

## Task 4: Intraday Refresh Propagation

- [x] Write a failing test in `tests/trading/test_runtime_intraday_live.py` or a focused helper test that passes a technical source row with `intraday_bars` and asserts `_build_intraday_refresh_payload()` includes the VWAP fields in refreshed technical values.
- [x] Run the focused test and verify it fails because the helper currently only carries `last_price`, `atr_pct`, and `dollar_volume`.
- [x] Update `src/trading/phases/intraday/helpers.py` to call `build_technical_signals()` for technical rows and carry the computed VWAP fields while preserving current fallback behavior for missing price.
- [x] Re-run the focused intraday test and verify it passes.

## Task 5: Verification And Tracker

- [x] Run `source ~/.venv/bin/activate && pytest tests/trading/test_technical_signals.py tests/trading/test_signal_sources.py tests/trading/test_runtime_intraday_live.py tests/tools/test_market_data.py -q`.
- [x] Run `source ~/.venv/bin/activate && python -m compileall -q src`.
- [x] Run `git diff --check`.
- [x] Update this implementation plan checkboxes.
- [x] Add a completion entry to `plan/progress_tracker.md` with implementation summary and verification evidence.
