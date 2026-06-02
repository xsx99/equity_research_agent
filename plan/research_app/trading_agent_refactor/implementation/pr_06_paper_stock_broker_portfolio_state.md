# Implementation Module PR 6: Alpaca-Backed Paper Stock Broker and Portfolio State

## PR 6: Alpaca-Backed Paper Stock Broker + Portfolio State

**Goal:** Add Alpaca-backed common-stock paper execution and unified paper margin-account portfolio state after guarded trading decisions and deterministic risk approval. Alpaca paper trading is the stock execution/account source of truth; local paper tables are audit, reconciliation, and replay mirrors.

**Files:**
- Create/modify: `src/trading/paper_stock_broker.py`
- Create/modify: `src/trading/portfolio/state.py`
- Modify: `src/trading/repository.py`
- Modify: `src/trading/pipeline.py`
- Add ORM models/migration for `paper_orders`, `paper_executions`, `paper_positions`, `portfolio_snapshots`
- Test: `tests/trading/test_paper_stock_broker.py`
- Test: `tests/trading/test_portfolio.py`
- Add smoke script coverage for real Alpaca paper order submission and account/position sync.

Implementation notes:

- Consume only Pydantic-validated `TradingDecision` rows or safe fallbacks from PR 5.
- Sync Alpaca paper account/positions before risk evaluation when broker state may have changed; map synced paper positions, cash, buying power, margin requirements, and latest portfolio snapshots into the PR 4 `PortfolioContext` / `RiskContext` contract before calling `RiskManager`.
- Risk manager remains the final gate before paper order creation.
- Enforce long-only common-stock paper orders in V2. Bearish evidence may reduce/reject/downgrade, but direct short-stock paper orders should be rejected before order creation.
- Model stocks and options in one paper margin account view. PR 6 stock fills, cash balance, stock market value, account equity, stock margin requirement, total margin requirement, buying power, excess liquidity, margin model profile/version, and margin requirement source in `portfolio_snapshots` must come from Alpaca paper account/position sync when available.
- Use `margin_model_profile = "alpaca_paper_account"` and `margin_requirement_source = "broker_reported"` for broker-sourced stock snapshots. Keep `estimated_fidelity_like_conservative_v1` only as an explicit offline/replay/local-simulation fallback or future option overlay estimate. Do not claim exact Fidelity matching unless broker-observed values are imported.
- Reject or reduce stock orders when unified account buying power, total margin requirement, or excess-liquidity limits would be violated before submitting to Alpaca.
- Enforce manual request mode again at order creation: `review_only` cannot create a paper order even when an earlier decision was actionable.
- Paper stock broker must be idempotent for a trade date / ticker / strategy / action through a deterministic Alpaca `client_order_id`.
- Persist broker identifiers and state: `client_order_id`, broker order id, broker status, rejection reason, filled quantity, filled average price, submitted/fill timestamps, and linked trading/risk decision ids.
- Unit tests must mock Alpaca HTTP calls. Live Alpaca paper smoke checks must remain standalone and opt-in so unit tests do not spend API rate limits or mutate the paper account unexpectedly.

Already-written implementation adjustments:

- `src/trading/paper_stock_broker.py`: keep local guardrails and idempotency, but submit supported stock actions to Alpaca paper trading using `market` / `day` orders. Poll order status by `client_order_id`; create local execution records only from broker-reported filled state.
- `src/trading/portfolio/state.py`: keep the offline `PortfolioLedger` only for replay/local simulation. The live PR 6 workflow should build `PortfolioSnapshot` from Alpaca `/v2/account` and `StockPosition` rows from `/v2/positions`.
- `src/trading/workflows/paper_execution.py`: after a broker-reported fill, sync account and positions, replace local stock positions with broker-synced positions, persist the broker-sourced snapshot, and preserve local strategy/trade-identity metadata for mapped positions.
- DB/ORM/migration: keep `paper_orders`, `paper_executions`, `paper_positions`, and `portfolio_snapshots`, but treat them as application audit/reconciliation records. Include broker/client order identifiers and broker-sourced margin profile/source fields.
- Existing tests: replace local-fill assertions with mocked Alpaca order/account/position payload assertions. Keep guardrail tests for `review_only`, short-stock rejection, unsupported actions, and non-positive quantity rejection.
- Future PR 7/8 consumers: read PR 6 stock account/position state as broker-sourced. Option simulation and intraday rebalance must overlay or sync against the same account view, not create a separate local buying-power pool.

Stop after PR 6 for review/merge.

---
