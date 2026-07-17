# PR 51: Late Fill Reconciliation And Closed Trade UI

**Date:** 2026-07-17

## Goal

Fix the CRDO-shaped failure where Alpaca paper orders fill after the immediate polling window, leaving local `paper_orders` stale, no `paper_executions`, and a misleading `/today?tab=trades` closed-position detail.

## Scope

1. Add a stock-order late-fill reconciliation path that refreshes non-terminal local paper stock orders against Alpaca, persists filled order status, saves missing executions, and refreshes broker-sourced positions.
2. Tighten the `/today` trades workspace so the `closed_today` bucket only means positions closed on the current trade date; older closed rows remain available as recent closed context but should not be selected by default as current work.
3. Keep the fix local to existing paper stock execution, portfolio sync, and today presenter/loader boundaries. No schema change.

## Implementation Plan

- Add tests first:
  - Broker/order reconciliation should turn a stale accepted order into a filled order plus a persisted execution when Alpaca now reports `filled`.
  - Portfolio sync/workflow integration should call this reconciliation before/around broker position sync.
  - Today workspace should not put a historical closed position into `closed_today` when `as_of` is a later date.
- Implement minimal repository support to load refreshable stock orders.
- Implement a small reconciliation helper in the stock execution/portfolio-sync boundary using existing `PaperStockBroker.refresh_order`.
- Update the workspace presenter to date-filter closed positions for the `closed_today` bucket and expose older closed rows separately only if needed by templates/tests.
- Verify with focused tests, full affected test modules, compile, `git diff --check`, and rendered `/today?tab=trades` smoke.

## Verification

Run after implementation:

```bash
source ~/.venv/bin/activate && pytest tests/trading/test_paper_stock_broker.py tests/trading/test_portfolio_sync.py tests/web/test_today_workspace.py -q
source ~/.venv/bin/activate && pytest tests/web -q
source ~/.venv/bin/activate && pytest tests/trading/test_paper_stock_broker.py tests/trading/test_portfolio_sync.py -q
source ~/.venv/bin/activate && python -m compileall -q src
git diff --check
```

If the local app can run, render `/today?tab=trades&ticker=CRDO` and confirm CRDO is not shown as a current closed item unless its `closed_at` is the current local trade date.
