# Cumulative Portfolio P&L Reconciliation

**Date:** 2026-08-14  
**Status:** Approved for implementation planning  
**Scope:** Alpaca-backed paper-stock portfolio snapshots, `/today` account P&L KPIs, and an explicit historical snapshot backfill.

## Problem

The dashboard currently reports cumulative realized and unrealized P&L as zero even though the paper account has closed and open stock trades. The broker-account mapper reads `realized_pl` and `unrealized_pl` keys that are absent from the Alpaca account payload and silently defaults both values to zero. The header sometimes repairs unrealized P&L from open position rows, but lazy position loading means the value changes by selected tab.

The local execution mirror also stores `net_cash_effect` as negative for every filled stock order. A filled sell therefore has the wrong cash-flow sign. This column cannot be trusted as the source for historical P&L until it is repaired.

The requested operator-facing meaning is:

- `realized_pnl`: cumulative realized stock-trading P&L since the paper account started at $1,000,000;
- `unrealized_pnl`: mark-to-market P&L of all currently open stock positions at the snapshot time;
- historical `portfolio_snapshots` must be backfilled to the same point-in-time meaning;
- all `/today` tabs must display the same values for the same latest snapshot.

## Options Considered

### 1. Replay local fills and reconcile to account equity — selected

Replay filled stock executions in time order. Buys add quantity and cost; reductions/exits realize the difference between sale price and the current weighted-average cost. At each snapshot, unrealized P&L is broker stock market value minus the replayed cost basis still open at that time. Compare realized plus unrealized with account equity minus the configured $1,000,000 baseline and retain any difference as a reconciliation residual.

This keeps realized and unrealized semantically distinct, supports point-in-time backfill, and exposes missing activities instead of hiding them.

### 2. Derive realized only from the account identity

Compute `realized = equity - baseline - unrealized`. This is simpler, but transfers, dividends, fees, interest, and missing activities would be mislabeled as realized trading P&L.

### 3. Rebuild from Alpaca account activities

Fetch and page through broker activities. This could eventually provide the most complete ledger, but introduces a new external dependency and rate-limit/failure surface. It is outside this focused repair.

## Design

### Pure stock P&L ledger

Add a small pure domain component under `src/trading/portfolio/` that consumes normalized filled-stock events:

```text
execution_id, ticker, executed_at, action, quantity, fill_price
```

Supported actions:

- `enter_long` and any supported long increase add quantity at fill price and update weighted-average cost;
- `reduce` and `exit` match no more than the currently open quantity and realize `(fill_price - average_cost) * matched_quantity`;
- zero/non-positive quantities and prices are rejected;
- a sell larger than the replayed open quantity is an explicit reconciliation error, not an invented short position;
- `execution_id` is required and unique within the replay input;
- event ordering is deterministic by `(executed_at, execution_id)`.

The component exposes cumulative realized P&L and the remaining quantity/cost basis by ticker at any requested cutoff. It must not depend on SQLAlchemy, broker clients, or the dashboard.

The initial implementation covers stock executions only. Broker or simulated option activity is not silently folded into stock realized P&L; any account-level difference remains visible in the reconciliation residual.

### Live portfolio sync

The broker portfolio sync already has the current broker positions before saving the snapshot. Extend the sync boundary to load normalized filled-stock events through the repository and enrich the broker account snapshot before persistence. Both live sync and historical backfill use the replayed ledger cost basis; broker `average_entry_price` is an independent reconciliation input, not an alternative P&L basis:

```text
realized_pnl   = ledger cumulative realized at snapshot time
unrealized_pnl = broker_stock_market_value - replayed_open_stock_cost_basis
total_pnl      = account_equity - configured starting equity
residual       = total_pnl - realized_pnl - unrealized_pnl
```

The starting equity defaults to `$1,000,000` through one explicit portfolio-P&L configuration value; it is not duplicated in presenter or backfill code. The replay boundary is the latest persisted portfolio snapshot that represents a clean account reset:

- has `account_equity` equal to the configured starting equity within currency tolerance;
- has zero `stock_market_value` and zero `option_market_value`;
- has no filled execution at the exact same timestamp; an ambiguous same-time candidate is skipped.

That snapshot time becomes `pnl_tracking_started_at`. Only executions and snapshots at or after this boundary belong to the active account lifecycle; earlier rows are excluded from calculation and are not modified by the backfill. Selecting the latest clean reset makes repeated paper-account resets deterministic. The backfill and live calculation abort if no valid boundary exists, if the first post-boundary state contains initial inventory without a corresponding buy execution, or if post-boundary execution history is incomplete. The chosen boundary and excluded pre-boundary row counts are written to snapshot metadata and dry-run output.

At live sync and for the latest repair cutoff, replayed open quantity per ticker must equal broker/local mirrored quantity within a small numeric tolerance. Replayed weighted-average cost must also agree with the broker average entry price within a currency tolerance. A quantity mismatch, missing initial inventory, duplicate execution id, or oversell is a validation failure and blocks persistence/backfill. A small cost mismatch is recorded as a reconciliation diagnostic and the replayed cost basis remains authoritative; a material cost mismatch is a validation failure. Dry-run output lists every mismatch and tolerance applied.

Historical `paper_positions` are lifecycle rows rather than point-in-time position snapshots, so a non-flat historical `stock_market_value` cannot prove its per-ticker quantities. The repair therefore leaves every non-flat historical snapshot untouched and reports its exact unverified count/range. It repairs flat historical snapshots, whose zero inventory is independently checkable, and the latest snapshot, whose replayed quantities and costs are checked against the current broker mirror. This narrows the original backfill scope to avoid fabricating historical unrealized P&L from incomplete fills.

Snapshot metadata records:

```json
{
  "pnl_calculation_method": "weighted_average_stock_fills_v1",
  "pnl_starting_equity": 1000000.0,
  "pnl_tracking_started_at": "2026-06-01T13:00:00+00:00",
  "pnl_reconciliation_residual": -6.45,
  "pnl_fill_count": 82
}
```

A residual is diagnostic only. The implementation does not force realized P&L to make the account identity balance. A configurable or module-level small tolerance controls whether the metadata also marks the snapshot as reconciled; it does not change the displayed P&L.

If the execution history cannot be loaded or is internally inconsistent, live sync must fail before persisting a misleading snapshot. Existing broker account and positions remain untouched.

### Cash-effect direction

When creating a future `PaperExecutionRecord`:

- long buy: `net_cash_effect = -quantity * fill_price`;
- reduce/exit sell: `net_cash_effect = +quantity * fill_price`.

The calculation uses the order action already available when the record is created. P&L replay uses action and fill price directly rather than trusting `net_cash_effect`.

The historical backfill repairs the sign of existing sell execution rows after validating the joined order action. It does not alter quantity, price, order status, or broker identifiers.

### Historical backfill

Provide a standalone, explicit script under `scripts/` with dry-run as its default. The script:

1. loads filled stock executions joined to their order action;
2. locates and validates the account-lifecycle replay boundary;
3. validates unique execution ids and replays post-boundary events in deterministic order;
4. walks portfolio snapshots in ascending time order;
5. computes point-in-time realized P&L and remaining stock cost basis;
6. computes snapshot unrealized P&L from `stock_market_value - remaining_cost_basis`;
7. validates point-in-time quantities wherever a mirrored position state is available and validates the latest state against broker/local mirrored positions;
8. updates realized/unrealized fields and merges calculation metadata only when `--apply` is supplied;
9. repairs sell `net_cash_effect` signs only with `--apply`;
10. commits in one database transaction and rolls back on any validation failure.

Dry-run output includes the selected replay boundary, row counts, earliest/latest updated snapshot, latest calculated P&L, maximum absolute reconciliation residual, quantity/cost mismatches with tolerances, sell cash-effect repair count, and validation errors. Re-running `--apply` produces the same values and no additional changes.

The script must verify that PostgreSQL uses a persistent, non-temporary data directory before applying changes, following `documents/general_instructions.md`.

### Dashboard consistency

The header uses the latest persisted snapshot for both realized and unrealized P&L. It no longer changes the header value according to whether the selected tab happened to load positions. Position-table unrealized P&L remains independently calculated per row and is covered by a consistency test against the latest snapshot using the same documented currency tolerance allowed for small broker-versus-replay cost differences.

No template or CSS change is needed. Existing currency formatting and positive/negative tone remain in place.

## Data and Compatibility

- No schema migration is required; `portfolio_snapshots` already has realized/unrealized numeric columns and JSON metadata.
- Repository interfaces gain a focused read model for filled stock events rather than exposing ORM rows to the domain ledger.
- The normalized read model includes the stable `paper_execution_id` as `execution_id`; duplicate ids are rejected before replay.
- Existing snapshot consumers keep the same field names and types.
- Existing snapshots are changed only by the explicit backfill command.
- The backfill is production-data mutation and is not run automatically by tests, migrations, application startup, or deployment.

## Testing

Follow red-green-refactor for each behavior.

1. Pure ledger tests:
   - profitable and losing round trips;
   - multiple buys followed by partial and complete reductions;
   - deterministic ordering;
   - invalid values and oversell rejection;
   - duplicate execution-id rejection and equal-timestamp stable ordering;
   - cutoff behavior for historical snapshots.
2. Broker/repository tests:
   - future buy/sell cash-effect signs;
   - normalized event loading;
   - live snapshot enrichment and residual metadata;
   - missing boundary, initial inventory, quantity mismatch, and material cost mismatch failures;
   - persistence is skipped on invalid execution history.
3. Backfill tests:
   - dry-run performs no writes;
   - `--apply` updates historical snapshots and sell cash effects atomically;
   - a second run is idempotent;
   - persistent PostgreSQL directory guard blocks unsafe apply mode.
4. Dashboard tests:
   - all selected tabs return identical latest realized/unrealized values;
   - header values come from the latest snapshot;
   - current position sum agrees with latest snapshot unrealized P&L.
5. Verification:
   - focused portfolio, broker, repository, script, and web suites;
   - full unit suite;
   - compile and `git diff --check`;
   - dry-run against the real database;
   - apply only after reviewing dry-run output;
   - render `/today` and inspect the KPI row on at least Overview, Risk & Macro, and System.

## Acceptance Criteria

- The latest production snapshot displays cumulative realized stock P&L near the independently diagnosed `-$11.07k`, not zero.
- Unrealized P&L reflects current broker positions and is not zero unless the actual open-position sum is zero.
- The same latest realized/unrealized values appear on every `/today` tab.
- Verifiable flat historical snapshots and the fully validated latest snapshot are backfilled after an explicitly approved apply run; non-flat historical snapshots remain unchanged and are explicitly reported as unverified.
- Future sell executions have positive cash effect and buys have negative cash effect.
- Reconciliation residuals are auditable and never silently added to realized P&L.
- Tests and the standalone dry-run demonstrate that no production data changes occur without `--apply`.

## Out of Scope

- Fetching Alpaca account activities.
- Full option realized-P&L attribution.
- Tax-lot methods other than weighted-average cost.
- Changing account equity, broker positions, orders, or fill prices.
- Automatically running the production backfill during deployment.
